"""The pure-Python UI backend - see ui/__init__.py for when it's used
rather than ui/native_element.py. What both backends share (flags, handlers,
animation, the styles/style/visible/rect properties, Layout, ElementStates,
...) lives in ui/base.py; this file is layout, measuring and the Python
side of the element tree."""
import uuid
from typing import Callable
from FreeBodyEngine import warning, get_service
from FreeBodyEngine.ui.base import (  # noqa: F401 - re-exported, imported from here by older code
    STATE_STYLE_KEYS, INTERACTION_FLAGS, VALID_ANCHORS, VALID_OVERFLOWS, DEFAULT_STYLES,
    style_keys_for, StyleView, _copy_styles, _content_scale,
    ElementStates, Layout, TreeBehaviour, ElementBehaviour, UIAnimation,
)


"""
===============================================================================
UI STYLE DOCUMENTATION
===============================================================================

Elements can be built with UIElement(tag, styles={...}) as below, or with
the shorthand in ui/builders.py (Column, Row, Text, Button, Input, ...),
which builds the same UIElements from keyword styles. Shared, live style
sets - a theme's "button" - are ui.Style objects (ui/style.py), given to an
element as `style=` underneath its own styles.

SIZE
-------------------------------------------------------------------------------

width
    Controls the width of an element.

    Examples:
        "width": 200
        "width": "200"
        "width": "50w"
        "width": "100ww"

height
    Controls the height of an element.

    Examples:
        "height": 100
        "height": "100"
        "height": "50h"
        "height": "100hw"


SIZE UNITS
-------------------------------------------------------------------------------

Plain number
    Fixed number of pixels.

        "width": 200
        "height": "64"


w
    Percentage of the parent content width.

        "width": "50w"

    Means:
        50% of the parent's content width.


h
    Percentage of the parent content height.

        "height": "50h"


ww
    Percentage of the root/window width.

        "width": "50ww"


hw
    Percentage of the root/window height.

        "height": "50hw"


auto
    Fits this element to its own children's stacked size along its
    `layout` direction - "height": "auto" with layout "vertical" (the
    common case: a list container that should be exactly as tall as
    its rows, not clipped to a guessed fixed number, and not squashed
    to 0 by DEFAULT_STYLES if you forget to set a height at all) sums
    every non-anchored child's own height plus the gaps between them;
    "width": "auto" with layout "horizontal" does the same across
    width. On the cross axis ("height": "auto" under a *horizontal*
    layout, or "width": "auto" under a vertical one) it fits to the
    tallest/widest child instead.

    Example:

        styles={
            "width": "100w",
            "height": "auto",
            "layout": "vertical",
        }

    A child that's itself "auto" is measured the same way, so "auto"
    nests to any depth. An element with no children fits its own text
    instead - its words in its font and size, one line tall - so a label
    or button needs no size of its own.


PADDING
-------------------------------------------------------------------------------

padding
    Applies padding to all four sides of an element.

        "padding": 10

    Equivalent to:

        "padding_left": 10
        "padding_right": 10
        "padding_top": 10
        "padding_bottom": 10


padding_left
    Padding on the left side.

        "padding_left": 20


padding_right
    Padding on the right side.

        "padding_right": 20


padding_top
    Padding on the top side.

        "padding_top": 20


padding_bottom
    Padding on the bottom side.

        "padding_bottom": 20

Individual padding properties override "padding".


CHILD LAYOUT
-------------------------------------------------------------------------------

layout
    Controls the direction in which children are automatically laid out.

    Supported values:

        "vertical"
            Children are placed from top to bottom.

        "horizontal"
            Children are placed from left to right.

    Default:
        "vertical"

    Example:

        styles={
            "layout": "horizontal"
        }


gap
    Space placed between children in the automatic layout.

    Example:

        styles={
            "layout": "horizontal",
            "gap": 10
        }


grow
    Set on a child: how much of the space its parent has left along the
    layout direction it takes, on top of its own size. Children share
    the leftover space in proportion to their grow values; 0 (the
    default) takes none. The usual header / content / footer:

        panel = UIElement(styles={"width": "100w", "height": "100h"})
        panel.add(header)                                   # fixed height
        panel.add(UIElement(styles={"grow": 1, "width": "100w"}))  # the rest
        panel.add(footer)                                   # fixed height

    Children never shrink: if they don't fit, grow children get nothing
    extra and the rest overflow as before.


justify
    Set on a container: where its children sit along the layout direction
    when they don't fill it - "start" (default), "center", "end", or
    "space_between" (first and last at the edges, the rest spread evenly
    between them). Has no effect while any child has grow, since that
    space is then taken.


align
    Set on a container: where each child sits across the layout direction
    - "start" (default), "center", "end", or "stretch" (as wide as the
    container in a vertical layout, as tall in a horizontal one - for a
    child with no width/height of its own on that axis).

        styles={"layout": "vertical", "align": "center", "justify": "center"}

    centers every child in the container.


align_self
    Set on a child: overrides its parent's align for just this child.
    "auto" (default) uses the parent's.


TRANSFORM
-------------------------------------------------------------------------------

Visual only: these change how an element's background (colour, image,
border) is drawn, around its centre, and nothing else - not its layout
rect, not where it can be clicked, and not its text or children, which
draw where they would anyway. All of them animate with set_style(...,
duration=...).

scale
    Size multiplier. Default 1.

rotation
    Clockwise turn, in degrees. Default 0.

tilt
    (x, y) in degrees: a 3D lean, drawn in perspective. x turns it about
    its vertical axis - positive takes the right edge away from you; y
    about its horizontal axis - positive takes the bottom edge away.
    Default (0, 0).

        cover.set_style("tilt", (8, -5))    # right edge back, top edge back

perspective
    How far away the viewer is, in pixels - smaller exaggerates a tilt.
    Default 1000.


VISIBILITY
-------------------------------------------------------------------------------

visible
    False hides an element and its whole subtree: it takes no space in
    its parent's layout, isn't drawn, and can't be hovered, clicked or
    typed into (a hidden focused field loses focus). Also settable as
    `element.visible = False`. Default True.


ROOT
-------------------------------------------------------------------------------

safe_area
    Set on the root (UIManager's styles): pads it by the window's
    safe-area insets (Window.safe_area_insets - a phone's status bar,
    notch and gesture bar), on top of its own padding, so nothing laid
    out inside it ends up underneath them. Zero on every desktop/web
    window, so harmless to leave on. Default False.


READING LAYOUT
-------------------------------------------------------------------------------

element.rect
    The element's position and size from the last layout pass, as a
    Layout(x, y, width, height), in the same units as its styles. Use it
    instead of `_layout`, which is the same rect in raw pixels (multiplied
    by the window's content_scale).


ANCHORS
-------------------------------------------------------------------------------

parent_anchor
    Selects the point in the parent used as the (0, 0) origin.

anchor
    Selects the point on the element placed at that origin.

    Both use:
        top_left, top_center, top_right
        center_left, center, center_right
        bottom_left, bottom_center, bottom_right

    Example:
        styles={
            "width": 100,
            "height": 100,
            "parent_anchor": "top_left",
            "anchor": "center"
        }

    With parent_anchor="top_left", the parent origin is its top-left
    corner. anchor="center" places the element's center at that origin.

    Setting only one of the two uses it for both: "parent_anchor":
    "top_right" alone pins the element's top-right corner to the parent's.

    x and y are offsets from the resulting anchor position (or from the
    normal flow position, for an element that isn't anchored). They take
    the same units as a size: "x": "10w" is 10% of the parent's width.

    Anchored children do not consume space in normal flow.

FLAGS
-------------------------------------------------------------------------------

An element has a set of flags, any number at once, and a style can be
overridden while a flag is set by giving the flag's name a dict of styles:

    styles={
        "base_color": GREY,
        "hover":    {"base_color": LIGHT_GREY},
        "pressed":  {"base_color": DARK_GREY},
        "selected": {"border_color": ACCENT, "border_width": 2},
    }

UIManager sets three of them from input:

    "hover"     the pointer is over the element (never on a touchscreen)
    "pressed"   the mouse button / finger went down on it and is still down
    "focused"   it's the text field keyboard input goes to

Any other name is the app's own, set with element.set_flag(name) /
set_flag(name, False) and read with has_flag(name):

    tab.selected = True                 # the "selected" flag
    track_row.set_flag("playing")       # styles["playing"] applies now

When several are set, their tables apply in this order, later winning:
the app's own flags (in the order they were set), "selected", "hover",
"focused", "pressed". "normal" applies only while no flag is set.

"clicked" (for pressed) and "selected" while focused are still honoured
from when an element had a single state, in which "selected" meant
focused - so a field styled {"selected": {...}} still shows it while
being typed into. element.state / set_state() / ElementStates are that
single-state form, kept for older code.


INTERACTION
-------------------------------------------------------------------------------

UIManager drives hit-testing against every element's computed `_layout`
each frame (topmost element under the cursor wins), and turns that into
state transitions plus the callbacks registered with `UIElement.on()`:

    "hover_enter" / "hover_exit"
        Cursor entered/left this element's rect. Also drives the
        "hover" state style automatically - no callback needed just to
        change appearance on hover.

    "press" / "release"
        Left mouse button went down/up while this element was hit.
        Also drives the "clicked" state style automatically.

    "click"
        Fired on release if the same element was still under the
        cursor - i.e. press-and-release, not press-and-drag-off.

    "submit"
        Fired on an editable element (see below) when Enter is
        pressed while it's focused. Called with the element's current
        text as its one argument.

Example:

    button.on("click", lambda: play_track(track))

on() adds a callback, alongside any already registered, and returns a
function that removes it again. To *replace* what an event does - a
"Follow"/"Unfollow" toggle re-wired every time it changes - set its
handler instead, which removes every earlier callback for that event:

    button.on_click = follow            # or set_handler("click", follow)
    button.on_click = unfollow          # follow no longer runs
    button.on_click = None              # nothing does

on_click, on_press, on_release, on_hover_enter, on_hover_exit and
on_submit exist as properties; set_handler(event, callback) works for
any event.

editable
    Marks this element as a text field. Clicking it focuses it (see
    the "selected"/FOCUSED state) and routes keyboard character/
    backspace/enter input into its "text" style. Clicking anywhere
    else clears focus.

        "editable": True

    Text input here is deliberately minimal - plain ASCII letters,
    digits, space and the common US-QWERTY punctuation keys, shifted
    per whether shift is held. No IME, dead keys, or non-US layout
    support; good enough for search boxes and short fields, not a
    general text editor.

secret
    Masks an editable element's drawn text with bullets - a password
    field. Only affects drawing: get_current_styles()["text"] (and a
    "submit" callback's argument) still carry the real, unmasked value.

        "editable": True,
        "secret": True

overflow
    Controls what happens when this element's children don't fit in
    its own box, along its `layout` direction - the CSS-like property
    name this was missing. One of:

        "visible" (default)
            Children draw past this element's own edges, uncontained -
            today's default behavior for every element that doesn't
            opt into anything else.

        "hidden"
            Clips children to this element's own rect (a scissor, so
            nothing draws outside it - see UIRenderer._draw_element),
            but does not scroll: content past the edge is just cut off,
            with no way to reach it via the mouse wheel or a scrollbar.

        "scroll"
            Clips *and* always shows a scrollbar along the scroll axis,
            even when the content already fits and there's nothing to
            scroll to - matching CSS's own "scroll" (as opposed to
            "auto"'s content-dependent visibility).

        "auto"
            Clips, scrolls, and shows a scrollbar *only* while the
            content actually overflows - the common case, and what
            every scrollable list in this app actually wants.

    Example:

        "overflow": "auto"

    The scroll offset is clamped every layout pass to the actual
    overflow (0 if children fit without scrolling), and persists
    across frames on the element itself - nothing else to wire up.
    Scrolling responds to both the mouse wheel and dragging the
    scrollbar thumb directly.

    "scroll": True is still accepted as an alias for "overflow": "auto"
    - every scrollable element from before "overflow" existed keeps
    working unchanged, it just also gets a real, draggable scrollbar
    drawn now instead of being wheel-only.

SCROLLBAR STYLES
-------------------------------------------------------------------------------

Only relevant on an element whose `overflow` is "scroll" or "auto".
The scrollbar itself is two real, ordinary UIElements (a track and a
thumb inside it) that this element manages internally - not something
app code has to build - so anything a UIElement can normally be styled
with (base_color, border_radius, border_width/color, and per-state
"hover"/"clicked" overrides included) works on them too, via:

    scrollbar_track
        Style dict merged over the default track appearance (a thin,
        mostly-invisible strip the thumb slides in).

    scrollbar_thumb
        Style dict merged over the default thumb appearance - give it
        a "hover" and/or "clicked" override here for the same kind of
        color-change-on-hover feedback a button gets.

    scrollbar_width
        Thickness of the bar, in pixels (default 8).

    scrollbar_margin
        Gap between the bar and this element's own edge, in pixels
        (default 2).

    scrollbar_min_thumb
        The thumb never gets shorter than this, in pixels (default
        24), so a very long list's thumb stays big enough to grab
        rather than shrinking to a sliver.

    Example - a thicker, brighter-on-hover scrollbar:

        styles={
            "overflow": "auto",
            "scrollbar_width": 12,
            "scrollbar_thumb": {
                "base_color": (0.4, 0.4, 0.4, 0.8),
                "border_radius": 6,
                "hover": {"base_color": (0.6, 0.6, 0.6, 0.9)},
            },
        }

    Drawn as an overlay (on top of content, not reserving space that
    shrinks it) along this element's right edge for a vertical layout,
    or bottom edge for a horizontal one.


ANIMATABLE STYLES
-------------------------------------------------------------------------------

Any numeric style can be animated using:

    element.set_style(
        "width",
        200,
        duration=0.5
    )

Strings containing numeric values can also be animated as long as their
non-numeric parts match.

Example:

    "50w" -> "100w"

is valid.

But:

    "50w" -> "100h"

is not compatible because the non-numeric parts differ.

===============================================================================
"""


