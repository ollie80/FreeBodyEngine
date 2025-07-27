from FreeBodyEngine.graphics.pipeline import GraphicsPipeline
from FreeBodyEngine.core.scene import SceneManager
from FreeBodyEngine import get_service
from FreeBodyEngine.graphics.color import Color

from FreeBodyEngine.graphics.framebuffer import AttachmentFormat, AttachmentType
from FreeBodyEngine.core.tilemap import TilemapRenderer
from FreeBodyEngine.graphics.sprite import Sprite2D, Sprite
from FreeBodyEngine.graphics.debug import Debug2D

class PBRPipeline(GraphicsPipeline):
    def __init__(self):
        super().__init__()
        self.dependencies.append('scene_manager')
        

    def on_initialize(self):
        super().on_initialize()
        self.scene_manager = get_service('scene_manager')
        self.scene_manager: SceneManager
        
        self.main_framebuffer = self.renderer.create_framebuffer(int(get_service('window').size[0]), int(get_service('window').size[1]), {
            'albedo': (AttachmentType.COLOR, AttachmentFormat.RGBA8),
            'normal': (AttachmentType.COLOR, AttachmentFormat.RGBA8),
            'emmision': (AttachmentType.COLOR, AttachmentFormat.RGBA8),
            'roughness': (AttachmentType.COLOR, AttachmentFormat.R8),
            'metallic': (AttachmentType.COLOR, AttachmentFormat.R8),
            'depth': (AttachmentType.DEPTH, AttachmentFormat.DEPTH24)
        }, transparent = True
        )
        
    def resize(self):
        self.main_framebuffer.resize(get_service('window').size)

    def draw(self):
        self.main_framebuffer.bind()
        camera = self.scene_manager.get_active().camera
        self.renderer.clear(camera.background_color)
        
        tilemaps: list[TilemapRenderer] = camera.scene.root.find_nodes_with_type('TilemapRenderer')
        for tilemap in tilemaps:
            tilemap.draw()
            

        sprites: list[Sprite2D] = camera.scene.root.find_nodes_with_type('Sprite2D')
        for sprite in sprites:
            self.renderer.draw_mesh(sprite._sprite.quad, sprite._sprite.material, sprite.world_transform, camera)

        debugs: list[Debug2D] = camera.scene.root.find_nodes_with_type('Debug2D')
        for debug in debugs:
            self.renderer.draw_mesh(debug.mesh, debug.material, debug.world_transform, camera)

        self.main_framebuffer.unbind()
        self.main_framebuffer.draw('albedo', get_service('window').size)


        