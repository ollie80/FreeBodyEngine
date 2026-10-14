"""LitePipeline: 2D, forward, and uncapped in lights.

The pipeline PBRPipeline is not. Both can draw a 2D scene, and for a while
this game used the PBR one - but it is built to light three-dimensional
surfaces, and the shape of it costs a 2D game dearly in two specific ways.

**Every light is evaluated at every pixel.** PBRPipeline's composite is one
fullscreen pass with the light loop unrolled inside it, so a sconce whose
reach covers a tenth of the view still costs the whole of it. That product -
lights times screen - is the only reason it needs a hard cap of eight lights.
Here a light is drawn as a quad the size of its own reach, blended additively
into a light buffer, so it costs the area it actually lights. There is no cap,
no ranking, and nothing to select: a room can hold as many candles as it is
worth drawing.

**And every light is evaluated as a physical surface.** Roughness, metallic, a
Fresnel term and a specular lobe, to produce a highlight nobody will see on a
pixel-art sconce. A surface here has a colour, a direction and a glow, and the
light pass is an attenuation and a dot product.

Three passes:

1. **Surface** - every sprite, tilemap and mesh into `colour`, `normal` and
   `emmisive`. No lighting; this pass only records what is there.
2. **Light** - `light` is cleared to the ambient and each light adds its own
   quad to it, marching an occluder mask on the way so walls block it (see
   set_occluders).
3. **Combine** - `colour * light + emmisive`, the one fullscreen pass a frame.

Shadows fall out of that same shape. PBRPipeline marches the same occluder
mask, but from inside its fullscreen composite, so every light pays for the
whole screen. Here the march happens inside each light's own quad, bounded by
that light's reach - so a sconce lighting a corner of the room marches a
corner of the room.

What it does not do is 3D. There is no depth-sorted opaque pass against a
world-space position buffer, no shadow *map* - 2D shadows here are the mask
march above, not a depth render - and no model support. A scene with `Model3D`
nodes in it wants PBRPipeline; this one is for the other kind of game, and
says so by not pretending.
"""
import numpy as np

from FreeBodyEngine import get_service
from FreeBodyEngine.core.scene import SceneManager
from FreeBodyEngine.graphics.color import Color
from FreeBodyEngine.graphics.framebuffer import AttachmentFormat, AttachmentType
from FreeBodyEngine.graphics.lite.material import LiteMaterial
from FreeBodyEngine.graphics.material import BlendMode
from FreeBodyEngine.graphics.mesh import generate_quad
from FreeBodyEngine.graphics.pipeline import GraphicsPipeline
from FreeBodyEngine.math import Vector3


