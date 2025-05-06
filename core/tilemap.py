from dataclasses import dataclass
import dataclasses
import math
import moderngl
import numpy as np
import pygame
from pygame.math import Vector2 as vector
import FreeBodyEngine as engine
import FreeBodyEngine.data
from typing import Type

CHUNK_VERT = """
#version 330 core

uniform mat4 proj;
uniform mat4 view;
uniform vec2 position;

in vec2 vert;
in vec2 texCoord;
out vec2 uv;

void main() {
    uv = texCoord;

    gl_Position = proj * view * vec4(vec2(vert + position).x, vec2(vert + position).y, 0.0, 1.0);
}
"""

CHUNK_FRAG = """

""" 

BITMASK_LOOKUP = {
    0b0000: "none",
    0b0001: "top",
    0b0010: "right",
    0b0011: "top_right",
    0b0100: "bottom",
    0b0101: "top_bottom",
    0b0110: "bottom_right",
    0b0111: "top_bottom_right",
    0b1000: "left",
    0b1001: "top_left",
    0b1010: "left_right",
    0b1011: "top_left_right",
    0b1100: "bottom_left",
    0b1101: "top_bottom_left",
    0b1110: "bottom_left_right",
    0b1111: "all"
}


def empty_chunk_frag_data(chunk_size):
    data = np.full((chunk_size * chunk_size, 2), -1.0, dtype=np.float32)  # Shape (256,2)
    return data


class ChunkShader(engine.graphics.Shader):
    def __init__(self, scene: engine.actor.Scene, image: "ChunkImage"):
        self.image = image
        super().__init__(scene, scene.files.load_text("engine/shader/graphics/world.vert"), scene.files.load_text("engine/shader/graphics/chunk.frag"))

    def set_uniforms(self, pos_data, albedo: moderngl.Texture, normal: moderngl.Texture):
        self.set_generic_uniforms()
        self.set_vert_uniforms()
        self.set_frag_uniforms(pos_data, albedo, normal)

    def set_frag_uniforms(self, pos_data, albedo: moderngl.Texture, normal: moderngl.Texture):
        
        self.program['chunk_size'] = self.image.chunk.tilemap.chunk_size
        self.program['img_positions'].write(pos_data)
        
        albedo_id = self.image.scene.texture_locker.add(self.image.name) 
        normal_id = self.image.scene.texture_locker.add(self.image.normal_name)

        albedo.use(albedo_id)
        normal.use(normal_id)

        self.program['spritesheet'] = albedo_id
        self.program['normal'] = normal_id

        self.program['spritesheet_size'] = albedo.size
        self.program['tile_size'] = self.image.chunk.tilemap.tile_size
        self.image.scene.texture_locker.remove(self.image.name)
        self.image.scene.texture_locker.remove(self.image.normal_name)

class ChunkImage(engine.graphics.Image):
    def __init__(self, chunk: "Chunk", scene: engine.actor.Scene):
        self.chunk = chunk
        super().__init__(None, self.chunk.image_key, scene, size=(self.chunk.tilemap.chunk_world_size, self.chunk.tilemap.chunk_world_size))
        self.set_shader(ChunkShader(self.scene, self))
        self.position = self.chunk.world_position

    def draw(self):
        groups = {}
        i = 0
        for y in self.chunk.tiles:
            for tile in y:
                if tile != None:
                    if tile.tileset_name not in groups.keys():
                        groups[tile.tileset_name] = self.chunk.tilemap.frag_data.copy()
                    groups[tile.tileset_name][i] = [tile.image_pos[0], tile.image_pos[1]]
                i += 1

        for group in groups:
            tileset = self.chunk.tilemap.get_tileset(group)
            albedo = tileset.general
            normal = tileset.normal

            
            self.shader.set_uniforms(groups[group], albedo, normal)
            self.render_object.render(mode=moderngl.TRIANGLE_STRIP)

class Tileset:
    def __init__(self, scene: engine.actor.Scene, data):
        self.scene = scene
        self.spritesheet = self.scene.files.load_spritesheet(data['spritesheet'])
        self.type = data['type']

    @property
    def general(self):
        return self.spritesheet.general

    @property
    def normal(self):
        return self.spritesheet.normal
    
    def update(self, dt):
        pass

class AutoTileset(Tileset):
    def __init__(self, scene, data):
        super().__init__(scene, data)
        self.tiles: dict[str, tuple[int, int]] = data['tiles']
        self.diagonals: bool = data.get('diagonals', False)

