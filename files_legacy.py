import json
import platform
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING
from FreeBodyEngine.utils import abstractmethod
from importlib.resources import files


import PIL
from FreeBodyEngine import get_main, warning, error, get_flag, get_service, DEVMODE, PROJECT_PATH, ALLOW_DISK_WRITE
from FreeBodyEngine.graphics.sprite import Sprite
from FreeBodyEngine.graphics.material import Material
from FreeBodyEngine.core.service import Service
from FreeBodyEngine.utils import get_platform
from FreeBodyEngine.graphics.model.gltf_parser import GLBParser, GLTFParser
from FreeBodyEngine.graphics.model import Model

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

class FileSystem:
    @abstractmethod
    def read(self, path: str, start:int=0, end:int=-1) -> bytes:
        """
        Reads bytes from the start position to the end position.
        
        :param path: The file path.
        :type path: str

        :param start: The starting offset in bytes.
        :type start: int

        :param end: The end position in bytes, setting it to -1 will read all bytes.
        :type end: int 
        """
        pass

    @abstractmethod
    def write(self, path: str, data: bytes):
        """
        Sets the bytes in the file at the given path, returns true if operation was successful, false if not.

        :param path: The path of the file.
        :type path: str

        :param data: The data that will be put in the file.
        :type data: bytes

        :rtype: bool
        """
        pass

    @abstractmethod
    def create_file(self, path: str) -> bool:
        """
        Creates a file at the path. Returns true if file creation was successful, else false.

        :param path: 
        """

    @abstractmethod
    def create_directory(self, path: str, recursive=False) -> bool:
        pass

    @abstractmethod
    def exists(self, path: str) -> bool:
        """
        Checks if the file at the given path exists.
        
        :param path: The file path.
        :type path: str
        """
        pass

class AssetPackFileSystem(FileSystem):
    def __init__(self, settings: dict):
        self.settings = settings
        
    def open_stream(self) -> FileStream:
        pass        

    def read(self, path:str, start:int=0, end:int=-1):
        """
        
        """
        if self.exists(path):
            with open(path) as f:
                f.seek(start)
                read_size = start-end
                if end == -1:
                    read_size = -1
                data = f.read(read_size)
                f.close()
                return data
        return bytes()

    def write(self, path, data):
        if get_flag(ALLOW_DISK_WRITE, True):
            if self.exists(path):
                return True
            
            else:
                creation_successful = self.create_file(path)
                
                if creation_successful:
                    return True
                
                warning(f"Could write to file at path {path}, file creation failed.")

        else:
            warning(f'Could not write to file, at path {path}, disk writes disabled.')

class VirtualFileSystem(FileSystem):
    def __init__(self, path: str):
        self.path = path
        
    def exists(self, path):
        if get_platform() in ['darwin', 'linux', 'windows']:
            return os.path.exists(path)
        
    def read(self, path: str, start:int=0,end:int=-1):
        platform = get_platform()
        
        if platform in ['win32', 'darwin', 'linux']:
            with open(path, 'rb') as f:
                f.seek(start)
                size = start-end
                if end == -1:
                    size = None
                data = f.read(size)
                f.close()
                return data

    def write(self, path: str, data: bytes):
        if get_flag(ALLOW_DISK_WRITE, False):
            with open(path, 'wb') as f:
                f.write(data)
                f.close()
        else:
            warning(f'Could not write to file, at path {path}, disk writes disabled.')

    def create_file(self, path):
        pass

    def create_directory(self, path, recursive=False):
        pass        

