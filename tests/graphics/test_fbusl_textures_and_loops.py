"""discard, for/break/continue, the texture types and the sample_* family, run
for real: each shader goes through a backend's generator, then a real GL
driver, and the pixels it draws are read back.

GL33 and GL44 run on whichever GL 4.x context this machine has. The WebGL2
generator's GLSL ES runs on the same context - desktop drivers compile
`#version 300 es` - which checks everything but the browser's own API calls.
SPIR-V has compile-only checks here; running it needs a Vulkan device, which
test_vulkan.py's helpers provide when the `vulkan` package is installed.
"""
import numpy as np
import pytest

import fbusl
from fbusl import ShaderType
from fbusl.injector import Injector

glfw = pytest.importorskip("glfw")
from OpenGL.GL import *

from FreeBodyEngine.graphics.gl33 import shader as gl33_shader
from FreeBodyEngine.graphics.gl33.generator import GL33Generator
from FreeBodyEngine.graphics.gl44 import shader as gl44_shader
from FreeBodyEngine.graphics.gl44.generator import GL44Generator
from FreeBodyEngine.graphics.webgl.generator import WebGL2Generator
from FreeBodyEngine.graphics.vulkan.generator import SPIRVGenerator
from FreeBodyEngine.graphics.vulkan import spirv as sv
from FreeBodyEngine.graphics.texture import Texture, TextureCube, TextureShadow, TextureVolume

SIZE = 8

VERT = """
def main():
    x: float = float((VERTEX_INDEX << 1) & 2)
    y: float = float(VERTEX_INDEX & 2)
    VERTEX_POSITION = vec4(x * 2.0 - 1.0, y * 2.0 - 1.0, 0.0, 1.0)
"""

GENERATORS = [GL33Generator, GL44Generator, WebGL2Generator]


@pytest.fixture(scope="module")
def context():
    if not glfw.init():
        pytest.skip("no GLFW")
    glfw.window_hint(glfw.VISIBLE, glfw.FALSE)
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 4)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
    window = glfw.create_window(SIZE, SIZE, "fbusl", None, None)
    if not window:
        pytest.skip("no GL context")
    glfw.make_context_current(window)
    vao = glGenVertexArrays(1)
    glBindVertexArray(vao)
    fbo = glGenFramebuffers(1)
    color = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, color)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA32F, SIZE, SIZE, 0, GL_RGBA, GL_FLOAT, None)
    glBindFramebuffer(GL_FRAMEBUFFER, fbo)
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, color, 0)
    glViewport(0, 0, SIZE, SIZE)
    yield
    glfw.destroy_window(window)


def compile_stage(source, kind, stage, generator):
    text = fbusl.compile(source, stage, generator, Injector())
    shader = glCreateShader(kind)
    glShaderSource(shader, text)
    glCompileShader(shader)
    assert glGetShaderiv(shader, GL_COMPILE_STATUS), f"{glGetShaderInfoLog(shader)}\n{text}"
    return shader


def program(fragment, generator):
    prog = glCreateProgram()
    glAttachShader(prog, compile_stage(VERT, GL_VERTEX_SHADER, ShaderType.VERTEX, generator))
    glAttachShader(prog, compile_stage(fragment, GL_FRAGMENT_SHADER, ShaderType.FRAGMENT, generator))
    glLinkProgram(prog)
    assert glGetProgramiv(prog, GL_LINK_STATUS), glGetProgramInfoLog(prog)
    glUseProgram(prog)
    return prog


def draw():
    glClearColor(0.25, 0.25, 0.25, 0.25)
    glClear(GL_COLOR_BUFFER_BIT)
    glDrawArrays(GL_TRIANGLES, 0, 3)
    data = glReadPixels(0, 0, SIZE, SIZE, GL_RGBA, GL_FLOAT)
    return np.frombuffer(data, np.float32).reshape(SIZE, SIZE, 4)


def pixel_of(body, generator, declarations=""):
    """What a one-expression fragment shader writes, everywhere."""
    program(f"""
{declarations}
@output
result: vec4

def main():
{body}
""", generator)
    return draw()[SIZE // 2, SIZE // 2]


def texture_2d(pixels, levels=None):
    tex = glGenTextures(1)
    glActiveTexture(GL_TEXTURE0)
    glBindTexture(GL_TEXTURE_2D, tex)
    for level, data in enumerate(levels or [pixels]):
        h, w = data.shape[:2]
        glTexImage2D(GL_TEXTURE_2D, level, GL_RGBA8, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, data)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAX_LEVEL, len(levels or [pixels]) - 1)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST_MIPMAP_NEAREST)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
    return tex


