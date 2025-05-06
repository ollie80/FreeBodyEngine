import pygame
from pygame import Vector2 as vector

class Collider:
    def __init__(self, position: vector):
        pass

    def collide_point(self, point: vector):
        raise NotImplementedError(f"Point collision not implemented on Collide: {str(self)}")

    
    def collide_circle(self, other: "CircleCollider"):
        raise NotImplementedError(f"Circle collision not implemented on Collide: {str(self)}")
    
    def collide_rectangle(self, other: "RectangleCollider"):
        raise NotImplementedError(f"Rect collision not implemented on Collide: {str(self)}")
    

class CircleCollider(Collider):
    def __init__(self, raduis: int, position: vector):
        self.position = position
        self.radius = raduis

    def collide_point(self, point: vector):
        dist = self.position.distance_to(point)
        if dist <= self.radius:
            return True
        return False

    def collide_circle(self, other: "CircleCollider"):
        dist = self.position.distance_to(other.position)
        if dist <= self.radius + other.radius:
            return True
        return False
    
    def collide_rect(self, other: "RectangleCollider"):
        # Find the closest point on the rectangle to the circle center
        x, y = other.position.x, other.position.y
        w, h = other.size
        closest_x = max(x, min(self.position.x, x + w))
        closest_y = max(y, min(self.position.y, y + h))

        # Compute the distance from the circle's center to this closest point
        closest_point = vector(closest_x, closest_y)
        distance = other.position.distance_to(closest_point)
        return distance <= other.radius


class RectangleCollider(Collider):
    def __init__(self, position: vector, size: tuple):
        self.position = position  # Top-left corner
        self.size = size          # (width, height)

    def collide_point(self, point: vector):
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
        closest_point = vector(closest_x, closest_y)
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
    def __init__(self, origin: vector, direction: vector):
        self.origin = origin
        self.direction = direction.normalized()

    def intersect_circle(self, circle: CircleCollider):
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