class FileManager(Service):
    """
    The asset manager loads the files packaged by the engine. Uses paths that are relative to the asset folder specified in the build config.
    """
    def __init__(self):
        super().__init__('files')
        path = get_flag(PROJECT_PATH, './')
        self.dev = get_flag(DEVMODE, False)

        if self.dev:
            self.file_system = VirtualFileSystem('./assets')
            if os.path.exists(os.path.join(path, 'fbproject.toml')): 
                build_settings = tomllib.loads(open(os.path.join(path, 'fbproject.toml')).read())
                self.path = os.path.join(path, build_settings.get('assets', './assets'))
                self.game_name = build_settings.get('name')

        else:
            if system_path_exists('./assets.fbap'):    
                self.file_system = AssetPackFileSystem(self.parse_asset_pack('./assets.fbap'))
                self.path = './assets'        

        self.engine_path = 'FreeBodyEngine'
    
        if not self.dev:
            self.asset_pack_path = system_abs_path('./assets.fbap')
            self.atlas_map = self.create_atlas_map()

    def parse_asset_pack(self, path: str):        
        header = system_read_bytes(path, 0, 3).decode('utf-8')
        
        if not header == ASSET_PACK_HEADER:
            error(f'Asset Pack header invalid, expected "{ASSET_PACK_HEADER}", got "{header}".')
        
        print(header)

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
        
        return os.path.join(base, self.game_name)

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
        return get_service('audio').create_sound(io.BytesIO(data))

    def load_material(self, path: str, injector=None) -> Material:
        """
        Load an '.fbmat' file.
        """
        data = self.load_toml(path)
        
        mat = get_service('graphics').create_material(data, injector)
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
                tex = get_service('renderer').texture_manager._create_standalone_texture(open(self.get_file_path(path), 'rb').read())
                return get_service('renderer').load_image(tex)
            else:
                atlas_img, atlas_data, atlas_path = self.find_image_atlas(path)
                
                tex = get_service('renderer').texture_manager._create_atlas_texture(atlas_img, atlas_path, atlas_data, path)
                return get_service('renderer').load_image(tex)
        else:
            raise FileExistsError(f"No image at path '{path}'.")

    def load_texture_stack(self, paths: list[str]):
        if all(self.file_exsists(x) for x in paths):
            if self.dev:
                tex = get_service('renderer').texture_manager._create_standalone_texture_stack([io.BytesIO(self.file_system.read(self.get_file_path(path))) for path in paths])
                return tex
            else:
                return

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

        return Sprite(image, mat, get_service('renderer'), visible, z)

    def load_model(self, path: str, model_name: str = None, scale=None) -> Model:
        s = path.split('.')
        file_type = s[len(s)-1]
        if file_type == 'gltf':
            data = self.load_json(path)
            
            bin_path = path.removesuffix('.gltf') + '.bin'
            bin_data = self.load_data(bin_path, True)
            
            parser = GLTFParser(data, bin_data)
            return parser.build_model(model_name, get_service('graphics'), get_service('renderer'), scale)


        elif file_type == 'glb':
            data = self.load_data(path, True)
            glb_parser = GLBParser(data)

            gltf_parser = GLTFParser(glb_parser.get_json(), glb_parser.get_binary_buffer())
            return gltf_parser.build_model(model_name, get_service('graphics'), get_service('renderer'))
        

def system_path_exists(path: str):
    plat = get_platform()
    if plat in ['darwing', 'win32', 'linux']:
        return os.path.exists(path)

def system_write(path: str, data: str):
    """Writes data to the file at the path."""
    if system_path_exists(path):
        plat = get_platform()
        if plat in ['darwin', 'win32', 'linux']:
            open(path, data)
         
def system_read_bytes(path: str, start=0, end=-1):
    plat = get_platform()
    if plat in ['darwin', 'win32', 'linux']:    
        with open(path, 'rb') as f:
            f.seek(start)
            return f.read(end - start + 1) if end > -1 else f.read()

def system_read_text(path: str, start=-1, end=-1):
    plat = get_platform()
    if plat in ['darwin', 'win32', 'linux']:
        with open(path, 'r') as f:
            f.seek(start)
            return f.read(end - start + 1) if end > -1 else f.read()

def system_abs_path(path: str):
    plat = get_platform()
    if plat in ['win32', 'linux', 'darwin']:
        os.path.abspath(path)