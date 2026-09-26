from dataclasses import dataclass
import uuid
from enum import Enum
from typing import Callable
from FreeBodyEngine.graphics.color import Color
from FreeBodyEngine.math import Curve, Linear
from FreeBodyEngine import warning, delta, get_service
import re


"""
===============================================================================
UI STYLE DOCUMENTATION
===============================================================================

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

    A child that's itself "auto" along the same axis can't be
    measured without laying it out for real first, so it's treated as
    contributing 0 rather than recursing indefinitely - auto-inside-
    auto (on the same axis) isn't supported.


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

    x and y are offsets from the resulting anchor position.

    Anchored children do not consume space in normal flow.

STATE STYLES
-------------------------------------------------------------------------------

Styles can also be overridden based on the element's state.

Available state names:

    "normal"
    "clicked"
    "hover"
    "selected"

Example:

    styles={
        "width": 100,
        "height": 50,

        "hover": {
            "width": 120
        },

        "clicked": {
            "height": 40
        }
    }

State-specific values override the normal values returned by
get_current_styles().


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

Registered callbacks stay registered until off()/clear() removes them,
including across re-renders of the same element - re-running the same
on() call (e.g. to reflect new state on a "Follow"/"Unfollow" toggle)
adds a second, third, ... callback rather than replacing the first.
clear(event) removes every callback on `event` at once, for exactly
that "about to re-attach the current handler" case.

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


class GenericElement:
    """Base for anything that can parent `UIElement`s - shared by `RootElement`
    and `UIElement` itself so elements nest arbitrarily deep."""

    def __init__(self, tag: str = None):
        """Args:
            tag: Optional identifier for this element, not used by the layout/draw code itself.
        """
        self.children: dict[uuid.UUID, 'UIElement'] = {}
        self.tag = tag
        self.styles: dict[str, any] = {}

    def add(self, element: 'UIElement') -> None:
        """Adds `element` as a child of this element."""
        element._initialize(self)

    def _remove(self, element_id: uuid.UUID) -> None:
        del self.children[element_id]

    def remove(self, element: 'UIElement') -> None:
        """Removes `element` from this element's children."""
        self._remove(element.id)

    def _draw(self):
        pass

    def _update(self):
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

    def __init__(self, width: int, height: int, styles={}):
        """Args:
            width: Width of the root layout area (typically the window/framebuffer width), in pixels.
            height: Height of the root layout area (typically the window/framebuffer height), in pixels.
            styles: Root-level styles - see the style documentation above.
        """
        super().__init__()

        self.styles = styles
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

    def set_styles(self, styles: dict[str, any]):
        """Replaces the root's styles wholesale."""
        self.styles = styles

    def calculate_layout(self):
        """
        Calculate the root content area and recursively calculate
        the layout of all children.
        """

        styles = self.styles

        pad = int(styles.get("padding", 0))

        pad_left = int(styles.get("padding_left", pad))
        pad_right = int(styles.get("padding_right", pad))
        pad_top = int(styles.get("padding_top", pad))
        pad_bottom = int(styles.get("padding_bottom", pad))

        content_x = self.layout.x + pad_left
        content_y = self.layout.y + pad_top

        content_w = max(0, self.width - pad_left - pad_right)
        content_h = max(0, self.height - pad_top - pad_bottom)

        layout_dir = styles.get("layout", "vertical")
        gap = int(styles.get("gap", 0))

        child_offset_x = content_x
        child_offset_y = content_y

        root_content_layout = Layout(content_x, content_y, content_w, content_h)

        for child in self.children.values():

            #
            # Checked via _has_own_style rather than
            # get_current_styles(): the merged result always contains
            # "anchor"/"parent_anchor" because of DEFAULT_STYLES, so
            # checking presence there would always be true and this
            # check would never distinguish an anchored child from a
            # non-anchored one - including one anchored only through
            # a state override (e.g. `"hover": {"anchor": ...}`).
            #
            anchored = (
                child._has_own_style("anchor") or
                child._has_own_style("parent_anchor")
            )

            #
            # Anchored elements use the entire root content area as their
            # positioning area.
            #
            # Normal elements use the current flow position.
            #
            if anchored:
                child.calculate_layout(self, root_content_layout)

            else:
                child_layout = Layout(child_offset_x, child_offset_y, content_w, content_h)
                child.calculate_layout(self, child_layout)

                #
                # Only non-anchored children participate in normal flow.
                #
                if layout_dir == "vertical":
                    child_offset_y += child._layout.height + gap

                elif layout_dir == "horizontal":
                    child_offset_x += child._layout.width + gap

                else:
                    warning(
                        f'Unknown layout direction "{layout_dir}". '
                        f'Expected "vertical" or "horizontal".'
                    )


