"""
Native X11 backend for FreeBodyEngine.

This mirrors the public behaviour of WaylandWindow, but talks directly to X11
instead of GLFW. It intentionally contains NO graphics API code: EGL/OpenGL
stays in the renderer, exactly like the native Wayland backend.

Dependencies:
    - system libX11 (Arch: pacman -S libx11)
    - xkbcommon is not required here; X11 resolves keysyms through XLookupKeysym.

Native handles exposed for the graphics backend:
    window.native_display     -> Display* as ctypes.c_void_p
    window.native_window      -> X11 Window/XID as int
    window.native_visual_id   -> X11 visual ID of the window's default visual

For EGL on X11, the renderer should normally use:
    eglGetDisplay(window.native_display)
    eglCreateWindowSurface(..., window.native_window, ...)

The EGL config should be compatible with the X11 visual used by this window.
For the simple/default X11 path implemented here, native_visual_id is exposed
so the renderer can constrain EGL_NATIVE_VISUAL_ID when choosing a config.
"""

from __future__ import annotations

import ctypes
import ctypes.util
from typing import TYPE_CHECKING, Optional
import numpy
from FreeBodyEngine.core.window import Window, Cursor, WINDOW_RESIZE, FRAMEBUFFER_RESIZE
from FreeBodyEngine.core.mouse import Mouse
from FreeBodyEngine.core.input import Key, KeyCallbackType
from FreeBodyEngine.math import Vector
from FreeBodyEngine import emit_event, QUIT, error, get_main, get_service, get_time

if TYPE_CHECKING:
    from FreeBodyEngine.graphics.image import Image


# ---------------------------------------------------------------------------
# X11 constants / C types
# ---------------------------------------------------------------------------

X_EVENT_KEY_PRESS = 2
X_EVENT_KEY_RELEASE = 3
X_EVENT_BUTTON_PRESS = 4
X_EVENT_BUTTON_RELEASE = 5
X_EVENT_MOTION_NOTIFY = 6
X_EVENT_CONFIGURE_NOTIFY = 22
X_EVENT_CLIENT_MESSAGE = 33

X_EVENT_MASK_KEY_PRESS = 1 << 0
X_EVENT_MASK_KEY_RELEASE = 1 << 1
X_EVENT_MASK_BUTTON_PRESS = 1 << 2
X_EVENT_MASK_BUTTON_RELEASE = 1 << 3
X_EVENT_MASK_POINTER_MOTION = 1 << 6
X_EVENT_MASK_STRUCTURE_NOTIFY = 1 << 17

X_COPY_FROM_PARENT = 0
X_INPUT_OUTPUT = 1

# X11's primitive native handle types.
DisplayPtr = ctypes.c_void_p
XID = ctypes.c_ulong
Bool = ctypes.c_int
Time = ctypes.c_ulong
KeySym = ctypes.c_ulong
Atom = ctypes.c_ulong


# ---------------------------------------------------------------------------
# XEvent structures. We only model the fields used by this backend.
# ---------------------------------------------------------------------------

class _XAnyEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("serial", ctypes.c_ulong),
        ("send_event", Bool),
        ("display", DisplayPtr),
        ("window", XID),
    ]


class _XKeyEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("serial", ctypes.c_ulong),
        ("send_event", Bool),
        ("display", DisplayPtr),
        ("window", XID),
        ("root", XID),
        ("subwindow", XID),
        ("time", Time),
        ("x", ctypes.c_int),
        ("y", ctypes.c_int),
        ("x_root", ctypes.c_int),
        ("y_root", ctypes.c_int),
        ("state", ctypes.c_uint),
        ("keycode", ctypes.c_uint),
        ("same_screen", Bool),
    ]


class _XButtonEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("serial", ctypes.c_ulong),
        ("send_event", Bool),
        ("display", DisplayPtr),
        ("window", XID),
        ("root", XID),
        ("subwindow", XID),
        ("time", Time),
        ("x", ctypes.c_int),
        ("y", ctypes.c_int),
        ("x_root", ctypes.c_int),
        ("y_root", ctypes.c_int),
        ("state", ctypes.c_uint),
        ("button", ctypes.c_uint),
        ("same_screen", Bool),
    ]


