"""Tests for ui.Style - shared, live style sets - on both backends (see
conftest.py)."""
import gc

import pytest

import FreeBodyEngine.ui.style as style_module
from FreeBodyEngine.ui import Style
from FreeBodyEngine.ui.element import ElementStates

RED = (1.0, 0.0, 0.0, 1.0)
GREEN = (0.0, 1.0, 0.0, 1.0)
BLUE = (0.0, 0.0, 1.0, 1.0)


# -- a Style on its own ---------------------------------------------------------

def test_reads_like_a_dict_and_like_attributes():
    style = Style(width=10, base_color=RED)
    assert style["width"] == 10
    assert style.base_color == RED
    assert dict(style) == {"width": 10, "base_color": RED}
    assert {**style} == {"width": 10, "base_color": RED}


def test_values_can_be_set_and_removed():
    style = Style(width=10)
    style.height = 5
    style["width"] = 20
    style.update(gap=3)
    del style.height
    assert dict(style) == {"width": 20, "gap": 3}


def test_a_dict_state_override_becomes_a_style():
    style = Style(hover={"base_color": RED})
    assert style["hover"] == {"base_color": RED}


def test_unknown_styles_warn_with_a_suggestion(monkeypatch):
    warnings = []
    monkeypatch.setattr(style_module, "warning", warnings.append)
    Style(widht=10)
    assert warnings == ['Style: unknown style "widht" - did you mean "width"?']


def test_or_builds_on_both_with_the_right_winning():
    combined = Style(width=10, base_color=RED) | Style(base_color=GREEN)
    assert dict(combined) == {"width": 10, "base_color": GREEN}


def test_state_overrides_merge_across_bases():
    combined = Style(hover={"base_color": RED, "width": 1}) | Style(hover={"base_color": GREEN})
    assert combined["hover"] == {"base_color": GREEN, "width": 1}


def test_a_derived_style_follows_its_bases():
    button = Style(base_color=RED)
    danger = Style(button, width=5)
    button.base_color = BLUE
    assert danger.base_color == BLUE


def test_a_derived_style_follows_a_nested_state_style():
    hover = Style(base_color=RED)
    button = Style(hover=hover)
    hover.base_color = GREEN
    assert button["hover"] == {"base_color": GREEN}


def test_removing_an_own_value_falls_back_to_the_base():
    danger = Style(Style(base_color=RED), base_color=GREEN)
    del danger["base_color"]
    assert danger.base_color == RED


def test_styles_compare_by_identity():
    assert Style(width=1) != Style(width=1)


# -- on elements -----------------------------------------------------------------

def test_an_element_uses_its_style(ui):
    box = ui.UIElement(style=Style(width=40))
    assert box.get_current_styles()["width"] == 40


def test_changing_a_style_restyles_its_elements(ui):
    button = Style(base_color=RED)
    a, b = ui.UIElement(style=button), ui.UIElement(style=button)
    a.get_current_styles(), b.get_current_styles()

    button.base_color = GREEN
    assert a.get_current_styles()["base_color"] == GREEN
    assert b.get_current_styles()["base_color"] == GREEN


def test_changing_a_base_restyles_elements_of_a_derived_style(ui):
    button = Style(base_color=RED)
    box = ui.UIElement(style=button | Style(width=3))
    box.get_current_styles()

    button.base_color = BLUE
    assert box.get_current_styles()["base_color"] == BLUE


def test_the_elements_own_styles_win_over_its_style(ui):
    box = ui.UIElement(styles={"width": 7}, style=Style(width=40, height=2))
    assert box.get_current_styles()["width"] == 7
    assert box.get_current_styles()["height"] == 2


def test_a_state_override_wins_over_a_plain_value_from_either_layer(ui):
    box = ui.UIElement(styles={"base_color": RED}, style=Style(hover={"base_color": GREEN}))
    box.set_state(ElementStates.HOVER)
    assert box.get_current_styles()["base_color"] == GREEN


def test_the_elements_own_state_override_wins_over_its_styles(ui):
    box = ui.UIElement(styles={"hover": {"base_color": RED}}, style=Style(hover={"base_color": GREEN}))
    box.set_state(ElementStates.HOVER)
    assert box.get_current_styles()["base_color"] == RED


def test_replacing_an_elements_style_stops_following_the_old_one(ui):
    old, new = Style(width=1), Style(width=2)
    box = ui.UIElement(style=old)
    box.style = new
    old.width = 99
    assert box.get_current_styles()["width"] == 2
    assert box.style is new


def test_removing_an_elements_style(ui):
    box = ui.UIElement(style=Style(width=1))
    box.style = None
    assert box.get_current_styles()["width"] == 0


def test_an_anchor_from_a_style_anchors_the_element(ui):
    root = ui.RootElement(800, 600)
    box = ui.UIElement(styles={"width": 10, "height": 10}, style=Style(parent_anchor="bottom_right"))
    root.add(box)
    root.calculate_layout()
    assert (box._layout.x, box._layout.y) == (790, 590)


def test_animating_starts_from_the_styles_value(ui):
    box = ui.UIElement(style=Style(width=100))
    box.set_style("width", 200, duration=1.0)
    box._update()
    assert box.styles["width"] == pytest.approx(150)


def test_elements_that_are_gone_are_not_kept_alive_or_restyled(ui):
    button = Style(width=1)
    ui.UIElement(style=button)
    gc.collect()
    button.width = 2
    assert len(button._dependents) == 0
