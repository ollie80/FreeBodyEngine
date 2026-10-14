"""Tests for a sprite's `z`, the depth nudge that controls 2D layering.

Three separate defects used to make `z` a no-op for the sprites that most
need it - every transparent, alpha cut-out sprite in a 2D game:

  * `Sprite2D.__init__` assigned `self._sprite.z = z` unconditionally from a
    default of 0, so wrapping a loaded sprite discarded whatever z its
    `.fbspr` declared.
  * `AnimatedSprite2D` built its Sprite with the caller's `z` and then let
    that same line overwrite it, so an animated sprite's z never survived
    construction at all.
  * `Renderer.flush_transparent` sorted purely on `camera_distance()`, which
    squares its z term - burying a ~1e-2 nudge under an x/y term measured in
    world units, and discarding z's sign along the way.

The draw-order tests below drive the real `flush_transparent` rather than
re-implementing its sort, which is the only version of this that would have
caught the third defect.
"""
import pytest

from FreeBodyEngine.graphics.material import BlendMode
from FreeBodyEngine.graphics.renderer import Renderer
from FreeBodyEngine.graphics.animation import Animation, AnimationFrame, AnimationSet
from FreeBodyEngine.graphics.sprite import AnimatedSprite2D, Sprite, Sprite2D
from FreeBodyEngine.math import Transform, Vector


class _Shader(dict):
    """`_draw_call` sets uniforms by item assignment; a dict is enough."""


class _Material:
    """A transparent-blend material, named so a recorded draw is identifiable."""
    def __init__(self, name):
        self.name = name
        self.blend_mode = BlendMode.TRANSPARENT
        self.shader = _Shader()


class _Camera:
    """Just enough camera for camera_distance() and `_draw_call`'s uniforms."""
    view_matrix = None
    proj_matrix = None

    class _T:
        position = Vector(0, 0)
    world_transform = _T()


class _RecordingRenderer(Renderer):
    """Records the order flush_transparent() issues draws in.

    Built via `object.__new__` to skip `Renderer.__init__`, which registers
    itself as the 'renderer' service and needs a live Main.
    """
    @classmethod
    def make(cls):
        r = object.__new__(cls)
        r.calls = []
        r._current_blend_mode = None
        r.drawn = []
        return r

    def draw_mesh(self, mesh, material):
        self.drawn.append(material.name)

    def set_blend_mode(self, mode):
        self._current_blend_mode = mode

    # Unused abstract surface - flush_transparent touches none of it.
    def load_image(self, data): pass
    def load_material(self, data): pass
    def load_shader(self, vertex, fragment, injector=None): pass
    def create_framebuffer(self, width, height, attachments): pass
    def clear(self, color): pass
    def destroy(self): pass
    def resize(self): pass
    def draw_line(self, start, end, width, color): pass
    def draw_mesh_instanced(self, mesh, material, model_matrices, camera): pass
    def draw_circle(self, radius, position, color): pass
    def get_mesh_class(self): pass
    def get_image_class(self): pass
    def get_material_class(self): pass
    def get_shader_class(self): pass
    def get_framebuffer_class(self): pass
    def get_texture_class(self): pass


def _draw_order(layers):
    """Submits one transparent sprite per (name, position, z) through the real
    renderer and returns the names in the order they were drawn - back to
    front, so the last name is the one that ends up on top."""
    renderer = _RecordingRenderer.make()
    camera = _Camera()
    for name, position, z in layers:
        renderer.submit(None, _Material(name), Transform(position, 0.0, Vector(1, 1)), camera, z)
    renderer.flush_transparent()
    return renderer.drawn


def _sprite(z=0.0):
    """A Sprite with a given z, bypassing __init__ - constructing one for
    real needs a renderer, a texture and a material."""
    s = object.__new__(Sprite)
    s.z = z
    return s


# -- z surviving construction ---------------------------------------------

def test_sprite2d_keeps_the_sprites_own_z_when_not_given_one():
    assert Sprite2D(_sprite(z=-0.0096))._sprite.z == -0.0096


def test_sprite2d_z_argument_overrides_the_sprites_own():
    assert Sprite2D(_sprite(z=-0.0096), z=-0.0008)._sprite.z == -0.0008


def test_sprite2d_accepts_an_explicit_zero():
    """Distinct from "no z given" - 0.0 must still clear a declared z."""
    assert Sprite2D(_sprite(z=-0.0096), z=0.0)._sprite.z == 0.0


def _animation_set():
    """A one-frame, one-animation set - enough to build an AnimatedSprite2D."""
    frame = AnimationFrame(texture=object(), duration=1.0)
    return AnimationSet({'idle': Animation(name='idle', frames=[frame])})


class _InstancingMaterial(_Material):
    """AnimatedSprite2D's Sprite takes a per-object copy via instance()."""
    def __init__(self, name='anim'):
        super().__init__(name)
        self.properties = {}

    def instance(self):
        copy = _InstancingMaterial(self.name)
        copy.properties = dict(self.properties)
        return copy


@pytest.fixture
def stub_quad(monkeypatch):
    """Sprite.__init__ builds its quad via generate_quad(), which reaches for
    the live renderer service through create_static_mesh(). The mesh has
    nothing to do with z."""
    monkeypatch.setattr('FreeBodyEngine.graphics.sprite.generate_quad',
                        lambda *a, **k: object())


def test_animated_sprite2d_keeps_its_z(stub_quad):
    """The player and its weapon are both AnimatedSprite2Ds; this used to
    construct the Sprite with `z` and then have Sprite2D reset it to 0."""
    node = AnimatedSprite2D(_animation_set(), _InstancingMaterial(),
                            _RecordingRenderer.make(), z=-0.008)
    assert node._sprite.z == -0.008


def test_animated_sprite2d_defaults_to_no_nudge(stub_quad):
    node = AnimatedSprite2D(_animation_set(), _InstancingMaterial(),
                            _RecordingRenderer.make())
    assert node._sprite.z == 0


# -- transparent draw order ------------------------------------------------

def test_more_negative_z_draws_on_top_at_equal_positions():
    order = _draw_order([('back', Vector(0, 0), 0.0),
                         ('front', Vector(0, 0), -0.008)])
    assert order[-1] == 'front'


def test_z_outranks_distance_from_the_camera():
    """The player sits at the camera centre under a follow cam while its
    hands orbit it; the hands' higher layer has to win anyway."""
    order = _draw_order([('player', Vector(0, 0), -0.0080),
                         ('hand', Vector(10, 0), -0.0096)])
    assert order[-1] == 'hand'


def test_equal_z_still_resolves_farthest_first():
    order = _draw_order([('near', Vector(1, 0), -0.008),
                         ('far', Vector(50, 0), -0.008)])
    assert order == ['far', 'near']


def test_layer_stack_draws_back_to_front():
    step = 0.0008
    order = _draw_order([('weapon', Vector(10, 0), -11 * step),
                         ('floor', Vector(0, 0), -0 * step),
                         ('hand', Vector(10, 0), -12 * step),
                         ('body', Vector(0, 0), -10 * step)])
    assert order == ['floor', 'body', 'weapon', 'hand']


def test_flush_transparent_dequeues_what_it_drew():
    renderer = _RecordingRenderer.make()
    renderer.submit(None, _Material('a'), Transform(Vector(0, 0), 0.0, Vector(1, 1)), _Camera(), -0.008)
    renderer.flush_transparent()
    assert renderer.calls == []
