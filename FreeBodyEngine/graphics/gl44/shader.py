from fbusl.generator import Generator
from fbusl.node import *
from fbusl.semantic import SemanticAnalyser 
from FreeBodyEngine.graphics.shader import Shader
from FreeBodyEngine.graphics.gl44.generator import GL44Generator
from FreeBodyEngine.math import Vector, Vector3
from FreeBodyEngine import error as fb_error
from FreeBodyEngine import warning
from FreeBodyEngine import get_time
from FreeBodyEngine.graphics.texture import Texture, TextureStack
from FreeBodyEngine.graphics.buffer import Buffer as DataBuffer
from OpenGL.GL import *
import numpy as np
from FreeBodyEngine.graphics.color import Color
from FreeBodyEngine import get_service

from dataclasses import dataclass
import numpy
from typing import Union

GL_TYPE_NAMES = {
    GL_INT: "int",
    GL_INT_VEC2: "ivec2",
    GL_INT_VEC3: "ivec3",
    GL_INT_VEC4: "ivec4",
    GL_FLOAT: "float",
    GL_FLOAT_VEC2: "vec2",
    GL_FLOAT_VEC3: "vec3",
    GL_FLOAT_VEC4: "vec4",
    GL_FLOAT_MAT2: "mat2",
    GL_FLOAT_MAT3: "mat3",
    GL_FLOAT_MAT4: "mat4",
    GL_BOOL: "bool",
    GL_SAMPLER_2D: "sampler2D",
    GL_SAMPLER_2D_ARRAY: "sampler2DArray",
}

@dataclass
class GL44Uniform:
    """A shader program's introspected uniform: its GL `location`, array
    `size` (>1 for a uniform array, e.g. a `sampler2D[N]`), and GL `type`
    enum."""
    location: any
    size: int
    type: str

def create_shader_program(vertex_src, fragment_src, geometry_src=None):
    """Compiles and links `vertex_src`/`fragment_src` (and `geometry_src`,
    if given) into a linked GL program, raising RuntimeError with the
    driver's log on a compile or link failure. The per-stage shader objects
    are deleted once linked - only the program is kept."""
    vertex_shader = compile_shader(vertex_src, GL_VERTEX_SHADER)
    fragment_shader = compile_shader(fragment_src, GL_FRAGMENT_SHADER)
    geometry_shader = compile_shader(geometry_src, GL_GEOMETRY_SHADER) if geometry_src is not None else None

    program = glCreateProgram()
    glAttachShader(program, vertex_shader)
    glAttachShader(program, fragment_shader)
    if geometry_shader is not None:
        glAttachShader(program, geometry_shader)
    glLinkProgram(program)

    if glGetProgramiv(program, GL_LINK_STATUS) != GL_TRUE:
        error = glGetProgramInfoLog(program).decode()
        raise RuntimeError(f"Shader link error:\n{error}")

    glDeleteShader(vertex_shader)
    glDeleteShader(fragment_shader)
    if geometry_shader is not None:
        glDeleteShader(geometry_shader)

    return program

def compile_shader(source, shader_type):
    """Compiles `source` as a `shader_type` GL shader object, raising
    RuntimeError with the driver's compile log on failure."""
    shader = glCreateShader(shader_type)
    glShaderSource(shader, source)
    glCompileShader(shader)

    if glGetShaderiv(shader, GL_COMPILE_STATUS) != GL_TRUE:
        error = glGetShaderInfoLog(shader).decode()
        raise RuntimeError(f"Shader compile error:\n{error}")

    return shader


