"""
FreeBody Engine created by ollie80
"""

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from FreeBodyEngine.core.main import Main

_main_object: 'Main' = None

def _set_main(main: 'Main'):
    global _main_object
    _main_object = main

def get_main():
    if _main_object == None:
        raise RuntimeError("No main object has been created.")
    return _main_object

def delta() -> float:
    """Returns deltatime for the current frame in seconds."""
    return get_main().time.deltatime

def warning(msg):
    get_main().logger.warning(msg)

from FreeBodyEngine import core
from FreeBodyEngine import math
# from FreeBodyEngine import net
# from FreeBodyEngine import ui
from FreeBodyEngine import graphics
from FreeBodyEngine import utils

from FreeBodyEngine.graphics.color import Color as color
from FreeBodyEngine.core.files import load_image
from FreeBodyEngine.core.window import create_cursor, set_cursor


__all__ = [ "graphics", "utils", "core", "math", "get_main", "_set_main", "load_image", "create_cursor", "set_cursor", "warning", "delta", "color"]



