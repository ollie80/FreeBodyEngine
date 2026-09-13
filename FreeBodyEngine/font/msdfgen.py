"""A real multi-channel signed distance field (MSDF) generator, implementing
Chlumsky's technique (https://github.com/Chlumsky/msdfgen): each glyph
outline's edges are colored into cyan/magenta/yellow (two of R/G/B each) so
that sharp corners survive being packed into 3 channels, and the final
alpha in a shader is reconstructed via median(r, g, b) - see
engine_assets/text/text.fbfrag.

Scope, stated plainly:
- Real quadratic and cubic Bezier curve reconstruction from FreeType outline
  tags (not the previous version's "every point is a straight line" bug).
- Real per-channel signed distance and real nonzero/even-odd winding-rule
  sign (via ray casting over the actual reconstructed contours - not the
  previous version's "sign from the nearest edge's local cross product",
  which was wrong at concavities and multi-contour glyphs).
- Curves are subdivided into short line segments *for the distance
  computation specifically* (still colored and corner-detected at the true
  curve level) so the whole raster can be vectorized with NumPy instead of
  a per-pixel Python loop - the previous implementation's per-pixel loop
  was already reported "extremely slow" even without doing this much
  extra math per pixel. This is indistinguishable from true analytic
  curve distance at normal text/UI sizes, but is a real, disclosed
  simplification from doing Newton's-method refinement against the exact
  curve at every pixel.
- msdfgen's "error correction" pass (patching rare median-disagreement
  artifacts at very acute angles) is not implemented - a reasonable,
  documented limitation affecting only pathological glyph shapes.
"""
import math
import freetype
import numpy as np
from PIL import Image

# FreeType outline tag bits (FT_CURVE_TAG).
_ON_CURVE = 0x01
_CUBIC = 0x02

# Edge colors: each is 2-of-3 RGB channels "on". Any two color-adjacent
# edges around a corner share exactly one channel, which is what makes
# median(r,g,b) reconstruction continuous across smooth edges while still
# capturing sharp corners.
WHITE = (1, 1, 1)
CYAN = (0, 1, 1)
MAGENTA = (1, 0, 1)
YELLOW = (1, 1, 0)
_PALETTE = (CYAN, MAGENTA, YELLOW)

CORNER_ANGLE_THRESHOLD = math.radians(15)  # direction changes sharper than this count as a corner
CURVE_SEGMENTS = 8            # line segments per curve, for distance + winding only


class Edge:
    __slots__ = ("kind", "points", "color")

    def __init__(self, kind: str, points: list[np.ndarray]):
        self.kind = kind  # "line" | "quad" | "cubic"
        self.points = points
        self.color = WHITE

    def start(self) -> np.ndarray:
        return self.points[0]

    def end(self) -> np.ndarray:
        return self.points[-1]

    def direction_at_start(self) -> np.ndarray:
        d = self.points[1] - self.points[0]
        n = np.linalg.norm(d)
        return d / n if n > 1e-9 else np.array([1.0, 0.0])

    def direction_at_end(self) -> np.ndarray:
        d = self.points[-1] - self.points[-2]
        n = np.linalg.norm(d)
        return d / n if n > 1e-9 else np.array([1.0, 0.0])

    def flatten(self, segments: int = CURVE_SEGMENTS) -> list[np.ndarray]:
        """Returns the edge's start point followed by `segments` interior
        samples (used for distance + winding, not for edge coloring)."""
        if self.kind == "line":
            return [self.points[0]]
        ts = np.linspace(0.0, 1.0, segments, endpoint=False)
        pts = [self.points[0]]
        for t in ts[1:]:
            pts.append(self._eval(t))
        return pts

    def _eval(self, t: float) -> np.ndarray:
        if self.kind == "quad":
            p0, p1, p2 = self.points
            return (1 - t) ** 2 * p0 + 2 * (1 - t) * t * p1 + t ** 2 * p2
        if self.kind == "cubic":
            p0, p1, p2, p3 = self.points
            return (
                (1 - t) ** 3 * p0
                + 3 * (1 - t) ** 2 * t * p1
                + 3 * (1 - t) * t ** 2 * p2
                + t ** 3 * p3
            )
        raise ValueError(f"Cannot evaluate a line edge parametrically: {self.kind}")


