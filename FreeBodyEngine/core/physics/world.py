"""PhysicsWorld - the rigid-body physics step.

Ties everything else in this package together: finds every RigidBody2D/
Joint2D in the scene, runs broad-phase then narrow-phase collision
detection, solves every contact and joint together via sequential
impulses, integrates positions, updates sleep state, and fires collision/
trigger events - once per fixed-timestep physics tick. `core.scene.Scene`
calls `step()` directly; nothing else in the engine needs to.

No object here persists physics state across steps except the bodies
themselves (`RigidBody2D.touching`, `.is_sleeping`, etc.) - this module
just re-discovers the scene's bodies/joints fresh every step (the same
convention `PhysicsBody`/`Ray2D` already use elsewhere in this codebase)
rather than requiring a body to be explicitly registered with some
separate persistent world object.
"""

import math

from FreeBodyEngine.math import Vector
from FreeBodyEngine.core.scene import Scene
from FreeBodyEngine.core.physics.body import RigidBody2D, BodyType
from FreeBodyEngine.core.physics.joints import Joint2D
from FreeBodyEngine.core.physics.broadphase import SpatialHash
from FreeBodyEngine.core.physics.contact import generate_manifold, Manifold

VELOCITY_ITERATIONS = 8

# How much of a contact's penetration to remove per step (0-1) - not all
# of it at once, or a deeply-overlapping pair would "pop" apart violently
# in a single frame instead of settling smoothly.
BAUMGARTE = 0.2
# Penetration up to this depth is left alone rather than corrected - without
# this, resting contacts would jitter as the solver endlessly chases the
# last fraction of a millimeter of overlap.
LINEAR_SLOP = 0.005
# Caps the position-correction bias velocity itself, so a body that starts
# a step badly overlapping something (e.g. just spawned inside a wall)
# still separates smoothly over several steps instead of launching away
# in one.
MAX_CORRECTION_SPEED = 4.0

# A body's linear/angular speed must stay under these for SLEEP_TIME_THRESHOLD
# seconds before it's allowed to sleep - matches the values Box2D itself
# defaults to (adjusted for degrees rather than radians).
SLEEP_LINEAR_THRESHOLD = 0.05
SLEEP_ANGULAR_THRESHOLD = 3.0
SLEEP_TIME_THRESHOLD = 0.5

GRAVITY = Vector(0, -9.8)


class _ContactPoint:
    """Precomputed per-contact-point solver state for a single physics
    step - effective masses and the restitution target speed, plus the
    running normal/tangent impulse accumulators the solver iterates on.
    Rebuilt from scratch every step; see `joints.py`'s docstring on why
    this solver doesn't warm-start rather than persisting these across
    steps."""
    __slots__ = ('point', 'normal_mass', 'tangent_mass', 'restitution_bias', 'normal_impulse', 'tangent_impulse')

    def __init__(self, point: Vector):
        self.point = point
        self.normal_impulse = 0.0
        self.tangent_impulse = 0.0


