from FreeBodyEngine.graphics.image import Image


class WebGL2Image(Image):
    """The WebGL2 implementation of Image - a thin wrapper reading its
    pixel data/rect straight off the underlying WebGL2TextureManager-owned
    Texture, same as GLImage."""
    def __init__(self, data):
        super().__init__(data)

    def get_size(self):
        """Returns the wrapped texture's UV rect `(x, y, w, h)`."""
        return self.texture.uv_rect

    def get_data(self):
        """Returns the wrapped texture's raw pixel data."""
        return self.texture.get_image_data()
