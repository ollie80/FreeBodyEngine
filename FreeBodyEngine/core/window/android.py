"""Window backend for Android, running under python-for-android's (p4a's)
"sdl2" bootstrap - see FreeBodyEngine.utils.get_platform()'s own docstring
for how `get_platform()` tells this apart from desktop Linux (`sys.platform`
alone can't).

Unlike Kivy (p4a's other, more common consumer), this doesn't need Kivy at
all - p4a's own docs are explicit that the sdl2 bootstrap works for "Python
apps using other libraries, such as pysdl2 and pyopengl" with no Kivy
involved, which is exactly the shape every other native FreeBodyEngine
backend already has (PySDL2 is also what core/window/headless.py already
uses, just for an invisible dummy-driver window there rather than a real
one). SDL2 itself is what actually creates the Android window/GL surface
and pumps Android's own event loop, wrapped in a normal-looking blocking
main() - core/main.py needs no Android-specific run loop the way
_run_web() exists for Pyodide's requestAnimationFrame model.

Graphics note: the GL context requested here is OpenGL ES 3.0, not desktop
core GL - graphics/gles's renderer (not graphics/gl33's) is what actually
targets this, reusing WebGL2Generator's GLSL ES 300 shader codegen (WebGL2
*is* GLES 3.0) rather than GL33Generator's desktop-only `#version 330`
output.

Known gap: Android's Activity pause/resume lifecycle (app backgrounded,
GL surface potentially destroyed and recreated) isn't handled here yet -
SDL_APP_WILLENTERBACKGROUND/DIDENTERFOREGROUND events arrive through the
same event pump as everything else below, but nothing currently reacts to
them. A backgrounded-then-resumed session may need its GL context/
resources rebuilt in ways this first pass doesn't attempt.
"""
import os

os.environ.setdefault("PYSDL2_DLL_PATH", "")  # p4a's sdl2 bootstrap bundles
# its own libSDL2.so already on Android's native library search path -
# unlike headless.py's desktop use (which points PySDL2 at this engine's
# own vendored DLL), nothing extra needs pointing at here, but PySDL2
# still checks this env var before falling back to its own discovery, so
# an unset (not merely absent) value avoids it trying a desktop-shaped
# search first.

import sdl2

from FreeBodyEngine.core.window import Window, Cursor, WINDOW_RESIZE, FRAMEBUFFER_RESIZE
from FreeBodyEngine.core.window.headless import SDL_KEY_MAP
from FreeBodyEngine.core.mouse import Mouse
from FreeBodyEngine.core.input import Key, KeyCallbackType
from FreeBodyEngine.math import Vector
from FreeBodyEngine import emit_event, error, get_main, get_service, get_time, QUIT
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from FreeBodyEngine.graphics.image import Image

# Reverse of headless.py's own Key -> SDLK_* map - needed here (not there)
# because a real window has to interpret *incoming* SDL_KEYDOWN/UP events
# back into this engine's Key enum, not just look a Key up to poll it.
_SDL_KEY_MAP_REVERSE = {v: k for k, v in SDL_KEY_MAP.items()}

# Only the first 3 buttons - SDL's own numbering (LEFT/MIDDLE/RIGHT) isn't
# in the same order as this engine's 0/1/2 button convention (see
# GLFWWindow's own glfw_mouse_button_map for the same reindexing need).
_SDL_MOUSE_BUTTON_MAP = {
    0: sdl2.SDL_BUTTON_LEFT,
    1: sdl2.SDL_BUTTON_RIGHT,
    2: sdl2.SDL_BUTTON_MIDDLE,
}
_SDL_MOUSE_BUTTON_MAP_REVERSE = {v: k for k, v in _SDL_MOUSE_BUTTON_MAP.items()}

_CHAR_TO_KEY = None


