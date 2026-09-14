from FreeBodyEngine.math import Vector, Vector3
from FreeBodyEngine.utils import abstractmethod
from FreeBodyEngine import get_main
from typing import TYPE_CHECKING, Literal, Union
from FreeBodyEngine.core.node import Node2D
from FreeBodyEngine.core.scene import Scene
from FreeBodyEngine.graphics.debug import RectangleColliderDebug, CircleColliderDebug, PolygonColliderDebug
import numpy as np
import math

class CollisionShape:
    """
    A Collision Shape. Contains logic for basic arcade collisions.


    :param position: The position of the collider.
    :type position: Vector
    """
    def __init__(self, position: Vector, rotation: float):
        """No-op base initializer - concrete shapes (Circle/RectangleCollisionShape) set their own position/rotation/size attributes directly instead of calling this."""
        pass

    def collide(self, other: Union['CollisionShape', Vector]) -> bool:
        """
        Checks collision with any collider object or point.

        :param other: Checked object.
        :type other: Collider | Vector

        :rtype: bool
        """
        if isinstance(other, CircleCollisionShape): return self.collide_circle(other)
        elif isinstance(other, RectangleCollisionShape): return self.collide_rectangle(other)
        elif isinstance(other, PolygonCollisionShape): return self.collide_polygon(other)
        elif isinstance(other, Vector): return self.collide_point(other)
        else: raise TypeError(f"Object of class {other.__class__} cannot be collided with.")

    @abstractmethod
    def collide_point(self, point: Vector) -> bool:
        """
        Checks for collision against a point.

        :param point: The checked point.
        :type point: Vector

        :rtype: bool
        """
        raise NotImplementedError(f"Point collision not implemented on Collider: {str(self)}")

    @abstractmethod
    def collide_circle(self, other: "CircleCollisionShape") -> bool:
        """
        Checks for collision against a circle collider.

        
        :param other: The checked collider.
        :type other: CircleCollider
        
        :return    bool: collision?
        """
        raise NotImplementedError(f"Circle collision not implemented on Collider: {str(self)}")
    
    @abstractmethod
    def collide_rectangle(self, other: "RectangleCollisionShape") -> bool:
        """
        Checks for collision against a rectangle collider.

        Parameters:
            other (RectangleCollider): The checked collider.

        Returns:
            bool: collision?
        """
        raise NotImplementedError(f"Rect collision not implemented on Collider: {str(self)}")

    @abstractmethod
    def collide_polygon(self, other: "PolygonCollisionShape") -> bool:
        """Checks for collision against a general convex polygon collider."""
        raise NotImplementedError(f"Polygon collision not implemented on Collider: {str(self)}")

    @abstractmethod
    def get_aabb(self) -> tuple[Vector, Vector]:
        """Returns this shape's world-space axis-aligned bounding box as
        `(min, max)` corners - used by the physics broad phase to cheaply
        reject non-overlapping pairs before running real narrow-phase
        collision."""
        raise NotImplementedError(f"AABB not implemented on Collider: {str(self)}")

    @abstractmethod
    def compute_mass(self, density: float) -> tuple[float, float]:
        """Returns `(mass, moment_of_inertia)` for this shape at the given
        `density`, both about this shape's own centroid - used by
        `RigidBody2D` to auto-derive mass/inertia from its collider rather
        than requiring them to be set by hand."""
        raise NotImplementedError(f"Mass computation not implemented on Collider: {str(self)}")

def _edge_normal(edge: Vector) -> Vector:
    """Returns the outward-facing unit normal of an edge vector, assuming
    counter-clockwise winding (as both RectangleCollisionShape's and
    PolygonCollisionShape's corners are) - a 90-degree *clockwise*
    rotation of the edge direction, not `Vector.perpendicular()`'s
    counter-clockwise one (which gives the *inward* normal for a
    CCW-wound polygon instead). Getting this backwards doesn't affect a
    pure overlap/containment test (SAT and point-in-polygon are direction-
    agnostic - projecting onto -N instead of N just negates min/max
    symmetrically), which is why the bug this fixes went unnoticed there,
    but it matters a great deal once a normal's actual direction is used
    (e.g. as a physics contact/push-out normal)."""
    return Vector(edge.y, -edge.x).normalized

