from OpenGL.GL import *
from FreeBodyEngine.graphics.mesh import Mesh, BufferUsage, IndexType, AttributeType, PrimitiveType
import numpy as np


class GLMesh(Mesh):
    """The GL 3.3 implementation of Mesh: owns a real VAO, one VBO per
    vertex attribute, and an optional EBO for indexed drawing. Maps the
    abstract PrimitiveType onto the actual GL draw-mode enum once at
    construction (`_render_mode`) rather than re-resolving it on every
    draw()."""
    def __init__(self, attributes: dict[str, tuple], indices: np.ndarray = None,
                 primitive=None, index_type=None, usage=None):
        """Generates the VAO and, if `indices` is given, the EBO (VBOs
        themselves are created lazily per-attribute in upload()), resolves
        `primitive` to its GL draw-mode enum, and immediately calls upload()
        to push the mesh's initial data to the GPU."""
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
        """(Re)creates one VBO per entry in `self.attributes` and uploads its
        data, wiring each up as a sequential vertex attribute starting at
        location 0 in `self.attributes`' iteration order - so the order
        attributes are inserted into that dict is exactly the order the
        matching shader's `in` locations must line up with. Also uploads
        `self.indices` into the EBO if this mesh has one, recording its GL
        index-element type (`gl_index_type`) for draw() to use."""
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
        """Issues the draw call: `glDrawElements` against the EBO if this
        mesh has indices, else `glDrawArrays` over a vertex count derived
        from the first attribute's raw array length divided by 3 (i.e. this
        non-indexed path assumes that first attribute is 3 components wide,
        such as a "verticies" vec3 channel)."""
        glBindVertexArray(self.vao)

        if self.indices is not None:
            glDrawElements(self._render_mode, len(self.indices), self.gl_index_type, None)
        else:
            
            first_attr = next(iter(self.attributes.values()))[1]
            glDrawArrays(self._render_mode, 0, len(first_attr) // 3)
        glBindVertexArray(0)

    def destroy(self):
        """Deletes every attribute VBO, the EBO if this mesh has one, and the
        VAO itself, releasing all of this mesh's GPU resources."""
        for vbo in self.vbos.values():
            glDeleteBuffers(1, [vbo])
        if self.ebo:
            glDeleteBuffers(1, [self.ebo])
        glDeleteVertexArrays(1, [self.vao])
