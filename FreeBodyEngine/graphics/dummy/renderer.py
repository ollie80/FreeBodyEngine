from FreeBodyEngine.graphics.renderer import Renderer


class DummyRenderer(Renderer):
    """A no-op Renderer backend - every drawing/resource method below is a stub that does nothing."""
    def __init__(self, main):
        """See Renderer.__init__()."""
        super().__init__(main)

    def load_image(self, data):
        """No-op stub - see Renderer.load_image()."""
        pass

    def load_material(self, data):
        """No-op stub - see Renderer.load_material()."""
        pass

    def load_shader(self, vertex, fragment, injector = None):
        """No-op stub - see Renderer.load_shader()."""
        pass

    def create_framebuffer(self, width: int, height: int, attachments):
        """No-op stub - see Renderer.create_framebuffer()."""
        pass

    def clear(self, color):
        """No-op stub - see Renderer.clear()."""
        pass

    def destroy(self):
        """No-op stub - see Renderer.destroy()."""
        pass

    def resize(self):
        """No-op stub - see Renderer.resize()."""
        pass

    def draw_line(self, start: tuple[float, float], end: tuple[float, float], width: int, color):
        """No-op stub - see Renderer.draw_line()."""
        pass

    def draw_mesh(self, mesh, material, transform, camera):
        """No-op stub - see Renderer.draw_mesh()."""
        pass

    def draw_mesh_instanced(self, mesh, material, model_matrices, camera):
        """No-op stub - see Renderer.draw_mesh_instanced()."""
        pass

    def set_blend_mode(self, mode):
        """No-op stub - see Renderer.set_blend_mode()."""
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
