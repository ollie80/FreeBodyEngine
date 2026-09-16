from FreeBodyEngine.core.window import Window, Cursor, WINDOW_RESIZE, FRAMEBUFFER_RESIZE 
from FreeBodyEngine.core.mouse import Mouse
from FreeBodyEngine.utils import abstractmethod
from typing import TYPE_CHECKING
from FreeBodyEngine.core.input import Key, KeyCallbackType, GamepadButton, GamepadAxis
from FreeBodyEngine.math import Vector
from FreeBodyEngine.core.camera import Camera
from FreeBodyEngine import emit_event
from FreeBodyEngine import get_flag, DEVMODE, QUIT, error, get_main, get_service, get_time
import numpy

import glfw

if TYPE_CHECKING:
    from FreeBodyEngine.core.main import Main
    from FreeBodyEngine.graphics.image import Image

GLFW_KEY_CALLBACK_TYPE_MAP = {
    glfw.PRESS: KeyCallbackType.PRESS,
    glfw.RELEASE: KeyCallbackType.RELEASE,
    glfw.REPEAT: KeyCallbackType.REPEAT
}

GLFW_CHARACTER_MAP = {
    Key.A: glfw.KEY_A,
    Key.B: glfw.KEY_B,
    Key.C: glfw.KEY_C,
    Key.D: glfw.KEY_D,
    Key.E: glfw.KEY_E,
    Key.F: glfw.KEY_F,
    Key.G: glfw.KEY_G,
    Key.H: glfw.KEY_H,
    Key.I: glfw.KEY_I,
    Key.J: glfw.KEY_J,
    Key.K: glfw.KEY_K,
    Key.L: glfw.KEY_L,
    Key.M: glfw.KEY_M,
    Key.N: glfw.KEY_N,
    Key.O: glfw.KEY_O,
    Key.P: glfw.KEY_P,
    Key.Q: glfw.KEY_Q,
    Key.R: glfw.KEY_R,
    Key.S: glfw.KEY_S,
    Key.T: glfw.KEY_T,
    Key.U: glfw.KEY_U,
    Key.V: glfw.KEY_V,
    Key.W: glfw.KEY_W,
    Key.X: glfw.KEY_X,
    Key.Y: glfw.KEY_Y,
    Key.Z: glfw.KEY_Z,

    Key.ONE: glfw.KEY_1,
    Key.TWO: glfw.KEY_2,
    Key.THREE: glfw.KEY_3,
    Key.FOUR: glfw.KEY_4,
    Key.FIVE: glfw.KEY_5,
    Key.SIX: glfw.KEY_6,
    Key.SEVEN: glfw.KEY_7,
    Key.EIGHT: glfw.KEY_8,
    Key.NINE: glfw.KEY_9,
    Key.ZERO: glfw.KEY_0,

    Key.MINUS: glfw.KEY_MINUS,
    Key.EQUAL: glfw.KEY_EQUAL,
    Key.LEFT_BRACKET: glfw.KEY_LEFT_BRACKET,
    Key.RIGHT_BRACKET: glfw.KEY_RIGHT_BRACKET,
    Key.BACKSLASH: glfw.KEY_BACKSLASH,
    Key.SEMICOLON: glfw.KEY_SEMICOLON,
    Key.APOSTROPHE: glfw.KEY_APOSTROPHE,
    Key.TILDE: glfw.KEY_GRAVE_ACCENT,
    Key.COMMA: glfw.KEY_COMMA,
    Key.PERIOD: glfw.KEY_PERIOD,
    Key.SLASH: glfw.KEY_SLASH,

    Key.SPACE: glfw.KEY_SPACE,
    Key.RETURN: glfw.KEY_ENTER,
    Key.BACKSPACE: glfw.KEY_BACKSPACE,
    Key.TAB: glfw.KEY_TAB,
    Key.ESCAPE: glfw.KEY_ESCAPE,
    Key.CAPS_LOCK: glfw.KEY_CAPS_LOCK,

    Key.L_CTRL: glfw.KEY_LEFT_CONTROL,
    Key.R_CTRL: glfw.KEY_RIGHT_CONTROL,
    Key.L_SHIFT: glfw.KEY_LEFT_SHIFT,
    Key.R_SHIFT: glfw.KEY_RIGHT_SHIFT,
    Key.L_ALT: glfw.KEY_LEFT_ALT,
    Key.R_ALT: glfw.KEY_RIGHT_ALT,
    Key.L_SUPER: glfw.KEY_LEFT_SUPER,
    Key.R_SUPER: glfw.KEY_RIGHT_SUPER,

    Key.INSERT: glfw.KEY_INSERT,
    Key.DELETE: glfw.KEY_DELETE,
    Key.HOME: glfw.KEY_HOME,
    Key.END: glfw.KEY_END,
    Key.PG_UP: glfw.KEY_PAGE_UP,
    Key.PG_DOWN: glfw.KEY_PAGE_DOWN,
    Key.UP: glfw.KEY_UP,
    Key.DOWN: glfw.KEY_DOWN,
    Key.LEFT: glfw.KEY_LEFT,
    Key.RIGHT: glfw.KEY_RIGHT,

    Key.F1: glfw.KEY_F1,
    Key.F2: glfw.KEY_F2,
    Key.F3: glfw.KEY_F3,
    Key.F4: glfw.KEY_F4,
    Key.F5: glfw.KEY_F5,
    Key.F6: glfw.KEY_F6,
    Key.F7: glfw.KEY_F7,
    Key.F8: glfw.KEY_F8,
    Key.F9: glfw.KEY_F9,
    Key.F10: glfw.KEY_F10,
    Key.F11: glfw.KEY_F11,
    Key.F12: glfw.KEY_F12,
    Key.F13: glfw.KEY_F13,
    Key.F14: glfw.KEY_F14,
    Key.F15: glfw.KEY_F15,
    Key.F16: glfw.KEY_F16,
    Key.F17: glfw.KEY_F17,
    Key.F18: glfw.KEY_F18,
    Key.F19: glfw.KEY_F19,
    Key.F20: glfw.KEY_F20,
    Key.F21: glfw.KEY_F21,
    Key.F22: glfw.KEY_F22,
    Key.F23: glfw.KEY_F23,
    Key.F24: glfw.KEY_F24,

    Key.NUMPAD_0: glfw.KEY_KP_0,
    Key.NUMPAD_1: glfw.KEY_KP_1,
    Key.NUMPAD_2: glfw.KEY_KP_2,
    Key.NUMPAD_3: glfw.KEY_KP_3,
    Key.NUMPAD_4: glfw.KEY_KP_4,
    Key.NUMPAD_5: glfw.KEY_KP_5,
    Key.NUMPAD_6: glfw.KEY_KP_6,
    Key.NUMPAD_7: glfw.KEY_KP_7,
    Key.NUMPAD_8: glfw.KEY_KP_8,
    Key.NUMPAD_9: glfw.KEY_KP_9,
    Key.NUMPAD_DECIMAL: glfw.KEY_KP_DECIMAL,
    Key.NUMPAD_DIVIDE: glfw.KEY_KP_DIVIDE,
    Key.NUMPAD_MULTIPLY: glfw.KEY_KP_MULTIPLY,
    Key.NUMPAD_SUBTRACT: glfw.KEY_KP_SUBTRACT,
    Key.NUMPAD_ADD: glfw.KEY_KP_ADD,
    Key.NUMPAD_ENTER: glfw.KEY_KP_ENTER,
}

