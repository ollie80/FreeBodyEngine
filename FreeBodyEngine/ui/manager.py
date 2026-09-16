from FreeBodyEngine.core.service import Service
from FreeBodyEngine.ui.element import RootElement, UIElement, GenericElement, ElementStates
from FreeBodyEngine.core.update import UpdatePhase
from FreeBodyEngine import register_event_callback, unregister_event_callback, register_service_update, unregister_service_update, get_service
from FreeBodyEngine.core.window import FRAMEBUFFER_RESIZE
from FreeBodyEngine.core.input import Key, KEY_PRESS, KEY_REPEAT
from FreeBodyEngine.math import Vector

LEFT_MOUSE_BUTTON = 0

# Deliberately minimal - US-QWERTY only, no IME/dead-keys/non-US layouts.
# Good enough for search boxes and short text fields (see the "editable"
# style docs in ui/element.py), not a general text editor. Each entry is
# (unshifted, shifted).
KEY_CHAR_MAP = {
    Key.A: ('a', 'A'), Key.B: ('b', 'B'), Key.C: ('c', 'C'), Key.D: ('d', 'D'),
    Key.E: ('e', 'E'), Key.F: ('f', 'F'), Key.G: ('g', 'G'), Key.H: ('h', 'H'),
    Key.I: ('i', 'I'), Key.J: ('j', 'J'), Key.K: ('k', 'K'), Key.L: ('l', 'L'),
    Key.M: ('m', 'M'), Key.N: ('n', 'N'), Key.O: ('o', 'O'), Key.P: ('p', 'P'),
    Key.Q: ('q', 'Q'), Key.R: ('r', 'R'), Key.S: ('s', 'S'), Key.T: ('t', 'T'),
    Key.U: ('u', 'U'), Key.V: ('v', 'V'), Key.W: ('w', 'W'), Key.X: ('x', 'X'),
    Key.Y: ('y', 'Y'), Key.Z: ('z', 'Z'),

    Key.ONE: ('1', '!'), Key.TWO: ('2', '@'), Key.THREE: ('3', '#'),
    Key.FOUR: ('4', '$'), Key.FIVE: ('5', '%'), Key.SIX: ('6', '^'),
    Key.SEVEN: ('7', '&'), Key.EIGHT: ('8', '*'), Key.NINE: ('9', '('),
    Key.ZERO: ('0', ')'),

    Key.SPACE: (' ', ' '),
    Key.MINUS: ('-', '_'), Key.EQUAL: ('=', '+'),
    Key.LEFT_BRACKET: ('[', '{'), Key.RIGHT_BRACKET: (']', '}'),
    Key.BACKSLASH: ('\\', '|'), Key.SEMICOLON: (';', ':'),
    Key.APOSTROPHE: ("'", '"'), Key.TILDE: ('`', '~'),
    Key.COMMA: (',', '<'), Key.PERIOD: ('.', '>'), Key.SLASH: ('/', '?'),
}


