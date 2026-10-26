"""Tests for flow layout (grow, justify, align, align_self), visibility,
element.rect and the root's safe_area - run against both backends (see
conftest.py). The root is 800x600 at a content scale of 1 unless a test
says otherwise."""
import pytest

from FreeBodyEngine.math import Vector
from FreeBodyEngine.ui.renderer import UIRenderer


def rect(element):
    layout = element._layout
    return (layout.x, layout.y, layout.width, layout.height)


def lay_out(ui, *children, root_styles=None):
    root = ui.RootElement(800, 600, root_styles)
    for child in children:
        root.add(child)
    root.calculate_layout()
    return root


# -- grow -------------------------------------------------------------------------

def test_grow_takes_the_space_left(ui):
    panel = ui.UIElement(styles={"width": "100w", "height": "100h"})
    header = ui.UIElement(styles={"width": "100w", "height": 50})
    body = ui.UIElement(styles={"width": "100w", "grow": 1})
    footer = ui.UIElement(styles={"width": "100w", "height": 100})
    for child in (header, body, footer):
        panel.add(child)
    lay_out(ui, panel)

    assert rect(body) == (0, 50, 800, 450)
    assert rect(footer) == (0, 500, 800, 100)


def test_grow_is_shared_in_proportion(ui):
    row = ui.UIElement(styles={"width": 400, "height": 10, "layout": "horizontal"})
    a = ui.UIElement(styles={"height": 10, "grow": 1})
    b = ui.UIElement(styles={"height": 10, "grow": 3})
    row.add(a)
    row.add(b)
    lay_out(ui, row)

    assert rect(a) == (0, 0, 100, 10)
    assert rect(b) == (100, 0, 300, 10)


def test_grow_adds_to_the_childs_own_size_and_counts_gaps(ui):
    row = ui.UIElement(styles={"width": 400, "height": 10, "layout": "horizontal", "gap": 20})
    fixed = ui.UIElement(styles={"width": 100, "height": 10})
    growing = ui.UIElement(styles={"width": 50, "height": 10, "grow": 1})
    row.add(fixed)
    row.add(growing)
    lay_out(ui, row)

    assert rect(growing) == (120, 0, 280, 10)


def test_grow_gets_nothing_when_children_already_overflow(ui):
    column = ui.UIElement(styles={"width": 10, "height": 100})
    big = ui.UIElement(styles={"width": 10, "height": 150})
    growing = ui.UIElement(styles={"width": 10, "grow": 1})
    column.add(big)
    column.add(growing)
    lay_out(ui, column)

    assert rect(growing) == (0, 150, 10, 0)


def test_a_grown_childs_children_lay_out_in_its_grown_size(ui):
    panel = ui.UIElement(styles={"width": 100, "height": 300})
    panel.add(ui.UIElement(styles={"width": 100, "height": 100}))
    body = ui.UIElement(styles={"width": 100, "grow": 1})
    inner = ui.UIElement(styles={"width": "100w", "height": "50h"})
    panel.add(body)
    body.add(inner)
    lay_out(ui, panel)

    assert rect(inner) == (0, 100, 100, 100)


# -- justify ------------------------------------------------------------------------

def column_of_two(ui, justify):
    column = ui.UIElement(styles={"width": 100, "height": 600, "justify": justify})
    a = ui.UIElement(styles={"width": 100, "height": 100})
    b = ui.UIElement(styles={"width": 100, "height": 100})
    column.add(a)
    column.add(b)
    lay_out(ui, column)
    return a, b


@pytest.mark.parametrize("justify, first_y, second_y", [
    ("start", 0, 100),
    ("center", 200, 300),
    ("end", 400, 500),
    ("space_between", 0, 500),
])
def test_justify(ui, justify, first_y, second_y):
    a, b = column_of_two(ui, justify)
    assert (rect(a)[1], rect(b)[1]) == (first_y, second_y)


def test_justify_on_the_root(ui):
    box = ui.UIElement(styles={"width": 100, "height": 100})
    lay_out(ui, box, root_styles={"justify": "end", "layout": "horizontal"})
    assert rect(box)[:2] == (700, 0)


def test_justify_moves_the_whole_subtree(ui):
    column = ui.UIElement(styles={"width": 100, "height": 600, "justify": "end"})
    card = ui.UIElement(styles={"width": 100, "height": 100, "padding": 10})
    label = ui.UIElement(styles={"width": 20, "height": 20})
    column.add(card)
    card.add(label)
    lay_out(ui, column)

    assert rect(label)[:2] == (10, 510)


