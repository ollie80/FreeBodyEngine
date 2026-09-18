import subprocess
import os
import sys
import time
import tomllib

from FreeBodyEngine.build.builder import build

def main(path='./'):
    """CLI entry point for `fb run`: builds the project fresh (`build(path, True)`), then launches its main file in a subprocess with `--dev`/`--path=`/`--name=` plus every original CLI argument forwarded, so the launched process sees the same flags this one was invoked with. Swallows Ctrl+C so interrupting the dev run doesn't surface as a traceback.

    `--web` (see get_build_platform() in build/builder.py, which also
    checks for this same flag) takes a completely different path here too
    - see _run_web() - since "launch a subprocess" has no web equivalent
    at all: there's no second process to launch inside a browser tab, and
    the project doesn't run until an actual browser loads the built
    page."""
    try:
        flags = sys.argv

        if "--web" in flags:
            _run_web(path)
            return

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

def _run_web(path):
    """`fb run --web`'s entry point: builds the web dev bundle (see
    Builder.build_for_dev_web()), serves `dev/web/` over a plain local
    HTTP server, opens the default browser at it, and blocks until
    Ctrl+C - standing in for run_project()'s own `subprocess.run(...)`
    block above, just waiting on a server instead of a child process
    (there is no process to wait on here; the actual "game" only starts
    once a browser loads the page and Pyodide finishes booting - see
    build/builder.py's generated bootstrap.py)."""
    import webbrowser
    from FreeBodyEngine.dev.web_server import find_free_port, serve_forever_in_background

    build(path, True)

    web_dir = os.path.abspath(os.path.join(path, "dev", "web"))
    port = find_free_port()
    server = serve_forever_in_background(web_dir, port)
    url = f"http://localhost:{port}/index.html"

    print(f"Serving web dev build at {url}")
    print("Press Ctrl+C to stop.")

    try:
        webbrowser.open(url)
    except Exception:
        pass

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()

if __name__ == '__main__':
    main()