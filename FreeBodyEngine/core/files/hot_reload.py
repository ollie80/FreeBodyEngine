"""Dev-mode-only hot reload: a path-keyed registry of live Texture/Material/
Sprite objects (each of loaders/texture.py, loaders/material.py, and
loaders/sprite.py registers what it creates here, and returns the cached
object on a repeat load_file() for the same path instead of creating a
second, independent instance - hot reload only has anything to update in
place if every consumer of a given asset path is actually sharing one
object), and the FILE_CHANGE -> reload dispatch DevFileSystem wires up to
its FileWatcher.

Reloading always mutates the SAME live object in place (same GL texture id,
same Shader's GL program, same Material/Sprite Python object) rather than
creating a new one - nothing tracks who's holding a reference to a loaded
asset, so an in-place update is the only way an edit becomes visible without
restarting the game.

Never active outside dev mode (is_enabled() gates on the DEVMODE flag) - a
release build's AssetPackFileSystem has no FileWatcher and never calls into
this module at all, but the loaders guard on is_enabled() too rather than
just "am I DevFileSystem", so the cache doesn't change a release build's
"always a fresh object" behavior even if that ever became reachable another
way.
"""
import weakref
from FreeBodyEngine import get_service, get_flag, DEVMODE, warning

TEXTURE = "texture"
MATERIAL = "material"
SPRITE = "sprite"

_registry: dict[str, tuple[str, object]] = {}
# Per-path copies handed out to callers - see track_instance().
_instances: dict[str, "weakref.WeakSet"] = {}


def is_enabled() -> bool:
    """Whether hot reload's cache/registry should be used at all - gates on
    the DEVMODE flag, since a release build has no FileWatcher to ever
    trigger a reload from."""
    return get_flag(DEVMODE, False)


def get_cached(path: str, kind: str):
    """Returns the live object at `path` if one was already registered as
    this same `kind`, else None (a fresh load is needed - either nothing's
    been loaded from `path` yet, or it was loaded as a different kind, e.g.
    a texture stack sharing an image path with an ordinary sprite texture)."""
    entry = _registry.get(path)
    if entry is not None and entry[0] == kind:
        return entry[1]
    return None


def register(path: str, kind: str, obj):
    """Records `obj` (as the given `kind` - TEXTURE/MATERIAL/SPRITE) as the
    live object loaded from `path`, so a later edit to `path` can find and
    mutate it in place. Overwrites any previous registration for `path`."""
    _registry[path] = (kind, obj)


def track_instance(path: str, obj):
    """Records a per-object copy handed out for `path`, and returns it.

    A texture or a material can be shared by everything that loads it, so one
    registered object is all those kinds need. A sprite cannot: `visible` and
    `z` are per-object state, and handing the same Sprite to every node that
    loads one file made them impossible to show or hide independently (see
    Sprite.instance). So the registry keeps the canonical object to reload
    *into*, and this keeps track of the copies in use so a reload can reach
    them too.

    Weakly held - a sprite belonging to a node that has been killed should not
    be kept alive by the reloader, and there is no unregister call to make at
    the right moment even if anything knew when that moment was.
    """
    _instances.setdefault(path, weakref.WeakSet()).add(obj)
    return obj


def live_instances(path: str) -> list:
    """Every copy handed out for `path` that is still in use."""
    return list(_instances.get(path, ()))


def reload_asset(path: str):
    """Called for every FILE_CHANGE - a no-op for any path that was never
    loaded (or loaded but never registered here, e.g. a texture *stack*'s
    layers), which is most files in an asset directory on most changes."""
    entry = _registry.get(path)
    if entry is None:
        return

    kind, obj = entry
    try:
        if kind == TEXTURE:
            _reload_texture(path, obj)
        elif kind == MATERIAL:
            _reload_material(path, obj)
        elif kind == SPRITE:
            _reload_sprite(path, obj)
    except Exception as e:
        warning(f'Hot reload of "{path}" failed: {e}')


def reload_shader_source(path: str):
    """Called for every FILE_CHANGE too, separately from reload_asset():
    a changed .fbvert/.fbfrag/.fbgeom isn't itself a registered asset (it
    has no single Material of its own - the same shader file is very
    commonly shared across many materials, e.g. every material using the
    engine's default_shader.fb{vert,frag}), so this instead recompiles
    every *currently registered* Material whose shader was built from this
    exact path, in place, one by one."""
    for kind, obj in list(_registry.values()):
        if kind != MATERIAL:
            continue
        if path in (obj._vert_source_path, obj._frag_source_path, obj._geom_source_path):
            try:
                obj.reload_shader()
            except Exception as e:
                warning(f'Hot reload of shader "{path}" failed for a material: {e}')


def _reload_texture(path, texture):
    from FreeBodyEngine.core.files import get_file
    file = get_file(path)
    if file is None:
        return
    get_service('renderer').texture_manager.reload_standalone_texture(texture.id, file.read(bytes=True))


def _reload_material(path, material):
    from FreeBodyEngine.core.files import get_file
    from FreeBodyEngine.core.files.loaders.toml import load_toml
    file = get_file(path)
    if file is None:
        return
    material.reload(load_toml(file))

    # Sprite.__init__ (graphics/sprite.py) forces its own texture straight
    # into `material.properties['albedo']`, overriding whatever the
    # .fbmat's own data says for albedo - reload() just rebuilt
    # `properties` from that data from scratch, which would silently
    # revert any sprite using this exact Material back to the file's
    # stated albedo (or its default) instead of the sprite's real image.
    # Restore the override for every registered sprite sharing it.
    for kind, obj in list(_registry.values()):
        if kind == SPRITE and obj.material is material:
            obj.material.properties['albedo'] = obj.texture


def _reload_sprite(path, sprite):
    """A changed `.fbspr` itself (not the image/material it points at,
    which are separate registered paths reloaded independently above) -
    e.g. it now names a different image or material entirely."""
    from FreeBodyEngine.core.files import get_file, load_file
    from FreeBodyEngine.core.files.loaders.toml import load_toml
    file = get_file(path)
    if file is None:
        return
    data = load_toml(file)

    img_path = data.get('image')
    if img_path:
        texture = load_file(img_path)
        if texture:
            sprite.texture = texture

    mat_path = data.get('material')
    if mat_path:
        material = load_file(mat_path)
        if material:
            sprite.material = material

    # Same override as Sprite.__init__ and _reload_material() above -
    # whichever of texture/material this sprite ends up with (just
    # swapped in above, or unchanged from before), its material's albedo
    # must be *this* sprite's texture, not whatever that material's own
    # file says.
    sprite.material.properties['albedo'] = sprite.texture

    sprite.visible = data.get('visible', sprite.visible)
    sprite.z = data.get('z', sprite.z)

    # The registered Sprite is the one reloaded *into*; what is actually on
    # screen are the per-object copies handed out from it (see
    # Sprite.instance), so the same swap has to reach each of them. `visible`
    # is deliberately not pushed across: it is the per-object state the copies
    # exist for, and a game that has hidden one of them means it.
    for live in live_instances(path):
        live.texture = sprite.texture
        live.material.properties['albedo'] = live.texture
        if mat_path and live.material is not sprite.material:
            live.material = sprite.material.instance()
            live.material.properties['albedo'] = live.texture
        live.z = sprite.z
