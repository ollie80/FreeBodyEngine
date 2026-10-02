"""Tilemap spritesheets: how a tile's stored `image_id` becomes an actual
image.

A tilemap spritesheet wraps an ordinary `.fbsheet` - the same grid-sliced
spritesheet format `.fbanim` frames already address with `pos = [col, row]`
(see `core/files/loaders/spritesheet.py`). Tiles are cells of that grid, so
a tileset is authored exactly like an animation sheet and carries the same
texture maps (`albedo`, `normal`, ...).

This replaced a parallel mechanism built on `TextureStack`, which uploaded
one GL array-texture layer per separate image file - that capped a tilemap
at `MAX_TEXTURE_STACK_SIZE` (64) distinct tiles and meant a grid sheet had
to be sliced into one file per tile on disk, duplicating what `.fbsheet`
already does with pure UV math.
"""

from FreeBodyEngine.utils import abstractmethod
from FreeBodyEngine.core.files import load_file, SPRITESHEET_FILE, TILESET_FILE
from FreeBodyEngine.core.tilemap.rules import parse_rules, NEIGHBOUR_GRID_INDEX
from FreeBodyEngine import warning

from typing import TYPE_CHECKING, Optional, Sequence, Union
if TYPE_CHECKING:
    from FreeBodyEngine.core.tilemap import Tilemap, Tile
    from FreeBodyEngine.graphics.spritesheet import Spritesheet

from enum import auto


class UpdateMode:
    """Determines when the 'get_image_index' function will be called. Frame means its called every frame. Chunk means its called on every chunk update. Once is only called once per tile. Never means it will never be called, and the image id will be used instead."""
    FRAME = auto()
    CHUNK = auto()
    ONCE = auto()
    NEVER = auto()


class TilemapSpritesheet:
    """Base class for a tilemap's image lookup: maps a tile's stored
    `image_id` (and, for auto-tiling, its neighbours) to a cell of this
    spritesheet's grid.

    Subclasses implement `get_image_index` for a particular lookup strategy
    (fixed, auto-tiled, animated). `update_mode` says how often the tilemap
    re-runs that lookup for a tile - see `UpdateMode`.
    """

    def __init__(self, data: dict[str, any], tilemap: 'Tilemap', update_mode: UpdateMode = UpdateMode.NEVER):
        """Args:
            data: The spritesheet definition. `name` identifies it within the
                tilemap, `sheet` is the path to its `.fbsheet`.
            tilemap: The tilemap this spritesheet belongs to.
            update_mode: How often `get_image_index` is re-run for a tile.
        """
        self.data = data
        self.tilemap = tilemap
        self.update_mode = update_mode

        self.name: str = data.get('name')
        if self.name is None:
            warning('Tilemap spritesheet has no "name".')

        sheet_path = data.get('sheet')
        self.sheet: Optional['Spritesheet'] = None
        if sheet_path is None:
            warning(f'Tilemap spritesheet "{self.name}" has no "sheet" path.')
        else:
            self.sheet = load_file(sheet_path, SPRITESHEET_FILE)
            if self.sheet is None:
                warning(f'Tilemap spritesheet "{self.name}" could not load sheet "{sheet_path}".')

    @property
    def size(self) -> tuple[int, int]:
        """This sheet's grid as `(cols, rows)`, or `(1, 1)` if it failed to load."""
        return self.sheet.size if self.sheet is not None else (1, 1)

    @property
    def cell_count(self) -> int:
        """How many cells this sheet's grid holds."""
        cols, rows = self.size
        return cols * rows

    def get_map(self, map_name: str):
        """This sheet's whole-image texture for `map_name` (e.g. `albedo`,
        `normal`), or None if the sheet declares no such map.

        The whole sheet is returned, not one cell: a tile's cell is selected
        by the UVs baked into the chunk mesh (see
        `renderer.generate_chunk_mesh`), so every tile drawn from this sheet
        shares one texture binding and therefore one draw call.
        """
        if self.sheet is None:
            return None
        return self.sheet.maps.get(map_name)

    def cell_index(self, cell: Union[int, Sequence[int]]) -> int:
        """Normalizes `cell` - either a flat cell index or a `[col, row]`
        pair, matching how `.fbanim` frames address the same sheets - into a
        flat index."""
        if isinstance(cell, (list, tuple)):
            cols, _ = self.size
            col, row = cell
            return int(row) * cols + int(col)
        return int(cell)

    @staticmethod
    def get_name():
        """The type name spritesheet data uses to select this class (see `Tilemap.add_spritesheet_type`)."""
        return "spritesheet"

    @abstractmethod
    def get_image_index(self, tile: 'Tile', neighbors: tuple['Tile', ...]) -> int:
        """
        Standardized function to get the image_index for any given tile. The frequency this is run is determined by this spritesheet's 'update_mode'.

        :param tile: The tile that the image index is being gotten for.
        :type tile: Tile

        :param neighbors: The 8 neighbors of the given tile, ordered in the clockwise direction starting in the top left. Includes neighbors in nearby chunks, and None where there is no tile.
        :type neighbors: tuple[Tile, ...]

        :rtype: int
        """
        pass

    def update(self):
        """
        Called when the tilemap node is updated.
        """
        pass


