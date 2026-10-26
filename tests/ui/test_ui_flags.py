"""Tests for element flags (hover/pressed/focused from input, plus the app's
own, like selected) and replaceable event handlers, on both backends (see
conftest.py)."""
from FreeBodyEngine.math import Vector
from FreeBodyEngine.ui import Style
from FreeBodyEngine.ui.element import ElementStates, style_keys_for

GREY = (0.5, 0.5, 0.5, 1.0)
RED = (1.0, 0.0, 0.0, 1.0)
GREEN = (0.0, 1.0, 0.0, 1.0)
BLUE = (0.0, 0.0, 1.0, 1.0)


def colour(element):
    return element.get_current_styles()["base_color"]


# -- flags ----------------------------------------------------------------------

def test_flags_can_be_set_and_cleared(ui):
    box = ui.UIElement()
    box.set_flag("playing")
    box.selected = True
    assert box.flags == ("playing", "selected")
    assert box.has_flag("playing") and box.selected

    box.set_flag("playing", False)
    box.selected = False
    assert box.flags == ()


def test_a_flags_table_applies_while_its_set(ui):
    box = ui.UIElement(styles={"base_color": GREY, "playing": {"base_color": GREEN}})
    box.set_flag("playing")
    assert colour(box) == GREEN
    box.set_flag("playing", False)
    assert colour(box) == GREY


def test_flags_combine(ui):
    box = ui.UIElement(styles={
        "selected": {"border_width": 2},
        "hover": {"base_color": RED},
    })
    box.selected = True
    box.set_flag("hover")
    styles = box.get_current_styles()
    assert styles["border_width"] == 2 and styles["base_color"] == RED


def test_later_flags_win(ui):
    box = ui.UIElement(styles={
        "playing": {"base_color": BLUE},
        "selected": {"base_color": GREEN},
        "hover": {"base_color": RED},
        "pressed": {"base_color": GREY},
    })
    box.set_flag("playing")
    assert colour(box) == BLUE
    box.selected = True
    assert colour(box) == GREEN
    box.set_flag("hover")
    assert colour(box) == RED
    box.set_flag("pressed")
    assert colour(box) == GREY


def test_normal_applies_only_with_no_flags(ui):
    box = ui.UIElement(styles={"normal": {"width": 1}, "width": 5})
    assert box.get_current_styles()["width"] == 1
    box.set_flag("hover")
    assert box.get_current_styles()["width"] == 5


def test_the_old_names_still_apply(ui):
    box = ui.UIElement(styles={"clicked": {"base_color": RED}, "selected": {"border_width": 3}})
    box.set_flag("pressed")
    assert colour(box) == RED
    box.set_flag("pressed", False)
    box.set_flag("focused")
    assert box.get_current_styles()["border_width"] == 3


def test_the_new_name_wins_over_the_old(ui):
    box = ui.UIElement(styles={"clicked": {"base_color": RED}, "pressed": {"base_color": GREEN}})
    box.set_flag("pressed")
    assert colour(box) == GREEN


def test_style_keys_for():
    assert style_keys_for([]) == ["normal"]
    assert style_keys_for(["pressed", "playing", "hover"]) == ["playing", "hover", "clicked", "pressed"]
    assert style_keys_for(["focused", "selected"]) == ["selected", "focused"]


def test_a_styles_flag_tables_apply(ui):
    button = Style(base_color=GREY, selected=Style(base_color=GREEN), playing={"base_color": BLUE})
    box = ui.UIElement(style=button)
    box.selected = True
    assert colour(box) == GREEN
    box.selected = False
    box.set_flag("playing")
    assert colour(box) == BLUE


def test_an_app_flag_table_merges_across_style_bases():
    combined = Style(playing={"base_color": RED, "width": 1}) | Style(playing={"base_color": GREEN})
    assert combined["playing"] == {"base_color": GREEN, "width": 1}


def test_a_dict_style_is_not_taken_for_a_flag():
    combined = Style(scrollbar_thumb={"base_color": RED, "width": 1}) | Style(scrollbar_thumb={"base_color": GREEN})
    assert combined["scrollbar_thumb"] == {"base_color": GREEN}


def test_writing_into_a_flags_table_directly_is_seen(ui):
    box = ui.UIElement(styles={"playing": {"width": 1}})
    box.set_flag("playing")
    assert box.get_current_styles()["width"] == 1
    box.styles["playing"]["width"] = 2
    assert box.get_current_styles()["width"] == 2


def test_an_anchor_under_a_flag_anchors_the_element(ui):
    root = ui.RootElement(800, 600)
    box = ui.UIElement(styles={"width": 10, "height": 10, "docked": {"parent_anchor": "bottom_right"}})
    root.add(box)
    box.set_flag("docked")
    root.calculate_layout()
    assert (box._layout.x, box._layout.y) == (790, 590)


# -- the older single state ----------------------------------------------------------

