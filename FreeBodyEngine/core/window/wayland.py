from FreeBodyEngine.core.window import Window, Cursor, WINDOW_RESIZE, FRAMEBUFFER_RESIZE
from FreeBodyEngine.core.mouse import Mouse
from FreeBodyEngine.utils import abstractmethod
from typing import TYPE_CHECKING, Optional
from FreeBodyEngine.core.input import Key, KeyCallbackType, GamepadButton, GamepadAxis
from FreeBodyEngine.math import Vector
from FreeBodyEngine.core.camera import Camera
from FreeBodyEngine import emit_event
from FreeBodyEngine import get_flag, DEVMODE, QUIT, error, get_main, get_service, get_time, warning
import numpy
import os
import mmap
import ctypes
import cffi
import select
import struct
import subprocess

from evdev import InputDevice, list_devices, ecodes

from pywayland.client import Display
from pywayland.protocol.wayland import (
    WlCompositor,
    WlSeat,
    WlKeyboard,
    WlPointer,
    WlSurface,
    WlDataDeviceManager,
)

try:
    from pywayland.protocol.xdg_shell import XdgWmBase, XdgSurface, XdgToplevel
except ImportError as e:
    raise ImportError(
        "xdg_shell protocol is not available in your pywayland install. ") from e

# cursor-shape-v1 is an optional (if very widely supported - every wlroots
# compositor, including Hyprland, has it) staging protocol, unlike
# xdg_shell above - so its absence degrades to "no named-cursor support"
# (see _set_cursor_shape's None-check on _cursor_shape_manager) rather than
# refusing to start.
try:
    from pywayland.protocol.cursor_shape_v1 import WpCursorShapeManagerV1, WpCursorShapeDeviceV1
except ImportError:
    WpCursorShapeManagerV1 = None
    WpCursorShapeDeviceV1 = None

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


