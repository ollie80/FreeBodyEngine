"""Native (C++/pybind11) backing for UIElement/RootElement - Python
subclasses of the compiled Node class (see ui/native/node.hpp). Layout and
style merging run in C++; flags, handlers, animation and the styles/style/
visible/rect properties come from ui/base.py, shared with the pure-Python
backend (ui/element.py), and this file supplies only the primitives those
build on (see ui/base.py's docstring) plus the few places Node's shape
differs. Every method not defined here or in ui/base.py resolves straight
through to Node's own C++ binding with no extra Python dispatch.

Only importable where the compiled extension actually exists - see
ui/__init__.py's own flag/platform resolution for when this is chosen
over ui/element.py's pure-Python implementation (used unconditionally on
web, where no compiled extension can exist at all, and as an automatic
fallback anywhere the native module hasn't been built).

Imports the compiled `_fbengine_ui` extension directly
(`_fbengine_ui.node.Node` - named by scripts/build_native.py so it can't
collide with a project's own `_fbcpp`)
rather than through cli/cpp/compile.py's generated `node.py` convenience
shim (`from node import Node`, relying on sys.path containing
ui/native/cpp_scripts/) - that shim exists so *project* C++ scripts can
be imported by bare file name, but this module already knows exactly
which extension and submodule it wants, and the shim's own sys.path
requirement doesn't hold on every platform this needs to work on: a
desktop dev build's `_fbengine_ui` sits at ui/native/cpp_scripts/ and needs the
sys.path insertion below to be found at all, but an Android build's
`_fbengine_ui` is installed by python-for-android's own `pip install .` step
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

import _fbengine_ui  # noqa: E402 - the compiled extension itself, see the module docstring
Node = _fbengine_ui.node.Node  # noqa: E402

from FreeBodyEngine.ui import element as _element  # noqa: E402
from FreeBodyEngine.ui.element import _safe_area_insets  # noqa: E402
from FreeBodyEngine.ui.base import (  # noqa: E402
    DEFAULT_STYLES, Layout, TreeBehaviour, ElementBehaviour, UIAnimation,
)
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


class _ScrollbarPartProxy(ElementBehaviour):
    """Thin, cold-path wrapper around a scrollbar track/thumb - the two
    Node children Node::update_scrollbar() creates *inside* C++ (see its
    own comment in node.hpp on why pybind11 has no way to hand those back
    as anything but the plain base Node, even though the rest of the tree
    is UIElement throughout - a pybind11 object's Python type is fixed at
    construction, and neither a shared_ptr round-trip through a stored
    Python factory nor reassigning __class__ on the returned object
    (CPython refuses it - UIElement's __dict__ gives it a different
    deallocator than plain Node) got around that).

    Gets everything an element does from ui/base.py's ElementBehaviour,
    like UIElement, by supplying its primitives onto the wrapped Node;
    anything else is delegated to the Node via __getattr__.

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
        # What ElementBehaviour needs set up - UIManager hovers and presses
        # a thumb like any other element.
        self._flags = []
        self._handlers = {}
        self._style = None
        self.animations: list[UIAnimation] = []

    def __getattr__(self, name):
        return getattr(self._node, name)

    # -- ElementBehaviour's primitives, onto the wrapped Node ----------------
    def _raw_styles(self) -> dict:
        return Node.styles.__get__(self._node)

    def _set_raw_styles(self, styles: dict):
        Node.styles.__set__(self._node, styles)

    def _invalidate_styles(self):
        self._node.invalidate_styles()

    def _set_style(self, name, val):
        self._node.set_style(name, val)

    @property
    def _style_base(self) -> dict:
        return self._node._base_styles

    @_style_base.setter
    def _style_base(self, value: dict):
        self._node._base_styles = value

    def _apply_style_keys(self, keys):
        self._node.set_style_keys(keys)

    def _register(self, event, callback):
        self._node.on(event, callback)

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

    def get_overflow(self, styles: dict = None) -> str:
        if styles is None:
            styles = self._node.get_current_styles()
        return self._node.get_overflow(styles)

    def _emit(self, event: str, *args) -> None:
        self._node.emit(event, *args)

    def add(self, element) -> None:
        self._node.add_child(element)

    @property
    def _scroll_offset(self) -> float:
        return self._node._scroll_offset

    @_scroll_offset.setter
    def _scroll_offset(self, value: float):
        self._node._scroll_offset = value

    def _draw(self):
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


def _measure_text(styles):
    # Looked up on each call, not bound once, so it can be replaced (tests
    # stand one in for the real font pipeline).
    return _element.measure_text(styles)


Node(DEFAULT_STYLES).set_text_measurer(_measure_text)


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


