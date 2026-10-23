import os
import io
import json

from FreeBodyEngine.core.files import FileResource
from FreeBodyEngine import get_service, error, warning

FONT_FILE = "FONT_FILE"

# CSS-style numeric weight -> the filename suffix a font family's weight
# variant is conventionally shipped under (e.g. "JetBrainsMono-Bold.ttf"
# next to "JetBrainsMono-Regular.ttf") - this is the naming convention
# actually used by every family with real weight variants in this engine's
# own asset set (JetBrainsMono) and is the same one most open-source
# families (Google Fonts et al.) publish under. There's no font file
# metadata to fall back on without a directory-listing capability the
# FileSystem abstraction doesn't have (AssetPackFileSystem's `.pak`s are a
# flat path -> bytes map, DevFileSystem never enumerates a directory) - so
# this is a real, disclosed limitation: a family that ships its weights
# under a different naming scheme won't resolve, and just falls back to
# the base (unweighted) font with a warning instead of erroring.
FONT_WEIGHT_NAMES = {
    100: "Thin", 200: "ExtraLight", 300: "Light", 400: "Regular",
    500: "Medium", 600: "SemiBold", 700: "Bold", 800: "ExtraBold", 900: "Black",
}
FONT_WEIGHT_ALIASES = {"normal": "regular", "book": "regular", "heavy": "black", "demibold": "semibold"}
DEFAULT_FONT_WEIGHT = 400

_WARNED_MISSING_WEIGHTS: set[tuple[str, str]] = set()


def normalize_font_weight(weight) -> tuple[int, str]:
    """Turns a `font_weight` style value (a name like "bold", or a CSS-
    style number 100-900) into (numeric_weight, CanonicalName). Unknown
    names warn and fall back to Regular; numbers snap to the nearest of
    the 9 standard weights."""
    if isinstance(weight, str):
        name = FONT_WEIGHT_ALIASES.get(weight.strip().lower(), weight.strip().lower())
        for number, canonical in FONT_WEIGHT_NAMES.items():
            if canonical.lower() == name:
                return number, canonical
        warning(f'Unknown font weight "{weight}" - using Regular.')
        return DEFAULT_FONT_WEIGHT, FONT_WEIGHT_NAMES[DEFAULT_FONT_WEIGHT]

    nearest = min(FONT_WEIGHT_NAMES, key=lambda number: abs(number - int(weight)))
    return nearest, FONT_WEIGHT_NAMES[nearest]


def _weight_variant_path(font_path: str, weight_name: str) -> str:
    """"FreeMono.ttf" + "Bold" -> "FreeMono-Bold.ttf". Plain string
    manipulation rather than os.path - these are virtual asset paths
    (always "/"-separated, per FileSystem's own convention), not real
    filesystem paths, so splitting on the host OS's separator would
    mangle them on Windows."""
    directory, _, filename = font_path.rpartition("/")
    stem, dot, ext = filename.rpartition(".")
    if not dot:
        stem, ext = filename, ""

    # If font_path already names a specific weight (e.g. resolving "Bold"
    # starting from ".../JetBrainsMono-Regular.ttf" rather than the bare
    # family file), replace that suffix instead of stacking another one
    # onto it.
    for existing_name in FONT_WEIGHT_NAMES.values():
        suffix = f"-{existing_name}"
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break

    new_filename = f"{stem}-{weight_name}.{ext}" if ext else f"{stem}-{weight_name}"
    return f"{directory}/{new_filename}" if directory else new_filename


