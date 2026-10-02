#                2 = image_id (1 byte), spritesheet_index (1 byte)  
_NUM_TILE_VALS = 2

# A tile's two values are one byte each, so the largest cell index or
# spritesheet index a tile can store is 255 (0 being reserved for "empty"/
# "no spritesheet").
_MAX_TILE_VAL = 255

from FreeBodyEngine.core.tilemap.tilemap import Tilemap, Layer
from FreeBodyEngine.core.tilemap.spritesheet import StaticSpritesheet, TilemapSpritesheet, AutoSpritesheet, UpdateMode
from FreeBodyEngine.core.tilemap.rules import TileRule, parse_rules
from FreeBodyEngine.core.tilemap.collision import TilemapCollider2D, merge_solid_rects
from FreeBodyEngine.core.tilemap.chunk import Chunk
from FreeBodyEngine.core.tilemap.tile import Tile


__all__ = ["Tilemap", "Tile", "Chunk", "StaticSpritesheet", "TilemapSpritesheet", "Layer", "_NUM_TILE_VALS", "_MAX_TILE_VAL", "AutoSpritesheet", "UpdateMode", "TileRule", "parse_rules", "TilemapCollider2D", "merge_solid_rects"]