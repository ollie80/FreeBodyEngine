"""VulkanTextureManager - the TextureManager interface on GpuImages.

Behaves like GL44TextureManager on purpose, down to uploading images
flipped on both axes and the atlas UV-rect arithmetic, because the rest of
the engine (slice_texture_cell, sample()'s uv_rect remap, sprites) was
written against exactly that. A texture here is a GpuImage plus how to
sample it (nearest or linear, mipmapped or not, repeat or clamp - the
GL defaults each creation path uses); resolve() hands both to a shader at
draw time, which is all GL's "bind to a texture unit" really was.
"""
import io
import uuid
from dataclasses import dataclass

import numpy as np
import vulkan as vk
from PIL import Image

from FreeBodyEngine import warning, error as fb_error, get_service
from FreeBodyEngine.graphics.texture import (TextureManager, Texture, TextureStack, MAX_TEXTURE_STACK_SIZE,
                                             decode_image_bytes)
from FreeBodyEngine.graphics.vulkan.image import GpuImage, mip_count

SAMPLED = vk.VK_IMAGE_USAGE_SAMPLED_BIT | vk.VK_IMAGE_USAGE_TRANSFER_DST_BIT | vk.VK_IMAGE_USAGE_TRANSFER_SRC_BIT


@dataclass
class _Entry:
    image: object  # a GpuImage, or an attachment wrapper exposing .gpu (see framebuffer.py)
    mipmapped: bool = False
    nearest: bool = False
    clamp: bool = False
    kind: str = "2d"  # or "array"

    @property
    def gpu(self) -> GpuImage:
        return getattr(self.image, "gpu", self.image)


