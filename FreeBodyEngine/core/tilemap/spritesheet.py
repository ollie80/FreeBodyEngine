from FreeBodyEngine.graphics.texture import TextureStack
from FreeBodyEngine.utils import load_texture_stack
from FreeBodyEngine.utils import abstractmethod
import numpy as np

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from FreeBodyEngine.core.tilemap import Tilemap, Tile
from enum import Enum, auto

class UpdateMode:
    """Determines when the 'get_image_index' function will be called. Frame means every its called every frame. Chunk means its called on every chunk update. Once is only called once per tile. Never means it will never be called, and the image id will be used instead."""
    frame = auto()
    chunk = auto()
    once = auto()
    never = auto()


class TilemapSpritesheet:
    def __init__(self, paths: list[str], update_mode: UpdateMode = UpdateMode.never):
        self.texture: TextureStack = load_texture_stack(paths)
        self.update_mode = update_mode

    @classmethod
    def _initialize_type(cls, tilemap: 'Tilemap'):
        tilemap._spritesheet_types[cls.get_name()] = cls

    def _initialize(self, tilemap: 'Tilemap'):
        
        tilemap.spritesheets[tilemap] = self

    @staticmethod
    def get_name():
        return "spritesheet"

    @abstractmethod
    def get_image_index(self, tile: 'Tile', neighbors: tuple['Tile', 'Tile', 'Tile', 'Tile', 'Tile', 'Tile', 'Tile', 'Tile']) -> int:
        """
        Standardized function to get the image_index for any given tile. The frequency this is run is determined by the tilemap's 'update_mode'.
        
        :param tile: The tile that the image index is being gotten for.
        :type tile: Tile

        :param neighbors: The 8 neighbors of the given tile, ordered in the clockwise direction stating in the top left. Includes nieghbors in nearby chunks.
        :type neighbors: tuple[Tile, Tile, Tile, Tile, Tile, Tile, Tile, Tile]

        :rtype: int
        """
        pass

    @abstractmethod
    def update(self):
        """
        Called when the tilemap node is updated.
        """
        pass

class StaticSpritesheet(TilemapSpritesheet):
    def __init__(self, paths: list[str]):
        super().__init__(paths, UpdateMode.once)

    @staticmethod
    def get_name():
        return "static_spritesheet"
    
    def get_image_index(self, tile, neighbors):
        return tile.image_id