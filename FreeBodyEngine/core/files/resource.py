from FreeBodyEngine.core.files.stream import FileStream
from FreeBodyEngine import get_service
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from FreeBodyEngine.core.files.system import FileSystem


class FileResource:
    def __init__(self, id: int, data: bytes | FileStream, file_path: str):
        self.data = data
        self.id = id
        self.file_path = file_path

    def clear(self):
        self.data.clear()

    def read(self, size=-1, offset=0, bytes=False) -> str|bytes:
        if bytes:
            return self.data.read(size, offset)
        return self.data.read(size, offset).decode()

    def write(self, data: bytes|str, offset = -1):
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
