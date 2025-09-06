"""
FreeBodyEngine created by ollie80
"""

import sys
import signal
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from FreeBodyEngine.core.main import Main
    from FreeBodyEngine.core.service import ServiceLocator, Service



_main_object: 'Main' = None


DLL_DIRECTORY = None

# flag constants
HEADLESS = "HEADLESS"
DEVMODE = "DEVMODE"
PROJECT_PATH = "PROJECT_PATH"
PROFILE_LAUNCH = "PROFILE_LAUNCH"
MAX_FPS = "MAX_FPS"
MAX_TPS = "MAX_TPS"
ALLOW_DISK_WRITE = "ALLOW_DISK_WRITE"
SUPRESS_WARNINGS = "SUPRESS_WARNINGS"
SUPRESS_ERRORS = "SUPRESS_ERRORS"

# events
QUIT = "QUIT"

PRE_FLAGS = {}

def get_flag(key: str, default: any):
    return get_main().flags.get(key, default) if main_exists() else PRE_FLAGS.get(key, default)
    
def set_flag(key: str, value: any):
    if main_exists():
        get_main().flags.set(key, value)
    else:
        PRE_FLAGS[key] = value

def _get_pre_flags():
    global PRE_FLAGS
    return PRE_FLAGS

def register_service_update(phase: str, callback: Callable, priority: int = 0):
    get_main().updater.register(phase, callback, priority)

def unregister_service_update(phase: str, callback: Callable):
    get_main().updater.unregister(phase, callback)

def fbquit():
    emit_event(QUIT)

def get_time():
    return get_main().time.get_time()

def register_service(service: 'Service'):
    get_service_locator()._register(service)

def unregister_service(name: str):
    get_service_locator()._unregister(name)

def get_service(name: str) -> 'Service':
    if service_exists(name):
        return get_service_locator()._get(name)
    else:
        from FreeBodyEngine.core.service import NullService

        return NullService(name)
    
def service_exists(name: str):
    return get_service_locator()._exists(name)

def get_service_locator() -> 'ServiceLocator':
    return get_main().services

def _set_main(main: 'Main'):
    global _main_object
    _main_object = main

def get_main(throw_error = True):
    global _main_object
    if _main_object == None:
        if throw_error:
            raise RuntimeError("No main object has been created.")
    return _main_object

def main_exists():
    global _main_object
    return _main_object != None

def delta() -> float:
    """Get deltatime for the current frame in seconds."""
    return get_main().time.delta_time

def register_event_callback(event_name: str, callable: Callable):
    get_service('event').register_callback(event_name, callable)

def unregister_event_callback(event_name: str, callable: Callable):
    get_service('event').unregister_callback(event_name, callable)

def register_event(name: str, *categories: str) -> None:
    return get_service('event').register_event(name, *categories)

def unregister_event(name: str) -> None:
    return get_service('event').unregister_event(name)

def emit_event(name: str, *callback_args, **callback_kwargs) -> None:
    return get_service('event').emit(name, *callback_args, **callback_kwargs)

def register_event_category(name: str, priority=0) -> None:
    return get_service('event').register_category(name, priority)

def unregister_event_category(name: str) -> None:
    return get_service('event').unregister_category(name)

def get_mouse() -> 'Mouse':
    return get_service('mouse')

def physics_delta() -> float:
    return get_main().updater.physics_timestep

def warning(msg):
    """Raises an warning."""
    get_service('logger').warning(msg)

def error(msg):
    """Throws an error."""
    get_service('logger').error(msg)

def _handle_signal(signal, frame):
    get_main().quit()


def log(*msg):
    """Logs any number of messages to the console."""
    get_service('logger').log(*msg, color="reset")

from FreeBodyEngine import core
from FreeBodyEngine import math
from FreeBodyEngine import net
from FreeBodyEngine import ui
from FreeBodyEngine.core.time import cooldown, physics_cooldown
from FreeBodyEngine.core.input import get_action_pressed, get_action_released, get_action_strength, get_action_vector
from FreeBodyEngine.core.mouse import Mouse
from FreeBodyEngine.utils import load_image, load_material, load_sprite, load_shader, load_sound, load_data, load_toml, load_model
from FreeBodyEngine import graphics
from FreeBodyEngine import utils
from FreeBodyEngine.utils import get_platform

from FreeBodyEngine.core.scene import add_scene, set_scene, remove_scene
from FreeBodyEngine.core.window import create_cursor, set_cursor

def init():
    """Initialise FreeBodyEngine"""
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    from FreeBodyEngine.utils import load_dlls
    global DLL_DIRECTORY

    DLL_DIRECTORY = load_dlls()

    main = core.main.Main()
    register_event(QUIT)

    return main


__all__ = [
            "utils",
            "ui",
            "net",
            "load_material",
            "load_image",
            'cooldown',
            'physics_cooldown',
            "get_pre_flags",
            "load_shader",
            "load_sound",
            "load_sprite",
            "get_platform",
            "core",
            "math",
            "graphics",
            "error",
            "warning",
            'add_scene', 
            'set_scene', 
            'remove_scene',
            "log",
            "get_main",
            "create_cursor",
            "set_cursor",
            "delta",
            "init",
            "get_action_pressed",
            "get_action_released",
            "get_action_strength",
            "get_action_vector",
            "register_service",
            "service_exists",
            "_set_main"
]