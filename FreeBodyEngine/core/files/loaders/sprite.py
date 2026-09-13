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
            return cached

    data = load_toml(file)
    type = data.get('type', "static")

    if type == "static":
        img_path = data.get('image')
        if not img_path:
            pass

        image = load_file(img_path)

    mat_path = data.get('material')

    if not mat_path:
        pass

    mat = load_file(mat_path)
    visible = data.get('visible', True)
    z = data.get('z', 0)

    sprite = Sprite(image, mat, get_service('renderer'), visible, z)

    if hot_reload.is_enabled():
        hot_reload.register(file.file_path, hot_reload.SPRITE, sprite)

    return sprite
