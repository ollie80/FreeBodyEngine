"""The OpenGL ES 3.0 implementation of the FB graphics system - used on
Android (see core/window/android.py, which requests exactly this context
version/profile from SDL2).

Deliberately thin: everything below except shader.py/renderer.py is
reused directly from graphics/gl33 unchanged - GLMesh/GLImage/GLFramebuffer/
GLTextureManager are all plain PyOpenGL (`OpenGL.GL`) calls, and GLES 3.0's
core API is a strict-enough subset of desktop GL 3.3's that none of them
needed a Android-specific override (framebuffer.py's one real divergence,
GL_CLAMP_TO_BORDER not existing in GLES, is handled with a platform check
right in that shared file - see its _set_shadow_map_wrap()). Only shader
compilation (which GLSL version/precision the FBUSL generator emits) and
the renderer's own wireframe debug mode (GLES has no glPolygonMode at all)
actually differ, which is what shader.py/renderer.py exist to override."""

from FreeBodyEngine.utils import get_platform

if get_platform() != "web":
    from FreeBodyEngine.graphics.gl33 import GLImage, GLMesh, GLFramebuffer
    from FreeBodyEngine.graphics.gles.shader import GLESShader
    from FreeBodyEngine.graphics.gles.renderer import GLESRenderer

    __all__ = ["GLMesh", "GLFramebuffer", "GLImage", "GLESShader", "GLESRenderer"]
else:
    __all__ = []
