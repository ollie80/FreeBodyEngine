from dataclasses import dataclass
from FreeBodyEngine.math import Vector
from FreeBodyEngine.core.tilemap.chunk import Chunk
from FreeBodyEngine.core.tilemap import _NUM_TILE_VALS
from FreeBodyEngine.core.node import Node2D
from FreeBodyEngine import get_service
from FreeBodyEngine.utils import fbnjit, HAS_NUMBA
from fbusl.injector import Injector
from FreeBodyEngine.graphics.color import Color
from FreeBodyEngine.graphics.material import BlendMode

from typing import TYPE_CHECKING
from FreeBodyEngine.graphics.mesh import AttributeType, BufferUsage
import numpy as np

if TYPE_CHECKING:
    from FreeBodyEngine.core.tilemap.tilemap import Tilemap

# A raw `from numba import types` (unlike fbnjit() below, which already
# degrades gracefully via utils.HAS_NUMBA) used to sit here unconditionally -
# fine on desktop, where numba is a real dependency, but numba itself has
# no Pyodide/WASM build at all (it JIT-compiles to native machine code via
# LLVM, which is fundamentally incompatible with running inside a WASM
# sandbox that can't JIT its own native code) - so importing it eagerly
# crashed `import FreeBodyEngine` itself on the web platform, the moment
# anything pulled in PBRPipeline (which imports TilemapRenderer
# unconditionally). Tilemap rendering isn't implemented for the web
# backend yet regardless, so `chunk_mesh_sig` is just left None there -
# fbnjit()'s own HAS_NUMBA fallback already ignores its signature argument
# when numba isn't installed, so this doesn't change desktop behavior at
# all, only what happens when numba genuinely isn't available.
if HAS_NUMBA:
    from numba import types
    chunk_mesh_sig = types.Tuple((types.float32[:, :], types.float32[:, :], types.uint32[:]))(
        types.uint8[:], types.int32, types.int32, types.int32, types.int32, types.int32
    )
else:
    chunk_mesh_sig = None