class _NativeTree(TreeBehaviour):
    """What UIElement and RootElement here both are on top of Node: the
    TreeBehaviour primitives (see ui/base.py) over Node's own style dict,
    and a children list whose Python wrappers stay alive."""

    def _init_tree(self, styles):
        # Keeps every added child's *Python* wrapper alive for as long as
        # it's attached - pybind11 only holds a *weak* association between
        # a C++ object and its Python wrapper. Node's own shared_ptr keeps
        # the child alive, but once nothing on the Python side references
        # its wrapper (`row = UIElement(...); container.add(row)` in a loop,
        # the common case), CPython collects it, and the next
        # get_children() builds a fresh wrapper that comes back as plain
        # Node, not UIElement (see node.hpp on why pybind11 can't preserve
        # a Python subclass that way) - losing flags, handlers, .children
        # and everything else Python-side on whatever child got collected.
        # This is what was causing "scrolling doesn't work a lot of the
        # time".
        self._py_children: list = []
        self.styles = styles

    # -- TreeBehaviour's primitives -------------------------------------------
    # The StyleView `styles` returns is over Node's own dict, so a write
    # into it invalidates Node's memoized get_current_styles().
    def _raw_styles(self) -> dict:
        return Node.styles.__get__(self)

    def _set_raw_styles(self, styles: dict):
        Node.styles.__set__(self, styles)

    def _invalidate_styles(self):
        self.invalidate_styles()

    # -- tree --------------------------------------------------------------------
    def add(self, element: 'UIElement') -> None:
        # Order matters: kept alive *before* add_child() - see _init_tree().
        self._py_children.append(element)
        self.add_child(element)

    def remove(self, element: 'UIElement') -> None:
        self.remove_child(element)
        for i, child in enumerate(self._py_children):
            if child is element:
                del self._py_children[i]
                break

    @property
    def children(self):
        # A live view (_ChildrenView, see its own docstring), not a
        # snapshot: phonon calls `.children.clear()` in over a dozen places
        # to empty a container before rebuilding it.
        return _ChildrenView(self)

    def _draw(self):
        pass


class UIElement(ElementBehaviour, _NativeTree, Node):
    """The native backend's UIElement - the compiled Node itself, with
    ui/base.py's ElementBehaviour on top. Same constructor and public
    surface as ui/element.py's; what's here is only the primitives
    ElementBehaviour builds on, and the few places Node's shape differs."""

    def __init__(self, tag: str = None, styles: dict = None, style=None):
        super().__init__(DEFAULT_STYLES)
        self.tag = tag
        self._style = None
        self._flags = []
        self._handlers = {}
        self.animations: list[UIAnimation] = []
        # Editable-field cursor state - see ui/manager.py's _on_key() and
        # ui/renderer.py's _draw_text(); text stays Python-side, so Node has
        # no notion of either.
        self._cursor_index = 0
        self._text_view_offset = 0.0
        self._init_tree(styles)
        if style is not None:
            self.style = style

    # -- ElementBehaviour's primitives --------------------------------------------
    def _set_style(self, name, val):
        Node.set_style(self, name, val)

    @property
    def _style_base(self) -> dict:
        return self._base_styles

    @_style_base.setter
    def _style_base(self, value: dict):
        self._base_styles = value

    def _apply_style_keys(self, keys):
        self.set_style_keys(keys)

    def _register(self, event, callback):
        Node.on(self, event, callback)

    def _emit(self, event: str, *args) -> None:
        self.emit(event, *args)

    # -- where Node's shape differs --------------------------------------------------
    def get_overflow(self, styles: dict = None) -> str:
        # Node.get_overflow() takes a required argument (see node.hpp) -
        # this restores the optional one ui/manager.py and ui/renderer.py
        # call it with.
        if styles is None:
            styles = self.get_current_styles()
        return super().get_overflow(styles)

    @property
    def parent(self):
        return self.get_parent()

    @property
    def _scrollbar_owner(self):
        return self.scrollbar_owner()

    @property
    def _layout(self) -> Layout:
        # UIRenderer/UIManager read element._layout.x/.y/.width/.height -
        # rebuilt from Node's flat attributes on each read.
        return Layout(self.x, self.y, self.width, self.height)


class RootElement(_NativeTree, Node):
    """The native backend's RootElement - see UIElement above."""

    def __init__(self, width: int, height: int, styles: dict = None):
        super().__init__(DEFAULT_STYLES)
        self.x = 0.0
        self.y = 0.0
        self.width = float(width)
        self.height = float(height)
        self._init_tree(styles)

    def calculate_layout(self):
        window = get_service("window")
        scale = window.content_scale if window is not None else 1.0
        insets = _safe_area_insets() if self.get_current_styles().get("safe_area", False) else (0.0, 0.0, 0.0, 0.0)
        self.calculate_root_layout(self.width, self.height, scale, *insets)

    @property
    def layout(self) -> Layout:
        # Read-only - see ui/manager.py's resize(), which writes
        # self.root.width/height directly (a write through this would
        # mutate a throwaway Layout and have no effect).
        return Layout(self.x, self.y, self.width, self.height)
