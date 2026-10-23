"""
FreeBodyEngine created by ollie80
"""

import os

# NOTE: this used to set os.environ.setdefault("PYOPENGL_ERROR_CHECKING",
# "0") here, to skip PyOpenGL's per-call glGetError() sync stall. Reverted
# - on a real EGL backend it crashes at the very first GL call:
# `AttributeError: module 'OpenGL.raw.EGL._errors' has no attribute
# '_error_checker'` (PyOpenGL's error-checking-disabled code path calling
# a private attribute that doesn't exist under EGL on that PyOpenGL
# version - not something worth chasing for the ~2.6% this measured as in
# testing anyway). Set PYOPENGL_ERROR_CHECKING=0 yourself before running,
# outside this codebase, if a GLX/desktop target wants it back.

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
TERMINAL_WINDOW = "TERMINAL_WINDOW"  # fb.set_flag(fb.TERMINAL_WINDOW, True) before init() - see core.window.terminal.TerminalWindow and ui.get_ui_renderer()
NATIVE_UI = "NATIVE_UI"  # fb.set_flag(fb.NATIVE_UI, False) before any UIElement/RootElement is constructed to force the pure-Python ui.element implementation instead of the compiled C++ one - see ui/__init__.py's own resolution logic. Defaults to True everywhere except get_platform() == "web" (no compiled-extension support there at all), and silently falls back to pure-Python if the native module hasn't been built (scripts/build_native.py) even where True.
PROJECT_PATH = "PROJECT_PATH"
PROFILER = "PROFILER"
NAME = "NAME"
FULLSCREEN = "FULLSCREEN"  # fb.set_flag(fb.FULLSCREEN, False) before init() to keep Android's status/navigation bars on screen - see core.window.android.AndroidWindow. Defaults True (a game's expectation); an app wants False. Set for you from [android] fullscreen in fbproject.toml - see build/builder.py.
FORCE_RENDERER = "FORCE_RENDERER"  # e.g. fb.set_flag(fb.FORCE_RENDERER, "gl33") to override graphics.get_renderer()'s auto-detection; "vulkan" forces Vulkan (otherwise chosen automatically when a Vulkan 1.3 GPU is present - see graphics.use_vulkan())
FORCE_GEOMETRY_MODE = "FORCE_GEOMETRY_MODE"  # "native", "pull" or "compute": pins how a geometry shader runs where the backend could choose (Vulkan picks native when the GPU has geometry shaders, else an emulation - see fbusl/geometry.py)

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
    """Seconds since the previous frame - the one to advance anything visual by.

    This is the time between UPDATE/DRAW runs, not between main-loop
    iterations: the loop iterates more often than it draws whenever it can run
    faster than the frame cap, and a per-iteration delta silently loses the
    time from the iterations that did not draw (see
    UpdateCoordinator.update()). Fixed-timestep work belongs on
    `physics_delta()` and the loop's own accumulators, which read
    `time.delta_time` directly.
    """
    return get_main().time.frame_delta_time

def register_event_callback(event_name: str, callable: Callable):
    """Registers `callable` to be invoked whenever `event_name` is emitted.

    A no-op if the "event" service isn't registered yet."""
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
from FreeBodyEngine.core.input import (get_action_pressed, get_action_just_pressed, get_action_released,
                                       get_action_strength, get_action_axis, get_action_vector)
from FreeBodyEngine.core.mouse import Mouse
from FreeBodyEngine.utils import add
from FreeBodyEngine import graphics
from FreeBodyEngine import utils
from FreeBodyEngine.utils import get_platform

from FreeBodyEngine.core.scene import add_scene, set_scene, remove_scene
from FreeBodyEngine.core.window import create_cursor, set_cursor
from FreeBodyEngine.core import input

# The classes a game reaches for, at the top level - `fb.Sprite2D` rather than
# `fb.graphics.sprite.Sprite2D`. The full paths keep working; these are the
# same objects.
from FreeBodyEngine.core.files import load_file, path_exists
from FreeBodyEngine.math import Vector, Vector3, Transform
from FreeBodyEngine.core.node import Node, Node2D, Node3D
from FreeBodyEngine.core.scene import Scene
from FreeBodyEngine.core.camera import Camera2D, Camera3D
from FreeBodyEngine.core.timer import Timer
from FreeBodyEngine.core.input import Key
from FreeBodyEngine.core.collider import (RectangleCollider2D, CircleCollider2D, PolygonCollider2D,
                                          Raycaster2D, cast_ray)
