from OpenGL.GL import *
from FreeBodyEngine.graphics.buffer import Buffer
import numpy as np


class UBOBuffer(Buffer):
    """Identical to graphics/gl33/buffer.py's UBOBuffer - uniform buffer
    objects haven't changed at all between GL 3.3 and 4.4."""
    def __init__(self, data: np.ndarray):
        """See UBOBuffer.__init__ (graphics/gl33/buffer.py) - allocates a
        GL_UNIFORM_BUFFER sized for `data` and uploads it immediately."""
        self.buffer_size = data.nbytes
        self.data = data
        self._current_slot = 0

        self.ubo = glGenBuffers(1)
        glBindBuffer(GL_UNIFORM_BUFFER, self.ubo)
        glBufferData(GL_UNIFORM_BUFFER, self.buffer_size, None, GL_DYNAMIC_DRAW)
        glBufferSubData(GL_UNIFORM_BUFFER, 0, self.buffer_size, self.data)
        glBindBuffer(GL_UNIFORM_BUFFER, 0)

    def bind(self, point: int):
        """Binds this UBO to uniform binding point `point` - remembered so
        unbind() can release the same point later."""
        glBindBufferBase(GL_UNIFORM_BUFFER, point, self.ubo)
        self._current_slot = point

    def unbind(self):
        """Unbinds this UBO from whatever binding point bind() last used."""
        glBindBufferBase(GL_UNIFORM_BUFFER, self._current_slot, 0)

    def set_data(self, new_data: np.ndarray):
        """Replaces this UBO's contents with `new_data`, reallocating the
        GPU buffer first if its byte size changed."""
        self.data = new_data
        new_size = new_data.nbytes
        glBindBuffer(GL_UNIFORM_BUFFER, self.ubo)
        if new_size != self.buffer_size:
            glBufferData(GL_UNIFORM_BUFFER, new_size, None, GL_DYNAMIC_DRAW)
            self.buffer_size = new_size
        glBufferSubData(GL_UNIFORM_BUFFER, 0, new_size, new_data)
        glBindBuffer(GL_UNIFORM_BUFFER, 0)

    def get_data(self):
        """Returns the data last passed to set_data() (or the constructor) -
        NOT updated by update() below, which writes to the GPU buffer
        directly without touching this bookkeeping."""
        return self.data

    @staticmethod
    def get_max_size() -> int:
        """Returns the GPU's max uniform block size in bytes
        (GL_MAX_UNIFORM_BLOCK_SIZE)."""
        return glGetIntegerv(GL_MAX_UNIFORM_BLOCK_SIZE)

    def update(self, data: np.ndarray, offset: int = 0):
        """Uploads `data` into this UBO starting at byte `offset`, without
        updating `self.data`/`self.buffer_size` the way set_data() does."""
        glBindBuffer(GL_UNIFORM_BUFFER, self.ubo)
        glBufferSubData(GL_UNIFORM_BUFFER, offset, data.nbytes, data)
        glBindBuffer(GL_UNIFORM_BUFFER, 0)

    def destroy(self):
        """Deletes this UBO's underlying GL buffer."""
        glDeleteBuffers(1, [self.ubo])


class SSBOBuffer(Buffer):
    """A real GL_SHADER_STORAGE_BUFFER - what backs a `buffer` block under
    GL44Generator's real SSBO codegen (see gl44/generator.py), unlike GL33's
    GL_TEXTURE_BUFFER-based emulation (gl33/buffer.py's TextureBuffer,
    read-only from GLSL). Readable *and* writable from a compute shader:
    `compute.buffer_write` is a real capability of this backend.

    Holds exactly one buffer block's worth of data - if that block declares
    several fields, all of them are packed into this one buffer, in
    declaration order, matching std430 layout rules (see
    GL44Generator.generate_buffer_block()). For the common case of a block
    with a single field (as both shipped kernels use), that's simply the
    field's own flat array.
    """
    def __init__(self, data: np.ndarray):
        """Creates the backing SSBO and uploads `data` via set_data()."""
        self.ssbo = glGenBuffers(1)
        self.data = None
        self._current_slot = 0
        self.set_data(data)

    def set_data(self, data: np.ndarray):
        """Uploads `data` into the SSBO, replacing its contents. bool arrays
        are converted to int32 first - GLSL has no packed bool array layout
        a numpy bool8 upload matches."""
        data = np.asarray(data)
        # std430 packs int/float/bool scalars and vecN's each as their
        # natural size - only bool needs converting (GLSL has no packed
        # bool array representation compatible with a numpy bool8 upload).
        if data.dtype == np.bool_:
            data = data.astype(np.int32)
        self.data = np.ascontiguousarray(data)

        glBindBuffer(GL_SHADER_STORAGE_BUFFER, self.ssbo)
        glBufferData(GL_SHADER_STORAGE_BUFFER, self.data.nbytes, self.data, GL_DYNAMIC_DRAW)
        glBindBuffer(GL_SHADER_STORAGE_BUFFER, 0)

    def get_data(self) -> np.ndarray:
        """Returns the data last passed to set_data() - NOT the buffer's
        live GPU contents if a compute dispatch has written into it since;
        use read_back() for that."""
        return self.data

    def read_back(self) -> np.ndarray:
        """Reads the buffer's *current* GPU-side contents (which may have
        been modified by a compute dispatch writing directly into it - the
        whole point of a writable SSBO) rather than just returning the last
        value passed to set_data()."""
        glBindBuffer(GL_SHADER_STORAGE_BUFFER, self.ssbo)
        raw = glGetBufferSubData(GL_SHADER_STORAGE_BUFFER, 0, self.data.nbytes)
        glBindBuffer(GL_SHADER_STORAGE_BUFFER, 0)
        return np.frombuffer(raw, dtype=self.data.dtype).reshape(self.data.shape)

    def bind(self, binding: int):
        """Binds this SSBO to shader storage binding point `binding` -
        remembered so unbind() can release the same point later."""
        glBindBufferBase(GL_SHADER_STORAGE_BUFFER, binding, self.ssbo)
        self._current_slot = binding

    def unbind(self):
        """Unbinds this SSBO from whatever binding point bind() last used."""
        glBindBufferBase(GL_SHADER_STORAGE_BUFFER, self._current_slot, 0)

    def destroy(self):
        """Deletes this SSBO's underlying GL buffer."""
        glDeleteBuffers(1, [self.ssbo])

    @staticmethod
    def get_max_size() -> int:
        """Returns the GPU's max shader storage block size in bytes
        (GL_MAX_SHADER_STORAGE_BLOCK_SIZE)."""
        return glGetIntegerv(GL_MAX_SHADER_STORAGE_BLOCK_SIZE)