def set_gl_uniform(loc, gl_type, val):
    """The actual glUniform*/glUniformMatrix* dispatch, factored out of
    GL44Shader.set_uniform so GL44ComputeShader (graphics/gl44/compute.py)
    can reuse it instead of duplicating this same type-dispatch table. Assumes
    the target program is already current (glUseProgram)."""
    if gl_type == GL_INT:
        glUniform1i(loc, val)

    elif gl_type == GL_BOOL:
        glUniform1i(loc, int(val))

    elif gl_type == GL_FLOAT:
        glUniform1f(loc, float(val))

    elif gl_type == GL_INT_VEC2:
        glUniform2iv(loc, 1, val)

    elif gl_type == GL_INT_VEC3:
        glUniform3iv(loc, 1, val)

    elif gl_type == GL_INT_VEC4:
        glUniform4iv(loc, 1, val)

    elif gl_type == GL_FLOAT_VEC2:
        glUniform2f(loc, val[0], val[1])

    elif gl_type == GL_FLOAT_VEC3:
        if isinstance(val, Color):
            fn = val.float_normalized
            v0, v1, v2 = fn[0], fn[1], fn[2]
        else:
            v0, v1, v2 = val[0], val[1], val[2]

        glUniform3f(loc, v0, v1, v2)

    elif gl_type == GL_FLOAT_VEC4:
        if isinstance(val, Color):
            fn = val.float_normalized_a
            v0, v1, v2, v3 = fn[0], fn[1], fn[2], fn[3]
        else:
            v0, v1, v2, v3 = val[0], val[1], val[2], val[3]

        glUniform4f(loc, v0, v1, v2, v3)

    elif gl_type == GL_FLOAT_MAT2:
        glUniformMatrix2fv(loc, 1, GL_FALSE, val)

    elif gl_type == GL_FLOAT_MAT3:
        glUniformMatrix3fv(loc, 1, GL_FALSE, val)

    elif gl_type == GL_FLOAT_MAT4:
        glUniformMatrix4fv(loc, 1, GL_FALSE, val)

    elif gl_type in (GL_SAMPLER_2D, GL_SAMPLER_2D_ARRAY):
        if isinstance(val, int):
            glUniform1i(loc, val)

