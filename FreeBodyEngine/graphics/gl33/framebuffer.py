from FreeBodyEngine.graphics.framebuffer import Framebuffer, AttachmentFormat, AttachmentType
from FreeBodyEngine.utils import get_platform
from OpenGL.GL import *
import numpy as np


def _set_shadow_map_wrap(target):
    """Sets `target`'s (a bound GL_TEXTURE_2D) wrap mode for a shadow map's
    depth texture: real GL_CLAMP_TO_BORDER + a white (far/1.0) border color
    everywhere except Android, where GLES 3.0's core profile has neither -
    GL_CLAMP_TO_BORDER is an extension there (EXT_texture_border_clamp,
    not guaranteed present), and there's no border color call to fall back
    to at all. GL_CLAMP_TO_EDGE is the closest available substitute: a
    sample just past the map's edge reads that edge's own depth instead of
    a guaranteed-lit border, which is very occasionally wrong right at a
    shadow map's boundary but never crashes - an acceptable first-pass
    trade for a feature (shadow mapping) that's a secondary concern for an
    initial Android build compared to getting sprites/UI on screen at
    all."""
    if get_platform() == "android":
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
    else:
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_BORDER)
        glTexParameterfv(GL_TEXTURE_2D, GL_TEXTURE_BORDER_COLOR, np.array([1.0, 1.0, 1.0, 1.0], dtype=np.float32))


GL_CHANNEL_COUNT = {
    GL_RED: 1,
    GL_RG: 2,
    GL_RGB: 3,
    GL_RGBA: 4,
}


GL_ATTACHMENT_FORMAT = {
    AttachmentFormat.R8: GL_R8,
    AttachmentFormat.RGBA8: GL_RGBA8,
    AttachmentFormat.RGBA16F: GL_RGBA16F,
    AttachmentFormat.RGBA32F: GL_RGBA32F,
    AttachmentFormat.RGB10_A2: GL_RGB10_A2,
    AttachmentFormat.R32F: GL_R32F,
    AttachmentFormat.RG32F: GL_RG32F,

    AttachmentFormat.DEPTH24: GL_DEPTH_COMPONENT24,
    AttachmentFormat.DEPTH32F: GL_DEPTH_COMPONENT32F,

    AttachmentFormat.STENCIL8: GL_STENCIL_INDEX8,

    AttachmentFormat.DEPTH24_STENCIL8: GL_DEPTH24_STENCIL8,
}

GL_ATTACHMENT_TYPE = {
    AttachmentFormat.R8: (GL_RED, GL_UNSIGNED_BYTE),
    AttachmentFormat.RGBA8: (GL_RGBA, GL_UNSIGNED_BYTE),
    AttachmentFormat.RGBA16F: (GL_RGBA, GL_FLOAT),
    AttachmentFormat.RGBA32F: (GL_RGBA, GL_FLOAT),
    AttachmentFormat.RGB10_A2: (GL_RGBA, GL_UNSIGNED_INT_2_10_10_10_REV),
    AttachmentFormat.R32F: (GL_RED, GL_FLOAT),
    AttachmentFormat.RG32F: (GL_RG, GL_FLOAT),

    AttachmentFormat.DEPTH24: (GL_DEPTH_COMPONENT, GL_UNSIGNED_INT),
    AttachmentFormat.DEPTH32F: (GL_DEPTH_COMPONENT, GL_FLOAT),

    AttachmentFormat.STENCIL8: (GL_STENCIL_INDEX, GL_UNSIGNED_BYTE),

    AttachmentFormat.DEPTH24_STENCIL8: (GL_DEPTH_STENCIL, GL_UNSIGNED_INT_24_8),
}



