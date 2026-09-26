"""Native (C++/pybind11) backing for UIElement/RootElement - thin Python
subclasses of the compiled Node class (see ui/native/node.hpp) that exist
*only* to reconcile a handful of naming/shape differences from the old
pure-Python ui.element implementation, so every existing call site
(phonon included) keeps working completely unchanged. Every method NOT
overridden here resolves straight through to Node's own C++ binding with
no extra Python dispatch in between - that's the entire reason option (a)
(bind the class directly) was chosen over a wrapper class in the first
place; a subclass that only overrides __init__ and a few glue methods
doesn't undo that for anything else.

Only importable where the compiled extension actually exists - see
ui/__init__.py's own flag/platform resolution for when this is chosen
over ui/element.py's pure-Python implementation (used unconditionally on
web, where no compiled extension can exist at all, and as an automatic
fallback anywhere the native module hasn't been built).

Imports the compiled `_fbcpp` extension directly (`_fbcpp.node.Node`)
rather than through cli/cpp/compile.py's generated `node.py` convenience
shim (`from node import Node`, relying on sys.path containing
ui/native/cpp_scripts/) - that shim exists so *project* C++ scripts can
be imported by bare file name, but this module already knows exactly
which extension and submodule it wants, and the shim's own sys.path
requirement doesn't hold on every platform this needs to work on: a
desktop dev build's `_fbcpp` sits at ui/native/cpp_scripts/ and needs the
sys.path insertion below to be found at all, but an Android build's
`_fbcpp` is installed by python-for-android's own `pip install .` step
(build/android_recipes/freebodyengine_native/__init__.py) straight into
its normal global site-packages, already importable with no path
insertion needed - and unlike desktop, that directory doesn't exist
on-device at all (only the pre-generated *sources* the recipe consumed
briefly existed at that path, host-side, during the build - see
Builder._generate_native_sources_for_android()). Trying to insert a
nonexistent path is harmless (Python just never finds anything to import
from it), so the insertion below is unconditional; only the actual
import needs this direct-and-explicit form to work on both."""
import os
import sys

# See the module docstring above - only actually needed for a desktop dev
# build (ui/native/cpp_scripts/ existing on disk there at all); a no-op
# on any platform where the compiled extension was installed straight
# into the normal global site-packages instead (Android).
_NATIVE_DIR = os.path.join(os.path.dirname(__file__), "native", "cpp_scripts")
if _NATIVE_DIR not in sys.path:
    sys.path.insert(0, _NATIVE_DIR)

import _fbcpp  # noqa: E402 - the compiled extension itself, see the module docstring
Node = _fbcpp.node.Node  # noqa: E402

from FreeBodyEngine.ui.element import UIElement as _PyUIElement  # noqa: E402
from FreeBodyEngine.ui.element import UIAnimation, Layout  # noqa: E402
from FreeBodyEngine.math import Linear  # noqa: E402
from FreeBodyEngine import get_service  # noqa: E402


class _ChildrenView:
    """Live, mutable view over `owner`'s real children - not a snapshot.

    The old pure-Python GenericElement.children was a real dict, and
    phonon relies on that directly: `some_element.children.clear()` is
    how it empties a container before rebuilding its content (view
    switching, search results, library tabs, playlist tracks - 14
    call sites in app_scene.py alone), not a hypothetical pattern. A
    fresh `{i: c for i, c in enumerate(get_children())}` snapshot dict
    (what this used to return) looks identical for every *read* (
    .values(), truthiness) but makes `.clear()` a silent no-op - mutating
    a throwaway dict has no effect on the real tree - which is exactly
    the bug that showed up as "opening a new page appends its content
    below whatever was already there instead of replacing it": every
    view switch's `content_area.children.clear()` was doing nothing.

    Deliberately minimal - only what's actually used against `.children`
    anywhere in this engine or phonon (checked via a real grep across
    both, not guessed): `.values()`, `.clear()`, truthiness/`len()`. Add
    more `dict`-shaped methods here if and when something new needs
    them, rather than trying to be a complete MutableMapping upfront."""

    def __init__(self, owner):
        self._owner = owner

    def values(self):
        return [_wrap_child(c) for c in self._owner.get_children()]

    def clear(self) -> None:
        # get_children() returns a snapshot copy (see Node::get_children's
        # own comment in node.hpp), so removing each one from `_owner`
        # while iterating this list is safe - it's not the live
        # underlying vector being mutated out from under the loop.
        for child in self._owner.get_children():
            self._owner.remove_child(child)
        # Also drops the Python-side keepalive references (see
        # UIElement.__init__'s own comment on why they exist) - without
        # this, elements removed via .children.clear() would keep their
        # Python wrappers (and every closure/callback they hold) alive
        # forever, a real memory leak across every view switch, not just
        # a missed cleanup.
        py_children = getattr(self._owner, "_py_children", None)
        if py_children is not None:
            py_children.clear()

    def __len__(self) -> int:
        return len(self._owner.get_children())

    def __bool__(self) -> bool:
        return len(self) > 0


