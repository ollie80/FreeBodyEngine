"""Draws text through the live FBUSL/GL33 pipeline using a real MSDF atlas
(graphics/text/font.py + font/atlasgen.py) - replaces the previous version
of this file, which targeted pygame+moderngl (dead code, imported nowhere)
and was never reachable.

Rendering follows the same pattern the engine already uses for UI elements
(ui/renderer.py's UIRenderer): one reusable quad mesh, redrawn once per
glyph with per-draw uniforms (`rect` for screen position, `uv_rect` for the
atlas region, matching engine_assets/text/text.fbvert/.fbfrag). That's one
draw call per character rather than one batched draw call per string - a
real, documented limitation worth revisiting if text-heavy scenes need it,
not a byproduct of anything technically required by MSDF rendering itself.
"""
from FreeBodyEngine.core.service import Service
from FreeBodyEngine import register_service_update, unregister_service_update, get_service
from FreeBodyEngine.core.update import UpdatePhase
from FreeBodyEngine.graphics.mesh import generate_quad

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from FreeBodyEngine.graphics.material import Material
    from FreeBodyEngine.graphics.text.font import Font


class TextRenderer(Service):
    """The "text_renderer" service - draws MSDF text with the engine's
    built-in text material, one draw call per glyph (see the module
    docstring)."""
    def __init__(self):
        """Builds the reusable quad mesh every glyph is drawn with; doesn't
        load the text material yet (see on_initialize()), since that needs
        the "files" service to already be up."""
        super().__init__('text_renderer')
        self.quad = generate_quad()
        self.material: 'Material' = None

    def on_initialize(self):
        """Loads the engine's built-in `text.fbmat` text material."""
        from FreeBodyEngine.core.files import load_file
        self.material = load_file('engine://text/text.fbmat')

    def measure_text(self, font: 'Font', text: str, px_size: float) -> float:
        """Total advance width of `text` at `px_size`, in screen pixels."""
        width = 0.0
        for ch in text:
            glyph = font.get_glyph(ord(ch))
            if glyph is not None:
                width += glyph.advance * px_size
        return width

    def draw_text(self, font: 'Font', text: str, x: float, y: float, px_size: float,
                   color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)):
        """Draws `text` with its baseline start at screen pixel (x, y) - the
        same top-left-origin, Y-down pixel convention ui/renderer.py's
        `rect` uniform already uses - at `px_size` pixels per em."""
        renderer = get_service('renderer')
        window = get_service('window')

        px_range = font.distance_range * (px_size / font.atlas_em_size)

        # framebuffer_size (physical pixels), not size (logical/window-
        # manager pixels) - ui/renderer.py's UIRenderer sizes its own
        # `window_size` uniform from UIManager's root, which is itself
        # sized from framebuffer_size (see ui/manager.py). Using the
        # logical size here instead meant text and the UI backgrounds it's
        # supposed to sit on were positioned in two different coordinate
        # spaces whenever they differ (any HiDPI/fractionally-scaled
        # display) - text would land at the wrong screen position
        # entirely, reading as "text behind the bubbles" once a bubble
        # happened to be drawn at the position the text should have had.
        self.material.shader.set_uniform('window_size', window.framebuffer_size)
        self.material.shader.set_uniform('atlas', font.texture)
        self.material.shader.set_uniform('text_color', color)
        self.material.shader.set_uniform('px_range', px_range)

        pen_x = x
        for ch in text:
            glyph = font.get_glyph(ord(ch))
            if glyph is None:
                continue

            left, bottom, right, top = glyph.plane_bounds
            if right > left and top > bottom:
                rect_x = pen_x + left * px_size
                rect_y = y - top * px_size
                rect_w = (right - left) * px_size
                rect_h = (top - bottom) * px_size

                u0, v0, u1, v1 = glyph.uv_bounds

                self.material.shader.set_uniform('rect', (rect_x, rect_y, rect_w, rect_h))
                self.material.shader.set_uniform('uv_rect', (u0, v0, u1 - u0, v1 - v0))
                renderer.draw_mesh(self.quad, self.material)

            pen_x += glyph.advance * px_size
