from typing import Optional

from FreeBodyEngine.core.files import FileResource, load_file, SPRITESHEET_FILE
from FreeBodyEngine.core.files.loaders.toml import load_toml
from FreeBodyEngine.graphics.animation import Animation, AnimationFrame, AnimationSet
from FreeBodyEngine.graphics.spritesheet import Spritesheet
from FreeBodyEngine import warning

SPRITESHEET_KEY = 'spritesheet'


def load_animation(file: FileResource) -> AnimationSet:
    """Loads a `.fbanim` file: a TOML document that may set a top-level
    default `spritesheet` path, plus any number of `[name]` tables - each a
    named animation with an optional `loop` flag, an optional per-animation
    `spritesheet` override, and a `frames` list. Each frame gives a
    `duration` and either a `pos = [col, row]` cell to slice out of the
    active spritesheet, or a standalone `image` path that replaces the
    spritesheet for that one frame."""
    data = load_toml(file)
    default_spritesheet_path = data.get(SPRITESHEET_KEY)

    loaded_sheets: dict[str, Optional[Spritesheet]] = {}

    def get_spritesheet(path: str) -> Optional[Spritesheet]:
        """Loads and caches the spritesheet at `path` in `loaded_sheets`, so a spritesheet referenced by multiple animations/frames is only decoded once. Returns None if `path` fails to load."""
        if path not in loaded_sheets:
            loaded_sheets[path] = load_file(path, SPRITESHEET_FILE) or None
        return loaded_sheets[path]

    animations = {}

    for name, anim_data in data.items():
        if not isinstance(anim_data, dict):
            continue  # e.g. the top-level "spritesheet" default, not an animation table

        loop = anim_data.get('loop', True)
        spritesheet_path = anim_data.get(SPRITESHEET_KEY, default_spritesheet_path)
        frames = []

        for frame_data in anim_data.get('frames', []):
            # Authored in milliseconds (e.g. `duration = 150`), matching every
            # other sprite-animation tool's convention - AnimationPlayer.update()
            # takes dt in seconds (it's fed straight from fb.delta()), so frame
            # durations are converted here once rather than at every update().
            duration = frame_data.get('duration', 100) / 1000.0
            image_path = frame_data.get('image')
            pos = frame_data.get('pos')

            if image_path is not None:
                texture = load_file(image_path)
                if not texture:
                    warning(f'Animation "{name}" could not load frame image "{image_path}".')
                    continue
            elif pos is not None:
                if not spritesheet_path:
                    warning(f'Animation "{name}" has a frame with "pos" set but no "spritesheet" is defined.')
                    continue

                sheet = get_spritesheet(spritesheet_path)
                if sheet is None:
                    warning(f'Animation "{name}" could not load spritesheet "{spritesheet_path}".')
                    continue

                texture = sheet.get_cell(pos)
                if texture is None:
                    warning(f'Animation "{name}" frame at pos {pos} has no "albedo" map in spritesheet "{spritesheet_path}".')
                    continue
            else:
                warning(f'Animation "{name}" has a frame with neither "pos" nor "image" set.')
                continue

            frames.append(AnimationFrame(texture, duration))

        if frames:
            animations[name] = Animation(name, frames, loop)
        else:
            warning(f'Animation "{name}" has no valid frames.')

    return AnimationSet(animations)
