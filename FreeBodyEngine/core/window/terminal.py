"""Terminal window backend (`fb.set_flag(fb.TERMINAL_WINDOW, True)`) -
renders the whole game as colored ASCII art directly in a real terminal,
with real mouse/keyboard input read from that same terminal. POSIX only
(termios/tty) - there's no Windows console equivalent implemented here.

Architecture, in one pass:

  - The actual GPU rendering is completely unchanged: this reuses
    GLFWWindow's own context creation with `visible=False` (the exact
    trick TestWindow already uses for automated screenshot-driven tests -
    see that module's docstring), so PBRPipeline/GL33Renderer/UIRenderer
    all believe they're drawing to a completely normal desktop window.
    Nothing about shaders, meshes, or GL state needed to change at all.

  - `size`/`framebuffer_size` report the real terminal's (columns, rows)
    - not pixels. This is the one deliberate architectural choice
    everything else follows from: since ui/manager.py and every UIElement
    lay out purely in terms of whatever `window.framebuffer_size` reports,
    reporting a terminal's actual character grid there means the *entire*
    existing UI layout/hit-testing/focus system works completely
    unmodified - it just thinks it's rendering to a very small screen,
    and TerminalUIRenderer (ui/terminal_renderer.py) draws each of its
    "pixels" as one real character cell. The trade-off: the 3D/GL world
    content this window reads back each frame is rendered at that same
    tiny native resolution (e.g. 120x40) - there's no supersampling here,
    so world-scene ASCII art will look considerably more blocky than a
    typical "image to ASCII art" converter that downsamples from a much
    higher-resolution source. Worth revisiting if the coarse world output
    matters more than the simplicity of one shared coordinate space.

  - Presentation (world -> ASCII) happens in draw(), which runs on
    UpdatePhase.LATE - after PBRPipeline *and* UIRenderer/
    TerminalUIRenderer have already drawn for this frame (both run on
    UpdatePhase.DRAW, strictly before LATE - see core/update.py). draw()
    reads back the GL framebuffer left behind by the 3D world pass,
    quantizes each pixel to an ASCII_RAMP character by luminance (colored
    via a real 24-bit ANSI foreground escape, not just the character
    glyph - the user asked for real color, not monochrome), then
    composites `self.ui_overlay` (written by TerminalUIRenderer, keyed by
    (column, row)) on top before emitting one batched write to the real
    terminal. UI always wins where both exist, matching every other
    backend's "UI drawn after/over the 3D world" ordering.

  - Input is real terminal I/O, not GLFW's (an invisible window never
    receives real keyboard/mouse events - GLFW's own polling in
    update() is harmless but doesn't do anything useful here). Raw mode
    (termios) is enabled so keys arrive immediately, unbuffered and
    unechoed; ANSI mouse reporting (SGR extended-coordinate mode, with
    motion reporting so hover states work at all) is enabled so clicks/
    drags/hovers/scrolls arrive as escape sequences on the same stdin.
    Both are parsed non-blockingly in update() (UpdatePhase.EARLY, before
    anything else runs this frame) via select() - never blocking the
    frame waiting for a key that isn't there yet.

  - A real terminal has no distinct "key released" signal the way a raw
    scancode-based backend does (SDL/GLFW know exactly when a physical
    key goes up; a terminal only ever tells you a key was typed). See
    _get_key_down()'s own docstring for the approximation used - a real,
    documented limitation, not an oversight.

Known gaps, deliberately not tackled in this first pass: Windows consoles
(no termios/tty equivalent used here), true Unicode text input beyond
KEY_CHAR_MAP's US-QWERTY coverage (same limitation TestWindow.inject_text
already documents), and any supersampling for the 3D-world ASCII output.
"""
import os
import sys
import time
import shutil
import select
import atexit
import signal

try:
    import termios
    import tty
    _HAS_TERMIOS = True
