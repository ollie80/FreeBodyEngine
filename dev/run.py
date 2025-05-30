import subprocess
import os
import sys
import json


try:
        
    # Define paths
    build_script = os.path.abspath("./FreeBodyEngine/build/builder.py")

    run_flags = ["--dev"]

    #pass on flags
    flags = sys.argv
    del flags[0]

    subprocess.run(["python", build_script, "--dev"], check=True)

    txt = open('build.json')
    build_config = json.loads(txt.read())

    main_script = os.path.abspath(build_config['main_file'])


    subprocess.run(["python", main_script, *run_flags, *flags])

except KeyboardInterrupt:
    sys.exit(0)
    