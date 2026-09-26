import os
import json
import hashlib
import re
import subprocess
import sys

from FreeBodyEngine.cli.cpp.macrogen import CppBindingGenerator

SCRIPTS_DIR_NAME = "cpp_scripts"
GEN_DIR_NAME = "gen"
EXTENSION_NAME = "_fbcpp"

CPP_EXT = '.cpp'
HEADER_EXTS = ('.hpp', '.h')


def compile_handler(env, args):
    """CLI entry point for `fb compile_scripts` / `fb cs`. Recompiles every
    `.cpp`/`.hpp`/`.h` file under the project's code directory that changed
    since the last run into one shared extension module, so the project's
    C++ files can `#include` each other and call into each other's
    functions/classes exactly like any normal multi-file C++ project, while
    each one is still individually `import`-able from Python by its own
    file name."""
    project = env.project_id
    force = "--force" in args
    positional = [a for a in args if not a.startswith('--')]
    if positional:
        project = positional[0]

    if project is None:
        print('No project specified or detected.')
        return

    project_path = env.project_registry.get_project_path(project)
    code_path = os.path.abspath(os.path.join(project_path, env.project_registry.get_project_config(project).get('code')))

    status = compile_cpp_scripts(code_path, sys.executable, force=force)
    if status == 'unchanged':
        print("CPP scripts up to date, nothing to compile.")
    elif status == 'no-sources':
        pass
    elif status == 'ok':
        print("CPP scripts compiled successfully.")
    else:
        print("CPP script compilation failed - see the compiler output above.")


class BoundFile:
    """One `.cpp`/`.hpp`/`.h` file, parsed for `//@bind` markers, plus how
    it needs to be fed into the combined build:

    - a header is always safe to `#include` from the generated bindings
      shim (that's what headers are for), so it's never compiled on its
      own - only ever pulled in wherever it's `#include`d.
    - a `.cpp` that binds a class/struct has to be `#include`d into the
      bindings shim too, since pybind11 needs the *full* type definition
      (size, constructors, method pointers) available where it's bound -
      a forward declaration isn't enough the way it is for a free
      function. To avoid defining that class's (non-inline) members twice
      - once from compiling the .cpp itself, once from the shim
      `#include`ing it - a "class-bound" .cpp is treated like a header
      too: pulled in only via the shim, not compiled as its own
      translation unit. (A class meant to be both Python-bound *and*
      called from other .cpp files needs to live in a header anyway, for
      the same reason any normal C++ class shared across files does.)
    - a `.cpp` that only binds free functions doesn't have this problem -
      a forward declaration is all pybind11 needs to reference a function
      - so it's compiled normally as its own translation unit (giving it
      completely ordinary extern linkage other files can also call into)
      and the shim just forward-declares whatever it binds.
    """
    def __init__(self, abs_path: str, code_path: str):
        """Parses `abs_path` for `//@bind` markers immediately (via
        `CppBindingGenerator`) and computes this file's safe, collision-free
        identifier (see `safe_name`)."""
        self.abs_path = abs_path
        self.is_header = abs_path.endswith(HEADER_EXTS)
        self.rel_path = os.path.relpath(abs_path, code_path)
        self.stem = os.path.splitext(os.path.basename(abs_path))[0]
        # Safe, unique C++ identifier for this file's generated registration
        # function - two files with the same basename in different
        # subdirectories must not collide.
        safe_rel = re.sub(r'[^0-9A-Za-z_]', '_', os.path.splitext(self.rel_path)[0])
        self.safe_name = f'{safe_rel}_{hashlib.blake2b(self.rel_path.encode(), digest_size=4).hexdigest()}'
        self.generator = CppBindingGenerator(open(abs_path, encoding='utf-8').read(), self.stem)
        self.generator.parse()

    @property
    def has_bindings(self) -> bool:
        """True if this file declared any bound classes or free
        functions."""
        return self.generator.has_bindings()

    @property
    def is_class_bound_cpp(self) -> bool:
        """True if this is a non-header `.cpp` that binds at least one
        class/struct (see the class docstring for why that changes how it's
        compiled)."""
        return not self.is_header and bool(self.generator.classes)

    @property
    def include_only(self) -> bool:
        """True if this file must only ever be pulled in via `#include`
        (never compiled as its own translation unit) - see the class
        docstring."""
        return self.is_header or self.is_class_bound_cpp

    @property
    def register_fn_name(self) -> str:
        """The name of the generated C++ function that registers this
        file's bindings into a pybind11 module."""
        return f'_fbbind_register_{self.safe_name}'


