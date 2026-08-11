from FreeBodyEngine import warning, get_flag, set_flag, DEVMODE, get_service

ASSET_WRITES_PERMITTED = "ASSET_WRITES_PERMITTED"
set_flag(ASSET_WRITES_PERMITTED, True)
 
from FreeBodyEngine.core.files.watcher import FileWatcher
from FreeBodyEngine.core.files.stream import FileStream
from FreeBodyEngine.core.files.resource import FileResource
from FreeBodyEngine.core.files.system import FileSystem
from FreeBodyEngine.core.files.asset_pack import AssetPackFileSystem, AssetPack
from FreeBodyEngine.core.files.dev import DevFileSystem
from FreeBodyEngine.core.dev import get_project
from FreeBodyEngine.utils import get_platform


def get_file(path: str) -> FileResource:
    return get_service('files').get_file(path)

loaders = {}

def load_file(path: str):
    file = get_service('files').get_file(path)

    dot_index = path.rfind('.')
    slash_index = max(path.rfind('/'), path.rfind('\\'))

    if dot_index == -1 or dot_index < slash_index:
        return ''  # no extension, or the dot is in a directory name

    extension = path[dot_index + 1:]

    return loaders[extension](file)

from FreeBodyEngine.core.files.loaders.toml import load_toml
from FreeBodyEngine.core.files.loaders.sprite import load_sprite
from FreeBodyEngine.core.files.loaders.image import load_image
from FreeBodyEngine.core.files.loaders.material import load_material

loaders = {
    "toml": load_toml,
    'fbspr': load_sprite,
    'fbmat': load_material,
    'png': load_image,
    'jpg': load_image,
    'jpeg': load_image
}

def join_paths(*paths):
    sanitised = [p.replace('\\', '/') for p in paths if p != '']

    if not sanitised:
        return ''

    is_absolute = sanitised[0].startswith('/')
    trailing_slash = sanitised[-1].endswith('/')

    combined = '/'.join(sanitised)
    raw_parts = combined.split('/')

    resolved = []
    for part in raw_parts:
        if part == '' or part == '.':
            continue
        elif part == '..':
            if resolved and resolved[-1] != '..':
                resolved.pop()
            elif not is_absolute:
                resolved.append('..')
        else:
            resolved.append(part)

    result = '/'.join(resolved)

    if is_absolute:
        result = '/' + result
    if trailing_slash and result != '' and not result.endswith('/'):
        result += '/'

    return result if result else ('/' if is_absolute else '.')

def get_file_system() -> FileSystem:
    platform = get_platform()
    
    if platform in ("win32", "darwin", "linux"):
        if not get_flag(DEVMODE, False):
            return AssetPackFileSystem()
        else:
            return DevFileSystem(join_paths(get_project().path, get_project().assets))

__all__ = ['FileSystem', 'FileStream', 'FileResource', "FileWatcher", 'AssetPackFileSystem', 'AssetPack', 'get_file_system', 'load_file']
