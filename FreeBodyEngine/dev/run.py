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

        # core.dev.find_project() also puts the project's code dir on
        # sys.path, but only once fb.init() actually runs - which is
        # necessarily after main.py's own top-level imports, since those
        # run the moment the interpreter loads the file. A main.py that
        # imports its own code/ modules the normal way, at the top of the
        # file (the obvious thing to do, and the only way to split a
        # project across more than one file) would `ModuleNotFoundError`
        # before ever reaching fb.init(). Setting PYTHONPATH on the
        # subprocess instead makes the code dir importable from the
        # interpreter's very first line, before any of main.py runs -
        # order-independent, unlike relying on fb.init() alone.
        code_path = os.path.abspath(os.path.join(path, build_config['code']))
        env = os.environ.copy()
        existing_pythonpath = env.get('PYTHONPATH', '')
        env['PYTHONPATH'] = os.pathsep.join(
            p for p in (code_path, existing_pythonpath) if p
        )

        subprocess.run([sys.executable, main_script, *run_flags, *flags], env=env)

    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    main()