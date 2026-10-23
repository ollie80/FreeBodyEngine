from FreeBodyEngine.core.node import Node2D
from FreeBodyEngine.math import Vector
from FreeBodyEngine.graphics.mesh import generate_quad
from FreeBodyEngine.graphics.animation import AnimationSet, AnimationPlayer
from FreeBodyEngine.graphics.texture import Texture
from FreeBodyEngine import delta, get_service

from typing import TYPE_CHECKING, Optional
if TYPE_CHECKING:
    from FreeBodyEngine.graphics.material import Material


# One unit quad per renderer, shared by every sprite - each sprite used to
# build its own identical mesh. Keyed by renderer so a second engine started
# in the same process doesn't draw with the first one's GPU buffers.
_quads: dict[int, object] = {}


def _shared_quad():
    renderer = get_service('renderer')
    key = id(renderer)
    if key not in _quads:
        _quads[key] = generate_quad()
    return _quads[key]


def default_sprite_material() -> 'Material':
    """The material a sprite gets when none is given: the active pipeline's
    default shader, alpha-blended. Blended rather than opaque because sprites
    are nearly always cut-outs, and an opaque one writes its transparent
    corners into PBR's G-buffer as black - a black box around every sprite.
    Built once per pipeline."""
    pipeline = get_service('graphics')
    material = getattr(pipeline, '_default_sprite_material', None)
    if material is None:
        material = pipeline.create_material({'blend': 'transparent'}, None)
        pipeline._default_sprite_material = material
    return material


class Sprite:
    """A drawable unit: a texture, a material, and - if it animates - the
    animations it plays, independent of the node tree. Sprite2D gives one a
    place in the scene.

    Loading a `.fbspr` gives one; Sprite2D also builds one itself when handed
    a loaded animation or image."""
    def __init__(self, texture: 'Texture', material: 'Material' = None, visible: bool = True,
                 z: float = 0, normal: 'Texture' = None, animations: AnimationSet = None):
        """Assigns `texture` onto the material's `albedo` property. With no
        `material`, the pipeline's default sprite material is used (see
        default_sprite_material()). `z` is a world-space depth nudge applied
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
        tile), rendering as invisible no matter what order it was drawn in.

        `animations`, if given, are what a Sprite2D showing this sprite plays.
        """
        self.z = z
        self.animations = animations

        self.texture = texture
        # A per-object copy, because the next line writes this sprite's own
        # texture into the material's albedo slot - and a `.fbmat` is cached
        # per path, so every sprite loaded from the same material file would
        # otherwise share one slot and the last one constructed would win for
        # all of them. See Material.instance().
        self.material = (material if material is not None else default_sprite_material()).instance()
        self.material.properties['albedo'] = self.texture

        # A normal map is set only when there is one: leaving the property
        # absent (rather than present and zero) keeps a colour-only sprite
        # lit by its geometric normal, which is what the lighting composite
        # falls back to - see graphics/pbr/shaders.py.
        self.normal = normal
        if normal is not None:
            self.material.properties['normal'] = normal
        self.quad = _shared_quad()
        self.visible = visible

    @classmethod
    def from_animations(cls, animations: AnimationSet, material: 'Material' = None, **kwargs) -> 'Sprite':
        """A sprite that plays `animations`, starting on the first frame of
        the first one."""
        if not animations.animations:
            raise ValueError("AnimationSet contains no animations")
        first = next(iter(animations.animations.values())).frames[0]
        return cls(first.texture, material, normal=first.normal, animations=animations, **kwargs)

    def instance(self) -> 'Sprite':
        """Returns a per-object copy of this Sprite: its own `visible`, `z`
        and material, sharing the same texture and animations.

        Exactly the problem `Material.instance()` solves, one level up. An
        `.fbspr` is cached per path while hot reload is on (see
        core/files/loaders/sprite.py), so every node loaded from one sprite
        file was handed the *same* Sprite - and `visible` lives on the Sprite,
        with Sprite2D.visible being a straight proxy to it. Two nodes from one
        file could not then be shown and hidden independently: hiding one hid
        every one of them, and showing one showed them all.

        That is a trap rather than a quirk, because of how it presents. The
        obvious way to build a set of identical things - a row of candles, all
        loading `flame.fbspr` - gives each its own light, its own position and
        its own everything *except* the one piece of state the game actually
        toggles. Lighting a single candle lit every flame in the level while
        only one of them emitted any light.

        Worse, it only happened in dev: the cache is gated on DEVMODE, so a
        release build constructed a fresh Sprite per load and behaved
        correctly. Returning an instance here makes the two agree, and makes
        the dev path the one that is correct rather than the one that is fast.
        """
        return Sprite(self.texture, self.material, self.visible, self.z, self.normal, self.animations)


def _as_sprite(source, material: 'Material' = None) -> Sprite:
    """Whatever Sprite2D was handed, as a Sprite: a loaded Sprite as-is (with
    `material` swapped in if one was given), or one built around a loaded
    animation set or image."""
    if isinstance(source, Sprite):
        if material is not None:
            return Sprite(source.texture, material, source.visible, source.z, source.normal, source.animations)
        return source
    if isinstance(source, AnimationSet):
        return Sprite.from_animations(source, material)
    if isinstance(source, Texture):
        return Sprite(source, material)
    raise TypeError(
        f"Sprite2D takes a loaded Sprite (.fbspr), animation set (.fbanim) or image, "
        f"not {type(source).__name__}. Load the file first with fb.load_file().")


