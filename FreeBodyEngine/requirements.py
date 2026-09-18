GLOBAL = [
    "PyOpenGL >= 3.1.9",
    "numpy >= 2.3.1",
    "glfw >= 2.9.0",
    "watchdog",
    "freetype-py",
    "PySDL2",
    "sounddevice",
    "soundfile",
    "scipy",
    'pillow',
    'fbusl',
    'numba',
    'pybind11',
]

WINDOWS = [
    "pywin32",
    "windows-curses"
]

LINUX = ["pywayland", "python-xlib", "evdev", "cffi", "xkbcommon"]

DARWIN = ["pyobjc"]

# Deliberately NOT derived from GLOBAL (unlike WINDOWS/DARWIN/LINUX, which
# get appended on top of it - see builder.py's get_platform_dependencies()):
# GLOBAL carries several packages that are actively wrong on Android -
# `glfw` has no Android target at all (core/window/android.py uses PySDL2
# instead), `sounddevice` wraps PortAudio, which has no Android backend
# either, and `numba`/`scipy` are both real risks to get through a p4a
# cross-compile (LLVM/ARM JIT and BLAS/Fortran toolchains respectively) -
# left out of a first pass rather than discovered as a broken build. This
# list is python-for-android's own recipe/pip names, unpinned - buildozer.spec
# resolves each one to a p4a recipe if one exists, else installs it as a
# plain pip wheel/sdist for the target ABI; version pins are left off since
# pinning against recipes that haven't been tried yet is more likely to
# break the build than help it.
ANDROID = [
    "numpy",
    "pillow",
    "freetype-py",
    "pysdl2",
    "pyopengl",
    # Not an app dependency in any normal sense - a real p4a recipe
    # (pythonforandroid/recipes/android/) providing the small `android`
    # Python package p4a's own patched `ctypes.util.find_library()`
    # unconditionally imports on every build (`from
    # android._ctypes_library_finder import find_library` - a hard `if
    # True:` at the top of that file, not gated behind the bootstrap
    # choice at all), regardless of whether the app uses Kivy. Without
    # it, PyOpenGL's platform loader (which calls find_library() to
    # locate libEGL.so/libGLESv2.so) ImportErrors, and - because
    # PyOpenGL's own plugin loader swallows that ImportError and returns
    # None instead of propagating it (see OpenGL/plugins.py's Plugin.load())
    # - the failure surfaces many frames away as a bare `TypeError:
    # 'NoneType' object is not callable`, with nothing pointing back at
    # the missing `android` package at all.
    "android",
]

