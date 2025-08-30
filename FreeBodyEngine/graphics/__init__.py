from FreeBodyEngine.utils import get_platform
from FreeBodyEngine.graphics import color
from FreeBodyEngine.graphics import image
from FreeBodyEngine.graphics import renderer
from FreeBodyEngine.graphics import material
from FreeBodyEngine.graphics import mesh
from FreeBodyEngine.graphics import sprite
from FreeBodyEngine.graphics import gl33
from FreeBodyEngine.graphics import pbr
from FreeBodyEngine.graphics import pipeline
from FreeBodyEngine.graphics import model

import sys

def get_renderer() -> type[renderer.Renderer]:
    """Get the correct renderer for the platform."""
    platform = get_platform()

    if platform == "win32":
        #DX12
        pass
    elif platform == 'linux':
        #gl44
        pass
    elif platform == 'darwin':
        #metal
        pass

    # gl33 is made to support pretty much every device, it may actually run on a smart fridge (eat shit pirate)
    from FreeBodyEngine.graphics.gl33.renderer import GL33Renderer
    return GL33Renderer
    


__all__ = ["color", "mesh", "material", "renderer", "pipeline", "image", 'pbr', "gl33", 'sprite', 'model']