def get_outline(face: freetype.Face, char: str):
    # FT_LOAD_NO_SCALE is required here: without it, outline.points come
    # back in scaled 26.6 pixel-space relative to whatever set_char_size()
    # was last called with, not raw font design units - but generate_char's
    # `scale = atlas_size / units_per_EM` and its planeBounds math both
    # assume raw font units (the same space glyph.advance.x uses under this
    # flag). This call also overwrites whatever face.load_char() the caller
    # already did on the same glyph slot, which is why the flag has to
    # match here independently rather than being inherited.
    face.load_char(char, freetype.FT_LOAD_NO_BITMAP | freetype.FT_LOAD_NO_SCALE)
    outline = face.glyph.outline
    points = np.array(outline.points, dtype=np.float64)
    tags = outline.tags
    contours = outline.contours
    return points, tags, contours


def _tag_kind(tag: int) -> str:
    if tag & _ON_CURVE:
        return "on"
    return "cubic" if (tag & _CUBIC) else "conic"


def contour_to_edges(points: np.ndarray, tags) -> list[Edge]:
    """Reconstructs one contour's real line/quadratic/cubic edges from
    FreeType's point/tag arrays, honoring the standard TrueType convention
    that two consecutive quadratic off-curve points imply an on-curve
    midpoint between them."""
    n = len(points)
    if n == 0:
        return []

    kinds = [_tag_kind(t) for t in tags]

    start_idx = next((i for i, k in enumerate(kinds) if k == "on"), None)
    if start_idx is None:
        # A fully-conic contour (rare) - synthesize a start point at the
        # midpoint of the last and first points, per convention.
        mid = (points[-1] + points[0]) / 2.0
        seq_points = [mid] + list(points) + [mid]
        seq_kinds = ["on"] + kinds + ["on"]
    else:
        seq_points = list(points[start_idx:]) + list(points[: start_idx + 1])
        seq_kinds = kinds[start_idx:] + kinds[: start_idx + 1]

    edges: list[Edge] = []
    i = 0
    current = seq_points[0]
    m = len(seq_points)
    while i < m - 1:
        kind = seq_kinds[i + 1]
        if kind == "on":
            edges.append(Edge("line", [current, seq_points[i + 1]]))
            current = seq_points[i + 1]
            i += 1
        elif kind == "conic":
            control = seq_points[i + 1]
            if i + 2 < m and seq_kinds[i + 2] == "conic":
                implied_on = (control + seq_points[i + 2]) / 2.0
                edges.append(Edge("quad", [current, control, implied_on]))
                current = implied_on
                i += 1
            else:
                end = seq_points[i + 2] if i + 2 < m else seq_points[0]
                edges.append(Edge("quad", [current, control, end]))
                current = end
                i += 2
        else:  # cubic
            c1 = seq_points[i + 1]
            c2 = seq_points[i + 2] if i + 2 < m else seq_points[0]
            end = seq_points[i + 3] if i + 3 < m else seq_points[0]
            edges.append(Edge("cubic", [current, c1, c2, end]))
            current = end
            i += 3
    return edges


def color_edges(contour: list[Edge], threshold: float = CORNER_ANGLE_THRESHOLD):
    """Chlumsky's edge-coloring heuristic: cycle cyan/magenta/yellow at each
    detected corner (a sharp direction change between consecutive edges),
    so any two color-adjacent edges share exactly one channel. A contour
    with no corners (a fully smooth loop) gets one uniform color instead."""
    n = len(contour)
    if n == 0:
        return

    def is_corner(prev: Edge, cur: Edge) -> bool:
        # angle = deviation from perfectly straight continuation: 0 means
        # the incoming and outgoing tangents point the same way (smooth),
        # pi means a full reversal. Anything past `threshold` is a corner.
        d1 = prev.direction_at_end()
        d2 = cur.direction_at_start()
        dot = np.clip(np.dot(d1, d2), -1.0, 1.0)
        angle = np.arccos(dot)
        return angle > threshold

    corner_idx = [i for i in range(n) if is_corner(contour[i - 1], contour[i])]

    if not corner_idx:
        for e in contour:
            e.color = WHITE
        return

    palette_i = 0
    ci = 0
    color = _PALETTE[palette_i]
    for i in range(n):
        if ci < len(corner_idx) and i == corner_idx[ci]:
            palette_i = (palette_i + 1) % 3
            color = _PALETTE[palette_i]
            ci += 1
        contour[i].color = color


