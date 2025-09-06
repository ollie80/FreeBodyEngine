from FreeBodyEngine.cli.project import ProjectRegistry
from FreeBodyEngine.cli.fulcrum import fulcrum_handler
from FreeBodyEngine.dev.run import main as run_project
from FreeBodyEngine.cli.cpp import compile_handler
from FreeBodyEngine.build.builder import build
from FreeBodyEngine.font.atlasgen import generate_atlas

import tomllib
import sys
import os
import json
import shutil
import platform

from importlib.resources import files

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

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
    dev = False
    if "--dev" in args:
        dev = True
    if len(args) == 0:
        if env.project_path:
            build(env.project_path, dev)
        else:
            print("No project specified or detected.")
    
    else:
        build(env.project_registry.get_project_path(args[0]), dev)

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

def init_handler(env: Environment, args):
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
    if env.project_registry.project_exists(id):
        compile_handler(env, [id])


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

def confirm():
    return input("Are you sure you want to do that? y/N: ").lower().strip() == 'y'

def get_json_log_file(env):
    """Return path to the JSON log for the current project or environment."""
    name = env.project_registry.get_project_config(env.project_id).get('name') if env.project_id else None

    if not name:
        print("No project found.")
        return ''

    system = platform.system()
    if system == "Windows":
        base = os.getenv("APPDATA")
    elif system == "Darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.getenv("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))

    return os.path.join(base, name, "log.jsonl")


def log_read_handler(env, args):
    """Read the last N log entries from the JSON log file, optionally filtered by type."""
    num_entries = int(args[0]) if len(args) > 0 else 50
    log_type = args[1].upper() if len(args) > 1 else None

    log_file = get_json_log_file(env)
    if not os.path.exists(log_file):
        print("No log file found.")
        return

    matching_entries = []
    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
                if log_type is None or entry["type"] == log_type:
                    matching_entries.append(entry)
            except Exception:
                continue

    for entry in matching_entries[-num_entries:]:
        print(f"[{entry['timestamp']}] {entry['type']} [{entry['id']}]: {entry['message']}")


def log_wipe_handler(env, args):
    """Wipe the JSON log file."""
    log_file = get_json_log_file(env)
    if not os.path.exists(log_file):
        print("No log file found.")
        return

    if confirm():
        with open(log_file, "w", encoding="utf-8") as f:
            f.write('')
        print("Log wiped.")
    else:
        print("Aborting.")

