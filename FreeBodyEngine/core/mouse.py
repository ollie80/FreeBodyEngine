from FreeBodyEngine.math import Vector
from FreeBodyEngine.utils import abstractmethod
from FreeBodyEngine.core.service import Service
from FreeBodyEngine import register_service_update, unregister_service_update

class Mouse(Service):
    def __init__(self):
        super().__init__('mouse')
        self.dependencies.append('window')

        self._dragging = False
        self.drag_start = Vector()

        self.position = Vector()
        self.world_position = Vector()
        
        self._cursor_hidden = False
        self._interal_cursor_hidden = False
        self.double_click_threshold = 0.4 
    
    def on_initialize(self):
        register_service_update('early', self.update)

    def on_destroy(self):
        unregister_service_update('early', self.update)

    @abstractmethod
    def lock_position(self):
        """Locks the cursor position on screen, stoping it from moving while still getting movement information."""
        pass

    @abstractmethod
    def unlock_position(self):
        pass

    @abstractmethod
    def get_pressed(self, button: int) -> bool:
        pass

    @abstractmethod
    def get_down(self, button: int) -> bool:
        pass
    
    @abstractmethod
    def get_released(self, button: int) -> bool:
        pass

    @abstractmethod
    def get_double_click(self, button: int) -> bool:
        pass

    @abstractmethod
    def get_dragging(self, button: int) -> bool:
        pass

    @abstractmethod
    def get_drag_start(self, button: int, world: bool = False) -> Vector:
        pass

    def get_drag_offset(self, button: int, world: bool = False) -> Vector:
        if world:
            return self.get_drag_start(button, world) + self.world_position
        else:
            return self.get_drag_start(button, world) + self.position


    @abstractmethod
    def hide_cursor(self):
        pass

    @abstractmethod
    def set_cursor(self):
        pass

    @abstractmethod
    def update(self):
        pass
    