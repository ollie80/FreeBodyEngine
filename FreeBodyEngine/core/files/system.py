from FreeBodyEngine.utils import abstractmethod
from FreeBodyEngine.core.service import Service
from FreeBodyEngine.core.files.resource import FileResource
from FreeBodyEngine.core.files.stream import FileStream


class FileSystem(Service):
    def __init__(self):
        super().__init__('files')
        self.current_file_id = 0
        self.resources: dict[int, FileStream] = {} 

    def generate_file_id(self):
        # maybe change to use UUIDs
        return_id = self.current_file_id
        self.current_file_id += 1

        return return_id

    @abstractmethod
    def ensure_path(self, path: str):
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
        pass