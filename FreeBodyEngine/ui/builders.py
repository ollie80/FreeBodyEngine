"""Shorthand for building UI trees - functions that return ordinary
UIElements, so everything here mixes freely with UIElement(styles={...})
code and with each other:

    from FreeBodyEngine.ui import Column, Text, Button, Style

    button = Style(font=FONT, font_size=36, padding=16, base_color=PURPLE,
                   hover=Style(base_color=GOLD))

    menu = Column(
        Text("BIG D", size=150, color=GOLD, font=FONT),
        Button("PLAY", on_click=play, style=button),
        Button("QUIT", on_click=quit, style=button),
        fill=True, align="center", justify="center", gap=20,
    )
    fb.get_service("ui").add(menu)
    menu.visible = False

Every builder takes:

    *children / children=[...]
        Elements to add, in order. None is skipped, so a child can be
        conditional: `Row(icon if show_icon else None, label)`.
    style=
        A ui.Style the element is drawn with (see UIElement.style).
    tag=
        The element's tag.
    fill=True
        Shorthand for "width": "100w", "height": "100h".
    on_<event>=callback
        Makes `callback` the handler for that event - on_click, on_submit,
        on_hover_enter, on_press, on_swipe_move, ... (see the INTERACTION
        docs in ui/element.py, and UIElement.set_handler()).
    any other keyword
        A style, checked against the styles the engine knows - a typo
        warns rather than silently doing nothing.

A builder's own defaults (a Column's "auto" size, a Button's centered text)
only apply where neither its keywords nor its `style` set that value.
"""
from FreeBodyEngine.ui.style import Style, check_style_key


def _element_class():
    # Resolved per call, not at import: which backend UIElement is depends
    # on flags a project sets after importing the engine (see
    # ui/__init__.py's _resolve_element_classes).
    from FreeBodyEngine import ui
    return ui.UIElement


def _build(where: str, children: tuple, defaults: dict, kwargs: dict, aliases: dict = None):
    tag = kwargs.pop("tag", None)
    style: Style | None = kwargs.pop("style", None)
    children = (*children, *(kwargs.pop("children", None) or ()))
    if kwargs.pop("fill", False):
        kwargs.setdefault("width", "100w")
        kwargs.setdefault("height", "100h")

    events = {key[3:]: kwargs.pop(key) for key in list(kwargs) if key.startswith("on_")}

    styles = {}
    for key, value in kwargs.items():
        key = (aliases or {}).get(key, key)
        check_style_key(key, where)
        styles[key] = value
    for key, value in defaults.items():
        if key not in styles and (style is None or key not in style):
            styles[key] = value

    element = _element_class()(tag, styles=styles, style=style)

    for child in children:
        if child is not None:
            element.add(child)
    for event, callback in events.items():
        if callback is not None:
            element.set_handler(event, callback)

    return element


# Text widgets also take size= and color=, for font_size and text_color.
_TEXT_ALIASES = {"size": "font_size", "color": "text_color"}

_CONTAINER_DEFAULTS = {"width": "auto", "height": "auto"}


def Box(*children, **kwargs):
    """A plain element - sized to fit its children unless given a size."""
    return _build("Box", children, _CONTAINER_DEFAULTS, kwargs)


def Column(*children, **kwargs):
    """Children stacked top to bottom - sized to fit them unless given a size."""
    return _build("Column", children, {**_CONTAINER_DEFAULTS, "layout": "vertical"}, kwargs)


def Row(*children, **kwargs):
    """Children side by side, left to right - sized to fit them unless given
    a size."""
    return _build("Row", children, {**_CONTAINER_DEFAULTS, "layout": "horizontal"}, kwargs)


def Spacer(grow: float = 1, **kwargs):
    """Empty space taking a share of what's left in its Row/Column - pushes
    whatever follows it to the far end."""
    kwargs["grow"] = grow
    return _build("Spacer", (), {}, kwargs)


def Text(text: str = "", *children, **kwargs):
    """A label, sized to fit its text unless given a size. Needs a font
    (font=, or from its style)."""
    kwargs["text"] = text
    return _build("Text", children, {"width": "auto", "height": "auto"}, kwargs, _TEXT_ALIASES)


def Button(text: str = "", *children, **kwargs):
    """A clickable label - Text with its text centered, plus on_click=."""
    kwargs["text"] = text
    return _build("Button", children, {"width": "auto", "height": "auto", "text_align": "center"},
                  kwargs, _TEXT_ALIASES)


def Input(text: str = "", **kwargs):
    """A single-line text field - the width of its parent unless given one,
    one line of text tall. on_submit= is called with its text on Enter;
    secret=True masks it."""
    kwargs["text"] = text
    kwargs["editable"] = True
    return _build("Input", (), {"width": "100w", "height": "auto"}, kwargs, _TEXT_ALIASES)


def Image(image, **kwargs):
    """An element showing `image` (a texture path) as its background."""
    kwargs["image"] = image
    return _build("Image", (), {}, kwargs)
