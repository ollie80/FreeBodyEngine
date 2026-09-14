"""Broad-phase collision pruning for the rigid-body physics system.

Checking every pair of bodies in the scene with the real (comparatively
expensive) narrow-phase test in `contact.py` doesn't scale - a
`SpatialHash` buckets bodies by their AABB into a uniform grid first, so
only pairs that actually share a cell (i.e. could plausibly be touching)
ever reach narrow-phase at all.
"""

from FreeBodyEngine.math import Vector


class SpatialHash:
    """Buckets AABBs into a uniform grid of `cell_size`-sized cells. A
    body spanning multiple cells is inserted into every one its AABB
    touches. Rebuilt from scratch each physics step rather than
    incrementally maintained - bodies move only a little per step, but
    rebuilding is far simpler than tracking cell membership changes, and
    for the body counts an actual 2D game has (tens to low hundreds, not
    thousands), cheap enough to just redo every time."""
    def __init__(self, cell_size: float = 4.0):
        """`cell_size` should be roughly the size of a typical body in
        the scene - too small and most bodies span many cells (inflating
        the pair count with redundant lookups), too large and unrelated
        bodies on opposite sides of the world end up sharing a cell."""
        self.cell_size = cell_size
        self.cells: dict[tuple[int, int], list] = {}

    def clear(self):
        """Empties every cell, ready for the next step's `insert()` calls."""
        self.cells.clear()

    def _cell_range(self, aabb_min: Vector, aabb_max: Vector) -> tuple[int, int, int, int]:
        """Converts a world-space AABB into inclusive grid-cell coordinate
        bounds `(min_cx, min_cy, max_cx, max_cy)`."""
        cs = self.cell_size
        return (
            int(aabb_min.x // cs), int(aabb_min.y // cs),
            int(aabb_max.x // cs), int(aabb_max.y // cs),
        )

    def insert(self, item, aabb_min: Vector, aabb_max: Vector):
        """Adds `item` to every cell its `(aabb_min, aabb_max)` box overlaps."""
        min_cx, min_cy, max_cx, max_cy = self._cell_range(aabb_min, aabb_max)
        for cx in range(min_cx, max_cx + 1):
            for cy in range(min_cy, max_cy + 1):
                self.cells.setdefault((cx, cy), []).append(item)

    def find_pairs(self) -> set[tuple]:
        """Returns the set of candidate item pairs that share at least one
        cell - deduplicated (a pair spanning several shared cells is only
        reported once) and order-independent (keyed by `id()` so the same
        pair is never reported as both `(a, b)` and `(b, a)`). Still just
        candidates - the real narrow-phase test still has to confirm each
        pair actually overlaps."""
        pairs = set()
        for bucket in self.cells.values():
            n = len(bucket)
            for i in range(n):
                for j in range(i + 1, n):
                    a, b = bucket[i], bucket[j]
                    key = (a, b) if id(a) < id(b) else (b, a)
                    pairs.add(key)
        return pairs
