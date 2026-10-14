"""The Vulkan backend: FBUSL -> SPIR-V, and the compute/raytrace API
(fb.graphics.create_compute_shader / create_raytrace_shader /
create_compute_buffer) running on it with hardware ray queries.

The compile-only tests run anywhere. The rest need a Vulkan device with
VK_KHR_acceleration_structure + VK_KHR_ray_query and skip without one -
there's no validator in this toolchain, so running the generated SPIR-V
on a real driver and comparing results is the actual test.
"""
import math
import struct

import numpy as np
import pytest

import fbusl
from fbusl.parser import Lexer, Parser
from fbusl.semantic import SemanticAnalyser
from fbusl.node import BinOp, InlineIf, Setter

from FreeBodyEngine.graphics.vulkan.compute import compile_spirv


def parse(source, shader_type=fbusl.ShaderType.COMPUTE):
    tree = Parser(Lexer(source).tokenize()).parse()
    SemanticAnalyser(tree, shader_type).analyse()
    return tree


# -- FBUSL language fixes (no GPU) ---------------------------------------------

def test_inline_if_binds_loosest():
    tree = parse("""
@compute(local_size_x=1)
def main():
    p: vec3 = vec3(1.0, 1.0, 1.0)
    n: vec3 = vec3(0.0, 1.0, 0.0)
    q: vec3 = p + n * 0.5 if p.x > 0.0 else p - n
""")
    value = tree[0].body[2].value
    assert isinstance(value, InlineIf)
    assert isinstance(value.then_expr, BinOp) and value.then_expr.op == "+"


def test_logical_and_bitwise_operators_and_compound_assignment():
    tree = parse("""
@compute(local_size_x=1)
def main():
    i: int = 5
    i += 3
    j: int = (i % 3) ^ (i << 2) | (i >> 1) & 7
    ok: bool = i > 2 and not (j < 0) or False
""")
    setter = tree[0].body[1]
    assert isinstance(setter, Setter) and setter.value.op == "+"
    assert tree[0].body[3].value.type == "bool"


def test_param_qualifiers_and_conditions_ending_in_identifiers():
    parse("""
def bump(v: inout float, by: float):
    v = v + by

@compute(local_size_x=1)
def main():
    k: int = 0
    n: int = 4
    while k < n:
        k += 1
""")


def test_conditions_are_type_checked():
    with pytest.raises(fbusl.FBUSLCompileError):
        parse("""
@compute(local_size_x=1)
def main():
    if undefined_thing > 0.0:
        x: float = 1.0
""")


# -- SPIR-V generation (no GPU) --------------------------------------------------

def test_spirv_header_and_binding_layout():
    code, reflection, _ = compile_spirv("""
@uniform
scale: float

readwrite buffer Data:
    a: float[1]
    b: vec4[1]

@output
color: vec4

@compute(local_size_x=8, local_size_y=4)
def main():
    i: int = GLOBAL_INVOCATION_ID.x
    Data.a[i] = scale
    color = vec4(1.0, 0.0, 0.0, 1.0)
""")
    magic, version = struct.unpack("<II", code[:8])
    assert magic == 0x07230203
    assert version == 0x00010500
    names = [(b["name"], b["kind"], b["binding"]) for b in reflection["bindings"]]
    assert names == [("uniforms", "uniform_buffer", 0), ("color", "storage_image", 1),
                     ("Data.a", "storage_buffer", 2), ("Data.b", "storage_buffer", 3)]
    assert reflection["local_size"] == (8, 4, 1)


def test_raytrace_stage_declares_acceleration_structure():
    _, reflection, module = compile_spirv("""
readwrite buffer Out:
    t: float[1]

@raytrace(local_size_x=1)
def main():
    h: RayHit = trace_ray(make_ray(vec3(0.0, 0.0, 0.0), vec3(0.0, 0.0, 1.0)))
    Out.t[0] = h.t
""", fbusl.ShaderType.RAYTRACE)
    assert reflection["bindings"][-1]["kind"] == "acceleration_structure"
    assert "RayQueryProceedKHR" in module.dump()


