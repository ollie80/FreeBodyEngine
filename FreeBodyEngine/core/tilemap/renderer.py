from dataclasses import dataclass
from FreeBodyEngine.math import Vector
from FreeBodyEngine.core.tilemap.chunk import Chunk
from FreeBodyEngine.core.tilemap import _NUM_TILE_VALS
from FreeBodyEngine.core.node import Node2D
from FreeBodyEngine import get_service
from FreeBodyEngine.utils import fbnjit
from fbusl.injector import Injector
from typing import TYPE_CHECKING
from FreeBodyEngine.graphics.mesh import AttributeType, BufferUsage
import numpy as np
from numba import types

if TYPE_CHECKING:
    from FreeBodyEngine.core.tilemap.tilemap import Tilemap

chunk_mesh_sig = types.Tuple((types.float32[:, :], types.float32[:, :], types.uint32[:]))(types.uint8[:], types.int32, types.int32)

@fbnjit(chunk_mesh_sig, cache=True)
def generate_chunk_mesh(chunk_data: np.ndarray, tile_size: int, chunk_size: int):        
    tiles_x = chunk_size
    tiles_y = chunk_size
    num_tiles = tiles_x * tiles_y

    vertices = np.zeros((num_tiles * 4, 4), dtype=np.float32)
    uv_array = np.zeros((num_tiles * 4, 2), dtype=np.float32)
    indices = np.zeros(num_tiles * 6, dtype=np.uint32)

    vtx_offset = 0
    idx_offset = 0
    uv_offset = 0

    for y in range(tiles_y):
        for x in range(tiles_x):
            base = (y * tiles_x + x) * _NUM_TILE_VALS
            image_id = chunk_data[base]
            sprite_id = chunk_data[base + 1]
            
            if image_id == 0 and sprite_id == 0:
                continue
            
            x0, y0 = x * tile_size, y * tile_size
            x1, y1 = x0 + tile_size, y0 + tile_size
            uvs = np.array([[0,0],[1,0],[1,1],[0,1]], dtype=np.float32)
            positions = np.array([[x0,y0],[x1,y0],[x1,y1],[x0,y1]], dtype=np.float32)
            
            for i in range(4):
                px, py = positions[i]
                u, v = uvs[i]
                vertices[vtx_offset + i] = [px, py, image_id, sprite_id]
                uv_array[uv_offset + i] = [u, v]
            
            indices[idx_offset:idx_offset+6] = [
                vtx_offset, vtx_offset+1, vtx_offset+2,
                vtx_offset+2, vtx_offset+3, vtx_offset
            ]
            
            vtx_offset += 4
            idx_offset += 6
            uv_offset += 4
    
    return vertices[:vtx_offset], uv_array[:uv_offset], indices[:idx_offset]



class TilemapRenderer(Node2D):
    def __init__(self, position: Vector, rotation: float, scale: Vector):
        super().__init__(position, rotation, scale)
        self.parental_requirement = "Tilemap"
        self.parent: 'Tilemap'

    def on_initialize(self):
        self.material = get_service('graphics').create_material({"shader": {"vert": "engine/shader/graphics/tilemap.fbvert", "frag": "engine/shader/graphics/tilemap.fbfrag"}}, TilemapInjector(self.parent.chunk_size, self.parent.tile_size))

    def draw(self, camera):
        for layer in self.parent.layers:
            for chunk_pos in self.parent.layers[layer].chunks:
                chunk = self.parent.layers[layer].chunks[chunk_pos]

                vertices, uvs, indices = generate_chunk_mesh(chunk.tiles, self.parent.tile_size, self.parent.chunk_size)
                mesh = get_service('renderer').get_mesh_class()(attributes={'vertices': (AttributeType.VEC4, vertices), 'uvs': (AttributeType.VEC2, uvs)}, indices=indices, usage=BufferUsage.DYNAMIC)
                self.material.shader.set_uniform('chunk_pos', (chunk.position.x, chunk.position.y))
                get_service("renderer").draw_mesh(mesh, self.material, self.world_transform, camera)


class TilemapInjector(Injector):
    def __init__(self, chunk_size, tile_size):
        self.chunk_size = chunk_size
        self.tile_size = tile_size

    def source_inject(self, source):
        new = source
        new = new.replace('_ENGINE_CHUNK_SIZE', str(self.chunk_size))
        new = new.replace('_ENGINE_CHUNK_WORLD_SIZE', str(self.chunk_size * self.tile_size))
        new = new.replace('_ENGINE_TILE_SIZE', str(self.tile_size))
        new = new.replace('_ENGINE_MAX_SPRITESHEETS',  str(2))
        new = new.replace('_ENGINE_MAX_SPRITESHEET_TEXTURES', str(2))
        print(new)
        return new