def _get_char_to_key_map():
    """Lazily builds (and caches) the reverse of ui/manager.py's own
    KEY_CHAR_MAP - `{character: (Key, needs_shift)}` - for translating
    SDL_TEXTINPUT's committed text back into the Key-based events
    ui/manager.py's _on_key() expects (see AndroidWindow.update()'s own
    SDL_TEXTINPUT handling). Imported lazily, not at module load time, so
    importing this window backend doesn't also drag in the entire UI
    system before anything's decided this backend is even the one in use."""
    global _CHAR_TO_KEY
    if _CHAR_TO_KEY is None:
        from FreeBodyEngine.ui.manager import KEY_CHAR_MAP
        _CHAR_TO_KEY = {}
        for key, (lower, upper) in KEY_CHAR_MAP.items():
            _CHAR_TO_KEY[lower] = (key, False)
            if upper != lower:
                _CHAR_TO_KEY[upper] = (key, True)
    return _CHAR_TO_KEY


_PRINTABLE_KEYS = None


def _get_printable_keys():
    """Lazily builds (and caches) the set of Key values ui/manager.py's
    KEY_CHAR_MAP covers - every key that produces a plain typed character
    (letters, digits, punctuation, space). Used to suppress AndroidWindow.
    update()'s own SDL_KEYDOWN-driven key_callback for exactly these keys
    while a text field is focused: Android's soft keyboard fires BOTH an
    SDL_KEYDOWN *and* an SDL_TEXTINPUT for the same keystroke on these
    keys (confirmed the hard way - every typed character was appearing
    twice), unlike BACKSPACE/RETURN/arrow keys/etc, which only ever
    arrive as SDL_KEYDOWN and still need to go through that path
    normally."""
    global _PRINTABLE_KEYS
    if _PRINTABLE_KEYS is None:
        from FreeBodyEngine.ui.manager import KEY_CHAR_MAP
        _PRINTABLE_KEYS = set(KEY_CHAR_MAP.keys())
    return _PRINTABLE_KEYS