@pytest.mark.parametrize("generator", GENERATORS)
def test_discard_writes_nothing(context, generator):
    program("""
@output
result: vec4

def main():
    discard
    result = vec4(1.0, 1.0, 1.0, 1.0)
""", generator)
    assert np.allclose(draw(), 0.25)


@pytest.mark.parametrize("generator", GENERATORS)
def test_for_range_forms(context, generator):
    pixel = pixel_of("""
    a: int = 0
    for i in range(4):
        a += i
    b: int = 0
    for i in range(2, 5):
        b += i
    c: int = 0
    for i in range(10, 0, -3):
        c += 1
    result = vec4(float(a), float(b), float(c), 1.0)
""", generator)
    assert pixel.tolist() == [6.0, 9.0, 4.0, 1.0]


@pytest.mark.parametrize("generator", GENERATORS)
def test_break_continue_and_stop_read_once(context, generator):
    pixel = pixel_of("""
    a: int = 0
    for i in range(10):
        if i == 2:
            continue
        if i == 5:
            break
        a += i
    n: int = 3
    b: int = 0
    for i in range(n):
        n = 100
        b += 1
    k: int = 0
    c: int = 0
    while k < 100:
        k += 1
        if k > 4:
            break
        if k == 2:
            continue
        c += 1
    result = vec4(float(a), float(b), float(c), 1.0)
""", generator)
    assert pixel.tolist() == [8.0, 3.0, 3.0, 1.0]


@pytest.mark.parametrize("generator", GENERATORS)
def test_vector_math(context, generator):
    pixel = pixel_of("""
    m: vec2 = mod(vec2(-0.25, 1.25), 1.0)
    s: vec2 = step(0.5, vec2(0.25, 0.75))
    f: vec2 = floor(vec2(1.5, -1.5)) + fract(vec2(1.5, 0.25))
    p: vec2 = mix(vec2(0.0, 1.0), vec2(1.0, 3.0), vec2(0.5, 0.5))
    c: vec2 = clamp(vec2(-1.0, 2.0), vec2(0.0, 0.0), vec2(1.0, 1.0))
    q: vec2 = vec2(ivec2(vec2(1.75, -1.75)) + ivec2(1, 1))
    t: float = dot(vec4(1.0, 2.0, 3.0, 4.0), vec4(1.0, 1.0, 1.0, 1.0))
    u: vec2 = 1.0 - vec2(0.25, 0.5)
    result = vec4(m.x + s.y * 10.0, f.y + p.y * 10.0, c.y + q.x * 10.0 + q.y * 100.0, t + u.x)
""", generator)
    # q: truncates toward zero, then adds: (2, 0).
    assert pixel == pytest.approx([10.75, 18.25 + 0.0, 21.0, 10.75])


@pytest.mark.parametrize("generator", GENERATORS)
def test_sample_level_picks_a_mip(context, generator):
    big = np.full((4, 4, 4), [255, 0, 0, 255], np.uint8)
    small = np.full((2, 2, 4), [0, 255, 0, 255], np.uint8)
    texture_2d(None, [big, small])
    prog = program("""
@uniform
tex: texture

@output
result: vec4

def main():
    result = sample_level(tex, vec2(0.5, 0.5), 1.0)
""", generator)
    glUniform4f(glGetUniformLocation(prog, "_ENGINE_tex_uv_rect"), 0, 0, 1, 1)
    glUniform1i(glGetUniformLocation(prog, "tex"), 0)
    assert draw()[0, 0].tolist() == [0.0, 1.0, 0.0, 1.0]


@pytest.mark.parametrize("generator", GENERATORS)
def test_sample_texel_is_exact_and_stays_in_the_rect(context, generator):
    pixels = np.zeros((4, 4, 4), np.uint8)
    pixels[..., 3] = 255
    pixels[3, 2] = (255, 128, 0, 255)  # row 3, column 2
    texture_2d(pixels)
    prog = program("""
@uniform
tex: texture

@output
result: vec4

def main():
    result = sample_texel(tex, ivec2(0, 1), 0)
""", generator)
    # A sub-rect starting at column 2, row 2: its texel (0, 1) is (2, 3).
    glUniform4f(glGetUniformLocation(prog, "_ENGINE_tex_uv_rect"), 0.5, 0.5, 0.5, 0.5)
    glUniform1i(glGetUniformLocation(prog, "tex"), 0)
    assert draw()[0, 0] == pytest.approx([1.0, 128 / 255, 0.0, 1.0])


