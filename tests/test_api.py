"""Tests for the top-level `FreeBodyEngine` namespace.

`from FreeBodyEngine import *` raised AttributeError: `__all__` listed five
loaders that did not exist, and a missing comma ran "audio" and "add"
together.
"""
import FreeBodyEngine as fb


def test_star_import_works():
    namespace = {}
    exec("from FreeBodyEngine import *", namespace)
    assert 'Sprite2D' in namespace and 'Scene' in namespace


def test_every_exported_name_exists():
    missing = [name for name in fb.__all__ if not hasattr(fb, name)]
    assert missing == []


def test_star_import_does_not_shadow_builtins():
    """`math` and `input` stay reachable as fb.math and fb.input, but a star
    import must not replace the standard library's `math` or `input()`."""
    assert 'math' not in fb.__all__ and 'input' not in fb.__all__
    assert fb.math.Vector is fb.Vector
    assert callable(fb.input.pressed)


def test_flat_names_are_the_real_classes():
    from FreeBodyEngine.graphics.sprite import Sprite2D
    from FreeBodyEngine.core.scene import Scene
    from FreeBodyEngine.core.collider import RectangleCollider2D
    assert fb.Sprite2D is Sprite2D
    assert fb.Scene is Scene
    assert fb.RectangleCollider2D is RectangleCollider2D


def test_ui_element_resolves_lazily():
    assert fb.UIElement is fb.ui.UIElement


def test_hooks_nothing_called_are_gone():
    """on_pre_update, on_post_update, on_draw and on_event_loop were declared
    on Node but never called by anything - overriding one silently did
    nothing."""
    for hook in ('on_pre_update', 'on_post_update', 'on_draw', 'on_event_loop'):
        assert not hasattr(fb.Node2D, hook)
        assert not hasattr(fb.Sprite2D, hook)