def test_fragment_stage_compiles_with_located_outputs():
    _, reflection, module = compile_spirv("""
@output
color: vec4

def main():
    color = vec4(1.0, 1.0, 1.0, 1.0)
""", fbusl.ShaderType.FRAGMENT)
    assert [name for name, _ in reflection["outputs"]] == ["color"]
    dump = module.dump()
    assert "EntryPoint" in dump and "ExecutionMode" in dump


# -- on the GPU, through fb.graphics ------------------------------------------------

@pytest.fixture(scope="module")
def engine():
    import FreeBodyEngine as fb
    fb.set_flag(fb.FORCE_RENDERER, "vulkan")
    try:
        fb.init()
        fb.graphics.ensure_gpu_context()
    except Exception as e:  # no loader or no Vulkan 1.3 device
        pytest.skip(f"no Vulkan device: {e}")
    yield fb


def _needs_ray_tracing(fb):
    if not fb.get_service("renderer").ctx.ray_tracing:
        pytest.skip("this GPU has no hardware ray tracing")


COMPUTE_SRC = """
struct Pair:
    a: float
    b: vec3

@uniform
scale: float
offset: vec3
count: int
rot: mat3
weights: float[4]

readwrite buffer Out:
    f: float[1]
    v: vec4[1]
    n: int[1]

@output
coords: vec2

def hash(x: int) -> int:
    h: int = x * 747796405 + 289133645
    h = ((h >> 16) & 65535) ^ h
    h = h * 1103515245
    return (h >> 8) & 16777215

def classify(x: float) -> float:
    if x < 2.0:
        return 1.0
    elif x < 5.0:
        return 2.0
    else:
        return 3.0

def bump(v: inout float, by: float):
    v = v + by

@compute(local_size_x=8)
def main():
    i: int = GLOBAL_INVOCATION_ID.x
    x: float = float(i)
    total: float = 0.0
    k: int = 0
    while k < i:
        total += float(k)
        k += 1
    p: Pair = Pair(x, vec3(1.0, 2.0, x))
    p.b.y = p.b.y * scale
    acc: float = x
    bump(acc, 10.0)
    v: vec3 = vec3(x, 2.0 * x, 3.0)
    v.xz = vec2(7.0, 8.0)
    ok: bool = (i % 3 == 0 and i != 6) or not (i < 10)
    m: float = clamp(sin(x) * 2.0, -1.0, 1.0) + sqrt(x) + pow(2.0, 3.0) + max(x, 3.0) + floor(x * 0.5)
    Out.f[i * 6 + 0] = total
    Out.f[i * 6 + 1] = classify(x)
    Out.f[i * 6 + 2] = acc
    Out.f[i * 6 + 3] = p.b.y + p.a
    Out.f[i * 6 + 4] = (5.0 if ok else -5.0) + weights[i % 4]
    Out.f[i * 6 + 5] = m + length(rot * offset) + float(count)
    Out.v[i] = vec4(v, -x)
    Out.n[i] = hash(i)
    coords = vec2(x, float(DISPATCH_SIZE.x))
"""


def _hash_ref(x):
    def wrap(v):
        v &= 0xFFFFFFFF
        return v - (1 << 32) if v >= 1 << 31 else v
    h = wrap(x * 747796405 + 289133645)
    h = ((h >> 16) & 65535) ^ h
    h = wrap(h * 1103515245)
    return (h >> 8) & 16777215


