"""Tests that every UI element owns its styles dict.

Elements stored whatever dict they were given - the `{}` default, one object
for every call, or a style dict the game reused across elements - and
set_style() writes into it, so styling one element restyled all the others.
"""
from FreeBodyEngine.ui.element import RootElement, UIElement


def test_elements_without_styles_do_not_share_them():
    a, b = UIElement(), UIElement()
    a._set_style('width', 123)
    assert 'width' not in b.styles


def test_a_reused_style_dict_is_not_changed_through_one_element():
    button_style = {'width': 10}
    a, b = UIElement(styles=button_style), UIElement(styles=button_style)
    a._set_style('width', 99)
    assert b.styles['width'] == 10
    assert button_style == {'width': 10}


def test_root_elements_do_not_share_styles():
    a, b = RootElement(100, 100), RootElement(100, 100)
    a.styles['colour'] = 'red'
    assert 'colour' not in b.styles
