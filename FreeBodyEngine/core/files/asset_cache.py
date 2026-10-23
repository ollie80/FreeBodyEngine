"""One on-disk cache for every asset the engine converts into its own
format - fonts into MSDF atlases, glTF models into `.fbmesh` files - shared
by every build (dev, web, Android, release) and by dev mode at runtime.

Lives at `<project>/build/asset_cache/`, outside the asset directory, so
nothing it writes is picked up as a project asset, bundled twice, or seen
by DevFileSystem's FileWatcher. Each kind of asset gets its own folder
(`_ENGINE_fonts/`, `_ENGINE_models/`) named the same as the virtual path a
release build bundles it under - so a baked file refers to its neighbours
by the same path in dev and in release.

`index.json` records, per kind and source path, the source's content hash
and the files baked from it. A source whose hash still matches is never
re-baked; a changed one is re-baked and its old files removed. Hashing
content rather than comparing mtimes survives a fresh checkout or copy,
where mtimes get reset but bytes don't change.

In dev mode the loaders call ensure() directly, so a font or model is baked
the first time it's loaded (or the first time after it changes) - no build
step needed, and the result is reused on every run after that.
"""
import os
import json
import hashlib
from typing import Callable

CACHE_DIR_NAME = "asset_cache"
INDEX_NAME = "index.json"

FONTS = "fonts"
MODELS = "models"

# kind -> folder inside the cache, which is also the virtual path prefix
# baked files are bundled under in a release build.
KIND_DIRS = {
    FONTS: "_ENGINE_fonts",
    MODELS: "_ENGINE_models",
}

# Bumped whenever a baker's output format changes, so every existing cache
# entry of that kind is treated as stale instead of being loaded wrongly.
BAKE_VERSIONS = {
    FONTS: 1,
    MODELS: 1,
}


def cache_root_for(project_path: str) -> str:
    """The cache directory for the project rooted at `project_path`."""
    return os.path.join(project_path, "build", CACHE_DIR_NAME)


def safe_name(rel_path: str) -> str:
    """Flattens a source path into one filename stem, so assets of the same
    name in different folders (e.g. "ui/test.ttf" vs "levels/test.ttf")
    don't collide inside one cache folder."""
    return rel_path.replace("://", "/").replace("/", "__").rsplit(".", 1)[0]


