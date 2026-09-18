"""The web window backend - runs under Pyodide (this engine compiled to
WASM, executing inside an actual browser tab, not a native process at
all - see utils.get_platform()'s own docstring for why `sys.platform`
reports `"emscripten"` there). Unlike every other backend (GLFW/Wayland/
X11/Win32/headless), there's no OS-level window to create: "the window" is
an HTML `<canvas>` element already sitting in the page (or created here if
one isn't), and "the GPU context" is that canvas's `webgl2` context,
reached entirely through Pyodide's `js` bridge - none of PyOpenGL/GLFW/SDL2
is importable here at all, since none of them exist inside the WASM
sandbox. See graphics/webgl/renderer.py for the WebGL2 renderer that
actually draws into this context.

Input works the same shape as every other backend (poll-per-frame state
that `update()` refreshes) but is *fed* the opposite way around: a native
backend polls its OS/library for the current state every frame (e.g.
`glfw.get_key()`); a browser only ever *pushes* input as async DOM events,
so this backend's job is to catch those events the instant they fire (via
`addEventListener`, using `pyodide.ffi.create_proxy` to hand a JS-callable
wrapper for a Python callback) and buffer them into the same per-frame
state shape `update()` already exposes everywhere else - real backends
just get there via a different route.
"""
import js
from pyodide.ffi import create_proxy, create_once_callable

from FreeBodyEngine.core.window.generic import Window, Cursor
from FreeBodyEngine.core.mouse import Mouse
from FreeBodyEngine.core.input import Key, KeyCallbackType
from FreeBodyEngine.math import Vector
from FreeBodyEngine import get_service, warning
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from FreeBodyEngine.graphics.image import Image

CANVAS_ID = "fb-canvas"

# KeyboardEvent.code (layout-independent - unlike .key, unaffected by
# Shift/AltGr/IME) -> this engine's own Key enum. Covers the same set
# core/window/headless.py's SDL_KEY_MAP does, so a project's input code
# doesn't need to know or care which backend is actually running.
JS_KEY_MAP = {
    "KeyA": Key.A, "KeyB": Key.B, "KeyC": Key.C, "KeyD": Key.D, "KeyE": Key.E,
    "KeyF": Key.F, "KeyG": Key.G, "KeyH": Key.H, "KeyI": Key.I, "KeyJ": Key.J,
    "KeyK": Key.K, "KeyL": Key.L, "KeyM": Key.M, "KeyN": Key.N, "KeyO": Key.O,
    "KeyP": Key.P, "KeyQ": Key.Q, "KeyR": Key.R, "KeyS": Key.S, "KeyT": Key.T,
    "KeyU": Key.U, "KeyV": Key.V, "KeyW": Key.W, "KeyX": Key.X, "KeyY": Key.Y,
    "KeyZ": Key.Z,

    "Digit0": Key.ZERO, "Digit1": Key.ONE, "Digit2": Key.TWO, "Digit3": Key.THREE,
    "Digit4": Key.FOUR, "Digit5": Key.FIVE, "Digit6": Key.SIX, "Digit7": Key.SEVEN,
    "Digit8": Key.EIGHT, "Digit9": Key.NINE,

    "Minus": Key.MINUS, "Equal": Key.EQUAL, "BracketLeft": Key.LEFT_BRACKET,
    "BracketRight": Key.RIGHT_BRACKET, "Backslash": Key.BACKSLASH,
    "Semicolon": Key.SEMICOLON, "Quote": Key.APOSTROPHE, "Backquote": Key.TILDE,
    "Comma": Key.COMMA, "Period": Key.PERIOD, "Slash": Key.SLASH,

    "Space": Key.SPACE, "Enter": Key.RETURN, "Backspace": Key.BACKSPACE,
    "Tab": Key.TAB, "Escape": Key.ESCAPE, "CapsLock": Key.CAPS_LOCK,

    "ControlLeft": Key.L_CTRL, "ControlRight": Key.R_CTRL,
    "ShiftLeft": Key.L_SHIFT, "ShiftRight": Key.R_SHIFT,
    "AltLeft": Key.L_ALT, "AltRight": Key.R_ALT,
    "MetaLeft": Key.L_SUPER, "MetaRight": Key.R_SUPER,

    "Insert": Key.INSERT, "Delete": Key.DELETE, "Home": Key.HOME, "End": Key.END,
    "PageUp": Key.PG_UP, "PageDown": Key.PG_DOWN,
    "ArrowUp": Key.UP, "ArrowDown": Key.DOWN, "ArrowLeft": Key.LEFT, "ArrowRight": Key.RIGHT,

    "F1": Key.F1, "F2": Key.F2, "F3": Key.F3, "F4": Key.F4, "F5": Key.F5,
    "F6": Key.F6, "F7": Key.F7, "F8": Key.F8, "F9": Key.F9, "F10": Key.F10,
    "F11": Key.F11,
}

