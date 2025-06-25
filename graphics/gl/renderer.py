from FreeBodyEngine.graphics.renderer import Renderer
from FreeBodyEngine.graphics.gl import context
from FreeBodyEngine.graphics.color import Color
from FreeBodyEngine.graphics.gl.texture import GLTextureManager
from FreeBodyEngine.graphics.gl import GLImage
from FreeBodyEngine.graphics.sprite import Sprite
from FreeBodyEngine.graphics.gl.shader import GLShader
from FreeBodyEngine.graphics.gl.material import GLMaterial
from FreeBodyEngine.graphics.fbusl.injector import Injector 

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from FreeBodyEngine.core.main import Main
    from FreeBodyEngine.core.camera import Camera
    from FreeBodyEngine.graphics.material import Material
    from FreeBodyEngine.math import Vector


import numpy as np

from OpenGL import WGL
from OpenGL.GL import *


class GLRenderer(Renderer):
    """
    The OpenGL renderer. Uses OpenGL version 330 Core.
    """
    def __init__(self, main: 'Main'):
        super().__init__(main)
        if self.main.window.window_type == "win32":
            self.context = context.create_context_win32(self.main.window)  
        
        self.texture_manager = GLTextureManager()

    def load_image(self, data):
        return GLImage(self, data)

    def load_material(self, data):
        return Material(data)

    def destroy(self):
        if self.main.winow.window_type == "win32":
            WGL.wglMakeCurrent(self.main.window.hdc, None)
        WGL.wglDeleteContext(self.context)

    def clear(self, color: 'Color'):
        glClearColor(*color.float_normalized_a)

        glClear(GL_COLOR_BUFFER_BIT)

    def load_shader(self, vertex, fragment, injector: Injector = Injector):
        return GLShader(vertex, fragment, injector)

    def load_material(self, data):
        return GLMaterial(data)

    def draw_line(self, start, end, width, color: 'Color'):
        glLineWidth(width)
        line_vertices = np.array([
            -start[0], start[1],
            end[0], end[1]
        ], dtype=np.float32)
        vao = glGenVertexArrays(1)
        vbo = glGenBuffers(1)
        glBindVertexArray(vao)
        glBindBuffer(GL_ARRAY_BUFFER, vbo)
        glBufferData(GL_ARRAY_BUFFER, line_vertices.nbytes, line_vertices, GL_STATIC_DRAW)

        # Enable attribute 0 as position
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 0, None)

        glBindVertexArray(0)

        glUseProgram(self.line_program)

        glUniform4f(glGetUniformLocation(self.line_program, "line_color"), *color.float_normalized_a)

        glBindVertexArray(vao)
        glDrawArrays(GL_LINES, 0, 2)
        glBindVertexArray(0)

    def draw_circle(self, radius, position, color):
        pass

    def draw_image(self, image: 'GLImage', material: 'Material', pos: 'Vector', camera: 'Camera'):
        image.texture.use()