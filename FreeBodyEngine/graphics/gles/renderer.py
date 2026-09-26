"""GLESRenderer: GL33Renderer (graphics/gl33/renderer.py) with only
load_shader() overridden - see graphics/gles/__init__.py's module docstring
for why nothing else needs to differ. Context creation in on_initialize()
already needs no Android-specific branch either: AndroidWindow
(core/window/android.py) creates and makes current its own SDL2 GL
context before the renderer ever runs, the same way GLFWWindow does for
desktop - on_initialize()'s per-window_type dispatch there is only for
backends (wayland/x11/win32) that hand the renderer a bare surface to
attach a context to itself."""
from FreeBodyEngine.graphics.gl33.renderer import GL33Renderer
from FreeBodyEngine.graphics.gles.shader import GLESShader
from fbusl.injector import Injector


class GLESRenderer(GL33Renderer):
    """The OpenGL ES 3.0 renderer, used on Android."""

    def load_shader(self, vertex, fragment, injector: Injector = Injector(), geometry=None):
        """Compiles `vertex`/`fragment` (and optional `geometry`) FBUSL
        source into a GLESShader (GLSL ES 300, via WebGL2Generator) rather
        than GL33Renderer's desktop GLShader (GLSL 330)."""
        return GLESShader(vertex, fragment, injector, geometry)
