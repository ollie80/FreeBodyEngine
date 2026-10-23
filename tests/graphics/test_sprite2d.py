"""Tests for Sprite2D taking a loaded sprite, animation set or image, and
playing animations itself.

Animated sprites used to be a separate class, AnimatedSprite2D, built from an
animation set, a material and the renderer passed in by hand; a plain image
needed a .fbspr and a .fbmat before it could be drawn at all.
"""
import pytest

import FreeBodyEngine.graphics.sprite as sprite_module
from FreeBodyEngine.graphics.animation import Animation, AnimationFrame, AnimationSet
from FreeBodyEngine.graphics.sprite import Sprite, Sprite2D
from FreeBodyEngine.graphics.texture import Texture

STEP = 0.1


class _Material:
    def __init__(self, name='default'):
        self.name = name
        self.properties = {}

    def instance(self):
        copy = _Material(self.name)
        copy.properties = dict(self.properties)
        return copy


def _texture(name):
    texture = object.__new__(Texture)
    texture.name = name
    return texture


@pytest.fixture(autouse=True)
def no_gpu(monkeypatch):
    """No renderer or pipeline here: a placeholder quad, a stand-in default
    material, and a fixed frame time."""
    monkeypatch.setattr(sprite_module, '_shared_quad', lambda: object())
    monkeypatch.setattr(sprite_module, 'default_sprite_material', lambda: _Material())
    monkeypatch.setattr(sprite_module, 'delta', lambda: STEP)


def _animations():
    frames = lambda prefix, n: [AnimationFrame(_texture(f'{prefix}{i}'), 0.1) for i in range(n)]
    return AnimationSet({
        'idle': Animation('idle', frames('idle', 2)),
        'die': Animation('die', frames('die', 3), loop=False),
    })


def _shown(node):
    return node.material.properties['albedo'].name


def test_an_image_becomes_a_sprite_with_the_default_material():
    rock = _texture('rock')
    node = Sprite2D(rock)
    assert node.texture is rock
    assert node.material.name == 'default'
    assert node.material.properties['albedo'] is rock
    assert node.animations == [] and node.animation is None


def test_a_material_can_be_given():
    node = Sprite2D(_texture('rock'), material=_Material('pixel'))
    assert node.material.name == 'pixel'


def test_an_animation_set_becomes_an_animated_sprite():
    node = Sprite2D(_animations())
    assert node.animations == ['idle', 'die']
    assert node.animation == 'idle' and _shown(node) == 'idle0'
    node.update()
    assert _shown(node) == 'idle1'
    node.update()
    assert _shown(node) == 'idle0'          # loops


def test_start_on_a_named_animation():
    assert _shown(Sprite2D(_animations(), animation='die')) == 'die0'


def test_play_switches_and_finished_reports_the_end():
    node = Sprite2D(_animations())
    node.play('die')
    assert _shown(node) == 'die0' and not node.finished
    for _ in range(3):
        node.update()
    assert _shown(node) == 'die2' and node.finished


def test_stop_pauses_and_speed_scales():
    node = Sprite2D(_animations())
    node.stop()
    node.update()
    assert _shown(node) == 'idle0'
    node.play()
    node.speed = 2.0
    node.update()                             # 0.2s: two frames on, back to idle0
    assert _shown(node) == 'idle0' and node.frame == 0


def test_animation_runs_even_if_on_update_is_overridden():
    class Player(Sprite2D):
        def on_update(self):
            pass                              # no super()

    node = Player(_animations())
    node.update()
    assert _shown(node) == 'idle1'


def test_a_loaded_sprite_carrying_animations_animates():
    sprite = Sprite.from_animations(_animations(), _Material('pixel'), z=0.5)
    node = Sprite2D(sprite)
    assert node.z == 0.5
    node.update()
    assert _shown(node) == 'idle1'


def test_public_properties():
    node = Sprite2D(_texture('rock'), z=0.25, visible=False)
    assert node.z == 0.25 and node.visible is False
    node.z, node.visible = 0.5, True
    assert node.sprite.z == 0.5 and node.sprite.visible is True
    gem = _texture('gem')
    node.texture = gem
    assert node.material.properties['albedo'] is gem


def test_flip_negates_the_draw_scale_only():
    node = Sprite2D(_texture('rock'), scale=__import__('FreeBodyEngine.math', fromlist=['Vector']).Vector(2, 3))
    node.flip_x = True
    assert tuple(node.draw_transform.scale) == (-2, 3)
    assert tuple(node.transform.scale) == (2, 3)
    node.flip_x, node.flip_y = False, True
    assert tuple(node.draw_transform.scale) == (2, -3)


def test_anything_else_is_a_clear_error():
    with pytest.raises(TypeError, match='load the file first'.lower().split()[0] if False else 'fb.load_file'):
        Sprite2D('graphics/rock.png')
