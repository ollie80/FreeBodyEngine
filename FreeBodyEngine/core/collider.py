from FreeBodyEngine.math import Vector, Vector3
from FreeBodyEngine.utils import abstractmethod
from FreeBodyEngine import get_main
from typing import TYPE_CHECKING, Literal, Union
from FreeBodyEngine.core.node import Node2D
from FreeBodyEngine.core.scene import Scene
from FreeBodyEngine.graphics.debug import RectangleColliderDebug, CircleColliderDebug
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

        cos_r = math.cos(self.rotation)
        sin_r = math.sin(self.rotation)

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
        return [
            (corners[1] - corners[0]).normalized.perpendicular(),
            (corners[3] - corners[0]).normalized.perpendicular()
        ]

    def _project_onto_axis(self, corners, axis):
        projections = [corner.dot(axis) for corner in corners]
        return min(projections), max(projections)

    def collide_rectangle(self, other: "RectangleCollisionShape"):
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

    def collide_point(self, point: Vector):
        """Checks whether `point` lies inside the rectangle by projecting it onto the rectangle's two (rotated) axes and testing against the rectangle's extent on each.

        Returns:
            bool: True if the point is inside the rectangle.
        """
        corners = self._get_corners()
        axis1 = (corners[1] - corners[0]).normalized().perpendicular()
        axis2 = (corners[3] - corners[0]).normalized().perpendicular()

        def project_point(p, axis):
            return p.dot(axis)

        min_a, max_a = self._project_onto_axis(corners, axis1)
        min_b, max_b = self._project_onto_axis([point], axis1)
        if max_b < min_a or max_a < min_b:
            return False

        min_a, max_a = self._project_onto_axis(corners, axis2)
        min_b, max_b = self._project_onto_axis([point], axis2)
        return not (max_b < min_a or max_a < min_b)

    def collide_circle(self, other: "CircleCollisionShape"):
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

    def cast(self, max_dist: float = 100):
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
