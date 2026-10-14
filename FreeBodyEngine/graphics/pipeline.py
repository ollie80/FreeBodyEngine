from FreeBodyEngine.core.service import Service
from FreeBodyEngine.core.update import UpdatePhase
from FreeBodyEngine import get_service, register_service_update, unregister_service_update, register_event_callback, unregister_event_callback
from FreeBodyEngine.utils import abstractmethod
from FreeBodyEngine.graphics.renderer import Renderer
from FreeBodyEngine.graphics.material import Material
from FreeBodyEngine.core.window import FRAMEBUFFER_RESIZE


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
    def draw(self):
        """Runs one frame's worth of render passes - called automatically every UpdatePhase.DRAW."""
        pass