class GLFramebuffer(Framebuffer):
    """The GL 3.3 implementation of Framebuffer: a real `glGenFramebuffers`
    object with one GL_TEXTURE_2D per color attachment (so it can also be
    sampled from later, e.g. a G-buffer channel) and a single shared
    renderbuffer for whichever depth/stencil/depth-stencil attachment was
    requested. `self.attachments[name]` (inherited from the base class) is
    repurposed here to hold each color attachment's actual
    `GL_COLOR_ATTACHMENT0 + n` enum rather than the `(AttachmentType,
    AttachmentFormat)` pair the constructor received - that original pair is
    kept separately in `self._attachments` since resize() needs it again to
    recreate storage at the new size."""
    def __init__(self, width, height, attachments, transparent=False):
        """Creates the FBO and, for every requested attachment, the backing
        GL object: a mipmapless linear-filtered GL_TEXTURE_2D for each COLOR
        attachment (bound to consecutive GL_COLOR_ATTACHMENTn slots), or one
        shared renderbuffer for a DEPTH/STENCIL/DEPTH_STENCIL attachment.
        Color attachments are also collected into `draw_buffers` and wired up
        via `glDrawBuffers` so a shader with multiple `@output` fields
        actually renders to all of them; with no color attachments at all,
        `glDrawBuffer(GL_NONE)`/`glReadBuffer(GL_NONE)` are set instead
        (a depth-only FBO, e.g. a shadow map). Raises RuntimeError if the
        finished FBO fails `glCheckFramebufferStatus`. `transparent` enables
        standard alpha blending for subsequent draws into this FBO."""
        super().__init__(width, height, attachments)
        self.fbo = glGenFramebuffers(1)
        self.textures = {}
        self._attachments = attachments.copy()

        glBindFramebuffer(GL_FRAMEBUFFER, self.fbo)

        draw_buffers = []
        color_attachment_index = 0
        
        for name, (att_type, att_format) in attachments.items():
            if att_type == AttachmentType.COLOR:
                tex = glGenTextures(1)
                glBindTexture(GL_TEXTURE_2D, tex)
                internal_format = GL_ATTACHMENT_FORMAT[att_format]
                fmt, typ = GL_ATTACHMENT_TYPE[att_format]
                glTexImage2D(GL_TEXTURE_2D, 0, internal_format, width, height, 0, fmt, typ, None)

                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)

                attachment_enum = GL_COLOR_ATTACHMENT0 + color_attachment_index
                glFramebufferTexture2D(GL_FRAMEBUFFER, attachment_enum, GL_TEXTURE_2D, tex, 0)

                self.textures[name] = tex
                self.attachments[name] = attachment_enum

                draw_buffers.append(attachment_enum)
                color_attachment_index += 1

            elif att_type == AttachmentType.DEPTH:
                # A texture, not a renderbuffer (unlike STENCIL/DEPTH_STENCIL
                # below) - a shadow-map pass needs to sample this back as a
                # regular texture in a later shader (see PBRPipeline's
                # directional-light shadow pass), which a renderbuffer can't
                # be. GL_NEAREST since depth-comparison shadow sampling does
                # its own bias/PCF rather than relying on hardware filtering,
                # and GL_CLAMP_TO_BORDER with a border depth of 1.0 (max/far)
                # so sampling outside the map's bounds reads as "not in
                # shadow" instead of wrapping/repeating garbage.
                tex = glGenTextures(1)
                glBindTexture(GL_TEXTURE_2D, tex)
                internal_format = GL_ATTACHMENT_FORMAT[att_format]
                fmt, typ = GL_ATTACHMENT_TYPE[att_format]
                glTexImage2D(GL_TEXTURE_2D, 0, internal_format, width, height, 0, fmt, typ, None)

                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
                _set_shadow_map_wrap(GL_TEXTURE_2D)

                glFramebufferTexture2D(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_TEXTURE_2D, tex, 0)

                self.textures[name] = tex
                self.depth_texture_name = name

            elif att_type == AttachmentType.STENCIL:
                self.depth_renderbuffer = glGenRenderbuffers(1)
                glBindRenderbuffer(GL_ATTACHMENT_FORMAT, self.depth_renderbuffer)
                internal_format = GL_ATTACHMENT_FORMAT[att_format]
                glRenderbufferStorage(GL_RENDERBUFFER, internal_format, width, height)
                glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_STENCIL_ATTACHMENT, GL_RENDERBUFFER, self.depth_renderbuffer)

            elif att_type == AttachmentType.DEPTH_STENCIL:
                self.depth_renderbuffer = glGenRenderbuffers(1)
                glBindRenderbuffer(GL_RENDERBUFFER, self.depth_renderbuffer)
                internal_format = GL_ATTACHMENT_FORMAT[att_format]
                glRenderbufferStorage(GL_RENDERBUFFER, internal_format, width, height)
                glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_STENCIL_ATTACHMENT, GL_RENDERBUFFER, self.depth_renderbuffer)

            else:
                raise ValueError(f"Unsupported attachment type: {att_type}")

        self.num_color_attachments = color_attachment_index

        if draw_buffers:
            glDrawBuffers(len(draw_buffers), draw_buffers)
        else:
            glDrawBuffer(GL_NONE)
            glReadBuffer(GL_NONE)

        status = glCheckFramebufferStatus(GL_FRAMEBUFFER)
        if status != GL_FRAMEBUFFER_COMPLETE:
            raise RuntimeError(f"Framebuffer incomplete: status {status}")

        if transparent:

            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glEnable(GL_BLEND)

        glBindFramebuffer(GL_FRAMEBUFFER, 0)

    def _draw_depth_texture(tex, size):
        pass

    def clear_color_attachment(self, name: str, value=(0.0, 0.0, 0.0, 0.0)):
        """Clears the named color attachment to `value` via
        `glClearBufferfv(GL_COLOR, draw_buffer_index, ...)`, targeting only
        that attachment's own draw-buffer index rather than every bound draw
        buffer at once (the effect a plain `glClear(GL_COLOR_BUFFER_BIT)`
        would have) - see the abstract method's docstring for why that
        distinction matters for a multi-attachment G-buffer."""
        if name not in self.attachments:
            raise ValueError(f"No attachment named '{name}'")
        if self._attachments[name][0] != AttachmentType.COLOR:
            raise ValueError(f"Attachment '{name}' is not a color attachment")

        draw_buffer_index = self.attachments[name] - GL_COLOR_ATTACHMENT0
        glClearBufferfv(GL_COLOR, draw_buffer_index, np.array(value, dtype=np.float32))

    def draw(self, attachment, size: tuple[int,int] = None):
        """Draw a named attachment to the screen."""
        if attachment not in self.attachments:
            raise ValueError(f"No attachment named '{attachment}'")

        size = (self.width, self.height) if size is None else size
        tex = self.textures.get(attachment)

        if self._attachments[attachment][0] == AttachmentType.DEPTH:
            self._draw_depth_texture(tex, size)
            return

        attachment_enum = self.attachments[attachment]

        glBindFramebuffer(GL_READ_FRAMEBUFFER, self.fbo)
        glReadBuffer(attachment_enum)

        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, 0)
        glBlitFramebuffer(
            0, 0, self.width, self.height,
            0, 0, size[0], size[1],
            GL_COLOR_BUFFER_BIT, GL_NEAREST
        )

        glBindFramebuffer(GL_READ_FRAMEBUFFER, 0)
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, 0)

    def read(self, attachment_name: str) -> np.ndarray:
        """Reads back the named color attachment's pixels via
        `glReadPixels`, always as GL_FLOAT regardless of the attachment's own
        storage type, and reshapes the raw buffer into a (height, width,
        channels) float32 array (`channels` derived from the attachment's GL
        format via GL_CHANNEL_COUNT). This is a synchronous GPU->CPU stall -
        see the abstract method's docstring for when that's acceptable."""
        if attachment_name not in self._attachments:
            raise ValueError(f"No attachment named '{attachment_name}'")

        att_type, att_format = self._attachments[attachment_name]
        if att_type != AttachmentType.COLOR:
            raise ValueError(f"Attachment '{attachment_name}' is not a color attachment")

        fmt, _typ = GL_ATTACHMENT_TYPE[att_format]
        channels = GL_CHANNEL_COUNT[fmt]

        glBindFramebuffer(GL_READ_FRAMEBUFFER, self.fbo)
        glReadBuffer(self.attachments[attachment_name])
        raw = glReadPixels(0, 0, self.width, self.height, fmt, GL_FLOAT)
        glBindFramebuffer(GL_READ_FRAMEBUFFER, 0)

        return np.frombuffer(raw, dtype=np.float32).reshape(self.height, self.width, channels)

    def get_attachment_texture(self, attachment_name):
        """Returns the raw GL texture id backing the named color attachment
        (there's nothing to return for a depth/stencil attachment - those are
        renderbuffers, not textures - so only entries in `self.textures`
        apply)."""
        if attachment_name in self.textures.keys():
            return self.textures[attachment_name]
        else:
            error(f'No attachment "{attachment_name}" on framebuffer: {self}')

    def resize(self, size: tuple[int, int]):
        """Recreates every attachment's storage at the new `size`, mirroring
        __init__'s attachment loop: each color texture is deleted and
        regenerated at the new dimensions (a GL texture's storage can't be
        resized in place), and the shared depth/stencil renderbuffer is
        likewise deleted and regenerated if one exists. Also re-runs the
        draw-buffers wiring and completeness check __init__ does, and updates
        the GL viewport to match. Raises RuntimeError if the resized FBO is
        incomplete."""
        self.width, self.height = size[0], size[1]

        glBindFramebuffer(GL_FRAMEBUFFER, self.fbo)

        draw_buffers = []
        color_attachment_index = 0

        for name, (att_type, att_format) in self._attachments.items():
            internal_format = GL_ATTACHMENT_FORMAT[att_format]

            if att_type == AttachmentType.COLOR:
                glDeleteTextures(1, [self.textures[name]])

                tex = glGenTextures(1)
                glBindTexture(GL_TEXTURE_2D, tex)

                fmt, typ = GL_ATTACHMENT_TYPE[att_format]
                glTexImage2D(GL_TEXTURE_2D, 0, internal_format, self.width, self.height, 0, fmt, typ, None)

                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)

                attachment_enum = GL_COLOR_ATTACHMENT0 + color_attachment_index
                glFramebufferTexture2D(GL_FRAMEBUFFER, attachment_enum, GL_TEXTURE_2D, tex, 0)

                self.textures[name] = tex
                self.attachments[name] = attachment_enum

                draw_buffers.append(attachment_enum)
                color_attachment_index += 1

            elif att_type == AttachmentType.DEPTH:
                # Texture-backed, matching __init__ - see the comment there.
                glDeleteTextures(1, [self.textures[name]])

                tex = glGenTextures(1)
                glBindTexture(GL_TEXTURE_2D, tex)
                fmt, typ = GL_ATTACHMENT_TYPE[att_format]
                glTexImage2D(GL_TEXTURE_2D, 0, internal_format, self.width, self.height, 0, fmt, typ, None)

                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
                _set_shadow_map_wrap(GL_TEXTURE_2D)

                glFramebufferTexture2D(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_TEXTURE_2D, tex, 0)
                self.textures[name] = tex

            elif att_type in (AttachmentType.STENCIL, AttachmentType.DEPTH_STENCIL):
                if hasattr(self, "depth_renderbuffer"):
                    glDeleteRenderbuffers(1, [self.depth_renderbuffer])

                self.depth_renderbuffer = glGenRenderbuffers(1)
                glBindRenderbuffer(GL_RENDERBUFFER, self.depth_renderbuffer)
                glRenderbufferStorage(GL_RENDERBUFFER, internal_format, self.width, self.height)

                if att_type == AttachmentType.STENCIL:
                    glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_STENCIL_ATTACHMENT, GL_RENDERBUFFER, self.depth_renderbuffer)
                elif att_type == AttachmentType.DEPTH_STENCIL:
                    glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_STENCIL_ATTACHMENT, GL_RENDERBUFFER, self.depth_renderbuffer)

        self.num_color_attachments = color_attachment_index

        if draw_buffers:
            glDrawBuffers(len(draw_buffers), draw_buffers)
        else:
            glDrawBuffer(GL_NONE)
            glReadBuffer(GL_NONE)

        status = glCheckFramebufferStatus(GL_FRAMEBUFFER)
        if status != GL_FRAMEBUFFER_COMPLETE:
            raise RuntimeError(f"Framebuffer incomplete after resize: status {status}")
        glViewport(0, 0, self.width, self.height)
        glBindFramebuffer(GL_FRAMEBUFFER, 0)

    def bind(self):
        """Binds this FBO as the current GL_FRAMEBUFFER and sets the GL
        viewport to its full size, so subsequent draws render into it at
        the correct resolution instead of whatever viewport the
        previously-bound target left set."""
        glBindFramebuffer(GL_FRAMEBUFFER, self.fbo)
        glViewport(0, 0, self.width, self.height)

    def set_draw_buffers(self, names: list[str]):
        """See Framebuffer.set_draw_buffers. Assumes this FBO is already
        bound.

        Builds the same full-width, position-equals-attachment-index array
        WebGL2Framebuffer.set_draw_buffers() is forced to use (GL_NONE at
        every color attachment not in `names`) rather than the more
        compact `[self.attachments[n] for n in names]` this used to be -
        desktop GL doesn't require that shape (it can remap an arbitrary
        subset onto sequential fragment-output locations starting at 0),
        but PBRPipeline's shaders (see graphics/pbr/shaders.py's
        LIGHTING_COMPOSITE_FRAG/default_forward.fbfrag) declare their real
        `@output` field at whatever location its physical attachment index
        is - padded with unused leading fields to get there - specifically
        so the *same* FBUSL source compiles correctly on WebGL2, which has
        no remapping at all (see WebGL2Framebuffer.set_draw_buffers()'s
        own docstring). Matching that convention here means one shared
        assumption ("output location N always means physical attachment
        N") holds on both backends instead of desktop silently tolerating
        a mismatch WebGL2 can't."""
        requested = {self.attachments[name] for name in names}
        bufs = [
            (GL_COLOR_ATTACHMENT0 + i) if (GL_COLOR_ATTACHMENT0 + i) in requested else GL_NONE
            for i in range(self.num_color_attachments)
        ]
        glDrawBuffers(len(bufs), bufs)

    def unbind(self):
        """Rebinds the default framebuffer (0), i.e. the window's own
        backbuffer."""
        glBindFramebuffer(GL_FRAMEBUFFER, 0)
