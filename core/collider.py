import pygame
from FreeBodyEngine.math import Vector, Vector3
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Union



class Collider(ABC):
    """
    A generic collider object.


    :param position: The position of the collider.
    :type position: Vector
    """
    def __init__(self, position: Vector, rotation: float):
        self.position = position
        self.rotation = rotation

    @abstractmethod
    def collide(self, other: Union['Collider', Vector]) -> bool:
        """
        Checks collision with any collider object or point.

        :param other: Checked object.
        :type other: Collider | Vector

        :rtype: bool
        """
        if isinstance(other, CircleCollider): return self.collide_circle(other)
        elif isinstance(other, RectangleCollider): return self.collide_rectangle(other)
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
    def collide_circle(self, other: "CircleCollider") -> bool:
        """
        Checks for collision against a circle collider.

        
        :param other: The checked collider.
        :type other: CircleCollider
        
        :return    bool: collision?
        """
        raise NotImplementedError(f"Circle collision not implemented on Collider: {str(self)}")
    
    @abstractmethod
    def collide_rectangle(self, other: "RectangleCollider") -> bool:
        """
        Checks for collision against a rectangle collider.

        Parameters:
            other (RectangleCollider): The checked collider.
        
        Returns:
            bool: collision?
        """
        raise NotImplementedError(f"Rect collision not implemented on Collider: {str(self)}")


class CircleCollider(Collider):
    """
    A circular collider object.
    
    :param radius: The Radius of the collider shape.
    :type radius: int
    :param position: The center of the collider.
    :type position: Vector
    """
    def __init__(self, raduis: int, position: Vector, rotation: float):
        self.position = position
        self.radius = raduis
        self.rotation = rotation

    def collide_point(self, point: Vector):
        dist = self.position.distance_to(point)
        return dist <= self.radius

    def collide_circle(self, other: "CircleCollider"):
        dist = self.position.distance_to(other.position)
        return dist <= self.radius + other.radius
    
    def collide_rect(self, other: "RectangleCollider"):
        # Find the closest point on the rectangle to the circle center
        x, y = other.position.x, other.position.y
        w, h = other.size
        closest_x = max(x, min(self.position.x, x + w))
        closest_y = max(y, min(self.position.y, y + h))

        # Compute the distance from the circle's center to this closest point
        closest_point = Vector(closest_x, closest_y)
        distance = other.position.distance_to(closest_point)
        return distance <= self.radius


class RectangleCollider(Collider):
    """
    A rectangular collider object.
    
    :param position: The center of the collider.
    :type position: Vector
    :param size: The size of the collider shape (width, height).
    :type size: tuple
    """

    def __init__(self, position: Vector, size: tuple, rotation: float):
        self.position = position  # Top-left corner
        self.size = size          # (width, height)
        self.rotation = rotation

    def collide_point(self, point: Vector):
        x, y = self.position.x, self.position.y
        w, h = self.size
        return (x <= point.x <= x + w) and (y <= point.y <= y + h)
    
    def collide_circle(self, other: CircleCollider):
        # Find the closest point on the rectangle to the circle center
        x, y = self.position.x, self.position.y
        w, h = self.size
        closest_x = max(x, min(other.position.x, x + w))
        closest_y = max(y, min(other.position.y, y + h))

        # Compute the distance from the circle's center to this closest point
        closest_point = Vector(closest_x, closest_y)
        distance = other.position.distance_to(closest_point)
        return distance <= other.radius

    def collide_rectangle(self, other: "RectangleCollider"):
        x1, y1 = self.position.x, self.position.y
        w1, h1 = self.size
        x2, y2 = other.position.x, other.position.y
        w2, h2 = other.size

        return not (
            x1 + w1 < x2 or
            x1 > x2 + w2 or
            y1 + h1 < y2 or
            y1 > y2 + h2
        )

class Ray:
    """
    A ray object.
    
    :param origin: The starting position of the ray.
    :type origin: Vector

    :param direction: The direction of the ray.    
    :type direction: Vector
    """

    def __init__(self, origin: Vector, direction: Vector):
        self.origin = origin
        self.direction = direction.normalized()

    def intersect_circle(self, circle: CircleCollider) -> Vector | None:
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

    def intersect_rectangle(self, rect: RectangleCollider):
        """
        Checks for intersection with a rectangle collider.

        :param circle: The checked circle.
        :type circle: RectangleCollider

        :returns: The point of intersection, or None if there is no intersection. 
        :rtype: Vector or None
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

        hit_point = self.origin + self.direction * tmin
        return hit_point
    
    def interscet(self, collider: Collider):
                

        if isinstance(collider, RectangleCollider):
            return self.intersect_rectangle(collider)
        if isinstance(collider, CircleCollider):
            return self.intersect_circle(collider)
        
        raise ValueError(f"Provided collider type is not supported, type: {collider.__class__}")

    def update(self, dt):
        for collider in self.scene.colliders:
            self.intersect(collider)