# -- align ----------------------------------------------------------------------------

@pytest.mark.parametrize("align, x, width", [
    ("start", 0, 200),
    ("center", 300, 200),
    ("end", 600, 200),
])
def test_align(ui, align, x, width):
    column = ui.UIElement(styles={"width": 800, "height": 600, "align": align})
    child = ui.UIElement(styles={"width": 200, "height": 50})
    column.add(child)
    lay_out(ui, column)
    assert (rect(child)[0], rect(child)[2]) == (x, width)


def test_stretch_fills_the_cross_axis_unless_the_child_has_a_size(ui):
    row = ui.UIElement(styles={"width": 800, "height": 80, "layout": "horizontal", "align": "stretch"})
    stretched = ui.UIElement(styles={"width": 100})
    sized = ui.UIElement(styles={"width": 100, "height": 20})
    row.add(stretched)
    row.add(sized)
    lay_out(ui, row)

    assert rect(stretched) == (0, 0, 100, 80)
    assert rect(sized) == (100, 0, 100, 20)


def test_align_self_overrides_align(ui):
    column = ui.UIElement(styles={"width": 800, "height": 600, "align": "center"})
    centered = ui.UIElement(styles={"width": 200, "height": 50})
    pinned = ui.UIElement(styles={"width": 200, "height": 50, "align_self": "end"})
    column.add(centered)
    column.add(pinned)
    lay_out(ui, column)

    assert rect(centered)[0] == 300
    assert rect(pinned)[0] == 600


def test_centering_a_menu(ui):
    menu = ui.UIElement(styles={"width": "100w", "height": "100h", "align": "center",
                                "justify": "center", "gap": 20})
    title = ui.UIElement(styles={"width": 400, "height": 100})
    button = ui.UIElement(styles={"width": 200, "height": 60})
    menu.add(title)
    menu.add(button)
    lay_out(ui, menu)

    assert rect(title) == (200, 210, 400, 100)
    assert rect(button) == (300, 330, 200, 60)


# -- visible -------------------------------------------------------------------------------

def test_a_hidden_child_takes_no_space(ui):
    column = ui.UIElement(styles={"width": 100, "height": 600})
    hidden = ui.UIElement(styles={"width": 100, "height": 100, "visible": False})
    shown = ui.UIElement(styles={"width": 100, "height": 100})
    column.add(hidden)
    column.add(shown)
    lay_out(ui, column)

    assert rect(hidden) == (0, 0, 0, 0)
    assert rect(shown)[1] == 0


def test_hidden_children_are_not_measured(ui):
    column = ui.UIElement(styles={"width": 100, "height": "auto"})
    column.add(ui.UIElement(styles={"width": 100, "height": 40}))
    column.add(ui.UIElement(styles={"width": 100, "height": 40, "visible": False}))
    lay_out(ui, column)

    assert rect(column)[3] == 40


def test_the_visible_property(ui):
    box = ui.UIElement()
    assert box.visible
    box.visible = False
    assert not box.visible
    assert box.get_current_styles()["visible"] is False


def test_showing_again_lays_out_again(ui):
    column = ui.UIElement(styles={"width": 100, "height": 600})
    toggled = ui.UIElement(styles={"width": 100, "height": 100})
    after = ui.UIElement(styles={"width": 100, "height": 100})
    column.add(toggled)
    column.add(after)
    root = lay_out(ui, column)

    toggled.visible = False
    root.calculate_layout()
    assert rect(after)[1] == 0

    toggled.visible = True
    root.calculate_layout()
    assert rect(after)[1] == 100


def test_hidden_elements_and_their_children_cannot_be_hit(ui, make_manager):
    manager = make_manager()
    panel = ui.UIElement(styles={"width": 100, "height": 100, "visible": False})
    button = ui.UIElement(styles={"width": 50, "height": 50})
    manager.add(panel)
    panel.add(button)
    manager.root.calculate_layout()

    assert manager._hit_test(manager.root.children, Vector(10, 10)) is None


def test_hiding_a_focused_fields_container_unfocuses_it(ui, make_manager):
    manager = make_manager()
    panel = ui.UIElement()
    field = ui.UIElement(styles={"editable": True, "text": ""})
    manager.add(panel)
    panel.add(field)
    manager._set_focus(field)

    panel.visible = False
    manager._handle_mouse()
    assert manager._focused is None


