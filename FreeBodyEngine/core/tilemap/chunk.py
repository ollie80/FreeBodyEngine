from FreeBodyEngine.math import Vector
import numpy as np
from typing import TYPE_CHECKING
from FreeBodyEngine.core.tilemap import _NUM_TILE_VALS
if TYPE_CHECKING:
    from FreeBodyEngine.core.tilemap import Tilemap
    from FreeBodyEngine.core.tilemap import Tile

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
        """
        array_offset = self._tile_index(position) * _NUM_TILE_VALS

        image_id = self.tiles[array_offset]
        spritesheet_index = self.tiles[array_offset + 1]
        return Tile(position, image_id, spritesheet_index)

    def _get_tile_neighbors(self, pos: tuple[int, int]):
        for y in range(-1, 1):
            for x in range(-1, 1):
                neighbor_pos = (pos[0] + x, pos[1] + y)

                if neighbor_pos[0] < 0:
                    chunk = self.tilemap.get_chunk()
                    
                    
                    
                    continue 
                
                if neighbor_pos[0] > self.size:
                    chunk = self.tilemap.get_chunk()
                    
                    
                    continue 
                

    def get_tile_neighbors(self, position: Vector):
        """Gets the tile's neighbors, reaching across chunk boundaries as needed."""
        return self._get_tile_neighbors((position.x, position.y))

    def set_tile(self, position: Vector, image_id: int, spritesheet_index: int):
        """Writes a tile's image id and spritesheet index at `position` (local to this chunk)."""
        array_offset = self._tile_index(position) * _NUM_TILE_VALS

        self.tiles[array_offset] = image_id
        self.tiles[array_offset + 1] = spritesheet_index

    def remove_tile(self, position: Vector):
        """Clears the tile at `position` (local to this chunk) back to empty."""
        array_offset = self._tile_index(position) * _NUM_TILE_VALS

        self.tiles[array_offset] = 0
        self.tiles[array_offset + 1] = 0
