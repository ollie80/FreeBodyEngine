from dataclasses import dataclass
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
    project_file_path = path + "\\fbproject.toml"
    project_data = loads(open_file(project_file_path, 'r').read())
    return Project(path, project_data['assets'], project_data['code'], project_data['main_file'], project_data["name"])
    
def find_project():
    if get_flag(DEVMODE, False):
        global PROJECT
        PROJECT = load_project()

def get_project() -> Project:
    return PROJECT