def test_compute_matches_reference(engine):
    fb = engine
    n = 16
    shader = fb.graphics.create_compute_shader(COMPUTE_SRC)
    assert type(shader).__name__ == "VulkanComputeShader"
    rot = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]], np.float32)
    shader.set_uniform("scale", 3.0)
    shader.set_uniform("offset", (1.0, 2.0, 2.0))
    shader.set_uniform("count", 5)
    shader.set_uniform("rot", rot)
    shader.set_uniform("weights", [0.5, 1.5, 2.5, 3.5])
    f_buf = fb.graphics.create_compute_buffer(np.zeros(n * 6, np.float32))
    v_buf = fb.graphics.create_compute_buffer(np.zeros((n, 4), np.float32))
    n_buf = fb.graphics.create_compute_buffer(np.zeros(n, np.int32))
    shader.bind_buffer("Out", "f", f_buf)
    shader.bind_buffer("Out", "v", v_buf)
    shader.bind_buffer("Out", "n", n_buf)
    shader.dispatch(n, 1)
    f = f_buf.read_back().reshape(n, 6)
    v, ints = v_buf.read_back(), n_buf.read_back()
    coords = shader.read_output("coords")
    assert coords.shape == (1, n, 2)
    rot_len = np.linalg.norm(rot @ np.array([1.0, 2.0, 2.0]))
    for i in range(n):
        x = float(i)
        ok = (i % 3 == 0 and i != 6) or not (i < 10)
        m = min(max(math.sin(x) * 2, -1), 1) + math.sqrt(x) + 8 + max(x, 3) + math.floor(x * 0.5)
        expected = [sum(range(i)), 1.0 if x < 2 else 2.0 if x < 5 else 3.0, x + 10, 6.0 + x,
                    (5.0 if ok else -5.0) + [0.5, 1.5, 2.5, 3.5][i % 4], m + rot_len + 5]
        assert list(f[i]) == pytest.approx(expected, rel=1e-5, abs=1e-4), f"invocation {i}"
        assert list(v[i]) == pytest.approx([7.0, 2 * x, 8.0, -x])
        assert ints[i] == _hash_ref(i)
        assert list(coords[0, i]) == pytest.approx([x, float(n)])  # DISPATCH_SIZE is exact, not rounded up
    for buf in (f_buf, v_buf, n_buf):
        buf.destroy()
    shader.destroy()


def test_raytrace_shader_uses_hardware_ray_queries(engine):
    fb = engine
    _needs_ray_tracing(fb)
    src = """
@output
hit: vec4

@raytrace(local_size_x=8, local_size_y=8)
def main():
    px: ivec3 = GLOBAL_INVOCATION_ID
    x: float = -2.0 + 7.0 * (float(px.x) + 0.5) / 32.0
    y: float = -1.5 + 3.0 * (float(px.y) + 0.5) / 8.0
    r: Ray = make_ray(vec3(x, y, -5.0), vec3(0.0, 0.0, 1.0))
    h: RayHit = trace_ray(r)
    blocked: float = 1.0 if trace_shadow(r, 5.5) else 0.0
    hit = vec4(1.0 if h.hit else 0.0, h.t, float(h.prim), blocked)
"""
    shader = fb.graphics.create_raytrace_shader(src)
    assert type(shader).__name__ == "VulkanRaytraceShader"
    quad = np.array([[[-1, -1, 0], [1, -1, 0], [1, 1, 0]], [[-1, -1, 0], [1, 1, 0], [-1, 1, 0]]], np.float32)
    far_quad = quad + np.array([3.0, 0.0, 1.0], np.float32)  # triangles 2 and 3, one unit further away
    shader.upload_scene(None, None, np.concatenate([quad, far_quad]))
    shader.dispatch(32, 8)
    data = shader.read_output("hit")
    for py in range(8):
        for px in range(32):
            x, y = -2 + 7 * (px + 0.5) / 32, -1.5 + 3 * (py + 0.5) / 8
            in_a, in_b = abs(x) <= 1 and abs(y) <= 1, abs(x - 3) <= 1 and abs(y) <= 1
            hit, t, prim, blocked = data[py, px]
            assert hit == float(in_a or in_b)
            if in_a:
                assert (t, blocked) == pytest.approx((5.0, 1.0), abs=1e-3) and prim in (0, 1)
            elif in_b:
                assert (t, blocked) == pytest.approx((6.0, 0.0), abs=1e-3) and prim in (2, 3)
            else:
                assert blocked == 0.0
    shader.destroy()


