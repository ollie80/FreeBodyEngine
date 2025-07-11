from FreeBodyEngine.graphics.image import Image
from FreeBodyEngine.graphics.texture import Texture
from typing import TYPE_CHECKING
import numpy as np

if TYPE_CHECKING:
    from FreeBodyEngine.graphics.gl33.renderer import GLRenderer


class GLImage(Image):
    def __init__(self, data: str, renderer: 'GLRenderer'):
        super().__init__(data, renderer)
        
    def get_size(self):
        return self.texture.uv_rect

    def get_data(self):
        return self.texture.get_image_data()
    
