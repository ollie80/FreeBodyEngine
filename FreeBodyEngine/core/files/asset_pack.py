import os
import sys
import json
import struct

from FreeBodyEngine.core.files.system import FileSystem
from FreeBodyEngine.core.files.stream import FileStream
from FreeBodyEngine.core.files.resource import FileResource
from FreeBodyEngine.core.files.dev import get_user_file_path, DevFileStream
from FreeBodyEngine import get_flag, warning
from FreeBodyEngine.core.files import ASSET_WRITES_PERMITTED

MAGIC = b"FBAP"
VERSION = 1


class AssetPack:
    """Reads the `.pak` format written by build/builder.py's bundle_assets():
    a MAGIC + version + entry-count header, an entry table (path, absolute
    data offset, data length), then the raw concatenated data. The whole
    table is parsed once at construction so any entry is then a direct
    slice - no per-read scanning."""

    def __init__(self, data: bytes):
        """Parses `data` (the whole `.pak` file's bytes) immediately -
        raises ValueError if it isn't a valid, current-version pak."""
        if data[0:4] != MAGIC:
            raise ValueError("Not a valid FreeBodyEngine asset pack (bad magic).")

        version, count = struct.unpack_from("<HI", data, 4)
        if version != VERSION:
            raise ValueError(f"Unsupported asset pack version {version} (expected {VERSION}).")

        self._data = data
        self._index: dict[str, tuple[int, int]] = {}

        pos = 10
        for _ in range(count):
            path_len = struct.unpack_from("<H", data, pos)[0]
            pos += 2
            path = data[pos:pos + path_len].decode("utf-8")
            pos += path_len
            offset, length = struct.unpack_from("<QI", data, pos)
            pos += 12
            self._index[path] = (offset, length)

    def __contains__(self, path: str) -> bool:
        return path in self._index

    def read(self, path: str) -> bytes:
        """Returns the raw bytes stored at `path` - a direct slice of the
        already-loaded pack data, since __init__ parsed the entry table up
        front. Raises KeyError if `path` isn't in this pack (check with
        `in` first)."""
        offset, length = self._index[path]
        return self._data[offset:offset + length]


class AssetPackStream(FileStream):
    """A read-only FileStream view onto one entry of an AssetPack.

    `.path` mirrors DevFileStream's same-named attribute - callers (notably
    fbusl.compile(), which duck-types a source object as `.data.path` +
    `.read()` for error-message filenames) expect any FileStream to carry
    one, regardless of backend."""

    def __init__(self, pack: AssetPack, path: str):
        """Wraps the entry at `path` within `pack` - reads nothing yet."""
        self._pack = pack
        self._path = path
        self.path = path

    def read(self, size=-1, offset=0) -> bytes:
        """Returns `size` bytes starting at `offset` into the entry's data
        (the whole entry when `size` is -1, the default). Re-reads the full
        entry from the pack on every call rather than caching it."""
        data = self._pack.read(self._path)
        return data[offset:] if size == -1 else data[offset:offset + size]


class AssetPackFileSystem(FileSystem):
    """The release-mode FileSystem: reads bundled `.pak` files sitting next
    to the frozen executable (see build/builder.py's run_pyinstaller, which
    ships `dist/assets/*.pak` as loose sibling files). `user://` paths are
    the one exception - runtime-writable data (saves, logs) isn't part of
    any read-only pak, so those still hit the real filesystem, same as
    DevFileSystem does."""

    PACK_NAMES = ("data", "images", "mesh")

    ATLAS_METADATA_KEY = "_ENGINE_atlas.json"
    ATLAS_IMAGE_KEY = "_ENGINE_atlas.png"

    def __init__(self, packs: dict[str, AssetPack] | None = None, asset_dir: str | None = None):
        """Loads every `PACK_NAMES` `.pak` found under `asset_dir` (default:
        an `assets/` directory next to the frozen executable), unless
        `packs` is given directly (mainly for tests). Also loads the shared
        atlas's UV metadata out of the "data" pack, if present."""
        super().__init__()
        base = asset_dir or os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "assets")
        self.packs = packs if packs is not None else self._load_packs(base)

        # build/atlas_gen.py packs every source image into one shared atlas
        # texture at build time - the original file no longer exists
        # standalone in any pak under its own name, only as a named region
        # of this atlas. Loaded once here so texture loading can look a
        # requested path up as an atlas region instead of a real file.
        self.atlas_uv: dict[str, tuple[float, float, float, float]] = {}
        data_pack = self.packs.get("data")
        if data_pack is not None and self.ATLAS_METADATA_KEY in data_pack:
            self.atlas_uv = json.loads(data_pack.read(self.ATLAS_METADATA_KEY).decode("utf-8"))

        self.user_files_path = self.sanitise_path(get_user_file_path())

    def _load_packs(self, base: str) -> dict[str, AssetPack]:
        packs = {}
        for name in self.PACK_NAMES:
            pak_path = os.path.join(base, f"{name}.pak")
            if os.path.exists(pak_path):
                with open(pak_path, "rb") as f:
                    packs[name] = AssetPack(f.read())
        return packs

    def _resolve(self, path: str) -> str:
        path = self.sanitise_path(path)
        if path.startswith("engine://"):
            return "engine/" + path.removeprefix("engine://")
        return path

    def get_atlas_uv(self, path: str) -> tuple[float, float, float, float] | None:
        """Returns the (x, y, w, h) normalized UV rect `path` was packed
        into the shared atlas at, or None if it isn't an atlas-packed image
        (e.g. it's a non-image asset, or this is DevFileSystem/not release
        mode - other FileSystem classes simply don't define this method,
        callers should use getattr(fs, 'get_atlas_uv', None))."""
        return self.atlas_uv.get(self._resolve(path))

    def ensure_path(self, path: str) -> bool:
        """Returns whether `path` exists as an entry in any loaded pack."""
        resolved = self._resolve(path)
        return any(resolved in pack for pack in self.packs.values())

    def get_file(self, path: str):
        """Resolves `path` to a FileResource. `user://` paths go straight
        to the real filesystem (same as DevFileSystem, since packs are
        read-only); anything else is looked up across every loaded pack,
        falling back to a region of the shared atlas image if `path` was
        atlas-packed at build time (see get_atlas_uv) rather than bundled
        as its own pack entry. Warns and returns None if `path` isn't found
        anywhere."""
        sanitised = self.sanitise_path(path)

        if sanitised.startswith("user://"):
            system_path = os.path.expanduser(self.user_files_path + sanitised.removeprefix("user://"))
            stream = DevFileStream(system_path, get_flag(ASSET_WRITES_PERMITTED, False))
            return self._add(FileResource(self.generate_file_id(), stream, path))

        resolved = self._resolve(sanitised)
        for pack in self.packs.values():
            if resolved in pack:
                stream = AssetPackStream(pack, resolved)
                return self._add(FileResource(self.generate_file_id(), stream, path))

        if resolved in self.atlas_uv:
            # Packed into the shared atlas at build time (build/atlas_gen.py)
            # - there is no standalone pak entry for it, only a named region
            # of the atlas image. The stream here is intentionally empty:
            # load_texture() must recognize this via get_atlas_uv() and load
            # the shared atlas instead of reading this resource directly -
            # returning a resource at all (rather than None) is what lets
            # file.file_path reach that check in the first place.
            return self._add(FileResource(self.generate_file_id(), FileStream(), path))

        warning(f"File does not exist in any asset pack: {path}")
        return None
