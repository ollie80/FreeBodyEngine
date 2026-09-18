"""
FreeBodyEngine created by ollie80
"""

import sys
import signal
from typing import TYPE_CHECKING, Callable, overload

if TYPE_CHECKING:
    from FreeBodyEngine.core.main import Main
    from FreeBodyEngine.core.service import ServiceLocator, Service

_main_object: 'Main' = None

DLL_DIRECTORY = None

DEFAULT_NAME = "FREEBODY_PROJECT"

# flag constants
HEADLESS = "HEADLESS"
DEVMODE = "DEVMODE"
TEST_WINDOW = "TEST_WINDOW"  # fb.set_flag(fb.TEST_WINDOW, True) before init() - see core.window.testwindow.TestWindow
PROJECT_PATH = "PROJECT_PATH"
PROFILER = "PROFILER"
NAME = "NAME"
FORCE_RENDERER = "FORCE_RENDERER"  # e.g. fb.set_flag(fb.FORCE_RENDERER, "gl33") to override graphics.get_renderer()'s auto-detection

MAX_FPS = "MAX_FPS"
MAX_TPS = "MAX_TPS"

ALLOW_DISK_WRITE = "ALLOW_DISK_WRITE"

SUPRESS_WARNINGS = "SUPRESS_WARNINGS"
SUPRESS_ERRORS = "SUPRESS_ERRORS"
SUPRESS_LOGS = "SUPRESS_LOGS"

# events
QUIT = "QUIT"

PRE_FLAGS = {}

def get_flag(key: str, default: any):
    """Gets the value of global flag `key`, or `default` if it isn't set.

    Works both before and after `init()`: before a `Main` exists, flags live
    in the temporary `PRE_FLAGS` store; afterwards they're read from the
    live `Main.flags`, which is seeded from `PRE_FLAGS` on startup."""
    return get_main().flags.get(key, default) if main_exists() else PRE_FLAGS.get(key, default)

def set_flag(key: str, value: any):
    """Sets global flag `key` to `value`.

    Before `init()` creates a `Main`, this writes into the temporary
    `PRE_FLAGS` store (later consumed by `Main.__init__`) instead of a live
    `GlobalFlags`, so flags can be set ahead of engine startup."""
    if main_exists():
        get_main().flags.set(key, value)
    else:
        PRE_FLAGS[key] = value

def _get_pre_flags():
    global PRE_FLAGS
    return PRE_FLAGS

if TYPE_CHECKING:
    from FreeBodyEngine.core.update import UpdatePhase

def register_service_update(phase: 'UpdatePhase', callback: Callable, priority: int = 0):
    """Registers `callback` to run every `phase` of the main update loop.

    Higher `priority` callbacks run first within the same phase - see
    `UpdateCoordinator.register`."""
    get_main().updater.register(phase, callback, priority)

def unregister_service_update(phase: 'UpdatePhase', callback: Callable):
    """Removes a callback previously registered for `phase` with `register_service_update`."""
    get_main().updater.unregister(phase, callback)

def fbquit():
    """Requests an orderly engine shutdown by emitting the QUIT event."""
    emit_event(QUIT)

def get_time():
    """Returns the current engine time in seconds."""
    return get_main().time.get_time()

def register_service(service: 'Service'):
    """Registers `service` with the global service locator, making it
    retrievable afterwards via `get_service(service.name)`."""
    get_service_locator()._register(service)

def unregister_service(name: str):
    """Unregisters and destroys the service registered under `name`."""
    get_service_locator()._unregister(name)

def get_service(name: str) -> 'Service':
    """Returns the registered service named `name`, or None if no such service exists."""
    if service_exists(name):
        return get_service_locator()._get(name)
    else:
        return None

def service_exists(name: str):
    """Returns whether a service named `name` is currently registered."""
    return get_service_locator()._exists(name)

def get_service_locator() -> 'ServiceLocator':
    """Returns the engine's global `ServiceLocator`."""
    return get_main().services

def _set_main(main: 'Main'):
    global _main_object
    _main_object = main

def get_main(throw_error = True):
    """Returns the global `Main` instance.

    Raises:
        RuntimeError: if no `Main` has been created yet and `throw_error`
            is True (the default). With `throw_error=False`, returns None
            instead in that case."""
    global _main_object
    if _main_object == None:
        if throw_error:
            raise RuntimeError("No main object has been created.")
    return _main_object

