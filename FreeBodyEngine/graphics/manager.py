from typing import TYPE_CHECKING, overload, Union
from FreeBodyEngine import log, warning
from FreeBodyEngine.graphics.image import Image 
from FreeBodyEngine.graphics.sprite import Sprite2D, Sprite
from FreeBodyEngine.graphics.image import Image 
from FreeBodyEngine.math import GenericVector, Transform
from dataclasses import dataclass
from FreeBodyEngine.graphics.debug import Debug2D

from FreeBodyEngine.graphics.framebuffer import AttachmentFormat, AttachmentType

if TYPE_CHECKING:
    from FreeBodyEngine.core.main import Main
    from FreeBodyEngine.core.scene import Scene
    from FreeBodyEngine.core.camera import Camera
    from FreeBodyEngine.core.window import Window
    from FreeBodyEngine.graphics.renderer import Renderer

RENDERING_MODES = ["full", "albedo", "lighting", "normal", "emission"]

@dataclass 
class DrawCall:
    obj: any
    pos: GenericVector


class GraphicsManager:
    """
    The graphics manager.
    
    :param main: The main object.
    :type main: Main
    """
    def __init__(self, main: 'Main', renderer: 'Renderer', window: 'Window'):
        self.main = main
        self.rendering_mode = "full"
        self.renderer = renderer
        self.window = window
        self.draw_calls: list[DrawCall] = []

        self.main_framebuffer = self.renderer.create_framebuffer(int(self.window.size[0]), int(self.window.size[1]), {
            'albedo': (AttachmentType.COLOR, AttachmentFormat.RGBA8),
            'normal': (AttachmentType.COLOR, AttachmentFormat.RGBA8),
            'emmision': (AttachmentType.COLOR, AttachmentFormat.RGBA8),
            'roughness': (AttachmentType.COLOR, AttachmentFormat.R8),
            'metallic': (AttachmentType.COLOR, AttachmentFormat.R8),
            'depth': (AttachmentType.DEPTH, AttachmentFormat.DEPTH24)
            }
        )
    
    def resize(self):
        self.main_framebuffer.resize(self.window.size)

    def _draw_sprite(self, sprite: Sprite, transform: Transform, camera: 'Camera2D'):
        self.renderer.draw_mesh(sprite.quad, sprite.material, transform, camera)

    def load_material(self, data):
        return self.renderer.load_material(data)

    def load_image(self, data):
        return self.renderer.load_image(data)

    def _draw_2D(self, camera: 'Camera2D'):
        """
        Draws the scene from the perspective of a camera.

        :pararm camera: The camera that the scene will be drawn from.
        :type camera: Camera
        """
        
        self.main_framebuffer.bind()
        self.renderer.clear(camera.background_color)
        
        sprites: list[Sprite2D] = camera.scene.root.find_nodes_with_type('Sprite2D')
        for sprite in sprites:
            self._draw_sprite(sprite._sprite, sprite.world_transform, camera)

        debugs: list[Debug2D] = camera.scene.root.find_nodes_with_type('Debug2D')
        for debug in debugs:
            self.renderer.draw_mesh(debug.mesh, debug.material, debug.world_transform, camera)


        self.main_framebuffer.unbind()
        self.main_framebuffer.draw('albedo', self.window.size)


    def draw(self, camera):
        """Draws a scene from the perspective of a camera."""
        
        self._draw_2D(camera)


class GraphicsPipeline:
    def __init__(self):
        pass

    def draw_scene(self, scene: 'Scene', camera: 'Camera'):
        pass