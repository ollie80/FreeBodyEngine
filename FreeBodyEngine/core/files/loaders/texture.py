from FreeBodyEngine.core.files import FileResource
from FreeBodyEngine import get_service, error
import FreeBodyEngine.core.files.hot_reload as hot_reload

TEXTURE_FILE = "TEXTURE_FILE"

def load_texture(file: FileResource):
    """Loads an image file into a Texture. If it was packed into the shared
    atlas at build time (release builds only, see build/atlas_gen.py),
    returns a view into that atlas instead of decoding `file` itself.
    Otherwise decodes `file` as a standalone texture; in dev mode, returns
    the already-registered live Texture for this exact path if one exists
    rather than creating a new one, and registers a freshly-created one so
    a later edit can be hot-reloaded in place (see
    core/files/hot_reload.py) - atlas-backed textures are never registered
    this way, since dev mode never atlas-packs, so there's nothing there to
    hot-reload."""
    if file is None:
        error("Cannot load texture: the requested file was not found.")
        return None

    if hot_reload.is_enabled():
        cached = hot_reload.get_cached(file.file_path, hot_reload.TEXTURE)
        if cached is not None:
            return cached

    renderer = get_service('renderer')
    files = get_service('files')

    # Release builds pack every source image into one shared atlas texture
    # at build time (build/atlas_gen.py) - the original file no longer
    # exists standalone in any pak, only as a named region of that atlas.
    # DevFileSystem (and anything else that doesn't atlas-pack) simply has
    # no get_atlas_uv method, so this is a no-op there.
    get_atlas_uv = getattr(files, "get_atlas_uv", None)
    atlas_uv = get_atlas_uv(file.file_path) if get_atlas_uv else None

    if atlas_uv is not None:
        atlas_file = files.get_file(files.ATLAS_IMAGE_KEY)
        return renderer.texture_manager._create_atlas_texture(
            atlas_file.read(bytes=True), files.ATLAS_IMAGE_KEY, {file.file_path: atlas_uv}, file.file_path
        )

    texture = renderer.texture_manager._create_standalone_texture(file.read(bytes=True))

    # Only the standalone path is cached/hot-reloadable - an atlas-backed
    # Texture (above) is a view into a release build's shared atlas image,
    # which build_for_release() produces once and dev mode never does at
    # all, so there's nothing there for a dev-mode file edit to reload.
    if hot_reload.is_enabled():
        hot_reload.register(file.file_path, hot_reload.TEXTURE, texture)

    return texture
