import sys
import subprocess
import os
from FreeBodyEngine.cli.project import ProjectRegistry
from FreeBodyEngine.dev.run import main as run_project
import tomllib
import platform
from importlib.resources import files
import shutil

class Command:
    def __init__(self, names, handler=None, subcommands=None, help_text=""):
        self.names = names  # list of aliases
        self.handler = handler  # function to call
        self.subcommands = subcommands or []  # list of subcommands (Command objects)
        self.help_text = help_text

    def matches(self, name):
        return name in self.names

    def find_subcommand(self, name):
        for cmd in self.subcommands:
            if cmd.matches(name):
                return cmd
        return None
    
    def print_help(self, path=[]):
        command_path = " ".join(path + [self.names[0]])
        print(f"Usage: fb {command_path} [subcommand] [args]" if self.subcommands else f"Usage: fb {command_path} [args]")
        print(f"Description: {self.help_text}")
        if self.subcommands:
            print("\nAvailable subcommands:")
            for cmd in self.subcommands:
                print(f"  {cmd.names[0]:10} - {cmd.help_text}")


def build_handler(args):
    subprocess.run(["python", "FreeBodyEngine/build/builder.py", '--dev', *args], shell=True)

def run_handler(args):
    if len(args) == 0:
        if os.path.exists('./fbproject.toml'):
            try:
                run_project()
            except KeyboardInterrupt:
                sys.exit(0)
        else:
            print("No project specified.")
    else:
        id =  args[0]
        if project_registry.project_exisits(id):
            path = project_registry.get_project_path(id)
            try:
                run_project(path)
            except KeyboardInterrupt:
                sys.exit(0)
        else:
            print(f"Project with ID '{id}' does not exist.")

def get_current_project():
    """Gets the ID of the current FB Project."""
    cwd = os.getcwd()
    project_file = os.path.join(cwd, "fbproject.toml")
    
    if os.path.exists(project_file):
        project_name = tomllib.loads(open(project_file).read()).get("name", None)
        project_id = project_registry.get_project_id(project_name)
        if project_id == None:
            print('No FreeBody project found in the current directory. Did you initialize the project using `freebody init`?')
        return project_id

def create_sprite(args):
    if len(args) < 1:
        print("Usage: fb create sprite <name>")
        return
    print(f"Creating project '{args[0]}'")

def init_handler(args):
    cwd = os.getcwd()
    project_file = os.path.join(cwd, "fbproject.toml")
    if os.path.exists(project_file):
        project_data = tomllib.loads(open(project_file).read())
        project_name = project_data.get('name', None)
    
        id = project_registry.get_project_id(project_name)
        if id == None:
            project_registry.add_project(cwd, project_name)
            #print(f'Created project "{project_name}" with path "{cwd}"')
        else:
            print(f'A project with the name "{project_name}" already exists.')
        

def project_handler(args):
    pass

def get_log_file():
    name = project_registry.get_project_name(get_current_project())
    if name == None:
        print("No project found.")
        return ""
    system = platform.system()
        
    if system == "Windows":
        base = os.getenv("APPDATA")
    elif system == "Darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.getenv("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    
    return os.path.join(base, name, "log.txt")

def log_read_handler(args):
    num_lines = int(args[0]) if len(args) > 0 else 50
    log_type = args[1].upper() if len(args) > 1 else None

    log = get_log_file()
    if not os.path.exists(log):
        print("No log file found.")
        return

    matching_lines = []
    with open(log, "rb") as f:
        f.seek(0, os.SEEK_END)
        pos = f.tell()
        line_bytes = []

        while pos > 0 and len(matching_lines) < num_lines:
            pos -= 1
            f.seek(pos)
            byte = f.read(1)
            if byte == b'\n':
                if line_bytes:
                    line = b''.join(reversed(line_bytes)).decode('utf-8', errors='ignore')
                    if log_type is None or f"[{log_type}]" in line:
                        matching_lines.append(line)
                    line_bytes = []
            else:
                line_bytes.append(byte)

        # Handle first line (start of file) if not newline-terminated
        if line_bytes and len(matching_lines) < num_lines:
            line = b''.join(reversed(line_bytes)).decode('utf-8', errors='ignore')
            if log_type is None or f"[{log_type}]" in line:
                matching_lines.append(line)

    # Print in forward (time) order
    for line in reversed(matching_lines):
        print(line, end="" if line.endswith("\n") else "\n")

def confirm():
    return input("Are you sure you want to do that? y/N: ").lower().strip() == 'y'