def main_exists():
    """Returns whether the global `Main` instance has been created yet."""
    global _main_object
    return _main_object != None

def delta() -> float:
    """Get deltatime for the current frame in seconds."""
    return get_main().time.delta_time

def register_event_callback(event_name: str, callable: Callable):
    """Registers `callable` to be invoked whenever `event_name` is emitted.

    A no-op if the "event" service isn't registered yet."""
    print(get_service_locator().services.keys())

    if service_exists("event"):
        get_service('event').register_callback(event_name, callable)

def unregister_event_callback(event_name: str, callable: Callable):
    """Unregisters `callable` from `event_name`, previously registered with
    `register_event_callback`. A no-op if the "event" service isn't registered."""
    if service_exists("event"):
        get_service('event').unregister_callback(event_name, callable)

def register_event(name: str, *categories: str) -> None:
    """Registers a new event named `name`, filed under `categories`.

    A no-op if the "event" service isn't registered yet."""
    if service_exists("event"):
        return get_service('event').register_event(name, *categories)

def unregister_event(name: str) -> None:
    """Unregisters the event named `name`. A no-op if the "event" service isn't registered."""
    if service_exists("event"):
        return get_service('event').unregister_event(name)

def emit_event(name: str, *callback_args, **callback_kwargs) -> None:
    """Emits event `name`, invoking every callback registered on it with the
    given arguments. A no-op if the "event" service isn't registered."""
    if service_exists("event"):
        return get_service('event').emit(name, *callback_args, **callback_kwargs)

def register_event_category(name: str, priority=0) -> None:
    """Registers a new event category named `name` at the given `priority`.

    A no-op if the "event" service isn't registered yet."""
    if service_exists("event"):
        return get_service('event').register_category(name, priority)

def unregister_event_category(name: str) -> None:
    """Unregisters the event category named `name`. A no-op if the "event" service isn't registered."""
    if service_exists("event"):
        return get_service('event').unregister_category(name)

def get_mouse() -> 'Mouse':
    """Returns the registered "mouse" service."""
    return get_service('mouse')

def physics_delta() -> float:
    """Returns the fixed physics timestep in seconds (see `UpdateCoordinator.physics_timestep`)."""
    return get_main().updater.physics_timestep

def warning(msg):
    """Raises an warning.

    Falls back to a plain `print()` if no `Main`/'logger' service exists
    yet - a module can legitimately call this from its own top-level
    import-time code (e.g. utils.fbnjit()'s "numba isn't installed"
    notice, hit whenever a module using it is imported anywhere before
    numba-dependent code runs, not just after fb.init()), and get_service()
    itself requires a live Main to even ask whether 'logger' is
    registered. This used to crash instead (AttributeError on
    `None.warning(...)`, since get_service() returns None rather than
    raising when the service or the Main it needs doesn't exist) -
    surfaced by the web platform specifically (see core/tilemap/
    renderer.py's own comment: numba is never installed there, so this
    fallback path - previously untested on any platform that has numba -
    ran for the first time and crashed the whole import chain instead of
    just printing a warning like every other platform silently never
    exercised this line to notice)."""
    if main_exists() and service_exists('logger'):
        get_service('logger').warning(msg)
    else:
        print(f"[warning] {msg}")

def error(msg):
    """Throws an error. See warning()'s own docstring for why this falls
    back to plain `print()` before a Main/'logger' service exists."""
    if main_exists() and service_exists('logger'):
        get_service('logger').error(msg)
    else:
        print(f"[error] {msg}")

def _handle_signal(signal, frame):
    get_main().quit()

def log(*msg):
    """Logs any number of messages to the console."""
    get_service('logger').log(*msg, color="reset")

from FreeBodyEngine import core
from FreeBodyEngine import audio
from FreeBodyEngine import math
from FreeBodyEngine import net
from FreeBodyEngine import ui
from FreeBodyEngine.core.time import cooldown, physics_cooldown
from FreeBodyEngine.core.input import get_action_pressed, get_action_released, get_action_strength, get_action_vector
from FreeBodyEngine.core.mouse import Mouse
from FreeBodyEngine.utils import add
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

    

    if get_flag(DEVMODE, False):
        from FreeBodyEngine.core.dev import find_project
        find_project()

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
            "_get_pre_flags",
            "load_shader",
            "load_sound",
            "load_sprite",
            "audio"
            'add',
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
