"""A persistent cache of compiled shaders.

Turning FBUSL source into a backend's shading language is pure, slow
Python: measured at 150ms for one vertex/fragment pair, of which the
GL driver's own compile and link is about 16ms. The other 134ms is
lexing, parsing and semantic analysis, and it produces exactly the
same output every time the same source is compiled for the same
target. This keeps that output on disk so it is produced once per
machine rather than once per launch.

Cached at runtime rather than baked at build time, deliberately. The
engine chooses its backend when it starts - GL33, GL44, and in time
Vulkan or DirectX, decided by what the device and driver turn out to
support - so what a given shader compiles *to* is not known until it
runs. A build-time bake would have to guess every target in advance
and would still miss any backend added later, while a cache keyed on
the target records whatever actually happened. The same applies to
shaders assembled at runtime, which a build step cannot see at all.

What a cached entry is keyed on:

  - the source text, so an edit misses and recompiles
  - the generator, which is the target language
  - the injector's own key, since an injector rewrites the source and
    the AST before generation (see Injector.cache_key)
  - the shader stage
  - CACHE_VERSION, for when this module's own format changes

An injector that cannot describe itself disables caching for that
compile rather than risking a wrong hit - see _injector_key.
"""
import hashlib
import os
import sys
from pathlib import Path

from fbusl import compile as fbusl_compile
from fbusl.injector import Injector

# Bumped when anything about the stored format or the key changes, so
# old entries are missed rather than misread. Part of the key itself,
# so stale files simply stop being found.
CACHE_VERSION = 1

# A compile that produces more than this is not something to be writing
# to disk thousands of times; it is a sign something has gone wrong.
_MAX_ENTRY_BYTES = 4 * 1024 * 1024

_cache_dir: Path | None = None
_cache_disabled = False


def _resolve_cache_dir() -> Path | None:
    """Where compiled shaders live, per platform, or None if nowhere
    sensible exists.

    A user cache directory rather than anywhere inside the project: the
    contents are specific to this machine's driver and backend choice,
    they are regenerable, and they should not end up in source control
    or in a build.
    """
    override = os.environ.get("FB_SHADER_CACHE")
    if override:
        return Path(override)

    from FreeBodyEngine.utils import get_platform
    platform = get_platform()

    if platform == "web":
        return None  # no filesystem to cache onto

    if platform == "android":
        # p4a points this at the app's own private directory, which is
        # the only place an app may write without asking.
        root = os.environ.get("ANDROID_ARGUMENT")
        return Path(root) / "cache" / "shaders" if root else None

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "freebody" / "shaders"

    if sys.platform.startswith("win"):
        root = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP")
        return Path(root) / "freebody" / "shaders" if root else None

    root = os.environ.get("XDG_CACHE_HOME")
    base = Path(root) if root else Path.home() / ".cache"
    return base / "freebody" / "shaders"


def cache_dir() -> Path | None:
    global _cache_dir
    if _cache_dir is None and not _cache_disabled:
        _cache_dir = _resolve_cache_dir()
    return _cache_dir


def _injector_key(injector: Injector) -> str | None:
    """The injector's contribution to the cache key, or None if this
    compile must not be cached.

    A subclass that rewrites source or AST and has not overridden
    cache_key() would inherit the base class's "" and silently collide
    with every other such subclass, so inheriting it is treated as "no
    key" rather than "no effect". Only the base Injector itself gets to
    mean nothing by it.
    """
    base_key = getattr(Injector, "cache_key", None)
    if base_key is None:
        # An fbusl too old to have the hook at all. Without it there is
        # no way to tell an injector that rewrites nothing from one that
        # rewrites everything, so nothing is cached.
        return None
    if type(injector) is Injector:
        return ""
    if getattr(type(injector), "cache_key", None) is base_key:
        return None
    try:
        return injector.cache_key()
    except Exception:
        return None


def _source_text(source) -> str | None:
    """FBUSL accepts a string or anything FileResource-shaped; hashing
    needs the text either way, and reading it here means compile()
    doesn't read it a second time."""
    if isinstance(source, str):
        return source
    read = getattr(source, "read", None)
    if read is None:
        return None
    try:
        return read()
    except Exception:
        return None


def compile_cached(source, shader_type, generator, injector: Injector) -> str:
    """fbusl.compile(), with its result remembered on disk.

    Falls back to compiling normally - and silently - whenever the
    cache cannot be used or trusted: an injector that cannot describe
    itself, a source that cannot be read as text, a platform with
    nowhere to write, an unreadable or oversized entry. The cache is an
    optimisation, and nothing here is allowed to be the reason a shader
    fails to build.
    """
    text = _source_text(source)
    injector_key = _injector_key(injector)
    directory = cache_dir()

    if text is None or injector_key is None or directory is None:
        return fbusl_compile(source, shader_type, generator, injector)

    digest = hashlib.sha256()
    for part in (
        str(CACHE_VERSION),
        getattr(generator, "__module__", ""), getattr(generator, "__qualname__", str(generator)),
        getattr(shader_type, "name", str(shader_type)),
        injector_key,
        text,
    ):
        digest.update(part.encode("utf-8", "replace"))
        digest.update(b"\x00")
    path = directory / f"{digest.hexdigest()}.txt"

    try:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    except OSError:
        pass  # unreadable entry - recompile and try to replace it

    # Compiled from the text rather than the original source object, so
    # a FileResource is read once here rather than again inside
    # compile().
    result = fbusl_compile(text, shader_type, generator, injector)

    try:
        if len(result) <= _MAX_ENTRY_BYTES:
            directory.mkdir(parents=True, exist_ok=True)
            # Written beside the real name and moved into place, so a
            # second process reading this entry never sees half a file.
            temporary = path.with_suffix(f".{os.getpid()}.part")
            temporary.write_text(result, encoding="utf-8")
            os.replace(temporary, path)
    except OSError:
        pass  # read-only filesystem, no space - caching is optional

    return result


def clear() -> int:
    """Deletes every cached shader, returning how many were removed."""
    directory = cache_dir()
    if directory is None or not directory.is_dir():
        return 0
    removed = 0
    for entry in directory.glob("*.txt"):
        try:
            entry.unlink()
            removed += 1
        except OSError:
            pass
    return removed
