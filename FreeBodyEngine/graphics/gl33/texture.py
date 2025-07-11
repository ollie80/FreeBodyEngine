from FreeBodyEngine.graphics.texture import TextureManager, Texture
from FreeBodyEngine import warning
from OpenGL.GL import *
import numpy as np

class GLTextureManager(TextureManager):
    def _create_texture(self, internal_image) -> Texture:
        img_data = np.array(internal_image.convert('RGBA'), dtype=np.uint8)
        width, height = internal_image.size
        if self.dev_mode:
            id, uv_rect = self._create_standalone_texture(img_data, width, height)
            return Texture(self, id, uv_rect)

    def _create_standalone_texture(self, image_data, width, height):
        """Gets a standalone texture."""
        tex_id = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, tex_id)

        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0,
                     GL_RGBA, GL_UNSIGNED_BYTE, image_data)
        glGenerateMipmap(GL_TEXTURE_2D);

        self.standalone_textures.append(tex_id)
        return tex_id, (0, 0, 1, 1)
        

    def _use_texture(self, id):
        """Binds the texture."""
        glActiveTexture(GL_TEXTURE0)

        if id in self.standalone_textures:
            glBindTexture(GL_TEXTURE_2D, id)
            self.current_texture = id
        elif id in self.atlas_textures:
            glBindTexture(GL_TEXTURE_2D, id)
            self.current_texture = id
        else:
            warning(f"Cannot bind texture with id '{id}' as it doesn't exsist.")        
        
        return 0

    def _create_atlas_texture(self):
        """Gets a texture from an atlas."""
        pass

    def _delete_texture(self):
        pass