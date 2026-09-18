from FreeBodyEngine.math import Vector
from FreeBodyEngine.utils import abstractmethod


class DummyMouse:
    """No-op stand-in for Mouse (core/mouse.py), used by headless windows where there's no real cursor to track. Every query reports "nothing pressed/dragging" instead of reading any backend state."""
    def __init__(self):
        """Sets up the same attributes as Mouse, all at their default/empty values."""
        self._dragging = False
        self.drag_start = Vector()

        self.position = Vector()
        self.world_position = Vector()

        self._cursor_hidden = False

    def get_pressed(self, button: int) -> bool:
        """Always returns False - there is no real mouse to be pressed."""
        return False

    def get_down(self, button: int) -> bool:
        """Always returns False - there is no real mouse to be held down."""
        return False

    def get_released(self, button: int) -> bool:
        """Always returns False - there is no real mouse to be released."""
        return False

    def get_double_click(self, button: int) -> bool:
        """Always returns False - there is no real mouse to be double-clicked."""
        return False

    def get_dragging(self, button: int) -> bool:
        """Always returns False - there is no real mouse to be dragging."""
        return False

    def get_drag_start(self, button: int, world: bool = False):
        """Always returns a zero Vector - there is no real drag to have started."""
        return Vector()

    def get_drag_offset(self, button: int, world: bool = False):
        """Always returns a zero Vector - there is no real drag to measure."""
        return Vector()

    def hide_cursor(self):
        """No-op - there is no real cursor to hide."""
        pass

    def set_cursor(self, shape: str = "default"):
        """No-op - there is no real cursor to set."""
        pass

    def update(self):
        """No-op - there is no real mouse state to poll."""
        pass