def _project_points(points: list[Vector], axis: Vector) -> tuple[float, float]:
    """Projects `points` onto `axis` and returns `(min, max)` of the
    resulting scalar range - the shared building block behind every SAT
    overlap/containment test below."""
    projections = [p.dot(axis) for p in points]
    return min(projections), max(projections)

def _convex_polygons_overlap(corners_a: list[Vector], axes_a: list[Vector], corners_b: list[Vector], axes_b: list[Vector]) -> bool:
    """SAT overlap test between any two convex polygons, given their
    world-space corners and face-normal axes - the same algorithm
    `RectangleCollisionShape.collide_rectangle` uses, generalized so
    `PolygonCollisionShape` can share it instead of duplicating SAT."""
    for axis in axes_a + axes_b:
        min_a, max_a = _project_points(corners_a, axis)
        min_b, max_b = _project_points(corners_b, axis)
        if max_a < min_b or max_b < min_a:
            return False
    return True

def _point_in_convex_polygon(corners: list[Vector], axes: list[Vector], point: Vector) -> bool:
    """SAT-based point-in-convex-polygon test: `point` is inside iff its
    projection falls within the polygon's own projection on every one of
    the polygon's face-normal axes."""
    for axis in axes:
        min_p, max_p = _project_points(corners, axis)
        point_proj = point.dot(axis)
        if point_proj < min_p or point_proj > max_p:
            return False
    return True

def _closest_point_on_polygon(corners: list[Vector], point: Vector) -> Vector:
    """Returns the closest point on a convex polygon's boundary (edges, in
    order) to `point` - generalizes
    `RectangleCollisionShape._closest_point_on_bounds` to any vertex
    count."""
    closest_point = corners[0]
    min_dist_sq = float('inf')

    for i in range(len(corners)):
        start = corners[i]
        end = corners[(i + 1) % len(corners)]

        edge = end - start
        to_point = point - start
        edge_len_sq = edge.dot(edge)
        if edge_len_sq == 0:
            projection = start
        else:
            t = max(0, min(1, to_point.dot(edge) / edge_len_sq))
            projection = start + edge * t

        dist_sq = (point - projection).dot(point - projection)
        if dist_sq < min_dist_sq:
            min_dist_sq = dist_sq
            closest_point = projection

    return closest_point

def regular_polygon_vertices(sides: int, radius: float) -> list[Vector]:
    """Returns `sides` local vertices (centered on the origin, first vertex
    pointing along +X) for a regular polygon inscribed in a circle of
    `radius` - a convenient way to build a `PolygonCollisionShape` that
    approximates a circle/capsule more closely than a box does (e.g. for a
    rounded-looking limb segment), without needing true curved-edge
    collision support."""
    return [
        Vector(radius * math.cos(2 * math.pi * i / sides), radius * math.sin(2 * math.pi * i / sides))
        for i in range(sides)
    ]

class CircleCollisionShape(CollisionShape):
    """A circular collision shape, defined by a center position and radius."""
    def __init__(self, position: Vector, rotation: float, radius: int):
        """Stores the circle's position, rotation, and radius directly (rotation has no effect on a circle's shape, but is kept for a consistent CollisionShape interface)."""
        self.position = position
        self.radius = radius
        self.rotation = rotation

    def collide_point(self, point: Vector):
        """Checks whether `point` lies within the circle's radius."""
        return self.position.distance(point) <= self.radius

    def collide_circle(self, other: "CircleCollisionShape"):
        """Checks whether the two circles overlap by comparing the distance between their centers to the sum of their radii."""
        return self.position.distance(other.position) <= self.radius + other.radius

    def collide_rectangle(self, other: "RectangleCollisionShape"):
        """Checks collision against a rectangle by delegating to the rectangle's own circle-collision test."""
        return other.collide_circle(self)

    def collide_polygon(self, other: "PolygonCollisionShape") -> bool:
        """Checks collision against a polygon by delegating to the polygon's own circle-collision test."""
        return other.collide_circle(self)

    def get_aabb(self) -> tuple[Vector, Vector]:
        """The circle's bounding box: its position offset by `radius` on every side."""
        r = Vector(self.radius, self.radius)
        return self.position - r, self.position + r

    def compute_mass(self, density: float) -> tuple[float, float]:
        """A solid disk's mass is `density * pi * r^2`; its moment of
        inertia about its own center is `mass * r^2 / 2`."""
        mass = density * math.pi * self.radius ** 2
        inertia = mass * self.radius ** 2 / 2
        return mass, inertia

