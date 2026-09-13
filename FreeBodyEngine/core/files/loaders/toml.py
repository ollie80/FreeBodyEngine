import tomllib
from FreeBodyEngine.core.files import FileResource

TOML_FILE = "TOML_FILE"

def load_toml(file: FileResource) -> dict:
    """Parses `file` as TOML into a plain dict - an empty file parses to
    `{}` rather than erroring."""
    data = file.read()
    
    if len(data) > 0:
        return tomllib.loads(data)
    return dict()