class GLFWWindow(Window):
    """Window backend built on GLFW, the engine's cross-platform fallback.

    Used whenever a native backend (X11/Wayland/Win32) isn't selected or
    available - GLFW handles window creation, the OpenGL context, and input
    polling itself, so this class is mostly a thin translation layer between
    GLFW's API and the engine's Window/Mouse contracts.
    """
    def __init__(self, size: tuple[int, int], title: str):
        """Initializes GLFW, creates the window and its OpenGL 4.3 core context, and makes it current."""
        super().__init__(size, title)
        self.window_type = 'glfw'


        if not glfw.init():
            raise RuntimeError("GLFW failed to initialize")
        glfw.init_hint(glfw.PLATFORM, glfw.PLATFORM_X11)
        glfw.window_hint(glfw.SCALE_FRAMEBUFFER, glfw.TRUE)
        glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 4)
        glfw.window_hint(glfw.POSITION_X, 200)
        glfw.window_hint(glfw.POSITION_Y, 200)
        glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
        glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
        glfw.window_hint(glfw.OPENGL_DEBUG_CONTEXT, get_flag(DEVMODE, False))
        glfw.window_hint(glfw.DEPTH_BITS, 24)

        self._window = glfw.create_window(size[0], size[1], title, None, None)
        if not self._window:
            glfw.terminate()
            error("Failed to create GLFW window")

        glfw.make_context_current(self._window)
        glfw.set_window_size_callback(self._window, self.resize)

        # Neither of these was ever wired up before - _key_callback existed
        # as a method but nothing told GLFW to call it, so no KEY_PRESS/
        # RELEASE/REPEAT event ever fired on this backend (Wayland's
        # equivalent path, _on_keyboard_key, was already connected). Scroll
        # is new: GLFWMouse.get_scroll_delta() reads self._scroll_accum,
        # accumulated here and drained once per frame.
        glfw.set_key_callback(self._window, self._key_callback)
        glfw.set_scroll_callback(self._window, self._scroll_callback)
        self._scroll_accum = Vector(0.0, 0.0)

    def _key_callback(self, window, key, scancode, action, mods):
        input_key = GLFW_CHARACTER_MAP[key]
        key_type = GLFW_KEY_CALLBACK_TYPE_MAP[action]

        get_service('input')._key_callback(input_key, key_type)

    def _scroll_callback(self, window, xoffset, yoffset):
        self._scroll_accum += Vector(xoffset, yoffset)

    def set_title(self, new_title):
        """Sets the OS-level window title."""
        glfw.set_window_title(self._window, new_title)

    @property
    def size(self) -> tuple[int, int]:
        """The window's client area size, in pixels, as reported by GLFW."""
        return glfw.get_window_size(self._window)

    @property
    def framebuffer_size(self) -> tuple[int, int]:
        """The size, in pixels, of the GL framebuffer (may differ from `size` under display scaling)."""
        return glfw.get_framebuffer_size(self._window)

    def resize(self, window, width, height):
        """GLFW window-size callback - fires WINDOW_RESIZE/FRAMEBUFFER_RESIZE for both programmatic and user-driven resizes."""
        emit_event(WINDOW_RESIZE, (width, height))
        emit_event(FRAMEBUFFER_RESIZE, self.framebuffer_size)


    @size.setter
    def size(self, new: tuple[int, int]):
        """Resizes the window's client area to `new` (width, height), in pixels."""
        glfw.set_window_size(self._window, new[0], new[1])


    @property
    def position(self) -> tuple[int, int]:
        """The window's position on screen, in pixels, as (x, y)."""
        return glfw.get_window_pos(self._window)

    @position.setter
    def position(self, new: tuple[int, int]):
        """Moves the window to `new` (x, y), in pixels."""
        glfw.set_window_pos(self._window, new[0], new[1])

    def is_ready(self) -> bool:
        """True as long as GLFW hasn't been told to close this window."""
        return not glfw.window_should_close(self._window)

    def _get_key_down(self, key: Key):
        return 0.0 if glfw.get_key(self._window, GLFW_CHARACTER_MAP[key]) == glfw.RELEASE else 1.0

    def _get_gamepad_state(self, gamepad: int):
        if not glfw.joystick_is_gamepad(gamepad):
            return {
                button: 0.0 for button in GamepadButton
            } | {
                axis: 0.0 for axis in GamepadAxis
            }

        state = {
            button: 0.0 for button in GamepadButton
        } | {
            axis: 0.0 for axis in GamepadAxis
        }

        gamepad_state = glfw.get_gamepad_state(gamepad)

        if gamepad_state is None:
            return state

        button_map = {
            GamepadButton.A: glfw.GAMEPAD_BUTTON_A,
            GamepadButton.B: glfw.GAMEPAD_BUTTON_B,
            GamepadButton.X: glfw.GAMEPAD_BUTTON_X,
            GamepadButton.Y: glfw.GAMEPAD_BUTTON_Y,
            GamepadButton.LB: glfw.GAMEPAD_BUTTON_LEFT_BUMPER,
            GamepadButton.RB: glfw.GAMEPAD_BUTTON_RIGHT_BUMPER,
            GamepadButton.LS_DOWN: glfw.GAMEPAD_BUTTON_LEFT_THUMB,
            GamepadButton.RS_DOWN: glfw.GAMEPAD_BUTTON_RIGHT_THUMB,
            GamepadButton.GUIDE: glfw.GAMEPAD_BUTTON_GUIDE,
            GamepadButton.DPAD_UP: glfw.GAMEPAD_BUTTON_DPAD_UP,
            GamepadButton.DPAD_RIGHT: glfw.GAMEPAD_BUTTON_DPAD_RIGHT,
            GamepadButton.DPAD_DOWN: glfw.GAMEPAD_BUTTON_DPAD_DOWN,
            GamepadButton.DPAD_LEFT: glfw.GAMEPAD_BUTTON_DPAD_LEFT,
        }

        for button, glfw_button in button_map.items():
            state[button] = float(
                gamepad_state.buttons[glfw_button]
            )

        axis_map = {
            GamepadAxis.LEFT_X: glfw.GAMEPAD_AXIS_LEFT_X,
            GamepadAxis.LEFT_Y: glfw.GAMEPAD_AXIS_LEFT_Y,
            GamepadAxis.RIGHT_X: glfw.GAMEPAD_AXIS_RIGHT_X,
            GamepadAxis.RIGHT_Y: glfw.GAMEPAD_AXIS_RIGHT_Y,
            GamepadAxis.LEFT_TRIGGER: glfw.GAMEPAD_AXIS_LEFT_TRIGGER,
            GamepadAxis.RIGHT_TRIGGER: glfw.GAMEPAD_AXIS_RIGHT_TRIGGER,
        }

        for axis, glfw_axis in axis_map.items():
            state[axis] = float(
                gamepad_state.axes[glfw_axis]
            )

        return state 
         

    def _create_cursor(self, image: 'Image'):
        pass

    def _set_cursor(self, cursor: 'Cursor'):
        pass

    def create_mouse(self):
        """Creates and returns this window's GLFWMouse."""
        return GLFWMouse(self)

    def close(self):
        """Flags the GLFW window to close, destroys it, terminates GLFW, and emits QUIT."""
        glfw.set_window_should_close(self._window, True)
        glfw.destroy_window(self._window)
        glfw.terminate()
        emit_event(QUIT)

    def draw(self):
        """Swaps the GLFW window's front/back buffers to present the frame."""
        glfw.swap_buffers(self._window)

    def update(self):
        """Polls GLFW events for this frame and quits the engine once the window is told to close."""
        glfw.poll_events()
        if glfw.window_should_close(self._window):

            get_main().quit()

