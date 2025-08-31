from dataclasses import dataclass
from FreeBodyEngine.math import Vector
from FreeBodyEngine.core.node import Node2D
from FreeBodyEngine.core.tilemap.spritesheet import TilemapSpritesheet, StaticSpritesheet
from FreeBodyEngine.core.tilemap.renderer import TilemapRenderer
from FreeBodyEngine.core.tilemap.chunk import Chunk
from FreeBodyEngine.core.tilemap.tile import Tile
from FreeBodyEngine.core.tilemap import _NUM_TILE_VALS
from FreeBodyEngine import warning, error
from FreeBodyEngine.utils import fbnjit
import numpy as np
import math

@dataclass
class Layer:
    name: str
    chunks: dict[Vector, Chunk]
    visible: bool

@fbnjit("uint8[:](uint16, uint16)")
def generate_empty_chunk_data(chunk_size: int, num_tile_vals: int) -> np.ndarray:
    return np.zeros(chunk_size*chunk_size*num_tile_vals, dtype=np.uint8)

class Tilemap(Node2D):
    def __init__(self, position: Vector = Vector(), rotation: float = 0, scale: Vector = Vector(1, 1), chunk_size: int=16, tile_size: int=1):
        super().__init__(position, rotation, scale)
        self.layers: dict[str, Layer] = {}
        self.chunk_size = chunk_size
        self.tile_size = tile_size
        self._spritesheet_types: dict[str, type[TilemapSpritesheet]] = {'static': StaticSpritesheet}
        self.spritesheets: dict[str, TilemapSpritesheet] = {}

    def add_layer(self, name, chunks: dict[Vector, Chunk] = {}, visible = False):
        self.layers[name] = Layer(name, chunks, visible)

    def add_spritesheet_type(self, name: str, type: type['TilemapSpritesheet']):
        self.spritesheet_types[name] = type

    def get_tile_neighbors():
        pass

    def create_spritesheet(self, data):
        """Creates a spritesheet and adds it the tilemaps spritesheets."""
        spritesheet_type = data.get('type', 'static')
        spritesheet_name = data.get('name', None)
        
        if spritesheet_name == None:
            error('Cannot add spritesheet because no name was set.')
            return
        
        self.add_spritesheet(spritesheet_name, self._spritesheet_types[spritesheet_type](data))

    def add_spritesheet(self, name: str, spritesheet: 'TilemapSpritesheet'):
        if name in self._spritesheet_types:
            warning(f'Cant add spritesheet "{name}" because it already exsists.')
            return
        
        self.spritesheets[name] = spritesheet

    def create_renderer(self):
        self.add(TilemapRenderer(Vector(), 0, Vector(1, 1)))

    def set_tile(self, position: Vector, image_id: int, spritesheet: str, layer: str):
        chunk = self.get_chunk(self.chunk_pos(position), layer)
        tile_pos = self.tile_pos(position)

        chunk.set_tile(tile_pos, image_id, spritesheet)

    def get_tile(self, position: Vector, layer: str) -> Tile:
        chunk = self.get_chunk(self.chunk_pos(position), layer)
        return chunk.get_tile(position)

    def add_chunk(self, position: Vector, layer: str, data: np.ndarray=None) -> Chunk:
        self.layers[layer].chunks[position] = Chunk(self, position, self.chunk_size, generate_empty_chunk_data(self.chunk_size, _NUM_TILE_VALS) if not isinstance(data, np.ndarray) else data)

    def tilemap_pos(self, position: Vector) -> Vector:
        '''Converts a world position into a position in the tilemap.'''
        return Vector(math.floor(position.x / self.tile_size), -math.floor(position.y / self.tile_size)-1)

    def chunk_pos(self, position: Vector) -> Vector:
        '''Converts a tilemap position into a chunk position.'''
        return Vector(math.floor(position.x / self.chunk_size), math.floor(position.y / self.chunk_size))

    def tile_pos(self, position: Vector) -> Vector:
        '''Converts a tilemap position into the tile position in the chunk.'''
        return Vector(math.floor(position.x % self.chunk_size), math.floor(position.y % self.chunk_size))

    def get_chunk(self, position: Vector, layer: str) -> Chunk:
        if self.chunk_exists(position, layer):
            return self.layers[layer].chunks[position]
        else:
            error(f'No chunk at position "{position}".')

    def chunk_exists(self, position: Vector, layer: str) -> bool:
        return position in self.layers[layer].chunks.keys()

    def __str__(self):
        layers = {}
        for layer in self.layers:
            layers[self.layers[layer].name] = self.layers[layer].chunks
        
        return str(layers)
            
