"""Physics constraints (joints) between RigidBody2D bodies.

Every joint here is solved the same way contacts are (see `world.py`):
once per physics step, `init_velocity_constraint()` precomputes anchors
and effective mass from the bodies' current position/rotation, then
`solve_velocity_constraint()` runs once per solver iteration, applying a
corrective impulse that (over several iterations, interleaved with every
other joint and contact in the scene) converges the whole system toward
satisfying every constraint at once. This is what makes chained,
motor-driven limbs - like a procedurally-animated spider leg - possible:
each leg segment is its own RigidBody2D, connected to its neighbor by a
RevoluteJoint2D with a motor, and the solver reconciles all of them
together rather than one at a time.

A joint's two bodies must already be in the scene (added via
`scene.add()`) before the joint itself is constructed - anchors are
converted from world space to each body's local space immediately, which
needs a valid `world_position`/`world_rotation` to convert from.
"""

import math

from FreeBodyEngine.core.node import Node
from FreeBodyEngine.core.physics.body import RigidBody2D
from FreeBodyEngine.math import Vector


# Caps how fast a joint's Baumgarte position-correction bias is allowed to
# pull a body back into compliance, the same way world.py's contact solver
# caps its own position bias (MAX_CORRECTION_SPEED there) - without this,
# a joint whose two bodies start out far from satisfying it (e.g. a
# procedurally-placed limb chain whose segments weren't positioned exactly
# where their joints expect) would inject a correction proportional to the
# *entire* initial error in a single step, which for a large error is far
# more velocity than the joint should ever need to add - the difference
# between "snaps smoothly into place over a few frames" and "launches
# across the map on frame one."
MAX_JOINT_BIAS_SPEED = 4.0

# Positional error below this is left alone, so the position solver doesn't
# jitter bodies back and forth chasing a rounding error.
LINEAR_SLOP = 0.005

# The most a single position-solver pass will move a joint's anchors together.
MAX_LINEAR_CORRECTION = 0.2

# And the most degrees of limit violation it will take out in one pass.
MAX_ANGULAR_CORRECTION = 8.0


def _solve_2x2(k11: float, k12: float, k21: float, k22: float, bx: float, by: float) -> Vector:
    """Solves the 2x2 linear system `K * x = b` via Cramer's rule - the
    shared building block behind every point-to-point constraint below
    (the effective mass matrix relating a pair of anchor points' relative
    velocity to the impulse needed to zero it)."""
    det = k11 * k22 - k12 * k21
    if abs(det) < 1e-12:
        return Vector(0, 0)
    inv_det = 1.0 / det
    return Vector(inv_det * (k22 * bx - k12 * by), inv_det * (k11 * by - k21 * bx))


class Joint2D(Node):
    """Base class for a physics constraint between two bodies. Not a
    Node2D - a joint has no position/rotation of its own, so it's added
    directly under the scene root (or anywhere in the tree, really -
    like everything else here it's discovered by `find_nodes_with_type`,
    not by transform hierarchy)."""
    def __init__(self, body_a: RigidBody2D, body_b: RigidBody2D | None, collide_connected: bool = False):
        """`collide_connected` controls whether `body_a`/`body_b` still
        generate contact-solver collisions with each other despite being
        jointed - off by default (matching every other engine's
        convention), since two directly-jointed bodies (e.g. a leg
        segment's two ends) are expected to overlap/touch by
        construction, and fighting that with the contact solver too would
        just make the joint fight itself. `body_b` is `None` only for
        joints that connect a single body to a fixed external point
        rather than to another body (see `TargetJoint2D`)."""
        super().__init__()
        self.body_a = body_a
        self.body_b = body_b
        self.collide_connected = collide_connected

    def init_velocity_constraint(self, dt: float):
        """Called once per physics step, before any solver iterations -
        override to precompute anchors/effective mass (anything that only
        changes once per step, not per iteration)."""
        pass

    def solve_position_constraint(self) -> float:
        """Pushes the two bodies' positions back toward satisfying this
        joint, returning how far apart its anchor points still are.

        Run after integration, separately from the velocity constraints, and
        acting on positions directly rather than through velocity - so the
        correction leaves no energy behind in the bodies the way a velocity
        bias does. Joints that have no positional error to speak of can leave
        this alone.
        """
        return 0.0

    def solve_velocity_constraint(self):
        """Called once per solver iteration (several times per physics
        step) - override to apply this joint's corrective impulse(s)."""
        pass