# class AnimatedTileset(Tileset):
#     def __init__(self, scene: engine.core.Scene, data):
#         super().__init__(scene, data)
#         self.animation_player = 

#     def update(self):


@dataclass
class TileData:
    type: Type["Tile"]
    tileset_name: str
    img_pos: tuple

@dataclass
class WorldTileData:
    type: Type["WorldTile"]
    tileset_name: str

# class AnimatedTileData:
#     type: Type["AnimatedTile"]
#     tileset_name: str

class Tile:
    def __init__(self, data: Type[TileData]):
        self.image_pos = data.img_pos # position in spritesheet
        self.tileset_name = data.tileset_name

    def initialize(self, chunk: "Chunk", pos: vector):
        self.chunk = chunk
        self.position = pos
        self.on_initialize()
    
    def on_update(self):
        pass

    def on_initialize(self):
        pass

class WorldTile(Tile): # autotiling
    def __init__(self, data: WorldTileData):
        self.tileset_name = data.tileset_name
        self.image_pos = (0, 0)  

    def on_initialize(self):
        self.update_image()      
        
    def on_update(self):
        self.update_image()
    
    def update_image(self):
        bitmask = self.get_bitmask()
        tile_key = BITMASK_LOOKUP.get(bitmask, "none")

        self.image_pos = self.chunk.tilemap.get_tileset(self.tileset_name).tiles[tile_key]

    def get_bitmask(self):
        neighbors = self.chunk.check_neighbors(self)
        
        bitmask = 0
        if neighbors[0]: bitmask |= 1  # Top
        if neighbors[1]: bitmask |= 2  # Right
        if neighbors[2]: bitmask |= 4  # Bottom
        if neighbors[3]: bitmask |= 8  # Left
        return bitmask


class Object:
    def __init__(self, image, pos: vector, name: str, collision_type: str = "none", size=(64, 64)):
        self.position  = pos
        self.name = name
        self.chunk: Chunk = None
        self.collision_type = collision_type
        self.image = image
        self.size = size
        
    def initialize(self, chunk: "Chunk"):
        self.chunk = chunk
        if isinstance(self.image, pygame.Surface):
            self.load_image()

    def load_image(self):
            self.image = engine.graphics.Image(self.image, self.name, self.chunk.tilemap.scene, self.size)
            self.image.position = self.world_position
            self.image.set_shader(engine.graphics.DefaultShader())

    @property
    def world_position(self):
        return self.position + self.chunk.world_position

    def check_collisions(self):
        for actor in (e for e in self.chunk.tilemap.scene.entities if isinstance(e, engine.actor.Actor)):
            if actor.collision_type != "none" and self.chunk.tilemap.get_chunk_pos(self) == self.chunk.position:
                self.on_collision(actor)
                
    def on_collision(self, other: engine.actor.Actor):
        pass

    def draw(self):
        self.chunk.tilemap.scene.graphics.add_general(self.image)

        self.on_draw()

    def update(self, dt):
        self.image.update(dt)
        self.on_update(dt)

    def on_update(self, dt):
        pass

    def on_chunk_tile_update(self):
        pass

    def on_chunk_object_update(self):
        pass

    def on_draw(self):
        pass

    def on_unload(self):
        pass

    def on_load(self):
        pass

