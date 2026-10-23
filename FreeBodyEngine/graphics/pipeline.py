from FreeBodyEngine.core.service import Service
from FreeBodyEngine.core.update import UpdatePhase
from FreeBodyEngine import get_service, register_service_update, unregister_service_update, register_event_callback, unregister_event_callback
from FreeBodyEngine.utils import abstractmethod
from FreeBodyEngine.graphics.renderer import Renderer
from FreeBodyEngine.graphics.material import Material
from FreeBodyEngine.core.window import FRAMEBUFFER_RESIZE
from FreeBodyEngine.graphics.framebuffer import Framebuffer


# Copies one framebuffer attachment into another framebuffer - how a
# pipeline hands its finished image to a framebuffer it was given rather
# than the window (see GraphicsPipeline._present). A shader rather than a
# blit because Framebuffer.draw() only ever blits to the window.
PRESENT_VERT = """
@input
vertex: vec3
uvs: vec2
normal: vec3

@output
uv: vec2

def main():
    # From the clip-space position, not the quad's `uvs`: those are authored
    # for the engine's rotated standalone textures, and a framebuffer
    # attachment is not rotated - see lite/combine.fbvert.
    uv = vec2(vertex.x * 0.5 + 0.5, vertex.y * 0.5 + 0.5)
    VERTEX_POSITION = vec4(vertex.x, vertex.y, 0.0, 1.0)
"""

PRESENT_FRAG = """
@uniform
Image: texture

@input
uv: vec2

@output
result: vec4

def main():
    result = sample(Image, uv)
"""


class GraphicsPipeline(Service):
    """Abstract base for a rendering pipeline (e.g. PBRPipeline) - owns the
    actual sequence of passes/draw calls a frame goes through, built on top
    of a Renderer backend's low-level drawing primitives. Registers itself
    as the 'graphics' service and depends on 'renderer'.
    """
    def __init__(self):
        """Declares 'renderer' as a service dependency."""
        super().__init__('graphics')
        self.dependencies.append('renderer')

    def on_initialize(self):
        """Registers draw() to run every UpdatePhase.DRAW, fetches the 'renderer' service, and subscribes resize() to FRAMEBUFFER_RESIZE."""
        register_service_update(UpdatePhase.DRAW, self.draw)
        self.renderer = get_service('renderer')
        self.renderer: Renderer
        register_event_callback(FRAMEBUFFER_RESIZE, self.resize)

    def on_destroy(self):
        """Unregisters draw() from UpdatePhase.DRAW and resize() from FRAMEBUFFER_RESIZE."""
        unregister_service_update(UpdatePhase.DRAW, self.draw)
        unregister_event_callback(FRAMEBUFFER_RESIZE, self.resize)

    # Which shader pair a Tilemap draws with. A tilemap writes whatever
    # channels the pipeline's passes expect, so the pipeline owns the choice -
    # the PBR G-buffer wants seven outputs and LitePipeline's surface pass
    # wants three, and a tilemap cannot know which it is being drawn into.
    tilemap_shader = ('engine://shader/graphics/tilemap.fbvert',
                      'engine://shader/graphics/tilemap.fbfrag')

    @abstractmethod
    def resize(self, size: tuple[int, int]):
        """Called on FRAMEBUFFER_RESIZE with the new framebuffer `size` (pixels) - subclasses resize whatever framebuffers/render targets they own."""
        pass

    @abstractmethod
    def create_material(self, data) -> Material:
        """Builds and returns this pipeline's Material subclass from `data` (e.g. a parsed .fbmat file)."""
        pass

    @abstractmethod
    def draw_scene(self, framebuffer: Framebuffer = None):
        """Renders the active scene through this pipeline's passes.

        With no `framebuffer` the finished image goes to the window, as
        every frame does. Given one, it goes into that framebuffer's first
        colour attachment instead and the window is left untouched - for a
        render-to-texture target such as a minimap, a mirror or an editor
        viewport.

        The passes themselves always run in the pipeline's own window-sized
        buffers, so the image is scaled to fit `framebuffer`, and the camera
        keeps the window's aspect ratio."""
        pass

    def draw(self):
        """Runs one frame's worth of render passes - called automatically every UpdatePhase.DRAW."""
        self.draw_scene()

    def _bind_output(self, framebuffer: Framebuffer | None, window_size: tuple[int, int]):
        """Binds wherever the finished image goes: the window, or the first
        colour attachment of `framebuffer`. A final pass that draws its own
        fullscreen quad (rather than going through _present()) calls this,
        then _finish_output()."""
        if framebuffer is None:
            self.renderer.bind_window_framebuffer(window_size)
        else:
            framebuffer.bind()
            framebuffer.set_draw_buffers(framebuffer.color_attachments[:1])

    def _finish_output(self, framebuffer: Framebuffer | None, window_size: tuple[int, int]):
        """Hands the frame back to the window after drawing into
        `framebuffer` - whatever draws next (UI, text) expects the window
        bound, at the window's viewport."""
        if framebuffer is not None:
            framebuffer.unbind()
            self.renderer.bind_window_framebuffer(window_size)

    def _present(self, source: Framebuffer, attachment: str, framebuffer: Framebuffer | None,
                 window_size: tuple[int, int]):
        """Puts `source`'s `attachment` wherever this frame is going: blitted
        to the window when `framebuffer` is None, otherwise copied into
        `framebuffer` (see draw_scene)."""
        if framebuffer is None:
            source.unbind()
            source.draw(attachment, window_size)
            return

        if getattr(self, '_present_shader', None) is None:
            from fbusl.injector import Injector
            from FreeBodyEngine.graphics.mesh import generate_quad
            self._present_shader = self.renderer.load_shader(PRESENT_VERT, PRESENT_FRAG, Injector(), None)
            self._present_quad = generate_quad(2.0, 2.0)

        self._present_shader['Image'] = self.renderer.texture_manager.wrap_external_texture(
            source.get_attachment_texture(attachment))
        self._bind_output(framebuffer, window_size)
        self.renderer.disable_depth_testing()
        self._present_shader.use()
        self._present_quad.draw()
        self._finish_output(framebuffer, window_size)
