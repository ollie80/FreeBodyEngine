from FreeBodyEngine.core.entity import Entity
from FreeBodyEngine.core import collider
from FreeBodyEngine.math import Vector
from FreeBodyEngine import delta

class PhysicsBody(Entity):
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
    def __init__(self, position: Vector, collider: collider.Collider, mass: int = 1, velocity: Vector = Vector(0, 0), friction: float = 0.98):
        super().__init__(position)
        self.collider = collider
        self.vel = velocity
        self.mass = mass
        self.friction = friction
        self.forces = Vector(0, 0)

    @property
    def rotation(self):
        return self.collider.rotation

    @rotation.setter
    def rotation(self, new: float):
        self.collider.rotation = new

    def _integrate_forces(self):
        acceleration = self.forces / self.mass
        dt = delta()
        self.vel += acceleration * dt
        self.vel *= (1 - self.friction * dt)
        self.position += self.vel * dt

        self.forces = Vector(0, 0)

    def _check_collisions(self):
        for entity in self.scene.entities:
            if isinstance(entity, PhysicsBody):
                if self.collider.collide(entity.collider):
                    self._resolve_collision(entity.collider)

    def _resolve_collision(self, other: collider.Collider):
        if self.collider.position.x > self.collider.collide(other):
            print("resolve collision")


    def apply_force(self, force: Vector):
        """
        Applies a force to the physics body.

        :param force: The force that will be applied to the body.
        :type force: vector
        """
        self.forces += force
    
    def update(self):
        self.on_update()
        self._integrate_forces()
        self.on_post_update()
