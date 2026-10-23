from FreeBodyEngine.core.files import FileResource, load_file
from FreeBodyEngine.core.files.loaders.toml import load_toml
from FreeBodyEngine import get_service, error
from FreeBodyEngine.graphics.sprite import Sprite
import FreeBodyEngine.core.files.hot_reload as hot_reload

SPRITE_FILE = "SPRITE_FILE"

def load_sprite(file: FileResource):
    """
    Loads an .fbspr file.
    """
    if hot_reload.is_enabled():
        cached = hot_reload.get_cached(file.file_path, hot_reload.SPRITE)
        if cached is not None:
            # A copy, not the cached object itself. `visible` and `z` are
            # per-object state, so handing every caller one Sprite meant a row
            # of candles all loading flame.fbspr could not be shown or hidden
            # independently - see Sprite.instance for what that looked like.
            return hot_reload.track_instance(file.file_path, cached.instance())

    data = load_toml(file)

    # `image` for a still sprite, `animations` (an .fbanim) for an animated
    # one - or both, the image then being what shows before anything plays.
    # `material` is optional: the pipeline's default sprite material is used
    # without one (see graphics/sprite.py's default_sprite_material()).
    img_path = data.get('image')
    anim_path = data.get('animations')
    if not img_path and not anim_path:
        error(f'Sprite "{file.file_path}" names neither an image nor animations.')
        return None

    animations = load_file(anim_path) if anim_path else None
    mat_path = data.get('material')
    mat = load_file(mat_path) if mat_path else None
    visible = data.get('visible', True)
    z = data.get('z', 0)

    # Optional surface relief, so a static sprite can be lit the same way a
    # tile or an animated sprite is.
    normal_path = data.get('normal')
    normal = load_file(normal_path) if normal_path else None

    if img_path:
        sprite = Sprite(load_file(img_path), mat, visible, z, normal, animations)
    else:
        sprite = Sprite.from_animations(animations, mat, visible=visible, z=z)

    if hot_reload.is_enabled():
        # The registered Sprite is a template to reload into, never drawn;
        # callers get copies of it.
        hot_reload.register(file.file_path, hot_reload.SPRITE, sprite)
        return hot_reload.track_instance(file.file_path, sprite.instance())

    return sprite