class _ScrollbarPartProxy:
    """Thin, cold-path wrapper around a scrollbar track/thumb - the two
    Node children Node::update_scrollbar() creates *inside* C++ (see its
    own comment in node.hpp on why pybind11 has no way to hand those back
    as anything but the plain base Node, even though the rest of the tree
    is UIElement throughout - a pybind11 object's Python type is fixed at
    construction, and neither a shared_ptr round-trip through a stored
    Python factory nor reassigning __class__ on the returned object
    (CPython refuses it - UIElement's __dict__ gives it a different
    deallocator than plain Node) got around that).

    Delegates every UIElement method/property not explicitly listed here
    straight to the wrapped Node via __getattr__, and supplies just the
    handful of UIElement-only names ui/manager.py and ui/renderer.py
    actually read on a scrollbar part (.children/._layout/.state/
    get_overflow) - the same "no processing layer" principle UIElement
    itself follows, just accepted as a real (if rare: at most 2 elements
    per scrollable container, never the bulk of the tree) exception here
    rather than pretended away.

    Cached per underlying Node (see _wrap_child below) rather than
    reconstructed on every access - ui/manager.py's scrollbar-thumb drag
    handling compares `self._pressed is hit`/`self._dragging_thumb is
    hit`-style identity across many frames of the same drag, which only
    holds if the same Python object keeps coming back for the same
    underlying track/thumb."""

    def __init__(self, node):
        self._node = node
        # Plain instance attributes, not delegated - a write to either
        # (`element._cursor_index = ...`, ui/renderer.py's own caret
        # clamping) lands in this proxy's own __dict__ and is found there
        # on the next read, before __getattr__'s delegation to self._node
        # even runs. A scrollbar track/thumb is never itself an editable
        # text field, but UIRenderer's _draw_text() touches these
        # unconditionally on every element it draws (see its own comment
        # on why - a focused field's caret has to draw even with no text
        # yet), track/thumb included.
        self._cursor_index = 0
        self._text_view_offset = 0.0

    def __getattr__(self, name):
        return getattr(self._node, name)

    def __eq__(self, other):
        other_node = other._node if isinstance(other, _ScrollbarPartProxy) else other
        return self._node is other_node

    def __hash__(self):
        return hash(self._node)

    @property
    def children(self):
        return _ChildrenView(self._node)

    @property
    def _layout(self) -> Layout:
        return Layout(self._node.x, self._node.y, self._node.width, self._node.height)

    @property
    def state(self):
        from FreeBodyEngine.ui.element import ElementStates
        return ElementStates(self._node.get_state())

    def get_overflow(self, styles: dict = None) -> str:
        if styles is None:
            styles = self._node.get_current_styles()
        return self._node.get_overflow(styles)

    def set_state(self, state) -> None:
        # A scrollbar thumb/track is a real, hit-testable element -
        # ui/manager.py's ordinary hover/press/click dispatch calls this
        # on it exactly like any other element (ElementStates enum
        # member, not a plain string - see UIElement.set_state's own
        # comment on why).
        self._node.set_state(state.value if hasattr(state, "value") else state)

    def get_state(self):
        from FreeBodyEngine.ui.element import ElementStates
        return ElementStates(self._node.get_state())

    def _emit(self, event: str, *args) -> None:
        self._node.emit(event, *args)

    def add(self, element) -> None:
        self._node.add_child(element)

    def scroll_by(self, delta_px: float) -> None:
        self._node._scroll_offset += delta_px

    def _draw(self):
        pass

    def _update(self):
        pass

    @property
    def parent(self):
        parent_node = self._node.get_parent()
        return _wrap_child(parent_node) if parent_node is not None else None

    @property
    def _scrollbar_owner(self):
        return self._node.scrollbar_owner()


# id(bare Node) -> _ScrollbarPartProxy. Keyed by the object itself (not
# id()) so holding a cache entry also holds a real reference to the
# wrapped Node, sidestepping any id()-reuse-after-GC staleness risk -
# harmless here anyway since a scrollable element's track/thumb already
# live for as long as it does (held by its own _scroll_track_/_thumb_
# shared_ptr members on the C++ side), not just for as long as this cache
# entry does.
_scrollbar_proxy_cache: dict = {}


