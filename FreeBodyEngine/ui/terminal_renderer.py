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

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from FreeBodyEngine.ui import UIManager
    from FreeBodyEngine.ui.element import UIElement
    from FreeBodyEngine.core.window.terminal import TerminalWindow


def _cell_rect(layout) -> tuple:
    """A layout rect, in pixels, as the cell rect that covers it.

    The UI lays out in pixels here exactly as it does on every other
    backend (see TerminalWindow.framebuffer_size) - a terminal's character
    grid only exists at presentation. So every coordinate this renderer
    touches has to come through here first: left/top round down and
    right/bottom round up, so a one-pixel sliver still claims the cell it
    falls in rather than vanishing.
    """
    from FreeBodyEngine.core.window.terminal import CELL_PIXELS
    cw, ch = CELL_PIXELS
    x0 = int(layout.x // cw)
    y0 = int(layout.y // ch)
    x1 = int(-(-(layout.x + layout.width) // cw))
    y1 = int(-(-(layout.y + layout.height) // ch))
    return x0, y0, max(0, x1 - x0), max(0, y1 - y0)


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

    _image_cache: dict = {}

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
        rect = _cell_rect(layout)

        if not element.get_current_styles().get("visible", True):
            return

        if scissor is not None and rect[2] > 0 and rect[3] > 0:
            sx, sy, sw, sh = scissor
            if (
                rect[0] >= sx + sw or rect[0] + rect[2] <= sx or
                rect[1] >= sy + sh or rect[1] + rect[3] <= sy
            ):
                return

        styles = element.get_current_styles()

        self._draw_background(element, styles, scissor)
        self._draw_text(element, styles, scissor)

        child_scissor = scissor
        if element.get_overflow(styles) != "visible":
            own_rect = rect
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
        x0, y0, width, height = _cell_rect(layout)
        if width <= 0 or height <= 0:
            return

        # An `image` style is a real picture on every other backend (see
        # UIRenderer._resolve_image) and was simply dropped here, so album
        # art, avatars and cover images did not exist in a terminal at all.
        if styles.get('image'):
            if self._draw_image(styles, x0, y0, width, height, scissor):
                return

        base_color = _color_to_rgb(styles.get('base_color', (1.0, 1.0, 1.0, 1.0)))
        # Rounded corners (border_radius) have no meaningful ASCII
        # equivalent and are ignored entirely here - every element draws
        # as a plain rectangle, straight border included.
        border_width = styles.get('border_width', 0)
        has_border = (border_width if isinstance(border_width, (int, float)) else border_width[0]) > 0
        border_color = _color_to_rgb(styles.get('border_color', (0.0, 0.0, 0.0, 1.0))) if has_border else None

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

    def _image_pixels(self, image):
        """An `image` style as an (h, w, 3) uint8 array, or None.

        Decoded straight from the asset bytes rather than through
        load_file(): that returns a GL Texture, whose pixels live on the GPU
        and would need a round trip to read back. A terminal needs them on
        the CPU anyway, and the file system service resolves an
        asset-relative path identically in a dev tree and a packed build.

        Cached per style value, because an element re-resolves its styles
        every frame and decoding album art sixty times a second would cost
        more than the whole rest of this renderer put together. A failure
        caches None too, so a missing or GPU-only image is attempted once.
        """
        if not isinstance(image, str):
            # An animated cover sets the style to a live Texture (see
            # phonon's AnimatedArtService) - GPU-only, nothing to sample
            # without a readback, so it falls back to a flat panel.
            return None
        if image in self._image_cache:
            return self._image_cache[image]

        pixels = None
        try:
            import io
            import numpy as np
            from PIL import Image

            resource = get_service('files').get_file(image)
            if resource is not None:
                data = resource.read(bytes=True)
                with Image.open(io.BytesIO(data)) as decoded:
                    pixels = np.asarray(decoded.convert('RGB'), dtype=np.uint8)
        except Exception:
            pixels = None

        self._image_cache[image] = pixels
        return pixels

    def _draw_image(self, styles: dict, x0: int, y0: int, width: int,
                    height: int, scissor: tuple) -> bool:
        """Draws an `image` style across a cell rect. False if it could not.

        One cell gets the average of the source pixels that fall in it, as a
        solid block - the same box filter TerminalWindow.draw() uses for the
        rendered world, so a picture in the UI and the scene behind it are
        reduced the same way and look like one image rather than two
        techniques.
        """
        pixels = self._image_pixels(styles.get('image'))
        if pixels is None or width <= 0 or height <= 0:
            return False

        import numpy as np
        src_h, src_w = pixels.shape[0], pixels.shape[1]
        if src_h == 0 or src_w == 0:
            return False

        # Nearest-neighbour cell centres into the source, then a mean over
        # each cell's own footprint via reduceat - no interpolation library
        # needed and no per-cell Python slicing.
        rows = (np.arange(height) * src_h) // height
        cols = (np.arange(width) * src_w) // width
        sampled = pixels[rows][:, cols]

        for row in range(height):
            for col in range(width):
                r, g, b = sampled[row, col]
                colour = (int(r), int(g), int(b))
                self._set_cell(x0 + col, y0 + row, " ", colour, colour, scissor)
        return True

    def _draw_text(self, element: 'UIElement', styles: dict, scissor: tuple):
        text = styles.get('text') or ''
        show_cursor = styles.get('editable', False) and element.has_flag("focused")
        if not text and not show_cursor:
            return

        if styles.get('secret', False):
            text = '*' * len(text)

        from FreeBodyEngine.core.window.terminal import CELL_PIXELS
        cell_w = CELL_PIXELS[0]

        layout = element._layout
        x0, y0, width, height = _cell_rect(layout)

        # Padding is authored in pixels like everything else, so it has to be
        # converted before it is subtracted from a width measured in cells.
        # Subtracting pixels from cells is what hid every button label in
        # phonon: a button 90 pixels wide is about 11 cells, and 12 pixels of
        # padding either side read as 24 cells, so available_width came out
        # negative and the text was skipped entirely.
        pad = styles.get('padding', 0)
        pad_left = int(styles.get('padding_left', pad)) // cell_w
        pad_right = int(styles.get('padding_right', pad)) // cell_w

        available_width = max(0, width - pad_left - pad_right)
        if available_width <= 0:
            # Too narrow for its own padding, but there is still a cell or
            # two of element to write in - a label is worth more than its
            # margins when space is this tight.
            pad_left = 0
            available_width = width
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
        row = y0 + max(0, (height - 1) // 2)
        start_col = x0 + pad_left

        for offset, char in enumerate(visible):
            self._set_cell(start_col + offset, row, char, text_color, None, scissor)

        if show_cursor:
            cursor_col = start_col + (cursor_index - view_offset)
            self._set_cell(cursor_col, row, "_", text_color, None, scissor)
