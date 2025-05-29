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

import venv.scripts

import venv.scripts.common


SUPPORTED_PLATFORMS = ["windows", "darwin", "linux"]

FONT_FILE_TYPES = ["ttf"]
DATA_FILE_TYPES = ["txt", "json", "fbusl", 'mp3', 'wav']
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
        return path.removeprefix(root_dir)
    
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
        
        self.bundle_assets(images, 'image', self.asset_path)
        self.bundle_assets(meshes, 'mesh', self.asset_path)
        
        font_paths = self.convert_font(fonts)
        self.bundle_assets(font_paths[0], 'data', self.temp_path)
        self.bundle_assets(font_paths[1], 'image', self.temp_path)

        self.build_code()
        print("Successfully build game for release.")


    def build_for_dev(self):
        images, data, meshes, fonts = self.locate_assets()
        self.bundle_assets(data, 'data', self.asset_path)
        self.bundle_assets(images, 'image', self.asset_path)
        self.bundle_assets(meshes, 'mesh', self.asset_path)
        
        font_paths = self.convert_fonts(fonts)
        self.bundle_assets(font_paths[0], 'data', self.temp_path)
        self.bundle_assets(font_paths[1], 'image', self.temp_path)

        print("Successfully build game for development.")

def get_relative_path(path: str, folder: str) -> str:
    full = Path(path)

    return full.relative_to(folder).as_posix()

output_path = os.path.abspath(".\\build")

data_file_types = [".json", ".txt", ".shader", ".glsl", ".vert", ".frag", ".composite", ".animation", ".spritesheet", ".tileset", ".mp3", ".wav"]
font_file_types = [".ttf"]
image_file_types = ['.png', '.jpg', '.jpeg']

def load_text(path: str):
    file = open(path, "r")
    text = file.read()
    file.close()
    return text

def load_json(path: str):
    txt = load_text(path)
    return json.loads(txt)

def convert_font(path: str, out_path: str):
    font_path = os.path.abspath(path)
    exe_path = "FreeBodyEngine/build/msdf-atlas-gen.exe"

    font_name = os.path.basename(path).split('.')[0]
    img_path = f"{out_path+font_name}.png"
    json_path = f"{out_path+font_name}.json"
    subprocess.run([exe_path, '-font', font_path, '-imageout', img_path, '-json', json_path], stdout=subprocess.DEVNULL)
    return (img_path, font_path.split(".")[0] + ".png"), (json_path, font_path.split(".")[0] + ".json")

def bundle(paths: list[str], output_path: str, asset_dir: str, mapped_paths: list[tuple[str, str]] = [], path_prefix = "", open_mode = 'wb'):
    with open(f"{output_path}.pak", open_mode) as f:
        for path in paths:
            data = open(f"{path}", "rb").read()
            rel = path_prefix + get_relative_path(path, asset_dir)
            f.write(struct.pack("<H", len(rel)))
            f.write(rel.encode("utf-8"))
            f.write(struct.pack("<I", len(data)))
            f.write(data)
        
        for path in mapped_paths:
            data = open(f"{path[0]}", "rb").read()
            rel = path_prefix + get_relative_path(path[1], asset_dir)
            f.write(struct.pack("<H", len(rel)))
            f.write(rel.encode("utf-8"))
            f.write(struct.pack("<I", len(data)))
            f.write(data)

def find_assets(dir_path: str, extensions: list[str]):
    matches = []
    for root, _, files in os.walk(dir_path):
        for file in files:
            for extension in extensions:
                if file.endswith(extension):
                    matches.append(os.path.join(root, file))
    
    return matches