# JS MouseEvent.button -> this engine's own button index convention
# (0=left, 1=middle, 2=right - matches GLFW's own numbering, which the rest
# of the engine, e.g. ui/manager.py, already assumes).
JS_MOUSE_BUTTON_MAP = {0: 0, 1: 1, 2: 2}


class WebWindow(Window):
    """Window backend for a browser tab running under Pyodide. Owns the
    page's `<canvas>` element and its `webgl2` context; has no OS-level
    position/decorations/title bar at all (those concepts belong to the
    browser tab/window, not to anything this engine controls), so the
    handful of abstract methods about them are honest no-ops rather than
    faked native behavior.
    """
    def __init__(self, size: tuple[int, int], title: str = "FreeBodyEngine"):
        """Finds (or creates) the page's canvas, sizes it to `size`, and
        gets its `webgl2` rendering context - graphics/webgl/renderer.py
        reads `self.gl` back out of this window the same way GL33Renderer
        reads `self.window._window` on GLFW."""
        super().__init__(size, title)
        self.window_type = 'web'
        self._should_close = False
        self._title = title

        canvas = js.document.getElementById(CANVAS_ID)
        if canvas is None:
            canvas = js.document.createElement("canvas")
            canvas.id = CANVAS_ID
            js.document.body.appendChild(canvas)

        self.canvas = canvas
        self.canvas.width = size[0]
        self.canvas.height = size[1]

        # alpha=False: this engine always draws an opaque scene and
        # compositing the canvas against the page behind it is never
        # wanted - without this WebGL2's default premultiplied-alpha
        # canvas blending can make a translucent trail/fade effect
        # blend with the *page background* instead of reading as fully
        # opaque. antialias=False: FreeBodyEngine already renders through
        # its own postprocess/trail pipeline (see e.g. phonon's
        # VisualizerPipeline) - browser MSAA on top of that is wasted
        # GPU time, not extra quality.
        context_options = js.Object.new()
        context_options.alpha = False
        context_options.antialias = False
        context_options.preserveDrawingBuffer = False
        self.gl = canvas.getContext("webgl2", context_options)
        if self.gl is None:
            raise RuntimeError(
                "Could not create a WebGL2 context - this browser/GPU doesn't support it."
            )

        self._down_keys: set[str] = set()
        self._resize_pending: tuple[int, int] | None = None

        self._mousemove_proxy = create_proxy(self._on_mousemove)
        self._mousedown_proxy = create_proxy(self._on_mousedown)
        self._mouseup_proxy = create_proxy(self._on_mouseup)
        self._wheel_proxy = create_proxy(self._on_wheel)
        self._keydown_proxy = create_proxy(self._on_keydown)
        self._keyup_proxy = create_proxy(self._on_keyup)
        self._paste_proxy = create_proxy(self._on_paste)
        self._contextmenu_proxy = create_proxy(lambda e: e.preventDefault())

        canvas.addEventListener("mousemove", self._mousemove_proxy)
        canvas.addEventListener("mousedown", self._mousedown_proxy)
        canvas.addEventListener("mouseup", self._mouseup_proxy)
        canvas.addEventListener("wheel", self._wheel_proxy)
        # contextmenu (right-click) is prevented on the canvas specifically
        # - a real game legitimately uses the right mouse button for its
        # own input (see ui/manager.py's button conventions), and the
        # browser's native context menu popping up on every right-click
        # would make that unusable.
        canvas.addEventListener("contextmenu", self._contextmenu_proxy)
        js.window.addEventListener("keydown", self._keydown_proxy)
        js.window.addEventListener("keyup", self._keyup_proxy)
        # See _on_paste()/get_clipboard_text() below for why this - not
        # navigator.clipboard.readText() - is how pasting actually works
        # on this backend.
        js.window.addEventListener("paste", self._paste_proxy)

        self._mouse_pos = Vector(0, 0)
        self._mouse_down = [False, False, False]
        self._scroll_accum = Vector(0.0, 0.0)

    def _on_mousemove(self, event):
        # `event.clientX/clientY` are always CSS pixels, never scaled by
        # devicePixelRatio - but every consumer of Mouse.position (see
        # ui/manager.py, which lays out and hit-tests entirely against
        # `window.framebuffer_size`) expects framebuffer-pixel
        # coordinates, same as every native backend already reports
        # (GLFW's cursor callback is in framebuffer pixels there too).
        # Without this scale, a HiDPI tab (devicePixelRatio != 1) has
        # every click land at the wrong fraction of where the UI thinks
        # it is - e.g. at devicePixelRatio 1.5 a click 2/3 of the way
        # into a field's real bounds still reads as outside them.
        rect = self.canvas.getBoundingClientRect()
        scale_x = self.canvas.width / rect.width if rect.width else 1.0
        scale_y = self.canvas.height / rect.height if rect.height else 1.0
        self._mouse_pos = Vector(
            (event.clientX - rect.left) * scale_x,
            (event.clientY - rect.top) * scale_y,
        )

    def _on_mousedown(self, event):
        button = JS_MOUSE_BUTTON_MAP.get(event.button)
        if button is not None:
            self._mouse_down[button] = True

    def _on_mouseup(self, event):
        button = JS_MOUSE_BUTTON_MAP.get(event.button)
        if button is not None:
            self._mouse_down[button] = False

    def _on_wheel(self, event):
        event.preventDefault()
        # deltaY > 0 is "scrolled down" in the DOM - negated so positive y
        # means "scrolled up", matching Mouse.get_scroll_delta()'s own
        # documented convention (see core/mouse.py).
        self._scroll_accum += Vector(-event.deltaX, -event.deltaY) * 0.01

    def _on_keydown(self, event):
        self._down_keys.add(event.code)

        # Every other backend (GLFWWindow._key_callback, x11.py, wayland.py,
        # testwindow.py) feeds Input._key_callback() directly from its own
        # native key event - that's what actually drives the KEY_PRESS/
        # KEY_REPEAT/KEY_RELEASE events ui/manager.py's _on_key() (all text
        # field typing, arrow/backspace/delete/submit handling) is
        # registered against. `_down_keys` alone only backs the *polled*
        # _get_key_down() path (held-modifier checks like ctrl/shift) - so
        # without this, that event stream never fires on web at all and
        # every keystroke is silently dropped by the UI. `event.repeat` is
        # the DOM's own key-repeat flag (true while a key is held past the
        # OS repeat delay), the same distinction GLFW's REPEAT action
        # encodes natively.
        key = JS_KEY_MAP.get(event.code)
        if key is not None:
            key_type = KeyCallbackType.REPEAT if event.repeat else KeyCallbackType.PRESS
            get_service('input')._key_callback(key, key_type)

    def _on_keyup(self, event):
        self._down_keys.discard(event.code)

        key = JS_KEY_MAP.get(event.code)
        if key is not None:
            get_service('input')._key_callback(key, KeyCallbackType.RELEASE)

    def _on_paste(self, event):
        """Handles the browser's native `paste` ClipboardEvent - see
        get_clipboard_text()'s own docstring for why this, not
        navigator.clipboard.readText(), is what actually backs pasting on
        this backend. Unlike the Clipboard API, `event.clipboardData` is
        populated synchronously as part of the event the moment the user
        does Ctrl+V (or a right-click "Paste") - no Promise, no
        permissions prompt, since it's a direct result of that user
        gesture rather than an on-demand read - so this can hand the text
        straight to ui/manager.py's UIManager.paste_text() the instant it
        arrives, same call the desktop backends' Ctrl+V keydown handling
        makes once *its* (synchronous) get_clipboard_text() returns.

        Registered on `js.window` rather than the canvas: this engine's
        keydown/keyup listeners already are too (see __init__), since
        nothing here relies on the canvas holding real DOM focus - a
        `paste` event fired anywhere in the page while this is the only
        tab open reaches this the same way a keystroke does."""
        event.preventDefault()
        clipboard_data = event.clipboardData
        text = clipboard_data.getData("text/plain") if clipboard_data else None

        ui = get_service('ui')
        if ui is not None:
            ui.paste_text(text)

    def create_mouse(self) -> Mouse:
        """Creates and returns WebMouse, wired up to this window's
        JS-event-fed button/position state."""
        return WebMouse(self)

    def is_ready(self) -> bool:
        """True until close() is called - a browser tab has no equivalent
        of a native "window close" request this engine would need to poll
        for (closing the tab just kills the whole WASM runtime outright)."""
        return not self._should_close

    @property
    def size(self) -> tuple[int, int]:
        """The canvas's CSS pixel size."""
        return (int(self.canvas.clientWidth) or self.canvas.width, int(self.canvas.clientHeight) or self.canvas.height)

    @size.setter
    def size(self, new: tuple[int, int]):
        """Resizes the canvas's CSS box (its drawing-buffer resolution is
        governed by `framebuffer_size`/devicePixelRatio - see there)."""
        self.canvas.style.width = f"{new[0]}px"
        self.canvas.style.height = f"{new[1]}px"

    @property
    def framebuffer_size(self) -> tuple[int, int]:
        """The canvas's actual drawing-buffer resolution (`width`/`height`
        attributes, not its CSS box size) - scaled by devicePixelRatio so
        this reads correctly on a HiDPI display, matching every other
        backend's framebuffer_size/size distinction."""
        return (int(self.canvas.width), int(self.canvas.height))

    @property
    def position(self) -> tuple[int, int]:
        """Always (0, 0) - a canvas has no OS-level window position; where
        it sits on the page is a CSS/layout concern outside this engine."""
        return (0, 0)

    @position.setter
    def position(self, new: tuple[int, int]):
        """No-op - see the `position` getter's docstring."""
        pass

    def set_title(self, new_title: str):
        """Sets the browser tab's title (`document.title`) - the closest
        web equivalent of a native window's title bar."""
        self._title = new_title
        js.document.title = new_title

    def _get_key_down(self, key: Key) -> float:
        code = _KEY_TO_JS_CODE.get(key)
        if code is None:
            return 0.0
        return 1.0 if code in self._down_keys else 0.0

    def _get_gamepad_state(self, id: int):
        """Not yet implemented - the Gamepad API needs an explicit poll
        (`navigator.getGamepads()`) this backend doesn't hook up yet."""
        return None

    def _create_cursor(self, image: 'Image'):
        """Not yet implemented - a custom CSS cursor would be built from a
        data: URL; see WebMouse.set_cursor() for the standard-shape case
        that *is* implemented."""
        return Cursor()

    def _set_cursor(self, cursor: 'Cursor'):
        pass

    def get_clipboard_text(self) -> str | None:
        """Still a no-op (see Window.get_clipboard_text's own concrete
        no-op default) - the Clipboard API (`navigator.clipboard.
        readText()`) is async (returns a JS Promise) and this method's
        contract is synchronous, so it's not bridged here. This does NOT
        mean pasting is broken on web, though: ui/manager.py's Ctrl+V
        handling calls this and does nothing useful with the None it gets
        back, but the actual paste happens through a separate, genuinely
        synchronous path - see _on_paste() above, which the browser's own
        native `paste` event drives directly into UIManager.paste_text()
        without ever needing to come through here."""
        return super().get_clipboard_text()

    def set_clipboard_text(self, text: str):
        """Writes `text` to the system clipboard via the Clipboard API's
        `writeText()` - unlike reading (see get_clipboard_text()/
        _on_paste()'s docstrings for why *that* needs the native `paste`
        event instead of this same API's `readText()`), writing has
        nothing a caller needs handed back, so there's no synchronous-
        contract mismatch to work around here: the write just happens in
        the background, the same "fire it and don't wait" shape as any
        other JS Promise this engine doesn't need the result of.

        Two real constraints inherited straight from the browser, not
        something this method can smooth over: `writeText()` only exists
        in a secure context (HTTPS, or localhost - not a plain `http://`
        page), and only succeeds when called from within a real user-
        gesture handler (a click callback, e.g. phonon's "copy share
        link" button) - calling it on a timer or at startup gets silently
        rejected. A rejection here is real feedback of that, not this
        binding failing, so it's surfaced as a warning rather than
        swallowed."""
        def _on_error(err):
            warning(f"set_clipboard_text() failed: {err}")

        js.navigator.clipboard.writeText(text).catch(create_once_callable(_on_error))

    def close(self):
        """Marks this window as closed and tears down its event listeners
        - there's no native resource to release (the canvas/GL context are
        just left as the browser tab exits, whether now or later)."""
        self._should_close = True
        self.canvas.removeEventListener("mousemove", self._mousemove_proxy)
        self.canvas.removeEventListener("mousedown", self._mousedown_proxy)
        self.canvas.removeEventListener("mouseup", self._mouseup_proxy)
        self.canvas.removeEventListener("wheel", self._wheel_proxy)
        self.canvas.removeEventListener("contextmenu", self._contextmenu_proxy)
        js.window.removeEventListener("keydown", self._keydown_proxy)
        js.window.removeEventListener("keyup", self._keyup_proxy)
        js.window.removeEventListener("paste", self._paste_proxy)
        from FreeBodyEngine import fbquit
        fbquit()

    def draw(self):
        """No-op - WebGL2 presents to the canvas implicitly the moment the
        current JS task (this whole animation-frame callback - see
        core/main.py's web run loop) returns control to the browser, the
        same way a native backend's real swap-buffers call presents its
        already-rendered backbuffer."""
        pass

    def update(self):
        """Applies any canvas resize requested by the page (see the
        `resize()` note below) and emits FRAMEBUFFER_RESIZE/WINDOW_RESIZE
        so the renderer's viewport and any letterboxing UI stay in sync -
        there's no OS event queue to pump here (JS event listeners already
        deliver input the instant it happens, not once per polled frame),
        so this is lighter than a native backend's update()."""
        from FreeBodyEngine.core.window import WINDOW_RESIZE, FRAMEBUFFER_RESIZE
        from FreeBodyEngine import emit_event

        css_w, css_h = js.window.innerWidth, js.window.innerHeight
        dpr = js.window.devicePixelRatio or 1
        fb_w, fb_h = int(css_w * dpr), int(css_h * dpr)
        if (fb_w, fb_h) != (self.canvas.width, self.canvas.height):
            self.canvas.style.width = f"{css_w}px"
            self.canvas.style.height = f"{css_h}px"
            self.canvas.width = fb_w
            self.canvas.height = fb_h
            emit_event(WINDOW_RESIZE, (css_w, css_h))
            emit_event(FRAMEBUFFER_RESIZE, (fb_w, fb_h))


