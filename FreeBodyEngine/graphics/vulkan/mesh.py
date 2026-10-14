"""VulkanMesh - the Mesh interface on Vulkan buffers. As GL44Mesh: one
buffer per attribute, bound to vertex input locations in `attributes`
dict order, plus an optional index buffer.

The difference that matters: GL applies glBufferData between two draws
immediately, so a mesh rewritten mid-frame (text, lines, anything
batched) draws each version in turn. Vulkan executes the frame's commands
later, all at once - so set_data() on a buffer already used this frame
moves to a fresh buffer instead of overwriting the one an earlier draw is
still going to read. The old buffer is freed once the frame is done.
"""
import numpy as np
import vulkan as vk

from FreeBodyEngine import get_service
from FreeBodyEngine.graphics.mesh import Mesh, AttributeType, IndexType, PrimitiveType, BufferUsage
from FreeBodyEngine.graphics.vulkan.context import Buffer

# AttributeType -> (VkFormat, components, numpy dtype)
ATTRIBUTE_FORMATS = {
    AttributeType.FLOAT: (vk.VK_FORMAT_R32_SFLOAT, 1, np.float32),
    AttributeType.VEC2: (vk.VK_FORMAT_R32G32_SFLOAT, 2, np.float32),
    AttributeType.VEC3: (vk.VK_FORMAT_R32G32B32_SFLOAT, 3, np.float32),
    AttributeType.VEC4: (vk.VK_FORMAT_R32G32B32A32_SFLOAT, 4, np.float32),
    AttributeType.INT: (vk.VK_FORMAT_R32_SINT, 1, np.int32),
    AttributeType.IVEC2: (vk.VK_FORMAT_R32G32_SINT, 2, np.int32),
    AttributeType.IVEC3: (vk.VK_FORMAT_R32G32B32_SINT, 3, np.int32),
    AttributeType.IVEC4: (vk.VK_FORMAT_R32G32B32A32_SINT, 4, np.int32),
}
TOPOLOGIES = {
    PrimitiveType.TRIANGLES: vk.VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST,
    PrimitiveType.TRIANGLE_STRIP: vk.VK_PRIMITIVE_TOPOLOGY_TRIANGLE_STRIP,
    PrimitiveType.TRIANGLE_FAN: vk.VK_PRIMITIVE_TOPOLOGY_TRIANGLE_FAN,
    PrimitiveType.POINTS: vk.VK_PRIMITIVE_TOPOLOGY_POINT_LIST,
    PrimitiveType.LINES: vk.VK_PRIMITIVE_TOPOLOGY_LINE_LIST,
    PrimitiveType.LINE_STRIP: vk.VK_PRIMITIVE_TOPOLOGY_LINE_STRIP,
}
# Storage too: an emulated geometry stage reads meshes as storage buffers.
VERTEX = vk.VK_BUFFER_USAGE_VERTEX_BUFFER_BIT | vk.VK_BUFFER_USAGE_STORAGE_BUFFER_BIT
INDEX = vk.VK_BUFFER_USAGE_INDEX_BUFFER_BIT | vk.VK_BUFFER_USAGE_STORAGE_BUFFER_BIT


class _Stream:
    """One attribute's (or the index) buffer, and the frame it was last
    drawn in - see the module docstring."""
    __slots__ = ("buffer", "drawn_in")

    def __init__(self, buffer):
        self.buffer = buffer
        self.drawn_in = -1


