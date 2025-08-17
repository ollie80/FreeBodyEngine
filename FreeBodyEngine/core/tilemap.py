from FreeBodyEngine.core.node import Node2D
from FreeBodyEngine.math import Vector
from FreeBodyEngine.graphics.material import Material
from FreeBodyEngine.graphics.fbusl.injector import Injector
import numpy as np
from FreeBodyEngine import get_main, warning, error, get_service
from FreeBodyEngine.utils import abstractmethod
from dataclasses import dataclass

import math

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from FreeBodyEngine.graphics.texture import Texture
    from FreeBodyEngine.graphics.renderer import Renderer



class Tile:
    def __init__(self, position: Vector, image_id: Vector, spritesheet: str, chunk: 'Chunk'):
        self._position = position
        self._image_id = image_id
        self._spritesheet = spritesheet
        self._chunk = chunk
    
    @property
    def position(self) -> Vector:
        return self._position
    
    @position.setter
    def position(self, new: Vector):
        if new != self._position:
            self._chunk.remove_tile(self._position)
            self._position = new
            self._chunk.set_tile(self._position, self._image_id, self._spritesheet)

    @property
    def image_id(self) -> int:
        return self.image_id

    @image_id.setter
    def image_id(self, new: int):
        self._chunk.set_image_id(self._position, new)

    @property
    def spritesheet(self) -> str:
        return self._spritesheet

    @spritesheet.setter
    def spritesheet(self, new: str):
        self._chunk.set_spritesheet(self._position, new)

    def destroy(self):
        self._chunk.remove_tile(self._position)

    def __repr__(self):
        return f"Tile({self.position})"

class Chunk:
    def __init__(self, tilemap: 'Tilemap', position: Vector, size: int):
        self.tilemap = tilemap
        self.size = size
        self.position = position

        tile_dtype = np.dtype([
            ('position', np.float32, 2),      # vec2 (8 bytes)
            ('_pad0', np.float32, 2),         # padding (8 bytes)
            ('image_id', np.int32),           # 4 bytes
            ('spritesheet_index', np.int32),  # 4 bytes
            ('_pad1', np.float32, 2),         # padding (8 bytes)
        ])

        chunk_dtype = np.dtype([
            ('position', np.float32, 2),      # vec2 (8 bytes)
            ('_pad0', np.float32, 2),         # padding (8 bytes)
            ('tiles', tile_dtype, size * size),  
        ])

        self.data = np.zeros(1, dtype=chunk_dtype)
        self.data['position'][0] = (position.x, position.y)

    def _tile_index(self, position: Vector) -> int:
        return int(position.x + position.y * self.size)

    def get_tile(self, position: Vector) -> 'Tile':
        idx = self._tile_index(position)
        t = self.data['tiles'][0][idx]

        if t['image_id'] == -1:
            return None

        tile_pos = Vector(t['position'][0], t['position'][1])
        return Tile(tile_pos, t['image_id'], t['spritesheet_index'], self)

    def set_tile(self, position: Vector, image_id: int, spritesheet_index: int):
        idx = self._tile_index(position)
        self.data['tiles'][0][idx]['position'] = (position.x, position.y)
        self.data['tiles'][0][idx]['image_id'] = image_id
        self.data['tiles'][0][idx]['spritesheet_index'] = spritesheet_index

    def remove_tile(self, position: Vector):
        idx = self._tile_index(position)
        self.data['tiles'][0][idx]['image_id'] = -1
        self.data['tiles'][0][idx]['spritesheet_index'] = -1
        self.data['tiles'][0][idx]['position'] = (-1, -1)

    def get_all_tiles(self) -> list['Tile']:
        tiles = []
        for idx in range(self.size * self.size):
            tile_data = self.data['tiles'][0][idx]
            if tile_data['image_id'] != -1:
                tile_pos = Vector(tile_data['position'][0], tile_data['position'][1])
                tiles.append(Tile(tile_pos, tile_data['image_id'], tile_data['spritesheet_index'], self))
        return tiles

    def __str__(self):
        rows = []
        for y in range(self.size):
            row = []
            for x in range(self.size):
                idx = x + y * self.size
                tile = self.data['tiles'][0][idx]
                row.append(f"({tile['position'][0]:.0f},{tile['position'][1]:.0f}), id:{tile['image_id']}, ss:{tile['spritesheet_index']}")
            rows.append(", ".join(row))
        return "\n".join(rows)

    def __repr__(self):
        return str(self)
    
