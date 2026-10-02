from FreeBodyEngine.math import Vector

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from FreeBodyEngine.core.tilemap import Chunk


class Tile:
    """A single tile, backing onto its owning `Chunk`'s underlying data array.

    A `Tile` is a lightweight view rather than the source of truth - it
    holds no state of its own beyond what it was constructed with, and every
    property setter writes straight through to `_chunk` so the change is
    reflected in the chunk's tile data immediately.
    """

    def __init__(self, position: Vector, image_id: int, spritesheet_index: int, chunk: 'Chunk'):
        """Args:
            position: The tile's position, local to `chunk`.
            image_id: The id of the image drawn for this tile, as stored in
                the chunk - 0 means "no tile here", and any other value is
                the tile's cell index within its spritesheet, plus one (see
                `Chunk.set_tile`).
            spritesheet_index: The index of the spritesheet `image_id` is
                looked up in - an int, not a name, because that is what a
                chunk's two-bytes-per-tile data array actually stores (see
                `Tilemap.get_spritesheet_index` for the name mapping). 0
                means "no spritesheet", which is also an empty tile.
            chunk: The chunk this tile belongs to; writes made through this
                `Tile` are applied to `chunk`.
        """
        self._position = position
        self._image_id = image_id
        self._spritesheet_index = spritesheet_index
        self._chunk = chunk

    @property
    def empty(self) -> bool:
        """Whether this tile slot holds no tile at all."""
        return self._image_id == 0 or self._spritesheet_index == 0

    @property
    def position(self) -> Vector:
        """The tile's position, local to its chunk."""
        return self._position

    @property
    def tilemap_position(self) -> Vector:
        """The tile's position in tilemap coordinates, i.e. its chunk's
        position scaled up plus its own position within that chunk.

        Auto-tiling rules need this: a rule that picks between several cells
        does so by hashing the tile's position, which has to be unique across
        the whole tilemap rather than repeating once per chunk."""
        chunk = self._chunk
        size = chunk.size
        return Vector(chunk.position.x * size + self._position.x,
                      chunk.position.y * size + self._position.y)

    @position.setter
    def position(self, new: Vector):
        """Moves the tile within its chunk, removing it from the old slot and
        re-writing it into the new one so the chunk's tile data stays consistent."""
        if new != self._position:
            self._chunk.remove_tile(self._position)
            self._position = new
            self._chunk._write_tile(self._position, self._image_id, self._spritesheet_index)

    @property
    def image_id(self) -> int:
        """The id of the image drawn for this tile."""
        return self._image_id

    @image_id.setter
    def image_id(self, new: int):
        """Sets the image drawn for this tile."""
        self._image_id = new
        self._chunk._write_tile(self._position, new, self._spritesheet_index)

    @property
    def spritesheet_index(self) -> int:
        """The index of the spritesheet `image_id` is looked up in."""
        return self._spritesheet_index

    @spritesheet_index.setter
    def spritesheet_index(self, new: int):
        """Sets the spritesheet `image_id` is looked up in."""
        self._spritesheet_index = new
        self._chunk._write_tile(self._position, self._image_id, new)

    def destroy(self):
        """Removes this tile from its chunk."""
        self._chunk.remove_tile(self._position)

    def __repr__(self):
        return f"Tile({self.position}, image_id={self._image_id}, spritesheet_index={self._spritesheet_index})"