except ImportError:
    # Windows - raw mode/ANSI mouse reporting need a different mechanism
    # (msvcrt/Win32 console APIs) that isn't implemented here. Constructing
    # TerminalWindow still fails loudly later (no terminal size, no raw
    # mode) rather than silently degrading to something broken.
    _HAS_TERMIOS = False

from OpenGL.GL import glReadPixels, GL_RGB, GL_UNSIGNED_BYTE
import numpy as np
import glfw

from FreeBodyEngine.core.window.glfw import GLFWWindow
from FreeBodyEngine.core.mouse import Mouse
from FreeBodyEngine.core.input import Key, KeyCallbackType
from FreeBodyEngine.math import Vector
from FreeBodyEngine import get_service, get_main, warning

# Dark -> light, by normalized luminance. The classic ramp used by every
# "image to ASCII art" tool going back decades - kept short and simple
# rather than a longer 70-character ramp, since most terminal fonts can't
# actually distinguish much more than this many distinct "densities" at a
# glance anyway.
ASCII_RAMP = " .:-=+*#%@"

# What one terminal cell stands for, in notional pixels, for `size`. A cell
# is about twice as tall as it is wide in every common terminal font, and
# that ratio is the part that matters - the absolute scale only sets what a
# game's zoom means, and 8x16 puts a typical 120x40 terminal at 960x640,
# which is a normal window size.
CELL_PIXELS = (8, 16)

# Non-printable keys' well-known ANSI sequences in raw mode. Covers the
# handful essentially every terminal emulator agrees on (arrows, home/end,
# delete) - not a full terminfo/curses-level parse, which this doesn't
# need for a first pass.
_ESCAPE_SEQUENCE_KEYS = {
    "\x1b[A": Key.UP, "\x1bOA": Key.UP,
    "\x1b[B": Key.DOWN, "\x1bOB": Key.DOWN,
    "\x1b[C": Key.RIGHT, "\x1bOC": Key.RIGHT,
    "\x1b[D": Key.LEFT, "\x1bOD": Key.LEFT,
    "\x1b[H": Key.HOME, "\x1b[1~": Key.HOME, "\x1bOH": Key.HOME,
    "\x1b[F": Key.END, "\x1b[4~": Key.END, "\x1bOF": Key.END,
    "\x1b[3~": Key.DELETE,
}

_SINGLE_BYTE_KEYS = {
    "\r": Key.RETURN, "\n": Key.RETURN,
    "\x7f": Key.BACKSPACE, "\x08": Key.BACKSPACE,
    "\t": Key.TAB,
}

# How long a key is reported as "still down" (_get_key_down()) after its
# last observed repeat, with no real key-up signal to go on - see that
# method's own docstring.
_KEY_DOWN_GRACE_PERIOD = 0.3

_CHAR_TO_KEY = None


def _get_char_to_key_map():
    """Lazily builds (and caches) the reverse of ui/manager.py's own
    KEY_CHAR_MAP - `{character: (Key, needs_shift)}`. A terminal in raw
    mode, like Android's IME (see core/window/android.py's own identical
    helper), delivers already-composed characters, not physical scancodes
    - typing a capital letter sends the literal capital byte, not a
    shift-modifier bit alongside a base key - so reverse-mapping the
    received character straight to (Key, needs_shift) and faking that
    shift state (see AndroidWindow._synthetic_shift's docstring for the
    same trick, reused verbatim here) is both correct and simpler than
    trying to track "real" modifier-key state that raw terminal input
    doesn't actually provide."""
    global _CHAR_TO_KEY
    if _CHAR_TO_KEY is None:
        from FreeBodyEngine.ui.manager import KEY_CHAR_MAP
        _CHAR_TO_KEY = {}
        for key, (lower, upper) in KEY_CHAR_MAP.items():
            _CHAR_TO_KEY[lower] = (key, False)
            if upper != lower:
                _CHAR_TO_KEY[upper] = (key, True)
    return _CHAR_TO_KEY


