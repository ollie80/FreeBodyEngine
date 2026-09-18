from FreeBodyEngine import warning, get_flag, set_flag, DEVMODE, get_service

ASSET_WRITES_PERMITTED = "ASSET_WRITES_PERMITTED"
set_flag(ASSET_WRITES_PERMITTED, True)
from typing import TYPE_CHECKING

if TYPE_CHECKING: 
    from FreeBodyEngine.core.files.resource import FileResource
    
def get_file(path: str) -> 'FileResource':
    """Shorthand for `get_service('files').get_file(path)`."""
    return get_service('files').get_file(path)

def path_exists(path: str) -> bool:
    """Returns whether `path` (a virtual asset path - see FileSystem.
    get_file()) resolves to a real file under the active FileSystem.
    `get_file()` itself already returns None rather than raising for a
    path that doesn't resolve, so this is just that check spelled out -
    added because engine_assets/default_main_file.py (the template every
    new project starts from via `fb init`) called a same-purpose
    `path_exsists` (note the typo) that had never actually existed here
    at all, on any platform: a fresh project with no `actions.toml` (the
    common case - it's optional input-action config) crashed with
    AttributeError the instant register_default_services() ran, before
    ever reaching main.run()."""
    return get_service('files').get_file(path) is not None

loaders = {}

MODEL_FILE = "MODEL_FILE"
TOML_FILE = "TOML_FILE"
SPRITE_FILE = "LOAD_SPRITE"
TEXTURE_FILE = "LOAD_TEXTURE"
MATERIAL_FILE = "LOAD_MATERIAL"
TEXTURE_STACK_FILE = "TEXTURE_STACK_FILE"
SOUND_FILE = "SOUND_FILE"
FONT_FILE = "FONT_FILE"
ANIMATION_FILE = "ANIMATION_FILE"
SPRITESHEET_FILE = "SPRITESHEET_FILE"

from FreeBodyEngine.core.files.loader import load_file

from FreeBodyEngine.core.files.watcher import FileWatcher
from FreeBodyEngine.core.files.stream import FileStream
from FreeBodyEngine.core.files.resource import FileResource
from FreeBodyEngine.core.files.system import FileSystem
from FreeBodyEngine.core.files.asset_pack import AssetPackFileSystem, AssetPack
from FreeBodyEngine.core.files.dev import DevFileSystem


__all__ = [
    'FileSystem',
    'FileStream',
    'FileResource',
    "FileWatcher",
    'AssetPackFileSystem',
    'AssetPack',
    'get_file_system',
    'load_file',
    ]

from FreeBodyEngine.core.files.loaders.toml import load_toml
from FreeBodyEngine.core.files.loaders.sprite import load_sprite
from FreeBodyEngine.core.files.loaders.texture import load_texture
from FreeBodyEngine.core.files.loaders.material import load_material
from FreeBodyEngine.core.files.loaders.texture_stack import load_texture_stack
from FreeBodyEngine.core.files.loaders.model import load_model
from FreeBodyEngine.core.files.loaders.sound import load_sound
from FreeBodyEngine.core.files.loaders.font import load_font
from FreeBodyEngine.core.files.loaders.animation import load_animation
from FreeBodyEngine.core.files.loaders.spritesheet import load_spritesheet
# file_type: (loader, supported_extensions, supports_multiple_files)
#
# Loader order matters when multiple loaders support the same extension.
# If the first matching loader does not support multiple files, the next
# matching loader that does will be used.
loaders = {
    TOML_FILE: (load_toml, ('.toml',), False),
    SPRITE_FILE: (load_sprite, ('.fbspr',), False),
    MATERIAL_FILE: (load_material, ('.fbmat',), False),
    MODEL_FILE: (load_model, ('.glb', '.gltf'), False),
    TEXTURE_FILE: (load_texture, ('.png', '.jpg', '.jpeg', '.webp'), False),
    TEXTURE_STACK_FILE: (
        load_texture_stack,
        ('.png', '.jpg', '.jpeg', '.webp'),
        True,
    ),
    SOUND_FILE: (
        load_sound, ('.mp3',), False
    ),
    FONT_FILE: (load_font, ('.fbfont',), False),
    ANIMATION_FILE: (load_animation, ('.fbanim',), False),
    SPRITESHEET_FILE: (load_spritesheet, ('.fbsheet',), False),
}



def join_paths(*paths):
    """Joins `paths` with "/" and normalizes the result the way `os.path`
    would (resolving `.` and `..` segments, collapsing repeated slashes),
    but always on "/" regardless of host OS - these are virtual asset
    paths, not real filesystem paths, so using `os.path` itself would
    mangle them on Windows. A leading `..` past the start of a relative
    join is kept (there's nothing to resolve it against yet); the same
    past the start of an absolute path is dropped instead, since going
    above `/` isn't meaningful. Preserves a trailing slash from the last
    non-empty argument. Empty arguments are ignored; an all-empty input
    returns `''`."""
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

from FreeBodyEngine.core.dev import get_project
from FreeBodyEngine.utils import get_platform
def get_file_system() -> FileSystem:
    """Constructs the right FileSystem for how the engine is currently
    running: an AssetPackFileSystem (reading bundled `.pak`s) unless the
    DEVMODE flag is set, in which case a DevFileSystem rooted at the
    current project's asset directory. Returns None on an unsupported
    platform (anything other than win32/darwin/linux/web/android).

    DevFileSystem itself has no platform-specific code at all (see
    core/files/dev.py's open_file() - a plain builtin open(), which reads
    from Pyodide's own virtual filesystem transparently once a web dev
    build's bootstrap has unpacked the project's files into it - see
    build/builder.py's build_for_dev_web()) - "web" only needed adding to
    this tuple, not a whole new branch, for `fb run --web` dev builds to
    get a real FileSystem instead of silently None. A release build's
    AssetPackFileSystem path isn't reachable for "web" yet regardless
    (see Builder.build_for_web() - web release builds aren't implemented
    at all), so that half of this function is unchanged.

    "android" needed adding for the same reason "web" did: Android's own
    per-app private storage (where build_for_dev_android() copies the
    project's assets - see its own docstring) is a completely ordinary
    POSIX filesystem underneath, so DevFileSystem's plain open() calls
    need nothing platform-specific here either - just a dispatch entry
    that wasn't there yet, not a new FileSystem implementation."""
    platform = get_platform()

    if platform in ("win32", "darwin", "linux", "web", "android"):
        if not get_flag(DEVMODE, False):
            return AssetPackFileSystem()
        else:
            return DevFileSystem(
                join_paths(get_project().path, get_project().assets))
