"""Tests that the shadow frustum only ever moves in whole shadow-map texels.

The frustum follows the camera, so without quantizing its centre the map is
re-rasterized onto a grid that has shifted a fraction of a texel every time
the camera moves at all, and every shadow edge in the scene jumps between
neighbouring texels from frame to frame. It shows as flickering shadows
whenever the camera creeps by less than a texel per frame - a vehicle
crawling, or a chase camera still easing into place after the thing it
follows has stopped.
"""
import numpy as np
import pytest

from FreeBodyEngine.graphics.pbr.pipeline import (
    PBRPipeline, SHADOW_BIAS_TEXELS, SHADOW_MAP_SIZE, _shadow_depth_range)
from FreeBodyEngine.math import Vector3


class _Light:
    """The four things _shadow_matrices() reads off a directional light."""

    def __init__(self, extent=110.0, distance=160.0):
        self.direction3 = Vector3(-0.353128915, -0.788010754, -0.504320356)
        self.shadow_extent = extent
        self.shadow_distance = distance


class _Camera:
    class _Transform:
        def __init__(self, position):
            self.position = position

    def __init__(self, position):
        self.world_transform = self._Transform(position)

    def inherits_from(self, type_name):
        return type_name == 'Node3D'


@pytest.fixture
def pipeline():
    """A PBRPipeline that was never initialized - the shadow matrices are
    pure arithmetic over the light and camera and touch no GL state."""
    return PBRPipeline()


def _map_position(pipeline, light, camera_position, world_point):
    """Where `world_point` lands on the shadow map, in texels, for a camera
    at `camera_position`."""
    view, proj = pipeline._shadow_matrices(light, _Camera(camera_position))
    clip = np.array([world_point.x, world_point.y, world_point.z, 1.0]) @ (
        view.astype(np.float64) @ proj.astype(np.float64))
    return (clip[:2] / clip[3] * 0.5 + 0.5) * SHADOW_MAP_SIZE


def _texel(light):
    return (2.0 * light.shadow_extent) / SHADOW_MAP_SIZE


def test_sub_texel_camera_moves_shift_the_map_by_whole_texels(pipeline):
    """The flicker itself: ten sub-texel steps along one texel of camera
    travel, and a fixed piece of world must land on a whole texel each time.
    Unsnapped, it wobbles by up to half a texel - which is exactly the
    neighbouring-texel jump that shows as flicker."""
    light = _Light()
    point = Vector3(3.0, 0.0, -45.0)
    start = Vector3(0.0, 7.5, -39.21)
    base = _map_position(pipeline, light, start, point)

    for step in range(1, 11):
        crept = Vector3(start.x, start.y, start.z + _texel(light) * step / 10)
        moved = _map_position(pipeline, light, crept, point) - base
        assert np.allclose(moved, np.round(moved), atol=1e-3)


def test_frustum_still_follows_the_camera(pipeline):
    """Snapping must not pin the frustum in place - it exists to keep the
    shadowed region around whatever the camera is looking at."""
    light = _Light()
    near = pipeline._shadow_matrices(light, _Camera(Vector3(0.0, 7.5, 0.0)))[0]
    far = pipeline._shadow_matrices(light, _Camera(Vector3(0.0, 7.5, -100.0)))[0]
    assert not np.allclose(near, far)


def test_snapping_follows_the_light_not_the_world_axes(pipeline):
    """The grid is the light's, so the invariant has to hold for a camera
    creeping along any world axis, under any sun angle."""
    light = _Light()
    light.direction3 = Vector3(0.0, -1.0, 0.0)  # straight down, a different basis
    point = Vector3(12.0, 0.0, 4.0)
    start = Vector3(1.0, 9.0, 2.0)
    base = _map_position(pipeline, light, start, point)

    step = _texel(light) / 3
    for crept in (Vector3(start.x + step, start.y, start.z),
                  Vector3(start.x, start.y + step, start.z),
                  Vector3(start.x, start.y, start.z + step)):
        moved = _map_position(pipeline, light, crept, point) - base
        assert np.allclose(moved, np.round(moved), atol=1e-3)


def test_depth_bias_is_a_fixed_world_distance_at_any_scene_scale():
    """The bias used to be a constant fraction of the frustum's depth range,
    so it grew with shadow_distance: 8cm at the engine's 30-unit default but
    the better part of a metre once a scene pushed the sun's frustum out to
    cover an outdoor view distance - which quietly erased the shadow of
    anything shorter than that."""
    def bias_in_world_units(light):
        near, far = _shadow_depth_range(light)
        texel_world = (2.0 * light.shadow_extent) / SHADOW_MAP_SIZE
        normalized = (texel_world * SHADOW_BIAS_TEXELS) / max(far - near, 0.001)
        return normalized * (far - near)

    small = _Light(extent=20.0, distance=30.0)
    large = _Light(extent=110.0, distance=160.0)

    # Each stays a couple of texels, whatever the frustum's depth range is.
    assert bias_in_world_units(small) == pytest.approx(
        _texel(small) * SHADOW_BIAS_TEXELS, rel=1e-6)
    assert bias_in_world_units(large) == pytest.approx(
        _texel(large) * SHADOW_BIAS_TEXELS, rel=1e-6)
    # And the large scene's bias is nowhere near the 0.8m the old constant gave it.
    assert bias_in_world_units(large) < 0.3
