from FreeBodyEngine import get_service
from FreeBodyEngine.core.files.resource import FileResource
from io import BytesIO

def load_sound(file: FileResource):
    """Loads an `.mp3` file into a playable sound via the audio service."""
    data = file.read(bytes=True)
    return get_service('audio').create_sound(BytesIO(data))


