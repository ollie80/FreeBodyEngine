from FreeBodyEngine.graphics import color
from FreeBodyEngine.graphics import image
from FreeBodyEngine.graphics import renderer
from FreeBodyEngine.graphics import material
from FreeBodyEngine.graphics import mesh
from FreeBodyEngine.graphics import sprite
from FreeBodyEngine.graphics import gl33
from FreeBodyEngine.graphics import fbusl
from FreeBodyEngine.graphics import pbr
from FreeBodyEngine.graphics import pipeline

import sys

def get_renderer() -> type[renderer.Renderer]:
    """Get the correct renderer for the platform."""
    platform = sys.platform
    if platform == 'win32':
        from FreeBodyEngine.graphics.gl33.renderer import GL33Renderer
        return GL33Renderer
    


__all__ = ["color", "mesh", "material", "renderer", "pipeline", "image", 'pbr', "gl33", 'sprite', 'fbusl']
