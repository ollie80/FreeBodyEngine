from FreeBodyEngine.core.node import Node2D
from FreeBodyEngine.math import Vector
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from FreeBodyEngine.graphics.mesh import Mesh
    from FreeBodyEngine.graphics.material import Material


class MeshNode2D(Node2D):
    """A Node2D that draws an arbitrary Mesh with a Material - the 2D
    equivalent of Sprite2D for solid geometry that isn't a textured quad
    (e.g. a filled circle/polygon, generated via graphics/mesh.py's
    generate_circle()/generate_polygon()).

    Submitted into the normal opaque/transparent draw queue alongside
    every other sprite/model (see PBRPipeline._collect()/draw()), so it's
    properly depth-tested against the rest of the scene and lit by the
    deferred composite pass - unlike graphics/debug.py's Debug2D nodes,
    which are drawn as an unlit, undepth-tested overlay *after* the
    lighting composite pass and are meant only for collider/debug
    visualization, not real scene geometry.
    """
    def __init__(self, mesh: 'Mesh', material: 'Material', position: Vector = Vector(), rotation: float = 0.0, scale: Vector = Vector(1, 1)):
        """Stores the `mesh`/`material` this node draws at its own 2D
        transform."""
        super().__init__(position, rotation, scale)
        self.mesh = mesh
        self.material = material
