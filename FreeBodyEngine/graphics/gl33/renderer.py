from FreeBodyEngine.graphics.renderer import Renderer
from FreeBodyEngine.graphics.color import Color
from FreeBodyEngine.graphics.gl33 import GLImage, GLMesh, GLFramebuffer, context
from FreeBodyEngine.graphics.sprite import Sprite
from FreeBodyEngine.graphics.gl33.shader import GLShader
from FreeBodyEngine.graphics.gl33.texture import GLTextureManager
from FreeBodyEngine.graphics.gl33.material import GLMaterial
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
from OpenGL.GL.ARB.debug_output import * # for debug_callback


@GLDEBUGPROC
def debug_callback(source, type, id, severity, length, message, userParam):
    msg = ctypes.string_at(message, length).decode('utf-8')
    print(f"[OpenGL DEBUG] {msg}")

class GLRenderer(Renderer):
    """
    The OpenGL renderer. Uses OpenGL version 330 Core.
    """
    def __init__(self, main: 'Main'):
        super().__init__(main)

        self.mesh_class = GLMesh
        self.image_class = GLImage
        self.texture_manager = GLTextureManager()
        if self.main.window.window_type == "win32":
            self.context = context.create_win32_opengl_context(self.main.window, self.main.dev)
        glEnable(GL_DEBUG_OUTPUT)
        glEnable(GL_DEBUG_OUTPUT_SYNCHRONOUS)  
        glDebugMessageCallback(debug_callback, None)
        width, height = self.main.window.size
        glViewport(0, 0, width, height)
        
        # enable transparency
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

    def resize(self):
        width, height = self.main.window.size
        glViewport(0, 0, width, height)

    def load_image(self, texture: "Texture"):
        return GLImage(texture)
         
    def load_material(self, data):
        return Material(data)

    def destroy(self):
        if self.main.winow.window_type == "win32":
            WGL.wglMakeCurrent(self.main.window.hdc, None)
        WGL.wglDeleteContext(self.context)

    def create_framebuffer(self, width, height, attachments):
        return GLFramebuffer(width, height, attachments)

    def clear(self, color: 'Color'):
        glClearColor(*color.float_normalized_a)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        glClear(GL_COLOR_BUFFER_BIT)

    def load_shader(self, vertex, fragment, injector: Injector = Injector):
        return GLShader(vertex, fragment, injector)

    def load_material(self, data):
        return GLMaterial(data)

    def draw_mesh(self, mesh, material: 'GLMaterial', transform, camera):
        material.use(transform, camera)
        material.shader.use()
        if material.render_mode == "wireframe":
            glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)

        glBindVertexArray(mesh.vao)
        glDrawElements(GL_TRIANGLES, len(mesh.indices), GL_UNSIGNED_INT, ctypes.c_void_p(0))

        if material.render_mode == "wireframe":
            glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)


        glBindVertexArray(0)

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
