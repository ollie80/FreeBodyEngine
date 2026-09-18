import numpy as np

from FreeBodyEngine.graphics.framebuffer import Framebuffer, AttachmentFormat, AttachmentType
from FreeBodyEngine.graphics.webgl.interop import to_typed_array
from FreeBodyEngine import get_service, error


class WebGL2Framebuffer(Framebuffer):
    """The WebGL2 implementation of Framebuffer - see GLFramebuffer's own
    docstring, same shape: one GL_TEXTURE_2D per color attachment, a
    shared renderbuffer for depth/stencil/depth-stencil. Floating-point
    color attachments (RGBA16F/RGBA32F/R32F/RG32F - used throughout this
    engine's HDR/compute-emulation paths) need the `EXT_color_buffer_float`
    extension explicitly requested up front; unlike desktop GL 3.3 (where
    float render targets are core), WebGL2 only *guarantees* 8-bit/sRGB
    color-renderable formats without it."""

    _FORMAT_INFO = None  # populated lazily on first instance - needs a live `gl` to read extension support

    def __init__(self, width, height, attachments, transparent=False):
        super().__init__(width, height, attachments)
        self.gl = get_service('renderer').gl
        gl = self.gl

        if WebGL2Framebuffer._FORMAT_INFO is None:
            gl.getExtension("EXT_color_buffer_float")
            WebGL2Framebuffer._FORMAT_INFO = {
                AttachmentFormat.R8: (gl.R8, gl.RED, gl.UNSIGNED_BYTE),
                AttachmentFormat.RGBA8: (gl.RGBA8, gl.RGBA, gl.UNSIGNED_BYTE),
                AttachmentFormat.RGBA16F: (gl.RGBA16F, gl.RGBA, gl.FLOAT),
                AttachmentFormat.RGBA32F: (gl.RGBA32F, gl.RGBA, gl.FLOAT),
                AttachmentFormat.R32F: (gl.R32F, gl.RED, gl.FLOAT),
                AttachmentFormat.RG32F: (gl.RG32F, gl.RG, gl.FLOAT),
                AttachmentFormat.DEPTH24: (gl.DEPTH_COMPONENT24, gl.DEPTH_COMPONENT, gl.UNSIGNED_INT),
                AttachmentFormat.DEPTH32F: (gl.DEPTH_COMPONENT32F, gl.DEPTH_COMPONENT, gl.FLOAT),
                # `format`/`type` are never actually used for this one -
                # STENCIL8 always goes through the renderbuffer path below
                # (renderbufferStorage() takes only an internal format,
                # no format/type pair) - and WebGL2 has no `STENCIL_INDEX`
                # enum at all to put there regardless (unlike desktop GL,
                # which uses it for a would-be texture-backed stencil
                # attachment this backend doesn't support anyway).
                AttachmentFormat.STENCIL8: (gl.STENCIL_INDEX8, None, None),
                AttachmentFormat.DEPTH24_STENCIL8: (gl.DEPTH24_STENCIL8, gl.DEPTH_STENCIL, gl.UNSIGNED_INT_24_8),
            }

        self.fbo = gl.createFramebuffer()
        self.textures = {}
        self._attachments = attachments.copy()
        self.depth_texture_name = None
        self.depth_renderbuffer = None

        gl.bindFramebuffer(gl.FRAMEBUFFER, self.fbo)
        self._create_attachments(attachments)

        if transparent:
            gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA)
            gl.enable(gl.BLEND)

        gl.bindFramebuffer(gl.FRAMEBUFFER, None)

    def _create_attachments(self, attachments):
        gl = self.gl
        draw_buffers = []
        color_index = 0

        # Every gl.bindTexture(TEXTURE_2D, ...) below lands on whatever
        # texture unit is *currently active* - bindTexture never takes a
        # unit argument, it always targets ACTIVE_TEXTURE. Restoring
        # ACTIVE_TEXTURE afterward is NOT enough on its own: that only
        # controls which unit the *next* bindTexture call would affect, it
        # doesn't undo whatever got bound (or, per this method's own
        # explicit-unbind-after-setup below, un-bound) on the unit actually
        # used *during* this loop. A caller that already bound an input
        # texture to some unit (e.g. WebGL2ComputeShader.bind_texture(),
        # right before dispatch()'s "create self._fbo if the size changed"
        # triggers a fresh WebGL2Framebuffer here) would have that same
        # unit silently reassigned to - and then emptied of, once this
        # method's per-attachment unbind runs - this framebuffer's own
        # texture, with no GL error to show for it: sampling an emptied
        # unit isn't an error, it just silently returns the well-defined
        # "no texture bound" fallback value (0,0,0,1), which is exactly
        # what a naive save/restore of ACTIVE_TEXTURE alone would still
        # let through. Using a unit *no* ordinary caller is ever bound to
        # use - the driver's last one, since real shaders overwhelmingly
        # start allocating from unit 0 upward and rarely approach the
        # limit - keeps this setup work from ever touching whatever unit
        # the caller actually cares about, the same hazard (and the same
        # fix) as graphics/gl33/buffer.py's TextureBuffer.set_data().
        prev_active_unit = gl.getParameter(gl.ACTIVE_TEXTURE)
        scratch_unit = gl.getParameter(gl.MAX_COMBINED_TEXTURE_IMAGE_UNITS) - 1
        gl.activeTexture(gl.TEXTURE0 + scratch_unit)

        for name, (att_type, att_format) in attachments.items():
            internal_format, fmt, typ = self._FORMAT_INFO[att_format]

            if att_type == AttachmentType.COLOR:
                tex = gl.createTexture()
                gl.bindTexture(gl.TEXTURE_2D, tex)
                gl.texImage2D(gl.TEXTURE_2D, 0, internal_format, self.width, self.height, 0, fmt, typ, None)
                gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR)
                gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
                gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
                gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
                # Unbound immediately after setup - left bound, this would
                # sit forever in whatever texture unit happens to be
                # active (unit 0, by default) completely outside
                # WebGL2TextureManager's slot bookkeeping (this bind never
                # went through _allocate_slot), so the *first* time this
                # same framebuffer is later bound as a draw target again,
                # its own attachment is still "active" in that unit -
                # WebGL2's feedback-loop check flags that immediately,
                # regardless of whether anything actually samples it. See
                # WebGL2TextureManager.begin_draw()'s docstring for the
                # general version of this hazard.
                gl.bindTexture(gl.TEXTURE_2D, None)

                attachment_enum = gl.COLOR_ATTACHMENT0 + color_index
                gl.framebufferTexture2D(gl.FRAMEBUFFER, attachment_enum, gl.TEXTURE_2D, tex, 0)

                self.textures[name] = tex
                self.attachments[name] = attachment_enum
                draw_buffers.append(attachment_enum)
                color_index += 1

            elif att_type == AttachmentType.DEPTH:
                tex = gl.createTexture()
                gl.bindTexture(gl.TEXTURE_2D, tex)
                gl.texImage2D(gl.TEXTURE_2D, 0, internal_format, self.width, self.height, 0, fmt, typ, None)
                gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST)
                gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST)
                gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
                gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
                gl.bindTexture(gl.TEXTURE_2D, None)
                gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.DEPTH_ATTACHMENT, gl.TEXTURE_2D, tex, 0)
                self.textures[name] = tex
                self.depth_texture_name = name

            elif att_type in (AttachmentType.STENCIL, AttachmentType.DEPTH_STENCIL):
                rb = gl.createRenderbuffer()
                gl.bindRenderbuffer(gl.RENDERBUFFER, rb)
                gl.renderbufferStorage(gl.RENDERBUFFER, internal_format, self.width, self.height)
                target = gl.STENCIL_ATTACHMENT if att_type == AttachmentType.STENCIL else gl.DEPTH_STENCIL_ATTACHMENT
                gl.framebufferRenderbuffer(gl.FRAMEBUFFER, target, gl.RENDERBUFFER, rb)
                self.depth_renderbuffer = rb

            else:
                raise ValueError(f"Unsupported attachment type: {att_type}")

        gl.activeTexture(prev_active_unit)

        # Remembered for set_draw_buffers() below - it needs to know how
        # many COLOR_ATTACHMENTi slots this FBO actually has, not just
        # which ones a given call wants active.
        self.num_color_attachments = color_index

        if draw_buffers:
            gl.drawBuffers(draw_buffers)
        else:
            gl.drawBuffers([gl.NONE])
            gl.readBuffer(gl.NONE)

        status = gl.checkFramebufferStatus(gl.FRAMEBUFFER)
        if status != gl.FRAMEBUFFER_COMPLETE:
            raise RuntimeError(f"Framebuffer incomplete: status {status}")

    def clear_color_attachment(self, name: str, value=(0.0, 0.0, 0.0, 0.0)):
        """See GLFramebuffer.clear_color_attachment() - `clearBufferfv`
        targets one draw-buffer index at a time, same as desktop GL."""
        gl = self.gl
        if name not in self.attachments:
            raise ValueError(f"No attachment named '{name}'")
        if self._attachments[name][0] != AttachmentType.COLOR:
            raise ValueError(f"Attachment '{name}' is not a color attachment")

        draw_buffer_index = self.attachments[name] - gl.COLOR_ATTACHMENT0
        gl.clearBufferfv(gl.COLOR, draw_buffer_index, to_typed_array(np.array(value, dtype=np.float32)))

    def draw(self, attachment, size: tuple[int, int] = None):
        """Blits a named color attachment to the currently bound
        framebuffer (the default/window framebuffer, in the common case -
        see FramePresenter-style callers) via `blitFramebuffer`, which
        WebGL2 has natively (unlike WebGL1, which needed a fullscreen-quad
        shader trick for this)."""
        gl = self.gl
        if attachment not in self.attachments:
            raise ValueError(f"No attachment named '{attachment}'")

        size = (self.width, self.height) if size is None else size
        if self._attachments[attachment][0] == AttachmentType.DEPTH:
            return  # no depth-texture presentation path yet, matching GLFramebuffer's own stub

        attachment_enum = self.attachments[attachment]

        gl.bindFramebuffer(gl.READ_FRAMEBUFFER, self.fbo)
        gl.readBuffer(attachment_enum)
        gl.bindFramebuffer(gl.DRAW_FRAMEBUFFER, None)
        gl.blitFramebuffer(0, 0, self.width, self.height, 0, 0, size[0], size[1], gl.COLOR_BUFFER_BIT, gl.NEAREST)
        gl.bindFramebuffer(gl.READ_FRAMEBUFFER, None)
        gl.bindFramebuffer(gl.DRAW_FRAMEBUFFER, None)

    def read(self, attachment_name: str) -> np.ndarray:
        """Synchronous GPU->CPU readback via `readPixels` - see the
        abstract method's own docstring for when that's acceptable.
        `readPixels` needs a pre-sized JS typed array to write into
        (unlike PyOpenGL's glReadPixels, which allocates and returns one),
        so one is created up front and copied back out via `.to_py()`."""
        gl = self.gl
        if attachment_name not in self._attachments:
            raise ValueError(f"No attachment named '{attachment_name}'")

        att_type, att_format = self._attachments[attachment_name]
        if att_type != AttachmentType.COLOR:
            raise ValueError(f"Attachment '{attachment_name}' is not a color attachment")

        _internal, fmt, _typ = self._FORMAT_INFO[att_format]
        channels = {gl.RED: 1, gl.RG: 2, gl.RGB: 3, gl.RGBA: 4}[fmt]

        gl.bindFramebuffer(gl.READ_FRAMEBUFFER, self.fbo)
        gl.readBuffer(self.attachments[attachment_name])

        import js
        out = js.Float32Array.new(self.width * self.height * channels)
        gl.readPixels(0, 0, self.width, self.height, fmt, gl.FLOAT, out)
        gl.bindFramebuffer(gl.READ_FRAMEBUFFER, None)

        raw = np.asarray(out.to_py(), dtype=np.float32)
        return raw.reshape(self.height, self.width, channels)

    def get_attachment_texture(self, attachment_name):
        """Returns the raw WebGLTexture backing the named color
        attachment."""
        if attachment_name in self.textures:
            return self.textures[attachment_name]
        error(f'No attachment "{attachment_name}" on framebuffer: {self}')

    def resize(self, size: tuple[int, int]):
        """Recreates every attachment's storage at the new `size` - deletes
        and regenerates each one (WebGL2, like desktop GL, can't resize a
        texture/renderbuffer's storage in place)."""
        gl = self.gl
        self.width, self.height = size[0], size[1]

        gl.bindFramebuffer(gl.FRAMEBUFFER, self.fbo)

        for tex in self.textures.values():
            gl.deleteTexture(tex)
        self.textures = {}
        if self.depth_renderbuffer is not None:
            gl.deleteRenderbuffer(self.depth_renderbuffer)
            self.depth_renderbuffer = None

        self._create_attachments(self._attachments)

        gl.viewport(0, 0, self.width, self.height)
        gl.bindFramebuffer(gl.FRAMEBUFFER, None)

    def bind(self):
        """Binds this FBO and sets the viewport to its full size."""
        gl = self.gl
        gl.bindFramebuffer(gl.FRAMEBUFFER, self.fbo)
        gl.viewport(0, 0, self.width, self.height)

    def set_draw_buffers(self, names: list[str]):
        """See Framebuffer.set_draw_buffers(). Assumes this FBO is already
        bound.

        Unlike desktop GL (glDrawBuffers there can list attachments in any
        order or subset - array index N just means "fragment output N
        goes to whichever attachment is listed here"), WebGL2 requires
        array index i to be either NONE or *exactly* COLOR_ATTACHMENTi -
        the array position IS the attachment index, and can't reorder or
        compact them. So this can't just be `gl.drawBuffers([self.
        attachments[n] for n in names])` the way GLFramebuffer's desktop
        equivalent is (that mapped straight through and failed the
        instant `names` requested a non-contiguous-from-zero subset, e.g.
        a G-buffer's attachments 1-3 without attachment 0 - the WebGL2
        error is literally "drawBuffers: COLOR_ATTACHMENTi_EXT or NONE").
        Building a full-width array covering every color attachment this
        FBO has, with NONE at every index not in `names`, satisfies that
        restriction regardless of which subset was requested."""
        gl = self.gl
        requested = {self.attachments[name] for name in names}
        bufs = [
            (gl.COLOR_ATTACHMENT0 + i) if (gl.COLOR_ATTACHMENT0 + i) in requested else gl.NONE
            for i in range(self.num_color_attachments)
        ]
        gl.drawBuffers(bufs)

    def unbind(self):
        """Rebinds the default framebuffer (the canvas's own backbuffer)."""
        self.gl.bindFramebuffer(self.gl.FRAMEBUFFER, None)
