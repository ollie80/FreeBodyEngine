# engine/fb.py
import sys
import subprocess

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
    try:
        subprocess.run(["python", "FreeBodyEngine/dev/run.py", *args], shell=True)
    except KeyboardInterrupt:
        sys.exit(0)

def create_project_handler(args):
    if len(args) < 1:
        print("Usage: fb create project <name>")
        return
    print(f"Creating project '{args[0]}'")

def create_file_handler(args):
    if len(args) < 1:
        print("Usage: fb create file <filename>")
        return
    print(f"Creating file '{args[0]}'")

def help_handler(args):
    print("FreeBodyEngine CLI")
    print("Usage: fb <command> [subcommand] [args]")
    print("Available commands:")
    for cmd in root_commands:
        print("  ", cmd.names[0], "-", cmd.help_text)
    sys.exit(0)

root_commands = [
    Command(["build", "b"], build_handler, help_text="Build the project"),
    Command(["run", "r"], run_handler, help_text="Run the project"),
    Command(["create", "c"], subcommands=[
        Command(["project", "p"], create_project_handler, help_text="Create a new project")
    ], help_text="Create a new resource"),
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
    dispatch(sys.argv[1:], root_commands)
