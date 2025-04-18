import subprocess
import os
import sys

# Define paths
build_script = os.path.abspath("./FreeBodyEngine/build/build.py")
main_script = os.path.abspath("./main.py")

# Run the build script with the --dev flag
subprocess.run(["python", build_script, "--dev"], check=True)

#pass on flags
flags = sys.argv
del flags[0]

# Run the main script
subprocess.run(["python", main_script, "--dev", *flags])