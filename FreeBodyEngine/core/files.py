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
from FreeBodyEngine.graphics.image import Image
import os
import io

import struct

def load_sprite(path: str):
    if not get_main().headless_mode:
        return get_main().files.load_sprite(path)
    else:
        warning("Cannot load a sprite while in headless mode as it requires a renderer.")

def load_image(path: str):
    if not get_main().headless_mode:
        return get_main().files.load_image(path)
    else:
        warning("Cannot load an image while in headless mode as it requires a renderer.")

def load_material(path: str):
    if not get_main().headless_mode:
        return get_main().files.load_material(path)
    else:
        warning("Cannot load a material while in headless mode as it requires a renderer.")

def load_shader(path: str):
    if not get_main().headless_mode:
        return get_main().files.load_shader(path)
    else:
        warning("Cannot load a shader while in headless mode as it requires a renderer.")

def load_sprite(path: str):
    if not get_main().headless_mode:
        return get_main().files.load_sprite(path)
    else:
        warning("Cannot load a shader while in healess mode as it requires a renderer.")

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
            self.data = read_assets(path + "/data.pak")
            self.images = read_assets(path + "/images.pak")
        
        self.main = main
        # self.meshes = read_assets(path + "/meshes.pak")

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

            if (path in self.images.keys()) or (path in self.data.keys()):
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


    def load_data(self, path: str):
        if not self.dev:
            if path in self.data.keys():
                return io.BytesIO(self.data[path]).read().decode('UTF-8')
            else:
                raise FileExistsError(f"No data file at path '{path}'.")

        else:
            sys_path = self.get_file_path(path)
            if os.path.exists(sys_path):
                return open(sys_path).read()
            else:
                raise FileExistsError(f"No data file at path '{sys_path}'.")

    def load_material(self, path: str):
        """
        Load an '.fbmat' file.
        """
        data = self.load_toml(path)
        
        mat = self.main.graphics.load_material(data)
        return mat 

    def load_image(self, path: str):
        if self.file_exsists(path):
            if self.dev:
                return self.main.graphics.load_image(open(self.get_file_path(path), 'rb').read())
            else:
                return self.main.graphics.load_image(self.images[path])
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
