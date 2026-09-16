from FreeBodyEngine.core.window import Window, Cursor, WINDOW_RESIZE, FRAMEBUFFER_RESIZE
from FreeBodyEngine.core.mouse import Mouse
from FreeBodyEngine.utils import abstractmethod
from typing import TYPE_CHECKING, Optional
from FreeBodyEngine.core.input import Key, KeyCallbackType, GamepadButton, GamepadAxis
from FreeBodyEngine.math import Vector
from FreeBodyEngine.core.camera import Camera
from FreeBodyEngine import emit_event
from FreeBodyEngine import get_flag, DEVMODE, QUIT, error, get_main, get_service, get_time
import numpy
import os
import mmap
import ctypes
import cffi
import select

from evdev import InputDevice, list_devices, ecodes

from pywayland.client import Display
from pywayland.protocol.wayland import (
    WlCompositor,
    WlSeat,
    WlKeyboard,
    WlPointer,
    WlSurface,
)

try:
    from pywayland.protocol.xdg_shell import XdgWmBase, XdgSurface, XdgToplevel
except ImportError as e:
    raise ImportError(
        "xdg_shell protocol is not available in your pywayland install. ") from e

import xkbcommon.xkb as xkb

if TYPE_CHECKING:
    from FreeBodyEngine.core.main import Main
    from FreeBodyEngine.graphics.image import Image


# ---------------------------------------------------------------------------
# Key translation: xkbcommon keysym -> engine Key
#
# Unlike GLFW (which hands you a platform-independent virtual keycode
# directly), Wayland only gives you a raw evdev scancode. You have to run
# that scancode through the keymap the compositor gave you (via xkbcommon)
# to get an actual keysym, and *that's* what you match against layout-aware
# keys like letters/punctuation.
#
# Different builds of the `xkbcommon` Python binding expose keysym values
# differently - some have a flat `xkb.keysym.XKB_KEY_*` constant namespace,
# others don't expose keysym constants as Python attributes at all. The one
# thing every build has (it's a 1:1 wrap of libxkbcommon's own
# xkb_keysym_from_name()) is a name-based lookup function, so the table below
# is built from the standard X11 keysym *names* and resolved to integers
# at import time via that function instead of hardcoded constants.
# ---------------------------------------------------------------------------
def _resolve_keysym_from_name(name: str):
    """
    Look up a keysym by its standard X11 name (e.g. "a", "F1", "Return"),
    trying whichever function name this xkbcommon binding actually exposes.
    """
    for candidate in ("keysym_from_name", "Keysym_from_name", "xkb_keysym_from_name"):
        fn = getattr(xkb, candidate, None)
        if fn is not None:
            result = fn(name)
            return int(result) if result else None
    # last resort: some bindings put it on a Keysym class instead of the module
    keysym_cls = getattr(xkb, "Keysym", None)
    if keysym_cls is not None and hasattr(keysym_cls, "from_name"):
        result = keysym_cls.from_name(name)
        return int(result) if result else None
    raise AttributeError(
        "Could not find a keysym-from-name function on xkbcommon.xkb.")


