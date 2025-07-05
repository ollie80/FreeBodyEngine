from FreeBodyEngine.graphics.framebuffer import Framebuffer, AttachmentFormat, AttachmentType
from OpenGL.GL import *


GL_ATTACHMENT_FORMAT = {
    AttachmentFormat.R8: GL_R8,
    AttachmentFormat.RGBA8: GL_RGBA8,
    AttachmentFormat.RGBA16F: GL_RGBA16F,
    AttachmentFormat.RGBA32F: GL_RGBA32F,
    AttachmentFormat.RGB10_A2: GL_RGB10_A2,

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

    AttachmentFormat.DEPTH24: (GL_DEPTH_COMPONENT, GL_UNSIGNED_INT),
    AttachmentFormat.DEPTH32F: (GL_DEPTH_COMPONENT, GL_FLOAT),

    AttachmentFormat.STENCIL8: (GL_STENCIL_INDEX, GL_UNSIGNED_BYTE),

    AttachmentFormat.DEPTH24_STENCIL8: (GL_DEPTH_STENCIL, GL_UNSIGNED_INT_24_8),
}

class GLFramebuffer(Framebuffer):
    def __init__(self, width, height, attachments):
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

        glBindFramebuffer(GL_FRAMEBUFFER, 0)

    def draw(self, attachment):
        """Draw a named attachment to the screen."""
        if attachment not in self.attachments:
            raise ValueError(f"No attachment named '{attachment}'")
        
        attachment_enum = self.attachments[attachment]

        glBindFramebuffer(GL_READ_FRAMEBUFFER, self.fbo)
        glReadBuffer(attachment_enum)

        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, 0)
        glBlitFramebuffer(
            0, 0, self.width, self.height,
            0, 0, self.width, self.height,
            GL_COLOR_BUFFER_BIT, GL_NEAREST
        )

        glBindFramebuffer(GL_READ_FRAMEBUFFER, 0)
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, 0)

    def get_attachment_texture(self, attachment_name):
        if attachment_name in self.textures.keys():
            return self.textures[attachment_name]
        else:
            error(f'No attachment "{attachment_name}" on framebuffer: {self}')

    def resize(self, size: tuple[int, int]):
        self.width, self.height = size

        glBindFramebuffer(GL_FRAMEBUFFER, self.fbo)

        draw_buffers = []
        color_attachment_index = 0

        for name in self._attachments:
            att_type, att_format = self._attachments[name]
            
            if att_type == AttachmentType.COLOR:

                glDeleteTextures(1, [self.textures[name]])

                tex = glGenTextures(1)
                glBindTexture(GL_TEXTURE_2D, tex)
                internal_format = GL_ATTACHMENT_FORMAT[att_format]
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
                glDeleteRenderbuffers(1, [self.depth_renderbuffer])
                self.depth_renderbuffer = glGenRenderbuffers(1)
                glBindRenderbuffer(GL_RENDERBUFFER, self.depth_renderbuffer)
                internal_format = GL_ATTACHMENT_FORMAT[att_format]
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

        glBindFramebuffer(GL_FRAMEBUFFER, 0)

    def bind(self):
        glBindFramebuffer(GL_FRAMEBUFFER, self.fbo)
        glViewport(0, 0, self.width, self.height)

    def unbind(self):
        glBindFramebuffer(GL_FRAMEBUFFER, 0)