#
# Values are a tuple of every keysym name that key can produce, not just
# one - xkb_state_key_get_one_sym() (see _on_keyboard_key) resolves the
# keysym for a keycode *at its current modifier state*, so holding Shift
# while pressing the "a" key produces the keysym for "A", a completely
# different integer from lowercase "a"'s. A lookup table built only from
# the unshifted name (as this one used to be) has no entry for that
# integer at all, so _on_keyboard_key's `XKB_KEYSYM_TO_KEY.get(keysym)`
# missed and silently dropped the whole key press - not just the
# character, the *event*, before it ever reached KEY_PRESS or manager.py's
# KEY_CHAR_MAP. That's the concrete shape of "text input only registers
# lowercase letters": every letter typed with Shift held, and every
# digit's shifted symbol (!@#$ etc.), hit exactly this gap. Mapping every
# shifted variant to the same engine Key here means Key.A means "the A
# key" regardless of which case was actually pressed, the same as GLFW's
# virtual keycodes already do - manager.py's own shift check (already
# correct) picks the actual character from there.
#
_KEY_TO_KEYSYM_NAMES = {
    Key.A: ("a", "A"), Key.B: ("b", "B"), Key.C: ("c", "C"), Key.D: ("d", "D"),
    Key.E: ("e", "E"), Key.F: ("f", "F"), Key.G: ("g", "G"), Key.H: ("h", "H"),
    Key.I: ("i", "I"), Key.J: ("j", "J"), Key.K: ("k", "K"), Key.L: ("l", "L"),
    Key.M: ("m", "M"), Key.N: ("n", "N"), Key.O: ("o", "O"), Key.P: ("p", "P"),
    Key.Q: ("q", "Q"), Key.R: ("r", "R"), Key.S: ("s", "S"), Key.T: ("t", "T"),
    Key.U: ("u", "U"), Key.V: ("v", "V"), Key.W: ("w", "W"), Key.X: ("x", "X"),
    Key.Y: ("y", "Y"), Key.Z: ("z", "Z"),

    Key.ONE: ("1", "exclam"), Key.TWO: ("2", "at"), Key.THREE: ("3", "numbersign"),
    Key.FOUR: ("4", "dollar"), Key.FIVE: ("5", "percent"), Key.SIX: ("6", "asciicircum"),
    Key.SEVEN: ("7", "ampersand"), Key.EIGHT: ("8", "asterisk"),
    Key.NINE: ("9", "parenleft"), Key.ZERO: ("0", "parenright"),

    Key.MINUS: ("minus", "underscore"), Key.EQUAL: ("equal", "plus"),
    Key.LEFT_BRACKET: ("bracketleft", "braceleft"), Key.RIGHT_BRACKET: ("bracketright", "braceright"),
    Key.BACKSLASH: ("backslash", "bar"), Key.SEMICOLON: ("semicolon", "colon"),
    Key.APOSTROPHE: ("apostrophe", "quotedbl"), Key.TILDE: ("grave", "asciitilde"),
    Key.COMMA: ("comma", "less"), Key.PERIOD: ("period", "greater"), Key.SLASH: ("slash", "question"),

    Key.SPACE: ("space",), Key.RETURN: ("Return",), Key.BACKSPACE: ("BackSpace",),
    Key.TAB: ("Tab",), Key.ESCAPE: ("Escape",), Key.CAPS_LOCK: ("Caps_Lock",),

    Key.L_CTRL: ("Control_L",), Key.R_CTRL: ("Control_R",),
    Key.L_SHIFT: ("Shift_L",), Key.R_SHIFT: ("Shift_R",),
    Key.L_ALT: ("Alt_L",), Key.R_ALT: ("Alt_R",),
    Key.L_SUPER: ("Super_L",), Key.R_SUPER: ("Super_R",),

    Key.INSERT: ("Insert",), Key.DELETE: ("Delete",),
    Key.HOME: ("Home",), Key.END: ("End",),
    Key.PG_UP: ("Page_Up",), Key.PG_DOWN: ("Page_Down",),
    Key.UP: ("Up",), Key.DOWN: ("Down",), Key.LEFT: ("Left",), Key.RIGHT: ("Right",),

    Key.F1: ("F1",), Key.F2: ("F2",), Key.F3: ("F3",), Key.F4: ("F4",), Key.F5: ("F5",), Key.F6: ("F6",),
    Key.F7: ("F7",), Key.F8: ("F8",), Key.F9: ("F9",), Key.F10: ("F10",), Key.F11: ("F11",), Key.F12: ("F12",),
    Key.F13: ("F13",), Key.F14: ("F14",), Key.F15: ("F15",), Key.F16: ("F16",), Key.F17: ("F17",), Key.F18: ("F18",),
    Key.F19: ("F19",), Key.F20: ("F20",), Key.F21: ("F21",), Key.F22: ("F22",), Key.F23: ("F23",), Key.F24: ("F24",),

    Key.NUMPAD_0: ("KP_0",), Key.NUMPAD_1: ("KP_1",), Key.NUMPAD_2: ("KP_2",), Key.NUMPAD_3: ("KP_3",),
    Key.NUMPAD_4: ("KP_4",), Key.NUMPAD_5: ("KP_5",), Key.NUMPAD_6: ("KP_6",), Key.NUMPAD_7: ("KP_7",),
    Key.NUMPAD_8: ("KP_8",), Key.NUMPAD_9: ("KP_9",), Key.NUMPAD_DECIMAL: ("KP_Decimal",),
    Key.NUMPAD_DIVIDE: ("KP_Divide",), Key.NUMPAD_MULTIPLY: ("KP_Multiply",),
    Key.NUMPAD_SUBTRACT: ("KP_Subtract",), Key.NUMPAD_ADD: ("KP_Add",), Key.NUMPAD_ENTER: ("KP_Enter",),
}

