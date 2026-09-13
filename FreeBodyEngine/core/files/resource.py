from FreeBodyEngine.core.files.stream import FileStream
from FreeBodyEngine import get_service
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from FreeBodyEngine.core.files.system import FileSystem


class FileResource:
    """A handle to one loaded file, returned by FileSystem.get_file() - the
    common, backend-agnostic interface loaders/callers use regardless of
    whether `data` is a DevFileStream, an AssetPackStream, or any other
    FileStream implementation."""
    def __init__(self, id: int, data: FileStream, file_path: str):
        self.data = data
        self.id = id
        self.file_path = file_path

    def clear(self):
        """Clears the underlying file's contents (a no-op if the backing
        FileStream doesn't allow writes)."""
        self.data.clear()

    def read(self, size=-1, offset=0, bytes=False) -> str|bytes:
        """Reads `size` bytes starting at `offset` (the whole file by
        default). Decodes the result to `str` unless `bytes=True` is
        passed - an empty read decodes to `""` rather than raising, since
        an empty byte string is valid UTF-8 but callers generally want a
        plain empty string back, not to special-case it themselves."""
        if bytes:
            return self.data.read(size, offset)


        file_bytes = self.data.read(size, offset)

        return file_bytes.decode() if len(file_bytes) > 0 else ""

    def write(self, data: bytes|str, offset = -1):
        """Writes `data` at `offset` (appending at the current end of file
        when `offset` is -1, the default). A no-op if the backing
        FileStream doesn't allow writes."""
        self.data.write(data, offset)

    def __str__(self):
        if isinstance(self.data, FileStream):
            return str(self.data.read())
        else:
            return str(self.data)
        
    def __bytes__(self):
        if isinstance(self.data, FileStream):
            return self.data.read()
        else:
            return self.data

    def __getitem__(self, index):
        return self.data[index]  

    def __setitem__(self, index, value):
        self.data[index] = value

    def __iter__(self):
        for byte in self.data:
            yield byte
