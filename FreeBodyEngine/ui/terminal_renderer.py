"""Terminal implementation of the 'ui_renderer' service (see
ui.get_ui_renderer() and core/window/terminal.py's own module docstring
for the broader architecture) - draws the same UI tree UIRenderer
(ui/renderer.py) does, but as literal characters written into
TerminalWindow's `ui_overlay` buffer instead of GL draw calls.

Deliberately a fresh, standalone class rather than a UIRenderer subclass:
UIRenderer.__init__ does GL-specific setup (a shared background quad mesh,
an FBUSL material/shader) this backend has no use for at all - every
"draw" here is just writing (char, fg, bg) tuples into a dict, since a
terminal cell already *is* a flat-colored, monospaced unit with nothing
to rasterize. That also means text needs no font/atlas/glyph-metrics
machinery whatsoever: a terminal's own monospace font makes "measuring"
text trivial (`len(text)`), unlike UIRenderer._draw_text's real
text_renderer.measure_text() calls against actual font metrics.

Mirrors UIRenderer.draw()'s recursive _draw_element() tree-walk and
scissor-rect clipping logic (see that method's own extensive docs for why
both exist) closely enough that a bug fixed in one is worth checking in
the other, but doesn't share code with it - GL draw calls and terminal-
cell writes have too little in common to make a shared base worthwhile
here.
"""
from FreeBodyEngine.core.service import Service
from FreeBodyEngine import register_service_update, unregister_service_update, get_service
from FreeBodyEngine.core.update import UpdatePhase
from FreeBodyEngine.ui.element import ElementStates

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from FreeBodyEngine.ui import UIManager
    from FreeBodyEngine.ui.element import UIElement
    from FreeBodyEngine.core.window.terminal import TerminalWindow


def _color_to_rgb(value) -> tuple:
    """Converts a style color (an (r, g, b[, a]) tuple of 0..1 floats -
    see ui/renderer.py's own `base_color`/`text_color`/etc. styles) to a
    plain 0-255 int RGB triple for an ANSI truecolor escape. Alpha is
    ignored - there's no real compositing against whatever's underneath a
    terminal cell, unlike a GPU blend; a translucent style just reads as
    fully opaque here rather than not drawing at all, the closest
    approximation available."""
    r, g, b = value[0], value[1], value[2]
    return (int(max(0.0, min(1.0, r)) * 255), int(max(0.0, min(1.0, g)) * 255), int(max(0.0, min(1.0, b)) * 255))


