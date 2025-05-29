from FreeBodyEngine.core.node import Node2D
from FreeBodyEngine.math import Vector, Vector3

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from FreeBodyEngine.graphics.image import Image

class Sprite2D(Node2D):
    def __init__(self, image: 'Image', position: Vector = Vector(), rotaition: float = 0.0, scale: Vector = Vector(1, 1)):
        super().__init__(position, rotaition, scale)
        self.image = image
        


class Sprite3D(Node2D):
    def __init__(self, image: 'Image'):
        pass