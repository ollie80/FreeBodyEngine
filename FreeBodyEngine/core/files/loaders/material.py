from FreeBodyEngine.core.files import FileResource
from FreeBodyEngine.core.files.loaders.toml import load_toml
from FreeBodyEngine import get_service
import FreeBodyEngine.core.files.hot_reload as hot_reload

MATERIAL_FILE = "MATERIAL_FILE"

def load_material(file: FileResource):
    """Loads a `.fbmat` TOML file into a real Material via the graphics
    service. In dev mode, returns the already-registered live Material for
    this exact path instead of building a new one if one exists - see
    core/files/hot_reload.py - and registers a freshly-built one so a later
    edit to this file can be hot-reloaded in place."""
    if hot_reload.is_enabled():
        cached = hot_reload.get_cached(file.file_path, hot_reload.MATERIAL)
        if cached is not None:
            return cached

    material = get_service('graphics').create_material(load_toml(file), None)

    if hot_reload.is_enabled():
        hot_reload.register(file.file_path, hot_reload.MATERIAL, material)

    return material
