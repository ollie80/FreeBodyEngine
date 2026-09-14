from FreeBodyEngine.graphics.image import Image
from FreeBodyEngine.graphics.texture import Texture
from typing import TYPE_CHECKING
import numpy as np

if TYPE_CHECKING:
    from FreeBodyEngine.graphics.gl44.renderer import GL44Renderer


class GL44Image(Image):
    """The GL 4.4 implementation of Image - identical to GLImage
    (graphics/gl33/image.py), since exposing a Texture's pixel data doesn't
    involve anything backend-specific beyond the Texture/TextureManager
    machinery both backends already share."""
    def __init__(self, data: str):
        """Wraps the given texture-backed `data` via the base Image
        constructor."""
        super().__init__(data)

    def get_size(self):
        """Returns this image's UV rect (the sub-region of its backing
        texture/atlas this image occupies), not literal pixel dimensions."""
        return self.texture.uv_rect

    def get_data(self):
        """Returns this image's raw pixel data, read back from its backing
        Texture."""
        return self.texture.get_image_data()