class DistanceJoint2D(Joint2D):
    """A rigid rod between a fixed point on each body - holds the
    distance between `anchor_a`/`anchor_b` fixed at `length` via a stiff
    Baumgarte-corrected constraint. For a springy, non-rigid version, see
    `SpringJoint2D`."""
    def __init__(self, body_a: RigidBody2D, body_b: RigidBody2D, anchor_a: Vector = None, anchor_b: Vector = None, length: float | None = None, collide_connected: bool = False):
        """`anchor_a`/`anchor_b` are LOCAL offsets from each body's center
        (defaulting to `(0, 0)`, the body's own center of mass) - stored
        local rather than as world points, since the joint has to track
        them as the bodies rotate. `length` defaults to the anchors'
        actual distance apart at creation time."""
        super().__init__(body_a, body_b, collide_connected)
        self.anchor_a = anchor_a if anchor_a is not None else Vector(0, 0)
        self.anchor_b = anchor_b if anchor_b is not None else Vector(0, 0)
        self.length = length
        self.beta = 0.2  # Baumgarte position-correction factor (0-1: how much of the position error to remove per step)

    def init_velocity_constraint(self, dt: float):
        self._dt = dt
        self._ra = self.anchor_a.rotated(self.body_a.world_rotation)
        self._rb = self.anchor_b.rotated(self.body_b.world_rotation)

        pa = self.body_a.world_position + self._ra
        pb = self.body_b.world_position + self._rb
        delta = pb - pa
        dist = delta.magnitude

        if self.length is None:
            self.length = dist

        self._normal = delta.normalized if dist > 1e-9 else Vector(1, 0)
        separation = dist - self.length

        ra_cross_n = self._ra.cross(self._normal)
        rb_cross_n = self._rb.cross(self._normal)
        k = (self.body_a.inv_mass + self.body_b.inv_mass +
             self.body_a.inv_inertia * ra_cross_n ** 2 +
             self.body_b.inv_inertia * rb_cross_n ** 2)
        self._effective_mass = 1.0 / k if k > 0 else 0.0
        self._bias = max(-MAX_JOINT_BIAS_SPEED, min(MAX_JOINT_BIAS_SPEED, (self.beta / dt) * separation))

    def solve_velocity_constraint(self):
        va = self.body_a.velocity_at_point(self.body_a.world_position + self._ra)
        vb = self.body_b.velocity_at_point(self.body_b.world_position + self._rb)
        relative_speed = (vb - va).dot(self._normal)

        impulse_mag = -self._effective_mass * (relative_speed + self._bias)
        impulse = self._normal * impulse_mag

        self.body_a.apply_impulse(-impulse, self.body_a.world_position + self._ra)
        self.body_b.apply_impulse(impulse, self.body_b.world_position + self._rb)


