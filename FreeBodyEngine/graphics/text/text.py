"""Draws text through the live FBUSL/GL33 pipeline using a real MSDF atlas
(graphics/text/font.py + font/atlasgen.py) - replaces the previous version
of this file, which targeted pygame+moderngl (dead code, imported nowhere)
and was never reachable.

Batches every *queued* string sharing the same font atlas texture into one
draw call (see queue_text()/flush() below) - this used to batch a whole
string into one draw call but still issue that draw immediately, one call
per string (see git history for that version's own docstring, which in
turn replaced an even older one-draw-call-per-glyph version). Real
profiling of phonon (a track-list-heavy screen, ~100 rows each with 2
labels and 2-3 buttons, all of them text) showed UIRenderer.draw() costing
~14ms CPU / ~12ms GPU with *that* per-string version - not fill-rate, but
the sheer number of draw_text() calls (400-500 on a busy screen), each
paying its own Python glyph-shaping loop plus two full GPU buffer
re-uploads (glBufferData) and a separate draw call.

Callers now call queue_text() (same signature as the old draw_text())
instead of getting an immediate draw - it appends this string's glyph
quads to a per-atlas-texture pending list instead of drawing them, and
UIRenderer.draw() calls flush() at the same points it already flushes its
own batched background instances (see ui/renderer.py's _flush_text and its
callers) - end of frame, scissor changes, and whenever backgrounds and
text need to interleave to preserve paint order. flush() then issues one
draw call per distinct atlas texture that was actually used this frame,
however many queue_text() calls contributed glyphs to it.
"""
from FreeBodyEngine.core.service import Service
from FreeBodyEngine import register_service_update, unregister_service_update, get_service, warning
from FreeBodyEngine.core.update import UpdatePhase
from FreeBodyEngine.graphics.mesh import AttributeType, BufferUsage, IndexType
import numpy as np

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from FreeBodyEngine.graphics.material import Material
    from FreeBodyEngine.graphics.text.font import Font

# Starting capacity (in glyphs) for the shared batch mesh - grown
# geometrically (see _ensure_capacity) whenever a single flush() needs to
# draw more glyphs, for one atlas texture, than currently fit. Not a hard
# cap the way the old per-string _MAX_GLYPHS_PER_DRAW was: a flush can now
# legitimately hold every on-screen string sharing one font, which for a
# busy list screen is easily thousands of glyphs, not one string's worth.
_INITIAL_GLYPH_CAPACITY = 1024


