# engine/fb.py
import subprocess
import sys

def build(args):
    print("Building not yet implemented.")

def run(args):
    subprocess.run(["python", "FreeBodyEngine/dev/run.py", *args], shell=True)

    

def create(args):
    if len(args) > 0:
        pass
    else:
        print("Usage: fb create <command>")
    
        
def _help(args):
    print("FreeBody Engine CLI")
    print("Usage: fb <command>")
    print("Commands: build, run")
    sys.exit(1)


def main():
    commands = {"build": [["build", "b"], build], "run": [["run", "r"], run], "create": [["create", "c"], create], "help": [["help", "h"], _help]}


    if len(sys.argv) < 2:
        _help([])    

    cmd = sys.argv[1]
    args = sys.argv

    del args[0]
    del args[0]

    found = False

    for command in commands:
        if cmd in commands[command][0]:
            commands[command][1](args)
            found = True
            break

    if not found:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
