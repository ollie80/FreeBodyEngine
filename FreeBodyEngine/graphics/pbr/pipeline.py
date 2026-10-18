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
from FreeBodyEngine.graphics.lighting import Light, LightType
from FreeBodyEngine.graphics.pbr.shaders import (MAX_LIGHTS, LIGHTING_COMPOSITE_VERT,
                                                 LIGHTING_COMPOSITE_FRAG, FXAA_VERT, FXAA_FRAG,
                                                 AO_FRAG, AO_BLUR_FRAG, TONEMAP_FRAG,
                                                 DOF_COC_FRAG, DOF_BOKEH_FRAG,
                                                 DOF_COMPOSITE_FRAG, DOF_MAX_BLUR)

from FreeBodyEngine.graphics.framebuffer import AttachmentFormat, AttachmentType
# TilemapRenderer is deliberately not imported. Nothing here uses the
# name - _collect() identifies one with node.inherits_from(
# 'TilemapRenderer'), a string - and importing it reached the tilemap
# module, whose @fbnjit decorators pull in numba and, behind numba,
# scipy. That was 450ms on every engine import, for a symbol this
# file never referred to.
from FreeBodyEngine.graphics.sprite import Sprite2D, Sprite
from FreeBodyEngine.graphics.debug import Debug2D
from FreeBodyEngine.graphics.mesh2d import MeshNode2D
from FreeBodyEngine.graphics.model.model import Model3D

from FreeBodyEngine.math import Transform, Vector3, Vector
from FreeBodyEngine.core.camera import Camera
from FreeBodyEngine.graphics.mesh import Mesh, generate_quad
from FreeBodyEngine.graphics.material import Material, BlendMode
from fbusl.injector import Injector

import numpy as np

SHADOW_MAP_SIZE = 2048

# How much depth slop the shadow comparison allows, measured in shadow-map
# texels of world distance. Big enough that a lit surface doesn't shadow
# itself across the PCF kernel's reach; small enough that a shadow stays
# attached to what casts it.
SHADOW_BIAS_TEXELS = 2.0


