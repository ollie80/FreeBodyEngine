"""Tests for the tilemap's tile addressing, chunk mesh and auto-tiling rules.

These cover the parts that need no GL context: the rule compiler/evaluator,
the chunk mesh's cell UV maths, and tile addressing across chunk boundaries.
Everything here was either unreachable or wrong before (see git history
around the tilemap commits) - Chunk.get_tile raised on every call,
Tilemap.get_tile read the wrong slot, and nothing ever evaluated a rule.
"""
import numpy as np
import pytest

from FreeBodyEngine.core.tilemap import _NUM_TILE_VALS
from FreeBodyEngine.core.tilemap.rules import (
    TileRule, parse_rules, NEIGHBOUR_GRID_INDEX, _matches_glyph,
)
from FreeBodyEngine.core.tilemap.renderer import generate_chunk_mesh
from FreeBodyEngine.math import Vector


class FakeTile:
    """Stands in for a Tile for rule evaluation, which only ever reads
    `empty` and `spritesheet_index`."""

    def __init__(self, spritesheet_index=1, empty=False):
        self.spritesheet_index = spritesheet_index
        self.empty = empty


# -- rule compilation ------------------------------------------------------

def test_parse_rules_keeps_only_testable_cells():
    """`.` glyphs and the centre are dropped at compile time, so a rule that
    tests two neighbours costs two checks rather than nine."""
    rules = parse_rules({'rule': [{'match': ["...", ".#o", "..."], 'cell': [4, 0]}]})
    assert len(rules) == 1
    assert rules[0].tests == ((5, 'o'),)


def test_parse_rules_rejects_a_malformed_grid():
    assert parse_rules({'rule': [{'match': ["..", ".#", ".."], 'cell': 0}]}) == []
    assert parse_rules({'rule': [{'match': ["...", ".#."], 'cell': 0}]}) == []


def test_parse_rules_rejects_an_unknown_glyph():
    assert parse_rules({'rule': [{'match': ["...", ".#z", "..."], 'cell': 0}]}) == []


def test_parse_rules_requires_a_cell():
    assert parse_rules({'rule': [{'match': ["...", ".#.", "..."]}]}) == []


@pytest.mark.parametrize("cell, expected", [
    (3, [3]),                               # a flat index
    ([2, 1], [[2, 1]]),                     # a single [col, row] pair
    ([[0, 0], [1, 0]], [[0, 0], [1, 0]]),   # several cells, as pairs
    ([0, 1, 2], [0, 1, 2]),                 # several cells, as flat indices
])
def test_parse_rules_normalizes_cell_forms(cell, expected):
    """A `[col, row]` pair and a list of cells are both lists of ints, so the
    two have to be told apart by shape."""
    rules = parse_rules({'rule': [{'match': ["...", ".#.", "..."], 'cell': cell}]})
    assert list(rules[0].cells) == expected


# -- glyph semantics -------------------------------------------------------

def test_same_and_not_same_are_about_the_spritesheet():
    same = FakeTile(spritesheet_index=1)
    other = FakeTile(spritesheet_index=2)
    assert _matches_glyph('#', same, 1)
    assert not _matches_glyph('#', other, 1)
    assert _matches_glyph('o', other, 1)
    assert not _matches_glyph('o', same, 1)


def test_a_missing_chunk_counts_as_empty():
    """None means no chunk exists in that direction. An unloaded chunk and an
    empty tile have to look the same to a rule, or a tileset would need a
    separate case for the edge of what happens to be loaded."""
    for value in (None, FakeTile(empty=True)):
        assert _matches_glyph('e', value, 1)
        assert _matches_glyph('o', value, 1)
        assert not _matches_glyph('#', value, 1)
        assert not _matches_glyph('t', value, 1)


def test_any_tile_glyph_ignores_which_spritesheet():
    assert _matches_glyph('t', FakeTile(spritesheet_index=7), 1)
    assert not _matches_glyph('t', FakeTile(empty=True), 1)


def test_any_glyph_matches_everything():
    for value in (None, FakeTile(empty=True), FakeTile(spritesheet_index=3)):
        assert _matches_glyph('.', value, 1)


# -- rule matching ---------------------------------------------------------

def _grid(**neighbours):
    """A 3x3 grid with the tile at the centre, named neighbours filled in."""
    names = ('tl', 't', 'tr', 'r', 'br', 'b', 'bl', 'l')
    grid = [None] * 9
    grid[4] = FakeTile()
    for name, value in neighbours.items():
        grid[NEIGHBOUR_GRID_INDEX[names.index(name)]] = value
    return grid


def test_rule_matches_only_when_every_test_holds():
    rule = parse_rules({'rule': [{'match': [".#.", ".#.", "..."], 'cell': 0}]})[0]
    assert rule.matches(_grid(t=FakeTile()), 1)
    assert not rule.matches(_grid(), 1)
    assert not rule.matches(_grid(t=FakeTile(spritesheet_index=2)), 1)


def test_neighbour_order_is_clockwise_from_top_left():
    """`Tilemap.get_tile_neighbors` documents this order and AutoSpritesheet
    relies on it to place neighbours into the grid a rule is written as."""
    assert NEIGHBOUR_GRID_INDEX == (0, 1, 2, 5, 8, 7, 6, 3)
    # the 4th entry is the right-hand neighbour, i.e. grid index 5
    rule = parse_rules({'rule': [{'match': ["...", "..#", "..."], 'cell': 0}]})[0]
    assert rule.matches(_grid(r=FakeTile()), 1)
    assert not rule.matches(_grid(l=FakeTile()), 1)


