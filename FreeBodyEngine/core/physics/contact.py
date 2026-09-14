"""Narrow-phase contact manifold generation for the rigid-body physics
system.

`core.collider`'s `CollisionShape.collide()` only answers "do these
overlap?" - a real physics solver needs to know *how much* (the
penetration depth, to push bodies apart by the right amount) and *where*
(one or two world-space contact points, so a resting box doesn't slowly
rotate/tip the way it would with only a single averaged contact) and
*which way* (the separating normal, to resolve velocity along the right
axis). The functions here produce that richer `Manifold` instead, reusing
the same shape classes and SAT building blocks `core.collider` already
has (`_project_points`, `_convex_polygons_overlap` and friends) rather
than duplicating shape geometry.
"""

from dataclasses import dataclass, field
from FreeBodyEngine.math import Vector
from FreeBodyEngine.core.collider import (
    CircleCollisionShape,
    CollisionShape,
    _project_points,
)


@dataclass
class Manifold:
    """A narrow-phase collision result: `normal` points from shape A
    toward shape B, `penetration` is how far they overlap along it, and
    `points` holds 1-2 world-space contact points (2 for a stable
    polygon-vs-polygon face contact, 1 for anything involving a circle,
    which only ever touches at a single point)."""
    normal: Vector
    penetration: float
    points: list = field(default_factory=list)


def _corners_and_axes(shape):
    """Returns `(corners, axes)` for any shape exposing the polygon-like
    `_get_corners()`/`_get_axes()` interface (Rectangle and Polygon both
    do) - lets the functions below treat them uniformly."""
    corners = shape._get_corners()
    return corners, shape._get_axes(corners)


def circle_vs_circle(a: CircleCollisionShape, b: CircleCollisionShape) -> Manifold | None:
    """Circle-circle is the simplest possible case: overlap iff the
    center distance is less than the summed radii, contact normal is
    along the line between centers, and the single contact point sits
    halfway into the overlap."""
    delta = b.position - a.position
    dist = delta.magnitude
    radius_sum = a.radius + b.radius

    if dist >= radius_sum:
        return None

    normal = delta.normalized if dist > 1e-9 else Vector(1, 0)
    penetration = radius_sum - dist
    point = a.position + normal * (a.radius - penetration / 2)
    return Manifold(normal, penetration, [point])


def circle_vs_polygon(circle: CircleCollisionShape, polygon) -> Manifold | None:
    """Circle-vs-(Rectangle|Polygon): finds the polygon face the circle's
    center is most separated from (or, if the center is inside the
    polygon, the *least* deeply contained face, i.e. the one the circle
    should be pushed out through). If that separation is >= the circle's
    radius on any face, they don't overlap; otherwise the contact normal
    is that face's normal and the single contact point is the circle's
    surface point along it."""
    corners, axes = _corners_and_axes(polygon)

    best_axis = None
    best_separation = float('-inf')

    for axis in axes:
        _, max_p = _project_points(corners, axis)
        center_proj = circle.position.dot(axis)
        # Separation of the circle's *surface* (not center) from this
        # face - a face the center has already passed (negative
        # separation) still needs checking since the polygon may be
        # convex-but-not-huge relative to the circle.
        separation = center_proj - max_p
        if separation > best_separation:
            best_separation = separation
            best_axis = axis

    if best_separation > circle.radius:
        return None

    if best_separation > 0:
        # Center is outside the polygon, closest to `best_axis`'s face -
        # push straight out along that face normal.
        normal = best_axis
        penetration = circle.radius - best_separation
        point = circle.position - normal * circle.radius
    else:
        # Center is inside the polygon (every face separation is
        # negative) - `best_axis` is the face it's closest to escaping
        # through, still the right push-out direction.
        normal = best_axis
        penetration = circle.radius - best_separation
        point = circle.position - normal * circle.radius

    return Manifold(normal, penetration, [point])


def _clip_segment(points: list[Vector], normal: Vector, offset: float) -> list[Vector]:
    """Sutherland-Hodgman clipping of the 2-point segment `points` against
    the single half-plane `dot(p, normal) <= offset` - the building block
    `_polygon_vs_polygon` uses to clip an incident face down to the
    reference face's side planes. Always returns 0 or 2 points (a segment
    clipped by one plane is still a segment, or nothing)."""
    out = []
    d0 = points[0].dot(normal) - offset
    d1 = points[1].dot(normal) - offset

    if d0 <= 0:
        out.append(points[0])
    if d1 <= 0:
        out.append(points[1])

    if d0 * d1 < 0:
        t = d0 / (d0 - d1)
        out.append(points[0] + (points[1] - points[0]) * t)

    return out