@dataclass
class Layer:
    name: str
    chunks: dict[Vector, Chunk]
    visible: bool

class Tilemap(Node2D):
    def __init__(self, position: Vector = Vector(), rotation: float = 0, scale: Vector = Vector(1, 1), chunk_size: int=16, tile_size: int=1):
        super().__init__(position, rotation, scale)
        self.layers: dict[str, Layer] = {}
        self.chunk_size = chunk_size
        self.tile_size = tile_size
        self._spritesheet_types: dict[str, type[TileSpritesheet]] = {'static': StaticSpritesheet}
        self.spritesheets: dict[str, TileSpritesheet] = {}

    def add_layer(self, name, chunks: dict[Vector, Chunk] = {}, visible = False):
        self.layers[name] = Layer(name, chunks, visible)

    def add_spritesheet_type(self, name: str, type: type['TileSpritesheet']):
        self.spritesheet_types[name] = type

    def create_spritesheet(self, data):
        """Creates a spritesheet and adds it the tilemaps spritesheets."""
        spritesheet_type = data.get('type', 'static')
        spritesheet_name = data.get('name', None)
        
        if spritesheet_name == None:
            error('Cannot add spritesheet because no name was set.')
            return
        
        self.add_spritesheet(spritesheet_name, self._spritesheet_types[spritesheet_type](data))

    def add_spritesheet(self, name: str, spritesheet: 'TileSpritesheet'):
        if name in self._spritesheet_types:
            warning(f'Cant add spritesheet "{name}" because it already exsists.')
            return
        
        self.spritesheets[name] = spritesheet

    def create_renderer(self):
        self.add(TilemapRenderer(Vector(), 0, Vector(1, 1)))

    def get_layer_data(self, layer: str) -> np.ndarray:
        chunks = self.layers[layer].chunks
        chunk_count = len(chunks)
        tiles_per_chunk = self.chunk_size * self.chunk_size
        total_tiles = chunk_count * tiles_per_chunk
        
        data = np.empty((total_tiles, 8), dtype=np.float32)
        
        i = 0
        for chunk_pos, chunk in chunks.items():
            tiles_flat = chunk.data['tiles'].reshape(-1)
            
            data[i:i+tiles_per_chunk, 0] = chunk_pos.x
            data[i:i+tiles_per_chunk, 1] = chunk_pos.y
            data[i:i+tiles_per_chunk, 2] = 1.5
            data[i:i+tiles_per_chunk, 3] = 1.5
            
            data[i:i+tiles_per_chunk, 4] = tiles_flat['position'][:, 0]
            data[i:i+tiles_per_chunk, 5] = tiles_flat['position'][:, 1]
            data[i:i+tiles_per_chunk, 6] = tiles_flat['image_id'].astype(np.float32)
            data[i:i+tiles_per_chunk, 7] = tiles_flat['spritesheet_index'].astype(np.float32)
            
            i += tiles_per_chunk
        
        return data

    def set_tile(self, position: Vector, image_id: int, spritesheet: str, layer: str):
        chunk = self.get_chunk(self.chunk_pos(position), layer)
        chunk.set_tile(self.tile_pos(position), image_id, spritesheet)

    def get_tile(self, position: Vector, layer: str) -> Tile:
        chunk = self.get_chunk(self.chunk_pos(position), layer)
        return chunk.get_tile(position)

    def add_chunk(self, position: Vector, layer: str) -> Chunk:
        self.layers[layer].chunks[position] = Chunk(self, position, self.chunk_size)

    def tilemap_pos(self, position: Vector) -> Vector:
        '''Converts a world position into a position in the tilemap.'''
        return Vector(math.floor(position.x / self.tile_size), math.floor(position.y / self.tile_size))

    def chunk_pos(self, position: Vector) -> Vector:
        '''Converts a tilemap position into a chunk position.'''
        return Vector(math.floor(position.x / self.chunk_size), math.floor(position.y / self.chunk_size))

    def tile_pos(self, position: Vector) -> Vector:
        '''Converts a tilemap position into the tile position in the chunk.'''
        return Vector(math.floor(position.x % self.chunk_size), math.floor(position.y % self.chunk_size))

    def get_spritesheet_data(self):
        return np.array([])

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
            