class AndroidWindow(Window):
    """Window backend built on SDL2's Android support (via p4a's sdl2
    bootstrap) - SDL2 owns window/GL-surface creation and Android's event
    loop; this class translates between SDL2's API and the engine's
    Window/Mouse contracts, the same role GLFWWindow plays for GLFW."""

    def __init__(self, size: tuple[int, int], title: str = "FreeBodyEngine"):
        super().__init__(size, title)
        self.window_type = 'android'
        self._should_close = False

        if sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO | sdl2.SDL_INIT_GAMECONTROLLER) != 0:
            raise RuntimeError(f"SDL_Init failed: {sdl2.SDL_GetError().decode()}")

        sdl2.SDL_GL_SetAttribute(sdl2.SDL_GL_CONTEXT_PROFILE_MASK, sdl2.SDL_GL_CONTEXT_PROFILE_ES)
        sdl2.SDL_GL_SetAttribute(sdl2.SDL_GL_CONTEXT_MAJOR_VERSION, 3)
        sdl2.SDL_GL_SetAttribute(sdl2.SDL_GL_CONTEXT_MINOR_VERSION, 0)
        sdl2.SDL_GL_SetAttribute(sdl2.SDL_GL_DEPTH_SIZE, 24)
        sdl2.SDL_GL_SetAttribute(sdl2.SDL_GL_DOUBLEBUFFER, 1)

        # SDL_WINDOW_FULLSCREEN: there's no windowed mode on Android - the
        # requested `size` is accepted only for contract-shape consistency
        # with every other backend (glfw.py/wayland.py/etc. all take one).
        # SDL_WINDOW_ALLOW_HIGHDPI so framebuffer_size below actually
        # reflects the real panel resolution rather than a scaled-down
        # logical size, the same distinction WebWindow's framebuffer_size
        # already has to make for a HiDPI browser tab.
        self._window = sdl2.SDL_CreateWindow(
            title.encode(),
            sdl2.SDL_WINDOWPOS_UNDEFINED, sdl2.SDL_WINDOWPOS_UNDEFINED,
            size[0], size[1],
            sdl2.SDL_WINDOW_OPENGL | sdl2.SDL_WINDOW_FULLSCREEN | sdl2.SDL_WINDOW_ALLOW_HIGHDPI,
        )
        if not self._window:
            sdl2.SDL_Quit()
            error(f"Failed to create SDL window: {sdl2.SDL_GetError().decode()}")

        self._gl_context = sdl2.SDL_GL_CreateContext(self._window)
        if not self._gl_context:
            error(f"Failed to create GL context: {sdl2.SDL_GetError().decode()}")

        # Written by update()'s event pump below, read by AndroidMouse -
        # same split WebWindow/WebMouse already use (an event-fed source
        # of truth on the window, diffed into press/release/drag state by
        # the Mouse each frame), since SDL's event queue is naturally
        # event-driven the same way JS's DOM events are, unlike GLFW's
        # poll-every-frame model GLFWWindow/GLFWMouse are built around.
        self._mouse_pos = Vector(0.0, 0.0)
        self._mouse_down = [False, False, False]
        self._scroll_accum = Vector(0.0, 0.0)

        # SDL_StartTextInput()/SDL_StopTextInput() is what shows/hides
        # Android's on-screen keyboard - toggled from update() below by
        # polling ui/manager.py's UIManager._focused each frame (only
        # non-None while an *editable* element is focused - see
        # UIManager._handle_mouse()'s own "click anywhere clears focus
        # unless it landed on an editable element" comment), not called
        # unconditionally here: showing it at app startup regardless of
        # whether anything is actually focused made a keyboard flash open
        # immediately and then get dismissed the instant a text field was
        # actually tapped (Android treating that first tap as a
        # dismiss-then-refocus, or similar), instead of only appearing
        # when something is genuinely ready to receive typed text.
        self._text_input_active = False

        # See _get_key_down()'s own comment for why this exists: Android's
        # IME delivers already-shifted/-cased committed text through
        # SDL_TEXTINPUT, not a physical shift key being held, but
        # ui/manager.py's _on_key() derives the character to insert from
        # `window._get_key_down(Key.L_SHIFT)` - this lets update()'s
        # SDL_TEXTINPUT handling below fake that signal for exactly the
        # duration of the one synthesized key-press callback it triggers.
        self._synthetic_shift = False

        # Cache for safe_area_insets below - populated lazily (see that
        # property) since the real value needs a live JNI round-trip
        # (getRootWindowInsets() can also legitimately return null for a
        # few frames at startup, before the decor view has ever been laid
        # out) and, with this app locked to portrait (see buildozer.spec's
        # own `orientation = portrait`), never changes for the rest of the
        # session once it's been read once - no resize/rotation listener
        # needed to invalidate it.
        self._safe_area_insets_cache = None

        # Cache for content_scale below - same "read once via JNI, then
        # never again" reasoning as safe_area_insets, and for basically
        # the same underlying reason too (this is the OS's own display
        # density, which doesn't change mid-session any more than the
        # insets do).
        self._content_scale_cache = None

    def set_title(self, new_title):
        """No real title bar on Android (fullscreen, no window chrome) -
        still forwarded to SDL for whatever it does with it (e.g. the
        recent-apps task-switcher label), same contract as every other
        backend."""
        sdl2.SDL_SetWindowTitle(self._window, new_title.encode())

    @property
    def size(self) -> tuple[int, int]:
        w, h = sdl2.c_int(), sdl2.c_int()
        sdl2.SDL_GetWindowSize(self._window, w, h)
        return (w.value, h.value)

    @size.setter
    def size(self, new: tuple[int, int]):
        """No-op in effect - Android has no windowed resizing - kept only
        so code shared with desktop backends that does set window.size
        doesn't need an Android-specific guard."""
        sdl2.SDL_SetWindowSize(self._window, new[0], new[1])

    @property
    def framebuffer_size(self) -> tuple[int, int]:
        """The real drawable surface size, in pixels - see
        SDL_WINDOW_ALLOW_HIGHDPI above for why this can differ from
        `size`."""
        w, h = sdl2.c_int(), sdl2.c_int()
        sdl2.SDL_GL_GetDrawableSize(self._window, w, h)
        return (w.value, h.value)

    @property
    def content_scale(self) -> float:
        """Overrides Window.content_scale's generic `framebuffer_size[0] /
        size[0]` computation - that formula only produces a real scale
        factor on platforms where the OS actually reports a *different*
        logical window size than the physical framebuffer (a HiDPI/Retina
        display's own "points vs pixels" split). Android's SDL backend
        doesn't have that distinction at all - `SDL_GetWindowSize()` and
        `SDL_GL_GetDrawableSize()` both report the exact same raw display
        pixels - so the generic formula always evaluates to a meaningless
        1.0 here regardless of the device's real screen density, confirmed
        live as this project's single biggest mobile scaling problem:
        every fixed-pixel style value everywhere (buttons, text, icons,
        padding - the whole UI) rendered at its literal raw-pixel size on
        this device's 450dpi/2.8125x-density display instead of the
        comfortable physical size it was actually designed at (against a
        much lower-density desktop monitor) - "everything is tiny",
        project-wide, all from this one silently-wrong number.

        Queried instead from Android's own real, authoritative answer to
        "how many raw pixels make up one density-independent unit" -
        `DisplayMetrics.density` - via pyjnius, exactly the way
        safe_area_insets above already does for the same category of
        Android-only information this engine has no other way to reach.
        This is also, not coincidentally, the same density bucket Android
        itself already designs every app's own UI against (confirmed via
        `adb shell wm density`/`dumpsys window displays` on this exact
        device: a 1080px-wide, 450dpi screen is reported as `sw384dp`
        - 1080 / 2.8125 = 384 - not "1080dp")."""
        if self._content_scale_cache is not None:
            return self._content_scale_cache

        try:
            from jnius import autoclass
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            activity = PythonActivity.mActivity
            density = float(activity.getResources().getDisplayMetrics().density)
        except Exception:
            return 1.0

        if density <= 0:
            return 1.0

        self._content_scale_cache = density
        return density

    @property
    def safe_area_insets(self) -> tuple[float, float, float, float]:
        """(top, right, bottom, left) - see Window.safe_area_insets' own
        docstring for the general contract. Queried from Android's own
        WindowInsets via pyjnius (already a bundled dependency - no new
        native/recipe work needed): `getSystemWindowInsetTop/Right/Bottom/
        Left()` rather than the newer Type-based
        `getInsets(WindowInsets.Type.systemBars())` API, since the former
        has been available since API 20 and this project's own
        `android.minapi` (see buildozer.spec) is 24 - the latter only
        exists from API 30 and would need its own fallback path for
        anything older regardless.

        Cached after the first successful read - see __init__'s own
        comment on `_safe_area_insets_cache` for why that's safe here.
        `getRootWindowInsets()` can legitimately return null for the first
        few frames (the decor view hasn't been laid out by the Android
        side yet) - (0.0, 0.0, 0.0, 0.0) (i.e. "no known unsafe edges yet")
        is returned for as long as that's the case, exactly like every
        other backend's real, permanent default."""
        if self._safe_area_insets_cache is not None:
            return self._safe_area_insets_cache

        try:
            from jnius import autoclass
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            activity = PythonActivity.mActivity
            insets = activity.getWindow().getDecorView().getRootWindowInsets()
            if insets is None:
                return (0.0, 0.0, 0.0, 0.0)

            scale = self.content_scale
            if scale <= 0:
                scale = 1.0

            result = (
                insets.getSystemWindowInsetTop() / scale,
                insets.getSystemWindowInsetRight() / scale,
                insets.getSystemWindowInsetBottom() / scale,
                insets.getSystemWindowInsetLeft() / scale,
            )
        except Exception:
            return (0.0, 0.0, 0.0, 0.0)

        self._safe_area_insets_cache = result
        return result

    @property
    def position(self) -> tuple[int, int]:
        """Always (0, 0) - a fullscreen Android window has no independent
        position to report."""
        return (0, 0)

    @position.setter
    def position(self, new: tuple[int, int]):
        pass

    def is_ready(self) -> bool:
        return not self._should_close

    def _get_key_down(self, key: Key) -> float:
        # See __init__'s own comment on self._synthetic_shift: a
        # SDL_TEXTINPUT-triggered synthetic key-press (see update() below)
        # needs ui/manager.py's _on_key() to see the *correct* shift state
        # for the character the IME already committed, not whatever a
        # (nonexistent, on Android) physical shift key's real state is.
        if self._synthetic_shift and key in (Key.L_SHIFT, Key.R_SHIFT):
            return 1.0

        state = sdl2.SDL_GetKeyboardState(None)
        scancode = sdl2.SDL_GetScancodeFromKey(SDL_KEY_MAP[key])
        return float(state[scancode])

    def _get_gamepad_state(self, id: int):
        """Not yet implemented - SDL_GameController support (a Bluetooth
        controller paired to the device) would go here, the same shape as
        GLFWWindow._get_gamepad_state()'s own button/axis mapping."""
        pass

    def _create_cursor(self, image: 'Image'):
        pass

    def _set_cursor(self, cursor: 'Cursor'):
        pass

    def create_mouse(self):
        """Creates and returns this window's AndroidMouse."""
        return AndroidMouse(self)

    def close(self):
        self._should_close = True
        sdl2.SDL_GL_DeleteContext(self._gl_context)
        sdl2.SDL_DestroyWindow(self._window)
        sdl2.SDL_Quit()
        emit_event(QUIT)

    def draw(self):
        sdl2.SDL_GL_SwapWindow(self._window)

    def update(self):
        """Pumps SDL's event queue for this frame. Touches arrive as
        synthesized SDL_MOUSEBUTTONDOWN/UP/MOTION events by default (SDL's
        own touch-to-mouse emulation, on by default on Android) - a
        genuine second finger/pinch/multitouch gesture isn't captured this
        way (SDL_FINGERDOWN/MOTION/UP are the real multitouch events, not
        read here yet), but every single-touch interaction this engine's
        existing UI/click/drag handling already expects from a Mouse
        works unchanged, for free, without a separate touch code path."""
        input_service = get_service('input')

        event = sdl2.SDL_Event()
        while sdl2.SDL_PollEvent(event):
            if event.type == sdl2.SDL_QUIT:
                get_main().quit()

            elif event.type == sdl2.SDL_WINDOWEVENT:
                if event.window.event in (sdl2.SDL_WINDOWEVENT_RESIZED, sdl2.SDL_WINDOWEVENT_SIZE_CHANGED):
                    emit_event(WINDOW_RESIZE, self.size)
                    emit_event(FRAMEBUFFER_RESIZE, self.framebuffer_size)

            elif event.type in (sdl2.SDL_KEYDOWN, sdl2.SDL_KEYUP):
                key = _SDL_KEY_MAP_REVERSE.get(event.key.keysym.sym)
                # Android's soft keyboard fires both an SDL_KEYDOWN *and*
                # an SDL_TEXTINPUT for the same keystroke on every plain
                # character key (letters/digits/punctuation/space) - only
                # SDL_TEXTINPUT (handled below) is used for those while a
                # text field is focused, or every typed character shows up
                # twice. Non-character keys (BACKSPACE, RETURN, arrows,
                # ...) never generate SDL_TEXTINPUT at all and still need
                # this path regardless of focus state.
                suppressed = self._text_input_active and key in _get_printable_keys()
                if key is not None and input_service is not None and not suppressed:
                    if event.type == sdl2.SDL_KEYDOWN:
                        key_type = KeyCallbackType.REPEAT if event.key.repeat else KeyCallbackType.PRESS
                    else:
                        key_type = KeyCallbackType.RELEASE
                    input_service._key_callback(key, key_type)

            elif event.type == sdl2.SDL_MOUSEMOTION:
                self._mouse_pos = Vector(float(event.motion.x), float(event.motion.y))

            elif event.type in (sdl2.SDL_MOUSEBUTTONDOWN, sdl2.SDL_MOUSEBUTTONUP):
                button = _SDL_MOUSE_BUTTON_MAP_REVERSE.get(event.button.button)
                if button is not None:
                    self._mouse_down[button] = (event.type == sdl2.SDL_MOUSEBUTTONDOWN)

            elif event.type == sdl2.SDL_MOUSEWHEEL:
                # Only relevant with a USB-OTG/Bluetooth mouse attached -
                # matches WebMouse._on_wheel()'s own sign convention
                # (positive y = scrolled up).
                self._scroll_accum += Vector(float(event.wheel.x), float(event.wheel.y))

            elif event.type == sdl2.SDL_TEXTINPUT:
                # The Android on-screen keyboard's actual typing path -
                # see _sync_text_input_visibility() for when the keyboard
                # generating these is actually shown. Unlike a
                # physical keyboard (SDL_KEYDOWN with a scancode
                # identifying *which key*), the IME here hands over
                # already-composed, already-cased UTF-8 text with no
                # concept of "which physical key produced this" at all -
                # bridged back into ui/manager.py's Key-enum-based
                # _on_key() by reverse-looking up each character against
                # the same KEY_CHAR_MAP it uses going the other direction,
                # and faking the shift state that map's second column
                # would have needed (see _get_key_down() and
                # self._synthetic_shift above). Characters with no entry
                # there (e.g. anything outside plain ASCII letters/digits/
                # punctuation) are silently dropped rather than crashing -
                # full Unicode text input isn't something this engine's
                # Key-based text-entry model supports on any platform yet.
                text = event.text.text.split(b"\x00", 1)[0].decode("utf-8", errors="ignore")
                char_to_key = _get_char_to_key_map()
                for char in text:
                    key, needs_shift = char_to_key.get(char, (None, False))
                    if key is None:
                        continue
                    self._synthetic_shift = needs_shift
                    input_service._key_callback(key, KeyCallbackType.PRESS)
                self._synthetic_shift = False

        if self._should_close:
            get_main().quit()

        self._sync_text_input_visibility()

    def _sync_text_input_visibility(self):
        """Shows/hides Android's on-screen keyboard to match whether an
        editable UI element is currently focused - see __init__'s own
        comment on why this is polled here each frame rather than shown
        unconditionally for the process's whole lifetime. `ui` may not be
        registered yet this early (or ever, for a non-UI game), and
        `_focused` is UIManager-internal state with no public accessor -
        both handled the same defensive way."""
        ui = get_service('ui')
        focused = getattr(ui, '_focused', None) is not None if ui is not None else False

        if focused and not self._text_input_active:
            sdl2.SDL_StartTextInput()
            self._text_input_active = True
        elif not focused and self._text_input_active:
            sdl2.SDL_StopTextInput()
            self._text_input_active = False


