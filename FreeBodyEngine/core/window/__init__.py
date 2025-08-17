from FreeBodyEngine.core.window.generic import Window, Cursor, WINDOW_RESIZE
from FreeBodyEngine import get_main, warning, get_flag, HEADLESS
import sys

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from FreeBodyEngine.graphics.image import Image

def get_window() -> type[Window]:
    """Gets the correct window class for the platform."""
    platform = sys.platform
    
    if get_flag(HEADLESS, False):
        from FreeBodyEngine.core.window.headless import HeadlessWindow
        return HeadlessWindow

    if get_flag("WIN32_WINDOW", False):
        from FreeBodyEngine.core.window.win32 import Win32Window
        return Win32Window
    
    from FreeBodyEngine.core.window.glfw import GLFWWindow
    return GLFWWindow
    
    



def create_cursor(image: 'Image'):
    main = get_main()
    if not main.headless_mode:
        return main.window._create_cursor(image)
    else:
        warning("Cannot create cursor object while in headless mode as it requires a window.")
        return Cursor() # returns a dummy cursor object
    

def set_cursor(cursor: Cursor):
    main = get_main()
    if not main.headless_mode:
        main.window._set_cursor(cursor)
    else:
        warning("Cannot set cursor object while in headless mode as it requires a window.")




__all__ = ["Window", "Cursor", "WINDOW_RESIZE"]