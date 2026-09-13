import importlib.resources
import os
import json
import tomllib
import subprocess
import shutil
import hashlib
from pathlib import Path
import sys

import FreeBodyEngine.lib
import sys
import venv
import struct
import venv
import importlib
from FreeBodyEngine.font.atlasgen import generate_atlas
from FreeBodyEngine.build.atlas_gen import AtlasGen
from FreeBodyEngine.build.progress import ProgressBar
from FreeBodyEngine.core.files.loaders.font import FONT_MANIFEST_KEY
from FreeBodyEngine.core.files.loaders.model import GLBParser, GLTFParser, bake_gltf_to_fbmesh, MODEL_MANIFEST_KEY
from FreeBodyEngine import requirements as fb_requirements
from FreeBodyEngine.cli.cpp.compile import compile_cpp_scripts, SCRIPTS_DIR_NAME

SUPPORTED_PLATFORMS = ["windows", "darwin", "linux"]

FONT_FILE_TYPES = ["ttf", "otf"]
DATA_FILE_TYPES = ["txt", "json", "fbusl", "fbvert", "fbfrag", "fbmat", "fbspr", "fbanim", "fbsheet", 'mp3', 'wav', 'toml']
IMAGE_FILE_TYPES = ["png", "jpg", "jpeg"]
# "glb"/"gltf" used to be missing here entirely - a project's glTF models
# were never picked up by locate_assets()/get_engine_assets() at all, so a
# release build silently shipped without them (AssetPackFileSystem has
# nothing to serve `load_file('model.glb')` at runtime). Both now get
# pre-baked into a flat `.fbmesh` by build_models() below rather than
# bundled as raw bytes - see MODEL_FILE_TYPES.
MESH_FILE_TYPES = ["fbx"]
MODEL_FILE_TYPES = ["glb", "gltf"]
FONT_ATLAS_SIZE = 48
FONT_RANGE_PX = 4.0
FONT_BUILD_DIR = "_ENGINE_fonts"
FONT_CACHE_NAME = "_ENGINE_font_cache.json"
MODEL_BUILD_DIR = "_ENGINE_models"
MODEL_CACHE_NAME = "_ENGINE_model_cache.json"