class Chunk: 
    def __init__(self, position: vector, tilemap: "TileMap", layer_name: str, chunk_key: str): 
        self.position = position # not world pos
        self.tiles: list[list[Tile]] = []
        self.tilemap = tilemap
        self.layer_name: str = layer_name
        self.chunk_key = chunk_key
        self.image_key = "chunk_" + self.chunk_key + "_" + tilemap.name
        self.image: engine.graphics.Image = ChunkImage(self, self.tilemap.scene)
        self.objects: list[Object] = []
        
    @property
    def world_position(self):
        return self.tilemap.position + (self.position * (self.tilemap.tile_size * self.tilemap.chunk_size))

    def get_tile(self, pos) -> Tile:
        if pos.x < self.tilemap.chunk_size and pos.y < self.tilemap.chunk_size:
            tile = self.tiles[round(pos.y)][round(pos.x)]
            return tile
        return None
    
    def set_tile(self, pos: vector, tile: Tile, update: bool = True):
        self.tiles[round(pos.y)][round(pos.x)] = tile
        tile.initialize(self, pos)
        if update:
            neighbors = self.get_neighbors(tile)
            for t in neighbors:
                if t != None:
                    t.on_update() 

    def object_update(self):
        for object in self.objects:
            object.on_chunk_object_update()

    def tile_update(self):
        for y in self.tiles:
            for tile in y:
                if tile != None:
                    tile.on_update()
        for object in self.objects:
            object.on_chunk_tile_update()
    
    def add_object(self, object):
        self.objects.append(object)
        self.object_update()

    def remove_object(self, object):
        self.objects.remove(object)
        self.object_update()

    def remove_tile(self, pos):
        self.tiles[round(pos.y)][round(pos.x)] = None
        self.tile_update()

    def update(self, dt):
        for object in self.objects:
            object.update(dt)

    def kill(self):
        self.tilemap.remove_chunk(self)
        self.image.remove()

    def update_neighbor_chunks(self):
        directions = [vector(0, -1), vector(1, 0), vector(0, 1), vector(-1, 0)]
        for direction in directions:
            
            chunk = self.tilemap.get_chunk(self.layer_name, self.position+direction)
            if chunk:
                chunk.generate_image()

    def check_neighbors(self, tile):
        new = []
        neighbors = self.get_neighbors(tile)
        for t in neighbors:
            if t != None and t.tileset_name == tile.tileset_name:
                new.append(t)
            else:
                new.append(None)

        return new

    def get_neighbors(self, tile):
        directions = [vector(0, -1), vector(1, 0), vector(0, 1), vector(-1, 0)]
        neighbors = []
        
        for direction in directions:
            neighbor = None
            neighbor_pos = tile.position + direction
            if (neighbor_pos.x > 15 or neighbor_pos.x < 0) or (neighbor_pos.y > 15 or neighbor_pos.y < 0):
                neighbor_chunk = self.tilemap.get_chunk(self.layer_name, self.position - direction)
                if neighbor_chunk:
                    neighbor = neighbor_chunk.get_tile(vector(neighbor_pos.x%16, neighbor_pos.y%16))
            else:
                neighbor = self.get_tile(neighbor_pos)
            
                
            neighbors.append(neighbor)
        
        return neighbors

    def graphics_setup(self):
        self.shader = ChunkShader()
        self.vao = engine.graphics.create_fullscreen_quad(self.tilemap.scene.glCtx, )

    def draw(self):
        self.tilemap.scene.graphics.add_general(self.image)

    def __str__(self):
        return f"Chunk at pos: {self.position}. with tiles: {self.tiles}"

@dataclass
class Layer:
    name: str
    chunks: list[Chunk]
    collision: bool

