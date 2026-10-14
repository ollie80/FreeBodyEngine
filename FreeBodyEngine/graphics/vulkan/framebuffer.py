"""VulkanFramebuffer - the Framebuffer interface on GpuImages, with
GL44Framebuffer's semantics: bind() makes it the target of subsequent
draws, set_draw_buffers() picks which color attachments fragment outputs
0, 1, ... write, draw() blits one attachment to the window, read() copies
one back to the CPU.

Each attachment is an _Attachment wrapper around its current GpuImage, and
that wrapper is what get_attachment_texture() returns - so a Texture made
from it (TextureManager.wrap_external_texture) stays valid across
resize(), which swaps the image underneath. (Under GL a resize deletes the
texture id, and callers re-wrap; doing that here too is harmless.)
"""
import vulkan as vk

from FreeBodyEngine import get_service, error as fb_error
from FreeBodyEngine.graphics.framebuffer import Framebuffer, AttachmentFormat, AttachmentType
from FreeBodyEngine.graphics.vulkan.image import GpuImage

FORMATS = {
    AttachmentFormat.R8: vk.VK_FORMAT_R8_UNORM,
    AttachmentFormat.RGBA8: vk.VK_FORMAT_R8G8B8A8_UNORM,
    AttachmentFormat.RGBA16F: vk.VK_FORMAT_R16G16B16A16_SFLOAT,
    AttachmentFormat.RGBA32F: vk.VK_FORMAT_R32G32B32A32_SFLOAT,
    AttachmentFormat.RGB10_A2: vk.VK_FORMAT_A2B10G10R10_UNORM_PACK32,
    AttachmentFormat.R32F: vk.VK_FORMAT_R32_SFLOAT,
    AttachmentFormat.RG32F: vk.VK_FORMAT_R32G32_SFLOAT,
    # 24-bit depth isn't renderable everywhere (AMD has no D24); 32-bit
    # float depth is, and is at least as precise.
    AttachmentFormat.DEPTH24: vk.VK_FORMAT_D32_SFLOAT,
    AttachmentFormat.DEPTH32F: vk.VK_FORMAT_D32_SFLOAT,
    AttachmentFormat.STENCIL8: vk.VK_FORMAT_D32_SFLOAT_S8_UINT,
    AttachmentFormat.DEPTH24_STENCIL8: vk.VK_FORMAT_D32_SFLOAT_S8_UINT,
}
COLOR_USAGE = (vk.VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | vk.VK_IMAGE_USAGE_SAMPLED_BIT
               | vk.VK_IMAGE_USAGE_TRANSFER_SRC_BIT | vk.VK_IMAGE_USAGE_TRANSFER_DST_BIT)
DEPTH_USAGE = (vk.VK_IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT | vk.VK_IMAGE_USAGE_SAMPLED_BIT
               | vk.VK_IMAGE_USAGE_TRANSFER_SRC_BIT)


class _Attachment:
    """A stable handle onto an attachment's current GpuImage."""

    def __init__(self, gpu: GpuImage):
        self.gpu = gpu


class VulkanFramebuffer(Framebuffer):
    def __init__(self, width, height, attachments, transparent=False):
        super().__init__(width, height, dict(attachments))
        self.renderer = get_service("renderer")
        self._attachments = dict(attachments)
        self.images: dict[str, _Attachment] = {}
        self.color_names: list[str] = []
        self.depth_name: str | None = None
        for name, (att_type, _) in self._attachments.items():
            if att_type == AttachmentType.COLOR:
                self.color_names.append(name)
            elif self.depth_name is None:
                self.depth_name = name
            else:
                raise ValueError("A framebuffer can only have one depth/stencil attachment")
        self.draw_buffers = list(self.color_names)
        self._create_images()

    def _create_images(self):
        ctx = self.renderer.ctx
        for name, (att_type, att_format) in self._attachments.items():
            usage = COLOR_USAGE if att_type == AttachmentType.COLOR else DEPTH_USAGE
            gpu = GpuImage(ctx, self.width, self.height, FORMATS[att_format], usage)
            if name in self.images:
                self.renderer.defer_destroy(self.images[name].gpu)
                self.images[name].gpu = gpu
            else:
                self.images[name] = _Attachment(gpu)

    # -- the Framebuffer interface --------------------------------------------------

    def render_targets(self) -> list[GpuImage | None]:
        """One slot per color attachment, in declaration order - None where
        set_draw_buffers() left it out. Fragment output n always reaches
        attachment n, as GL44's GL_NONE-padded draw buffers do: the PBR
        pipeline's shaders write e.g. location 7 when only 'lit' is drawn."""
        drawn = set(self.draw_buffers)
        return [self.images[name].gpu if name in drawn else None for name in self.color_names]

    def depth_target(self) -> GpuImage | None:
        return self.images[self.depth_name].gpu if self.depth_name else None

    def bind(self):
        self.renderer.set_target(self, (self.width, self.height))

    def unbind(self):
        self.renderer.set_target(None, None)

    def set_draw_buffers(self, names: list[str]):
        for name in names:
            if name not in self.color_names:
                raise ValueError(f"No color attachment named '{name}'")
        self.draw_buffers = list(names)
        self.renderer.target_changed(self)

    def clear_color_attachment(self, name: str, value=(0.0, 0.0, 0.0, 0.0)):
        if name not in self._attachments:
            raise ValueError(f"No attachment named '{name}'")
        if self._attachments[name][0] != AttachmentType.COLOR:
            raise ValueError(f"Attachment '{name}' is not a color attachment")
        self.renderer.clear_attachment(self, name, value)

    def draw(self, attachment, size: tuple[int, int] = None):
        """Blits `attachment` onto the window, scaled to `size` - which,
        as with GL44's glBlitFramebuffer to framebuffer 0, means the
        window regardless of what's currently bound."""
        if attachment not in self._attachments:
            raise ValueError(f"No attachment named '{attachment}'")
        if self._attachments[attachment][0] != AttachmentType.COLOR:
            return  # GL44 doesn't draw depth attachments either
        size = (self.width, self.height) if size is None else size
        self.renderer.blit_to_window(self.images[attachment].gpu, size)

    def read(self, attachment_name: str):
        if attachment_name not in self._attachments:
            raise ValueError(f"No attachment named '{attachment_name}'")
        if self._attachments[attachment_name][0] != AttachmentType.COLOR:
            raise ValueError(f"Attachment '{attachment_name}' is not a color attachment")
        return self.renderer.read_image(self.images[attachment_name].gpu, as_float=True)

    def get_attachment_texture(self, attachment_name):
        if attachment_name in self.images:
            return self.images[attachment_name]
        fb_error(f'No attachment "{attachment_name}" on framebuffer: {self}')

    def resize(self, size: tuple[int, int]):
        self.width, self.height = int(size[0]), int(size[1])
        self.renderer.target_changed(self)
        self._create_images()
        if self.renderer.target is self:
            self.renderer.set_target(self, (self.width, self.height))

    def destroy(self):
        for attachment in self.images.values():
            self.renderer.defer_destroy(attachment.gpu)