def _flip_uv(px_left, px_top, px_right, px_bottom, atlas_w, atlas_h):
    """A `.fbfont`'s atlasBounds are pixel coordinates in the *original*
    unflipped atlas PNG (origin top-left, Y down - the PIL convention
    build/atlas_gen.py's AtlasGen uses). The texture actually uploaded to
    the GPU below (via _create_standalone_texture) is flipped 180 degrees
    (both axes) before upload, so a corner (u, v) in the original image
    lives at (1-u, 1-v) in the uploaded texture.

    text.fbvert samples this rect with a *non-reversed* walk (screen-left
    -> uv_rect.x, screen-top -> uv_rect.y, increasing towards
    uv_rect.x+uv_rect.z / .y+uv_rect.w) - it doesn't go through a mesh with
    pre-mirrored UVs the way ordinary sprite quads do. Since the texture
    itself is point-reflected, undoing that with only a translated (but
    same-direction) rect - keeping px_left's flipped value first, in
    left-to-right/top-to-bottom order - would sample the glyph rotated
    180 degrees (confirmed visually: 'M' rendered as 'W'). The fix is to
    flip *without* swapping which corner is which: the corner that was
    left/top stays first, it just lands at (1-u, 1-v) - which necessarily
    makes the second coordinate smaller than the first (a "negative size"
    rect). That's fine: the vertex shader only linearly interpolates
    between the two uniform components, direction doesn't matter."""
    u0, v0 = px_left / atlas_w, px_top / atlas_h
    u1, v1 = px_right / atlas_w, px_bottom / atlas_h
    return (1.0 - u0, 1.0 - v0, 1.0 - u1, 1.0 - v1)


def _font_from_atlas(atlas_image_bytes: bytes, data: dict) -> 'Font':
    """Builds a runtime Font/Glyph set from an MSDF atlas image (raw PNG
    bytes) plus its metadata dict (the `{"atlas", "metrics", "glyphs"}`
    schema font/atlasgen.py's generate_atlas() produces) - shared by both
    load_font() (pre-baked `.fbfont` assets) and resolve_font() (atlases
    built on the fly from a raw .ttf/.otf)."""
    from FreeBodyEngine.graphics.text.font import Font, Glyph  # lazy - avoids a core.files <-> graphics import cycle

    texture = get_service('renderer').texture_manager._create_font_atlas_texture(atlas_image_bytes)

    atlas_w = data["atlas"]["width"]
    atlas_h = data["atlas"]["height"]

    glyphs: dict[int, Glyph] = {}
    for g in data["glyphs"]:
        pb = g["planeBounds"]
        ab = g["atlasBounds"]
        uv_bounds = _flip_uv(ab["left"], ab["top"], ab["right"], ab["bottom"], atlas_w, atlas_h)
        glyphs[g["unicode"]] = Glyph(
            advance=g["advance"],
            plane_bounds=(pb["left"], pb["bottom"], pb["right"], pb["top"]),
            uv_bounds=uv_bounds,
        )

    metrics = data["metrics"]
    return Font(
        texture,
        glyphs,
        data["atlas"]["distanceRange"],
        data["atlas"]["size"],
        metrics["ascender"],
        metrics["descender"],
        metrics["lineHeight"],
    )


def load_font(file: FileResource) -> 'Font':
    """Loads a pre-baked `.fbfont` sidecar (as written by font/atlasgen.py
    / the `freebody create font` CLI command) plus its atlas image."""
    data = json.loads(file.read())

    # The atlas image sits next to the .fbfont file (both written together),
    # referenced by bare filename.
    directory = os.path.dirname(file.file_path)
    image_path = f"{directory}/{data['atlas']['image']}" if directory else data["atlas"]["image"]

    # Deliberately not going through load_file()/load_texture(): the font
    # atlas image is a whole standalone texture that this loader computes
    # its own per-glyph UVs against, not something that should be looked up
    # against the *sprite* atlas load_texture() knows about (both are just
    # "some .png under assets/", but they're unrelated atlases).
    image_file = get_service('files').get_file(image_path)
    return _font_from_atlas(image_file.read(bytes=True), data)


# One resolved Font per (font path, size, range) for the lifetime of the
# process - resolve_font() is meant to be called with a plain style value
# like "test.ttf" on every UI element that uses that font, so without this
# cache every element would reload/regenerate the same atlas.
_FONT_CACHE: dict[tuple[str, int, float], 'Font'] = {}

DEFAULT_FONT_ATLAS_SIZE = 48
DEFAULT_FONT_RANGE_PX = 4.0


def font_cache_extra(size: int = DEFAULT_FONT_ATLAS_SIZE, range_px: float = DEFAULT_FONT_RANGE_PX) -> str:
    """The atlas settings folded into a font's asset-cache hash - one
    place, so a build's bake and a dev-mode bake of the same font agree."""
    return f"{size}:{range_px}"


