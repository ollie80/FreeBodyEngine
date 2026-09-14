from OpenGL.GL import *
from FreeBodyEngine.graphics.mesh import Mesh, BufferUsage, IndexType, AttributeType, PrimitiveType
import numpy as np


class GL44Mesh(Mesh):
    """The GL 4.4 implementation of Mesh: one VAO with one VBO per attribute
    (bound to sequential vertex attribute locations in `attributes`' dict
    order) plus an optional EBO for indexed drawing. Identical in mechanism
    to GLMesh (graphics/gl33/mesh.py) - core vertex array/buffer upload
    hasn't changed between GL 3.3 and 4.4."""
    def __init__(self, attributes: dict[str, tuple], indices: np.ndarray = None,
                 primitive=None, index_type=None, usage=None):
        """Creates the VAO/VBOs/EBO (the EBO only if `indices` is given),
        picks the GL primitive enum matching `primitive`, and immediately
        uploads the given attribute/index data via `upload()`."""
        super().__init__(attributes, indices, primitive, index_type, usage)

        self.vao = glGenVertexArrays(1)
        self.vbos = {} 
        self.ebo = glGenBuffers(1) if indices is not None else None

        self._render_mode = {
            PrimitiveType.TRIANGLES: GL_TRIANGLES,
            PrimitiveType.TRIANGLE_STRIP: GL_TRIANGLE_STRIP,
            PrimitiveType.TRIANGLE_FAN: GL_TRIANGLE_FAN
        }.get(self.primitive, GL_TRIANGLES)


        self.upload()

    def _set_attribute_data(self, attribute_name, data):
        usage_map = {
            BufferUsage.STATIC: GL_STATIC_DRAW,
            BufferUsage.DYNAMIC: GL_DYNAMIC_DRAW,
            BufferUsage.STREAM: GL_STREAM_DRAW
        }
        glBindBuffer(GL_ARRAY_BUFFER, self.vbos[attribute_name])
        glBufferData(GL_ARRAY_BUFFER, data.nbytes, data, usage_map.get(self.usage, GL_STATIC_DRAW))

    def upload(self):
        """Uploads every attribute in `self.attributes` to its own VBO and
        wires it to a sequential vertex attribute location (location 0, 1,
        2, ... in dict iteration order - so the order attributes are passed
        in matters), then uploads `self.indices` to the EBO if present.
        Raises ValueError for an AttributeType this backend doesn't know how
        to map to a GL type/size (MAT3/MAT4/VEC5/VEC6/IVEC5/IVEC6)."""
        glBindVertexArray(self.vao)

        usage_map = {
            BufferUsage.STATIC: GL_STATIC_DRAW,
            BufferUsage.DYNAMIC: GL_DYNAMIC_DRAW,
            BufferUsage.STREAM: GL_STREAM_DRAW
        }
        gl_usage = usage_map.get(self.usage, GL_STATIC_DRAW)
        
        location = 0
        for semantic, (attr_type, data) in self.attributes.items():
            vbo = glGenBuffers(1)
            self.vbos[semantic] = vbo

            glBindBuffer(GL_ARRAY_BUFFER, vbo)
            glBufferData(GL_ARRAY_BUFFER, data.nbytes, data, gl_usage)

            if attr_type == AttributeType.FLOAT:
                size, gl_type = 1, GL_FLOAT
            elif attr_type == AttributeType.VEC2:
                size, gl_type = 2, GL_FLOAT
            elif attr_type == AttributeType.VEC3:
                size, gl_type = 3, GL_FLOAT
            elif attr_type == AttributeType.VEC4:
                size, gl_type = 4, GL_FLOAT

            elif attr_type == AttributeType.INT:
                size, gl_type = 1, GL_INT
            elif attr_type == AttributeType.IVEC2:
                size, gl_type = 2, GL_INT
            elif attr_type == AttributeType.IVEC3:
                size, gl_type = 3, GL_INT
            elif attr_type == AttributeType.IVEC4:
                size, gl_type = 4, GL_INT
            else:
                raise ValueError(f"Unsupported AttributeType: {attr_type}")

            glEnableVertexAttribArray(location)
            glVertexAttribPointer(location, size, gl_type, GL_FALSE, 0, None)
            location += 1

        if self.indices is not None:

            glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.ebo)
            if self.index_type == IndexType.UINT16:
                gl_index_type = GL_UNSIGNED_SHORT
            else:
                gl_index_type = GL_UNSIGNED_INT
            glBufferData(GL_ELEMENT_ARRAY_BUFFER, self.indices.nbytes, self.indices, gl_usage)
            self.gl_index_type = gl_index_type

        glBindVertexArray(0)

    def draw(self):
        """Issues the draw call for this mesh's currently uploaded buffers:
        `glDrawElements` if it has an index buffer, otherwise
        `glDrawArrays` sized off the first attribute's vertex count (its
        raw element count divided by 3, so this assumes that attribute is
        3-component - e.g. positions)."""
        glBindVertexArray(self.vao)

        if self.indices is not None:
            glDrawElements(self._render_mode, len(self.indices), self.gl_index_type, None)
        else:
            
            first_attr = next(iter(self.attributes.values()))[1]
            glDrawArrays(self._render_mode, 0, len(first_attr) // 3)
        glBindVertexArray(0)

    def destroy(self):
        """Deletes every VBO, the EBO (if any), and the VAO itself."""
        for vbo in self.vbos.values():
            glDeleteBuffers(1, [vbo])
        if self.ebo:
            glDeleteBuffers(1, [self.ebo])
        glDeleteVertexArrays(1, [self.vao])
