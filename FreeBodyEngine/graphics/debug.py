"""Visual debuging nodes."""

from FreeBodyEngine import get_service
from FreeBodyEngine.core.node import Node2D
from FreeBodyEngine.core.files.loader import load_file
from FreeBodyEngine.graphics.mesh import Mesh, generate_circle, generate_quad
from FreeBodyEngine.graphics.renderer import Renderer

class Debug2D(Node2D):
    """Base node for 2D debug-visualization overlays - wraps a mesh and
    material so a debug shape can be drawn without going through a full
    Sprite (e.g. for collider outlines)."""
    def __init__(self, mesh, material):
        """Stores the given mesh and material for later drawing."""
        super().__init__()
        self.mesh = mesh
        self.material = material

class RectangleColliderDebug(Debug2D):
    """Debug overlay drawn as a quad, added as a child by
    `RectangleCollider2D.toggle_debug_visuals()` to visualize a
    RectangleCollider2D's extent."""
    def __init__(self):
        """Builds the debug quad mesh and loads the shared
        `engine://debug/debug.fbmat` debug material."""
        super().__init__(generate_quad(), load_file('engine://debug/debug.fbmat'))

class CircleColliderDebug(Debug2D):
    """Debug overlay drawn as a circle, added as a child by
    `CircleCollider2D.toggle_debug_visuals()` to visualize a
    CircleCollider2D's extent."""
    def __init__(self):
        """Builds the debug circle mesh (radius 0.5, i.e. unit diameter, so
        the node's own scale maps directly onto the collider's radius) and
        loads the shared `engine://debug/debug.fbmat` debug material."""
        super().__init__(generate_circle(0.5), load_file('engine://debug/debug.fbmat'))