def bake_font_file(source_abs: str, name: str, size: int = DEFAULT_FONT_ATLAS_SIZE,
                   range_px: float = DEFAULT_FONT_RANGE_PX) -> tuple[str, dict[str, bytes]]:
    """Bakes the `.ttf`/`.otf` at real path `source_abs` into an MSDF atlas
    + `.fbfont` sidecar - the baker core/files/asset_cache.py's
    AssetCache.ensure() runs for fonts, both from a build and lazily in
    dev mode. Returns `(main_name, files)`: the `.fbfont` file name and
    both files to write, named after `name`."""
    from FreeBodyEngine.font.atlasgen import generate_atlas

    atlas_image, data = generate_atlas(source_abs, size, range_px=range_px)
    image_name = f"{name}.png"
    data["atlas"]["image"] = image_name

    png_buffer = io.BytesIO()
    atlas_image.save(png_buffer, format="PNG")

    main = f"{name}.fbfont"
    return main, {main: json.dumps(data).encode("utf-8"), image_name: png_buffer.getvalue()}


def _resolve_dev_font(font_path: str, size: int, range_px: float) -> 'Font | None':
    """Dev mode: loads `font_path` from the project's asset cache, baking
    it there first if it's new or has changed since the last bake. None if
    there's no dev cache, the font isn't a file on disk, or baking fails -
    the caller then generates the atlas in memory instead."""
    from FreeBodyEngine.core.files import asset_cache

    cache = asset_cache.get_dev_cache()
    if cache is None:
        return None
    source = asset_cache.dev_source_path(font_path)
    if source is None:
        return None
    key, source_abs = source

    # A non-default size gets its own entry and files, so two sizes of one
    # font don't keep re-baking over each other.
    suffix = ""
    if (size, range_px) != (DEFAULT_FONT_ATLAS_SIZE, DEFAULT_FONT_RANGE_PX):
        suffix = f"_{size}_{range_px:g}".replace(".", "p")
        key = f"{key}#{suffix}"

    def bake(abs_path, _name):
        return bake_font_file(abs_path, asset_cache.safe_name(source[0]) + suffix, size, range_px)

    try:
        entry, _ = cache.ensure(asset_cache.FONTS, key, source_abs, bake, extra=font_cache_extra(size, range_px))
    except Exception as e:
        warning(f'Could not bake font "{font_path}": {e}')
        return None
    built_file = get_service('files').get_file(cache.virtual_path(asset_cache.FONTS, entry["main"]))
    return load_font(built_file) if built_file is not None else None


def _font_exists(font_path: str) -> bool:
    """Whether `font_path` is a font that can be resolved - a file on disk
    in dev mode, an entry in the font manifest in release."""
    from FreeBodyEngine.core.files import asset_cache

    if asset_cache.get_dev_cache() is not None:
        return asset_cache.dev_source_path(font_path) is not None
    return font_path in _load_font_manifest()

# build/builder.py's build_fonts() pre-builds every project font it finds
# into an MSDF atlas + `.fbfont` under this reserved folder, and records
# {original_relative_path: built_relative_path} in this manifest file - both
# bundled the same way as any other asset, so this is one `get_file()` away
# in dev *and* release. `None` means "not checked yet"; `{}` means "checked,
# nothing built" (e.g. a project that hasn't run a build since adding this
# feature) - both are cached so a missing manifest is only looked up once.
FONT_MANIFEST_KEY = "_ENGINE_font_manifest.json"
_FONT_MANIFEST: dict[str, str] | None = None


def _load_font_manifest() -> dict[str, str]:
    global _FONT_MANIFEST
    if _FONT_MANIFEST is not None:
        return _FONT_MANIFEST

    manifest_file = get_service('files').get_file(FONT_MANIFEST_KEY)
    content = manifest_file.read() if manifest_file is not None else ""
    try:
        # DevFileSystem.get_file() on a path that doesn't exist yet (true
        # for any project that hasn't run a dev/release build since font
        # pre-baking was added) auto-creates an empty stub file there when
        # writes are permitted (true by default in dev mode) -
        # `manifest_file` then comes back non-None but empty, not None, so
        # this can't just be an `if manifest_file is not None` check.
        _FONT_MANIFEST = json.loads(content) if content else {}
    except ValueError:
        _FONT_MANIFEST = {}
    return _FONT_MANIFEST