class AndroidMouse(Mouse):
    """Mouse implementation for AndroidWindow - diffs this frame's
    SDL-event-fed state (see AndroidWindow.update()) against last frame's
    to derive pressed/released/dragging, the same event-fed shape
    WebMouse.update() already uses for the same underlying reason (an
    async/event-pushed input source, not a per-frame-polled one like
    GLFWMouse's)."""

    def __init__(self, window: AndroidWindow):
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

    def get_scroll_delta(self) -> Vector:
        return self.scroll_delta

    def get_pressed(self, button: int) -> bool:
        return self._pressed[button]

    def get_released(self, button: int) -> bool:
        return self._released[button]

    def get_down(self, button: int) -> bool:
        return self._down[button]

    def get_double_click(self, button: int) -> bool:
        return self._double_clicked[button]

    def get_dragging(self, button: int) -> bool:
        return self._dragging[button]

    def get_drag_start(self, button: int, world: bool = False) -> Vector:
        return self._drag_start[button]

    def set_cursor(self, shape: str = "default"):
        pass  # no cursor concept on a touch device

    def hide_cursor(self):
        pass

    def update(self):
        from FreeBodyEngine import get_time as _get_time

        self.position = self.window._mouse_pos
        self.world_position = self.position

        scene = get_service('scene_manager')
        active = scene.get_active() if scene else None
        if active is not None and active.camera is not None:
            cam = active.camera
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

        now = _get_time()
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

        # Snapshot-then-reset, in that order - see WebMouse.get_scroll_delta()'s
        # own docstring for exactly why get_scroll_delta() must read a
        # stable snapshot (this.scroll_delta) rather than the live
        # accumulator: reading the accumulator directly and zeroing it in
        # the same update() meant whichever ran first each frame,
        # scroll consumers always saw the just-reset value, discarding
        # every scroll event silently. Reproducing that exact bug in a
        # brand new backend would be a strange way to relearn it.
        self.scroll_delta = self.window._scroll_accum
        self.window._scroll_accum = Vector(0.0, 0.0)
