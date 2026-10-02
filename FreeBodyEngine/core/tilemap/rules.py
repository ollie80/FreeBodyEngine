"""Auto-tiling rules: how a tile picks its image from what surrounds it.

The engine ships no tiling scheme of its own - no built-in notion of
"edges", "corners", 4-neighbour vs 8-neighbour, or a fixed 16- or 47-case
blob. A project declares its own rules as data, and this module only
evaluates them. That means the same machinery expresses a classic 16-case
edge set, a full 47-case blob, or something neither of those describes,
with no engine change.

A rule is a 3x3 pattern over the tile and its eight neighbours, written as
three strings so the shape it matches is visible in the file::

    sheet = "map/walls.fbsheet"
    default = [1, 1]

    [[rule]]
    match = ["...",
             ".#o",
             "..."]
    cell = [4, 0]

    [[rule]]
    match = [".#.",
             "###",
             ".#."]
    cell = [[1, 1], [2, 1]]   # picked per tile position, for variation

Rules are tried in order and the first match wins, falling back to
`default`. The centre character is the tile being resolved and is never
tested - it is there so the grid reads as a shape.

Glyphs:

===== ==========================================================
``.``  any - this neighbour is not tested
``#``  the same spritesheet as the tile being resolved
``o``  *not* the same spritesheet, which includes an empty slot
``e``  empty - no tile at all
``t``  any tile - a tile of any spritesheet, but not empty
===== ==========================================================
"""

from FreeBodyEngine import warning

from typing import TYPE_CHECKING, Optional, Sequence, Union
if TYPE_CHECKING:
    from FreeBodyEngine.core.tilemap import Tile

ANY = '.'
SAME = '#'
NOT_SAME = 'o'
EMPTY = 'e'
ANY_TILE = 't'

GLYPHS = (ANY, SAME, NOT_SAME, EMPTY, ANY_TILE)

# The centre of the 3x3 grid is the tile itself, never a neighbour.
_CENTRE = 4

# Neighbours as `Tilemap.get_tile_neighbors` orders them (clockwise from the
# top-left), mapped to their index in the 3x3 grid a rule is written as.
NEIGHBOUR_GRID_INDEX = (0, 1, 2, 5, 8, 7, 6, 3)


def _matches_glyph(glyph: str, neighbor: Optional['Tile'], spritesheet_index: int) -> bool:
    """Whether one neighbour satisfies one glyph. `neighbor` is None where
    the tilemap has no chunk at all in that direction, which counts as
    empty - an unloaded chunk and an empty tile look the same to a rule."""
    empty = neighbor is None or neighbor.empty

    if glyph == ANY:
        return True
    if glyph == EMPTY:
        return empty
    if glyph == ANY_TILE:
        return not empty
    if glyph == SAME:
        return (not empty) and neighbor.spritesheet_index == spritesheet_index
    if glyph == NOT_SAME:
        return empty or neighbor.spritesheet_index != spritesheet_index
    return True


class TileRule:
    """One compiled auto-tiling rule: the neighbour tests it requires, and
    the cell (or cells) it selects when they all hold."""

    __slots__ = ('tests', 'cells')

    def __init__(self, tests: Sequence[tuple[int, str]], cells: Sequence[Union[int, Sequence[int]]]):
        """Args:
            tests: `(grid index, glyph)` pairs to check. Only the entries
                that can actually fail are kept - `.` glyphs and the centre
                are dropped at compile time, so a rule that tests two
                neighbours costs two checks rather than nine.
            cells: The cell this rule selects, as a one-element sequence; or
                several, to be chosen between per tile position.
        """
        self.tests = tuple(tests)
        self.cells = tuple(cells)

    def matches(self, grid: Sequence[Optional['Tile']], spritesheet_index: int) -> bool:
        """Whether every one of this rule's neighbour tests holds for `grid`
        (a 9-element 3x3, row-major, with the tile itself at the centre)."""
        for index, glyph in self.tests:
            if not _matches_glyph(glyph, grid[index], spritesheet_index):
                return False
        return True

    def pick_cell(self, x: int, y: int) -> Union[int, Sequence[int]]:
        """The cell this rule selects at tilemap position `(x, y)`.

        With several cells listed, one is chosen by hashing the position, so
        a variant is stable for a given tile - re-resolving it (because a
        neighbour changed, say) must not make it flicker to a different
        variant - while neighbouring tiles still differ.
        """
        if len(self.cells) == 1:
            return self.cells[0]
        # Two large odd multipliers, xor-mixed: enough to decorrelate
        # adjacent x and y so a 2-variant set does not come out as stripes
        # the way (x + y) % 2 would.
        h = (int(x) * 73856093) ^ (int(y) * 19349663)
        return self.cells[h % len(self.cells)]

    def __repr__(self):
        return f"TileRule(tests={self.tests}, cells={self.cells})"


def _compile_match(match: Sequence[str], where: str) -> Optional[list[tuple[int, str]]]:
    """Compiles a rule's 3x3 `match` grid into the list of neighbour tests it
    implies, or None if the grid is malformed."""
    rows = list(match)
    if len(rows) != 3 or any(len(row) != 3 for row in rows):
        warning(f'{where}: a rule\'s "match" must be 3 rows of 3 characters, got {rows!r}.')
        return None

    tests = []
    for row_index, row in enumerate(rows):
        for col_index, glyph in enumerate(row):
            index = row_index * 3 + col_index
            if index == _CENTRE:
                continue
            if glyph not in GLYPHS:
                warning(f'{where}: unknown match glyph {glyph!r}; expected one of {"".join(GLYPHS)}.')
                return None
            if glyph == ANY:
                continue
            tests.append((index, glyph))
    return tests


def _normalize_cells(cell, where: str) -> Optional[list]:
    """Normalizes a rule's `cell` - a flat index, a `[col, row]` pair, or a
    list of either - into a list of cells."""
    if cell is None:
        warning(f'{where}: a rule has no "cell".')
        return None

    if isinstance(cell, int):
        return [cell]

    if isinstance(cell, (list, tuple)):
        if len(cell) == 0:
            warning(f'{where}: a rule\'s "cell" is empty.')
            return None
        # `[col, row]`, versus a list of cells: a pair of plain ints is one
        # cell, anything holding a list/tuple is a list of them.
        if all(isinstance(entry, int) for entry in cell):
            if len(cell) == 2:
                return [list(cell)]
            return [entry for entry in cell]
        return [list(entry) if isinstance(entry, (list, tuple)) else entry for entry in cell]

    warning(f'{where}: a rule\'s "cell" must be an int, a [col, row] pair, or a list of those; got {cell!r}.')
    return None


def parse_rules(data: dict, where: str = 'tileset') -> list[TileRule]:
    """Compiles the `[[rule]]` entries of a tileset definition into
    `TileRule`s, skipping (with a warning) any that are malformed."""
    rules = []
    raw_rules = data.get('rule') or data.get('rules') or []

    for raw in raw_rules:
        if not isinstance(raw, dict):
            warning(f'{where}: a rule is not a table.')
            continue

        tests = _compile_match(raw.get('match', []), where)
        if tests is None:
            continue

        cells = _normalize_cells(raw.get('cell'), where)
        if cells is None:
            continue

        rules.append(TileRule(tests, cells))

    return rules