class TilemapRenderer(Node2D):
    def __init__(self, position: Vector, rotation: float, scale: Vector):
        super().__init__(position, rotation, scale)
        self.parental_requirement = "Tilemap"
        
        self.parent: Tilemap

    def on_initialize(self):
        self.renderer: Renderer = get_service('renderer')

        chunk_world_size = self.parent.chunk_size * self.parent.tile_size
        self.mesh = self.renderer.mesh_class.generate_quad(1.0, 1.0)


        self.tilemap_buffer = self.renderer.create_buffer(np.array([]))
        
        tile_bytes = 16 # position (8 bytes) + image id (4 bytes) + spritesheet id (4 bytes)
        chunk_bytes = 16 + (tile_bytes * self.parent.chunk_size) # position (8 bytes) + padding (8 bytes) + tiles 
        
        max_ubo_size = self.renderer.get_max_buffer_size()

        self.max_rendered_chunks = math.floor(max_ubo_size / chunk_bytes)
        self.spritesheet_buffer = self.renderer.create_buffer(np.array([]))
        self.material: Material = get_service('files').load_material('engine/graphics/tilemap.fbmat', TilemapInjector(self.parent.chunk_size, self.parent.tile_size, self.max_rendered_chunks))

    def draw(self, camera):
        self.spritesheet_buffer.set_data(self.parent.get_spritesheet_data())
        
        self.material.shader.set_buffer('SpritesheetData', self.spritesheet_buffer)
        self.material.shader.set_buffer('Chunks', self.tilemap_buffer)

        for layer in self.parent.layers:
            self.tilemap_buffer.set_data(self.parent.get_layer_data(layer))

            self.renderer.draw_mesh_instanced(self.mesh, len(self.parent.layers[layer].chunks), self.material, self.world_transform, camera)

        self.tilemap_buffer.unbind()
        self.spritesheet_buffer.unbind()
        

class TilemapInjector(Injector):
    def __init__(self, chunk_size, tile_size, max_chunks):
        super().__init__()

        self.chunk_size = chunk_size
        self.max_chunks = max_chunks
        self.tile_size = tile_size

    def pre_lexer_inject(self, source):
        new = source
        new = new.replace('_ENGINE_CHUNK_SIZE', str(self.chunk_size))
        new = new.replace('_ENGINE_CHUNK_WORLD_SIZE', str(self.chunk_size * self.tile_size))
        new = new.replace('_ENGINE_TILE_SIZE', str(self.tile_size))
        new = new.replace('_ENGINE_MAX_CHUNKS',  str(self.max_chunks))
        new = new.replace('_ENGINE_MAX_SPRITESHEETS',  str(2))
        new = new.replace('_ENGINE_MAX_SPRITESHEET_TEXTURES', str(2))

        return new

class TileSpritesheet:
    def __init__(self, data, name: str, texture: 'Texture'):
        self.name = name
        self.texture = texture

    @abstractmethod
    def update(self):
        pass
    
class StaticSpritesheet:
    def __init__(self, data):
        self.data = data
        self.map: dict[str, tuple[int, int, int, int]] = self.data.get('map', {})

    def get_data(self):
        return np.array()

    def get_image_id(self, name: str):
        return self.map[name]

    def update(self):
        pass
