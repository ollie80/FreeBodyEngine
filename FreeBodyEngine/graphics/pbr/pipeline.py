"""PBRPipeline: PBRPipeline draws the active scene's tilemaps/sprites/debug
draws/3D models into a multi-attachment G-buffer, runs a deferred lighting
composite pass over it (see graphics/pbr/lighting.py for the Light node
types and graphics/pbr/shaders.py for the composite/forward shader source),
then forward-shades any transparent objects on top, and finally presents the
result.

Frame structure:
  1. Opaque/additive geometry (blend_mode OPAQUE/ADDITIVE - see
     graphics/material.py's BlendMode) is queued via Renderer.submit() and
     drawn into the G-buffer via Renderer.flush_opaque() - state-minimizing
     batching (see graphics/instancing.py), not GPU instancing.
  2. If a shadow-casting DirectionalLight3D exists, its shadow map is
     rendered first (a depth-only pass from the light's own view/projection
     - see _render_shadow_map()) so step 3 can sample it.
  3. A single fullscreen composite pass (_draw_composite) reads the
     G-buffer back and accumulates every active light (up to
     graphics.pbr.shaders.MAX_LIGHTS) into the 'lit' attachment - one
     fragment-shader loop over the whole screen, not one draw call per
     light. This is what keeps lighting itself cheap regardless of light
     count (within MAX_LIGHTS).
  4. Transparent geometry (blend_mode TRANSPARENT) is forward-shaded
     directly onto 'lit' via Renderer.flush_transparent(), since a deferred
     G-buffer can only hold one opaque surface per pixel and can't
     represent a blended one at all.
  5. 'lit' (now `output_channel`'s default) is blitted to the window.

Why light data is MAX_LIGHTS flat uniform slots, not a real uniform array or
an FBUSL `@buffer` block: `@buffer` blocks exist in FBUSL's grammar but
GL33Generator's own docstring says GL33 "has no real SSBOs" and implements
them via buffer-texture reads restricted to `readonly` - written for the
raytrace/compute-kernel path (see graphics/gl33/compute.py), not proven for
an ordinary vertex/fragment Shader. A true GLSL uniform array (`vec4[32]`)
is representable in FBUSL's type grammar, but GLShader.set_uniform's
GL-call dispatch (graphics/gl33/shader.py's set_gl_uniform) only issues
single-element glUniform*/glUniformMatrix* calls, never the *v variants an
array uniform needs. Flat per-slot uniforms (`Light0_Color`, `Light1_
Color`, ...) use only already-proven scalar/vector uniform plumbing - lower
risk than exercising either untested path for this rebuild, at the cost of
MAX_LIGHTS being a hard cap that costs a shader recompile to raise (see
graphics/pbr/shaders.py).
"""
import math

from FreeBodyEngine.graphics.pipeline import GraphicsPipeline
from FreeBodyEngine.core.scene import SceneManager
from FreeBodyEngine import get_service
from FreeBodyEngine.graphics.color import Color
from FreeBodyEngine.graphics.pbr.material import PBRMaterial
from FreeBodyEngine.graphics.pbr.lighting import Light, LightType
from FreeBodyEngine.graphics.pbr.shaders import MAX_LIGHTS, LIGHTING_COMPOSITE_VERT, LIGHTING_COMPOSITE_FRAG

from FreeBodyEngine.graphics.framebuffer import AttachmentFormat, AttachmentType
from FreeBodyEngine.core.tilemap.renderer import TilemapRenderer
from FreeBodyEngine.graphics.sprite import Sprite2D, Sprite
from FreeBodyEngine.graphics.debug import Debug2D
from FreeBodyEngine.graphics.model.model import Model3D

from FreeBodyEngine.math import Transform, Vector3, Vector
from FreeBodyEngine.core.camera import Camera
from FreeBodyEngine.graphics.mesh import Mesh, generate_quad
from FreeBodyEngine.graphics.material import Material
from fbusl.injector import Injector

import numpy as np

SHADOW_MAP_SIZE = 2048


