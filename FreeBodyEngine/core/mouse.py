from FreeBodyEngine.math import Vector
from FreeBodyEngine.utils import abstractmethod


class Mouse:
    def __init__(self):
        self._dragging = False
        self.drag_start = Vector()

        self.position = Vector()
        self.world_position = Vector()
        
        self._cursor_hidden = False
        self._interal_cursor_hidden = False
        self.double_click_threshold = 0.4 #seconds
    
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
    