import json
from pathlib import Path
from typing import TYPE_CHECKING
import PIL
from FreeBodyEngine import get_main, warning

if TYPE_CHECKING:
    from FreeBodyEngine.core.main import Main
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

def load_sprite(path: str):
    return get_main().files.load_sprite(path)

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
    def __init__(self, path):
        self.path = path
        self.data = read_assets(path + "/data.pak")
        self.images = read_assets(path + "/images.pak")
        # self.meshes = read_assets(path + "/meshes.pak")

    def load_json(self, path: str):
        return json.loads(self.load_data(path))

    def load_data(self, path: str):
        if path in self.data.keys():
            return io.BytesIO(self.data[path]).read()
        else:
            raise FileExistsError(f"No data file at path '{path}'.")


    def load_sprite(self, path: str):
        """
        Loads an .fbspr file.
        """
        data = self.load_json(path)
        type = data.get('type', "static")
        
        if type == "static":    
            image = self.load_image()
            self.main.graphics.create_sprite()

    def load_image(self, path: str):
        if path in self.images.keys():
            return Image(self.images[path])
        else:
            raise FileExistsError(f"No image at path '{path}'.")
