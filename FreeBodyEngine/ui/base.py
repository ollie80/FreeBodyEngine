"""What both UI backends share - ui/element.py (pure Python) and
ui/native_element.py (the compiled Node) - written once, so the two can't
drift apart.

TreeBehaviour is anything with styles and children (both backends' root
too); ElementBehaviour adds everything else an element does that isn't
layout: flags, event handlers, animation, the shared Style layer, and the
visible/rect properties. Each backend provides a handful of primitives
these build on:

    _raw_styles() / _set_raw_styles(dict)   the element's own style dict
    _invalidate_styles()                    drop the merged-styles cache
    _set_style(name, value)                 write one style, uncached
    _style_base (attribute)                 the Style layer's live dict
    _apply_style_keys(keys)                 which flag tables now apply
    _register(event, callback)              add a callback
    off / clear_event / _emit / has_event   the rest of the callback list
    children, _layout, get_current_styles()

plus `self._flags = []`, `self._handlers = {}`, `self.animations = []` and
`self._style = None` in __init__.
"""
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from enum import Enum
from typing import Callable
import re

from FreeBodyEngine.graphics.color import Color
from FreeBodyEngine.math import Curve, Linear
from FreeBodyEngine import warning, delta, get_service


#: The engine's own flag names usable as style override tables - see the
#: FLAGS docs above. An app's own flags ("playing", ...) work the same way;
#: these are just the ones the engine itself sets or has always known.
STATE_STYLE_KEYS = ("normal", "hover", "pressed", "focused", "selected", "clicked")

#: Flags UIManager sets from input - everything else is the app's.
INTERACTION_FLAGS = ("hover", "focused", "pressed")

# Override tables each interaction flag applies, lowest first. "clicked" and
# "selected" are the names pressed/focused had when an element had a single
# state ("selected" meant focused) - still honoured, so existing styles keep
# working, with the new name winning where both are set.
_FLAG_STYLE_KEYS = {
    "hover": ("hover",),
    "focused": ("selected", "focused"),
    "pressed": ("clicked", "pressed"),
}


def style_keys_for(flags) -> list:
    """The override tables that apply for a set of flags, lowest precedence
    first: "normal" when there are none; otherwise the app's own flags in
    the order they were set, then "selected", "hover", "focused",
    "pressed"."""
    if not flags:
        return ["normal"]
    keys = [flag for flag in flags if flag not in INTERACTION_FLAGS and flag != "selected"]
    if "selected" in flags:
        keys.append("selected")
    for flag in INTERACTION_FLAGS:
        if flag in flags:
            keys.extend(_FLAG_STYLE_KEYS[flag])
    return list(dict.fromkeys(keys))


class StyleView(MutableMapping):
    """What `element.styles` returns: the element's own style dict, behind a
    view that tells the element whenever it changes.

    get_current_styles() is memoized, so a write that went straight into the
    raw dict (`element.styles["width"] = 10`, or `element.styles["hover"]
    ["base_color"] = ...`) used to leave the cached merge in place and do
    nothing at all. Every write through this view - including into a state
    override table, which comes back as a view of its own - invalidates it.
    Shared by both backends; `on_change` is how each one drops its cache."""

    __slots__ = ("_raw", "_on_change")

    def __init__(self, raw: dict, on_change: Callable[[], None]):
        self._raw = raw
        self._on_change = on_change

    def __getitem__(self, key):
        value = self._raw[key]
        # Any dict - a flag's override table, or a dict-valued style like
        # "scrollbar_thumb" - so writes into it are seen too.
        if isinstance(value, dict):
            return StyleView(value, self._on_change)
        return value

    def __setitem__(self, key, value):
        if isinstance(value, Mapping):
            value = dict(value)
        self._raw[key] = value
        self._on_change()

    def __delitem__(self, key):
        del self._raw[key]
        self._on_change()

    def __iter__(self):
        return iter(self._raw)

    def __len__(self):
        return len(self._raw)

    def __contains__(self, key):
        return key in self._raw

    def __repr__(self):
        return f"StyleView({self._raw!r})"


