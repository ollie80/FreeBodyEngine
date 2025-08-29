#                2 = image_id (1 byte), spritesheet_index (1 byte)  
_NUM_TILE_VALS = 2

from FreeBodyEngine.core.tilemap.tilemap import Tilemap, Layer
from FreeBodyEngine.core.tilemap.spritesheet import StaticSpritesheet, TilemapSpritesheet
from FreeBodyEngine.core.tilemap.chunk import Chunk
from FreeBodyEngine.core.tilemap.tile import Tile


__all__ = ["Tilemap", "Tile", "Chunk", "StaticSpritesheet", "TilemapSpritesheet", "Layer", "_NUM_TILE_VALS"]