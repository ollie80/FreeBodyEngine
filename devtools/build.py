import os
import json
import subprocess
import shutil

def load_text(path: str):
    file = open(path, "r")
    text = file.read()
    file.close()
    return text

def load_json(path:str):
    txt = load_text(path)
    return json.loads(txt)


if __name__ == "__main__":
    build_settings: dict = load_json("build.json")
    if os.path.exists('build'):
        shutil.rmtree('build')
    os.mkdir("build")
    os.chdir("build")
    print(os.getcwd())  # Shows the current working directory

    
    # Create a virtual environment inside build/
    subprocess.run("python -m venv ./", shell=True)
    pip_path = "/Scripts/pip3.exe"

    # Install dependencies from requirements.txt inside the venv
    for dependency in build_settings['dependencies']:
        print(dependency)
        subprocess.run(f"{pip_path} install {dependency}", shell=True)
