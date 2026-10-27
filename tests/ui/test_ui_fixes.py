"""Tests for fixed UI bugs - animation, styles, layout, hit-testing and
input - run against both backends (see conftest.py)."""
import pytest

from FreeBodyEngine.core.input import Key
from FreeBodyEngine.math import Vector
import FreeBodyEngine.ui.element as py_backend


def rect(element):
    layout = element._layout
    return (layout.x, layout.y, layout.width, layout.height)


# -- animation ----------------------------------------------------------------

def test_animations_advance_each_frame_and_land_exactly(ui):
    root = ui.RootElement(800, 600)
    box = ui.UIElement(styles={"width": 100})
    root.add(box)

    box.set_style("width", 200, duration=1.0)
    root._update()
    assert box.styles["width"] == pytest.approx(150)

    root._update()
    assert box.styles["width"] == 200
    assert box.animations == []


def test_nested_elements_animate_too(ui):
    root = ui.RootElement(800, 600)
    outer = ui.UIElement()
    inner = ui.UIElement(styles={"height": 0})
    root.add(outer)
    outer.add(inner)

    inner.set_style("height", 10, duration=0.5)
    root._update()
    assert inner.styles["height"] == 10


def test_a_style_never_set_animates_from_its_default(ui):
    box = ui.UIElement()
    box.set_style("base_color", (1.0, 1.0, 1.0, 1.0), duration=1.0)
    box._update()
    assert box.styles["base_color"] == pytest.approx((0.5, 0.5, 0.5, 0.5))


def test_int_to_float_is_animatable(ui):
    box = ui.UIElement(styles={"width": 100})
    box.set_style("width", 200.5, duration=1.0)
    assert len(box.animations) == 1


def test_incompatible_units_raise_a_value_error(ui):
    box = ui.UIElement(styles={"width": "50w"})
    with pytest.raises(ValueError):
        box.set_style("width", "100h", duration=1.0)
    assert box.animations == []


def test_setting_a_style_stops_its_running_animation(ui):
    box = ui.UIElement(styles={"width": 100})
    box.set_style("width", 200, duration=1.0)
    box.set_style("width", 50)
    box._update()
    assert box.styles["width"] == 50


# -- styles -------------------------------------------------------------------

def test_writing_into_styles_directly_is_seen(ui):
    box = ui.UIElement(styles={"width": 100})
    assert box.get_current_styles()["width"] == 100

    box.styles["width"] = 40
    assert box.get_current_styles()["width"] == 40


def test_writing_into_a_state_table_directly_is_seen(ui):
    box = ui.UIElement(styles={"hover": {"width": 10}})
    box.set_state(py_backend.ElementStates.HOVER)
    assert box.get_current_styles()["width"] == 10

    box.styles["hover"]["width"] = 20
    assert box.get_current_styles()["width"] == 20


def test_a_shared_state_table_is_not_changed_through_one_element(ui):
    hover = {"width": 10}
    box = ui.UIElement(styles={"hover": hover})
    box.styles["hover"]["width"] = 99
    assert hover == {"width": 10}


def test_replacing_styles_wholesale_is_seen(ui):
    box = ui.UIElement(styles={"width": 100})
    box.get_current_styles()
    box.styles = {"width": 7}
    assert box.get_current_styles()["width"] == 7


# -- layout -------------------------------------------------------------------

def test_one_anchor_is_used_for_both(ui):
    root = ui.RootElement(800, 600)
    box = ui.UIElement(styles={"width": 50, "height": 20, "parent_anchor": "top_right"})
    root.add(box)
    root.calculate_layout()
    assert rect(box) == (750, 0, 50, 20)


def test_anchor_alone_is_used_for_both(ui):
    root = ui.RootElement(800, 600)
    box = ui.UIElement(styles={"width": 50, "height": 20, "anchor": "bottom_left"})
    root.add(box)
    root.calculate_layout()
    assert rect(box) == (0, 580, 50, 20)


def test_offsets_take_size_units(ui):
    root = ui.RootElement(800, 600)
    box = ui.UIElement(styles={"width": 10, "height": 10, "x": "10w", "y": "50h"})
    root.add(box)
    root.calculate_layout()
    assert rect(box)[:2] == (80, 300)


def test_root_padding_takes_size_units(ui):
    root = ui.RootElement(800, 600, styles={"padding": "10w"})
    box = ui.UIElement(styles={"width": 10, "height": 10})
    root.add(box)
    root.calculate_layout()
    assert rect(box)[:2] == (80, 80)


