from FreeBodyEngine.core.files import FileResource, load_file
from FreeBodyEngine.core.files.loaders.toml import load_toml
from FreeBodyEngine import get_service, error
from FreeBodyEngine.graphics.sprite import Sprite


def load_sprite(file: FileResource):
    """
    Loads an .fbspr file.
    """
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

    return Sprite(image, mat, get_service('renderer'), visible, z)