def _find_max_separation(corners_a, axes_a, corners_b):
    """Finds the face on polygon A (by index into `axes_a`) with the
    largest separation from polygon B - the core SAT query, run once with
    A/B swapped to check both polygons' faces as candidate separating
    axes.

    `axes_a[i]` is face `i`'s *outward* normal (see `_edge_normal`), so
    B is on the separated side of that face exactly when B's closest
    approach in the normal's own direction (`min_b`, its smallest
    projection onto it) is still beyond the face itself (`max_a`, which
    equals the face's own offset along its own normal, since a convex
    polygon's vertices never project further outward than the face they
    define). This must NOT be symmetrized into `max(min_b - max_a,
    min_a - max_b)` - that would make a face and its exact opposite
    (same line, opposite normal) report the same separation, silently
    discarding which of the two is actually the one B is overlapping."""
    best_index = 0
    best_separation = float('-inf')

    for i, axis in enumerate(axes_a):
        _, max_a = _project_points(corners_a, axis)
        min_b, _ = _project_points(corners_b, axis)
        separation = min_b - max_a
        if separation > best_separation:
            best_separation = separation
            best_index = i

    return best_index, best_separation


def _incident_face(corners_i, axes_i, ref_normal: Vector) -> tuple[Vector, Vector]:
    """Finds the edge on the incident polygon whose normal is most
    anti-parallel to `ref_normal` (i.e. most directly facing the
    reference face) - that's the face that's actually penetrating the
    reference face, and the one that gets clipped down to 1-2 contact
    points."""
    best_index = 0
    best_dot = float('inf')
    for i, axis in enumerate(axes_i):
        d = axis.dot(ref_normal)
        if d < best_dot:
            best_dot = d
            best_index = i

    return corners_i[best_index], corners_i[(best_index + 1) % len(corners_i)]


def polygon_vs_polygon(shape_a, shape_b) -> Manifold | None:
    """SAT collision between any two convex polygon-like shapes (Rectangle
    and/or Polygon, in any combination - both expose the same
    `_get_corners()`/`_get_axes()` interface) with reference/incident
    face clipping for up to 2 stable contact points, following the
    standard box2d-lite `Collide()` algorithm: find each polygon's best
    (least-penetrating) separating face, pick the reference face as
    whichever polygon is less penetrated (for numerical stability, with a
    small bias toward keeping A as the reference to avoid flip-flopping
    when separations are nearly equal), find the incident polygon's most
    anti-parallel face, then clip that incident edge against the
    reference face's two side planes and keep whatever's left that's
    still behind the reference face."""
    corners_a, axes_a = _corners_and_axes(shape_a)
    corners_b, axes_b = _corners_and_axes(shape_b)

    edge_a, separation_a = _find_max_separation(corners_a, axes_a, corners_b)
    if separation_a >= 0:
        return None

    edge_b, separation_b = _find_max_separation(corners_b, axes_b, corners_a)
    if separation_b >= 0:
        return None

    flip = separation_b > separation_a + 0.001

    if flip:
        ref_corners, ref_axes, ref_edge = corners_b, axes_b, edge_b
        inc_corners, inc_axes = corners_a, axes_a
    else:
        ref_corners, ref_axes, ref_edge = corners_a, axes_a, edge_a
        inc_corners, inc_axes = corners_b, axes_b

    ref_normal = ref_axes[ref_edge]
    ref_v1 = ref_corners[ref_edge]
    ref_v2 = ref_corners[(ref_edge + 1) % len(ref_corners)]

    incident_edge = list(_incident_face(inc_corners, inc_axes, ref_normal))

    tangent = (ref_v2 - ref_v1).normalized
    side1_normal = -tangent
    side1_offset = side1_normal.dot(ref_v1)
    clipped = _clip_segment(incident_edge, side1_normal, side1_offset)
    if len(clipped) < 2:
        return None

    side2_normal = tangent
    side2_offset = side2_normal.dot(ref_v2)
    clipped = _clip_segment(clipped, side2_normal, side2_offset)
    if len(clipped) < 2:
        return None

    ref_offset = ref_normal.dot(ref_v1)
    points = []
    max_penetration = 0.0
    for p in clipped:
        separation = p.dot(ref_normal) - ref_offset
        if separation <= 0:
            points.append(p)
            max_penetration = max(max_penetration, -separation)

    if not points:
        return None

    normal = -ref_normal if flip else ref_normal
    return Manifold(normal, max_penetration, points)


def generate_manifold(shape_a: CollisionShape, shape_b: CollisionShape) -> Manifold | None:
    """Dispatches to the right narrow-phase function for `shape_a`/
    `shape_b`'s concrete types, normalizing the result so `normal` always
    points from `shape_a` toward `shape_b` regardless of which order the
    underlying function needed them in. `circle_vs_polygon(circle,
    polygon)` always returns a normal pointing away from the polygon's
    face, toward the circle - i.e. from its *polygon* argument to its
    *circle* argument - so that needs negating exactly when the circle is
    `shape_a` (polygon->circle is then shape_b->shape_a, the reverse of
    what's wanted), and needs no change when the circle is `shape_b`
    (polygon->circle is already shape_a->shape_b)."""
    a_is_circle = isinstance(shape_a, CircleCollisionShape)
    b_is_circle = isinstance(shape_b, CircleCollisionShape)

    if a_is_circle and b_is_circle:
        return circle_vs_circle(shape_a, shape_b)

    if a_is_circle:
        manifold = circle_vs_polygon(shape_a, shape_b)
        if manifold is not None:
            manifold.normal = -manifold.normal
        return manifold

    if b_is_circle:
        return circle_vs_polygon(shape_b, shape_a)

    return polygon_vs_polygon(shape_a, shape_b)
