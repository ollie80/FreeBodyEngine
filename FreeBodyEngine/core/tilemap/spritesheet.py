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
from FreeBodyEngine.core.files import load_file, SPRITESHEET_FILE
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
