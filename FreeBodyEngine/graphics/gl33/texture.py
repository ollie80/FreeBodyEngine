from FreeBodyEngine.graphics.texture import TextureManager, Texture, TextureStack, MAX_TEXTURE_STACK_SIZE
from FreeBodyEngine import warning
from FreeBodyEngine import error as fb_error
from OpenGL.GL import *
import numpy as np
from PIL import Image
import uuid
import io


class GLTextureManager(TextureManager):
    """The GL 3.3 implementation of TextureManager: owns the real GL texture
    objects behind every standalone/atlas/font-atlas/stack id, and does the
    actual `glActiveTexture`/`glBindTexture` slot bookkeeping (`texture_slots`/
    `slot_textures`/`next_texture_slot`) that maps an engine-side id to a live
    GPU texture unit for the current draw."""

    def __init__(self, *args, **kwargs):
        """Initializes the (empty) slot-tracking dicts and queries the
        driver's actual texture-unit limit (`GL_MAX_COMBINED_TEXTURE_IMAGE_UNITS`)
        into `max_texture_slots`, so `_allocate_slot` can refuse to overrun
        real hardware capacity instead of silently binding past it."""
        super().__init__(*args, **kwargs)

        self.texture_slots = {}
        self.slot_textures = {}
        self.next_texture_slot = 0
        self.max_texture_slots = glGetIntegerv(GL_MAX_COMBINED_TEXTURE_IMAGE_UNITS)

    def begin_draw(self):
        """Resets texture-unit allocation for a fresh draw: every
        previously-bound slot is forgotten and `next_texture_slot` restarts
        at 0. Called once per `GLShader.draw_mesh()` (see that method), so
        each mesh's material rebinds its textures from unit 0 rather than
        accumulating allocations across the whole frame - texture-buffer
        bindings a compute kernel manages itself (see GLComputeShader's own
        `_next_unit`) are deliberately independent of this and are never
        reset by it."""
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
        # Never set explicitly, this fell back to GL's actual spec default
        # for GL_TEXTURE_MIN_FILTER - GL_NEAREST_MIPMAP_LINEAR, which still
        # samples the nearest single texel within whichever mip level it
        # picks (only the *choice* of level is filtered, not the texels in
        # it). Any minified texture - an avatar shown smaller than its
        # source image, which is the normal case - looked visibly blocky
        # as a result. GL_LINEAR_MIPMAP_LINEAR (full trilinear) actually
        # blends both within and across mip levels.
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)

        id = self.gen_id()
        self.standalone_textures[id] = tex_id

        return Texture(self, id, (0, 0, 1, 1))

    def reload_standalone_texture(self, id, data):
        """Re-decodes `data` into the *same* GL texture this standalone
        Texture `id` already wraps (glTexImage2D on the existing tex_id,
        no glGenTextures) - every Material/Sprite holding a reference to
        the Texture object sees the new image with no extra wiring, since
        neither the engine-side `id` nor the underlying GL texture name
        changes. Used by dev-mode hot reload (core/files/hot_reload.py);
        not meaningful for an atlas-backed or font-atlas Texture, only one
        created by _create_standalone_texture()."""
        if id not in self.standalone_textures:
            warning(f"Cannot reload texture '{id}': it isn't a standalone texture.")
            return

        tex_id = self.standalone_textures[id]
        img = Image.open(io.BytesIO(data)).transpose(Image.Transpose.FLIP_TOP_BOTTOM).transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        image_data = np.array(img.convert('RGBA'), dtype=np.uint8)
        width, height = img.size

        glBindTexture(GL_TEXTURE_2D, tex_id)
        glTexImage2D(
            GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0,
            GL_RGBA, GL_UNSIGNED_BYTE, image_data
        )
        glGenerateMipmap(GL_TEXTURE_2D)

    def _create_font_atlas_texture(self, data) -> Texture:
        """Like _create_standalone_texture, but for an MSDF font atlas
        specifically: no mipmap chain, and clamped instead of repeated
        wrapping. An MSDF atlas's RGB channels only decode into a correct
        distance field under the median-of-3 reconstruction in text.fbfrag
        when sampled directly - any box-filtered minification (which is
        exactly what mipmapping is) blends *independent per-channel signed
        distances* together, which is not a meaningful operation and
        produces visible ghosting/noise around glyph edges once GL selects
        a blurred mip level (confirmed: this was the "text looks horrible"
        artifact, not a spacing or advance bug). MSDF's whole premise is
        resolution-independent rendering from one un-mipmapped bilinear
        sample, so this is correct rather than a quality tradeoff.
        CLAMP_TO_EDGE (vs. the default GL_REPEAT) additionally avoids any
        wraparound sampling at the atlas's outer border."""
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
        """Looks up `id`'s underlying GL texture and applies nearest- or
        linear-filtered sampling to both minification and magnification (see
        the inline comment below for why minification specifically uses the
        `_MIPMAP_NEAREST` variant rather than plain `GL_NEAREST`)."""
        target, texture = self._get_gl_texture(id)
        if texture is None:
            return

        glBindTexture(target, texture)
        # NEAREST_MIPMAP_NEAREST (not plain NEAREST) keeps mipmapping active
        # for minification, so a pixel-art sprite shrunk far away still
        # picks one crisp texel per pixel from a lower mip instead of
        # shimmering/aliasing - only magnification needs plain NEAREST to
        # get hard pixel edges instead of a blurred blend between texels.
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

            if width > max_width:
                max_width = width

            if height > max_height:
                max_height = height

        for img in loaded_images:
            padded_img = Image.new(
                'RGBA',
                (max_width, max_height),
                (0, 0, 0, 0)
            )

            padded_img.paste(img, (0, 0))

            image_data = np.array(padded_img, dtype=np.uint8)
            processed_data.append(image_data)

        layers = len(image_datas)

        texture_id = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D_ARRAY, texture_id)

        glTexStorage3D(
            GL_TEXTURE_2D_ARRAY,
            1,
            GL_RGBA8,
            max_width,
            max_height,
            layers
        )

        for layer, image_data in enumerate(processed_data):
            glTexSubImage3D(
                GL_TEXTURE_2D_ARRAY,
                0,
                0, 0, layer,
                max_width,
                max_height,
                1,
                GL_RGBA,
                GL_UNSIGNED_BYTE,
                image_data
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
            # See the identical fix in _create_standalone_texture - never
            # set explicitly, MIN_FILTER defaulted to GL's actual spec
            # default (GL_NEAREST_MIPMAP_LINEAR), which still nearest-
            # samples texels within a mip level and looks blocky whenever
            # a sprite is shown smaller than its source resolution.
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)

            id = self.gen_id()
            self.atlas_textures[id] = [tex_id, file_path]

        else:
            id = self.get_atlas_id_from_path(file_path)

        # The uploaded atlas image is flipped 180 degrees (top-bottom AND
        # left-right) above before it reaches the GPU, but `atlas_data[name]`
        # is a top-left-origin UV rect computed against the *original,
        # unflipped* atlas layout (build/atlas_gen.py's AtlasGen never sees
        # this flip). Left as-is, every sub-image would sample a rotated,
        # unrelated region of the atlas. A 180 degree rotation maps a rect's
        # origin from (x, y) to (1-x-w, 1-y-h); width/height are unchanged.
        x, y, w, h = atlas_data[name]
        rect = (1.0 - x - w, 1.0 - y - h, w, h)

        return Texture(self, id, rect)

    def get_atlas_id_from_path(self, file_path: str):
        """Reverse-looks-up the engine-side id already registered for the
        atlas at `file_path`, or None if that atlas hasn't been uploaded yet
        - used by `_create_atlas_texture` to dedupe repeated sub-images from
        the same atlas file onto one GL texture."""
        for atlas in self.atlas_textures:
            if self.atlas_textures[atlas][1] == file_path:
                return atlas

        return None

    def gen_id(self):
        """Generates a fresh unique engine-side texture id (a uuid4) to key
        one of `standalone_textures`/`atlas_textures`/`texture_stacks`."""
        return uuid.uuid4()

    def wrap_external_texture(self, gl_texture_id) -> Texture:
        """Registers a GL_TEXTURE_2D that wasn't created by this manager (e.g.
        a compute-dispatch FBO's color attachment) under a generated id, so it
        can flow through the same Texture/slot-binding machinery as any other
        texture - used by GLComputeShader.get_output_texture()."""
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
        """Resolves `id` to its underlying GL_TEXTURE_2D and allocates (or
        reuses) a texture unit for it via `_allocate_slot`, warning and
        returning None instead if `id` doesn't resolve to a real texture."""
        target, texture = self._get_gl_texture(id)

        if texture is None:
            warning(f"Cannot bind texture with id '{id}' as it doesn't exist.")
            return None

        return self._allocate_slot(id, target, texture)

    def bind_texture_stack(self, id):
        """Like bind_texture(), but for a GL_TEXTURE_2D_ARRAY-backed
        TextureStack id - allocates (or reuses) a texture unit for the whole
        array, not per-layer."""
        if id not in self.texture_stacks:
            warning(f"Cannot bind texture stack with id '{id}' as it doesn't exist.")
            return None

        return self._allocate_slot(
            id,
            GL_TEXTURE_2D_ARRAY,
            self.texture_stacks[id]
        )

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
