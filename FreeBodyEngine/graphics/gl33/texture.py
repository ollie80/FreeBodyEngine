from FreeBodyEngine.graphics.texture import TextureManager, Texture, TextureStack, MAX_TEXTURE_STACK_SIZE
from FreeBodyEngine import warning, error
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
        
    def _create_texture_stack(self, rects):
        if len(rects) > MAX_TEXTURE_STACK_SIZE:
            error(f'Could not create texture stack becuase the max size was exceeded, size: {len(rects)}, max: {MAX_TEXTURE_STACK_SIZE}')
            return
    
    def _create_standalone_texture_stack(self, image_datas: list):
        if len(image_datas) > MAX_TEXTURE_STACK_SIZE:
            error(f'Could not create texture stack because the max size was exceeded, size: {len(image_datas)}, max: {MAX_TEXTURE_STACK_SIZE}')
            return
        
        max_width = 0
        max_height = 0
        processed_data = []

        loaded_images = []

        for data in image_datas:
            img = Image.open(io.BytesIO(data)).transpose(Image.Transpose.FLIP_TOP_BOTTOM).transpose(Image.Transpose.FLIP_LEFT_RIGHT).convert('RGBA')
            loaded_images.append(img)
            w, h = img.size
            if w > max_width:
                max_width = w
            if h > max_height:
                max_height = h

        for img in loaded_images:
            padded_img = Image.new('RGBA', (max_width, max_height), (0, 0, 0, 0))
            padded_img.paste(img, (0, 0))
            image_data = np.array(padded_img, dtype=np.uint8)
            processed_data.append(image_data)

        layers = len(image_datas)
        texture_id = glGenTextures(1)
        
        glBindTexture(GL_TEXTURE_2D_ARRAY, texture_id)

        glTexStorage3D(GL_TEXTURE_2D_ARRAY, 1, GL_RGBA8, max_width, max_height, layers)

        for layer, img_data in enumerate(processed_data):
            glTexSubImage3D(
                GL_TEXTURE_2D_ARRAY,
                0,              # mipmap level
                0, 0, layer,    # xoffset, yoffset, zoffset (layer index)
                max_width,
                max_height,
                1,              # depth (1 layer)
                GL_RGBA,
                GL_UNSIGNED_BYTE,
                img_data
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