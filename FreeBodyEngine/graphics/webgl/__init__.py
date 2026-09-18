from FreeBodyEngine.utils import get_platform

# image.py/mesh.py/framebuffer.py all import graphics.webgl.interop, which
# imports Pyodide's `js` module - a virtual module that only exists inside
# an actual browser tab, not a real package pip could ever install. Every
# other cross-platform reuse of something under graphics/webgl/ so far
# (graphics/gles/shader.py importing WebGL2Generator, specifically because
# *that* module has no such dependency - see its own module docstring)
# still runs this file first: Python always executes a package's
# __init__.py before any of its submodules, regardless of which one was
# actually asked for. Unconditionally importing the JS-dependent submodules
# here made any such reuse crash immediately on desktop/Android with
# `ModuleNotFoundError: No module named 'js'`, before ever reaching the one
# submodule that didn't need guarding - guarded the same way
# graphics/gl33/__init__.py already guards its own PyOpenGL-dependent
# imports against the opposite direction (running on web).
if get_platform() == "web":
    from FreeBodyEngine.graphics.webgl.image import WebGL2Image
    from FreeBodyEngine.graphics.webgl.mesh import WebGL2Mesh
    from FreeBodyEngine.graphics.webgl.framebuffer import WebGL2Framebuffer

    __all__ = ["WebGL2Image", "WebGL2Mesh", "WebGL2Framebuffer"]
else:
    __all__ = []
