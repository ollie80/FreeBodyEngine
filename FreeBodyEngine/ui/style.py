"""Shared, live style sets for UI elements.

A Style is a named bundle of style values - a theme's "button", "row",
"title" - that elements are drawn with without copying it:

    button = Style(base_color=ACCENT, text_color=BG, padding=10, font=FONT,
                   hover=Style(base_color=ACCENT_2),
                   clicked=Style(base_color=BORDER_2))
    danger = button | Style(base_color=RED)      # or Style(button, base_color=RED)

    UIElement(style=button)                     # or el.style = button
    button.base_color = ACCENT_2                # every button, and danger, updates

An element's own `styles` sit on top of its Style (see UIElement.style for
the full precedence), so one element can still override a value without
needing a Style of its own.

A Style built from others (`a | b`, or `Style(a, b, ...)`) keeps following
them: change `a` and every Style and element built on it sees the change.
"""
import difflib
import weakref
from collections.abc import Mapping, MutableMapping

from FreeBodyEngine import warning
from FreeBodyEngine.ui.base import STATE_STYLE_KEYS, DEFAULT_STYLES

#: Every style key the engine reads - what a Style (and the ui builders)
#: check names against, so a typo warns instead of silently doing nothing.
KNOWN_STYLE_KEYS = frozenset(DEFAULT_STYLES) | {
    "padding_left", "padding_right", "padding_top", "padding_bottom", "safe_area",
} | frozenset(STATE_STYLE_KEYS)


def check_style_key(key: str, where: str = "Style") -> None:
    """Warns if `key` isn't a style the engine knows, suggesting the
    closest one that is."""
    if key in KNOWN_STYLE_KEYS:
        return
    close = difflib.get_close_matches(key, KNOWN_STYLE_KEYS, n=1)
    hint = f' - did you mean "{close[0]}"?' if close else ""
    warning(f'{where}: unknown style "{key}"{hint}')


def _is_flag_table(key: str, value) -> bool:
    """Whether `value` under `key` is a flag's override table (merged across
    a Style's bases) rather than a plain value: any dict or Style, except
    under a style that takes a dict as its value ("scrollbar_thumb")."""
    if not isinstance(value, Mapping):
        return False
    return key in STATE_STYLE_KEYS or key not in KNOWN_STYLE_KEYS


class Style(MutableMapping):
    """A live set of style values - see the module docstring.

    Reads like a dict of the merged result (`style["width"]`, `dict(style)`,
    `**style`), and its values can also be read and set as attributes
    (`style.base_color`). A state override ("hover", "clicked", "selected",
    "normal") is a Style of its own, or a plain dict that gets turned into
    one."""

    def __init__(self, *bases: 'Style', **styles):
        """Args:
            *bases: Styles this one is built on, lowest first - later ones
                win, and this Style's own values win over all of them.
            **styles: This Style's own values.
        """
        object.__setattr__(self, "_bases", list(bases))
        object.__setattr__(self, "_own", {})
        # The merged result. Elements hold this exact dict (see
        # UIElement.style), so it's only ever updated in place.
        object.__setattr__(self, "_flat", {})
        object.__setattr__(self, "_dependents", weakref.WeakSet())

        for base in bases:
            if not isinstance(base, Style):
                raise TypeError(f"Style bases must be Styles, got {type(base).__name__} - pass values as keywords.")
            base._dependents.add(self)

        for key, value in styles.items():
            self._store(key, value)
        self._rebuild()

    # -- building ---------------------------------------------------------------

    def _store(self, key: str, value):
        if _is_flag_table(key, value):
            # A flag's override table - the engine's ("hover", ...) or an
            # app's own ("playing"), which is why an unknown name is fine
            # here as long as it's given a table.
            if not isinstance(value, Style):
                value = Style(**value)
            value._dependents.add(self)
        elif key in STATE_STYLE_KEYS:
            raise TypeError(f'Style: "{key}" must be a Style or a dict, got {type(value).__name__}.')
        else:
            check_style_key(key)
        self._own[key] = value

    def _rebuild(self):
        merged = {}
        for base in self._bases:
            for key, value in base._flat.items():
                if _is_flag_table(key, value):
                    merged[key] = {**merged.get(key, {}), **value}
                else:
                    merged[key] = value
        for key, value in self._own.items():
            if isinstance(value, Style):
                merged[key] = {**merged.get(key, {}), **value._flat}
            else:
                merged[key] = value

        self._flat.clear()
        self._flat.update(merged)

        for dependent in list(self._dependents):
            if isinstance(dependent, Style):
                dependent._rebuild()
            else:
                dependent._style_changed()

    def _subscribe(self, element) -> dict:
        """Registers `element` to hear about changes, and returns the live
        dict it should read from. Weak: an element that's gone stops being
        told."""
        self._dependents.add(element)
        return self._flat

    def _unsubscribe(self, element):
        self._dependents.discard(element)

    # By identity: a Style is a live thing other Styles and elements follow,
    # kept in weak sets - two that happen to hold the same values aren't the
    # same Style. (Mapping would otherwise compare contents and make it
    # unhashable.)
    __eq__ = object.__eq__
    __hash__ = object.__hash__

    def __or__(self, other: 'Style') -> 'Style':
        """`a | b` - a new Style built on both, `b` winning."""
        if not isinstance(other, Style):
            return NotImplemented
        return Style(self, other)

    # -- changing ----------------------------------------------------------------

    def update(self, other=(), **styles):
        """Sets several values at once - one restyle, not one per value."""
        for key, value in dict(other, **styles).items():
            self._store(key, value)
        self._rebuild()

    def __setitem__(self, key, value):
        self._store(key, value)
        self._rebuild()

    def __delitem__(self, key):
        """Removes this Style's own value - one inherited from a base stays."""
        value = self._own.pop(key)
        if isinstance(value, Style):
            value._dependents.discard(self)
        self._rebuild()

    def clear(self):
        """Removes all of this Style's own values - inherited ones stay."""
        for value in self._own.values():
            if isinstance(value, Style):
                value._dependents.discard(self)
        self._own.clear()
        self._rebuild()

    def __setattr__(self, name, value):
        if name.startswith("_"):
            object.__setattr__(self, name, value)
        else:
            self[name] = value

    def __delattr__(self, name):
        try:
            del self[name]
        except KeyError:
            raise AttributeError(name) from None

    # -- reading ----------------------------------------------------------------

    def __getitem__(self, key):
        return self._flat[key]

    def __getattr__(self, name):
        # Only reached for names that aren't real attributes.
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self._flat[name]
        except KeyError:
            raise AttributeError(f"Style has no {name!r}") from None

    def __iter__(self):
        return iter(self._flat)

    def __len__(self):
        return len(self._flat)

    def __contains__(self, key):
        return key in self._flat

    def __repr__(self):
        return f"Style({self._flat!r})"
