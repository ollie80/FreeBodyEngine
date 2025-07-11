"""Visual debuging nodes."""

from FreeBodyEngine.utils import load_material
from FreeBodyEngine.core.node import Node2D
from FreeBodyEngine.graphics.mesh import Mesh
from FreeBodyEngine.graphics.renderer import Renderer

class Debug2D(Node2D):
    def __init__(self, mesh, material):
        super().__init__()
        self.mesh = mesh
        self.material = material

class RectangleColliderDebug(Debug2D):
    def __init__(self, renderer: Renderer):
        super().__init__(renderer.mesh_class.generate_quad(), load_material('engine/debug/debug.fbmat'))

class CircleColliderDebug(Debug2D):
    def __init__(self, renderer: Renderer):
        super().__init__(renderer.mesh_class.generate_circle(0.5), load_material('engine/debug/debug.fbmat'))