def log_traceback_handler(env, args):
    """Print the traceback for a specific log entry by ID, colored like Python traceback, then show warnings/errors at the bottom."""
    if not args:
        print("Usage: fb log traceback <id>")
        return

    log_id = int(args[0])
    log_file = get_json_log_file(env)

    if not os.path.exists(log_file):
        print("No log file found.")
        return

    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
                if entry["id"] == log_id:
                    tb = entry.get("traceback")
                    if tb:
                        if isinstance(tb, list):
                            tb_text = "\n".join(tb)
                        else:
                            tb_text = str(tb)

                        for tb_line in tb_text.splitlines():
                            stripped = tb_line.strip()

                            if tb_line.startswith("Traceback"):
                                print(f"\033[1;31m{tb_line}\033[0m")  # bold red
                            elif stripped.startswith('File'):
                                print(f"\033[33m{tb_line}\033[0m")     # yellow
                            elif any(keyword in tb_line for keyword in ("Error", "Exception")):
                                print(f"\033[31m{tb_line}\033[0m")     # red
                            else:
                                print(f"\033[0m{tb_line}\033[0m")      # gray
                    else:
                        print(f"No traceback stored for log ID {log_id}")

                    print('\n')
                    message = entry.get('message')
                    log_type = entry.get('type')
                    if log_type == "WARNING":
                        print(f"\033[33mWARNING: {message}\033[0m")  # yellow
                    if log_type == "ERROR":
                        print(f"\033[31mERROR: {message}\033[0m")    # red

                    print('\n')
                    return
            except Exception:
                continue

    print(f"No log entry found with ID {log_id}")

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
        if not env.project_registry.project_exists(project):
            print(f'Project with ID "{project}" does not exist.')
            return

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

    if env.project_registry.project_exists(project):
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
            at = "\033[35m@\033[0m"
            if env.project_id:
                prompt += f"{at}{env.project_registry.get_project_name(env.project_id)}"
            elif env.path:
                prompt += f'{at}{env.path}'
            prompt += "\033[35m>\033[0m "

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
def cloc_handler(env, args):
    extensions = {".cpp", ".py", ".fbusl", ".fbvert", ".fbfrag", ".fbspr", ".fbmat"}
    paths_to_check = []

    if args:
        arg = args[0]
        if env.project_registry.project_exists(arg):
            config = env.project_registry.get_project_config(arg)
            project_path = env.project_registry.get_project_path(arg)
            print(f"Counting lines for project '{env.project_registry.get_project_name(arg)}'")

            main_file = os.path.join(project_path, config.get('main_file'))
            if os.path.exists(main_file):
                paths_to_check.append(main_file)
            code_dir = os.path.join(project_path, config.get('code'))

            if os.path.isdir(code_dir):
                paths_to_check.append(code_dir)

            assets_dir = os.path.join(project_path, config.get('assets'))
            if os.path.isdir(assets_dir):
                paths_to_check.append(assets_dir)

        else:
            target_path = os.path.abspath(os.path.join(env.path, arg))
            if not os.path.exists(target_path):
                print(f"Path '{target_path}' does not exist.")
                return
            paths_to_check.append(target_path)
            print(f"Counting lines for directory '{target_path}'")
    else:
        if env.project_id:
            config = env.project_registry.get_project_config(env.project_id)
            project_path = env.project_registry.get_project_path(env.project_id)
            print(f"Counting lines for project '{env.project_registry.get_project_name(env.project_id)}'")

            main_file = os.path.join(project_path, config.get('main_file'))
            if os.path.exists(main_file):
                paths_to_check.append(main_file)

            code_dir = os.path.join(project_path, config.get('code'))
            if os.path.isdir(code_dir):
                paths_to_check.append(code_dir)

            assets_dir = os.path.join(project_path, config.get('assets'))
            if os.path.isdir(assets_dir):
                paths_to_check.append(assets_dir)

        else:
            paths_to_check.append(env.path)
            print(f"Counting lines for directory '{env.path}'")

    total_files = 0
    total_lines = 0
    per_ext = {ext: {"files": 0, "lines": 0} for ext in extensions}

    for path in paths_to_check:
        if os.path.isfile(path):
            ext = os.path.splitext(path)[1]
            if ext in extensions:
                total_files += 1
                per_ext[ext]["files"] += 1
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        line_count = sum(1 for _ in f)
                        total_lines += line_count
                        per_ext[ext]["lines"] += line_count
                except Exception as e:
                    print(f"Error reading {path}: {e}")
        else:
            for root, _, files in os.walk(path):
                for filename in files:
                    ext = os.path.splitext(filename)[1]
                    if ext in extensions:
                        total_files += 1
                        per_ext[ext]["files"] += 1
                        try:
                            with open(os.path.join(root, filename), "r", encoding="utf-8", errors="ignore") as f:
                                line_count = sum(1 for _ in f)
                                total_lines += line_count
                                per_ext[ext]["lines"] += line_count
                        except Exception as e:
                            print(f"Error reading {filename}: {e}")

    print("\nExtension breakdown:")
    for ext in sorted(extensions):
        if per_ext[ext]["files"] > 0:
            print(f"  {ext:<8} {per_ext[ext]['files']:>5} files, {per_ext[ext]['lines']:>7} lines")

    print(f"\nTotal files: {total_files}")
    print(f"Total lines: {total_lines}")