def _copy_styles(styles) -> dict:
    """An element's own copy of the styles it was given - including a copy of
    each dict in them (a flag's override table), so a "hover" dict shared
    between elements (a theme's) is never changed through one of them."""
    copied = dict(styles) if styles else {}
    for key, value in copied.items():
        if isinstance(value, Mapping):
            copied[key] = dict(value)
    return copied


def _content_scale() -> float:
    window = get_service("window")
    return window.content_scale if window is not None else 1.0



VALID_ANCHORS = {
    "top_left", "top_center", "top_right",
    "center_left", "center", "center_right",
    "bottom_left", "bottom_center", "bottom_right",
}

VALID_OVERFLOWS = {"visible", "hidden", "scroll", "auto"}


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

    "visible": True,
    "grow": 0,
    "justify": "start",
    "align": "start",
    "align_self": "auto",

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
    "text_align": "left",

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



class ElementStates(Enum):
    """The single interaction state an element used to have, before flags -
    see the FLAGS docs in ui/element.py. Kept for element.state / set_state(); new code
    uses set_flag()/has_flag() (note FOCUSED's value is "selected", the
    name focus used to have)."""
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


class TreeBehaviour:
    """Styles and children - shared by every element, and by both backends'
    root."""

    @property
    def styles(self) -> StyleView:
        """This element's own styles - see StyleView. Assigning a whole dict
        replaces them (with a copy)."""
        return StyleView(self._raw_styles(), self._invalidate_styles)

    @styles.setter
    def styles(self, value):
        self._set_raw_styles(_copy_styles(value))
        self._invalidate_styles()

    def set_styles(self, styles: dict):
        """Replaces this element's styles wholesale - the same as assigning
        `styles`."""
        self.styles = styles

    def _invalidate_styles(self):
        pass

    def _update(self):
        """Advances every descendant's running animations by one frame -
        UIManager calls this on the root each frame."""
        for child in list(self.children.values()):
            child._update()


def _handler_property(event: str) -> property:
    def get(self):
        return self._handlers.get(event)

    def set(self, callback):
        self.set_handler(event, callback)

    return property(get, set, doc=f'The "{event}" handler - see ElementBehaviour.set_handler().')