class Sprite2D(Node2D):
    """Draws a sprite in 2D space, and plays its animations if it has any.

    Takes whatever was loaded - a Sprite from a `.fbspr`, an animation set
    from a `.fbanim`, or an image - building the Sprite itself for the last
    two (with the pipeline's default material unless `material` is given):

        fb.Sprite2D(fb.load_file("graphics/coin.fbspr"))
        fb.Sprite2D(fb.load_file("graphics/player.fbanim"), animation="idle")
        fb.Sprite2D(fb.load_file("graphics/rock.png"))
    """
    def __init__(self, source, position: Vector = Vector(), rotation: float = 0.0, scale: Vector = Vector(1, 1),
                 z: Optional[float] = None, material: 'Material' = None, animation: Optional[str] = None,
                 visible: Optional[bool] = None):
        """`z` and `visible` default to None - meaning "leave the Sprite's own
        alone" - because a loaded sprite usually arrives already carrying
        them from its `.fbspr` (see core/files/loaders/sprite.py). Wrapping it
        used to reset a declared z to 0, so every `z = ...` line in a `.fbspr`
        was dead. Pass a value only to deliberately override the file.

        `animation` picks which animation to start on; the first one
        otherwise."""
        super().__init__(position, rotation, scale)
        self._sprite = _as_sprite(source, material)
        if z is not None:
            self._sprite.z = z
        if visible is not None:
            self._sprite.visible = visible

        # Mirror the sprite horizontally / vertically when drawn - see
        # draw_transform.
        self.flip_x = False
        self.flip_y = False
        # Playback rate: 2.0 plays animations twice as fast.
        self.speed = 1.0
        self.playing = True

        self._player = None
        if self._sprite.animations is not None:
            self._player = AnimationPlayer(self._sprite.animations, animation)
            self._show_frame()

    # -- the sprite ------------------------------------------------------

    @property
    def sprite(self) -> Sprite:
        """The Sprite being drawn."""
        return self._sprite

    @property
    def visible(self) -> bool:
        """Whether this sprite is drawn at all. The pipeline skips it entirely
        when False, so hiding something costs nothing and - unlike scaling it
        to zero - does not leave a transform whose rotation cannot be
        recovered."""
        return self._sprite.visible

    @visible.setter
    def visible(self, value: bool):
        self._sprite.visible = value

    @property
    def z(self) -> float:
        """Depth nudge - see Sprite.__init__. Higher draws in front."""
        return self._sprite.z

    @z.setter
    def z(self, value: float):
        self._sprite.z = value

    @property
    def material(self) -> 'Material':
        """This sprite's own copy of its material - set shader uniforms on it
        (`sprite.material.shader['Tint'] = ...`) without affecting other
        sprites using the same `.fbmat`."""
        return self._sprite.material

    @property
    def texture(self) -> 'Texture':
        """The image currently shown - the current frame, while animating."""
        return self._sprite.texture

    @texture.setter
    def texture(self, value: 'Texture'):
        self._sprite.texture = value
        self._sprite.material.properties['albedo'] = value

    @property
    def draw_transform(self):
        """The transform the pipeline draws with: the world transform, its
        scale negated on whichever axes are flipped."""
        transform = self.world_transform
        if not (self.flip_x or self.flip_y):
            return transform
        transform = transform.copy()
        if self.flip_x:
            transform.scale.x = -transform.scale.x
        if self.flip_y:
            transform.scale.y = -transform.scale.y
        return transform

    # -- animation -------------------------------------------------------

    @property
    def animations(self) -> list[str]:
        """The names of the animations this sprite can play - empty for a
        still one."""
        return list(self._sprite.animations.animations) if self._sprite.animations is not None else []

    @property
    def animation(self) -> Optional[str]:
        """The animation being played, or None for a still sprite. Setting it
        is play(name)."""
        return self._player.current_animation if self._player is not None else None

    @animation.setter
    def animation(self, name: str):
        self.play(name)

    @property
    def frame(self) -> int:
        """The current frame's index within the current animation."""
        return self._player.frame_index if self._player is not None else 0

    @property
    def finished(self) -> bool:
        """Whether a non-looping animation has reached its end. Never true
        for a looping one."""
        return self._player is not None and self._player.finished

    def play(self, name: Optional[str] = None, restart: bool = False):
        """Plays animation `name` - from the start unless it's already the one
        playing (pass `restart=True` to start it over anyway). With no name,
        resumes the current one after stop()."""
        self.playing = True
        if self._player is None:
            from FreeBodyEngine import warning
            warning(f'{self} has no animations to play.')
            return
        if name is not None:
            before = (self._player.current_animation, self._player.frame_index)
            self._player.set_animation(name, restart)
            if (self._player.current_animation, self._player.frame_index) != before:
                self._show_frame()

    def stop(self):
        """Pauses on the current frame; play() resumes."""
        self.playing = False

    def update(self):
        # Advanced here rather than in on_update(), so a subclass overriding
        # on_update() - the usual thing to do with a node - doesn't stop its
        # own animation by forgetting to call super().
        if self._player is not None and self.playing:
            if self._player.update(delta() * self.speed):
                self._show_frame()
        super().update()

    def _show_frame(self):
        frame = self._player.frame
        self._sprite.texture = frame.texture
        self._sprite.material.properties['albedo'] = frame.texture
        # Reassigned alongside the albedo so relief tracks the animation
        # rather than staying on whichever frame happened to be first. Only
        # where the sprite has a normal map: a colour-only one never created
        # the property (see Sprite.__init__), and adding it would stop it
        # being lit by its geometric normal.
        if frame.normal is not None and 'normal' in self._sprite.material.properties:
            self._sprite.material.properties['normal'] = frame.normal
