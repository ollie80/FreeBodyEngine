from FreeBodyEngine.graphics.pipeline import GraphicsPipeline
from FreeBodyEngine.core.scene import SceneManager
from FreeBodyEngine import get_service
from FreeBodyEngine.graphics.color import Color
from FreeBodyEngine.graphics.pbr.material import PBRMaterial

from FreeBodyEngine.graphics.framebuffer import AttachmentFormat, AttachmentType
from FreeBodyEngine.core.tilemap.renderer import TilemapRenderer
from FreeBodyEngine.graphics.sprite import Sprite2D, Sprite
from FreeBodyEngine.graphics.debug import Debug2D
from FreeBodyEngine.graphics.model.model import Model3D

from FreeBodyEngine.math import Transform
from FreeBodyEngine.core.camera import Camera
from FreeBodyEngine.graphics.mesh import Mesh
from FreeBodyEngine.graphics.material import Material

class PBRPipeline(GraphicsPipeline):
    """GraphicsPipeline for physically-based rendering: draws the active
    scene's tilemaps, 2D sprites, debug draws, and 3D models into a
    multi-attachment G-buffer (`main_framebuffer`) - albedo, normal,
    emission, roughness, metallic, plus full-precision world position/
    normal - then presents one selected attachment (`output_channel`) to
    the window. A downstream lighting pass can read the other G-buffer
    attachments back before/instead of that final blit.
    """
    def __init__(self):
        """Adds 'scene_manager' as a service dependency, alongside GraphicsPipeline's own 'renderer' dependency."""
        super().__init__()
        self.dependencies.append('scene_manager')

    def on_initialize(self):
        """Fetches the 'scene_manager' service and creates `main_framebuffer`,
        a window-sized G-buffer with one attachment per PBR channel (see
        class docstring) plus a depth attachment; `output_channel` defaults
        to 'albedo'."""
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
            # (see GLFramebuffer's attachment-index assignment). A lighting
            # pass (e.g. RaytraceDemo's raytraced-shadows pass) reads these
            # back to reconstruct per-pixel world position/normal without
            # needing the camera's inverse view-projection matrix at all.
            'gWorldPos': (AttachmentType.COLOR, AttachmentFormat.RGBA32F),
            'gWorldNormal': (AttachmentType.COLOR, AttachmentFormat.RGBA32F),
            'depth': (AttachmentType.DEPTH, AttachmentFormat.DEPTH24)
        }, transparent = True
        )
        self.output_channel = 'albedo' 
        

    def draw_world_mesh(self, mesh: Mesh, material: Material, transform: Transform, camera: Camera, instances: int = 1):
        """Sets `material`'s model/view/proj uniforms from `transform`/`camera`
        and draws `mesh` - instanced via draw_mesh_instanced() if
        `instances` is more than 1, otherwise a plain draw_mesh() call."""
        if instances == 1:
            material.shader['model'] = transform.model
            material.shader['view'] = camera.view_matrix
            material.shader['proj'] = camera.proj_matrix

            self.renderer.draw_mesh(mesh, material)
        else:
            material.shader['model'] = transform.model
            material.shader['view'] = camera.view_matrix
            material.shader['proj'] = camera.proj_matrix

            self.renderer.draw_mesh_instanced(mesh, material, instances)
        

    def resize(self, size: tuple[int, int]):
        """Resizes `main_framebuffer` to match the new framebuffer `size`."""

        self.main_framebuffer.resize(size)

    def draw(self):
        """Renders one frame: binds `main_framebuffer`, clears it (re-clearing
        `gWorldPos`'s alpha to 0 so "no geometry here" stays distinguishable
        from real geometry), draws every TilemapRenderer/Sprite2D/Debug2D/
        Model3D in the active scene's tree, then unbinds and blits
        `output_channel` to the window. Falls back to just clearing the
        window to opaque black if the active scene has no camera."""
        self.main_framebuffer.bind()
        camera = self.scene_manager.get_active().camera
        if camera:
            self.renderer.clear(camera.background_color)
            # Renderer.clear() clears every bound draw buffer to the same
            # color, including camera.background_color's alpha (1.0, since
            # it's meant to look opaque on screen) - that would leave
            # gWorldPos.w indistinguishable between "background, nothing
            # rasterized here" and "real geometry, happens to sit exactly at
            # this alpha" for any lighting pass trying to tell them apart
            # (see default_shader.fbfrag's gWorldPos/gWorldNormal outputs).
            # Re-clearing just this channel to alpha 0 after the general
            # clear keeps that a reliable sentinel.
            self.main_framebuffer.clear_color_attachment('gWorldPos', (0.0, 0.0, 0.0, 0.0))
            self.renderer.enable_depth_testing()

            tilemaps: list[TilemapRenderer] = camera.scene.root.find_nodes_with_type('TilemapRenderer')
            for tilemap in tilemaps:
                
                tilemap.draw(camera)

            sprites: list[Sprite2D] = camera.scene.root.find_nodes_with_type('Sprite2D')
            for sprite in sprites:
                self.draw_world_mesh(sprite._sprite.quad, sprite._sprite.material, sprite.world_transform, camera)

            debugs: list[Debug2D] = camera.scene.root.find_nodes_with_type('Debug2D')
            for debug in debugs: 
                self.draw_world_mesh(debug.mesh, debug.material, debug.world_transform, camera)


            models: list[Model3D] = camera.scene.root.find_nodes_with_type('Model3D')
            for model in models:    
                self.renderer.draw_model(
                    model._model, model.world_transform, camera)
                
            self.renderer.disable_depth_testing()

            self.main_framebuffer.unbind()
            window_size = get_service('window').framebuffer_size
            self.main_framebuffer.draw(self.output_channel, window_size)
        else:
            
            self.renderer.clear(Color("#000000FF"))
            window_size = get_service('window').framebuffer_size
            self.main_framebuffer.draw(self.output_channel, window_size)
        self.main_framebuffer.unbind()

    def create_material(self, data, injector):
        """Builds a PBRMaterial from `data`, using `injector` to resolve FBUSL builtins."""
        return PBRMaterial(data, injector)
