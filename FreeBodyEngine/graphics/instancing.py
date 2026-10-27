"""Batching for Renderer.flush_opaque()/flush_transparent() (see
graphics/renderer.py): drawing many sprites in one GPU call.

A sprite is a quad, a material and a transform, and most of a scene's
sprites share their quad and - in what they draw with, if not as objects -
their material: every Sprite has its own material instance (see
Material.instance()), but forty belts are forty instances of one texture.
Drawn one by one, each paid for its own shader bind, property and matrix
uploads and draw call, all from Python - a few hundred microseconds a
sprite, which a screen of a few hundred sprites can't afford.

So calls are grouped by `instance_key()`: the same mesh, a material with an
instanced shader (Material.instanced_shader()), and equal batch_key()s -
the same textures, colours, blend mode and filtering. Each group goes to
the GPU as one instanced draw (Renderer.draw_calls_instanced()), the
per-sprite model matrices and depth nudges in a per-instance vertex
buffer instead of uniforms. Anything without an instanced shader - a
custom shader, a mesh node - is drawn on its own exactly as before.

Ordering. Opaque draws are depth-tested and written, so their order never
mattered for what ends up on screen, and they are grouped freely.
Transparent draws composite in the order they're drawn: they're still
sorted by z, back to front, and only *within* one z are they grouped -
by what they draw with, then farthest first. Two overlapping transparent
sprites of the same z but different textures therefore draw in a fixed
order rather than by their distance from the camera; give them different
z's to choose which is on top (a 2D sprite's z is that control).
"""
import numpy as np

from FreeBodyEngine.graphics.renderer import Call


def instance_key(call: 'Call'):
    """What `call` can share an instanced draw with, or None if it can't be
    instanced at all. Worked out once per call - sorting and splitting both
    ask."""
    cached = call.__dict__.get('_instance_key', ...)
    if cached is not ...:
        return cached
    # Asked for, not assumed: anything drawing through a material-like object
    # of its own that isn't a Material just isn't instanced.
    instanced = getattr(call.material, 'instanced_shader', None)
    shader = instanced() if instanced is not None else None
    key = None if shader is None else (id(shader), id(call.mesh), call.material.batch_key())
    call.__dict__['_instance_key'] = key
    return key


def group_by_state(calls: list['Call']) -> list[list['Call']]:
    """Groups `calls` by what can be drawn together - `instance_key()`, or
    for a call that can't be instanced its own material and mesh - keeping
    each group in the order of its first call."""
    order: list = []
    groups: dict = {}
    for call in calls:
        key = instance_key(call)
        if key is None:
            key = ('alone', id(call.material), id(call.mesh))
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(call)
    return [groups[key] for key in order]


def sort_transparent(calls: list['Call']) -> list['Call']:
    """Back to front by z; within one z, grouped by instance_key() and
    farthest first in each group - see the module docstring. Draws that
    can't be instanced gain nothing from grouping, so they share one group
    and keep plain farthest-first order among themselves."""
    rank: dict = {}
    ranked = []
    for call in calls:
        key = instance_key(call)
        if key is None:
            key = 'not instanced'
        if key not in rank:
            rank[key] = len(rank)
        ranked.append((call.z, -rank[key], call.camera_distance(), call))
    ranked.sort(key=lambda item: item[:3], reverse=True)
    return [item[3] for item in ranked]


def runs(calls: list['Call']) -> list[list['Call']]:
    """Splits `calls` - already in drawing order - into runs that can each be
    one instanced draw: consecutive calls with the same instance_key(). A
    call that can't be instanced is a run of its own."""
    out: list[list['Call']] = []
    last = None
    for call in calls:
        key = instance_key(call)
        if key is not None and key == last:
            out[-1].append(call)
        else:
            out.append([call])
        last = key
    return out


def instance_data(calls: list['Call']) -> np.ndarray:
    """One row per call, float32: its model matrix's sixteen numbers (as
    Transform.model lays them out) and its z - what an instanced shader
    reads per instance (see lite/surface_instanced.fbvert).

    Built from the transforms' position, rotation and scale in one go rather
    than asking each for its 4x4 `model`, which builds three matrices and
    multiplies them, per sprite."""
    count = len(calls)
    px = np.empty(count); py = np.empty(count); angle = np.empty(count)
    sx = np.empty(count); sy = np.empty(count); z = np.empty(count)
    for i, call in enumerate(calls):
        t = call.transform
        px[i] = t.position.x
        py[i] = t.position.y
        angle[i] = t.rotation
        sx[i] = t.scale.x
        sy[i] = t.scale.y
        z[i] = call.z
    radians = np.radians(angle)
    cos, sin = np.cos(radians), np.sin(radians)
    # Transform.model = scale @ rotation @ translation, row-vector form.
    data = np.zeros((count, 17), dtype=np.float32)
    data[:, 0] = sx * cos
    data[:, 1] = sx * sin
    data[:, 4] = -sy * sin
    data[:, 5] = sy * cos
    data[:, 10] = 1.0
    data[:, 12] = px
    data[:, 13] = py
    data[:, 15] = 1.0
    data[:, 16] = z
    return data
