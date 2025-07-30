"""A headless window using SDL."""

import os
import sys
from pathlib import Path

from FreeBodyEngine.core.window import Window, Cursor
from FreeBodyEngine.utils import abstractmethod
from typing import TYPE_CHECKING
from FreeBodyEngine import error, DLL_DIRECTORY
from FreeBodyEngine.core.dummy.mouse import DummyMouse
from FreeBodyEngine.core.input import Key


if TYPE_CHECKING:
    from FreeBodyEngine.core.main import Main
    from FreeBodyEngine.graphics.image import Image

os.environ["PYSDL2_DLL_PATH"] = str(DLL_DIRECTORY)

import sdl2
import sdl2.ext


SDL_KEY_MAP = {
    Key.A: sdl2.SDLK_a,
    Key.B: sdl2.SDLK_b,
    Key.C: sdl2.SDLK_c,
    Key.D: sdl2.SDLK_d,
    Key.E: sdl2.SDLK_e,
    Key.F: sdl2.SDLK_f,
    Key.G: sdl2.SDLK_g,
    Key.H: sdl2.SDLK_h,
    Key.I: sdl2.SDLK_i,
    Key.J: sdl2.SDLK_j,
    Key.K: sdl2.SDLK_k,
    Key.L: sdl2.SDLK_l,
    Key.M: sdl2.SDLK_m,
    Key.N: sdl2.SDLK_n,
    Key.O: sdl2.SDLK_o,
    Key.P: sdl2.SDLK_p,
    Key.Q: sdl2.SDLK_q,
    Key.R: sdl2.SDLK_r,
    Key.S: sdl2.SDLK_s,
    Key.T: sdl2.SDLK_t,
    Key.U: sdl2.SDLK_u,
    Key.V: sdl2.SDLK_v,
    Key.W: sdl2.SDLK_w,
    Key.X: sdl2.SDLK_x,
    Key.Y: sdl2.SDLK_y,
    Key.Z: sdl2.SDLK_z,

    Key.ZERO: sdl2.SDLK_0,
    Key.ONE: sdl2.SDLK_1,
    Key.TWO: sdl2.SDLK_2,
    Key.THREE: sdl2.SDLK_3,
    Key.FOUR: sdl2.SDLK_4,
    Key.FIVE: sdl2.SDLK_5,
    Key.SIX: sdl2.SDLK_6,
    Key.SEVEN: sdl2.SDLK_7,
    Key.EIGHT: sdl2.SDLK_8,
    Key.NINE: sdl2.SDLK_9,

    Key.MINUS: sdl2.SDLK_MINUS,
    Key.EQUAL: sdl2.SDLK_EQUALS,
    Key.LEFT_BRACKET: sdl2.SDLK_LEFTBRACKET,
    Key.RIGHT_BRACKET: sdl2.SDLK_RIGHTBRACKET,
    Key.BACKSLASH: sdl2.SDLK_BACKSLASH,
    Key.SEMICOLON: sdl2.SDLK_SEMICOLON,
    Key.APOSTROPHE: sdl2.SDLK_QUOTE,
    Key.TILDE: sdl2.SDLK_BACKQUOTE,
    Key.COMMA: sdl2.SDLK_COMMA,
    Key.PERIOD: sdl2.SDLK_PERIOD,
    Key.SLASH: sdl2.SDLK_SLASH,

    Key.SPACE: sdl2.SDLK_SPACE,
    Key.RETURN: sdl2.SDLK_RETURN,
    Key.BACKSPACE: sdl2.SDLK_BACKSPACE,
    Key.TAB: sdl2.SDLK_TAB,
    Key.ESCAPE: sdl2.SDLK_ESCAPE,
    Key.CAPS_LOCK: sdl2.SDLK_CAPSLOCK,

    Key.L_CTRL: sdl2.SDLK_LCTRL,
    Key.R_CTRL: sdl2.SDLK_RCTRL,
    Key.L_SHIFT: sdl2.SDLK_LSHIFT,
    Key.R_SHIFT: sdl2.SDLK_RSHIFT,
    Key.L_ALT: sdl2.SDLK_LALT,
    Key.R_ALT: sdl2.SDLK_RALT,
    Key.L_SUPER: sdl2.SDLK_LGUI,
    Key.R_SUPER: sdl2.SDLK_RGUI,

    Key.INSERT: sdl2.SDLK_INSERT,
    Key.DELETE: sdl2.SDLK_DELETE,
    Key.HOME: sdl2.SDLK_HOME,
    Key.END: sdl2.SDLK_END,
    Key.PG_UP: sdl2.SDLK_PAGEUP,
    Key.PG_DOWN: sdl2.SDLK_PAGEDOWN,
    Key.UP: sdl2.SDLK_UP,
    Key.DOWN: sdl2.SDLK_DOWN,
    Key.LEFT: sdl2.SDLK_LEFT,
    Key.RIGHT: sdl2.SDLK_RIGHT,

    Key.F1: sdl2.SDLK_F1,
    Key.F2: sdl2.SDLK_F2,
    Key.F3: sdl2.SDLK_F3,
    Key.F4: sdl2.SDLK_F4,
    Key.F5: sdl2.SDLK_F5,
    Key.F6: sdl2.SDLK_F6,
    Key.F7: sdl2.SDLK_F7,
    Key.F8: sdl2.SDLK_F8,
    Key.F9: sdl2.SDLK_F9,
    Key.F10: sdl2.SDLK_F10,
    Key.F11: sdl2.SDLK_F11,
    Key.F12: sdl2.SDLK_F12,
    Key.F13: sdl2.SDLK_F13,
    Key.F14: sdl2.SDLK_F14,
    Key.F15: sdl2.SDLK_F15,
    Key.F16: sdl2.SDLK_F16,
    Key.F17: sdl2.SDLK_F17,
    Key.F18: sdl2.SDLK_F18,
    Key.F19: sdl2.SDLK_F19,
    Key.F20: sdl2.SDLK_F20,
    Key.F21: sdl2.SDLK_F21,
    Key.F22: sdl2.SDLK_F22,
    Key.F23: sdl2.SDLK_F23,
    Key.F24: sdl2.SDLK_F24,

    Key.NUMPAD_0: sdl2.SDLK_KP_0,
    Key.NUMPAD_1: sdl2.SDLK_KP_1,
    Key.NUMPAD_2: sdl2.SDLK_KP_2,
    Key.NUMPAD_3: sdl2.SDLK_KP_3,
    Key.NUMPAD_4: sdl2.SDLK_KP_4,
    Key.NUMPAD_5: sdl2.SDLK_KP_5,
    Key.NUMPAD_6: sdl2.SDLK_KP_6,
    Key.NUMPAD_7: sdl2.SDLK_KP_7,
    Key.NUMPAD_8: sdl2.SDLK_KP_8,
    Key.NUMPAD_9: sdl2.SDLK_KP_9,
    Key.NUMPAD_DECIMAL: sdl2.SDLK_KP_PERIOD,
    Key.NUMPAD_DIVIDE: sdl2.SDLK_KP_DIVIDE,
    Key.NUMPAD_MULTIPLY: sdl2.SDLK_KP_MULTIPLY,
    Key.NUMPAD_SUBTRACT: sdl2.SDLK_KP_MINUS,
    Key.NUMPAD_ADD: sdl2.SDLK_KP_PLUS,
    Key.NUMPAD_ENTER: sdl2.SDLK_KP_ENTER,
}



