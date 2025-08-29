from FreeBodyEngine.math import Vector

class Tile:
    def __init__(self, position: Vector, image_id: Vector, spritesheet: str, chunk: 'Chunk'):
        self._position = position
        self._image_id = image_id
        self._spritesheet = spritesheet
        self._chunk = chunk
    @property
    def position(self) -> Vector:
        return self._position
    
    @position.setter
    def position(self, new: Vector):
        if new != self._position:
            self._chunk.remove_tile(self._position)
            self._position = new
            self._chunk.set_tile(self._position, self._image_id, self._spritesheet)

    @property
    def image_id(self) -> int:
        return self.image_id

    @image_id.setter
    def image_id(self, new: int):
        self._chunk.set_image_id(self._position, new)

    @property
    def spritesheet(self) -> str:
        return self._spritesheet

    @spritesheet.setter
    def spritesheet(self, new: str):
        self._chunk.set_spritesheet(self._position, new)

    def destroy(self):
        self._chunk.remove_tile(self._position)

    def __repr__(self):
        return f"Tile({self.position})"
