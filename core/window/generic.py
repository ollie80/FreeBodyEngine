from FreeBodyEngine.utils import abstractmethod
from typing import TYPE_CHECKING, Union, Literal

if TYPE_CHECKING:
    from FreeBodyEngine.core.main import Main
    from FreeBodyEngine.graphics.image import Image

class Cursor:
    """The generic cursor class. Abstracts cursor management to easily create cross-platform cursors."""
    pass

class Window:
    """
    The generic window class. Its purpose is to abstract window management.
    """
    def __init__(self, main: 'Main', size: tuple[int, int], window_type: str, title="FreeBodyEngine", display=None):
        self.main = main
        self.window_type = window_type

    @abstractmethod
    def set_size(self, size: tuple[int, int]):
        pass

    @abstractmethod
    def _create_cursor(self, image: 'Image'):
        """Creates cross-platform cursor objects."""
        pass

    @abstractmethod
    def _set_cursor(self, cursor: 'Cursor'):
        pass

    @abstractmethod
    def close(self):
        pass

    @abstractmethod
    def update(self, dt):
        pass