class _XMotionEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("serial", ctypes.c_ulong),
        ("send_event", Bool),
        ("display", DisplayPtr),
        ("window", XID),
        ("root", XID),
        ("subwindow", XID),
        ("time", Time),
        ("x", ctypes.c_int),
        ("y", ctypes.c_int),
        ("x_root", ctypes.c_int),
        ("y_root", ctypes.c_int),
        ("state", ctypes.c_uint),
        ("is_hint", ctypes.c_char),
        ("same_screen", Bool),
    ]


class _XConfigureEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("serial", ctypes.c_ulong),
        ("send_event", Bool),
        ("display", DisplayPtr),
        ("event", XID),
        ("window", XID),
        ("x", ctypes.c_int),
        ("y", ctypes.c_int),
        ("width", ctypes.c_int),
        ("height", ctypes.c_int),
        ("border_width", ctypes.c_int),
        ("above", XID),
        ("override_redirect", Bool),
    ]


class _ClientMessageData(ctypes.Union):
    _fields_ = [
        ("b", ctypes.c_char * 20),
        ("s", ctypes.c_short * 10),
        ("l", ctypes.c_long * 5),
    ]


class _XClientMessageEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("serial", ctypes.c_ulong),
        ("send_event", Bool),
        ("display", DisplayPtr),
        ("window", XID),
        ("message_type", Atom),
        ("format", ctypes.c_int),
        ("data", _ClientMessageData),
    ]


class _XEvent(ctypes.Union):
    _fields_ = [
        ("type", ctypes.c_int),
        ("xany", _XAnyEvent),
        ("xkey", _XKeyEvent),
        ("xbutton", _XButtonEvent),
        ("xmotion", _XMotionEvent),
        ("xconfigure", _XConfigureEvent),
        ("xclient", _XClientMessageEvent),
        ("pad", ctypes.c_long * 24),
    ]


# ---------------------------------------------------------------------------
# Xlib loading
# ---------------------------------------------------------------------------

_libname = ctypes.util.find_library("X11") or "libX11.so.6"
_x11 = ctypes.CDLL(_libname)

_x11.XOpenDisplay.restype = DisplayPtr
_x11.XOpenDisplay.argtypes = [ctypes.c_char_p]

_x11.XCloseDisplay.restype = ctypes.c_int
_x11.XCloseDisplay.argtypes = [DisplayPtr]

_x11.XDefaultScreen.restype = ctypes.c_int
_x11.XDefaultScreen.argtypes = [DisplayPtr]

_x11.XRootWindow.restype = XID
_x11.XRootWindow.argtypes = [DisplayPtr, ctypes.c_int]

_x11.XDefaultDepth.restype = ctypes.c_int
_x11.XDefaultDepth.argtypes = [DisplayPtr, ctypes.c_int]

_x11.XDefaultVisual.restype = DisplayPtr
_x11.XDefaultVisual.argtypes = [DisplayPtr, ctypes.c_int]

_x11.XVisualIDFromVisual.restype = XID
_x11.XVisualIDFromVisual.argtypes = [DisplayPtr]

_x11.XCreateSimpleWindow.restype = XID
_x11.XCreateSimpleWindow.argtypes = [
    DisplayPtr,
    XID,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_uint,
    ctypes.c_uint,
    ctypes.c_uint,
    ctypes.c_ulong,
    ctypes.c_ulong,
]

_x11.XSelectInput.restype = ctypes.c_int
_x11.XSelectInput.argtypes = [DisplayPtr, XID, ctypes.c_long]

_x11.XMapWindow.restype = ctypes.c_int
_x11.XMapWindow.argtypes = [DisplayPtr, XID]

_x11.XDestroyWindow.restype = ctypes.c_int
_x11.XDestroyWindow.argtypes = [DisplayPtr, XID]

_x11.XFlush.restype = ctypes.c_int
_x11.XFlush.argtypes = [DisplayPtr]

