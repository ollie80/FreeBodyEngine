from FreeBodyEngine.core.node import Node2D
from FreeBodyEngine.core.collider import Collider2D, RectangleCollisionShape, CircleCollisionShape
from FreeBodyEngine.math import Vector
from FreeBodyEngine import physics_delta, log
from typing import Union


class PhysicsBody(Node2D):
    """
    A basic arcade physics object.

    :param position: The world position of the body.
    :type position: Vector

    :param collider: The colider object used for the body's collisions.
    :type collider: Collider

    :param mass: The mass of the body.
    :type mass: int

    :param velocity: The starting velocity of body.
    :type velocity: Vector

    :param friction: The friction that will be applied to the body.
    :type friction: float
    """
    def __init__(self, position: Vector = Vector(), rotation: float = 0.0, scale: Vector = Vector(1, 1), mass: int = 1, velocity: Vector = Vector(0, 0), rotational_velocity: float = 0.0, friction: float = 0.98):
        super().__init__(position, rotation, scale)
        self.vel = velocity
        self.rot_vel = rotational_velocity
        self.mass = mass
        self.friction = friction
        self.requirements = ["Collider2D"]
        self.forces = Vector()
        self.accumulated_acceleration = Vector()

        self.rot_forces = 0

    def _integrate_forces(self):
        rot_accel = self.rot_forces / self.mass
        
        acceleration = self.forces / self.mass
        acceleration += self.accumulated_acceleration
        dt = physics_delta()
        
        self.vel += acceleration * dt
        self.rot_vel += rot_accel * dt
    
        self.vel *= (self.friction * dt)
        self.transform.position += self.vel * dt

        self.rot_vel *= (self.friction * dt)
        self.transform.rotation += self.rot_vel * dt

        self.forces = Vector()
        self.accumulated_acceleration = Vector()
        
    def _check_collisions(self):
        s_collider = self.find_nodes_with_type('Collider2D')[0]
        for collider in self.scene.root.find_nodes_with_type('Collider2D'):
            if collider != s_collider:
                if s_collider.collide(collider):
                    self._resolve_collision(s_collider, collider)   
                    self.on_collision(s_collider, collider)
   
    def _resolve_collision(self, collider: Collider2D, other: Collider2D):
        a = collider.collision_shape
        b = other.collision_shape

        def apply_mtv(mtv: Vector, contact_point: Vector):
            self.world_transform.position += mtv

            if self.vel.dot(mtv) < 0:
                mtv_dir = mtv.normalized
                self.vel -= mtv_dir * self.vel.dot(mtv_dir)

            if contact_point:
                r = contact_point - self.world_transform.position
                torque = r.cross(mtv)
                self.rot_vel += torque / self.mass

        if isinstance(a, RectangleCollisionShape) and isinstance(b, RectangleCollisionShape):
            corners_a = a._get_corners()
            corners_b = b._get_corners()

            axes = a._get_axes(corners_a) + b._get_axes(corners_b)

            min_overlap = float('inf')
            smallest_axis = None

            for axis in axes:
                min_a, max_a = a._project_onto_axis(corners_a, axis)
                min_b, max_b = b._project_onto_axis(corners_b, axis)

                overlap = min(max_a, max_b) - max(min_a, min_b)
                if overlap <= 0:
                    return 
                if overlap < min_overlap:
                    min_overlap = overlap
                    smallest_axis = axis

            direction = a.position - b.position
            if smallest_axis.dot(direction) < 0:
                smallest_axis = -smallest_axis

            mtv = smallest_axis.normalized * min_overlap
            contact_point = a.position 
            apply_mtv(mtv, contact_point)

        elif isinstance(a, CircleCollisionShape) and isinstance(b, CircleCollisionShape):
            delta = a.position - b.position
            dist = delta.magnitude
            overlap = a.radius + b.radius - dist

            if overlap > 0 and dist != 0:
                mtv = delta.normalized * overlap
                contact_point = a.position - delta.normalized * a.radius
                apply_mtv(mtv, contact_point)

        elif isinstance(a, RectangleCollisionShape) and isinstance(b, CircleCollisionShape):
            contact_point = a._closest_point_on_bounds(b.position)
            delta = b.position - contact_point
            dist = delta.magnitude
            overlap = b.radius - dist
            if overlap > 0 and dist != 0:
                mtv = -delta.normalized * overlap
                apply_mtv(mtv, contact_point)

        elif isinstance(a, CircleCollisionShape) and isinstance(b, RectangleCollisionShape):
            contact_point = b._closest_point_on_bounds(a.position)
            delta = a.position - contact_point
            dist = delta.magnitude
            overlap = (a.radius - dist)
            if overlap > 0 and dist != 0:
                mtv = delta.normalized * overlap
                apply_mtv(mtv, contact_point)

    def on_collision(self, collider: Collider2D, other: Collider2D):
        pass

    def apply_force(self, force: Vector):
        """
        Applies a force to the physics body.

        :param force: The force that will be applied to the body.
        :type force: vector
        """
        self.forces += force

    def apply_acceleration(self, acceleration: Vector):
        self.accumulated_acceleration += acceleration

    def apply_rotation_force(self, force: float):
        self.rot_forces += force
    

    def on_physics_process(self):
        pass
    