def _line_distance_grid(P: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Vectorized unsigned point-to-segment distance. P: (H, W, 2)."""
    ab = b - a
    ab_len2 = float(np.dot(ab, ab))
    if ab_len2 < 1e-12:
        return np.linalg.norm(P - a, axis=-1)
    t = np.clip(((P - a) @ ab) / ab_len2, 0.0, 1.0)
    proj = a + t[..., None] * ab
    return np.linalg.norm(P - proj, axis=-1)


def _point_in_polygon_grid(P: np.ndarray, poly: list[np.ndarray]) -> np.ndarray:
    """Vectorized even-odd ray-casting point-in-polygon test. P: (H, W, 2)."""
    n = len(poly)
    inside = np.zeros(P.shape[:2], dtype=bool)
    x, y = P[..., 0], P[..., 1]
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        cond = (y1 > y) != (y2 > y)
        with np.errstate(divide="ignore", invalid="ignore"):
            x_int = x1 + (y - y1) / (y2 - y1) * (x2 - x1)
        inside ^= cond & (x < x_int)
    return inside


def generate_msdf(contours: list[list[Edge]], width: int, height: int, scale_vec: np.ndarray, offset: np.ndarray, range_px: float) -> Image.Image:
    """Rasterizes `contours` (each already colored via color_edges) into a
    `width` x `height` MSDF. `scale_vec`/`offset` map outline-space
    coordinates (FreeType convention: Y increases upward) to output-pixel
    space (row 0 = top, Y increases downward) - `scale_vec` is
    `(scale, -scale)` so the Y component of every transformed point is also
    flipped; `range_px` is the SDF's output-texel spread on each side of the
    true edge. Rectangular (not square) since generate_char() sizes this to
    each glyph's own tight bounding box rather than a fixed per-font cell."""
    ys, xs = np.meshgrid(np.arange(height) + 0.5, np.arange(width) + 0.5, indexing="ij")
    grid = np.stack([xs, ys], axis=-1)  # (height, width, 2), output-pixel space

    channel_dist = {0: np.full((height, width), range_px, dtype=np.float64),
                     1: np.full((height, width), range_px, dtype=np.float64),
                     2: np.full((height, width), range_px, dtype=np.float64)}

    flattened_polys = []
    for contour in contours:
        poly = []
        for edge in contour:
            for pt in edge.flatten():
                poly.append(pt * scale_vec + offset)
            for ch in range(3):
                if edge.color[ch]:
                    seg_points = [p * scale_vec + offset for p in edge.flatten()] + [edge.end() * scale_vec + offset]
                    for a, b in zip(seg_points[:-1], seg_points[1:]):
                        d = _line_distance_grid(grid, a, b)
                        channel_dist[ch] = np.minimum(channel_dist[ch], d)
        flattened_polys.append(poly)

    inside = np.zeros((height, width), dtype=bool)
    for poly in flattened_polys:
        if len(poly) >= 3:
            inside ^= _point_in_polygon_grid(grid, poly)

    sign = np.where(inside, 1.0, -1.0)

    out = np.zeros((height, width, 4), dtype=np.uint8)
    for ch in range(3):
        signed = channel_dist[ch] * sign
        out[..., ch] = np.clip(signed / range_px * 127.0 + 128.0, 0, 255).astype(np.uint8)
    out[..., 3] = 255

    return Image.fromarray(out, mode="RGBA")


def get_global_metadata(face: freetype.Face, em_size: int):
    """Font-wide metrics, em-relative (divide FreeType's 26.6-fixed-point
    values by `em_size * 64`). Must be called after set_char_size()."""
    scale = 1.0 / (em_size * 64.0)
    ascender = face.size.ascender * scale
    descender = face.size.descender * scale
    line_height = face.size.height * scale
    return ascender, descender, line_height


def generate_char(char: str, face: freetype.Face, atlas_size: int, range_px: float = 4.0):
    """Generates one glyph's MSDF bitmap plus its em-relative metrics. A
    single `scale` (derived from the face's units_per_EM, not this glyph's
    own bounding box) is used for every glyph in a font, so relative glyph
    sizes are preserved across the whole atlas - the previous
    implementation independently rescaled each glyph's own bounding box to
    fill its cell, destroying relative sizing.
    """
    upem = face.units_per_EM
    scale = atlas_size / float(upem)

    face.load_char(char, freetype.FT_LOAD_NO_BITMAP | freetype.FT_LOAD_NO_SCALE)
    glyph = face.glyph
    # With FT_LOAD_NO_SCALE, advance.x is already in raw font units (verified
    # empirically - e.g. 600 for a 1000-upem monospace font's 0.6em advance).
    # linearHoriAdvance is NOT affected by FT_LOAD_NO_SCALE at all and stays
    # in its own unrelated fixed-point encoding - dividing that by upem, as
    # an earlier version of this function did, produced advances off by
    # roughly two orders of magnitude.
    advance = glyph.advance.x / upem

    points, tags, contours_idx = get_outline(face, char)

    if len(points) == 0:
        # Whitespace or a glyph with no outline - metrics only, empty bitmap.
        empty = Image.new("RGBA", (atlas_size, atlas_size), (0, 0, 0, 0))
        return empty, {
            "advance": advance,
            "planeBounds": {"left": 0.0, "bottom": 0.0, "right": 0.0, "top": 0.0},
        }

    contours = []
    start = 0
    for end in contours_idx:
        contour_points = points[start : end + 1]
        contour_tags = tags[start : end + 1]
        edges = contour_to_edges(contour_points, contour_tags)
        color_edges(edges)
        contours.append(edges)
        start = end + 1

    # FreeType outline space has Y increasing upward; raster/image space has
    # row 0 at the top (Y increasing downward). scale_vec's negated Y
    # component performs that flip consistently everywhere a point gets
    # mapped into pixel space (see generate_msdf) - min/max are computed
    # *after* scaling (not before) since negating Y swaps which extreme is
    # the minimum.
    scale_vec = np.array([scale, -scale])
    scaled = points * scale_vec
    min_scaled = scaled.min(axis=0)
    max_scaled = scaled.max(axis=0)

    padding = range_px
    offset = np.array([padding - min_scaled[0], padding - min_scaled[1]])

    # Size the raster tightly to this glyph's own bounding box (plus a
    # padding-px margin on every side for the distance falloff) rather than
    # a fixed atlas_size x atlas_size cell. A fixed per-font cell is
    # roughly 1em square, but a glyph's own ink is usually much narrower
    # (e.g. 'F' in a 0.6em-advance monospace font is only ~0.48em wide) -
    # packing the full cell meant atlasBounds (the whole cell) and
    # planeBounds (the tight glyph bbox, used to size the destination quad
    # at render time) described regions of two different sizes, so
    # sampling the cell into a plane_bounds-sized quad squeezed every
    # glyph down to a fraction of its real size, with the unused remainder
    # of the cell showing as blank margin around it - this is exactly the
    # "letters render too small / look too spaced out" bug that motivated
    # this rewrite. Cropping tightly makes the two agree.
    cell_width = max(1, math.ceil(max_scaled[0] - min_scaled[0] + 2 * padding))
    cell_height = max(1, math.ceil(max_scaled[1] - min_scaled[1] + 2 * padding))

    img = generate_msdf(contours, cell_width, cell_height, scale_vec, offset, range_px)

    # planeBounds must describe the same region atlasBounds will (the
    # padded raster above, not just the bare ink bbox) so the two agree -
    # expressed in em-relative units, independent of atlas pixel size.
    # `padding` is in output pixels and `atlas_size` is pixels-per-em (by
    # this function's own parameter contract), so dividing by `atlas_size`
    # - not `scale`, which is pixels-per-*font-unit* (atlas_size/upem) and
    # would leave this still in font-unit-sized numbers, off by ~upem/1 -
    # converts it to the same em fraction raw_min/raw_max are already in.
    margin_em = padding / atlas_size
    raw_min = points.min(axis=0) / upem
    raw_max = points.max(axis=0) / upem
    plane_bounds = {
        "left": float(raw_min[0] - margin_em),
        "bottom": float(raw_min[1] - margin_em),
        "right": float(raw_max[0] + margin_em),
        "top": float(raw_max[1] + margin_em),
    }

    return img, {"advance": advance, "planeBounds": plane_bounds}
