from FreeBodyEngine.graphics.gl33.shader import GLShader
from FreeBodyEngine.graphics.material import Material
from FreeBodyEngine.graphics.fbusl import compile
from OpenGL.GL import *

class GLMaterial(Material):
    def __init__(self, data):
        super().__init__(data)
        self.shader: GLShader
        
    def change_shader(self, shader: GLShader):
        """

        """
        pass
        
        