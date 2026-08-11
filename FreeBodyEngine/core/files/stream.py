from FreeBodyEngine.utils import abstractmethod


class FileStream:
    @abstractmethod
    def write(self, data: bytes, offset = 0):
        """
        Writes bytes to the IO stream.
        """
        pass

    @abstractmethod
    def read(self, size=-1, offset = 0) -> bytes:
        """Reads bytes from the IO stream."""
        pass

    def remove(self, start: int, end: int):
        """
        Removes bytes within a range
        """
        pass

    def clear(self):
        """
        Clears all bytes from a file.
        """
        pass

    def __getitem__(self, index):
        return self.read(1, index)

    def __setitem__(self, index, value):
        self.write(value, index)