def _shadow_depth_range(light) -> tuple[float, float]:
    """The shadow frustum's near and far planes for `light`, in world units.

    Shared by the projection matrix and the depth bias so the two cannot
    drift apart - the bias is a fraction of exactly this range (see
    _apply_lighting_uniforms)."""
    return 0.1, light.shadow_distance * 2.0


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
            # Float, not RGBA8: the composite writes radiance, and a sunlit
            # surface or a specular highlight is legitimately past 1.0.
            # Clamped to 8 bits here, every one of those arrived at the
            # tonemap pass already flattened to the same white, which is
            # exactly the headroom the curve exists to use.
            'lit': (AttachmentType.COLOR, AttachmentFormat.RGBA16F),
            'depth': (AttachmentType.DEPTH, AttachmentFormat.DEPTH24)
        }, transparent = True
        )
        self._gbuffer_attachments = ['albedo', 'normal', 'emmision', 'roughness', 'metallic', 'gWorldPos', 'gWorldNormal']
        self.output_channel = 'lit'

        self.ambient = Vector3(0.03, 0.03, 0.03)
        # When True, the composite/forward-transparent shaders skip PBR
        # lighting entirely and output albedo (+emissive) untouched - for
        # scenes with no real lights (2D/flat-colored games) that still
        # want 'lit' (rather than a raw G-buffer channel) as their
        # `output_channel`, since 'lit' is the only attachment transparent
        # geometry ever reaches (see module docstring, step 4) - a raw
        # G-buffer channel like 'albedo' never shows transparent-blended
        # objects at all, since those are forward-shaded directly onto
        # 'lit' and never touch the G-buffer.
        self.unlit = False

        # What blocks light, as a world-space mask - see set_occluders().
        # None until something supplies one, which is every scene that has no
        # walls to cast with.
        self._occluder_texture = None
        self._occluder_origin = (0.0, 0.0)
        self._occluder_extent = (1.0, 1.0)
        # The light's apparent size in world units, which is what gives a
        # shadow its penumbra. 0 is a hard edge; a few units is enough to take
        # the harshness off without the shadow losing its shape.
        self.shadow_softness = 0.0

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

        # Antialiasing. FXAA, as a final fullscreen pass over the finished
        # image - see shaders.FXAA_FRAG's header for why a deferred renderer
        # cannot simply turn MSAA on.
        self._fxaa_shader = self.renderer.load_shader(FXAA_VERT, FXAA_FRAG, Injector(), None)
        self.antialiasing = True
        # How many shadow-map texels wide the PCF kernel reaches. 1.0 is
        # just enough to antialias the edge; larger genuinely softens it,
        # at the cost of the 16 taps spreading far enough to show their
        # own pattern.
        self.shadow_pcf_radius = 1.0

        # Distance fog. Off by default (density 0) so existing scenes are
        # unchanged; set `fog_color` to the scene's horizon and `fog_end` at
        # or just inside the camera's far plane so distant geometry fades
        # out rather than popping out of the frustum.
        self.fog_color = Vector3(0.78, 0.86, 0.93)
        self.fog_start = 60.0
        self.fog_end = 380.0
        self.fog_density = 0.0
        # Edge sensitivity, as a fraction of the brighter side's luma. 0.166
        # is the usual "default quality" value; lower catches more edges and
        # softens more of the image with them.
        self.fxaa_edge_threshold = 0.166
        # Absolute floor, so near-black areas are not filtered on noise.
        self.fxaa_edge_threshold_min = 0.0833
        # How far along an edge the blur may reach, in texels.
        self.fxaa_span_max = 8.0

        # Exposure and tonemapping - see shaders.TONEMAP_FRAG. On by
        # default: the composite's output is radiance, and sending that to a
        # screen unmapped is not a style, it is a missing step. A project
        # whose colours are authored as final output (flat 2D art, say)
        # turns it off, and `unlit` turns it off implicitly for the same
        # reason.
        self.tonemap = True
        self.exposure = 1.0
        # Grade, applied after the curve - 1.0 and 0.0 leave the image
        # alone. See shaders.TONEMAP_FRAG for why saturation and contrast
        # belong with a miniature look rather than being gratuitous.
        self.saturation = 1.0
        self.contrast = 1.0
        self.vignette = 0.0
        self._dof_view_pos = Vector3(0.0, 0.0, 0.0)
        self._tonemap_shader = self.renderer.load_shader(FXAA_VERT, TONEMAP_FRAG, Injector(), None)
        self._post_framebuffer = self.renderer.create_framebuffer(
            self.main_framebuffer.width, self.main_framebuffer.height, {
                'tonemapped': (AttachmentType.COLOR, AttachmentFormat.RGBA8),
            })

        # Depth of field - see shaders.DOF_COMPOSITE_FRAG. Off by default:
        # it is a look, not a correction, and a project that has not asked
        # for it should not pay two passes for it.
        self.dof = False
        # Metres either side of whatever is in the middle of the screen
        # that stay sharp, and how far past that the blur reaches full
        # strength.
        self.dof_range = 14.0
        self.dof_falloff = 40.0
        self.dof_strength = 1.0
        # Tilt-shift: blur toward the top and bottom of the frame whatever
        # the depth is there. The depth term is the photographic effect;
        # this band is the one that reads as "diorama". 0 turns it off.
        self.dof_tilt = 0.0
        self.dof_tilt_band = 0.55
        self._dof_coc_shader = self.renderer.load_shader(FXAA_VERT, DOF_COC_FRAG, Injector(), None)
        self._dof_bokeh_shader = self.renderer.load_shader(FXAA_VERT, DOF_BOKEH_FRAG, Injector(), None)
        self._dof_shader = self.renderer.load_shader(FXAA_VERT, DOF_COMPOSITE_FRAG, Injector(), None)

        # Half resolution, and float: the gather runs on radiance, before
        # the tonemap, because a highlight that has already been rolled off
        # to white has nothing left to spread into a bright disc. Alpha
        # carries the signed circle of confusion through both passes.
        half = (max(self.main_framebuffer.width // 2, 1),
                max(self.main_framebuffer.height // 2, 1))
        self._dof_coc = self.renderer.create_framebuffer(half[0], half[1], {
            'coc': (AttachmentType.COLOR, AttachmentFormat.RGBA16F),
        })
        self._dof_bokeh = self.renderer.create_framebuffer(half[0], half[1], {
            'bokeh': (AttachmentType.COLOR, AttachmentFormat.RGBA16F),
        })
        self._dof_framebuffer = self.renderer.create_framebuffer(
            self.main_framebuffer.width, self.main_framebuffer.height, {
                'focused': (AttachmentType.COLOR, AttachmentFormat.RGBA16F),
            })

        # Ambient occlusion - see shaders.AO_FRAG. Two framebuffers because
        # the pass is dithered and needs a blur, and a blur cannot read and
        # write one target.
        self.ao = True
        # World units. About a metre suits human-scale scenes; a model
        # viewer wants centimetres and a city block wants metres.
        self.ao_radius = 1.0
        # How much ambient a fully occluded point loses. 1.0 removes all of
        # it, which is darker than any real contact and reads as soot.
        self.ao_strength = 0.9
        # World-space slop before a surface counts as occluding, the depth
        # bias of this pass - see AO_FRAG.
        self.ao_bias = 0.05
        self._ao_shader = self.renderer.load_shader(FXAA_VERT, AO_FRAG, Injector(), None)
        self._ao_blur_shader = self.renderer.load_shader(FXAA_VERT, AO_BLUR_FRAG, Injector(), None)
        self._ao_framebuffer = self.renderer.create_framebuffer(
            self.main_framebuffer.width, self.main_framebuffer.height, {
                'ao': (AttachmentType.COLOR, AttachmentFormat.R8),
            })
        self._ao_blur_framebuffer = self.renderer.create_framebuffer(
            self.main_framebuffer.width, self.main_framebuffer.height, {
                'ao': (AttachmentType.COLOR, AttachmentFormat.R8),
            })

        # Speed lines, drawn in the same final pass as the antialiasing
        # (they are a screen-space overlay, so the last pass before the
        # screen is exactly where they belong and they cost nothing extra).
        # `speed_line_strength` is meant to be driven per frame by whatever
        # is moving - 0 is off.
        self.speed_line_strength = 0.0
        self.speed_line_color = Vector3(1.0, 1.0, 1.0)
        self.speed_line_inner_radius = 0.42
        self.speed_line_width = 0.32
        self.speed_line_count = 90.0

    def draw_world_mesh(self, mesh: Mesh, material: Material, transform: Transform, camera: Camera, instances: int = 1):
        """Queues `mesh`/`material`/`transform` for drawing against `camera`
        via Renderer.submit() (see Renderer.flush_opaque()/
        flush_transparent() for when queued calls actually get drawn).
        `instances` is accepted but unused - see graphics/instancing.py's
        module docstring for why automatic GPU instancing isn't part of
        this queue."""
        self.renderer.submit(mesh, material, transform, camera)

    def resize(self, size: tuple[int, int]):
        """Resizes `main_framebuffer` and every full-screen pass that has to
        stay the same size as it - the AO pair and the tonemap target all
        sample it by UV, so a stale size samples the wrong texels rather
        than failing outright."""
        self.main_framebuffer.resize(size)
        self._post_framebuffer.resize(size)
        self._dof_framebuffer.resize(size)
        self._dof_coc.resize((max(size[0] // 2, 1), max(size[1] // 2, 1)))
        self._dof_bokeh.resize((max(size[0] // 2, 1), max(size[1] // 2, 1)))
        self._ao_framebuffer.resize(size)
        self._ao_blur_framebuffer.resize(size)

    def _collect(self, node, tilemaps, sprites, debugs, models, lights, meshes):
        """Recursively walks `node`'s subtree once, bucketing every node
        into whichever of the six lists it belongs to - replaces separate
        find_nodes_with_type() tree walks (one per drawable type) the
        previous implementation did every frame with a single walk that
        also picks up lights along the way."""
        if node.inherits_from('TilemapRenderer'):
            tilemaps.append(node)
        elif node.inherits_from('Sprite2D'):
            # `visible` was accepted by Sprite's constructor and stored, and
            # then read by nothing at all - every sprite was drawn whatever it
            # said. Checked at collection so an invisible sprite costs no
            # transform, no submit and no shadow-map draw either.
            if node._sprite.visible:
                sprites.append(node)
        elif node.inherits_from('MeshNode2D'):
            meshes.append(node)
        elif node.inherits_from('Debug2D'):
            debugs.append(node)
        elif node.inherits_from('Model3D'):
            models.append(node)
        elif node.inherits_from('Light'):
            lights.append(node)

        for child_id in node.children:
            self._collect(node.children[child_id], tilemaps, sprites, debugs, models, lights, meshes)

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

        # Built from a look-at basis along `direction3`, not by rebuilding
        # the light's Euler rotation the way Camera3D does.
        #
        # Reconstructing it from the Euler angles mixed two conventions that
        # disagree: `eye` above comes from `direction3`, which is
        # lighting._pitch_yaw_roll_to_forward, and that function's pitch
        # sign is the *opposite* of the one Camera3D's view matrix uses
        # (negative pitch points down for the light helper, up for the
        # camera). So the shadow camera was placed correctly and then
        # pointed the other way, and every surface came back shadowed.
        #
        # A basis built straight from the direction the light actually
        # shines cannot disagree with itself. The rows are the camera's
        # local axes in world space, which is what the row-vector world
        # matrix below wants - local -Z is forward, matching Camera3D.
        forward = np.array([direction.x, direction.y, direction.z], dtype=np.float32)
        norm = np.linalg.norm(forward)
        if norm == 0.0:
            forward = np.array([0.0, -1.0, 0.0], dtype=np.float32)
        else:
            forward = forward / norm

        # Any world up that is not parallel to `forward`; a sun directly
        # overhead is the one case where +Y is no use.
        world_up = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        if abs(float(np.dot(forward, world_up))) > 0.999:
            world_up = np.array([0.0, 0.0, 1.0], dtype=np.float32)

        right = np.cross(forward, world_up)
        right = right / np.linalg.norm(right)
        up = np.cross(right, forward)

        # Snap the frustum's centre to whole shadow-map texels, along the
        # light's own two lateral axes.
        #
        # Without this the map is re-rasterized onto a grid that has moved a
        # fraction of a texel every time the camera moves at all, so every
        # shadow edge in the scene jumps between neighbouring texels from one
        # frame to the next - which reads as flickering whenever the camera
        # creeps by less than a texel per frame (a vehicle crawling, or a
        # chase camera still easing into place after the thing it follows has
        # stopped). Faster than that and the motion hides it; exactly still
        # and it is stable but arbitrary. Quantizing the centre means a
        # sub-texel move produces the *same* matrix, so the map's contents
        # only change when the grid itself steps - one whole texel at a time.
        texel = (2.0 * light.shadow_extent) / SHADOW_MAP_SIZE
        centre = np.array([target.x, target.y, target.z], dtype=np.float32)
        for axis in (right, up):
            offset = float(np.dot(centre, axis))
            centre = centre + axis * (round(offset / texel) * texel - offset)
        eye = Vector3(float(centre[0]), float(centre[1]), float(centre[2])) - direction * light.shadow_distance

        world_matrix = np.array([
            [right[0], right[1], right[2], 0.0],
            [up[0], up[1], up[2], 0.0],
            [-forward[0], -forward[1], -forward[2], 0.0],
            [eye.x, eye.y, eye.z, 1.0],
        ], dtype=np.float32)
        view = np.linalg.inv(world_matrix)

        half = light.shadow_extent
        near, far = _shadow_depth_range(light)
        # Row-vector layout: the depth translation goes in the last ROW,
        # not the last column.
        #
        # Written column-vector (translation at [2][3]) it was consumed as
        # row-vector by both users of this matrix - the depth pass's
        # `proj * view * model * vertex`, and the composite's
        # `ShadowMatrix * worldPos` - because a numpy array uploaded to a
        # GL mat4 arrives transposed. That made clip-space w equal
        # `1 - z*(far+near)/(far-near)` instead of a constant 1, so the
        # perspective divide shrank every fragment toward the middle of the
        # shadow map: the whole world sampled a handful of texels around
        # uv (0.5, 0.5) at a near-constant depth, and came back shadowed.
        proj = np.array([
            [1.0 / half, 0.0, 0.0, 0.0],
            [0.0, 1.0 / half, 0.0, 0.0],
            [0.0, 0.0, -2.0 / (far - near), 0.0],
            [0.0, 0.0, -(far + near) / (far - near), 1.0],
        ], dtype=np.float32)

        return view, proj

    def _render_shadow_map(self, light, view, proj, sprites, debugs, models, meshes):
        """Depth-only pass: draws every opaque mesh's shadow-caster
        geometry (sprites/mesh nodes/debug draws/3D model submeshes -
        tilemaps aren't included, since TilemapRenderer draws itself
        directly rather than exposing individual meshes) from `light`'s
        view/projection into `self._shadow_framebuffer`, using the raw
        mesh.draw() rather than going through a Material (this pass only
        cares about depth, no material properties are read)."""
        self._shadow_framebuffer.bind()
        self.renderer.clear(Color("#000000FF"))
        self.renderer.enable_depth_testing()

        self._shadow_shader['view'] = view
        self._shadow_shader['proj'] = proj

        for sprite in sprites:
            self._shadow_shader['model'] = sprite.world_transform.model
            sprite._sprite.quad.draw()

        for mesh_node in meshes:
            self._shadow_shader['model'] = mesh_node.world_transform.model
            mesh_node.mesh.draw()

        for debug in debugs:
            self._shadow_shader['model'] = debug.world_transform.model
            debug.mesh.draw()

        for model in models:
            if not getattr(model, 'cast_shadows', True):
                continue  # see Model3D.cast_shadows
            # A model whose mesh isn't its final geometry - points a geometry
            # shader builds the real thing from - brings a depth shader that
            # runs the same stages (Model3D.shadow_shader).
            shader = getattr(model, 'shadow_shader', None)
            if shader is not None:
                shader['view'] = view
                shader['proj'] = proj
            else:
                shader = self._shadow_shader
            # Bound explicitly, every model. Setting a uniform binds the
            # program it belongs to, which is why this worked for as long
            # as it did - but a shader that already holds the value being
            # set has nothing to upload and so binds nothing, and then the
            # draw below goes out under whatever program the *previous*
            # model left bound. Between two ordinary models that is
            # harmless; between a model with a geometry-shader depth pass
            # (buildings, drawn from points) and a plain triangle mesh
            # after it, the triangles are fed to a geometry shader
            # declaring points in, which is GL_INVALID_OPERATION and takes
            # the whole shadow pass down with it.
            shader.use()
            for mesh_name in model._model.meshes:
                shader['model'] = model.world_transform.model
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

    def _select_lights(self, lights: list, camera) -> list:
        """The MAX_LIGHTS lights that matter most to what this camera sees.

        There are only MAX_LIGHTS uniform slots, and what used to happen to
        light number MAX_LIGHTS+1 was simply nothing: the slots were filled
        from the list in tree-walk order and the rest were dropped without a
        word. Tree order is creation order, so in a scene with more lights than
        slots the ones that lost were always the most recently added - which is
        to say the ones attached to the player, the thing the camera is
        actually looking at. A lantern carried through a room of twenty wall
        lamps lit nothing at all.

        So the slots go to the lights whose reach is nearest the camera.
        `distance - range` is negative for a light whose falloff sphere
        contains the eye and grows with how far one falls short of it, which
        ranks a close dim light above a distant bright one the way the shading
        actually behaves. A directional light has neither position nor range
        and lights everything, so it always takes a slot.

        Note this is per frame and unweighted by what is on screen, so a camera
        moving through more than MAX_LIGHTS lights will swap one for another at
        the point the ranking crosses over. Raising MAX_LIGHTS (a shader
        recompile - see graphics/pbr/shaders.py) is the lever if that shows.
        """
        eye = self._camera_view_pos(camera)

        ranked = []
        for light in lights:
            if not light.enabled:
                continue
            if light.light_type == LightType.DIRECTIONAL:
                ranked.append((-math.inf, light))
                continue
            position = light.world_position3
            distance = math.sqrt((position.x - eye.x) ** 2
                                 + (position.y - eye.y) ** 2
                                 + (position.z - eye.z) ** 2)
            ranked.append((distance - light.range, light))

        if len(ranked) > MAX_LIGHTS:
            # keyed, so two equally-ranked lights never get compared to each other
            ranked.sort(key=lambda entry: entry[0])
            del ranked[MAX_LIGHTS:]

        return [light for _, light in ranked]

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
        shader['Unlit'] = self.unlit
        shader['FogColor'] = self.fog_color
        shader['FogStart'] = self.fog_start
        shader['FogEnd'] = self.fog_end
        shader['FogDensity'] = self.fog_density

        if shadow_light is not None:
            shader['ShadowEnabled'] = True
            shader['ShadowTexelSize'] = 1.0 / SHADOW_MAP_SIZE
            shader['ShadowSoftnessRadius'] = self.shadow_pcf_radius
            # In world units first, then as a fraction of the frustum's depth
            # range, which is what the shader compares in.
            #
            # A constant in depth-range units (what this was) means the slop
            # scales with `shadow_distance`: the engine's 30-unit default is
            # a harmless 8cm, but a scene that pushes the frustum out to a few
            # hundred units - an outdoor one, where the sun has to cover a
            # view distance - silently turns it into most of a metre, and
            # every shadow cast by anything shorter than that simply isn't
            # there. Derived from the texel size instead, it is the same
            # fraction of a texel at any scene scale.
            near, far = _shadow_depth_range(shadow_light)
            texel_world = (2.0 * shadow_light.shadow_extent) / SHADOW_MAP_SIZE
            shader['ShadowBias'] = (texel_world * SHADOW_BIAS_TEXELS) / max(far - near, 0.001)
            shader['ShadowMap'] = self.renderer.texture_manager.wrap_external_texture(
                self._shadow_framebuffer.get_attachment_texture('depth')
            )
            shader['ShadowMatrix'] = shadow_matrix
        else:
            shader['ShadowEnabled'] = False

    def set_occluders(self, texture, origin, extent):
        """Hands the lighting pass a world-space mask of what blocks light.

        `texture` is sampled in its red channel: anything above 0.5 is solid.
        `origin` is the world position of its bottom-left corner and `extent`
        the world size it covers, so a fragment maps into it by a subtract and
        a divide - the shader does no transform of its own.

        A mask rather than occluder geometry because the occluders in a tile
        game already are a grid: a texture lookup is the intersection test, so
        there is no per-light render pass and nothing to rebuild when a light
        moves. It only changes when the level does.

        Pass `texture=None` to turn shadow casting off again. How soft the
        resulting shadows are is `shadow_softness`, set separately - it is a
        property of the lights, not of what blocks them.
        """
        self._occluder_texture = texture
        self._occluder_origin = (float(origin[0]), float(origin[1]))
        self._occluder_extent = (max(float(extent[0]), 1e-6), max(float(extent[1]), 1e-6))

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
            # The normal-map channel. Written by every G-buffer shader since
            # the pipeline was built, but never bound here, so nothing ever
            # read it - see LIGHTING_COMPOSITE_FRAG's own note.
            ('gNormal', 'normal'),
        ):
            gl_tex = self.main_framebuffer.get_attachment_texture(attachment)
            self._composite_shader[uniform_name] = texture_manager.wrap_external_texture(gl_tex)

        self._apply_lighting_uniforms(self._composite_shader, active_lights, shadow_light, shadow_matrix, self._camera_view_pos(camera))

        # Composite-only, deliberately: the occlusion march lives in
        # accumulate_lighting, which only this shader has. A forward-lit
        # transparent object is shaded by its own material shader, which never
        # declared these - so setting them there is an error about a uniform
        # that genuinely is not in that program, not a missing feature to fix.
        # Transparent objects therefore do not receive 2D shadows, the same way
        # they already do not receive the directional shadow map.
        if getattr(self, '_ao_active', False):
            self._composite_shader['AOEnabled'] = True
            self._composite_shader['AOMap'] = self.renderer.texture_manager.wrap_external_texture(
                self._ao_blur_framebuffer.get_attachment_texture('ao'))
        else:
            self._composite_shader['AOEnabled'] = False

        if self._occluder_texture is not None:
            self._composite_shader['OccluderEnabled'] = True
            self._composite_shader['OccluderMap'] = self._occluder_texture
            self._composite_shader['OccluderOrigin'] = self._occluder_origin
            self._composite_shader['OccluderExtent'] = self._occluder_extent
            self._composite_shader['ShadowSoftness'] = float(self.shadow_softness)
        else:
            self._composite_shader['OccluderEnabled'] = False

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

        tilemaps, sprites, debugs, models, lights, meshes = [], [], [], [], [], []
        self._collect(camera.scene.root, tilemaps, sprites, debugs, models, lights, meshes)

        lights = self._select_lights(lights, camera)

        shadow_light = self._pick_shadow_light(lights)
        shadow_view = shadow_proj = None
        if shadow_light is not None:
            shadow_view, shadow_proj = self._shadow_matrices(shadow_light, camera)
            self._render_shadow_map(shadow_light, shadow_view, shadow_proj, sprites, debugs, models, meshes)
            self.main_framebuffer.bind()
            self.main_framebuffer.set_draw_buffers(self._gbuffer_attachments)
            # _render_shadow_map ends by disabling depth testing, and the
            # enable_depth_testing() above it ran *before* the shadow pass -
            # so without this the entire G-buffer pass drew with GL_DEPTH_TEST
            # off and the scene resolved by draw order alone. Every box showed
            # its own back faces through its front, whatever was submitted
            # last covered whatever was in front of it, and a skybox could not
            # work at all. Only reachable with a shadow-casting light in the
            # scene, which is why it stayed hidden for as long as nothing
            # cast one.
            self.renderer.enable_depth_testing()

        for tilemap in tilemaps:
            tilemap.draw(camera)

        for sprite in sprites:
            self.renderer.submit(sprite._sprite.quad, sprite._sprite.material, sprite.world_transform, camera, z=sprite._sprite.z)

        for mesh_node in meshes:
            self.renderer.submit(mesh_node.mesh, mesh_node.material, mesh_node.world_transform, camera)

        for model in models:
            for mesh_name in model._model.meshes:
                material = model._model.materials[model._model.material_map[mesh_name]]
                self.renderer.submit(model._model.meshes[mesh_name], material, model.world_transform, camera)

        self.renderer.flush_opaque()

        # Light every unique transparent material's own forward shader with
        # the same light-list state the composite pass uses, before
        # flush_transparent() draws them - they don't go through the
        # composite pass at all (see module docstring).
        # `view @ proj`, not `proj @ view`. The composite shader multiplies
        # column-style (`ShadowMatrix * worldPos`) but a numpy array
        # uploaded to a GL mat4 arrives transposed, so GLSL sees this
        # matrix's transpose - which makes the shader's effective operation
        # the row-vector `worldPos @ ShadowMatrix`, the same convention the
        # vertex shaders' `proj * view * model * vertex` already resolves
        # to. Composed the other way round the factors applied backwards,
        # every fragment landed outside the shadow map's depth range, and
        # the whole world came back shadowed.
        # Ambient occlusion, between the G-buffer and the composite that
        # samples it. Only with 3D models in the scene: every surface in a
        # 2D one is a quad on the same plane facing the camera, so every tap
        # lands at the same distance as its origin and the pass can only
        # ever return "unoccluded" - at the cost of a full-screen pass.
        ao_active = bool(self.ao) and len(models) > 0
        if ao_active:
            self._render_ao(camera)
            self.main_framebuffer.bind()
            self.main_framebuffer.set_draw_buffers(self._gbuffer_attachments)
        self._ao_active = ao_active

        # Kept for the depth-of-field composite, which runs after the
        # scene is finished and no longer has the camera to hand.
        self._dof_view_pos = self._camera_view_pos(camera)

        shadow_matrix = (shadow_view @ shadow_proj) if shadow_light is not None else None
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
        # flush_transparent() leaves the renderer's blend state at
        # BlendMode.TRANSPARENT (GL_BLEND on, glDepthMask(GL_FALSE) - see
        # GL33Renderer.set_blend_mode()) whenever anything transparent was
        # actually drawn this frame, and nothing else resets it before
        # the present blit below or before whatever draws after this
        # pipeline runs (e.g. UI/text - see graphics/text/text.py,
        # ui/renderer.py - neither of which sets blend state itself, so
        # both silently inherited whatever this pipeline left behind).
        # Resetting to OPAQUE here is a no-op when nothing transparent was
        # drawn (set_blend_mode() already skips redundant GL calls).
        self.renderer.set_blend_mode(BlendMode.OPAQUE)
        self.renderer.disable_depth_testing()

        # Antialias on the way to the screen. Skipped when `output_channel`
        # is some other G-buffer channel: those are debug views of raw
        # surface data (world positions, normals), and running an
        # edge-detecting blur over them would show something that is not
        # what is in the buffer.
        # The post pass does the AA resolve *and* the speed-line overlay, so
        # it also runs when antialiasing is off but speed lines are not.
        if self.output_channel == 'lit':
            # Unconditional, unlike the AA resolve below it: with the 'lit'
            # attachment holding radiance, skipping this would not mean "no
            # tonemapping", it would mean handing an 8-bit screen values it
            # cannot show. Turning the curve itself off is `tonemap`.
            if self.dof:
                self._draw_dof()
            self._draw_tonemap()
            if self.antialiasing or self.speed_line_strength > 0.0:
                self._draw_fxaa(window_size)
            else:
                self._post_framebuffer.unbind()
                self._post_framebuffer.draw('tonemapped', window_size)
        else:
            self.main_framebuffer.unbind()
            self.main_framebuffer.draw(self.output_channel, window_size)

    def _render_ao(self, camera):
        """Fills the AO buffer from the G-buffer, then blurs the dither out
        of it - see shaders.AO_FRAG.

        Runs after the G-buffer is complete and before the lighting
        composite, which is the only window where world position and normal
        exist for every visible surface and nothing has been lit yet."""
        texture_manager = self.renderer.texture_manager

        self._ao_framebuffer.bind()
        # White is "nothing occludes this", so anything the pass skips (the
        # sky) stays unshaded rather than arriving black.
        self.renderer.clear(Color("#FFFFFFFF"))
        self.renderer.disable_depth_testing()

        shader = self._ao_shader
        shader['gWorldPos'] = texture_manager.wrap_external_texture(
            self.main_framebuffer.get_attachment_texture('gWorldPos'))
        shader['gWorldNormal'] = texture_manager.wrap_external_texture(
            self.main_framebuffer.get_attachment_texture('gWorldNormal'))
        # Same `view @ proj` composition order, and the same reason, as the
        # shadow matrix - see render()'s note.
        shader['ViewProj'] = camera.view_matrix @ camera.proj_matrix
        shader['ViewPos'] = self._camera_view_pos(camera)
        shader['Radius'] = self.ao_radius
        shader['Strength'] = self.ao_strength
        shader['Bias'] = self.ao_bias
        shader['model'] = self._identity_model
        shader.use()
        self._composite_quad.draw()
        self._ao_framebuffer.unbind()

        self._ao_blur_framebuffer.bind()
        self.renderer.clear(Color("#FFFFFFFF"))
        blur = self._ao_blur_shader
        blur['AOMap'] = texture_manager.wrap_external_texture(
            self._ao_framebuffer.get_attachment_texture('ao'))
        blur['InverseResolution'] = (
            1.0 / max(self._ao_framebuffer.width, 1),
            1.0 / max(self._ao_framebuffer.height, 1),
        )
        blur['model'] = self._identity_model
        blur.use()
        self._composite_quad.draw()
        self._ao_blur_framebuffer.unbind()

    def _draw_tonemap(self):
        """Maps the composite's radiance onto what a screen can show - see
        shaders.TONEMAP_FRAG.

        Its own pass rather than a few lines at the end of the composite,
        because the forward-shaded transparent objects are drawn onto 'lit'
        *after* the composite has run: tonemapping inside it would map the
        opaque world and leave everything blended on top of it unmapped, at
        a different exposure. One pass over the finished image maps all of
        it once. It is also what FXAA then runs on, which is what FXAA
        wants - its edge detection is a luma threshold, and luma only means
        anything on display-referred values."""
        self._post_framebuffer.bind()
        self.renderer.disable_depth_testing()

        # The depth-of-field result if it ran, the raw lit buffer if not.
        source = self.main_framebuffer.get_attachment_texture('lit')
        if self.dof:
            source = self._dof_framebuffer.get_attachment_texture('focused')

        shader = self._tonemap_shader
        shader['Screen'] = self.renderer.texture_manager.wrap_external_texture(source)
        shader['Exposure'] = self.exposure
        # `unlit` means the scene's colours are already final - running them
        # through a filmic curve would be a second opinion nobody asked for.
        shader['TonemapEnabled'] = bool(self.tonemap) and not bool(self.unlit)
        shader['Saturation'] = self.saturation
        shader['Contrast'] = self.contrast
        shader['Vignette'] = self.vignette
        shader['model'] = self._identity_model
        shader.use()
        self._composite_quad.draw()
        self._post_framebuffer.unbind()

    def _draw_dof(self):
        """Circle of confusion, bokeh gather, composite.

        Runs on the lit buffer before the tonemap, and writes a buffer the
        tonemap then reads instead - so everything downstream is unchanged
        and the curve rolls off bokeh highlights rather than the other way
        round.
        """
        texture_manager = self.renderer.texture_manager
        lit = self.main_framebuffer.get_attachment_texture('lit')

        # 1. Half-resolution colour, with the signed circle of confusion
        #    packed into alpha.
        self._dof_coc.bind()
        self.renderer.disable_depth_testing()
        shader = self._dof_coc_shader
        shader['Screen'] = texture_manager.wrap_external_texture(lit)
        shader['gWorldPos'] = texture_manager.wrap_external_texture(
            self.main_framebuffer.get_attachment_texture('gWorldPos'))
        shader['ViewPos'] = self._dof_view_pos
        shader['FocusRange'] = self.dof_range
        shader['FocusFalloff'] = self.dof_falloff
        shader['TiltStrength'] = self.dof_tilt
        shader['TiltBand'] = self.dof_tilt_band
        shader['model'] = self._identity_model
        shader.use()
        self._composite_quad.draw()
        self._dof_coc.unbind()

        # 2. The gather. Fixed tap count; the per-pixel radius comes out of
        #    which taps each pixel's own circle of confusion accepts.
        self._dof_bokeh.bind()
        shader = self._dof_bokeh_shader
        shader['Source'] = texture_manager.wrap_external_texture(
            self._dof_coc.get_attachment_texture('coc'))
        shader['TexelSize'] = (1.0 / max(self._dof_coc.width, 1),
                               1.0 / max(self._dof_coc.height, 1))
        shader['MaxBlur'] = DOF_MAX_BLUR
        shader['model'] = self._identity_model
        shader.use()
        self._composite_quad.draw()
        self._dof_bokeh.unbind()

        # 3. Back against the full-resolution image, by how far out of
        #    focus each pixel is - so anything sharp keeps every pixel it
        #    had.
        self._dof_framebuffer.bind()
        shader = self._dof_shader
        shader['Sharp'] = texture_manager.wrap_external_texture(lit)
        shader['Bokeh'] = texture_manager.wrap_external_texture(
            self._dof_bokeh.get_attachment_texture('bokeh'))
        shader['Strength'] = self.dof_strength
        shader['model'] = self._identity_model
        shader.use()
        self._composite_quad.draw()
        self._dof_framebuffer.unbind()

    def _draw_fxaa(self, window_size: tuple[int, int]):
        """Resolves 'lit' to the screen through the FXAA shader.

        Unlike Framebuffer.draw(), which blits an attachment straight to the
        window, this is a real fullscreen quad draw into the default
        framebuffer - so it binds that framebuffer and sets the viewport
        itself (bind_window_framebuffer does both).

        `InverseResolution` is one texel of the *framebuffer*, not of the
        window: the two differ whenever the window is scaled, and FXAA's
        taps have to land on real texel centres of the image it is
        filtering or the edge detection reads neighbours that are not
        neighbours.
        """
        self.renderer.bind_window_framebuffer(window_size)

        # The tonemapped image, not 'lit' itself: FXAA thresholds on luma,
        # and a luma taken from unmapped radiance has no fixed meaning - the
        # same edge passes or fails the test depending on how bright the
        # scene happens to be.
        source = self._post_framebuffer
        lit_texture = source.get_attachment_texture('tonemapped')
        self._fxaa_shader['Screen'] = self.renderer.texture_manager.wrap_external_texture(lit_texture)
        self._fxaa_shader['InverseResolution'] = (
            1.0 / max(source.width, 1),
            1.0 / max(source.height, 1),
        )
        self._fxaa_shader['EdgeThreshold'] = self.fxaa_edge_threshold
        self._fxaa_shader['EdgeThresholdMin'] = self.fxaa_edge_threshold_min
        self._fxaa_shader['SpanMax'] = self.fxaa_span_max

        self._fxaa_shader['SpeedLineStrength'] = self.speed_line_strength
        self._fxaa_shader['SpeedLineColor'] = self.speed_line_color
        self._fxaa_shader['SpeedLineInnerRadius'] = self.speed_line_inner_radius
        self._fxaa_shader['SpeedLineWidth'] = self.speed_line_width
        self._fxaa_shader['SpeedLineCount'] = self.speed_line_count
        self._fxaa_shader['ScreenAspect'] = window_size[0] / max(window_size[1], 1)

        self._fxaa_shader['model'] = self._identity_model

        self.renderer.disable_depth_testing()
        self._fxaa_shader.use()
        self._composite_quad.draw()

    def create_material(self, data, injector):
        """Builds a PBRMaterial from `data`, using `injector` to resolve FBUSL builtins."""
        return PBRMaterial(data, injector)
