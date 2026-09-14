from OpenGL import WGL


import win32gui
from OpenGL.GL import glGetString, GL_VERSION

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from FreeBodyEngine.core.window import Win32Window

PFD_DRAW_TO_WINDOW = 0x00000004
PFD_SUPPORT_OPENGL = 0x00000020
PFD_DOUBLEBUFFER = 0x00000001
PFD_TYPE_RGBA = 0
PFD_MAIN_PLANE = 0


def create_win32_opengl_context(window: 'Win32Window', debug):
    """Sets up a GL context for `window` via WGL: builds a
    PIXELFORMATDESCRIPTOR requesting a double-buffered, 32-bit RGBA,
    24-bit-depth/8-bit-stencil pixel format, chooses and sets that format on
    `window.hdc`, then creates and activates (`wglMakeCurrent`) a rendering
    context bound to that HDC. No explicit version/profile is requested here
    (unlike the Wayland/EGL path's explicit 3.3 core-profile attribs), so the
    context WGL hands back is whatever the driver's default
    `wglCreateContext` behavior yields. Returns the created `hrc`; `debug` is
    currently unused on this backend."""
    hdc = window.hdc

    pfd = WGL.PIXELFORMATDESCRIPTOR()
    pfd.nSize = WGL.sizeof(WGL.PIXELFORMATDESCRIPTOR)
    pfd.nVersion = 1
    pfd.dwFlags = PFD_DRAW_TO_WINDOW | PFD_SUPPORT_OPENGL | PFD_DOUBLEBUFFER
    pfd.iPixelType = PFD_TYPE_RGBA
    pfd.cColorBits = 32
    pfd.cDepthBits = 24
    pfd.cStencilBits = 8
    pfd.iLayerType = PFD_MAIN_PLANE

    # choose and set the pixel format
    pixel_format = WGL.ChoosePixelFormat(hdc, pfd)
    if pixel_format == 0:
        raise RuntimeError("Failed to choose a valid pixel format.")

    if not WGL.SetPixelFormat(hdc, pixel_format, pfd):
        raise RuntimeError("Failed to set pixel format.")

    # create and set up context for use with the window
    hrc = WGL.wglCreateContext(hdc)
    if not hrc:
        raise RuntimeError("Failed to create OpenGL context.")
        
    if not WGL.wglMakeCurrent(hdc, hrc):
        raise RuntimeError("Failed to activate OpenGL context.")
    

    return hrc 