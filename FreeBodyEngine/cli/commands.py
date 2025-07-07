import sys
import subprocess
import os
from FreeBodyEngine.cli.project import ProjectRegistry
from FreeBodyEngine.cli.fulcrum import fulcrum_handler
from FreeBodyEngine.dev.run import main as run_project
import tomllib
import platform
from importlib.resources import files
import shutil


from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import threading

class Environment:
    def __init__(self, path=None, project_id=None):
        self.project_id = project_id
        self.project_path = None
        self.observer = None
        self.running = False
        self.path = None

        self.project_registry = ProjectRegistry()

        if project_id:
            self.project_path = self.project_registry.get_project_path(project_id)
            self.path = self.project_path
        elif path:
            self.path = os.path.abspath(path)
            # try detect project in path if exists
            project_id = self.detect_project()
            if project_id:
                self.project_id = project_id
                self.project_path = self.project_registry.get_project_path(project_id)
        else:
            self.path = os.getcwd()
            project_id = self.detect_project()
            if project_id:
                self.project_id = project_id
                self.project_path = self.project_registry.get_project_path(project_id)

    def detect_project(self):
        config_path = os.path.join(self.path, "fbproject.toml")
        if os.path.exists(config_path):
            try:
                data = tomllib.loads(open(config_path, "r").read())
                project_name = data.get("name", None)
                if project_name:
                    pid = self.project_registry.get_project_id(project_name)
                    if pid:
                        return pid
            except Exception:
                pass
        return None

    def start(self):
        self.running = True
        if self.project_path:
            self.observer = Observer()
            handler = FileChangeHandler(self)
            self.observer.schedule(handler, self.project_path, recursive=True)
            self.observer.start()

    def stop(self):
        self.running = False
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None

    def on_file_change(self, path):
        print(f"[env] File changed: {path}")
    
    def reload_registry(self):
        self.project_registry = ProjectRegistry()

class FileChangeHandler(FileSystemEventHandler):
    def __init__(self, env):
        self.env = env

    def on_modified(self, event):
        if not event.is_directory:
            self.env.on_file_change(event.src_path)

class Command:
    def __init__(self, names, handler=None, subcommands=None, help_text=""):
        self.names = names
        self.handler = handler
        self.subcommands = subcommands or []
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


def build_handler(env, args):
    subprocess.run(["python", "FreeBodyEngine/build/builder.py", '--dev', *args], shell=True, cwd=env.path)

def run_handler(env, args):
    if len(args) == 0:
        if env.project_path:
            try:
                run_project(env.project_path)
            except KeyboardInterrupt:
                pass
        else:
            print("No project specified or detected.")
    else:
        id = args[0]
        if env.project_registry.project_exists(id):
            path = env.project_registry.get_project_path(id)
            try:
                run_project(path)
            except KeyboardInterrupt:
                pass
        else:
            print(f"Project with ID '{id}' does not exist.")

def get_current_project(env):
    cwd = env.path
    project_file = os.path.join(cwd, "fbproject.toml")
    if os.path.exists(project_file):
        project_name = tomllib.loads(open(project_file, "rb").read()).get("name", None)
        project_id = env.project_registry.get_project_id(project_name)
        if project_id is None:
            print('No FreeBody project found in the current directory. Did you initialize the project using `freebody init`?')
        return project_id

def create_sprite(env, args):
    if len(args) < 1:
        print("Usage: fb create sprite <name>")
        return
    print(f"Creating sprite '{args[0]}' in environment path '{env.path}'")

def init_handler(env, args):
    cwd = env.path
    project_file = os.path.join(cwd, "./fbproject.toml")
    if os.path.exists(project_file):
        project_data = tomllib.loads(open(project_file, "r").read())
        project_name = project_data.get('name', None)

        id = env.project_registry.get_project_id(project_name)
        if id is None:
            env.project_registry.add_project(cwd, project_name)
        else:
            print(f'A project with the name "{project_name}" already exists.')
    
    env.reload_registry()

def get_log_file(env):
    name = None
    if env.project_id:
        name = env.project_registry.get_project_name(env.project_id)
    else:
        name = None

    if name is None:
        print("No project found.")
        return ''

    system = platform.system()
    if system == "Windows":
        base = os.getenv("APPDATA")
    elif system == "Darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.getenv("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))

    return os.path.join(base, name, "log.txt")

def log_read_handler(env, args):
    num_lines = int(args[0]) if len(args) > 0 else 50
    log_type = args[1].upper() if len(args) > 1 else None

    log = get_log_file(env)

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

        if line_bytes and len(matching_lines) < num_lines:
            line = b''.join(reversed(line_bytes)).decode('utf-8', errors='ignore')
            if log_type is None or f"[{log_type}]" in line:
                matching_lines.append(line)

    for line in reversed(matching_lines):
        print(line, end="" if line.endswith("\n") else "\n")

def confirm():
    return input("Are you sure you want to do that? y/N: ").lower().strip() == 'y'