def test_reuploading_a_scene_rebuilds_it_in_place(engine):
    """Same triangle count -> the fast path that rewrites the vertices and
    rebuilds both acceleration structures into their existing memory.
    Rays have to see the new positions, not the old ones."""
    fb = engine
    _needs_ray_tracing(fb)
    src = """
@output
t: float

@raytrace(local_size_x=1)
def main():
    h: RayHit = trace_ray(make_ray(vec3(0.0, 0.0, -5.0), vec3(0.0, 0.0, 1.0)))
    t = h.t
"""
    shader = fb.graphics.create_raytrace_shader(src)
    tri = np.array([[[-1, -1, 0], [1, -1, 0], [0, 1, 0]]], np.float32)
    distances = []
    for z in (0.0, 2.0, -1.5):
        shader.upload_scene(None, None, tri + np.array([0, 0, z], np.float32))
        shader.dispatch(1, 1)
        distances.append(float(shader.read_output("t")[0, 0, 0]))
    assert distances == pytest.approx([5.0, 7.0, 3.5], abs=1e-3)
    scene_after = shader._scene
    shader.upload_scene(None, None, tri)
    assert shader._scene is scene_after  # rebuilt in place, not reallocated
    shader.destroy()


# -- rasterizing ---------------------------------------------------------------------

RASTER_VS = """
@input
position: vec3
@input
uv: vec2
@output
v_uv: vec2
def main():
    v_uv = uv
    VERTEX_POSITION = vec4(position, 1.0)
"""
RASTER_FS = """
@input
v_uv: vec2
@uniform
tint: vec4
@output
color: vec4
def main():
    color = vec4(v_uv, 0.0, 1.0) * tint
"""


def _framebuffer(r, size=32):
    from FreeBodyEngine.graphics.framebuffer import AttachmentFormat, AttachmentType
    return r.create_framebuffer(size, size, {"color": (AttachmentType.COLOR, AttachmentFormat.RGBA8),
                                             "depth": (AttachmentType.DEPTH, AttachmentFormat.DEPTH24)})


def _triangle(r, indices=(0, 1, 2)):
    from FreeBodyEngine.graphics.mesh import AttributeType
    return r.get_mesh_class()({"position": (AttributeType.VEC3, [-1, -1, 0, 1, -1, 0, -1, 1, 0]),
                               "uv": (AttributeType.VEC2, [0, 0, 1, 0, 0, 1])}, indices=list(indices))


def test_triangle_rasterizes_with_gl_conventions(engine):
    """Interpolated varyings, uniforms, and GL's memory layout - row 0 is
    the bottom of the image, as glReadPixels would return it."""
    from FreeBodyEngine.graphics.color import Color
    r = engine.get_service("renderer")
    fbo = _framebuffer(r)
    shader = r.load_shader(RASTER_VS, RASTER_FS)
    fbo.bind()
    r.clear(Color("#FF0000FF"))
    shader.set_uniform("tint", (1.0, 1.0, 1.0, 1.0))
    shader.use()
    _triangle(r).draw()
    fbo.unbind()
    px = fbo.read("color")
    assert list(px[31, 31]) == pytest.approx([1.0, 0.0, 0.0, 1.0], abs=0.01)  # outside: clear color
    assert list(px[0, 0][:2]) == pytest.approx([0.0, 0.0], abs=0.03)          # bottom left: uv (0, 0)
    assert px[0, 28][0] > 0.8 and px[28, 0][1] > 0.8                         # u grows right, v up


def test_uniforms_snapshot_per_draw(engine):
    """Set a uniform, draw, set it again, draw: each draw keeps its own
    value even though Vulkan runs both later."""
    from FreeBodyEngine.graphics.color import Color
    r = engine.get_service("renderer")
    r.resize((32, 32))  # set_scissor flips against the window height, as GL44 does
    fbo = _framebuffer(r)
    shader = r.load_shader(RASTER_VS, RASTER_FS)
    mesh = _triangle(r)
    fbo.bind()
    r.clear(Color("#000000FF"))
    shader.set_uniform("tint", (0.0, 0.0, 0.0, 1.0)); shader.use(); mesh.draw()
    r.set_scissor(0, 0, 32, 16)  # top half (top-left origin)
    shader.set_uniform("tint", (1.0, 1.0, 1.0, 1.0)); shader.use(); mesh.draw()
    r.clear_scissor()
    fbo.unbind()
    px = fbo.read("color")
    assert px[4, 4][0] < 0.05   # bottom half: the first draw only
    assert px[20, 6][1] > 0.4   # top half: the second draw