def discover_files(code_path: str) -> list:
    """Finds every `.cpp`/`.hpp`/`.h` under the project's code directory,
    excluding the generated cpp_scripts/ output directory itself."""
    scripts_dir = os.path.join(code_path, SCRIPTS_DIR_NAME)
    found = []
    for root, dirs, files in os.walk(code_path):
        if os.path.abspath(root) == os.path.abspath(scripts_dir) or os.path.abspath(root).startswith(os.path.abspath(scripts_dir) + os.sep):
            dirs[:] = []
            continue
        for file in files:
            if file.endswith((CPP_EXT,) + HEADER_EXTS):
                found.append(os.path.join(root, file))
    return sorted(found)


def hash_source(source: str) -> str:
    """Returns a stable content hash of `source`, used to detect whether a
    file has changed since the last compile."""
    h = hashlib.blake2b(digest_size=16)
    h.update(source.encode("utf-8"))
    return h.hexdigest()


def _metadata_path(scripts_dir: str) -> str:
    return os.path.join(scripts_dir, 'data.json')


def _load_metadata(scripts_dir: str) -> dict:
    path = _metadata_path(scripts_dir)
    if not os.path.exists(path):
        return {}
    try:
        return json.loads(open(path, encoding='utf-8').read())
    except (json.JSONDecodeError, OSError):
        return {}


def generate_setup_py(sources: list, include_dirs: list, cxx_standard_flag: str) -> str:
    """Renders a `setup.py` that builds `sources` into the `_fbcpp`
    extension module via pybind11/setuptools.

    Finding pybind11's own headers checks the `FBCPP_PYBIND11_INCLUDE`
    env var first, falling back to `import pybind11; pybind11.
    get_include()` only if it's unset - not the other way around, and not
    an unconditional `import pybind11` the way this used to read. On
    desktop that env var is simply never set, so this behaves exactly as
    before (a normal pip-installed pybind11, importable by whatever
    Python is running this file). Cross-compiling for Android needs the
    env var, though - confirmed live via a real build: p4a's own pybind11
    recipe (install_in_hostpython = True) doesn't make it `import`-able
    from the hostpython python-for-android's own CppCompiledComponents
    PythonRecipe.build_compiled_components() actually runs this setup.py
    with, so `import pybind11` crashed outright with a ModuleNotFoundError
    before ever reaching the Extension() definition below - no include_dirs
    value could have mattered at that point, however it was computed. See
    build/android_recipes/freebodyengine_native/__init__.py's own
    get_recipe_env() for where the env var actually gets set, reading the
    same build-dir-relative header path every other p4a recipe needing
    pybind11 uses (Recipe.get_recipe('pybind11', ctx).get_include_dir()) -
    the officially-supported way to consume another recipe's own output,
    as opposed to a live `import` of it."""
    sources_literal = str([s.replace('\\', '/') for s in sources])
    include_dirs_literal = str([d.replace('\\', '/') for d in include_dirs])
    return f"""
import os
from setuptools import setup, Extension

_pybind11_include = os.environ.get("FBCPP_PYBIND11_INCLUDE")
if _pybind11_include is None:
    import pybind11
    _pybind11_include = pybind11.get_include()

ext_modules = [
    Extension(
        "{EXTENSION_NAME}",
        {sources_literal},
        include_dirs={include_dirs_literal} + [_pybind11_include],
        language="c++",
        extra_compile_args=["{cxx_standard_flag}"],
    ),
]

setup(
    # The *distribution* name (pip/wheel metadata - PEP 508 requires it
    # start with a letter or digit) is deliberately not "{EXTENSION_NAME}"
    # itself - that's the *importable module* name instead (set via
    # Extension()'s own first argument above, completely independent of
    # this one; nothing else needs the two to match). Confirmed live via
    # a real Android build: desktop's own build invokes setup.py directly
    # (`build_ext --inplace`, bypassing pip/wheel metadata validation
    # entirely - see compile_cpp_scripts()'s own subprocess command), but
    # python-for-android's CppCompiledComponentsPythonRecipe installs via
    # a real `pip install .`, whose PEP 517 build-backend frontend
    # rejects "{EXTENSION_NAME}" outright ("Invalid distribution name or
    # version syntax") - a leading underscore was never actually valid
    # there, just never exercised by a build strict enough to check.
    name="fbcpp",
    version="0.0.0",
    ext_modules=ext_modules,
    zip_safe=False,
)
"""