class RectangleCollisionShape(CollisionShape):
    """An oriented (rotatable) rectangular collision shape, defined by a center position, size, and rotation."""
    def __init__(self, position: Vector, rotation: float, size: Vector):
        """Stores the rectangle's position, size, and rotation directly."""
        self.position = position
        self.size = size
        self.rotation = rotation

    def _closest_point_on_bounds(self, point: Vector) -> Vector:
        corners = self._get_corners()
        closest_point = None
        min_dist_sq = float('inf')

        for i in range(len(corners)):
            start = corners[i]
            end = corners[(i + 1) % len(corners)]  

            edge = end - start
            to_point = point - start
            edge_len_sq = edge.dot(edge)
            if edge_len_sq == 0:
                projection = start
            else:
                t = max(0, min(1, to_point.dot(edge) / edge_len_sq))
                projection = start + edge * t

            dist_sq = (point - projection).dot(point - projection)
            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
                closest_point = projection

        return closest_point

    def _get_corners(self):
        hw = self.size.x / 2
        hh = self.size.y / 2

        rot_rad = math.radians(self.rotation)
        cos_r = math.cos(rot_rad)
        sin_r = math.sin(rot_rad)

        local_corners = [
            Vector(-hw, -hh),
            Vector(hw, -hh),
            Vector(hw, hh),
            Vector(-hw, hh),
        ]

        return [
            Vector(
                self.position.x + corner.x * cos_r - corner.y * sin_r,
                self.position.y + corner.x * sin_r + corner.y * cos_r
            )
            for corner in local_corners
        ]

    def _get_axes(self, corners):
        """Returns one outward-facing normal per edge (4, matching
        `corners[i]`->`corners[i+1]` for each `i`) - not just the 2
        unique face directions a rectangle's parallel-edge symmetry would
        allow, so this has the same per-edge indexing
        `PolygonCollisionShape._get_axes` uses, which the physics
        narrow-phase's reference/incident face selection depends on. The
        redundant second occurrence of each direction (opposite edges
        share an axis, just negated) is harmless for the plain overlap/
        containment tests elsewhere in this class - just a repeated,
        already-passing check."""
        return [_edge_normal(corners[(i + 1) % len(corners)] - corners[i]) for i in range(len(corners))]

    def _project_onto_axis(self, corners, axis):
        projections = [corner.dot(axis) for corner in corners]
        return min(projections), max(projections)

    def collide_rectangle(self, other: "RectangleCollisionShape") -> bool:
        """Checks for overlap with another rectangle using the separating axis theorem (SAT): tests both rectangles' face normals as candidate separating axes, and reports a collision only if no axis separates them.

        Returns:
            bool: True if the rectangles overlap.
        """
        corners_a = self._get_corners()
        corners_b = other._get_corners()

        axes = self._get_axes(corners_a) + other._get_axes(corners_b)

        for axis in axes:
            min_a, max_a = self._project_onto_axis(corners_a, axis)
            min_b, max_b = self._project_onto_axis(corners_b, axis)

            if max_a < min_b or max_b < min_a:
                return False

        return True

    def collide_point(self, point: Vector) -> bool:
        """Checks whether `point` lies inside the rectangle by projecting it onto the rectangle's two (rotated) axes and testing against the rectangle's extent on each.

        Returns:
            bool: True if the point is inside the rectangle.
        """
        corners = self._get_corners()
        axis1 = (corners[1] - corners[0]).normalized().perpendicular()
        axis2 = (corners[3] - corners[0]).normalized().perpendicular()

        def project_point(p, axis):
            """SAT helper: projects point `p` onto `axis` via the dot product, giving its scalar position along that axis for overlap comparison. Defined for symmetry with `_project_onto_axis()` but not actually called below - `_project_onto_axis()` already inlines the same projection over its point list."""
            return p.dot(axis)

        min_a, max_a = self._project_onto_axis(corners, axis1)
        min_b, max_b = self._project_onto_axis([point], axis1)
        if max_b < min_a or max_a < min_b:
            return False

        min_a, max_a = self._project_onto_axis(corners, axis2)
        min_b, max_b = self._project_onto_axis([point], axis2)
        return not (max_b < min_a or max_a < min_b)

    def collide_circle(self, other: "CircleCollisionShape") -> bool:
        """Checks for overlap with a circle by clamping the circle's center onto the rectangle's bounds along each axis to find the closest point on the rectangle, then comparing that distance to the circle's radius.

        Returns:
            bool: True if the circle overlaps the rectangle.
        """
        corners = self._get_corners()

        closest = other.position
        for axis in self._get_axes(corners):
            min_proj, max_proj = self._project_onto_axis(corners, axis)
            center_proj = other.position.dot(axis)

            if center_proj < min_proj:
                closest = closest - axis * (min_proj - center_proj)
            elif center_proj > max_proj:
                closest = closest + axis * (center_proj - max_proj)

        return closest.distance(other.position) <= other.radius

    def collide_polygon(self, other: "PolygonCollisionShape") -> bool:
        """Checks for overlap with a general convex polygon via SAT, treating this rectangle as its own 4-corner polygon."""
        corners = self._get_corners()
        return _convex_polygons_overlap(corners, self._get_axes(corners), other._get_corners(), other._get_axes())

    def get_aabb(self) -> tuple[Vector, Vector]:
        """The rectangle's bounding box: the min/max of its (possibly rotated) corners."""
        corners = self._get_corners()
        xs = [c.x for c in corners]
        ys = [c.y for c in corners]
        return Vector(min(xs), min(ys)), Vector(max(xs), max(ys))

    def compute_mass(self, density: float) -> tuple[float, float]:
        """A solid `w`x`h` box's mass is `density * w * h`; its moment of
        inertia about its own center is `mass * (w^2 + h^2) / 12`."""
        w, h = self.size.x, self.size.y
        mass = density * w * h
        inertia = mass * (w ** 2 + h ** 2) / 12
        return mass, inertia

