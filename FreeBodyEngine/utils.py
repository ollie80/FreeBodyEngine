from FreeBodyEngine import get_main, warning, get_flag, get_service

def abstractmethod(func):
    def wrapper(*args, **kwargs):
        cls_name = args[0].__class__.__name__
        raise NotImplementedError(f"Method '{func.__name__}' is not implemented on '{cls_name}'.")
    return wrapper

import sys
import os
import platform
from pathlib import Path

def load_dlls():
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

def load_sprite(path: str):
    return get_service('files').load_sprite(path)

def load_data(path: str):
    return get_service('files').load_data(path)

def load_toml(path: str):
    return get_service('files').load_toml(path)


def load_image(path: str):
    return get_service('files').load_image(path)

def load_material(path: str):
    return get_service('files').load_material(path)


def load_sound(path: str):
    return get_main().files.load_sound(path)


def load_shader(path: str):
    return get_service('files').load_shader(path)

def load_sprite(path: str):
    return get_service('files').load_sprite(path)

def load_model(path: str, model_name: str = None, scale=None):
    return get_service('files').load_model(path, model_name, scale)