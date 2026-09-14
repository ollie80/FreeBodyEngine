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
    """A drawable unit combining a texture, material, and generated quad
    mesh, independent of the node tree - Sprite2D/Sprite3D each wrap one to
    give it a scene position via a Transform."""
    def __init__(self, texture: 'Texture', material: 'Material', renderer: 'Renderer', visisble: bool = True, z=0):
        """Stores `texture`/`material`/`renderer`, assigns `texture` onto
        the material's `albedo` property, and generates the flat quad mesh
        this sprite is drawn with."""
        self.renderer = renderer
        self.z = z

        self.texture = texture
        self.material = material
        self.material.properties['albedo'] = self.texture
        self.quad = generate_quad()
        self.visisble = visisble
    

class Sprite2D(Node2D):
    """Positions a Sprite in 2D space by wrapping it in a Node2D, so it can
    be added to the node tree and inherit a world transform - the Sprite
    itself stays transform-less."""
    def __init__(self, sprite: Sprite, position: Vector = Vector(), rotaition: float = 0.0, scale: Vector = Vector(1, 1)):
        """Wraps `sprite` with a 2D Transform (`position`/`rotaition`/
        `scale`) so it can be parented into the node tree."""
        super().__init__(position, rotaition, scale)
        self._sprite = sprite

    def on_draw(self):
        """Draws the wrapped sprite. Mirrors the `Node.on_draw` hook
        pattern (see core/node.py)."""
        self._sprite.draw()

class Sprite3D(Node2D):
    """Intended 3D counterpart to Sprite2D for positioning a Sprite via a
    3D transform."""
    def __init__(self, image: 'Image'):
        """Not yet implemented - accepts an image but does not initialize
        the node or store anything."""
        pass


class AnimatedSprite2D(Sprite2D):
    """A Sprite2D whose texture is driven by an AnimationPlayer instead of
    staying fixed. `material` must already define an `albedo` property
    (e.g. loaded from a `.fbmat` file) - each frame change reassigns it to
    that frame's texture."""
    def __init__(self, animation_set: AnimationSet, material: 'Material', renderer: 'Renderer', default_animation: Optional[str] = None, position: Vector = Vector(), rotation: float = 0.0, scale: Vector = Vector(1, 1), visible: bool = True, z=0):
        """Builds an AnimationPlayer for `animation_set`, wraps its current
        frame's texture in a fresh Sprite, and initializes as a Sprite2D
        with that sprite - so the sprite's texture starts out driven by the
        animation player from the very first frame."""
        self.player = AnimationPlayer(animation_set, default_animation)
        sprite = Sprite(self.player.frame.texture, material, renderer, visible, z)
        super().__init__(sprite, position, rotation, scale)

    def set_animation(self, name: str, restart: bool = False):
        """Switches the underlying AnimationPlayer to the animation named
        `name`, optionally restarting it from frame zero even if it's
        already the active animation."""
        self.player.set_animation(name, restart)

    def on_update(self):
        """Advances the AnimationPlayer by this frame's delta time and, if
        that changed the current frame, reassigns the sprite's material
        `albedo` to the new frame's texture."""
        if self.player.update(delta()):
            self._sprite.material.albedo = self.player.frame.texture