class SpringJoint2D(Joint2D):
    """A soft distance joint - stretches/compresses springily around
    `length` instead of holding it rigidly like `DistanceJoint2D`, via a
    damped-spring constraint (`frequency` in Hz, `damping_ratio` from 0 =
    undamped/bouncy to 1 = critically damped/no overshoot). The standard
    "soft constraints" derivation (as used by Box2D's own soft distance
    joint) folding the spring's frequency/damping into the impulse solve
    itself, rather than applying a separate explicit spring force."""
    def __init__(self, body_a: RigidBody2D, body_b: RigidBody2D, anchor_a: Vector = None, anchor_b: Vector = None, length: float | None = None, frequency: float = 4.0, damping_ratio: float = 0.5, collide_connected: bool = False):
        super().__init__(body_a, body_b, collide_connected)
        self.anchor_a = anchor_a if anchor_a is not None else Vector(0, 0)
        self.anchor_b = anchor_b if anchor_b is not None else Vector(0, 0)
        self.length = length
        self.frequency = frequency
        self.damping_ratio = damping_ratio
        self._impulse = 0.0

    def init_velocity_constraint(self, dt: float):
        self._dt = dt
        self._ra = self.anchor_a.rotated(self.body_a.world_rotation)
        self._rb = self.anchor_b.rotated(self.body_b.world_rotation)

        pa = self.body_a.world_position + self._ra
        pb = self.body_b.world_position + self._rb
        delta = pb - pa
        dist = delta.magnitude

        if self.length is None:
            self.length = dist

        self._normal = delta.normalized if dist > 1e-9 else Vector(1, 0)
        separation = dist - self.length

        ra_cross_n = self._ra.cross(self._normal)
        rb_cross_n = self._rb.cross(self._normal)
        k = (self.body_a.inv_mass + self.body_b.inv_mass +
             self.body_a.inv_inertia * ra_cross_n ** 2 +
             self.body_b.inv_inertia * rb_cross_n ** 2)
        effective_mass = 1.0 / k if k > 0 else 0.0

        omega = 2 * math.pi * self.frequency
        damping_coeff = 2 * effective_mass * self.damping_ratio * omega
        spring_k = effective_mass * omega * omega
        gamma = dt * (damping_coeff + dt * spring_k)
        self._gamma = 1.0 / gamma if gamma > 1e-12 else 0.0
        self._bias = separation * dt * spring_k * self._gamma

        self._soft_mass = 1.0 / (k + self._gamma) if (k + self._gamma) > 0 else 0.0
        # Box2D's own soft-constraint joints let this persist across steps
        # because they warm-start: re-applying last step's final impulse
        # to the bodies' velocities before this step's first iteration, so
        # `self._impulse` still means "impulse already reflected in the
        # current velocity state." This solver doesn't warm-start, so
        # without a reset here `gamma * self._impulse` would keep feeding
        # back an ever-growing value that was never actually re-applied -
        # in practice, a spring that just accelerates monotonically
        # instead of oscillating toward equilibrium.
        self._impulse = 0.0

    def solve_velocity_constraint(self):
        va = self.body_a.velocity_at_point(self.body_a.world_position + self._ra)
        vb = self.body_b.velocity_at_point(self.body_b.world_position + self._rb)
        relative_speed = (vb - va).dot(self._normal)

        impulse_mag = -self._soft_mass * (relative_speed + self._bias + self._gamma * self._impulse)
        self._impulse += impulse_mag
        impulse = self._normal * impulse_mag

        self.body_a.apply_impulse(-impulse, self.body_a.world_position + self._ra)
        self.body_b.apply_impulse(impulse, self.body_b.world_position + self._rb)


