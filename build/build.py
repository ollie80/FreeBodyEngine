import os
import json
import subprocess
import shutil
import struct
from pathlib import Path
import sys
import os
import shutil
import subprocess
import sys
import venv


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
        print(f"\n❌ Failed to install {package}:")
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
    is_devmode = False
    for arg in sys.argv:
        if arg == "--dev":
            is_devmode = True
        
    #load build settings
    try:
        build_settings: dict = load_json('./build.json')
    except:
        raise FileNotFoundError("No build config file found.")

    try:
        pip_dependencies = build_settings["dependencies"] + ["pygame-ce", "moderngl",]
    except:
        raise ValueError("No dependecies specified in build config.")
        
    try:
        main_file = build_settings["main_file"]
    except:
        raise ValueError("No main file specified in build config.")
    
    try:
        code_path = os.path.abspath(build_settings['code'])
    except:
        raise ValueError("No code path specified in build config.")

    try:
        assets_path = os.path.abspath(build_settings['assets'])
    except:
        raise ValueError("No asset path specified in build config.")

    #clear old files
    if os.path.exists(output_path):
        shutil.rmtree(output_path)
    
    asset_out_path = os.path.abspath("./dist/")
    
    if is_devmode:
        asset_out_path = os.path.abspath("./dev/")

    build_assets(asset_out_path)
    
    if not is_devmode:
        build_code()

    