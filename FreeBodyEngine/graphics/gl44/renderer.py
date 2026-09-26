from FreeBodyEngine.graphics.renderer import Renderer
from FreeBodyEngine.graphics.color import Color
from FreeBodyEngine.graphics.gl44 import GL44Image, GL44Mesh, GL44Framebuffer
from FreeBodyEngine.graphics.sprite import Sprite
from FreeBodyEngine.graphics.gl44.shader import GL44Shader
from FreeBodyEngine.graphics.gl44.texture import GL44TextureManager
from fbusl.injector import Injector
from FreeBodyEngine.graphics.texture import Texture
from FreeBodyEngine.graphics.material import Material, BlendMode
from FreeBodyEngine import DEVMODE, get_flag, warning
from FreeBodyEngine.graphics.gl44.buffer import UBOBuffer

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from FreeBodyEngine.core.main import Main
    from FreeBodyEngine.core.camera import Camera
    from FreeBodyEngine.graphics.material import Material
    from FreeBodyEngine.math import Vector

from FreeBodyEngine import get_service, service_exists
from FreeBodyEngine.utils import get_platform
from FreeBodyEngine.core.files import get_file
import numpy as np

if get_platform() == "win32":
    from OpenGL import WGL

from OpenGL.GL import *
from OpenGL.GL.ARB.debug_output import *  # for debug_callback

MIN_GL_VERSION = (4, 4)


@GLDEBUGPROC
def debug_callback(source, type, id, severity, length, message, userParam):
    """GL_DEBUG_OUTPUT callback (see glDebugMessageCallback in on_initialize)
    - decodes the driver's UTF-8 message and prints it, so GL errors/
    warnings surface immediately instead of needing a manual glGetError()
    poll."""
    msg = ctypes.string_at(message, length).decode('utf-8')
    print(f"[OpenGL DEBUG] {msg}")


