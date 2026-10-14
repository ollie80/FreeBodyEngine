"""Tests for the RigidBody2D/Joint2D solver, built around a chain of revolute
joints hanging off a kinematic anchor - a lantern swinging from a walking
character, which is what each of these failures was first found in.

Each of them is silent: nothing errors, nothing warns, the chain just behaves
like something other than a chain.
"""
import pytest

from FreeBodyEngine.core.node import RootNode
from FreeBodyEngine.core.collider import CircleCollider2D
from FreeBodyEngine.core.physics.body import RigidBody2D, BodyType
from FreeBodyEngine.core.physics.joints import RevoluteJoint2D
from FreeBodyEngine.core.physics import world
from FreeBodyEngine.math import Vector


STEP = 1 / 60
LINK_SPACING = 3.0


class _Scene:
    """The two attributes world.step() actually reads off a scene."""

    def __init__(self, root):
        self.root = root


def _body(root, pos, body_type=BodyType.DYNAMIC, mass=10.0, **kwargs):
    body = RigidBody2D(position=pos, body_type=body_type, mass=mass,
                       fixed_rotation=True, **kwargs)
    body.add(CircleCollider2D())
    root.add(body)
    return body


def _chain(links=3, anchor_type=BodyType.KINEMATIC):
    """A kinematic anchor with `links` dynamic links hanging below it."""
    root = RootNode(scene=None)
    anchor = _body(root, Vector(0, 0), anchor_type)
    bodies = [anchor]
    for i in range(1, links + 1):
        bodies.append(_body(root, Vector(0, -LINK_SPACING * i)))

    for a, b in zip(bodies, bodies[1:]):
        midpoint = (a.transform.position + b.transform.position) / 2
        root.add(RevoluteJoint2D(a, b, midpoint, collide_connected=False))

    return _Scene(root), bodies


def _advance(scene, steps):
    for _ in range(steps):
        world.step(scene, STEP)


def _gaps(bodies):
    return [(b.world_position - a.world_position).magnitude
            for a, b in zip(bodies, bodies[1:])]


def test_mass_is_resolved_even_when_on_initialize_is_overridden():
    """A subclass that overrides on_initialize and forgets to call super()
    never resolves its collider, so mass - and with it inv_mass - stays zero.

    That is not an inert mistake. Gravity is applied straight to velocity, so
    the body still accelerates, while every constraint solved against it
    computes an effective mass of zero and can apply no impulse at all. It
    falls forever, through everything, and nothing says a word.
    """
    class Forgetful(RigidBody2D):
        def on_initialize(self):
            pass

    root = RootNode(scene=None)
    body = Forgetful(position=Vector(0, 0))
    body.add(CircleCollider2D())
    root.add(body)

    assert body.inv_mass == 0.0, 'precondition: the override skipped the base hook'

    _advance(_Scene(root), 1)

    assert body.inv_mass > 0.0
    assert body.collider is not None


def test_a_joint_wakes_the_body_on_the_other_end():
    """Contacts wake what they hit; joints had no equivalent. A chain that
    settled and fell asleep stayed asleep when its anchor moved off - its
    constraints were still solved, but a sleeping body is never integrated, so
    the solved velocity was discarded every step and the joint stretched to
    any length at all."""
    scene, bodies = _chain()
    anchor = bodies[0]

    _advance(scene, 60)
    for body in bodies[1:]:
        body.is_sleeping = True

    anchor.linear_velocity = Vector(60, 0)
    _advance(scene, 1)

    assert not any(body.is_sleeping for body in bodies[1:]), (
        'the wake has to travel the whole chain, not just the link the anchor '
        'is joined to')


def test_a_dragged_chain_keeps_its_length():
    """Dragging the anchor at a steady speed used to pull the chain apart a
    little further every step, because positional drift was only fed back as a
    velocity bias capped at MAX_JOINT_BIAS_SPEED - so a joint dragged faster
    than that separated faster than the bias could close it, with nothing to
    stop it. A three-link chain pulled at a walking pace reached several times
    its real length."""
    scene, bodies = _chain()
    anchor = bodies[0]

    for _ in range(120):
        anchor.linear_velocity = Vector(75, 0)
        world.step(scene, STEP)

    for gap in _gaps(bodies):
        assert gap == pytest.approx(LINK_SPACING, abs=0.25)


def test_a_hanging_chain_holds_its_length():
    """The baseline the drag test is measured against: left alone, the chain
    hangs straight down at exactly its built length."""
    scene, bodies = _chain()
    _advance(scene, 60)

    for gap in _gaps(bodies):
        assert gap == pytest.approx(LINK_SPACING, abs=0.05)
    assert bodies[-1].world_position.y == pytest.approx(-LINK_SPACING * 3, abs=0.1)


def test_an_arcade_body_does_not_collide_with_a_rigid_body():
    """The two physics systems are documented as not interacting, and a
    RigidBody2D does only ever see other RigidBody2Ds - but the arcade side
    collected every Collider2D in the scene regardless of what owned it, so
    the separation only held one way. An arcade PhysicsBody walking into a
    rigid body's collider was pushed back out of it while the rigid body felt
    nothing, which is a lantern on a chain shoving its own owner around.
    """
    from FreeBodyEngine.core.physics import PhysicsBody

    root = RootNode(scene=None)
    rigid = _body(root, Vector(0, 0))
    assert rigid.collider.rigid_body is rigid, 'the body claims its collider'

    walker = PhysicsBody(position=Vector(0, 0))
    walker.add(CircleCollider2D())
    root.add(walker)

    # exactly what Scene._physics_process hands the arcade narrow phase
    colliders = []
    for collider in root.find_nodes_with_type('Collider2D'):
        collider.apply_transform()
        if collider.rigid_body is not None:
            continue
        aabb_min, aabb_max = collider.collision_shape.get_aabb()
        colliders.append((collider, aabb_min, aabb_max))

    before = walker.transform.position.copy()
    walker._check_collisions(colliders)

    assert walker.transform.position.x == pytest.approx(before.x)
    assert walker.transform.position.y == pytest.approx(before.y)
