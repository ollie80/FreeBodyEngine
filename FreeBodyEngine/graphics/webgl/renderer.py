"""WebGL2Renderer: the web backend's Renderer implementation - see this
package's other modules for the pieces it ties together (shader.py,
mesh.py, framebuffer.py, texture.py). Mirrors GL33Renderer's shape and
method set exactly (including which Renderer methods it does *not*
override - load_image/load_image_from_atlas/load_material are abstract on
the base class but GL33Renderer never implements them either, so nothing
in the engine actually calls them; this backend matches that instead of
inventing new behavior GL33 itself doesn't have).

The one structural difference from every desktop backend: OpenGL is a
global, thread-bound state machine (`glFoo(...)` always acts on "whatever
context is current"), so GL33Renderer never needs to pass a context object
around. WebGL2 is a JS *object* (`WebGL2RenderingContext`) - there's no
implicit "current context" - so this renderer resolves and caches it once,
as `self.gl`, and every other webgl/*.py module fetches it back via
`get_service('renderer').gl`."""
from FreeBodyEngine.graphics.renderer import Renderer
from FreeBodyEngine.graphics.color import Color
from FreeBodyEngine.graphics.material import BlendMode
from FreeBodyEngine.graphics.webgl.mesh import WebGL2Mesh
from FreeBodyEngine.graphics.webgl.image import WebGL2Image
from FreeBodyEngine.graphics.webgl.framebuffer import WebGL2Framebuffer
from FreeBodyEngine.graphics.webgl.shader import WebGL2Shader
from FreeBodyEngine.graphics.webgl.texture import WebGL2TextureManager
from FreeBodyEngine import get_service, service_exists
from fbusl.injector import Injector

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from FreeBodyEngine.graphics.mesh import Mesh
    from FreeBodyEngine.graphics.material import Material


