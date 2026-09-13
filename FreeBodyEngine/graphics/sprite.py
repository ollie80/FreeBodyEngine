from FreeBodyEngine.core.node import Node2D
from FreeBodyEngine.math import Vector, Vector3
from FreeBodyEngine.graphics.mesh import generate_quad
from FreeBodyEngine.graphics.animation import AnimationSet, AnimationPlayer
from FreeBodyEngine import delta

from typing import TYPE_CHECKING, Optional
if TYPE_CHECKING:
    from FreeBodyEngine.graphics.texture import Texture
    from FreeBodyEngine.graphics.material import Material
    from FreeBodyEngine.core.scene import Scene
    from FreeBodyEngine.graphics.renderer import Renderer

class Sprite:
    def __init__(self, texture: 'Texture', material: 'Material', renderer: 'Renderer', visisble: bool = True, z=0):
        self.renderer = renderer
        self.z = z

        self.texture = texture
        self.material = material
        self.material.properties['albedo'] = self.texture
        self.quad = generate_quad()
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


class AnimatedSprite2D(Sprite2D):
    """A Sprite2D whose texture is driven by an AnimationPlayer instead of
    staying fixed. `material` must already define an `albedo` property
    (e.g. loaded from a `.fbmat` file) - each frame change reassigns it to
    that frame's texture."""
    def __init__(self, animation_set: AnimationSet, material: 'Material', renderer: 'Renderer', default_animation: Optional[str] = None, position: Vector = Vector(), rotation: float = 0.0, scale: Vector = Vector(1, 1), visible: bool = True, z=0):
        self.player = AnimationPlayer(animation_set, default_animation)
        sprite = Sprite(self.player.frame.texture, material, renderer, visible, z)
        super().__init__(sprite, position, rotation, scale)

    def set_animation(self, name: str, restart: bool = False):
        self.player.set_animation(name, restart)

    def on_update(self):
        if self.player.update(delta()):
            self._sprite.material.albedo = self.player.frame.texture

