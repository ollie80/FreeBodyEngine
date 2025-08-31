from FreeBodyEngine.math import Vector
import numpy as np
from typing import TYPE_CHECKING
from FreeBodyEngine.core.tilemap import _NUM_TILE_VALS
if TYPE_CHECKING:
    from FreeBodyEngine.core.tilemap import Tilemap
    from FreeBodyEngine.core.tilemap import Tile

class Chunk:
    def __init__(self, tilemap: 'Tilemap', position: Vector, size: int, data: np.ndarray):
        self.tilemap = tilemap
        self.size = size
        self.position = position
        self._updated = False
        self.tiles: np.ndarray = data

    def _tile_index(self, position: Vector) -> int:
        return position.y * self.size + position.x

    def get_tile(self, position: Vector) -> 'Tile':
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
        return self._get_tile_neighbors((position.x, position.y))

    def set_tile(self, position: Vector, image_id: int, spritesheet_index: int):
        array_offset = self._tile_index(position) * _NUM_TILE_VALS
        
        self.tiles[array_offset] = image_id
        self.tiles[array_offset + 1] = spritesheet_index

    def remove_tile(self, position: Vector):
        array_offset = self._tile_index(position) * _NUM_TILE_VALS
        
        self.tiles[array_offset] = 0
        self.tiles[array_offset + 1] = 0
