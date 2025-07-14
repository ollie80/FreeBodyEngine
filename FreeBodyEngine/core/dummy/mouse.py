from FreeBodyEngine.math import Vector
from FreeBodyEngine.utils import abstractmethod


class DummyMouse:
    def __init__(self):
        self._dragging = False
        self.drag_start = Vector()

        self.position = Vector()
        self.world_position = Vector()
        
        self._cursor_hidden = False
    
    def get_pressed(self, button: int) -> bool:
        return False

    def get_down(self, button: int) -> bool:
        return False
    
    def get_released(self, button: int) -> bool:
        return False

    def get_double_click(self, button: int) -> bool:
        return False

    def get_dragging(self, button: int) -> bool:
        return False

    def get_drag_start(self, button: int, world: bool = False):
        return Vector()

    def get_drag_offset(self, button: int, world: bool = False):
        return Vector()

    def hide_cursor(self):
        pass

    def set_cursor(self):
        pass

    def update(self):
        pass
    