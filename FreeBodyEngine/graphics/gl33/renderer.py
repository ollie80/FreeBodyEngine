from FreeBodyEngine.graphics.renderer import Renderer
from FreeBodyEngine.graphics.color import Color
from FreeBodyEngine.graphics.gl33 import GLImage, GLMesh, GLFramebuffer
from FreeBodyEngine.graphics.sprite import Sprite
from FreeBodyEngine.graphics.gl33.shader import GLShader
from FreeBodyEngine.graphics.gl33.texture import GLTextureManager
from fbusl.injector import Injector 
from FreeBodyEngine.graphics.texture import Texture
from FreeBodyEngine.graphics.material import Material
from FreeBodyEngine import DEVMODE, get_flag
from FreeBodyEngine.graphics.gl33.buffer import UBOBuffer

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from FreeBodyEngine.core.main import Main
    from FreeBodyEngine.core.camera import Camera
    from FreeBodyEngine.graphics.material import Material
    from FreeBodyEngine.math import Vector

from FreeBodyEngine import get_service, service_exists
from FreeBodyEngine.utils import get_platform

import numpy as np

if get_platform() == "win32": 
    from OpenGL import WGL

from OpenGL.GL import *
from OpenGL.GL.ARB.debug_output import * # for debug_callback


@GLDEBUGPROC
def debug_callback(source, type, id, severity, length, message, userParam):
    """GL_DEBUG_OUTPUT callback (see glDebugMessageCallback in on_initialize)
    - decodes the driver's UTF-8 message and prints it, so GL errors/
    warnings surface immediately instead of needing a manual glGetError()
    poll."""
    msg = ctypes.string_at(message, length).decode('utf-8')
    print(f"[OpenGL DEBUG] {msg}")

class GL33Renderer(Renderer):
    """
    The OpenGL renderer. Uses OpenGL version 330 Core.
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

        self.mesh_class = GLMesh

    def on_initialize(self):
        """Creates (or attaches to) the OpenGL context for the current window
        backend (glfw/wayland/win32/x11), or - if no 'window' service is
        registered at all - assumes a raw offscreen context already exists
        and is current (a true headless compute session, see
        graphics.ensure_gpu_context()). Also enables GL_DEBUG_OUTPUT and
        sets the initial viewport."""
        super().on_initialize()

        if service_exists('window'):
            self.window = get_service('window')

            if self.window.window_type == "glfw":
                from glfw import make_context_current
                make_context_current(self.window._window)
            elif self.window.window_type == 'wayland':
                from FreeBodyEngine.graphics.gl33.context.wayland import create_wayland_opengl_context
                self.context = create_wayland_opengl_context(self.window, get_flag(DEVMODE, False))
            elif get_platform() == "win32":
                from FreeBodyEngine.graphics.gl33.context.win32 import create_win32_opengl_context
                self.context = create_win32_opengl_context(self.window, get_flag(DEVMODE, False))
            elif self.window.window_type == 'x11':
                from FreeBodyEngine.graphics.gl33.context.x11 import create_x11_opengl_context
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

        glEnable(GL_DEBUG_OUTPUT)
        glEnable(GL_DEBUG_OUTPUT_SYNCHRONOUS)
        glDebugMessageCallback(debug_callback, None)
        # framebuffer_size (physical/device pixels), not size (logical/
        # window-manager pixels) - these differ under HiDPI or fractional
        # display scaling, and glViewport must match the actual
        # framebuffer being rendered into. resize() below (called on the
        # FRAMEBUFFER_RESIZE event) already gets this right - this initial
        # setup was the one place still using the wrong one, so the
        # viewport was wrong from the moment the window opened on any
        # scaled display, not just after a resize. (width/height were
        # already resolved above, using the window's real size if one
        # exists, or a headless-compute fallback if not.)
        glViewport(0, 0, width, height)

        self.texture_manager = GLTextureManager()
        
    def create_buffer(self, data):
        """Wraps `data` in a UBOBuffer, GL33's Buffer implementation."""
        return UBOBuffer(data)

    def get_max_buffer_size(self) -> int:
        """Returns the max size of a UBOBuffer, in bytes."""
        return UBOBuffer.get_max_size()

    def resize(self, size: tuple[int, int]):
        """Updates the GL viewport to `size`, and resizes the platform-specific window surface (wayland/x11) to match."""
        glViewport(0, 0, size[0], size[1])

        if self.window.window_type == 'wayland':

            from FreeBodyEngine.graphics.gl33.context.wayland import resize_wayland_opengl_surface
            resize_wayland_opengl_surface(self.window, size[0], size[1])
        elif self.window.window_type == 'x11':
            from FreeBodyEngine.graphics.gl33.context.x11 import resize_x11_opengl_surface
            resize_x11_opengl_surface(self.window, size[0], size[1])

    def get_mesh_class(self) -> type[GLMesh]:
        """Returns GLMesh."""
        return GLMesh

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
            from FreeBodyEngine.graphics.gl33.context.wayland import swap_wayland_opengl_buffers
            swap_wayland_opengl_buffers(self.window)
        elif self.window.window_type == 'x11':
            from FreeBodyEngine.graphics.gl33.context.x11 import swap_x11_opengl_buffers
            swap_x11_opengl_buffers(self.window)


    @property
    def create_framebuffer(self):
        """Returns GLFramebuffer."""
        return GLFramebuffer

    def clear(self, color: 'Color'):
        """Clears the color and depth buffers of the currently bound framebuffer to `color`."""
        glClearColor(*color.float_normalized_a)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        glClear(GL_COLOR_BUFFER_BIT)

    def load_shader(self, vertex, fragment, injector: Injector = Injector, geometry=None):
        """Compiles `vertex`/`fragment` (and optional `geometry`) FBUSL source into a GLShader, using `injector` to resolve engine-provided builtins."""
        return GLShader(vertex, fragment, injector, geometry)

    def draw_mesh_instanced(self, mesh, instances, material, transform, camera):
        """Draws `instances` copies of `mesh` in one glDrawElementsInstanced
        call, first setting `material`'s model/view/proj uniforms from
        `transform`/`camera`."""
        material.use(transform, camera)
        material.shader.use()

        glBindVertexArray(mesh.vao)
        glDrawElementsInstanced(GL_TRIANGLES, len(mesh.indices), GL_UNSIGNED_INT, ctypes.c_void_p(0), instances)

        glBindVertexArray(0) 

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

    def draw_line(self, start: tuple[int, int], end: tuple[int, int], width, color: 'Color'):
        """Draws a line segment from `start` to `end` using a dedicated line
        shader program (`self.line_program`), building a fresh 2-point
        VAO/VBO every call."""
        glLineWidth(width)
        line_vertices = np.array([
            -start[0], start[1],
            end[0], end[1]
        ], dtype=np.float32)
        vao = glGenVertexArrays(1)
        vbo = glGenBuffers(1)
        glBindVertexArray(vao)
        glBindBuffer(GL_ARRAY_BUFFER, vbo)
        glBufferData(GL_ARRAY_BUFFER, line_vertices.nbytes, line_vertices, GL_STATIC_DRAW)

        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 0, None)

        glBindVertexArray(0)

        glUseProgram(self.line_program)

        glUniform4f(glGetUniformLocation(self.line_program, "line_color"), *color.float_normalized_a)

        glBindVertexArray(vao)
        glDrawArrays(GL_LINES, 0, 2)
        glBindVertexArray(0)

    def draw_circle(self, radius, position, color):
        """Not yet implemented - always a no-op."""
        pass
