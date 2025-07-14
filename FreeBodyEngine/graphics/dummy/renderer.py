from FreeBodyEngine.graphics.renderer import Renderer


class DummyRenderer(Renderer):
    def __init__(self, main):
        super().__init__(main)

    def load_image(self, data):
        pass

    def load_material(self, data):
        pass

    def load_shader(self, vertex, fragment, injector = None):
        pass
    
    def create_framebuffer(self, width: int, height: int, attachments):
        pass

    def clear(self, color):
        pass 

    def destroy(self):
        pass

    def resize(self):
        pass

    def draw_line(self, start: tuple[float, float], end: tuple[float, float], width: int, color):
        pass

    def draw_mesh(self, mesh, material, transform, camera):
        pass

    def draw_circle(self, radius: float, position: tuple[float, float], color):
        """
        Draws a filled circle at the position.

        :param start: The center of the circle (NDC).
        :type start: tuple[float, float]
        :param radius: The radius of the circle (NDC).
        :type radius: float
        """
        pass
