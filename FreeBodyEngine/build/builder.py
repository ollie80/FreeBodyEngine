import importlib.resources
import os
import json
import tomllib
import subprocess
import shutil
from pathlib import Path
import sys

import FreeBodyEngine.lib
import sys
import venv
import struct
import venv
import importlib
from FreeBodyEngine.font.atlasgen import generate_atlas
from FreeBodyEngine.build.atlas_gen import AtlasGen
from FreeBodyEngine import requirements as fb_requirements

SUPPORTED_PLATFORMS = ["windows", "darwin", "linux"]

FONT_FILE_TYPES = ["ttf"]
DATA_FILE_TYPES = ["txt", "json", "fbusl", "fbvert", "fbfrag", "fbmat", "fbspr", 'mp3', 'wav', 'toml']
IMAGE_FILE_TYPES = ["png", "jpg", "jpeg"]
MESH_FILE_TYPES = ["fbx"]
FONT_SIZE = 16

class Builder:
    def __init__(self, path, dev):
        self.build_settings: dict = load_toml(f'{path}/fbproject.toml')
        
        args = sys.argv.copy()
        del args[0]


        self.platform = self.get_build_platform(args)

        self.dependencies: list[str] = self.get_user_setting('dependencies') + self.get_platform_dependencies(self.platform)
        self.dependencies.append("pyinstaller")

        self.asset_path = os.path.abspath(os.path.join(path, self.get_user_setting('assets')))
        self.code_path = os.path.abspath(os.path.join(path, self.get_user_setting('code')))
        self.build_path = os.path.abspath(f'{path}/build/')
        self.temp_path = os.path.abspath(f'{path}/build/temp/')
        self.cache_path = os.path.join(self.build_path, "cache.json")
        
        self.output_path = os.path.abspath(f'{path}/dist/')
        self.asset_out_path = os.path.join(self.output_path, 'assets')
        self.main_file = os.path.abspath(os.path.join(path, self.get_user_setting('main_file')))
        
        self.build_cache = self.get_build_cache()

        if self.platform == "web" and not dev:
            self.build_for_web()
        elif self.platform == "web":
            print("Cannot build for web in dev mode, building for your system platform instead.")

        if dev:
            self.output_path = os.path.abspath(f'{path}/dev/assets/')

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

        requirements = [] 
        requirements += fb_requirements.GLOBAL

        if platform == "windows":
            requirements += fb_requirements.WINDOWS
        
        elif platform == "darwin":
            requirements += fb_requirements.DARWIN

        elif platform == "linux":
            requirements += fb_requirements.LINUX

        return requirements


    def get_build_platform(self, args: list[str]):
        sys_plat = sys.platform
        if "--web" in args:
            return "web"

        elif sys_plat in SUPPORTED_PLATFORMS:                
            return sys_plat
        
        elif sys_plat == "win32":
            return 'windows'
        
        elif sys_plat == "darwin":
            return sys_plat
        
        elif sys_plat == "linux":
            return sys_plat
            
        else:
            print("Current platform is not supported, aborting build.")

    def locate_assets(self): 
        images = {}
        data = {}
        meshes = {}
        fonts = {}
        for dir_path, _, file_names in os.walk(self.asset_path):
            for file_name in file_names:
                file_type = file_name.split('.')[1]
                file_path = dir_path + "/" + file_name
                if file_type in IMAGE_FILE_TYPES:
                    images[file_path] = get_relative_path(file_path, self.asset_path)
                elif file_type in MESH_FILE_TYPES:
                    meshes[file_path] = get_relative_path(file_path, self.asset_path)
                elif file_type in DATA_FILE_TYPES:
                    data[file_path] = get_relative_path(file_path, self.asset_path)
                elif file_type in FONT_FILE_TYPES:
                    fonts[file_path] = get_relative_path(file_path, self.asset_path)
        return images, data, meshes

    def bundle_assets(self, paths: dict[str, str], name: str):
        with open(os.path.join(self.asset_out_path, f"{name}.pak"), 'wb') as file:
            for path in paths:
                data = open(path, "rb").read()
                out_path = paths[path]
                file.write(struct.pack("<H", len(out_path)))
                file.write(out_path.encode("utf-8"))
                file.write(struct.pack("<I", len(data)))
                file.write(data)

    def reset_dirs(self):
        """Resets the build, temp, and dist directories."""
        if not os.path.exists(self.build_path):
            os.mkdir(self.build_path)
        shutil.rmtree(self.temp_path)
        os.mkdir(self.temp_path)

        shutil.rmtree(self.output_path)
        os.mkdir(self.output_path)
        os.mkdir(self.asset_out_path)

    def get_build_cache(self):
        if os.path.exists(self.cache_path):
            return json.loads(open(self.cache_path, 'r').read())
        else:
            return {}
        
    def create_build_cache(self):
        cache = {}
        cache['dependencies'] = self.dependencies

        open(self.cache_path, 'w').write(cache)


    def setup_venv(self):
        venv_path = os.path.abspath(self.build_path+"/venv/")
        venv.EnvBuilder(with_pip=True).create(venv_path)
        executable = os.path.abspath(venv_path + "/Scripts/python.exe")

        self.install_dependencies(executable)
        self.install_freebody(executable)
        self.run_pyinstaller(executable)

    def install_freebody(self, venv_executable):
        package_path = os.path.abspath(os.path.join(__file__, "..", "..", ".."))
        subprocess.check_call([venv_executable, "-m", "pip", "install", package_path])


    def install_dependencies(self, venv_executable):
        subprocess.check_call([venv_executable, "-m", "pip", "install", *self.dependencies])

    def run_pyinstaller(self, venv_executable):
        dist_path = os.path.join(self.temp_path, "pyinstaller", 'dist')
        work_path = os.path.join(self.temp_path, "pyinstaller", 'work')
        spec_path = os.path.join(self.temp_path, "pyinstaller", 'game.spec')
        name = self.build_settings.get('name', 'FreeBodyGame')

        spec = importlib.util.find_spec("FreeBodyEngine.lib")

        if spec is None or spec.origin is None:
            raise RuntimeError("Could not locate FreeBodyEngine.lib on the filesystem")

        lib_path = Path(spec.origin).parent

        subprocess.check_call([venv_executable, "-m", "PyInstaller", "--onefile", 
                            "--windowed",
                            "--name", name,
                            self.main_file,
                            "--distpath", dist_path,
                            "--workpath", work_path,
                            "--specpath", spec_path,
                            "--add-data", f"{lib_path};FreeBodyEngine/lib"

        ]) 
        
        executable = name + '.exe'
        shutil.move(os.path.join(dist_path, executable), os.path.join(self.output_path, executable))

    def build_code(self):
        """
        Builds code into an execuatable usign pyinstaller.
        """
        self.setup_venv()

    def get_engine_assets(self):
        images = {}
        data = {}
        meshes = {}
        fonts = {}
        resource = importlib.resources.files(FreeBodyEngine).joinpath("engine_assets")

        with importlib.resources.as_file(resource) as asset_path:
            engine_assets_dir = str(asset_path)

        for dir_path, _, file_names in os.walk(engine_assets_dir):
            for file_name in file_names:
                file_type = file_name.split('.')[1]
                file_path = dir_path + "/" + file_name
                if file_type in IMAGE_FILE_TYPES:
                    images[file_path] = 'engine/' + get_relative_path(file_path, engine_assets_dir)
                elif file_type in MESH_FILE_TYPES:
                    meshes[file_path] = 'engine/' + get_relative_path(file_path, engine_assets_dir)
                elif file_type in DATA_FILE_TYPES:
                    data[file_path] = 'engine/' + get_relative_path(file_path, engine_assets_dir)
                elif file_type in FONT_FILE_TYPES:
                    fonts[file_path] = 'engine/' + get_relative_path(file_path, engine_assets_dir)
        return images, data, meshes


    def build_for_web(self, args):
        raise NotImplementedError("Web builds not yet implemented.")

    def build_for_release(self):
        images, data, meshes = self.locate_assets()
        engine_images, engine_data, engine_meshes = self.get_engine_assets()
        self.reset_dirs()

        atlas_path = os.path.join(self.temp_path, '_ENGINE_atlas.png')
        atlas_data_path = os.path.join(self.temp_path, '_ENGINE_atlas.json')

        self.atlas_generator = AtlasGen(images | engine_images)
        self.atlas_generator.save(atlas_path, atlas_data_path)
        
        data[atlas_data_path] = "_ENGINE_atlas.json"
        data |= engine_data
        self.bundle_assets(data, 'data')
        
        self.bundle_assets({atlas_path: '_ENGINE_atlas.png'}, 'images')
        
        self.bundle_assets(meshes, 'mesh')

        self.build_code()
        print(f"Successfully built game for release, platform: {self.platform}.")
        
    def build_for_dev(self):
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

def load_toml(path: str):
    txt = load_text(path)
    return tomllib.loads(txt)

def build(path='./', dev=False):
    Builder(path, dev)