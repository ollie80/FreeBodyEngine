from FreeBodyEngine.core.tilemap.spritesheet import TilemapSpritesheet, StaticSpritesheet
from FreeBodyEngine.core.tilemap.renderer import TilemapRenderer
from FreeBodyEngine.core.tilemap import _NUM_TILE_VALS
from FreeBodyEngine.core.tilemap.chunk import Chunk
from FreeBodyEngine.core.tilemap.tile import Tile
from FreeBodyEngine.core.node import Node2D
from FreeBodyEngine import warning, error
from FreeBodyEngine.utils import fbnjit
from FreeBodyEngine.math import Vector

import math
import numpy as np
from dataclasses import dataclass

@dataclass
class Layer:
    """One named, independently-visible layer of a `Tilemap`, holding its own
    set of `Chunk`s keyed by chunk position."""
    name: str
    chunks: dict[Vector, Chunk]
    visible: bool

@fbnjit("uint8[:](uint16, uint16)")
def generate_empty_chunk_data(chunk_size: int, num_tile_vals: int) -> np.ndarray:
    """Allocates a zeroed `chunk_size` x `chunk_size` tile data array (empty
    chunk) with `num_tile_vals` values per tile, matching the layout `Chunk` expects."""
    return np.zeros(chunk_size*chunk_size*num_tile_vals, dtype=np.uint8)

class Tilemap(Node2D):
    """A layered grid of tiles, split into fixed-size `Chunk`s for storage
    and rendering. Tile positions are addressed in tilemap coordinates (see
    `tilemap_pos`); `chunk_pos`/`tile_pos` convert those down to the chunk
    a tile lives in and its local position within that chunk.
    """

    def __init__(self, position: Vector = Vector(), rotation: float = 0, scale: Vector = Vector(1, 1), chunk_size: int=16, tile_size: int=1):
        """Args:
            position: World position of the tilemap node.
            rotation: World rotation of the tilemap node.
            scale: World scale of the tilemap node.
            chunk_size: Width/height of each chunk, in tiles.
            tile_size: Size of a single tile, in world units.
        """
        super().__init__(position, rotation, scale)
        self.layers: dict[str, Layer] = {}
        self.chunk_size = chunk_size
        self.tile_size = tile_size
        self.renderer = None

        self._spritesheet_types: dict[str, type[TilemapSpritesheet]] = {'static': StaticSpritesheet}
        self.spritesheets: dict[str, TilemapSpritesheet] = {}


    def add_layer(self, name, chunks: dict[Vector, Chunk] = {}, visible = False):
        """Creates a new, empty (unless `chunks` is given) layer under `name`."""
        self.layers[name] = Layer(name, chunks, visible)

    def add_spritesheet_type(self, type: type['TilemapSpritesheet']):
        """Registers a `TilemapSpritesheet` subclass so it can be created by
        `create_spritesheet`/`add_spritesheet` via its `get_name()`."""
        self._spritesheet_types[type.get_name()] = type

    def get_tile_neighbors():
        """Not yet implemented."""
        pass

    def create_spritesheet(self, data):
        """Creates a spritesheet and adds it the tilemaps spritesheets."""
        spritesheet_type = data.get('type', 'static')
        spritesheet_name = data.get('name', None)
        
        if spritesheet_name == None:
            error('Cannot add spritesheet because no name was set.')
            return
        
        self.add_spritesheet(spritesheet_name, self._spritesheet_types[spritesheet_type](data))

    def add_spritesheet(self, spritesheet_type: str, data: dict):
        """Instantiates a registered spritesheet type from `data` and stores it
        under `data["name"]`. Requires `create_renderer` to have been called
        first, since spritesheet construction needs the renderer to upload textures."""
        if not spritesheet_type in self._spritesheet_types:
            warning(f"Spritesheet type '{spritesheet_type}' is not defined")
        
        if self.renderer:
            name = data.get('name', None)
            if name == None:
                warning('Could not add spritesheet, a name was not defined in the provided data.')
                return 
            
            self.spritesheets[name] = self._spritesheet_types[spritesheet_type](data, self.renderer)
        else:
            warning('Could not add spritesheet, as no tilemap renderer has been created')

    def create_renderer(self):
        """Creates and attaches this tilemap's `TilemapRenderer`, and registers
        the built-in `StaticSpritesheet` type. Must be called before any
        spritesheet is added (see `add_spritesheet`)."""
        self.renderer = TilemapRenderer(Vector(), 0, Vector(1, 1))
        self.add(self.renderer)
        self.add_spritesheet_type(StaticSpritesheet)

    def set_tile(self, position: Vector, image_id: int, spritesheet: str, layer: str):
        """Sets the tile at tilemap `position` on `layer`, resolving it to the
        owning chunk first."""
        chunk = self.get_chunk(self.chunk_pos(position), layer)
        tile_pos = self.tile_pos(position)

        chunk.set_tile(tile_pos, image_id, spritesheet)

    def get_tile(self, position: Vector, layer: str) -> Tile:
        """Gets the tile at tilemap `position` on `layer`, resolving it to the
        owning chunk first."""
        chunk = self.get_chunk(self.chunk_pos(position), layer)
        return chunk.get_tile(position)

    def add_chunk(self, position: Vector, layer: str, data: np.ndarray=None) -> Chunk:
        """Creates a chunk at chunk-grid `position` on `layer`, backed by `data`
        if given, otherwise a freshly allocated empty chunk."""
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
        """Gets the chunk at chunk-grid `position` on `layer`, logging an error
        (and returning `None`) if no chunk exists there."""
        if self.chunk_exists(position, layer):
            return self.layers[layer].chunks[position]
        else:
            error(f'No chunk at position "{position}".')

    def chunk_exists(self, position: Vector, layer: str) -> bool:
        """Whether a chunk has been created at chunk-grid `position` on `layer`."""
        return position in self.layers[layer].chunks.keys()

    def __str__(self):
        layers = {}
        for layer in self.layers:
            layers[self.layers[layer].name] = self.layers[layer].chunks
        
        return str(layers)