class TerminalUIRenderer(Service):
    """See module docstring. Registered under the same 'ui_renderer' name
    UIRenderer uses, so anything doing `get_service('ui_renderer')`
    doesn't need to know or care which backend actually implements it."""

    def __init__(self):
        super().__init__('ui_renderer')
        self.dependencies.append('ui')
        self.dependencies.append('window')

    def on_initialize(self):
        register_service_update(UpdatePhase.DRAW, self.draw)
        self.ui: 'UIManager' = get_service('ui')
        self.window: 'TerminalWindow' = get_service('window')

    def on_destroy(self):
        unregister_service_update(UpdatePhase.DRAW, self.draw)

    def draw(self):
        """Draws every top-level element of the UI tree (and, recursively,
        their children) into `self.window.ui_overlay` - painter's-algorithm
        order, later siblings/children overwriting earlier ones' cells,
        same as UIRenderer.draw()."""
        for element in self.ui.root.children.values():
            self._draw_element(element, None)

    @staticmethod
    def _intersect_rect(a: tuple, b: tuple) -> tuple:
        """See UIRenderer._intersect_rect - identical rect-intersection math."""
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        x = max(ax, bx)
        y = max(ay, by)
        x2 = min(ax + aw, bx + bw)
        y2 = min(ay + ah, by + bh)
        return (x, y, max(0.0, x2 - x), max(0.0, y2 - y))

    def _draw_element(self, element: 'UIElement', scissor: tuple):
        """See UIRenderer._draw_element - same offscreen-skip/scissor-
        inheritance/recursion shape, minus the GPU-specific scissor
        binding (a cell either falls inside the current clip rect or it
        doesn't - checked per-cell in _set_cell() instead of via a bound
        GPU scissor rect)."""
        layout = element._layout

        if scissor is not None and layout.width > 0 and layout.height > 0:
            sx, sy, sw, sh = scissor
            if (
                layout.x >= sx + sw or layout.x + layout.width <= sx or
                layout.y >= sy + sh or layout.y + layout.height <= sy
            ):
                return

        styles = element.get_current_styles()

        self._draw_background(element, styles, scissor)
        self._draw_text(element, styles, scissor)

        child_scissor = scissor
        if element.get_overflow(styles) != "visible":
            own_rect = (layout.x, layout.y, layout.width, layout.height)
            child_scissor = (
                self._intersect_rect(scissor, own_rect) if scissor is not None else own_rect
            )

        for child in element.children.values():
            self._draw_element(child, child_scissor)

    def _in_scissor(self, col: int, row: int, scissor: tuple) -> bool:
        if scissor is None:
            return True
        sx, sy, sw, sh = scissor
        return sx <= col < sx + sw and sy <= row < sy + sh

    def _set_cell(self, col: int, row: int, char: str, fg: tuple, bg: tuple, scissor: tuple):
        col, row = int(col), int(row)
        if col < 0 or row < 0 or col >= self.window._columns or row >= self.window._rows:
            return
        if not self._in_scissor(col, row, scissor):
            return
        self.window.ui_overlay[(col, row)] = (char, fg, bg)

    def _draw_background(self, element: 'UIElement', styles: dict, scissor: tuple):
        layout = element._layout
        width, height = int(layout.width), int(layout.height)
        if width <= 0 or height <= 0:
            return

        base_color = _color_to_rgb(styles.get('base_color', (1.0, 1.0, 1.0, 1.0)))
        # Rounded corners (border_radius) have no meaningful ASCII
        # equivalent and are ignored entirely here - every element draws
        # as a plain rectangle, straight border included.
        border_width = styles.get('border_width', 0)
        has_border = (border_width if isinstance(border_width, (int, float)) else border_width[0]) > 0
        border_color = _color_to_rgb(styles.get('border_color', (0.0, 0.0, 0.0, 1.0))) if has_border else None

        x0, y0 = int(layout.x), int(layout.y)
        for row in range(y0, y0 + height):
            for col in range(x0, x0 + width):
                if has_border and (row == y0 or row == y0 + height - 1 or col == x0 or col == x0 + width - 1):
                    if row == y0 or row == y0 + height - 1:
                        char = "+" if col in (x0, x0 + width - 1) else "-"
                    else:
                        char = "|"
                    self._set_cell(col, row, char, border_color, None, scissor)
                else:
                    self._set_cell(col, row, " ", base_color, base_color, scissor)

    def _draw_text(self, element: 'UIElement', styles: dict, scissor: tuple):
        text = styles.get('text') or ''
        show_cursor = styles.get('editable', False) and element.state == ElementStates.FOCUSED
        if not text and not show_cursor:
            return

        if styles.get('secret', False):
            text = '*' * len(text)

        layout = element._layout
        pad = styles.get('padding', 0)
        pad_left = int(styles.get('padding_left', pad))
        pad_top = int(styles.get('padding_top', pad))
        pad_right = int(styles.get('padding_right', pad))

        available_width = max(0, int(layout.width) - pad_left - pad_right)
        if available_width <= 0:
            return

        text_color = _color_to_rgb(styles.get('text_color', (1.0, 1.0, 1.0, 1.0)))

        # A terminal's font is already monospace - "measuring" text is
        # just its length, no font metrics needed at all (contrast
        # UIRenderer._draw_text's real text_renderer.measure_text() calls).
        element._cursor_index = max(0, min(element._cursor_index, len(text)))
        cursor_index = element._cursor_index

        editable = styles.get('editable', False)
        view_offset = 0
        if editable and len(text) > available_width:
            # Keep the cursor in view by scrolling the visible window,
            # same intent as UIRenderer._draw_text's own view_offset -
            # simplified since there's no sub-character scrolling to do
            # in a character grid.
            if cursor_index > available_width:
                view_offset = cursor_index - available_width
            visible = text[view_offset:view_offset + available_width]
        elif not editable and len(text) > available_width:
            ellipsis = "..." if available_width >= 3 else "." * available_width
            visible = (text[:max(0, available_width - len(ellipsis))] + ellipsis) if available_width > 0 else ""
        else:
            visible = text

        # Vertically centered in the element's own box, single line only -
        # this engine's UI text is effectively always single-line (see
        # UIRenderer._draw_text's own line_height/baseline math, which
        # this mirrors the *intent* of without needing font ascender/
        # descender values a terminal font has no equivalent for).
        row = int(layout.y) + max(0, (int(layout.height) - 1) // 2)
        start_col = int(layout.x) + pad_left

        for offset, char in enumerate(visible):
            self._set_cell(start_col + offset, row, char, text_color, None, scissor)

        if show_cursor:
            cursor_col = start_col + (cursor_index - view_offset)
            self._set_cell(cursor_col, row, "_", text_color, None, scissor)
