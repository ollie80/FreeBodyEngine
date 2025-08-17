import os
import json
import hashlib
import re
import subprocess
import sys
import shutil
from FreeBodyEngine.cli.cpp.macrogen import CppBindingGenerator

def compile_handler(env, args):
    project = env.project_id
    if len(args) > 0:
        project = args[0]

    if project == None:
        print('No project specified or detected.')
        return
    
    project_path = env.project_registry.get_project_path(project)
    code_path = os.path.abspath(os.path.join(project_path, env.project_registry.get_project_config(project).get('code')))

    scripts_dir = ensure_scripts_dir(code_path)
    
    build_all = ensure_metadata_file(scripts_dir)
    if "--force" in args:
        build_all = False

    if not build_all:
        metadata = {}

    else:
        metadata = load_metadata_file(scripts_dir)
    
    
    for root, _, files in os.walk(code_path):
        if root.endswith('cpp_scripts'):
            continue
        for file in files:

            if file.endswith(('.cpp', '.hpp', '.h')):
                rel_path = os.path.join(root, file)                
                
                module_name = file.split('.')[0]
                
                source = open(rel_path).read()
                hashed_source =  hash_source(source)

                file_changed = True

                if rel_path in metadata:
                    hashed_file = metadata[rel_path]
                    if hashed_file == hashed_source:
                        file_changed = False

                metadata[rel_path] = hashed_source

                if file_changed:
                    macrogen = CppBindingGenerator(source, module_name)
                    macrogen.parse()
                    injected_source = macrogen.generate()
                    
                    cpp_path = os.path.abspath(os.path.join(scripts_dir, module_name + '.cpp'))
                    setup_path = os.path.abspath(os.path.join(scripts_dir, 'setup.py'))

                    with open(cpp_path, 'w') as f:
                        f.write(injected_source)
                        f.close()
                    
                    with open(setup_path, 'w') as f:
                        f.write(generate_setup_py(module_name, cpp_path))
                        f.close()

                    
                    result = subprocess.run([sys.executable, setup_path, 'build_ext', '--inplace'], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL, cwd=scripts_dir)
                    
                    if result.returncode != 0:
                        print(f"Build failed for module '{module_name}'.")
                        return

                    try:
                        if os.path.exists(cpp_path):
                            os.remove(cpp_path)
                        if os.path.exists(setup_path):
                            os.remove(setup_path)
                        build_dir = os.path.join(scripts_dir, 'build')
                        if os.path.exists(build_dir) and os.path.isdir(build_dir):
                            shutil.rmtree(build_dir)

                    except Exception as e:
                        print(f"Cleanup failed: {e}")
                    
                    stub_path = os.path.join(scripts_dir, module_name + '.pyi')
                    with open(stub_path, 'w') as f:
                        f.write(macrogen.generate_pyi())
                        f.close()
    
    metadata_path = os.path.join(scripts_dir, 'data.json')
    with open(metadata_path, 'w', encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

def ensure_scripts_dir(code_dir: str):
    """Ensures that a cpp_scripts/ directory exsists in the project code directory. Returns the path."""
    dir_name = "cpp_scripts"
    full_path = os.path.join(code_dir, dir_name)
    if not os.path.exists(full_path):
        os.mkdir(full_path)
    
    return full_path

def ensure_metadata_file(scripts_dir: str):
    """Ensures that a cpp_scripts/data.json metadata file exsists in the project code directory. Returns true if it already exsisted and false if not."""
    path = os.path.join(scripts_dir, 'data.json')
    existed = True 
    if not os.path.exists(path):
        existed = False
        open(path, 'x')
    return existed

def load_metadata_file(scripts_dir: str):
    txt = open(os.path.join(scripts_dir, 'data.json')).read()
    return json.loads(txt)

def supress_command_output():
    sys.stdout = open(os.devnull, 'w')

def restore_command_output():
    sys.stdout = sys.__stdout__



def generate_setup_py(name: str, filepath: str):
    filepath = filepath.replace('\\', '/')
    extra_compile_args = []
    if sys.platform == "win32":
        extra_compile_args.append("/std:c++17")
    else:
        extra_compile_args.append("-std=c++17")

    source = f"""
from setuptools import setup, Extension
import pybind11

ext_modules = [
    Extension(
        "{name}",
        ["{filepath}"],
        include_dirs=[pybind11.get_include()],
        language="c++",
        extra_compile_args={str(extra_compile_args)},
    ),
]

setup(
    name="{name}",
    ext_modules=ext_modules,
    zip_safe=False,
)
"""
    return source
    

def hash_source(source: str) -> str:
    h = hashlib.blake2b(digest_size=16)
    h.update(source.encode("utf-8"))
    return h.hexdigest()