class RevoluteJoint2D(Joint2D):
    """A hinge: locks a shared world-space anchor point between the two
    bodies (they can rotate freely around it, but not translate apart),
    with an optional motor (drives their RELATIVE angular speed toward
    `motor_speed`, clamped to `max_motor_torque`) and/or angle limits
    (bounds their relative rotation to `[lower_angle, upper_angle]`
    degrees, measured from whatever their relative angle happened to be
    when this joint was created) - exactly what a motor-driven,
    limited-range limb joint (an elbow/knee/shoulder) needs."""
    def __init__(self, body_a: RigidBody2D, body_b: RigidBody2D, anchor: Vector, collide_connected: bool = False,
                 enable_motor: bool = False, motor_speed: float = 0.0, max_motor_torque: float = 0.0,
                 enable_limit: bool = False, lower_angle: float = 0.0, upper_angle: float = 0.0):
        """`anchor` is a WORLD-space point - both bodies must already be
        in the scene so their current world transform is valid, since
        it's immediately converted to a local offset on each body (so the
        joint tracks the same material point on each as they move,
        rather than staying fixed in world space)."""
        super().__init__(body_a, body_b, collide_connected)
        self.anchor_a = (anchor - body_a.world_position).rotated(-body_a.world_rotation)
        self.anchor_b = (anchor - body_b.world_position).rotated(-body_b.world_rotation)
        self.reference_angle = body_b.world_rotation - body_a.world_rotation

        self.enable_motor = enable_motor
        self.motor_speed = motor_speed
        self.max_motor_torque = max_motor_torque

        self.enable_limit = enable_limit
        self.lower_angle = lower_angle
        self.upper_angle = upper_angle

        self.beta = 0.2
        self._motor_impulse = 0.0
        self._lower_impulse = 0.0
        self._upper_impulse = 0.0
        self._point_impulse = Vector(0, 0)

    def init_velocity_constraint(self, dt: float):
        self._dt = dt
        self._ra = self.anchor_a.rotated(self.body_a.world_rotation)
        self._rb = self.anchor_b.rotated(self.body_b.world_rotation)

        ma, mb = self.body_a.inv_mass, self.body_b.inv_mass
        ia, ib = self.body_a.inv_inertia, self.body_b.inv_inertia

        k11 = ma + mb + ia * self._ra.y ** 2 + ib * self._rb.y ** 2
        k12 = -ia * self._ra.x * self._ra.y - ib * self._rb.x * self._rb.y
        k22 = ma + mb + ia * self._ra.x ** 2 + ib * self._rb.x ** 2
        self._k = (k11, k12, k12, k22)

        angular_k = ia + ib
        self._angular_mass = 1.0 / angular_k if angular_k > 0 else 0.0

        pa = self.body_a.world_position + self._ra
        pb = self.body_b.world_position + self._rb
        self._point_error = pb - pa

        # Warm start the point constraint: re-apply the impulse this joint
        # settled on last step before solving this one, so the iterations below
        # start from an almost-correct answer instead of from zero.
        #
        # Without it a chain is soft, and visibly so. Each step's eight
        # Gauss-Seidel passes have to rediscover the whole force from nothing,
        # and they only partly get there, so a chain dragged along at a steady
        # speed stretches a little further every step - a three-link lantern
        # chain pulled at walking pace settles at roughly three times its real
        # length. The position bias cannot rescue that either; it is capped at
        # MAX_JOINT_BIAS_SPEED so that a large error is corrected gently rather
        # than explosively, which means it pulls in far slower than the drag
        # pulls out.
        self.body_a.apply_impulse(-self._point_impulse, pa)
        self.body_b.apply_impulse(self._point_impulse, pb)

    def solve_velocity_constraint(self):
        if self.enable_motor and self._angular_mass > 0:
            relative_speed = math.radians(self.body_b.angular_velocity - self.body_a.angular_velocity)
            target_speed = math.radians(self.motor_speed)
            cdot = relative_speed - target_speed

            impulse = -self._angular_mass * cdot
            max_impulse = self.max_motor_torque * self._dt
            old_impulse = self._motor_impulse
            self._motor_impulse = max(-max_impulse, min(max_impulse, old_impulse + impulse))
            impulse = self._motor_impulse - old_impulse

            self.body_a.angular_velocity -= math.degrees(self.body_a.inv_inertia * impulse)
            self.body_b.angular_velocity += math.degrees(self.body_b.inv_inertia * impulse)

        if self.enable_limit and self._angular_mass > 0:
            # Each limit is only even considered while the joint is
            # actually at or past it - exactly like a contact constraint
            # only exists while two shapes are actually penetrating, not
            # "active with zero bias" the rest of the time. Computing a
            # correction unconditionally (gated only by clamping the
            # ACCUMULATED impulse to stay one-directional, without also
            # gating whether to run the correction AT ALL) meant any
            # nonzero relative velocity - even while nowhere near either
            # limit - fed a spurious "correction," which fought the motor
            # from the very first frame. Each limit also tracks its own
            # accumulated, clamped impulse (like the motor above) so 8
            # solver iterations converge instead of each one independently
            # over-correcting on top of the last.
            relative_angle = self.body_b.world_rotation - self.body_a.world_rotation - self.reference_angle

            if relative_angle <= self.lower_angle:
                c = relative_angle - self.lower_angle
                relative_speed = math.radians(self.body_b.angular_velocity - self.body_a.angular_velocity)
                bias = (self.beta / self._dt) * math.radians(c)
                raw = -self._angular_mass * (relative_speed + bias)
                new_lower = max(self._lower_impulse + raw, 0.0)
                delta = new_lower - self._lower_impulse
                self._lower_impulse = new_lower

                self.body_a.angular_velocity -= math.degrees(self.body_a.inv_inertia * delta)
                self.body_b.angular_velocity += math.degrees(self.body_b.inv_inertia * delta)
            else:
                self._lower_impulse = 0.0

            if relative_angle >= self.upper_angle:
                c = relative_angle - self.upper_angle
                relative_speed = math.radians(self.body_b.angular_velocity - self.body_a.angular_velocity)
                bias = (self.beta / self._dt) * math.radians(c)
                raw = -self._angular_mass * (relative_speed + bias)
                new_upper = max(self._upper_impulse - raw, 0.0)
                delta = new_upper - self._upper_impulse
                self._upper_impulse = new_upper

                self.body_a.angular_velocity += math.degrees(self.body_a.inv_inertia * delta)
                self.body_b.angular_velocity -= math.degrees(self.body_b.inv_inertia * delta)
            else:
                self._upper_impulse = 0.0

        va = self.body_a.velocity_at_point(self.body_a.world_position + self._ra)
        vb = self.body_b.velocity_at_point(self.body_b.world_position + self._rb)
        cdot = vb - va
        bias = self._point_error * (self.beta / self._dt)
        if bias.magnitude > MAX_JOINT_BIAS_SPEED:
            bias = bias.normalized * MAX_JOINT_BIAS_SPEED

        k11, k12, k21, k22 = self._k
        impulse = _solve_2x2(k11, k12, k21, k22, -(cdot.x + bias.x), -(cdot.y + bias.y))

        self._point_impulse += impulse
        self.body_a.apply_impulse(-impulse, self.body_a.world_position + self._ra)
        self.body_b.apply_impulse(impulse, self.body_b.world_position + self._rb)

    def solve_position_constraint(self) -> float:
        a, b = self.body_a, self.body_b

        # The angle limit gets corrected before the anchor point, and for the
        # same reason the anchor point needs correcting at all: a limit
        # enforced only through a velocity bias is a limit that enough energy
        # simply passes through. A chain of these would fold back on itself and
        # wrap over its own anchor, with the relative angle three times past a
        # limit that was supposedly holding it.
        angular_error = 0.0
        angular_k = a.inv_inertia + b.inv_inertia
        if self.enable_limit and angular_k > 0:
            relative_angle = b.world_rotation - a.world_rotation - self.reference_angle

            violation = 0.0
            if relative_angle < self.lower_angle:
                violation = relative_angle - self.lower_angle
            elif relative_angle > self.upper_angle:
                violation = relative_angle - self.upper_angle

            if violation != 0.0:
                angular_error = abs(violation)
                violation = max(-MAX_ANGULAR_CORRECTION,
                                min(MAX_ANGULAR_CORRECTION, violation))
                impulse = -math.radians(violation) / angular_k
                a.transform.rotation -= math.degrees(a.inv_inertia * impulse)
                b.transform.rotation += math.degrees(b.inv_inertia * impulse)

        ra = self.anchor_a.rotated(a.world_rotation)
        rb = self.anchor_b.rotated(b.world_rotation)
        error = (b.world_position + rb) - (a.world_position + ra)
        magnitude = error.magnitude
        # Reported together so world.step's early-out cannot call a joint
        # settled while its limit is still being violated.
        worst = max(magnitude, math.radians(angular_error))
        if magnitude < LINEAR_SLOP:
            return worst

        # Clamped so one pass never teleports a badly separated joint; the
        # remaining error is taken off by the passes and steps after it.
        correction = error
        if magnitude > MAX_LINEAR_CORRECTION:
            correction = error.normalized * MAX_LINEAR_CORRECTION

        ma, mb = a.inv_mass, b.inv_mass
        ia, ib = a.inv_inertia, b.inv_inertia

        k11 = ma + mb + ia * ra.y ** 2 + ib * rb.y ** 2
        k12 = -ia * ra.x * ra.y - ib * rb.x * rb.y
        k22 = ma + mb + ia * ra.x ** 2 + ib * rb.x ** 2

        impulse = _solve_2x2(k11, k12, k12, k22, -correction.x, -correction.y)

        a.transform.position -= impulse * ma
        a.transform.rotation -= math.degrees(ia * ra.cross(impulse))
        b.transform.position += impulse * mb
        b.transform.rotation += math.degrees(ib * rb.cross(impulse))

        return worst


