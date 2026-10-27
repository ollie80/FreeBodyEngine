"""Tests for sprite batching (graphics/instancing.py).

Every sprite used to be its own draw call - shader bind, property and matrix
uploads and a draw, all from Python - so a screen of a few hundred sprites
cost tens of milliseconds a frame. Sprites that draw with the same thing are
now grouped into one instanced draw; these pin down what may be grouped,
in what order things are drawn, and that the per-instance data matches what
each sprite's own model matrix was.

No GL context here: calls carry stand-in materials, and the renderer only
records what it would draw.
"""
import numpy as np
import pytest

from FreeBodyEngine.graphics.instancing import instance_data, runs, sort_transparent
from FreeBodyEngine.graphics.material import BlendMode, Material
from FreeBodyEngine.graphics.renderer import Call, Renderer
from FreeBodyEngine.graphics.texture import Texture
from FreeBodyEngine.math import Transform, Vector


class _Material:
    """Just what batching asks of a material."""
    def __init__(self, look, instanced=True, blend=BlendMode.TRANSPARENT):
        self.look = look
        self.blend_mode = blend
        self._shader = object() if instanced else None

    def instanced_shader(self):
        return self._shader

    def batch_key(self):
        return (self.look,)


class _Camera:
    def __init__(self):
        self.world_transform = Transform(Vector(0, 0), 0, Vector(1, 1))


MESH = object()
CAMERA = _Camera()
SHADERS = {}


def _call(look, x=0.0, z=0.0, instanced=True, rotation=0.0, scale=(1, 1)):
    material = _Material(look, instanced)
    if instanced:
        # One shader per look, as instances of one material share theirs.
        material._shader = SHADERS.setdefault(look, object())
    return Call(MESH, Transform(Vector(x, 0), rotation, Vector(*scale)), material, CAMERA, z)


# -- what's drawn per instance ----------------------------------------------------

@pytest.mark.parametrize('rotation, scale', [(0, (1, 1)), (90, (2, 3)), (-37.5, (-1, 1)), (200, (0.5, -2))])
def test_instance_data_is_each_sprites_own_model_matrix_and_z(rotation, scale):
    calls = [_call('belt', x=3.25, z=-0.004, rotation=rotation, scale=scale),
             _call('belt', x=-7, z=0.5, rotation=rotation + 10, scale=scale)]
    calls[1].transform.position.y = 11
    data = instance_data(calls)
    assert data.dtype == np.float32 and data.shape == (2, 17)
    for row, call in zip(data, calls):
        np.testing.assert_allclose(row[:16], call.transform.model.reshape(16), atol=1e-5)
        assert row[16] == pytest.approx(call.z)


# -- ordering --------------------------------------------------------------------------

def test_transparent_draws_stay_back_to_front_by_z():
    calls = [_call('a', z=-0.003), _call('b', z=0.0), _call('a', z=-0.001), _call('c', z=0.002)]
    assert [c.z for c in sort_transparent(calls)] == [0.002, 0.0, -0.001, -0.003]


def test_within_a_z_the_same_look_draws_together_farthest_first():
    calls = [_call('belt', x=1), _call('drill', x=9), _call('belt', x=5), _call('drill', x=2), _call('belt', x=3)]
    ordered = sort_transparent(calls)
    looks = [c.material.look for c in ordered]
    assert looks in (['belt'] * 3 + ['drill'] * 2, ['drill'] * 2 + ['belt'] * 3)
    belts = [c.transform.position.x for c in ordered if c.material.look == 'belt']
    assert belts == [5, 3, 1]


def test_runs_break_where_the_look_changes_and_uninstanced_draws_go_alone():
    calls = [_call('a'), _call('a'), _call('b'), _call('x', instanced=False), _call('x', instanced=False), _call('a')]
    assert [len(run) for run in runs(calls)] == [2, 1, 1, 1, 1]


# -- the renderer --------------------------------------------------------------------

