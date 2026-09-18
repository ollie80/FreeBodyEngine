"""Visual debuging nodes."""

from typing import Literal
from FreeBodyEngine import get_service
from FreeBodyEngine.core.node import Node2D
from FreeBodyEngine.core.files.loader import load_file
from FreeBodyEngine.graphics.mesh import Mesh, generate_circle, generate_quad, generate_polygon
from FreeBodyEngine.graphics.renderer import Renderer

class Debug2D(Node2D):
    """Base node for 2D debug-visualization overlays - wraps a mesh and
    material so a debug shape can be drawn without going through a full
    Sprite (e.g. for collider outlines)."""
    def __init__(self, draw_type: Literal["mesh", "line"] ="mesh", mesh=None, material=None, line_start=None, line_end=None, line_width=None):
        """Stores the given mesh and material for later drawing."""
        super().__init__()
        self.draw_type = draw_type
        self.mesh = mesh
        self.material = material
        self.line_start = line_start
        self.line_end = line_end
        self.line_width = line_width

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
        super().__init__(draw_type='mesh', mesh=generate_circle(0.5), material=load_file('engine://debug/debug.fbmat'))

class PolygonColliderDebug(Debug2D):
    """Debug overlay drawn as a filled polygon, added as a child by
    `PolygonCollider2D.toggle_debug_visuals()` to visualize a
    PolygonCollider2D's extent."""
    def __init__(self, local_vertices):
        """Builds the debug polygon mesh from the same `local_vertices` the
        PolygonCollisionShape itself uses, and loads the shared
        `engine://debug/debug.fbmat` debug material."""
        super().__init__(draw_type='mesh', mesh=generate_polygon([(v.x, v.y) for v in local_vertices]), material=load_file('engine://debug/debug.fbmat'))



