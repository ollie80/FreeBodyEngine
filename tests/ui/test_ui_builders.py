"""Tests for the ui builders (Column, Row, Text, Button, ...) and text-fitting
"auto" sizes, on both backends (see conftest.py). Text is measured by the
fake in conftest.py: 10px per character, as tall as its font size."""
import FreeBodyEngine.ui.element as element_module
import FreeBodyEngine.ui.style as style_module
from FreeBodyEngine.ui import Style


def rect(element):
    layout = element._layout
    return (layout.x, layout.y, layout.width, layout.height)


def lay_out(ui, *children):
    root = ui.RootElement(800, 600)
    for child in children:
        root.add(child)
    root.calculate_layout()
    return root


# -- building -----------------------------------------------------------------------

def test_children_are_added_in_order_and_none_is_skipped(ui, builders):
    a, b, c = builders.Box(), builders.Box(), builders.Box()
    column = builders.Column(a, None, b, children=[c])
    assert list(column.children.values()) == [a, b, c]


def test_builders_return_ordinary_elements(ui, builders):
    column = builders.Column(gap=4, tag="menu")
    assert isinstance(column, ui.UIElement)
    assert column.tag == "menu"
    assert column.get_current_styles()["layout"] == "vertical"
    assert builders.Row().get_current_styles()["layout"] == "horizontal"


def test_keywords_are_styles_and_typos_warn(ui, builders, monkeypatch):
    warnings = []
    monkeypatch.setattr(style_module, "warning", warnings.append)
    box = builders.Box(gap=4, font_sise=3)
    assert box.get_current_styles()["gap"] == 4
    assert warnings == ['Box: unknown style "font_sise" - did you mean "font_size"?']


def test_text_takes_size_and_color(ui, builders):
    label = builders.Text("hi", size=30, color=(1, 0, 0, 1))
    styles = label.get_current_styles()
    assert (styles["text"], styles["font_size"], styles["text_color"]) == ("hi", 30, (1, 0, 0, 1))


def test_event_keywords_register_callbacks(ui, builders):
    clicks, submits = [], []
    button = builders.Button("go", on_click=lambda: clicks.append(1))
    field = builders.Input(on_submit=submits.append)
    button._emit("click")
    field._emit("submit", "text")
    assert clicks == [1] and submits == ["text"]


def test_fill(ui, builders):
    panel = builders.Column(fill=True)
    lay_out(ui, panel)
    assert rect(panel) == (0, 0, 800, 600)


def test_defaults_give_way_to_the_style(ui, builders):
    sized = builders.Button("go", style=Style(width=200))
    assert sized.get_current_styles()["width"] == 200
    assert builders.Button("go").get_current_styles()["width"] == "auto"


def test_input_is_an_editable_field(ui, builders):
    field = builders.Input("abc", secret=True)
    styles = field.get_current_styles()
    assert styles["editable"] and styles["secret"] and styles["text"] == "abc"


def test_image(ui, builders):
    assert builders.Image("avatar.png", width=10).get_current_styles()["image"] == "avatar.png"


# -- fitting text ------------------------------------------------------------------

def test_text_fits_its_words_and_padding(ui, builders):
    label = builders.Text("abc", font="f.ttf", size=20, padding=5)
    lay_out(ui, label)
    assert rect(label)[2:] == (40, 30)


def test_an_empty_field_is_one_line_tall(ui, builders):
    field = builders.Input(font="f.ttf", size=20, width=100)
    lay_out(ui, field)
    assert rect(field)[2:] == (100, 20)


def test_without_a_font_auto_text_has_no_size(ui, builders):
    label = builders.Text("abc")
    lay_out(ui, label)
    assert rect(label)[2:] == (0, 0)


def test_a_column_fits_its_buttons(ui, builders):
    column = builders.Column(
        builders.Button("PLAY", font="f.ttf", size=20),
        builders.Button("QUIT!!", font="f.ttf", size=20),
        gap=10,
    )
    lay_out(ui, column)
    assert rect(column)[2:] == (60, 50)


def test_a_spacer_pushes_the_rest_to_the_end(ui, builders):
    left = builders.Text("ab", font="f.ttf", size=10)
    right = builders.Text("cd", font="f.ttf", size=10)
    row = builders.Row(left, builders.Spacer(), right, width=400)
    lay_out(ui, row)
    assert rect(left)[0] == 0
    assert rect(right)[0] == 380


def test_a_centered_menu(ui, builders):
    title = builders.Text("BIG D", font="f.ttf", size=100)
    play = builders.Button("PLAY", font="f.ttf", size=20, padding=10)
    menu = builders.Column(title, play, fill=True, align="center", justify="center", gap=20)
    lay_out(ui, menu)

    # 100 + 20 + 40 tall in total, centered in 600; each centered across 800.
    assert rect(title) == (375, 220, 50, 100)
    assert rect(play) == (370, 340, 60, 40)


def test_measure_text_needs_a_running_text_renderer(services):
    assert element_module.measure_text({"font": "f.ttf", "text": "abc"}) is None
    assert element_module.measure_text({"text": "abc"}) is None
