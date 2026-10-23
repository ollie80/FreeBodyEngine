from FreeBodyEngine.core.files import FileStream
from FreeBodyEngine.core.files import FileResource
from FreeBodyEngine.core.files import FileWatcher
from FreeBodyEngine.core.files import FileSystem
from FreeBodyEngine.core.files import ASSET_WRITES_PERMITTED
from FreeBodyEngine.core.files.watcher.generic import FILE_CHANGE
from FreeBodyEngine.core.files.asset_cache import KIND_DIRS
import FreeBodyEngine.core.files.hot_reload as hot_reload
from FreeBodyEngine import get_flag, NAME, DEFAULT_NAME, warning, error
from FreeBodyEngine import register_service_update, unregister_service_update, register_event_callback, unregister_event_callback
from FreeBodyEngine.core.update import UpdatePhase
from FreeBodyEngine.utils import get_platform
from pathlib import Path
import os
from os.path import exists
from importlib.resources import files, as_file


def get_user_file_path():
    """Returns the per-platform base directory for `user://` files (saves,
    logs, and other runtime-writable data) - unset for any platform other
    than linux/win32/darwin."""
    platform = get_platform()
    name = get_flag(NAME, DEFAULT_NAME)
    if platform == 'linux':
        return f'~/.local/share/{name}/' 
    if platform == 'win32':
        return str(Path.home()) + f"/AppData/Local/{name}/"
    if platform == 'darwin':
        return f"~/Library/Application Support/{name}/"
    return ""

def open_file(path, mode):
    """Thin wrapper around the builtin `open()` - exists so DevFileStream
    can be tested/mocked by patching this one call site instead of the
    builtin itself."""
    return open(path, mode)

class DevFileSystem(FileSystem):
    """The dev-mode FileSystem: reads/writes loose files straight off disk
    under `asset_directory` (rather than a bundled release `.pak`, see
    AssetPackFileSystem) and drives a FileWatcher so edits to those files
    trigger hot reload."""
    def __init__(self, asset_directory: str, cache_directory: str | None = None):
        """Starts a FileWatcher polling `asset_directory` immediately -
        actually wiring its update() into the update loop happens later,
        in on_initialize(). `cache_directory` is the project's asset cache
        (see core/files/asset_cache.py) - paths under its folders
        (`_ENGINE_fonts/`, `_ENGINE_models/`) are read from there."""
        super().__init__()
        self.cache_directory = self.ensure_trailing_slash(self.sanitise_path(cache_directory)) if cache_directory else None

        self.user_files_path = self.sanitise_path(get_user_file_path())
        self.hot_reloading = True
        self.asset_directory = self.ensure_trailing_slash(self.sanitise_path(asset_directory))
        self.file_watcher = FileWatcher(os.path.expanduser(self.asset_directory))

    def on_initialize(self):
        """Wires the FileWatcher's polling into the update loop and starts
        listening for the FILE_CHANGE events it emits, for as long as this
        FileSystem is alive (i.e. the whole dev-mode run)."""
        # FileWatcher isn't itself a registered Service (see its own
        # docstring) - this is what actually drives its polling and turns
        # a detected change into a reload, for the lifetime of this
        # FileSystem (i.e. the whole dev-mode run).
        register_service_update(UpdatePhase.EARLY, self.file_watcher.update)
        register_event_callback(FILE_CHANGE, self._on_file_change)

    def on_destroy(self):
        """Undoes on_initialize()'s registrations."""
        unregister_service_update(UpdatePhase.EARLY, self.file_watcher.update)
        unregister_event_callback(FILE_CHANGE, self._on_file_change)

    def _on_file_change(self, relative_path: str):
        ext = relative_path.rsplit(".", 1)[-1].lower() if "." in relative_path else ""
        if ext in ("fbvert", "fbfrag"):
            hot_reload.reload_shader_source(relative_path)
        else:
            hot_reload.reload_asset(relative_path)

    def get_system_path(self, path: str) -> str:
        """Intended to resolve a virtual path to a real host filesystem
        path, mirroring get_file()'s path-prefix handling. Not currently
        called anywhere in the engine; note the `engine/`-prefixed branch
        falls through without a return (implicitly returning None) rather
        than resolving anything."""
        if path.startswith('engine/'):
            pass
        else:
            return path

    def ensure_path(self, path):
        """Returns whether `path` (a real, already-resolved host filesystem
        path) exists on disk."""
        return exists(path)

    def _resolve(self, path) -> tuple[str, bool]:
        """`path` as a real path on disk, and whether it may be written -
        see get_file()."""
        if path.startswith('user://'):
            system_path = self.user_files_path + self.sanitise_path(path.removeprefix("user://"))
            writes_permitted = True
        elif path.startswith('engine://'):
            system_path = str(files('FreeBodyEngine.engine_assets').joinpath(path.removeprefix("engine://")))
            writes_permitted = False
        elif self.cache_directory is not None and path.split("/", 1)[0] in KIND_DIRS.values():
            # Baked fonts/models - see core/files/asset_cache.py. Never
            # writable through here: only AssetCache.ensure() writes them.
            system_path = self.cache_directory + self.sanitise_path(path)
            writes_permitted = False
        else:
            system_path = self.asset_directory + self.sanitise_path(path)
            writes_permitted = get_flag(ASSET_WRITES_PERMITTED, False)
        return os.path.expanduser(system_path), writes_permitted

    def path_exists(self, path) -> bool:
        """Whether `path` is a file on disk - see core/files' path_exists()."""
        return exists(self._resolve(path)[0])

    def get_file(self, path):
        """Resolves `path` to a real file on disk and returns a FileResource
        wrapping it - `user://` paths resolve under the per-platform user
        data directory (always writable), `engine://` paths resolve into
        the installed `FreeBodyEngine.engine_assets` package (never
        writable), and anything else resolves under `asset_directory`
        (writable only when ASSET_WRITES_PERMITTED is set, true by default
        in dev mode).

        A path that doesn't exist and can't be written warns and returns
        None. One that can be written gets a resource whose file is only
        created when something writes to it - see DevFileStream. It used to
        be created right here, so any mistyped asset path (or a probe like
        path_exists()) left an empty file in the project's assets. The
        existence check was also inverted: it refused files that *did*
        exist."""
        system_path, writes_permitted = self._resolve(path)

        if not writes_permitted and not exists(system_path):
            warning(f'File does not exist at {path}.')
            return None

        stream = DevFileStream(system_path, writes_permitted)
        return self._add(FileResource(self.generate_file_id(), stream, path))

