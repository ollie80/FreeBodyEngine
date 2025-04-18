import os
import json
import subprocess
import shutil
import struct
from pathlib import Path
import sys

def get_relative_path(path: str, folder: str) -> str:
    full = Path(path)

    return full.relative_to(folder).as_posix()
    
output_path = os.path.abspath(".\\build")

data_file_types = [".json", ".animation", ".spritesheet", ".tileset"]
font_file_types = [".ttf"]

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

def bundle(paths: list[str], output_path: str, asset_dir: str, mapped_paths: list[tuple[str, str]]): #mapped paths are needed for temp assets
    with open(f"{output_path}.pak", "wb") as f:
        for path in paths:
            data = open(f"{path}", "rb").read()
            rel = get_relative_path(path, asset_dir)
            f.write(struct.pack("<H", len(rel)))
            f.write(rel.encode("utf-8"))
            f.write(struct.pack("<I", len(data)))
            f.write(data)
        
        for path in mapped_paths:
            data = open(f"{path[0]}", "rb").read()
            rel = get_relative_path(path[1], asset_dir)
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

    #convert fonts
    font_dir = out_path + "\\temp\\font\\"
    os.mkdir(font_dir)

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

    img_paths = find_assets(assets_path, ['.png', '.jpg', '.jpeg'])
    bundle(img_paths, out_path + "\\assets\\images", assets_path, font_imgs)

    data_paths = find_assets(assets_path, ['.png', '.jpg', '.jpeg'])
    bundle(data_paths, out_path + "\\assets\\data", assets_path, font_data)

    
    #remove temp files
    shutil.rmtree(out_path + "\\temp")

def build_code():
    
    #clone code files
    shutil.copytree("./FreeBodyEngine", output_path + "/FreeBodyEngine", ignore=shutil.ignore_patterns('dev', 'build'))
    
    code_path_name = os.path.basename(code_path)
    shutil.copytree(code_path, output_path + "/" + code_path_name)
    
    main_file_name = os.path.basename(main_file)
    shutil.copyfile(main_file, output_path + "/" + main_file_name)

    for package in pip_dependencies:
        print(f"Installing {package}...")
        subprocess.check_call([
            sys.executable,
            "-m", "pip",
            "install",
            package        ])
    
    env_paths = os.pathsep.join(str(p) for p in output_path)
    
    pyinstaller_flags = [
        "pyinstaller",
        "--onefile"
        ]

    if is_devmode:
        pyinstaller_flags.append("--noconsole")

    subprocess.check_call([
        *pyinstaller_flags,
        main_file
    ])    


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
    
    asset_out_path = output_path
    
    if is_devmode:
        asset_out_path = os.path.abspath("./dev/")

    build_assets(asset_out_path)
    
    if not is_devmode:
        build_code()

    print("\nDone! Your executable and game assets should be in the 'dist' folder.")
    