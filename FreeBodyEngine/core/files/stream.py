


class FileStream:
    """Base class for a FileSystem backend's raw byte-level IO (DevFileStream
    for a real file on disk, AssetPackStream for a read-only view into a
    bundled `.pak`) - every method here is a no-op stub, meant to be
    overridden; the default (write-nothing, read-nothing) FileStream is
    itself used as a placeholder for a resource with no real backing data
    (see AssetPackFileSystem.get_file()'s atlas-region case)."""

    def write(self, data: bytes, offset = 0):
        """
        Writes bytes to the IO stream.
        """
        pass


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