class PolygonCollisionShape(CollisionShape):
    """A general convex collision shape, defined by an ordered, centroid-
    relative list of local vertices (`local_vertices`) plus a world
    position/rotation - RectangleCollisionShape's fixed-4-corner shape is a
    common enough special case to keep as its own simpler class, but
    anything else convex (a hexagon, an octagon standing in for a rounded
    capsule via `regular_polygon_vertices`, a custom hull) goes through
    this one instead. Vertices must be wound consistently (order doesn't
    matter which way, just that it's consistent) and the shape must
    actually be convex - SAT and the mass formula below both assume it."""
    def __init__(self, position: Vector, rotation: float, local_vertices: list[Vector]):
        """Stores `local_vertices` (centroid-relative, in the shape's own
        unrotated local space) alongside position/rotation - world-space
        corners are recomputed from these on every query rather than
        cached, matching RectangleCollisionShape's approach."""
        self.position = position
        self.rotation = rotation
        self.local_vertices = local_vertices

    def _get_corners(self) -> list[Vector]:
        """Returns this polygon's vertices transformed into world space by
        its current position/rotation."""
        return [self.position + v.rotated(self.rotation) for v in self.local_vertices]

    def _get_axes(self, corners: list[Vector] = None) -> list[Vector]:
        """Returns one outward-facing normal axis per edge - unlike a
        rectangle (where opposite edges share a normal, so only 2 axes are
        needed), a general polygon needs a normal for every edge since
        nothing is assumed about parallelism."""
        if corners is None:
            corners = self._get_corners()
        return [_edge_normal(corners[(i + 1) % len(corners)] - corners[i]) for i in range(len(corners))]

    def collide_point(self, point: Vector) -> bool:
        """Checks whether `point` lies inside the polygon via the SAT containment test."""
        corners = self._get_corners()
        return _point_in_convex_polygon(corners, self._get_axes(corners), point)

    def collide_circle(self, other: "CircleCollisionShape") -> bool:
        """Checks for overlap with a circle: if the circle's center is
        inside the polygon it's automatically a collision (the closest-
        boundary-point check below only makes sense for a center outside
        the polygon - otherwise it'd measure to whichever edge happens to
        be nearest, which can be much farther away than the circle's own
        radius, missing the case where a small circle sits deep inside a
        larger polygon)."""
        corners = self._get_corners()
        axes = self._get_axes(corners)
        if _point_in_convex_polygon(corners, axes, other.position):
            return True
        closest = _closest_point_on_polygon(corners, other.position)
        return closest.distance(other.position) <= other.radius

    def collide_rectangle(self, other: "RectangleCollisionShape") -> bool:
        """Checks for overlap with a rectangle by delegating to the rectangle's own polygon-collision test."""
        return other.collide_polygon(self)

    def collide_polygon(self, other: "PolygonCollisionShape") -> bool:
        """Checks for overlap with another convex polygon via SAT."""
        corners = self._get_corners()
        return _convex_polygons_overlap(corners, self._get_axes(corners), other._get_corners(), other._get_axes())

    def get_aabb(self) -> tuple[Vector, Vector]:
        """The polygon's bounding box: the min/max of its world-space vertices."""
        corners = self._get_corners()
        xs = [c.x for c in corners]
        ys = [c.y for c in corners]
        return Vector(min(xs), min(ys)), Vector(max(xs), max(ys))

    def compute_mass(self, density: float) -> tuple[float, float]:
        """Standard convex-polygon mass/inertia formula (as used by e.g.
        Box2D's `b2PolygonShape::ComputeMass`): triangulates the polygon
        into a fan from its own centroid and sums each triangle's area and
        second-moment contribution, rather than assuming a closed-form
        shape like the circle/box formulas above can."""
        vertices = self.local_vertices
        area = 0.0
        centroid = Vector(0, 0)
        inertia = 0.0
        # 1/6 rather than the usual 1/3 because the cross-product term
        # below is already 2x the signed triangle area - baking that
        # factor of 2 into the divisor here keeps it out of every term.
        k_inv3 = 1.0 / 3.0

        for i in range(len(vertices)):
            p1 = vertices[i]
            p2 = vertices[(i + 1) % len(vertices)]

            cross = p1.cross(p2)
            triangle_area = 0.5 * cross

            area += triangle_area
            centroid += (p1 + p2) * (triangle_area * k_inv3)

            intx2 = p1.x * p1.x + p1.x * p2.x + p2.x * p2.x
            inty2 = p1.y * p1.y + p1.y * p2.y + p2.y * p2.y
            inertia += (0.25 * k_inv3 * cross) * (intx2 + inty2)

        centroid /= area
        mass = density * area

        # Recentered from the local origin to the polygon's own centroid
        # (parallel axis theorem) since `local_vertices` isn't guaranteed
        # to already be centroid-relative.
        inertia = density * inertia - mass * centroid.dot(centroid)
        return mass, inertia

