"""Tests for which lights get the pipeline's MAX_LIGHTS uniform slots.

There are only MAX_LIGHTS slots and no array uniform behind them, so a scene
with more lights than slots has to choose. It used to choose by tree-walk
order and drop the rest silently, which meant the newest nodes always lost -
the ones attached to whatever the camera is following.
"""
import pytest

from FreeBodyEngine.core.node import RootNode
from FreeBodyEngine.graphics.color import Color
from FreeBodyEngine.graphics.lighting import PointLight2D, DirectionalLight2D
from FreeBodyEngine.graphics.pbr.pipeline import PBRPipeline
from FreeBodyEngine.graphics.pbr.shaders import MAX_LIGHTS
from FreeBodyEngine.math import Vector


class _Camera:
    """The two things _camera_view_pos() reads off a camera."""

    class _Transform:
        def __init__(self, position):
            self.position = position

    def __init__(self, position=Vector(0, 0)):
        self.world_transform = self._Transform(position)

    def inherits_from(self, type_name):
        return type_name == 'Node2D'


@pytest.fixture
def pipeline():
    """A PBRPipeline that was never initialized - light selection is pure
    arithmetic over the node list and touches no GL state."""
    return PBRPipeline()


# world_position composes through the parent chain, so a light has to be in a
# tree to have one at all.
_ROOT = RootNode(scene=None)


def _point(x, y, range=64.0):
    light = PointLight2D(position=Vector(x, y), range=range, color=Color('#FFFFFF'))
    _ROOT.add(light)
    return light


def test_a_light_at_the_camera_wins_over_distant_ones_added_first(pipeline):
    """The failure this was written for: a lantern carried by the player is
    the last light added to the scene, so in tree order it was always the one
    dropped - the one light that should never be."""
    far = [_point(1000 + i * 10, 0) for i in range(MAX_LIGHTS)]
    carried = _point(0, 0)

    chosen = pipeline._select_lights(far + [carried], _Camera())

    assert carried in chosen
    assert len(chosen) == MAX_LIGHTS


def test_selection_is_by_reach_not_raw_distance(pipeline):
    """A close light with a tiny range reaches the camera less than a further
    one with a large range, so when a slot has to be given up it is the close
    one that goes. Ordering within the chosen set carries no meaning - every
    active slot is summed - so this is asserted by what survives the cut."""
    near_but_tiny = _point(50, 0, range=1.0)
    further_but_wide = _point(80, 0, range=400.0)
    crowd = [_point(60 + i, 0, range=300.0) for i in range(MAX_LIGHTS - 1)]

    chosen = pipeline._select_lights([near_but_tiny] + crowd + [further_but_wide], _Camera())

    assert further_but_wide in chosen
    assert near_but_tiny not in chosen


def test_directional_lights_always_get_a_slot(pipeline):
    """A directional light has no position or range - it lights everything, so
    there is no distance at which dropping it is right."""
    sun = DirectionalLight2D()
    _ROOT.add(sun)
    crowd = [_point(i, 0) for i in range(MAX_LIGHTS * 2)]

    chosen = pipeline._select_lights(crowd + [sun], _Camera())

    assert sun in chosen


def test_a_disabled_light_takes_no_slot(pipeline):
    """`Light.enabled` existed but was never read anywhere, so switching a
    light off did nothing at all - and it still occupied one of the slots."""
    off = _point(0, 0)
    off.enabled = False
    on = _point(5, 0)

    chosen = pipeline._select_lights([off, on], _Camera())

    assert chosen == [on]


def test_every_light_is_kept_when_they_fit(pipeline):
    lights = [_point(i * 5, 0) for i in range(MAX_LIGHTS)]

    assert len(pipeline._select_lights(lights, _Camera())) == MAX_LIGHTS


def test_an_invisible_sprite_is_not_collected(pipeline):
    """`visible` was accepted by Sprite's constructor, stored under a
    misspelled name, and read by nothing - so hiding a sprite did nothing and
    the only way to hide something was to remove its node or scale it to zero
    (which raises, since a zero scale has no recoverable rotation)."""

    class _Node:
        """Just what _collect() touches on a node."""

        def __init__(self, type_name=None, visible=True):
            self.type_name = type_name
            self.children = {}
            if type_name == 'Sprite2D':
                self._sprite = type('_S', (), {'visible': visible})()

        def inherits_from(self, name):
            return name == self.type_name

    shown = _Node('Sprite2D', visible=True)
    hidden = _Node('Sprite2D', visible=False)
    root = _Node()
    root.children = {0: shown, 1: hidden}

    buckets = ([], [], [], [], [], [])
    pipeline._collect(root, *buckets)
    sprites = buckets[1]

    assert shown in sprites
    assert hidden not in sprites
