from dataclasses import dataclass
import uuid
from enum import Enum
from typing import Callable
from FreeBodyEngine.graphics.color import Color
from FreeBodyEngine.math import Curve, Linear
from FreeBodyEngine import warning, delta
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

scroll
    Turns on mouse-wheel scrolling of this element's children along
    its `layout` direction, and clips their drawing to this element's
    own rect (children are never drawn outside their scrollable
    ancestor's bounds, however far they scroll).

        "scroll": True

    The scroll offset is clamped every layout pass to the actual
    overflow (0 if children fit without scrolling), and persists
    across frames on the element itself - nothing else to wire up.


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
        self.width = width
        self.height = height

        self.layout = Layout(0, 0, width, height)

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
        "scroll": False,
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

    def _emit(self, event: str, *args) -> None:
        """Calls every callback registered for `event` via `on()`, in
        registration order. Copies the callback list first so a callback
        that itself calls on()/off() doesn't mutate the list mid-iteration."""
        for callback in list(self._event_callbacks.get(event, ())):
            callback(*args)

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
        """

        current_styles = dict(self.DEFAULT_STYLES)
        current_styles.update(self.styles)

        state_name = self.state.value

        if state_name in self.styles:
            for k, v in self.styles[state_name].items():
                current_styles[k] = v

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
        """

        s = str(size).strip().lower()

        if not s:
            return 0

        #
        # Plain numeric value.
        #
        try:
            return int(float(s))

        except ValueError:
            pass

        #
        # Window-relative unit.
        #
        if s[-2:] in ("ww", "hw"):
            num = float(s[:-2])
            suffix = s[-2:]

        else:
            num = float(s[:-1])
            suffix = s[-1]

        if suffix == "w":
            return int(parent_layout.width * (num / 100.0))

        if suffix == "h":
            return int(parent_layout.height * (num / 100.0))

        if suffix == "ww":
            return int(root_layout.width * (num / 100.0))

        if suffix == "hw":
            return int(root_layout.height * (num / 100.0))

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
        # Size
        #
        self._layout.width = self._parse_size(
            styles.get("width", "0"), parent_layout, root.layout
        )

        self._layout.height = self._parse_size(
            styles.get("height", "0"), parent_layout, root.layout
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

        if anchored:
            self._apply_anchor(
                styles.get("parent_anchor", "center"),
                styles.get("anchor", "center"),
                parent_layout,
                styles.get("x", 0),
                styles.get("y", 0)
            )
        else:
            self._layout.x += styles.get("x", 0)
            self._layout.y += styles.get("y", 0)

        #
        # Calculate this element's content rectangle.
        #
        content_x = self._layout.x + pad_left
        content_y = self._layout.y + pad_top

        content_w = max(0, self._layout.width - pad_left - pad_right)
        content_h = max(0, self._layout.height - pad_top - pad_bottom)

        content_layout = Layout(content_x, content_y, content_w, content_h)

        #
        # Child layout settings.
        #
        layout_dir = styles.get("layout", "vertical")

        gap = self._parse_size(styles.get("gap", 0), content_layout, root.layout)

        child_offset_x = content_x
        child_offset_y = content_y

        #
        # Scrolling: measure total child extent along the flow direction
        # (a lightweight pass - just each non-anchored child's own size,
        # not a full layout) so the offset can be clamped to actual
        # overflow before it's applied below. Sizes don't depend on scroll
        # position (parse_size uses content_layout, which is scroll-
        # independent), so this measurement doesn't change once children
        # are laid out for real - measuring it twice per child is the
        # tradeoff for not needing a separate pre-layout pass.
        #
        if styles.get("scroll", False):
            total_extent = 0.0
            seen_first = False

            for child in self.children.values():
                child_anchored = (
                    child._has_own_style("anchor") or
                    child._has_own_style("parent_anchor")
                )
                if child_anchored:
                    continue

                child_styles = child.get_current_styles()
                if layout_dir == "vertical":
                    extent = self._parse_size(
                        child_styles.get("height", "0"), content_layout, root.layout
                    )
                else:
                    extent = self._parse_size(
                        child_styles.get("width", "0"), content_layout, root.layout
                    )

                if seen_first:
                    total_extent += gap
                total_extent += extent
                seen_first = True

            viewport_extent = content_h if layout_dir == "vertical" else content_w
            max_scroll = max(0.0, total_extent - viewport_extent)
            self._scroll_offset = max(0.0, min(self._scroll_offset, max_scroll))

            if layout_dir == "vertical":
                child_offset_y -= self._scroll_offset
            else:
                child_offset_x -= self._scroll_offset
        else:
            self._scroll_offset = 0.0

        #
        # Calculate children.
        #
        for child in self.children.values():

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