class Collider2D(Node2D):
    """Base node for 2D colliders - wraps a CollisionShape and keeps it in sync with the node's world transform each update."""
    def __init__(self, collision_shape_cls: type[CollisionShape], position=Vector(), rotation=0, scale=Vector(1, 1)):
        """Creates the collision shape instance via `collision_shape_cls(position, rotation, scale)` - passing `scale` for whichever third parameter that shape class expects (`size` for RectangleCollisionShape). CircleCollider2D corrects this immediately afterward by overwriting `collision_shape.radius`, since a circle's constructor expects a radius, not a size vector."""
        super().__init__(position, rotation, scale)
        self.collision_shape = collision_shape_cls(position, rotation, scale)
        self._last_matrix = None

    def on_update(self):
        """Keeps the collision shape's position/rotation/size in sync with the node's world transform every frame."""
        self.apply_transform()

    def collide(self, other: 'Collider2D'):
        """Checks collision against another Collider2D by delegating to the underlying collision shapes."""
        return self.collision_shape.collide(other.collision_shape)


    @abstractmethod
    def toggle_debug_visuals(self):
        """Adds or removes this collider's debug-visualization child node, depending on whether one is already present."""
        pass

    @abstractmethod
    def apply_transform(self):
        """Copies the node's world transform onto the underlying collision shape's position/rotation/size."""
        pass

class RectangleCollider2D(Collider2D):
    """A rectangular Collider2D, backed by a RectangleCollisionShape."""
    def __init__(self, position = Vector(), rotation = 0, scale = Vector(1, 1)):
        """Creates a RectangleCollider2D with the collision shape's size taken directly from `scale`."""
        super().__init__(RectangleCollisionShape, position, rotation, scale)
        self.collision_shape: RectangleCollisionShape

    def toggle_debug_visuals(self):
        """Adds a RectangleColliderDebug child if this collider (already initialized) has none yet, otherwise removes any existing ones."""
        if self.is_initialized:
            debug = self.find_nodes_with_type('RectangleColliderDebug')
            if len(debug) > 0:
                for d in debug:
                    d.kill()
            else:
                self.add(RectangleColliderDebug())

    def apply_transform(self):
        """Syncs the collision shape's position, rotation, and size to the node's current world transform."""

        self.collision_shape.position = self.world_transform.position
        self.collision_shape.rotation = self.world_transform.rotation
        self.collision_shape.size = self.world_transform.scale

