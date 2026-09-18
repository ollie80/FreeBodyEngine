from FreeBodyEngine.core.service import Service
from FreeBodyEngine import register_service_update, unregister_service_update, get_service, warning, get_time
from FreeBodyEngine.core.update import UpdatePhase
from FreeBodyEngine.graphics.mesh import generate_quad
from FreeBodyEngine.math import Transform, Vector
from FreeBodyEngine.core.camera import Camera, CAMERA_PROJECTION
from FreeBodyEngine.graphics.color import Color
from FreeBodyEngine.core.files import load_file
from FreeBodyEngine.ui.element import ElementStates
import numpy as np

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from FreeBodyEngine.ui import UIManager
    from FreeBodyEngine.ui.element import UIElement
    from FreeBodyEngine.graphics.material import Material

class UIRenderer(Service):
    """Engine service that draws the UI tree owned by the `ui` service (`UIManager`)."""

    def __init__(self):
        """Loads the shared background quad mesh/material used to draw every element."""
        super().__init__('ui_renderer')
        self.dependencies.append('ui')

        self.quad = generate_quad()

        self.material: 'Material' = load_file('engine://ui/element.fbmat')

        # Keyed by the raw `image` style path - a background image (e.g. an
        # avatar) is loaded once and reused every frame/every element that
        # references the same path, the same way resolve_font() caches
        # fonts. Goes through load_file() so plain sprite .png assets that
        # already live in the shared sprite atlas are looked up there
        # instead of duplicated as a second standalone texture.
        self._image_cache: dict[str, any] = {}

        # The scissor rect (x, y, width, height) currently bound on the GPU,
        # or None for unclipped - tracked so _apply_scissor only issues a
        # real set_scissor/clear_scissor call when it's actually changing,
        # rather than once per element regardless of whether it moved.
        self._active_scissor = None

    def on_initialize(self):
        """Registers the draw callback and grabs a reference to the `ui` service's tree."""
        register_service_update(UpdatePhase.DRAW, self.draw)
        self.ui: 'UIManager' = get_service('ui')

    def on_destroy(self):
        """Unregisters the draw callback registered in `on_initialize`."""
        unregister_service_update(UpdatePhase.DRAW, self.draw)

    def draw(self):
        """Draws every top-level element of the UI tree (and, recursively, their children).

        Depth testing is explicitly turned off first, then back on after -
        nothing here ever did this before, so the UI silently inherited
        whatever depth-test state the 3D pipeline (PBRPipeline) happened to
        leave behind (on for its opaque/lighting passes - see
        graphics/pbr/pipeline.py - off only during its own composite step).
        Every UI element's background and text share the same mesh, drawn
        at the same implicit depth, in the same frame's depth buffer as
        whatever 3D content came before - with depth testing left on and
        GL's default depth func (GL_LESS), a background quad writes a
        depth value that its own text quad, drawn microseconds later at
        that identical depth, then fails to beat ("less than", not
        "less-or-equal") - so the text silently doesn't draw. Which
        specific elements this hits depends on incidental depth-buffer
        contents from whatever 3D drawing happened to precede them that
        frame, which is exactly the "some buttons show their label, some
        don't, no obvious pattern" bug this fixes. A 2D overlay drawn last
        in painter's-algorithm order (later siblings on top - see
        _draw_element's docs) was never supposed to depend on the depth
        buffer at all.
        """
        renderer = get_service('renderer')
        renderer.disable_depth_testing()

        for element in self.ui.root.children.values():
            self._draw_element(element, None)
        self._apply_scissor(None)

        renderer.enable_depth_testing()

    @staticmethod
    def _intersect_rect(a: tuple, b: tuple) -> tuple:
        """Intersection of two (x, y, width, height) rects, clamped to a
        non-negative width/height (an empty intersection, not a negative one)."""
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        x = max(ax, bx)
        y = max(ay, by)
        x2 = min(ax + aw, bx + bw)
        y2 = min(ay + ah, by + bh)
        return (x, y, max(0.0, x2 - x), max(0.0, y2 - y))

    def _apply_scissor(self, rect: tuple):
        """Binds `rect` as the active GPU scissor (or clears it for `None`),
        skipping the actual renderer call if it's already what's bound."""
        if rect == self._active_scissor:
            return

        self._active_scissor = rect
        renderer = get_service('renderer')

        if rect is None:
            renderer.clear_scissor()
        else:
            renderer.set_scissor(*rect)

    def _draw_element(self, element: 'UIElement', scissor: tuple):
        """Draws one element's background/text, then recurses into its own
        children - UIElement.calculate_layout() already computes correct
        layouts for arbitrarily nested trees (see ui/element.py), but until
        now this only ever drew direct children of the root, so nothing
        composed of nested elements (an avatar + bubble inside a message
        row, say) ever actually rendered past its top-level container.

        `scissor` is the (x, y, width, height) clip rect inherited from the
        nearest ancestor whose overflow isn't "visible" (see ui/element.py's
        OVERFLOW docs), or None if there isn't one. An element entirely outside it is skipped
        along with its whole subtree - nothing under a scrolled-out-of-view
        row can be visible either, so this also caps how much of an
        offscreen subtree gets a draw call, not just its own background/
        text. (Full virtualization - skipping *layout*, not just drawing,
        for offscreen rows - is a further improvement, not this one.)

        The "outside the scissor rect" test only applies when this element
        itself has a real (positive) width and height. A zero-size element
        is not the same thing as an off-screen one: a plain layout wrapper
        with no explicit height (see ui/element.py's "auto" size docs -
        before that existed, *every* such wrapper defaulted to height 0
        from DEFAULT_STYLES) reports zero size for itself while still
        having children with their own real, independent geometry
        (fixed-pixel row heights inside it, say). Treating "zero size" as
        "fully clipped, skip the whole subtree" - what this used to do -
        discarded every one of those children's draw calls along with it,
        silently: a search-results list, or any dynamically-populated
        container built the obvious way (an unsized wrapper around rows
        added later), rendered nothing at all despite every row existing
        in the tree with the right text and a valid size of its own."""
        layout = element._layout

        if scissor is not None and layout.width > 0 and layout.height > 0:
            sx, sy, sw, sh = scissor
            if (
                layout.x >= sx + sw or layout.x + layout.width <= sx or
                layout.y >= sy + sh or layout.y + layout.height <= sy
            ):
                return

        self._apply_scissor(scissor)

        styles = element.get_current_styles()

        self._draw_background(element, styles)
        self._draw_text(element, styles)

        child_scissor = scissor
        if element.get_overflow(styles) != "visible":
            own_rect = (layout.x, layout.y, layout.width, layout.height)
            child_scissor = (
                self._intersect_rect(scissor, own_rect) if scissor is not None else own_rect
            )

        for child in element.children.values():
            self._draw_element(child, child_scissor)

    @staticmethod
    def _to_vec4(value) -> tuple:
        """border_radius/border_width are single numbers in the common
        case (one radius/thickness for every corner/edge) but the shader
        takes a vec4 (per-corner radius in top_left/top_right/bottom_right/
        bottom_left order, matching CSS) so asymmetric shapes - like an
        Instagram-style bubble with one flattened corner on its "tail"
        side - are just a 4-tuple instead of a new style."""
        if isinstance(value, (tuple, list)):
            if len(value) == 4:
                return tuple(float(v) for v in value)
            warning(f'Expected 4 values for a per-corner/per-edge style, got {value!r}.')
            return (0.0, 0.0, 0.0, 0.0)
        return (float(value),) * 4

    def _resolve_image(self, path: str):
        cached = self._image_cache.get(path)
        if cached is not None:
            return cached

        texture = load_file(path)
        if texture is not None:
            self._image_cache[path] = texture
        return texture

    def _draw_background(self, element: 'UIElement', styles: dict):
        width, height = element._layout.width, element._layout.height
        if width <= 0 or height <= 0:
            return

        shader = self.material.shader
        shader.set_uniform('window_size', (self.ui.root.width, self.ui.root.height))
        shader.set_uniform('rect', (element._layout.x, element._layout.y, width, height))
        shader.set_uniform('size', (float(width), float(height)))
        shader.set_uniform('border_radius', self._to_vec4(styles.get('border_radius', 0)))
        shader.set_uniform('border_width', self._to_vec4(styles.get('border_width', 0)))
        shader.set_uniform('border_color', styles.get('border_color', (0.0, 0.0, 0.0, 1.0)))
        shader.set_uniform('base_color', styles.get('base_color', (1.0, 1.0, 1.0, 1.0)))

        image_path = styles.get('image')
        texture = self._resolve_image(image_path) if image_path else None
        shader.set_uniform('use_texture', texture is not None)
        if texture is not None:
            shader.set_uniform('background_texture', texture)

        get_service('renderer').draw_mesh(self.quad, self.material)

    def _draw_text(self, element: 'UIElement', styles: dict):
        text = styles.get('text') or ''
        font_path = styles.get('font')

        # A focused, editable field still needs its caret drawn even with
        # no text yet (an empty search box you've just clicked into is the
        # most common case) - so this can't bail out just because `text`
        # is empty the way it used to; only a missing font (nothing at all
        # could be drawn) or "neither text nor a cursor to draw" bails.
        show_cursor = styles.get('editable', False) and element.state == ElementStates.FOCUSED
        if font_path is None or (not text and not show_cursor):
            return

        # Masking happens here, drawing-only - get_current_styles()["text"]
        # (what the "submit" callback receives, what add_playlist_track()
        # etc. would actually send) still carries the real value; only the
        # glyphs drawn to screen are replaced.
        if styles.get('secret', False):
            text = '•' * len(text)

        from FreeBodyEngine.core.files.loaders.font import resolve_font  # lazy - avoids a ui <-> core.files import cycle (utils.py imports ui.element early during core.files' own init)
        font = resolve_font(font_path, weight=styles.get('font_weight', 'regular'))
        if font is None:
            return

        font_size = styles.get('font_size', 24)
        pad = styles.get('padding', 0)
        pad_left = styles.get('padding_left', pad)
        pad_right = styles.get('padding_right', pad)
        pad_top = styles.get('padding_top', pad)
        pad_bottom = styles.get('padding_bottom', pad)

        text_renderer = get_service('text_renderer')
        editable = styles.get('editable', False)

        # Elements have a fixed pixel width/height (or one resolved from a
        # percentage - see UIElement._parse_size), so text longer than
        # that would otherwise just overflow past the element's edge with
        # nothing to stop it (draw_text has no concept of a bound to stop
        # at). An editable field scrolls horizontally to keep the cursor
        # in view instead - the right call for something you're actively
        # typing into (eliding the *end* with "..." would hide what you
        # just typed the moment a search query got long); every other
        # element keeps eliding with an ellipsis, same as before.
        available_width = element._layout.width - pad_left - pad_right
        draw_x = element._layout.x + pad_left
        clip_rect = None

        # Clamped here (not just wherever it's mutated in manager.py) so a
        # cursor left past the end of shorter text - the field's own text
        # was set programmatically out from under it, say - never indexes
        # past the string it's about to be measured against below.
        element._cursor_index = max(0, min(element._cursor_index, len(text)))
        cursor_index = element._cursor_index

        if editable:
            full_width = text_renderer.measure_text(font, text, font_size)
            cursor_px = text_renderer.measure_text(font, text[:cursor_index], font_size)

            view_offset = element._text_view_offset
            if available_width > 0:
                if full_width <= available_width:
                    view_offset = 0.0
                else:
                    if cursor_px - view_offset < 0:
                        view_offset = cursor_px
                    elif cursor_px - view_offset > available_width:
                        view_offset = cursor_px - available_width
                    view_offset = max(0.0, min(view_offset, full_width - available_width))
            element._text_view_offset = view_offset

            draw_x -= view_offset
            if full_width > available_width:
                clip_rect = (element._layout.x + pad_left, element._layout.y, max(0, available_width), element._layout.height)
        elif available_width > 0 and text_renderer.measure_text(font, text, font_size) > available_width:
            ellipsis = '...'
            ellipsis_width = text_renderer.measure_text(font, ellipsis, font_size)
            truncated = text
            while truncated and text_renderer.measure_text(font, truncated, font_size) + ellipsis_width > available_width:
                truncated = truncated[:-1]
            text = (truncated + ellipsis) if truncated else ellipsis

        # Vertically centered in the padded content box using the font's
        # real ascender/descender (not just font_size) - previously this
        # always baseline-aligned to the top (padding_top + font_size),
        # which reads fine for a top-aligned multi-line block but left
        # every single-line label (virtually everything - every button,
        # every row) sitting near the top of its box with visibly more
        # empty space below than above, instead of actually centered.
        content_top = element._layout.y + pad_top
        content_height = max(0, element._layout.height - pad_top - pad_bottom)
        line_height = (font.ascender - font.descender) * font_size
        baseline_y = content_top + (content_height - line_height) / 2 + font.ascender * font_size

        text_color = styles.get('text_color', (1.0, 1.0, 1.0, 1.0))

        # A scrolled/overflowing editable field needs its own clip so the
        # part scrolled "off-screen" doesn't just draw past the field's
        # edge into whatever's next to it - nothing about a plain
        # UIElement clips its own text to its own bounds otherwise (see
        # _draw_element's docs on "overflow" - that's about clipping
        # *children*, not an element's own content). Scoped to just this
        # draw call and restored after, rather than left active, so it
        # doesn't clip whatever's drawn next.
        previous_scissor = self._active_scissor
        if clip_rect is not None:
            new_scissor = self._intersect_rect(previous_scissor, clip_rect) if previous_scissor is not None else clip_rect
            self._apply_scissor(new_scissor)

        if text:
            text_renderer.draw_text(font, text, draw_x, baseline_y, font_size, text_color)

        if show_cursor:
            # Blinks at 1Hz (on for the first half-second of each second,
            # off for the second) - a solid, unblinking caret reads as
            # part of the text ("Search|" looks like a typo), same reason
            # every OS text field blinks its own. Drawn as a plain "|"
            # glyph through the same text pipeline rather than a separate
            # quad, positioned from `cursor_index` (see ui/manager.py's
            # _on_key, which moves/inserts/deletes at it) rather than
            # always trailing the text - the cursor can now sit mid-string,
            # not just at the end.
            if int(get_time() * 2) % 2 == 0:
                cursor_x = draw_x + text_renderer.measure_text(font, text[:cursor_index], font_size)
                text_renderer.draw_text(font, '|', cursor_x, baseline_y, font_size, text_color)

        if clip_rect is not None:
            self._apply_scissor(previous_scissor)
