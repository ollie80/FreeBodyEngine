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
    def __init__(self, texture: 'Texture', material: 'Material', renderer: 'Renderer', visisble: bool = True, z: float = 0, normal: 'Texture' = None):
        """Stores `texture`/`material`/`renderer`, assigns `texture` onto
        the material's `albedo` property, and generates the flat quad mesh
        this sprite is drawn with. `z` is a world-space depth nudge applied
        on top of this sprite's own (Z-less - see math.py's Transform)
        position/rotation/scale - see Renderer._z_offset_matrix() - so two
        sprites positioned identically in 2D can still resolve the depth
        test predictably (e.g. one drawn on top of the other) instead of
        tying at an identical depth. Matters most for a transparent-blend
        sprite: it's forward-shaded in a pass that runs after every opaque
        draw's depth is already committed (see PBRPipeline's module
        docstring), so without a `z` nudge it always ties - and loses,
        GL_LESS never passes on equal depth - against any opaque geometry
        already sitting at the same depth underneath it (e.g. a floor
        tile), rendering as invisible no matter what order it was drawn in."""
        self.renderer = renderer
        self.z = z

        self.texture = texture
        # A per-object copy, because the next line writes this sprite's own
        # texture into the material's albedo slot - and a `.fbmat` is cached
        # per path, so every sprite loaded from the same material file would
        # otherwise share one slot and the last one constructed would win for
        # all of them. See Material.instance().
        self.material = material.instance()
        self.material.properties['albedo'] = self.texture

        # A normal map is set only when there is one: leaving the property
        # absent (rather than present and zero) keeps a colour-only sprite
        # lit by its geometric normal, which is what the lighting composite
        # falls back to - see graphics/pbr/shaders.py.
        self.normal = normal
        if normal is not None:
            self.material.properties['normal'] = normal
        self.quad = generate_quad()
        self.visisble = visisble
    

class Sprite2D(Node2D):
    """Positions a Sprite in 2D space by wrapping it in a Node2D, so it can
    be added to the node tree and inherit a world transform - the Sprite
    itself stays transform-less."""
    def __init__(self, sprite: Sprite, position: Vector = Vector(), rotaition: float = 0.0, scale: Vector = Vector(1, 1), z: Optional[float] = None):
        """Wraps `sprite` with a 2D Transform (`position`/`rotaition`/
        `scale`) so it can be parented into the node tree.

        `z` defaults to None - meaning "leave the Sprite's own z alone" -
        rather than 0, because `sprite` usually arrives already carrying
        one: a `.fbspr` can declare `z` and its loader passes it to the
        Sprite constructor (see core/files/loaders/sprite.py). This used to
        assign `self._sprite.z = z` unconditionally, so merely wrapping a
        loaded sprite in a Sprite2D silently reset that declared z to 0 and
        every `z = ...` line in a `.fbspr` was dead. Pass a float here only
        to deliberately override the file."""
        super().__init__(position, rotaition, scale)
        self._sprite = sprite
        if z is not None:
            self._sprite.z = z

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
        frame = self.player.frame
        sprite = Sprite(frame.texture, material, renderer, visible, z, frame.normal)
        # `z` is given to the Sprite above and deliberately not forwarded to
        # Sprite2D, whose None default now leaves an already-set z alone.
        # Forwarding 0 here is exactly the bug that made every animated
        # sprite's z a no-op: the Sprite was built with the caller's z and
        # Sprite2D.__init__ then overwrote it with its own default.
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
            frame = self.player.frame
            self._sprite.material.albedo = frame.texture
            # Reassigned alongside the albedo so relief tracks the animation
            # rather than staying on whichever frame happened to be first.
            # Guarded on the property existing, since a colour-only
            # animation's Sprite never created one (see Sprite.__init__) and
            # Material.__setattr__ only redirects to a key already present -
            # assigning it anyway would silently set a plain attribute that
            # use() never uploads.
            if frame.normal is not None and 'normal' in self._sprite.material.properties:
                self._sprite.material.properties['normal'] = frame.normal

