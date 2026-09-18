import numpy as np

from FreeBodyEngine.graphics.mesh import Mesh, BufferUsage, IndexType, AttributeType, PrimitiveType
from FreeBodyEngine.graphics.webgl.interop import to_typed_array
from FreeBodyEngine import get_service


class WebGL2Mesh(Mesh):
    """The WebGL2 implementation of Mesh - see GLMesh's own docstring, same
    shape: one real VAO, one VBO per vertex attribute, an optional EBO for
    indexed drawing. WebGL2 (unlike WebGL1) has native `createVertexArray`/
    `bindVertexArray`, so this needs no OES_vertex_array_object shim."""
    def __init__(self, attributes: dict[str, tuple], indices: np.ndarray = None,
                 primitive=None, index_type=None, usage=None):
        super().__init__(attributes, indices, primitive, index_type, usage)
        self.gl = get_service('renderer').gl
        gl = self.gl

        self.vao = gl.createVertexArray()
        self.vbos = {}
        self.ebo = gl.createBuffer() if indices is not None else None

        self._render_mode = {
            PrimitiveType.TRIANGLES: gl.TRIANGLES,
            PrimitiveType.TRIANGLE_STRIP: gl.TRIANGLE_STRIP,
            PrimitiveType.TRIANGLE_FAN: gl.TRIANGLE_FAN,
        }.get(self.primitive, gl.TRIANGLES)

        self.upload()

    def _gl_usage(self):
        gl = self.gl
        return {
            BufferUsage.STATIC: gl.STATIC_DRAW,
            BufferUsage.DYNAMIC: gl.DYNAMIC_DRAW,
            BufferUsage.STREAM: gl.STREAM_DRAW,
        }.get(self.usage, gl.STATIC_DRAW)

    def _set_attribute_data(self, attribute_name, data):
        gl = self.gl
        gl.bindBuffer(gl.ARRAY_BUFFER, self.vbos[attribute_name])
        gl.bufferData(gl.ARRAY_BUFFER, to_typed_array(data, dtype=np.float32), self._gl_usage())

    def upload(self):
        """(Re)creates one VBO per entry in `self.attributes` and uploads
        its data, wiring each up as a sequential vertex attribute starting
        at location 0, in the same declaration order GLMesh.upload() uses
        - see its own docstring for why that order matters."""
        gl = self.gl
        gl.bindVertexArray(self.vao)
        gl_usage = self._gl_usage()

        location = 0
        for semantic, (attr_type, data) in self.attributes.items():
            vbo = gl.createBuffer()
            self.vbos[semantic] = vbo

            gl.bindBuffer(gl.ARRAY_BUFFER, vbo)

            if attr_type == AttributeType.FLOAT:
                size, np_dtype, gl_type = 1, np.float32, gl.FLOAT
            elif attr_type == AttributeType.VEC2:
                size, np_dtype, gl_type = 2, np.float32, gl.FLOAT
            elif attr_type == AttributeType.VEC3:
                size, np_dtype, gl_type = 3, np.float32, gl.FLOAT
            elif attr_type == AttributeType.VEC4:
                size, np_dtype, gl_type = 4, np.float32, gl.FLOAT
            elif attr_type == AttributeType.INT:
                size, np_dtype, gl_type = 1, np.int32, gl.INT
            elif attr_type == AttributeType.IVEC2:
                size, np_dtype, gl_type = 2, np.int32, gl.INT
            elif attr_type == AttributeType.IVEC3:
                size, np_dtype, gl_type = 3, np.int32, gl.INT
            elif attr_type == AttributeType.IVEC4:
                size, np_dtype, gl_type = 4, np.int32, gl.INT
            else:
                raise ValueError(f"Unsupported AttributeType: {attr_type}")

            gl.bufferData(gl.ARRAY_BUFFER, to_typed_array(data, dtype=np_dtype), gl_usage)

            gl.enableVertexAttribArray(location)
            if gl_type == gl.INT:
                gl.vertexAttribIPointer(location, size, gl_type, 0, 0)
            else:
                gl.vertexAttribPointer(location, size, gl_type, False, 0, 0)
            location += 1

        if self.indices is not None:
            gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, self.ebo)
            if self.index_type == IndexType.UINT16:
                self.gl_index_type = gl.UNSIGNED_SHORT
                index_dtype = np.uint16
            else:
                self.gl_index_type = gl.UNSIGNED_INT
                index_dtype = np.uint32
            gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, to_typed_array(self.indices, dtype=index_dtype), gl_usage)

        gl.bindVertexArray(None)

    def draw(self):
        """Issues the draw call - `drawElements` against the EBO if this
        mesh has indices, else `drawArrays` (same non-indexed vertex-count
        assumption GLMesh.draw() makes: the first attribute is a 3-wide
        channel)."""
        gl = self.gl
        gl.bindVertexArray(self.vao)

        if self.indices is not None:
            gl.drawElements(self._render_mode, len(self.indices), self.gl_index_type, 0)
        else:
            first_attr = next(iter(self.attributes.values()))[1]
            gl.drawArrays(self._render_mode, 0, len(first_attr) // 3)

        gl.bindVertexArray(None)

    def destroy(self):
        """Deletes every attribute VBO, the EBO if this mesh has one, and
        the VAO itself."""
        gl = self.gl
        for vbo in self.vbos.values():
            gl.deleteBuffer(vbo)
        if self.ebo:
            gl.deleteBuffer(self.ebo)
        gl.deleteVertexArray(self.vao)
