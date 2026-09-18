"""The OpenGL 3.3 implementation of the FB graphics system."""

import os
from FreeBodyEngine.utils import get_platform

# PyOpenGL picks its platform backend (GLX/WGL/Darwin/EGL/...) the moment
# `OpenGL.platform` is first imported (see its own _load(), triggered by
# any sibling's `from OpenGL.GL import *` below) by guessing from
# `sys.platform`/`DISPLAY`/`WAYLAND_DISPLAY` - on Android, `sys.platform`
# is plain "linux" (see utils.get_platform()'s own docstring) with no X11
# display of any kind, so that guess resolves to a GLX plugin that has
# nothing to attach to; PyOpenGL's plugin loader then returns None instead
# of raising, and the very next line calls that None as if it were the
# resolved platform class - a bare `TypeError: 'NoneType' object is not
# callable` with no clue this was ever about GLX at all. Setting
# PYOPENGL_PLATFORM up front short-circuits that guess entirely: `egl` is
# the platform module PyOpenGL ships specifically for contexts created
# through EGL rather than GLX/WGL - exactly how SDL2 sets up Android's GL
# context (see core/window/android.py) - and it must be set before this
# file's own imports below, since PyOpenGL's platform is selected once, at
# `OpenGL.platform` import time, not re-checked afterward.
if get_platform() == "android":
    os.environ.setdefault("PYOPENGL_PLATFORM", "egl")

# Every sibling below except generator.py imports PyOpenGL (`from OpenGL.GL
# import *`) at its own top level - a ctypes wrapper around a real native
# libGL that doesn't exist inside a Pyodide/WASM browser session (see
# utils.get_platform()'s docstring for why `sys.platform == "emscripten"`
# is normalized to "web" there). graphics/webgl/generator.py imports
# GL33Generator specifically *because* it has no OpenGL dependency of its
# own (pure FBUSL codegen - see its own module docstring), but Python
# always runs a package's __init__.py before any of its submodules
# regardless of which one was actually asked for - so
# `from FreeBodyEngine.graphics.gl33.generator import GL33Generator` was
# still crashing on web, via this file's own unconditional imports, before
# ever reaching generator.py itself. Guarded the same way graphics/
# __init__.py already guards its own `import gl33` for the same reason.
if get_platform() != "web":
    from FreeBodyEngine.graphics.gl33.image import GLImage
    from FreeBodyEngine.graphics.gl33.mesh import GLMesh
    from FreeBodyEngine.graphics.gl33.framebuffer import GLFramebuffer
    from FreeBodyEngine.graphics.gl33.renderer import GL33Renderer
    from FreeBodyEngine.graphics.gl33.shader import GLShader

    __all__ = ["GLMesh", "GLFramebuffer", "GLRenderer", "GLShader", "GLImage"]
else:
    __all__ = []
