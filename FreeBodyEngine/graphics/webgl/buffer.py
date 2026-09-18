"""WebGL2TextureBuffer: the WebGL2 implementation of the buffer-texture
"readable storage buffer" - see graphics/gl33/buffer.py's own TextureBuffer
for the desktop equivalent this mirrors. WebGL2 (GLSL ES 3.00) has no
GL_TEXTURE_BUFFER/samplerBuffer at all (that's ES 3.2+/desktop-only, no
WebGL2 extension exposes it either) - the same "read-only buffer, sampled
via texelFetch" contract is emulated here as an ordinary 2D data texture
instead. A 1D index `i` maps to a 2D texel at `(i % width, i / width)`,
where `width` is however wide this texture was actually created (queried
back in GLSL via `textureSize()` - see WebGL2Generator's `_ENGINE_buf_idx()`
helper) - no separate "width" uniform needs uploading or staying in sync.
"""
import numpy as np

from FreeBodyEngine.graphics.buffer import Buffer
from FreeBodyEngine.graphics.webgl.interop import to_typed_array
from FreeBodyEngine import get_service


class WebGL2TextureBuffer(Buffer):
    _FORMAT_TABLE = None  # populated lazily - needs a live `gl` to read its enums
    _FLOAT_FORMAT_BY_COMPONENTS = None
    _INT_FORMAT_BY_COMPONENTS = None

    def __init__(self, data: np.ndarray, gl_internal_format=None):
        """Creates the backing 2D texture and uploads `data` via
        set_data(). `gl_internal_format` overrides the format set_data()
        would otherwise infer from `data`'s shape/dtype (see
        `_infer_format`) - matching TextureBuffer.__init__()'s own
        contract exactly."""
        self.gl = get_service('renderer').gl
        gl = self.gl

        if WebGL2TextureBuffer._FORMAT_TABLE is None:
            WebGL2TextureBuffer._FORMAT_TABLE = {
                gl.R32F: (gl.RED, gl.FLOAT), gl.RG32F: (gl.RG, gl.FLOAT),
                gl.RGB32F: (gl.RGB, gl.FLOAT), gl.RGBA32F: (gl.RGBA, gl.FLOAT),
                gl.R32I: (gl.RED_INTEGER, gl.INT), gl.RG32I: (gl.RG_INTEGER, gl.INT),
                gl.RGB32I: (gl.RGB_INTEGER, gl.INT), gl.RGBA32I: (gl.RGBA_INTEGER, gl.INT),
            }
            WebGL2TextureBuffer._FLOAT_FORMAT_BY_COMPONENTS = {1: gl.R32F, 2: gl.RG32F, 3: gl.RGB32F, 4: gl.RGBA32F}
            WebGL2TextureBuffer._INT_FORMAT_BY_COMPONENTS = {1: gl.R32I, 2: gl.RG32I, 3: gl.RGB32I, 4: gl.RGBA32I}

        self.internal_format = gl_internal_format
        self.tex = gl.createTexture()
        self.data = None
        self.width = 1
        self.height = 1
        self.set_data(data)

    def _infer_format(self, data: np.ndarray):
        # Same shape-driven inference as TextureBuffer._infer_format() - a
        # flat (N,) array is 1 component/texel, an (N, k) array is k.
        components = 1 if data.ndim == 1 else data.shape[-1]
        table = (WebGL2TextureBuffer._INT_FORMAT_BY_COMPONENTS if np.issubdtype(data.dtype, np.integer)
                 else WebGL2TextureBuffer._FLOAT_FORMAT_BY_COMPONENTS)
        if components not in table:
            raise ValueError(f"TextureBuffer data's last dimension must be 1-4 components, got {components}")
        return table[components]

    def set_data(self, data: np.ndarray):
        """Uploads `data` into a 2D texture sized to hold it one texel per
        element, wrapping to further rows as needed (`width` capped at
        this GPU's MAX_TEXTURE_SIZE, `height` grown instead once a single
        row can't hold every element) - the WebGL2 texture equivalent of
        TextureBuffer.set_data()'s GL_TEXTURE_BUFFER upload. The tail of
        the last row is zero-padded when `data`'s length isn't an exact
        multiple of `width`; nothing in this backend's generated GLSL
        (see WebGL2Generator's buffer-block/raytrace codegen) ever
        computes an index reaching into that padding, so its contents
        are never actually read."""
        gl = self.gl
        data = np.asarray(data)
        if self.internal_format is None:
            self.internal_format = self._infer_format(data)

        is_int = self.internal_format in (gl.R32I, gl.RG32I, gl.RGB32I, gl.RGBA32I)
        dtype = np.int32 if is_int else np.float32
        components = 1 if data.ndim == 1 else data.shape[-1]
        flat = np.ascontiguousarray(data, dtype=dtype).reshape(-1, components)
        count = flat.shape[0]
        self.data = flat

        max_size = gl.getParameter(gl.MAX_TEXTURE_SIZE)
        width = min(max(count, 1), max_size)
        height = max(1, -(-count // width))  # ceil(count / width)
        self.width, self.height = width, height

        padded = np.zeros((width * height, components), dtype=dtype)
        padded[:count] = flat

        fmt, typ = WebGL2TextureBuffer._FORMAT_TABLE[self.internal_format]

        gl.bindTexture(gl.TEXTURE_2D, self.tex)
        gl.texImage2D(gl.TEXTURE_2D, 0, self.internal_format, width, height, 0, fmt, typ, to_typed_array(padded, dtype=dtype))
        # NEAREST/CLAMP_TO_EDGE: this is a data texture read exclusively via
        # texelFetch (an exact, unfiltered texel lookup - filtering/wrapping
        # settings don't even apply to it), but WebGL2 still requires a
        # texture to be "complete" - these just need to be *some* valid,
        # non-mipmapped setting, not left at their LINEAR/REPEAT defaults
        # which would make a NPOT-sized texture like this incomplete.
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST)
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST)
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
        # Unbound immediately, not left resident in whatever unit happens to
        # be active - see WebGL2Framebuffer._create_attachments()'s own
        # comment on exactly this hazard (a stray untracked binding here
        # could alias a framebuffer attachment later and trip WebGL2's
        # feedback-loop check).
        gl.bindTexture(gl.TEXTURE_2D, None)

    def get_data(self):
        """Returns the data last passed to set_data(), already coerced to
        this buffer's actual dtype/format (unpadded - the real element
        count, not width*height)."""
        return self.data

    def bind(self, texture_unit: int):
        """Activates `texture_unit` and binds this buffer's data texture to
        it, ready for `texelFetch()` in GLSL."""
        gl = self.gl
        gl.activeTexture(gl.TEXTURE0 + texture_unit)
        gl.bindTexture(gl.TEXTURE_2D, self.tex)

    def unbind(self):
        """Unbinds GL_TEXTURE_2D from whichever unit is currently active."""
        self.gl.bindTexture(self.gl.TEXTURE_2D, None)

    def destroy(self):
        """Deletes this object's underlying GL texture."""
        self.gl.deleteTexture(self.tex)

    @staticmethod
    def get_max_size() -> int:
        """Returns this GPU's max element count for one buffer (a single
        MAX_TEXTURE_SIZE-wide row of texels) - the WebGL2 analogue of
        TextureBuffer.get_max_size()'s GL_MAX_TEXTURE_BUFFER_SIZE, though
        unlike a real buffer texture this backend can still grow *taller*
        instead of failing outright past this many elements (see
        set_data()'s height growth) - this is a "still fits in one row"
        figure, not a hard ceiling."""
        gl = get_service('renderer').gl
        return gl.getParameter(gl.MAX_TEXTURE_SIZE)