_KEY_TO_KEYSYM_NAME = {
    Key.A: "a", Key.B: "b", Key.C: "c", Key.D: "d", Key.E: "e", Key.F: "f",
    Key.G: "g", Key.H: "h", Key.I: "i", Key.J: "j", Key.K: "k", Key.L: "l",
    Key.M: "m", Key.N: "n", Key.O: "o", Key.P: "p", Key.Q: "q", Key.R: "r",
    Key.S: "s", Key.T: "t", Key.U: "u", Key.V: "v", Key.W: "w", Key.X: "x",
    Key.Y: "y", Key.Z: "z",

    Key.ONE: "1", Key.TWO: "2", Key.THREE: "3", Key.FOUR: "4", Key.FIVE: "5",
    Key.SIX: "6", Key.SEVEN: "7", Key.EIGHT: "8", Key.NINE: "9", Key.ZERO: "0",

    Key.MINUS: "minus", Key.EQUAL: "equal",
    Key.LEFT_BRACKET: "bracketleft", Key.RIGHT_BRACKET: "bracketright",
    Key.BACKSLASH: "backslash", Key.SEMICOLON: "semicolon",
    Key.APOSTROPHE: "apostrophe", Key.TILDE: "grave",
    Key.COMMA: "comma", Key.PERIOD: "period", Key.SLASH: "slash",

    Key.SPACE: "space", Key.RETURN: "Return", Key.BACKSPACE: "BackSpace",
    Key.TAB: "Tab", Key.ESCAPE: "Escape", Key.CAPS_LOCK: "Caps_Lock",

    Key.L_CTRL: "Control_L", Key.R_CTRL: "Control_R",
    Key.L_SHIFT: "Shift_L", Key.R_SHIFT: "Shift_R",
    Key.L_ALT: "Alt_L", Key.R_ALT: "Alt_R",
    Key.L_SUPER: "Super_L", Key.R_SUPER: "Super_R",

    Key.INSERT: "Insert", Key.DELETE: "Delete",
    Key.HOME: "Home", Key.END: "End",
    Key.PG_UP: "Page_Up", Key.PG_DOWN: "Page_Down",
    Key.UP: "Up", Key.DOWN: "Down", Key.LEFT: "Left", Key.RIGHT: "Right",

    Key.F1: "F1", Key.F2: "F2", Key.F3: "F3", Key.F4: "F4", Key.F5: "F5", Key.F6: "F6",
    Key.F7: "F7", Key.F8: "F8", Key.F9: "F9", Key.F10: "F10", Key.F11: "F11", Key.F12: "F12",
    Key.F13: "F13", Key.F14: "F14", Key.F15: "F15", Key.F16: "F16", Key.F17: "F17", Key.F18: "F18",
    Key.F19: "F19", Key.F20: "F20", Key.F21: "F21", Key.F22: "F22", Key.F23: "F23", Key.F24: "F24",

    Key.NUMPAD_0: "KP_0", Key.NUMPAD_1: "KP_1", Key.NUMPAD_2: "KP_2", Key.NUMPAD_3: "KP_3",
    Key.NUMPAD_4: "KP_4", Key.NUMPAD_5: "KP_5", Key.NUMPAD_6: "KP_6", Key.NUMPAD_7: "KP_7",
    Key.NUMPAD_8: "KP_8", Key.NUMPAD_9: "KP_9", Key.NUMPAD_DECIMAL: "KP_Decimal",
    Key.NUMPAD_DIVIDE: "KP_Divide", Key.NUMPAD_MULTIPLY: "KP_Multiply",
    Key.NUMPAD_SUBTRACT: "KP_Subtract", Key.NUMPAD_ADD: "KP_Add", Key.NUMPAD_ENTER: "KP_Enter",
}

XKB_KEYSYM_TO_KEY = {}
for _key, _name in _KEY_TO_KEYSYM_NAME.items():
    _ks = _resolve_keysym_from_name(_name)
    if _ks is not None:
        XKB_KEYSYM_TO_KEY[_ks] = _key

# ---------------------------------------------------------------------------
# cffi -> ctypes pointer bridge
#
# pywayland is built on cffi, so every pointer it hands back (e.g.
# `some_proxy._ptr`) is a `_cffi_backend` CData object. PyOpenGL's EGL/GLX
# bindings are ctypes-based and have no idea what a CData object is - passing
# one straight into e.g. EGL.eglGetDisplay() raises:
#   TypeError: '_cffi_backend.__CDataGCP' object cannot be interpreted as
#   ctypes.c_void_p
#
# The fix is just reading the pointer's numeric address out via cffi and
# handing that address to ctypes instead. A throwaway FFI() instance works
# fine for this - casting a pointer to an integer type doesn't require the
# same FFI instance that created it, since it's just reinterpreting the raw
# address.
# ---------------------------------------------------------------------------
_cffi_bridge = cffi.FFI()


def _cdata_to_voidp(cdata) -> ctypes.c_void_p:
    if cdata is None:
        return ctypes.c_void_p(0)
    address = int(_cffi_bridge.cast("uintptr_t", cdata))
    return ctypes.c_void_p(address)


def _find_native_ptr(obj, attr_candidates: tuple):
    """
    pywayland's internal attribute name for "the raw pointer under this
    wrapper object" isn't guaranteed stable across versions - try the known
    candidates and fail loudly with how to find the right one otherwise.
    """
    for name in attr_candidates:
        if hasattr(obj, name):
            return getattr(obj, name)
    raise AttributeError(
        f"Could not find a native pointer attribute on {obj!r} (tried "
        f"{attr_candidates}). Run: python3 -c \"import pprint; "
        f"pprint.pprint(vars({obj.__class__.__module__}.{obj.__class__.__name__}))\" "
        "or `print(vars(obj))` on the live object, find the cffi CData "
        "attribute, and add its name to attr_candidates."
    )


