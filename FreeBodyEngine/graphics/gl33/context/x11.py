"""
Native X11/OpenGL context creation using EGL.

This is the X11 counterpart to context/wayland.py and is intended to work with
X11Window from window_x11.py.

The window backend owns only X11 windowing/input. This module owns the EGL
connection, EGLSurface and EGLContext, exactly like the Wayland EGL context
module owns those pieces for the Wayland backend.

Expected X11 window attributes:
    window.native_display    -> X11 Display* as ctypes.c_void_p
    window.native_window     -> X11 Window/XID
    window.native_visual_id  -> X11 visual ID
    window.size              -> (width, height)

On X11, EGL can use the X11 Display* directly, so there is no wl_egl_window
wrapper. The X11 Window/XID is passed directly to eglCreateWindowSurface().
"""

from OpenGL import EGL
import ctypes
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from FreeBodyEngine.core.window import X11Window


# EGL_KHR_create_context / EGL 1.5 context attributes.
EGL_CONTEXT_MAJOR_VERSION = 0x3098
EGL_CONTEXT_MINOR_VERSION = 0x30FB
EGL_CONTEXT_OPENGL_PROFILE_MASK = 0x30FD
EGL_CONTEXT_OPENGL_CORE_PROFILE_BIT = 0x00000001
EGL_CONTEXT_OPENGL_DEBUG = 0x31B0

# EGL 1.0/1.1 native visual ID attribute used when selecting an X11-compatible
# EGLConfig. The selected config's native visual must match the X11 Window's
# visual for eglCreateWindowSurface() to be valid on X11.
EGL_NATIVE_VISUAL_ID = 0x302E


def _egl_attrib_array(attribs: list[int]) -> ctypes.Array:
    """Build a ctypes EGLint array terminated by EGL_NONE."""
    ArrayType = EGL.EGLint * len(attribs)
    return ArrayType(*attribs)


def _egl_error(prefix: str) -> RuntimeError:
    """Include the current EGL error code when raising a context error."""
    try:
        err = EGL.eglGetError()
        return RuntimeError(f"{prefix} (EGL error: 0x{int(err):04X})")
    except Exception:
        return RuntimeError(prefix)


