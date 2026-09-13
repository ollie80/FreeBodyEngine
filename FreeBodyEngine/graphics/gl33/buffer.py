from OpenGL.GL import *
from FreeBodyEngine.graphics.buffer import Buffer
import numpy as np

class UBOBuffer(Buffer):
    """The OpenGL 3.3 implementation of the buffer class."""
    def __init__(self, data: np.ndarray):
        """Allocates a GL_UNIFORM_BUFFER sized for `data` and uploads it
        immediately."""
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
        updating `self.data`/`self.buffer_size` the way set_data() does - for
        partial updates where get_data()'s bookkeeping isn't expected to
        reflect every byte of the live GPU buffer."""
        glBindBuffer(GL_UNIFORM_BUFFER, self.ubo)
        glBufferSubData(GL_UNIFORM_BUFFER, offset, data.nbytes, data)
        glBindBuffer(GL_UNIFORM_BUFFER, 0)

    def destroy(self):
        """Deletes this UBO's underlying GL buffer."""
        glDeleteBuffers(1, [self.ubo])


_FLOAT_FORMAT_BY_COMPONENTS = {1: GL_R32F, 2: GL_RG32F, 3: GL_RGB32F, 4: GL_RGBA32F}
_INT_FORMAT_BY_COMPONENTS = {1: GL_R32I, 2: GL_RG32I, 3: GL_RGB32I, 4: GL_RGBA32I}


class TextureBuffer(Buffer):
    """A GL_TEXTURE_BUFFER-backed storage buffer - the SSBO-equivalent
    "readable buffer" usable under a plain 3.3 core context (texture buffer
    objects are core since GL 3.1; real SSBOs need GL 4.3). Read-only from
    GLSL (sampled via `texelFetch`); written from Python via `set_data()`.
    Used for both compute-kernel `buffer` blocks and raytracing scene data.
    """
    def __init__(self, data: np.ndarray, gl_internal_format=None):
        """Creates the backing GL_TEXTURE_BUFFER (`tbo`) and its sampling
        texture (`tex`), then uploads `data` via set_data(). `gl_internal_format`
        overrides the format set_data() would otherwise infer from `data`'s
        shape/dtype (see `_infer_format`)."""
        self.internal_format = gl_internal_format
        self.tbo = glGenBuffers(1)
        self.tex = glGenTextures(1)
        self.data = None
        self.set_data(data)

    def _infer_format(self, data: np.ndarray):
        # A flat (N,) array is 1 float/int per texel (a `float[N]`/`int[N]`
        # buffer field); an (N, k) array is k components per texel (a
        # `vecK[N]` field, or a struct-array field already packed by the
        # generator's texel layout - see GL33Generator._compute_struct_layout).
        # Getting this wrong silently reads every element strided/offset
        # instead of erroring, so it's inferred from the data's own shape
        # rather than left as a default a caller could forget to override.
        components = 1 if data.ndim == 1 else data.shape[-1]
        table = _INT_FORMAT_BY_COMPONENTS if np.issubdtype(data.dtype, np.integer) else _FLOAT_FORMAT_BY_COMPONENTS
        if components not in table:
            raise ValueError(f"TextureBuffer data's last dimension must be 1-4 components, got {components}")
        return table[components]

    def set_data(self, data: np.ndarray):
        """Uploads `data` into the buffer object and (re)binds it as a buffer
        texture. The GL internal format is inferred from `data`'s shape/
        dtype only if `gl_internal_format` wasn't fixed at construction -
        once set (either way), every later call reuses that same format
        regardless of what a new `data` array's own shape might imply."""
        data = np.asarray(data)
        if self.internal_format is None:
            self.internal_format = self._infer_format(data)

        dtype = np.int32 if self.internal_format in (GL_R32I, GL_RG32I, GL_RGB32I, GL_RGBA32I) else np.float32
        self.data = np.ascontiguousarray(data, dtype=dtype)

        glBindBuffer(GL_TEXTURE_BUFFER, self.tbo)
        glBufferData(GL_TEXTURE_BUFFER, self.data.nbytes, self.data, GL_DYNAMIC_DRAW)
        glBindBuffer(GL_TEXTURE_BUFFER, 0)

        # glBindTexture(GL_TEXTURE_BUFFER, ...) binds on whatever texture
        # unit is *currently active* - not a unit this object owns. Without
        # saving/restoring that unit's prior binding, re-uploading (or even
        # just constructing) one TextureBuffer would silently unbind
        # whatever unrelated sampler another already-`bind()`-ed
        # TextureBuffer left active on that same unit, breaking it the next
        # time it's sampled with no error anywhere.
        prev_unit = glGetIntegerv(GL_ACTIVE_TEXTURE)
        prev_bound = glGetIntegerv(GL_TEXTURE_BINDING_BUFFER)

        glBindTexture(GL_TEXTURE_BUFFER, self.tex)
        glTexBuffer(GL_TEXTURE_BUFFER, self.internal_format, self.tbo)

        glBindTexture(GL_TEXTURE_BUFFER, prev_bound)
        glActiveTexture(prev_unit)

    def get_data(self):
        """Returns the data last passed to set_data(), already coerced to
        the buffer's actual dtype/format."""
        return self.data

    def bind(self, texture_unit: int):
        """Activates `texture_unit` and binds this buffer's sampling texture
        to it, ready for `texelFetch()` in GLSL."""
        glActiveTexture(GL_TEXTURE0 + texture_unit)
        glBindTexture(GL_TEXTURE_BUFFER, self.tex)

    def unbind(self):
        """Unbinds GL_TEXTURE_BUFFER from whichever unit is currently
        active."""
        glBindTexture(GL_TEXTURE_BUFFER, 0)

    def destroy(self):
        """Deletes this object's GL texture and buffer."""
        glDeleteTextures(1, [self.tex])
        glDeleteBuffers(1, [self.tbo])

    @staticmethod
    def get_max_size() -> int:
        """Returns the GPU's max texture buffer size in bytes
        (GL_MAX_TEXTURE_BUFFER_SIZE)."""
        return glGetIntegerv(GL_MAX_TEXTURE_BUFFER_SIZE)