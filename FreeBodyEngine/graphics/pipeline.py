from FreeBodyEngine.core.service import Service
from FreeBodyEngine import get_service, register_service_update, unregister_service_update
from FreeBodyEngine.utils import abstractmethod
from FreeBodyEngine.graphics.renderer import Renderer
from FreeBodyEngine.graphics.material import Material

class GraphicsPipeline(Service):
    def __init__(self):
        super().__init__('graphics')
        self.dependencies.append('renderer')

    def on_initialize(self):
        register_service_update('draw', self.draw)
        self.renderer = get_service('renderer')
        self.renderer: Renderer

    def on_destroy(self):
        unregister_service_update('draw', self.draw)

    @abstractmethod
    def create_material(self, data) -> Material:
        pass

    @abstractmethod
    def draw(self):
        pass