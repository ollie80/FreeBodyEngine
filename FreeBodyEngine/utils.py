from FreeBodyEngine import get_main, warning, get_flag, get_service
from typing import Literal, overload

def get_platform() -> Literal['win32', 'darwin', 'linux', 'web']:
    """Returns the identifier for the current host platform, or None if it
    isn't one of the ones recognized here (other platforms - e.g. mobile,
    console - aren't handled yet).

    `sys.platform` reports `"emscripten"` under Pyodide (a browser tab
    running this engine compiled to WASM - see core/window/web.py) -
    normalized to `"web"` here so the rest of the engine (graphics.
    get_renderer(), core/window/__init__.py's get_window()) has one
    consistent name to branch on instead of every call site needing to
    know the raw `sys.platform` string Pyodide happens to report."""
    sys_plat = sys.platform
    if sys_plat in ['win32', 'darwin', 'linux']:
        return sys_plat
    if sys_plat == 'emscripten':
        return 'web'
    # handle stuff like android, IOs, console

def abstractmethod(func):
    """Decorator marking a method as abstract: the decorated method always
    raises `NotImplementedError` when called, naming both the method and
    the instance's class - `func`'s own body is never executed, regardless
    of what it contains."""
    def wrapper(*args, **kwargs):
        """Raises `NotImplementedError` naming both `func` and the calling instance's class, instead of running `func`'s own body."""
        cls_name = args[0].__class__.__name__
        raise NotImplementedError(f"Method '{func.__name__}' is not implemented on '{cls_name}'.")
    return wrapper

import sys
import os
import platform
from pathlib import Path

def load_dlls():
    """Locates this engine's bundled native library directory for the
    current platform/architecture (under `sys._MEIPASS` when running as a
    PyInstaller-frozen build, else next to the installed package) and adds
    it to the OS's dynamic library search path (`os.add_dll_directory` on
    Windows, `DYLD_LIBRARY_PATH` on macOS, `LD_LIBRARY_PATH` on Linux).
    Returns the resolved directory.

    Raises:
        RuntimeError: if the host platform isn't win32/darwin/linux/web.
        FileNotFoundError: if the expected library directory doesn't exist."""
    system = sys.platform
    arch = platform.machine()

    # A WASM binary running inside the browser sandbox (Pyodide) can't
    # dynamically load a desktop shared library at all - there's no
    # concept of an OS-level dynamic linker search path to extend, and
    # nothing under lib/windows|macos|linux would even load if there
    # were. No-op instead of raising: fb.init() calls this unconditionally
    # regardless of platform, and a *native* dependency this engine has
    # anywhere (PyOpenGL, SDL2) simply isn't imported on the web code path
    # in the first place (see core.window.web/graphics.webgl), so there's
    # nothing this actually needed to find here.
    if system == "emscripten":
        return None

    if system == "win32":
        arch_folder = "x64" if sys.maxsize > 2**32 else "x86"
        lib_subpath = f"FreeBodyEngine/lib/windows/{arch_folder}"
    elif system == "darwin":
        arch_folder = "arm64" if arch == "arm64" else "x86_64"
        lib_subpath = f"FreeBodyEngine/lib/macos/{arch_folder}"
    elif system.startswith("linux"):
        arch_folder = "x64" if sys.maxsize > 2**32 else "x86"
        lib_subpath = f"FreeBodyEngine/lib/linux/{arch_folder}"
    else:
        raise RuntimeError(f"Unsupported platform: {system}")

    if getattr(sys, 'frozen', False):
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path(__file__).parent.parent

    dll_dir = base_path / lib_subpath

    if not dll_dir.exists():
        raise FileNotFoundError(f"Library directory not found: {dll_dir}")

    if system == "win32":
        os.add_dll_directory(str(dll_dir))
    elif system == "darwin":
        existing = os.environ.get("DYLD_LIBRARY_PATH", "")
        paths = [str(dll_dir)]
        if existing:
            paths.append(existing)
        os.environ["DYLD_LIBRARY_PATH"] = ":".join(paths)
    elif system.startswith("linux"):
        existing = os.environ.get("LD_LIBRARY_PATH", "")
        paths = [str(dll_dir)]
        if existing:
            paths.append(existing)
        os.environ["LD_LIBRARY_PATH"] = ":".join(paths)

    return dll_dir

try:
    import numba
    HAS_NUMBA = True
except ImportError:
    HAS_NUMBA = False

def fbjit(signature=None, *args, **kwargs):
    """JIT-compiles the decorated function with `numba.jit(signature, **kwargs)` when numba is installed; otherwise warns once and falls back to the no-op `decorator` below, which returns the function unchanged - lets call sites use `@fbjit` unconditionally regardless of whether numba is available."""
    if HAS_NUMBA:
        return numba.jit(signature, **kwargs)

    else:
        def decorator(func):
            """No-op fallback used when numba isn't installed: returns `func` unmodified."""
            return func

        warning('Could not import numba.')
        return decorator

def fbnjit(*args, **kwargs):
    """JIT-compiles the decorated function in nopython mode via `numba.njit(*args, **kwargs)` when numba is installed; otherwise warns once and falls back to the no-op `decorator` below, which returns the function unchanged."""
    if HAS_NUMBA:
        return numba.njit(*args, **kwargs)
    else:
        def decorator(func):
            """No-op fallback used when numba isn't installed: returns `func` unmodified."""
            return func

        warning('Could not import numba.')
        return decorator

from FreeBodyEngine.core.node import Node
from FreeBodyEngine.ui.element import UIElement

@overload
def add(node: 'Node'):
    """
    Add a node to the current scene.
    """
    pass

@overload
def add(element: UIElement):
    """
    Adds a ui element to the root node in the ui manager.
    """
    pass

def add(obj: any):
    """
    Adds a object to the correct service. e.g. giving a Node2D object would add it to the current scene in the scene manager service.
    """
    if isinstance(obj, Node):
        get_service('scene').get_active().add(obj)
    
    elif isinstance(obj, UIElement):
        get_service('ui').add(obj)
