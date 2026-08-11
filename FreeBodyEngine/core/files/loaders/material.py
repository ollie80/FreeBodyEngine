from FreeBodyEngine.core.files import FileResource
from FreeBodyEngine.core.files.loaders.toml import load_toml
from FreeBodyEngine import get_service

def load_material(file: FileResource):    
    return get_service('graphics').create_material(load_toml(file), None)
