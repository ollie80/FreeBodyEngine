from FreeBodyEngine.core.service import Service
from FreeBodyEngine import register_service_update, unregister_service_update, get_service
from FreeBodyEngine.core.update import UpdatePhase
from FreeBodyEngine.graphics.mesh import generate_quad
from FreeBodyEngine.math import Transform, Vector
from FreeBodyEngine.core.camera import Camera, CAMERA_PROJECTION
from FreeBodyEngine.graphics.color import Color

import numpy as np

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from FreeBodyEngine.ui import UIManager
    from FreeBodyEngine.graphics.material import Material

UI_DRAW_PRIORITY = 9999999

class UICamera(Camera):
    def __init__(self):
        super().__init__(CAMERA_PROJECTION.ORTHOGRAPHIC,  Color('#ffffff00'), 1)

    def handle_window_resize(self, size: tuple[int, int]):
        self.view_matrix = np.array([0,0,0,0,
                                     0,0,0,0,
                                     0,0,0,0,
                                     0,0,0,0])

class UIRenderer(Service):
    def __init__(self):
        super().__init__('ui_renderer')
        self.dependencies.append('ui')

        self.quad = generate_quad()
        self.material: 'Material' = load_material('engine/ui/element.fbmat')

        self.camera = UICamera()

    def on_initialize(self):
        register_service_update(UpdatePhase.DRAW, self.draw, UI_DRAW_PRIORITY)
        self.ui: 'UIManager' = get_service('ui')

    def on_destroy(self):
        unregister_service_update(UpdatePhase.DRAW, self.draw)

    def draw(self):
        empty_transform = Transform(Vector(), 0, Vector())

        for id in self.ui.root.children:
            element = self.ui.root.children[id]

            self.material.shader.set_uniform('layout', (element._layout.x, element._layout.y, element._layout.width, element._layout.height))

            get_service('renderer').draw_mesh(self.quad, self.material, empty_transform, self.camera)