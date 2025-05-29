from typing import TYPE_CHECKING
from FreeBodyEngine.utils import abstractmethod

if TYPE_CHECKING:
    from FreeBodyEngine.core.main import Main
    from FreeBodyEngine.graphics.material import Material
    from FreeBodyEngine.graphics.color import Color
    from FreeBodyEngine.graphics.image import Image
    from FreeBodyEngine.graphics.mesh import Mesh
    from FreeBodyEngine.core.camera import Camera



class Renderer:
    """
    The purpose of the renderer is to abstract rendering with different graphics APIs.
    The Renderer uses NDC (Normalised Device Coordinates) instead of pixel coordinates.

    :param main: The main object.
    :type main: Main
    """
    def __init__(self, main: 'Main'):
        self.main = main

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
    def clear(self):
        pass 

    @abstractmethod
    def destroy(self):
        pass

    @abstractmethod
    def draw_image(self, image: 'Image', material: 'Material', camera: 'Camera'):
        pass
        

    @abstractmethod
    def draw_mesh(self, image: 'Mesh', material: 'Material', camera: 'Camera'):
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