def resolve_font(font_path: str, size: int = DEFAULT_FONT_ATLAS_SIZE, range_px: float = DEFAULT_FONT_RANGE_PX,
                  weight=DEFAULT_FONT_WEIGHT) -> 'Font | None':
    """Turns a plain path to a raw font file (a `font` style value like
    "test.ttf") into a ready-to-render Font.

    `weight` (a name like "bold"/"semibold", or a CSS-style number
    100-900 - see FONT_WEIGHT_NAMES) is resolved to a sibling file next to
    `font_path` following the "{family}-{Weight}.ttf" naming convention
    (see _weight_variant_path) *before* anything else below runs - the
    manifest lookup and cache both key off the actual resolved path, so a
    bold variant is fully a separate font/atlas from its regular weight,
    not a runtime style applied to one shared atlas (there's no italic/
    bold synthesis - this only ever selects a real, separately-authored
    font file).

    That lookup never goes through get_file(): DevFileSystem.get_file()
    on a path that turns out not to exist
    - which a guessed weight-variant filename very often will - creates
    an empty stub file there when ASSET_WRITES_PERMITTED is set (true in
    dev mode), then FreeType fails on that empty "font" with an opaque
    FT_Exception instead of a clean "not found". In dev mode it checks
    the disk directly, in release the manifest (see _font_exists()); if
    no matching sibling file exists, warns once and falls back to
    `font_path` at its base weight.

    In dev mode the (possibly weight-resolved) font is loaded from the
    project's asset cache, baked there first if it's new or changed (see
    core/files/asset_cache.py). In release it's looked up in the manifest
    build_fonts() bundles and loaded from the pre-built `.fbfont` that
    points at. If neither finds it (a release `engine://` font, which
    build_fonts() doesn't cover), its atlas is generated on the spot and
    kept in memory for this run only."""
    weight_number, weight_name = normalize_font_weight(weight)
    if weight_number != DEFAULT_FONT_WEIGHT:
        candidate = _weight_variant_path(font_path, weight_name)
        if _font_exists(candidate):
            font_path = candidate
        elif (font_path, weight_name) not in _WARNED_MISSING_WEIGHTS:
            # UI text is redrawn every frame (see ui/renderer.py's
            # _draw_text) - without deduping, a label that just always
            # requests an unavailable weight would print this warning 60
            # times a second forever instead of once.
            _WARNED_MISSING_WEIGHTS.add((font_path, weight_name))
            warning(f'No "{weight_name}" weight variant found for "{font_path}" (looked for "{candidate}") - using the base font instead.')

    cache_key = (font_path, size, range_px)
    cached = _FONT_CACHE.get(cache_key)
    if cached is not None:
        return cached

    font = _resolve_dev_font(font_path, size, range_px)
    if font is not None:
        _FONT_CACHE[cache_key] = font
        return font

    from FreeBodyEngine.core.files import asset_cache
    manifest = _load_font_manifest() if asset_cache.get_dev_cache() is None else {}
    built_path = manifest.get(font_path)
    if built_path is not None:
        built_file = get_service('files').get_file(built_path)
        if built_file is not None:
            font = load_font(built_file)
            _FONT_CACHE[cache_key] = font
            return font

    font_file = get_service('files').get_file(font_path)
    if font_file is None:
        error(f"Cannot resolve font: '{font_path}' was not found.")
        return None

    from FreeBodyEngine.font.atlasgen import generate_atlas

    atlas_image, data = generate_atlas(io.BytesIO(font_file.read(bytes=True)), size, range_px=range_px)

    png_buffer = io.BytesIO()
    atlas_image.save(png_buffer, format="PNG")

    font = _font_from_atlas(png_buffer.getvalue(), data)
    _FONT_CACHE[cache_key] = font
    return font