from FreeBodyEngine.core.physics import PhysicsBody
from FreeBodyEngine.core.physics.body import RigidBody2D
from FreeBodyEngine.core.physics.joints import (DistanceJoint2D, SpringJoint2D, RevoluteJoint2D,
                                                WeldJoint2D, TargetJoint2D)
from FreeBodyEngine.core.tilemap.tilemap import Tilemap
from FreeBodyEngine.graphics.color import Color
from FreeBodyEngine.graphics.sprite import Sprite, Sprite2D
from FreeBodyEngine.graphics.mesh2d import MeshNode2D
from FreeBodyEngine.graphics.model.model import Model3D
from FreeBodyEngine.graphics.lighting import (PointLight2D, DirectionalLight2D, SpotLight2D,
                                              PointLight3D, DirectionalLight3D, SpotLight3D)
from FreeBodyEngine.ui import UIManager


def __getattr__(name):
    """`fb.UIElement`/`fb.RootElement` resolve lazily, through `fb.ui` - which
    of the native and pure-Python implementations to use is only decided the
    first time one is asked for (see ui/__init__.py), after flags are set."""
    if name in ("UIElement", "RootElement"):
        return getattr(ui, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")



def init():
    """Initialise FreeBodyEngine"""
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    from FreeBodyEngine.utils import load_dlls
    global DLL_DIRECTORY

    DLL_DIRECTORY = load_dlls()

    # Not gated on DEVMODE: find_project() now decides for itself based on
    # whether an fbproject.toml is actually there, so a project's code
    # directory lands on sys.path whether or not --dev was passed. Gating it
    # on the flag meant every project had to repeat the same sys.path
    # insert in its own main.py to import its own modules without --dev.
    from FreeBodyEngine.core.dev import find_project
    find_project()

    main = core.main.Main()
    register_event(QUIT)

    return main

# What `from FreeBodyEngine import *` brings in. Every name here must exist -
# it listed five loaders that didn't (and ran "audio" and "add" together for
# want of a comma), so the import raised AttributeError. tests/test_api.py
# checks it.
#
# `math` and `input` are left out on purpose: star-importing them would
# replace the standard library's `math` and the builtin `input()` in the
# importing module. They stay reachable as `fb.math` and `fb.input`.
__all__ = [
    # subpackages
    "core", "graphics", "audio", "ui", "net", "utils",
    # engine lifecycle and services
    "init", "get_main", "main_exists", "fbquit", "get_platform",
    "register_service", "unregister_service", "get_service", "service_exists",
    "register_service_update", "unregister_service_update",
    # flags
    "get_flag", "set_flag",
    "HEADLESS", "DEVMODE", "TEST_WINDOW", "TERMINAL_WINDOW", "NATIVE_UI", "PROJECT_PATH",
    "PROFILER", "NAME", "FULLSCREEN", "FORCE_RENDERER", "FORCE_GEOMETRY_MODE",
    "MAX_FPS", "MAX_TPS", "ALLOW_DISK_WRITE", "SUPRESS_WARNINGS", "SUPRESS_ERRORS",
    "SUPRESS_LOGS", "QUIT",
    # events
    "register_event", "unregister_event", "emit_event",
    "register_event_callback", "unregister_event_callback",
    "register_event_category", "unregister_event_category",
    # time
    "delta", "physics_delta", "get_time", "cooldown", "physics_cooldown", "Timer",
    # logging
    "log", "warning", "error",
    # scenes and nodes
    "add", "add_scene", "set_scene", "remove_scene", "Scene",
    "Node", "Node2D", "Node3D", "Camera2D", "Camera3D",
    # files
    "load_file", "path_exists",
    # maths
    "Vector", "Vector3", "Transform",
    # input
    "Key", "get_mouse", "create_cursor", "set_cursor",
    "get_action_pressed", "get_action_just_pressed", "get_action_released",
    "get_action_strength", "get_action_axis", "get_action_vector",
    # physics
    "RectangleCollider2D", "CircleCollider2D", "PolygonCollider2D", "Raycaster2D", "cast_ray",
    "PhysicsBody", "RigidBody2D",
    "DistanceJoint2D", "SpringJoint2D", "RevoluteJoint2D", "WeldJoint2D", "TargetJoint2D",
    "Tilemap",
    # graphics
    "Color", "Sprite", "Sprite2D", "MeshNode2D", "Model3D",
    "PointLight2D", "DirectionalLight2D", "SpotLight2D",
    "PointLight3D", "DirectionalLight3D", "SpotLight3D",
    # ui
    "UIManager", "UIElement", "RootElement",
]
