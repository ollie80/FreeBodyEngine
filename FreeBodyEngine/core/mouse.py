from FreeBodyEngine.math import Vector
from FreeBodyEngine.utils import abstractmethod
from FreeBodyEngine.core.service import Service
from FreeBodyEngine.core.update import UpdatePhase
from FreeBodyEngine import register_service_update, unregister_service_update, warning

class Mouse(Service):
    """Base mouse service - tracks cursor position, button state, dragging, and double-clicks. Each window backend (GLFW/X11/Wayland) provides a concrete subclass implementing the abstract methods below."""
    def __init__(self):
        """Sets up default cursor/drag/button-state tracking."""
        super().__init__('mouse')
        self.dependencies.append('window')

        self._dragging = False
        self.drag_start = Vector()

        self.position = Vector()
        self.world_position = Vector()
        
        self._cursor_hidden = False
        self._interal_cursor_hidden = False
        self.double_click_threshold = 0.4
        self._warned_no_cursor_support = False
    
    def on_initialize(self):
        """Registers update() to run every frame's EARLY phase."""
        register_service_update(UpdatePhase.EARLY, self.update)

    def on_destroy(self):
        """Unregisters update() from the EARLY update phase."""
        unregister_service_update(UpdatePhase.EARLY, self.update)

    @abstractmethod
    def lock_position(self):
        """Locks the cursor position on screen, stoping it from moving while still getting movement information."""
        pass

    @abstractmethod
    def unlock_position(self):
        """Releases a cursor lock previously set by lock_position(), letting the cursor move freely again."""
        pass

    @abstractmethod
    def get_pressed(self, button: int) -> bool:
        """Returns whether `button` was pressed down this frame."""
        pass

    @abstractmethod
    def get_down(self, button: int) -> bool:
        """Returns whether `button` is currently held down."""
        pass

    @abstractmethod
    def get_released(self, button: int) -> bool:
        """Returns whether `button` was released this frame."""
        pass

    @abstractmethod
    def get_double_click(self, button: int) -> bool:
        """Returns whether `button` was double-clicked this frame (two presses within `double_click_threshold` seconds)."""
        pass

    @abstractmethod
    def get_dragging(self, button: int) -> bool:
        """Returns whether `button` is currently being dragged."""
        pass

    @abstractmethod
    def get_drag_start(self, button: int, world: bool = False) -> Vector:
        """Returns the position `button`'s current drag started at, in world or screen space depending on `world`."""
        pass

    def get_scroll_delta(self) -> Vector:
        """Returns how far the scroll wheel moved this frame (x = horizontal,
        y = vertical - positive y is scrolling up). Concrete default of
        `Vector(0, 0)` (no scrolling) for backends that don't report a wheel
        yet; GLFWMouse and WaylandMouse override this with real values."""
        return Vector(0, 0)

    def get_drag_offset(self, button: int, world: bool = False) -> Vector:
        """Returns how far the cursor has moved since `button`'s drag started, in world or screen space depending on `world`."""
        if world:
            return self.get_drag_start(button, world) + self.world_position
        else:
            return self.get_drag_start(button, world) + self.position


    def hide_cursor(self):
        """Hides the system cursor. Concrete no-op (with a one-time warning)
        for backends that haven't implemented real cursor control yet -
        see WaylandMouse/GLFWMouse for the backends that actually do."""
        if not self._warned_no_cursor_support:
            warning(f"hide_cursor() is not implemented on '{self.__class__.__name__}' - ignoring.")
            self._warned_no_cursor_support = True

    def set_cursor(self, shape: str = "default"):
        """Sets the system cursor's shape - one of "default", "pointer",
        "text", "grab", "grabbing", "crosshair", "wait", "not_allowed"
        (backends may support more; unsupported names fall back to
        "default"). Concrete no-op (with a one-time warning) for backends
        that haven't implemented real cursor control yet - see
        WaylandMouse/GLFWMouse for the backends that actually do."""
        if not self._warned_no_cursor_support:
            warning(f"set_cursor() is not implemented on '{self.__class__.__name__}' - ignoring.")
            self._warned_no_cursor_support = True

    @abstractmethod
    def update(self):
        """Polls the window backend for the current cursor position and button state, refreshing this frame's press/release/drag/double-click tracking."""
        pass