class HeadlessWindow(Window):
    def __init__(self, size: tuple[int, int], title="FreeBodyEngine"):
        super().__init__(size, title)
        self.window_type = 'headless'
        self._size = size
        self._title = title
        self._should_close = False

        os.environ["SDL_VIDEODRIVER"] = "dummy"

        if sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO | sdl2.SDL_INIT_GAMECONTROLLER) != 0:
            raise RuntimeError(f"SDL_Init failed: {sdl2.SDL_GetError().decode()}")

        self._window = sdl2.SDL_CreateWindow(
            title.encode(),
            sdl2.SDL_WINDOWPOS_UNDEFINED,
            sdl2.SDL_WINDOWPOS_UNDEFINED,
            size[0], size[1],
            sdl2.SDL_WINDOW_HIDDEN
        )

        if not self._window:
            sdl2.SDL_Quit()
            error("Failed to create SDL window")

    def create_mouse(self):
        return None

    def set_title(self, new_title):
        pass

    @property
    def size(self) -> tuple[int, int]:
        w = sdl2.c_int()
        h = sdl2.c_int()
        sdl2.SDL_GetWindowSize(self._window, w, h)
        return (w.value, h.value)

    @size.setter
    def size(self, new: tuple[int, int]):
        sdl2.SDL_SetWindowSize(self._window, new[0], new[1])

    @property
    def position(self) -> tuple[int, int]:
        x = sdl2.c_int()
        y = sdl2.c_int()
        sdl2.SDL_GetWindowPosition(self._window, x, y)
        return (x.value, y.value)

    @position.setter
    def position(self, new: tuple[int, int]):
        sdl2.SDL_SetWindowPosition(self._window, new[0], new[1])

    def is_ready(self) -> bool:
        return not self._should_close

    def _get_key_down(self, key: Key):
        state = sdl2.SDL_GetKeyboardState(None)
        scancode = sdl2.SDL_GetScancodeFromKey(SDL_KEY_MAP[key])
        return float(state[scancode])

    def _get_gamepad_state(self, gamepad: int):
        # use sdl2.SDL_GameController
        pass

    def _create_cursor(self, image: 'Image'):
        pass

    def _set_cursor(self, cursor: 'Cursor'):
        pass

    def close(self):
        self._should_close = True
        sdl2.SDL_DestroyWindow(self._window)
        sdl2.SDL_Quit()

    def draw(self):
        pass

    def update(self):
        events = sdl2.SDL_Event()
        while sdl2.SDL_PollEvent(events):
            if events.type == sdl2.SDL_QUIT:
                self.main.quit()

