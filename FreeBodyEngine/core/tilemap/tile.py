from FreeBodyEngine.math import Vector

class Tile:
    """A single tile, backing onto its owning `Chunk`'s underlying data array.

    A `Tile` is a lightweight view rather than the source of truth - it
    holds no state of its own beyond what it was constructed with, and every
    property setter writes straight through to `_chunk` so the change is
    reflected in the chunk's tile data immediately.
    """

    def __init__(self, position: Vector, image_id: Vector, spritesheet: str, chunk: 'Chunk'):
        """Args:
            position: The tile's position, local to `chunk`.
            image_id: The id of the image drawn for this tile.
            spritesheet: The name of the spritesheet `image_id` is looked up in.
            chunk: The chunk this tile belongs to; writes made through this
                `Tile` are applied to `chunk`.
        """
        self._position = position
        self._image_id = image_id
        self._spritesheet = spritesheet
        self._chunk = chunk
    @property
    def position(self) -> Vector:
        """The tile's position, local to its chunk."""
        return self._position

    @position.setter
    def position(self, new: Vector):
        """Moves the tile within its chunk, removing it from the old slot and
        re-writing it into the new one so the chunk's tile data stays consistent."""
        if new != self._position:
            self._chunk.remove_tile(self._position)
            self._position = new
            self._chunk.set_tile(self._position, self._image_id, self._spritesheet)

    @property
    def image_id(self) -> int:
        """The id of the image drawn for this tile."""
        return self.image_id

    @image_id.setter
    def image_id(self, new: int):
        """Sets the image drawn for this tile."""
        self._chunk.set_image_id(self._position, new)

    @property
    def spritesheet(self) -> str:
        """The name of the spritesheet `image_id` is looked up in."""
        return self._spritesheet

    @spritesheet.setter
    def spritesheet(self, new: str):
        """Sets the spritesheet `image_id` is looked up in."""
        self._chunk.set_spritesheet(self._position, new)

    def destroy(self):
        """Removes this tile from its chunk."""
        self._chunk.remove_tile(self._position)

    def __repr__(self):
        return f"Tile({self.position})"
