"""
FreeBodyEngine created by ollie80
"""

import sys
import signal
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from FreeBodyEngine.core.main import Main


_main_object: 'Main' = None

def init():
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

def _set_main(main: 'Main'):
    global _main_object
    _main_object = main

def get_main():
    if _main_object == None:
        raise RuntimeError("No main object has been created.")
    return _main_object

def delta() -> float:
    """Returns deltatime for the current frame in seconds."""
    return get_main().time.delta_time

def warning(msg):
    get_main().logger.warning(msg)

def error(msg):
    get_main().logger.error(msg)

def handle_signal(signal, frame):
    get_main().quit()
    sys.exit(0)

def log(*msg):
    get_main().logger.log(*msg, color="reset")

from FreeBodyEngine import core
from FreeBodyEngine import math
# from FreeBodyEngine import net
# from FreeBodyEngine import ui
from FreeBodyEngine.core.files import load_image, load_material, load_sprite, load_shader
from FreeBodyEngine import graphics
from FreeBodyEngine import utils

from FreeBodyEngine.graphics.color import Color as color
from FreeBodyEngine.core.window import create_cursor, set_cursor
from FreeBodyEngine.math import Vector as vector

__all__ = ["utils", "core", "math", "get_main", "_set_main", "load_material", "load_image", "load_shader", "load_sprite", "graphics", "create_cursor", "set_cursor", "warning", "delta", "init", "color", "vector", "log"]



