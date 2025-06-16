from FreeBodyEngine.core.node import Node2D
from FreeBodyEngine.math import Vector, Vector3

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from FreeBodyEngine.graphics.image import Image
    from FreeBodyEngine.graphics.material import Material
    from FreeBodyEngine.core.scene import Scene

class Sprite:
    def __init__(self, image: 'Image', material: 'Material', visisble: bool = True, z=0):
        self.z = z

        self.image = image
        self.material = material

        self.visisble = visisble
    

class Sprite2D(Node2D):
    def __init__(self, sprite: Sprite, position: Vector = Vector(), rotaition: float = 0.0, scale: Vector = Vector(1, 1)):
        super().__init__(position, rotaition, scale)
        self._sprite = sprite
    
    def on_draw(self):
        self._sprite.draw()


class Sprite3D(Node2D):
    def __init__(self, image: 'Image'):
        pass