class UIManager(Service):
    """Engine service owning the UI tree's root element - the entry point for
    adding/removing top-level UI elements, and for driving their layout/
    animation update plus mouse hit-testing, keyboard text-input routing,
    and wheel scrolling (see the INTERACTION style docs in ui/element.py)."""

    # Pixels of scroll per unit of Mouse.get_scroll_delta() - tuned to feel
    # roughly like a native scrollable list under a standard mouse wheel.
    SCROLL_SPEED = 40.0

    def __init__(self, styles: dict[str, any] = {}):
        """Args:
            styles: Root-level styles, sized to the current framebuffer.
        """
        super().__init__('ui')

        win_size = get_service('window').framebuffer_size
        self.root = RootElement(win_size[0], win_size[1], styles)

        self._hovered: UIElement = None
        self._pressed: UIElement = None
        self._focused: UIElement = None

    def on_initialize(self):
        """Registers the resize/draw/update callbacks this service needs while active."""
        register_event_callback(FRAMEBUFFER_RESIZE, self.resize)
        register_service_update(UpdatePhase.DRAW, self.draw, 1000)
        register_service_update(UpdatePhase.UPDATE, self.update)
        register_event_callback(KEY_PRESS, self._on_key)
        register_event_callback(KEY_REPEAT, self._on_key)

    def on_destroy(self):
        """Unregisters the callbacks registered in `on_initialize`."""
        unregister_event_callback(FRAMEBUFFER_RESIZE, self.resize)
        unregister_service_update(UpdatePhase.DRAW, self.draw)
        unregister_service_update(UpdatePhase.UPDATE, self.update)
        unregister_event_callback(KEY_PRESS, self._on_key)
        unregister_event_callback(KEY_REPEAT, self._on_key)

    def resize(self, size: tuple[int, int]):
        """Resizes the root layout area to match the new framebuffer size."""
        self.root.layout.width = size[0]
        self.root.layout.height = size[1]


    def add(self, element: UIElement):
        """Adds `element` as a top-level child of the UI root."""
        self.root.add(element)

    def draw(self):
        """Draws the UI tree."""
        self.root._draw()

    def remove(self, element: UIElement):
        """Removes `element` from the UI root's children."""
        self.root.remove(element)

    def update(self):
        """Advances any running style animations, recalculates the whole
        tree's layout from the (possibly now-changed) styles, then runs
        mouse hit-testing/hover/click/scroll for this frame."""

        self.root._update()

        self.root.calculate_layout()

        self._handle_mouse()

    # -- hit-testing / mouse -----------------------------------------------

    def _hit_test(self, children: dict, point: Vector) -> UIElement:
        """Returns the most specific (deepest) element under `point`, or
        None. Siblings are checked topmost-first (later-added = drawn last
        = on top, matching UIRenderer's draw order), and a matched
        element's own children are always checked before falling back to
        the element itself, so a button inside a row is hit before the row
        is."""
        for element in reversed(list(children.values())):
            layout = element._layout
            if (
                layout.width > 0 and layout.height > 0 and
                layout.x <= point.x < layout.x + layout.width and
                layout.y <= point.y < layout.y + layout.height
            ):
                child_hit = self._hit_test(element.children, point)
                return child_hit if child_hit is not None else element

        return None

    def _find_scroll_target(self, element: UIElement) -> UIElement:
        """Walks up from `element` (inclusive) to the nearest ancestor with
        the "scroll" style on, or None if there isn't one."""
        node = element
        while isinstance(node, UIElement):
            if node.get_current_styles().get("scroll", False):
                return node
            node = node.parent if isinstance(node.parent, GenericElement) else None
        return None

    def _set_focus(self, element: UIElement):
        if element is self._focused:
            return

        if self._focused is not None:
            self._focused.set_state(
                ElementStates.HOVER if self._focused is self._hovered else ElementStates.NORMAL
            )

        self._focused = element

        if element is not None:
            element.set_state(ElementStates.FOCUSED)

    def _handle_mouse(self):
        if not self.root.children:
            return

        mouse = get_service('mouse')
        point = mouse.position
        hit = self._hit_test(self.root.children, point)

        #
        # Hover.
        #
        if hit is not self._hovered:
            if self._hovered is not None:
                self._hovered._emit("hover_exit")
                if self._hovered not in (self._pressed, self._focused):
                    self._hovered.set_state(ElementStates.NORMAL)

            if hit is not None:
                hit._emit("hover_enter")
                if hit not in (self._pressed, self._focused):
                    hit.set_state(ElementStates.HOVER)

            self._hovered = hit

        #
        # Press / focus. A click anywhere clears focus unless it landed on
        # an editable element - so clicking a button or empty space while a
        # search box is focused defocuses it, same as every other UI.
        #
        if mouse.get_pressed(LEFT_MOUSE_BUTTON):
            self._pressed = hit

            if hit is not None:
                hit.set_state(ElementStates.CLICKED)
                hit._emit("press")

                if hit.get_current_styles().get("editable", False):
                    self._set_focus(hit)
                else:
                    self._set_focus(None)
            else:
                self._set_focus(None)

        #
        # Release / click.
        #
        if mouse.get_released(LEFT_MOUSE_BUTTON):
            if self._pressed is not None:
                self._pressed._emit("release")

                if self._pressed is hit:
                    self._pressed._emit("click")

                if self._pressed is self._focused:
                    self._pressed.set_state(ElementStates.FOCUSED)
                elif self._pressed is hit:
                    self._pressed.set_state(ElementStates.HOVER)
                else:
                    self._pressed.set_state(ElementStates.NORMAL)

                self._pressed = None

        #
        # Scroll.
        #
        scroll_delta = mouse.get_scroll_delta()
        if hit is not None and (scroll_delta.x != 0 or scroll_delta.y != 0):
            target = self._find_scroll_target(hit)
            if target is not None:
                layout_dir = target.get_current_styles().get("layout", "vertical")
                amount = scroll_delta.y if layout_dir == "vertical" else scroll_delta.x
                target.scroll_by(-amount * self.SCROLL_SPEED)

    # -- keyboard / text input ----------------------------------------------

    def _on_key(self, key: Key):
        if self._focused is None:
            return

        styles = self._focused.get_current_styles()
        text = styles.get("text", "")

        if key == Key.BACKSPACE:
            if text:
                self._focused.set_style("text", text[:-1])
            return

        if key == Key.RETURN:
            self._focused._emit("submit", text)
            return

        if key == Key.ESCAPE:
            self._set_focus(None)
            return

        chars = KEY_CHAR_MAP.get(key)
        if chars is None:
            return

        window = get_service('window')
        shift = bool(window._get_key_down(Key.L_SHIFT)) or bool(window._get_key_down(Key.R_SHIFT))
        self._focused.set_style("text", text + chars[1 if shift else 0])