XKB_KEYSYM_TO_KEY = {}
for _key, _names in _KEY_TO_KEYSYM_NAMES.items():
    for _name in _names:
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
        self._suspended = False
        self._scale = 1
        self._keys_down = {}

        # Key repeat: unlike GLFW (which gets synthetic repeat events from
        # the OS/toolkit for free - see GLFW_KEY_CALLBACK_TYPE_MAP's
        # GLFW_REPEAT), the Wayland protocol only ever reports a real
        # press or release from wl_keyboard.key - repeat-while-held is
        # explicitly the client's own responsibility, timed against the
        # rate/delay the compositor reports via wl_keyboard.repeat_info
        # (see _on_keyboard_repeat_info). Without this, holding a key down
        # produced exactly one character, however long it was held -
        # every other engine input (movement keys included, not just text)
        # was silently missing repeat on this backend.
        self._repeat_rate = 25.0  # chars/sec - overwritten by the compositor's real repeat_info once it arrives
        self._repeat_delay_ms = 400.0
        self._repeat_keycode: Optional[int] = None
        self._repeat_key: Optional[Key] = None
        self._repeat_next_time = 0.0

        self._compositor: Optional[WlCompositor] = None
        self._wm_base: Optional[XdgWmBase] = None
        self._seat: Optional[WlSeat] = None
        self._wl_pointer: Optional[WlPointer] = None
        self._wl_keyboard: Optional[WlKeyboard] = None

        self._cursor_shape_manager: Optional['WpCursorShapeManagerV1'] = None
        self._cursor_shape_device: Optional['WpCursorShapeDeviceV1'] = None
        self._last_pointer_enter_serial: Optional[int] = None

        self._data_device_manager: Optional[WlDataDeviceManager] = None
        self._data_device = None
        self._clipboard_offer = None  # current WlDataOffer for the clipboard selection, or None
        self._pending_offers = []  # keeps not-yet-resolved offers alive - see _on_data_offer

        self._xkb_context = xkb.Context()
        self._xkb_keymap = None
        self._xkb_state = None

        self.mouse: Optional['WaylandMouse'] = None

        self._gamepads = {}

        self._display = Display()
        self._display.connect()

        # Stored on self rather than left as a local - pywayland tracks
        # live WlRegistry objects via a class-level weak registry
        # (WlRegistry.registry) and falls back to it to resolve *any*
        # later event carrying a "new_id" argument (needs somewhere to
        # look up the display to construct the new proxy against - see
        # protocol_core/message.py's c_to_arguments). A local-only
        # `registry` here would be garbage collected the moment __init__
        # returns, silently emptying that weak registry - which was never
        # a problem before because no event this backend previously
        # listened for ever carried a new_id argument, only requests like
        # registry.bind() (a different, send-side path). wl_data_device's
        # own "data_offer" event (see _ensure_data_device below) is the
        # first one that does, and was crashing with a raw "Cannot find
        # display" RuntimeError out of pywayland until this was kept alive.
        self._registry = self._display.get_registry()
        self._registry.dispatcher["global"] = self._on_registry_global
        self._registry.dispatcher["global_remove"] = lambda *_: None
        self._display.roundtrip()  # collect globals

        if self._compositor is None or self._wm_base is None:
            error("Wayland compositor is missing wl_compositor or xdg_wm_base")

        self._surface: WlSurface = self._compositor.create_surface()

        self._xdg_surface: XdgSurface = self._wm_base.get_xdg_surface(self._surface)
        self._xdg_surface.dispatcher["configure"] = self._on_xdg_surface_configure

        self._xdg_toplevel: XdgToplevel = self._xdg_surface.get_toplevel()
        self._xdg_toplevel.set_title(title)
        self._xdg_toplevel.set_app_id("FreeBodyEngine")
        # The size passed to a window is also its minimum - without this a
        # tiling compositor is free to shrink it to whatever fits its
        # layout (a few hundred px, easily), and nothing in the UI system
        # wraps or reflows content for a width it wasn't laid out for -
        # fixed-width elements (most buttons/fields, by design - see
        # ui/element.py's SIZE UNITS docs) just overflow past the window
        # edge instead. Compositors aren't required to honor this, but
        # every one of them attempts to.
        self._xdg_toplevel.set_min_size(size[0], size[1])
        self._xdg_toplevel.dispatcher["configure"] = self._on_toplevel_configure
        self._xdg_toplevel.dispatcher["close"] = self._on_toplevel_close

        self._update_opaque_region(size[0], size[1])
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
            # Bound as high as this pywayland install understands (up to
            # v7) rather than pinned to v1 - v6+ is what adds the
            # xdg_toplevel "suspended" state _on_toplevel_configure checks
            # for below, needed to stop rendering (and, critically, stop
            # blocking on eglSwapBuffers - see swap_wayland_opengl_buffers)
            # while this surface isn't actually being presented.
            self._wm_base = registry.bind(id_, XdgWmBase, min(version, XdgWmBase.version))
            self._wm_base.dispatcher["ping"] = lambda wm, serial: wm.pong(serial)
        elif interface == "wl_seat":
            self._seat = registry.bind(id_, WlSeat, min(version, 5))
            self._seat.dispatcher["capabilities"] = self._on_seat_capabilities
            self._ensure_data_device()
        elif interface == "wp_cursor_shape_manager_v1" and WpCursorShapeManagerV1 is not None:
            self._cursor_shape_manager = registry.bind(id_, WpCursorShapeManagerV1, min(version, 1))
        elif interface == "wl_data_device_manager":
            self._data_device_manager = registry.bind(id_, WlDataDeviceManager, min(version, WlDataDeviceManager.version))
            self._ensure_data_device()

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
            self._ensure_cursor_shape_device()

        if has_keyboard and self._wl_keyboard is None:
            self._wl_keyboard = seat.get_keyboard()
            self._wl_keyboard.dispatcher["keymap"] = self._on_keyboard_keymap
            self._wl_keyboard.dispatcher["key"] = self._on_keyboard_key
            self._wl_keyboard.dispatcher["modifiers"] = self._on_keyboard_modifiers
            self._wl_keyboard.dispatcher["repeat_info"] = self._on_keyboard_repeat_info
            self._wl_keyboard.dispatcher["enter"] = lambda *_: None
            self._wl_keyboard.dispatcher["leave"] = lambda *_: None

    # -- xdg-shell -----------------------------------------------------------

    def _update_opaque_region(self, width: int, height: int):
        """Tells the compositor to treat the whole surface as fully opaque,
        regardless of what alpha values this app actually draws into it.

        Without this, Wayland compositors composite a surface's real,
        rendered alpha channel against whatever's behind the window (the
        desktop wallpaper, other windows) - unlike X11, where a window is
        opaque by default unless a transparent visual is explicitly
        requested. Every color in this engine's UI system defaults to (or
        can be given) alpha < 1 for perfectly ordinary reasons that have
        nothing to do with the *window* being transparent - a plain text
        label's "no background box, just show the text" base_color is
        (0, 0, 0, 0), a modal's dimming backdrop might use partial alpha,
        etc. - and every one of those was instead punching a real hole in
        the window straight through to the desktop behind it. A one-line
        opaque region is the correct fix at the source, rather than
        auditing every UI color in every app built on this engine to avoid
        alpha < 1.

        Regions are one-shot (consumed by set_opaque_region, not reusable)
        and must cover the surface's *current* size - called from both
        __init__ and resize() so a live resize doesn't leave stale opaque
        bounds around a since-grown-or-shrunk surface."""
        region = self._compositor.create_region()
        region.add(0, 0, width, height)
        self._surface.set_opaque_region(region)
        region.destroy()

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

        # `states` arrives as a raw wl_array (a packed buffer of uint32s,
        # not something pywayland decodes for us - see ArgumentType.Array
        # in pywayland's own message.py), one of which may be "suspended" -
        # tracked here but NOT currently acted on anywhere. Two swap-gating
        # approaches built against this app's own "not responding" while
        # off-workspace/occluded report were both tried and reverted: first
        # skipping eglSwapBuffers directly on this flag (removed - an
        # optional v6+ state, no guarantee a given compositor actually
        # delivers it), then gating draw() on a wl_surface.frame() done
        # callback instead (removed - reproduced a *worse*, near-immediate
        # freeze even while fully visible, most likely from fighting
        # Mesa's own internal EGL presentation-feedback pacing on the same
        # surface, which this never touched).
        #
        # The actual, working fix ended up being unrelated to any of that:
        # graphics/gl44|gl33/context/wayland.py's create_*_opengl_context()
        # now calls eglSwapInterval(egl_display, 0) right after
        # eglMakeCurrent - vsync off means eglSwapBuffers presents and
        # returns immediately instead of blocking on presentation feedback
        # the compositor never sends for an unpresented surface, so it
        # never blocks in the first place, on this surface's suspended
        # state or otherwise. Left `_suspended` tracked-but-unused here
        # anyway, in case a future frame-limiter (now needed, running
        # uncapped/torn without vsync) wants a real visibility signal to
        # throttle against instead of a blind FPS cap.
        state_values = struct.unpack(f"{len(states) // 4}I", states)
        self._suspended = XdgToplevel.state.suspended.value in state_values

    def _on_toplevel_close(self, toplevel):
        self._should_close = True

    # -- pointer --------------------------------------------------------------

    def _on_pointer_enter(self, pointer, serial, surface, surface_x, surface_y):
        self._last_pointer_enter_serial = serial
        if self.mouse is not None:
            self.mouse._set_position(surface_x, surface_y)

        # A client is required to assert a cursor image/shape on every
        # wl_pointer.enter - the compositor does not reset or own this
        # state itself, it just keeps showing whatever the *previously*
        # focused surface last set. Skip this and the cursor silently
        # inherits whatever that other window left behind, including
        # "hidden" (e.g. coming from a game or video player that hides its
        # own cursor) - this is what made the system cursor disappear when
        # focus moved onto this window from one of those.
        self._set_cursor_shape("default")

    # -- cursor shape (cursor-shape-v1) ---------------------------------------

    _CURSOR_SHAPES = {
        "default": "default", "pointer": "pointer", "text": "text",
        "grab": "grab", "grabbing": "grabbing", "crosshair": "crosshair",
        "wait": "wait", "not_allowed": "not_allowed",
    }

    def _ensure_cursor_shape_device(self) -> Optional['WpCursorShapeDeviceV1']:
        """Lazily creates the wp_cursor_shape_device_v1 wrapping this
        window's wl_pointer, once both exist - the manager global and the
        seat's pointer capability can arrive in either order during the
        initial registry roundtrip, so this is called from both places
        that create one of the two instead of assuming an order."""
        if (
            self._cursor_shape_device is None
            and self._cursor_shape_manager is not None
            and self._wl_pointer is not None
        ):
            self._cursor_shape_device = self._cursor_shape_manager.get_pointer(self._wl_pointer)
        return self._cursor_shape_device

    def _set_cursor_shape(self, shape: str):
        """Tells the compositor which named cursor shape to show over this
        window's surface. A no-op if the compositor doesn't support
        cursor-shape-v1 (_ensure_cursor_shape_device stays None) or if no
        pointer has ever entered this surface yet (set_shape needs the
        *enter* event's serial specifically - motion/button events don't
        carry one usable for this, same restriction the older
        wl_pointer.set_cursor request has)."""
        device = self._ensure_cursor_shape_device()
        if device is None or self._last_pointer_enter_serial is None:
            return
        name = self._CURSOR_SHAPES.get(shape, "default")
        device.set_shape(self._last_pointer_enter_serial, WpCursorShapeDeviceV1.shape[name].value)

    # -- clipboard --------------------------------------------------------------

    def _ensure_data_device(self):
        """Lazily creates the wl_data_device wrapping this window's seat,
        once both the wl_data_device_manager global and the seat exist -
        same reasoning as _ensure_cursor_shape_device: the two arrive from
        separate registry/seat-capability callbacks in no guaranteed
        order, so this is called from both places that create one of the
        two rather than assuming an order."""
        if self._data_device is None and self._data_device_manager is not None and self._seat is not None:
            self._data_device = self._data_device_manager.get_data_device(self._seat)
            self._data_device.dispatcher["data_offer"] = self._on_data_offer
            self._data_device.dispatcher["selection"] = self._on_data_selection
            self._data_device.dispatcher["enter"] = lambda *_: None
            self._data_device.dispatcher["leave"] = lambda *_: None
            self._data_device.dispatcher["motion"] = lambda *_: None
            self._data_device.dispatcher["drop"] = lambda *_: None
        return self._data_device

    def _on_data_offer(self, data_device, offer):
        # A new offer always precedes the "selection" event that will (or
        # won't) reference it - this just needs to start tracking which
        # mime types it actually advertises, so get_clipboard_text() can
        # pick a text one instead of blindly requesting "text/plain" from
        # an offer that's actually, say, an image.
        #
        # `offer`'s only strong reference here would otherwise be the
        # closure below, which is itself only reachable *through* `offer`
        # (offer -> its own dispatcher dict -> this lambda -> this closure
        # cell -> offer) - a reference cycle with nothing external keeping
        # it alive, so Python's cyclic GC is free to collect it before the
        # "selection" event ever arrives to reference the same object
        # (this is exactly what a "was it garbage collected?" RuntimeError
        # out of pywayland's own dispatch code turned out to mean).
        # _pending_offers gives it one real external reference until
        # _on_data_selection below either promotes or discards it.
        offer._mime_types = set()
        offer.dispatcher["offer"] = lambda o, mime_type: offer._mime_types.add(mime_type)
        self._pending_offers.append(offer)

    def _on_data_selection(self, data_device, offer):
        # `offer` is None when the clipboard is cleared entirely (not the
        # common case, but a real one - e.g. a client that took ownership
        # of the selection and then exited). Whichever offer just became
        # (or stopped being) the selection is the only one worth a
        # reference anymore - every other pending one was for some earlier
        # selection that's already been superseded.
        self._clipboard_offer = offer
        self._pending_offers = [o for o in self._pending_offers if o is offer]

    _TEXT_MIME_TYPES = ("text/plain;charset=utf-8", "text/plain", "UTF8_STRING", "STRING", "TEXT")

    def get_clipboard_text(self) -> Optional[str]:
        """Returns the system clipboard's current text content, or None if
        it's empty, isn't text, or couldn't be read. Synchronous (reads a
        pipe the offering client writes into - the standard Wayland
        clipboard mechanism, the same one `wl-paste` itself uses) - fine
        for a user-initiated Ctrl+V, not something to call every frame."""
        offer = self._clipboard_offer
        if offer is None:
            return None

        mime_type = next((m for m in self._TEXT_MIME_TYPES if m in offer._mime_types), None)
        if mime_type is None:
            return None

        read_fd, write_fd = os.pipe()
        try:
            offer.receive(mime_type, write_fd)
            os.close(write_fd)
            write_fd = -1
            # The receive() request above only queues on our side until
            # flushed - the offering client can't start writing into the
            # pipe until it actually sees the request, and reading before
            # that would just see an immediate (wrong) EOF.
            self._display.flush()

            chunks = []
            while True:
                chunk = os.read(read_fd, 4096)
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks).decode("utf-8", errors="replace")
        except OSError:
            return None
        finally:
            if write_fd != -1:
                os.close(write_fd)
            os.close(read_fd)

    def set_clipboard_text(self, text: str):
        """Sets the system clipboard's text content by handing it to
        `wl-copy` (wl-clipboard) as a subprocess, rather than this
        backend implementing the wl_data_device/wl_data_source write
        protocol itself.

        There *was* a hand-rolled implementation here (create a
        wl_data_source, offer the same text mime types
        get_clipboard_text() reads, wl_data_device.set_selection() with a
        real input-event serial) that looked protocol-correct - verified
        with wl-paste itself, repeatedly - and still didn't work pasting
        into Firefox, for reasons that were never pinned down (this
        sandbox has no way to drive Firefox's own UI to see what it was
        actually doing differently). Rather than keep guessing at
        implementation details one at a time, this hands the job to the
        actual reference implementation real users already run daily for
        exactly this - wl-copy manages its own short-lived Wayland client
        connection entirely independently of this window (no serial from
        here needed at all), and is a known-good known quantity that
        every other clipboard tool on this system already works with.
        Silently does nothing if wl-copy isn't installed or the call
        fails - no worse than the old implementation's own silent
        no-op-if-nothing-clicked-yet behavior."""
        try:
            subprocess.run(["wl-copy"], input=text.encode("utf-8"), check=True)
        except (OSError, subprocess.CalledProcessError) as e:
            warning(f"wl-copy failed while setting clipboard text: {e}")

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

    def _on_keyboard_repeat_info(self, keyboard, rate, delay):
        """The compositor's own repeat rate/delay (Settings > Keyboard on
        most desktops) - `rate` is characters/sec, `delay` is milliseconds
        before the first repeat. `rate == 0` means the compositor wants
        repeat disabled entirely."""
        self._repeat_rate = float(rate)
        self._repeat_delay_ms = float(delay)

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
            self._keys_down[engine_key] = True

            # Only one key repeats at a time, same as every real text
            # field/terminal - a second key pressed while the first is
            # still held takes over the repeat slot rather than queuing
            # or repeating both, matching normal OS behavior.
            if self._repeat_rate > 0:
                self._repeat_keycode = xkb_keycode
                self._repeat_key = engine_key
                self._repeat_next_time = get_time() + self._repeat_delay_ms / 1000.0

            get_service('input')._key_callback(engine_key, KeyCallbackType.PRESS)

        elif state == WlKeyboard.key_state.released.value:
            self._keys_down[engine_key] = False

            if engine_key == self._repeat_key:
                self._repeat_key = None
                self._repeat_keycode = None

            get_service('input')._key_callback(engine_key, KeyCallbackType.RELEASE)

    def _update_key_repeat(self):
        """Wayland only ever reports a real press/release from
        wl_keyboard.key (see _KEY_TO_KEYSYM_NAMES's docs) - repeat-while-
        held is the client's own job, timed against repeat_info. Called
        from update() every frame; re-resolves the keysym from the held
        keycode at *this* moment rather than reusing the one from the
        original press, so e.g. releasing Shift partway through a held
        letter key correctly starts repeating the lowercase form."""
        if self._repeat_key is None or self._xkb_state is None:
            return

        now = get_time()
        if now < self._repeat_next_time:
            return

        keysym = self._xkb_state.key_get_one_sym(self._repeat_keycode)
        engine_key = XKB_KEYSYM_TO_KEY.get(keysym, self._repeat_key)
        get_service('input')._key_callback(engine_key, KeyCallbackType.REPEAT)

        self._repeat_next_time = now + 1.0 / self._repeat_rate

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
        self._update_opaque_region(width, height)
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
        """Flushes and dispatches pending Wayland events (non-blocking), polls gamepads, ticks key repeat, and quits once closed."""

        self._display.flush()
        self._display.dispatch(block=False)
        self._update_gamepads()
        self._update_key_repeat()

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

    def set_cursor(self, shape: str = "default"):
        """Sets the system cursor's shape - see WaylandWindow._set_cursor_shape
        for the actual protocol call and the set of names supported."""
        self.window._set_cursor_shape(shape)

    def hide_cursor(self):
        """Hides the system cursor via the classic wl_pointer.set_cursor
        request with a null surface - cursor-shape-v1 has no "hidden" shape
        of its own, so hiding still goes through the older mechanism (the
        two aren't exclusive - whichever request was sent most recently for
        this pointer wins, per the protocol)."""
        pointer = self.window._wl_pointer
        serial = self.window._last_pointer_enter_serial
        if pointer is not None and serial is not None:
            pointer.set_cursor(serial, None, 0, 0)

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
