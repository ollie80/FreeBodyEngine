from FreeBodyEngine.core.service import Service
from FreeBodyEngine.utils import abstractmethod
from FreeBodyEngine import register_service_update, register_event
from FreeBodyEngine.core.update import UpdatePhase

FILE_CHANGE = "ENGINE_file_change"

class FileWatcher(Service):
    def __init__(self, directory: str):
        self.directory = directory
        register_event(FILE_CHANGE)
    
    def on_initialize(self):
        register_service_update(UpdatePhase.EARLY)

    @abstractmethod
    def update(self):
        pass