@pytest.fixture(params=[(gl33_shader, "GLShader"), (gl44_shader, "GL44Shader")], ids=["gl33", "gl44"])
def engine_backend(request, context, monkeypatch):
    """A real texture manager and a real Shader class, so uniforms take the
    same path through set_uniform/_bind_textures that a game's do."""
    module, shader_class = request.param
    if module is gl33_shader:
        from FreeBodyEngine.graphics.gl33.texture import GLTextureManager as Manager
    else:
        from FreeBodyEngine.graphics.gl44.texture import GL44TextureManager as Manager
    manager = Manager()

    class Renderer:
        texture_manager = manager

    monkeypatch.setattr(module, "get_service", lambda name: Renderer)
    return manager, getattr(module, shader_class)


FULLSCREEN = VERT


def run(shader_class, fragment, **uniforms):
    shader = shader_class(FULLSCREEN, fragment, Injector())
    for name, value in uniforms.items():
        shader[name] = value
    shader.use()
    return draw()


def test_volume_filters_across_slices(engine_backend):
    manager, shader_class = engine_backend
    pixels = np.zeros((4, 1, 1), np.uint8)
    pixels[2:] = 255  # bottom half of the block dark, top half bright
    volume = manager.create_texture_volume(pixels)
    assert isinstance(volume, TextureVolume)
    out = run(shader_class, """
@uniform
vol: textureVolume

@output
result: vec4

def main():
    a: float = sample(vol, vec3(0.5, 0.5, 0.125)).x
    b: float = sample_level(vol, vec3(0.5, 0.5, 0.875), 0.0).x
    c: float = sample(vol, vec3(0.5, 0.5, 0.5)).x
    d: float = sample_texel(vol, ivec3(0, 0, 3), 0).x
    result = vec4(a, b, c, d)
""", vol=volume)
    assert out[0, 0] == pytest.approx([0.0, 1.0, 0.5, 1.0], abs=0.01)


def test_cube_reads_by_direction_and_has_mips(engine_backend):
    manager, shader_class = engine_backend
    faces = np.zeros((6, 4, 4, 4), np.float32)
    faces[:, :, :, 3] = 1.0
    faces[0, :, :, 0] = 3.0   # +x: radiance past 1
    faces[2, :, :, 1] = 1.0   # +y
    faces[5, :, :, 2] = 1.0   # -z
    cube = manager.create_texture_cube(faces)
    assert isinstance(cube, TextureCube)
    out = run(shader_class, """
@uniform
sky: textureCube

@output
result: vec4

def main():
    a: float = sample(sky, vec3(1.0, 0.0, 0.0)).x
    b: float = sample_level(sky, vec3(0.0, 1.0, 0.0), 0.0).y
    c: float = sample(sky, vec3(0.0, 0.0, -1.0)).z
    d: float = sample_level(sky, vec3(1.0, 0.0, 0.0), 2.0).x
    result = vec4(a, b, c, d)
""", sky=cube)
    assert out[0, 0][:3] == pytest.approx([3.0, 1.0, 1.0], abs=0.01)
    assert out[0, 0][3] == pytest.approx(3.0, abs=0.01)  # a 1x1 mip of a flat face


def depth_texture():
    """A 2x1 depth image: 0.25 on the left, 0.75 on the right."""
    tex = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tex)
    data = np.array([[0.25, 0.75]], np.float32)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_DEPTH_COMPONENT32F, 2, 1, 0, GL_DEPTH_COMPONENT, GL_FLOAT, data)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
    return tex


def test_shadow_compares_and_leaves_plain_reads_alone(engine_backend):
    manager, shader_class = engine_backend
    tex = depth_texture()
    shadow = manager.wrap_shadow_texture(tex)
    assert isinstance(shadow, TextureShadow)
    out = run(shader_class, """
@uniform
map: textureShadow

@output
result: vec4

def main():
    lit_left: float = sample_shadow(map, vec2(0.01, 0.5), 0.5)
    lit_right: float = sample_shadow(map, vec2(0.99, 0.5), 0.5)
    between: float = sample_shadow(map, vec2(0.5, 0.5), 0.5)
    result = vec4(lit_left, lit_right, between, 1.0)
""", map=shadow)
    assert out[0, 0][:3] == pytest.approx([0.0, 1.0, 0.5], abs=0.05)

    # The unit it used is handed back without the comparison on it: the same
    # image, read plainly right after, returns depth.
    plain = run(shader_class, """
@uniform
depth_image: texture

@output
result: vec4

def main():
    result = vec4(sample(depth_image, vec2(0.01, 0.5)).x, 0.0, 0.0, 1.0)
""", depth_image=Texture(manager, manager.wrap_external_texture(tex).id, (0, 0, 1, 1)))
    assert plain[0, 0][0] == pytest.approx(0.25, abs=0.01)


