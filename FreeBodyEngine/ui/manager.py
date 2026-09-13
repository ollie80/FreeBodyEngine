from FreeBodyEngine.core.service import Service
from FreeBodyEngine.ui.element import RootElement, UIElement, GenericElement
from FreeBodyEngine.core.update import UpdatePhase
from FreeBodyEngine import register_event_callback, unregister_event_callback, register_service_update, unregister_service_update, get_service
from FreeBodyEngine.core.window import FRAMEBUFFER_RESIZE

class UIManager(Service):
    """Engine service owning the UI tree's root element - the entry point for
    adding/removing top-level UI elements and driving their layout/animation update."""

    def __init__(self, styles: dict[str, any] = {}):
        """Args:
            styles: Root-level styles, sized to the current framebuffer.
        """
        super().__init__('ui')

        win_size = get_service('window').framebuffer_size
        self.root = RootElement(win_size[0], win_size[1], styles)

    def on_initialize(self):
        """Registers the resize/draw/update callbacks this service needs while active."""
        register_event_callback(FRAMEBUFFER_RESIZE, self.resize)
        register_service_update(UpdatePhase.DRAW, self.draw, 1000)
        register_service_update(UpdatePhase.UPDATE, self.update)

    def on_destroy(self):
        """Unregisters the callbacks registered in `on_initialize`."""
        unregister_event_callback(FRAMEBUFFER_RESIZE, self.resize)
        unregister_service_update(UpdatePhase.DRAW, self.draw)
        unregister_service_update(UpdatePhase.UPDATE, self.update)

    def resize(self, size: tuple[int, int]):
        """Resizes the root layout area to match the new framebuffer size."""
        self.root.layout.width = size[0]
        self.root.layout.height = size[1]


    def add(self, element: UIElement):
        """Adds `element` as a top-level child of the UI root."""
        self.root.add(element)

    def draw(self):
        """Draws the UI tree."""
        self.root._draw()

    def remove(self, element: UIElement):
        """Removes `element` from the UI root's children."""
        self.root.remove(element)

    def update(self):
        """Advances any running style animations, then recalculates the whole
        tree's layout from the (possibly now-changed) styles."""

        self.root._update()

        self.root.calculate_layout()
