"""CPU-side BVH construction for GLRaytraceShader (graphics/gl33/compute.py).

This is a data-format contract, not a codegen concern: the layout produced
here (2 texels/node AABB, one int4 meta/node, a fixed traversal-stack depth
on the GLSL side) is fixed by GL33Generator._generate_raytrace_intrinsics().
A simple median-split builder is enough to prove the mechanism works - a
surface-area-heuristic (SAH) builder would produce a better-quality BVH for
the same primitive count, but is a quality optimization, not a correctness
requirement, and is left as a follow-on.
"""
import numpy as np


def build_bvh(triangles: np.ndarray, max_leaf_size: int = 4):
    """Builds a median-split BVH over `triangles` (shape (N, 3, 3), float32
    vertex positions - N triangles, 3 vertices each, 3 floats per vertex).

    Returns `(aabb_array, meta_array, ordered_triangles)`:
    - `aabb_array`: (num_nodes*2, 4) float32 - 2 texels per node, node `i`'s
      AABB min at row `2*i`, max at row `2*i+1` (the unused 4th component is
      left 0). Node 0 is always the root.
    - `meta_array`: (num_nodes, 4) int32 - `(left_child, right_child,
      first_prim, prim_count)` per node. A leaf has `prim_count > 0` and its
      primitives are `ordered_triangles[first_prim : first_prim+prim_count]`;
      an interior node has `prim_count == 0` and real `left_child`/`right_child`.
    - `ordered_triangles`: (N, 3, 3) float32 - `triangles` reordered so each
      leaf's primitives are contiguous. Upload *this*, not the original
      `triangles`, as the raytrace shader's `triangles` buffer field -
      `meta_array`'s `first_prim` indices refer to this order.
    """
    triangles = np.asarray(triangles, dtype=np.float32)
    if len(triangles) == 0:
        raise ValueError("build_bvh requires at least one triangle")

    tri_mins = triangles.min(axis=1)
    tri_maxs = triangles.max(axis=1)
    centroids = (tri_mins + tri_maxs) * 0.5

    nodes = []
    order = []

    def build(indices) -> int:
        """Recursively builds one BVH node over `indices` (triangle
        indices) and returns its index into `nodes`. At or below
        `max_leaf_size` it becomes a leaf: its triangles are appended to
        `order` (accumulating the final `ordered_triangles` permutation)
        and recorded as a contiguous `first`/`count` range. Otherwise it's
        an interior node - `indices` is split at the median centroid along
        the node AABB's longest axis (median-split, not a surface-area
        heuristic; see module docstring) and the two halves recurse into
        `left`/`right` children."""
        node_index = len(nodes)
        nodes.append(None)

        node_min = tri_mins[indices].min(axis=0)
        node_max = tri_maxs[indices].max(axis=0)

        if len(indices) <= max_leaf_size:
            first = len(order)
            order.extend(indices)
            nodes[node_index] = {
                "min": node_min, "max": node_max,
                "left": 0, "right": 0, "first": first, "count": len(indices),
            }
            return node_index

        extent = node_max - node_min
        axis = int(np.argmax(extent))
        sorted_indices = sorted(indices, key=lambda i: centroids[i][axis])
        mid = len(sorted_indices) // 2

        left_child = build(sorted_indices[:mid])
        right_child = build(sorted_indices[mid:])

        nodes[node_index] = {
            "min": node_min, "max": node_max,
            "left": left_child, "right": right_child, "first": 0, "count": 0,
        }
        return node_index

    build(list(range(len(triangles))))

    aabb_array = np.zeros((len(nodes) * 2, 4), dtype=np.float32)
    meta_array = np.zeros((len(nodes), 4), dtype=np.int32)
    for i, node in enumerate(nodes):
        aabb_array[i * 2, :3] = node["min"]
        aabb_array[i * 2 + 1, :3] = node["max"]
        meta_array[i] = (node["left"], node["right"], node["first"], node["count"])

    ordered_triangles = triangles[order]
    return aabb_array, meta_array, ordered_triangles