# Built once, at import time - the reverse of JS_KEY_MAP, for
# WebWindow._get_key_down()'s Key -> JS code lookup.
_KEY_TO_JS_CODE = {v: k for k, v in JS_KEY_MAP.items()}


class WebMouse(Mouse):
    """Mouse implementation for WebWindow - unlike a native backend's
    Mouse (which polls a live OS/library button state every frame - see
    GLFWMouse.update()), the *source* of truth here is already the async
    JS event listeners WebWindow's constructor wired up; update() just
    diffs against last frame's snapshot of that same state to derive
    pressed/released/dragging, the same as every other Mouse backend
    does from its own polled state."""
    def __init__(self, window: WebWindow):
        super().__init__()
        self.window = window
        self._pressed = [False, False, False]
        self._released = [False, False, False]
        self._down = [False, False, False]
        self._dragging = [False, False, False]
        self._drag_start = [Vector(0, 0)] * 3
        self._double_clicked = [False, False, False]
        self.last_click_time = [-500.0, -500.0, -500.0]
        self.drag_threshold = 4.0
        self.double_click_threshold = 0.4
        self.scroll_delta = Vector(0.0, 0.0)

    def lock_position(self):
        """Requests Pointer Lock on the canvas - the browser equivalent of
        a native cursor-lock (mouse movement keeps reporting deltas with
        the system cursor hidden and pinned in place)."""
        self.window.canvas.requestPointerLock()

    def unlock_position(self):
        """Releases a Pointer Lock previously requested by
        lock_position()."""
        js.document.exitPointerLock()

    def get_pressed(self, button: int) -> bool:
        return self._pressed[button]

    def get_down(self, button: int) -> bool:
        return self._down[button]

    def get_released(self, button: int) -> bool:
        return self._released[button]

    def get_double_click(self, button: int) -> bool:
        return self._double_clicked[button]

    def get_dragging(self, button: int) -> bool:
        return self._dragging[button]

    def get_drag_start(self, button: int, world: bool = False) -> Vector:
        return self._drag_start[button]

    def get_scroll_delta(self) -> Vector:
        """How far the scroll wheel moved this frame - drained from
        `_scroll_accum` (the live, wheel-event-fed accumulator - see
        WebWindow._on_wheel()) into this stable snapshot once per
        update(), the same as GLFWMouse.get_scroll_delta()'s own
        docstring describes for its GLFW callback equivalent. This used
        to return `_scroll_accum` directly, which update() *also* resets
        to zero every frame - whichever ran first each frame, this read
        the reset value, not the accumulated one, so mouse-wheel scroll
        events were silently discarded 100% of the time on web."""
        return self.scroll_delta

    def set_cursor(self, shape: str = "default"):
        """Sets the canvas's CSS `cursor` style - a real implementation
        (unlike Mouse's own concrete no-op default), since every shape
        this engine's UI hover system asks for (see ui/manager.py) has a
        direct standard CSS cursor keyword equivalent."""
        css_cursor = {
            "default": "default", "pointer": "pointer", "text": "text",
            "grab": "grab", "grabbing": "grabbing", "crosshair": "crosshair",
            "wait": "wait", "not_allowed": "not-allowed",
        }.get(shape, "default")
        self.window.canvas.style.cursor = css_cursor

    def hide_cursor(self):
        """Hides the system cursor over the canvas via CSS."""
        self.window.canvas.style.cursor = "none"

    def update(self):
        """Diffs this frame's JS-event-fed button state against last
        frame's to derive pressed/released, and drives drag/double-click
        tracking off real elapsed time (fb.get_time()) - mirroring
        GLFWMouse.update()'s own logic exactly, just against a
        JS-delivered `_mouse_down` instead of a polled one."""
        from FreeBodyEngine import get_time

        self.position = self.window._mouse_pos
        self.world_position = self.position

        scene = get_service('scene_manager')
        active = scene.get_active() if scene else None
        if active is not None and active.camera is not None:
            cam = active.camera
            # `self.position` is in framebuffer pixels (see _on_mousemove) -
            # divide by the matching framebuffer_size, not the CSS `size`,
            # or this drifts from the cursor by the devicePixelRatio factor
            # on any HiDPI tab.
            size = self.window.framebuffer_size
            if size[0] > 0 and size[1] > 0:
                ndc_x = (self.position.x / size[0]) * 2.0 - 1.0
                ndc_y = 1.0 - (self.position.y / size[1]) * 2.0
                import numpy
                clip_pos = (ndc_x, ndc_y, 0.0, 1.0)
                proj_view_inverse = numpy.linalg.inv(cam.proj_matrix @ cam._get_view_mat())
                p = proj_view_inverse @ clip_pos
                p /= p[3]
                self.world_position = Vector(p[0], p[1])

        now = get_time()
        self._pressed = [False, False, False]
        self._released = [False, False, False]
        self._double_clicked = [False, False, False]

        for i in range(3):
            was_down = self._down[i]
            is_down = self.window._mouse_down[i]

            if is_down and not was_down:
                self._pressed[i] = True
                self._drag_start[i] = self.position
                if now - self.last_click_time[i] <= self.double_click_threshold:
                    self._double_clicked[i] = True
                self.last_click_time[i] = now

            if not is_down and was_down:
                self._released[i] = True
                self._dragging[i] = False

            if is_down and not self._dragging[i]:
                if (self.position - self._drag_start[i]).magnitude >= self.drag_threshold:
                    self._dragging[i] = True

            self._down[i] = is_down

        self.scroll_delta = self.window._scroll_accum
        self.window._scroll_accum = Vector(0.0, 0.0)