class ElementBehaviour(TreeBehaviour):
    """Everything an element does that isn't layout, shared by both
    backends' UIElement (and the native backend's scrollbar parts) - see
    this module's docstring for what each backend provides underneath."""

    VALID_ANCHORS = VALID_ANCHORS
    VALID_OVERFLOWS = VALID_OVERFLOWS
    DEFAULT_STYLES = DEFAULT_STYLES

    # -- styles -----------------------------------------------------------------

    @property
    def style(self) -> 'Style | None':
        """The shared ui.Style this element is drawn with, underneath its own
        `styles`. Not copied: changing the Style (`theme.button.base_color =
        ...`) restyles every element using it, from the next frame.

        Precedence, lowest first: DEFAULT_STYLES, the Style, this element's
        own styles, then for each flag that's set (see the FLAGS docs in
        ui/element.py, which also give their order) the Style's override
        table and then this element's own - so a flag always wins over a
        plain value, wherever each came from."""
        return self._style

    @style.setter
    def style(self, style: 'Style | None'):
        if self._style is not None:
            self._style._unsubscribe(self)
        self._style = style
        self._style_base = style._subscribe(self) if style is not None else {}
        self._invalidate_styles()

    def _style_changed(self):
        """Called by this element's Style when it (or a Style it's built
        from) changes."""
        self._invalidate_styles()

    def set_style(self, name: str, val, duration: float = 0, curve=Linear):
        """
        Set or animate a style.

        Immediate:

            element.set_style("width", 200)

        Animated:

            element.set_style("width", 200, duration=0.5)

        Either way, any animation already running on the same style stops.
        """
        self._cancel_animations(name)

        if duration == 0:
            self._set_style(name, val)
        else:
            self.animations.append(UIAnimation(self, name, val, duration, curve))

    def _cancel_animations(self, name: str):
        """Stops any running animation of style `name` - a newer set_style()
        for the same style wins, rather than the old animation overwriting
        it on its next frame (or two animations fighting over it)."""
        self.animations = [a for a in self.animations if a.style != name]

    def _update(self):
        # A copy: a finishing animation removes itself from the list.
        for animation in list(self.animations):
            animation.update()
        super()._update()

    @property
    def visible(self) -> bool:
        """Whether this element (and so its subtree) is laid out, drawn and
        hit-tested at all - the "visible" style."""
        return bool(self.get_current_styles().get("visible", True))

    @visible.setter
    def visible(self, value: bool):
        self.set_style("visible", bool(value))

    @property
    def rect(self) -> 'Layout':
        """This element's position and size from the last layout pass, in the
        same UI units its styles use. `_layout` is the same rect in raw
        pixels (multiplied by the window's content_scale)."""
        scale = _content_scale() or 1.0
        layout = self._layout
        return Layout(layout.x / scale, layout.y / scale, layout.width / scale, layout.height / scale)

    # -- events -------------------------------------------------------------------

    def on(self, event: str, callback: Callable) -> Callable[[], None]:
        """Registers `callback` to run when `event` fires on this element -
        "hover_enter", "hover_exit", "press", "release", "click", or
        "submit" (editable elements only) - see the INTERACTION docs in
        ui/element.py. Adds to any already registered; set_handler() (or
        `on_click = ...`) replaces them instead.

        Returns a function that unregisters it again."""
        self._register(event, callback)
        return lambda: self.off(event, callback)

    def clear(self, event: str) -> None:
        """Removes every callback registered for `event`."""
        self.clear_event(event)

    def scroll_by(self, delta_px: float) -> None:
        """Adjusts this element's scroll offset by `delta_px` (only has any
        visible effect if its overflow scrolls). Clamped to the valid range
        on the next layout pass."""
        self._scroll_offset += delta_px

    # -- flags ----------------------------------------------------------------

    @property
    def flags(self) -> tuple:
        """Every flag currently set on this element - see the FLAGS docs."""
        return tuple(self._flags)

    def has_flag(self, name: str) -> bool:
        return name in self._flags

    def set_flag(self, name: str, on: bool = True) -> None:
        """Sets (or with on=False, clears) flag `name`. Its override table in
        this element's styles or Style - styles[name] - applies while it's
        set. "hover", "focused" and "pressed" are set by UIManager from
        input; any other name is the app's to use."""
        flags = self._flags
        if on == (name in flags):
            return
        if on:
            flags.append(name)
        else:
            flags.remove(name)
        self._apply_style_keys(style_keys_for(flags))

    @property
    def selected(self) -> bool:
        """The "selected" flag - the app's to set (a current tab, a chosen
        row, a toggle that's on)."""
        return self.has_flag("selected")

    @selected.setter
    def selected(self, value: bool):
        self.set_flag("selected", bool(value))

    @property
    def hovered(self) -> bool:
        return self.has_flag("hover")

    @property
    def pressed(self) -> bool:
        return self.has_flag("pressed")

    @property
    def focused(self) -> bool:
        return self.has_flag("focused")

    # The single state an element used to have, kept for code written
    # against it. Reports the most specific interaction flag set.
    @property
    def state(self) -> 'ElementStates':
        if self.has_flag("pressed"):
            return ElementStates.CLICKED
        if self.has_flag("focused"):
            return ElementStates.FOCUSED
        if self.has_flag("hover"):
            return ElementStates.HOVER
        return ElementStates.NORMAL

    def get_state(self) -> 'ElementStates':
        return self.state

    def set_state(self, state: 'ElementStates') -> None:
        """Older single-state form of set_flag(): sets the one interaction
        flag `state` stands for (none, for NORMAL) and clears the other
        two. Flags the app set are untouched."""
        if not isinstance(state, ElementStates):
            state = ElementStates(state)
        wanted = {
            ElementStates.NORMAL: None, ElementStates.HOVER: "hover",
            ElementStates.CLICKED: "pressed", ElementStates.FOCUSED: "focused",
        }[state]
        for flag in INTERACTION_FLAGS:
            self.set_flag(flag, flag == wanted)

    # -- handlers ---------------------------------------------------------------

    def set_handler(self, event: str, callback) -> None:
        """Makes `callback` the one handler for `event`, replacing every
        callback registered for it before (by on() too); None just removes
        them. What `on_click = ...` and the builders' on_click= do - so
        re-setting a handler when an element is rebuilt or its behaviour
        changes never stacks up duplicates the way repeating on() does."""
        self.clear_event(event)
        self._handlers.pop(event, None)
        if callback is not None:
            self.on(event, callback)
            self._handlers[event] = callback

    on_click = _handler_property("click")
    on_press = _handler_property("press")
    on_release = _handler_property("release")
    on_hover_enter = _handler_property("hover_enter")
    on_hover_exit = _handler_property("hover_exit")
    on_submit = _handler_property("submit")


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
        # set_style() passes the curve class itself as its default.
        self.curve = curve() if isinstance(curve, type) else curve
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
        # Whatever the style is now - its own value, or the default if it
        # was never set. get_style() only knows the former, so animating a
        # style the element hadn't set yet ("fade in from the default
        # transparent base_color") started from None and raised.
        styles = self.element.styles
        base = getattr(self.element, "_style_base", None) or {}
        if self.style in styles:
            val = styles[self.style]
        elif self.style in base:
            val = base[self.style]
        else:
            val = self.element.DEFAULT_STYLES.get(self.style)

        if isinstance(val, (int, float, tuple, list, str)):
            return val

        raise ValueError(f'Cannot animate style "{self.style}" from {val!r} ({type(val).__name__}).')

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

        # These all raise: this runs before the animation is added to its
        # element, so there's nothing to remove() yet (which is what these
        # used to try, raising from list.remove instead). 100 -> 200.5 is
        # fine - only the kind of value has to match, not int vs float.
        number = (int, float)
        if isinstance(start, number) and isinstance(end, number):
            return

        if isinstance(start, (tuple, list)) and isinstance(end, (tuple, list)):
            if self._get_shape(start) != self._get_shape(end):
                raise ValueError(f'Cannot animate "{self.style}" between {start!r} and {end!r}: different shapes.')
            return

        if isinstance(start, str) and isinstance(end, str):
            start_nums, start_parts = self._extract_numbers(start)
            end_nums, end_parts = self._extract_numbers(end)

            non_numeric_start = [
                p for p in start_parts if not re.fullmatch(r'-?\d+\.?\d*', p)
            ]

            non_numeric_end = [
                p for p in end_parts if not re.fullmatch(r'-?\d+\.?\d*', p)
            ]

            if non_numeric_start != non_numeric_end or len(start_nums) != len(end_nums):
                raise ValueError(f'Cannot animate "{self.style}" between "{start}" and "{end}": their units differ.')
            return

        raise ValueError(
            f'Cannot animate "{self.style}" from {type(start).__name__} to {type(end).__name__}.'
        )

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
        # Curve has no __call__ - this used to raise on the first frame.
        t = self.curve.get_value(t) if hasattr(self.curve, "get_value") else self.curve(t)

        if self.elapsed >= self.duration:
            # Exactly the value asked for, not a float that's almost it
            # ("100.0w" for "100w", 199.99999 for 200).
            new_value = self.end_value
        else:
            new_value = self._interpolate(self.start_value, self.end_value, t)

        self.element._set_style(self.style, new_value)

        if self.elapsed >= self.duration:
            self.finished = True

            if self in self.element.animations:
                self.remove()

    def remove(self):
        """Detaches this animation from its element, stopping it from being updated further."""
        self.element.animations.remove(self)