class LitePipeline(GraphicsPipeline):
    """Draws a 2D scene in three passes - see the module docstring."""

    tilemap_shader = ('engine://shader/lite/tilemap.fbvert',
                      'engine://shader/lite/tilemap.fbfrag')

    def on_initialize(self):
        super().on_initialize()
        self.scene_manager: SceneManager = get_service('scene_manager')

        size = get_service('window').framebuffer_size
        self.main_framebuffer = self.renderer.create_framebuffer(
            int(size[0]), int(size[1]),
            {
                # What a surface looks like, which way it faces, and what it
                # glows with. Five attachments against PBRPipeline's eight,
                # and every one of them eight bits - there is no world
                # position channel because the light pass interpolates it
                # (see lite/light.fbvert) and no roughness or metallic
                # because nothing here asks.
                'colour': (AttachmentType.COLOR, AttachmentFormat.RGBA8),
                'normal': (AttachmentType.COLOR, AttachmentFormat.RGBA8),
                'emmisive': (AttachmentType.COLOR, AttachmentFormat.RGBA8),
                'light': (AttachmentType.COLOR, AttachmentFormat.RGBA8),
                'lit': (AttachmentType.COLOR, AttachmentFormat.RGBA8),
                'depth': (AttachmentType.DEPTH, AttachmentFormat.DEPTH24),
            },
            transparent=True)

        self._surface_attachments = ['colour', 'normal', 'emmisive']
        self.output_channel = 'lit'

        files = get_service('files')
        self._light_shader = self.renderer.load_shader(
            files.get_file('engine://shader/lite/light.fbvert'),
            files.get_file('engine://shader/lite/light.fbfrag'))
        self._combine_shader = self.renderer.load_shader(
            files.get_file('engine://shader/lite/combine.fbvert'),
            files.get_file('engine://shader/lite/combine.fbfrag'))
        self._overlay_shader = self.renderer.load_shader(
            files.get_file('engine://shader/lite/overlay.fbvert'),
            files.get_file('engine://shader/lite/overlay.fbfrag'))

        # A unit quad, scaled and moved per light by its model matrix, and a
        # clip-space one for the combine pass.
        self._light_quad = generate_quad(1.0, 1.0)
        self._fullscreen_quad = generate_quad(2.0, 2.0)
        self._identity = np.identity(4, dtype=np.float32)

        self.ambient = Vector3(0.05, 0.05, 0.05)
        # Draws the surface colour with no light applied at all - for a scene
        # that wants flat art and no lighting model whatsoever.
        self.unlit = False

        # What blocks light, as a world-space mask - see set_occluders().
        self._occluder_texture = None
        self._occluder_origin = (0.0, 0.0)
        self._occluder_extent = (1.0, 1.0)
        # A light's apparent size in world units: 0 is a hard edge, larger
        # values widen the penumbra with distance from the occluder.
        self.shadow_softness = 0.0
        # How many samples the occlusion march takes toward each light. A
        # uniform rather than a baked constant - the march is a real loop here
        # (see lite/light.fbfrag), so this is tunable without recompiling,
        # which is the knob to reach for if shadows ever cost too much.
        self.shadow_steps = 14

    def create_material(self, data, injector=None) -> LiteMaterial:
        return LiteMaterial(data, injector)

    def resize(self, size: tuple[int, int]):
        self.main_framebuffer.resize(size)

    def set_occluders(self, texture, origin, extent):
        """Hands the light pass a world-space mask of what blocks light.

        `texture` is sampled in its red channel: anything above 0.5 is solid.
        `origin` is the world position of its bottom-left corner and `extent`
        the world size it covers, so a fragment maps into it by a subtract and
        a divide - the shader does no transform of its own.

        A mask rather than occluder geometry because the occluders in a tile
        game already are a grid: a texture lookup is the intersection test, so
        there is no per-light render pass and nothing to rebuild when a light
        moves. It only changes when the level does.

        The same signature as PBRPipeline.set_occluders, deliberately -
        Tilemap.cast_shadows duck-types on this method's presence and does not
        care which pipeline it is talking to, so a scene that cast shadows
        under PBRPipeline casts them here without being touched.

        Where the two differ is cost. PBR marches this mask inside its
        fullscreen composite, for every light at every pixel on screen; here
        the march happens inside each light's own quad, so a sconce reaching a
        tenth of the view pays for a tenth of the view.

        Pass `texture=None` to turn shadow casting off again. How soft the
        resulting shadows are is `shadow_softness`, set separately - it is a
        property of the lights, not of what blocks them.
        """
        self._occluder_texture = texture
        self._occluder_origin = (float(origin[0]), float(origin[1]))
        self._occluder_extent = (max(float(extent[0]), 1e-6), max(float(extent[1]), 1e-6))

    # -- collection --------------------------------------------------------

    def _collect(self, node, tilemaps, sprites, meshes, debugs, lights):
        """One walk of the tree, bucketing what it finds.

        A single pass rather than one per type: the tree is walked every
        frame, and walking it five times to ask five questions is four walks
        more than the answer needs.
        """
        if node.inherits_from('TilemapRenderer'):
            tilemaps.append(node)
        elif node.inherits_from('Sprite2D'):
            if node._sprite.visible:
                sprites.append(node)
        elif node.inherits_from('MeshNode2D'):
            meshes.append(node)
        elif node.inherits_from('Debug2D'):
            debugs.append(node)
        elif node.inherits_from('Light'):
            lights.append(node)

        for child_id in node.children:
            self._collect(node.children[child_id], tilemaps, sprites, meshes,
                          debugs, lights)

    # -- passes ------------------------------------------------------------

    def _view_rect(self, camera, margin: float):
        """The world rectangle the camera can see, widened by `margin`.

        Returns None whenever the camera is not the simple axis-aligned 2D
        case - culling something that should have been drawn is far worse
        than drawing something that did not need to be.
        """
        zoom = getattr(camera, 'zoom', None)
        if not zoom or zoom <= 0:
            return None
        size = get_service('window').size  # matches Camera._update_projection_matrix
        centre = camera.transform.position
        half_w = size[0] / 2.0 / zoom + margin
        half_h = size[1] / 2.0 / zoom + margin
        return (centre.x - half_w, centre.x + half_w,
                centre.y - half_h, centre.y + half_h)

    def _on_screen(self, node, view) -> bool:
        """Whether a sprite can touch the view at all.

        Residency keeps a room's nodes alive for a good distance past the
        edge of the screen (hotel.Hotel's margins are in hundreds of world
        units, and deliberately so - a room has to be standing before it
        scrolls into frame). At a zoom of 8 the camera sees about 120x90
        world units, so most of what is alive is nowhere near visible, and
        every one of those sprites was still costing a full draw call: its
        own uniform uploads, texture binds and draw. The tilemap had exactly
        this gap too (see TilemapRenderer._visible_chunks).

        The test is the sprite's own extent, not a fixed margin: a sprite is
        a unit quad scaled by its transform, so its scale *is* its world
        size, and a large one is correctly kept while its centre is still
        off screen.
        """
        transform = node.world_transform
        position = transform.position
        scale = transform.scale
        reach = max(abs(scale.x), abs(scale.y))
        return not (position.x + reach < view[0] or position.x - reach > view[1]
                    or position.y + reach < view[2] or position.y - reach > view[3])

    def _light_model(self, light) -> np.ndarray:
        """The model matrix putting a unit quad over a light's whole reach.

        Twice the range across, so the quad's edges sit exactly where the
        light's attenuation reaches zero - any larger is shading pixels that
        can only come out black, and any smaller clips the light.
        """
        position = light.world_position
        span = float(light.range) * 2.0

        # Row-vector convention, matching Transform.model: the renderer
        # multiplies `v @ M`, so the translation lives in the bottom row. Put
        # in the last column instead it is a shear, and the light's quad comes
        # out as a fan of streaks across the screen rather than a disc.
        model = np.identity(4, dtype=np.float32)
        model[0][0] = span
        model[1][1] = span
        model[3][0] = position.x
        model[3][1] = position.y
        return model

    def _draw_lights(self, camera, lights):
        """Accumulates every light into the light buffer, one quad each."""
        self.main_framebuffer.set_draw_buffers(['light'])
        # Cleared to the ambient rather than black: ambient is just the light
        # that reaches everywhere, so it belongs in the same buffer instead of
        # being a special case in the combine.
        self.main_framebuffer.clear_color_attachment(
            'light', (self.ambient.x, self.ambient.y, self.ambient.z, 1.0))

        if self.unlit:
            # Nothing accumulates, and the combine multiplies by a buffer of
            # flat white - the surface colour, untouched.
            self.main_framebuffer.clear_color_attachment('light', (1.0, 1.0, 1.0, 1.0))
            return

        self.renderer.disable_depth_testing()
        self.renderer.set_blend_mode(BlendMode.ADDITIVE)

        shader = self._light_shader
        shader['view'] = camera.view_matrix
        shader['proj'] = camera.proj_matrix
        shader['NormalMap'] = self.renderer.texture_manager.wrap_external_texture(
            self.main_framebuffer.get_attachment_texture('normal'))

        # Also per pass rather than per light: what blocks light is a property
        # of the level, identical for every light in the frame.
        if self._occluder_texture is not None:
            shader['OccluderEnabled'] = True
            shader['OccluderMap'] = self._occluder_texture
            shader['OccluderOrigin'] = self._occluder_origin
            shader['OccluderExtent'] = self._occluder_extent
            shader['ShadowSoftness'] = float(self.shadow_softness)
            shader['ShadowSteps'] = float(self.shadow_steps)
        else:
            shader['OccluderEnabled'] = False

        # Bound once, not per light. `use()` rebinds the program and every
        # texture the shader holds, and the normal map does not change between
        # lights - doing it inside the loop made a room of candles pay a
        # texture rebind each, which is most of what a light costs.
        shader.use()

        for light in lights:
            if not light.enabled:
                continue
            shader['model'] = self._light_model(light)
            shader['LightPos'] = (light.world_position.x, light.world_position.y)
            # Handed over as a Color - set_uniform knows how to unpack one
            # into a vec3, the same way the PBR light uniforms take it.
            shader['LightColor'] = light.color
            shader['LightIntensity'] = float(light.intensity)
            shader['LightRange'] = float(light.range)
            self._light_quad.draw()

        self.renderer.set_blend_mode(BlendMode.OPAQUE)

    def _combine(self):
        """Surface colour times the light that reached it, plus its glow."""
        textures = self.renderer.texture_manager
        shader = self._combine_shader
        for uniform, attachment in (('ColourMap', 'colour'), ('LightMap', 'light'),
                                    ('EmmisiveMap', 'emmisive')):
            shader[uniform] = textures.wrap_external_texture(
                self.main_framebuffer.get_attachment_texture(attachment))

        self.main_framebuffer.set_draw_buffers(['lit'])
        self.renderer.disable_depth_testing()
        shader.use()
        self._fullscreen_quad.draw()

    def _draw_overlay(self, camera, debugs):
        """Debug geometry, drawn over the finished image rather than into it.

        Through this pipeline's own shader rather than each gizmo's material,
        because a material here is a *surface* - it writes the three channels
        the light pass reads, and those land in slots this pass has disabled,
        so a gizmo drawn with one writes nothing at all. An overlay is not a
        surface: it is a flat colour laid on top, and it takes its colour from
        the material's emissive, which is where a gizmo's colour already lives
        (emissive being the one channel that survives being unlit).
        """
        if not debugs:
            return

        shader = self._overlay_shader
        shader['view'] = camera.view_matrix
        shader['proj'] = camera.proj_matrix

        self.main_framebuffer.set_draw_buffers(['lit'])
        self.renderer.disable_depth_testing()
        self.renderer.set_blend_mode(BlendMode.TRANSPARENT)

        for debug in debugs:
            if debug.draw_type != 'mesh' or debug.mesh is None:
                continue
            colour = debug.material.properties.get('emmisive')
            if colour is None:
                continue
            shader['model'] = debug.world_transform.model
            shader['Colour'] = colour
            shader.use()
            debug.mesh.draw()

        self.renderer.set_blend_mode(BlendMode.OPAQUE)

    # -- the frame ---------------------------------------------------------

    def draw(self):
        self.main_framebuffer.bind()
        camera = self.scene_manager.get_active().camera
        window_size = get_service('window').framebuffer_size

        if not camera:
            self.renderer.clear(Color("#000000FF"))
            self.main_framebuffer.draw(self.output_channel, window_size)
            self.main_framebuffer.unbind()
            return

        self.main_framebuffer.set_draw_buffers(
            self._surface_attachments + ['light', 'lit'])
        self.renderer.clear(camera.background_color)
        self.renderer.enable_depth_testing()
        self.main_framebuffer.set_draw_buffers(self._surface_attachments)

        tilemaps, sprites, meshes, debugs, lights = [], [], [], [], []
        self._collect(camera.scene.root, tilemaps, sprites, meshes, debugs, lights)

        for tilemap in tilemaps:
            tilemap.draw(camera)

        # A margin on top of each sprite's own extent, for a camera that lags
        # its target: it moves between this test and the frame being seen.
        view = self._view_rect(camera, 64.0)

        for sprite in sprites:
            if view is not None and not self._on_screen(sprite, view):
                continue
            self.renderer.submit(sprite._sprite.quad, sprite._sprite.material,
                                 sprite.world_transform, camera, z=sprite._sprite.z)

        for mesh_node in meshes:
            if view is not None and not self._on_screen(mesh_node, view):
                continue
            self.renderer.submit(mesh_node.mesh, mesh_node.material,
                                 mesh_node.world_transform, camera)

        self.renderer.flush_opaque()
        self.renderer.flush_transparent()

        self._draw_lights(camera, lights)
        self._combine()

        self._draw_overlay(camera, debugs)

        self.main_framebuffer.draw(self.output_channel, window_size)
        self.main_framebuffer.unbind()
