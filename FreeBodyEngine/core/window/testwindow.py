"""An invisible GLFW-backed window for automated testing (fb.TEST_WINDOW).

A real OpenGL context and a real render target exist here - the actual
UI renders exactly as it does in production - but the GLFW window is
created with VISIBLE forced off (see GLFWWindow's `visible` param), so
nothing ever appears on screen, steals focus, or triggers a window-
manager popup. Paired with SyntheticMouse below and the
inject_key_down/inject_key_up/inject_text methods on TestWindow, a
whole app session can be driven and inspected (via capture_screenshot())
without any real display, input hardware, or user interruption - see
phonon's test_harness.py for the driver that actually uses this.
"""
from OpenGL.GL import (
    glReadPixels, glPixelStorei, GL_PACK_ALIGNMENT, GL_RGB, GL_UNSIGNED_BYTE,
)
from PIL import Image as PILImage
import glfw

from FreeBodyEngine.core.window.glfw import GLFWWindow
from FreeBodyEngine.core.mouse import Mouse
from FreeBodyEngine.core.input import Key, KeyCallbackType
from FreeBodyEngine.math import Vector
from FreeBodyEngine import get_service
from FreeBodyEngine.ui.manager import KEY_CHAR_MAP

# Reverse of ui/manager.py's KEY_CHAR_MAP (unshifted/shifted char per
# Key) - built once here so inject_text() can go character -> (Key,
# needs_shift) without hand-duplicating that table.
_CHAR_TO_KEY: dict[str, tuple[Key, bool]] = {}
for _key, (_lo, _hi) in KEY_CHAR_MAP.items():
    _CHAR_TO_KEY.setdefault(_lo, (_key, False))
    _CHAR_TO_KEY.setdefault(_hi, (_key, True))


class TestWindow(GLFWWindow):
    """See module docstring. `window_type` stays 'glfw' deliberately - the
    renderer's context-selection code only special-cases 'wayland'/'x11'/
    'win32', so this rides the same default GL path a real GLFWWindow
    would use, with no renderer changes needed."""

    def __init__(self, size: tuple[int, int], title: str):
        super().__init__(size, title, visible=False)
        # Read by _get_key_down() below instead of real GLFW hardware
        # state - inject_key_down/up() are this dict's only writers.
        self._synthetic_keys: dict[Key, bool] = {}

    def create_mouse(self):
        """Returns a SyntheticMouse instead of a real GLFWMouse - see that class."""
        return SyntheticMouse(self)

    def _get_key_down(self, key: Key) -> float:
        return 1.0 if self._synthetic_keys.get(key, False) else 0.0

    # -- input injection -----------------------------------------------

    def inject_key_down(self, key: Key):
        """Marks `key` held and fires KEY_PRESS/KEY_REPEAT through
        Input._key_callback() - the exact same call a real keypress
        reaches via GLFWWindow._key_callback(), so every listener (UI
        text-input, actions, ...) sees an indistinguishable event."""
        already_down = self._synthetic_keys.get(key, False)
        self._synthetic_keys[key] = True
        get_service('input')._key_callback(
            key, KeyCallbackType.REPEAT if already_down else KeyCallbackType.PRESS
        )

    def inject_key_up(self, key: Key):
        """Marks `key` released and fires KEY_RELEASE - see inject_key_down()."""
        self._synthetic_keys[key] = False
        get_service('input')._key_callback(key, KeyCallbackType.RELEASE)

    def inject_key_tap(self, key: Key):
        """A full press-then-release of `key`, for keys a test doesn't need to hold (Enter, Escape, arrows, ...)."""
        self.inject_key_down(key)
        self.inject_key_up(key)

    def inject_text(self, text: str):
        """Types `text` one character at a time through the same KEY_PRESS
        path a real keyboard uses (see ui/manager.py's _on_key) - US-
        QWERTY only, same limitation as KEY_CHAR_MAP itself. Characters
        with no mapping (anything KEY_CHAR_MAP doesn't cover) are
        silently skipped rather than raising, since a test typing a
        whole sentence shouldn't die over one stray character."""
        for ch in text:
            entry = _CHAR_TO_KEY.get(ch)
            if entry is None:
                continue
            key, needs_shift = entry
            if needs_shift:
                self.inject_key_down(Key.L_SHIFT)
            self.inject_key_tap(key)
            if needs_shift:
                self.inject_key_up(Key.L_SHIFT)

    def capture_screenshot(self, path: str):
        """Saves the current framebuffer to a PNG at `path` - since this
        window is never shown on screen, this is the only way to see a
        frame. Call right after stepping a frame (so the buffer holds
        what was just drawn), before the next draw() overwrites it."""
        glfw.make_context_current(self._window)
        width, height = self.framebuffer_size
        glPixelStorei(GL_PACK_ALIGNMENT, 1)  # rows aren't 4-byte aligned for arbitrary RGB widths
        pixels = glReadPixels(0, 0, width, height, GL_RGB, GL_UNSIGNED_BYTE)
        image = PILImage.frombytes("RGB", (width, height), pixels)
        image = image.transpose(PILImage.FLIP_TOP_BOTTOM)  # GL reads bottom-up
        image.save(path)


