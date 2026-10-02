"""Tests for PhysicsBody's force integration.

`friction` used to be applied as `vel *= friction * dt`, which at 60Hz
multiplied velocity by 0.0163 for the default friction of 0.98 - and by
0.0167 even for friction=1.0. Velocity was destroyed within a step or two
whatever the value, so nothing could be moved by setting `vel` at all.
"""
import pytest

import FreeBodyEngine.core.physics as physics_module
from FreeBodyEngine.core.physics import PhysicsBody
from FreeBodyEngine.math import Vector


STEP = 1 / 60


@pytest.fixture
def fixed_step(monkeypatch):
    """Pins the physics timestep, which otherwise needs a live Main."""
    monkeypatch.setattr(physics_module, 'physics_delta', lambda: STEP)


def _advance(body, seconds):
    for _ in range(round(seconds / STEP)):
        body._integrate_forces()


def test_friction_of_one_leaves_speed_untouched(fixed_step):
    body = PhysicsBody(velocity=Vector(10, 0), friction=1.0)
    _advance(body, 1.0)
    assert body.vel.x == pytest.approx(10.0)


def test_friction_is_the_fraction_kept_per_second(fixed_step):
    for friction, expected in ((0.98, 9.8), (0.5, 5.0), (0.25, 2.5)):
        body = PhysicsBody(velocity=Vector(10, 0), friction=friction)
        _advance(body, 1.0)
        assert body.vel.x == pytest.approx(expected, rel=1e-6)


def test_damping_is_framerate_independent(monkeypatch):
    """The whole point of raising friction to the step length: halving the
    timestep must not change how much speed is lost over the same period."""
    results = []
    for step in (1 / 30, 1 / 60, 1 / 240):
        monkeypatch.setattr(physics_module, 'physics_delta', lambda s=step: s)
        body = PhysicsBody(velocity=Vector(10, 0), friction=0.5)
        for _ in range(round(1.0 / step)):
            body._integrate_forces()
        results.append(body.vel.x)
    for value in results:
        assert value == pytest.approx(5.0, rel=1e-6)


def test_a_body_with_velocity_actually_moves(fixed_step):
    """The symptom that mattered: setting vel moved a body essentially not at
    all, because the damping had already zeroed it."""
    body = PhysicsBody(velocity=Vector(6, 0), friction=1.0)
    _advance(body, 1.0)
    assert body.transform.position.x == pytest.approx(6.0, rel=1e-3)


def test_applied_force_accelerates_by_mass(fixed_step):
    body = PhysicsBody(friction=1.0, mass=2)
    for _ in range(round(1.0 / STEP)):
        body.apply_force(Vector(4, 0))
        body._integrate_forces()
    # a = F/m = 2 units/s^2, so after 1s the speed is about 2
    assert body.vel.x == pytest.approx(2.0, rel=1e-2)


def test_forces_are_cleared_each_step(fixed_step):
    body = PhysicsBody(friction=1.0)
    body.apply_force(Vector(10, 0))
    body._integrate_forces()
    speed_after_one = body.vel.x
    body._integrate_forces()
    assert body.vel.x == pytest.approx(speed_after_one)


def test_rotational_velocity_decays_the_same_way(fixed_step):
    body = PhysicsBody(rotational_velocity=10.0, friction=0.5)
    _advance(body, 1.0)
    assert body.rot_vel == pytest.approx(5.0, rel=1e-6)


def test_friction_above_one_warns(fixed_step, capsys):
    """It makes a body accelerate with no force applied, which is almost
    certainly a mistake - FreeBodyDev passes friction=4."""
    PhysicsBody(friction=4.0)
    assert 'friction' in capsys.readouterr().out.lower()
