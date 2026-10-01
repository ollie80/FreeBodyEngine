"""Pushing a code-only change to a device without rebuilding the APK.

A python-for-android dev build puts loose `.py` files and assets inside
the APK and extracts them to the app's private directory on first run.
Nothing about a Python edit requires a new APK - but the normal path
rebuilds one anyway, which costs minutes, reinstalls the app, and is
the reason iterating on a phone is so much slower than on a desktop.

So `fb run --android` works out which of the two it needs. If only
pushable files changed, the changed ones are copied straight into the
extracted app directory and the app is restarted; everything else
falls back to the full build. There is no flag to remember - the
decision is made from what actually changed.

What forces a full build is anything that isn't just a file the app
reads at runtime: buildozer.spec (permissions, icons, services, the
presplash, the Java source directory), the Java sources themselves,
and any compiled .so. Those are packaged, not extracted, and no amount
of pushing will make the running app notice them.

Reaching the private directory uses `run-as`, which the platform
allows for a debuggable build - which a dev build always is. No root,
and nothing to set up on the phone beyond the USB debugging that was
already needed to install anything at all.
"""
import hashlib
import json
import os
import subprocess

# Buildozer's own build cache and output, and the spec that describes
# how to package - none of it is part of the running app's file tree.
_NOT_PUSHABLE_DIRS = {".buildozer", "bin"}
_SPEC_NAME = "buildozer.spec"

# Changing any of these means the APK itself is different, so pushing
# files into the old one would leave the app running something that no
# longer matches what it was built from.
_REBUILD_SUFFIXES = (".so", ".java", ".jar", ".aar", ".xml")

STATE_NAME = ".fb_android_sync.json"


def _digest(path: str) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            sha.update(block)
    return sha.hexdigest()


def fingerprint(android_dir: str, extra_dirs=()) -> tuple[dict, dict]:
    """(pushable, packaged) file digests for the current build output.

    `pushable` is everything the running app reads from its own
    extracted directory. `packaged` is everything that only exists by
    virtue of having been built into the APK - a change to any of it
    means a real build.
    """
    pushable, packaged = {}, {}

    for root, dirs, files in os.walk(android_dir):
        dirs[:] = [d for d in dirs
                   if os.path.relpath(os.path.join(root, d), android_dir).split(os.sep)[0]
                   not in _NOT_PUSHABLE_DIRS]
        for name in files:
            full = os.path.join(root, name)
            relative = os.path.relpath(full, android_dir).replace(os.sep, "/")
            if relative.split("/")[0] in _NOT_PUSHABLE_DIRS:
                continue
            try:
                digest = _digest(full)
            except OSError:
                continue
            if relative == _SPEC_NAME or name.endswith(_REBUILD_SUFFIXES):
                packaged[relative] = digest
            else:
                pushable[relative] = digest

    # The Java directory lives in the project, not the build output, and
    # is compiled in rather than extracted - see the builder's
    # android.add_src support.
    for extra in extra_dirs:
        for root, _dirs, files in os.walk(extra):
            for name in files:
                full = os.path.join(root, name)
                try:
                    packaged["java/" + os.path.relpath(full, extra).replace(os.sep, "/")] = _digest(full)
                except OSError:
                    continue

    return pushable, packaged


def load_state(android_dir: str) -> dict:
    try:
        with open(os.path.join(android_dir, STATE_NAME)) as handle:
            return json.load(handle)
    except Exception:
        return {}


def save_state(android_dir: str, pushable: dict, packaged: dict, package_id: str):
    try:
        with open(os.path.join(android_dir, STATE_NAME), "w") as handle:
            json.dump({"pushable": pushable, "packaged": packaged,
                       "package_id": package_id}, handle)
    except OSError:
        pass  # only costs a slower next run


def app_is_installed(adb: str, package_id: str) -> bool:
    result = subprocess.run([adb, "shell", "pm", "path", package_id],
                            capture_output=True, text=True)
    return result.returncode == 0 and "package:" in result.stdout