class TextRenderer(Service):
    """The "text_renderer" service - draws MSDF text with the engine's
    built-in text material, batching every string queued since the last
    flush() - across as many queue_text() calls as share a font atlas -
    into a single draw call (see the module docstring)."""
    def __init__(self):
        """Doesn't build the batch mesh or load the text material yet
        (see on_initialize()), since both need the "renderer"/"files"
        services to already be up."""
        super().__init__('text_renderer')
        self.material: 'Material' = None
        self._batch_mesh = None
        # The full, pre-built index pattern for however many glyphs
        # _glyph_capacity currently supports ([0,1,2,2,1,3, 4,5,6,6,5,7,
        # ...]) - flush() never uploads a new index buffer for a batch that
        # fits, just slices this (a plain Python/numpy slice, no GPU call
        # at all) to however many glyphs that batch actually needs.
        self._max_indices: np.ndarray = None
        self._glyph_capacity = 0

        # Keyed by font atlas texture (the one thing that can't vary
        # within a single draw call - see queue_text()) - each value is a
        # dict of plain Python lists (vertices/uvs/colors/px_ranges),
        # appended to by every queue_text() call sharing that atlas since
        # the last flush(), and a running glyph_count used to size the
        # arrays flush() builds from them.
        self._pending: dict = {}

    def on_initialize(self):
        """Loads the engine's built-in `text.fbmat` text material and
        builds the persistent, reusable glyph-batch mesh."""
        from FreeBodyEngine.core.files import load_file
        self.material = load_file('engine://text/text.fbmat')
        self._ensure_capacity(_INITIAL_GLYPH_CAPACITY)

    def _ensure_capacity(self, glyph_count: int):
        """(Re)builds the shared batch mesh so it can hold at least
        `glyph_count` glyphs, growing geometrically (like a Python list)
        rather than to the exact requested size, so a busy frame doesn't
        force a rebuild on every single flush() once it settles near its
        steady-state glyph count."""
        if glyph_count <= self._glyph_capacity:
            return

        capacity = max(glyph_count, self._glyph_capacity * 2, _INITIAL_GLYPH_CAPACITY)
        max_verts = capacity * 4
        vertices = np.zeros(max_verts * 3, dtype=np.float32)
        uvs = np.zeros(max_verts * 2, dtype=np.float32)
        normals = np.zeros(max_verts * 3, dtype=np.float32)
        colors = np.zeros(max_verts * 4, dtype=np.float32)
        px_ranges = np.zeros(max_verts, dtype=np.float32)

        indices = np.zeros(capacity * 6, dtype=np.uint32)
        base = np.arange(capacity, dtype=np.uint32) * 4
        # Two triangles per quad: (0,1,2) and (2,1,3), matching the old
        # per-glyph unit quad's own winding (generate_quad()'s indices)
        # exactly, just repeated at every glyph's own vertex offset.
        indices[0::6] = base
        indices[1::6] = base + 1
        indices[2::6] = base + 2
        indices[3::6] = base + 2
        indices[4::6] = base + 1
        indices[5::6] = base + 3
        self._max_indices = indices
        self._glyph_capacity = capacity

        mesh_cls = get_service("renderer").get_mesh_class()
        self._batch_mesh = mesh_cls(
            {
                "verticies": (AttributeType.VEC3, vertices),
                "uvs": (AttributeType.VEC2, uvs),
                "normals": (AttributeType.VEC3, normals),
                "colors": (AttributeType.VEC4, colors),
                "px_ranges": (AttributeType.FLOAT, px_ranges),
            },
            indices=indices,
            index_type=IndexType.UINT32,
            usage=BufferUsage.DYNAMIC,
        )

    def measure_text(self, font: 'Font', text: str, px_size: float) -> float:
        """Total advance width of `text` at `px_size`, in screen pixels."""
        width = 0.0
        for ch in text:
            glyph = font.get_glyph(ord(ch))
            if glyph is not None:
                width += glyph.advance * px_size
        return width

    def queue_text(self, font: 'Font', text: str, x: float, y: float, px_size: float,
                    color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)):
        """Queues `text` (baseline start at screen pixel (x, y), same
        top-left-origin Y-down convention this always used) to be drawn on
        the next flush() - grouped with every other pending string that
        shares this font's atlas texture, regardless of its own size or
        color (both travel per-vertex now - see text.fbvert), so unrelated
        labels/buttons batch into one draw call together as long as
        nothing in between forced a flush (see ui/renderer.py's
        _queue_bg/_queue_text discipline for what does)."""
        font_px_range = font.distance_range * (px_size / font.atlas_em_size)

        pen_x = x
        batch = self._pending.setdefault(font.texture, {
            "vertices": [], "uvs": [], "colors": [], "px_ranges": [], "glyph_count": 0,
        })

        window = get_service('window')
        win_w, win_h = window.framebuffer_size
        if win_w <= 0 or win_h <= 0:
            return

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

                x0 = rect_x / win_w * 2.0 - 1.0
                x1 = (rect_x + rect_w) / win_w * 2.0 - 1.0
                top_y = 1.0 - rect_y / win_h * 2.0
                bottom_y = 1.0 - (rect_y + rect_h) / win_h * 2.0

                # Vertex order matches the old shader's VERTEX_INDEX 0..3
                # (top-left, top-right, bottom-left, bottom-right) - not
                # load-bearing on its own (only the index buffer's winding
                # actually matters for facing/culling), but keeping it
                # means _ensure_capacity()'s index pattern is a direct,
                # obviously-correct carryover of generate_quad()'s own.
                batch["vertices"].extend((x0, top_y, 0.0, x1, top_y, 0.0, x0, bottom_y, 0.0, x1, bottom_y, 0.0))
                batch["uvs"].extend((u0, v0, u1, v0, u0, v1, u1, v1))
                batch["colors"].extend(color * 4)
                batch["px_ranges"].extend((font_px_range,) * 4)
                batch["glyph_count"] += 1

            pen_x += glyph.advance * px_size

    def flush(self):
        """Draws every string queued since the last flush() - one draw
        call per distinct atlas texture, however many queue_text() calls
        contributed glyphs to it - and clears the queue. A no-op when
        nothing's pending, called defensively from several places (see
        ui/renderer.py) that don't know or care whether anything actually
        is."""
        if not self._pending:
            return

        renderer = get_service('renderer')
        total_glyphs = max(batch["glyph_count"] for batch in self._pending.values())
        self._ensure_capacity(total_glyphs)

        for texture, batch in self._pending.items():
            glyph_count = batch["glyph_count"]
            if glyph_count == 0:
                continue

            self._batch_mesh.set_data("verticies", np.array(batch["vertices"], dtype=np.float32))
            self._batch_mesh.set_data("uvs", np.array(batch["uvs"], dtype=np.float32))
            self._batch_mesh.set_data("colors", np.array(batch["colors"], dtype=np.float32))
            self._batch_mesh.set_data("px_ranges", np.array(batch["px_ranges"], dtype=np.float32))
            self._batch_mesh.indices = self._max_indices[:glyph_count * 6]

            self.material.shader.set_uniform('atlas', texture)
            renderer.draw_mesh(self._batch_mesh, self.material)

        self._pending.clear()
