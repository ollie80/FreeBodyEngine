"""GPU images for the rasterizing side of the Vulkan backend - textures,
framebuffer attachments, the window's own color/depth target - plus the
Image wrapper the Renderer interface hands out.

Every GpuImage tracks the layout it was last transitioned to, so callers
just ask for the layout they need next (`image.transition(cmd, layout)`)
and the right barrier is emitted - the Vulkan equivalent of GL quietly
doing it for them.

All of these keep OpenGL's memory layout: row 0 is the *bottom* of the
picture. Textures are uploaded the way GL44TextureManager uploads them,
framebuffers are rendered without a flipped viewport, and only the final
copy to the swapchain flips - see renderer.py.
"""
import numpy as np
import vulkan as vk

from FreeBodyEngine.graphics.image import Image
from FreeBodyEngine.graphics.vulkan.context import Buffer

# layout -> (access mask, pipeline stage) for whatever last used / next uses it.
_LAYOUT_USE = {
    vk.VK_IMAGE_LAYOUT_UNDEFINED: (0, vk.VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT),
    vk.VK_IMAGE_LAYOUT_GENERAL: (vk.VK_ACCESS_MEMORY_READ_BIT | vk.VK_ACCESS_MEMORY_WRITE_BIT,
                                 vk.VK_PIPELINE_STAGE_ALL_COMMANDS_BIT),
    vk.VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL: (
        vk.VK_ACCESS_COLOR_ATTACHMENT_READ_BIT | vk.VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT,
        vk.VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT),
    vk.VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL: (
        vk.VK_ACCESS_DEPTH_STENCIL_ATTACHMENT_READ_BIT | vk.VK_ACCESS_DEPTH_STENCIL_ATTACHMENT_WRITE_BIT,
        vk.VK_PIPELINE_STAGE_EARLY_FRAGMENT_TESTS_BIT | vk.VK_PIPELINE_STAGE_LATE_FRAGMENT_TESTS_BIT),
    vk.VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL: (
        vk.VK_ACCESS_SHADER_READ_BIT,
        vk.VK_PIPELINE_STAGE_VERTEX_SHADER_BIT | vk.VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT
        | vk.VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT),
    vk.VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL: (vk.VK_ACCESS_TRANSFER_READ_BIT, vk.VK_PIPELINE_STAGE_TRANSFER_BIT),
    vk.VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL: (vk.VK_ACCESS_TRANSFER_WRITE_BIT, vk.VK_PIPELINE_STAGE_TRANSFER_BIT),
    vk.VK_IMAGE_LAYOUT_PRESENT_SRC_KHR: (0, vk.VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT),
}

DEPTH_FORMATS = {vk.VK_FORMAT_D32_SFLOAT, vk.VK_FORMAT_D32_SFLOAT_S8_UINT, vk.VK_FORMAT_D24_UNORM_S8_UINT}

# Bytes per pixel and channel count, for uploads and readbacks.
FORMAT_INFO = {
    vk.VK_FORMAT_R8_UNORM: (1, 1, np.uint8),
    vk.VK_FORMAT_R8G8B8A8_UNORM: (4, 4, np.uint8),
    vk.VK_FORMAT_A2B10G10R10_UNORM_PACK32: (4, 4, None),
    vk.VK_FORMAT_R16G16B16A16_SFLOAT: (8, 4, np.float16),
    vk.VK_FORMAT_R32G32B32A32_SFLOAT: (16, 4, np.float32),
    vk.VK_FORMAT_R32_SFLOAT: (4, 1, np.float32),
    vk.VK_FORMAT_R32G32_SFLOAT: (8, 2, np.float32),
    vk.VK_FORMAT_R32_SINT: (4, 1, np.int32),
}


def image_barrier(cmd, image, old_layout, new_layout, aspect, mip=0, mip_count=1, layers=1):
    src_access, src_stage = _LAYOUT_USE[old_layout]
    dst_access, dst_stage = _LAYOUT_USE[new_layout]
    vk.vkCmdPipelineBarrier(cmd, src_stage, dst_stage, 0, 0, None, 0, None, 1, [vk.VkImageMemoryBarrier(
        srcAccessMask=src_access, dstAccessMask=dst_access, oldLayout=old_layout, newLayout=new_layout,
        srcQueueFamilyIndex=vk.VK_QUEUE_FAMILY_IGNORED, dstQueueFamilyIndex=vk.VK_QUEUE_FAMILY_IGNORED,
        image=image, subresourceRange=vk.VkImageSubresourceRange(
            aspectMask=aspect, baseMipLevel=mip, levelCount=mip_count, baseArrayLayer=0, layerCount=layers))])


