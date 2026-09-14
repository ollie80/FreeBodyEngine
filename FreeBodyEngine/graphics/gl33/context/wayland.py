"""
Wayland equivalent of create_win32_opengl_context, using EGL instead of WGL
(Wayland has no WGL/GLX-style "get a DC and pick a pixel format" API -
EGL is the only game in town).

Unlike WGL, EGL doesn't work directly against a wl_surface - Wayland has no
native concept of a drawable surface for GL to render into. You have to wrap
the wl_surface in a `wl_egl_window` (from libwayland-egl) first, and that's
*that* which gets handed to eglCreateWindowSurface. This module does that
wrapping via ctypes, since PyOpenGL doesn't bind libwayland-egl itself.

Expects `window` to be a WaylandWindow (see window_wayland.py) - specifically
it needs `window.native_display` (wl_display*) and `window.native_surface`
(wl_surface*).

Because there's no separate "hdc" object to hang the swap-chain off of like
there is on Win32, this stores everything EGL-related it created directly on
the window object:

    window.egl_display   - EGLDisplay
    window.egl_surface   - EGLSurface (the thing you eglSwapBuffers)
    window.egl_context   - EGLContext (also returned, for parity with the
                            win32 version returning `hrc`)
    window._egl_window   - the underlying wl_egl_window*, needed if you ever
                            call wl_egl_window_resize on a resize event

Dependencies: PyOpenGL (for OpenGL.EGL) and libwayland-egl.so (comes with
the wayland client libraries most distros already have installed - it's
what any Wayland+EGL app, Qt/GTK/SDL included, links against).
"""
from OpenGL import EGL
import ctypes
import ctypes.util
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from FreeBodyEngine.core.window import WaylandWindow

# --- libwayland-egl bindings (PyOpenGL has no wrapper for this itself) -----

_libname = ctypes.util.find_library("wayland-egl") or "libwayland-egl.so.1"
_wayland_egl = ctypes.CDLL(_libname)

_wayland_egl.wl_egl_window_create.restype = ctypes.c_void_p
_wayland_egl.wl_egl_window_create.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]

_wayland_egl.wl_egl_window_resize.restype = None
_wayland_egl.wl_egl_window_resize.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]

_wayland_egl.wl_egl_window_destroy.restype = None
_wayland_egl.wl_egl_window_destroy.argtypes = [ctypes.c_void_p]

# EGL_KHR_create_context attribs (core in EGL 1.5, but the KHR enum values
# are identical and more widely supported by drivers)
EGL_CONTEXT_MAJOR_VERSION = 0x3098
EGL_CONTEXT_MINOR_VERSION = 0x30FB
EGL_CONTEXT_OPENGL_PROFILE_MASK = 0x30FD
EGL_CONTEXT_OPENGL_CORE_PROFILE_BIT = 0x00000001
EGL_CONTEXT_OPENGL_DEBUG = 0x31B0


def _egl_attrib_array(attribs: list) -> ctypes.Array:
    ArrayType = EGL.EGLint * len(attribs)
    return ArrayType(*attribs)