class CircleCollider2D(Collider2D):
    """A circular Collider2D, backed by a CircleCollisionShape."""
    def __init__(self, position = Vector(), rotation = 0, scale = Vector(1, 1)):
        """Creates a CircleCollider2D, deriving the collision shape's radius from `scale.x` (half of it, so `scale.x` acts as the circle's diameter)."""
        super().__init__(CircleCollisionShape, position, rotation, scale)
        self.collision_shape: CircleCollisionShape
        self.collision_shape.radius = scale.x / 2

    def toggle_debug_visuals(self):
        """Adds a CircleColliderDebug child if this collider (already initialized) has none yet, otherwise removes any existing ones."""
        if self.is_initialized:
            debug = self.find_nodes_with_type('RectangleColliderDebug')
            if len(debug) > 0:
                for d in debug:
                    d.kill()
            else:
                self.add(CircleColliderDebug())

    def apply_transform(self):
        """Syncs the collision shape's position and rotation to the node's world transform, and derives its radius from the world scale's x component."""
        self.collision_shape.position = self.world_transform.position
        self.collision_shape.rotation = self.world_transform.rotation
        self.collision_shape.radius = self.world_transform.scale.x / 2

class PolygonCollider2D(Collider2D):
    """A general convex-polygon Collider2D, backed by a
    PolygonCollisionShape - unlike Rectangle/CircleCollider2D, its shape
    isn't derived from `scale` (a polygon's shape is its vertex list, not
    a single size), so `local_vertices` is a required constructor argument
    instead."""
    def __init__(self, local_vertices: list[Vector], position=Vector(), rotation=0, scale=Vector(1, 1)):
        """Creates a PolygonCollider2D from `local_vertices` (centroid-
        relative, in the shape's own unrotated local space).

        Deliberately doesn't go through Collider2D.__init__'s usual
        `collision_shape_cls(position, rotation, scale)` pattern - that
        reuses one `scale` argument for both this NODE's own transform
        and the shape constructor's third argument, which works for
        Rectangle/CircleCollider2D (where that third argument IS a scale)
        but not here, where PolygonCollisionShape's third argument is the
        vertex list instead. Passing `local_vertices` through as if it
        were `scale` would silently corrupt this node's own
        `transform.scale` into a vector built from two Vectors instead of
        two floats."""
        Node2D.__init__(self, position, rotation, scale)
        self.collision_shape = PolygonCollisionShape(position, rotation, local_vertices)
        self._last_matrix = None

    def toggle_debug_visuals(self):
        """Adds a PolygonColliderDebug child if this collider (already initialized) has none yet, otherwise removes any existing ones."""
        if self.is_initialized:
            debug = self.find_nodes_with_type('PolygonColliderDebug')
            if len(debug) > 0:
                for d in debug:
                    d.kill()
            else:
                self.add(PolygonColliderDebug(self.collision_shape.local_vertices))

    def apply_transform(self):
        """Syncs the collision shape's position and rotation to the node's current world transform (the polygon's local vertices, and hence its size, don't change with the node's scale)."""
        self.collision_shape.position = self.world_transform.position
        self.collision_shape.rotation = self.world_transform.rotation