class GpuImage:
    def __init__(self, ctx, width: int, height: int, fmt: int, usage: int, mips: int = 1, layers: int = 1,
                 array_view: bool = False):
        self.ctx = ctx
        self.width, self.height = max(int(width), 1), max(int(height), 1)
        self.format, self.mips, self.layers = fmt, mips, layers
        if fmt in DEPTH_FORMATS:
            self.aspect = vk.VK_IMAGE_ASPECT_DEPTH_BIT
            self.view_aspect = vk.VK_IMAGE_ASPECT_DEPTH_BIT
            if fmt != vk.VK_FORMAT_D32_SFLOAT:
                self.aspect |= vk.VK_IMAGE_ASPECT_STENCIL_BIT
        else:
            self.aspect = self.view_aspect = vk.VK_IMAGE_ASPECT_COLOR_BIT
        self.is_depth = fmt in DEPTH_FORMATS
        self.handle = vk.vkCreateImage(ctx.device, vk.VkImageCreateInfo(
            imageType=vk.VK_IMAGE_TYPE_2D, format=fmt,
            extent=vk.VkExtent3D(width=self.width, height=self.height, depth=1),
            mipLevels=mips, arrayLayers=layers, samples=vk.VK_SAMPLE_COUNT_1_BIT,
            tiling=vk.VK_IMAGE_TILING_OPTIMAL, usage=usage, sharingMode=vk.VK_SHARING_MODE_EXCLUSIVE,
            initialLayout=vk.VK_IMAGE_LAYOUT_UNDEFINED), None)
        requirements = vk.vkGetImageMemoryRequirements(ctx.device, self.handle)
        self.memory = vk.vkAllocateMemory(ctx.device, vk.VkMemoryAllocateInfo(
            allocationSize=requirements.size,
            memoryTypeIndex=ctx.memory_type(requirements.memoryTypeBits, vk.VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT)), None)
        vk.vkBindImageMemory(ctx.device, self.handle, self.memory, 0)
        self.view = vk.vkCreateImageView(ctx.device, vk.VkImageViewCreateInfo(
            image=self.handle,
            viewType=vk.VK_IMAGE_VIEW_TYPE_2D_ARRAY if (layers > 1 or array_view) else vk.VK_IMAGE_VIEW_TYPE_2D,
            format=fmt, subresourceRange=vk.VkImageSubresourceRange(
                aspectMask=self.view_aspect, baseMipLevel=0, levelCount=mips, baseArrayLayer=0, layerCount=layers)),
            None)
        self.layout = vk.VK_IMAGE_LAYOUT_UNDEFINED

    def transition(self, cmd, layout):
        """Moves the image to `layout`, with the barrier that ordering
        needs. A no-op if it's already there - except between two uses as
        an attachment, which still need ordering, handled by the renderer
        when rendering begins."""
        if layout == self.layout:
            return
        image_barrier(cmd, self.handle, self.layout, layout, self.aspect, 0, self.mips, self.layers)
        self.layout = layout

    def upload(self, pixels: bytes, layer: int = 0, generate_mips: bool = False):
        """Copies tightly packed pixels (this image's format) into one layer
        and leaves the image ready to sample. Runs its own submission."""
        ctx = self.ctx
        staging = Buffer(ctx, len(pixels), vk.VK_BUFFER_USAGE_TRANSFER_SRC_BIT)
        staging.write(pixels)
        with ctx.commands() as cmd:
            self.transition(cmd, vk.VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL)
            vk.vkCmdCopyBufferToImage(cmd, staging.handle, self.handle, vk.VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, [
                vk.VkBufferImageCopy(bufferOffset=0, bufferRowLength=0, bufferImageHeight=0,
                                     imageSubresource=vk.VkImageSubresourceLayers(
                                         aspectMask=self.aspect, mipLevel=0, baseArrayLayer=layer, layerCount=1),
                                     imageOffset=vk.VkOffset3D(0, 0, 0),
                                     imageExtent=vk.VkExtent3D(self.width, self.height, 1))])
            if generate_mips and self.mips > 1:
                self._generate_mips(cmd)
            else:
                self.transition(cmd, vk.VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL)
        staging.destroy()

    def _generate_mips(self, cmd):
        """Downsamples level 0 into every smaller level with blits - what
        glGenerateMipmap does. Leaves the whole image SHADER_READ_ONLY."""
        w, h = self.width, self.height
        dst = vk.VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL
        src = vk.VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL
        read = vk.VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL
        for level in range(1, self.mips):
            image_barrier(cmd, self.handle, dst, src, self.aspect, level - 1, 1, self.layers)
            nw, nh = max(w // 2, 1), max(h // 2, 1)
            vk.vkCmdBlitImage(cmd, self.handle, src, self.handle, dst, 1, [vk.VkImageBlit(
                srcSubresource=vk.VkImageSubresourceLayers(aspectMask=self.aspect, mipLevel=level - 1,
                                                           baseArrayLayer=0, layerCount=self.layers),
                srcOffsets=[vk.VkOffset3D(0, 0, 0), vk.VkOffset3D(w, h, 1)],
                dstSubresource=vk.VkImageSubresourceLayers(aspectMask=self.aspect, mipLevel=level,
                                                           baseArrayLayer=0, layerCount=self.layers),
                dstOffsets=[vk.VkOffset3D(0, 0, 0), vk.VkOffset3D(nw, nh, 1)])], vk.VK_FILTER_LINEAR)
            image_barrier(cmd, self.handle, src, read, self.aspect, level - 1, 1, self.layers)
            w, h = nw, nh
        image_barrier(cmd, self.handle, dst, read, self.aspect, self.mips - 1, 1, self.layers)
        self.layout = read

    def destroy(self):
        if self.handle is not None:
            vk.vkDestroyImageView(self.ctx.device, self.view, None)
            vk.vkDestroyImage(self.ctx.device, self.handle, None)
            vk.vkFreeMemory(self.ctx.device, self.memory, None)
            self.handle = None


def mip_count(width: int, height: int) -> int:
    return max(int(np.floor(np.log2(max(width, height, 1)))) + 1, 1)


class VulkanImage(Image):
    """Same as GL44Image - an Image is just a view onto a Texture."""

    def get_size(self):
        return self.texture.uv_rect

    def get_data(self):
        return self.texture.get_image_data()
