from FreeBodyEngine.graphics.image import Image
from OpenGL.GL import *

class GLImage(Image):
    def __init__(self, data: str):
        super().__init__(data)

        img_data = self._image.tobytes()
        width, height = self._image.size
        self.texture = glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, img_data)
    