def log_wipe_handler(env, args):
    log = get_log_file(env)
    if not os.path.exists(log):
        print("No log file found.")
        return

    if confirm():
        with open(log, "w") as f:
            f.write('')
    else:
        print('Aborting.')
        return

def delete_project(env, args):
    project = None
    if not len(args) > 0:
        current_project = get_current_project(env)
        if current_project is not None:
            project = current_project
        else:
            print("No project ID specified.")
            return
    else:
        project = args[0]
        if not env.project_registry.project_exisits(project):
            print(f'Project with ID "{project}" does not exist.')
            return

    path = env.project_registry.get_project_path(project)
    print(f'Deleting project "{env.project_registry.get_project_name(project)}" with ID "{project}" at path {path}.')

    if confirm():
        if confirm():
            shutil.rmtree(path)
        else:
            print("Aborting.")
    else:
        print("Aborting.")

def list_projects(env, args):
    print("{:<4} {:<20} {:<50}".format("ID", "Name", "Path"))
    print("-" * 80)
    for p in env.project_registry.projects:
        print("{:<4} {:<20} {:<50}".format(
            p.get('id'),
            p.get('name'),
            p.get('path')
        ))

def cat_handler(env, args):
    if not args:
        print("Usage: cat <file>")
        return

    target_path = os.path.abspath(os.path.join(env.path, args[0]))

    if not os.path.exists(target_path):
        print(f"'{target_path}' does not exist.")
        return

    if os.path.isdir(target_path):
        print(f"'{target_path}' is a directory.")
        return

    try:
        print('\n')
        with open(target_path, 'r', encoding='utf-8') as f:
            print(f.read())
    except Exception as e:
        print(f"Error reading file: {e}")

def create_project(env, args):
    if len(args) < 1:
        print("Usage: create_project.py <project_name> [base_path]")
        return

    project_name = args[0]
    base_path = args[1] if len(args) >= 2 else env.path

    project_dir = os.path.join(base_path, project_name)

    assets_dir = os.path.join(project_dir, 'assets')
    code_dir = os.path.join(project_dir, 'code')
    main_py_content = open(files('FreeBodyEngine.engine_assets').joinpath('default_main_file.py')).read()

    try:
        os.mkdir(project_dir)
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
    init_handler(env, [])

    print(f"Project '{project_name}' created successfully and initialized at {os.path.abspath(project_dir)}")

def get_project(env, args):
    if len(args) > 0:
        project = args[0]
    else:
        current = get_current_project(env)
        if current is not None:
            project = current
        else:
            print("No project ID specified.")
            return

    if not env.project_registry.project_exists(project):
        print(f"Project with ID {project} does not exist.")
    else:
        print(f'ID: "{project}", Name: "{env.project_registry.get_project_name(project)}", Path: "{env.project_registry.get_project_path(project)}"')

def get_project_lines(env, id: str):
    config = env.project_registry.get_project_config(id)
    lines = 0
    path = env.project_registry.get_project_path(id)
    lines += len(open(os.path.join(path, config.get('main_file'))).readlines())

    for root, dirs, files in os.walk(os.path.join(path, config.get('code'))):
        for filename in files:
            if filename.endswith('.py'):
                lines += len(open(os.path.join(root, filename)).readlines())
    return lines

def lines_project(env, args):
    if len(args) > 0:
        project = args[0]
    else:
        current = get_current_project(env)
        if current is not None:
            project = current
        else:
            print("No project specified.")
            return

    if env.project_registry.project_exisits(project):
        print(f'Total Lines: {get_project_lines(env, project)}')
    else:
        print(f'Project with ID "{project}" does not exist.')

def enter_handler(env, args):
    if len(args) > 0:
        env.project_id = args[0]
        env.project_path = env.project_registry.get_project_path(args[0])

    env.start()
    
    while env.running:
        try:
            prompt = "freebody"
            at = "\033[34m@\033[0m"
            if env.project_id:
                prompt += f"{at}{env.project_registry.get_project_name(env.project_id)}"
            elif env.path:
                prompt += f'{at}{env.path}'
            prompt += "\033[34m>\033[0m "

            command_line = input(prompt).strip()
        except KeyboardInterrupt:
            print("\nType 'exit' or 'quit' to leave the environment.")
            continue  # don't exit the loop

        if not command_line:
            continue

        if command_line.lower() in ('exit', 'quit'):
            break

        parts = command_line.split()
        dispatch(parts, root_commands, env)

    env.stop()

def mkdir_handler(env, args):
    if not args:
        print("Usage: mkdir <path>")
        return
    
    dir_path = os.path.abspath(os.path.join(env.path, args[0]))
    if os.path.exists(dir_path):
        print(f'Path "{dir_path}" already exists.')
        return
    os.makedirs(dir_path)
    
def rm_handler(env, args):
    flags, positional = parse_options(args, {'r', 'f'})
    recusive = 'r' in flags
    force = 'f' in flags

    if len(positional) == 0:
        print("Usage: rm <path>")
        return

    path = os.path.join(env.path, positional[0])
    if os.path.exists(path):
        if os.path.isdir(path):
            if recusive:
                if force:
                    shutil.rmtree(path)        
                else:
                    if confirm():
                        shutil.rmtree(path)
                    else:
                        print('Aborting.')
            else:
                print(f'ERROR: "{path}" is directory, use -r to delete recursively.')
        else:
            os.remove(path)
    else:
        print(f'Path "{path}" does not exist.')
    env.reload_registry()

        
