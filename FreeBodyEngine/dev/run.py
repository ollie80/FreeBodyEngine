import subprocess
import os
import sys
import time
import shutil
import glob
import tomllib

from FreeBodyEngine.build.builder import build

def main(path='./'):
    """CLI entry point for `fb run`: builds the project fresh (`build(path, True)`), then launches its main file in a subprocess with `--dev`/`--path=`/`--name=` plus every original CLI argument forwarded, so the launched process sees the same flags this one was invoked with. Swallows Ctrl+C so interrupting the dev run doesn't surface as a traceback.

    `--web` (see get_build_platform() in build/builder.py, which also
    checks for this same flag) takes a completely different path here too
    - see _run_web() - since "launch a subprocess" has no web equivalent
    at all: there's no second process to launch inside a browser tab, and
    the project doesn't run until an actual browser loads the built
    page.

    `--android` is a third, separate path - see _run_android() - for the
    same reason: there's no local subprocess to launch at all, only a
    build to hand to buildozer and a remote device to install it on and
    launch it on over `adb`."""
    try:
        flags = sys.argv

        if "--web" in flags:
            _run_web(path)
            return

        if "--android" in flags:
            _run_android(path)
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

def _find_tool(name):
    """Looks for an executable named `name`, checking next to the current
    interpreter first (where `pip install`-ed console scripts like
    `buildozer` land, in the same venv `fb` itself is running from) before
    falling back to a plain `PATH` lookup (where a system package like
    `adb` - installed via `pacman`/`apt`, not pip - actually lives).
    Returns None if it can't be found either way."""
    candidate = os.path.join(os.path.dirname(sys.executable), name)
    if os.path.exists(candidate):
        return candidate
    return shutil.which(name)

def _android_package_id(build_config):
    """Derives the Android application id buildozer.spec was generated
    with (see Builder._write_buildozer_spec()) from the project's own
    `fbproject.toml` - `package.domain` is hardcoded to `dev.freebody`
    there, and `package.name` is the project's `name` with every
    non-alphanumeric character replaced with `_`; both computations have
    to stay in sync with that method since nothing here reads the
    generated buildozer.spec back."""
    package_name = "".join(c if c.isalnum() else "_" for c in build_config["name"].lower())
    return f"dev.freebody.{package_name}"

def _run_android(path):
    """`fb run --android`'s entry point: builds the Android dev project
    (see Builder.build_for_dev_android()), runs `buildozer android debug`
    in it to produce a debug APK, installs that APK on whatever device is
    currently reachable over `adb` (a phone plugged in via USB with
    developer options/USB debugging enabled, or a paired wireless
    connection - either way, this is just `adb`'s own device selection,
    nothing android-specific to this engine), launches it via its
    bootstrap Activity, and streams `adb logcat` to this terminal until
    Ctrl+C - no interaction with the phone itself needed beyond the
    one-time developer-options/USB-debugging setup.

    Requires `buildozer` (installed via this project's own
    `pip install buildozer cython`) and `adb` (a system package - e.g.
    `pacman -S android-tools` on Arch) to both be found by _find_tool();
    prints a clear message and bails out rather than a raw
    FileNotFoundError if either is missing."""
    build(path, True)

    android_dir = os.path.abspath(os.path.join(path, "dev", "android"))

    buildozer = _find_tool("buildozer")
    if buildozer is None:
        print("Could not find 'buildozer'. Install it with: pip install buildozer cython")
        return

    adb = _find_tool("adb")
    if adb is None:
        print("Could not find 'adb'. Install it with your system package manager, e.g. 'pacman -S android-tools' on Arch.")
        return

    print("Building Android debug APK (this can take a long time on the first run while buildozer downloads the SDK/NDK)...")
    result = subprocess.run([buildozer, "-v", "android", "debug"], cwd=android_dir)
    if result.returncode != 0:
        print("buildozer build failed - see its output above.")
        return

    apks = glob.glob(os.path.join(android_dir, "bin", "*.apk"))
    if not apks:
        print(f"buildozer reported success but no APK was found under {os.path.join(android_dir, 'bin')}.")
        return
    apk_path = max(apks, key=os.path.getmtime)

    devices = subprocess.run([adb, "devices"], capture_output=True, text=True).stdout
    connected = [line for line in devices.splitlines()[1:] if line.strip().endswith("device")]
    if not connected:
        print("No Android device found by adb. Plug one in over USB with USB debugging enabled (check 'adb devices').")
        return

    txt = open(f'{path}/fbproject.toml')
    build_config = tomllib.loads(txt.read())
    package_id = _android_package_id(build_config)
    activity = f"{package_id}/org.kivy.android.PythonActivity"

    print(f"Installing {os.path.basename(apk_path)}...")
    subprocess.run([adb, "install", "-r", apk_path])

    print(f"Launching {activity}...")
    subprocess.run([adb, "shell", "am", "start", "-n", activity])

    subprocess.run([adb, "logcat", "-c"])
    print("Streaming logcat - press Ctrl+C to stop (the app keeps running on the device).")
    logcat = subprocess.Popen([adb, "logcat"])
    try:
        logcat.wait()
    except KeyboardInterrupt:
        logcat.terminate()

if __name__ == '__main__':
    main()