class WeldJoint2D(Joint2D):
    """Rigidly fuses two bodies together at a shared world-space anchor
    point AND their current relative angle - like `RevoluteJoint2D` with
    its rotational freedom locked too, so the pair behaves as a single
    rigid body while still being two separate (and later detachable)
    ones. Useful for permanently gluing parts together without folding
    them into a single RigidBody2D/collider."""
    def __init__(self, body_a: RigidBody2D, body_b: RigidBody2D, anchor: Vector, collide_connected: bool = False):
        super().__init__(body_a, body_b, collide_connected)
        self.anchor_a = (anchor - body_a.world_position).rotated(-body_a.world_rotation)
        self.anchor_b = (anchor - body_b.world_position).rotated(-body_b.world_rotation)
        self.reference_angle = body_b.world_rotation - body_a.world_rotation
        self.beta = 0.2

    def init_velocity_constraint(self, dt: float):
        self._dt = dt
        self._ra = self.anchor_a.rotated(self.body_a.world_rotation)
        self._rb = self.anchor_b.rotated(self.body_b.world_rotation)

        ma, mb = self.body_a.inv_mass, self.body_b.inv_mass
        ia, ib = self.body_a.inv_inertia, self.body_b.inv_inertia

        k11 = ma + mb + ia * self._ra.y ** 2 + ib * self._rb.y ** 2
        k12 = -ia * self._ra.x * self._ra.y - ib * self._rb.x * self._rb.y
        k22 = ma + mb + ia * self._ra.x ** 2 + ib * self._rb.x ** 2
        self._k = (k11, k12, k12, k22)

        angular_k = ia + ib
        self._angular_mass = 1.0 / angular_k if angular_k > 0 else 0.0

        pa = self.body_a.world_position + self._ra
        pb = self.body_b.world_position + self._rb
        self._point_error = pb - pa
        self._angle_error = self.body_b.world_rotation - self.body_a.world_rotation - self.reference_angle

    def solve_velocity_constraint(self):
        if self._angular_mass > 0:
            cdot = math.radians(self.body_b.angular_velocity - self.body_a.angular_velocity)
            bias = (self.beta / self._dt) * math.radians(self._angle_error)
            impulse = -self._angular_mass * (cdot + bias)
            self.body_a.angular_velocity -= math.degrees(self.body_a.inv_inertia * impulse)
            self.body_b.angular_velocity += math.degrees(self.body_b.inv_inertia * impulse)

        va = self.body_a.velocity_at_point(self.body_a.world_position + self._ra)
        vb = self.body_b.velocity_at_point(self.body_b.world_position + self._rb)
        cdot = vb - va
        bias = self._point_error * (self.beta / self._dt)
        if bias.magnitude > MAX_JOINT_BIAS_SPEED:
            bias = bias.normalized * MAX_JOINT_BIAS_SPEED

        k11, k12, k21, k22 = self._k
        impulse = _solve_2x2(k11, k12, k21, k22, -(cdot.x + bias.x), -(cdot.y + bias.y))

        self.body_a.apply_impulse(-impulse, self.body_a.world_position + self._ra)
        self.body_b.apply_impulse(impulse, self.body_b.world_position + self._rb)


