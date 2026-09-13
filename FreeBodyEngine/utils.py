from FreeBodyEngine import get_main, warning, get_flag, get_service
from typing import Literal, overload

def get_platform() -> Literal['win32','darwin','linux']:
    """Returns the identifier for the current host platform, or None if it
    isn't one of the three recognized here (other platforms - e.g. mobile,
    console - aren't handled yet)."""
    sys_plat = sys.platform
    if sys_plat in ['win32', 'darwin', 'linux']:
        return sys_plat
    # handle stuff like android, IOs, console

def abstractmethod(func):
    """Decorator marking a method as abstract: the decorated method always
    raises `NotImplementedError` when called, naming both the method and
    the instance's class - `func`'s own body is never executed, regardless
    of what it contains."""
    def wrapper(*args, **kwargs):
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
        RuntimeError: if the host platform isn't win32/darwin/linux.
        FileNotFoundError: if the expected library directory doesn't exist."""
    system = sys.platform
    arch = platform.machine()

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
    if HAS_NUMBA:
        return numba.jit(signature, **kwargs)
    
    else:
        def decorator(func):
            return func
        
        warning('Could not import numba.')
        return decorator

def fbnjit(*args, **kwargs):
    if HAS_NUMBA:
        return numba.njit(*args, **kwargs)
    else:
        def decorator(func):
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
