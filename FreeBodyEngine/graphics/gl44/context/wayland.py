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
    """Creates a GL 4.4 core-profile context for `window` via EGL: gets/
    initializes the EGL display, binds the OpenGL API, chooses an EGLConfig
    matching an 8/8/8/8 + 24-depth + 8-stencil framebuffer, wraps
    `window.native_surface` in a `wl_egl_window` (the "native window" EGL
    needs, since Wayland has no drawable concept of its own), creates the
    window surface and context, and makes it current. Every EGL handle
    created is stashed directly on `window` (there's no single "hdc"-like
    object to carry them on), and the context is requested as 4.4 core
    (vs. GL33's equivalent requesting 3.3) - the only real difference from
    that version of this function. Raises RuntimeError, naming the specific
    step, on any EGL failure."""




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
        EGL_CONTEXT_MAJOR_VERSION, 4,
        EGL_CONTEXT_MINOR_VERSION, 4,
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

    # 0, not the EGL default of 1 - the actual fix for the "app doesn't
    # update at all while off the active workspace/occluded" bug the two
    # reverted attempts below swap_wayland_opengl_buffers() were chasing.
    # Root cause, confirmed: with vsync on, eglSwapBuffers blocks until the
    # compositor delivers presentation feedback for this surface - which it
    # doesn't while the surface isn't actually being presented (switched
    # away from, minimized, fully occluded on some compositors) - and
    # because the engine's whole update loop is one synchronous thread (see
    # Main.run()), a blocked swap doesn't just stall rendering, it stalls
    # every service's update() too, ProfilerServer's included (exactly what
    # broke `fb profile` needing the same workspace as the app it profiles).
    # Disabling vsync at the EGL level makes eglSwapBuffers present-and-
    # return immediately regardless of compositor feedback, sidestepping
    # the block entirely rather than trying to skip/gate the call itself
    # (both prior attempts, see below, fought the driver's own pacing
    # instead and made things worse) - now uncapped/torn without a frame
    # limiter, presumably acceptable to trade for "runs at all".
    EGL.eglSwapInterval(egl_display, 0)

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
    """Equivalent of Win32's SwapBuffers(hdc); call this from window.draw().

    Plain and unconditional, and correctly so now - the actual fix for
    this call blocking (and, transitively, freezing the whole engine)
    while off-workspace/occluded is create_wayland_opengl_context()'s own
    eglSwapInterval(egl_display, 0) call, not anything here. See its
    comment for the two earlier, reverted attempts that tried gating this
    function itself instead."""
    EGL.eglSwapBuffers(window.egl_display, window.egl_surface)

    pending = getattr(window, "_pending_egl_resize", None)
    if pending is not None:
        _wayland_egl.wl_egl_window_resize(window._egl_window, pending[0], pending[1], 0, 0)
        window._pending_egl_resize = None


def destroy_wayland_opengl_context(window: 'WaylandWindow'):
    """Tears down everything `create_wayland_opengl_context` created on
    `window`, in order: releases the current context, destroys the EGL
    context and surface, destroys the underlying `wl_egl_window`, then
    terminates the EGL display connection."""
    EGL.eglMakeCurrent(window.egl_display, EGL.EGL_NO_SURFACE, EGL.EGL_NO_SURFACE, EGL.EGL_NO_CONTEXT)
    EGL.eglDestroyContext(window.egl_display, window.egl_context)
    EGL.eglDestroySurface(window.egl_display, window.egl_surface)
    _wayland_egl.wl_egl_window_destroy(window._egl_window)
    EGL.eglTerminate(window.egl_display)
