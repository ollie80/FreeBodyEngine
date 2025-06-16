from typing import TYPE_CHECKING
import PIL
import PIL.Image
import io
from FreeBodyEngine.utils import abstractmethod

if TYPE_CHECKING:
    from FreeBodyEngine.core.main import Main
    from FreeBodyEngine.graphics.renderer import Renderer

class Image:
    def __init__(self, data: str):
        self._image: PIL.Image.Image = PIL.Image.open(io.BytesIO(data))

    @abstractmethod
    def get_data(self):
        pass          

    @abstractmethod    
    def get_data(self):
        pass