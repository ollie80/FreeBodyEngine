"""The OpenGL 3.3 implementation of the FB graphics system."""

from FreeBodyEngine.utils import get_platform

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
