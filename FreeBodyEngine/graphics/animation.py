from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from FreeBodyEngine.graphics.texture import Texture


@dataclass
class AnimationFrame:
    """A single frame of an animation. `texture` may be a whole standalone
    image, or a Texture whose uv_rect has already been narrowed down to one
    cell of a spritesheet image."""
    texture: 'Texture'
    duration: float


@dataclass
class Animation:
    """A single named animation: its ordered frames and whether it loops
    back to the first frame after the last, or holds on it."""
    name: str
    frames: list[AnimationFrame]
    loop: bool = True


class AnimationSet:
    """The parsed contents of a `.fbanim` file: every named animation it defines."""
    def __init__(self, animations: dict[str, Animation]):
        """Wraps an already-built name -> Animation mapping."""
        self.animations = animations

    def get(self, name: str) -> Animation:
        """Returns the Animation named `name` - raises KeyError if it isn't
        in this set."""
        return self.animations[name]

    def __contains__(self, name: str) -> bool:
        return name in self.animations


class AnimationPlayer:
    """Advances an AnimationSet's frames over time for a single sprite instance."""
    def __init__(self, animation_set: AnimationSet, default: Optional[str] = None):
        """Starts playback of `default` (or, if omitted, whichever
        animation happens to be first in `animation_set` - dict insertion
        order, i.e. the order it was defined in the `.fbanim` file) at its
        first frame."""
        self.animation_set = animation_set

        if default is None:
            default = next(iter(animation_set.animations))

        self.current_animation = default
        self.frame_index = 0
        self.elapsed = 0.0

    @property
    def animation(self) -> Animation:
        """The Animation currently playing."""
        return self.animation_set.animations[self.current_animation]

    @property
    def frame(self) -> AnimationFrame:
        """The frame currently being displayed."""
        return self.animation.frames[self.frame_index]

    def set_animation(self, name: str, restart: bool = False):
        """Switches playback to the animation named `name`. If it's already
        the current animation, this is a no-op unless `restart` is True, in
        which case playback jumps back to frame 0. Warns and does nothing
        if `name` doesn't exist in this player's AnimationSet."""
        if name not in self.animation_set.animations:
            from FreeBodyEngine import warning
            warning(f'Animation "{name}" does not exist.')
            return

        if name != self.current_animation or restart:
            self.current_animation = name
            self.frame_index = 0
            self.elapsed = 0.0

    def update(self, dt: float) -> bool:
        """Advances playback by dt seconds. Returns True if the current frame changed."""
        anim = self.animation
        if len(anim.frames) <= 1:
            return False

        self.elapsed += dt
        changed = False

        frame = anim.frames[self.frame_index]
        while self.elapsed >= max(frame.duration, 1e-4):
            self.elapsed -= frame.duration

            if self.frame_index + 1 < len(anim.frames):
                self.frame_index += 1
                changed = True
            elif anim.loop:
                self.frame_index = 0
                changed = True
            else:
                break

            frame = anim.frames[self.frame_index]

        return changed
