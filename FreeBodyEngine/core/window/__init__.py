from FreeBodyEngine.core.window.generic import Window, Cursor, WINDOW_RESIZE, FRAMEBUFFER_RESIZE
from FreeBodyEngine import get_main, warning, get_flag, HEADLESS, TEST_WINDOW, TERMINAL_WINDOW
import sys
import os

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from FreeBodyEngine.graphics.image import Image

def get_window() -> type[Window]:
    """Gets the correct window class for the platform."""
    platform = sys.platform

    if platform == "emscripten":
        # Running under Pyodide, inside an actual browser tab - see
        # utils.get_platform()'s docstring for why `sys.platform` reports
        # this. Checked first, before every other flag/platform branch
        # below: none of GLFW/Wayland/X11/Win32/SDL2 (headless) even
        # import successfully here (they wrap native libraries that don't
        # exist inside the WASM sandbox), so this can't fall through to
        # them the way a misconfigured flag on a real desktop might.
        from FreeBodyEngine.core.window.web import WebWindow
        return WebWindow

    if "ANDROID_ARGUMENT" in os.environ:
        # Checked unconditionally, with no `platform == "linux"`
        # precondition - see utils.get_platform()'s own docstring for why
        # that precondition was actually wrong (confirmed on a real
        # device: it isn't safe to assume p4a's CPython build always
        # reports plain `sys.platform == "linux"`). Checked before every
        # other branch below regardless of what `sys.platform` turns out
        # to be, so Android can never fall through into a desktop Wayland/
        # X11 branch and try to import bindings that don't exist there.
        from FreeBodyEngine.core.window.android import AndroidWindow
        return AndroidWindow

    if get_flag("GLFW_WINDOW", False):
        from FreeBodyEngine.core.window.glfw import GLFWWindow

    elif get_flag(TEST_WINDOW, False):
        # A real, GL-rendering GLFW window that's simply never made
        # visible - lets automated tests drive/screenshot a session
        # without a real window ever appearing (see testwindow.py's
        # module docstring). Checked before HEADLESS: that flag means no
        # GL context at all, which is the opposite of what testing the
        # actual rendered UI needs.
        from FreeBodyEngine.core.window.testwindow import TestWindow
        return TestWindow

    elif get_flag(TERMINAL_WINDOW, False):
        # Also a real, GL-rendering (but never natively shown) GLFW window
        # under the hood - same trick TestWindow uses - except the actual
        # *presentation* is a from-scratch terminal renderer (framebuffer
        # readback -> ASCII art) and input comes from the real terminal
        # (raw mode + ANSI mouse reporting) instead of injected test
        # values. See core.window.terminal's own module docstring.
        from FreeBodyEngine.core.window.terminal import TerminalWindow
        return TerminalWindow

    elif get_flag(HEADLESS, False):
        from FreeBodyEngine.core.window.headless import HeadlessWindow
        return HeadlessWindow

    elif get_flag("WIN32_WINDOW", False):
        from FreeBodyEngine.core.window.win32 import Win32Window
        return Win32Window
    
    elif platform == 'linux':
        if bool(os.environ.get("WAYLAND_DISPLAY")):
            if get_flag("FORCE_X11", False):
                from FreeBodyEngine.core.window.x11 import X11Window
                return X11Window
            else:
                from FreeBodyEngine.core.window.wayland import WaylandWindow 
                return WaylandWindow
        else:    
            from FreeBodyEngine.core.window.x11 import X11Window
            return X11Window
    from FreeBodyEngine.core.window.glfw import GLFWWindow
    return GLFWWindow 

def create_cursor(image: 'Image'):
    """Creates a platform cursor from `image` via the active window backend, or a dummy Cursor in headless mode."""
    main = get_main()
    if not main.headless_mode:
        return main.window._create_cursor(image)
    else:
        warning("Cannot create cursor object while in headless mode as it requires a window.")
        return Cursor() # returns a dummy cursor object


def set_cursor(cursor: Cursor):
    """Sets the active window's cursor to `cursor`; warns and does nothing in headless mode."""
    main = get_main()
    if not main.headless_mode:
        main.window._set_cursor(cursor)
    else:
        warning("Cannot set cursor object while in headless mode as it requires a window.")




__all__ = ["Window", "Cursor", "WINDOW_RESIZE", "FRAMEBUFFER_RESIZE"]
