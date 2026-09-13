from FreeBodyEngine.utils import get_platform
from FreeBodyEngine.graphics import color
from FreeBodyEngine.graphics import image
from FreeBodyEngine.graphics import renderer
from FreeBodyEngine.graphics import material
from FreeBodyEngine.graphics import mesh
from FreeBodyEngine.graphics import sprite
from FreeBodyEngine.graphics import gl33
from FreeBodyEngine.graphics import pbr
from FreeBodyEngine.graphics import pipeline
from FreeBodyEngine.graphics import model
from FreeBodyEngine.graphics import text

import sys

def get_renderer() -> type[renderer.Renderer]:
    """Get the correct renderer for the platform.

    `fb.set_flag(fb.FORCE_RENDERER, "gl33")` (or `"gl44"`) overrides
    auto-detection entirely - the main reason to: comparing backends
    against each other (e.g. ComputeStressTest) needs the ability to pick
    GL33 deliberately even on hardware that's perfectly capable of GL44,
    which auto-detection alone could never do (it would always prefer the
    newer one)."""
    from FreeBodyEngine import get_flag, FORCE_RENDERER

    forced = get_flag(FORCE_RENDERER, None)
    if forced == "gl33":
        from FreeBodyEngine.graphics.gl33.renderer import GL33Renderer
        return GL33Renderer
    if forced == "gl44":
        from FreeBodyEngine.graphics.gl44.renderer import GL44Renderer
        return GL44Renderer

    platform = get_platform()

    if platform in ("win32", "linux", "darwin"):
        # By the time get_renderer() runs, the window (and its GL context)
        # already exists and is current - register_default_services()
        # registers 'window' before calling this - so the *actual* context
        # version can just be queried directly instead of guessing from the
        # platform alone.
        try:
            from OpenGL.GL import glGetIntegerv, GL_MAJOR_VERSION, GL_MINOR_VERSION
            version = (glGetIntegerv(GL_MAJOR_VERSION), glGetIntegerv(GL_MINOR_VERSION))
            if version >= (4, 4):
                from FreeBodyEngine.graphics.gl44.renderer import GL44Renderer
                return GL44Renderer
        except Exception:
            pass  # no current GL context (or the query failed) - fall through to GL33

    # gl33 is made to support pretty much every device, it might actually run on a smart fridge (eat shit pirate)
    from FreeBodyEngine.graphics.gl33.renderer import GL33Renderer
    return GL33Renderer


def ensure_gpu_context():
    """Makes sure a live GPU context - and the matching Renderer service -
    exists, transparently creating one if nothing has set one up yet. Write
    once, run anywhere: a normal windowed game already has both (the window
    is created, then get_renderer() picks and registers the right backend)
    by the time anything calls this, so it's a no-op there. It only ever
    does something for a program that wants GPU compute with no window at
    all - a benchmark, a command-line tool.

    "No window at all" is the operative phrase: this does *not* register a
    'window' service, hidden or otherwise - it uses
    core.window.glfw.create_raw_offscreen_context(), a bare GL context with
    no Window/Service wrapper, no input/event pump, nothing. GL33Renderer/
    GL44Renderer.on_initialize() both handle 'window' simply not existing.

    Not the same thing as `fb.HEADLESS` - that flag means "no GPU at all"
    (HeadlessWindow, an SDL dummy-driver window with no GL context, for a
    dedicated server that never touches graphics). This is the opposite: a
    real GPU context, with no window service at all standing in for one.
    Using this while HEADLESS is set is a contradiction and raises rather
    than guessing which one was actually meant.
    """
    from FreeBodyEngine import service_exists, register_service, get_service, main_exists, error

    if not main_exists():
        error("fb.init() must be called before ensure_gpu_context()/create_compute_shader().")
        return

    if service_exists('renderer'):
        return  # a renderer (and, ordinarily, a window) already exist - reuse them as-is

    if service_exists('window'):
        window = get_service('window')
        if window.window_type == 'headless':
            error(
                "Can't create a GPU context: this session was started with fb.HEADLESS set, "
                "which means no GL context at all (for a dedicated server with no GPU). GPU "
                "compute and fb.HEADLESS are mutually exclusive."
            )
            return
        # A real window exists but no renderer was registered for it yet
        # (unusual - normally get_renderer() already ran as part of
        # registering the window) - nothing to create, just pick a backend
        # for its existing context below.
    else:
        # No window service at all, by design - see the docstring. Always
        # GLFW here regardless of platform/FORCE_X11/etc, which exist to
        # integrate a *visible* window with a platform's native windowing;
        # a compute-only context has no use for any of that. GLFW is the
        # same portable fallback get_window() itself reaches for on any
        # platform it has no more specific answer for.
        from FreeBodyEngine.core.window.glfw import create_raw_offscreen_context
        create_raw_offscreen_context()

    register_service(get_renderer()())


def _is_gl44() -> bool:
    from FreeBodyEngine.graphics.gl44.renderer import GL44Renderer
    return get_renderer() is GL44Renderer


def create_compute_shader(source, injector=None, **kwargs):
    """Creates a compute shader using whichever backend this session is (or
    will be) running under - GL44's real glDispatchCompute if the GPU/
    driver support it, GL33's fullscreen-quad-emulated fallback otherwise -
    entirely transparently. Code written against the returned ComputeShader
    never needs to know or branch on which backend actually produced it.
    Creates a GPU context automatically (see ensure_gpu_context()) if one
    doesn't exist yet."""
    ensure_gpu_context()
    if _is_gl44():
        from FreeBodyEngine.graphics.gl44.compute import GL44ComputeShader
        return GL44ComputeShader(source, injector, **kwargs)
    from FreeBodyEngine.graphics.gl33.compute import GLComputeShader
    return GLComputeShader(source, injector, **kwargs)


def create_compute_buffer(data):
    """Creates whatever buffer type the current compute backend's `buffer`
    blocks actually need - a real read/write SSBO under GL44, a read-only
    texture buffer under GL33 - so code calling ComputeShader.bind_buffer()
    doesn't need to know or care which one it got either."""
    ensure_gpu_context()
    if _is_gl44():
        from FreeBodyEngine.graphics.gl44.buffer import SSBOBuffer
        return SSBOBuffer(data)
    from FreeBodyEngine.graphics.gl33.buffer import TextureBuffer
    return TextureBuffer(data)


__all__ = ["color", "mesh", "material", "renderer", "pipeline", "image", 'pbr', "gl33", 'sprite', 'model', 'text',
           'get_renderer', 'ensure_gpu_context', 'create_compute_shader', 'create_compute_buffer']
