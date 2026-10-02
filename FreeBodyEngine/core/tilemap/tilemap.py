from FreeBodyEngine.core.tilemap.spritesheet import TilemapSpritesheet, StaticSpritesheet
from FreeBodyEngine.core.tilemap.renderer import TilemapRenderer
from FreeBodyEngine.core.tilemap import _NUM_TILE_VALS, _MAX_TILE_VAL
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

        self._spritesheet_types: dict[str, type[TilemapSpritesheet]] = {
            'static': StaticSpritesheet,
            StaticSpritesheet.get_name(): StaticSpritesheet,
        }
        self.spritesheets: dict[str, TilemapSpritesheet] = {}
        # A chunk stores a tile's spritesheet as a one-byte index, not a
        # name, so a name <-> index registry is what makes the two halves of
        # the API meet. There was none: add_spritesheet keyed spritesheets by
        # name only, while Chunk.set_tile took an int, leaving a caller to
        # invent indices by hand. Index 0 is reserved for "no spritesheet",
        # which is also what an empty tile stores.
        self._spritesheet_order: list[str] = []


    def add_layer(self, name, chunks: dict[Vector, Chunk] = None, visible = True):
        """Creates a new, empty (unless `chunks` is given) layer under `name`.

        `chunks` defaults to None rather than `{}`: a mutable default is
        evaluated once at definition time, so every layer added without an
        explicit dict used to share one single chunk dict - a tile placed on
        any layer appeared on all of them. Invisible on a one-layer tilemap
        (the only case anything had exercised), wrong the moment a second
        layer existed.

        `visible` defaults to True because `TilemapRenderer.draw` ignored the
        flag entirely until it was honoured, so every layer drew regardless -
        defaulting to False while honouring it would silently stop existing
        tilemaps from rendering at all."""
        self.layers[name] = Layer(name, {} if chunks is None else chunks, visible)

    def add_spritesheet_type(self, type: type['TilemapSpritesheet']):
        """Registers a `TilemapSpritesheet` subclass so it can be created by
        `create_spritesheet`/`add_spritesheet` via its `get_name()`."""
        self._spritesheet_types[type.get_name()] = type

    def create_spritesheet(self, data: dict):
        """Creates a spritesheet from `data` and adds it to the tilemap's
        spritesheets, taking its type from `data["type"]`.

        This used to call `add_spritesheet(name, type(data))` - passing the
        spritesheet's *name* where that method expects a type, and
        constructing the spritesheet with one argument where it takes two.
        """
        spritesheet_type = data.get('type', StaticSpritesheet.get_name())
        if data.get('name') is None:
            error('Cannot add spritesheet because no name was set.')
            return

        return self.add_spritesheet(spritesheet_type, data)

    def add_spritesheet(self, spritesheet_type: str, data: dict) -> int:
        """Instantiates a registered spritesheet type from `data`, stores it
        under `data["name"]`, and returns the index tiles refer to it by.

        No longer requires `create_renderer` to have been called first: a
        spritesheet wraps a `.fbsheet` loaded through the file system, so it
        has no need of the tilemap's own renderer at construction time.
        """
        if spritesheet_type not in self._spritesheet_types:
            warning(f"Spritesheet type '{spritesheet_type}' is not defined")
            return 0

        name = data.get('name', None)
        if name is None:
            warning('Could not add spritesheet, a name was not defined in the provided data.')
            return 0

        spritesheet = self._spritesheet_types[spritesheet_type](data, self)
        self.spritesheets[name] = spritesheet

        if name not in self._spritesheet_order:
            self._spritesheet_order.append(name)

        index = self.get_spritesheet_index(name)
        if spritesheet.cell_count > _MAX_TILE_VAL:
            warning(
                f'Spritesheet "{name}" has {spritesheet.cell_count} cells, but a tile '
                f'stores its cell in one byte - only the first {_MAX_TILE_VAL} are addressable.'
            )
        if index > _MAX_TILE_VAL:
            warning(
                f'Tilemap has more than {_MAX_TILE_VAL} spritesheets; "{name}" is not addressable, '
                'since a tile stores its spritesheet in one byte.'
            )
        return index

    def get_spritesheet_index(self, name: str) -> int:
        """The index tiles store to refer to the spritesheet called `name`, or
        0 (meaning "no spritesheet") if no such spritesheet is registered.

        Indices are 1-based so that 0 can mean "none", matching an empty
        tile's stored bytes.
        """
        if name not in self._spritesheet_order:
            return 0
        return self._spritesheet_order.index(name) + 1

    def get_spritesheet_by_index(self, index: int) -> 'TilemapSpritesheet':
        """The spritesheet an `index` stored in a tile refers to, or None."""
        if index < 1 or index > len(self._spritesheet_order):
            return None
        return self.spritesheets.get(self._spritesheet_order[index - 1])

    def iter_spritesheets(self):
        """Every registered spritesheet as `(index, spritesheet)` pairs, in
        the order they were added."""
        return [(i + 1, self.spritesheets[name]) for i, name in enumerate(self._spritesheet_order)]

    def _resolve_spritesheet(self, spritesheet) -> int:
        """Normalizes a spritesheet given as either a registered name or an
        already-resolved index into an index."""
        if isinstance(spritesheet, str):
            index = self.get_spritesheet_index(spritesheet)
            if index == 0:
                warning(f'No spritesheet named "{spritesheet}" is registered on this tilemap.')
            return index
        return int(spritesheet)

    def create_renderer(self):
        """Creates and attaches this tilemap's `TilemapRenderer`.

        Spritesheets may be added before or after this - they no longer need
        the renderer to exist (see `add_spritesheet`) - but nothing is drawn
        until it does.
        """
        self.renderer = TilemapRenderer(Vector(), 0, Vector(1, 1))
        self.add(self.renderer)

    def set_tile(self, position: Vector, cell, spritesheet, layer: str):
        """Sets the tile at tilemap `position` on `layer`, resolving it to the
        owning chunk first.

        Args:
            position: Position in tilemap coordinates (see `tilemap_pos`).
            cell: Which cell of the spritesheet's grid to draw - either a flat
                cell index or a `[col, row]` pair, the same way a `.fbanim`
                frame's `pos` addresses one.
            spritesheet: The spritesheet's registered name, or its index.
            layer: Which layer to place the tile on.
        """
        chunk = self.get_chunk(self.chunk_pos(position), layer)
        if chunk is None:
            return

        sheet_index = self._resolve_spritesheet(spritesheet)
        sheet = self.get_spritesheet_by_index(sheet_index)
        cell_index = sheet.cell_index(cell) if sheet is not None else int(cell)

        # Stored offset by one so that 0 can mean "no tile" - see
        # renderer.generate_chunk_mesh.
        chunk.set_tile(self.tile_pos(position), cell_index + 1, sheet_index)

    def remove_tile(self, position: Vector, layer: str):
        """Clears the tile at tilemap `position` on `layer`."""
        chunk = self.get_chunk(self.chunk_pos(position), layer)
        if chunk is None:
            return
        chunk.remove_tile(self.tile_pos(position))

    def get_tile(self, position: Vector, layer: str) -> Tile:
        """Gets the tile at tilemap `position` on `layer`, resolving it to the
        owning chunk first.

        Returns None if no chunk covers `position`.
        """
        chunk = self.get_chunk(self.chunk_pos(position), layer)
        if chunk is None:
            return None
        # Chunk.get_tile addresses tiles local to the chunk, so the tilemap
        # position has to be reduced the same way set_tile already does it -
        # passing the raw tilemap position straight through read whatever
        # unrelated slot that index happened to land on.
        return chunk.get_tile(self.tile_pos(position))

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