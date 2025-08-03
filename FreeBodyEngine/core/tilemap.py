from FreeBodyEngine.core.node import Node2D
from FreeBodyEngine.math import Vector
from FreeBodyEngine.graphics.material import Material
from FreeBodyEngine.graphics.fbusl.injector import Injector
import numpy as np
from FreeBodyEngine import get_main, warning, error
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

class Chunk:
    def __init__(self, tilemap: 'Tilemap', position: Vector, size: int):
        self.tilemap = tilemap
        self.size = size
        self.position = position
        self.tiles: np.ndarray = self.generate_empty_data()

    def generate_empty_data(self) -> np.ndarray:
        # size*size grid of [-1,]*4
        return np.full((self.size, self.size, 4), -1, dtype=np.int32)

    def get_tile(self, position: Vector) -> Tile:
        t = self.tiles[position.x, position.y]
        return Tile(Vector(t[0], t[1]), t[2], t[3], self)

    def set_spritesheet(self, position: Vector, new_spritesheet: str):
        self.tiles[position.x, position.y][3] = new_spritesheet

    def set_image_id(self, position: Vector, new_image_id: int):
        self.tiles[position.x, position.y][2] = new_image_id

    def remove_tile(self, position: Vector):
        self.tiles[position.x, position.y] = [-1] * 4

    def set_tile(self, position: Vector, image_id: int, spritesheet: str):
        self.tiles[position.x, position.y] = (position.x, position.y, image_id, spritesheet)

    def __str__(self):
        rows = []
        for y in range(self.size):
            row = []
            for x in range(self.size):
                tile = self.tiles[x, y].tolist()
                row.append(str(tile))
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
    def __init__(self, position: Vector = Vector(), rotation: float = 0, scale: Vector = Vector(), chunk_size: int=16, tile_size: int=1):
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
        self.add(TilemapRenderer(Vector(), 0, Vector()))

    def get_layer_data(self, layer: str) -> np.ndarray:
        flattened_chunks = [chunk.reshape(-1, 3) for chunk in self.layers[layer].chunks]
        return np.concatenate(flattened_chunks, axis=0)

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
        self.renderer = self.scene.main.renderer

        chunk_world_size = self.parent.chunk_size * self.parent.tile_size
        self.mesh = get_main().renderer.mesh_class.generate_quad(chunk_world_size, chunk_world_size)


        self.tilemap_buffer = self.renderer.create_buffer(self.parent.get_layer_data())
        
        tile_bytes = 16 # position (8 bytes) + image id (4 bytes) + spritesheet id (4 bytes)
        chunk_bytes = 16 + (tile_bytes * self.parent.chunk_size) # position (8 bytes) + padding (8 bytes) + tiles 
        
        max_ubo_size = get_main().renderer.buffer_class.get_max_size()

        self.max_rendered_chunks = math.floor(max_ubo_size / chunk_bytes)

        self.spritesheet_buffer = self.renderer.create_buffer(self.parent.get_spritesheet_data())

        self.material: Material = get_main().files.load_material('engine/graphics/tilemap.fbmat')

    def draw(self, camera):
        self.spritesheet_buffer.set_data(self.parent.get_spritesheet_data())
        self.material.shader.set_buffer('')

        for layer in self.parent.layers:
            self.tilemap_buffer.set_data(self.parent.get_layer_data(self.parent.layers[layer]))

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
        new.replace('_ENGINE_CHUNK_SIZE', self.chunk_size)
        new.replace('_ENGINE_MAX_CHUNKS',  self.chunk_size)

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