def _app_dir(adb: str, package_id: str) -> str | None:
    """Where p4a extracted the app, as a path `run-as` can reach.

    Asked for rather than assumed: the private directory is
    /data/data/<pkg> on some devices and /data/user/0/<pkg> on others,
    and run-as starts in it either way, so a relative path sidesteps
    the difference entirely."""
    result = subprocess.run(
        [adb, "shell", f"run-as {package_id} ls files/app/main.py"],
        capture_output=True, text=True)
    if result.returncode == 0 and "main.py" in result.stdout:
        return "files/app"
    return None


def can_fast_sync(adb: str, package_id: str, pushable: dict, packaged: dict,
                  state: dict) -> tuple[bool, str]:
    """Whether this change can be pushed, and why not when it can't.

    The reason is returned so the run can say which it chose - a build
    that silently takes four minutes when the last one took four
    seconds is worse than one that explains itself."""
    if not state:
        return False, "no previous sync recorded"
    if state.get("package_id") != package_id:
        return False, "package id changed"
    if state.get("packaged") != packaged:
        return False, "packaging changed (spec, Java or native code)"
    if not app_is_installed(adb, package_id):
        return False, "app is not installed on this device"
    if _app_dir(adb, package_id) is None:
        return False, "the installed app's files aren't reachable with run-as"
    if pushable == state.get("pushable"):
        return True, "nothing changed"
    return True, "only app files changed"


def changed_files(pushable: dict, state: dict) -> list[str]:
    previous = state.get("pushable", {})
    return sorted(path for path, digest in pushable.items()
                  if previous.get(path) != digest)


def deleted_files(pushable: dict, state: dict) -> list[str]:
    return sorted(set(state.get("pushable", {})) - set(pushable))


def push(adb: str, package_id: str, android_dir: str, relative_paths: list[str],
         removed: list[str], on_progress=None) -> bool:
    """Copies `relative_paths` into the installed app's own directory.

    Two steps per file because `adb push` cannot write into another
    app's private storage directly: push to a world-writable staging
    path first, then have `run-as` move it across as the app's own
    uid."""
    app_dir = _app_dir(adb, package_id)
    if app_dir is None:
        return False

    staging = "/data/local/tmp/fb_android_sync"
    subprocess.run([adb, "shell", f"rm -rf {staging} && mkdir -p {staging}"],
                   capture_output=True)

    for index, relative in enumerate(relative_paths, 1):
        local = os.path.join(android_dir, relative.replace("/", os.sep))
        remote_tmp = f"{staging}/{index}"
        result = subprocess.run([adb, "push", local, remote_tmp], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Could not push {relative}: {result.stderr.strip()}")
            return False

        parent = os.path.dirname(relative)
        mkdir = f"mkdir -p {app_dir}/{parent} && " if parent else ""
        result = subprocess.run(
            [adb, "shell",
             f"run-as {package_id} sh -c '{mkdir}cat {remote_tmp} > {app_dir}/{relative}'"],
            capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Could not install {relative} into the app: {result.stderr.strip()}")
            return False
        if on_progress:
            on_progress(index, len(relative_paths), relative)

    for relative in removed:
        subprocess.run(
            [adb, "shell", f"run-as {package_id} rm -f {app_dir}/{relative}"],
            capture_output=True)

    # p4a precompiles to .pyc next to the source on first import, and a
    # stale one wins over a newer .py whose timestamp the push didn't
    # preserve. Dropping them costs one slower import and removes the
    # entire class of "I pushed it and nothing changed".
    subprocess.run(
        [adb, "shell", f"run-as {package_id} sh -c 'find {app_dir} -name \"*.pyc\" -delete'"],
        capture_output=True)

    subprocess.run([adb, "shell", f"rm -rf {staging}"], capture_output=True)
    return True


def restart(adb: str, package_id: str, activity: str):
    """Stops the app and starts it again.

    force-stop rather than just launching: the service process runs
    separately and keeps its own loaded Python, so starting the
    activity on top of a running app would leave the old code playing
    audio underneath the new code drawing the UI."""
    subprocess.run([adb, "shell", "am", "force-stop", package_id], capture_output=True)
    subprocess.run([adb, "shell", "am", "start", "-n", activity], capture_output=True)
