from FreeBodyEngine.graphics.mesh import Mesh
from OpenGL.GL import *

class GLMesh(Mesh):
    def __init__(self, vertices, normals, uvs, indices):
        super().__init__(vertices, normals, uvs, indices)
        self.vao = glGenVertexArrays(1)
        self.vbo_vertices = glGenBuffers(1)
        self.vbo_uvs = glGenBuffers(1)
        self.vbo_normals = glGenBuffers(1)
        self.ebo = glGenBuffers(1)
        self.upload()

    def upload(self):
        """Uploads mesh data to the GPU."""
        glBindVertexArray(self.vao)

        # verticies 
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo_vertices)
        glBufferData(GL_ARRAY_BUFFER, self.vertices.nbytes, self.vertices, GL_STATIC_DRAW)
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 0, None)

        # UVs
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo_uvs)
        glBufferData(GL_ARRAY_BUFFER, self.uvs.nbytes, self.uvs, GL_STATIC_DRAW)
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 0, None)

        # normals
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo_normals)
        glBufferData(GL_ARRAY_BUFFER, self.normals.nbytes, self.normals, GL_STATIC_DRAW)
        glEnableVertexAttribArray(2)
        glVertexAttribPointer(2, 3, GL_FLOAT, GL_FALSE, 0, None)
 
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.ebo)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, self.indices.nbytes, self.indices, GL_STATIC_DRAW)

        glBindVertexArray(0)

    def destroy(self):
        glDeleteBuffers(1, [self.vbo_vertices])
        glDeleteBuffers(1, [self.vbo_uvs])
        glDeleteBuffers(1, [self.vbo_normals])
        glDeleteBuffers(1, [self.ebo])
        glDeleteVertexArrays(1, [self.vao])