def _wrap_child(child):
    """Returns `child` unchanged if it's already a real UIElement, or the
    cached _ScrollbarPartProxy for it otherwise - see that class's own
    docstring. Every UIElement.children/RootElement.children read goes
    through this, not just scrollbar-adjacent code, since a plain
    dict-comprehension can't tell which case it's in without checking."""
    if isinstance(child, UIElement):
        return child
    proxy = _scrollbar_proxy_cache.get(child)
    if proxy is None:
        proxy = _ScrollbarPartProxy(child)
        _scrollbar_proxy_cache[child] = proxy
    return proxy


class UIElement(Node):
    """Drop-in replacement for ui.element.UIElement - same constructor
    shape, same public method names/behavior. This class *is* the
    compiled Node (see the module docstring); every method below exists
    only to bridge a real naming/shape difference from the old
    implementation, not to add a processing layer in front of Node's own
    bindings."""

    # Re-exposed for any code that references these on the class itself
    # (documentation, validation) rather than through an instance - kept
    # as the single source of truth in ui.element rather than duplicated
    # here, so the two implementations' defaults can't silently drift
    # apart from each other over time.
    VALID_ANCHORS = _PyUIElement.VALID_ANCHORS
    VALID_OVERFLOWS = _PyUIElement.VALID_OVERFLOWS
    DEFAULT_STYLES = _PyUIElement.DEFAULT_STYLES

    def __init__(self, tag: str = None, styles: dict = None):
        super().__init__(self.DEFAULT_STYLES)
        self.tag = tag
        self.animations: list[UIAnimation] = []
        # Editable-field cursor state - see ui/manager.py's _on_key() and
        # ui/renderer.py's _draw_text(), neither of which is being touched
        # by this rewrite (see the class-bind design discussion on why
        # text stays entirely Python-side) - plain Python attributes here
        # since Node has no notion of either.
        self._cursor_index = 0
        self._text_view_offset = 0.0
        # Keeps every added child's *Python* wrapper alive for as long as
        # it's actually attached here - see add()'s own comment on why
        # this exists (a real, confirmed bug otherwise, not a
        # precaution): pybind11's identity registry only holds a *weak*
        # association between a C++ object and its Python wrapper. The
        # C++ side's own shared_ptr (in this element's children_) keeps
        # the underlying object alive fine on its own, but once nothing
        # on the *Python* side still references a child (its only
        # variable went out of scope, say - an ordinary, common pattern:
        # `row = UIElement(...); container.add(row)` in a loop, never
        # keeping `row` around afterward), CPython collects that wrapper
        # immediately. The next get_children() call then has to build a
        # brand new wrapper for the same underlying object - and a
        # C++-side-constructed wrapper always comes back as plain Node,
        # never UIElement (see node.hpp's own comment on why pybind11
        # can't preserve a Python subclass through that path) - silently
        # losing every UIElement-only behavior (state, event callbacks,
        # .children, everything ui/manager.py's hit-testing/scroll-target
        # walk depends on) on whatever child happened to get collected.
        # Confirmed via a real repro, not theorized - this is what was
        # actually causing "scrolling doesn't work a lot of the time".
        self._py_children: list = []

        for key, value in (styles or {}).items():
            self.set_style(key, value)

    # -- styles / animation ------------------------------------------------
    # Animations stay Python-side permanently (see node.hpp's own class
    # docstring on why) - set_style(duration=...) still creates the same
    # UIAnimation the pure-Python implementation always did, it just lands
    # each frame's interpolated value via Node.set_style() (aliased below
    # as _set_style, the private name UIAnimation.update() calls) instead
    # of the old UIElement's.
    def set_style(self, name, val, duration: float = 0, curve=Linear):
        if duration == 0:
            super().set_style(name, val)
        else:
            self.animations.append(UIAnimation(self, name, val, duration, curve))

    def _set_style(self, name, val):
        super().set_style(name, val)

    def get_overflow(self, styles: dict = None) -> str:
        # Node.get_overflow() takes a required argument (see its own
        # comment in node.hpp on why) - this restores the old optional-
        # argument shape ui/manager.py and ui/renderer.py both call it
        # with.
        if styles is None:
            styles = self.get_current_styles()
        return super().get_overflow(styles)

    def _update(self):
        for animation in self.animations:
            animation.update()

    def set_state(self, state) -> None:
        # ui/manager.py calls this with an ElementStates enum member
        # (element.py's own ElementStates, shared by both backends - see
        # its docstring on why FOCUSED's value is "selected" not
        # "focused") everywhere it sets state - Node.set_state() only
        # takes the plain string itself.
        super().set_state(state.value if hasattr(state, "value") else state)

    def get_state(self):
        from FreeBodyEngine.ui.element import ElementStates
        return ElementStates(super().get_state())

    @property
    def state(self):
        # UIRenderer reads element.state directly (`element.state ==
        # ElementStates.FOCUSED`, for caret visibility) rather than
        # through get_state() - deliberately left untouched by this
        # rewrite, so this has to exist as a plain attribute too.
        return self.get_state()

    # -- tree / event naming compatibility ----------------------------------
    def add(self, element: 'UIElement') -> None:
        # Order matters: append to the Python-side keepalive list *before*
        # add_child() - see __init__'s own comment on why this list exists
        # at all.
        self._py_children.append(element)
        self.add_child(element)

    def remove(self, element: 'UIElement') -> None:
        self.remove_child(element)
        for i, child in enumerate(self._py_children):
            if child is element:
                del self._py_children[i]
                break

    def _emit(self, event: str, *args) -> None:
        self.emit(event, *args)

    def scroll_by(self, delta_px: float) -> None:
        self._scroll_offset += delta_px

    def _draw(self):
        pass

    @property
    def parent(self):
        return self.get_parent()

    @property
    def _scrollbar_owner(self):
        return self.scrollbar_owner()

    @property
    def children(self):
        # A live view (_ChildrenView, see its own docstring), not a
        # uuid-keyed dict the way the old GenericElement.children was -
        # nothing outside ui/element.py's own internals ever indexes it
        # by key, only .values()/.clear()/truthiness (checked via a real
        # grep across this engine and phonon, not guessed) - but it does
        # have to be *live*: phonon calls `.children.clear()` in over a
        # dozen places to empty a container before rebuilding it, and a
        # snapshot dict makes that silently do nothing.
        return _ChildrenView(self)

    @property
    def _layout(self) -> Layout:
        # UIRenderer reads element._layout.x/.y/.width/.height for every
        # element it draws - deliberately left untouched by this rewrite
        # (see the class-bind design discussion), so this reconstructs
        # the same Layout shape it expects from Node's flat x/y/width/
        # height attributes, fresh on each read.
        return Layout(self.x, self.y, self.width, self.height)