def cwoc_handler(env, args):
    extensions = {".cpp", ".py", ".fbusl", ".fbvert", ".fbfrag", ".fbspr", ".fbmat"}
    paths_to_check = []

    if args:
        arg = args[0]
        if env.project_registry.project_exists(arg):
            config = env.project_registry.get_project_config(arg)
            project_path = env.project_registry.get_project_path(arg)
            print(f"Counting words for project '{env.project_registry.get_project_name(arg)}'")

            main_file = os.path.join(project_path, config.get('main_file'))
            if os.path.exists(main_file):
                paths_to_check.append(main_file)

            code_dir = os.path.join(project_path, config.get('code'))
            if os.path.isdir(code_dir):
                paths_to_check.append(code_dir)

            assets_dir = os.path.join(project_path, config.get('assets'))
            if os.path.isdir(assets_dir):
                paths_to_check.append(assets_dir)

        else:
            target_path = os.path.abspath(os.path.join(env.path, arg))
            if not os.path.exists(target_path):
                print(f"Path '{target_path}' does not exist.")
                return
            paths_to_check.append(target_path)
            print(f"Counting words for directory '{target_path}'")
    else:
        if env.project_id:
            config = env.project_registry.get_project_config(env.project_id)
            project_path = env.project_registry.get_project_path(env.project_id)
            print(f"Counting words for project '{env.project_registry.get_project_name(env.project_id)}'")

            main_file = os.path.join(project_path, config.get('main_file'))
            if os.path.exists(main_file):
                paths_to_check.append(main_file)

            code_dir = os.path.join(project_path, config.get('code'))
            if os.path.isdir(code_dir):
                paths_to_check.append(code_dir)

            assets_dir = os.path.join(project_path, config.get('assets'))
            if os.path.isdir(assets_dir):
                paths_to_check.append(assets_dir)
        else:
            paths_to_check.append(env.path)
            print(f"Counting words for directory '{env.path}'")

    total_files = 0
    total_words = 0
    per_ext = {ext: {"files": 0, "words": 0} for ext in extensions}

    for path in paths_to_check:
        if os.path.isfile(path):
            ext = os.path.splitext(path)[1]
            if ext in extensions:
                total_files += 1
                per_ext[ext]["files"] += 1
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        word_count = sum(len(line.split()) for line in f)
                        total_words += word_count
                        per_ext[ext]["words"] += word_count
                except Exception as e:
                    print(f"Error reading {path}: {e}")
        else:
            for root, _, files in os.walk(path):
                for filename in files:
                    ext = os.path.splitext(filename)[1]
                    if ext in extensions:
                        total_files += 1
                        per_ext[ext]["files"] += 1
                        try:
                            with open(os.path.join(root, filename), "r", encoding="utf-8", errors="ignore") as f:
                                word_count = sum(len(line.split()) for line in f)
                                total_words += word_count
                                per_ext[ext]["words"] += word_count
                        except Exception as e:
                            print(f"Error reading {filename}: {e}")

    print("\nExtension breakdown:")
    for ext in sorted(extensions):
        if per_ext[ext]["files"] > 0:
            print(f"  {ext:<8} {per_ext[ext]['files']:>5} files, {per_ext[ext]['words']:>7} words")

    print(f"\nTotal files: {total_files}")
    print(f"Total words: {total_words}")


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

def create_font(env, args):
    size = 16
    if len(args) == 0:
        project = env.project_id
        if not project:
            print('No project specified or detected.')
            return
    else:
        project = args[0]
        if len(args) < 2:
            print('Usage: freebody create font <project> <relative_font_path> [char_size]')
            return
        relative_font_path = args[1]
        
        if len(args) > 2:
            size = args[2]

    if env.project_registry.project_exists(project):
        conf = env.project_registry.get_project_config(project)

        asset_path = os.path.abspath(os.path.join(env.project_registry.get_project_path(project), conf.get('assets')))
        font_path = os.path.join(asset_path, relative_font_path)
        
        if not os.path.exists(font_path):
            print(f"Font file '{relative_font_path}' does not exsist in directory the asset directory.")
            return
        
        font_registry = os.path.join(asset_path, '.font')
        if not os.path.exists(font_registry):
            os.mkdir(font_registry)

        font_name = os.path.basename(font_path)
        if not font_name.endswith('.ttf'):
            print("Font must be a .ttf file.")
            return

        image, data = generate_atlas(font_path, size)
        image.save(os.path.join(font_registry, font_name.removesuffix('.ttf') + ".png"))
        
        with open(os.path.join(font_registry, font_name.removesuffix('.ttf') + ".json"), 'w') as f:
            json.dump(data, f)

        print(f"Successfully created font with name '{font_name.removesuffix('.ttf')}'.")

    else:
        print(f"Project with ID {project} does not exist.")

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
        Command(["project", "p"], create_project, help_text="Create a new project."),
        Command(["font", "f"], create_font, help_text="Create a font.")
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
    Command(["fulcrum"], fulcrum_handler, help_text='A small text editor.'),
    Command(["compile_scripts", 'cs'], compile_handler, help_text='Compiles CPP scripts.'),
    Command(["cloc"], cloc_handler, help_text="Counts the lines of code in the current directory or specified project."),
    Command(["cwoc"], cwoc_handler, help_text="Counts the words of code in the current directory or specified project."),
    Command(['traceback', 'tb'], log_traceback_handler, help_text="Print the traceback for a log entry by ID.")
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
