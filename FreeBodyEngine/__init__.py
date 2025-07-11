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
    """Initialise FreeBodyEngine"""
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

def _set_main(main: 'Main'):
    global _main_object
    _main_object = main

def get_main(throw_error = True):
    if _main_object == None:
        if throw_error:
            raise RuntimeError("No main object has been created.")
        else:
            return None
    return _main_object

def delta() -> float:
    """Get deltatime for the current frame in seconds."""
    return get_main().time.delta_time

def get_mouse():
    return get_main().mouse

def physics_delta() -> float:
    return 1 / get_main().physics_tps

def warning(msg):
    """Raises a warning."""
    get_main().logger.warning(msg)

def error(msg):
    """Throws an error."""
    get_main().logger.error(msg)


def _handle_signal(signal, frame):
    get_main().quit()

def log(*msg):
    """Logs any number of messages to the console."""
    get_main().logger.log(*msg, color="reset")

from FreeBodyEngine import core
from FreeBodyEngine import math
# from FreeBodyEngine import net
# from FreeBodyEngine import ui
from FreeBodyEngine.core.time import cooldown, physics_cooldown
from FreeBodyEngine.core.input import get_action_pressed, get_action_released, get_action_strength, get_vector
from FreeBodyEngine.utils import load_image, load_material, load_sprite, load_shader
from FreeBodyEngine import graphics
from FreeBodyEngine import utils

from FreeBodyEngine.core.window import create_cursor, set_cursor

__all__ = ["utils", "load_material", "load_image", 'cooldown', 'physics_cooldown', "load_shader", "load_sprite", "core", "math", "graphics", "error", "warning", "log", "get_main", "create_cursor", "set_cursor", "delta", "init", "get_action_pressed", "get_action_released", "get_action_strength", "get_vector"]