def create_x11_opengl_context(window: 'X11Window', debug):
    """Create an EGL/OpenGL context and window surface for an X11Window."""

    egl_display = EGL.eglGetDisplay(window.native_display)
    if egl_display == EGL.EGL_NO_DISPLAY:
        raise _egl_error("Failed to get EGL display from X11 Display.")

    major, minor = EGL.EGLint(), EGL.EGLint()
    if not EGL.eglInitialize(
        egl_display,
        ctypes.byref(major),
        ctypes.byref(minor),
    ):
        raise _egl_error("Failed to initialize EGL.")

    if not EGL.eglBindAPI(EGL.EGL_OPENGL_API):
        raise _egl_error("Failed to bind the desktop OpenGL API to this EGL thread.")

    # Match the EGLConfig to the X11 visual used by the window. This is the
    # important X11-specific part: the native visual and EGL config must be
    # compatible for eglCreateWindowSurface to succeed.
    native_visual_id_attr = (
        EGL.EGL_NATIVE_VISUAL_ID
        if hasattr(EGL, "EGL_NATIVE_VISUAL_ID")
        else EGL_NATIVE_VISUAL_ID
    )

    config_attribs = _egl_attrib_array([
        EGL.EGL_SURFACE_TYPE, EGL.EGL_WINDOW_BIT,
        EGL.EGL_RENDERABLE_TYPE, EGL.EGL_OPENGL_BIT,
        native_visual_id_attr, int(window.native_visual_id),
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

    if not EGL.eglChooseConfig(
        egl_display,
        config_attribs,
        ctypes.byref(egl_config),
        1,
        ctypes.byref(num_configs),
    ):
        raise _egl_error("Failed to choose an X11-compatible EGL config.")

    if num_configs.value == 0:
        raise RuntimeError(
            "No EGL configs matched the X11 window visual "
            f"(visual ID {window.native_visual_id})."
        )

    # X11 Window/XID is already the native drawable. Unlike Wayland there is
    # no wl_egl_window wrapper.
    egl_surface = EGL.eglCreateWindowSurface(
        egl_display,
        egl_config,
        window.native_window,
        None,
    )
    if egl_surface == EGL.EGL_NO_SURFACE:
        raise _egl_error("Failed to create EGL window surface for X11 window.")

    context_attribs = [
        EGL_CONTEXT_MAJOR_VERSION, 3,
        EGL_CONTEXT_MINOR_VERSION, 3,
        EGL_CONTEXT_OPENGL_PROFILE_MASK, EGL_CONTEXT_OPENGL_CORE_PROFILE_BIT,
    ]

    if debug:
        context_attribs += [EGL_CONTEXT_OPENGL_DEBUG, EGL.EGL_TRUE]

    context_attribs.append(EGL.EGL_NONE)

    egl_context = EGL.eglCreateContext(
        egl_display,
        egl_config,
        EGL.EGL_NO_CONTEXT,
        _egl_attrib_array(context_attribs),
    )
    if egl_context == EGL.EGL_NO_CONTEXT:
        EGL.eglDestroySurface(egl_display, egl_surface)
        raise _egl_error("Failed to create OpenGL context.")

    if not EGL.eglMakeCurrent(
        egl_display,
        egl_surface,
        egl_surface,
        egl_context,
    ):
        EGL.eglDestroyContext(egl_display, egl_context)
        EGL.eglDestroySurface(egl_display, egl_surface)
        raise _egl_error("Failed to activate OpenGL context.")

    # 0, not the EGL default of 1 - see the matching comment on the Wayland
    # context backend's eglSwapInterval call: without this, eglSwapBuffers
    # blocks on presentation feedback that isn't delivered for a surface
    # that isn't actually being presented, which - since the whole engine
    # is one synchronous update loop - freezes every service's update(),
    # not just rendering, while off the active workspace/occluded.
    EGL.eglSwapInterval(egl_display, 0)

    # Keep the same state layout as the Wayland context backend so the generic
    # renderer can treat both contexts uniformly.
    window.egl_display = egl_display
    window.egl_surface = egl_surface
    window.egl_context = egl_context
    window.egl_config = egl_config

    return egl_context


def resize_x11_opengl_surface(window: 'X11Window', width: int, height: int):
    """
    Record an X11 resize request.

    X11 itself applies the resize to the Window. No EGL surface resize call is
    required; the drawable remains the same X11 Window and eglSwapBuffers will
    present using its current dimensions.
    """
    window.size = (width, height)


def swap_x11_opengl_buffers(window: 'X11Window'):
    """Present the current EGL back buffer for the X11 window."""
    if not EGL.eglSwapBuffers(window.egl_display, window.egl_surface):
        raise _egl_error("eglSwapBuffers failed.")


def destroy_x11_opengl_context(window: 'X11Window'):
    """Destroy the EGL surface/context and terminate the X11 EGL display."""
    egl_display = getattr(window, "egl_display", EGL.EGL_NO_DISPLAY)
    egl_surface = getattr(window, "egl_surface", EGL.EGL_NO_SURFACE)
    egl_context = getattr(window, "egl_context", EGL.EGL_NO_CONTEXT)

    if egl_display == EGL.EGL_NO_DISPLAY:
        return

    try:
        EGL.eglMakeCurrent(
            egl_display,
            EGL.EGL_NO_SURFACE,
            EGL.EGL_NO_SURFACE,
            EGL.EGL_NO_CONTEXT,
        )
    finally:
        if egl_context != EGL.EGL_NO_CONTEXT:
            EGL.eglDestroyContext(egl_display, egl_context)
        if egl_surface != EGL.EGL_NO_SURFACE:
            EGL.eglDestroySurface(egl_display, egl_surface)
        EGL.eglTerminate(egl_display)

        window.egl_display = EGL.EGL_NO_DISPLAY
        window.egl_surface = EGL.EGL_NO_SURFACE
        window.egl_context = EGL.EGL_NO_CONTEXT
        window.egl_config = None