def test_clear_respects_the_scissor(engine):
    """glClear is scissored - UIRenderer clears only its dirty rect, and a
    full clear would wipe the rest of its cached UI layer."""
    from FreeBodyEngine.graphics.color import Color
    r = engine.get_service("renderer")
    r.resize((32, 32))
    fbo = _framebuffer(r)
    fbo.bind()
    r.clear(Color("#FF0000FF"))
    r.set_scissor(0, 0, 8, 8)
    r.clear(Color("#00FF00FF"))
    r.clear_scissor()
    fbo.unbind()
    px = fbo.read("color")
    assert list(px[31, 0]) == pytest.approx([0.0, 1.0, 0.0, 1.0], abs=0.01)  # top-left 8x8
    assert list(px[0, 31]) == pytest.approx([1.0, 0.0, 0.0, 1.0], abs=0.01)  # untouched


def test_shortening_mesh_indices_draws_fewer_triangles(engine):
    """TextRenderer uploads indices once and shortens a batch with
    `mesh.indices = all_indices[:n]` - GL44 draws len(mesh.indices)."""
    from FreeBodyEngine.graphics.color import Color
    r = engine.get_service("renderer")
    fbo = _framebuffer(r)
    shader = r.load_shader(RASTER_VS, RASTER_FS)
    mesh = _triangle(r, indices=(0, 1, 2, 0, 1, 2))
    mesh.indices = mesh.indices[:0]
    fbo.bind()
    r.clear(Color("#000000FF"))
    shader.set_uniform("tint", (1.0, 1.0, 1.0, 1.0)); shader.use(); mesh.draw()
    fbo.unbind()
    assert fbo.read("color")[2, 28][0] < 0.05


def test_framebuffer_draw_blits_to_the_window(engine):
    from FreeBodyEngine.graphics.color import Color
    r = engine.get_service("renderer")
    r.resize((16, 16))
    fbo = _framebuffer(r, 16)
    fbo.bind(); r.clear(Color("#00FF00FF")); fbo.unbind()
    r.bind_window_framebuffer((16, 16)); r.clear(Color("#0000FFFF"))
    fbo.draw("color", (16, 16))
    assert list(r.read_image(r.window_target.color)[8, 8]) == [0, 255, 0, 255]


def test_device_limits_survive_garbage_collection(engine):
    """ctx.limits used to point into freed cffi memory; the uniform ring's
    alignment then read as garbage and draws "overflowed" at random."""
    import gc
    gc.collect()
    ctx = engine.get_service("renderer").ctx
    assert 1 <= ctx.limits.minUniformBufferOffsetAlignment <= 256


# -- geometry shaders ----------------------------------------------------------------

GEOMETRY_VS = """
@input
position: vec3
@input
tri_id: int
@output
v_id: int
def main():
    v_id = tri_id
    VERTEX_POSITION = vec4(position, 1.0)
"""
GEOMETRY_FS = """
@input
g_color: vec3
@input
g_flag: int
@output
out_color: vec4
def main():
    c: vec3 = g_color
    if g_flag == 1:
        c = vec3(1.0, 1.0, 1.0) - c
    out_color = vec4(c, 1.0)
"""
# A shrunken copy of each triangle, then - for even triangles only - `petals`
# quads around its centre, each its own strip: data-dependent emit counts,
# EndPrimitive between strips, and odd strip triangles (winding swaps).
GEOMETRY_GS = """
@input
v_id: int
@uniform
petals: int
@output
g_color: vec3
@output
g_flag: int

def emit_at(p: vec4, color: vec3, flag: int):
    VERTEX_POSITION = p
    g_color = color
    g_flag = flag
    EmitVertex()

@geometry(input=triangles, output=triangle_strip, max_vertices=MAXV)
def main():
    c: vec4 = (input_position(0) + input_position(1) + input_position(2)) * (1.0 / 3.0)
    i: int = 0
    while i < 3:
        emit_at(mix(input_position(i), c, 0.3), vec3(1.0 if i == 0 else 0.0, 1.0 if i == 1 else 0.0, 0.5), 0)
        i += 1
    EndPrimitive()
    if v_id[0] % 2 == 0:
        k: int = 0
        while k < petals:
            a: float = float(k) * 6.2831853 / float(petals)
            d: vec4 = vec4(cos(a), sin(a), 0.0, 0.0) * 0.06
            s: vec4 = vec4(-sin(a), cos(a), 0.0, 0.0) * 0.02
            emit_at(c + s, vec3(1.0, 0.5, 0.0), 1)
            emit_at(c - s, vec3(1.0, 0.5, 0.0), 1)
            emit_at(c + d + s, vec3(0.0, 0.5, 1.0), 1)
            emit_at(c + d - s, vec3(0.0, 0.5, 1.0), 1)
            EndPrimitive()
            k += 1
"""