class GL44Renderer(Renderer):
    """
    The OpenGL renderer. Uses OpenGL version 4.4 core - real compute
    shaders (glDispatchCompute), writable SSBOs, and image load/store,
    unlike GL33Renderer's fullscreen-fragment-shader compute emulation. A
    completely separate, independently selectable backend (see
    graphics/get_renderer()) - GL33Renderer is untouched and still exists
    for hardware/platforms that can't do better than 3.3.
    """
    def __init__(self):
        """Sets the backend's Mesh subclass; GPU context creation happens in
        on_initialize() instead, since it depends on a window (or lack
        thereof) that doesn't exist yet at construction time."""
        super().__init__()
        # No unconditional 'window' dependency: graphics.ensure_gpu_context()
        # registers this renderer with *no* window service at all for a
        # headless-compute-only session (a raw context already exists and
        # is current by then - see core.window.glfw.create_raw_offscreen_
        # context()) - on_initialize() below handles 'window' not existing.
        # Declaring the dependency anyway would make ServiceLocator refuse
        # to even call on_initialize() in that case.

        self.mesh_class = GL44Mesh

        # Read by FreeBodyEngine.core.profiler_server.ProfilerServer (see
        # its own module docstring) - cumulative, never reset here, so a
        # consumer computes its own per-frame delta rather than this
        # renderer needing to know when a "frame" starts/ends on anyone
        # else's behalf.
        self.total_draw_calls = 0

        # GPU timer query pool - see begin_gpu_query()/end_gpu_query()'s
        # own docstrings. Left empty until on_initialize() actually has a
        # live GL context to allocate queries against; both methods are
        # no-ops until then (or permanently, if query allocation itself
        # fails - see on_initialize()).
        self._gpu_query_ids = []
        self._gpu_query_pending = []
        self._gpu_query_index = 0
        self._gpu_query_active = False
        self._gpu_timing_supported = False
        self._gpu_query_stall_frames = 0
        self.last_gpu_ms: float = None

    def on_initialize(self):
        """Creates (or attaches to) the OpenGL context for the current window
        backend (glfw/wayland/win32/x11), or - if no 'window' service is
        registered at all - assumes a raw offscreen context already exists
        and is current (a true headless compute session, see
        graphics.ensure_gpu_context()). Then warns (but doesn't raise) if
        the resulting context is below MIN_GL_VERSION, and enables
        GL_DEBUG_OUTPUT plus the initial viewport."""
        super().on_initialize()

        if service_exists('window'):
            self.window = get_service('window')

            if self.window.window_type == "glfw":
                from glfw import make_context_current
                make_context_current(self.window._window)
            elif self.window.window_type == 'wayland':
                from FreeBodyEngine.graphics.gl44.context.wayland import create_wayland_opengl_context
                self.context = create_wayland_opengl_context(self.window, get_flag(DEVMODE, False))
            elif get_platform() == "win32":
                from FreeBodyEngine.graphics.gl44.context.win32 import create_win32_opengl_context
                self.context = create_win32_opengl_context(self.window, get_flag(DEVMODE, False))
            elif self.window.window_type == 'x11':
                from FreeBodyEngine.graphics.gl44.context.x11 import create_x11_opengl_context
                self.context = create_x11_opengl_context(self.window, get_flag(DEVMODE, False))

            width, height = self.window.framebuffer_size
        else:
            # No window service at all - a true headless compute session
            # (see graphics.ensure_gpu_context()). A raw context already
            # exists and is current; there's no window-driven framebuffer
            # size to query, and nothing here ever draws to the default
            # framebuffer anyway.
            self.window = None
            width, height = 1, 1

        major = glGetIntegerv(GL_MAJOR_VERSION)
        minor = glGetIntegerv(GL_MINOR_VERSION)
        if (major, minor) < MIN_GL_VERSION:
            warning(
                f"GL44Renderer requires OpenGL {MIN_GL_VERSION[0]}.{MIN_GL_VERSION[1]}+, "
                f"but this context is only {major}.{minor} - use GL33Renderer instead "
                f"(see FreeBodyEngine.graphics.get_renderer())."
            )

        glEnable(GL_DEBUG_OUTPUT)
        glEnable(GL_DEBUG_OUTPUT_SYNCHRONOUS)
        glDebugMessageCallback(debug_callback, None)

        glViewport(0, 0, width, height)

        self.texture_manager = GL44TextureManager()

        self.line_shader = self.load_shader(get_file("engine://shader/line.fbvert").read(), get_file("engine://shader/line.fbfrag").read())

        # GPU timer query pool for begin_gpu_query()/end_gpu_query() - see
        # their own docstrings. A pool (not a single query) since a
        # query's result isn't available until the GPU actually catches
        # up, often a frame or more later - round-robining through
        # several means a query is (almost) never still pending when its
        # slot comes back around, without ever blocking to wait for one.
        # Wrapped in try/except since query support (or this specific
        # target, GL_TIME_ELAPSED) isn't guaranteed on every driver this
        # renderer might end up running against - GPU timing degrades to
        # unavailable (last_gpu_ms stays None) rather than crashing
        # startup over a profiling feature nothing may even be using.
        try:
            self._gpu_query_ids = list(glGenQueries(4))
            self._gpu_query_pending = [False] * len(self._gpu_query_ids)
            self._gpu_timing_supported = True
        except Exception as e:
            warning(f"GL44Renderer: GPU timer queries unavailable ({e}) - GPU timing will read as unavailable.")
            self._gpu_timing_supported = False

    def create_buffer(self, data):
        """Wraps `data` in a UBOBuffer, GL44's Buffer implementation."""
        return UBOBuffer(data)

    def get_max_buffer_size(self) -> int:
        """Returns the max size of a UBOBuffer, in bytes."""
        return UBOBuffer.get_max_size()

    def resize(self, size: tuple[int, int]):
        """Updates the GL viewport to `size`, and resizes the platform-specific window surface (wayland/x11) to match."""
        glViewport(0, 0, size[0], size[1])

        if self.window.window_type == 'wayland':
            from FreeBodyEngine.graphics.gl44.context.wayland import resize_wayland_opengl_surface
            resize_wayland_opengl_surface(self.window, size[0], size[1])
        elif self.window.window_type == 'x11':
            from FreeBodyEngine.graphics.gl44.context.x11 import resize_x11_opengl_surface
            resize_x11_opengl_surface(self.window, size[0], size[1])

    def get_mesh_class(self) -> type[GL44Mesh]:
        """Returns GL44Mesh."""
        return GL44Mesh

    def destroy(self):
        """Releases the OpenGL context (win32 only - wglMakeCurrent/wglDeleteContext are Windows-specific)."""
        if self.main.winow.window_type == "win32":
            WGL.wglMakeCurrent(self.window.hdc, None)
        WGL.wglDeleteContext(self.context)

    def swap_buffers(self):
        """Swaps the front/back buffers for a manually-created wayland/x11
        context. glfw drives its own swap directly (see core/window/glfw.py)
        instead of going through the renderer, so this is a no-op there."""
        if self.window.window_type == 'wayland':
            from FreeBodyEngine.graphics.gl44.context.wayland import swap_wayland_opengl_buffers
            swap_wayland_opengl_buffers(self.window)
        elif self.window.window_type == 'x11':
            from FreeBodyEngine.graphics.gl44.context.x11 import swap_x11_opengl_buffers
            swap_x11_opengl_buffers(self.window)

    @property
    def create_framebuffer(self):
        """Returns GL44Framebuffer."""
        return GL44Framebuffer

    def clear(self, color: 'Color'):
        """Clears the color and depth buffers of the currently bound framebuffer to `color`."""
        glClearColor(*color.float_normalized_a)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

    def set_blend_mode(self, mode: BlendMode):
        """See Renderer.set_blend_mode. Skips the actual GL calls if `mode`
        already matches the last mode set, since flush() calls this between
        every group even when consecutive groups share a mode."""
        if mode == self._current_blend_mode:
            return
        self._current_blend_mode = mode

        if mode == BlendMode.OPAQUE:
            glDisable(GL_BLEND)
            glDepthMask(GL_TRUE)
        elif mode == BlendMode.TRANSPARENT:
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glDepthMask(GL_FALSE)
        elif mode == BlendMode.ADDITIVE:
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE)
            glDepthMask(GL_TRUE)

    def load_shader(self, vertex, fragment, injector: Injector = Injector(), geometry=None):
        """Compiles `vertex`/`fragment` (and optional `geometry`) FBUSL source into a GL44Shader, using `injector` to resolve engine-provided builtins."""
        return GL44Shader(vertex, fragment, injector, geometry)

    def draw_mesh_instanced(self, mesh, material, model_matrices, camera):
        """Draws one copy of `mesh` per row of `model_matrices` (shape
        (N, 4, 4)) in a single glDrawElementsInstanced call - see
        GL33Renderer.draw_mesh_instanced for the identical implementation
        and its docstring (GL44 doesn't need anything version-specific for
        instanced vertex-attribute arrays, so this is deliberately not
        using GL44-only features like SSBOs)."""
        material.shader['view'] = camera.view_matrix
        material.shader['proj'] = camera.proj_matrix
        material.use()
        material.shader.use()

        glBindVertexArray(mesh.vao)

        base_location = len(mesh.attributes)
        instance_data = np.ascontiguousarray(model_matrices, dtype=np.float32)
        instance_vbo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, instance_vbo)
        glBufferData(GL_ARRAY_BUFFER, instance_data.nbytes, instance_data, GL_STREAM_DRAW)

        stride = 16 * 4
        for column in range(4):
            location = base_location + column
            glEnableVertexAttribArray(location)
            glVertexAttribPointer(location, 4, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(column * 16))
            glVertexAttribDivisor(location, 1)

        glDrawElementsInstanced(GL_TRIANGLES, len(mesh.indices), GL_UNSIGNED_INT, ctypes.c_void_p(0), len(model_matrices))

        for column in range(4):
            location = base_location + column
            glVertexAttribDivisor(location, 0)
            glDisableVertexAttribArray(location)

        glBindVertexArray(0)
        glDeleteBuffers(1, [instance_vbo])

    def draw_ui_background_instances(self, mesh, material, instance_data):
        """Draws `instance_data` (an (N, 20) float32 array - 5 vec4s per
        instance: rect, border_radius, border_width, border_color,
        base_color, in that order - see UIRenderer._flush_instances for
        the exact packing) as N instances of `mesh` in a single
        glDrawElementsInstanced call. The batched counterpart to
        draw_mesh() for UI element backgrounds: UIRenderer queues every
        eligible (untextured) element's background instead of drawing it
        immediately, cutting what used to be N draw_mesh() calls (each
        paying 8 real set_uniform()s - confirmed the single largest
        remaining cost in UIRenderer.draw() by cProfile, after every
        earlier fix) down to one instance-buffer upload and one draw call
        per batch. Same divisor=1 per-instance-attribute mechanism as
        draw_mesh_instanced above, and - after a real, reproduced bug -
        the exact same gen/delete-a-fresh-VBO-every-call pattern too, not
        a persistent one reused across flushes: this runs up to ~20-40
        times a *single* frame (once per batch boundary - see
        UIRenderer._flush_instances), and reusing one VBO across that many
        same-frame glBufferData/glDrawElementsInstanced pairs produced an
        intermittent flicker plus, on the same episodes, the whole app
        appearing to stop responding to input - consistent with a GPU
        driver stall on the reused buffer blocking the single synchronous
        update loop (input polling included), the same underlying failure
        class as the off-workspace eglSwapBuffers freeze fixed earlier
        this session, just self-inflicted here instead of compositor-
        triggered. A fresh buffer per call costs a real glGenBuffers/
        glDeleteBuffers pair, but that's cheap next to what batching
        already saves, and correctness beats it regardless."""
        self.total_draw_calls += 1
        material.use()
        material.shader.use()

        glBindVertexArray(mesh.vao)

        base_location = len(mesh.attributes)
        data = np.ascontiguousarray(instance_data, dtype=np.float32)

        instance_vbo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, instance_vbo)
        glBufferData(GL_ARRAY_BUFFER, data.nbytes, data, GL_STREAM_DRAW)

        stride = 20 * 4  # 5 vec4s, 4 bytes/float
        for i in range(5):
            location = base_location + i
            glEnableVertexAttribArray(location)
            glVertexAttribPointer(location, 4, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(i * 16))
            glVertexAttribDivisor(location, 1)

        glDrawElementsInstanced(GL_TRIANGLES, len(mesh.indices), GL_UNSIGNED_INT, ctypes.c_void_p(0), len(data))

        for i in range(5):
            location = base_location + i
            glVertexAttribDivisor(location, 0)
            glDisableVertexAttribArray(location)

        glBindVertexArray(0)
        glDeleteBuffers(1, [instance_vbo])

    def enable_depth_testing(self):
        """Enables GL_DEPTH_TEST."""
        glEnable(GL_DEPTH_TEST)

    def disable_depth_testing(self):
        """Disables GL_DEPTH_TEST."""
        glDisable(GL_DEPTH_TEST)

    def draw_mesh(self, mesh: 'Mesh', material: 'Material'):
        """Binds `material` and draws `mesh`'s indexed triangles. Temporarily
        switches to wireframe polygon mode if `material.data['render_mode']
        == "wireframe"`."""
        self.total_draw_calls += 1
        self.texture_manager.begin_draw()
        material.use()
        material.shader.use()

        render_mode = material.data.get('render_mode', None)
        if render_mode != None:
            if render_mode == "wireframe":
                glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)

        glBindVertexArray(mesh.vao)
        glDrawElements(GL_TRIANGLES, len(mesh.indices), GL_UNSIGNED_INT, ctypes.c_void_p(0))

        if render_mode != None:
            if render_mode == "wireframe":
                glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)

        glBindVertexArray(0)

    def begin_gpu_query(self):
        """Starts timing GPU-side execution time for whatever draw calls
        happen between this and the next end_gpu_query() - read by
        FreeBodyEngine.core.profiler_server.ProfilerServer, which brackets
        this around a whole frame's DRAW phase (see its own module
        docstring for exactly where/why).

        A no-op if query allocation failed at startup, or ever failed at
        runtime before (self._gpu_timing_supported is False - see
        on_initialize() and the try/except below), or if the query this
        call would reuse hasn't finished yet (skips this frame's timing
        rather than either blocking for it or starting a second,
        overlapping GL_TIME_ELAPSED query, which is invalid GL usage -
        only one may be active at a time).

        Reads the result via glGetQueryObjectuiv (32-bit), not the more
        "correct" glGetQueryObjectui64v - confirmed live on real hardware
        that the 64-bit read raises `KeyError` inside PyOpenGL's own
        array-type conversion (a PyOpenGL/driver mismatch over the 64-bit
        result enum, nothing about the query itself being invalid). A
        single frame's GL_TIME_ELAPSED, in nanoseconds, fits comfortably
        in 32 bits regardless (max ~4.3 seconds; real frames are under
        100ms), so this isn't a precision compromise for what this is
        actually used for - it just avoids the buggy code path entirely.
        Still wrapped in its own try/except (separate from
        on_initialize()'s) in case some *other* driver fails a different
        way: without it, a failure here would raise fresh out of this
        same call every single frame forever (caught, each time, by
        UpdateCoordinator._run()'s own safety net - so it never crashes
        the app, but it would spam a full traceback into the log every
        frame indefinitely) instead of being recognized once and
        disabling GPU timing cleanly, the same way a genuinely
        unsupported driver already does."""
        if not self._gpu_timing_supported:
            return

        idx = self._gpu_query_index
        if self._gpu_query_pending[idx]:
            if glGetQueryObjectiv(self._gpu_query_ids[idx], GL_QUERY_RESULT_AVAILABLE):
                try:
                    nanoseconds = glGetQueryObjectuiv(self._gpu_query_ids[idx], GL_QUERY_RESULT)
                    self.last_gpu_ms = nanoseconds / 1_000_000.0
                except Exception as e:
                    warning(f"GL44Renderer: reading a GPU timer query failed ({e}) - disabling GPU timing for this session.")
                    self._gpu_timing_supported = False
                    self.last_gpu_ms = None
                    return
                self._gpu_query_pending[idx] = False
                self._gpu_query_stall_frames = 0
            else:
                # Not available yet - normal for the first frame or two
                # (the GPU hasn't caught up), not normal indefinitely. A
                # query that never, ever becomes available (no error, no
                # exception, just permanently GL_FALSE) is a real failure
                # mode on some driver/context combinations - confirmed
                # live: neither this method's own try/except above nor
                # on_initialize()'s ever fires, so without this counter
                # GPU timing would silently read as unavailable forever
                # with nothing in the log to explain why.
                self._gpu_query_stall_frames += 1
                if self._gpu_query_stall_frames > 300:
                    warning(
                        "GL44Renderer: a GPU timer query has not become available after "
                        f"{self._gpu_query_stall_frames} frames (glGetQueryObjectiv(..., "
                        "GL_QUERY_RESULT_AVAILABLE) keeps returning false, with no GL error) "
                        "- this driver/context likely doesn't actually complete GL_TIME_ELAPSED "
                        "queries despite accepting them. Disabling GPU timing for this session."
                    )
                    self._gpu_timing_supported = False
                    self.last_gpu_ms = None
                    return

        if self._gpu_query_pending[idx]:
            # Still not ready even after a full trip around the pool -
            # every slot is backed up waiting on the GPU. Skip starting a
            # new query this frame rather than reusing a slot whose old
            # result hasn't been read yet.
            self._gpu_query_active = False
            return

        try:
            glBeginQuery(GL_TIME_ELAPSED, self._gpu_query_ids[idx])
        except Exception as e:
            warning(f"GL44Renderer: glBeginQuery(GL_TIME_ELAPSED) failed ({e}) - disabling GPU timing for this session.")
            self._gpu_timing_supported = False
            self.last_gpu_ms = None
            return
        self._gpu_query_active = True

    def end_gpu_query(self):
        """Ends the query begin_gpu_query() started, if it actually
        started one this frame (see its own docstring for when it
        wouldn't have)."""
        if not self._gpu_timing_supported or not self._gpu_query_active:
            return

        try:
            glEndQuery(GL_TIME_ELAPSED)
        except Exception as e:
            warning(f"GL44Renderer: glEndQuery(GL_TIME_ELAPSED) failed ({e}) - disabling GPU timing for this session.")
            self._gpu_timing_supported = False
            self.last_gpu_ms = None
            self._gpu_query_active = False
            return
        self._gpu_query_pending[self._gpu_query_index] = True
        self._gpu_query_index = (self._gpu_query_index + 1) % len(self._gpu_query_ids)
        self._gpu_query_active = False

    def set_scissor(self, x: int, y: int, width: int, height: int):
        """See Renderer.set_scissor(). `x`/`y` come in top-left-origin,
        Y-down (UIRenderer's convention) - glScissor wants bottom-left
        origin, so `y` is flipped against the framebuffer height."""
        fb_height = self.window.framebuffer_size[1]
        glEnable(GL_SCISSOR_TEST)
        glScissor(int(x), int(fb_height - y - height), max(0, int(width)), max(0, int(height)))

    def clear_scissor(self):
        """See Renderer.clear_scissor()."""
        glDisable(GL_SCISSOR_TEST)

    def get_active_framebuffer(self):
        """See Renderer.get_active_framebuffer()."""
        return glGetIntegerv(GL_FRAMEBUFFER_BINDING)

    def bind_active_framebuffer(self, handle):
        """See Renderer.bind_active_framebuffer()."""
        if handle is not None:
            glBindFramebuffer(GL_FRAMEBUFFER, handle)

    def draw_line(self, start: tuple[int, int], end: tuple[int, int], width, color: 'Color'):
        """Draws a line segment from `start` to `end` using a dedicated line
        shader program (`self.line_program`), building a fresh 2-point
        VAO/VBO every call."""
        glLineWidth(width)
        line_vertices = np.array([
            -start[0], start[1],
            -end[0], end[1]
        ], dtype=np.float32)
        vao = glGenVertexArrays(1)
        vbo = glGenBuffers(1)
        glBindVertexArray(vao)
        glBindBuffer(GL_ARRAY_BUFFER, vbo)
        glBufferData(GL_ARRAY_BUFFER, line_vertices.nbytes, line_vertices, GL_STATIC_DRAW)

        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 0, None)

        glBindVertexArray(0)

        self.line_shader.use()
        self.line_shader.set_uniform('line_color', color)
       
        glBindVertexArray(vao)
        glDrawArrays(GL_LINES, 0, 2)
        glBindVertexArray(0)

    def draw_circle(self, radius, position, color):
        """Not yet implemented - always a no-op."""
        pass
