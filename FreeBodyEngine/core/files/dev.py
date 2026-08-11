from FreeBodyEngine.core.files import FileSystem
from FreeBodyEngine.core.files import FileStream
from FreeBodyEngine.core.files import FileResource
from FreeBodyEngine.core.files import FileWatcher
from FreeBodyEngine.core.files import ASSET_WRITES_PERMITTED
from FreeBodyEngine import get_flag, NAME, DEFAULT_NAME, warning, error
from FreeBodyEngine.utils import get_platform
from pathlib import Path
import os
from os.path import exists


def get_user_file_path():
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
    return open(path, mode)

class DevFileSystem(FileSystem):
    def __init__(self, asset_directory: str):
        super().__init__()

        self.file_watcher = FileWatcher(self.sanitise_path(asset_directory))
        self.user_files_path = self.sanitise_path(get_user_file_path())
        self.hot_reloading = True
        self.asset_directory = self.ensure_trailing_slash(self.sanitise_path(asset_directory))

    def get_system_path(self, path: str) -> str:
        if path.startswith('engine/'):
            pass
        else:
            return path

    def ensure_path(self, path):
        return exists(path)

    def get_file(self, path):
        system_path = ""
        if path.startswith('user://'):
            system_path = self.sanitise_path(path).removeprefix("user://")
            system_path = self.user_files_path + system_path
            writes_permitted = True

        else:
            system_path = self.asset_directory + self.sanitise_path(path)
            writes_permitted = get_flag(ASSET_WRITES_PERMITTED, False)

            if self.ensure_path(system_path) and not writes_permitted:
                warning(f'File does not exsist at {path}.')
                return None

        stream = DevFileStream(system_path, writes_permitted)

        return self._add(FileResource(self.generate_file_id(), stream, path))

class DevFileStream(FileStream):
    def __init__(self, path: str, writes_allowed: bool):
        if not exists(path):
            if writes_allowed:
                dirname = os.path.dirname(path)
                if dirname:
                    os.makedirs(dirname, exist_ok=True)
                open_file(path, 'w').close()
            else:
                error(f'No file at path {path}')

        mode = 'r+b' if writes_allowed else 'rb'
        self._stream = open_file(path, mode)

        self.writes_allowed = writes_allowed

    def __len__(self):
        pos = self._stream.tell()
        self._stream.seek(0, 2)
        size = self._stream.tell()
        self._stream.seek(pos)
        return size

    def write(self, data: str|bytes, offset=-1):
        if isinstance(data, str):
            data = data.encode()

        if not self.writes_allowed:
            return

        final_offset = len(self) if offset == -1 else offset

        self._stream.seek(final_offset)
        self._stream.write(data)
        self._stream.flush()
        self._stream.seek(0)

    def read(self, size=-1, offset=0) -> bytes:
        self._stream.seek(offset)
        val = self._stream.read(size)
        self._stream.seek(0)
        
        return val

    def remove(self, start=0, end=-1):
        if not self.writes_allowed:
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
        if self.writes_allowed:
            self._stream.truncate(0)
            self._stream.flush()
            self._stream.seek(0)

    def close(self):
        self._stream.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __getitem__(self, index):
        return self.read(1, index)

    def __setitem__(self, index, value):
        self.write(value, index)