def log_wipe_handler(args):
    log = get_log_file()
    if not os.path.exists(log):
        print("No log file found.")
        return

    if confirm():
        f = open(log, "w")
        f.write('')
    else:
        print('Aborting.')
        return

def delete_project(args):
    project = None
    if not len(args) > 0:
        current_project = get_current_project()
        if current_project != None:
            project = current_project
        else:
            print("No project ID specified.")
            return
    else:
        project = args[0]
        if not project_registry.project_exisits(project):
            print(f'Project with ID "{project}" does not exsist.')
            return
        
    path = project_registry.get_project_path(project)
    print(f'Deleting project "{project_registry.get_project_name(project)}" with ID "{project}" at path {path}.')
    
    if confirm():
        if confirm():
            shutil.rmtree(path)
        else:
            print("Aborting.")
    else:
        print("Aborting.")
    
def list_projects(args):
    print("{:<4} {:<20} {:<50}".format("ID", "Name", "Path"))
    print("-" * 80)
    for p in project_registry.projects:
        print("{:<4} {:<20} {:<50}".format(
            p.get('id'),
            p.get('name'),
            p.get('path')
        ))       

def create_project(args):
    if len(args) < 1:
        print("Usage: create_project.py <project_name> [base_path]")
        return

    project_name = args[0]
    base_path = args[1] if len(args) >= 2 else os.getcwd()

    project_dir = os.path.join(base_path, project_name)

    assets_dir = os.path.join(project_dir, 'assets')
    code_dir = os.path.join(project_dir, 'code')
    main_py_content = open(files('FreeBodyEngine.engine_assets').joinpath('default_main_file.py')).read()
    os.mkdir(project_dir)
    try:
        os.mkdir(assets_dir)
        os.mkdir(code_dir)
    except FileExistsError:
        print(f"Error: Project directory '{project_dir}' or subdirectories already exist.")
        return

    toml_content = f"""name = "{project_name}"
dependencies = []
main_file = "./main.py"
assets = "./assets"
code = "./code"
"""
    with open(os.path.join(project_dir, 'fbproject.toml'), 'w', encoding='utf-8') as f:
        f.write(toml_content)

    with open(os.path.join(project_dir, 'main.py'), 'w', encoding='utf-8') as f:
        f.write(main_py_content)
    
    os.chdir(project_dir)
    init_handler([])

    print(f"Project '{project_name}' created successfully and initialized at {os.path.abspath(project_dir)}")

    

def help_handler(args):
    print("FreeBodyEngine CLI")
    print("Usage: fb <command> [subcommand] [args]")
    print("Available commands:")
    for cmd in root_commands:
        print("  ", cmd.names[0], "-", cmd.help_text)
    sys.exit(0)

root_commands = [
    Command(["build", "b"], build_handler, help_text="Build the project"),
    Command(["init", 'i'], init_handler, help_text="Initializes the project in the current directory, must be run before any other commands."),
    Command(["run", "r"], run_handler, help_text="Run a project."),
    Command(['project', "p"], subcommands=[
        Command(['list', "l"], list_projects, help_text="List all projects in the registry."),
        Command(['delete', "d"], delete_project, help_text="Deletes a project.")
    ], help_text="Commands to work with the FB Project system."),
    Command(["create", "c"], subcommands=[
        Command(["sprite", "s"], create_sprite, help_text="Create a new sprite."),
        Command(["project", "p"], create_project, help_text="Create a new project.")
    ], help_text="Create a new resource"),
    Command(['log', 'l'], subcommands=[
        Command(['wipe', 'w'], log_wipe_handler, help_text='Permanantly wipes a log file.'),
        Command(['read', 'r'], log_read_handler, help_text='Reads a log file.')
    ], help_text="Access and Modify project log files."),
    Command(["help", "h"], help_handler, help_text="Show help")
]

def dispatch(args, commands, path=[]):
    if not args:
        print("No command provided.\n")
        help_handler([])
        return

    cmd_name = args[0]

    for cmd in commands:
        if cmd.matches(cmd_name):
            if len(args) > 1 and args[1] in ("--help", "-h"):
                cmd.print_help(path)
                return

            if cmd.subcommands and len(args) > 1:
                dispatch(args[1:], cmd.subcommands, path + [cmd.names[0]])
            elif cmd.handler:
                cmd.handler(args[1:])
            else:
                cmd.print_help(path)
            return

    print(f"Unknown command: {cmd_name}")
    sys.exit(1)



def main():
    global project_registry
    project_registry = ProjectRegistry()
    dispatch(sys.argv[1:], root_commands)