class Ray2D:
    """
    A 2D ray object.
    
    :param origin: The starting position of the ray.
    :type origin: Vector

    :param direction: The direction of the ray.    
    :type direction: Vector
    """

    def __init__(self, origin: Vector, direction: Vector, scene: 'Scene'):
        """Normalizes `direction` and stores it along with `origin` and the scene the ray will be cast against."""
        self.origin = origin
        self.direction = direction.normalized
        self.scene = scene

    def intersect_circle(self, circle: CircleCollisionShape) -> Vector | None:
        """
        Checks for intersection with a circle collider.

        :param circle: The checked circle.
        :type circle: CircleCollider

        :returns: The point of intersection (Vector), or None if there is no intersection. 
        :rtype: Vector or None
        """
        oc = self.origin - circle.position
        d = self.direction

        a = d.dot(d)
        b = 2 * oc.dot(d)
        c = oc.dot(oc) - circle.radius ** 2

        discriminant = b ** 2 - 4 * a * c
        if discriminant < 0:
            return None  # No intersection

        sqrt_disc = discriminant ** 0.5
        t1 = (-b - sqrt_disc) / (2 * a)
        t2 = (-b + sqrt_disc) / (2 * a)

        if t1 >= 0:
            hit_point = self.origin + d * t1
            return hit_point
        elif t2 >= 0:
            hit_point = self.origin + d * t2
            return hit_point

        return None  # Behind ray

    def intersect_rectangle(self, rect: RectangleCollisionShape):
        """
        Checks for intersection with a rectangle collider.

        :param rect: The rectangle collider.
        :returns: The point of intersection, or None if there is no intersection.
        """
        x, y = rect.position.x, rect.position.y
        w, h = rect.size
        

        inv_dir_x = 1 / self.direction.x if self.direction.x != 0 else float('inf')
        inv_dir_y = 1 / self.direction.y if self.direction.y != 0 else float('inf')
        t1 = (x - self.origin.x) * inv_dir_x
        t2 = (x + w - self.origin.x) * inv_dir_x
        t3 = (y - self.origin.y) * inv_dir_y
        t4 = (y + h - self.origin.y) * inv_dir_y

        tmin = max(min(t1, t2), min(t3, t4))
        tmax = min(max(t1, t2), max(t3, t4))

        if tmax < 0 or tmin > tmax:
            return None  # No intersection

        if tmin < 0:
            return None  # Intersection is behind the ray

        hit_point = self.origin + self.direction * tmin
        return hit_point

    def intersect(self, collider: Union[Collider2D, CollisionShape]):
        """Dispatches to intersect_circle()/intersect_rectangle() based on `collider`'s (or its `collision_shape`'s) concrete type.

        Raises:
            ValueError: If `collider` is not a supported Collider2D/CollisionShape type.
        """
        if isinstance(collider, Collider2D):
            if isinstance(collider.collision_shape, RectangleCollisionShape):
                return self.intersect_rectangle(collider.collision_shape)
            
            elif isinstance(collider.collision_shape, CircleCollisionShape):
                return self.intersect_circle(collider.collision_shape)

        elif isinstance(collider, RectangleCollisionShape):
            return self.intersect_rectangle(collider)
        elif isinstance(collider, CircleCollisionShape):
            return self.intersect_circle(collider)
        else:
            raise ValueError(f"Provided collider type is not supported, type: {collider.__class__}")

    def cast(self, max_dist: float = 100) -> Vector | None:
        """Finds the closest collider in the scene that this ray intersects.

        Only considers colliders whose own position is within `max_dist` of
        the ray's origin (a cheap broad-phase filter, not a check on the
        actual intersection point) before running the real intersection
        test on each.

        Returns:
            Vector | None: The closest intersection point found, or None if
            the ray hits nothing.
        """
        colliders: list[Collider2D] = self.scene.root.find_nodes_with_type('Collider2D')
        found = []
        for collider in colliders:
            if collider.world_position.distance(self.origin) < max_dist:
                point = self.intersect(collider)
                if point:
                    found.append(point)

        if len(found) > 0:
            closest = found[0]
            for point in found:
                if self.origin.distance(point) < self.origin.distance(closest):
                    closest = point
            
            return closest
        
        else:
            return None

class Raycaster2D(Node2D):
    """A node that casts a ray from its own world position, facing its own world rotation, every update."""
    def __init__(self):
        """Initializes the node; the ray itself isn't created until on_initialize(), once the node has a world transform to read."""
        super().__init__()

    def on_initialize(self):
        """Creates the ray, facing the node's current world rotation from its current world position."""
        self.ray = Ray2D(self.world_transform.position, Vector.from_angle(self.world_transform.rotation), self.scene)

    def update(self):
        """Re-aims the ray at the node's current world transform and casts it."""
        self.ray.direction = Vector.from_angle(self.world_transform.rotation)
        self.ray.origin = self.world_transform.position
        self.ray.cast()
        super().update()


def cast_ray(position: Vector, direction: Vector, max_distance: float, scene: 'Scene' = None):
    """
    Casts a ray.

    :param position: The point the ray is cast from.
    :type position: Vector 

    :param direction: The direction that the ray is cast in.
    :type direction: Vector

    :param scene: The scene that the ray will be cast in, defaults to the curent scene.
    :type scene: Scene
    """
    if scene == None:
        scene = get_main().active_scene
        if scene == None:
            warning('Cannot cast ray as no scene was specified and there is no active scene.')
            return None
        
        ray = Ray2D(position, direction, scene)
        return ray.cast()