# evdev BTN_* codes for mouse buttons 0-7, same slots as the GLFW backend's
# glfw_mouse_button_map so WaylandMouse lines up with GLFWMouse index-for-index.
LINUX_BTN_CODES = {
    0: 0x110,  # BTN_LEFT
    1: 0x111,  # BTN_RIGHT
    2: 0x112,  # BTN_MIDDLE
    3: 0x113,  # BTN_SIDE
    4: 0x114,  # BTN_EXTRA
    5: 0x115,  # BTN_FORWARD
    6: 0x116,  # BTN_BACK
    7: 0x117,  # BTN_TASK
}
BTN_CODE_TO_INDEX = {v: k for k, v in LINUX_BTN_CODES.items()}


class WaylandWindow(Window):
    """Native Wayland window backend (xdg-shell), talking to the compositor directly rather than through GLFW.

    Contains no graphics API code - EGL/OpenGL stays in the renderer, which
    uses `native_display`/`native_surface` below. Input is entirely
    event-driven (pointer/keyboard from the Wayland seat, gamepads read
    separately via evdev), unlike GLFW's poll-based `get_key`/`get_cursor_pos`.
    """
    def __init__(self, size: tuple[int, int], title: str):
        """Connects to the Wayland display, binds the required globals, and creates an xdg-shell toplevel surface.

        Blocks until the compositor sends its first configure event, so a
        real size is known before this constructor returns control to the
        engine.
        """
        super().__init__(size, title)
        self.window_type = 'wayland'

        self._should_close = False
        self._pending_size = size
        self._configured = False
        self._scale = 1
        self._keys_down = {}

        self._compositor: Optional[WlCompositor] = None
        self._wm_base: Optional[XdgWmBase] = None
        self._seat: Optional[WlSeat] = None
        self._wl_pointer: Optional[WlPointer] = None
        self._wl_keyboard: Optional[WlKeyboard] = None

        self._xkb_context = xkb.Context()
        self._xkb_keymap = None
        self._xkb_state = None

        self.mouse: Optional['WaylandMouse'] = None

        self._gamepads = {}

        self._display = Display()
        self._display.connect()

        registry = self._display.get_registry()
        registry.dispatcher["global"] = self._on_registry_global
        registry.dispatcher["global_remove"] = lambda *_: None
        self._display.roundtrip()  # collect globals

        if self._compositor is None or self._wm_base is None:
            error("Wayland compositor is missing wl_compositor or xdg_wm_base")

        self._surface: WlSurface = self._compositor.create_surface()

        self._xdg_surface: XdgSurface = self._wm_base.get_xdg_surface(self._surface)
        self._xdg_surface.dispatcher["configure"] = self._on_xdg_surface_configure

        self._xdg_toplevel: XdgToplevel = self._xdg_surface.get_toplevel()
        self._xdg_toplevel.set_title(title)
        self._xdg_toplevel.set_app_id("FreeBodyEngine")
        self._xdg_toplevel.dispatcher["configure"] = self._on_toplevel_configure
        self._xdg_toplevel.dispatcher["close"] = self._on_toplevel_close

        self._surface.commit()
        # Block until the compositor sends the first configure so we have a
        # real size before returning control to the engine.
        while not self._configured:
            self._display.dispatch(block=True)

        self._discover_gamepads()

    # -- global binding ----------------------------------------------------

    def _on_registry_global(self, registry, id_, interface, version):
        if interface == "wl_compositor":
            self._compositor = registry.bind(id_, WlCompositor, min(version, 4))
        elif interface == "xdg_wm_base":
            self._wm_base = registry.bind(id_, XdgWmBase, min(version, 1))
            self._wm_base.dispatcher["ping"] = lambda wm, serial: wm.pong(serial)
        elif interface == "wl_seat":
            self._seat = registry.bind(id_, WlSeat, min(version, 5))
            self._seat.dispatcher["capabilities"] = self._on_seat_capabilities

    def _on_seat_capabilities(self, seat, capabilities):
        has_pointer = bool(capabilities & WlSeat.capability.pointer.value)
        has_keyboard = bool(capabilities & WlSeat.capability.keyboard.value)

        if has_pointer and self._wl_pointer is None:
            self._wl_pointer = seat.get_pointer()
            self._wl_pointer.dispatcher["enter"] = self._on_pointer_enter
            self._wl_pointer.dispatcher["leave"] = lambda *_: None
            self._wl_pointer.dispatcher["motion"] = self._on_pointer_motion
            self._wl_pointer.dispatcher["button"] = self._on_pointer_button
            self._wl_pointer.dispatcher["axis"] = self._on_pointer_axis

        if has_keyboard and self._wl_keyboard is None:
            self._wl_keyboard = seat.get_keyboard()
            self._wl_keyboard.dispatcher["keymap"] = self._on_keyboard_keymap
            self._wl_keyboard.dispatcher["key"] = self._on_keyboard_key
            self._wl_keyboard.dispatcher["modifiers"] = self._on_keyboard_modifiers
            self._wl_keyboard.dispatcher["enter"] = lambda *_: None
            self._wl_keyboard.dispatcher["leave"] = lambda *_: None

    # -- xdg-shell -----------------------------------------------------------

    def _on_xdg_surface_configure(self, xdg_surface, serial):
        xdg_surface.ack_configure(serial)
        self._surface.commit()
        if not self._configured:
            self._configured = True

    def _on_toplevel_configure(self, toplevel, width, height, states):
        # width/height == 0 means "you decide" - keep whatever we currently have.
        # This fires on every compositor-driven resize (e.g. the user dragging
        # an edge), so it has to go through the same resize() path as the
        # size setter does - otherwise WINDOW_RESIZE/FRAMEBUFFER_RESIZE never
        # fire for drag-resizes, only for programmatic `window.size = ...`.
        if width > 0 and height > 0 and (width, height) != self._pending_size:
            self.resize(None, width, height)

    def _on_toplevel_close(self, toplevel):
        self._should_close = True

    # -- pointer --------------------------------------------------------------

    def _on_pointer_enter(self, pointer, serial, surface, surface_x, surface_y):
        if self.mouse is not None:
            self.mouse._set_position(surface_x, surface_y)

    def _on_pointer_motion(self, pointer, time, surface_x, surface_y):
        if self.mouse is not None:
            self.mouse._set_position(surface_x, surface_y)

    def _on_pointer_button(self, pointer, serial, time, button, state):
        index = BTN_CODE_TO_INDEX.get(button)
        if index is None or self.mouse is None:
            return
        pressed = state == WlPointer.button_state.pressed.value
        self.mouse._on_button(index, pressed, time)

    def _on_pointer_axis(self, pointer, time, axis, value):
        # value is in "wl fixed" units already converted to float by
        # pywayland - roughly 10.0 per traditional wheel notch (matching
        # libinput's default), so this is scaled down to land in the same
        # "about 1.0 per notch" range GLFW's scroll callback reports, and
        # the sign is flipped for vertical so scrolling down (positive
        # wl_pointer value) moves content up, matching every other scroll
        # convention (terminals, browsers, waybar's own scroll bindings).
        if self.mouse is None:
            return
        delta = value / 10.0
        if axis == WlPointer.axis.vertical_scroll.value:
            self.mouse._on_axis(0, -delta)
        elif axis == WlPointer.axis.horizontal_scroll.value:
            self.mouse._on_axis(delta, 0)

    # -- keyboard ---------------------------------------------------------

    def _on_keyboard_keymap(self, keyboard, format_, fd, size):
        try:
            data = mmap.mmap(fd, size, prot=mmap.PROT_READ)
            keymap_string = data.read(size).decode("utf-8").rstrip("\x00")
            data.close()
        finally:
            os.close(fd)

        self._xkb_keymap = self._xkb_context.keymap_new_from_string(keymap_string)
        self._xkb_state = self._xkb_keymap.state_new()

    def _on_keyboard_modifiers(self, keyboard, serial, mods_depressed, mods_latched, mods_locked, group):
        if self._xkb_state is not None:
            self._xkb_state.update_mask(mods_depressed, mods_latched, mods_locked, 0, 0, group)

    def _on_keyboard_key(self, keyboard, serial, time, key, state):
        if self._xkb_state is None:
            return
        # evdev keycodes are offset by 8 from the xkb keycode space.
        xkb_keycode = key + 8
        keysym = self._xkb_state.key_get_one_sym(xkb_keycode)
        engine_key = XKB_KEYSYM_TO_KEY.get(keysym)
        if engine_key is None:
            return

        if state == WlKeyboard.key_state.pressed.value:
            key_type = KeyCallbackType.PRESS
            self._keys_down[engine_key] = True
        elif state == WlKeyboard.key_state.released.value:
            key_type = KeyCallbackType.RELEASE
            self._keys_down[engine_key] = False
        else:
            key_type = KeyCallbackType.REPEAT

        get_service('input')._key_callback(engine_key, key_type)

    # -- gamepad ----------------------------------------------------------

    def _discover_gamepads(self):
        for path in list_devices():
            try:
                device = InputDevice(path)
            except OSError:
                continue

            capabilities = device.capabilities()

            if ecodes.EV_ABS not in capabilities or ecodes.EV_KEY not in capabilities:
                device.close()
                continue

            abs_codes = {code for code, _ in capabilities[ecodes.EV_ABS]}

            if ecodes.ABS_X not in abs_codes or ecodes.ABS_Y not in abs_codes:
                device.close()
                continue

            gamepad_id = len(self._gamepads)

            self._gamepads[gamepad_id] = {
                "device": device,
                "buttons": {},
                "axes": {},
            }

    def _update_gamepads(self):
        for gamepad in self._gamepads.values():
            device = gamepad["device"]

            while True:
                ready, _, _ = select.select([device.fd], [], [], 0)

                if not ready:
                    break

                try:
                    event = device.read_one()
                except OSError:
                    break

                if event is None:
                    break

                if event.type == ecodes.EV_KEY:
                    gamepad["buttons"][event.code] = float(event.value)

                elif event.type == ecodes.EV_ABS:
                    gamepad["axes"][event.code] = event.value

    def _normalize_axis(self, device, code, value):
        info = device.absinfo(code)

        if info is None:
            return 0.0

        minimum = info.min
        maximum = info.max

        if maximum == minimum:
            return 0.0

        value = (value - minimum) / (maximum - minimum)
        return max(-1.0, min(1.0, value * 2.0 - 1.0))

    def _normalize_trigger(self, device, code, value):
        info = device.absinfo(code)

        if info is None:
            return 0.0

        minimum = info.min
        maximum = info.max

        if maximum == minimum:
            return 0.0

        return max(0.0, min(1.0, (value - minimum) / (maximum - minimum)))

    def _get_gamepad_state(self, gamepad: int):
        self._update_gamepads()

        if gamepad not in self._gamepads:
            return {
                button: 0.0 for button in GamepadButton
            } | {
                axis: 0.0 for axis in GamepadAxis
            }

        device = self._gamepads[gamepad]["device"]
        buttons = self._gamepads[gamepad]["buttons"]
        axes = self._gamepads[gamepad]["axes"]

        state = {
            button: 0.0 for button in GamepadButton
        }

        state.update({
            axis: 0.0 for axis in GamepadAxis
        })

        button_map = {
            GamepadButton.A: ecodes.BTN_SOUTH,
            GamepadButton.B: ecodes.BTN_EAST,
            GamepadButton.X: ecodes.BTN_NORTH,
            GamepadButton.Y: ecodes.BTN_WEST,
            GamepadButton.LB: ecodes.BTN_TL,
            GamepadButton.RB: ecodes.BTN_TR,
            GamepadButton.LS_DOWN: ecodes.BTN_THUMBL,
            GamepadButton.RS_DOWN: ecodes.BTN_THUMBR,
            GamepadButton.GUIDE: ecodes.BTN_MODE,
        }

        for button, code in button_map.items():
            state[button] = buttons.get(code, 0.0)

        dpad_x = axes.get(ecodes.ABS_HAT0X, 0)
        dpad_y = axes.get(ecodes.ABS_HAT0Y, 0)

        state[GamepadButton.DPAD_LEFT] = 1.0 if dpad_x < 0 else 0.0
        state[GamepadButton.DPAD_RIGHT] = 1.0 if dpad_x > 0 else 0.0
        state[GamepadButton.DPAD_UP] = 1.0 if dpad_y < 0 else 0.0
        state[GamepadButton.DPAD_DOWN] = 1.0 if dpad_y > 0 else 0.0

        axis_map = {
            GamepadAxis.LEFT_X: ecodes.ABS_X,
            GamepadAxis.LEFT_Y: ecodes.ABS_Y,
            GamepadAxis.RIGHT_X: ecodes.ABS_RX,
            GamepadAxis.RIGHT_Y: ecodes.ABS_RY,
        }

        for axis, code in axis_map.items():
            if code in axes:
                state[axis] = self._normalize_axis(
                    device,
                    code,
                    axes[code]
                )

        if ecodes.ABS_Z in axes:
            state[GamepadAxis.LEFT_TRIGGER] = self._normalize_trigger(
                device,
                ecodes.ABS_Z,
                axes[ecodes.ABS_Z]
            )
        elif ecodes.BTN_TL2 in buttons:
            state[GamepadAxis.LEFT_TRIGGER] = buttons[ecodes.BTN_TL2]

        if ecodes.ABS_RZ in axes:
            state[GamepadAxis.RIGHT_TRIGGER] = self._normalize_trigger(
                device,
                ecodes.ABS_RZ,
                axes[ecodes.ABS_RZ]
            )
        elif ecodes.BTN_TR2 in buttons:
            state[GamepadAxis.RIGHT_TRIGGER] = buttons[ecodes.BTN_TR2]

        return state

    # -- Window interface ---------------------------------------------------

    def set_title(self, new_title):
        """Sets the xdg-shell toplevel's title."""
        self._xdg_toplevel.set_title(new_title)

    @property
    def native_display(self):
        """
        wl_display* as a ctypes.c_void_p, for handing to EGL / Vulkan / etc.
        (bridged from pywayland's cffi pointer - see _cdata_to_voidp above)
        """
        raw = _find_native_ptr(self._display, ("_ptr", "_display", "_display_ptr"))
        return _cdata_to_voidp(raw)

    @property
    def native_surface(self):
        """
        wl_surface* as a ctypes.c_void_p, for handing to EGL / Vulkan / etc.
        (bridged from pywayland's cffi pointer - see _cdata_to_voidp above)
        """
        raw = _find_native_ptr(self._surface, ("_ptr",))
        return _cdata_to_voidp(raw)

    @property
    def size(self) -> tuple[int, int]:
        """The window's last known (requested or compositor-configured) size, in pixels."""
        return self._pending_size

    @size.setter
    def size(self, new: tuple[int, int]):
        """Requests a resize to `new` (width, height), in pixels, via resize()."""
        # There is no protocol request to force a toplevel to a given size;
        # we can only pick one ourselves and let resize() below tell the
        # compositor about it (geometry included) and fire local callbacks.
        # A real resize (e.g. the user dragging an edge) instead arrives
        # through _on_toplevel_configure, which also goes through resize().
        if new != self._pending_size:
            self.resize(None, new[0], new[1])

    @property
    def framebuffer_size(self) -> tuple[int, int]:
        """The window size scaled by the output's buffer scale factor."""
        w, h = self._pending_size
        return (w * self._scale, h * self._scale)

    @property
    def position(self) -> tuple[int, int]:
        """Always (0, 0) - the Wayland protocol does not expose a client window's position on screen."""
        # Wayland does not expose or allow setting client window position.
        return (0, 0)

    @position.setter
    def position(self, new: tuple[int, int]):
        """No-op - positioning a client window is not supported by the Wayland windowing model."""
        pass  # not supported by the Wayland windowing model

    def resize(self, window, width, height):
        """Records the new size, updates the surface's window geometry, and fires WINDOW_RESIZE/FRAMEBUFFER_RESIZE.

        The single path both the size setter and compositor-driven resizes
        (_on_toplevel_configure) go through, so local state and the events
        the rest of the engine listens for stay consistent either way.
        """
        self._pending_size = (width, height)
        # Has to be updated on every resize, not just programmatic ones -
        # otherwise the compositor keeps clipping/presenting the surface at
        # whatever rectangle was last set here, even once the buffer
        # underneath has actually grown/shrunk to the new size.
        self._xdg_surface.set_window_geometry(0, 0, width, height)
        emit_event(WINDOW_RESIZE, (width, height))
        emit_event(FRAMEBUFFER_RESIZE, self.framebuffer_size)

    def is_ready(self) -> bool:
        """True until the compositor or user has requested this window close."""
        return not self._should_close

    def _get_key_down(self, key: Key):
        # There's no "query current key state" call in the Wayland protocol
        # like glfw.get_key() - state has to be tracked from the press/
        # release events we already get in _on_keyboard_key.
        return self._keys_down.get(key, False)

    def _create_cursor(self, image: 'Image'):
        pass  # TODO: wl_cursor / wp_cursor_shape support

    def _set_cursor(self, cursor: 'Cursor'):
        pass  # TODO: wl_pointer.set_cursor with a wl_buffer from wl_cursor

    def create_mouse(self):
        """Creates this window's WaylandMouse and stores it so pointer callbacks (e.g. _on_pointer_motion) can reach it."""
        self.mouse = WaylandMouse(self)
        return self.mouse

    def close(self):
        """Flags the window to close, closes any open gamepad devices, destroys the xdg-shell surfaces, and disconnects."""
        self._should_close = True

        for gamepad in self._gamepads.values():
            try:
                gamepad["device"].close()
            except OSError:
                pass

        self._xdg_toplevel.destroy()
        self._xdg_surface.destroy()
        self._surface.destroy()
        self._display.disconnect()
        emit_event(QUIT)

    def draw(self):
        """Asks the renderer to swap buffers, presenting the frame."""
        renderer = get_service('renderer')
        if renderer != None:
            renderer.swap_buffers()

    def update(self):
        """Flushes and dispatches pending Wayland events (non-blocking), polls gamepads, and quits once closed."""

        self._display.flush()
        self._display.dispatch(block=False)
        self._update_gamepads()

        if self._should_close:
            get_main().quit()


