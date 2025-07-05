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
    def __init__(self, data: str, renderer: 'Renderer'):
        self.renderer = renderer

        self._image: PIL.Image.Image = PIL.Image.open(io.BytesIO(data)).transpose(PIL.Image.Transpose.FLIP_TOP_BOTTOM)
        self.texture: Texture = self.renderer.texture_manager._create_texture(self._image)        

    @abstractmethod
    def get_data(self):
        pass          

    @abstractmethod    
    def get_data(self):
        pass