def _geometry_render(fb, mode, max_vertices, indexed=True):
    from FreeBodyEngine.graphics.color import Color
    from FreeBodyEngine.graphics.mesh import AttributeType, PrimitiveType, IndexType
    r = fb.get_service("renderer")
    fb.set_flag(fb.FORCE_GEOMETRY_MODE, mode)
    try:
        shader = r.load_shader(GEOMETRY_VS, GEOMETRY_FS, geometry=GEOMETRY_GS.replace("MAXV", str(max_vertices)))
    finally:
        fb.set_flag(fb.FORCE_GEOMETRY_MODE, None)
    pos, ids = [], []
    for n in range(4):
        x0, y0 = -0.9 + (n % 2) * 0.9, -0.9 + (n // 2) * 0.9
        pos += [x0, y0, 0.0, x0 + 0.8, y0, 0.0, x0, y0 + 0.8, 0.0]
        ids += [n, n, n]
    attributes = {"position": (AttributeType.VEC3, np.array(pos, np.float32)),
                  "tri_id": (AttributeType.INT, np.array(ids, np.int32))}
    if indexed:
        mesh = r.get_mesh_class()(attributes, indices=np.arange(12, dtype=np.uint16),
                                  index_type=IndexType.UINT16, primitive=PrimitiveType.TRIANGLES)
    else:
        mesh = r.get_mesh_class()(attributes, primitive=PrimitiveType.TRIANGLES)
    fbo = _framebuffer(r, 64)
    fbo.bind()
    r.clear(Color("#000000FF"))
    shader.set_uniform("petals", (max_vertices - 3) // 4)
    shader.use()
    mesh.draw()
    fbo.unbind()
    return shader.geometry_mode, (fbo.read("color") * 255).round().astype(np.uint8)


def test_geometry_shaders_render_the_same_natively_and_emulated(engine):
    """Native (when the GPU has geometry shaders), vertex-pulled and
    compute-pre-pass emulation all draw the same pixels - strips split
    into lists, EndPrimitive, odd-triangle winding, int outputs, and both
    indexed and unindexed meshes."""
    fb = engine
    r = fb.get_service("renderer")
    for max_vertices in (11, 35):  # 2 petals; 8 petals
        for indexed in (True, False):
            images = {}
            for mode in ("native", "pull", "compute"):
                if mode == "native" and not r.ctx.geometry_shader:
                    continue
                actual, images[mode] = _geometry_render(fb, mode, max_vertices, indexed)
                assert actual == mode
            reference = images.get("native", images["pull"])
            assert int((reference[..., :3].sum(-1) > 0).sum()) > 300  # it drew something
            for mode, image in images.items():
                assert np.array_equal(image, reference), f"{mode} differs (max_vertices={max_vertices})"


def test_geometry_emulation_mode_follows_the_shader(engine):
    """Without native geometry shaders, small outputs re-run per vertex
    ("pull") and large ones take the compute pre-pass."""
    from fbusl.parser import Lexer, Parser
    from fbusl.geometry import choose_mode

    def parse(src):
        return Parser(Lexer(src).tokenize()).parse()

    small = GEOMETRY_GS.replace("MAXV", "6")
    large = GEOMETRY_GS.replace("MAXV", "35")
    assert choose_mode(parse(GEOMETRY_VS), parse(small), has_atomic_compute=True) == "pull"
    assert choose_mode(parse(GEOMETRY_VS), parse(large), has_atomic_compute=True) == "compute"
    # Emulated compute (GL33/WebGL2) has no atomics to append with.
    assert choose_mode(parse(GEOMETRY_VS), parse(large), has_atomic_compute=False) == "pull"