class GL44Shader(Shader):
    """The GL 4.4 implementation of Shader: compiles FBUSL source via
    GL44Generator into a real GL program, introspects its uniforms, and
    caches each uniform's last-set value so set_uniform() can skip a
    redundant glUniform* call when the value hasn't actually changed."""
    def __init__(self, vertex_source, fragment_source, injector, geometry_source=None):
        """Compiles `vertex_source`/`fragment_source`(/`geometry_source`)
        into a linked GL program (via GL44Generator) and introspects its
        active uniforms into `self.uniforms`, seeding `uniform_cache` with
        `None` for each so the first set_uniform() call for any uniform
        always goes through."""
        super().__init__(vertex_source, fragment_source, GL44Generator, injector, geometry_source)
        self._shader = create_shader_program(self.fbusl_vertex_source, self.fbusl_fragment_source, self.fbusl_geometry_source)

        self.uniforms: dict[str, GL44Uniform] = {}
        self.setup_uniforms()

        self.uniform_cache: dict[str, any] = {}

        for name in self.uniforms:
            self.uniform_cache[name] = None

    def rebuild(self, injector=..., vertex_source=None, fragment_source=None, geometry_source=...):
        """See GLShader.rebuild() (graphics/gl33/shader.py) for why
        vertex_source/fragment_source default to re-using `self`'s existing
        ones rather than being required, and why geometry_source's default
        is the `...` sentinel rather than `None`."""
        if vertex_source is None:
            vertex_source = self.vertex_source
        if fragment_source is None:
            fragment_source = self.fragment_source
        if geometry_source is ...:
            geometry_source = self.geometry_source

        super().__init__(vertex_source, fragment_source, self.generator, injector, geometry_source)
        self._shader = create_shader_program(self.fbusl_vertex_source, self.fbusl_fragment_source, self.fbusl_geometry_source)
        self.uniforms = {}
        self.setup_uniforms()
        self.uniform_cache = {name: None for name in self.uniforms}

    def setup_uniforms(self):
        """Populates `self.uniforms` from the program's active uniforms
        (glGetActiveUniform), normalizing the name PyOpenGL hands back
        (which can come as `str`, `bytes`, or a numpy array depending on
        driver/binding) to a plain, null-terminated string."""
        count = glGetProgramiv(self._shader, GL_ACTIVE_UNIFORMS)

        for i in range(count):
            name, size, gl_type = glGetActiveUniform(self._shader, i)

            if isinstance(name, numpy.ndarray):
                name = name.tobytes().split(b'\x00', 1)[0].decode('utf-8')
            elif isinstance(name, bytes):
                name = name.split(b'\x00', 1)[0].decode('utf-8')
            else:
                name = name.rstrip('\x00')

            location = glGetUniformLocation(self._shader, name)

            self.uniforms[name] = GL44Uniform(location, size, gl_type)

        # Precomputed once here (setup_uniforms() is the one place both
        # __init__ and rebuild() populate self.uniforms from) rather than
        # rescanning the *entire* uniform dict - including every plain
        # non-sampler uniform (rect, color, matrices, ...) - on every
        # single use()/_bind_textures() call, which real profiling (a
        # text-heavy UI, one draw call per glyph - see graphics/text/
        # text.py's own docstring on why - so use() runs constantly) showed
        # costing more real time than the GL calls it exists to make: a
        # shader with, say, 8 uniforms and 1 actual sampler was still
        # doing 8 isinstance-equivalent type checks per glyph to find that
        # one sampler, every glyph, of every text draw, every frame.
        self._sampler_uniforms = [
            name for name, uniform in self.uniforms.items()
            if uniform.type in (GL_SAMPLER_2D, GL_SAMPLER_2D_ARRAY)
        ]

    def check_val_type(self, val: any, gl_type: int, name: str) -> bool:
        """Validates that `val` is an acceptable Python value for a uniform
        of GL type `gl_type` - logging an engine error and returning False
        if not. `Color`/`Vector`/`Vector3` are accepted directly for the
        vector GL types they map onto, alongside a plain tuple/list/ndarray
        of the right length."""
        def is_vec_of_length(obj, length, types=(int, float)):
            """Returns True if `obj` is a plain sequence/ndarray of `length`
            elements of `types`, or a `Color`/`Vector`/`Vector3` that maps
            onto a vector of `length` components."""
            if isinstance(obj, (tuple, list, np.ndarray)) and len(obj) == length and all(isinstance(x, types) for x in obj):
                return True

            elif isinstance(obj, Color) and length >= 3:
                return True

            elif isinstance(obj, Vector) and length == 2:
                return True

            elif isinstance(obj, Vector3) and length == 3:
                return True

        if gl_type == GL_INT:
            if isinstance(val, int):
                return True

        elif gl_type == GL_INT_VEC2:
            if is_vec_of_length(val, 2, types=(int,)):
                return True

        elif gl_type == GL_INT_VEC3:
            if is_vec_of_length(val, 3, types=(int,)):
                return True

        elif gl_type == GL_INT_VEC4:
            return is_vec_of_length(val, 4, types=(int,))

        elif gl_type == GL_BOOL:
            if isinstance(val, bool):
                return True

        elif gl_type == GL_FLOAT:
            return isinstance(val, (float, int))

        elif gl_type == GL_FLOAT_VEC2:
            if is_vec_of_length(val, 2):
                return True

        elif gl_type == GL_FLOAT_VEC3:
            if is_vec_of_length(val, 3):
                return True

        elif gl_type == GL_FLOAT_VEC4:
            return is_vec_of_length(val, 4)

        elif gl_type == GL_FLOAT_MAT2:
            if isinstance(val, np.ndarray) and val.shape == (2, 2):
                return True

        elif gl_type == GL_FLOAT_MAT3:
            if isinstance(val, np.ndarray) and val.shape == (3, 3):
                return True

        elif gl_type == GL_FLOAT_MAT4:
            if isinstance(val, np.ndarray) and val.shape == (4, 4):
                return True

        elif gl_type == GL_SAMPLER_2D:
            if isinstance(val, (int, Texture)):
                return True

        elif gl_type == GL_SAMPLER_2D_ARRAY:
            if isinstance(val, (int, TextureStack)):
                return True

        fb_error(f'Cannot set uniform "{name}" of type "{GL_TYPE_NAMES.get(gl_type, "Unknown")}" to value of type "{type(val).__name__}"')
        return False

    def set_uniform(self, name: str, val: any):
        """Sets uniform `name` to `val`, after `check_val_type()` validates
        it. Skips the actual glUniform* call *and* type validation if `val`
        equals the value already cached for this uniform, avoiding redundant
        driver calls (and redundant re-validation of a value already known
        good) when the same value is set every frame - as material
        properties typically are, and - more heavily - as most of a text
        draw's uniforms are across every glyph of a string (see graphics/
        text/text.py's draw_text(): window_size/atlas/text_color/px_range
        are set once, outside its per-glyph loop, but every glyph still
        re-sets `rect`/`uv_rect`, and used to pay this same validation cost
        for those even though *they* do change every glyph - the cache
        check moving first only ever removes work, never adds any).

        The equality check itself runs before validation, not after - a
        value that's already cached must have passed validation the first
        time it was set, so skipping validation on a repeat of that exact
        value can't let anything invalid slip through uncaught.

        Texture/TextureStack uniforms are the one exception, deliberately
        excluded from this short-circuit even when `val` is the identical
        object already cached: they're live GPU resources whose *contents*
        can change without their Python identity changing (a render
        target, say), so "the same Texture object" doesn't mean "still
        safe to skip" the way it does for a plain value - see
        _bind_textures(), which always re-binds every sampler uniform
        every call for exactly this reason (its own cost is bounded by the
        texture manager's *own* per-frame slot cache, not this one)."""
        if name not in self.uniforms:
            fb_error(f"Uniform '{name}' not found in shader")
            return

        uniform = self.uniforms[name]
        cached_val = self.uniform_cache[name]

        if not isinstance(val, (Texture, TextureStack)):
            if (not isinstance(val, np.ndarray)) and (not isinstance(cached_val, np.ndarray)):
                if cached_val == val:
                    return
            else:
                if np.array_equal(val, cached_val):
                    return

        if not self.check_val_type(val, uniform.type, name):
            return

        self.uniform_cache[name] = val

        glUseProgram(self._shader)
        set_gl_uniform(uniform.location, uniform.type, val)

    def set_buffer(self, name: str, buffer: DataBuffer):
        """Binds `buffer` to the uniform block declared as `name` in this
        shader's source (`self.data['buffers']`, populated by
        generator-produced metadata) - warns instead of raising if `name`
        isn't a known buffer block."""
        if name in self.data['buffers']:

            block_index = glGetUniformBlockIndex(self._shader, self.data['buffers'][name][1].encode('utf-8'))

            binding_point = self.data['buffers'][name][0]
            glUniformBlockBinding(self._shader, block_index, binding_point)

            buffer.bind(binding_point)

        else:
            warning(f'Shader {self}, does not have buffer of name "{name}".')

    def get_uniform(self, name: str):
        """Returns the introspected GL44Uniform record (location/size/type)
        for uniform `name`."""
        return self.uniforms[name]
    def _bind_textures(self):
        texture_manager = get_service('renderer').texture_manager
        # Iterates self._sampler_uniforms (precomputed once in
        # setup_uniforms()), not self.uniforms.items() - see that list's
        # own comment for why: this runs on every single use() call
        # (constantly, for text - one draw call per glyph), and a shader
        # with mostly non-sampler uniforms was paying a type check on
        # every one of them just to find the (often single) sampler each
        # time.
        for name in self._sampler_uniforms:
            uniform = self.uniforms[name]
            if uniform.type == GL_SAMPLER_2D:
                if uniform.size == 1:
                    texture = self.uniform_cache[name]

                    if texture is None:
                        continue

                    if not isinstance(texture, Texture):
                        continue

                    slot = texture_manager.bind_texture(texture.id)

                    if slot is None:
                        continue

                    glUniform1i(uniform.location, slot)

                    rect = texture.uv_rect
                    uv_rect = f"_ENGINE_{name}_uv_rect"

                    if uv_rect in self.uniforms:
                        glUniform4f(
                            self.uniforms[uv_rect].location,
                            rect[0],
                            rect[1],
                            rect[2],
                            rect[3]
                        )

                else:
                    textures = self.uniform_cache[name]

                    if textures is None:
                        continue

                    slots = []

                    for tex in textures:
                        if isinstance(tex, Texture):
                            slot = texture_manager.bind_texture(tex.id)
                            if slot is not None:
                                slots.append(slot)

                    if slots:
                        glUniform1iv(
                            uniform.location,
                            len(slots),
                            slots
                        )

            elif uniform.type == GL_SAMPLER_2D_ARRAY:
                stack = self.uniform_cache[name]

                if stack is None:
                    continue

                slot = texture_manager.bind_texture_stack(stack.id)

                if slot is None:
                    continue

                glUniform1i(uniform.location, slot)

                for i, rect in enumerate(stack.uv_rects):
                    
                    if not isinstance(rect, (tuple, list, np.ndarray)) or len(rect) != 4:
                        fb_error(f'Texture "{name}" has an invalid uv_rect: {rect!r}')
                        continue


                    uv_rect = f"_ENGINE_{name}_uv_rect[{i}]"

                    if uv_rect in self.uniforms:
                        glUniform4f(
                            self.uniforms[uv_rect].location,
                            rect[0],
                            rect[1],
                            rect[2],
                            rect[3]
                        )

    def use(self):
        """Activates this shader's program, updates the `TIME` builtin
        uniform if the shader declares one, and binds every currently-cached
        texture/texture-stack uniform (see `_bind_textures`)."""
        glUseProgram(self._shader)

        if 'TIME' in self.uniforms:
            glUniform1f(self.uniforms['TIME'].location, get_time())

        self._bind_textures()