class _ContactConstraint:
    """One physics step's solvable contact between two bodies - the
    `Manifold` from narrow-phase plus the extra per-point solver state
    (effective mass, restitution bias) needed to actually resolve it."""
    def __init__(self, body_a: RigidBody2D, body_b: RigidBody2D, manifold: Manifold):
        self.body_a = body_a
        self.body_b = body_b
        self.manifold = manifold
        self.friction = math.sqrt(max(body_a.friction, 0.0) * max(body_b.friction, 0.0))
        self.restitution = max(body_a.restitution, body_b.restitution)
        self.points: list[_ContactPoint] = []

    def init_velocity_constraint(self):
        a, b = self.body_a, self.body_b
        n = self.manifold.normal
        t = Vector(-n.y, n.x)

        self.points = []
        for p in self.manifold.points:
            cp = _ContactPoint(p)
            ra = p - a.world_position
            rb = p - b.world_position

            rn_a = ra.cross(n)
            rn_b = rb.cross(n)
            k_normal = a.inv_mass + b.inv_mass + a.inv_inertia * rn_a ** 2 + b.inv_inertia * rn_b ** 2
            cp.normal_mass = 1.0 / k_normal if k_normal > 0 else 0.0

            rt_a = ra.cross(t)
            rt_b = rb.cross(t)
            k_tangent = a.inv_mass + b.inv_mass + a.inv_inertia * rt_a ** 2 + b.inv_inertia * rt_b ** 2
            cp.tangent_mass = 1.0 / k_tangent if k_tangent > 0 else 0.0

            relative_vel = b.velocity_at_point(p) - a.velocity_at_point(p)
            closing_speed = relative_vel.dot(n)
            # Only bounce off a real impact, not the tiny numerical closing
            # speeds a resting contact has anyway - without this floor,
            # restitution would make every stack of boxes buzz instead of
            # settling (matches Box2D's own b2_velocityThreshold).
            cp.restitution_bias = -self.restitution * closing_speed if closing_speed < -1.0 else 0.0

            self.points.append(cp)

    def solve_velocity_constraint(self, dt: float):
        a, b = self.body_a, self.body_b
        n = self.manifold.normal
        t = Vector(-n.y, n.x)
        position_bias = min(
            (BAUMGARTE / dt) * max(self.manifold.penetration - LINEAR_SLOP, 0.0),
            MAX_CORRECTION_SPEED,
        )

        for cp in self.points:
            relative_vel = b.velocity_at_point(cp.point) - a.velocity_at_point(cp.point)
            vn = relative_vel.dot(n)

            lambda_n = -cp.normal_mass * (vn - cp.restitution_bias - position_bias)
            new_impulse = max(cp.normal_impulse + lambda_n, 0.0)
            lambda_n = new_impulse - cp.normal_impulse
            cp.normal_impulse = new_impulse

            impulse = n * lambda_n
            a.apply_impulse(-impulse, cp.point)
            b.apply_impulse(impulse, cp.point)

        for cp in self.points:
            relative_vel = b.velocity_at_point(cp.point) - a.velocity_at_point(cp.point)
            vt = relative_vel.dot(t)

            lambda_t = -cp.tangent_mass * vt
            max_friction = self.friction * cp.normal_impulse
            new_impulse = max(-max_friction, min(max_friction, cp.tangent_impulse + lambda_t))
            lambda_t = new_impulse - cp.tangent_impulse
            cp.tangent_impulse = new_impulse

            impulse = t * lambda_t
            a.apply_impulse(-impulse, cp.point)
            b.apply_impulse(impulse, cp.point)


def _flip_manifold(manifold: Manifold) -> Manifold:
    """Returns a copy of `manifold` with its normal reversed - handed to
    the second body in a colliding pair's `on_collision_*` callbacks, so
    `contact.normal` always points away from whichever body is receiving
    the callback (per `RigidBody2D.on_collision_enter`'s documented
    contract), regardless of which body happened to be narrow-phase's
    `shape_a`."""
    return Manifold(-manifold.normal, manifold.penetration, manifold.points)