glfw_mouse_button_map = {
    0: glfw.MOUSE_BUTTON_1,
    1: glfw.MOUSE_BUTTON_2,
    2: glfw.MOUSE_BUTTON_3,
    3: glfw.MOUSE_BUTTON_4,
    4: glfw.MOUSE_BUTTON_5,
    5: glfw.MOUSE_BUTTON_6,
    6: glfw.MOUSE_BUTTON_7,
    7: glfw.MOUSE_BUTTON_8
}

class GLFWMouse(Mouse):
    """Mouse implementation for the GLFW backend - polls button/position state from GLFW each frame."""
    def __init__(self, window: GLFWWindow):
        """Sets up per-button state tracking for `window`."""
        super().__init__()
        self.window = window
        self._pressed = [False] * 8
        self._released = [False] * 8
        self._down = [False] * 8
        self._double_clicked = [False] * 8
        self._dragging = [False] * 8
        self.last_click_time = -500
        self.drag_threshold = 0.2
        self.scroll_delta = Vector(0, 0)

    def get_scroll_delta(self) -> Vector:
        """How far the scroll wheel moved this frame, drained from the
        window's GLFW scroll callback each `update()`."""
        return self.scroll_delta

    def get_pressed(self, button: int):
        """True on the frame `button` was pressed."""
        return self._pressed[button]

    def get_released(self, button: int):
        """True on the frame `button` was released."""
        return self._released[button]

    def get_down(self, button: int):
        """True for as long as `button` is held down."""
        return self._down[button]

    def get_double_click(self, button: int):
        """True on the frame `button` was pressed as part of a double-click."""
        return self._double_clicked[button]

    def update(self):
        """Polls GLFW's cursor/button state for this frame and updates screen and world-space position, click and drag state."""
        self.position = Vector(glfw.get_cursor_pos(self.window._window))
        scene = get_service('scene_manager').get_active()
        
        self.world_position = self.position
        if scene != None:
            cam: Camera = scene.camera
            if cam != None:
                ndc_x = (self.position.x / self.window.size[0]) * 2.0 - 1.0 #convert to clip space
                ndc_y = (self.position.y / self.window.size[1]) * 2.0 - 1.0
                clip_pos = (ndc_x, ndc_y, 0.0, 1.0)
                
                proj_view_inverse = numpy.linalg.inv(cam.proj_matrix @ cam._get_view_mat())
                p =  proj_view_inverse @ clip_pos
                p /= p[3]
                self.world_position = Vector(p[0], p[1])
        
        self._pressed = [False] * 8
        self._released = [False] * 8
        self._double_clicked = [False] * 8

        self.scroll_delta = self.window._scroll_accum
        self.window._scroll_accum = Vector(0.0, 0.0)

        for i in range(len(self._pressed)):
            glfw_i = glfw_mouse_button_map[i]
            button_state = glfw.get_mouse_button(self.window._window, glfw_i)
            
            pressed = button_state == glfw.PRESS
            released = button_state == glfw.RELEASE

            if self._down[i]:
                pressed = False
            
            if pressed:
                self._down[i] = True
                time = get_time()
                time_dif = time - self.last_click_time
                if time_dif <= self.double_click_threshold:
                    self._double_clicked[i] = True
                self.last_click_time = time
                

            if released:
                self._down[i] = False

            self._pressed[i] = pressed

            self._released[i] = released


