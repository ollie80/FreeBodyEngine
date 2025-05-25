from FreeBodyEngine.graphics.renderer import Renderer
from FreeBodyEngine.graphics.gl import context
from typing import TYPE_CHECKING
import numpy as np

from OpenGL import WGL
from OpenGL.GL import *
from FreeBodyEngine.graphics.color import Color

if TYPE_CHECKING:
    from FreeBodyEngine.core.main import Main
    from FreeBodyEngine.core.camera import Camera
    from FreeBodyEngine.graphics.material import Material
    from FreeBodyEngine.graphics.gl import GLImage

def create_shader_program(vertex_src, fragment_src):
    vertex_shader = compile_shader(vertex_src, GL_VERTEX_SHADER)
    fragment_shader = compile_shader(fragment_src, GL_FRAGMENT_SHADER)

    program = glCreateProgram()
    glAttachShader(program, vertex_shader)
    glAttachShader(program, fragment_shader)
    glLinkProgram(program)

    if glGetProgramiv(program, GL_LINK_STATUS) != GL_TRUE:
        error = glGetProgramInfoLog(program).decode()
        raise RuntimeError(f"Shader link error:\n{error}")

    glDeleteShader(vertex_shader)
    glDeleteShader(fragment_shader)

    return program


def compile_shader(source, shader_type):
    shader = glCreateShader(shader_type)
    glShaderSource(shader, source)
    glCompileShader(shader)

    if glGetShaderiv(shader, GL_COMPILE_STATUS) != GL_TRUE:
        error = glGetShaderInfoLog(shader).decode()
        raise RuntimeError(f"Shader compile error:\n{error}")
    
    return shader

class GLRenderer(Renderer):
    """
    The OpenGL renderer. Uses OpenGL version 330 Core.
    """
    def __init__(self, main: 'Main'):
        super().__init__(main)
        if self.main.window.window_type == "win32":
            self.context = context.create_context_win32(self.main.window)
        

    def destroy(self):
        if self.main.winow.window_type == "win32":
            WGL.wglMakeCurrent(self.main.window.hdc, None)
        WGL.wglDeleteContext(self.context)
        
    def clear(self, color: 'Color'):
        # Set the clear color to red (R=1, G=0, B=0, A=1)
        glClearColor(*color.float_normalized_a)

        # Clear the screen (color buffer only)
        glClear(GL_COLOR_BUFFER_BIT)


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

    def draw_image(self, image: 'GLImage', material: 'Material', camera: 'Camera'):
        pass        