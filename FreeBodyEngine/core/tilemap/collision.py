"""Turning a tilemap layer's solid tiles into collision geometry.

The arcade physics system finds collidable geometry by walking the scene for
`Collider2D` nodes and resolving each against a body's own shape (see
core/physics/__init__.py). A tilemap has no colliders of its own, so marking
a layer `collision = True` generates them - and generates as few as it can,
by merging runs of solid tiles into maximal rectangles rather than emitting
one collider per tile.

That merge matters more than it looks: `PhysicsBody._check_collisions` walks
every `Collider2D` in the scene for every body, every physics step, so the
collider count is paid repeatedly. A plain 40-tile wall is one rectangle
here instead of forty.
"""

from FreeBodyEngine.core.collider import RectangleCollider2D
from FreeBodyEngine.math import Vector

from typing import Iterable


class TilemapCollider2D(RectangleCollider2D):
    """One merged rectangle of a tilemap's collision geometry.

    A subclass purely so the tilemap can find and replace the colliders it
    generated without touching any a project added itself - it is an ordinary
    RectangleCollider2D in every other respect, and in particular still
    carries a RectangleCollisionShape, which is what
    `PhysicsBody._resolve_collision` dispatches on.
    """

    def __init__(self, position=Vector(), scale=Vector(1, 1)):
        super().__init__(position, 0, scale)


def merge_solid_rects(solid: Iterable[tuple[int, int]]) -> list[tuple[int, int, int, int]]:
    """Covers every position in `solid` with as few axis-aligned rectangles as
    a greedy sweep manages, returning them as `(x, y, width, height)` in tile
    units.

    Greedy rather than optimal: each uncovered cell, taken in row-major
    order, is extended as far right as it can go and then down as far as the
    full width stays solid. Optimal rectangle covering is a much harder
    problem and buys little here - the shapes that matter in practice (walls,
    rooms, corridors) are already runs and rectangles, and this collapses
    them completely.
    """
    remaining = set(solid)
    rects: list[tuple[int, int, int, int]] = []

    for x, y in sorted(remaining, key=lambda p: (p[1], p[0])):
        if (x, y) not in remaining:
            continue

        width = 1
        while (x + width, y) in remaining:
            width += 1

        height = 1
        while all((x + dx, y + height) in remaining for dx in range(width)):
            height += 1

        for dy in range(height):
            for dx in range(width):
                remaining.discard((x + dx, y + dy))

        rects.append((x, y, width, height))

    return rects


def rect_to_collider(rect: tuple[int, int, int, int], tile_size: float) -> TilemapCollider2D:
    """Builds the collider for one merged tile rectangle.

    A RectangleCollisionShape is centred on its position, and tile rows run
    downward in world space (see `Tilemap.tilemap_pos`), so tile row `y`
    occupies world y from `-(y + 1) * tile_size` to `-y * tile_size`.
    """
    x, y, width, height = rect

    centre_x = (x + width / 2) * tile_size
    centre_y = -(y + height / 2) * tile_size

    return TilemapCollider2D(
        position=Vector(centre_x, centre_y),
        scale=Vector(width * tile_size, height * tile_size),
    )
