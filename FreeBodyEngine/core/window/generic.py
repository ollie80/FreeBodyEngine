from FreeBodyEngine.utils import abstractmethod
from FreeBodyEngine import register_service_update, unregister_service_update, get_service, service_exists
from typing import TYPE_CHECKING, Union, Literal
from FreeBodyEngine.core.input import Key
from FreeBodyEngine.core.mouse import Mouse

if TYPE_CHECKING:
    from FreeBodyEngine.core.main import Main
    from FreeBodyEngine.graphics.image import Image

from FreeBodyEngine.core.service import Service

class Cursor:
    """The generic cursor class. Abstracts cursor management to easily create cross-platform cursors."""
    pass

class Window(Service):
    """
    The generic window class. Its purpose is to abstract window management.
    """
    def __init__(self, size: tuple[int, int], title: str):
        super().__init__('window')
        self.window_type = None

    def on_initialize(self):
        register_service_update('early', self.update)
        register_service_update('late', self.draw)

    def on_destroy(self):
        unregister_service_update('early', self.update)
        unregister_service_update('late', self.draw)

    @property
    @abstractmethod
    def size(self) -> tuple[int, int]:
        pass

    @size.setter
    @abstractmethod
    def size(self, new: tuple[int, int]):
        pass

    @abstractmethod
    def create_mouse(self) -> Mouse:
        pass

    def _resize(self):
        if service_exists('renderer'):
            get_service('renderer').resize()        

        if service_exists('graphics'):
            get_service('graphics').resize()

    @abstractmethod
    def is_ready(self) -> bool:
        pass

    @property
    @abstractmethod
    def position(self) -> tuple[int, int]:
        pass

    @size.setter
    @abstractmethod
    def position(self, new: tuple[int, int]):
        pass

    @abstractmethod
    def _create_cursor(self, image: 'Image'):
        """Creates cross-platform cursor objects."""
        pass

    @abstractmethod
    def _set_cursor(self, cursor: 'Cursor'):
        pass

    @abstractmethod
    def _get_key_down(self, key: Key) -> float:
        pass

    @abstractmethod
    def set_title(self, new_title: str):
        pass

    @abstractmethod
    def _get_gamepad_state(self, id: int):
        pass

    @abstractmethod
    def close(self):
        pass

    @abstractmethod
    def draw(self):
        pass

    @abstractmethod
    def update(self):
        pass