def test_state_reports_the_most_specific_interaction_flag(ui):
    box = ui.UIElement()
    assert box.state == ElementStates.NORMAL
    box.set_flag("hover")
    assert box.state == ElementStates.HOVER
    box.set_flag("focused")
    assert box.state == ElementStates.FOCUSED
    box.set_flag("pressed")
    assert box.state == ElementStates.CLICKED


def test_set_state_sets_one_interaction_flag_and_leaves_the_apps(ui):
    box = ui.UIElement()
    box.selected = True
    box.set_state(ElementStates.HOVER)
    assert box.flags == ("selected", "hover")
    box.set_state(ElementStates.CLICKED)
    assert box.flags == ("selected", "pressed")
    box.set_state(ElementStates.NORMAL)
    assert box.flags == ("selected",)


# -- from input ----------------------------------------------------------------------

def press(manager, mouse, point):
    mouse.position = point
    mouse.pressed = mouse.down = True
    manager._handle_mouse()
    mouse.pressed = False


def release(manager, mouse):
    mouse.down = False
    mouse.released = True
    manager._handle_mouse()
    mouse.released = False


def test_hover_press_and_focus_are_independent(ui, make_manager, services):
    manager = make_manager()
    field = ui.UIElement(styles={"width": 100, "height": 30, "editable": True, "text": ""})
    manager.add(field)
    manager.root.calculate_layout()
    mouse = services["mouse"]

    press(manager, mouse, Vector(10, 10))
    assert set(field.flags) == {"hover", "pressed", "focused"}

    release(manager, mouse)
    assert set(field.flags) == {"hover", "focused"}

    mouse.position = Vector(500, 500)
    manager._handle_mouse()
    assert field.flags == ("focused",)


def test_input_leaves_the_apps_flags_alone(ui, make_manager, services):
    manager = make_manager()
    tab = ui.UIElement(styles={"width": 100, "height": 30})
    tab.selected = True
    manager.add(tab)
    manager.root.calculate_layout()
    mouse = services["mouse"]

    press(manager, mouse, Vector(10, 10))
    release(manager, mouse)
    mouse.position = Vector(500, 500)
    manager._handle_mouse()
    assert tab.flags == ("selected",)


def test_a_removed_hovered_element_loses_its_hover(ui, make_manager, services):
    manager = make_manager()
    box = ui.UIElement(styles={"width": 100, "height": 30})
    manager.add(box)
    manager.root.calculate_layout()
    services["mouse"].position = Vector(10, 10)
    manager._handle_mouse()
    assert box.hovered

    manager.remove(box)
    manager._handle_mouse()
    assert not box.hovered


# -- handlers ----------------------------------------------------------------------

def test_setting_a_handler_replaces_the_last(ui):
    calls = []
    button = ui.UIElement()
    button.on_click = lambda: calls.append("follow")
    button.on_click = lambda: calls.append("unfollow")
    button._emit("click")
    assert calls == ["unfollow"]


def test_setting_a_handler_replaces_on_callbacks_too(ui):
    calls = []
    button = ui.UIElement()
    button.on("click", lambda: calls.append("old"))
    button.set_handler("click", lambda: calls.append("new"))
    button._emit("click")
    assert calls == ["new"]


def test_none_removes_the_handler(ui):
    calls = []
    button = ui.UIElement()
    button.on_click = lambda: calls.append(1)
    button.on_click = None
    button._emit("click")
    assert calls == [] and button.on_click is None
    assert not button.has_event("click")


def test_the_handler_can_be_read_back(ui):
    button = ui.UIElement()
    def handler(text):
        pass
    button.on_submit = handler
    assert button.on_submit is handler


def test_on_adds_and_returns_a_remover(ui):
    calls = []
    button = ui.UIElement()
    button.on("click", lambda: calls.append("a"))
    remove_b = button.on("click", lambda: calls.append("b"))
    remove_b()
    button._emit("click")
    assert calls == ["a"]


def test_builder_handlers_can_be_replaced_later(ui, builders):
    calls = []
    button = builders.Button("go", on_click=lambda: calls.append("first"))
    button.on_click = lambda: calls.append("second")
    button._emit("click")
    assert calls == ["second"]


def test_a_scrollbar_thumb_lights_up_on_hover(ui, make_manager, services):
    manager = make_manager()
    scroller = ui.UIElement(styles={"width": 100, "height": 100, "overflow": "scroll",
                                    "scrollbar_thumb": {"hover": {"base_color": RED}}})
    for _ in range(3):
        scroller.add(ui.UIElement(styles={"width": 50, "height": 100}))
    manager.add(scroller)
    manager.root.calculate_layout()

    services["mouse"].position = Vector(93, 5)
    manager._handle_mouse()
    thumb = manager._hovered
    assert thumb is not None and getattr(thumb, "_is_scrollbar_thumb", False)
    assert colour(thumb) == RED