# -- cell variation --------------------------------------------------------

def test_a_single_cell_is_position_independent():
    rule = TileRule([], [[1, 1]])
    assert rule.pick_cell(0, 0) == [1, 1]
    assert rule.pick_cell(37, -4) == [1, 1]


def test_cell_variation_is_stable_for_a_position():
    """Re-resolving a tile (because a neighbour changed) must not make it
    flicker to a different variant."""
    rule = TileRule([], [0, 1, 2])
    for x, y in ((0, 0), (5, 3), (-2, 9)):
        assert rule.pick_cell(x, y) == rule.pick_cell(x, y)


def test_cell_variation_differs_across_positions():
    """Two variants must not come out as stripes the way (x + y) % 2 would."""
    rule = TileRule([], [0, 1])
    picks = {(x, y): rule.pick_cell(x, y) for x in range(8) for y in range(8)}
    assert set(picks.values()) == {0, 1}
    # adjacent tiles differ at least sometimes, in both axes
    assert any(picks[(x, y)] != picks[(x + 1, y)] for x in range(7) for y in range(8))
    assert any(picks[(x, y)] != picks[(x, y + 1)] for x in range(8) for y in range(7))


# -- chunk mesh ------------------------------------------------------------

CHUNK = 4


def _chunk_data(tiles):
    """A chunk array with `tiles` as {(x, y): (cell, sheet_index)}."""
    data = np.zeros(CHUNK * CHUNK * _NUM_TILE_VALS, dtype=np.uint8)
    for (x, y), (cell, sheet) in tiles.items():
        base = (y * CHUNK + x) * _NUM_TILE_VALS
        data[base] = cell + 1
        data[base + 1] = sheet
    return data


def test_mesh_emits_only_the_requested_spritesheets_tiles():
    data = _chunk_data({(0, 0): (0, 1), (1, 0): (0, 2)})
    v1, _, i1 = generate_chunk_mesh(data, 1, CHUNK, 1, 2, 2)
    v2, _, i2 = generate_chunk_mesh(data, 1, CHUNK, 2, 2, 2)
    assert len(v1) == 4 and len(i1) == 6
    assert len(v2) == 4 and len(i2) == 6


def test_mesh_is_empty_for_a_spritesheet_with_no_tiles():
    data = _chunk_data({(0, 0): (0, 1)})
    v, uv, i = generate_chunk_mesh(data, 1, CHUNK, 3, 2, 2)
    assert len(v) == 0 and len(uv) == 0 and len(i) == 0


def test_empty_tiles_cost_nothing():
    v, _, i = generate_chunk_mesh(_chunk_data({}), 1, CHUNK, 1, 2, 2)
    assert len(v) == 0 and len(i) == 0


def test_tile_rows_run_downward():
    """Tilemap.tilemap_pos maps a world position to -floor(y/tile) - 1, so
    row 0 covers world y in [-tile, 0) and later rows sit below it. The mesh
    used to lay rows out bottom-up, the exact mirror of that."""
    data = _chunk_data({(0, 0): (0, 1), (0, 1): (0, 1)})
    v, _, _ = generate_chunk_mesh(data, 1, CHUNK, 1, 2, 2)
    row0, row1 = v[0:4], v[4:8]
    assert row0[:, 1].min() == -1 and row0[:, 1].max() == 0
    assert row1[:, 1].min() == -2 and row1[:, 1].max() == -1


def test_tile_columns_run_rightward():
    data = _chunk_data({(0, 0): (0, 1), (1, 0): (0, 1)})
    v, _, _ = generate_chunk_mesh(data, 1, CHUNK, 1, 2, 2)
    assert v[0:4][:, 0].min() == 0 and v[0:4][:, 0].max() == 1
    assert v[4:8][:, 0].min() == 1 and v[4:8][:, 0].max() == 2


def test_cell_uvs_match_slice_texture_cell():
    """A tile addresses a cell exactly like a .fbanim frame's pos = [col, row]
    does, so the rect baked into the mesh has to be the one
    slice_texture_cell would produce for that cell - mirrored the same way,
    because standalone textures are uploaded flipped."""
    cols = rows = 4
    for cell, (col, row) in ((0, (0, 0)), (5, (1, 1)), (11, (3, 2))):
        data = _chunk_data({(0, 0): (cell, 1)})
        _, uv, _ = generate_chunk_mesh(data, 1, CHUNK, 1, cols, rows)
        expected_u = (cols - col - 1) / cols
        expected_v = (rows - row - 1) / rows
        assert uv[:, 0].min() == pytest.approx(expected_u)
        assert uv[:, 0].max() == pytest.approx(expected_u + 1 / cols)
        assert uv[:, 1].min() == pytest.approx(expected_v)
        assert uv[:, 1].max() == pytest.approx(expected_v + 1 / rows)


def test_uv_runs_opposite_to_x_matching_generate_quad():
    """generate_quad's u runs 1 -> 0 left to right, to compensate for the
    180-degree rotation standalone textures are uploaded with. A tile's baked
    UVs follow the same convention or its art comes out mirrored relative to
    every sprite's."""
    data = _chunk_data({(0, 0): (0, 1)})
    v, uv, _ = generate_chunk_mesh(data, 1, CHUNK, 1, 2, 2)
    left = int(np.argmin(v[:, 0]))
    right = int(np.argmax(v[:, 0]))
    assert uv[left, 0] > uv[right, 0]
