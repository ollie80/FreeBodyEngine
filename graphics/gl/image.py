from FreeBodyEngine.graphics.image import Image
from FreeBodyEngine.graphics.texture import Texture
from typing import TYPE_CHECKING
import numpy as np

if TYPE_CHECKING:
    from FreeBodyEngine.graphics.gl.renderer import GLRenderer


class GLImage(Image):
    def __init__(self, renderer: 'GLRenderer', data: str):
        self.renderer = renderer
        super().__init__(data)

        img_data = np.array(self._image.convert('RGBA'), dtype=np.uint8)
        width, height = self._image.size
        self.texture: Texture = self.renderer.texture_manager._create_texture(img_data, width, height)        
        
    def get_size(self):
        return self.texture.uv_rect

    def get_data(self):
        return self.texture.get_image_data()
    
