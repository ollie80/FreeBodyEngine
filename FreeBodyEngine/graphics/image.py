from typing import TYPE_CHECKING
import PIL
import PIL.Image
import io
from FreeBodyEngine.utils import abstractmethod

if TYPE_CHECKING:
    from FreeBodyEngine.core.main import Main
    from FreeBodyEngine.graphics.renderer import Renderer
    from FreeBodyEngine.graphics.texture import Texture

class Image:
    def __init__(self, texture: 'Texture'):        
        self.texture = texture
#        self._image: PIL.Image.Image = PIL.Image.open(io.BytesIO(texture.get_image_data())).transpose(PIL.Image.Transpose.FLIP_TOP_BOTTOM)

    @abstractmethod
    def get_data(self):
        pass
