"""Tests for the rigid-body world's handling of plain colliders, CHARACTER
bodies and per-scene gravity.

Rigid bodies only ever saw other rigid bodies: a plain Collider2D - a wall, a
tilemap's collision - was not there for them. There was no body that moved
the way the arcade PhysicsBody does (set a velocity, slide along walls), and
gravity was one fixed constant for every scene.
"""
import pytest

import FreeBodyEngine as fb
from FreeBodyEngine.core.physics import world
from FreeBodyEngine.core.physics.body import BodyType, RigidBody2D
from FreeBodyEngine.math import Vector

STEP = 1 / 60


def _scene(gravity=Vector(0, -9.8)):
    scene = fb.Scene('test')
    scene.gravity = gravity
    return scene


def _box(scene, position, size=Vector(1, 1), body_type=BodyType.DYNAMIC, **kwargs):
    body = RigidBody2D(position=position, body_type=body_type, fixed_rotation=True, **kwargs)
    body.add(fb.RectangleCollider2D(scale=size))
    scene.add(body)
    return body


def _wall(scene, position, size):
    wall = fb.RectangleCollider2D(position=position, scale=size)
    scene.add(wall)
    return wall


def _advance(scene, seconds):
    for _ in range(round(seconds / STEP)):
        world.step(scene, STEP)


def test_a_dynamic_body_lands_on_a_plain_collider():
    scene = _scene()
    _wall(scene, Vector(0, 0), Vector(20, 1))
    box = _box(scene, Vector(0, 3))
    _advance(scene, 3.0)
    assert box.transform.position.y == pytest.approx(1.0, abs=0.05)


def test_collision_with_a_plain_collider_is_entered_once():
    entered = []

    class Box(RigidBody2D):
        def on_collision_enter(self, other, contact):
            entered.append(other)

    scene = _scene()
    floor = _wall(scene, Vector(0, 0), Vector(20, 1))
    box = Box(position=Vector(0, 3), fixed_rotation=True)
    box.add(fb.RectangleCollider2D())
    scene.add(box)
    _advance(scene, 3.0)
    assert len(entered) == 1
    assert entered[0].collider is floor


def test_a_sensor_collider_does_not_block():
    scene = _scene()
    zone = _wall(scene, Vector(0, 0), Vector(20, 1))
    zone.is_sensor = True
    box = _box(scene, Vector(0, 3))
    _advance(scene, 2.0)
    assert box.transform.position.y < -1


def test_scene_gravity():
    still = _scene(Vector(0, 0))
    box = _box(still, Vector(0, 0))
    _advance(still, 1.0)
    assert box.transform.position.y == 0

    sideways = _scene(Vector(5, 0))
    box = _box(sideways, Vector(0, 0))
    _advance(sideways, 1.0)
    assert box.transform.position.x > 1


def test_character_stops_at_a_wall_and_slides_along_it():
    scene = _scene(Vector(0, 0))
    _wall(scene, Vector(3, 0), Vector(1, 20))
    player = _box(scene, Vector(0, 0), body_type=BodyType.CHARACTER)
    for _ in range(120):
        player.linear_velocity = Vector(4, 2)      # into the wall, and along it
        world.step(scene, STEP)
    assert player.transform.position.x == pytest.approx(2.0, abs=0.02)
    assert player.transform.position.y == pytest.approx(4.0, abs=0.1)
    assert player.on_wall and not player.on_floor


def test_character_lands_and_knows_it_is_on_the_floor():
    scene = _scene()
    _wall(scene, Vector(0, 0), Vector(20, 1))
    player = _box(scene, Vector(0, 3), body_type=BodyType.CHARACTER)
    _advance(scene, 3.0)
    assert player.transform.position.y == pytest.approx(1.0, abs=0.02)
    assert player.on_floor


def test_character_pushes_a_dynamic_body():
    scene = _scene(Vector(0, 0))
    crate = _box(scene, Vector(1.5, 0))
    player = _box(scene, Vector(0, 0), body_type=BodyType.CHARACTER)
    for _ in range(60):
        player.linear_velocity = Vector(2, 0)
        world.step(scene, STEP)
    assert crate.transform.position.x > 2.5
    assert player.transform.position.x == pytest.approx(2.0, abs=0.05)
