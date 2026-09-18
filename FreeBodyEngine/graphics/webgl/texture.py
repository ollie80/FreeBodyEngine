import io
import uuid

import numpy as np
from PIL import Image as PILImage

from FreeBodyEngine.graphics.texture import TextureManager, Texture
from FreeBodyEngine.graphics.webgl.interop import to_typed_array
from FreeBodyEngine import warning, error as fb_error, get_service


class WebGL2TextureManager(TextureManager):
    """The WebGL2 implementation of TextureManager - see GLTextureManager's
    own docstring, same shape (standalone textures + a slot-allocation
    scheme mapping an engine-side id to a live texture unit for the
    current draw). Texture *stacks* (sampler2DArray - used for tilemap/
    sprite-sheet spritesheets, see graphics/texture.py's own docstring)
    aren't implemented yet for the web backend - `_create_texture_stack`/
    `_create_standalone_texture_stack`/`bind_texture_stack` raise a clear
    error instead of silently doing nothing, so a project that needs one
    finds out immediately rather than getting a blank texture at runtime."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.gl = get_service('renderer').gl

        self.texture_slots = {}
        self.slot_textures = {}
        self.next_texture_slot = 0
        self.max_texture_slots = self.gl.getParameter(self.gl.MAX_COMBINED_TEXTURE_IMAGE_UNITS)

    def begin_draw(self):
        """See GLTextureManager.begin_draw() - resets texture-unit
        allocation for a fresh draw call. Unlike the desktop GL33/GL44
        equivalents, this also does a REAL gl.bindTexture(..., None) on
        every unit the previous draw used, not just a Python-side
        bookkeeping reset. WebGL2 raises GL_INVALID_OPERATION ("Feedback
        loop formed between Framebuffer and active Texture") the moment
        ANY texture image unit still has a texture bound that is also one
        of the CURRENTLY bound draw framebuffer's attachments - even one
        the active program's samplers don't actually read this draw call
        (unlike desktop GL, which only cares about what's actually
        sampled). A framebuffer's own color/burn texture, once wrapped via
        wrap_external_texture() and sampled for a ping-pong effect (e.g.
        phonon's VisualizerPipeline reading last frame's output), gets a
        slot allocated on first use and - without a real unbind here -
        stays physically resident in that unit forever after. Once the
        ping-pong flips and that same framebuffer becomes the draw target
        again, its own texture is still sitting in some other unit and
        WebGL2 refuses to draw."""
        gl = self.gl
        for slot in range(self.next_texture_slot):
            gl.activeTexture(gl.TEXTURE0 + slot)
            gl.bindTexture(gl.TEXTURE_2D, None)

        self.texture_slots.clear()
        self.slot_textures.clear()
        self.next_texture_slot = 0

    def _decode_rgba(self, data: bytes):
        """Decodes `data` (an encoded image's raw bytes - PNG/JPEG/etc,
        via Pillow) into a flipped RGBA uint8 array, and returns it
        alongside (width, height). Flipped on both axes to match
        GLTextureManager._create_standalone_texture()'s own flip - the
        rest of the engine (UV rects, sprite flipping conventions) already
        assumes that flip, and a web build has to sample identically to a
        native one for the same asset."""
        img = PILImage.open(io.BytesIO(data)).transpose(PILImage.Transpose.FLIP_TOP_BOTTOM).transpose(PILImage.Transpose.FLIP_LEFT_RIGHT)
        image_data = np.array(img.convert('RGBA'), dtype=np.uint8)
        width, height = img.size
        return image_data, width, height

    def _create_standalone_texture(self, data) -> Texture:
        gl = self.gl
        image_data, width, height = self._decode_rgba(data)

        tex = gl.createTexture()
        gl.bindTexture(gl.TEXTURE_2D, tex)
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, width, height, 0, gl.RGBA, gl.UNSIGNED_BYTE, to_typed_array(image_data, dtype=np.uint8))
        gl.generateMipmap(gl.TEXTURE_2D)
        # See GLTextureManager._create_standalone_texture()'s own comment -
        # full trilinear filtering, not whatever the driver's un-set
        # default happens to be, so a minified texture doesn't look blocky.
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR)
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)

        id = self.gen_id()
        self.standalone_textures[id] = tex
        return Texture(self, id, (0, 0, 1, 1))

    def reload_standalone_texture(self, id, data):
        """See GLTextureManager.reload_standalone_texture() - re-decodes
        `data` into the same WebGL texture this id already wraps, for
        dev-mode hot reload."""
        if id not in self.standalone_textures:
            warning(f"Cannot reload texture '{id}': it isn't a standalone texture.")
            return

        gl = self.gl
        tex = self.standalone_textures[id]
        image_data, width, height = self._decode_rgba(data)

        gl.bindTexture(gl.TEXTURE_2D, tex)
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, width, height, 0, gl.RGBA, gl.UNSIGNED_BYTE, to_typed_array(image_data, dtype=np.uint8))
        gl.generateMipmap(gl.TEXTURE_2D)

    def _create_font_atlas_texture(self, data) -> Texture:
        """See GLTextureManager._create_font_atlas_texture()'s own
        docstring for why an MSDF atlas needs no mipmap chain and clamped
        wrapping - same reasoning applies unchanged."""
        gl = self.gl
        image_data, width, height = self._decode_rgba(data)

        tex = gl.createTexture()
        gl.bindTexture(gl.TEXTURE_2D, tex)
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, width, height, 0, gl.RGBA, gl.UNSIGNED_BYTE, to_typed_array(image_data, dtype=np.uint8))
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR)
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)

        id = self.gen_id()
        self.standalone_textures[id] = tex
        return Texture(self, id, (0, 0, 1, 1))

    def set_texture_filter(self, id, nearest: bool):
        """See GLTextureManager.set_texture_filter() - same
        NEAREST_MIPMAP_NEAREST-for-minification reasoning."""
        gl = self.gl
        target, texture = self._get_gl_texture(id)
        if texture is None:
            return

        gl.bindTexture(target, texture)
        gl.texParameteri(target, gl.TEXTURE_MIN_FILTER, gl.NEAREST_MIPMAP_NEAREST if nearest else gl.LINEAR_MIPMAP_LINEAR)
        gl.texParameteri(target, gl.TEXTURE_MAG_FILTER, gl.NEAREST if nearest else gl.LINEAR)

    def _create_texture_stack(self, rects):
        raise NotImplementedError(
            "Texture stacks (sampler2DArray) aren't supported by the web backend yet."
        )

    def _create_standalone_texture_stack(self, image_datas: list):
        raise NotImplementedError(
            "Texture stacks (sampler2DArray) aren't supported by the web backend yet."
        )

    def gen_id(self):
        """Generates a fresh unique engine-side texture id."""
        return uuid.uuid4()

    def wrap_external_texture(self, gl_texture) -> Texture:
        """Registers a WebGLTexture that wasn't created by this manager
        (e.g. a pipeline's own framebuffer color attachment - see
        WebGL2Framebuffer.get_attachment_texture()) under a generated id,
        so it can flow through the same Texture/slot-binding machinery as
        any other texture. Same use case as GLTextureManager's own
        wrap_external_texture() (a fullscreen-effect pipeline sampling its
        own previous frame - see phonon's VisualizerPipeline for the
        pattern this exists for)."""
        id = self.gen_id()
        self.standalone_textures[id] = gl_texture
        return Texture(self, id, (0, 0, 1, 1))

    def _get_gl_texture(self, id):
        if id in self.standalone_textures:
            return self.gl.TEXTURE_2D, self.standalone_textures[id]
        if id in self.atlas_textures:
            return self.gl.TEXTURE_2D, self.atlas_textures[id][0]
        return None, None

    def _allocate_slot(self, id, target, texture):
        gl = self.gl
        if id in self.texture_slots:
            return self.texture_slots[id]

        if self.next_texture_slot >= self.max_texture_slots:
            fb_error(
                f'Could not bind texture "{id}": '
                f'all {self.max_texture_slots} WebGL2 texture units are in use.'
            )
            return None

        slot = self.next_texture_slot
        self.next_texture_slot += 1

        self.texture_slots[id] = slot
        self.slot_textures[slot] = id

        gl.activeTexture(gl.TEXTURE0 + slot)
        gl.bindTexture(target, texture)

        return slot

    def bind_texture(self, id):
        """See GLTextureManager.bind_texture()."""
        target, texture = self._get_gl_texture(id)
        if texture is None:
            warning(f"Cannot bind texture with id '{id}' as it doesn't exist.")
            return None
        return self._allocate_slot(id, target, texture)

    def bind_texture_stack(self, id):
        raise NotImplementedError(
            "Texture stacks (sampler2DArray) aren't supported by the web backend yet."
        )

    def _use_texture_stack(self, id):
        return self.bind_texture_stack(id)

    def _use_texture(self, id):
        return self.bind_texture(id)

    def _delete_texture(self, id):
        gl = self.gl
        slot = self.texture_slots.pop(id, None)
        if slot is not None:
            self.slot_textures.pop(slot, None)

        if id in self.standalone_textures:
            gl.deleteTexture(self.standalone_textures[id])
            del self.standalone_textures[id]
        elif id in self.atlas_textures:
            gl.deleteTexture(self.atlas_textures[id][0])
            del self.atlas_textures[id]
