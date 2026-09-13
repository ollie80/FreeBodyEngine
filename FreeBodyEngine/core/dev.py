from dataclasses import dataclass
import os
import sys
from FreeBodyEngine import get_flag, PROJECT_PATH, DEVMODE
from FreeBodyEngine.core.files.dev import open_file
from tomllib import loads
from FreeBodyEngine import warning

@dataclass
class Project:
    path: str
    assets: str
    code: str
    main_file: str
    name: str

PROJECT: Project = None

def load_project() -> Project:
    """
    Finds and parses the project file.
    """
    path = get_flag(PROJECT_PATH, '/')
    project_file_path = path + "/fbproject.toml"
    project_data = loads(open_file(project_file_path, 'r').read())
    return Project(path, project_data['assets'], project_data['code'], project_data['main_file'], project_data["name"])

def _add_code_dir_to_path(project: Project):
    """Puts the project's code directory (and its compiled cpp_scripts/
    output) on sys.path, so both plain .py files under it and the modules
    `fb compile_scripts` builds from .cpp files are importable the normal
    way (`import foo`) from the project's main file."""
    code_path = os.path.abspath(os.path.join(project.path, project.code))
    for path in (code_path, os.path.join(code_path, 'cpp_scripts')):
        if path not in sys.path:
            sys.path.insert(0, path)

def find_project():
    if get_flag(DEVMODE, False):
        global PROJECT
        PROJECT = load_project()
        _add_code_dir_to_path(PROJECT)

def get_project() -> Project:
    return PROJECT