# -- hit-testing --------------------------------------------------------------

def test_clipped_children_cannot_be_hit(ui, make_manager):
    manager = make_manager()
    clip = ui.UIElement(styles={"width": 100, "height": 100, "overflow": "hidden"})
    first = ui.UIElement(styles={"width": 100, "height": 100})
    hidden = ui.UIElement(styles={"width": 100, "height": 100})
    manager.add(clip)
    clip.add(first)
    clip.add(hidden)
    manager.root.calculate_layout()

    assert manager._hit_test(manager.root.children, Vector(50, 150)) is None
    assert manager._hit_test(manager.root.children, Vector(50, 50)) is first


def test_a_child_outside_its_parent_can_be_hit(ui, make_manager):
    manager = make_manager()
    button = ui.UIElement(styles={"width": 100, "height": 50})
    dropdown = ui.UIElement(styles={"width": 100, "height": 80, "parent_anchor": "top_left", "y": 50})
    manager.add(button)
    button.add(dropdown)
    manager.root.calculate_layout()

    assert manager._hit_test(manager.root.children, Vector(50, 100)) is dropdown


def test_children_of_a_zero_size_wrapper_can_be_hit(ui, make_manager):
    manager = make_manager()
    wrapper = ui.UIElement()
    row = ui.UIElement(styles={"width": 100, "height": 30})
    manager.add(wrapper)
    wrapper.add(row)
    manager.root.calculate_layout()

    assert manager._hit_test(manager.root.children, Vector(10, 10)) is row


# -- input --------------------------------------------------------------------

def test_a_gesture_search_stops_at_the_root(ui, make_manager):
    manager = make_manager()
    row = ui.UIElement(styles={"width": 100, "height": 30})
    manager.add(row)
    assert manager._claim_gesture(row, True) == (None, None)

    row.on("swipe_move", lambda dx, dy: None)
    assert manager._claim_gesture(row, True) == (row, "swipe")


def test_dragging_does_not_crash(ui, make_manager, services):
    manager = make_manager()
    row = ui.UIElement(styles={"width": 100, "height": 30})
    manager.add(row)
    manager.root.calculate_layout()
    mouse = services["mouse"]

    mouse.position = Vector(10, 10)
    mouse.pressed = mouse.down = True
    manager._handle_mouse()

    mouse.pressed = False
    mouse.dragging = True
    mouse.position = Vector(60, 12)
    manager._handle_mouse()


def test_a_removed_field_stops_receiving_keys(ui, make_manager):
    manager = make_manager()
    field = ui.UIElement(styles={"width": 100, "height": 30, "editable": True, "text": ""})
    manager.add(field)
    manager._set_focus(field)

    manager.remove(field)
    manager._on_key(Key.A)
    assert field.get_current_styles()["text"] == ""
    assert manager._focused is None


def test_a_field_emptied_out_of_its_container_stops_receiving_keys(ui, make_manager):
    manager = make_manager()
    panel = ui.UIElement()
    field = ui.UIElement(styles={"editable": True, "text": ""})
    manager.add(panel)
    panel.add(field)
    manager._set_focus(field)

    panel.children.clear()
    manager._on_key(Key.A)
    assert field.get_current_styles()["text"] == ""


def test_paste_leaves_the_cursor_after_the_pasted_text(ui, make_manager):
    manager = make_manager()
    field = ui.UIElement(styles={"editable": True, "text": "ab"})
    manager.add(field)
    manager._set_focus(field)

    manager.paste_text("xyz")
    assert field.get_current_styles()["text"] == "abxyz"
    assert field._cursor_index == 5


def test_a_hovered_element_whose_container_was_cleared_and_collected(ui, make_manager, services):
    import gc
    manager = make_manager()
    page = ui.UIElement(styles={"width": 400, "height": 400})
    section = ui.UIElement(styles={"width": 400, "height": 100})
    row = ui.UIElement(styles={"width": 400, "height": 50})
    manager.add(page)
    page.add(section)
    section.add(row)
    manager.root.calculate_layout()
    services["mouse"].position = Vector(10, 10)
    manager._handle_mouse()
    assert manager._hovered is row

    # A page rebuild: the section goes, and nothing on the Python side
    # holds it any more - only the manager still holds the row.
    page.children.clear()
    del section
    gc.collect()

    services["mouse"].position = Vector(500, 500)
    manager._handle_mouse()
    assert manager._hovered is None