def _safe_area_insets() -> tuple:
    """The window's (top, right, bottom, left) safe-area insets, in pixels -
    Window.safe_area_insets reports them in UI units."""
    window = get_service("window")
    insets = getattr(window, "safe_area_insets", None) if window is not None else None
    if not insets:
        return (0.0, 0.0, 0.0, 0.0)
    scale = window.content_scale or 1.0
    return tuple(inset * scale for inset in insets)


_text_size_cache: dict = {}


def measure_text(styles: dict) -> tuple | None:
    """(width, height) in pixels of an element's text - its "text" (or, for
    a "secret" field, the bullets drawn instead) in its font, size and
    weight - or None if there's nothing to measure it with (no font set, no
    text renderer running). Height is one line, so an empty field still
    gets the height of the text it will hold.

    What "auto" sizes an element with text and no children to - so a label
    or button fits its words without being given a size. Cached by
    font/weight/size/text, since layout asks every frame."""
    font_path = styles.get("font")
    if font_path is None:
        return None

    text = styles.get("text") or ""
    if styles.get("secret", False):
        text = "•" * len(text)
    weight = styles.get("font_weight", "regular")
    size = styles.get("font_size", 24) * _content_scale()

    key = (font_path, weight, size, text)
    cached = _text_size_cache.get(key)
    if cached is not None:
        return cached

    text_renderer = get_service("text_renderer")
    if text_renderer is None:
        return None
    from FreeBodyEngine.core.files.loaders.font import resolve_font  # lazy - see UIRenderer._draw_text
    font = resolve_font(font_path, weight=weight)
    if font is None:
        return None

    measured = (text_renderer.measure_text(font, text, size), (font.ascender - font.descender) * size)
    if len(_text_size_cache) > 4096:
        _text_size_cache.clear()
    _text_size_cache[key] = measured
    return measured