class VulkanTextureManager(TextureManager):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.entries: dict = {}
        self._samplers: dict = {}
        self._stream_sizes: dict = {}

    # -- samplers -----------------------------------------------------------------

    def sampler(self, nearest: bool, mipmapped: bool, clamp: bool):
        key = (nearest, mipmapped, clamp)
        if key not in self._samplers:
            filt = vk.VK_FILTER_NEAREST if nearest else vk.VK_FILTER_LINEAR
            mode = vk.VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE if clamp else vk.VK_SAMPLER_ADDRESS_MODE_REPEAT
            self._samplers[key] = vk.vkCreateSampler(self.ctx.device, vk.VkSamplerCreateInfo(
                magFilter=filt, minFilter=filt,
                mipmapMode=vk.VK_SAMPLER_MIPMAP_MODE_NEAREST if nearest else vk.VK_SAMPLER_MIPMAP_MODE_LINEAR,
                addressModeU=mode, addressModeV=mode, addressModeW=mode,
                maxLod=1000.0 if mipmapped else 0.0, borderColor=vk.VK_BORDER_COLOR_FLOAT_OPAQUE_WHITE), None)
        return self._samplers[key]

    def resolve(self, id):
        """(GpuImage, VkSampler) for texture `id`, or (None, None)."""
        entry = self.entries.get(id)
        if entry is None:
            return None, None
        return entry.gpu, self.sampler(entry.nearest, entry.mipmapped, entry.clamp)

    # -- creation ------------------------------------------------------------------

    def gen_id(self):
        return uuid.uuid4()

    @staticmethod
    def _decode(data) -> Image.Image:
        """RGBA, rotated 180 degrees as every backend uploads it - through
        decode_image_bytes, so .fbimg files work here too."""
        pixels, width, height = decode_image_bytes(data)
        return Image.fromarray(np.ascontiguousarray(pixels, dtype=np.uint8).reshape(height, width, 4), "RGBA")

    def _upload_rgba(self, img, mipmapped: bool, size=None) -> GpuImage:
        """`img`: a PIL image, or raw RGBA pixels with `size` = (width, height)."""
        width, height = size or img.size
        mips = mip_count(width, height) if mipmapped else 1
        gpu = GpuImage(self.ctx, width, height, vk.VK_FORMAT_R8G8B8A8_UNORM, SAMPLED, mips=mips)
        gpu.upload(np.asarray(img, dtype=np.uint8).tobytes(), generate_mips=mipmapped)
        return gpu

    def create_texture_from_pixels(self, image_data, width: int, height: int) -> Texture:
        """A standalone texture from already-decoded RGBA pixels (see
        decode_image_bytes) - what GL44TextureManager offers for loaders
        that decode on a thread pool."""
        if isinstance(image_data, (bytes, bytearray)):
            image_data = np.frombuffer(image_data, dtype=np.uint8)
        gpu = self._upload_rgba(image_data, mipmapped=True, size=(int(width), int(height)))
        return self._add(_Entry(gpu, mipmapped=True))

    def _add(self, entry: _Entry, uv_rect=(0, 0, 1, 1)) -> Texture:
        id = self.gen_id()
        self.entries[id] = entry
        self.standalone_textures[id] = entry  # what the base class and callers check membership against
        return Texture(self, id, uv_rect)

    def _create_standalone_texture(self, data) -> Texture:
        return self._add(_Entry(self._upload_rgba(self._decode(data), mipmapped=True), mipmapped=True))

    def _create_font_atlas_texture(self, data) -> Texture:
        return self._add(_Entry(self._upload_rgba(self._decode(data), mipmapped=False), clamp=True))

    def reload_standalone_texture(self, id, data):
        """Dev-mode hot reload: same id, new pixels."""
        entry = self.entries.get(id)
        if entry is None:
            return
        old = entry.image
        entry.image = self._upload_rgba(self._decode(data), mipmapped=entry.mipmapped)
        self._retire(old)

    def _atlas_exists(self, file_path):
        return any(v[1] == file_path for v in self.atlas_textures.values())

    def get_atlas_id_from_path(self, file_path: str):
        for atlas_id, (_, path) in self.atlas_textures.items():
            if path == file_path:
                return atlas_id
        return None

    def _create_atlas_texture(self, atlas_img, file_path, atlas_data, name):
        if not self._atlas_exists(file_path):
            entry = _Entry(self._upload_rgba(self._decode(atlas_img), mipmapped=True), mipmapped=True)
            id = self.gen_id()
            self.entries[id] = entry
            self.atlas_textures[id] = [entry, file_path]
        else:
            id = self.get_atlas_id_from_path(file_path)
        x, y, w, h = atlas_data[name]
        # Mirrored into the flipped upload's space, as GL44TextureManager does.
        return Texture(self, id, (1.0 - x - w, 1.0 - y - h, w, h))

    def _create_texture_stack(self, rects):
        if len(rects) > MAX_TEXTURE_STACK_SIZE:
            fb_error(f"Could not create texture stack because the max size was exceeded, size: {len(rects)}, "
                     f"max: {MAX_TEXTURE_STACK_SIZE}")

    def _create_standalone_texture_stack(self, image_datas: list) -> TextureStack | None:
        if len(image_datas) > MAX_TEXTURE_STACK_SIZE:
            fb_error(f"Could not create texture stack because the max size was exceeded, "
                     f"size: {len(image_datas)}, max: {MAX_TEXTURE_STACK_SIZE}")
            return None
        images = [self._decode(d) for d in image_datas]
        width = max(i.size[0] for i in images)
        height = max(i.size[1] for i in images)
        gpu = GpuImage(self.ctx, width, height, vk.VK_FORMAT_R8G8B8A8_UNORM, SAMPLED, layers=len(images),
                       array_view=True)
        for layer, img in enumerate(images):
            padded = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            padded.paste(img, (0, 0))
            gpu.upload(np.asarray(padded, dtype=np.uint8).tobytes(), layer=layer)
        id = self.gen_id()
        self.entries[id] = _Entry(gpu, clamp=True, kind="array")
        self.texture_stacks[id] = self.entries[id]
        return TextureStack(self, id, [(0, 0, 1, 1)] * len(images))

    def wrap_external_texture(self, handle) -> Texture:
        """`handle` is a framebuffer attachment (get_attachment_texture()),
        a GpuImage, or a compute kernel's StorageImage."""
        return self._add(_Entry(handle))

    # -- streaming (video frames) ---------------------------------------------------

    def create_stream_texture(self, width: int, height: int, channels: int = 3) -> Texture:
        gpu = GpuImage(self.ctx, width, height, vk.VK_FORMAT_R8G8B8A8_UNORM, SAMPLED)
        texture = self._add(_Entry(gpu, clamp=True))
        self._stream_sizes[texture.id] = (width, height, channels)
        gpu.upload(bytes(width * height * 4))
        return texture

    def update_stream_texture(self, id, pixels) -> bool:
        if id not in self._stream_sizes:
            warning(f"Cannot stream into texture '{id}': it isn't a stream texture.")
            return False
        width, height, channels = self._stream_sizes[id]
        if len(pixels) != width * height * channels:
            warning(f"Stream texture '{id}' wants {width * height * channels} bytes, got {len(pixels)}.")
            return False
        data = np.frombuffer(bytes(pixels), np.uint8).reshape(height, width, channels)
        if channels == 3:
            data = np.concatenate([data, np.full((height, width, 1), 255, np.uint8)], axis=2)
        renderer = get_service("renderer")
        renderer.before_upload(self.entries[id].gpu)
        self.entries[id].gpu.upload(np.ascontiguousarray(data).tobytes())
        return True

    def delete_stream_texture(self, id):
        self._stream_sizes.pop(id, None)
        self._delete_texture(id)

    # -- binding / state -----------------------------------------------------------

    def begin_draw(self):
        pass  # no texture units to recycle

    def bind_texture(self, id):
        """Kept for interface parity - there are no texture units, so this
        only reports whether the texture exists (as a slot-like int)."""
        if id not in self.entries:
            warning(f"Cannot bind texture with id '{id}' as it doesn't exist.")
            return None
        return 0

    def bind_texture_stack(self, id):
        return self.bind_texture(id)

    def _use_texture(self, id):
        return self.bind_texture(id)

    def _use_texture_stack(self, id):
        return self.bind_texture(id)

    def set_texture_filter(self, id, nearest: bool):
        entry = self.entries.get(id)
        if entry is not None:
            entry.nearest = bool(nearest)

    def _get_raw_data(self, id, rect):
        entry = self.entries.get(id)
        if entry is None:
            return None
        return get_service("renderer").read_image(entry.gpu)

    # -- deletion ------------------------------------------------------------------

    def _retire(self, image):
        if isinstance(image, GpuImage):
            get_service("renderer").defer_destroy(image)

    def _delete_texture(self, id):
        entry = self.entries.pop(id, None)
        self.standalone_textures.pop(id, None)
        self.atlas_textures.pop(id, None)
        self.texture_stacks.pop(id, None)
        if entry is not None:
            self._retire(entry.image)

    def destroy(self):
        for sampler in self._samplers.values():
            vk.vkDestroySampler(self.ctx.device, sampler, None)
        for entry in self.entries.values():
            if isinstance(entry.image, GpuImage):
                entry.image.destroy()
        self.entries.clear()
