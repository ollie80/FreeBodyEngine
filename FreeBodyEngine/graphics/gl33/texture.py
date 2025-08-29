from FreeBodyEngine.graphics.texture import TextureManager, Texture
from FreeBodyEngine import warning
from OpenGL.GL import *
import numpy as np
from PIL import Image
import uuid
import io

class GLTextureManager(TextureManager):
    def _create_standalone_texture(self, data) -> Texture:
        """Gets a standalone texture."""
        img: Image.Image = Image.open(io.BytesIO(data)).transpose(Image.Transpose.FLIP_TOP_BOTTOM).transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        image_data = np.array(img.convert('RGBA'), dtype=np.uint8)
        width, height = img.size

        tex_id = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, tex_id)

        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0,
                     GL_RGBA, GL_UNSIGNED_BYTE, image_data)
        glGenerateMipmap(GL_TEXTURE_2D)

        id = self.gen_id()
        self.standalone_textures[id] = tex_id
        return Texture(self, id, (0, 0, 1, 1))

    def _atlas_exists(self, file_path):
        for atlas in self.atlas_textures: 
            if atlas[1] == file_path: # file path
                return True
        return False
        
    def _create_atlas_texture(self, atlas_img, file_path, atlas_data, name):
        """Gets a texture from an atlas."""
        if not self._atlas_exists(file_path):
            img: Image.Image = Image.open(io.BytesIO(atlas_img)).transpose(Image.Transpose.FLIP_TOP_BOTTOM).transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            img_data = np.array(img.convert('RGBA'), dtype=np.uint8)
            width, height = img.size
            tex_id = glGenTextures(1)
        
            glBindTexture(GL_TEXTURE_2D, tex_id)

            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0,
                        GL_RGBA, GL_UNSIGNED_BYTE, img_data)
            glGenerateMipmap(GL_TEXTURE_2D);

            id = self.gen_id()
            self.atlas_textures[id] = [tex_id, file_path]

        else:
            id = self.get_atlas_id_from_path(file_path)

        return Texture(self, id, atlas_data[name])

    def get_atlas_id_from_path(self, file_path: str):
        for atlas in self.atlas_textures:
            if self.atlas_textures[atlas][1] == file_path:
                return atlas
        return None


    def gen_id(self):
        return uuid.uuid4()

    def _use_texture_stack(self, id):
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D_ARRAY, self.texture_stacks[id])
        

    def _use_texture(self, id):
        """Binds the texture."""
        glActiveTexture(GL_TEXTURE0)

        if id in self.standalone_textures:
            glBindTexture(GL_TEXTURE_2D, self.standalone_textures[id])
            self.current_texture = id

        elif id in self.atlas_textures:
            glBindTexture(GL_TEXTURE_2D, self.atlas_textures[id][0])
            self.current_texture = id
        
        else:
            warning(f"Cannot bind texture with id '{id}' as it doesn't exsist.")
        
        return 0


    def _delete_texture(self):
        pass