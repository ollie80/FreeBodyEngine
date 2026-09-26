"""Tests for Node2D's world_transform composition, built directly on a
RootNode/Node2D tree (no Main/window/renderer needed - the scene graph is
pure data)."""
import pytest

from FreeBodyEngine.core.node import RootNode, Node2D
from FreeBodyEngine.math import Vector


def test_world_transform_falls_back_to_local_under_root():
    root = RootNode(scene=None)
    child = Node2D(position=Vector(3, 4), rotation=45)
    root.add(child)

    assert child.world_transform.position.x == pytest.approx(3)
    assert child.world_transform.position.y == pytest.approx(4)
    assert child.world_transform.rotation == pytest.approx(45)


def test_world_transform_composes_through_rotated_parent():
    root = RootNode(scene=None)
    parent = Node2D(position=Vector(10, 0), rotation=90)
    root.add(parent)

    child = Node2D(position=Vector(1, 0))
    parent.add(child)

    assert child.world_position.x == pytest.approx(10, abs=1e-9)
    assert child.world_position.y == pytest.approx(1, abs=1e-9)
    assert child.world_rotation == pytest.approx(90, abs=1e-9)
