from FreeBodyEngine.core.service import Service
from FreeBodyEngine.ui.element import RootElement, UIElement, GenericElement
from FreeBodyEngine.core.update import UpdatePhase
from FreeBodyEngine import register_event_callback, unregister_event_callback, register_service_update, unregister_service_update, get_service
from FreeBodyEngine.core.window import WINDOW_RESIZE

class UIManager(Service):
    def __init__(self, styles: dict[str, any] = {}):
        super().__init__('ui')
        
        win_size = get_service('window').size 
        self.root = RootElement(styles, win_size[0], win_size[1])

    def on_initialize(self):
        register_event_callback(WINDOW_RESIZE, self.resize)
        register_service_update(UpdatePhase.DRAW, self.draw, 1000)

    def on_destroy(self):
        unregister_event_callback(WINDOW_RESIZE, self.resize)
        unregister_service_update(UpdatePhase.DRAW, self.draw)

    def resize(self, size: tuple[int, int]):
        self.root.layout.width = size[0]
        self.root.layout.height = size[1]

    def add(self, element: UIElement):
        self.root.add(element)

    def draw(self):
        self.root._draw()

    def remove(self, element: UIElement):
        self.root.remove(element)

    def update(self):
        self.root._update()
        
        self.update_layout(self.root)