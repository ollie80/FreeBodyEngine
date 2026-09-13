"""Visual debuging nodes."""

from FreeBodyEngine import get_service
from FreeBodyEngine.core.node import Node2D
from FreeBodyEngine.core.files.loader import load_file
from FreeBodyEngine.graphics.mesh import Mesh, generate_circle, generate_quad
from FreeBodyEngine.graphics.renderer import Renderer

class Debug2D(Node2D):
    def __init__(self, mesh, material):
        super().__init__()
        self.mesh = mesh
        self.material = material

class RectangleColliderDebug(Debug2D):
    def __init__(self):
        super().__init__(generate_quad(), load_file('engine://debug/debug.fbmat'))

class CircleColliderDebug(Debug2D):
    def __init__(self):
        super().__init__(generate_circle(0.5), load_file('engine://debug/debug.fbmat'))