class RootElement(Node):
    """Drop-in replacement for ui.element.RootElement - see UIElement's
    own docstring above for the "thin subclass, not a wrapper" reasoning,
    which applies identically here."""

    def __init__(self, width: int, height: int, styles: dict = None):
        super().__init__(UIElement.DEFAULT_STYLES)
        self.x = 0.0
        self.y = 0.0
        self.width = float(width)
        self.height = float(height)
        # See UIElement.__init__'s own (much longer) comment on why this
        # exists - the same real, confirmed GC-identity bug applies to the
        # root's own direct children (main_panel, every _open_modal()
        # backdrop) exactly as much as to any other element.
        self._py_children: list = []
        for key, value in (styles or {}).items():
            self.set_style(key, value)

    def set_styles(self, styles: dict):
        for key, value in styles.items():
            self.set_style(key, value)

    def add(self, element: 'UIElement') -> None:
        self._py_children.append(element)
        self.add_child(element)

    def remove(self, element: 'UIElement') -> None:
        self.remove_child(element)
        for i, child in enumerate(self._py_children):
            if child is element:
                del self._py_children[i]
                break

    def _draw(self):
        pass

    def _update(self):
        # See GenericElement._update()'s own no-op in ui/element.py -
        # matched here rather than "fixed": ui/manager.py's update() only
        # ever calls this on the root, and RootElement never overrode it
        # to cascade into children there either, so per-element animation
        # ticking (UIElement._update()) isn't actually reachable from
        # anywhere in the existing pure-Python implementation - a
        # pre-existing gap in that system, not something this rewrite
        # should silently start doing differently.
        pass

    def calculate_layout(self):
        window = get_service("window")
        scale = window.content_scale if window is not None else 1.0
        self.calculate_root_layout(self.width, self.height, scale)

    @property
    def layout(self) -> Layout:
        # Read-only - see ui/manager.py's resize(), which was updated to
        # write self.root.width/height directly instead of through
        # self.root.layout.width/height (a write through this property
        # would silently mutate a throwaway Layout and have no effect).
        return Layout(self.x, self.y, self.width, self.height)

    @property
    def children(self):
        return _ChildrenView(self)
