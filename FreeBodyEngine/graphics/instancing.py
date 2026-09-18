"""Call batching for Renderer.flush_opaque() (see graphics/renderer.py).

This is state-minimizing *batching* - grouping consecutive draws that share
a material/mesh so flush() issues them together, cutting redundant
glUseProgram/uniform/texture-bind churn - not real GPU instancing. Real
instancing (drawing N copies of a mesh in one glDrawElementsInstanced call
via a per-instance transform buffer) needs every mesh-drawing shader to
support a second, attribute-driven model-matrix path alongside the uniform
one it has today, which is a real ripple across default_shader/tilemap/text/
UI shaders - out of scope for this rebuild and tracked separately as the
engine roadmap's own "Instancing" item. Renderer.draw_mesh_instanced() is
real, correct infrastructure for that when it's built, but flush() below
does not call it - grouping here only ever changes call *order*, never call
*count*.
"""
from FreeBodyEngine.graphics.renderer import Call


def group_by_state(calls: list['Call']) -> list[list['Call']]:
    """Groups `calls` (preserving each group's relative order of first
    appearance) by `(material, mesh)` identity, so Renderer.flush() can draw
    every call sharing a material/mesh back-to-back. Materials/meshes are
    grouped by `id()` (object identity), not equality, since neither class
    defines `__eq__`."""
    order: list[tuple[int, int]] = []
    groups: dict[tuple[int, int], list['Call']] = {}

    for call in calls:
        key = (id(call.material), id(call.mesh))
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(call)

    return [groups[key] for key in order]
