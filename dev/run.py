import subprocess
import os
import sys
import json

# Define paths
build_script = os.path.abspath("./FreeBodyEngine/build/build.py")

run_flags = ["--dev"]

#pass on flags
flags = sys.argv
del flags[0]


subprocess.run(["python", build_script, "--dev"], check=True)


txt = open('build.json')
build_config = json.loads(txt.read())

main_script = os.path.abspath(build_config['main_file'])


# Run the main script
subprocess.run(["python", main_script, *run_flags, *flags])