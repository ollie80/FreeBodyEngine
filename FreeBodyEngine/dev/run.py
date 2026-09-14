import subprocess
import os
import sys
import tomllib

from FreeBodyEngine.build.builder import build 

def main(path='./'):
    """CLI entry point for `fb run`: builds the project fresh (`build(path, True)`), then launches its main file in a subprocess with `--dev`/`--path=`/`--name=` plus every original CLI argument forwarded, so the launched process sees the same flags this one was invoked with. Swallows Ctrl+C so interrupting the dev run doesn't surface as a traceback."""
    try:
        flags = sys.argv

        build(path, True)
        
        run_flags = ["--dev", f"--path={path}"]

        txt = open(f'{path}/fbproject.toml')
        build_config = tomllib.loads(txt.read())

        main_script = os.path.join(path, build_config['main_file'])
        run_flags.append("--name="+build_config["name"])

        subprocess.run([sys.executable, main_script, *run_flags, *flags])

    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    main()