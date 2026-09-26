"""Builds the engine's own native (C++) UI/physics modules - the
engine-developer counterpart to `fb compile_scripts`, which only knows
about a *project's* code directory (see cli/cpp/compile.py's own
docstring). Reuses that exact same compile_cpp_scripts()/macrogen.py
pipeline (the `//@bind` marker convention, the generated pybind11 shim,
the hash-based incremental rebuild) - the only thing this script adds is
pointing it at a directory inside the engine package instead of a
project's code/.

Usage: `python scripts/build_native.py [--force]`, from anywhere - always
resolves paths relative to this file, not the current working directory.

Each native/ subdirectory becomes its own independent `_fbcpp` extension
(imported as `<subsystem>.native.<stem>`, e.g. `ui.native.hit_test`) -
kept separate per subsystem rather than one engine-wide extension so a
change to physics/native/ doesn't force ui/native/ to recompile too.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from FreeBodyEngine.cli.cpp.compile import compile_cpp_scripts

ENGINE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "FreeBodyEngine"))

# Every engine subsystem with a native/ subdirectory - add a new entry here
# the day a second subsystem (e.g. physics) gets one.
NATIVE_DIRS = [
    os.path.join(ENGINE_ROOT, "ui", "native"),
]


def main():
    force = "--force" in sys.argv[1:]
    for native_dir in NATIVE_DIRS:
        label = os.path.relpath(native_dir, ENGINE_ROOT)
        if not os.path.isdir(native_dir):
            print(f"[{label}] directory does not exist, skipping")
            continue

        status = compile_cpp_scripts(native_dir, sys.executable, force=force)
        if status == "unchanged":
            print(f"[{label}] up to date, nothing to compile")
        elif status == "no-sources":
            print(f"[{label}] no .cpp/.hpp/.h files found")
        elif status == "ok":
            print(f"[{label}] compiled successfully")
        else:
            print(f"[{label}] FAILED - see compiler output above")
            sys.exit(1)


if __name__ == "__main__":
    main()
