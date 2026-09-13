from FreeBodyEngine import get_flag, DEVMODE
import numpy as np

MAX_TEXTURE_STACK_SIZE = 64

class Texture:
    """The texture object holds no real data, it just acts as a reference to the real texture in the manager."""
    def __init__(self, manager: 'TextureManager', id, uv_rect):
        """Stores the manager-owned `id` this Texture refers to, and the
        `uv_rect` selecting this texture's region within whatever atlas/
        standalone image that `id` resolves to."""
        self.manager = manager
        self.id = id
        self.uv_rect = uv_rect

    def get_image_data(self):
        """Returns this texture's region's raw pixel data, via the owning
        manager."""
        return self.manager._get_raw_data(self.id, self.uv_rect)

    def use(self):
        """Binds this texture for sampling and returns the texture unit it's
        now bound to."""
        return self.manager._use_texture(self.id)


def slice_texture_cell(texture: Texture, pos: 'list | tuple', grid: 'list | tuple') -> Texture:
    """Narrows a whole-image Texture down to one `[col, row]` cell of a
    `cols x rows` grid. (0, 0) is the top-left cell.

    Standalone/atlas textures are uploaded flipped on both axes (see
    GLTextureManager._create_standalone_texture), so a cell's rect has to be
    mirrored into that flipped space the same way whole-image atlas rects
    are (see the identical `1.0 - x - w` correction in
    GLTextureManager._create_atlas_texture) - otherwise every cell would
    sample a rotated, unrelated region of the sheet.
    """
    cols, rows = grid
    col, row = pos
    rx, ry, rw, rh = texture.uv_rect

    cw = rw / cols
    ch = rh / rows

    x = rx + cw * (cols - col - 1)
    y = ry + ch * (rows - row - 1)

    return Texture(texture.manager, texture.id, (x, y, cw, ch))

class TextureStack:
    """A fixed set of same-sized image layers uploaded as one texture-array
    resource (see TextureManager._create_texture_stack/
    _create_standalone_texture_stack), sampled by layer index from a shader.
    Unlike a plain Texture, one UV rect is kept per layer rather than a
    single rect for the whole thing."""
    def __init__(self, manager: 'TextureManager', id: int, uv_rects: list[tuple[int, int]]):
        """Stores the manager-owned `id` this stack refers to and its
        per-layer UV rects, reshaped to `(layers, 4)`."""
        self.manager = manager
        self.uv_rects = np.array(uv_rects, dtype=np.float32).reshape(-1, 4)
        self.id = id

    def use(self):
        """Binds this texture stack for sampling and returns the texture
        unit it's now bound to."""
        return self.manager._use_texture_stack(self.id)

class TextureManager:
    """Backend-agnostic owner of every texture resource (standalone images,
    atlas sub-images, MSDF font atlases, texture-array stacks). Concrete
    Texture/TextureStack objects only hold an opaque id back into here, so
    all real GPU-texture bookkeeping - creation, slot binding, hot reload,
    deletion - lives in one place, keyed off the backend-agnostic ids
    `gen_id()` generates."""
    def __init__(self):
        """Sets up the empty id -> GL-object tracking dicts a concrete
        backend fills in as textures/atlases/stacks are created."""
        self.dev_mode = get_flag(DEVMODE, False) # dev mode enables hot reloading, release mode uses atlases
        self.standalone_textures: dict[str, int] = {}
        self.texture_stacks: dict[str, int] = {}
        self.atlas_textures: dict[str, list[str, str]]= {} # {id, [graphicsID, fileID]}
        self.current_texture = None

    def _create_standalone_texture(self, image_data: str):
        """Gets a standalone texture."""
        pass

    def _create_standalone_texture_stack(self, image_data: list[str]) -> TextureStack:
        pass
    
    def _create_texture_stack(self, rects: tuple[int, tuple[float, float, float, float]]) -> TextureStack:
        pass

    def _get_raw_data(self, id, rect):
        pass

    def _use_texture_stack(self, id):
        pass

    def _use_texture(self, id):
        """Binds the texture and returns the texture slot."""
        pass

    def set_texture_filter(self, id, nearest: bool):
        """Switches a texture between nearest-neighbor sampling (crisp pixel
        art) and the default linear/mipmap filtering. Called every time a
        material using this texture is bound, since the same Texture may be
        shared by materials with different `filter` settings."""
        pass

    def _create_atlas_texture(self):
        """Gets a texture from an atlas."""

    def _delete_texture(self):
        pass
