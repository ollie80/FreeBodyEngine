from FreeBodyEngine.utils import abstractmethod
from FreeBodyEngine.core.update import UpdatePhase
from FreeBodyEngine import register_event, unregister_event, register_service_update, register_event_category, unregister_event_category, unregister_service_update, get_service, service_exists, warning
from typing import TYPE_CHECKING, Union, Literal
from FreeBodyEngine.core.input import Key
from FreeBodyEngine.core.mouse import Mouse

if TYPE_CHECKING:
    from FreeBodyEngine.core.main import Main
    from FreeBodyEngine.graphics.image import Image

from FreeBodyEngine.core.service import Service

WINDOW_RESIZE = "ENGINE_window_resize"
FRAMEBUFFER_RESIZE = "ENGINE_framebuffer_resize"

class Cursor:
    """Base class for a platform-native cursor handle.

    Has no behavior of its own - each backend that supports custom cursors
    (e.g. Win32Cursor) subclasses this to wrap its own native handle. Also
    used directly as the dummy cursor object returned by create_cursor() in
    headless mode, where there is no real window to own a cursor.
    """
    pass

class Window(Service):
    """Abstract base class for the engine's window backends.

    Registered as the 'window' service; every platform implementation
    (GLFWWindow, WaylandWindow, X11Window, Win32Window, HeadlessWindow)
    subclasses this and fills in the methods marked @abstractmethod below,
    which together form the contract the rest of the engine (input,
    rendering, the main loop) relies on regardless of which backend is
    actually running.
    """
    def __init__(self, size: tuple[int, int], title: str):
        """Registers this instance as the 'window' service.

        Subclasses call this first via super().__init__(), then go on to
        create their actual native window and set self.window_type to their
        own backend name (e.g. 'glfw', 'x11') - it starts as None here since
        the base class has no backend of its own.
        """
        super().__init__('window')
        self.window_type = None
        self._warned_no_clipboard_support = False

    def on_initialize(self):
        """Hooks window update/draw into the engine's per-frame update phases and registers the window resize events."""
        register_service_update(UpdatePhase.EARLY, self.update)
        register_service_update(UpdatePhase.LATE, self.draw)

        register_event_category('window')
        register_event(WINDOW_RESIZE, 'window')
        register_event(FRAMEBUFFER_RESIZE, 'window')

    def on_destroy(self):
        """Undoes on_initialize() - unhooks the per-frame update/draw calls and unregisters the window events."""
        unregister_service_update(UpdatePhase.EARLY, self.update)
        unregister_service_update(UpdatePhase.LATE, self.draw)


        unregister_event_category('window')
        unregister_event(WINDOW_RESIZE)
        unregister_event(FRAMEBUFFER_RESIZE)

    @property
    @abstractmethod
    def size(self) -> tuple[int, int]:
        """The window's client area size, in pixels, as (width, height)."""
        pass

    @size.setter
    @abstractmethod
    def size(self, new: tuple[int, int]):
        """Resizes the window's client area to `new` (width, height), in pixels."""
        pass

    @property
    @abstractmethod
    def framebuffer_size(self) -> tuple[int, int]:
        """The size, in pixels, of the actual drawable framebuffer.

        Not always equal to `size` - on displays with fractional/HiDPI
        scaling the OS may report the window's logical size while the GPU
        surface backing it is allocated at a different pixel density.
        """
        pass

    @abstractmethod
    def create_mouse(self) -> Mouse:
        """Creates and returns this backend's Mouse implementation, wired up to this window's input events."""
        pass

    @abstractmethod
    def is_ready(self) -> bool:
        """Whether the window has finished its platform-specific setup and is ready to be drawn to / receive input."""
        pass

    @property
    @abstractmethod
    def position(self) -> tuple[int, int]:
        """The window's position on screen, in pixels, as (x, y)."""
        pass

    @size.setter
    @abstractmethod
    def position(self, new: tuple[int, int]):
        """Moves the window to `new` (x, y), in pixels."""
        pass

    @abstractmethod
    def _create_cursor(self, image: 'Image'):
        pass

    @abstractmethod
    def _set_cursor(self, cursor: 'Cursor'):
        pass

    def get_clipboard_text(self) -> str | None:
        """Returns the system clipboard's current text content, or None if
        it's empty, isn't text, or this backend hasn't implemented real
        clipboard access yet - see WaylandWindow/GLFWWindow for the
        backends that actually do. Concrete no-op (with a one-time
        warning) rather than a crash-on-call abstract, since ui/manager.py
        calls this unconditionally on Ctrl+V regardless of backend."""
        if not self._warned_no_clipboard_support:
            warning(f"get_clipboard_text() is not implemented on '{self.__class__.__name__}' - ignoring.")
            self._warned_no_clipboard_support = True
        return None

    def set_clipboard_text(self, text: str):
        """Sets the system clipboard's text content - see get_clipboard_text
        just above for why this is a concrete no-op (with the same
        one-time warning flag) rather than a crash-on-call abstract."""
        if not self._warned_no_clipboard_support:
            warning(f"set_clipboard_text() is not implemented on '{self.__class__.__name__}' - ignoring.")
            self._warned_no_clipboard_support = True

    @abstractmethod
    def _get_key_down(self, key: Key) -> float:
        pass

    @abstractmethod
    def set_title(self, new_title: str):
        """Sets the OS-level window title/caption."""
        pass

    @abstractmethod
    def _get_gamepad_state(self, id: int):
        pass

    @abstractmethod
    def close(self):
        """Closes the window and releases its native resources, signaling the engine to quit."""
        pass

    @abstractmethod
    def draw(self):
        """Presents the completed frame, typically by swapping the window's front/back buffers."""
        pass

    @abstractmethod
    def update(self):
        """Pumps the platform's event queue for one frame, dispatching input events and detecting a close request."""
        pass


