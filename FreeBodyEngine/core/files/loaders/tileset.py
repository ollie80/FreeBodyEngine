from FreeBodyEngine.core.files import FileResource
from FreeBodyEngine.core.files.loaders.toml import load_toml

TILESET_FILE = "TILESET_FILE"


def load_tileset(file: FileResource) -> dict:
    """Loads a `.fbtiles` file: the TOML definition of one auto-tiled
    tileset - the `.fbsheet` its tiles come from, a `default` cell, and its
    `[[rule]]` entries.

    Returned as the raw parsed table rather than a compiled object, because
    what the rules mean is the tilemap's business, not the file system's -
    see core/tilemap/rules.py, which compiles them, and AutoSpritesheet,
    which evaluates them.
    """
    return load_toml(file)