class VulkanMesh(Mesh):
    def __init__(self, attributes, indices=None, primitive=None, index_type=None, usage=None):
        super().__init__(attributes, indices,
                         PrimitiveType.TRIANGLES if primitive is None else primitive,
                         IndexType.UINT16 if index_type is None else index_type,
                         BufferUsage.STATIC if usage is None else usage)
        self.renderer = get_service("renderer")
        self.topology = TOPOLOGIES.get(self.primitive, vk.VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST)
        self.streams: dict[str, _Stream] = {}
        self.formats: list[tuple[int, int]] = []  # (VkFormat, stride) per attribute, in location order
        self.counts: dict[str, int] = {}
        for name, (attr_type, data) in self.attributes.items():
            if attr_type not in ATTRIBUTE_FORMATS:
                raise ValueError(f"Unsupported AttributeType: {attr_type}")
            fmt, components, dtype = ATTRIBUTE_FORMATS[attr_type]
            self.formats.append((fmt, components * 4))
            self.streams[name] = _Stream(self._buffer(self._pack(name, data), VERTEX))
        self.index_stream = None
        self._uploaded_index_count = 0
        if indices is not None:
            self._set_indices(indices)

    def _pack(self, name, data) -> bytes:
        attr_type = self.attributes[name][0]
        fmt, components, dtype = ATTRIBUTE_FORMATS[attr_type]
        array = np.ascontiguousarray(np.asarray(data), dtype=dtype)
        self.counts[name] = array.size // components
        return array.tobytes()

    def _buffer(self, data: bytes, usage: int) -> Buffer:
        buf = Buffer(self.renderer.ctx, max(len(data), 4), usage)
        if data:
            buf.write(data)
        return buf

    def _set_indices(self, indices):
        dtype = np.uint16 if self.index_type == IndexType.UINT16 else np.uint32
        data = np.ascontiguousarray(np.asarray(indices), dtype=dtype)
        self._uploaded_index_count = data.size
        self.index_vk_type = vk.VK_INDEX_TYPE_UINT16 if dtype == np.uint16 else vk.VK_INDEX_TYPE_UINT32
        self.index_stream = _Stream(self._buffer(data.tobytes(), INDEX))

    def _set_attribute_data(self, attribute_name, data):
        attr_type = self.attributes[attribute_name][0]
        self.attributes[attribute_name] = (attr_type, data)
        packed = self._pack(attribute_name, data)
        stream = self.streams[attribute_name]
        if stream.drawn_in == self.renderer.frame_index or len(packed) > stream.buffer.size:
            # Still to be read by a draw recorded earlier this frame (or too
            # small) - write the new version somewhere else.
            self.renderer.defer_destroy(stream.buffer)
            self.streams[attribute_name] = _Stream(self._buffer(packed, VERTEX))
        else:
            stream.buffer.write(packed)

    @property
    def index_count(self) -> int:
        """len(self.indices), as GL44Mesh.draw() reads it at every draw -
        TextRenderer shortens a batch by assigning a prefix of the indices
        it uploaded once, without re-uploading."""
        if self.indices is None:
            return 0
        return min(len(self.indices), self._uploaded_index_count)

    @property
    def vertex_count(self) -> int:
        if not self.counts:
            return 0
        if self.index_stream is None:
            # GL44Mesh.draw() divides the first attribute's element count by
            # 3 - i.e. it assumes 3-component positions. Matched exactly.
            first = next(iter(self.attributes.values()))[1]
            return len(np.asarray(first).reshape(-1)) // 3
        return min(self.counts.values())

    def stream_buffers(self) -> list[Buffer]:
        """The attribute buffers in location order, marking them as used by
        the current frame."""
        frame = self.renderer.frame_index
        buffers = []
        for stream in self.streams.values():
            stream.drawn_in = frame
            buffers.append(stream.buffer)
        if self.index_stream is not None:
            self.index_stream.drawn_in = frame
        return buffers

    def draw(self):
        """Draws with whichever shader was last use()d - the same contract
        as GL44Mesh.draw() after glUseProgram."""
        self.renderer.draw_current(self)

    def destroy(self):
        for stream in self.streams.values():
            self.renderer.defer_destroy(stream.buffer)
        if self.index_stream is not None:
            self.renderer.defer_destroy(self.index_stream.buffer)
        self.streams = {}
