"""Runtime representation of a loaded `.fbfont` (an MSDF atlas + its
per-glyph metrics/UVs) - see font/atlasgen.py for how these are generated
and core/files/loaders/font.py for how this gets constructed from a loaded
file. This replaces the previous version of this file, which targeted
pygame+moderngl (dead code, imported nowhere) and parsed a JSON schema the
engine's own generator never actually produced.
"""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from FreeBodyEngine.graphics.texture import Texture


class Glyph:
    """One character's metrics and atlas location within a Font."""
    __slots__ = ("advance", "plane_bounds", "uv_bounds")

    def __init__(self, advance: float, plane_bounds: tuple[float, float, float, float], uv_bounds: tuple[float, float, float, float]):
        """Stores this glyph's advance width plus its already-computed
        plane/UV bounds - see the attribute comments below for exactly what
        each represents."""
        self.advance = advance
        # (left, bottom, right, top), em-relative, standard Y-up convention -
        # where a glyph's quad should be positioned relative to the pen.
        self.plane_bounds = plane_bounds
        # (u0, v0, u1, v1) in the *actual uploaded texture's* UV space
        # (already accounts for _create_standalone_texture's 180-degree
        # flip - see core/files/loaders/font.py) - where to sample the atlas.
        self.uv_bounds = uv_bounds


class Font:
    """A ready-to-render MSDF font: an atlas Texture plus, per Unicode
    codepoint, the Glyph describing where in it and how to draw that
    character."""
    def __init__(self, texture: 'Texture', glyphs: dict[int, Glyph], distance_range: float,
                 atlas_em_size: float, ascender: float, descender: float, line_height: float):
        """Stores the given atlas/glyphs/metrics directly - see the
        attribute comments below for what each metric means."""
        self.texture = texture
        self.glyphs = glyphs
        # `distance_range` is in atlas texels, relative to `atlas_em_size`
        # (the pixels-per-em the atlas was generated at) - a renderer needs
        # both to compute the correct on-screen AA scale (px_range) at
        # whatever em-size text is actually drawn at, which is virtually
        # never the same size the atlas happened to be generated at.
        self.distance_range = distance_range
        self.atlas_em_size = atlas_em_size
        self.ascender = ascender
        self.descender = descender
        self.line_height = line_height

    def get_glyph(self, codepoint: int) -> Glyph | None:
        """Returns the Glyph for `codepoint` (a Unicode code point, e.g.
        `ord(ch)`), or None if this font has no glyph for it."""
        return self.glyphs.get(codepoint)