class TerminalWindow(GLFWWindow):
    """See module docstring. `window_type` stays 'glfw' deliberately, for
    the same reason TestWindow's does - the renderer's own context-
    selection code only special-cases 'wayland'/'x11'/'win32', so this
    rides the same default GL path a real GLFWWindow already uses, with
    no renderer changes needed for the 3D world content."""

    def __init__(self, size: tuple[int, int], title: str = "FreeBodyEngine"):
        if not _HAS_TERMIOS:
            raise RuntimeError(
                "TerminalWindow requires a POSIX terminal (termios/tty) - "
                "not implemented for Windows consoles."
            )

        super().__init__(size, title, visible=False)

        columns, rows = shutil.get_terminal_size(fallback=(80, 24))
        self._columns = columns
        self._rows = rows
        # The GL side draws at full pixel resolution; only presentation is
        # per-cell. Without this the context stays at whatever `size` was
        # passed in and never matches what framebuffer_size reports.
        glfw.set_window_size(self._window, *self.size)

        # The real terminal emulator can be resized by the user at any
        # time, unlike a real OS window there's no GLFW/window-manager
        # event for that - the kernel delivers SIGWINCH to the foreground
        # process instead. The handler only sets a flag (signal handlers
        # can't safely do real work); _apply_pending_resize(), called from
        # update() once per frame, does the actual work of re-reading the
        # terminal size and forwarding it to the underlying (invisible)
        # GLFW window via glfw.set_window_size() - which reuses
        # GLFWWindow's own already-registered size callback (see
        # GLFWWindow.__init__'s set_window_size_callback) to fire the
        # exact same WINDOW_RESIZE/FRAMEBUFFER_RESIZE events a real
        # on-screen resize would, so PBRPipeline/Renderer's existing
        # FRAMEBUFFER_RESIZE subscriptions resize main_framebuffer/the GL
        # viewport without this window needing to know anything about
        # either of those.
        self._resize_pending = False
        signal.signal(signal.SIGWINCH, self._on_sigwinch)

        self._stdin_fd = sys.stdin.fileno()
        self._old_termios = termios.tcgetattr(self._stdin_fd)
        tty.setraw(self._stdin_fd)
        # setraw() disables ISIG along with everything else - re-enabled
        # so Ctrl+C still interrupts the process. Without this, a hung or
        # runaway session has no keyboard escape hatch at all.
        attrs = termios.tcgetattr(self._stdin_fd)
        attrs[3] |= termios.ISIG
        termios.tcsetattr(self._stdin_fd, termios.TCSANOW, attrs)

        # 1000/1002: click + button-drag reporting. 1003: *all* motion,
        # even with no button held - needed for hover states to work at
        # all (ui/manager.py's ElementStates.HOVER), at the cost of a much
        # chattier input stream, which every terminal this was written
        # against (kitty included) handles fine. 1006: SGR extended
        # coordinates - unambiguous to parse and not capped at 223
        # columns/rows the way the older X10 encoding is.
        sys.stdout.write("\x1b[?1000h\x1b[?1002h\x1b[?1003h\x1b[?1006h")
        sys.stdout.write("\x1b[?25l")  # hide the real terminal cursor
        sys.stdout.write("\x1b[2J")  # clear once up front
        sys.stdout.flush()

        self._restored = False
        atexit.register(self._restore_terminal)

        self._mouse_pos = Vector(0.0, 0.0)
        self._mouse_down = [False, False, False]
        self._scroll_accum = Vector(0.0, 0.0)

        self._synthetic_shift = False
        self._key_down_until: dict[Key, float] = {}

        self._stdin_buffer = ""

        # Written by TerminalUIRenderer.draw(), read (and cleared) by this
        # window's own draw() each frame - keyed by (column, row), valued
        # (char, (r, g, b) 0-255 foreground, (r, g, b) 0-255 background or
        # None). The one piece of shared, backend-specific state
        # TerminalUIRenderer needs that isn't already on the generic
        # UIElement/Window contract - the same "window owns a buffer,
        # something else feeds it" shape AndroidWindow's own
        # _mouse_pos/_mouse_down/_scroll_accum already use.
        self.ui_overlay: dict[tuple[int, int], tuple[str, tuple, tuple | None]] = {}

    def _restore_terminal(self):
        """Undoes every terminal-global change made in __init__ - mouse
        reporting, hidden cursor, raw mode. Registered with atexit (not
        just called from close()) so a crash mid-session still leaves the
        user's real terminal usable afterward instead of stuck in raw
        mode with the cursor hidden and mouse-report garbage printing on
        every click."""
        if self._restored:
            return
        self._restored = True
        try:
            sys.stdout.write("\x1b[?1000l\x1b[?1002l\x1b[?1003l\x1b[?1006l")
            sys.stdout.write("\x1b[?25h")
            sys.stdout.write("\x1b[0m\n")
            sys.stdout.flush()
            termios.tcsetattr(self._stdin_fd, termios.TCSADRAIN, self._old_termios)
        except Exception:
            pass  # best-effort - the process is on its way out either way

    def create_mouse(self):
        """Returns a TerminalMouse instead of a real GLFWMouse - see that class."""
        return TerminalMouse(self)

    def _on_sigwinch(self, signum, frame):
        self._resize_pending = True

    def _apply_pending_resize(self):
        """Re-reads the real terminal's size and, if it actually changed,
        forwards it to the underlying invisible GLFW window - see the
        SIGWINCH comment in __init__ for why this is deferred out of the
        signal handler and how the resize actually propagates from
        there."""
        if not self._resize_pending:
            return
        self._resize_pending = False

        columns, rows = shutil.get_terminal_size(fallback=(self._columns, self._rows))
        if (columns, rows) == (self._columns, self._rows):
            return

        self._columns, self._rows = columns, rows
        glfw.set_window_size(self._window, *self.size)
        sys.stdout.write("\x1b[2J")  # old frame was a different size - drop its leftover glyphs
        sys.stdout.flush()

    @property
    def size(self) -> tuple[int, int]:
        """The drawable area in *pixels* - not the character grid.

        `framebuffer_size` is the character grid; this is deliberately not.
        A camera builds its projection from this property (see
        Camera._update_projection_matrix), so reporting cells here made a
        game's zoom mean something entirely different from every other
        backend. A game picking `zoom = 8` for a 960-pixel-wide window got a
        fifteen-world-unit view in a 120-column terminal - less than a single
        16-unit tile, stretched across the whole screen, which is not
        recognisable as the game at all.

        One cell stands for CELL_PIXELS. Its 1:2 ratio is what keeps squares
        square: 120x40 cells reports as 960x640 pixels (aspect 1.5), and 120
        cells wide by 40 cells of double height is also 1.5, so the
        projection and the thing it is eventually displayed on agree.
        """
        return (self._columns * CELL_PIXELS[0], self._rows * CELL_PIXELS[1])

    @size.setter
    def size(self, new: tuple[int, int]):
        pass  # a terminal's size is controlled by the user's terminal emulator, not this window

    @property
    def framebuffer_size(self) -> tuple[int, int]:
        """The drawable area in pixels - the same as `size` here.

        Was the character grid, which made this backend a special case for
        everything that reads it: the UI laid out in cells (ui/manager.py
        sizes its root from this), so an app authored in pixels came out
        roughly ten times too large and its buttons' own padding swallowed
        their labels, and the graphics pipeline built its framebuffer at
        120x40, so the world and any custom pipeline - phonon's audio
        visualizer among them - were rendered at that.

        Now everything upstream of presentation works in ordinary pixels and
        the character grid exists only at the very end, in draw(), where the
        finished frame is averaged down into cells. That is the one place a
        terminal is actually different from a window.
        """
        return self.size

    def _get_key_down(self, key: Key) -> float:
        """Approximates "is this key currently held" from raw terminal
        input, which has no real key-up event at all - only "a key was
        typed" (and, if held on real hardware, typematic repeats of that
        same byte arriving every so often). This reports a key as "down"
        for a short grace period after its last observed press/repeat,
        decaying to "up" if nothing further arrives - close enough for
        ui/manager.py's own only real caller (_on_key()'s Ctrl/shift
        checks), but a poor fit for anything expecting true continuous-
        held-key semantics (WASD-style movement polling, say) - a real,
        inherent limitation of terminal input, not a bug to fix here."""
        if self._synthetic_shift and key in (Key.L_SHIFT, Key.R_SHIFT):
            return 1.0
        until = self._key_down_until.get(key)
        return 1.0 if until is not None and time.monotonic() < until else 0.0

    def _mark_key_down(self, key: Key):
        self._key_down_until[key] = time.monotonic() + _KEY_DOWN_GRACE_PERIOD

    # -- input: real terminal stdin -----------------------------------------

    def update(self):
        """Pumps GLFW's own event queue first (harmless housekeeping for
        the invisible window - see the module docstring), then drains
        whatever's currently waiting on the real terminal's stdin,
        non-blockingly, and dispatches it as key/mouse events."""
        super().update()

        self._apply_pending_resize()

        input_service = get_service('input')

        while True:
            ready, _, _ = select.select([self._stdin_fd], [], [], 0)
            if not ready:
                break
            chunk = os.read(self._stdin_fd, 4096)
            if not chunk:
                break
            self._stdin_buffer += chunk.decode("utf-8", errors="replace")

        self._process_stdin_buffer(input_service)

    def _process_stdin_buffer(self, input_service):
        buf = self._stdin_buffer
        i = 0
        n = len(buf)

        while i < n:
            ch = buf[i]

            if ch == "\x1b":
                # Could be a lone ESC keypress, or the start of a longer
                # escape sequence (arrow key, SGR mouse report, ...) -
                # only decidable by looking ahead. If the buffer doesn't
                # yet hold a full sequence, stop here and wait for the
                # next update() to bring the rest - never guess.
                consumed, handled = self._try_consume_escape(buf, i, input_service)
                if consumed == 0:
                    break  # incomplete - wait for more bytes next frame
                i += consumed
                continue

            if ch in _SINGLE_BYTE_KEYS:
                key = _SINGLE_BYTE_KEYS[ch]
                self._mark_key_down(key)
                if input_service is not None:
                    input_service._key_callback(key, KeyCallbackType.PRESS)
                i += 1
                continue

            entry = _get_char_to_key_map().get(ch)
            if entry is not None and input_service is not None:
                key, needs_shift = entry
                self._mark_key_down(key)
                self._synthetic_shift = needs_shift
                input_service._key_callback(key, KeyCallbackType.PRESS)
                self._synthetic_shift = False

            i += 1

        self._stdin_buffer = buf[i:]

    def _try_consume_escape(self, buf: str, start: int, input_service) -> tuple[int, bool]:
        """Attempts to parse one escape sequence starting at `buf[start]`
        (which is always '\\x1b'). Returns (bytes_consumed, handled) -
        `bytes_consumed == 0` means the buffer doesn't hold a complete
        sequence yet (caller stops and waits for more input)."""
        remaining = buf[start:]

        if remaining.startswith("\x1b[<"):
            # SGR mouse report: ESC [ < Cb ; Cx ; Cy (M|m)
            end = None
            for j, c in enumerate(remaining):
                if c in ("M", "m"):
                    end = j
                    break
            if end is None:
                return (0, False)  # incomplete
            self._handle_sgr_mouse(remaining[:end + 1])
            return (end + 1, True)

        # Fixed, known non-printable-key sequences, longest first so e.g.
        # "\x1b[1~" isn't mistaken for a truncated "\x1b[H"-style match.
        for seq, key in sorted(_ESCAPE_SEQUENCE_KEYS.items(), key=lambda kv: -len(kv[0])):
            if remaining.startswith(seq):
                self._mark_key_down(key)
                if input_service is not None:
                    input_service._key_callback(key, KeyCallbackType.PRESS)
                return (len(seq), True)

        if len(remaining) == 1:
            return (0, False)  # only the ESC byte so far - could be the start of any of the above

        # A genuine standalone ESC (nothing recognizable follows).
        self._mark_key_down(Key.ESCAPE)
        if input_service is not None:
            input_service._key_callback(Key.ESCAPE, KeyCallbackType.PRESS)
        return (1, True)

    def _handle_sgr_mouse(self, seq: str):
        """Parses one SGR mouse report (see __init__'s mouse-mode escapes)
        and updates this window's mouse state - read and diffed into
        press/release/drag by TerminalMouse.update() each frame, the same
        event-fed pattern AndroidWindow/WebWindow already use."""
        is_release = seq[-1] == "m"
        body = seq[3:-1]  # strip the "\x1b[<" prefix and trailing M/m
        parts = body.split(";")
        if len(parts) != 3:
            return
        try:
            cb, cx, cy = int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError:
            return

        # 1-based terminal coordinates -> 0-based cell coordinates,
        # matching every other backend's top-left-origin pixel convention
        # (here, one "pixel" is one character cell - see the module
        # docstring).
        self._mouse_pos = Vector(float(cx - 1), float(cy - 1))

        if cb & 64:
            # Scroll wheel - never has a matching release event, and
            # doesn't touch button state at all. Matches WebMouse's own
            # sign convention (positive y = scrolled up).
            self._scroll_accum += Vector(0.0, -1.0 if (cb & 1) else 1.0)
            return

        if cb & 32:
            return  # plain motion/hover with no button transition - position is already updated above

        button = cb & 3
        if button > 2:
            return  # an SGR button code this doesn't recognize - ignore rather than guess
        self._mouse_down[button] = not is_release

    def draw(self):
        """Presents the frame: reads back the GL framebuffer the 3D world
        pass already rendered (at this window's own tiny native
        resolution - see the module docstring), quantizes it to colored
        ASCII, composites TerminalUIRenderer's overlay on top, and writes
        the whole thing to the real terminal in one batched call."""
        glfw.make_context_current(self._window)

        width, height = self._columns, self._rows
        pixel_w, pixel_h = self.size

        # Read the frame at its real resolution and average each cell's block
        # of pixels down to one colour. The world used to be *rendered* at the
        # character grid - one pixel per cell, nothing to average - which made
        # everything upstream of here a special case and threw away the detail
        # a downsample keeps. A box filter over CELL_PIXELS is cheap (one
        # reshape and one mean) and is what makes album art and a shader
        # visualizer legible as cells rather than noise.
        raw = glReadPixels(0, 0, pixel_w, pixel_h, GL_RGB, GL_UNSIGNED_BYTE)
        frame = np.frombuffer(raw, dtype=np.uint8).reshape(pixel_h, pixel_w, 3)
        # GL's origin is bottom-left and a terminal's is top-left, so the
        # whole buffer is flipped once here rather than per row.
        frame = frame[::-1]
        cell_w, cell_h = CELL_PIXELS
        cells = (frame.reshape(height, cell_h, width, cell_w, 3)
                      .mean(axis=(1, 3))
                      .astype(np.uint8))
        luminance = (0.299 * cells[..., 0] + 0.587 * cells[..., 1]
                     + 0.114 * cells[..., 2]) / 255.0
        ramp_index = np.minimum(len(ASCII_RAMP) - 1,
                                (luminance * len(ASCII_RAMP)).astype(int))

        out = ["\x1b[H"]  # cursor home - overwrite in place, no full clear (avoids visible flicker)
        last_fg = None
        last_bg = None

        for row in range(height):
            for col in range(width):
                overlay_cell = self.ui_overlay.get((col, row))
                if overlay_cell is not None:
                    char, fg, bg = overlay_cell
                else:
                    pixel = cells[row, col]
                    char = ASCII_RAMP[ramp_index[row, col]]
                    fg = (int(pixel[0]), int(pixel[1]), int(pixel[2]))
                    bg = None

                if fg != last_fg:
                    out.append(f"\x1b[38;2;{fg[0]};{fg[1]};{fg[2]}m")
                    last_fg = fg
                if bg != last_bg:
                    out.append("\x1b[49m" if bg is None else f"\x1b[48;2;{bg[0]};{bg[1]};{bg[2]}m")
                    last_bg = bg

                out.append(char)
            out.append("\x1b[0K")  # clear to end of line (handles a narrower previous frame)
            if row != height - 1:
                out.append("\r\n")
                last_fg = last_bg = None  # SGR state doesn't reliably survive a fresh line in every terminal

        sys.stdout.write("".join(out))
        sys.stdout.flush()

        self.ui_overlay = {}

    def close(self):
        self._restore_terminal()
        super().close()


