from FreeBodyEngine.core.node import Node2D
from FreeBodyEngine.core.collider import Collider2D, RectangleCollisionShape, CircleCollisionShape
from FreeBodyEngine.math import Vector
from FreeBodyEngine import physics_delta, log, warning
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

    :param fixed_rotation: When True the body never rotates - its rotational
        velocity stays at zero and collisions apply no torque to it.

    :param friction: The fraction of its speed the body keeps per second -
        1.0 for no drag at all, 0.98 to bleed off 2% a second, 0.5 to halve
        it. Values above 1.0 accelerate the body indefinitely and are
        almost certainly a mistake.
    :type friction: float
    """
    def __init__(self, position: Vector = Vector(), rotation: float = 0.0, scale: Vector = Vector(1, 1), mass: int = 1, velocity: Vector = Vector(0, 0), rotational_velocity: float = 0.0, friction: float = 0.98, fixed_rotation: bool = False):
        """Sets up the body's starting motion state and requires a sibling Collider2D (declared in `self.requirements`) for collision checks."""
        super().__init__(position, rotation, scale)
        if friction > 1.0:
            warning(
                f"{type(self).__name__} was given friction={friction}, which is above 1.0. "
                "friction is the fraction of speed kept per second, so a value above 1.0 "
                "makes the body accelerate on its own without any force applied."
            )
        self.vel = velocity
        self.rot_vel = rotational_velocity
        self.mass = mass
        self.friction = friction
        self.requirements = ["Collider2D"]
        # A body that must never spin. Collision resolution converts the
        # push-out into torque, so anything that is upright by nature - a
        # character, a pickup, a sprite whose art has a fixed orientation -
        # otherwise ends up slowly rotating just from brushing a wall.
        # RigidBody2D has had this; PhysicsBody had no way to say it.
        self.fixed_rotation = fixed_rotation
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

        # `friction` is the fraction of speed a body keeps per second, so the
        # per-step factor is it raised to the step length: 1.0 leaves motion
        # untouched, 0.98 bleeds off 2% a second, 0.5 halves it.
        #
        # This was `self.vel *= (self.friction * dt)`, which multiplied
        # velocity by friction*dt - at 60Hz that is 0.0163 for the default
        # friction of 0.98, and still 0.0167 for friction=1.0. Velocity was
        # annihilated within a step or two whatever the value, so no amount of
        # tuning made `vel` usable and nothing could be moved by setting it;
        # the parameter also had no framerate-independent meaning, since the
        # damping scaled with the step length instead of compensating for it.
        decay = self.friction ** dt
        self.vel *= decay
        self.transform.position += self.vel * dt

        if self.fixed_rotation:
            self.rot_vel = 0.0
            self.transform.rotation = 0.0
        else:
            self.rot_vel *= decay
            self.transform.rotation += self.rot_vel * dt

        self.forces = Vector()
        self.accumulated_acceleration = Vector()
        
    def _check_collisions(self, colliders=None):
        """Resolves this body against every other collider in the scene.

        `colliders` is the scene's `(collider, aabb_min, aabb_max)` list,
        built by Scene._physics_process so the tree is walked - and every
        bounding box computed - once per step rather than once per body.

        Each pair is rejected on overlapping AABBs before the real
        intersection test. Without it every pair ran a full separating-axis
        test: a few bodies and the level's own colliders came to a quarter of
        a million SAT tests a second, and firing a five-pellet shotgun took
        the game from 84 fps to 3.
        """
        own = self.find_nodes_with_type('Collider2D')
        if not own:
            return
        s_collider = own[0]

        if colliders is None:
            colliders = [(c, *c.collision_shape.get_aabb())
                         for c in self.scene.root.find_nodes_with_type('Collider2D')]

        s_min, s_max = s_collider.collision_shape.get_aabb()
        s_min_x, s_min_y, s_max_x, s_max_y = s_min.x, s_min.y, s_max.x, s_max.y

        for collider, o_min, o_max in colliders:
            if collider is s_collider:
                continue

            # Bounds come precomputed once per step rather than being rebuilt
            # for every pair - with n bodies this was asking each collider for
            # its bounding box n times a step for a value that cannot have
            # changed in between.
            if (s_max_x < o_min.x or o_max.x < s_min_x or
                    s_max_y < o_min.y or o_max.y < s_min_y):
                continue

            if s_collider.collide(collider):
                self._resolve_collision(s_collider, collider)
                self.on_collision(s_collider, collider)
   
    def _resolve_collision(self, collider: Collider2D, other: Collider2D):
        a = collider.collision_shape
        b = other.collision_shape

        # Both bodies in a colliding pair run this independently (once from
        # each side's own _check_collisions()) - without splitting the
        # correction, each would push itself out by the FULL overlap as if
        # the other were stationary, so together they'd move twice as far
        # as needed and overshoot into a new overlap the opposite way next
        # tick, oscillating every frame (visible as jitter). Weighting by
        # the other body's share of the combined mass makes the two
        # corrections sum to exactly the needed separation, while a
        # non-PhysicsBody collider (e.g. static level geometry, no `mass`
        # to weigh against) still gets the entire correction pushed onto
        # the dynamic side, as before.
        other_mass = getattr(other.parent, 'mass', None)
        correction_share = 1.0 if other_mass is None else other_mass / (self.mass + other_mass)

        def apply_mtv(mtv: Vector, contact_point: Vector):
            """Applies this body's share (`correction_share`) of the collision's minimum translation vector `mtv`: pushes it out of the overlap, cancels the component of its velocity still moving into `mtv`'s direction (stopping it from accelerating further into the surface without killing tangential motion), and, if a contact point was found, converts the resulting linear impulse into an angular one via torque."""
            mtv = mtv * correction_share
            self.world_transform.position += mtv

            if self.vel.dot(mtv) < 0:
                mtv_dir = mtv.normalized
                self.vel -= mtv_dir * self.vel.dot(mtv_dir)

            if contact_point and not self.fixed_rotation:
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
        """Called after a collision with `other` has been resolved - override to react to collisions (e.g. play a sound, take damage)."""
        pass

    def apply_force(self, force: Vector):
        """
        Applies a force to the physics body.

        :param force: The force that will be applied to the body.
        :type force: vector
        """
        self.forces += force

    def apply_acceleration(self, acceleration: Vector):
        """Applies a mass-independent acceleration to the body (unlike apply_force(), this isn't divided by mass during integration)."""
        self.accumulated_acceleration += acceleration

    def apply_rotation_force(self, force: float):
        """Applies a rotational force (torque) to the body."""
        self.rot_forces += force


    def on_physics_process(self):
        """Called once per physics step - override to run custom per-step physics logic."""
        pass
    