def _windows_bundled_clang() -> str | None:
    """The engine bundles its own clang++ for Windows (next to the SDL2/glfw
    DLLs it also ships there) specifically so a game with C++ scripts
    doesn't require the player - or, for a dev build, the developer - to
    have Visual Studio installed just to compile them."""
    candidate = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "lib", "windows", "clang++.exe"))
    return candidate if os.path.exists(candidate) else None


def _build_env(platform_name: str) -> dict:
    env = os.environ.copy()
    if platform_name == 'windows' and 'CXX' not in env:
        clang = _windows_bundled_clang()
        if clang:
            env['CXX'] = clang
            env['CC'] = clang
    return env


def _extra_setup_args(platform_name: str) -> list:
    # distutils' default compiler on Windows is MSVC, which ignores CC/CXX
    # entirely (it always invokes cl.exe) - the mingw32 compiler class is
    # the one that actually respects them, which is what lets CXX above
    # point it at the bundled clang++ instead of requiring MSVC.
    if platform_name == 'windows' and _windows_bundled_clang() and 'CXX' not in os.environ:
        return ['--compiler=mingw32']
    return []


def compile_cpp_scripts(code_path: str, python_executable: str, platform_name: str | None = None, force: bool = False, quiet: bool = False, generate_only: bool = False) -> str:
    """(re)builds every bound `.cpp`/`.hpp`/`.h` file under `code_path` into
    one shared extension module (`cpp_scripts/_fbcpp.<...>`), plus one
    `import`-able Python shim per bound file (`cpp_scripts/<stem>.py`).
    Only actually invokes the compiler when something changed since the
    last call (tracked by content hash in `cpp_scripts/data.json`) - pass
    `force=True` to ignore that and rebuild from scratch.

    `generate_only=True` writes the generated `_bind.cpp`/`_module.cpp`/
    `setup.py`/shim files (steps 1-3 below) but never invokes a compiler at
    all - for a target this host can't build for directly (cross-
    compiling for Android: see build/android_recipes/
    freebodyengine_native/__init__.py, which feeds these pre-generated
    sources to python-for-android's own NDK toolchain instead). Since
    source generation is pure text and genuinely platform-independent (the
    same generated setup.py/*.cpp work as input to any C++ compiler), the
    *codegen* here doesn't need to change per target - only who actually
    invokes the compiler on the result does. Returns "generated" on
    success in this mode (never "unchanged" - always regenerates, there's
    no host build artifact to compare metadata against for staleness).

    Returns "unchanged" (nothing to do), "no-sources" (no .cpp/.hpp/.h files
    at all), "generated" (generate_only=True, see above), "ok", or "failed".
    """
    if platform_name is None:
        platform_name = {'win32': 'windows', 'darwin': 'darwin', 'linux': 'linux'}.get(sys.platform, sys.platform)

    scripts_dir = os.path.join(code_path, SCRIPTS_DIR_NAME)
    gen_dir = os.path.join(scripts_dir, GEN_DIR_NAME)
    os.makedirs(gen_dir, exist_ok=True)

    all_paths = discover_files(code_path)
    if not all_paths:
        return 'no-sources'

    old_metadata = {} if force else _load_metadata(scripts_dir)
    files = [BoundFile(p, code_path) for p in all_paths]
    new_metadata = {f.abs_path: hash_source(f.generator.source) for f in files}

    extension_exists = any(
        name.startswith(EXTENSION_NAME) and not name.endswith(('.py', '.pyi'))
        for name in os.listdir(scripts_dir)
    ) if os.path.isdir(scripts_dir) else False

    if not force and new_metadata == old_metadata and extension_exists:
        return 'unchanged'

    bound_files = [f for f in files if f.has_bindings]

    # 1. One generated "<file>_bind.cpp" per bound file: pulls in whatever
    #    it needs to see the real declarations (an #include for headers and
    #    class-bound .cpp's, a forward declaration for plain functions),
    #    then defines that file's registration function.
    for f in bound_files:
        lines = ['#include <pybind11/pybind11.h>', '#include <pybind11/stl.h>', '#include <memory>', 'namespace py = pybind11;', '']
        if f.include_only:
            lines.append(f'#include "{f.abs_path.replace(chr(92), "/")}"')
        else:
            lines.extend(f.generator.free_function_declarations())
        lines.append('')
        lines.append(f.generator.generate_bindings_function(f.register_fn_name))
        bind_path = os.path.join(gen_dir, f'{f.safe_name}_bind.cpp')
        open(bind_path, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')

        stub_path = os.path.join(scripts_dir, f'{f.stem}.pyi')
        open(stub_path, 'w', encoding='utf-8').write(f.generator.generate_pyi())

        shim_path = os.path.join(scripts_dir, f'{f.stem}.py')
        open(shim_path, 'w', encoding='utf-8').write(
            "# Auto-generated by `fb compile_scripts` - do not edit.\n"
            "import sys as _sys\n"
            f"from {EXTENSION_NAME} import {f.stem} as _mod\n"
            "_sys.modules[__name__] = _mod\n"
        )

    # 2. One aggregator with the single PYBIND11_MODULE entry point a shared
    #    library may have - each bound file gets its own named submodule so
    #    `import <filestem>` (via its shim above) sees only that file's
    #    bindings, not every other file's.
    module_lines = ['#include <pybind11/pybind11.h>', 'namespace py = pybind11;', '']
    for f in bound_files:
        module_lines.append(f'void {f.register_fn_name}(pybind11::module_& m);')
    module_lines.append('')
    module_lines.append(f'PYBIND11_MODULE({EXTENSION_NAME}, m) {{')
    for f in bound_files:
        module_lines.append(f'    {{ auto sub = m.def_submodule("{f.stem}"); {f.register_fn_name}(sub); }}')
    module_lines.append('}')
    open(os.path.join(gen_dir, '_module.cpp'), 'w', encoding='utf-8').write('\n'.join(module_lines) + '\n')

    # 3. Normal sources: every .cpp that isn't include-only compiles as its
    #    own translation unit and links against every other one exactly
    #    like any multi-file C++ project - this (plus headers being
    #    #include-able project-wide) is what "interact with each other like
    #    normal" actually comes down to.
    normal_sources = [f.abs_path for f in files if not f.is_header and not f.include_only]
    gen_sources = [os.path.join(gen_dir, f'{f.safe_name}_bind.cpp') for f in bound_files]
    gen_sources.append(os.path.join(gen_dir, '_module.cpp'))

    cxx_flag = '/std:c++17' if platform_name == 'windows' else '-std=c++17'
    setup_path = os.path.join(scripts_dir, 'setup.py')
    open(setup_path, 'w', encoding='utf-8').write(
        generate_setup_py(normal_sources + gen_sources, [code_path], cxx_flag)
    )

    if generate_only:
        return 'generated'

    env = _build_env(platform_name)
    cmd = [python_executable, setup_path, 'build_ext', '--inplace', *_extra_setup_args(platform_name)]
    # The `build/` directory (compiled .o's) is deliberately left in place
    # between runs - distutils only recompiles a source whose .o is older
    # than it, so keeping it around is exactly what makes "only the changed
    # files" true at the object-file level, on top of the hash check above
    # only deciding whether to rebuild/relink at all.
    result = subprocess.run(cmd, cwd=scripts_dir, env=env, capture_output=True, text=True)

    if result.returncode != 0:
        if not quiet:
            print(result.stdout)
            print(result.stderr)
        return 'failed'

    open(_metadata_path(scripts_dir), 'w', encoding='utf-8').write(json.dumps(new_metadata, indent=2))
    return 'ok'