def step(scene: Scene, dt: float):
    """Runs one fixed-timestep physics step for every RigidBody2D/Joint2D
    in `scene` - called by `Scene._physics_process()` alongside the older
    `PhysicsBody` loop (the two systems coexist; a scene can freely mix
    both kinds of body, they just don't interact with each other)."""
    bodies: list[RigidBody2D] = scene.root.find_nodes_with_type('RigidBody2D')
    joints: list[Joint2D] = scene.root.find_nodes_with_type('Joint2D')

    if not bodies:
        return

    for body in bodies:
        body.on_physics_process()

    non_colliding_pairs = set()
    for joint in joints:
        if not joint.collide_connected and joint.body_b is not None:
            non_colliding_pairs.add(frozenset((id(joint.body_a), id(joint.body_b))))

    for body in bodies:
        if body.body_type != BodyType.DYNAMIC or body.is_sleeping:
            continue
        body.linear_velocity += GRAVITY * body.gravity_scale * dt
        body.linear_velocity += body._force * body.inv_mass * dt
        body.angular_velocity += math.degrees(body._torque * body.inv_inertia * dt)
        body.linear_velocity *= 1.0 / (1.0 + dt * body.linear_damping)
        body.angular_velocity *= 1.0 / (1.0 + dt * body.angular_damping)
        body._force = Vector(0, 0)
        body._torque = 0.0

    # Collider2D.collision_shape is normally kept in sync with its node's
    # transform by apply_transform(), called from Collider2D.on_update()
    # during the UPDATE phase - but UpdateCoordinator runs PHYSICS *before*
    # UPDATE each frame, and PHYSICS can tick several times per UPDATE (a
    # fixed-timestep accumulator catching up), so relying on that would
    # mean narrow-phase tests against wherever the shape was as of last
    # frame's UPDATE, not this step's actual integrated position. Synced
    # here directly instead, so a body's collider always reflects exactly
    # where physics just put it.
    for body in bodies:
        if body.collider is not None:
            body.collider.apply_transform()

    hash_grid = SpatialHash()
    collidable = [body for body in bodies if body.collider is not None and not body.is_sleeping]
    for body in collidable:
        aabb_min, aabb_max = body.collider.collision_shape.get_aabb()
        hash_grid.insert(body, aabb_min, aabb_max)
    # Sleeping bodies still need to be collidable against (an awake body
    # falling onto a sleeping pile has to wake it) - inserted separately so
    # find_pairs() above only paired up already-awake bodies against each
    # other, avoiding doing real work for two sleeping bodies that are
    # (by definition) not going anywhere relative to each other anyway.
    sleeping = [body for body in bodies if body.collider is not None and body.is_sleeping]
    for body in sleeping:
        aabb_min, aabb_max = body.collider.collision_shape.get_aabb()
        hash_grid.insert(body, aabb_min, aabb_max)

    current_touching: dict[RigidBody2D, set] = {body: set() for body in bodies}
    contacts: list[_ContactConstraint] = []
    # Every touching pair with its manifold, for event dispatch - kept
    # separate from `contacts` because `contacts` deliberately excludes
    # sensor pairs and sleeping-body pairs (neither needs solving), but
    # both of those still need their on_trigger_enter/on_collision_enter
    # callbacks fired.
    touching_pairs: list[tuple[RigidBody2D, RigidBody2D, Manifold]] = []

    for a, b in hash_grid.find_pairs():
        if a.body_type != BodyType.DYNAMIC and b.body_type != BodyType.DYNAMIC:
            continue
        if (a.collision_layer & b.collision_mask) == 0 or (b.collision_layer & a.collision_mask) == 0:
            continue
        if frozenset((id(a), id(b))) in non_colliding_pairs:
            continue

        manifold = generate_manifold(a.collider.collision_shape, b.collider.collision_shape)
        if manifold is None:
            continue

        # Only a DYNAMIC body's touch should wake a sleeping one - a
        # STATIC body (the ground, say) is never "asleep" itself (it's
        # skipped by the sleep-check loop entirely) but also never
        # "awake" in the sense that matters here, so without this check
        # a body would wake back up the instant after falling asleep on
        # top of one, just for still touching it.
        if a.is_sleeping and not b.is_sleeping and b.body_type == BodyType.DYNAMIC:
            a.wake()
        elif b.is_sleeping and not a.is_sleeping and a.body_type == BodyType.DYNAMIC:
            b.wake()

        current_touching[a].add(b)
        current_touching[b].add(a)
        touching_pairs.append((a, b, manifold))

        # A still-sleeping body (neither side of this pair just woke via
        # the check above) must NOT get a contact constraint solved
        # against it at all, not just skip the wake-check - solving one
        # anyway would apply the same small per-step corrective impulse a
        # resting-but-awake body gets, and apply_impulse() waking
        # whichever body it's applied to would immediately undo the sleep
        # this same step, on every single step, forever.
        if not a.is_sensor and not b.is_sensor and not a.is_sleeping and not b.is_sleeping:
            constraint = _ContactConstraint(a, b, manifold)
            constraint.init_velocity_constraint()
            contacts.append(constraint)

    for joint in joints:
        joint.init_velocity_constraint(dt)

    for _ in range(VELOCITY_ITERATIONS):
        for joint in joints:
            joint.solve_velocity_constraint()
        for contact in contacts:
            contact.solve_velocity_constraint(dt)

    for body in bodies:
        if body.is_sleeping:
            continue
        if body.body_type == BodyType.STATIC:
            continue
        body.transform.position += body.linear_velocity * dt
        body.transform.rotation += body.angular_velocity * dt

    for body in bodies:
        if body.body_type != BodyType.DYNAMIC or not body.allow_sleep:
            continue
        if body.linear_velocity.magnitude < SLEEP_LINEAR_THRESHOLD and abs(body.angular_velocity) < SLEEP_ANGULAR_THRESHOLD:
            body._sleep_timer += dt
            if body._sleep_timer >= SLEEP_TIME_THRESHOLD:
                body.is_sleeping = True
                body.linear_velocity = Vector(0, 0)
                body.angular_velocity = 0.0
        else:
            body._sleep_timer = 0.0

    for a, b, manifold in touching_pairs:
        is_trigger = a.is_sensor or b.is_sensor
        was_touching = b in a.touching

        if is_trigger:
            if not was_touching:
                a.on_trigger_enter(b)
                b.on_trigger_enter(a)
        else:
            manifold_for_a = manifold
            manifold_for_b = _flip_manifold(manifold)
            if not was_touching:
                a.on_collision_enter(b, manifold_for_a)
                b.on_collision_enter(a, manifold_for_b)
            else:
                a.on_collision_stay(b, manifold_for_a)
                b.on_collision_stay(a, manifold_for_b)

    for body in bodies:
        for other in body.touching:
            if other not in current_touching[body]:
                if body.is_sensor or other.is_sensor:
                    body.on_trigger_exit(other)
                else:
                    body.on_collision_exit(other)
        body.touching = current_touching[body]
