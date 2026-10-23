"""Tests for Scene.remove() and cast_ray().

Scene.remove() passed its whole `*ids` tuple on as one id, so it never
removed anything. cast_ray() could not work at all: it asked Main for an
attribute it does not have, only cast when no scene was passed, and ignored
`max_distance`.
"""
from FreeBodyEngine.core.collider import RectangleCollider2D, cast_ray
from FreeBodyEngine.core.node import Node
from FreeBodyEngine.core.scene import Scene
from FreeBodyEngine.math import Vector


def test_remove_removes_one():
    scene = Scene('test')
    node = Node()
    scene.add(node)
    scene.remove(node.id)
    assert node.id not in scene.root.children


def test_remove_removes_several():
    scene = Scene('test')
    a, b, keep = Node(), Node(), Node()
    scene.add(a, b, keep)
    scene.remove(a.id, b.id)
    assert list(scene.root.children) == [keep.id]


def _scene_with_wall(x):
    scene = Scene('test')
    wall = RectangleCollider2D(position=Vector(x, 0), scale=Vector(2, 2))
    scene.add(wall)
    wall.apply_transform()
    return scene


def test_cast_ray_in_a_given_scene_hits():
    hit = cast_ray(Vector(0, 0), Vector(1, 0), 50, _scene_with_wall(10))
    assert hit is not None
    assert hit.x == __import__('pytest').approx(9.0, abs=1e-3)


def test_cast_ray_respects_max_distance():
    assert cast_ray(Vector(0, 0), Vector(1, 0), 5, _scene_with_wall(10)) is None
