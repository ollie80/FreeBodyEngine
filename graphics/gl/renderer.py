from FreeBodyEngine.graphics.renderer import Renderer
from FreeBodyEngine.graphics.manager import GraphicsManager


class GLRenderer(Renderer):
    """
    The OpenGL renderer. Uses OpenGL version 330 Core.
    """
    def __init__(self, manager: GraphicsManager):
        super().__init__(manager)

 
