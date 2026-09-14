from FreeBodyEngine.graphics.framebuffer import Framebuffer, AttachmentFormat, AttachmentType
from OpenGL.GL import *
import numpy as np


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



class GL44Framebuffer(Framebuffer):
    """The GL 4.4 implementation of Framebuffer: creates a real GL FBO with
    one 2D texture per color attachment and a shared renderbuffer for a
    depth/stencil/combined depth-stencil attachment (GL 4.4 has no
    functional need for a separate depth-only vs. combined path beyond
    which GL enum each is attached under)."""
    def __init__(self, width, height, attachments, transparent=False):
        """Creates the FBO and, for each entry in `attachments`, its backing
        GPU resource: a texture for a COLOR attachment (assigned sequential
        GL_COLOR_ATTACHMENT0+n slots and registered as a draw buffer), or a
        renderbuffer for DEPTH/STENCIL/DEPTH_STENCIL. Raises RuntimeError if
        the resulting FBO isn't GL_FRAMEBUFFER_COMPLETE. `transparent`
        enables standard alpha blending for subsequent draws into this
        framebuffer."""
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
                self.depth_renderbuffer = glGenRenderbuffers(1)
                glBindRenderbuffer(GL_RENDERBUFFER, self.depth_renderbuffer)
                internal_format = GL_ATTACHMENT_FORMAT[att_format]
                glRenderbufferStorage(GL_RENDERBUFFER, internal_format, width, height)
                glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, self.depth_renderbuffer)

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
        """Synchronously reads back color attachment `attachment_name`
        (glReadPixels, always as GL_FLOAT) into a `(height, width,
        channels)` numpy array - a GPU/CPU sync point, so only meant for
        compute-emulation-style result readback, not per-frame use. Raises
        ValueError if `attachment_name` doesn't exist or isn't a color
        attachment."""
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
        """Returns the raw GL texture name backing color attachment
        `attachment_name` (e.g. for wrapping via
        TextureManager.wrap_external_texture), logging an error instead of
        raising if it doesn't exist."""
        if attachment_name in self.textures.keys():
            return self.textures[attachment_name]
        else:
            error(f'No attachment "{attachment_name}" on framebuffer: {self}')

    def resize(self, size: tuple[int, int]):
        """Recreates every attachment's backing texture/renderbuffer at the
        new `size` in place (same FBO, same attachment slots) - deletes each
        old GL object first rather than leaking it. Raises RuntimeError if
        the FBO isn't complete afterward, and leaves the GL viewport set to
        the new size."""
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

            elif att_type in (AttachmentType.DEPTH, AttachmentType.STENCIL, AttachmentType.DEPTH_STENCIL):
                if hasattr(self, "depth_renderbuffer"):
                    glDeleteRenderbuffers(1, [self.depth_renderbuffer])

                self.depth_renderbuffer = glGenRenderbuffers(1)
                glBindRenderbuffer(GL_RENDERBUFFER, self.depth_renderbuffer)
                glRenderbufferStorage(GL_RENDERBUFFER, internal_format, self.width, self.height)

                if att_type == AttachmentType.DEPTH:
                    glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, self.depth_renderbuffer)
                elif att_type == AttachmentType.STENCIL:
                    glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_STENCIL_ATTACHMENT, GL_RENDERBUFFER, self.depth_renderbuffer)
                elif att_type == AttachmentType.DEPTH_STENCIL:
                    glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_STENCIL_ATTACHMENT, GL_RENDERBUFFER, self.depth_renderbuffer)

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
        """Binds this FBO as the current draw/read target and sets the GL
        viewport to its full size, so subsequent draw calls render into its
        attachments instead of the screen."""
        glBindFramebuffer(GL_FRAMEBUFFER, self.fbo)
        glViewport(0, 0, self.width, self.height)

    def unbind(self):
        """Rebinds the default framebuffer (id 0, the screen) - does not
        restore the previous viewport, so callers that resized it should
        reset that themselves."""
        glBindFramebuffer(GL_FRAMEBUFFER, 0)