def parse_size(size, parent_layout: 'Layout', root_layout: 'Layout') -> int:
    """
    Convert a style size into pixels.

    Supported formats:

        200
            Fixed pixels.

        "200"
            Fixed pixels.

        "69w"
            69% of parent content width.

        "69h"
            69% of parent content height.

        "69ww"
            69% of root/window width.

        "69hw"
            69% of root/window height.

    "auto" is a valid *style* value (see the SIZE UNITS docs) but is
    never passed here - calculate_layout() and _measure_flow_extent() both
    special-case it first. Anything unrecognized warns and is treated as 0
    rather than raising: one malformed style shouldn't be able to crash
    the whole layout pass.
    """

    s = str(size).strip().lower()

    if not s:
        return 0

    #
    # Plain numeric value - scaled by the window's content_scale so a
    # fixed pixel count stays the same physical size across devices.
    #
    try:
        return int(float(s) * _content_scale())

    except ValueError:
        pass

    try:
        if s[-2:] in ("ww", "hw"):
            num = float(s[:-2])
            suffix = s[-2:]
        else:
            num = float(s[:-1])
            suffix = s[-1]
    except ValueError:
        warning(f'Could not parse size "{size}" - expected a number, or one of the w/h/ww/hw suffixes.')
        return 0

    if suffix == "w":
        return int(parent_layout.width * (num / 100.0))

    if suffix == "h":
        return int(parent_layout.height * (num / 100.0))

    if suffix == "ww":
        return int(root_layout.width * (num / 100.0))

    if suffix == "hw":
        return int(root_layout.height * (num / 100.0))

    warning(f'Could not parse size "{size}" - unknown unit suffix "{suffix}".')
    return 0


VALID_ALIGNS = {"start", "center", "end", "stretch"}
VALID_JUSTIFIES = {"start", "center", "end", "space_between"}


def _is_anchored(element) -> bool:
    # _has_own_style, not the merged styles: those always contain
    # "anchor"/"parent_anchor" because of DEFAULT_STYLES.
    return element._has_own_style("anchor") or element._has_own_style("parent_anchor")


def _is_visible(element) -> bool:
    return bool(element.get_current_styles().get("visible", True))


def _choice(value, valid: set, name: str) -> str:
    if value in valid:
        return value
    warning(f'Unknown {name} "{value}". Expected one of: {", ".join(sorted(valid))}')
    return "start"


def _grow_of(element) -> float:
    try:
        return max(0.0, float(element.get_current_styles().get("grow", 0) or 0))
    except (TypeError, ValueError):
        warning(f'Could not parse grow "{element.get_current_styles().get("grow")}" - expected a number.')
        return 0.0


def _translate(element, dx: float, dy: float):
    """Moves an already laid-out element and its whole subtree."""
    if not dx and not dy:
        return
    layout = element._layout
    layout.x += dx
    layout.y += dy
    for child in element.children.values():
        _translate(child, dx, dy)


def layout_flow(container_styles: dict, children: dict, root: 'RootElement',
                flow_area: 'Layout', anchor_area: 'Layout', layout_dir: str, gap: float):
    """Lays out a container's children - shared by RootElement and UIElement.

    Anchored children are placed against `anchor_area` (the content box)
    and take no part in the flow. Hidden ("visible": False) children are
    skipped entirely. The rest are stacked along `layout_dir` starting at
    `flow_area`'s origin (the content box, moved by any scroll offset):

        grow          each child's share of the space left along the
                      layout direction, added to its own size
        justify       where the children sit along the layout direction
                      when there's space left: start/center/end/
                      space_between
        align         where each child sits across it: start/center/end/
                      stretch (fill the cross axis, for a child with no
                      size of its own on that axis); align_self overrides
                      it per child

    The common case - no grow, justify and align at "start" - lays each
    child out once at its final position. Otherwise every child is laid out
    once at the content origin, then moved into place with its subtree.
    """
    if layout_dir not in ("vertical", "horizontal"):
        warning(f'Unknown layout direction "{layout_dir}". Expected "vertical" or "horizontal".')
        layout_dir = "vertical"
    vertical = layout_dir == "vertical"

    justify = _choice(container_styles.get("justify", "start"), VALID_JUSTIFIES, "justify")
    align = _choice(container_styles.get("align", "start"), VALID_ALIGNS, "align")

    flow = []
    for child in children.values():
        # The scrollbar track/thumb are positioned by their owner's
        # _update_scrollbar(), not by flow or anchoring.
        if getattr(child, "_is_scrollbar_part", False):
            continue
        if not _is_visible(child):
            child._layout = Layout(0, 0, 0, 0)
            continue
        if _is_anchored(child):
            child.calculate_layout(root, anchor_area)
            continue
        flow.append(child)

    if not flow:
        return

    grows = [_grow_of(child) for child in flow]
    aligns = []
    for child in flow:
        own = child.get_current_styles().get("align_self", "auto")
        aligns.append(align if own in (None, "auto") else _choice(own, VALID_ALIGNS, "align_self"))

    if justify == "start" and not any(grows) and all(a == "start" for a in aligns):
        offset = flow_area.y if vertical else flow_area.x
        for child in flow:
            if vertical:
                child.calculate_layout(root, Layout(flow_area.x, offset, flow_area.width, flow_area.height))
                offset += child._layout.height + gap
            else:
                child.calculate_layout(root, Layout(offset, flow_area.y, flow_area.width, flow_area.height))
                offset += child._layout.width + gap
        return

    main_key, cross_key = ("height", "width") if vertical else ("width", "height")
    main_extent = flow_area.height if vertical else flow_area.width
    cross_extent = flow_area.width if vertical else flow_area.height

    def main_of(child):
        return child._layout.height if vertical else child._layout.width

    def cross_of(child):
        return child._layout.width if vertical else child._layout.height

    def lay_out(child, main_size, child_align):
        forced = {}
        if main_size is not None:
            forced["forced_" + main_key] = main_size
        if child_align == "stretch" and not child._has_own_style(cross_key):
            forced["forced_" + cross_key] = cross_extent
        child.calculate_layout(root, flow_area, **forced)

    used = gap * (len(flow) - 1)
    bases = {}
    for child, grow, child_align in zip(flow, grows, aligns):
        if grow:
            # Its own size along the layout direction is where it grows
            # from (for "auto", what it would fit).
            bases[child] = child._measure_size(main_key, flow_area, root)
            used += bases[child]
        else:
            lay_out(child, None, child_align)
            used += main_of(child)

    leftover = main_extent - used
    total_grow = sum(grows)
    for child, grow, child_align in zip(flow, grows, aligns):
        if grow:
            lay_out(child, bases[child] + max(0.0, leftover) * grow / total_grow, child_align)

    free = max(0.0, leftover) if total_grow == 0 else 0.0
    position, between = 0.0, 0.0
    if justify == "center":
        position = free / 2
    elif justify == "end":
        position = free
    elif justify == "space_between" and len(flow) > 1:
        between = free / (len(flow) - 1)

    for child, child_align in zip(flow, aligns):
        spare = cross_extent - cross_of(child)
        cross = spare / 2 if child_align == "center" else spare if child_align == "end" else 0.0
        if vertical:
            _translate(child, cross, position)
        else:
            _translate(child, position, cross)
        position += main_of(child) + gap + between


