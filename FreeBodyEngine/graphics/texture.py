class Texture:
    """The texture object holds no real data, it just acts as a reference to the real texture in the manager."""
    def __init__(self, manager: 'TextureManager', id, uv_rect):
        self.manager = manager
        self.id = id
        self.uv_rect = uv_rect


    def get_image_data(self):
        return self.manager._get_raw_data(self.id, self.uv_rect)

    def use(self):
        self.manager._use_texture(self.id)

class TextureManager:
    def __init__(self):
        self.dev_mode = True # dev mode enables hot reloading, release mode uses atlases
        self.standalone_textures = []
        self.atlas_textures = []

        self.current_texture = None # the texture that is currently bound   

    def _create_texture(self, image_data, width, height) -> Texture:
        pass

    def _create_standalone_texture(self, image_data, width, height):
        """Gets a standalone texture."""
        pass

    def _get_raw_data(self, id, rect):
        pass

    def _use_texture(self, id):
        """Binds the texture."""
        pass

    def _create_atlas_texture(self):
        """Gets a texture from an atlas."""
        pass

    def _delete_texture(self):
        pass