class WebGL2Renderer(Renderer):
    """The WebGL2 renderer - see this module's own docstring."""

    def __init__(self):
        """Sets the backend's Mesh subclass; the actual `gl` context is
        resolved in on_initialize() from the window (which must already
        exist and own a canvas/context by then - see WebWindow)."""
        super().__init__()
        self.mesh_class = WebGL2Mesh

    def on_initialize(self):
        """Resolves this session's WebGL2 context from the (required -
        unlike GL33Renderer, there's no true headless-compute path for
        web yet) 'window' service, enables standard alpha blending
        (matching GL33Renderer's own BlendMode.TRANSPARENT default - see
        its comment on why UI/sprite transparency depends on this being
        on), and sets the initial viewport."""
        super().on_initialize()

        if not service_exists('window'):
            raise RuntimeError(
                "WebGL2Renderer requires a 'window' service (WebWindow) to already be "
                "registered - there is no headless/context-less path for the web backend."
            )

        self.window = get_service('window')
        self.gl = self.window.gl

        width, height = self.window.framebuffer_size
        self.gl.viewport(0, 0, width, height)

        self.texture_manager = WebGL2TextureManager()

        self.gl.enable(self.gl.BLEND)
        self.gl.blendFunc(self.gl.SRC_ALPHA, self.gl.ONE_MINUS_SRC_ALPHA)
        self._current_blend_mode = BlendMode.TRANSPARENT

        from FreeBodyEngine.core.files import get_file
        self.line_shader = self.load_shader(get_file("engine://shader/line.fbvert"), get_file("engine://shader/line.fbfrag"))

    def create_buffer(self, data):
        """Not supported yet - see WebGL2Shader.set_buffer()'s own note;
        nothing reaches this without a project shader declaring an FBUSL
        `@buffer` block, which WebGL2Generator's empty CAPABILITIES
        already rejects at compile time before this could ever run."""
        raise NotImplementedError("Uniform buffer objects aren't supported by the web backend yet.")

    def get_max_buffer_size(self) -> int:
        raise NotImplementedError("Uniform buffer objects aren't supported by the web backend yet.")

    def resize(self, size: tuple[int, int]):
        """Updates the WebGL2 viewport to `size` - the canvas's own
        drawing-buffer resolution is already updated by WebWindow.update()
        before this fires (it's what triggers the FRAMEBUFFER_RESIZE event
        this is subscribed to - see Renderer.on_initialize())."""
        self.gl.viewport(0, 0, size[0], size[1])

    def get_mesh_class(self) -> type[WebGL2Mesh]:
        return WebGL2Mesh

    def get_image_class(self):
        return WebGL2Image

    def destroy(self):
        """No explicit GPU resource teardown - the WebGL2 context (and
        everything on it) is released the moment the browser tab itself
        goes away; there is no separate "close the context" call the way
        a native GL context has wglDeleteContext/etc."""
        pass

    @property
    def create_framebuffer(self):
        """Returns WebGL2Framebuffer."""
        return WebGL2Framebuffer

    def clear(self, color: 'Color'):
        """Clears the currently bound framebuffer's color and depth
        buffers to `color`."""
        r, g, b, a = color.float_normalized_a
        self.gl.clearColor(r, g, b, a)
        self.gl.clear(self.gl.COLOR_BUFFER_BIT | self.gl.DEPTH_BUFFER_BIT)

    def set_blend_mode(self, mode: BlendMode):
        """See GL33Renderer.set_blend_mode() - identical logic against
        `self.gl` instead of PyOpenGL's global functions."""
        if mode == self._current_blend_mode:
            return
        self._current_blend_mode = mode
        gl = self.gl

        if mode == BlendMode.OPAQUE:
            gl.disable(gl.BLEND)
            gl.depthMask(True)
        elif mode == BlendMode.TRANSPARENT:
            gl.enable(gl.BLEND)
            gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA)
            gl.depthMask(False)
        elif mode == BlendMode.ADDITIVE:
            gl.enable(gl.BLEND)
            gl.blendFunc(gl.SRC_ALPHA, gl.ONE)
            gl.depthMask(True)

    def load_shader(self, vertex, fragment, injector: Injector = Injector(), geometry=None):
        """Compiles `vertex`/`fragment` FBUSL source into a WebGL2Shader.
        `geometry` is accepted only for interface parity - see
        WebGL2Shader.__init__()'s own note on why a non-None value here
        would already have failed before reaching this point."""
        return WebGL2Shader(vertex, fragment, injector, geometry)

    def draw_mesh_instanced(self, mesh, material, model_matrices, camera):
        raise NotImplementedError("GPU instancing isn't supported by the web backend yet.")

    def enable_depth_testing(self):
        self.gl.enable(self.gl.DEPTH_TEST)

    def disable_depth_testing(self):
        self.gl.disable(self.gl.DEPTH_TEST)

    def draw_mesh(self, mesh: 'Mesh', material: 'Material'):
        """Binds `material` and draws `mesh`'s indexed triangles. Unlike
        GL33Renderer, there's no wireframe polygon-mode path -
        `gl.POLYGON_MODE`/`glPolygonMode` don't exist in WebGL2/GLES at
        all (wireframe rendering there needs a real line-topology mesh or
        a shader-based edge trick instead), so a material with
        `render_mode == "wireframe"` just draws filled on this backend."""
        material.use()
        material.shader.use()

        self.gl.bindVertexArray(mesh.vao)
        self.gl.drawElements(self.gl.TRIANGLES, len(mesh.indices), mesh.gl_index_type, 0)
        self.gl.bindVertexArray(None)

    def set_scissor(self, x: int, y: int, width: int, height: int):
        """See Renderer.set_scissor() - `y` flipped against the
        framebuffer height, matching GL33Renderer.set_scissor()'s own
        top-left-to-bottom-left conversion."""
        gl = self.gl
        fb_height = self.window.framebuffer_size[1]
        gl.enable(gl.SCISSOR_TEST)
        gl.scissor(int(x), int(fb_height - y - height), max(0, int(width)), max(0, int(height)))

    def clear_scissor(self):
        self.gl.disable(self.gl.SCISSOR_TEST)

    def draw_line(self, start: tuple[float, float], end: tuple[float, float], width, color: 'Color'):
        """Not yet implemented - GLES/WebGL2 also don't support
        `gl.lineWidth()` beyond 1px on most implementations (unlike
        GL33Renderer's `glLineWidth`), so this needs a real quad-based
        thick-line mesh rather than a straight port; deferred rather than
        silently drawing a 1px line no `width` argument actually
        controls."""
        raise NotImplementedError("draw_line() isn't supported by the web backend yet.")

    def draw_circle(self, radius, position, color):
        """Not implemented on GL33Renderer either - see its own stub."""
        pass