def content_hash(abs_path: str, extra: str = "") -> str:
    """Hash of the file at `abs_path` plus `extra` (whatever settings the
    bake depends on, e.g. a font's atlas size)."""
    h = hashlib.blake2b(digest_size=16)
    with open(abs_path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    h.update(f":{extra}".encode())
    return h.hexdigest()


class AssetCache:
    """A cache directory and its index - see the module docstring."""

    def __init__(self, root: str):
        self.root = root
        self.index_path = os.path.join(root, INDEX_NAME)
        self.index: dict[str, dict[str, dict]] = {}
        if os.path.exists(self.index_path):
            try:
                with open(self.index_path) as f:
                    self.index = json.load(f)
            except (OSError, ValueError):
                self.index = {}

    def kind_dir(self, kind: str) -> str:
        """The real folder `kind`'s baked files are written to."""
        return os.path.join(self.root, KIND_DIRS[kind])

    def file_path(self, kind: str, name: str) -> str:
        """The real path of baked file `name` of `kind`."""
        return os.path.join(self.kind_dir(kind), name)

    def virtual_path(self, kind: str, name: str) -> str:
        """The asset path baked file `name` of `kind` is loaded by -
        DevFileSystem maps it into this cache, a release build bundles it
        under the same path."""
        return f"{KIND_DIRS[kind]}/{name}"

    def lookup(self, kind: str, rel_path: str, source_hash: str) -> dict | None:
        """The index entry for `rel_path` if it was baked from a source with
        `source_hash` and all its files are still on disk, else None."""
        entry = self.index.get(kind, {}).get(rel_path)
        if entry is None or entry.get("hash") != source_hash:
            return None
        if entry.get("version") != BAKE_VERSIONS[kind]:
            return None
        if not all(os.path.exists(self.file_path(kind, name)) for name in entry["files"]):
            return None
        return entry

    def ensure(self, kind: str, rel_path: str, source_abs: str,
               bake: Callable[[str, str], tuple[str, dict[str, bytes]]],
               extra: str = "") -> tuple[dict, bool]:
        """Makes sure `rel_path` (read from `source_abs`) has an up-to-date
        bake, running `bake(source_abs, safe_name)` only if it doesn't.

        `bake` returns `(main_name, {file_name: bytes})` - `main_name` is
        the file a loader opens (the `.fbfont`/`.fbmesh`), the rest are its
        companions (atlas and texture images).

        Returns `(entry, baked)`: the index entry (`{"hash", "main",
        "files", "version"}`) and whether a bake actually ran."""
        source_hash = content_hash(source_abs, extra)
        entry = self.lookup(kind, rel_path, source_hash)
        if entry is not None:
            return entry, False

        main, files = bake(source_abs, safe_name(rel_path))

        os.makedirs(self.kind_dir(kind), exist_ok=True)
        for name, data in files.items():
            with open(self.file_path(kind, name), 'wb') as f:
                f.write(data)

        # Files the previous bake made that this one didn't (e.g. a model
        # that lost a texture) would otherwise sit in the cache forever.
        previous = self.index.get(kind, {}).get(rel_path)
        if previous is not None:
            for name in previous.get("files", []):
                if name not in files:
                    try:
                        os.remove(self.file_path(kind, name))
                    except OSError:
                        pass

        entry = {
            "hash": source_hash,
            "main": main,
            "files": list(files.keys()),
            "version": BAKE_VERSIONS[kind],
        }
        self.index.setdefault(kind, {})[rel_path] = entry
        self.save()
        return entry, True

    def save(self):
        """Writes the index, via a temporary file so a crash mid-write (or
        the game and a build both writing) can't leave it half-written."""
        os.makedirs(self.root, exist_ok=True)
        tmp_path = self.index_path + ".tmp"
        with open(tmp_path, 'w') as f:
            json.dump(self.index, f, indent=1)
        os.replace(tmp_path, self.index_path)


# ----------------------------------------------------------------
# Dev mode
# ----------------------------------------------------------------

_DEV_CACHE: AssetCache | None = None


def get_dev_cache() -> AssetCache | None:
    """The current project's cache when running in dev mode, else None (a
    release build only ever reads what was bundled into its `.pak`s)."""
    global _DEV_CACHE
    from FreeBodyEngine import get_flag, DEVMODE
    if not get_flag(DEVMODE, False):
        return None
    if _DEV_CACHE is None:
        from FreeBodyEngine.core.dev import get_project
        _DEV_CACHE = AssetCache(cache_root_for(get_project().path))
    return _DEV_CACHE


def dev_source_path(path: str) -> tuple[str, str] | None:
    """Resolves an asset path to `(cache_key, real_path)` for baking in dev
    mode, or None if it isn't a file on disk that can be baked (a `user://`
    path, an already-baked file, or a file that doesn't exist).

    Checks the disk directly rather than going through DevFileSystem's
    get_file(), which creates an empty stub file at any missing path when
    asset writes are allowed."""
    from FreeBodyEngine.core.dev import get_project

    if path.startswith("user://"):
        return None
    if path.startswith("engine://"):
        from importlib.resources import files
        rel = path.removeprefix("engine://")
        real = str(files('FreeBodyEngine.engine_assets').joinpath(rel))
        key = "engine/" + rel
    else:
        if path.split("/", 1)[0] in KIND_DIRS.values():
            return None
        project = get_project()
        real = os.path.join(project.path, project.assets, path)
        key = path
    if not os.path.isfile(real):
        return None
    return key, real
