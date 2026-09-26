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
    # Pillow's p4a recipe only compiles in WebP decode/encode support when
    # this is present in the build's recipe list (opt_depends = ['libwebp']
    # in pythonforandroid/recipes/Pillow/__init__.py) - without it, Image.
    # open() can't identify a WebP file's signature at all and raises
    # UnidentifiedImageError on every one, indistinguishable at the call
    # site from actually-corrupt image data. Needed for any project
    # decoding real-world web/CDN images, which are routinely served as
    # WebP even when the URL/API gives no hint of that up front.
    "libwebp",
    "freetype-py",
    "pysdl2",
    "pyopengl",
    # audio/android.py's own SDL-raw-device backend decodes Ogg/Vorbis
    # itself (streaming, a chunk at a time) rather than handing the whole
    # file to SDL2_mixer's Mix_LoadWAV_RW the way it used to - the
    # in-memory-array approach that replaced held an ENTIRE decoded track
    # in RAM at once (48kHz stereo float32 - tens to hundreds of MB per
    # track) and was confirmed live to get the whole app OOM-killed by
    # Android's own low-memory-killer within ~10-15 seconds of playing a
    # single ordinary track. `pyogg` (a ctypes binding, no compiled
    # extension of its own) is what actually does that streaming decode;
    # `libogg`/`libvorbis` are its own real native dependencies - already
    # needed elsewhere for ffmpeg's Vorbis encoder (see the local ffmpeg
    # p4a recipe override) and now doubly justified as this engine's own
    # core playback capability, not just an encoding target.
    "libogg",
    "libvorbis",
    "pyogg",
    # core/window/android.py's `safe_area_insets` reads Android's own
    # WindowInsets (status bar/notch/gesture-nav-bar coverage) directly via
    # pyjnius - a real p4a recipe (a JNI bridge, not a compiled extension
    # of this engine's own), needed for any UI to actually keep real
    # content clear of those system-drawn overlays instead of rendering
    # partly hidden underneath them, confirmed live on a real device.
    "pyjnius",
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
    # p4a's own stock recipe (pythonforandroid/recipes/pybind11/) - just
    # unpacks pybind11's headers into the build's host-python site-packages
    # and exposes their include dir, no compilation of its own. Needed by
    # the freebodyengine_native recipe right below it (its own headers
    # include <pybind11/pybind11.h>) - unlike GLOBAL's own "pybind11" entry
    # (used by cli/cpp/compile.py's *host* builds), this list is never
    # derived from GLOBAL at all (see this file's own comment on why), so
    # it has to be listed again here explicitly.
    "pybind11",
    # This engine's own native (C++) UI module (FreeBodyEngine/ui/native/
    # node.hpp) - see build/android_recipes/freebodyengine_native/
    # __init__.py for how it actually gets cross-compiled (a
    # CppCompiledComponentsPythonRecipe wrapping the same //@bind pipeline
    # every other platform's compile_cpp_scripts() already uses, fed its
    # pre-generated sources via the P4A_FREEBODYENGINE_NATIVE_DIR env var -
    # see dev/run.py's _run_android() and builder.py's
    # _generate_native_sources_for_android()). Listed as a requirement
    # here (not just dropped into p4a-recipes/) because p4a only builds a
    # recipe it finds in this list, local-recipe override or not - see
    # _write_local_p4a_recipes()'s own docstring on how the local-recipes
    # directory just makes p4a prefer *this* implementation of a name
    # already present here, it doesn't add the name to the build on its
    # own the way `ffmpeg` does (already a real p4a dependency elsewhere).
    # If this build ever fails (no NDK, no local recipe found, a real
    # compile error), ui/__init__.py's own NATIVE_UI resolution falls back
    # to the pure-Python UIElement automatically - this entry failing to
    # build doesn't need to block a release the way a core dependency
    # would, but it isn't given any special "optional" handling in
    # buildozer.spec itself; a failed build here just fails the whole APK
    # build like any other requirement would, until a real per-project
    # opt-out point exists (see _write_buildozer_spec()'s own docstring on
    # this file being a first working loop, not yet configurable).
    "freebodyengine_native",
]

