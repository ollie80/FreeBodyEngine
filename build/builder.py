import os
import json
import subprocess
import shutil
from pathlib import Path
import sys

from FreeBodyEngine.build.atlas_gen import AtlasGen
import sys
import venv
import struct
import venv


SUPPORTED_PLATFORMS = ["windows", "darwin", "linux"]

FONT_FILE_TYPES = ["ttf"]
DATA_FILE_TYPES = ["txt", "json", "fbusl", "fbmat", "fbspr", 'mp3', 'wav', 'toml']
IMAGE_FILE_TYPES = ["png", "jpg", "jpeg"]
MESH_FILE_TYPES = ["fbx"]

GLOBAL_DEPENDENCIES = ["numpy"]
WINDOWS_DEPENDENCIES = ["pywin32", "PyOpenGL", "vulkan"]
DARWIN_DEPENDENCIES = ["cocoa", "PyOpenGL"]
LINUX_DEPENDENCIES = ["xlib", "PyOpenGL", "vulkan"]
WEB_DEPENDENCIES = ["pyodide"]

class Builder:
    def __init__(self):
        self.build_settings: dict = load_json('./build.json')
        
        args = sys.argv.copy()
        del args[0]

        self.atlas_generator = AtlasGen()

        self.platform = self.get_build_platform(args)

        self.dependencies = self.get_user_setting('dependencies') + self.get_platform_dependencies(self.platform) + GLOBAL_DEPENDENCIES
        
        self.asset_path = os.path.abspath(self.get_user_setting('assets'))
        self.code_path = os.path.abspath(self.get_user_setting('code'))
        self.build_path = os.path.abspath('./build/')
        self.temp_path = os.path.abspath('./build/temp/')
        
        self.output_path = os.path.abspath('./dist/')
        self.main_file = self.get_user_setting('main_file')

        if self.platform == "web" and not '--dev' in args:
            self.build_for_web()
        elif self.platform == "web":
            print("Cannot build for web in dev mode, building for your system platform instead.")

        if "--dev" in args:
            self.output_path = os.path.abspath('./dev/assets/')

            self.build_for_dev()
        else:
            self.build_for_release()

    def get_user_setting(self, name: str, default: any = None):
        res = self.build_settings.get(name, None)
        if res == None and default == None:
            raise ValueError(f"Value '{name}' not set in the build config.")
        elif res == None:
            return default
        else:
            return res
        
    def get_out_path(self, path: str, root_dir: str):
        """
        Converts a system path into an output path.
        """
        return os.path.abspath(path).removeprefix(root_dir + "\\")
    
    def get_platform_dependencies(self, platform: str):
        if platform == "windows":
            return WINDOWS_DEPENDENCIES
        return []

    def get_build_platform(self, args: list[str]):
        sys_plat = sys.platform
        if "--web" in args:
            return "web"

        elif sys_plat in SUPPORTED_PLATFORMS:                
            return sys_plat
        elif sys_plat == "win32":
            return 'windows'
            
        else:
            print("Current platform is not supported, aborting build.")

    def locate_assets(self): 
        images = []
        data = []
        meshes = []
        fonts = []
        for dir_path, _, file_names in os.walk(self.asset_path):
            for file_name in file_names:
                file_type = file_name.split('.')[1]
                file_path = dir_path + "/" + file_name
                if file_type in IMAGE_FILE_TYPES:
                    images.append(file_path)
                elif file_type in MESH_FILE_TYPES:
                    meshes.append(file_path)
                elif file_type in DATA_FILE_TYPES:
                    data.append(file_path)
                elif file_type in FONT_FILE_TYPES:
                    fonts.append(file_path)
        
        return images, data, meshes, fonts

    def bundle_assets(self, paths: list[str], name: str, root_dir: str):
        with open(f"{self.output_path}/{name}.pak", 'wb') as file:
            for path in paths:
                data = open(f"{path}", "rb").read()
                out_path = self.get_out_path(path, root_dir)
                file.write(struct.pack("<H", len(out_path)))
                file.write(out_path.encode("utf-8"))
                file.write(struct.pack("<I", len(data)))
                file.write(data)

    def convert_fonts(self, paths: list[str]) -> tuple[list[str], list[str]]:
        return [], []

    def reset_dirs(self):
        """Resets the build, temp, and dist directories."""
        shutil.rmtree(self.build_path)
        os.mkdir(self.build_path)
        os.mkdir(self.temp_path)

        shutil.rmtree(self.output_path)
        os.mkdir(self.output_path)

    def setup_venv(self):
        venv_path = os.path.abspath(self.build_path+"/venv/")
        venv.EnvBuilder(with_pip=True).create(venv_path)
        executable = os.path.abspath(venv_path + "/Scripts/python.exe")

        self.install_dependencies(executable)
        self.run_pyinstaller(executable)

    def install_dependencies(self, venv_executable):
        subprocess.check_call([venv_executable, "-m", "pip", "install", *self.dependencies])

    def run_pyinstaller(self, venv_executable):
        subprocess.check_call([venv_executable, "-m", "PyInstaller", "--onefile", "--name", "MyGame", "--windowed", self.main_file]) 

    def build_code(self):
        """
        Builds code into an execuatable usign pyinstaller.
        """
        self.setup_venv()
        self.install_dependencies()
        self.run_pyinstaller()

    def build_for_web(self, args):
        bundle = '--bundle' == args
        raise NotImplemented("Web builds not supported.")

    def build_for_release(self):
        images, data, meshes, fonts = self.locate_assets()
        self.atlas_generator.generate(images)
        #then write atlas metadata, and bundle

        self.bundle_assets(data, 'data', self.asset_path)
        
        self.bundle_assets(images, 'images', self.asset_path)
        self.bundle_assets(meshes, 'mesh', self.asset_path)
        
        font_paths = self.convert_font(fonts)
        self.bundle_assets(font_paths[0], 'data', self.temp_path)
        self.bundle_assets(font_paths[1], 'images', self.temp_path)

        self.build_code()
        print(f"Successfully built game for release, platform: {self.platform}.")


    def build_for_dev(self):        
        # font_paths = self.convert_fonts(fonts)
        # self.bundle_assets(font_paths[0], 'data', self.temp_path)
        # self.bundle_assets(font_paths[1], 'images', self.temp_path)

        print("Successfully built game for development.")

def get_relative_path(path: str, folder: str) -> str:
    full = Path(path)

    return full.relative_to(folder).as_posix()

def load_text(path: str):
    file = open(path, "r")
    text = file.read()
    file.close()
    return text

def load_json(path: str):
    txt = load_text(path)
    return json.loads(txt)


if __name__ == "__main__":
    builder = Builder()
    