class Builder:
    """Orchestrates a whole project build (dev or release) from `fbproject.toml`
    at `path`: locates assets, pre-bakes fonts/models, generates the texture
    atlas, bundles everything into `.pak`s, and (for a release build) packages
    the project's code with PyInstaller. Building is a side effect of
    construction - `__init__` runs the whole pipeline before returning."""

    def __init__(self, path, dev):
        """Runs the full build pipeline for the project at `path`.

        Args:
            path: Project root directory containing `fbproject.toml`.
            dev: If True, builds loose assets for local development
                (`build_for_dev`); if False, produces a packaged release
                build (`build_for_release`)."""
        self.progress = ProgressBar()
        self.build_settings: dict = load_toml(f'{path}/fbproject.toml')

        args = sys.argv.copy()
        del args[0]


        self.platform = self.get_build_platform(args)

        # Real project files ship `dependencies = ['']` (a list holding one
        # empty string) - passed straight through, that becomes `pip install
        # ''`, which fails. Drop falsy entries before they ever reach pip.
        user_dependencies = [d for d in self.get_user_setting('dependencies') if d]
        self.dependencies: list[str] = user_dependencies + self.get_platform_dependencies(self.platform)
        self.dependencies.append("pyinstaller")

        # If a local FBUSL source checkout sits next to this FreeBodyEngine
        # checkout (this repo's own dev layout - .../freebody/FBUSL beside
        # .../freebody/FreeBodyEngine), install *that* instead of "fbusl"
        # from PyPI, the same way install_freebody() below installs this
        # engine from its own local path rather than PyPI. Without this, any
        # local FBUSL changes (new shader features, bug fixes) silently never
        # reach a built game - the build would fetch whatever old version is
        # published, not what's actually being developed against.
        self.fbusl_source_path = self._find_local_fbusl_source()
        if self.fbusl_source_path:
            self.dependencies = [d for d in self.dependencies if d.split()[0].split(">=")[0].split("==")[0] != "fbusl"]

        self.asset_path = os.path.abspath(os.path.join(path, self.get_user_setting('assets')))
        self.code_path = os.path.abspath(os.path.join(path, self.get_user_setting('code')))
        self.build_path = os.path.abspath(f'{path}/build/')
        self.temp_path = os.path.abspath(f'{path}/build/temp/')
        self.cache_path = os.path.join(self.build_path, "cache.json")

        # Unlike temp_path (wiped by reset_dirs() on every build), this
        # persists across release builds - fonts.build_fonts() needs a
        # stable place to keep previously-built atlases so its own content-
        # hash cache can actually skip rebuilding them next time.
        self.font_cache_path = os.path.join(self.build_path, "fonts")
        self.model_cache_path = os.path.join(self.build_path, "models")
        
        self.output_path = os.path.abspath(f'{path}/dist/')
        self.asset_out_path = os.path.join(self.output_path, 'assets')
        self.main_file = os.path.abspath(os.path.join(path, self.get_user_setting('main_file')))
        
        self.build_cache = self.get_build_cache()

        if self.platform == "web" and not dev:
            self.build_for_web()
        elif self.platform == "web":
            print("Cannot build for web in dev mode, building for your system platform instead.")

        if dev:
            self.output_path = os.path.abspath(f'{path}/dev/assets/')

            self.build_for_dev()
        else:
            self.build_for_release()

    def get_user_setting(self, name: str, default: any = None):
        """Looks up `name` in the project's `fbproject.toml` settings.

        Raises:
            ValueError: if `name` isn't set and no `default` was given."""
        res = self.build_settings.get(name, None)
        if res == None and default == None:
            raise ValueError(f"Value '{name}' not set in the build config.")
        elif res == None:
            return default
        else:
            return res
        
    def get_out_path(self, path: str, root_dir: str):
        """
        Converts a system path into an output path.
        """
        return os.path.abspath(path).removeprefix(root_dir + "\\")


    def get_platform_dependencies(self, platform: str):
        """Returns the pip dependency list for `platform`: the global
        requirements plus whichever of windows/darwin/linux's platform-
        specific requirements apply."""
        requirements = []
        requirements += fb_requirements.GLOBAL

        if platform == "windows":
            requirements += fb_requirements.WINDOWS
        
        elif platform == "darwin":
            requirements += fb_requirements.DARWIN

        elif platform == "linux":
            requirements += fb_requirements.LINUX

        return requirements


    def get_build_platform(self, args: list[str]):
        """Determines which platform to build for: "web" if `--web` is in
        `args`, otherwise the detected host platform ("windows" for
        `win32`, else `sys.platform` itself if it's one of
        `SUPPORTED_PLATFORMS`). Prints a message and returns None if the
        host platform isn't supported."""
        sys_plat = sys.platform
        if "--web" in args:
            return "web"

        elif sys_plat in SUPPORTED_PLATFORMS:                
            return sys_plat
        
        elif sys_plat == "win32":
            return 'windows'
        
        elif sys_plat == "darwin":
            return sys_plat
        
        elif sys_plat == "linux":
            return sys_plat
            
        else:
            print("Current platform is not supported, aborting build.")

    def locate_assets(self):
        """Walks the project's asset directory and buckets every file by
        type (image/data/mesh-or-model/font, per the `*_FILE_TYPES`
        constants). Returns `(images, data, meshes, fonts)`, each an
        `{absolute_path: path_relative_to_the_asset_dir}` map."""
        images = {}
        data = {}
        meshes = {}
        fonts = {}
        for dir_path, _, file_names in os.walk(self.asset_path):
            for file_name in file_names:
                file_type = file_name.split('.')[1]
                file_path = dir_path + "/" + file_name
                if file_type in IMAGE_FILE_TYPES:
                    images[file_path] = get_relative_path(file_path, self.asset_path)
                elif file_type in MESH_FILE_TYPES or file_type in MODEL_FILE_TYPES:
                    meshes[file_path] = get_relative_path(file_path, self.asset_path)
                elif file_type in DATA_FILE_TYPES:
                    data[file_path] = get_relative_path(file_path, self.asset_path)
                elif file_type in FONT_FILE_TYPES:
                    fonts[file_path] = get_relative_path(file_path, self.asset_path)
        return images, data, meshes, fonts

    def bundle_assets(self, paths: dict[str, str], name: str):
        """Writes a `.pak`: a "FBAP" magic + version + entry count, followed
        by an entry table (path, absolute data offset, data length) laid out
        entirely before the data section - see core/files/asset_pack.py's
        AssetPack for the matching reader. An upfront table with absolute
        offsets (vs. the old interleaved `path, data, path, data, ...`
        layout, which had no header/magic at all) lets the reader index the
        whole pack from just the header+table and fetch any entry in O(1)."""
        items = list(paths.items())
        self.progress.stage(f"Bundling {name}.pak", total=max(len(items), 1))
        entries = []
        for i, (src_path, out_path) in enumerate(items, 1):
            entries.append((out_path, open(src_path, "rb").read()))
            self.progress.update(i)

        header_size = 4 + 2 + 4
        table_size = sum(2 + len(out_path.encode("utf-8")) + 8 + 4 for out_path, _ in entries)
        offset = header_size + table_size

        table = bytearray()
        blob = bytearray()
        for out_path, data in entries:
            path_bytes = out_path.encode("utf-8")
            table += struct.pack("<H", len(path_bytes))
            table += path_bytes
            table += struct.pack("<QI", offset, len(data))
            blob += data
            offset += len(data)

        with open(os.path.join(self.asset_out_path, f"{name}.pak"), 'wb') as file:
            file.write(b"FBAP")
            file.write(struct.pack("<HI", 1, len(entries)))
            file.write(table)
            file.write(blob)

        self.progress.done(f"Bundled {len(entries)} file(s) into {name}.pak")

    def reset_dirs(self):
        """Resets the build, temp, and dist directories."""
        if not os.path.exists(self.build_path):
            os.mkdir(self.build_path)

        # rmtree requires the target to already exist - true on a rebuild,
        # false on a project's very first build, which crashed here before
        # ever reaching a real build error.
        if os.path.exists(self.temp_path):
            shutil.rmtree(self.temp_path)
        os.mkdir(self.temp_path)

        if os.path.exists(self.output_path):
            shutil.rmtree(self.output_path)
        os.mkdir(self.output_path)
        os.mkdir(self.asset_out_path)

    def get_build_cache(self):
        """Loads the build cache JSON at `self.cache_path`, or an empty dict
        if it doesn't exist yet."""
        if os.path.exists(self.cache_path):
            return json.loads(open(self.cache_path, 'r').read())
        else:
            return {}

    def create_build_cache(self):
        """Writes the current dependency list out to `self.cache_path`."""
        cache = {}
        cache['dependencies'] = self.dependencies

        open(self.cache_path, 'w').write(cache)


    def get_venv_python(self, venv_path: str) -> str:
        """Returns the path to the Python executable inside the venv at
        `venv_path`, using the platform-appropriate layout (`Scripts/` on
        Windows, `bin/` elsewhere)."""
        if self.platform == "windows":
            return os.path.abspath(os.path.join(venv_path, "Scripts", "python.exe"))
        return os.path.abspath(os.path.join(venv_path, "bin", "python3"))

    def _find_local_fbusl_source(self) -> str | None:
        """Looks for an FBUSL source checkout as a sibling directory of this
        FreeBodyEngine checkout (".../freebody/FBUSL" beside
        ".../freebody/FreeBodyEngine"). Returns its absolute path if found
        (a real source dir with a setup.py/pyproject.toml), else None - in
        which case "fbusl" is left as a normal PyPI dependency, which is the
        correct behavior for anyone without a local FBUSL checkout."""
        engine_repo_root = os.path.abspath(os.path.join(__file__, "..", "..", ".."))
        candidate = os.path.abspath(os.path.join(engine_repo_root, "..", "FBUSL"))
        has_setup = os.path.isfile(os.path.join(candidate, "setup.py"))
        has_pyproject = os.path.isfile(os.path.join(candidate, "pyproject.toml"))
        has_package = os.path.isdir(os.path.join(candidate, "fbusl"))
        if (has_setup or has_pyproject) and has_package:
            return candidate
        return None

    def _run_quiet(self, cmd: list[str]):
        """Runs a subprocess with its output captured rather than streamed
        to the terminal, so the progress bar's single line stays clean
        instead of being interleaved with pip's/PyInstaller's own verbose
        logging. On failure the captured output is printed in full - errors
        are never silently swallowed, only the noisy success-path output is."""
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            self.progress.fail(f"command exited with code {result.returncode}: {' '.join(cmd)}")
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print(result.stderr)
            raise RuntimeError(f"Build step failed: {' '.join(cmd)}")
        return result

    def setup_venv(self):
        """Creates a fresh build-only virtual environment and runs the rest
        of the release code pipeline inside it: installing dependencies,
        FBUSL, and this engine itself, compiling the project's C++ scripts,
        and packaging everything with PyInstaller."""
        venv_path = os.path.abspath(self.build_path+"/venv/")

        self.progress.stage("Creating virtual environment")
        venv.EnvBuilder(with_pip=True).create(venv_path)
        self.progress.done("Created virtual environment")

        executable = self.get_venv_python(venv_path)

        self.install_dependencies(executable)
        self.install_fbusl(executable)
        self.install_freebody(executable)
        self.compile_cpp_scripts(executable)
        self.run_pyinstaller(executable)

    def compile_cpp_scripts(self, venv_executable):
        """Compiles the project's .cpp/.hpp scripts (see cli/cpp/compile.py)
        using the release venv's own Python, so the resulting extension's
        ABI matches whatever CPython PyInstaller ends up embedding - always
        for `self.platform`, i.e. whatever platform this build is actually
        running on. Cross-compiling a CPython extension for a *different*
        OS/arch than the host isn't attempted (nothing in this engine's
        build pipeline cross-compiles - PyInstaller itself only ever
        packages for the host platform too), so a Windows/macOS/Linux
        release still has to be built from that platform, same as before
        this existed."""
        self.progress.stage("Compiling CPP scripts")
        status = compile_cpp_scripts(self.code_path, venv_executable, platform_name=self.platform, force=True, quiet=True)
        if status == 'failed':
            self.progress.fail("CPP script compilation failed")
            raise RuntimeError("CPP script compilation failed - rerun `fb compile_scripts` locally to see the compiler output.")
        self.progress.done("Compiled CPP scripts")

    def install_fbusl(self, venv_executable):
        """Installs FBUSL into the build venv - from `self.fbusl_source_path`
        if a local checkout was found (see `_find_local_fbusl_source`),
        otherwise a no-op (FBUSL is left as a normal PyPI dependency, already
        covered by `install_dependencies`)."""
        if not self.fbusl_source_path:
            return
        self.progress.stage("Installing local FBUSL source into the build environment")
        self._run_quiet([venv_executable, "-m", "pip", "install", self.fbusl_source_path])
        self.progress.done("Installed local FBUSL source into the build environment")

    def install_freebody(self, venv_executable):
        """Installs this local FreeBodyEngine checkout into the build venv,
        so the packaged game ships whatever engine version is actually being
        developed against rather than a published PyPI release."""
        package_path = os.path.abspath(os.path.join(__file__, "..", "..", ".."))
        self.progress.stage("Installing FreeBodyEngine into the build environment")
        self._run_quiet([venv_executable, "-m", "pip", "install", package_path])
        self.progress.done("Installed FreeBodyEngine into the build environment")

    def install_dependencies(self, venv_executable):
        """Installs `self.dependencies` (the project's declared dependencies
        plus platform requirements) into the build venv."""
        self.progress.stage(f"Installing {len(self.dependencies)} dependencies")
        self._run_quiet([venv_executable, "-m", "pip", "install", *self.dependencies])
        self.progress.done(f"Installed {len(self.dependencies)} dependencies")

    def run_pyinstaller(self, venv_executable):
        """Packages the project's `main_file` into a single-file, windowed
        executable with PyInstaller, then moves the resulting binary into
        `self.output_path`. Explicitly bundles the engine's native lib
        directory, every OpenGL submodule (PyOpenGL's platform backend is
        chosen via a dynamic import PyInstaller's static analysis can't
        trace), and any compiled C++ script extensions/shims under
        `self.code_path`."""
        dist_path = os.path.join(self.temp_path, "pyinstaller", 'dist')
        work_path = os.path.join(self.temp_path, "pyinstaller", 'work')
        spec_path = os.path.join(self.temp_path, "pyinstaller", 'game.spec')
        name = self.build_settings.get('name', 'FreeBodyGame')

        spec = importlib.util.find_spec("FreeBodyEngine.lib")

        if spec is None or spec.origin is None:
            raise RuntimeError("Could not locate FreeBodyEngine.lib on the filesystem")

        lib_path = Path(spec.origin).parent

        # PyInstaller requires ';' to separate the source/dest halves of
        # --add-data on Windows and ':' on every POSIX platform - this ran
        # unconditionally with the Windows separator regardless of host OS.
        add_data_sep = ";" if self.platform == "windows" else ":"

        self.progress.stage("Packaging with PyInstaller")

        # PyInstaller finds what to bundle by statically tracing imports from
        # main_file - since the project's code directory is a different
        # folder from main_file and nothing puts it on sys.path for that
        # analysis, `import foo` for any plain .py script under code/ (cpp
        # ones included) would otherwise go untraced and get silently left
        # out of the packaged build.
        cmd = [venv_executable, "-m", "PyInstaller", "--onefile",
                            "--windowed",
                            "--name", name,
                            self.main_file,
                            "--distpath", dist_path,
                            "--workpath", work_path,
                            "--specpath", spec_path,
                            "--paths", self.code_path,
                            "--add-data", f"{lib_path}{add_data_sep}FreeBodyEngine/lib",
                            # PyOpenGL selects its platform backend
                            # (OpenGL.platform.egl/glx/win32/darwin) via a
                            # dynamic import at runtime, which PyInstaller's
                            # static analysis can't see - left unbundled, the
                            # chosen backend fails to import, every GL
                            # function stays unbound (None), and the first
                            # call raises "TypeError: 'NoneType' object is
                            # not callable" deep inside PyOpenGL. Same class
                            # of issue for OpenGL.arrays' numpy/ctypes
                            # backends. Force all of it in regardless of
                            # which backend the target OS actually needs.
                            "--collect-submodules", "OpenGL",
        ]

        # PyInstaller's import tracing can't see through the tiny
        # `sys.modules[__name__] = ...` shim compile_cpp_scripts() generates
        # for each bound .cpp file, nor the compiled extension itself (a
        # binary, not something with imports to trace) - both are added
        # explicitly instead. --add-binary drops them at the frozen app's
        # root, which is always on sys.path for a PyInstaller build, so
        # `import <cpp file's name>` still resolves at runtime.
        cpp_scripts_dir = os.path.join(self.code_path, SCRIPTS_DIR_NAME)
        if os.path.isdir(cpp_scripts_dir):
            for entry in os.listdir(cpp_scripts_dir):
                entry_path = os.path.join(cpp_scripts_dir, entry)
                if os.path.isfile(entry_path) and entry not in ('data.json', 'setup.py'):
                    cmd += ["--add-binary", f"{entry_path}{add_data_sep}."]

        self._run_quiet(cmd)

        # PyInstaller only appends .exe to the produced binary on Windows.
        executable = name + '.exe' if self.platform == "windows" else name
        shutil.move(os.path.join(dist_path, executable), os.path.join(self.output_path, executable))
        self.progress.done("Packaged with PyInstaller")

    def build_code(self):
        """
        Builds code into an execuatable usign pyinstaller.
        """
        self.setup_venv()

    def get_engine_assets(self):
        """Like `locate_assets`, but over the engine's own bundled
        `engine_assets` package directory rather than the project's asset
        directory - every returned relative path is prefixed with
        `'engine/'`, matching the `engine://` asset namespace."""
        images = {}
        data = {}
        meshes = {}
        fonts = {}
        resource = importlib.resources.files(FreeBodyEngine).joinpath("engine_assets")

        with importlib.resources.as_file(resource) as asset_path:
            engine_assets_dir = str(asset_path)

        for dir_path, _, file_names in os.walk(engine_assets_dir):
            for file_name in file_names:
                file_type = file_name.split('.')[1]
                file_path = dir_path + "/" + file_name
                if file_type in IMAGE_FILE_TYPES:
                    images[file_path] = 'engine/' + get_relative_path(file_path, engine_assets_dir)
                elif file_type in MESH_FILE_TYPES or file_type in MODEL_FILE_TYPES:
                    meshes[file_path] = 'engine/' + get_relative_path(file_path, engine_assets_dir)
                elif file_type in DATA_FILE_TYPES:
                    data[file_path] = 'engine/' + get_relative_path(file_path, engine_assets_dir)
                elif file_type in FONT_FILE_TYPES:
                    fonts[file_path] = 'engine/' + get_relative_path(file_path, engine_assets_dir)
        return images, data, meshes, fonts


    def _font_content_hash(self, abs_path: str) -> str:
        """Content hash of a source font file plus the settings its atlas
        was generated with - used to decide whether a previously-built
        atlas is still valid, so re-running a build doesn't regenerate
        every font's MSDF atlas (genuinely slow for a whole family of
        weights) when nothing about it actually changed. Hashing content
        rather than comparing mtimes survives a fresh checkout/copy where
        mtimes get reset but bytes don't change."""
        h = hashlib.blake2b(digest_size=16)
        with open(abs_path, 'rb') as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        h.update(f":{FONT_ATLAS_SIZE}:{FONT_RANGE_PX}".encode())
        return h.hexdigest()

    def build_fonts(self, fonts: dict[str, str], output_dir: str):
        """Pre-builds every given font (.ttf/.otf) into an MSDF atlas +
        `.fbfont` sidecar under `output_dir`/_ENGINE_fonts, and writes a
        {original_relative_path: built_relative_path} manifest next to it -
        core/files/loaders/font.py's resolve_font() reads this same
        manifest at runtime so a `font` style's raw path (e.g.
        "FreeMono.ttf") resolves to the pre-built asset instead of being
        generated on the spot every run. `output_dir` is the *real* project
        asset directory for a dev build (DevFileSystem reads these loose
        files directly, nothing else to do) or a persistent per-project
        build-cache directory for a release build (the caller still has to
        fold the returned data/image file maps into the data.pak/
        images.pak bundles - `output_dir` itself is never bundled, only
        those explicit files are).

        A `_ENGINE_font_cache.json` next to the manifest records each
        source font's content hash - a font already built with the same
        hash is left alone entirely (not re-read, not re-rasterized),
        so re-running a build only pays for fonts that are new or actually
        changed since last time.

        Fonts under "engine://" (rel_path starting with "engine/") are
        skipped - they ship inside the installed FreeBodyEngine package,
        not a project's own build output, so resolve_font()'s on-the-fly
        generation fallback covers those instead.

        Returns (manifest, data_files, image_files) - the latter two are
        {abs_path: out_relative_path} maps in the same shape bundle_assets()
        expects, empty for anything build_for_dev() doesn't need them for.
        """
        manifest: dict[str, str] = {}
        data_files: dict[str, str] = {}
        image_files: dict[str, str] = {}

        items = [(abs_path, rel_path) for abs_path, rel_path in fonts.items() if not rel_path.startswith("engine/")]
        if not items:
            return manifest, data_files, image_files

        font_build_dir = os.path.join(output_dir, FONT_BUILD_DIR)
        os.makedirs(font_build_dir, exist_ok=True)

        cache_path = os.path.join(output_dir, FONT_CACHE_NAME)
        cache: dict[str, str] = {}
        if os.path.exists(cache_path):
            with open(cache_path) as f:
                cache = json.load(f)
        new_cache: dict[str, str] = {}

        built_count = 0
        skipped_count = 0

        self.progress.stage("Building fonts", total=len(items))
        for i, (abs_path, rel_path) in enumerate(items, 1):
            # Flattened so fonts of the same name in different asset
            # subdirectories (e.g. "ui/test.ttf" vs "levels/test.ttf") don't
            # collide in the shared build_dir.
            safe_name = rel_path.replace("/", "__").rsplit(".", 1)[0]
            image_name = f"{safe_name}.png"
            fbfont_abs = os.path.join(font_build_dir, f"{safe_name}.fbfont")
            image_abs = os.path.join(font_build_dir, image_name)
            built_rel = f"{FONT_BUILD_DIR}/{safe_name}.fbfont"

            content_hash = self._font_content_hash(abs_path)
            new_cache[rel_path] = content_hash

            up_to_date = (
                cache.get(rel_path) == content_hash
                and os.path.exists(fbfont_abs)
                and os.path.exists(image_abs)
            )

            if not up_to_date:
                atlas_image, data = generate_atlas(abs_path, FONT_ATLAS_SIZE, range_px=FONT_RANGE_PX)
                data["atlas"]["image"] = image_name
                atlas_image.save(image_abs)
                with open(fbfont_abs, 'w') as f:
                    json.dump(data, f)
                built_count += 1
            else:
                skipped_count += 1

            manifest[rel_path] = built_rel
            data_files[fbfont_abs] = built_rel
            image_files[image_abs] = f"{FONT_BUILD_DIR}/{image_name}"

            self.progress.update(i)

        manifest_abs = os.path.join(output_dir, FONT_MANIFEST_KEY)
        with open(manifest_abs, 'w') as f:
            json.dump(manifest, f)
        data_files[manifest_abs] = FONT_MANIFEST_KEY

        with open(cache_path, 'w') as f:
            json.dump(new_cache, f)

        self.progress.done(f"Built {built_count} font(s), {skipped_count} unchanged")
        return manifest, data_files, image_files

    def _model_content_hash(self, abs_path: str) -> str:
        """Same rationale as _font_content_hash() - a fresh checkout/copy
        resets mtimes without changing bytes, so content is what actually
        decides whether a model needs rebaking."""
        h = hashlib.blake2b(digest_size=16)
        with open(abs_path, 'rb') as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    def build_models(self, meshes: dict[str, str], output_dir: str):
        """Pre-bakes every project `.glb`/`.gltf` into a flat `.fbmesh` (see
        core/files/loaders/model.py's bake_gltf_to_fbmesh()) plus whatever
        textures it embeds, extracted to real files alongside it - a
        release build's runtime (AssetPackFileSystem) then never parses raw
        glTF JSON/accessors at all, only `np.frombuffer()`s the baked
        arrays straight out of the file.

        Content-hash cached exactly like build_fonts() (same manifest +
        cache-file shape, same "rebuild only what actually changed"
        behavior) - baking a large/high-poly model isn't free, and most
        builds change a handful of assets, not all of them.

        `.fbx` meshes (MESH_FILE_TYPES) are left alone here - only
        MODEL_FILE_TYPES (glTF) has a baked path today - and stay in
        `meshes` for the caller's own raw `mesh.pak` bundling.
        """
        manifest: dict[str, str] = {}
        data_files: dict[str, str] = {}
        image_files: dict[str, str] = {}

        items = [
            (abs_path, rel_path) for abs_path, rel_path in meshes.items()
            if rel_path.rsplit(".", 1)[-1].lower() in MODEL_FILE_TYPES
        ]

        model_build_dir = os.path.join(output_dir, MODEL_BUILD_DIR)
        cache_path = os.path.join(output_dir, MODEL_CACHE_NAME)
        cache: dict = {}
        if os.path.exists(cache_path):
            with open(cache_path) as f:
                cache = json.load(f)
        new_cache: dict = {}

        built_count = 0
        skipped_count = 0

        if items:
            os.makedirs(model_build_dir, exist_ok=True)
            self.progress.stage("Building models", total=len(items))

        for i, (abs_path, rel_path) in enumerate(items, 1):
            # Flattened so models of the same name in different asset
            # subdirectories don't collide in the shared build_dir - same
            # reasoning as build_fonts()'s safe_name.
            safe_name = rel_path.replace("/", "__").rsplit(".", 1)[0]
            fbmesh_abs = os.path.join(model_build_dir, f"{safe_name}.fbmesh")
            built_rel = f"{MODEL_BUILD_DIR}/{safe_name}.fbmesh"

            content_hash = self._model_content_hash(abs_path)
            new_cache[rel_path] = content_hash

            cached_images = cache.get(rel_path + ":images", [])
            up_to_date = (
                cache.get(rel_path) == content_hash
                and os.path.exists(fbmesh_abs)
                and all(os.path.exists(os.path.join(model_build_dir, name)) for name in cached_images)
            )

            if not up_to_date:
                with open(abs_path, 'rb') as f:
                    raw = f.read()

                if rel_path.lower().endswith(".glb"):
                    glb = GLBParser(raw)
                    parser = GLTFParser(glb.get_json(), glb.get_binary_buffer())
                else:
                    parser = GLTFParser(json.loads(raw), b"", os.path.dirname(abs_path))

                fbmesh_bytes, images = bake_gltf_to_fbmesh(parser, safe_name)

                with open(fbmesh_abs, 'wb') as f:
                    f.write(fbmesh_bytes)
                for image_name, image_bytes in images.items():
                    with open(os.path.join(model_build_dir, image_name), 'wb') as f:
                        f.write(image_bytes)

                new_cache[rel_path + ":images"] = list(images.keys())
                built_count += 1
            else:
                new_cache[rel_path + ":images"] = cached_images
                skipped_count += 1

            manifest[rel_path] = built_rel
            data_files[fbmesh_abs] = built_rel
            for image_name in new_cache[rel_path + ":images"]:
                image_files[os.path.join(model_build_dir, image_name)] = f"{MODEL_BUILD_DIR}/{image_name}"

            self.progress.update(i)

        # Always written, even if empty (matches build_fonts()'s manifest) -
        # core/files/loaders/model.py's _load_model_manifest() treats a
        # missing manifest file as "never built", but an *empty* one it can
        # still fetch and cache in one request rather than warning on every
        # miss against a file that was never going to exist.
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        manifest_abs = os.path.join(output_dir, MODEL_MANIFEST_KEY)
        with open(manifest_abs, 'w') as f:
            json.dump(manifest, f)
        data_files[manifest_abs] = MODEL_MANIFEST_KEY

        with open(cache_path, 'w') as f:
            json.dump(new_cache, f)

        if items:
            self.progress.done(f"Built {built_count} model(s), {skipped_count} unchanged")
        return manifest, data_files, image_files

    def build_for_web(self, args):
        """Placeholder for a web build target - always raises, since web
        builds aren't implemented yet."""
        raise NotImplementedError("Web builds not yet implemented.")

    def build_for_release(self):
        """Runs the full release pipeline: scans project and engine assets,
        resets the output directories, builds the shared texture atlas,
        pre-bakes fonts and models, bundles everything into `data`/`images`/
        `mesh` `.pak`s, and finally packages the project's code."""
        self.progress.stage("Scanning project assets")
        images, data, meshes, fonts = self.locate_assets()
        engine_images, engine_data, engine_meshes, engine_fonts = self.get_engine_assets()
        self.progress.done("Scanned project assets")

        self.reset_dirs()

        atlas_path = os.path.join(self.temp_path, '_ENGINE_atlas.png')
        atlas_data_path = os.path.join(self.temp_path, '_ENGINE_atlas.json')

        self.progress.stage("Generating texture atlas")
        self.atlas_generator = AtlasGen(images | engine_images)
        self.atlas_generator.save(atlas_path, atlas_data_path)
        self.progress.done("Generated texture atlas")

        _, font_data, font_images = self.build_fonts(fonts | engine_fonts, self.font_cache_path)
        _, model_data, model_images = self.build_models(meshes | engine_meshes, self.model_cache_path)

        data[atlas_data_path] = "_ENGINE_atlas.json"
        data |= engine_data
        data |= font_data
        data |= model_data
        self.bundle_assets(data, 'data')

        # Every source image goes into the shared atlas above for efficient
        # default sprite rendering (load_texture prefers the atlas view
        # whenever one exists - see core/files/loaders/texture.py), but
        # texture *stacks* (sampler2DArray, e.g. tilemap spritesheets) need
        # real standalone per-image pixel data to build their GL texture
        # array layers from - a shared-atlas UV view can't back a
        # sampler2DArray layer. So every source image is also bundled here
        # under its own name, alongside the combined atlas. This duplicates
        # image bytes on disk in exchange for both consumers actually
        # working; deduplicating that is a follow-on optimization, not a
        # correctness requirement.
        self.bundle_assets({atlas_path: '_ENGINE_atlas.png', **images, **engine_images, **font_images, **model_images}, 'images')

        # glTF models (MODEL_FILE_TYPES) are baked into the .fbmesh/manifest
        # pair build_models() just produced above (folded into data.pak/
        # images.pak already) - bundling their original, often much larger
        # raw bytes here too would just double-ship them for nothing. Only
        # MESH_FILE_TYPES (.fbx - no baked path yet) still goes in raw.
        raw_meshes = {
            abs_path: rel_path for abs_path, rel_path in (meshes | engine_meshes).items()
            if rel_path.rsplit(".", 1)[-1].lower() not in MODEL_FILE_TYPES
        }
        self.bundle_assets(raw_meshes, 'mesh')

        self.build_code()
        self.progress.done(f"Successfully built game for release, platform: {self.platform}.")

    def build_for_dev(self):
        """Prepares a development build: pre-bakes project fonts straight
        into the project's own asset directory (loose files, since
        `DevFileSystem` reads them directly rather than from a `.pak`).
        No atlas, model baking, or code packaging happens here - dev mode
        reads everything else directly off disk."""
        self.progress.stage("Preparing development build")
        _, _, _, fonts = self.locate_assets()
        self.build_fonts(fonts, self.asset_path)
        self.progress.done("Successfully built game for development.")


def get_relative_path(path: str, folder: str) -> str:
    """Returns `path` relative to `folder`, as a forward-slash-separated
    (POSIX-style) string regardless of host OS - matching the "/"-separated
    convention virtual asset paths use throughout the FileSystem abstraction."""
    full = Path(path)

    return full.relative_to(folder).as_posix()

def load_text(path: str):
    """Reads and returns the full text contents of the file at `path`."""
    file = open(path, "r")
    text = file.read()
    file.close()
    return text

def load_json(path: str):
    """Reads the file at `path` and parses it as JSON."""
    txt = load_text(path)
    return json.loads(txt)

def load_toml(path: str):
    """Reads the file at `path` and parses it as TOML."""
    txt = load_text(path)
    return tomllib.loads(txt)

def build(path='./', dev=False):
    """Runs a full project build at `path` (dev or release - see `Builder`)."""
    Builder(path, dev)