def build_assets(out_path):
    
    #create output directory
    if not os.path.exists(out_path):
        os.mkdir(out_path)
    
    temp_path = out_path + "\\temp"
    if os.path.exists(temp_path):
        shutil.rmtree(temp_path)
    os.mkdir(temp_path)

    engine_assets = os.path.abspath("FreeBodyEngine/engine_assets/")
    

    #convert fonts
    font_dir = out_path + "\\temp\\font\\"
    os.mkdir(font_dir)

    engine_fonts = find_assets(engine_assets, font_file_types)
    engine_font_images = []
    engine_font_data = []
    for path in engine_fonts:
        img_path, json_path = convert_font(path, font_dir)
        engine_font_images.append(img_path)    
        engine_font_data.append(json_path)


    font_paths = find_assets(assets_path, font_file_types)
    font_imgs = []
    font_data = []
    for path in font_paths:
        img_path, json_path = convert_font(path, font_dir)
        font_imgs.append(img_path)    
        font_data.append(json_path)

    # bundle assets
    asset_path = out_path + "\\assets"
    if os.path.exists(asset_path):
        shutil.rmtree(asset_path)
        
    os.mkdir(asset_path)  

    engine_images = find_assets(engine_assets, image_file_types)
    img_paths = find_assets(assets_path, image_file_types)
    bundle(img_paths, out_path + "\\assets\\images", assets_path, font_imgs)
    bundle(engine_images, out_path + "\\assets\\images", engine_assets, engine_font_images, "engine/", "ab")

    gen = AtlasGen()
    print(gen.generate(img_paths))

    engine_data = find_assets(engine_assets, data_file_types) 
    data_paths = find_assets(assets_path, data_file_types)
    bundle(data_paths, out_path + "\\assets\\data", assets_path, font_data)
    bundle(engine_data, out_path + "\\assets\\data", engine_assets, engine_font_data, "engine/", "ab")

    
    #remove temp files
    shutil.rmtree(out_path + "\\temp")

def install_with_logging(python_executable, package, cache_dir):
    print(f"Installing {package}...")
    try:
        subprocess.check_call([
            python_executable,
            "-m", "pip",
            "install",
            package,
            "--cache-dir", cache_dir
        ])
    except subprocess.CalledProcessError as e:
        print(f"\nFailed to install {package}:")
        subprocess.run([
            python_executable,
            "-m", "pip",
            "install",
            package,
            "--cache-dir", cache_dir
        ], check=False)
        raise e

def build_code():
    # Define paths
    env_dir = os.path.join(output_path, "venv")
    code_path_name = os.path.basename(code_path)
    main_file_name = os.path.basename(main_file)
    pip_cache_dir = os.path.join(output_path, ".pip_cache")

    # Copy necessary code files
    shutil.copytree("./FreeBodyEngine", os.path.join(output_path, "FreeBodyEngine"), ignore=shutil.ignore_patterns('dev', 'build'))
    shutil.copytree(code_path, os.path.join(output_path, code_path_name))
    shutil.copyfile(main_file, os.path.join(output_path, main_file_name))

    # Create a virtual environment
    print("Creating virtual environment...")
    venv.create(env_dir, with_pip=True)

    # Determine path to the Python executable in the venv
    if os.name == 'nt':
        python_executable = os.path.join(env_dir, "Scripts", "python.exe")
    else:
        python_executable = os.path.join(env_dir, "bin", "python")

    # Create pip cache directory if it doesn't exist
    os.makedirs(pip_cache_dir, exist_ok=True)

    # Install dependencies inside the venv using the cache
    for package in pip_dependencies:
        install_with_logging(python_executable, package, pip_cache_dir)


    # Install PyInstaller using the cache as well
    subprocess.check_call([
        python_executable,
        "-m", "pip",
        "install",
        "pyinstaller",
        "--cache-dir", pip_cache_dir
    ])

    # Build with PyInstaller
    pyinstaller_flags = [
        python_executable,
        "-m", "PyInstaller",
        "--onefile"
    ]

    if is_devmode:
        pyinstaller_flags.append("--noconsole")

    pyinstaller_flags.append(main_file_name)  # Use filename since we're in the output dir

    print("Running PyInstaller...")
    subprocess.check_call(pyinstaller_flags, cwd=output_path)

if __name__ == "__main__":
    builder = Builder()
        