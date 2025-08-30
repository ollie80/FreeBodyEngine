from FreeBodyEngine.graphics.texture import TextureStack
from FreeBodyEngine.utils import load_texture_stack
from FreeBodyEngine.utils import abstractmethod
from FreeBodyEngine.core.tilemap import Tilemap, Tile
import numpy as np

class TilemapSpritesheet:
    def __init__(self, paths: list[str]):
        self.texture: TextureStack = load_texture_stack(paths)

    @classmethod
    def _initialize_type(cls, tilemap: Tilemap):
        tilemap._spritesheet_types[cls.get_name()] = cls

    def _initialize(self, tilemap: Tilemap):
        tilemap.spritesheets[tilemap] = self

    @staticmethod
    def get_name():
        return "spritesheet"

    @abstractmethod
    def get_image_index(self, tile: Tile, neighbors: tuple[Tile, Tile, Tile, Tile, Tile, Tile, Tile, Tile]) -> int:
        """
        Standardized function to get the image_index for any given tile. Run every time a chunk is updated.
        
        :param tile: The tile that the image index is being gotten for.
        :type tile: Tile

        :param neighbors: The 8 neighbors of the given tile, ordered in the clockwise direction stating in the top left.
        :type neighbors: tuple[Tile, Tile, Tile, Tile, Tile, Tile, Tile, Tile]

        :rtype: int
        """
        pass

    @abstractmethod
    def update(self):
        pass

class StaticSpritesheet(TilemapSpritesheet):
    def __init__(self, paths: list[str]):
        super().__init__(paths)

    @staticmethod
    def get_name():
        return "static_spritesheet"
    
    def get_image_index(self, tile, neighbors):
        tile.image_id =
