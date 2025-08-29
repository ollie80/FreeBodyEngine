from FreeBodyEngine.graphics.texture import Texture
from FreeBodyEngine.utils import abstractmethod
import numpy as np

class TilemapSpritesheet:
    def __init__(self, data, name: str, texture: 'Texture'):
        self.name = name
        self.texture = texture

    @abstractmethod
    def update(self):
        pass
    
class StaticSpritesheet:
    def __init__(self, data):
        self.data = data
        self.map: dict[str, tuple[int, int, int, int]] = self.data.get('map', {})

    def get_data(self):
        return np.array()

    def get_image_id(self, name: str):
        return self.map[name]

    def update(self):
        pass