def parse_options(args, allowed_flags=None):
    """
    Separates flags (e.g. '-rf') from positional arguments.
    Returns: (set of flags, list of arguments)
    """
    flags = set()
    positional = []

    for arg in args:
        if arg.startswith('-') and not os.path.isdir(arg) and not os.path.isfile(arg):
            for ch in arg[1:]:
                if allowed_flags is None or ch in allowed_flags:
                    flags.add(ch)
        else:
            positional.append(arg)

    return flags, positional


def cd_handler(env, args):
    if not args:
        print("Usage: cd <path>")
        return

    new_path = os.path.abspath(os.path.join(env.path, args[0]))
    if os.path.isdir(new_path):
       project_id = None
    elif env.project_registry.project_exists(args[0]):
        project_id = args[0] 
    else:
        print(f"'{new_path}' is not a valid directory.")
        return

    if project_id != None:
        env.project_id = project_id
        env.project_path = env.project_registry.get_project_path(project_id)
        env.path = env.project_registry.get_project_path(project_id)
    else:
        env.path = new_path
        project_id = env.detect_project()
        env.project_id = project_id
        env.project_path = project_id


def ls_handler(env, args):
    target_path = env.path if not args else os.path.abspath(os.path.join(env.path, args[0]))
    
    if not os.path.isdir(target_path):
        print(f"'{target_path}' is not a valid directory.")
        return

    entries = os.listdir(target_path)
    entries.sort()

    for entry in entries:
        full_path = os.path.join(target_path, entry)
        if os.path.isdir(full_path):
            print(f"\033[34m{entry}/\033[0m")  # Blue for directories
        else:
            print(entry)

def help_handler(env, args):
    print("FreeBodyEngine CLI")
    print("Usage: fb <command> [subcommand] [args]")
    print("Available commands:")
    for cmd in root_commands:
        print("  ", cmd.names[0], "-", cmd.help_text)
    sys.exit(0)

def clear_handler(env, args):
    system = platform.system()
    if system == "Windows":
        os.system("cls")
    else:
        os.system("clear")


root_commands = [
    Command(["build", "b"], build_handler, help_text="Build the project"),
    Command(["init", 'i'], init_handler, help_text="Initializes the project in the current directory, must be run before any other commands."),
    Command(["run", "r"], run_handler, help_text="Run a project."),
    Command(['enter', 'e'], enter_handler, help_text="Enter the FreeBodyEngine environment."),
    Command(['project', "p"], subcommands=[
        Command(['list', "l"], list_projects, help_text="List all projects in the registry."),
        Command(['delete', "d"], delete_project, help_text="Deletes a project."),
        Command(['get', "g"], get_project, help_text="Gets the project information."),
        Command(['lines'], lines_project, help_text="Gets the lines of a project.")
    ], help_text="Commands to work with the FB Project system."),
    Command(["create", "c"], subcommands=[
        Command(["sprite", "s"], create_sprite, help_text="Create a new sprite."),
        Command(["project", "p"], create_project, help_text="Create a new project.")
    ], help_text="Create a new resource"),
    Command(['log', 'l'], subcommands=[
        Command(['wipe', 'w'], log_wipe_handler, help_text='Permanantly wipes a log file.'),
        Command(['read', 'r'], log_read_handler, help_text='Reads a log file.')
    ], help_text="Access and Modify project log files."),
    Command(["help", "h"], help_handler, help_text="Show help"),
    Command(['clear'], clear_handler, help_text="Clear the command line."),
    Command(['cd'], cd_handler, help_text="Change to a directory."),
    Command(['ls'], ls_handler, help_text="List files and sub-directories."),
    Command(['cat'], cat_handler, help_text="Print the contents of a file."),
    Command(["mkdir"], mkdir_handler, help_text="Create a directory."),
    Command(["rm"], rm_handler, help_text="Remove a file or directory."),
    Command(["fulcrum"], fulcrum_handler, help_text='A small text editor.')
]

def dispatch(args, commands, env=None, path=[]):
    if not args:
        print("No command provided.\n")
        help_handler(env, [])
        return

    cmd_name = args[0]

    for cmd in commands:
        if cmd.matches(cmd_name):
            if len(args) > 1 and args[1] in ("--help", "-h"):
                cmd.print_help(path)
                return

            if cmd.subcommands and len(args) > 1:
                dispatch(args[1:], cmd.subcommands, env, path + [cmd.names[0]])
            elif cmd.handler:
                if env is None:
                    env = Environment()
                cmd.handler(env, args[1:])
            else:
                cmd.print_help(path)
            return

    print(f"Unknown command: {cmd_name}")

def main():
    env = Environment()
    dispatch(sys.argv[1:], root_commands, env)