class GenericElement(TreeBehaviour):
    """Base for anything that can parent `UIElement`s - shared by `RootElement`
    and `UIElement` itself so elements nest arbitrarily deep."""

    def __init__(self, tag: str = None):
        """Args:
            tag: Optional identifier for this element, not used by the layout/draw code itself.
        """
        self.children: dict[uuid.UUID, 'UIElement'] = {}
        self.tag = tag
        self._styles: dict[str, any] = {}

    def _raw_styles(self) -> dict:
        return self._styles

    def _set_raw_styles(self, styles: dict):
        self._styles = styles

    def add(self, element: 'UIElement') -> None:
        """Adds `element` as a child of this element."""
        element._initialize(self)

    def _remove(self, element_id: uuid.UUID) -> None:
        element = self.children.pop(element_id)
        element.parent = None

    def remove(self, element: 'UIElement') -> None:
        """Removes `element` from this element's children."""
        self._remove(element.id)

    def _draw(self):
        pass

class RootElement(GenericElement):
    """
    Root UI element.

    Supported styles:

        padding
        padding_left
        padding_right
        padding_top
        padding_bottom

        layout:
            "vertical"
            "horizontal"

        gap
    """

    def __init__(self, width: int, height: int, styles=None):
        """Args:
            width: Width of the root layout area (typically the window/framebuffer width), in pixels.
            height: Height of the root layout area (typically the window/framebuffer height), in pixels.
            styles: Root-level styles - see the style documentation above.
        """
        super().__init__()

        self.styles = styles  # copied by the setter - see UIElement.__init__
        self.layout = Layout(0, 0, width, height)

    @property
    def width(self) -> int:
        """Current root width, in pixels. A property reading straight from
        `self.layout` (the one place UIManager.resize() actually updates)
        rather than a separate stored value - `width`/`height` used to be
        their own plain attributes, set once at construction and never
        touched again, while `resize()` only ever updated `self.layout`'s
        copy. Every window resize after the first frame left this
        permanently stuck at whatever size the window happened to be at
        launch: any code reading `root.width`/`root.height` directly (a
        content area sizing itself to "the window height minus my
        header/footer," say) silently kept computing against a stale
        snapshot forever after, however many times the real window
        resized - exactly the shape of "layout looks right on launch, then
        the proportions are wrong forever after," which a tiling window
        manager (retiling on every window open/close) triggers constantly.
        A property means every existing read of `root.width`/`root.height`
        just starts seeing the live value with no call-site changes."""
        return self.layout.width

    @width.setter
    def width(self, value: int):
        self.layout.width = value

    @property
    def height(self) -> int:
        """See `width` - the same live-vs-stale fix, for height."""
        return self.layout.height

    @height.setter
    def height(self, value: int):
        self.layout.height = value

    def calculate_layout(self):
        """
        Calculate the root content area and recursively calculate
        the layout of all children.
        """

        styles = self._styles
        # Same units and content scaling as any element's padding/gap -
        # these used to go through int(), so "2w" raised and a plain
        # number wasn't scaled. The native root already did this.
        window_layout = self.layout

        def size(key, fallback):
            return parse_size(styles[key], window_layout, window_layout) if key in styles else fallback

        pad = size("padding", 0)

        pad_left = size("padding_left", pad)
        pad_right = size("padding_right", pad)
        pad_top = size("padding_top", pad)
        pad_bottom = size("padding_bottom", pad)

        if styles.get("safe_area", False):
            inset_top, inset_right, inset_bottom, inset_left = _safe_area_insets()
            pad_top += inset_top
            pad_right += inset_right
            pad_bottom += inset_bottom
            pad_left += inset_left

        content_x = self.layout.x + pad_left
        content_y = self.layout.y + pad_top

        content_w = max(0, self.width - pad_left - pad_right)
        content_h = max(0, self.height - pad_top - pad_bottom)

        layout_dir = styles.get("layout", "vertical")
        gap = size("gap", 0)

        root_content_layout = Layout(content_x, content_y, content_w, content_h)
        layout_flow(styles, self.children, self, root_content_layout, root_content_layout, layout_dir, gap)


