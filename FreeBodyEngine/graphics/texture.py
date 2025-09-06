from FreeBodyEngine import get_flag, DEVMODE
import numpy as np

MAX_TEXTURE_STACK_SIZE = 64

class Texture:
    """The texture object holds no real data, it just acts as a reference to the real texture in the manager."""
    def __init__(self, manager: 'TextureManager', id, uv_rect):
        self.manager = manager
        self.id = id
        self.uv_rect = uv_rect

    def get_image_data(self):
        return self.manager._get_raw_data(self.id, self.uv_rect)

    def use(self):
        return self.manager._use_texture(self.id)

class TextureStack:
    def __init__(self, manager: 'TextureManager', id: int, uv_rects: list[tuple[int, int]]):
        self.manager = manager
        self.uv_rects = np.array(uv_rects, dtype=np.float32).flatten()
        self.id = id

    def use(self):
        return self.manager._use_texture_stack(self.id)

class TextureManager:
    def __init__(self):
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

    def _create_atlas_texture(self):
        """Gets a texture from an atlas."""

    def _delete_texture(self):
        pass
    