"""Identical to graphics/gl33/texture.py - ordinary 2D texture creation and
binding hasn't changed between GL 3.3 and 4.4. Kept as a separate copy
(rather than importing gl33's) so this backend has no runtime dependency on
gl33 at all, matching every other file in this module."""
from FreeBodyEngine.graphics.texture import TextureManager, Texture, TextureStack, MAX_TEXTURE_STACK_SIZE
from FreeBodyEngine import warning
from FreeBodyEngine import error as fb_error
from OpenGL.GL import *
import numpy as np
from PIL import Image
import uuid
import io


class GL44TextureManager(TextureManager):
    """The GL 4.4 implementation of TextureManager: creates standalone/atlas/
    font-atlas textures and texture-array stacks as real GL objects, and maps
    each one onto a GL texture unit on demand (see `_allocate_slot`) rather
    than binding every texture up front."""

    def __init__(self, *args, **kwargs):
        """Sets up the id<->texture-unit maps used to lazily assign GL
        texture units, and queries the driver's actual texture unit count
        (GL_MAX_COMBINED_TEXTURE_IMAGE_UNITS) rather than assuming the GL
        3.3-era minimum of 16, since 4.4 hardware/drivers commonly expose
        more."""
        super().__init__(*args, **kwargs)

        self.texture_slots = {}
        self.slot_textures = {}
        self.next_texture_slot = 0
        self.max_texture_slots = glGetIntegerv(GL_MAX_COMBINED_TEXTURE_IMAGE_UNITS)

    def begin_draw(self):
        """Resets the id<->texture-unit assignment for a new frame, so every
        texture bound last frame is re-allocated a (possibly different) unit
        as it's used again rather than assuming last frame's bindings are
        still valid."""
        self.texture_slots.clear()
        self.slot_textures.clear()
        self.next_texture_slot = 0

    def _create_standalone_texture(self, data) -> Texture:
        img = Image.open(io.BytesIO(data)).transpose(Image.Transpose.FLIP_TOP_BOTTOM).transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        image_data = np.array(img.convert('RGBA'), dtype=np.uint8)

        width, height = img.size

        tex_id = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, tex_id)

        glTexImage2D(
            GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0,
            GL_RGBA, GL_UNSIGNED_BYTE, image_data
        )

        glGenerateMipmap(GL_TEXTURE_2D)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)

        id = self.gen_id()
        self.standalone_textures[id] = tex_id

        return Texture(self, id, (0, 0, 1, 1))

    def _create_font_atlas_texture(self, data) -> Texture:
        img = Image.open(io.BytesIO(data)).transpose(Image.Transpose.FLIP_TOP_BOTTOM).transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        image_data = np.array(img.convert('RGBA'), dtype=np.uint8)

        width, height = img.size

        tex_id = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, tex_id)

        glTexImage2D(
            GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0,
            GL_RGBA, GL_UNSIGNED_BYTE, image_data
        )

        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)

        id = self.gen_id()
        self.standalone_textures[id] = tex_id

        return Texture(self, id, (0, 0, 1, 1))

    def set_texture_filter(self, id, nearest: bool):
        """Switches texture `id` between nearest-neighbor filtering (crisp
        pixel art, with mipmapping still enabled via
        GL_NEAREST_MIPMAP_NEAREST so minified sprites don't alias) and the
        default full-trilinear GL_LINEAR_MIPMAP_LINEAR/GL_LINEAR pair."""
        target, texture = self._get_gl_texture(id)
        if texture is None:
            return

        glBindTexture(target, texture)
        glTexParameteri(target, GL_TEXTURE_MIN_FILTER, GL_NEAREST_MIPMAP_NEAREST if nearest else GL_LINEAR_MIPMAP_LINEAR)
        glTexParameteri(target, GL_TEXTURE_MAG_FILTER, GL_NEAREST if nearest else GL_LINEAR)

    def _atlas_exists(self, file_path):
        for atlas in self.atlas_textures:
            if atlas[1] == file_path:
                return True
        return False

    def _create_texture_stack(self, rects):
        if len(rects) > MAX_TEXTURE_STACK_SIZE:
            fb_error(
                f'Could not create texture stack because the max size was exceeded, '
                f'size: {len(rects)}, max: {MAX_TEXTURE_STACK_SIZE}'
            )
            return

    def _create_standalone_texture_stack(self, image_datas: list):
        if len(image_datas) > MAX_TEXTURE_STACK_SIZE:
            fb_error(
                f'Could not create texture stack because the max size was exceeded, '
                f'size: {len(image_datas)}, max: {MAX_TEXTURE_STACK_SIZE}'
            )
            return

        max_width = 0
        max_height = 0
        processed_data = []
        loaded_images = []

        for data in image_datas:
            img = Image.open(data).transpose(
                Image.Transpose.FLIP_TOP_BOTTOM
            ).transpose(
                Image.Transpose.FLIP_LEFT_RIGHT
            ).convert('RGBA')

            loaded_images.append(img)

            width, height = img.size
            max_width = max(max_width, width)
            max_height = max(max_height, height)

        for img in loaded_images:
            padded_img = Image.new('RGBA', (max_width, max_height), (0, 0, 0, 0))
            padded_img.paste(img, (0, 0))
            processed_data.append(np.array(padded_img, dtype=np.uint8))

        layers = len(image_datas)

        texture_id = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D_ARRAY, texture_id)

        glTexStorage3D(GL_TEXTURE_2D_ARRAY, 1, GL_RGBA8, max_width, max_height, layers)

        for layer, image_data in enumerate(processed_data):
            glTexSubImage3D(
                GL_TEXTURE_2D_ARRAY, 0, 0, 0, layer,
                max_width, max_height, 1,
                GL_RGBA, GL_UNSIGNED_BYTE, image_data
            )

        glTexParameteri(GL_TEXTURE_2D_ARRAY, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D_ARRAY, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D_ARRAY, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D_ARRAY, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)

        glBindTexture(GL_TEXTURE_2D_ARRAY, 0)

        texture_stack_id = self.gen_id()
        self.texture_stacks[texture_stack_id] = texture_id

        uv_rects = [(0, 0, 1, 1) for _ in range(layers)]
        return TextureStack(self, texture_stack_id, uv_rects)

    def _create_atlas_texture(self, atlas_img, file_path, atlas_data, name):
        if not self._atlas_exists(file_path):
            img = Image.open(io.BytesIO(atlas_img)).transpose(
                Image.Transpose.FLIP_TOP_BOTTOM
            ).transpose(
                Image.Transpose.FLIP_LEFT_RIGHT
            )

            image_data = np.array(img.convert('RGBA'), dtype=np.uint8)
            width, height = img.size

            tex_id = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, tex_id)

            glTexImage2D(
                GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0,
                GL_RGBA, GL_UNSIGNED_BYTE, image_data
            )

            glGenerateMipmap(GL_TEXTURE_2D)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)

            id = self.gen_id()
            self.atlas_textures[id] = [tex_id, file_path]
        else:
            id = self.get_atlas_id_from_path(file_path)

        x, y, w, h = atlas_data[name]
        rect = (1.0 - x - w, 1.0 - y - h, w, h)

        return Texture(self, id, rect)

    def get_atlas_id_from_path(self, file_path: str):
        """Looks up the manager-owned id of the atlas GL texture that was
        built from `file_path`, or None if no atlas has been created from
        that file yet."""
        for atlas in self.atlas_textures:
            if self.atlas_textures[atlas][1] == file_path:
                return atlas
        return None

    def gen_id(self):
        """Generates a fresh backend-agnostic id for a new texture resource,
        independent of the underlying GL texture name."""
        return uuid.uuid4()

    def wrap_external_texture(self, gl_texture_id) -> Texture:
        """Registers a GL_TEXTURE_2D that wasn't created by this manager
        (e.g. a GL44ComputeShader dispatch's output texture, see
        GL44ComputeShader.get_output_texture()) under a generated id, so it
        can flow through the same Texture/slot-binding machinery as any
        other texture."""
        id = self.gen_id()
        self.standalone_textures[id] = gl_texture_id
        return Texture(self, id, (0, 0, 1, 1))

    def _get_gl_texture(self, id):
        if id in self.standalone_textures:
            return GL_TEXTURE_2D, self.standalone_textures[id]
        if id in self.atlas_textures:
            return GL_TEXTURE_2D, self.atlas_textures[id][0]
        return None, None

    def _allocate_slot(self, id, target, texture):
        if id in self.texture_slots:
            return self.texture_slots[id]

        if self.next_texture_slot >= self.max_texture_slots:
            fb_error(
                f'Could not bind texture "{id}": '
                f'all {self.max_texture_slots} OpenGL texture units are in use.'
            )
            return None

        slot = self.next_texture_slot
        self.next_texture_slot += 1

        self.texture_slots[id] = slot
        self.slot_textures[slot] = id

        glActiveTexture(GL_TEXTURE0 + slot)
        glBindTexture(target, texture)

        return slot

    def bind_texture(self, id):
        """Ensures standalone/atlas texture `id` is bound to some GL texture
        unit and returns that unit's index, reusing its existing unit if
        this frame already bound it (see `_allocate_slot`). Returns None
        (after warning) if `id` doesn't resolve to a live GL texture."""
        target, texture = self._get_gl_texture(id)
        if texture is None:
            warning(f"Cannot bind texture with id '{id}' as it doesn't exist.")
            return None
        return self._allocate_slot(id, target, texture)

    def bind_texture_stack(self, id):
        """Like `bind_texture`, but for a GL_TEXTURE_2D_ARRAY-backed
        TextureStack `id`."""
        if id not in self.texture_stacks:
            warning(f"Cannot bind texture stack with id '{id}' as it doesn't exist.")
            return None
        return self._allocate_slot(id, GL_TEXTURE_2D_ARRAY, self.texture_stacks[id])

    def _use_texture_stack(self, id):
        return self.bind_texture_stack(id)

    def _use_texture(self, id):
        return self.bind_texture(id)

    def _delete_texture(self, id):
        slot = self.texture_slots.pop(id, None)
        if slot is not None:
            self.slot_textures.pop(slot, None)

        if id in self.standalone_textures:
            glDeleteTextures([self.standalone_textures[id]])
            del self.standalone_textures[id]
        elif id in self.atlas_textures:
            glDeleteTextures([self.atlas_textures[id][0]])
            del self.atlas_textures[id]
        elif id in self.texture_stacks:
            glDeleteTextures([self.texture_stacks[id]])
            del self.texture_stacks[id]