_x11.XPending.restype = ctypes.c_int
_x11.XPending.argtypes = [DisplayPtr]

_x11.XNextEvent.restype = ctypes.c_int
_x11.XNextEvent.argtypes = [DisplayPtr, ctypes.POINTER(_XEvent)]

_x11.XInternAtom.restype = Atom
_x11.XInternAtom.argtypes = [DisplayPtr, ctypes.c_char_p, Bool]

_x11.XSetWMProtocols.restype = ctypes.c_int
_x11.XSetWMProtocols.argtypes = [DisplayPtr, XID, ctypes.POINTER(Atom), ctypes.c_int]

_x11.XStoreName.restype = ctypes.c_int
_x11.XStoreName.argtypes = [DisplayPtr, XID, ctypes.c_char_p]

_x11.XMoveWindow.restype = ctypes.c_int
_x11.XMoveWindow.argtypes = [DisplayPtr, XID, ctypes.c_int, ctypes.c_int]

_x11.XResizeWindow.restype = ctypes.c_int
_x11.XResizeWindow.argtypes = [DisplayPtr, XID, ctypes.c_uint, ctypes.c_uint]

_x11.XGetWindowAttributes.restype = ctypes.c_int


class _XWindowAttributes(ctypes.Structure):
    # Fields through x/y/width/height, followed by the rest of the structure.
    # The complete native struct is larger; we only access the fields at the
    # beginning and let ctypes copy the full returned object into this layout.
    _fields_ = [
        ("x", ctypes.c_int),
        ("y", ctypes.c_int),
        ("width", ctypes.c_int),
        ("height", ctypes.c_int),
        ("border_width", ctypes.c_int),
        ("depth", ctypes.c_int),
        ("visual", DisplayPtr),
        ("root", XID),
        ("class", ctypes.c_int),
        ("bit_gravity", ctypes.c_int),
        ("win_gravity", ctypes.c_int),
        ("backing_store", ctypes.c_int),
        ("backing_planes", ctypes.c_ulong),
        ("backing_pixel", ctypes.c_ulong),
        ("save_under", Bool),
        ("colormap", XID),
        ("map_installed", Bool),
        ("map_state", ctypes.c_int),
        ("all_event_masks", ctypes.c_long),
        ("your_event_mask", ctypes.c_long),
        ("do_not_propagate_mask", ctypes.c_long),
        ("override_redirect", Bool),
        ("screen", DisplayPtr),
    ]


_x11.XGetWindowAttributes.argtypes = [DisplayPtr, XID, ctypes.POINTER(_XWindowAttributes)]

# Optional but useful: make autorepeat detectable, so X11 gives us a press
# without the fake release/press pair for a held key on supporting servers.
try:
    _x11.XkbSetDetectableAutoRepeat.restype = Bool
    _x11.XkbSetDetectableAutoRepeat.argtypes = [DisplayPtr, Bool, ctypes.POINTER(Bool)]
    _HAS_XKB_DETECTABLE_REPEAT = True
except AttributeError:
    _HAS_XKB_DETECTABLE_REPEAT = False

_x11.XLookupKeysym.restype = KeySym
_x11.XLookupKeysym.argtypes = [ctypes.POINTER(_XKeyEvent), ctypes.c_int]

_x11.XKeysymToString.restype = ctypes.c_char_p
_x11.XKeysymToString.argtypes = [KeySym]


# ---------------------------------------------------------------------------
# Keys: use X11's names rather than hard-coding numerical keysyms.
# The names intentionally mirror the Wayland/xkbcommon backend.
# ---------------------------------------------------------------------------

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
    Key.HOME: "Home", Key.END: "End", Key.PG_UP: "Page_Up", Key.PG_DOWN: "Page_Down",
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

KEYSYM_NAME_TO_KEY = {name: key for key, name in _KEY_TO_KEYSYM_NAME.items()}


# X11 buttons. Scroll wheel buttons (4/5/6/7) are not exposed as regular
# mouse buttons because the existing Mouse interface has no wheel API.
_X11_BUTTON_TO_INDEX = {
    1: 0,  # left
    3: 1,  # right
    2: 2,  # middle
    8: 3,  # side/back on common mappings
    9: 4,  # extra/forward on common mappings
}


