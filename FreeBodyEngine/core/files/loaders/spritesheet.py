from FreeBodyEngine.core.files import FileResource, load_file
from FreeBodyEngine.core.files.loaders.toml import load_toml
from FreeBodyEngine.graphics.spritesheet import Spritesheet
from FreeBodyEngine import warning

SIZE_KEY = 'size'


def load_spritesheet(file: FileResource) -> Spritesheet:
    """Loads a `.fbsheet` file: a TOML document mapping texture map names
    (e.g. `albedo`, `normal`) to whole-image paths, plus a `size = [cols, rows]`
    grid shared by every map."""
    data = load_toml(file)

    size = data.get(SIZE_KEY)
    if size is None or len(size) != 2:
        warning(f'Spritesheet "{file.file_path}" is missing a valid "size = [cols, rows]".')
        size = (1, 1)

    maps = {}
    for map_name, image_path in data.items():
        if map_name == SIZE_KEY:
            continue

        texture = load_file(image_path)
        if not texture:
            warning(f'Spritesheet "{file.file_path}" could not load "{map_name}" map "{image_path}".')
            continue

        maps[map_name] = texture

    return Spritesheet(maps, tuple(size))