class TerminalMouse(Mouse):
    """Mouse implementation for TerminalWindow - diffs this frame's
    ANSI-mouse-report-fed state (see TerminalWindow._handle_sgr_mouse())
    against last frame's to derive pressed/released/dragging, the same
    event-fed shape WebMouse/AndroidMouse already use for the same
    underlying reason (an async/event-pushed input source, not a per-
    frame-polled one like GLFWMouse's)."""

    def __init__(self, window: TerminalWindow):
        super().__init__()
        self.window = window
        self._pressed = [False, False, False]
        self._released = [False, False, False]
        self._down = [False, False, False]
        self._dragging = [False, False, False]
        self._drag_start = [Vector(0, 0)] * 3
        self.scroll_delta = Vector(0.0, 0.0)

    def lock_position(self):
        pass  # no concept of a locked/captured cursor in a terminal

    def unlock_position(self):
        pass

    def get_scroll_delta(self) -> Vector:
        return self.scroll_delta

    def get_pressed(self, button: int) -> bool:
        return self._pressed[button]

    def get_released(self, button: int) -> bool:
        return self._released[button]

    def get_down(self, button: int) -> bool:
        return self._down[button]

    def get_double_click(self, button: int) -> bool:
        return False  # not tracked yet - real terminal click timing is coarse enough that this wasn't worth building for a first pass

    def get_dragging(self, button: int) -> bool:
        return self._dragging[button]

    def get_drag_start(self, button: int, world: bool = False) -> Vector:
        return self._drag_start[button]

    def set_cursor(self, shape: str = "default"):
        pass  # no system cursor to shape in a terminal

    def hide_cursor(self):
        pass  # already hidden for the whole session - see TerminalWindow.__init__

    def update(self):
        self.position = self.window._mouse_pos
        self.world_position = self.position

        self._pressed = [False, False, False]
        self._released = [False, False, False]

        for i in range(3):
            was_down = self._down[i]
            is_down = self.window._mouse_down[i]

            if is_down and not was_down:
                self._pressed[i] = True
                self._drag_start[i] = self.position

            if not is_down and was_down:
                self._released[i] = True
                self._dragging[i] = False

            if is_down and not self._dragging[i] and self.position != self._drag_start[i]:
                self._dragging[i] = True

            self._down[i] = is_down

        # Snapshot-then-reset, in that order - see WebMouse.get_scroll_delta()'s
        # own docstring for exactly why (reading the live accumulator
        # directly, then zeroing it in the same update(), means whichever
        # runs first each frame, consumers only ever see the just-reset
        # zero value).
        self.scroll_delta = self.window._scroll_accum
        self.window._scroll_accum = Vector(0.0, 0.0)
