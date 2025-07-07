import subprocess
import os
import sys
import tomllib

from FreeBodyEngine.build.builder import build 

def main(path='./'):
    try: 
        flags = sys.argv

        build(path, True)

        run_flags = ["--dev", f"--path={path}"]

        txt = open(f'{path}/fbproject.toml')
        build_config = tomllib.loads(txt.read())

        main_script = os.path.join(path, build_config['main_file'])


        subprocess.run(["python", main_script, *run_flags, *flags])

    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    main()