class TileMap:
    def __init__(self, scene: engine.actor.Scene, name: str, tile_size = 64, chunk_size = 16, pos: vector = vector(0,0)):
        self.tilesets: dict[str, Tileset] = {}
        self.chunks: list[Chunk] = []
        self.chunk_key_locker = engine.data.IndexKeyLocker()
        
        self.tile_size = tile_size

        self.position = pos

        self.name = name
        self.scene = scene
        
        self.chunk_size = chunk_size
        self.chunk_world_size = self.chunk_size * self.tile_size
        
        self.layers: dict[str, Layer] = {}
        self.frag_data = empty_chunk_frag_data(self.chunk_size)

    def get_chunk(self, layer, pos):
        for chunk in self.layers[layer].chunks:
            if chunk.position == pos:
                return chunk

    def get_world_pos(self, chunk_pos: vector, pos: vector):
        return vector(pos.x + (chunk_pos.x * self.chunk_size * self.tile_size), pos.y + (chunk_pos.y * self.chunk_size * self.tile_size))

    def remove_chunk(self, layer, chunk: Chunk):
        
        self.layers[layer].chunk.kill()
        self.layers[layer].chunks.remove(chunk)

    def get_bounds(self):
        first_key = next(iter(self.layers)) 
        default_set = False     # Get the first key
        for layer in self.layers:
            if not default_set:
                if len(self.layers[first_key].chunks) > 0:
                    chunk1 = self.layers[layer].chunks[0]
                    bounds = [chunk1.world_position.x, chunk1.world_position.y, chunk1.world_position.x + self.chunk_world_size, chunk1.world_position.y + self.chunk_world_size]
                    default_set = True

            for chunk in self.layers[layer].chunks:
                x, y = chunk.world_position.x, chunk.world_position.y
                max_x, max_y = self.chunk_world_size, self.chunk_world_size 
                if x < bounds[0]:
                    bounds[0] = x
                if y < bounds[1]:
                    bounds[1] = y
                if max_x > bounds[2]:
                    bounds[2] = max_x
                if max_y > bounds[3]:
                    bounds[3] = max_y

        if default_set == False:
            print(self.layers)

        return bounds
    
    def draw(self):
        for layer in self.layers:
            for chunk in self.layers[layer].chunks:
                chunk.draw()
    
    def remove_tile(self, layer, pos: vector):
        chunk_pos = self.get_chunk_pos(pos)
        chunk = self.get_chunk(layer, chunk_pos)
        t_pos = self.get_tile_pos(pos)
        chunk.remove_tile(t_pos)

    def get_tileset(self, name):
         if self.tilesets.get(name) != None:
             return self.tilesets[name]
         else: 
             self.tilesets[name] = self.scene.files.load_tileset(name, self.scene)
             return self.tilesets[name]

    def set_tile(self, layer, tile: Tile, pos: vector):
        chunk_pos = self.get_chunk_pos(pos)
        chunk = self.get_chunk(layer, chunk_pos)
        t_pos = self.get_tile_pos(pos)
        chunk.set_tile(t_pos, tile, True)

    def create_chunk(self, layer, pos: vector, tiles: dict[vector, TileData], objects: list[Object]):
        tile_data = self.generate_empty_chunk_data()
        chunk_id = self.chunk_key_locker.add()

        chunk = Chunk(pos, self, layer, chunk_id)
        chunk.tiles = tile_data
        for position in tiles:
            chunk.set_tile(vector(*position), tiles[position].type(tiles[position]), False)
        
        chunk.tile_update()
        
        self.layers[layer].chunks.append(chunk)

    def generate_empty_chunk_data(self):
        data = []
        for y in range(self.chunk_size):
            data.append([])
            for x in range(self.chunk_size):
                data[y].append(None)
        return data
    
    def add_layer(self, layer: Layer):
        self.layers[layer.name] = layer

    def get_chunk_pos(self, pos: vector):
        position = pos  - self.position
        return vector(math.floor(position.x / self.chunk_world_size), math.floor(position.y / self.chunk_world_size))

    def get_tile_pos(self, pos: vector):
        position = pos  - self.position
        return vector(math.floor(position.x / self.tile_size), math.floor(position.y / self.tile_size))

    def get_world_tile(self, pos: vector) -> Tile:
        chunk = self.get_chunk(self.get_chunk_pos(pos))
        return chunk.get_tile((chunk.position * self.chunk_size) + self.get_tile_pos(pos)) 

    def on_update(self):
        pass
    
    def get_chunk_data(self, chunk: "Chunk"): # returns the chunk as a list of TileData objects
        tiles = []
        for y in chunk.tiles:
            for tile in y:
                if tile != None:
                    if isinstance(tile, WorldTile):
                        tiledata = {'type': 'world', "tileset_name": tile.tileset_name}
                    
                    else:
                        tiledata = {'type': 'static', "tileset_name": tile.tileset_name, "img_pos": list(tile.image_pos)}

                    tiles.append({"position": list(tile.position), "data": tiledata})
        return tiles
    
    def get_data(self):
        data = {"name": self.name, "tile_size": self.tile_size, "chunk_size": self.chunk_size, "layers": []}
        for layer in self.layers:
            chunks = {}
            for chunk in self.layers[layer].chunks:
                chunks[chunk.chunk_key]= {"tiles": self.get_chunk_data(chunk), 'pos': list(chunk.position)}
            
            data['layers'].append({"chunks": chunks, "collision": self.layers[layer].collision, "name": self.layers[layer].name})
        return data

    def from_data(scene, data) -> "TileMap":
        tilemap = TileMap(scene, data['name'], data['tile_size'], data['chunk_size'])

        for layer in data['layers']:
            tilemap.add_layer(Layer(layer['name'], [], layer['collision']))
            for chunk in layer['chunks']:
                chunk_data = layer['chunks'][chunk]
                tiles = {}
                for tile in chunk_data['tiles']:
                    if tile['data']['type'] == "world":
                        tiledata = WorldTileData(WorldTile, tile['data']['tileset_name'])
                    elif tile['data']['type'] == "static":
                        tiledata = TileData(Tile, tile['data']['tileset_name'], tile['data']['img_pos'])

                    tiles[tuple(tile['position'])] = tiledata
                tilemap.create_chunk(layer['name'], vector(chunk_data['pos']), tiles, [])
                tilemap.get_chunk(layer['name'], vector(chunk_data['pos']))

        return tilemap

    def update(self, dt):
        for chunk in self.chunks:
            chunk.update(dt)
        
        self.on_update()