@fbnjit(chunk_mesh_sig, cache=True)
def generate_chunk_mesh(chunk_data: np.ndarray, tile_size: int, chunk_size: int,
                        spritesheet_index: int, sheet_cols: int, sheet_rows: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Builds a quad mesh for the tiles of one chunk that belong to one
    spritesheet, skipping empty tiles entirely so they cost nothing to draw.

    One mesh is built per (chunk, spritesheet) pair rather than per chunk:
    a spritesheet is one texture binding, and a tile's cell is selected by
    its UVs, so all tiles sharing a sheet draw together in one call.

    Unlike the previous version, a tile's vertices carry no `image_id`/
    `sprite_id` for the shader to resolve - the cell's sub-rect inside its
    spritesheet is baked straight into `uv_array` here, in sheet-local 0..1
    space. `sample()` then maps that through the sheet texture's own
    uv_rect (see graphics/gl33/generator.py's IMPLEMENTATIONS["sample"]),
    which is what makes it land correctly whether the sheet is a standalone
    texture (dev) or packed into an atlas (release). The cell rect is
    mirrored the same way `slice_texture_cell` mirrors one, because
    standalone textures are uploaded flipped on both axes - so a tile
    addresses a cell exactly like a `.fbanim` frame's `pos = [col, row]`
    does.

    Args:
        chunk_data: The chunk's flat per-tile value array (see `Chunk.tiles`).
        tile_size: Size of a tile in world units.
        chunk_size: Width/height of the chunk in tiles.
        spritesheet_index: Only tiles stored with this spritesheet index are
            emitted.
        sheet_cols: Columns in that spritesheet's cell grid.
        sheet_rows: Rows in that spritesheet's cell grid.

    Returns:
        `(vertices, uv_array, indices)`, each trimmed to just the tiles
        actually emitted.
    """
    num_tiles = chunk_size * chunk_size

    vertices = np.zeros((num_tiles * 4, 2), dtype=np.float32)
    uv_array = np.zeros((num_tiles * 4, 2), dtype=np.float32)
    indices = np.zeros(num_tiles * 6, dtype=np.uint32)

    vtx_offset = 0
    idx_offset = 0

    cell_w = 1.0 / sheet_cols
    cell_h = 1.0 / sheet_rows

    for y in range(chunk_size):
        for x in range(chunk_size):
            base = (y * chunk_size + x) * _NUM_TILE_VALS
            stored_id = chunk_data[base]
            sheet_id = chunk_data[base + 1]

            # A stored image id of 0 means "no tile", so cell indices are
            # stored offset by one. The old emptiness test was
            # `image_id < 0 and sprite_id == 0`, which treated a tile with
            # no image but a nonzero sheet as real and then indexed with a
            # negative id.
            if stored_id == 0 or sheet_id != spritesheet_index:
                continue

            cell = stored_id - 1
            col = cell % sheet_cols
            row = cell // sheet_cols

            u0 = cell_w * (sheet_cols - col - 1)
            v0 = cell_h * (sheet_rows - row - 1)
            u1 = u0 + cell_w
            v1 = v0 + cell_h

            x0 = x * tile_size
            x1 = x0 + tile_size

            # Tile rows run *downward* in world space: `Tilemap.tilemap_pos`
            # maps a world position to `-floor(y / tile_size) - 1`, so
            # tilemap row 0 covers world y in [-tile_size, 0) and higher
            # rows sit below it. This used to place row `y` at world y
            # `+y * tile_size`, laying rows out bottom-up - the exact
            # mirror of where tilemap_pos says they are, so a tile placed
            # at the mouse appeared reflected about y=0.
            y1 = -y * tile_size
            y0 = y1 - tile_size

            # Corner order and UV convention match graphics/mesh.py's
            # generate_quad(): u runs opposite to x (textures are uploaded
            # flipped left-right), v runs with y.
            vertices[vtx_offset + 0, 0] = x0
            vertices[vtx_offset + 0, 1] = y0
            uv_array[vtx_offset + 0, 0] = u1
            uv_array[vtx_offset + 0, 1] = v0

            vertices[vtx_offset + 1, 0] = x1
            vertices[vtx_offset + 1, 1] = y0
            uv_array[vtx_offset + 1, 0] = u0
            uv_array[vtx_offset + 1, 1] = v0

            vertices[vtx_offset + 2, 0] = x1
            vertices[vtx_offset + 2, 1] = y1
            uv_array[vtx_offset + 2, 0] = u0
            uv_array[vtx_offset + 2, 1] = v1

            vertices[vtx_offset + 3, 0] = x0
            vertices[vtx_offset + 3, 1] = y1
            uv_array[vtx_offset + 3, 0] = u1
            uv_array[vtx_offset + 3, 1] = v1

            indices[idx_offset + 0] = vtx_offset
            indices[idx_offset + 1] = vtx_offset + 1
            indices[idx_offset + 2] = vtx_offset + 2
            indices[idx_offset + 3] = vtx_offset + 2
            indices[idx_offset + 4] = vtx_offset + 3
            indices[idx_offset + 5] = vtx_offset

            vtx_offset += 4
            idx_offset += 6

    return vertices[:vtx_offset], uv_array[:vtx_offset], indices[:idx_offset]


class TilemapRenderer(Node2D):
    """Draws a `Tilemap`'s chunks. Must be a direct child of a `Tilemap`
    node (see `parental_requirement`) - created and attached automatically
    by `Tilemap.create_renderer`, not meant to be added directly."""

    def __init__(self, position: Vector, rotation: float, scale: Vector):
        """Args:
            position: Local position, relative to the parent `Tilemap`.
            rotation: Local rotation, relative to the parent `Tilemap`.
            scale: Local scale, relative to the parent `Tilemap`.
        """
        super().__init__(position, rotation, scale)
        self.parental_requirement = "Tilemap"
        self.parent: 'Tilemap'

    def on_initialize(self):
        """Creates the tilemap material, generating its shader source with
        this tilemap's chunk/tile sizes baked in via `TilemapInjector`.

        The material carries the same PBR property set a sprite's does, so
        each draw can point `albedo`/`normal` at whichever spritesheet it is
        drawing from. They're written straight into `properties` because
        `Material.parse_properties` only creates keys for properties present
        in the source `.fbmat` data, and `Material.__setattr__` only
        redirects to a key that already exists - the same reason
        `Sprite.__init__` assigns its texture that way.
        """
        self.material = get_service('graphics').create_material(
            {
                "filter": "nearest",
                "shader": {
                    "vert": "engine://shader/graphics/tilemap.fbvert",
                    "frag": "engine://shader/graphics/tilemap.fbfrag",
                },
            },
            TilemapInjector(self.parent.chunk_size, self.parent.tile_size),
        )
        self.material.properties['albedo'] = Color("#FFFFFFFF")
        self.material.properties['normal'] = Color("#00000000")

    def draw(self, camera):
        """Draws every visible layer of the parent tilemap, one draw call per
        (chunk, spritesheet) pair. A chunk's mesh is rebuilt from its raw
        tile data every call rather than cached.

        Layers are drawn in insertion order with alpha blending on and depth
        writes off (`BlendMode.TRANSPARENT`), so a transparent tile on one
        layer lets the layer below show through. Depth *writing* has to be
        off for that: every tile is coplanar, so with depth writes on the
        first layer drawn would win every overlapping pixel via GL_LESS and
        later layers would silently vanish. It also keeps tiles from
        occluding sprites, which is what a 2D background should do. The
        blend state is restored to OPAQUE afterwards, since this runs inside
        PBRPipeline's opaque G-buffer pass.
        """
        renderer = get_service('renderer')
        tilemap = self.parent
        mesh_class = renderer.get_mesh_class()

        shader = self.material.shader
        shader['proj'] = camera.proj_matrix
        shader['view'] = camera.view_matrix
        shader['model'] = self.parent.world_transform.model

        renderer.set_blend_mode(BlendMode.TRANSPARENT)
        try:
            for layer_name in tilemap.layers:
                layer = tilemap.layers[layer_name]
                if not layer.visible:
                    continue

                for chunk_pos in layer.chunks:
                    chunk = layer.chunks[chunk_pos]

                    for sheet_index, sheet in tilemap.iter_spritesheets():
                        cols, rows = sheet.size
                        vertices, uvs, indices = generate_chunk_mesh(
                            chunk.tiles, tilemap.tile_size, tilemap.chunk_size,
                            sheet_index, cols, rows,
                        )

                        if indices.shape[0] == 0:
                            continue

                        albedo = sheet.get_map('albedo')
                        if albedo is None:
                            continue

                        self.material.properties['albedo'] = albedo
                        normal = sheet.get_map('normal')
                        # A sheet with no normal map falls back to a zero
                        # colour rather than a flat-normal one: the lighting
                        # composite treats a zero-length normal as "no map
                        # here" and uses the surface's geometric normal
                        # instead (see graphics/pbr/shaders.py), which is
                        # also what a sprite with no normal map gets.
                        self.material.properties['normal'] = normal if normal is not None else Color("#00000000")

                        mesh = mesh_class(
                            attributes={
                                'vertices': (AttributeType.VEC2, vertices),
                                'uvs': (AttributeType.VEC2, uvs),
                            },
                            indices=indices,
                            usage=BufferUsage.DYNAMIC,
                        )

                        shader['chunk_pos'] = (chunk.position.x, chunk.position.y)
                        renderer.draw_mesh(mesh, self.material)
        finally:
            renderer.set_blend_mode(BlendMode.OPAQUE)


class TilemapInjector(Injector):
    """Bakes a tilemap's chunk/tile sizes as literal constants into the
    tilemap shader source, since the shader has no other way to know a
    given tilemap's fixed dimensions."""

    def __init__(self, chunk_size, tile_size):
        """Args:
            chunk_size: Width/height of a chunk, in tiles.
            tile_size: Size of a tile, in world units.
        """
        self.chunk_size = chunk_size
        self.tile_size = tile_size

    def cache_key(self) -> str:
        """The two numbers this injector bakes into the source - which is
        everything it varies on (see source_inject below)."""
        return f"tilemap:{self.chunk_size}:{self.tile_size}"

    def source_inject(self, source):
        """Replaces the `_ENGINE_*` placeholder tokens in `source` with this
        tilemap's actual chunk/tile sizes.

        `_ENGINE_MAX_SPRITESHEETS` is no longer emitted: it existed for a
        shader that would index an array of spritesheet samplers by a
        per-vertex `spritesheet_id`, but the shader source never referenced
        it, and the tilemap now issues one draw per spritesheet with that
        sheet's texture bound - so there is no sampler array and no cap on
        how many spritesheets a tilemap can use.
        """
        new = source
        new = new.replace('_ENGINE_CHUNK_SIZE', str(self.chunk_size))
        new = new.replace('_ENGINE_CHUNK_WORLD_SIZE', str(self.chunk_size * self.tile_size))
        new = new.replace('_ENGINE_TILE_SIZE', str(self.tile_size))
        return new
