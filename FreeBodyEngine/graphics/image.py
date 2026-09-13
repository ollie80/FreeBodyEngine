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
    """Backend-agnostic wrapper around a Texture that exposes its pixel data
    as a plain image, rather than as something sampled by a shader."""
    def __init__(self, texture: 'Texture'):
        """Stores the `texture` this Image wraps."""
        self.texture = texture
#        self._image: PIL.Image.Image = PIL.Image.open(io.BytesIO(texture.get_image_data())).transpose(PIL.Image.Transpose.FLIP_TOP_BOTTOM)

    @abstractmethod
    def get_data(self):
        """Returns this image's raw pixel data."""
        pass