def test_hiding_dirties_where_the_subtree_was_drawn(ui):
    renderer = UIRenderer.__new__(UIRenderer)
    renderer._dirty_rect = None

    panel = ui.UIElement(styles={"visible": False})
    popup = ui.UIElement()
    panel.add(popup)
    panel._ui_prev_rect, panel._ui_prev_signature = (0, 0, 10, 10), ()
    popup._ui_prev_rect, popup._ui_prev_signature = (50, 50, 10, 10), ()

    renderer._compute_dirty_rect(panel, (0, 0, 800, 600))
    assert renderer._dirty_rect == (0, 0, 60, 60)

    renderer._dirty_rect = None
    renderer._compute_dirty_rect(panel, (0, 0, 800, 600))
    assert renderer._dirty_rect is None


# -- rect, safe_area ----------------------------------------------------------------

def test_rect_is_in_ui_units(ui, services):
    services["window"].content_scale = 2.0
    box = ui.UIElement(styles={"width": 100, "height": 50, "x": 10})
    lay_out(ui, box)

    assert rect(box) == (20, 0, 200, 100)
    assert (box.rect.x, box.rect.y, box.rect.width, box.rect.height) == (10, 0, 100, 50)


def test_safe_area_pads_the_root(ui, services):
    services["window"].safe_area_insets = (20.0, 0.0, 30.0, 10.0)
    body = ui.UIElement(styles={"width": "100w", "grow": 1})
    lay_out(ui, body, root_styles={"safe_area": True})

    assert rect(body) == (10, 20, 790, 550)


def test_safe_area_insets_are_scaled_to_pixels(ui, services):
    services["window"].content_scale = 2.0
    services["window"].safe_area_insets = (20.0, 0.0, 0.0, 0.0)
    box = ui.UIElement(styles={"width": 10, "height": 10})
    lay_out(ui, box, root_styles={"safe_area": True})

    assert rect(box)[1] == 40


def test_safe_area_is_off_by_default(ui, services):
    services["window"].safe_area_insets = (20.0, 0.0, 0.0, 0.0)
    box = ui.UIElement(styles={"width": 10, "height": 10})
    lay_out(ui, box)

    assert rect(box)[1] == 0


# -- found while porting to the native backend -------------------------------------

def test_auto_on_the_cross_axis_fits_the_largest_child(ui):
    row = ui.UIElement(styles={"width": 400, "height": "auto", "layout": "horizontal"})
    row.add(ui.UIElement(styles={"width": 10, "height": 30}))
    row.add(ui.UIElement(styles={"width": 10, "height": 50}))
    lay_out(ui, row)

    assert rect(row)[3] == 50


def test_anchored_children_do_not_scroll_with_the_content(ui):
    scroller = ui.UIElement(styles={"width": 100, "height": 100, "overflow": "auto"})
    for _ in range(3):
        scroller.add(ui.UIElement(styles={"width": 100, "height": 100}))
    badge = ui.UIElement(styles={"width": 10, "height": 10, "parent_anchor": "top_left"})
    scroller.add(badge)
    root = lay_out(ui, scroller)

    scroller.scroll_by(50)
    root.calculate_layout()

    first_row = list(scroller.children.values())[0]
    assert rect(first_row)[1] == -50
    assert rect(badge)[1] == 0


def test_padding_is_scaled_once(ui, services):
    services["window"].content_scale = 2.0
    box = ui.UIElement(styles={"width": 100, "height": 100, "padding": 5})
    inner = ui.UIElement(styles={"width": 10, "height": 10})
    box.add(inner)
    lay_out(ui, box)

    assert rect(inner)[:2] == (10, 10)


def test_auto_inside_auto_is_right_on_the_first_frame(ui):
    outer = ui.UIElement(styles={"width": "auto", "height": "auto", "padding": 2})
    middle = ui.UIElement(styles={"width": "auto", "height": "auto", "layout": "horizontal", "gap": 4})
    middle.add(ui.UIElement(styles={"width": 10, "height": 30}))
    middle.add(ui.UIElement(styles={"width": 20, "height": 10}))
    outer.add(middle)
    lay_out(ui, outer)

    assert rect(middle)[2:] == (34, 30)
    assert rect(outer)[2:] == (38, 34)


def test_an_auto_grow_child_grows_from_what_it_fits(ui):
    row = ui.UIElement(styles={"width": 100, "height": 10, "layout": "horizontal"})
    growing = ui.UIElement(styles={"width": "auto", "height": 10, "grow": 1})
    growing.add(ui.UIElement(styles={"width": 30, "height": 10}))
    row.add(growing)
    row.add(ui.UIElement(styles={"width": 30, "height": 10, "grow": 1}))
    lay_out(ui, row)

    assert rect(growing)[2] == 50