class TargetJoint2D(Joint2D):
    """Pulls a single point on `body` toward a movable world-space
    `target`, softly (the same frequency/damping soft-constraint math as
    `SpringJoint2D`) and clamped to `max_force` - for mouse-drag
    interactions, a grapple hook's pull, or as the drive behind
    procedural IK (aim a leg's foot at a target step position and let the
    spring pull the limb chain toward it through its other joints,
    instead of hand-solving the chain's inverse kinematics directly).

    Only affects one body - the target point itself has no mass of its
    own, exactly like grabbing a body with the mouse."""
    def __init__(self, body: RigidBody2D, target: Vector, local_anchor: Vector = None, max_force: float = 1000.0, frequency: float = 5.0, damping_ratio: float = 0.7):
        super().__init__(body, None, collide_connected=True)
        self.target = target.copy()
        self.local_anchor = local_anchor if local_anchor is not None else Vector(0, 0)
        self.max_force = max_force
        self.frequency = frequency
        self.damping_ratio = damping_ratio
        self._impulse = Vector(0, 0)

    def init_velocity_constraint(self, dt: float):
        body = self.body_a
        self._dt = dt
        self._r = self.local_anchor.rotated(body.world_rotation)

        k11 = body.inv_mass + body.inv_inertia * self._r.y ** 2
        k12 = -body.inv_inertia * self._r.x * self._r.y
        k22 = body.inv_mass + body.inv_inertia * self._r.x ** 2

        omega = 2 * math.pi * self.frequency
        damping_coeff = 2 * body.mass * self.damping_ratio * omega if body.inv_mass > 0 else 0.0
        spring_k = body.mass * omega * omega if body.inv_mass > 0 else 0.0
        gamma = dt * (damping_coeff + dt * spring_k)
        self._gamma = 1.0 / gamma if gamma > 1e-12 else 0.0
        self._beta = dt * spring_k * self._gamma

        self._k = (k11 + self._gamma, k12, k12, k22 + self._gamma)

        anchor_pos = body.world_position + self._r
        self._c = anchor_pos - self.target
        # See SpringJoint2D's identical reset for why: without warm-
        # starting, this accumulator must start fresh each step rather
        # than carry the previous step's already-applied total forward.
        self._impulse = Vector(0, 0)

    def solve_velocity_constraint(self):
        body = self.body_a
        v = body.velocity_at_point(body.world_position + self._r)
        cdot = v + self._c * self._beta + self._impulse * self._gamma

        k11, k12, k21, k22 = self._k
        impulse = _solve_2x2(k11, k12, k21, k22, -cdot.x, -cdot.y)

        old_impulse = self._impulse
        self._impulse = self._impulse + impulse
        max_impulse = self.max_force * self._dt
        if self._impulse.magnitude > max_impulse:
            self._impulse = self._impulse.normalized * max_impulse
        impulse = self._impulse - old_impulse

        body.apply_impulse(impulse, body.world_position + self._r)
