from FreeBodyEngine.utils import abstractmethod
from FreeBodyEngine.core.service import Service
from FreeBodyEngine.core.files.resource import FileResource
from FreeBodyEngine.core.files.stream import FileStream


class FileSystem(Service):
    """Base class for the engine's pluggable file backends (DevFileSystem
    for loose files on disk, AssetPackFileSystem for bundled release
    `.pak`s) - registered as the "files" service, so callers go through
    `get_service('files')` rather than depending on a concrete subclass."""
    def __init__(self):
        """Registers this instance as the "files" service and sets up the
        empty resource registry subclasses' get_file() implementations add
        to via _add()."""
        super().__init__('files')
        self.current_file_id = 0
        self.resources: dict[int, FileStream] = {}

    def generate_file_id(self):
        """Returns a fresh, unique id for a new FileResource - ids are
        assigned sequentially and never reused within this FileSystem's
        lifetime."""
        # maybe change to use UUIDs
        return_id = self.current_file_id
        self.current_file_id += 1

        return return_id

    @abstractmethod
    def ensure_path(self, path: str):
        """Returns whether `path` exists in this backend."""
        pass

    def ensure_trailing_slash(self, path: str) -> str:
        """
        Ensures a directory path ends with a forward slash.
        Assumes the path has already been sanitised
        """
        if not path.endswith('/'):
            path += '/'
        return path

    def sanitise_path(self, path: str):
        """
        Converts file paths to use the forward slash standard.
        """
        return path.replace('\\', '/')

    def _get(self, id: int):
        return self.resources[id]
        
    def _add(self, resource: FileResource):
        self.resources[resource.id] = resource
        return resource

    @abstractmethod
    def get_file(self, path: str) -> FileResource:
        """Resolves `path` (a virtual asset path, e.g. possibly prefixed
        with `user://` or `engine://`) to a FileResource, or None if it
        can't be resolved."""
        pass