# -- language rules (no GPU) -----------------------------------------------------

def expect_error(source, stage=ShaderType.FRAGMENT):
    with pytest.raises(fbusl.FBUSLCompileError):
        fbusl.compile(source, stage, GL33Generator, Injector())


def test_discard_is_fragment_only():
    expect_error("""
def main():
    discard
    VERTEX_POSITION = vec4(0.0, 0.0, 0.0, 1.0)
""", ShaderType.VERTEX)


def test_break_needs_a_loop():
    expect_error("""
@output
r: vec4

def main():
    break
""")


def test_range_step_is_a_nonzero_constant():
    for step in ("0", "n"):
        expect_error(f"""
@output
r: vec4

def main():
    n: int = 1
    for i in range(0, 4, {step}):
        n += 1
""")


def test_sample_shadow_only_takes_a_shadow_texture():
    expect_error("""
@uniform
tex: texture

@output
r: vec4

def main():
    r = vec4(sample_shadow(tex, vec2(0.0, 0.0), 0.5), 0.0, 0.0, 1.0)
""")


# -- SPIR-V (compile only) -------------------------------------------------------

def spirv_ops(fragment):
    from fbusl.parser import Lexer, Parser
    from fbusl.semantic import SemanticAnalyser
    tree = Parser(Lexer(fragment).tokenize()).parse()
    SemanticAnalyser(tree, ShaderType.FRAGMENT).analyse()
    gen = SPIRVGenerator(tree, ShaderType.FRAGMENT, SPIRVGenerator.graphics_layout([tree]))
    code = gen.generate()
    assert code[:4] == sv.MAGIC.to_bytes(4, "little")
    ops = [i.op for section in gen.m.sections.values() for i in section]
    return ops, gen


def test_spirv_textures():
    ops, gen = spirv_ops("""
@uniform
tex: texture
stack: textureStack
vol: textureVolume
sky: textureCube
map: textureShadow

@output
result: vec4

def main():
    a: vec4 = sample_level(tex, vec2(0.5, 0.5), 1.0) + sample_texel(tex, ivec2(1, 2), 0)
    b: vec4 = sample_level(stack, 1, vec2(0.5, 0.5), 1.0) + sample_texel(stack, 1, ivec2(1, 2), 0)
    c: vec4 = sample(vol, vec3(0.5, 0.5, 0.5)) + sample_level(vol, vec3(0.5, 0.5, 0.5), 0.0) + sample_texel(vol, ivec3(1, 2, 3), 0)
    d: vec4 = sample(sky, vec3(1.0, 0.0, 0.0)) + sample_level(sky, vec3(1.0, 0.0, 0.0), 2.0)
    result = a + b + c + d + vec4(sample_shadow(map, vec2(0.5, 0.5), 0.5), 0.0, 0.0, 0.0)
""")
    for needed in ("ImageSampleExplicitLod", "ImageSampleImplicitLod", "ImageFetch", "ImageSampleDrefImplicitLod",
                   "ImageQuerySizeLod", "Image"):
        assert needed in ops
    kinds = {b["name"]: b.get("texture_kind") for b in gen.reflection["bindings"]}
    assert kinds["vol"] == "textureVolume" and kinds["sky"] == "textureCube" and kinds["map"] == "textureShadow"
    assert "_ENGINE_vol_uv_rect" not in gen.reflection["uniforms"]
    assert "_ENGINE_tex_uv_rect" in gen.reflection["uniforms"]


def test_spirv_control_flow_and_math():
    ops, _ = spirv_ops("""
@output
result: vec4

def main():
    a: int = 0
    for i in range(10, 0, -2):
        if i == 4:
            continue
        if i == 2:
            break
        a += i
    if a > 100:
        discard
    n: ivec2 = ivec2(vec2(1.5, 2.5)) + 1
    v: vec2 = mod(vec2(n), 2.0) + step(0.5, vec2(0.0, 1.0)) + smoothstep(0.0, 1.0, vec2(0.5, 0.5))
    w: vec2 = 1.0 - clamp(v, vec2(0.0, 0.0), vec2(1.0, 1.0)) + dFdx(v) + ceil(v) + min(v, 0.5)
    result = vec4(w.x, w.y, 0.0, 1.0)
""")
    assert ops.count("LoopMerge") == 1
    for needed in ("Kill", "FMod", "DPdx", "ConvertFToS", "ConvertSToF", "SGreaterThan"):
        assert needed in ops
