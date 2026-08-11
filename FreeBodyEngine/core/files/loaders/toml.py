import tomllib
from FreeBodyEngine.core.files import FileResource

def load_toml(file: FileResource) -> dict:
    return tomllib.loads(file.read())