import json
import platform
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING
from importlib.resources import files

import PIL
from FreeBodyEngine import get_main, warning, error
from FreeBodyEngine.graphics.sprite import Sprite

if TYPE_CHECKING:
    from FreeBodyEngine.core.main import Main

import FreeBodyEngine.engine_assets
import os
import io

import struct


def read_assets(path):
    assets = {}
    with open(path, "rb") as f:
        while True:
            len_bytes = f.read(2)
            if not len_bytes:
                break
            name_len = struct.unpack("<H", len_bytes)[0]
            name = f.read(name_len).decode("utf-8")
            data_len = struct.unpack("<I", f.read(4))[0]
            data = f.read(data_len)
            assets[name] = data
    return assets


class FileManager:
    """
    The asset manager loads the files packaged by the engine. Uses paths that are relative to the asset folder specified in the build config.
    """
    def __init__(self, main: 'Main', path, dev):
        self.path: str = path
        self.engine_path = 'FreeBodyEngine'
        self.dev = dev
    
        if not self.dev:
            self.data: dict[str, str] = read_assets(os.path.join(path, "data.pak"))
            self.images: dict[str, str] = read_assets(os.path.join(path, "images.pak"))
        
            print(self.data.keys())
            self.atlas_map = self.create_atlas_map()

        self.main = main

    def get_file_path(self, path: str):
        n_path = path
        if path.startswith('engine'):
            n_path = n_path.removeprefix('engine/')
            n_path = files(FreeBodyEngine.engine_assets).joinpath(n_path)            
        else:
            n_path = (self.path) + '/' + path
        return os.path.abspath(n_path)

    def file_exsists(self, path):
        if self.dev:
            if os.path.exists(self.get_file_path(path)):
                return True
        else:

            if (path in self.images.keys()) or (path in self.data.keys()) or (path in self.atlas_map.keys()):
                return True


    def get_data_file(self, path, default = None):
        file = self.data.get(path, default)
        if file == None:
            error(f"File at path: '{path}' not found.")

    def load_shader_source(self, path: str):
        return self.load_data(path)

    def load_json(self, path: str):
        return json.loads(self.load_data(path))

    def load_toml(self, path: str):
        return tomllib.loads(self.load_data(path))

    def get_save_location(self):
        system = platform.system()
        
        if system == "Windows":
            base = os.getenv("APPDATA")
        elif system == "Darwin":
            base = os.path.expanduser("~/Library/Application Support")
        else:  # Linux and others
            base = os.getenv("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
        
        return os.path.join(base, self.main.name)

    def load_data(self, path: str, bytes: bool = False):
        if not self.dev:
            if path in self.data:
                raw_bytes = self.data[path]
                return raw_bytes if bytes else raw_bytes.decode("utf-8")
            else:
                raise FileExistsError(f"No data file at path '{path}'.")
        else:
            sys_path = self.get_file_path(path)
            if os.path.exists(sys_path):
                mode = "rb" if bytes else "r"
                with open(sys_path, mode) as f:
                    return f.read()
            else:
                raise FileExistsError(f"No data file at path '{sys_path}'.")

    def load_sound(self, path: str):
        data = self.load_data(path, bytes=True)
        return self.main.audio.create_sound(io.BytesIO(data))

    def load_material(self, path: str):
        """
        Load an '.fbmat' file.
        """
        data = self.load_toml(path)
        
        mat = self.main.graphics.load_material(data)
        return mat        

    def create_atlas_map(self):
        atlas_map = {}
        for image in self.images:
            atlas_path = image.removesuffix('.png')
            data: dict = self.load_json(atlas_path + '.json')
            for path in data:
                atlas_map[path] = atlas_path
        return atlas_map
            


    def find_image_atlas(self, path):
        atlas_path = self.atlas_map[path]
        atlas_img = self.images[atlas_path + ".png"]
        atlas_data = self.load_json(atlas_path + ".json")
        return atlas_img, atlas_data, atlas_path

    def load_image(self, path: str):
        if self.file_exsists(path):
            if self.dev:
                tex = self.main.graphics.renderer.texture_manager._create_standalone_texture(open(self.get_file_path(path), 'rb').read())
                return self.main.graphics.load_image(tex)
            else:
                atlas_img, atlas_data, atlas_path = self.find_image_atlas(path)
                
                tex = self.main.graphics.renderer.texture_manager._create_atlas_texture(atlas_img, atlas_path, atlas_data, path)
                return self.main.graphics.load_image(tex)
        else:
            raise FileExistsError(f"No image at path '{path}'.")


    def load_sprite(self, path: str):
        """
        Loads an .fbspr file.
        """
        data = self.load_toml(path)
        type = data.get('type', "static")
        if type == "static":
            img_path = data.get('image')
            if not img_path:
                raise ValueError(f'No image specified in sprite file "{path}".')
            image = self.load_image(img_path)
        
        mat_path = data.get('material')
        if not mat_path:
            raise ValueError(f'No material specified in sprite file "{path}".')
        mat = self.load_material(mat_path)

        visible = data.get('visible', True)
        z = data.get('z', 0)

        return Sprite(image, mat, self.main.renderer, visible, z)