class DevFileStream(FileStream):
    """A FileStream backed by a real file on disk, opened in binary mode for
    the lifetime of the resource (`r+b` when writes are allowed, else read-
    only `rb`) rather than reopened per read/write.

    A writable path that doesn't exist yet stays that way until the first
    write: until then it reads as empty, and nothing is created on disk."""
    def __init__(self, path: str, writes_allowed: bool):
        """Opens `path` if it exists (errors if it doesn't and writes aren't
        allowed - a missing writable file is created by the first write)."""
        self.path = path
        self.writes_allowed = writes_allowed
        self._stream = None
        if exists(path):
            self._stream = open_file(path, 'r+b' if writes_allowed else 'rb')
        elif not writes_allowed:
            error(f'No file at path {path}')

    def _opened(self, create: bool = False):
        """The open file, opening it if it has appeared since (or creating
        it, with `create`); None if there is still no file."""
        if self._stream is None:
            if exists(self.path):
                self._stream = open_file(self.path, 'r+b' if self.writes_allowed else 'rb')
            elif create:
                dirname = os.path.dirname(self.path)
                if dirname:
                    os.makedirs(dirname, exist_ok=True)
                self._stream = open_file(self.path, 'w+b')
        return self._stream

    def __len__(self):
        if self._opened() is None:
            return 0
        pos = self._stream.tell()
        self._stream.seek(0, 2)
        size = self._stream.tell()
        self._stream.seek(pos)
        return size

    def write(self, data: str|bytes, offset=-1):
        """Writes `data` at `offset` (appending at the current end of file
        when `offset` is -1, the default). A no-op if writes aren't
        allowed. Leaves the stream position reset to 0 afterwards."""
        if isinstance(data, str):
            data = data.encode()

        if not self.writes_allowed:
            return

        final_offset = len(self) if offset == -1 else offset

        self._opened(create=True)
        self._stream.seek(final_offset)
        self._stream.write(data)
        self._stream.flush()
        self._stream.seek(0)

    def read(self, size=-1, offset=0) -> bytes:
        """Reads `size` bytes starting at `offset` (the whole file when
        `size` is -1, the default). Leaves the stream position reset to 0
        afterwards."""
        if self._opened() is None:
            return b""
        self._stream.seek(offset)
        val = self._stream.read(size)
        self._stream.seek(0)
         
        return val

    def remove(self, start=0, end=-1):
        """Deletes the byte range [start, end) from the file (the rest of
        the file when `end` is -1, the default), shifting every following
        byte down to close the gap and truncating the file to its new,
        shorter length. Copies in 1MB chunks rather than loading the whole
        tail into memory at once, since asset files this shifts can be
        large. A no-op if writes aren't allowed, or if the range is empty."""
        if not self.writes_allowed or self._opened() is None:
            return

        self._stream.seek(0, 2)
        file_size = self._stream.tell()

        if end == -1 or end > file_size:
            end = file_size

        if start >= end:
            return

        chunk_size = 1024 * 1024
        read_pos = end
        write_pos = start

        while read_pos < file_size:
            self._stream.seek(read_pos)
            chunk = self._stream.read(min(chunk_size, file_size - read_pos))
            if not chunk:
                break

            self._stream.seek(write_pos)
            self._stream.write(chunk)

            read_pos += len(chunk)
            write_pos += len(chunk)

        self._stream.truncate(write_pos)
        self._stream.flush()
        self._stream.seek(0)

    def clear(self):
        """Truncates the file to empty. A no-op if writes aren't allowed."""
        if self.writes_allowed and self._opened() is not None:
            self._stream.truncate(0)
            self._stream.flush()
            self._stream.seek(0)

    def close(self):
        """Closes the underlying file handle, if one was ever opened."""
        if self._stream is not None:
            self._stream.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __getitem__(self, index):
        return self.read(1, index)

    def __setitem__(self, index, value):
        self.write(value, index)