class WaylandMouse(Mouse):
    """
    Unlike GLFWMouse, this doesn't poll button/position state each frame -
    Wayland only tells you about input via events. WaylandWindow's pointer
    callbacks push updates into this class as they arrive; update() just
    turns those into the same one-frame pressed/released latch shape that
    the rest of the engine expects from GLFWMouse.
    """

    def __init__(self, window: WaylandWindow):
        """Sets up per-button event/state tracking for `window`; positions start at the origin until a pointer-enter/motion event arrives."""
        super().__init__()
        self.window = window
        self._down = [False] * 8
        self._pressed_events = [False] * 8
        self._released_events = [False] * 8
        self._pressed = [False] * 8
        self._released = [False] * 8
        self._double_clicked = [False] * 8
        self._dragging = [False] * 8
        self.last_click_time = -500
        self.drag_threshold = 0.2
        self.position = Vector(0, 0)
        self.world_position = Vector(0, 0)
        self._scroll_accum = Vector(0, 0)
        self.scroll_delta = Vector(0, 0)

    def _set_position(self, x: float, y: float):
        self.position = Vector(x, y)

    def _on_axis(self, dx: float, dy: float):
        self._scroll_accum += Vector(dx, dy)

    def get_scroll_delta(self) -> Vector:
        """How far the scroll wheel moved this frame - see `_on_pointer_axis`."""
        return self.scroll_delta

    def _on_button(self, index: int, pressed: bool, time: int):
        if pressed:
            self._down[index] = True
            self._pressed_events[index] = True
            t = get_time()
            time_dif = t - self.last_click_time
            if time_dif <= self.double_click_threshold:
                self._double_clicked[index] = True
            self.last_click_time = t
        else:
            self._down[index] = False
            self._released_events[index] = True

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
        """Latches this frame's pressed/released events (set by pointer callbacks) and updates world-space position."""
        # Latch this frame's edge events, then clear them for the next one -
        # same externally-visible behaviour as GLFWMouse's per-frame reset.
        self._pressed = self._pressed_events
        self._released = self._released_events
        self._pressed_events = [False] * 8
        self._released_events = [False] * 8

        self.scroll_delta = self._scroll_accum
        self._scroll_accum = Vector(0, 0)

        scene = get_service('scene_manager').get_active()

        self.world_position = self.position
        if scene is not None:
            cam: Camera = scene.camera
            if cam is not None:
                win_size = self.window.size
                ndc_x = (self.position.x / win_size[0]) * 2.0 - 1.0
                ndc_y = (self.position.y / win_size[1]) * 2.0 - 1.0
                clip_pos = (ndc_x, ndc_y, 0.0, 1.0)

                proj_view_inverse = numpy.linalg.inv(cam.proj_matrix @ cam._get_view_mat())
                p = proj_view_inverse @ clip_pos
                p /= p[3]
                self.world_position = Vector(p[0], p[1])

        self._double_clicked = [False] * 8