_raw_offscreen_window = None  # kept alive so GLFW doesn't tear the context down under us


def create_raw_offscreen_context():
    """A bare GLFW-backed OpenGL context with *no* Window/Service wrapper
    around it at all - not a GLFWWindow, not registered as the 'window'
    service, no input/event pump, nothing. Used by
    graphics.ensure_gpu_context() for a genuinely headless compute-only
    session: "headless" means no window service running at all, not a
    window service that merely happens to be invisible.

    Safe to call repeatedly - the same context is reused (and made current
    again, in case something else changed the current context on this
    thread since) rather than creating a new one each time.
    """
    global _raw_offscreen_window

    if _raw_offscreen_window is not None:
        glfw.make_context_current(_raw_offscreen_window)
        return _raw_offscreen_window

    if not glfw.init():
        raise RuntimeError("GLFW failed to initialize")

    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 4)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
    glfw.window_hint(glfw.VISIBLE, glfw.FALSE)

    window = glfw.create_window(1, 1, "", None, None)
    if not window:
        glfw.terminate()
        raise RuntimeError("Failed to create an offscreen OpenGL context")

    glfw.make_context_current(window)
    _raw_offscreen_window = window
    return window


def destroy_raw_offscreen_context():
    """Destroys the shared offscreen context created by create_raw_offscreen_context(), if one exists."""
    global _raw_offscreen_window
    if _raw_offscreen_window is not None:
        glfw.destroy_window(_raw_offscreen_window)
        _raw_offscreen_window = None
            
        
        
