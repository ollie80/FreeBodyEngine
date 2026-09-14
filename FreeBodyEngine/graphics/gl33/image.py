from FreeBodyEngine.graphics.image import Image
from FreeBodyEngine.graphics.texture import Texture
from typing import TYPE_CHECKING
import numpy as np

if TYPE_CHECKING:
    from FreeBodyEngine.graphics.gl33.renderer import GLRenderer


class GLImage(Image):
    """The GL 3.3 implementation of Image: a thin wrapper that reads its
    pixel data and rect straight off the underlying GLTextureManager-owned
    Texture rather than holding any separate GPU state of its own."""
    def __init__(self, data: str):
        """Forwards `data` (the Texture this image wraps) to Image.__init__,
        which stores it as `self.texture`."""
        super().__init__(data)

    def get_size(self):
        """Returns the wrapped texture's UV rect `(x, y, w, h)`."""
        return self.texture.uv_rect

    def get_data(self):
        """Returns the wrapped texture's raw pixel data (see
        Texture.get_image_data)."""
        return self.texture.get_image_data()