def create_wayland_opengl_context(window: 'WaylandWindow', debug):
    """Sets up a GL 3.3 core-profile context for `window` via EGL: gets and
    initializes the EGL display for `window.native_display`, binds the
    OpenGL API, chooses an EGLConfig matching an RGBA8/24-depth/8-stencil
    pixel format, wraps `window.native_surface` in a `wl_egl_window` (the
    native-window handle EGL actually needs - Wayland itself has no drawable
    surface concept GL can render into directly, see the module docstring),
    creates the EGL surface and context (requesting the debug context bit if
    `debug` is set), and makes it all current. Every object created is
    stashed directly onto `window` (`egl_display`/`egl_surface`/
    `egl_context`/`_egl_window`) since there's no single handle like Win32's
    `hdc` to carry it on; returns `egl_context` for parity with
    create_win32_opengl_context's `hrc` return."""

    egl_display = EGL.eglGetDisplay(window.native_display)
    if egl_display == EGL.EGL_NO_DISPLAY:
        raise RuntimeError("Failed to get EGL display.")

    major, minor = EGL.EGLint(), EGL.EGLint()
    if not EGL.eglInitialize(egl_display, ctypes.byref(major), ctypes.byref(minor)):
        raise RuntimeError("Failed to initialize EGL.")

    if not EGL.eglBindAPI(EGL.EGL_OPENGL_API):
        raise RuntimeError("Failed to bind the OpenGL API to this EGL thread.")

    # choose and set the pixel format equivalent (an EGLConfig)
    config_attribs = _egl_attrib_array([
        EGL.EGL_SURFACE_TYPE, EGL.EGL_WINDOW_BIT,
        EGL.EGL_RENDERABLE_TYPE, EGL.EGL_OPENGL_BIT,
        EGL.EGL_RED_SIZE, 8,
        EGL.EGL_GREEN_SIZE, 8,
        EGL.EGL_BLUE_SIZE, 8,
        EGL.EGL_ALPHA_SIZE, 8,
        EGL.EGL_DEPTH_SIZE, 24,
        EGL.EGL_STENCIL_SIZE, 8,
        EGL.EGL_NONE,
    ])

    num_configs = EGL.EGLint()
    egl_config = EGL.EGLConfig()
    if not EGL.eglChooseConfig(egl_display, config_attribs, ctypes.byref(egl_config), 1, ctypes.byref(num_configs)):
        raise RuntimeError("Failed to choose a valid EGL config.")
    if num_configs.value == 0:
        raise RuntimeError("No EGL configs matched the requested attributes.")

    # wrap the wl_surface in a wl_egl_window - this is the "native window"
    # EGL actually wants; there's no such wrapping step needed on Win32
    # because HWND/HDC already are the native drawable.
    width, height = window.size
    egl_window = _wayland_egl.wl_egl_window_create(window.native_surface, width, height)
    if not egl_window:
        raise RuntimeError("Failed to create wl_egl_window.")

    egl_surface = EGL.eglCreateWindowSurface(egl_display, egl_config, egl_window, None)
    if egl_surface == EGL.EGL_NO_SURFACE:
        raise RuntimeError("Failed to create EGL window surface.")

    # create and set up context for use with the window
    context_attribs = [
        EGL_CONTEXT_MAJOR_VERSION, 3,
        EGL_CONTEXT_MINOR_VERSION, 3,
        EGL_CONTEXT_OPENGL_PROFILE_MASK, EGL_CONTEXT_OPENGL_CORE_PROFILE_BIT,
    ]
    if debug:
        context_attribs += [EGL_CONTEXT_OPENGL_DEBUG, EGL.EGL_TRUE]
    context_attribs.append(EGL.EGL_NONE)

    egl_context = EGL.eglCreateContext(egl_display, egl_config, EGL.EGL_NO_CONTEXT, _egl_attrib_array(context_attribs))
    if egl_context == EGL.EGL_NO_CONTEXT:
        raise RuntimeError("Failed to create OpenGL context.")

    if not EGL.eglMakeCurrent(egl_display, egl_surface, egl_surface, egl_context):
        raise RuntimeError("Failed to activate OpenGL context.")

    # stash everything the window will need later (swapping, resizing,
    # tearing down) since there's no single handle like `hdc` to carry it on
    window.egl_display = egl_display
    window.egl_surface = egl_surface
    window.egl_context = egl_context
    window._egl_window = egl_window

    from OpenGL.GL import glGetString, GL_VERSION, GL_VENDOR, GL_RENDERER

    return egl_context


def resize_wayland_opengl_surface(window: 'WaylandWindow', width: int, height: int):
    """
    Call this from the window's resize handler - but note it doesn't resize
    anything immediately. It just queues the resize; the actual
    wl_egl_window_resize call happens in swap_wayland_opengl_buffers, right
    after the next eglSwapBuffers.

    This split matters: Wayland-EGL forbids issuing draw calls in between
    SwapBuffers and wl_egl_window_resize. Calling wl_egl_window_resize
    straight from an event callback (which can land at any point relative to
    your frame - mid-draw, pre-swap, whenever) is a known cause of resizes
    silently doing nothing or the surface hanging/getting stuck at the old
    size, especially on wlroots-based compositors (Hyprland, Sway) and
    nVidia's EGLStreams implementation. SDL hit exactly this and fixed it the
    same way: apply the new size only right after a swap.
    """
    window._pending_egl_resize = (width, height)
 

def swap_wayland_opengl_buffers(window: 'WaylandWindow'):
    """Equivalent of Win32's SwapBuffers(hdc); call this from window.draw()."""
    EGL.eglSwapBuffers(window.egl_display, window.egl_surface)

    pending = getattr(window, "_pending_egl_resize", None)
    if pending is not None:
        _wayland_egl.wl_egl_window_resize(window._egl_window, pending[0], pending[1], 0, 0)
        window._pending_egl_resize = None


def destroy_wayland_opengl_context(window: 'WaylandWindow'):
    """Tears down everything create_wayland_opengl_context() set up, in
    reverse: unbinds the context (eglMakeCurrent with no surface/context),
    destroys the EGL context and surface, destroys the underlying
    `wl_egl_window` wrapper (via libwayland-egl), and terminates the EGL
    display connection."""
    EGL.eglMakeCurrent(window.egl_display, EGL.EGL_NO_SURFACE, EGL.EGL_NO_SURFACE, EGL.EGL_NO_CONTEXT)
    EGL.eglDestroyContext(window.egl_display, window.egl_context)
    EGL.eglDestroySurface(window.egl_display, window.egl_surface)
    _wayland_egl.wl_egl_window_destroy(window._egl_window)
    EGL.eglTerminate(window.egl_display)