class StaticSpritesheet(TilemapSpritesheet):
    """A spritesheet where each tile's image is fixed by its stored
    `image_id` alone - no auto-tiling or animation, so the image never needs
    resolving at all (`UpdateMode.NEVER`)."""

    def __init__(self, data: dict[str, any], tilemap: 'Tilemap'):
        """Args:
            data: Spritesheet definition; `name` and `sheet` (its `.fbsheet` path).
            tilemap: The tilemap this spritesheet belongs to.
        """
        super().__init__(data, tilemap, UpdateMode.NEVER)

    @staticmethod
    def get_name():
        """The type name spritesheet data uses to select this class (see `Tilemap.add_spritesheet_type`)."""
        return "static_spritesheet"

    def get_image_index(self, tile, neighbors):
        """Returns `tile`'s stored image id unchanged; `neighbors` is unused."""
        return tile.image_id


class AutoSpritesheet(TilemapSpritesheet):
    """A spritesheet whose tiles pick their image from what surrounds them,
    by evaluating the project's own rules (see core/tilemap/rules.py).

    The engine defines no tiling scheme here - no built-in edge/corner
    handling, no fixed case count. The rules come from a `.fbtiles` file, so
    a project writes whatever tiling behaviour it wants.

    `UpdateMode.CHUNK`: a tile's image depends on its neighbours, so it is
    resolved when the tilemap is edited rather than every frame - placing or
    removing a tile re-resolves it and its eight neighbours, reaching into
    adjoining chunks where it sits on a chunk edge (see
    `Tilemap._resolve_around`).
    """

    def __init__(self, data: dict, tilemap: 'Tilemap'):
        """Args:
            data: Either `{'name': ..., 'tileset': 'path.fbtiles'}`, which
                takes the sheet, default cell and rules from that file, or an
                inline `{'name', 'sheet', 'rules', 'default'}`.
            tilemap: The tilemap this spritesheet belongs to.
        """
        tileset_path = data.get('tileset')
        if tileset_path is not None:
            tileset = load_file(tileset_path, TILESET_FILE)
            if not tileset:
                warning(f'Tilemap spritesheet "{data.get("name")}" could not load tileset "{tileset_path}".')
                tileset = {}
            # The file supplies sheet/default/rules; `data` still supplies the
            # name it is registered under, and wins on any key it sets itself.
            merged = dict(tileset)
            merged.update(data)
            data = merged

        super().__init__(data, tilemap, UpdateMode.CHUNK)

        self.rules = parse_rules(data, where=f'tileset "{self.name}"')
        if not self.rules:
            warning(f'Auto spritesheet "{self.name}" has no usable rules; every tile will use its default cell.')

        self.default_cell = data.get('default', 0)

    @staticmethod
    def get_name():
        """The type name spritesheet data uses to select this class (see `Tilemap.add_spritesheet_type`)."""
        return "auto_spritesheet"

    def get_image_index(self, tile: 'Tile', neighbors) -> int:
        """The cell index for `tile`, from the first of this tileset's rules
        whose pattern its neighbours satisfy, falling back to `default`.

        `neighbors` is the eight surrounding tiles clockwise from the
        top-left, as `Tilemap.get_tile_neighbors` returns them; None entries
        (no chunk in that direction) count as empty.
        """
        grid = [None] * 9
        for i, neighbor in enumerate(neighbors):
            grid[NEIGHBOUR_GRID_INDEX[i]] = neighbor
        grid[4] = tile

        position = tile.tilemap_position
        sheet_index = tile.spritesheet_index

        for rule in self.rules:
            if rule.matches(grid, sheet_index):
                return self.cell_index(rule.pick_cell(position.x, position.y))

        return self.cell_index(self.default_cell)