class _Recorder(Renderer):
    """A renderer that only writes down what it would draw."""
    def __init__(self):
        self.calls = []
        self.drawn = []
        self._current_blend_mode = None

    def _draw_call(self, call):
        self.drawn.append(('one', call.material.look))

    def draw_calls_instanced(self, calls):
        self.drawn.append(('instanced', calls[0].material.look, len(calls)))

    def set_blend_mode(self, mode):
        pass


def test_a_screen_of_sprites_is_one_draw_per_look():
    renderer = _Recorder()
    renderer.calls = [_call(look, x=i, z=-0.002) for i, look in enumerate(['belt', 'item', 'belt', 'item', 'belt'])]
    renderer.calls.append(_call('player', z=-0.01))
    renderer.flush_transparent()
    assert sorted(renderer.drawn) == [('instanced', 'belt', 3), ('instanced', 'item', 2), ('one', 'player')]
    assert renderer.calls == []


def test_opaque_draws_group_across_the_whole_queue():
    renderer = _Recorder()
    renderer.calls = [Call(MESH, Transform(Vector(i, 0), 0, Vector(1, 1)), _Material(look, blend=BlendMode.OPAQUE), CAMERA)
                      for i, look in enumerate(['wall', 'floor', 'wall', 'floor'])]
    for call in renderer.calls:
        call.material._shader = SHADERS.setdefault(call.material.look, object())
    renderer.flush_opaque()
    assert renderer.drawn == [('instanced', 'wall', 2), ('instanced', 'floor', 2)]


# -- materials ---------------------------------------------------------------------------

def _material(**properties):
    material = object.__new__(Material)
    object.__setattr__(material, 'data', {})
    object.__setattr__(material, 'properties', dict(properties))
    object.__setattr__(material, 'blend_mode', BlendMode.TRANSPARENT)
    object.__setattr__(material, 'pixel_filter', False)
    return material


def _texture():
    return object.__new__(Texture)


def test_instances_drawing_the_same_texture_batch_together():
    belt, drill = _texture(), _texture()
    base = _material(albedo=belt)
    assert base.instance().batch_key() == base.instance().batch_key()
    other = base.instance()
    other.properties['albedo'] = drill
    assert other.batch_key() != base.batch_key()


def test_blend_mode_and_filtering_split_batches():
    texture = _texture()
    a, b, c = _material(albedo=texture), _material(albedo=texture), _material(albedo=texture)
    object.__setattr__(b, 'blend_mode', BlendMode.OPAQUE)
    object.__setattr__(c, 'pixel_filter', True)
    assert len({a.batch_key(), b.batch_key(), c.batch_key()}) == 3


def test_a_plain_material_has_no_instanced_shader():
    assert _material().instanced_shader() is None


def test_a_lite_material_with_its_own_shader_isnt_instanced():
    from FreeBodyEngine.graphics.lite.material import LiteMaterial
    material = object.__new__(LiteMaterial)
    object.__setattr__(material, 'properties', {})
    object.__setattr__(material, '_vert_source_path', 'shaders/wobble.fbvert')
    object.__setattr__(material, '_frag_source_path', 'engine://shader/lite/surface.fbfrag')
    object.__setattr__(material, '_geom_source_path', None)
    assert material.instanced_shader() is None


# -- the model matrix ----------------------------------------------------------------------

def test_a_transforms_model_is_kept_until_it_changes():
    t = Transform(Vector(1, 2), 30, Vector(2, 2))
    first = t.model
    assert t.model is first
    t.rotation = 45
    assert t.model is not first
    np.testing.assert_allclose(t.model, Transform(Vector(1, 2), 45, Vector(2, 2)).model)


def test_the_kept_model_cant_be_changed_in_place():
    t = Transform(Vector(1, 2), 30, Vector(2, 2))
    with pytest.raises(ValueError):
        t.model[3, 0] = 99
