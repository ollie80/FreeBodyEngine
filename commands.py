# engine/fb.py
import subprocess
import sys

def build():
    print("Building not yet implemented")

def run():
    subprocess.run(["python", "FreeBodyEngine/dev/run.py"], shell=True)


def main():
    if len(sys.argv) < 2:
        print("Usage: fb <command>")
        print("Commands: build, run")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "build":
        build()
    elif cmd == "run":
        run()
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
