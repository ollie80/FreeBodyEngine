from FreeBodyEngine.core.window.generic import Window, Cursor
from FreeBodyEngine.core.window.win32 import Win32Window, Win32Cursor
from FreeBodyEngine.core.window.glfw import GLFWWindow
from FreeBodyEngine import get_main, warning

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from FreeBodyEngine.graphics.image import Image


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




__all__ = ["Window", "Cursor", "Win32Window", "Win32Cursor"]