import glfw
from FreeBodyEngine.core.window import Window, Cursor
from FreeBodyEngine.utils import abstractmethod
from typing import TYPE_CHECKING
from FreeBodyEngine import error
from FreeBodyEngine.core.input import Key

if TYPE_CHECKING:
    from FreeBodyEngine.core.main import Main
    from FreeBodyEngine.graphics.image import Image

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
    def __init__(self, main: 'Main', size: tuple[int, int], window_type: str, title="FreeBodyEngine", display=None):
        super().__init__(main, size, window_type, title, display)
        self._size = size
        self._title = title
        self._should_close = False

        if not glfw.init():
            raise RuntimeError("GLFW failed to initialize")
        
        if main.dev:
            debug = glfw.TRUE
        else:
            debug = glfw.FALSE
        glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 4)
        glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
        glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
        glfw.window_hint(glfw.OPENGL_DEBUG_CONTEXT, debug)
        glfw.window_hint(glfw.DEPTH_BITS, 24)

        self._window = glfw.create_window(size[0], size[1], title, None, None)
        if not self._window:
            glfw.terminate()
            error("Failed to create GLFW window")

        glfw.make_context_current(self._window)
        glfw.set_window_size_callback(self._window, self.resize)


    @property
    def size(self) -> tuple[int, int]:
        return glfw.get_window_size(self._window)

    def resize(self, window, width, height):
        self._resize()

    @size.setter
    def size(self, new: tuple[int, int]):
        glfw.set_window_size(self._window, new[0], new[1])

    @property
    def position(self) -> tuple[int, int]:
        return glfw.get_window_pos(self._window)

    @position.setter
    def position(self, new: tuple[int, int]):
        glfw.set_window_pos(self._window, new[0], new[1])

    def is_ready(self) -> bool:
        return not glfw.window_should_close(self._window)

    def _get_key_down(self, key: Key):
        return 0.0 if glfw.get_key(self._window, GLFW_CHARACTER_MAP[key]) == glfw.RELEASE else 1.0

    def _get_gamepad_state(self, gamepad: int):
        pass

    def _create_cursor(self, image: 'Image'):
        pass

    def _set_cursor(self, cursor: 'Cursor'):
        pass

    def close(self):
        glfw.set_window_should_close(self._window, True)
        glfw.destroy_window(self._window)
        glfw.terminate()

    def draw(self):
        glfw.swap_buffers(self._window)

    def update(self):
        glfw.poll_events()
        if glfw.window_should_close(self._window):
            
            self.main.quit()