class ElementStates(Enum):
    """The interaction states a `UIElement` can be in, matching the state-style
    override keys documented above (note `FOCUSED`'s value is `"selected"`, not `"focused"`)."""
    NORMAL = "normal"
    CLICKED = "clicked"
    HOVER = "hover"
    FOCUSED = "selected"


@dataclass
class Layout:
    """A computed screen-space rectangle: top-left `(x, y)` plus `width`/`height`, in pixels."""
    x: int
    y: int
    width: int
    height: int


class UIElement(GenericElement):
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

    State overrides:
        normal
        clicked
        hover
        selected
    """

    VALID_ANCHORS = {
        "top_left", "top_center", "top_right",
        "center_left", "center", "center_right",
        "bottom_left", "bottom_center", "bottom_right",
    }

    VALID_OVERFLOWS = {"visible", "hidden", "scroll", "auto"}

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

    DEFAULT_STYLES = {
        "width": 0,
        "height": 0,
        "padding": 0,
        "layout": "vertical",
        "gap": 0,
        "x": 0,
        "y": 0,
        "parent_anchor": "center",
        "anchor": "bottom_left",

        # Transparent, not opaque white - matching how every other UI
        # system defaults a plain container's background, and so a
        # layout-only wrapper (a row/column that just positions children)
        # doesn't render as a surprise solid box the moment it's given a
        # concrete width/height for layout purposes.
        "base_color": (0.0, 0.0, 0.0, 0.0),
        "border_radius": 0,
        "border_width": 0,
        "border_color": (0.0, 0.0, 0.0, 1.0),
        "image": None,

        "text": "",
        "font": None,
        "font_size": 24,
        "font_weight": "regular",
        "text_color": (1.0, 1.0, 1.0, 1.0),

        "editable": False,
        "secret": False,

        # "scroll" predates "overflow" and is kept only as a back-compat
        # alias for "overflow": "auto" (see get_overflow()) - every element
        # written against the old boolean keeps working unchanged.
        "scroll": False,
        "overflow": "visible",
        "scrollbar_width": 8,
        "scrollbar_margin": 2,
        "scrollbar_min_thumb": 24,
        "scrollbar_track": {},
        "scrollbar_thumb": {},
    }

    def __init__(self, tag: str = None, styles={}):
        """Args:
            tag: Optional identifier for this element, not used by the layout/draw code itself.
            styles: This element's styles - see the style documentation above.
        """
        super().__init__(tag)

        self.state = ElementStates.NORMAL
        self.styles: dict[str, any] = styles
        self.parent: GenericElement
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
        # Snapshot of this element's own scroll geometry, refreshed every
        # layout pass it's actually scrollable - read by UIManager while
        # dragging this element's thumb (see manager.py's _handle_mouse),
        # since the manager has no other way to know how a pixel of mouse
        # movement should translate into a scroll offset change.
        self._scroll_dir = "vertical"
        self._scroll_max = 0.0
        self._scroll_viewport_extent = 0.0
        self._scroll_content_extent = 0.0

    def on(self, event: str, callback: Callable) -> None:
        """Registers `callback` to run when `event` fires on this element -
        "hover_enter", "hover_exit", "press", "release", "click", or
        "submit" (editable elements only) - see the INTERACTION style docs
        above. Multiple callbacks may be registered for the same event."""
        self._event_callbacks.setdefault(event, []).append(callback)

    def off(self, event: str, callback: Callable) -> None:
        """Unregisters `callback` from `event`, if it was registered."""
        if callback in self._event_callbacks.get(event, ()):
            self._event_callbacks[event].remove(callback)

    def clear(self, event: str) -> None:
        """Removes every callback registered for `event` via on() - for
        re-rendering a element whose behavior changes with some state (a
        follow button toggling between "Follow"/"Unfollow", say) without
        accumulating a duplicate callback on it every time."""
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

    def scroll_by(self, delta_px: float) -> None:
        """Adjusts this element's scroll offset by `delta_px` (only has any
        visible effect if this element's "scroll" style is on). Clamped to
        the valid range on the next layout pass, so over-scrolling here just
        settles back to the nearest edge next frame rather than needing to
        be clamped here against content it hasn't measured yet."""
        self._scroll_offset += delta_px

    def _initialize(self, parent: GenericElement):
        self.parent = parent
        self.parent.children[self.id] = self

    def set_state(self, state: ElementStates) -> None:
        """
        Transition this element to a new interaction state (normal,
        hover, clicked, selected). This is the only place self.state
        should be assigned from outside the class - input handling
        (mouse-over/click detection against self._layout) should call
        this rather than setting element.state directly, so behavior
        stays consistent if this method grows validation/callbacks
        later.
        """

        if not isinstance(state, ElementStates):
            warning(f'set_state expected an ElementStates, got {type(state)}.')
            return

        self.state = state
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

        if key in self.styles:
            return True

        state_name = self.state.value

        if state_name in self.styles and key in self.styles[state_name]:
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

        current_styles = dict(self.DEFAULT_STYLES)
        current_styles.update(self.styles)

        state_name = self.state.value

        if state_name in self.styles:
            for k, v in self.styles[state_name].items():
                current_styles[k] = v

        self._styles_cache = current_styles
        return current_styles

    def _parse_size(self, size, parent_layout: Layout, root_layout: Layout) -> int:
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
        never passed to this method - calculate_layout() and
        _measure_flow_extent() both special-case it before ever calling
        _parse_size(). Reaching here with "auto" (or any other string this
        doesn't recognize) is always a caller bug, not a legitimate size -
        warned and treated as 0 rather than raising, consistent with how
        the rest of this class handles bad style input (see
        _apply_anchor's unknown-anchor handling, for instance) - one
        malformed style shouldn't be able to crash the whole layout pass.
        """

        s = str(size).strip().lower()

        if not s:
            return 0

        #
        # Plain numeric value - scaled by the window's content_scale (see
        # its own docstring) so a fixed pixel count stays the same
        # physical size across devices, rather than rendering tiny on a
        # high-density phone screen. 1.0 on every desktop display this
        # currently runs on, so this is a no-op there - only changes
        # anything on a backend/display where content_scale != 1.
        #
        try:
            window = get_service("window")
            scale = window.content_scale if window is not None else 1.0
            return int(float(s) * scale)

        except ValueError:
            pass

        #
        # Window-relative unit.
        #
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

    def get_style(self, name: str):
        """Gets the raw, un-merged value of style `name` set directly on this
        element (not through `get_current_styles()` - so no `DEFAULT_STYLES`
        fallback and no state-override merging), warning if it isn't set."""
        if name in self.styles:
            return self.styles[name]

        warning(f'Style "{name}" does not exist.')

    def _set_style(self, name: str, val: any):
        self.styles[name] = val
        self._styles_cache = None

    def set_style(self, name: str, val: any, duration=0, curve=Linear):
        """
        Set or animate a style.

        Immediate:

            element.set_style(
                "width",
                200
            )

        Animated:

            element.set_style(
                "width",
                200,
                duration=0.5
            )
        """

        if duration == 0:
            self._set_style(name, val)

        else:
            self.animations.append(
                UIAnimation(self, name, val, duration, curve)
            )

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

    def _measure_flow_extent(self, content_layout: Layout, root: 'RootElement', layout_dir: str, gap: float) -> float:
        """Sum of non-anchored children's own size along `layout_dir`, plus
        the gaps between them - a lightweight pass (just each child's own
        size, not a full layout) shared by "auto" sizing and "scroll"
        clamping, both of which need "how much space would my children
        take up if I just laid them out." Doesn't depend on this element's
        own size (only `content_layout`'s cross-axis and `root.layout`),
        so computing it more than once a frame is cheap and always gives
        the same answer."""
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
            if child_anchored or getattr(child, "_is_scrollbar_part", False):
                continue

            child_styles = child.get_current_styles()
            child_size_style = child_styles.get("height" if layout_dir == "vertical" else "width", "0")

            if child_size_style == "auto":
                # Can't resolve "auto" here without laying the child out
                # for real first - this pass is deliberately lighter than
                # that (see the docstring). Falls back to the child's own
                # _layout from the *last* full layout pass instead of
                # hardcoding 0: calculate_layout() runs every frame, and
                # this measurement itself runs before this element's own
                # children are laid out for the current frame (needed
                # first, to clamp the scroll offset / size this element
                # before positioning them) - so "last frame's value" is
                # one frame stale at worst, and self-corrects every frame
                # after, the same tradeoff "auto" sizing itself already
                # makes elsewhere. Hardcoding 0 instead made any scrollable
                # element with an "auto"-sized child (a plain vertical list
                # of rows, the single most common scrollable content there
                # is) measure as having virtually no content to scroll to,
                # regardless of how much it actually overflowed - scroll
                # clamping silently locked to ~0 rather than a real bug
                # anyone could point at, since the *label* said "auto" and
                # "auto" resolved fine everywhere else it was used.
                extent = child._layout.height if layout_dir == "vertical" else child._layout.width
            else:
                extent = self._parse_size(child_size_style, content_layout, root.layout)

            if seen_first:
                total_extent += gap
            total_extent += extent
            seen_first = True

        return total_extent

    def _measure_cross_extent(self, content_layout: Layout, root: 'RootElement', axis: str) -> float:
        """Largest non-anchored child's own size along `axis` ("vertical"
        for height, "horizontal" for width) - the cross-axis counterpart
        to _measure_flow_extent, used for "auto" on the axis a layout
        *doesn't* stack along. Same "auto" child fallback (last frame's
        _layout) and same anchored/scrollbar exclusions."""
        largest = 0.0
        key = "height" if axis == "vertical" else "width"

        for child in self.children.values():
            if (child._has_own_style("anchor") or child._has_own_style("parent_anchor")
                    or getattr(child, "_is_scrollbar_part", False)):
                continue

            child_size_style = child.get_current_styles().get(key, "0")
            if child_size_style == "auto":
                extent = child._layout.height if axis == "vertical" else child._layout.width
            else:
                extent = self._parse_size(child_size_style, content_layout, root.layout)
            largest = max(largest, extent)

        return largest

    def calculate_layout(self, root: 'RootElement', parent_layout: Layout = None):
        """
        Calculate this element's size and position, then recursively
        calculate the layout of its children.
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
        auto_width = width_style == "auto"
        auto_height = height_style == "auto"

        self._layout.width = 0 if auto_width else self._parse_size(
            width_style, parent_layout, root.layout
        )

        self._layout.height = 0 if auto_height else self._parse_size(
            height_style, parent_layout, root.layout
        )

        #
        # Padding
        #
        pad = self._parse_size(styles.get("padding", 0), parent_layout, root.layout)

        pad_left = self._parse_size(
            styles.get("padding_left", pad), parent_layout, root.layout
        )

        pad_right = self._parse_size(
            styles.get("padding_right", pad), parent_layout, root.layout
        )

        pad_top = self._parse_size(
            styles.get("padding_top", pad), parent_layout, root.layout
        )

        pad_bottom = self._parse_size(
            styles.get("padding_bottom", pad), parent_layout, root.layout
        )

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

        # Raw pixel offsets - bypass _parse_size (where content_scale
        # normally applies), so scaled here directly for the same reason
        # every other raw-pixel style read in this file now is.
        window = get_service("window")
        offset_scale = window.content_scale if window is not None else 1.0
        x_offset = styles.get("x", 0) * offset_scale
        y_offset = styles.get("y", 0) * offset_scale

        if anchored:
            self._apply_anchor(
                styles.get("parent_anchor", "center"),
                styles.get("anchor", "center"),
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

        #
        # Calculate children.
        #
        for child in self.children.values():

            # The scrollbar track/thumb (see _update_scrollbar(), called
            # after this loop) are real children for draw/hit-test
            # purposes, but they're positioned directly from this
            # element's own scroll state, not through flow or anchoring -
            # skipped here the same way _measure_flow_extent skips them.
            if getattr(child, "_is_scrollbar_part", False):
                continue

            #
            # See the comment in RootElement.calculate_layout - this
            # has to check _has_own_style, not the merged styles dict,
            # or every child would register as anchored.
            #
            child_anchored = (
                child._has_own_style("anchor") or
                child._has_own_style("parent_anchor")
            )

            #
            # Anchored children are positioned against the entire
            # content rectangle and do not participate in normal flow.
            #
            if child_anchored:
                child.calculate_layout(root, content_layout)
                continue

            #
            # Normal child.
            #
            child_layout = Layout(child_offset_x, child_offset_y, content_w, content_h)
            child.calculate_layout(root, child_layout)

            #
            # Advance flow position.
            #
            if layout_dir == "vertical":
                child_offset_y += child._layout.height + gap

            elif layout_dir == "horizontal":
                child_offset_x += child._layout.width + gap

            else:
                warning(
                    f'Unknown layout direction "{layout_dir}". '
                    f'Expected "vertical" or "horizontal".'
                )

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

    def _update(self):
        for animation in self.animations:
            animation.update()


class UIAnimation:
    """An in-progress animation of one style on one `UIElement`, created by
    `UIElement.set_style(..., duration=...)` and driven forward by
    `UIElement._update()` each frame until it reaches `duration` and removes itself."""

    def __init__(
        self,
        element: 'UIElement',
        style: str,
        end_value: any,
        duration: float,
        curve: Curve = Linear()
    ):
        """Args:
            element: The element whose style is being animated.
            style: Name of the style to animate.
            end_value: The value `style` should reach once the animation finishes.
            duration: How long the animation takes, in seconds.
            curve: Easing curve applied to the 0-1 progress before interpolating.

        Raises:
            ValueError: If `style`'s current value isn't an animatable type,
                or if it isn't compatible with `end_value` (see `_validate_animatable`).
        """
        self.style = style
        self.element = element
        self.curve = curve
        self.end_value = end_value
        self.duration = duration
        self.elapsed = 0.0
        self.finished = False

        self.start_value = self._capture_start_value()

        self._validate_animatable()

        if isinstance(self.start_value, str):
            self.start_nums, self.start_parts = self._extract_numbers(self.start_value)
            self.end_nums, self.end_parts = self._extract_numbers(self.end_value)

        elif isinstance(self.start_value, (tuple, list)):
            self.start_shape = self._get_shape(self.start_value)
            self.end_shape = self._get_shape(self.end_value)

    def _capture_start_value(self):
        val = self.element.get_style(self.style)

        if isinstance(val, (int, float, tuple, list, str)):
            return val

        raise ValueError(f"Unsupported type for animation: {type(val)}")

    def _extract_numbers(self, s: str):
        parts = re.split(r'(-?\d+\.?\d*)', s)

        nums = [
            float(p)
            for p in parts
            if re.fullmatch(r'-?\d+\.?\d*', p)
        ]

        return nums, parts

    def _get_shape(self, iterable):
        """
        Return the nested shape of tuples/lists.
        """

        if isinstance(iterable, (list, tuple)):
            return tuple(
                self._get_shape(x) if isinstance(x, (list, tuple)) else 0
                for x in iterable
            )

        return 0

    def _validate_animatable(self):
        """
        Ensure the start and end animation values are compatible.
        """

        end = self.end_value
        start = self.start_value

        if type(start) != type(end):
            raise ValueError(
                f"Start ({type(start)}) and end ({type(end)}) types do not match"
            )

        if isinstance(start, str):
            start_nums, start_parts = self._extract_numbers(start)
            end_nums, end_parts = self._extract_numbers(end)

            non_numeric_start = [
                p for p in start_parts if not re.fullmatch(r'-?\d+\.?\d*', p)
            ]

            non_numeric_end = [
                p for p in end_parts if not re.fullmatch(r'-?\d+\.?\d*', p)
            ]

            if non_numeric_start != non_numeric_end:
                warning("Non-numeric parts of start/end string do not match")
                self.remove()
                return

            if len(start_nums) != len(end_nums):
                warning("Number of numeric parts in start/end string do not match")
                self.remove()
                return

        elif isinstance(start, (tuple, list)):
            start_shape = self._get_shape(start)
            end_shape = self._get_shape(end)

            if start_shape != end_shape:
                warning("Start and end iterables have different shapes")
                self.remove()

    def _interpolate(self, start, end, t: float):
        if isinstance(start, (int, float)):
            return start + (end - start) * t

        elif isinstance(start, (tuple, list)):
            return type(start)(
                self._interpolate(s, e, t) for s, e in zip(start, end)
            )

        elif isinstance(start, Color):
            return

        elif isinstance(start, str):
            interpolated_nums = [
                s + (e - s) * t
                for s, e in zip(self.start_nums, self.end_nums)
            ]

            result = []
            num_idx = 0

            for p in self.start_parts:
                if re.fullmatch(r'-?\d+\.?\d*', p):
                    result.append(str(interpolated_nums[num_idx]))
                    num_idx += 1

                else:
                    result.append(p)

            return ''.join(result)

        else:
            warning("Could not interpolate between animation values.")
            self.remove()

    def update(self):
        """Advances the animation by one frame's delta time, writing the
        interpolated value straight into the element's style, and removes
        itself from the element once `duration` has elapsed."""
        delta_time = delta()

        if self.finished:
            return

        self.elapsed += delta_time

        t = min(self.elapsed / self.duration, 1.0)
        t = self.curve(t)

        new_value = self._interpolate(self.start_value, self.end_value, t)

        self.element._set_style(self.style, new_value)

        if self.elapsed >= self.duration:
            self.finished = True

            if self in self.element.animations:
                self.remove()

    def remove(self):
        """Detaches this animation from its element, stopping it from being updated further."""
        self.element.animations.remove(self)
