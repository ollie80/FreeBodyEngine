from FreeBodyEngine.core.files import FileResource
from FreeBodyEngine import get_service

def load_image(file: FileResource):
    texture = get_service('renderer').texture_manager._create_standalone_texture(file.read(bytes=True))
    return get_service('renderer').load_image(texture)

