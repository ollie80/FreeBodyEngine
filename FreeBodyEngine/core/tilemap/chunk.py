from FreeBodyEngine.math import Vector
import numpy as np
from typing import TYPE_CHECKING
from FreeBodyEngine.core.tilemap import _NUM_TILE_VALS
# Tile is imported for real, not just for type checking: get_tile()
# constructs one, and under TYPE_CHECKING alone that raised NameError.
from FreeBodyEngine.core.tilemap.tile import Tile
if TYPE_CHECKING:
    from FreeBodyEngine.core.tilemap import Tilemap

class Chunk:
    """A square block of `size` x `size` tiles within a `Tilemap` layer.

    Tile data is stored flat in `tiles`, a `numpy` array of `_NUM_TILE_VALS`
    values per tile (row-major, see `_tile_index`), rather than as a grid of
    `Tile` objects - `Tile` instances are only created on demand by
    `get_tile`.
    """

    def __init__(self, tilemap: 'Tilemap', position: Vector, size: int, data: np.ndarray):
        """Args:
            tilemap: The `Tilemap` this chunk belongs to.
            position: The chunk's position in chunk-grid coordinates (see
                `Tilemap.chunk_pos`), not world/tile coordinates.
            size: The chunk's width/height in tiles.
            data: Flat per-tile value array backing this chunk, `_NUM_TILE_VALS`
                values per tile.
        """
        self.tilemap = tilemap
        self.size = size
        self.position = position
        self._updated = False
        self.tiles: np.ndarray = data

    def _tile_index(self, position: Vector) -> int:
        return position.y * self.size + position.x

    def get_tile(self, position: Vector) -> 'Tile':
        """Builds a `Tile` view onto the tile at `position` (local to this chunk).

        `Tile` objects are not stored - this reads the raw values back out
        of `tiles` and wraps them fresh on every call.

        The owning chunk is passed to `Tile` so its property setters have
        something to write through to; omitting it used to raise TypeError
        on every single call, since `Tile.__init__` has always taken a
        `chunk` argument. Nothing in the engine called `get_tile`, which is
        why that went unnoticed.
        """
        array_offset = self._tile_index(position) * _NUM_TILE_VALS

        image_id = int(self.tiles[array_offset])
        spritesheet_index = int(self.tiles[array_offset + 1])
        return Tile(position, image_id, spritesheet_index, self)

    def get_tile_neighbors(self, position: Vector, layer: str):
        """This chunk-local tile's eight neighbours, reaching into adjoining
        chunks as needed.

        Resolved through the parent tilemap in tilemap coordinates rather
        than here: a neighbour across a chunk edge lives in a different chunk
        (or in none at all, where nothing has been created yet), and the
        tilemap is what knows how to find it. The previous implementation
        looped `range(-1, 1)` - which omits the +1 side entirely - and
        returned nothing at all.
        """
        size = self.size
        tilemap_position = Vector(self.position.x * size + position.x,
                                  self.position.y * size + position.y)
        return self.tilemap.get_tile_neighbors(tilemap_position, layer)

    def _write_tile(self, position: Vector, image_id: int, spritesheet_index: int):
        """Writes a tile's two raw stored bytes at `position` (local to this
        chunk), with no further bookkeeping beyond marking the chunk dirty.

        Separate from `set_tile` so `Tile`'s own property setters - and the
        auto-tiling resolve pass, which rewrites a neighbour's `image_id`
        without that counting as authoring a new tile - have a way to touch
        the data array that does not recurse back into tile-placement
        logic."""
        array_offset = self._tile_index(position) * _NUM_TILE_VALS

        self.tiles[array_offset] = image_id
        self.tiles[array_offset + 1] = spritesheet_index
        self._updated = True

    def set_tile(self, position: Vector, image_id: int, spritesheet_index: int):
        """Places a tile at `position` (local to this chunk), storing its
        image id and spritesheet index."""
        self._write_tile(position, image_id, spritesheet_index)

    def remove_tile(self, position: Vector):
        """Clears the tile at `position` (local to this chunk) back to empty."""
        self._write_tile(position, 0, 0)
