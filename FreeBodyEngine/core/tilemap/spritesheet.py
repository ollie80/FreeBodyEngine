from FreeBodyEngine.utils import abstractmethod
import numpy as np

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from FreeBodyEngine.core.tilemap.renderer import TilemapRenderer
    from FreeBodyEngine.core.tilemap import Tilemap, Tile

from enum import Enum, auto

class UpdateMode:
    """Determines when the 'get_image_index' function will be called. Frame means every its called every frame. Chunk means its called on every chunk update. Once is only called once per tile. Never means it will never be called, and the image id will be used instead."""
    FRAME = auto()
    CHUNK = auto()
    ONCE = auto()
    NEVER = auto()


class TilemapSpritesheet:
    """Base class for a tilemap's image-lookup source: maps a tile's
    `image_id` (and its neighbors, for auto-tiling) to an index into the
    renderer's uploaded texture stack. Subclasses implement `get_image_index`,
    `_extract_paths`, and `update` for a particular lookup strategy (static,
    auto-tiled, animated)."""

    def __init__(self, data: dict[str, any], renderer: 'TilemapRenderer', update_mode: UpdateMode = UpdateMode.NEVER):
        """Args:
            data: The spritesheet definition data (as passed to `Tilemap.create_spritesheet`).
            renderer: The tilemap's renderer; its texture stack is extended
                with the paths this spritesheet extracts from `data`.
            update_mode: How often `get_image_index` is re-run for a tile - see `UpdateMode`.
        """
        self.data = data
        self.path_map = renderer._add_textures(self._extract_paths(data))
        self.update_mode = update_mode

    @classmethod
    def _initialize_type(cls, tilemap: 'Tilemap'):
       tilemap._spritesheet_types[cls.get_name()] = cls

    def _initialize(self, tilemap: 'Tilemap'):

        tilemap.spritesheets[tilemap] = self

    @staticmethod
    def get_name():
        """The type name spritesheet data uses to select this class (see `Tilemap.add_spritesheet_type`)."""
        return "spritesheet"

    @abstractmethod
    def get_image_index(self, tile: 'Tile', neighbors: tuple['Tile', 'Tile', 'Tile', 'Tile', 'Tile', 'Tile', 'Tile', 'Tile']) -> int:
        """
        Standardized function to get the image_index for any given tile. The frequency this is run is determined by the tilemap's 'update_mode'.
        
        :param tile: The tile that the image index is being gotten for.
        :type tile: Tile

        :param neighbors: The 8 neighbors of the given tile, ordered in the clockwise direction stating in the top left. Includes neighbors in nearby chunks.
        :type neighbors: tuple[Tile, Tile, Tile, Tile, Tile, Tile, Tile, Tile]

        :rtype: int
        """
        pass

    @abstractmethod    
    def _extract_paths(self, data: dict[str, any]):
        """
        Used to extract paths from the data provided to the spritesheet.
        """
        pass

    @abstractmethod
    def update(self):
        """
        Called when the tilemap node is updated.
        """
        pass

class StaticSpritesheet(TilemapSpritesheet):
    """A spritesheet where each tile's image is fixed by its `image_id` alone
    (no auto-tiling/animation), so its image index only needs computing once
    per tile (`UpdateMode.ONCE`)."""

    def __init__(self, data: dict[str, any], renderer: "TilemapRenderer"):
        """Args:
            data: Spritesheet definition; `data["paths"]` is a list of
                `(key, path)` pairs, keyed by `image_id`.
            renderer: The tilemap's renderer, whose texture stack the paths are added to.
        """
        self.data = data

        super().__init__(self.data, renderer, UpdateMode.ONCE)

    def _extract_paths(self, data: dict[str, any]):
        path_data: list[tuple[str, str]] = data['paths']
        paths = []

        for i in range(len(path_data)):
            paths.append(path_data[i][1])
        
        return paths

    def get_image_id(self, key):
        """Looks up the `image_id` registered under `key` in `data["paths"]`,
        or `-1` if `key` isn't found."""
        for i in self.data:
            if self.data[i][0] == key:
                return i

        return -1

    @staticmethod
    def get_name():
        """The type name spritesheet data uses to select this class (see `Tilemap.add_spritesheet_type`)."""
        return "static_spritesheet"

    def get_image_index(self, tile, neighbors):
        """Looks up `tile`'s image index by its `image_id` alone; `neighbors` is unused."""
        return self.path_map[self.data[tile.image_id][1]]

class AutoSpritesheet(TilemapSpritesheet):
    """A spritesheet whose image index depends on a tile's neighbors (e.g.
    auto-tiling edges/corners), so it's recomputed on every chunk update
    (`UpdateMode.CHUNK`) rather than once."""

    def __init__(self, data: dict, renderer: "TilemapRenderer"):
        """Args:
            data: Spritesheet definition data.
            renderer: The tilemap's renderer, whose texture stack the paths are added to.
        """
        super().__init__(data, renderer, UpdateMode.CHUNK)

class AnimatedSpritesheet(TilemapSpritesheet):
    """A spritesheet whose image index changes every frame (e.g. a looping
    animation), so it's recomputed every frame (`UpdateMode.FRAME`)."""

    def __init__(self, data: dict, renderer: "TilemapRenderer"):
        """Args:
            data: Spritesheet definition data.
            renderer: The tilemap's renderer, whose texture stack the paths are added to.
        """
        super().__init__(data, renderer, UpdateMode.FRAME)

    @staticmethod
    def get_name():
        """The type name spritesheet data uses to select this class (see `Tilemap.add_spritesheet_type`)."""
        return 'animated_spritesheet'

    def get_image_index(self, tile, neighbors):
        """Gets `tile`'s current animation frame's image index."""
        super().get_image_index(tile, neighbors)
