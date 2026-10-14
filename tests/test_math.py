"""Regression tests for FreeBodyEngine.math's 2D transform/vector logic.

These lock in the rotation-direction and matrix-order fixes from the
Transform.model and Vector.rotated bugs (see git history around
07ef82f/eb48078) - both were silent (no exception, no shader error), only
visible by actually rendering a rotated, offset node.
"""
import numpy
import pytest

from FreeBodyEngine.math import Transform, Vector


def _apply(transform: Transform, point: Vector) -> tuple:
    """Applies `transform.model` to a homogeneous point, row-vector
    convention (`point @ model`), and returns the resulting (x, y)."""
    row = numpy.array([point.x, point.y, 0, 1], dtype=float)
    result = row @ transform.model
    return result[0], result[1]


def test_vector_rotated_is_counter_clockwise():
    v = Vector(1, 0).rotated(90)
    assert v.x == pytest.approx(0, abs=1e-9)
    assert v.y == pytest.approx(1, abs=1e-9)


def test_transform_model_rotates_counter_clockwise():
    t = Transform((0, 0), 90, (1, 1))
    x, y = _apply(t, Vector(1, 0))
    assert x == pytest.approx(0, abs=1e-9)
    assert y == pytest.approx(1, abs=1e-9)


def test_transform_model_translation_is_not_rotated_or_scaled():
    # A rotated, scaled transform's own position must land exactly where
    # it says, regardless of its rotation/scale - those apply to the
    # transform's *content*, not to its own translation offset.
    t = Transform((5, 3), 90, (2, 2))
    x, y = _apply(t, Vector(0, 0))
    assert x == pytest.approx(5, abs=1e-9)
    assert y == pytest.approx(3, abs=1e-9)


def test_transform_compose_with_rotated_parent():
    # A child offset (1, 0) under a parent at (10, 0) rotated 90 degrees
    # should land at (10, 1) in world space: the offset gets rotated by
    # the parent's rotation, then added to the parent's position.
    parent = Transform((10, 0), 90, (1, 1))
    child = Transform((1, 0), 0, (1, 1))
    world = child.compose_with(parent)

    assert world.position.x == pytest.approx(10, abs=1e-9)
    assert world.position.y == pytest.approx(1, abs=1e-9)
    assert world.rotation == pytest.approx(90, abs=1e-9)


def test_from_matrix_preserves_a_mirrored_scale():
    """A negative scale on one axis is how a sprite gets flipped, and
    from_matrix extracted scale with hypot - which is never negative. The
    mirror survived being set and was then thrown away the moment the
    transform was composed with its parent's, so a flipped sprite drew
    unflipped and nothing anywhere reported a problem.
    """
    from FreeBodyEngine.math import Transform

    mirrored = Transform((3, 4), 30.0, (9, -6))
    roundtripped = Transform.from_matrix(mirrored.to_matrix())

    assert roundtripped.scale.y < 0
    assert numpy.allclose(roundtripped.to_matrix(), mirrored.to_matrix())


def test_composing_a_mirrored_child_keeps_the_mirror():
    """The composition path is where this actually bit."""
    from FreeBodyEngine.math import Transform

    parent = Transform((10, 0), 0.0, (1, 1))
    child = Transform((0, 0), 180.0, (9, -6))

    composed = child.compose_with(parent)

    assert composed.scale.y < 0
    assert numpy.allclose(composed.to_matrix(), parent.to_matrix() @ child.to_matrix())


def test_an_unmirrored_transform_is_untouched():
    from FreeBodyEngine.math import Transform

    plain = Transform((1, 2), 45.0, (3, 4))
    roundtripped = Transform.from_matrix(plain.to_matrix())

    assert roundtripped.scale.x == pytest.approx(3)
    assert roundtripped.scale.y == pytest.approx(4)
    assert roundtripped.rotation == pytest.approx(45)