class PBRPipeline(GraphicsPipeline):
    """GraphicsPipeline for physically-based rendering - see module
    docstring for the full frame structure."""
    def __init__(self):
        """Adds 'scene_manager' as a service dependency, alongside GraphicsPipeline's own 'renderer' dependency."""
        super().__init__()
        self.dependencies.append('scene_manager')

    def on_initialize(self):
        """Fetches the 'scene_manager' service, creates `main_framebuffer`
        (the G-buffer plus a 'lit' attachment the composite/forward passes
        write into), compiles the internal composite/shadow shaders, and
        creates the shadow-map framebuffer. `output_channel` defaults to
        'lit' - still overridable to any other G-buffer channel for
        debugging (e.g. 'albedo', 'gWorldNormal')."""
        super().on_initialize()
        self.scene_manager = get_service('scene_manager')
        self.scene_manager: SceneManager

        self.main_framebuffer = self.renderer.create_framebuffer(int(get_service('window').framebuffer_size[0]), int(get_service('window').framebuffer_size[1]), {
            'albedo': (AttachmentType.COLOR, AttachmentFormat.RGBA8),
            'normal': (AttachmentType.COLOR, AttachmentFormat.RGBA8),
            'emmision': (AttachmentType.COLOR, AttachmentFormat.RGBA8),
            'roughness': (AttachmentType.COLOR, AttachmentFormat.R8),
            'metallic': (AttachmentType.COLOR, AttachmentFormat.R8),
            # World-space position/normal, at full float precision (unlike
            # the 8-bit color channels above) since these carry real scene
            # coordinates, not normalized [0, 1] color - order matches
            # default_shader.fbfrag's `gWorldPos`/`gWorldNormal` @output
            # declaration order exactly, which is what actually binds a
            # fragment shader's `out` variable to a given color attachment
            # (see GLFramebuffer's attachment-index assignment).
            'gWorldPos': (AttachmentType.COLOR, AttachmentFormat.RGBA32F),
            'gWorldNormal': (AttachmentType.COLOR, AttachmentFormat.RGBA32F),
            # The lighting composite/forward-transparent passes' sole
            # output - kept as its own attachment on the *same* FBO
            # (rather than a separate framebuffer) so both passes can share
            # the opaque pass's depth buffer for correct transparent
            # occlusion, isolated via set_draw_buffers() so they don't also
            # clobber the G-buffer channels above (see _draw_composite()).
            'lit': (AttachmentType.COLOR, AttachmentFormat.RGBA8),
            'depth': (AttachmentType.DEPTH, AttachmentFormat.DEPTH24)
        }, transparent = True
        )
        self._gbuffer_attachments = ['albedo', 'normal', 'emmision', 'roughness', 'metallic', 'gWorldPos', 'gWorldNormal']
        self.output_channel = 'lit'

        self.ambient = Vector3(0.03, 0.03, 0.03)

        files = get_service('files')
        self._composite_shader = self.renderer.load_shader(LIGHTING_COMPOSITE_VERT, LIGHTING_COMPOSITE_FRAG, Injector(), None)
        self._composite_quad = generate_quad(2.0, 2.0)
        self._identity_model = np.identity(4, dtype=np.float32)

        self._shadow_shader = self.renderer.load_shader(
            files.get_file('engine://shader/shadow_depth.fbvert'),
            files.get_file('engine://shader/shadow_depth.fbfrag'),
            Injector(), None,
        )
        self._shadow_framebuffer = self.renderer.create_framebuffer(SHADOW_MAP_SIZE, SHADOW_MAP_SIZE, {
            'depth': (AttachmentType.DEPTH, AttachmentFormat.DEPTH32F),
        })

    def draw_world_mesh(self, mesh: Mesh, material: Material, transform: Transform, camera: Camera, instances: int = 1):
        """Queues `mesh`/`material`/`transform` for drawing against `camera`
        via Renderer.submit() (see Renderer.flush_opaque()/
        flush_transparent() for when queued calls actually get drawn).
        `instances` is accepted but unused - see graphics/instancing.py's
        module docstring for why automatic GPU instancing isn't part of
        this queue."""
        self.renderer.submit(mesh, material, transform, camera)

    def resize(self, size: tuple[int, int]):
        """Resizes `main_framebuffer` to match the new framebuffer `size`."""
        self.main_framebuffer.resize(size)

    def _collect(self, node, tilemaps, sprites, debugs, models, lights):
        """Recursively walks `node`'s subtree once, bucketing every node
        into whichever of the five lists it belongs to - replaces four
        separate find_nodes_with_type() tree walks (one per drawable type)
        the previous implementation did every frame with a single walk that
        also picks up lights along the way."""
        if node.inherits_from('TilemapRenderer'):
            tilemaps.append(node)
        elif node.inherits_from('Sprite2D'):
            sprites.append(node)
        elif node.inherits_from('Debug2D'):
            debugs.append(node)
        elif node.inherits_from('Model3D'):
            models.append(node)
        elif node.inherits_from('Light'):
            lights.append(node)

        for child_id in node.children:
            self._collect(node.children[child_id], tilemaps, sprites, debugs, models, lights)

    def _pick_shadow_light(self, lights: list):
        """Returns the first shadow-casting DirectionalLight3D in `lights`,
        or None - the only light/shadow combination this pipeline actually
        renders a shadow map for today (see module docstring in
        graphics/pbr/lighting.py for why 2D lights and non-directional 3D
        lights don't cast shadows yet). If more than one qualifies, every
        other one is simply lit without a shadow this frame - only one
        shadow map is rendered per frame."""
        for light in lights:
            if light.light_type == LightType.DIRECTIONAL and light.inherits_from('Node3D') and light.cast_shadows:
                return light
        return None

    def _shadow_matrices(self, light, camera):
        """Builds the shadow-casting light's view/projection matrices -
        an orthographic frustum of half-width `light.shadow_extent`,
        looking along `light.direction3` from `light.shadow_distance`
        world units back, centered on the active camera's position (a
        simple, workable heuristic - it keeps the shadow frustum following
        whatever's actually in view rather than fixed at the world
        origin). Deliberately mirrors Camera3D._update_view_matrix's /
        _update_projection_matrix's exact matrix construction (core/
        camera.py) rather than a textbook look-at formula, since that's
        the convention default_shader.fbvert/shadow_depth.fbvert's `proj *
        view * model * vertex` multiplication is already proven against."""
        target = camera.world_transform.position if camera.inherits_from('Node3D') else Vector3(0.0, 0.0, 0.0)
        direction = light.direction3
        eye = target - direction * light.shadow_distance

        rot = light.world_transform.rotation
        pitch = math.radians(rot.x)
        yaw = math.radians(rot.y)
        roll = math.radians(rot.z)
        cx, sx = math.cos(pitch), math.sin(pitch)
        cy, sy = math.cos(yaw), math.sin(yaw)
        cz, sz = math.cos(roll), math.sin(roll)

        rotation_matrix = np.array([
            [cy * cz + sx * sy * sz, cz * sx * sy - cy * sz, cx * sy, 0.0],
            [cx * sz, cx * cz, -sx, 0.0],
            [cy * sx * sz - cz * sy, cy * cz * sx + sy * sz, cx * cy, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ], dtype=np.float32)
        translation_matrix = np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0],
            [0, 0, 1, 0],
            [eye.x, eye.y, eye.z, 1],
        ], dtype=np.float32)
        world_matrix = translation_matrix @ rotation_matrix
        view = np.linalg.inv(world_matrix)

        half = light.shadow_extent
        near = 0.1
        far = light.shadow_distance * 2.0
        proj = np.array([
            [1.0 / half, 0.0, 0.0, 0.0],
            [0.0, 1.0 / half, 0.0, 0.0],
            [0.0, 0.0, -2.0 / (far - near), -(far + near) / (far - near)],
            [0.0, 0.0, 0.0, 1.0],
        ], dtype=np.float32)

        return view, proj

    def _render_shadow_map(self, light, view, proj, sprites, debugs, models):
        """Depth-only pass: draws every opaque mesh's shadow-caster
        geometry (sprites/debug draws/3D model submeshes - tilemaps aren't
        included, since TilemapRenderer draws itself directly rather than
        exposing individual meshes) from `light`'s view/projection into
        `self._shadow_framebuffer`, using the raw mesh.draw() rather than
        going through a Material (this pass only cares about depth, no
        material properties are read)."""
        self._shadow_framebuffer.bind()
        self.renderer.clear(Color("#000000FF"))
        self.renderer.enable_depth_testing()

        self._shadow_shader['view'] = view
        self._shadow_shader['proj'] = proj

        for sprite in sprites:
            self._shadow_shader['model'] = sprite.world_transform.model
            sprite._sprite.quad.draw()

        for debug in debugs:
            self._shadow_shader['model'] = debug.world_transform.model
            debug.mesh.draw()

        for model in models:
            for mesh_name in model._model.meshes:
                self._shadow_shader['model'] = model.world_transform.model
                model._model.meshes[mesh_name].draw()

        self.renderer.disable_depth_testing()
        self._shadow_framebuffer.unbind()

    def _light_uniform_values(self, light) -> dict:
        """Maps one Light node onto the flat uniform-value set a Light{N}_*
        slot needs (see module docstring for why these are flat slots
        rather than a real uniform array)."""
        type_index = {LightType.POINT: 0, LightType.DIRECTIONAL: 1, LightType.SPOT: 2}[light.light_type]

        if light.light_type == LightType.DIRECTIONAL:
            position = Vector3(0.0, 0.0, 0.0)
        else:
            position = light.world_position3

        if light.light_type in (LightType.DIRECTIONAL, LightType.SPOT):
            direction = light.direction3
        else:
            direction = Vector3(0.0, 0.0, -1.0)

        spot_cos = math.cos(math.radians(light.spot_angle)) if light.light_type == LightType.SPOT else -1.0

        return {
            'Active': True,
            'Type': type_index,
            'Position': position,
            'Direction': direction,
            'Color': light.color,
            'Intensity': light.intensity,
            'Range': light.range if light.range > 0.0 else 0.0001,
            'SpotCos': spot_cos,
        }

    def _apply_lighting_uniforms(self, shader, active_lights: list, shadow_light, shadow_matrix, view_pos: Vector3):
        """Sets every Light{N}_* uniform (active slots from `active_lights`,
        every remaining slot explicitly deactivated), plus Ambient/ViewPos/
        Shadow* - on `shader`, which may be the composite pass's own shader
        or a transparent object's forward-lit material shader (see
        PBRPipeline.draw() - both need the identical light-list state to
        light the same scene consistently)."""
        for i in range(MAX_LIGHTS):
            prefix = f'Light{i}_'
            if i < len(active_lights):
                values = self._light_uniform_values(active_lights[i])
                for key, value in values.items():
                    shader[f'{prefix}{key}'] = value
            else:
                shader[f'{prefix}Active'] = False

        shader['Ambient'] = self.ambient
        shader['ViewPos'] = view_pos

        if shadow_light is not None:
            shader['ShadowEnabled'] = True
            shader['ShadowMap'] = self.renderer.texture_manager.wrap_external_texture(
                self._shadow_framebuffer.get_attachment_texture('depth')
            )
            shader['ShadowMatrix'] = shadow_matrix
        else:
            shader['ShadowEnabled'] = False

    def _camera_view_pos(self, camera) -> Vector3:
        """A world-space "eye" position for the lighting math's view
        direction - the camera's own position for a 3D scene. A 2D
        orthographic camera has no real depth/eye position in the same
        sense, so it gets a synthetic point directly above its XY position
        (matching the nominal Z height 2D lights themselves use - see
        graphics/pbr/lighting.py) purely so specular highlights compute
        something sane rather than using a degenerate view direction."""
        pos = camera.world_transform.position
        if camera.inherits_from('Node3D'):
            return pos
        return Vector3(pos.x, pos.y, 10.0)

    def _draw_composite(self, camera, active_lights: list, shadow_light, shadow_matrix):
        """The deferred lighting pass: binds every G-buffer channel as a
        texture on `self._composite_shader`, restricts draw output to just
        'lit' (via set_draw_buffers - see Framebuffer.set_draw_buffers'
        docstring for why the other G-buffer channels would otherwise also
        get clobbered), and draws one fullscreen quad. Depth test/write are
        both off - every pixel gets (re)written regardless of whatever
        depth the opaque pass left, since this pass doesn't compete with
        anything else for 'lit' yet (flush_transparent() runs after, with
        depth testing back on)."""
        texture_manager = self.renderer.texture_manager
        for uniform_name, attachment in (
            ('gAlbedo', 'albedo'), ('gEmmisive', 'emmision'),
            ('gRoughness', 'roughness'), ('gMetallic', 'metallic'),
            ('gWorldPos', 'gWorldPos'), ('gWorldNormal', 'gWorldNormal'),
        ):
            gl_tex = self.main_framebuffer.get_attachment_texture(attachment)
            self._composite_shader[uniform_name] = texture_manager.wrap_external_texture(gl_tex)

        self._apply_lighting_uniforms(self._composite_shader, active_lights, shadow_light, shadow_matrix, self._camera_view_pos(camera))
        self._composite_shader['model'] = self._identity_model

        self.main_framebuffer.set_draw_buffers(['lit'])
        self.renderer.disable_depth_testing()
        self._composite_shader.use()
        self._composite_quad.draw()

    def draw(self):
        """Renders one frame - see module docstring for the full frame
        structure. Falls back to just clearing the window to opaque black
        if the active scene has no camera."""
        self.main_framebuffer.bind()
        camera = self.scene_manager.get_active().camera
        window_size = get_service('window').framebuffer_size

        if not camera:
            self.renderer.clear(Color("#000000FF"))
            self.main_framebuffer.draw(self.output_channel, window_size)
            self.main_framebuffer.unbind()
            return

        # Cleared with every attachment (including 'lit') active as a draw
        # buffer, in the FBO's original attachment-index order - clear_
        # color_attachment()'s draw-buffer-index lookup (see GLFramebuffer)
        # assumes that order, so narrowing to just the G-buffer channels
        # happens *after* the clear, not before.
        self.main_framebuffer.set_draw_buffers(self._gbuffer_attachments + ['lit'])
        self.renderer.clear(camera.background_color)
        # Renderer.clear() clears every bound draw buffer to the same
        # color, including camera.background_color's alpha (1.0, since
        # it's meant to look opaque on screen) - that would leave
        # gWorldPos.w indistinguishable between "background, nothing
        # rasterized here" and "real geometry, happens to sit exactly at
        # this alpha" for the composite pass (see default_shader.fbfrag's
        # gWorldPos/gWorldNormal outputs). Re-clearing just this channel to
        # alpha 0 after the general clear keeps that a reliable sentinel.
        self.main_framebuffer.clear_color_attachment('gWorldPos', (0.0, 0.0, 0.0, 0.0))
        self.renderer.enable_depth_testing()
        self.main_framebuffer.set_draw_buffers(self._gbuffer_attachments)

        tilemaps, sprites, debugs, models, lights = [], [], [], [], []
        self._collect(camera.scene.root, tilemaps, sprites, debugs, models, lights)

        shadow_light = self._pick_shadow_light(lights)
        shadow_view = shadow_proj = None
        if shadow_light is not None:
            shadow_view, shadow_proj = self._shadow_matrices(shadow_light, camera)
            self._render_shadow_map(shadow_light, shadow_view, shadow_proj, sprites, debugs, models)
            self.main_framebuffer.bind()
            self.main_framebuffer.set_draw_buffers(self._gbuffer_attachments)

        for tilemap in tilemaps:
            tilemap.draw(camera)

        for sprite in sprites:
            self.renderer.submit(sprite._sprite.quad, sprite._sprite.material, sprite.world_transform, camera)

        for model in models:
            for mesh_name in model._model.meshes:
                material = model._model.materials[model._model.material_map[mesh_name]]
                self.renderer.submit(model._model.meshes[mesh_name], material, model.world_transform, camera)

        self.renderer.flush_opaque()

        # Light every unique transparent material's own forward shader with
        # the same light-list state the composite pass uses, before
        # flush_transparent() draws them - they don't go through the
        # composite pass at all (see module docstring).
        shadow_matrix = (shadow_proj @ shadow_view) if shadow_light is not None else None
        transparent_shaders_seen = set()
        for call in self.renderer.calls:
            shader = call.material.shader
            if id(shader) not in transparent_shaders_seen:
                transparent_shaders_seen.add(id(shader))
                self._apply_lighting_uniforms(shader, lights, shadow_light, shadow_matrix, self._camera_view_pos(camera))

        self._draw_composite(camera, lights, shadow_light, shadow_matrix)
        
        for debug in debugs:
            if debug.draw_type == 'mesh':
                
                self.draw_world_mesh(debug.mesh, debug.material, debug.world_transform, camera)        
            elif debug.draw_type == 'line':
                start = camera.proj_matrix @ np.array([
                    debug.line_start.x,
                    debug.line_start.y,
                    0.0,
                    1.0
                ])

                end = camera.proj_matrix @ np.array([
                    debug.line_end.x,
                    debug.line_end.y,
                    0.0,
                    1.0
                ])

                start = Vector(start[0], start[1])
                end = Vector(end[0], end[1])    
                self.renderer.draw_line(start, end, debug.line_width, Color("#FF0000"))

        self.renderer.enable_depth_testing()
        self.renderer.flush_transparent()
        self.renderer.disable_depth_testing()

        self.main_framebuffer.unbind()
        self.main_framebuffer.draw(self.output_channel, window_size)

    def create_material(self, data, injector):
        """Builds a PBRMaterial from `data`, using `injector` to resolve FBUSL builtins."""
        return PBRMaterial(data, injector)