class UIElement(ElementBehaviour, GenericElement):
    """
    Generic UI element.

    Supported styles:

    Sizing:
        width
        height

    Padding:
        padding
        padding_left
        padding_right
        padding_top
        padding_bottom

    Child layout:
        layout
        gap
        justify
        align

    As a child:
        grow
        align_self
        visible

    Positioning:
        parent_anchor
        anchor
        x
        y

    Text:
        text
            String to draw over the element via the engine's MSDF text
            pipeline. Empty (the default) draws nothing.

        font
            Path to a raw font file (e.g. "test.ttf"), resolved the same
            way any other asset path is - relative to the project's asset
            directory. Its MSDF atlas is generated and cached the first
            time it's used (see core/files/loaders/font.py's
            resolve_font()); no separate build step or `.fbfont` asset is
            required.

        font_size
            Text size in pixels.

        font_weight
            Selects a weight variant of `font` - either a name
            ("thin", "extralight", "light", "regular", "medium",
            "semibold", "bold", "extrabold", "black", plus the aliases
            "normal"/"book"/"heavy"/"demibold") or a CSS-style number
            100-900. Default is "regular"/400 (no change from `font`
            as given).

            Resolved as a sibling file next to `font` following the
            "{family}-{Weight}.ttf" naming convention (e.g. "bold" with
            font="JetBrainsMono-Regular.ttf" looks for
            "JetBrainsMono-Bold.ttf" beside it) - see
            core/files/loaders/font.py's resolve_font(). This selects a
            real, separately-authored font file; it doesn't synthesize
            bold/faux-bold from a single weight. If no matching file
            exists, warns once and falls back to `font` unchanged.

        text_color
            (r, g, b, a) text color, 0-1 per channel.

        text_align
            "left" (default), "center" or "right" - where the text sits
            within the element's padded content box when that box is
            wider than the text. Only matters for an element sized
            independently of its caption (a tab owning a third of a bar,
            a value aligned to a column's right edge); a shrink-wrapped
            button looks centered either way.

    State overrides:
        normal
        clicked
        hover
        selected
    """

    # Base appearance for the two internal UIElements every "scroll"/"auto"
    # overflow element manages (see _update_scrollbar()) - deliberately
    # understated (a thin, mostly-invisible track; a plain translucent grey
    # thumb) since these are meant to be restyled per-app via the
    # "scrollbar_track"/"scrollbar_thumb" style keys (see the SCROLLBAR
    # STYLES docs above), not to look finished on their own.
    _DEFAULT_SCROLLBAR_TRACK_STYLE = {
        "base_color": (0.0, 0.0, 0.0, 0.0),
        "border_radius": 0,
    }
    _DEFAULT_SCROLLBAR_THUMB_STYLE = {
        "base_color": (0.5, 0.5, 0.5, 0.5),
        "border_radius": 0,
        "hover": {"base_color": (0.65, 0.65, 0.65, 0.7)},
        "clicked": {"base_color": (0.8, 0.8, 0.8, 0.85)},
    }

    def __init__(self, tag: str = None, styles=None, style: 'Style' = None):
        """Args:
            tag: Optional identifier for this element, not used by the layout/draw code itself.
            styles: This element's styles - see the style documentation above.
            style: A shared ui.Style underneath `styles` - see the `style`
                property.
        """
        super().__init__(tag)

        # The shared Style layer (see the `style` property) - its live
        # merged dict, read by get_current_styles(), and the Style itself.
        self._style_base: dict = {}
        self._style = None

        self._flags: list[str] = []
        self._handlers: dict[str, Callable] = {}
        self._style_keys: list[str] = ["normal"]
        # An element's own copy (made by the `styles` setter, state tables
        # included). set_style() writes into it, and it used to be whatever
        # was passed - the `{}` default (one dict for every call) or a style
        # dict reused across elements - so styling one element restyled
        # every other element sharing it.
        self.styles = styles
        self.parent: GenericElement | None = None
        self.id = uuid.uuid4()
        self.animations: list[UIAnimation] = []
        self._layout = Layout(0, 0, 0, 0)
        self._scroll_offset = 0.0
        self._event_callbacks: dict[str, list[Callable]] = {}

        # Editable-field cursor state - see ui/manager.py's _on_key() (owns
        # moving/inserting/deleting at this index) and ui/renderer.py's
        # _draw_text() (owns drawing the caret at it, and keeping it in
        # view by adjusting _text_view_offset when it would otherwise
        # scroll outside the field). Meaningless on a non-editable element,
        # same as _scroll_offset is meaningless without "overflow" set -
        # cheap enough to just always have rather than conditionally
        # creating.
        self._cursor_index = 0
        self._text_view_offset = 0.0

        # get_current_styles() memoization - see that method's docstring
        # for why. Invalidated by the only two things that can change its
        # result: _set_style() (styles) and set_state() (state).
        self._styles_cache: dict[str, any] | None = None

        # Populated on demand by _update_scrollbar() the first time this
        # element's overflow actually needs a scrollbar - see that method
        # and the SCROLLBAR STYLES docs above. Left None otherwise so a
        # plain, non-scrolling element (the overwhelming majority) doesn't
        # pay for two extra UIElements it'll never use.
        self._scrollbar_track: 'UIElement | None' = None
        self._scrollbar_thumb: 'UIElement | None' = None

        if style is not None:
            self.style = style
        # Snapshot of this element's own scroll geometry, refreshed every
        # layout pass it's actually scrollable - read by UIManager while
        # dragging this element's thumb (see manager.py's _handle_mouse),
        # since the manager has no other way to know how a pixel of mouse
        # movement should translate into a scroll offset change.
        self._scroll_dir = "vertical"
        self._scroll_max = 0.0
        self._scroll_viewport_extent = 0.0
        self._scroll_content_extent = 0.0

    def _register(self, event: str, callback: Callable) -> None:
        self._event_callbacks.setdefault(event, []).append(callback)

    def off(self, event: str, callback: Callable) -> None:
        """Unregisters `callback` from `event`, if it was registered."""
        if callback in self._event_callbacks.get(event, ()):
            self._event_callbacks[event].remove(callback)

    def clear_event(self, event: str) -> None:
        """Removes every callback registered for `event` - see
        ElementBehaviour.clear()."""
        self._event_callbacks.pop(event, None)

    def _emit(self, event: str, *args) -> None:
        """Calls every callback registered for `event` via `on()`, in
        registration order. Copies the callback list first so a callback
        that itself calls on()/off() doesn't mutate the list mid-iteration."""
        for callback in list(self._event_callbacks.get(event, ())):
            callback(*args)

    def has_event(self, event: str) -> bool:
        """True if at least one callback is registered for `event` via
        on() - added alongside the native Node backend (ui/native_element.
        py), which can't safely expose _event_callbacks itself as a plain
        readable dict the way this pure-Python class does, so
        ui/manager.py's cursor-shape check uses this on both backends."""
        return bool(self._event_callbacks.get(event))

    def _initialize(self, parent: GenericElement):
        self.parent = parent
        self.parent.children[self.id] = self

    def get_parent(self) -> GenericElement | None:
        """The element this one was added to, or None - the same accessor
        the native backend has, which UIManager walks up through."""
        return self.parent

    def _invalidate_styles(self):
        self._styles_cache = None

    def _apply_style_keys(self, keys: list):
        self._style_keys = keys
        self._styles_cache = None

    def _has_own_style(self, key: str) -> bool:
        """
        True if `key` was explicitly set on this element - either at
        the top level, or inside the currently active state's
        override block.

        This is deliberately different from checking
        get_current_styles(): that merged dict always contains every
        DEFAULT_STYLES key (e.g. "anchor", "parent_anchor"), so
        checking presence there can never distinguish "the user set
        this" from "this is just the default".
        """

        for styles in (self._styles, self._style_base):
            if key in styles:
                return True
            for name in self._style_keys:
                table = styles.get(name)
                if isinstance(table, dict) and key in table:
                    return True

        return False

    def get_overflow(self, styles: dict = None) -> str:
        """Resolves the effective "overflow" mode - "visible", "hidden",
        "scroll", or "auto" - taking the "scroll": True legacy alias into
        account (see the OVERFLOW docs above). Checked via _has_own_style
        rather than the merged dict for the same reason anchor detection
        is: DEFAULT_STYLES always contains "overflow": "visible", so a
        plain presence check could never tell "explicitly set" apart from
        "just the default" - and an explicit "overflow" always wins over
        the older "scroll" flag if an element somehow has both."""
        if styles is None:
            styles = self.get_current_styles()

        if self._has_own_style("overflow"):
            value = styles.get("overflow", "visible")
            if value not in self.VALID_OVERFLOWS:
                warning(f'Unknown overflow "{value}". Expected one of: {", ".join(sorted(self.VALID_OVERFLOWS))}')
                return "visible"
            return value

        if styles.get("scroll", False):
            return "auto"

        return "visible"

    def get_current_styles(self) -> dict[str, any]:
        """
        Merge base styles with state-specific styles.

        Example:

            {
                "width": 100,

                "hover": {
                    "width": 120
                }
            }

        When hovered, width becomes 120.

        Memoized: this merge (a fresh dict allocation plus 2-3 dict scans)
        used to run on every single call, and every element gets called
        several times per frame - once each from calculate_layout(),
        _measure_flow_extent() (once per auto-sized parent's pass over its
        children), and _draw_element(), at minimum. On a view with a few
        hundred elements (a long playlist/search-results list, each row
        itself several elements) that's thousands of redundant dict
        allocations a frame for output that only ever changes when
        _set_style() or set_state() actually runs - the real, measured
        cause of this UI feeling sluggish on any list-heavy view. Cached
        here instead; both mutation points below clear the cache.
        """

        if self._styles_cache is not None:
            return self._styles_cache

        styles = self._styles
        base = self._style_base
        current_styles = dict(self.DEFAULT_STYLES)
        current_styles.update(base)
        current_styles.update(styles)

        for name in self._style_keys:
            for layer in (base, styles):
                table = layer.get(name)
                if isinstance(table, dict):
                    current_styles.update(table)

        self._styles_cache = current_styles
        return current_styles

    def _parse_size(self, size, parent_layout: Layout, root_layout: Layout) -> int:
        """Converts a style size into pixels - see parse_size()."""
        return parse_size(size, parent_layout, root_layout)

    def get_style(self, name: str):
        """Gets the raw, un-merged value of style `name` set directly on this
        element (not through `get_current_styles()` - so no `DEFAULT_STYLES`
        fallback and no state-override merging), warning if it isn't set."""
        if name in self.styles:
            return self.styles[name]

        warning(f'Style "{name}" does not exist.')

    def _set_style(self, name: str, val: any):
        self._styles[name] = val
        self._styles_cache = None

    def _resolve_anchors(self, styles: dict) -> tuple[str, str]:
        """(parent_anchor, anchor) for an anchored element. Setting only one
        of the two uses it for both - "parent_anchor": "top_left" alone
        pins this element's top-left corner to the parent's, rather than
        pairing it with DEFAULT_STYLES' "bottom_left" anchor and putting the
        element just above the parent, off its edge."""
        own_parent = self._has_own_style("parent_anchor")
        own_anchor = self._has_own_style("anchor")
        parent_anchor = styles.get("parent_anchor", "center")
        anchor = styles.get("anchor", "center")
        if own_parent and not own_anchor:
            anchor = parent_anchor
        elif own_anchor and not own_parent:
            parent_anchor = anchor
        return parent_anchor, anchor

    def _apply_anchor(
        self,
        parent_anchor: str,
        anchor: str,
        container: Layout,
        x: int = 0,
        y: int = 0
    ):
        parent_anchor = str(parent_anchor).lower()
        anchor = str(anchor).lower()

        if parent_anchor not in self.VALID_ANCHORS:
            warning(
                f'Unknown parent anchor "{parent_anchor}". '
                f'Expected one of: {", ".join(sorted(self.VALID_ANCHORS))}'
            )
            return

        if anchor not in self.VALID_ANCHORS:
            warning(
                f'Unknown anchor "{anchor}". '
                f'Expected one of: {", ".join(sorted(self.VALID_ANCHORS))}'
            )
            return

        positions = {
            "top_left": (-1, 1),
            "top_center": (0, 1),
            "top_right": (1, 1),
            "center_left": (-1, 0),
            "center": (0, 0),
            "center_right": (1, 0),
            "bottom_left": (-1, -1),
            "bottom_center": (0, -1),
            "bottom_right": (1, -1),
        }

        parent_x, parent_y = positions[parent_anchor]
        anchor_x, anchor_y = positions[anchor]

        #
        # origin_x / origin_y is the point *inside the parent* that the
        # chosen anchor point of this element will be placed on.
        #
        origin_x = container.x + ((parent_x + 1) / 2) * container.width
        origin_y = container.y + ((1 - parent_y) / 2) * container.height

        #
        # self._layout.x / self._layout.y are the element's top-left
        # corner. To place the chosen anchor point (left/center/right,
        # top/center/bottom) exactly on origin, the top-left corner has
        # to be offset from origin by the fraction of the element's own
        # size that lies between its top-left corner and that anchor
        # point:
        #
        #   anchor_x == -1 (left)   -> offset 0        (left edge IS the anchor point)
        #   anchor_x ==  0 (center) -> offset width / 2
        #   anchor_x ==  1 (right)  -> offset width
        #
        # which is ((anchor_x + 1) / 2) * width. The previous formula
        # (anchor_x * width / 2) used the wrong scale and sign, so every
        # anchor except "center_left"/"center_right" placed the element
        # in the wrong spot.
        #
        self._layout.x = int(origin_x - ((anchor_x + 1) / 2) * self._layout.width + x)
        self._layout.y = int(origin_y - ((1 - anchor_y) / 2) * self._layout.height + y)

    def _padding(self, styles: dict, parent_layout: Layout, root: 'RootElement') -> tuple:
        """(left, right, top, bottom) padding in pixels. A side that isn't
        set uses "padding" - already in pixels, so not run through
        _parse_size() a second time (which scaled it by content_scale
        twice)."""
        pad = self._parse_size(styles.get("padding", 0), parent_layout, root.layout)
        return tuple(
            self._parse_size(styles[key], parent_layout, root.layout) if key in styles else pad
            for key in ("padding_left", "padding_right", "padding_top", "padding_bottom")
        )

    def _flow_children(self) -> list:
        return [
            child for child in self.children.values()
            if not _is_anchored(child) and not getattr(child, "_is_scrollbar_part", False) and _is_visible(child)
        ]

    def _measure_size(self, key: str, parent_layout: Layout, root: 'RootElement') -> float:
        """This element's size along `key` ("width" or "height") without
        laying it out: its own size style, or for "auto" what it would fit -
        its children, measured the same way (so "auto" inside "auto" works),
        or with none, its text. What a parent's "auto" size, scroll range
        and grow measure their children with."""
        styles = self.get_current_styles()
        value = styles.get(key, 0)
        if value != "auto":
            return self._parse_size(value, parent_layout, root.layout)

        left, right, top, bottom = self._padding(styles, parent_layout, root)
        padding = left + right if key == "width" else top + bottom

        children = self._flow_children()
        if not children:
            text_size = measure_text(styles)
            if text_size is None:
                return padding
            return (text_size[0] if key == "width" else text_size[1]) + padding

        # The content box of an "auto" element isn't known yet - the same
        # zero-sized box calculate_layout() measures its children against.
        content = Layout(0, 0, 0, 0)
        sizes = [child._measure_size(key, content, root) for child in children]
        along = (key == "height") == (styles.get("layout", "vertical") == "vertical")
        if along:
            gap = self._parse_size(styles.get("gap", 0), content, root.layout)
            return sum(sizes) + gap * (len(sizes) - 1) + padding
        return max(sizes) + padding

    def _has_flow_children(self) -> bool:
        return any(
            not _is_anchored(child) and not getattr(child, "_is_scrollbar_part", False) and _is_visible(child)
            for child in self.children.values()
        )

    def _measure_flow_extent(self, content_layout: Layout, root: 'RootElement', layout_dir: str, gap: float) -> float:
        """Sum of non-anchored children's own size along `layout_dir`, plus
        the gaps between them - shared by "auto" sizing and "scroll"
        clamping, both of which need "how much space would my children
        take up if I just laid them out." Each child is measured without
        being laid out (see _measure_size()) - an "auto" child used to be
        given last frame's size instead, so anything nested in "auto"s was
        wrong on its first frame."""
        total_extent = 0.0
        seen_first = False

        for child in self.children.values():
            child_anchored = (
                child._has_own_style("anchor") or
                child._has_own_style("parent_anchor")
            )
            # The scrollbar track (see _update_scrollbar()) is real content
            # of this element in the sense that it's a real child, but it's
            # not part of what's being scrolled - it's the control *for*
            # scrolling, positioned manually rather than through flow/
            # anchor, and must never count toward "how much space would my
            # children take up" (that would make an element's own overflow
            # measurement depend on whether it has a scrollbar yet, which
            # depends on that same measurement - a feedback loop).
            if child_anchored or getattr(child, "_is_scrollbar_part", False) or not _is_visible(child):
                continue

            extent = child._measure_size("height" if layout_dir == "vertical" else "width", content_layout, root)

            if seen_first:
                total_extent += gap
            total_extent += extent
            seen_first = True

        return total_extent

    def _measure_cross_extent(self, content_layout: Layout, root: 'RootElement', axis: str) -> float:
        """Largest non-anchored child's own size along `axis` ("vertical"
        for height, "horizontal" for width) - the cross-axis counterpart
        to _measure_flow_extent, used for "auto" on the axis a layout
        *doesn't* stack along. Same exclusions."""
        largest = 0.0
        key = "height" if axis == "vertical" else "width"

        for child in self.children.values():
            if (child._has_own_style("anchor") or child._has_own_style("parent_anchor")
                    or getattr(child, "_is_scrollbar_part", False) or not _is_visible(child)):
                continue

            extent = child._measure_size(key, content_layout, root)
            largest = max(largest, extent)

        return largest

    def calculate_layout(self, root: 'RootElement', parent_layout: Layout = None,
                         forced_width: float = None, forced_height: float = None):
        """
        Calculate this element's size and position, then recursively
        calculate the layout of its children.

        `forced_width`/`forced_height` replace the size this element's own
        styles would give it - how the parent's flow layout applies "grow"
        and "align": "stretch" (see layout_flow()).
        """

        styles = self.get_current_styles()

        #
        # Determine available parent area.
        #
        if parent_layout is None:
            parent_layout = root.layout

        #
        # Size. "auto" (see the SIZE UNITS docs) can't be resolved until
        # children are measured, which itself needs the *other* axis
        # already resolved (a vertical auto-height list still needs its
        # own width settled first, so a "100w" child measures against a
        # real number) - so an auto dimension is deferred (left at 0 here)
        # and only actually resolved further down, after content_layout
        # exists, via _measure_flow_extent().
        #
        layout_dir = styles.get("layout", "vertical")
        width_style = styles.get("width", "0")
        height_style = styles.get("height", "0")
        auto_width = width_style == "auto" and forced_width is None
        auto_height = height_style == "auto" and forced_height is None

        if forced_width is not None:
            self._layout.width = forced_width
        else:
            self._layout.width = 0 if auto_width else self._parse_size(
                width_style, parent_layout, root.layout
            )

        if forced_height is not None:
            self._layout.height = forced_height
        else:
            self._layout.height = 0 if auto_height else self._parse_size(
                height_style, parent_layout, root.layout
            )

        pad_left, pad_right, pad_top, pad_bottom = self._padding(styles, parent_layout, root)

        #
        # Resolve any deferred "auto" dimension - using a *position-less*
        # content box (real width/height, but x/y at the origin) since
        # _measure_flow_extent only ever reads a content box's width/
        # height (for a percentage-sized child, or a percentage gap right
        # below), never its position. This has to happen *before* this
        # element's own x/y (and anchor placement especially) are resolved
        # - see the Size comment above for why "auto" can't resolve any
        # earlier than this, and the docs on _apply_anchor(): anchor
        # placement (unlike plain flow position) is a function of this
        # element's own width/height, e.g. "center" placing this element's
        # own midpoint on the origin. Anchoring against a still-deferred
        # "auto" size (0, until resolved) used to place the anchor point
        # correctly for a box of height/width 0, then leave it there even
        # once the real, much larger size was resolved a few lines later -
        # every anchored *and* "auto"-sized element (a popup that sizes to
        # its own content, say) rendered with its top-left corner sitting
        # where its *center* should have been, the rest of its real size
        # just spilling downward/rightward past that point instead of
        # actually being centered on it.
        #
        content_w = max(0, self._layout.width - pad_left - pad_right)
        content_h = max(0, self._layout.height - pad_top - pad_bottom)
        gap = self._parse_size(styles.get("gap", 0), Layout(0, 0, content_w, content_h), root.layout)

        if auto_width or auto_height:
            measured_extent = self._measure_flow_extent(Layout(0, 0, content_w, content_h), root, layout_dir, gap)

            if auto_height and layout_dir == "vertical":
                self._layout.height = measured_extent + pad_top + pad_bottom
                content_h = max(0, self._layout.height - pad_top - pad_bottom)
            elif auto_width and layout_dir == "horizontal":
                self._layout.width = measured_extent + pad_left + pad_right
                content_w = max(0, self._layout.width - pad_left - pad_right)

            # "auto" on the cross axis (height:auto under a horizontal
            # layout, e.g. a row of thumbnail + text column) fits to the
            # tallest/widest child instead of the flow-summed extent.
            if auto_height and layout_dir != "vertical":
                cross = self._measure_cross_extent(Layout(0, 0, content_w, content_h), root, "vertical")
                self._layout.height = cross + pad_top + pad_bottom
                content_h = max(0, self._layout.height - pad_top - pad_bottom)
            if auto_width and layout_dir == "vertical":
                cross = self._measure_cross_extent(Layout(0, 0, content_w, content_h), root, "horizontal")
                self._layout.width = cross + pad_left + pad_right
                content_w = max(0, self._layout.width - pad_left - pad_right)

            # No children to fit - fit the element's own text instead.
            if not self._has_flow_children():
                text_size = measure_text(styles)
                if text_size is not None:
                    if auto_width:
                        self._layout.width = text_size[0] + pad_left + pad_right
                        content_w = max(0, self._layout.width - pad_left - pad_right)
                    if auto_height:
                        self._layout.height = text_size[1] + pad_top + pad_bottom
                        content_h = max(0, self._layout.height - pad_top - pad_bottom)

        #
        # Default flow position.
        #
        self._layout.x = parent_layout.x
        self._layout.y = parent_layout.y

        #
        # Optional anchor positioning. Checked via _has_own_style
        # rather than the merged `styles` dict computed above, since
        # that merged result always contains "anchor"/"parent_anchor"
        # because of DEFAULT_STYLES - checking presence there would
        # always be true.
        #
        anchored = (
            self._has_own_style("anchor") or
            self._has_own_style("parent_anchor")
        )

        # Same units as a size ("10w" is 10% of the parent's width), and
        # content-scaled the same way - a plain multiply here used to raise
        # on any string.
        x_offset = self._parse_size(styles.get("x", 0), parent_layout, root.layout)
        y_offset = self._parse_size(styles.get("y", 0), parent_layout, root.layout)

        if anchored:
            parent_anchor, anchor = self._resolve_anchors(styles)
            self._apply_anchor(
                parent_anchor,
                anchor,
                parent_layout,
                x_offset,
                y_offset
            )
        else:
            self._layout.x += x_offset
            self._layout.y += y_offset

        #
        # Calculate this element's content rectangle - only now, using
        # this element's final x/y (anchor-resolved, if applicable) and
        # final width/height ("auto"-resolved, if applicable).
        #
        content_x = self._layout.x + pad_left
        content_y = self._layout.y + pad_top
        content_layout = Layout(content_x, content_y, content_w, content_h)

        child_offset_x = content_x
        child_offset_y = content_y

        #
        # Scrolling: clamp the offset to actual overflow, measured the
        # same way "auto" sizing measures children (see
        # _measure_flow_extent) - scroll and auto-size are mutually
        # exclusive uses in practice (scrolling means "clip to a fixed
        # size", auto means "grow to fit"), but nothing stops both styles
        # being set at once, so this runs independently either way.
        #
        overflow = self.get_overflow(styles)
        self._scroll_dir = layout_dir

        if overflow in ("scroll", "auto"):
            total_extent = self._measure_flow_extent(content_layout, root, layout_dir, gap)
            viewport_extent = content_h if layout_dir == "vertical" else content_w
            max_scroll = max(0.0, total_extent - viewport_extent)
            self._scroll_offset = max(0.0, min(self._scroll_offset, max_scroll))

            self._scroll_max = max_scroll
            self._scroll_viewport_extent = viewport_extent
            self._scroll_content_extent = total_extent

            if layout_dir == "vertical":
                child_offset_y -= self._scroll_offset
            else:
                child_offset_x -= self._scroll_offset
        else:
            # "hidden" clips (see the scissor logic in
            # UIRenderer._draw_element) but never actually offsets content -
            # there's no wheel/scrollbar path to reach the clipped-off part,
            # unlike "scroll"/"auto".
            self._scroll_offset = 0.0
            self._scroll_max = 0.0
            self._scroll_viewport_extent = content_h if layout_dir == "vertical" else content_w
            self._scroll_content_extent = self._scroll_viewport_extent

        layout_flow(styles, self.children, root,
                    Layout(child_offset_x, child_offset_y, content_w, content_h),
                    content_layout, layout_dir, gap)

        if overflow in ("scroll", "auto"):
            self._update_scrollbar(styles, overflow, layout_dir, content_x, content_y, content_w, content_h)
        elif self._scrollbar_track is not None:
            # No longer scrollable (overflow changed under it, or content
            # stopped overflowing) - zero out rather than destroy, so
            # nothing draws or hit-tests here without rebuilding the
            # elements if it becomes scrollable again later.
            self._scrollbar_track._layout = Layout(0, 0, 0, 0)
            self._scrollbar_thumb._layout = Layout(0, 0, 0, 0)

    def _update_scrollbar(
        self, styles: dict, overflow: str, layout_dir: str,
        content_x: float, content_y: float, content_w: float, content_h: float,
    ):
        """Creates (once) and repositions (every call) this element's
        scrollbar track+thumb - see the SCROLLBAR STYLES docs above.

        Deliberately two real UIElements rather than a special-cased draw
        call: adding them to `self.children` (thumb nested inside track)
        means UIRenderer's draw traversal and UIManager's hit-test/hover/
        click dispatch already reach them for free, with zero changes
        needed in either - the only things that *do* need to know about
        them are calculate_layout()/_measure_flow_extent() (skip them via
        `_is_scrollbar_part`, see above) and UIManager's drag handling
        (find them via `_is_scrollbar_thumb`, see manager.py)."""
        first_time = self._scrollbar_track is None

        if first_time:
            track = UIElement(None)
            thumb = UIElement(None)
            track._is_scrollbar_part = True
            thumb._is_scrollbar_part = True
            track._is_scrollbar_track = True
            thumb._is_scrollbar_thumb = True
            thumb._scrollbar_owner = self
            self.add(track)
            track.add(thumb)
            self._scrollbar_track = track
            self._scrollbar_thumb = thumb

            def on_track_click():
                # Only reached for a click that misses the thumb (a click
                # that hits the thumb resolves to the thumb itself, the
                # more specific hit - see UIManager._hit_test) - jumps
                # straight to the clicked fraction of the track rather
                # than paging, the more predictable of the two for a
                # thumb that's usually a large fraction of the track
                # anyway in a UI this size.
                mouse = get_service('mouse')
                if self._scroll_dir == "vertical":
                    click_pos = mouse.position.y - track._layout.y
                    available = max(1.0, track._layout.height - thumb._layout.height)
                else:
                    click_pos = mouse.position.x - track._layout.x
                    available = max(1.0, track._layout.width - thumb._layout.width)
                fraction = max(0.0, min(1.0, click_pos / available))
                self._scroll_offset = fraction * self._scroll_max

            track.on("click", on_track_click)

        track = self._scrollbar_track
        thumb = self._scrollbar_thumb

        # "auto" only actually shows the bar once there's real overflow to
        # scroll to - "scroll" always shows it, per the OVERFLOW docs.
        if overflow == "auto" and self._scroll_max <= 0:
            track._layout = Layout(0, 0, 0, 0)
            thumb._layout = Layout(0, 0, 0, 0)
            return

        track.styles = {**self._DEFAULT_SCROLLBAR_TRACK_STYLE, **styles.get("scrollbar_track", {})}
        thumb.styles = {**self._DEFAULT_SCROLLBAR_THUMB_STYLE, **styles.get("scrollbar_thumb", {})}

        # Raw pixel styles read directly here bypass _parse_size (where
        # content_scale normally applies - see Window.content_scale) so
        # each needs its own scaling, same reasoning as
        # UIRenderer._content_scale's callers.
        window = get_service("window")
        scale = window.content_scale if window is not None else 1.0
        width = styles.get("scrollbar_width", 8) * scale
        margin = styles.get("scrollbar_margin", 2) * scale
        min_thumb = styles.get("scrollbar_min_thumb", 24) * scale

        viewport = self._scroll_viewport_extent
        content_extent = self._scroll_content_extent
        ratio = (viewport / content_extent) if content_extent > 0 else 1.0
        fraction = (self._scroll_offset / self._scroll_max) if self._scroll_max > 0 else 0.0

        if layout_dir == "vertical":
            track_x = content_x + content_w - width - margin
            track_y = content_y
            track_w, track_h = width, content_h

            thumb_h = max(min_thumb, min(track_h, track_h * ratio))
            travel = max(0.0, track_h - thumb_h)
            thumb._layout = Layout(track_x, track_y + fraction * travel, width, thumb_h)
        else:
            track_x = content_x
            track_y = content_y + content_h - width - margin
            track_w, track_h = content_w, width

            thumb_w = max(min_thumb, min(track_w, track_w * ratio))
            travel = max(0.0, track_w - thumb_w)
            thumb._layout = Layout(track_x + fraction * travel, track_y, thumb_w, width)

        track._layout = Layout(track_x, track_y, track_w, track_h)