class SyntheticMouse(Mouse):
    """Mouse implementation driven entirely by inject_*() calls instead of
    real hardware - see TestWindow.

    Press/release are queued rather than applied immediately, so a
    press injected between frames only becomes visible (get_pressed())
    on the one frame it's drained during update() - matching how a real
    Mouse only reports a press on the exact frame it polls the
    transition, not before or after."""

    def __init__(self, window: TestWindow):
        super().__init__()
        self.window = window
        self._down = [False] * 8
        self._pressed = [False] * 8
        self._released = [False] * 8
        self._drag_start = [Vector()] * 8
        self._press_queue: list[int] = []
        self._release_queue: list[int] = []
        self.scroll_delta = Vector(0, 0)
        self._pending_scroll = Vector(0, 0)

    # -- injection -------------------------------------------------------

    def inject_move(self, x: float, y: float):
        """Moves the cursor to (x, y) in screen space - takes effect immediately, not queued (position is a level value, not edge-triggered)."""
        self.position = Vector(x, y)
        self.world_position = self.position

    def inject_press(self, button: int = 0):
        """Queues `button` to read as pressed on the next frame this mouse's update() runs."""
        self._press_queue.append(button)

    def inject_release(self, button: int = 0):
        """Queues `button` to read as released on the next frame this mouse's update() runs."""
        self._release_queue.append(button)

    def inject_click(self, x: float, y: float, button: int = 0):
        """Moves to (x, y) and queues a press - the caller must still step
        a frame and then inject_release() (see test_harness.py's
        Harness.click()) for a real click, exactly like real hardware:
        a click is a press on one frame and a release on a later one."""
        self.inject_move(x, y)
        self.inject_press(button)

    def inject_scroll(self, dx: float, dy: float):
        self._pending_scroll += Vector(dx, dy)

    # -- Mouse interface ---------------------------------------------------

    def lock_position(self):
        pass

    def unlock_position(self):
        pass

    def get_pressed(self, button: int) -> bool:
        return self._pressed[button]

    def get_down(self, button: int) -> bool:
        return self._down[button]

    def get_released(self, button: int) -> bool:
        return self._released[button]

    def get_double_click(self, button: int) -> bool:
        return False

    def get_dragging(self, button: int) -> bool:
        return self._down[button]

    def get_drag_start(self, button: int, world: bool = False) -> Vector:
        return self._drag_start[button]

    def get_scroll_delta(self) -> Vector:
        return self.scroll_delta

    def set_cursor(self, shape: str = "default"):
        pass  # never shown - no system cursor to set a shape on

    def update(self):
        """Drains this frame's queued press/release into the one-shot
        get_pressed()/get_released() flags (cleared first, same as every
        other Mouse backend clearing its own transient state each
        frame)."""
        self._pressed = [False] * 8
        self._released = [False] * 8

        for button in self._press_queue:
            self._pressed[button] = True
            self._down[button] = True
            self._drag_start[button] = self.position
        self._press_queue = []

        for button in self._release_queue:
            self._released[button] = True
            self._down[button] = False
        self._release_queue = []

        self.scroll_delta = self._pending_scroll
        self._pending_scroll = Vector(0, 0)
