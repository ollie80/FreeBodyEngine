"""Tests that texture units are handed back between draws.

The PBR and Lite pipelines wrap their framebuffer attachments with
wrap_external_texture() every frame and draw them with shader.use() +
mesh.draw(), never through Renderer.draw_mesh(). Each wrap made a new id
and nothing reset the unit counter outside draw_mesh(), so within a couple
of seconds every unit was taken and every bind logged an error.

No GL context here: the managers and shader are built without __init__ and
the GL calls they make are replaced with stand-ins.
"""
import pytest

import FreeBodyEngine.graphics.gl33.shader as gl33_shader
import FreeBodyEngine.graphics.gl33.texture as gl33_texture
import FreeBodyEngine.graphics.gl44.texture as gl44_texture


def _manager(module, monkeypatch, units=16):
    monkeypatch.setattr(module, 'glActiveTexture', lambda unit: None)
    monkeypatch.setattr(module, 'glBindTexture', lambda target, texture: None)
    manager = object.__new__(module.GLTextureManager if module is gl33_texture
                             else module.GL44TextureManager)
    manager.standalone_textures = {}
    manager.atlas_textures = {}
    manager.texture_stacks = {}
    manager.texture_slots = {}
    manager.slot_textures = {}
    manager._external_ids = {}
    manager.next_texture_slot = 0
    manager.max_texture_slots = units
    return manager


@pytest.fixture(params=[gl33_texture, gl44_texture], ids=['gl33', 'gl44'])
def manager(request, monkeypatch):
    return _manager(request.param, monkeypatch)


def test_wrapping_the_same_texture_keeps_one_id(manager):
    ids = {manager.wrap_external_texture(7).id for _ in range(100)}

    assert len(ids) == 1
    assert len(manager.standalone_textures) == 1


def test_different_textures_get_different_ids(manager):
    assert manager.wrap_external_texture(7).id != manager.wrap_external_texture(8).id


def test_rewrapping_takes_no_new_unit(manager):
    for _ in range(100):
        assert manager.bind_texture(manager.wrap_external_texture(7).id) == 0

    assert manager.next_texture_slot == 1


def test_a_deleted_wrap_is_not_handed_out_again(manager, monkeypatch):
    monkeypatch.setattr(gl33_texture, 'glDeleteTextures', lambda names: None)
    monkeypatch.setattr(gl44_texture, 'glDeleteTextures', lambda names: None)
    first = manager.wrap_external_texture(7).id
    manager._delete_texture(first)

    second = manager.wrap_external_texture(7).id

    assert second != first
    assert manager.standalone_textures[second] == 7


def test_use_hands_units_back_without_draw_mesh(monkeypatch):
    """A pass that draws with use() + mesh.draw() directly, every frame,
    for far more frames than there are units."""
    manager = _manager(gl33_texture, monkeypatch, units=4)

    class _Renderer:
        texture_manager = manager

    class _Uniform:
        type = gl33_shader.GL_SAMPLER_2D
        size = 1
        location = 0

    monkeypatch.setattr(gl33_shader, 'get_service', lambda name: _Renderer)
    monkeypatch.setattr(gl33_shader, 'glUseProgram', lambda program: None)
    monkeypatch.setattr(gl33_shader, 'glUniform1i', lambda location, value: None)
    errors = []
    monkeypatch.setattr(gl33_texture, 'fb_error', errors.append)

    shader = object.__new__(gl33_shader.GLShader)
    shader._shader = 1
    shader.uniforms = {'Screen': _Uniform()}
    shader.uniform_cache = {}
    shader.emulation = None

    for frame in range(50):
        shader.uniform_cache['Screen'] = manager.wrap_external_texture(100 + frame % 3)
        shader.use()

    assert errors == []
    assert manager.next_texture_slot == 1
