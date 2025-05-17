from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from FreeBodyEngine.graphics.manager import GraphicsManager
    from FreeBodyEngine.graphics.material import Material
    from FreeBodyEngine.graphics.color import Color
    from FreeBodyEngine.graphics.image import Image
    from FreeBodyEngine.core.camera import Camera



from abc import ABC, abstractmethod

class Renderer:
    """
    The purpose of the renderer is to abstract rendering with different graphics APIs.
    The Renderer uses NDC (Normalised Device Coordinates) instead of pixel coordinates.

    :param manager: The graphics manager.
    :type manager: GraphicsManager
    """
    def __init__(self, manager: 'GraphicsManager'):
        self.manager = manager

    @abstractmethod
    def draw_line(self, start: tuple[float, float], end: tuple[float, float], width: int, color: 'Color'):
        """
        Draws a line between the first and second point.
        
        :param start: The first point (NDC).
        :type start: tuple[float, float]
        :param end: The second point (NDC).
        :type end: tuple[float, float]
        :param width: The thickness of the line (Pixels).
        :type width: int 
        """
        pass
    
    @abstractmethod
    def draw_image(self, image: 'Image', camera: 'Camera'):
        pass

    @abstractmethod
    def draw_circle(self, radius: float, position: tuple[float, float], color: 'Color'):
        """
        Draws a filled circle at the position.

        :param start: The center of the circle (NDC).
        :type start: tuple[float, float]
        :param radius: The radius of the 
        :type radius: float
        """
        pass

    


    
 
# ------- TODO ----------
# - Vulkan Renderer
# - DirectX Renderer
# - Metal Renderer
#   PS5 + Switch 2?