class X11Window(Window):
    """Native X11/XWayland window backend for FreeBodyEngine."""

    def __init__(self, size: tuple[int, int], title: str):
        """Opens the X11 display, creates a simple window, and registers for the events this backend handles.

        Also opts into detectable autorepeat where the server supports it
        (`_HAS_XKB_DETECTABLE_REPEAT`), so a held key reports as PRESS then
        REPEAT rather than a synthetic RELEASE/PRESS pair per repeat tick.
        """
        super().__init__(size, title)
        self.window_type = "x11"

        self._should_close = False
        self._size = (int(size[0]), int(size[1]))
        self._scale = 1
        self._keys_down: dict[Key, bool] = {}
        self.mouse: Optional["X11Mouse"] = None

        self._display = _x11.XOpenDisplay(None)
        if not self._display:
            raise RuntimeError(
                "Failed to open X11 display. Is DISPLAY set and is XWayland/X11 available?"
            )

        try:
            self._screen = _x11.XDefaultScreen(self._display)
            self._root = _x11.XRootWindow(self._display, self._screen)
            visual = _x11.XDefaultVisual(self._display, self._screen)
            self._visual = visual
            self._visual_id = int(_x11.XVisualIDFromVisual(visual))

            self._window = _x11.XCreateSimpleWindow(
                self._display,
                self._root,
                0,
                0,
                self._size[0],
                self._size[1],
                0,
                0,
                0,
            )
            if not self._window:
                raise RuntimeError("XCreateSimpleWindow failed.")

            event_mask = (
                X_EVENT_MASK_KEY_PRESS
                | X_EVENT_MASK_KEY_RELEASE
                | X_EVENT_MASK_BUTTON_PRESS
                | X_EVENT_MASK_BUTTON_RELEASE
                | X_EVENT_MASK_POINTER_MOTION
                | X_EVENT_MASK_STRUCTURE_NOTIFY
            )
            _x11.XSelectInput(self._display, self._window, event_mask)

            # Tell the window manager that the application has a title.
            _x11.XStoreName(self._display, self._window, title.encode("utf-8", errors="replace"))

            # Handle the standard close button.
            self._wm_protocols = _x11.XInternAtom(self._display, b"WM_PROTOCOLS", False)
            self._wm_delete_window = _x11.XInternAtom(self._display, b"WM_DELETE_WINDOW", False)
            protocols = (Atom * 1)(self._wm_delete_window)
            if _x11.XSetWMProtocols(self._display, self._window, protocols, 1) == 0:
                raise RuntimeError("XSetWMProtocols failed.")

            if _HAS_XKB_DETECTABLE_REPEAT:
                supported = Bool()
                _x11.XkbSetDetectableAutoRepeat(self._display, True, ctypes.byref(supported))

            _x11.XMapWindow(self._display, self._window)
            _x11.XFlush(self._display)
        except Exception:
            _x11.XCloseDisplay(self._display)
            self._display = None
            raise

    # ------------------------------------------------------------------
    # Native handles
    # ------------------------------------------------------------------

    @property
    def native_display(self):
        """X11 Display* suitable for eglGetDisplay()."""
        return ctypes.c_void_p(self._display)

    @property
    def native_window(self) -> int:
        """X11 Window/XID suitable for eglCreateWindowSurface()."""
        return int(self._window)

    @property
    def native_visual_id(self) -> int:
        """Visual ID used by the X11 window; useful for EGL_NATIVE_VISUAL_ID."""
        return self._visual_id

    # ------------------------------------------------------------------
    # X11 event handling
    # ------------------------------------------------------------------

    def _lookup_key(self, event: _XKeyEvent):
        keysym = _x11.XLookupKeysym(ctypes.byref(event), 0)
        name = _x11.XKeysymToString(keysym)
        if not name:
            return None
        return KEYSYM_NAME_TO_KEY.get(name.decode("ascii", errors="ignore"))

    def _handle_event(self, event: _XEvent):
        event_type = int(event.type)

        if event_type == X_EVENT_CLIENT_MESSAGE:
            client = event.xclient
            if int(client.message_type) == int(self._wm_protocols):
                if int(client.data.l[0]) == int(self._wm_delete_window):
                    self._should_close = True
            return

        if event_type == X_EVENT_CONFIGURE_NOTIFY:
            cfg = event.xconfigure
            new_size = (int(cfg.width), int(cfg.height))
            if new_size != self._size and new_size[0] > 0 and new_size[1] > 0:
                self._size = new_size
                emit_event(WINDOW_RESIZE, new_size)
                emit_event(FRAMEBUFFER_RESIZE, self.framebuffer_size)
            return

        if event_type == X_EVENT_MOTION_NOTIFY:
            motion = event.xmotion
            if self.mouse is not None:
                self.mouse._set_position(motion.x, motion.y)
            return

        if event_type == X_EVENT_BUTTON_PRESS:
            button = event.xbutton
            index = _X11_BUTTON_TO_INDEX.get(int(button.button))
            if index is not None and self.mouse is not None:
                self.mouse._on_button(index, True, int(button.time))
            return

        if event_type == X_EVENT_BUTTON_RELEASE:
            button = event.xbutton
            index = _X11_BUTTON_TO_INDEX.get(int(button.button))
            if index is not None and self.mouse is not None:
                self.mouse._on_button(index, False, int(button.time))
            return

        if event_type == X_EVENT_KEY_PRESS:
            key_event = event.xkey
            key = self._lookup_key(key_event)
            if key is None:
                return

            # With detectable autorepeat enabled, a repeated press arrives as
            # a press while the key remains down. Otherwise this also behaves
            # sensibly for servers that don't provide detectable autorepeat.
            repeated = self._keys_down.get(key, False)
            self._keys_down[key] = True
            callback_type = KeyCallbackType.REPEAT if repeated else KeyCallbackType.PRESS
            get_service("input")._key_callback(key, callback_type)
            return

        if event_type == X_EVENT_KEY_RELEASE:
            key_event = event.xkey
            key = self._lookup_key(key_event)
            if key is None:
                return

            self._keys_down[key] = False
            get_service("input")._key_callback(key, KeyCallbackType.RELEASE)

    # ------------------------------------------------------------------
    # Window interface
    # ------------------------------------------------------------------

    def set_title(self, new_title):
        """Sets the window's WM_NAME via XStoreName."""
        _x11.XStoreName(self._display, self._window, str(new_title).encode("utf-8", errors="replace"))
        _x11.XFlush(self._display)

    @property
    def size(self) -> tuple[int, int]:
        """The window's last known size, in pixels, as (width, height)."""
        return self._size

    @size.setter
    def size(self, new: tuple[int, int]):
        """Resizes the window via XResizeWindow and fires WINDOW_RESIZE/FRAMEBUFFER_RESIZE immediately.

        Silently ignored if `new` isn't positive in both dimensions. The
        local size is updated right away rather than waiting for the
        server's ConfigureNotify, matching the Wayland backend's behavior;
        the eventual ConfigureNotify (handled in _handle_event) reconciles
        this with whatever the window manager actually granted.
        """
        width, height = int(new[0]), int(new[1])
        if width <= 0 or height <= 0:
            return
        _x11.XResizeWindow(self._display, self._window, width, height)
        _x11.XFlush(self._display)

        # Match the Wayland backend's immediate local state update. The
        # ConfigureNotify handler will reconcile this with the WM's result.
        if (width, height) != self._size:
            self._size = (width, height)
            emit_event(WINDOW_RESIZE, self._size)
            emit_event(FRAMEBUFFER_RESIZE, self.framebuffer_size)

    @property
    def framebuffer_size(self) -> tuple[int, int]:
        """The window size scaled by `_scale`."""
        return (self._size[0] * self._scale, self._size[1] * self._scale)

    @property
    def position(self) -> tuple[int, int]:
        """The window's position on screen, in pixels, read via XGetWindowAttributes (falls back to (0, 0) on failure)."""
        attrs = _XWindowAttributes()
        if _x11.XGetWindowAttributes(self._display, self._window, ctypes.byref(attrs)):
            return int(attrs.x), int(attrs.y)
        return (0, 0)

    @position.setter
    def position(self, new: tuple[int, int]):
        """Moves the window to `new` (x, y), in pixels, via XMoveWindow."""
        _x11.XMoveWindow(self._display, self._window, int(new[0]), int(new[1]))
        _x11.XFlush(self._display)

    def resize(self, window, width, height):
        """Convenience wrapper that resizes through the `size` setter."""
        self.size = (width, height)

    def is_ready(self) -> bool:
        """True until the window has received a WM_DELETE_WINDOW client message."""
        return not self._should_close

    def _get_key_down(self, key: Key):
        return self._keys_down.get(key, False)

    def _get_gamepad_state(self, gamepad: int):
        # Same deliberate stub as the native Wayland backend. Use evdev,
        # SDL, or another dedicated gamepad/input layer if the engine needs it.
        pass

    def _create_cursor(self, image: "Image"):
        # TODO: Xcursor/XFixes implementation.
        pass

    def _set_cursor(self, cursor: "Cursor"):
        # TODO: XDefineCursor/Xcursor implementation.
        pass

    def create_mouse(self):
        """Creates this window's X11Mouse and stores it so event handling (e.g. _handle_event) can reach it."""
        self.mouse = X11Mouse(self)
        return self.mouse

    def close(self):
        """Destroys the X11 window and closes the display connection, if not already closed."""
        if self._display is None:
            return

        self._should_close = True
        if self._window:
            _x11.XDestroyWindow(self._display, self._window)
            self._window = 0
        _x11.XFlush(self._display)
        _x11.XCloseDisplay(self._display)
        self._display = None
        emit_event(QUIT)

    def draw(self):
        """Asks the renderer to swap buffers, presenting the frame."""
        renderer = get_service("renderer")
        if renderer is not None:
            renderer.swap_buffers()

    def update(self):
        """Drains all currently queued X11 events (non-blocking) and quits the engine once closed."""
        # Drain all currently queued X11 events. Never block here; the engine's
        # main loop remains responsible for frame pacing.
        if self._display is None:
            return

        while _x11.XPending(self._display) > 0:
            event = _XEvent()
            _x11.XNextEvent(self._display, ctypes.byref(event))
            self._handle_event(event)

        _x11.XFlush(self._display)

        if self._should_close:
            get_main().quit()


