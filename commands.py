# engine/fb.py
import subprocess
import sys
from . import user_commands

commands = []

def get_command(command):
    return commands

def build(args, name):
    subprocess.run(["python", "FreeBodyEngine/build/builder.py", '--dev', *args], shell=True)

def run(args, name):
    try:
        subprocess.run(["python", "FreeBodyEngine/dev/run.py", *args], shell=True)
    except KeyboardInterrupt:
        sys.exit(0)
    

def create(args, name):
    if len(args) > 0:
        pass
    else:
        print("Usage: freebody/fb create <command>")
    
        
def _help(args, name):
    print("FreeBody Engine CLI")
    print("Usage: freebody/fb <command>")
    print("Commands: build, run")
    sys.exit(1)


def main():
    global commands
    commands = [[["build", "b"], build], [["run", "r"], run], [["create", "c"], create], [["help", "h"], _help]] + user_commands.commands

    if len(sys.argv) < 2:
        _help([])    

    cmd = sys.argv[1]
    args = sys.argv

    del args[0]
    del args[0]

    found = False

    for command in commands:
        if cmd in command[0]:
            command[1](args, command)
            found = True
            break

    if not found:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
