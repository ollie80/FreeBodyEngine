"""RigidBody2D - the new rigid-body physics node.

Unlike `PhysicsBody` (the older, simpler "arcade physics" system this
package still exports for backward compatibility - push-out collision
response with no concept of a real constraint solver), a `RigidBody2D`
is simulated by `PhysicsWorld` alongside every other body and `Joint2D`
in the scene, all at once, through a proper sequential-impulse velocity
solver - which is what makes joints, motors, and physically stable
stacking/resting contact possible at all.
"""

import math
from enum import Enum, auto

from FreeBodyEngine.core.node import Node2D
from FreeBodyEngine.core.collider import Collider2D
from FreeBodyEngine.math import Vector
from FreeBodyEngine import warning


class BodyType(Enum):
    """What drives a RigidBody2D's motion:

    - STATIC: never moves (infinite mass/inertia) - level geometry, walls.
    - KINEMATIC: moves only when *you* set its position/rotation directly
      (e.g. animating a moving platform) - unaffected by forces/impulses/
      collision response, but still pushes DYNAMIC bodies it touches.
    - DYNAMIC: fully simulated - forces, gravity, collision response, and
      joints all apply.
    """
    STATIC = auto()
    KINEMATIC = auto()
    DYNAMIC = auto()


class RigidBody2D(Node2D):
    """A physically-simulated body: requires a sibling `Collider2D` child
    (declared via `self.requirements`, exactly like `PhysicsBody`) whose
    shape drives both collision detection and (unless overridden) this
    body's auto-computed mass/inertia. Every RigidBody2D in a scene is
    simulated together by a `PhysicsWorld` (see `world.py`) - forces
    accumulate here between physics steps, but integration, collision
    response, and joint solving all happen there, not on the body itself.
    """
    def __init__(
        self,
        position: Vector = Vector(),
        rotation: float = 0.0,
        body_type: BodyType = BodyType.DYNAMIC,
        density: float = 1.0,
        mass: float | None = None,
        inertia: float | None = None,
        linear_velocity: Vector = Vector(0, 0),
        angular_velocity: float = 0.0,
        linear_damping: float = 0.05,
        angular_damping: float = 0.05,
        gravity_scale: float = 1.0,
        friction: float = 0.3,
        restitution: float = 0.0,
        fixed_rotation: bool = False,
        is_sensor: bool = False,
        collision_layer: int = 1,
        collision_mask: int = 0xFFFFFFFF,
        allow_sleep: bool = True,
    ):
        """Records every physics parameter, but doesn't compute mass/
        inertia yet - that needs this body's Collider2D child, which
        isn't available until `on_initialize()` runs.

        `mass`/`inertia`, if given, override the auto-derived values from
        `density` and the collider's shape entirely (useful for
        gameplay-driven bodies where "realistic" density-based mass would
        fight the feel you actually want).
        """
        super().__init__(position, rotation, Vector(1, 1))
        self.requirements = ["Collider2D"]

        self.body_type = body_type
        self.density = density
        self._mass_override = mass
        self._inertia_override = inertia

        self.linear_velocity = linear_velocity.copy()
        self.angular_velocity = angular_velocity

        self.linear_damping = linear_damping
        self.angular_damping = angular_damping
        self.gravity_scale = gravity_scale

        self.friction = friction
        self.restitution = restitution
        self.fixed_rotation = fixed_rotation
        self.is_sensor = is_sensor

        self.collision_layer = collision_layer
        self.collision_mask = collision_mask

        self.allow_sleep = allow_sleep
        self.is_sleeping = False
        self._sleep_timer = 0.0

        self.mass = 0.0
        self.inv_mass = 0.0
        self.inertia = 0.0
        self.inv_inertia = 0.0

        self._force = Vector(0, 0)
        self._torque = 0.0

        self.collider: Collider2D | None = None

    def on_initialize(self):
        """Finds this body's collider child and computes mass/inertia
        from it (unless overridden), then derives the inverse values the
        solver actually uses - 0 for a STATIC/KINEMATIC body (or, for
        inertia, a `fixed_rotation` one), so multiplying by inv_mass/
        inv_inertia anywhere naturally applies zero effect instead of
        needing a body-type check at every use site."""
        colliders = self.find_nodes_with_type('Collider2D')
        if not colliders:
            warning(f"RigidBody2D '{self}' has no Collider2D child - it won't collide with anything.")
        else:
            self.collider = colliders[0]

        self._compute_mass_data()

    def _compute_mass_data(self):
        """(Re)computes mass/inertia and their inverses - called once at
        init, and again by `set_density()`/whenever the collider's shape
        changes size, since a body's mass should track its actual shape
        rather than staying stuck at whatever it was on creation."""
        if self._mass_override is not None:
            self.mass = self._mass_override
        elif self.collider is not None:
            self.mass, computed_inertia = self.collider.collision_shape.compute_mass(self.density)
            if self._inertia_override is None:
                self.inertia = computed_inertia
        else:
            self.mass = 1.0

        if self._inertia_override is not None:
            self.inertia = self._inertia_override

        if self.body_type != BodyType.DYNAMIC:
            self.inv_mass = 0.0
            self.inv_inertia = 0.0
        else:
            self.inv_mass = 1.0 / self.mass if self.mass > 0 else 0.0
            self.inv_inertia = 0.0 if self.fixed_rotation or self.inertia <= 0 else 1.0 / self.inertia

    def apply_force(self, force: Vector, world_point: Vector | None = None):
        """Accumulates `force`, applied at `world_point` if given
        (otherwise at this body's center of mass, producing no torque).
        Cleared every physics step after integration - for a constant
        force (e.g. a thruster), call this every step, not just once."""
        if self.body_type != BodyType.DYNAMIC:
            return
        self.wake()
        self._force += force
        if world_point is not None:
            r = world_point - self.world_position
            self._torque += r.cross(force)

    def apply_torque(self, torque: float):
        """Accumulates a pure rotational force, with no linear component."""
        if self.body_type != BodyType.DYNAMIC:
            return
        self.wake()
        self._torque += torque

    def apply_impulse(self, impulse: Vector, world_point: Vector | None = None):
        """Immediately changes velocity by `impulse * inv_mass` (and
        angular velocity, if `world_point` is off-center) - unlike
        `apply_force()`, this is a one-shot velocity change applied right
        away, not accumulated for the next integration step. Used
        directly by explosions/knockback/etc, and internally by the
        constraint solver itself."""
        if self.body_type != BodyType.DYNAMIC:
            return
        self.wake()
        self.linear_velocity += impulse * self.inv_mass
        if world_point is not None:
            r = world_point - self.world_position
            # r.cross(impulse) * inv_inertia is a radians/sec change (the
            # inertia/impulse math is angle-representation-agnostic in the
            # physics sense, i.e. implicitly radians) - converted to
            # degrees/sec here, at the point of writing to
            # angular_velocity, to match Transform.rotation's convention.
            self.angular_velocity += math.degrees(self.inv_inertia * r.cross(impulse))

    def velocity_at_point(self, world_point: Vector) -> Vector:
        """The linear velocity of the material point on this body
        currently at `world_point` - its center-of-mass velocity plus the
        tangential velocity from rotation about that offset. Needed by
        the contact solver (relative velocity at the actual contact point,
        not just the two bodies' center velocities, matters once either
        body is rotating)."""
        r = world_point - self.world_position
        # Angular velocity is stored in degrees/sec (matching
        # Transform.rotation's convention) - the physics math itself
        # needs radians/sec, so it's converted right at this boundary
        # rather than storing angular velocity in a different unit than
        # the rotation it integrates into.
        omega_rad = math.radians(self.angular_velocity)
        # Tangential velocity from rotation: omega x r, in 2D reduces to
        # perpendicular(r) * omega.
        return self.linear_velocity + Vector(-r.y, r.x) * omega_rad

    def wake(self):
        """Clears sleeping state and resets the sleep timer - called
        automatically by force/impulse application, and by the solver
        when an awake body touches a sleeping one."""
        self.is_sleeping = False
        self._sleep_timer = 0.0

    def on_collision_enter(self, other: 'RigidBody2D', contact):
        """Called the first physics step two (non-sensor) bodies start
        touching - override to react (damage, sound, sticking). `contact`
        is the `core.physics.contact.Manifold` for this pair, in this
        body's own frame (i.e. `contact.normal` points from this body
        toward `other`)."""
        pass

    def on_collision_stay(self, other: 'RigidBody2D', contact):
        """Called every physics step (after the first) two bodies remain
        touching. No-op by default."""
        pass

    def on_collision_exit(self, other: 'RigidBody2D'):
        """Called the physics step two bodies stop touching, having
        touched the step before. No-op by default."""
        pass

    def on_trigger_enter(self, other: 'RigidBody2D'):
        """Called the first physics step this body (or `other`) starts
        overlapping a sensor - fired instead of `on_collision_enter` for
        any pair where either body has `is_sensor=True`, since a sensor
        detects overlap without a physical collision response. No-op by
        default."""
        pass

    def on_trigger_exit(self, other: 'RigidBody2D'):
        """Called the physics step this body/`other`'s sensor overlap ends."""
        pass

    def on_physics_process(self):
        """Called once per physics step, before force integration -
        override to run custom per-step physics logic (e.g. a leg's IK
        target update)."""
        pass
