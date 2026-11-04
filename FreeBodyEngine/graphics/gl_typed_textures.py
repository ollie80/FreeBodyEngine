"""Volume, cube and shadow textures for the desktop GL backends.

GL33 and GL44 keep separate texture managers, but these three types work
identically on both - none of it changed between 3.3 and 4.4 - so the calls
live in one place and each manager mixes this in.

A shadow texture is the one with a catch. Comparison is sampler state in GL,
and the same depth image may also be read plainly elsewhere, so it can't go on
the texture object. A sampler object bound to the texture *unit* holds it
instead, and has to come off again when that unit is next given to something
else - see release_compare_sampler().
"""
import numpy as np
from OpenGL.GL import *

from FreeBodyEngine.graphics.texture import TextureCube, TextureShadow, TextureVolume, volume_pixels, cube_pixels


class GLTypedTextures:
    """Mixed into GLTextureManager and GL44TextureManager."""

    _compare_sampler = None
    _compare_slots = None

    def create_texture_volume(self, pixels) -> TextureVolume:
        data, width, height, depth, channels = volume_pixels(pixels)
        tex = glGenTextures(1)
        glBindTexture(GL_TEXTURE_3D, tex)
        previous = glGetIntegerv(GL_UNPACK_ALIGNMENT)
        glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
        internal, fmt = (GL_R8, GL_RED) if channels == 1 else (GL_RGBA8, GL_RGBA)
        glTexImage3D(GL_TEXTURE_3D, 0, internal, width, height, depth, 0, fmt, GL_UNSIGNED_BYTE, data)
        glPixelStorei(GL_UNPACK_ALIGNMENT, previous)
        glTexParameteri(GL_TEXTURE_3D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_3D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        for axis in (GL_TEXTURE_WRAP_S, GL_TEXTURE_WRAP_T, GL_TEXTURE_WRAP_R):
            glTexParameteri(GL_TEXTURE_3D, axis, GL_REPEAT)
        id = self.gen_id()
        self.typed_textures[id] = (GL_TEXTURE_3D, tex)
        return TextureVolume(self, id)

    def create_texture_cube(self, faces) -> TextureCube:
        data, size, is_float = cube_pixels(faces)
        tex = glGenTextures(1)
        glBindTexture(GL_TEXTURE_CUBE_MAP, tex)
        internal, kind = (GL_RGBA16F, GL_FLOAT) if is_float else (GL_RGBA8, GL_UNSIGNED_BYTE)
        for face in range(6):
            glTexImage2D(GL_TEXTURE_CUBE_MAP_POSITIVE_X + face, 0, internal, size, size, 0, GL_RGBA, kind, data[face])
        glGenerateMipmap(GL_TEXTURE_CUBE_MAP)
        glTexParameteri(GL_TEXTURE_CUBE_MAP, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR)
        glTexParameteri(GL_TEXTURE_CUBE_MAP, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        for axis in (GL_TEXTURE_WRAP_S, GL_TEXTURE_WRAP_T, GL_TEXTURE_WRAP_R):
            glTexParameteri(GL_TEXTURE_CUBE_MAP, axis, GL_CLAMP_TO_EDGE)
        # Filtering across face edges - what GLES 3 and Vulkan always do.
        # A switch only desktop GL has.
        try:
            glEnable(GL_TEXTURE_CUBE_MAP_SEAMLESS)
        except Exception:
            pass
        id = self.gen_id()
        self.typed_textures[id] = (GL_TEXTURE_CUBE_MAP, tex)
        return TextureCube(self, id)

    def wrap_shadow_texture(self, handle) -> TextureShadow:
        """`handle` is a depth attachment, from get_attachment_texture()."""
        handle = int(handle)
        for id, (target, tex) in self.typed_textures.items():
            if target == GL_TEXTURE_2D and tex == handle:
                return TextureShadow(self, id)
        id = self.gen_id()
        self.typed_textures[id] = (GL_TEXTURE_2D, handle)
        return TextureShadow(self, id)

    def bind_typed_texture(self, id):
        entry = self.typed_textures.get(id)
        if entry is None:
            return None
        target, tex = entry
        slot = self._allocate_slot(id, target, tex)
        if slot is not None and target == GL_TEXTURE_2D:
            self._bind_compare_sampler(slot)
        return slot

    def _bind_compare_sampler(self, slot):
        if self._compare_sampler is None:
            sampler = glGenSamplers(1)
            glSamplerParameteri(sampler, GL_TEXTURE_COMPARE_MODE, GL_COMPARE_REF_TO_TEXTURE)
            glSamplerParameteri(sampler, GL_TEXTURE_COMPARE_FUNC, GL_LEQUAL)
            glSamplerParameteri(sampler, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glSamplerParameteri(sampler, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glSamplerParameteri(sampler, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
            glSamplerParameteri(sampler, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
            self._compare_sampler = sampler
            self._compare_slots = set()
        glBindSampler(slot, self._compare_sampler)
        self._compare_slots.add(slot)

    def release_compare_sampler(self, slot):
        """A unit that last held a shadow texture is about to hold something
        else, which must not be read through its comparison sampler."""
        if self._compare_slots and slot in self._compare_slots:
            glBindSampler(slot, 0)
            self._compare_slots.discard(slot)

    def _delete_typed_texture(self, id):
        entry = self.typed_textures.pop(id, None)
        if entry is not None and entry[0] != GL_TEXTURE_2D:  # a shadow texture's image belongs to its framebuffer
            glDeleteTextures([entry[1]])
