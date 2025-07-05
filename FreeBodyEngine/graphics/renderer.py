from typing import TYPE_CHECKING
from FreeBodyEngine.utils import abstractmethod
from FreeBodyEngine.graphics.fbusl.injector import Injector 

from FreeBodyEngine.graphics.image import Image
from FreeBodyEngine.graphics.mesh import Mesh
from FreeBodyEngine.graphics.framebuffer import AttachmentFormat, AttachmentType, Framebuffer
from FreeBodyEngine.graphics.texture import TextureManager


if TYPE_CHECKING:
    from FreeBodyEngine.core.main import Main
    from FreeBodyEngine.graphics.material import Material
    from FreeBodyEngine.graphics.color import Color
    from FreeBodyEngine.core.camera import Camera2D
    from FreeBodyEngine.math import Vector, Transform


class Renderer:
    """
    Renders graphics objects to the window's framebuffer. 
    :param main: The main object.
    :type main: Main
    """
    def __init__(self, main: 'Main'):
        self.main = main
        self.mesh_class = Mesh
        self.image_class = Image
        self.texture_manager = TextureManager()

    @abstractmethod
    def load_image(self, data):
        pass

    @abstractmethod
    def load_material(self, data):
        pass

    @abstractmethod
    def load_shader(self, vertex, fragment, injector: Injector = Injector):
        pass
    
    @abstractmethod
    def create_framebuffer(self, width: int, height: int, attachments: dict[str, tuple[AttachmentFormat, AttachmentType]]) -> Framebuffer:
        pass

    @abstractmethod
    def clear(self, color: 'Color'):
        pass 

    @abstractmethod
    def destroy(self):
        pass

    @abstractmethod
    def resize(self):
        pass

    @abstractmethod
    def draw_line(self, start: tuple[float, float], end: tuple[float, float], width: int, color: 'Color'):
        """
        Draws a line between the first and second point.
        
        :param start: The first point (NDC).
        :type start: tuple[float, float]
        :param end: The second point (NDC).
        :type end: tuple[float, float]
        :param width: The thickness of the line (NDC).
        :type width: int 
        """
        pass

    @abstractmethod
    def draw_mesh(self, mesh: 'Mesh', material: 'Material', transform: 'Transform', camera: 'Camera2D'):
        pass

    @abstractmethod
    def draw_circle(self, radius: float, position: tuple[float, float], color: 'Color'):
        """
        Draws a filled circle at the position.

        :param start: The center of the circle (NDC).
        :type start: tuple[float, float]
        :param radius: The radius of the circle (NDC).
        :type radius: float
        """
        pass