class X11Mouse(Mouse):
    """Mouse implementation matching the externally-visible Wayland backend."""

    def __init__(self, window: X11Window):
        """Sets up per-button event/state tracking for `window`; position starts at the origin until a motion event arrives."""
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

    def _set_position(self, x: float, y: float):
        self.position = Vector(x, y)

    def _on_button(self, index: int, pressed: bool, time_ms: int):
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
        """Latches this frame's pressed/released events (set by _handle_event) and updates world-space position."""
        self._pressed = self._pressed_events
        self._released = self._released_events
        self._pressed_events = [False] * 8
        self._released_events = [False] * 8

        scene_manager = get_service("scene_manager")
        scene = scene_manager.get_active() if scene_manager is not None else None

        self.world_position = self.position
        if scene is not None:
            cam = scene.camera
            if cam is not None:
                win_size = self.window.size
                if win_size[0] > 0 and win_size[1] > 0:
                    ndc_x = (self.position.x / win_size[0]) * 2.0 - 1.0
                    ndc_y = (self.position.y / win_size[1]) * 2.0 - 1.0
                    clip_pos = (ndc_x, ndc_y, 0.0, 1.0)

                    proj_view_inverse = numpy.linalg.inv(
                        cam.proj_matrix @ cam._get_view_mat()
                    )
                    p = proj_view_inverse @ clip_pos
                    p /= p[3]
                    self.world_position = Vector(p[0], p[1])

        self._double_clicked = [False] * 8




