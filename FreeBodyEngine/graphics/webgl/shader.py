"""WebGL2Shader: the WebGL2 implementation of Shader. Mirrors GL33Shader's
shape closely (compile via a Generator, introspect uniforms, cache their
last-set value) - the real difference throughout this file is mechanical,
not conceptual: PyOpenGL's `glFoo(...)` global-state calls become
`self.gl.foo(...)` calls against this specific canvas's WebGL2RenderingContext
object (JS has no implicit "current context" the way desktop GL does), and
raw ints/floats/bools that PyOpenGL happily takes straight from a numpy
array need to cross into JS as an explicit typed array first (see
graphics/webgl/interop.py).
"""
from dataclasses import dataclass

import numpy as np

from FreeBodyEngine.graphics.shader import Shader
from FreeBodyEngine.graphics.webgl.generator import WebGL2Generator
from FreeBodyEngine.graphics.webgl.interop import to_typed_array, to_js_matrix
from FreeBodyEngine.graphics.texture import Texture
from FreeBodyEngine.graphics.color import Color
from FreeBodyEngine.math import Vector, Vector3
from FreeBodyEngine import get_service, get_time, error as fb_error, warning


@dataclass
class WebGLUniform:
    """One introspected active uniform: its WebGL location handle (an
    opaque JS object, unlike GL33's plain int), array `size`, and WebGL
    `type` enum (a plain int - WebGL2's GLenum values for e.g.
    FLOAT/FLOAT_VEC3/SAMPLER_2D are numerically identical to desktop GL's,
    both being derived from the same OpenGL ES lineage, so GL33Shader's
    own type-name table/dispatch logic below carries over unchanged)."""
    location: any
    size: int
    type: int


def create_shader_program(gl, vertex_src: str, fragment_src: str):
    """Compiles and links `vertex_src`/`fragment_src` into a linked WebGL2
    program, raising RuntimeError with the driver's log on a compile or
    link failure - same contract as gl33/shader.py's own
    create_shader_program()."""
    vertex_shader = _compile_shader(gl, vertex_src, gl.VERTEX_SHADER)
    fragment_shader = _compile_shader(gl, fragment_src, gl.FRAGMENT_SHADER)

    program = gl.createProgram()
    gl.attachShader(program, vertex_shader)
    gl.attachShader(program, fragment_shader)
    gl.linkProgram(program)

    if not gl.getProgramParameter(program, gl.LINK_STATUS):
        log = gl.getProgramInfoLog(program)
        raise RuntimeError(f"Shader link error:\n{log}")

    gl.deleteShader(vertex_shader)
    gl.deleteShader(fragment_shader)

    return program


def _compile_shader(gl, source: str, shader_type):
    shader = gl.createShader(shader_type)
    gl.shaderSource(shader, source)
    gl.compileShader(shader)

    if not gl.getShaderParameter(shader, gl.COMPILE_STATUS):
        log = gl.getShaderInfoLog(shader)
        kind = "vertex" if shader_type == gl.VERTEX_SHADER else "fragment"
        raise RuntimeError(f"Shader compile error ({kind}):\n{log}\n\nSource:\n{source}")

    return shader


class WebGL2Shader(Shader):
    """The WebGL2 implementation of Shader - see this module's own
    docstring."""
    def __init__(self, vertex_source, fragment_source, injector, geometry_source=None):
        """Compiles `vertex_source`/`fragment_source` into a linked WebGL2
        program (via WebGL2Generator) and introspects its active uniforms
        into `self.uniforms`. `geometry_source` is accepted only for
        interface parity with GLShader/the abstract Shader signature -
        WebGL2 has no geometry shader stage at all, so a non-None value
        here would already have failed inside WebGL2Generator's
        (deliberately empty) CAPABILITIES before ever reaching this
        constructor."""
        super().__init__(vertex_source, fragment_source, WebGL2Generator, injector, geometry_source)
        self.gl = get_service('renderer').gl
        self._program = create_shader_program(self.gl, self.fbusl_vertex_source, self.fbusl_fragment_source)

        self.uniforms: dict[str, WebGLUniform] = {}
        self.setup_uniforms()

        self.uniform_cache: dict[str, any] = {name: None for name in self.uniforms}

    def rebuild(self, injector=..., vertex_source=None, fragment_source=None, geometry_source=...):
        """Recompiles this shader in place - see GLShader.rebuild()'s own
        docstring, same reasoning applies unchanged."""
        if vertex_source is None:
            vertex_source = self.vertex_source
        if fragment_source is None:
            fragment_source = self.fragment_source
        if geometry_source is ...:
            geometry_source = self.geometry_source

        super().__init__(vertex_source, fragment_source, self.generator, injector, geometry_source)
        self._program = create_shader_program(self.gl, self.fbusl_vertex_source, self.fbusl_fragment_source)
        self.uniforms = {}
        self.setup_uniforms()
        self.uniform_cache = {name: None for name in self.uniforms}

    def setup_uniforms(self):
        """Populates `self.uniforms` from the program's active uniforms
        (`getActiveUniform`/`getUniformLocation`) - the WebGL2 equivalent
        of GLShader.setup_uniforms(), just against JS's object-returning
        introspection calls instead of PyOpenGL's."""
        gl = self.gl
        count = gl.getProgramParameter(self._program, gl.ACTIVE_UNIFORMS)

        for i in range(count):
            info = gl.getActiveUniform(self._program, i)
            name = str(info.name)
            # WebGL reports an array uniform's active name with a "[0]"
            # suffix (e.g. "uv_rect_array[0]") - stripped so lookups by
            # the plain FBUSL-declared name (no index) still find it,
            # matching how a plain (non-array) uniform is named.
            if name.endswith("[0]"):
                name = name[:-3]
            location = gl.getUniformLocation(self._program, name)
            self.uniforms[name] = WebGLUniform(location, int(info.size), int(info.type))

    def get_uniform(self, name: str):
        """Returns the introspected WebGLUniform record for uniform `name`."""
        return self.uniforms[name]

    def check_val_type(self, val: any, gl_type: int, name: str) -> bool:
        """Same validation GLShader.check_val_type() does - WebGL2's type
        enum values line up with desktop GL's for every type this engine
        actually uses, so the exact same dispatch works unchanged."""
        gl = self.gl

        def is_vec_of_length(obj, length, types=(int, float)):
            if isinstance(obj, (tuple, list, np.ndarray)) and len(obj) == length and all(isinstance(x, types) for x in obj):
                return True
            elif isinstance(obj, Color) and length >= 3:
                return True
            elif isinstance(obj, Vector) and length == 2:
                return True
            elif isinstance(obj, Vector3) and length == 3:
                return True
            return False

        if gl_type == gl.INT:
            return isinstance(val, int)
        elif gl_type == gl.BOOL:
            return isinstance(val, bool)
        elif gl_type == gl.FLOAT:
            return isinstance(val, (float, int))
        elif gl_type == gl.FLOAT_VEC2:
            return is_vec_of_length(val, 2)
        elif gl_type == gl.FLOAT_VEC3:
            return is_vec_of_length(val, 3)
        elif gl_type == gl.FLOAT_VEC4:
            return is_vec_of_length(val, 4)
        elif gl_type == gl.INT_VEC2:
            return is_vec_of_length(val, 2, types=(int,))
        elif gl_type == gl.INT_VEC3:
            return is_vec_of_length(val, 3, types=(int,))
        elif gl_type == gl.INT_VEC4:
            return is_vec_of_length(val, 4, types=(int,))
        elif gl_type == gl.FLOAT_MAT2:
            return isinstance(val, np.ndarray) and val.shape == (2, 2)
        elif gl_type == gl.FLOAT_MAT3:
            return isinstance(val, np.ndarray) and val.shape == (3, 3)
        elif gl_type == gl.FLOAT_MAT4:
            return isinstance(val, np.ndarray) and val.shape == (4, 4)
        elif gl_type == gl.SAMPLER_2D:
            return isinstance(val, (int, Texture))
        elif gl_type == gl.SAMPLER_2D_ARRAY:
            return isinstance(val, int)

        fb_error(f'Cannot set uniform "{name}" to value of type "{type(val).__name__}"')
        return False

    def set_uniform(self, name: str, val: any):
        """Sets uniform `name` to `val` - same skip-if-unchanged caching
        as GLShader.set_uniform()."""
        if name not in self.uniforms:
            fb_error(f"Uniform '{name}' not found in shader")
            return

        if not self.check_val_type(val, self.uniforms[name].type, name):
            return

        cached_val = self.uniform_cache[name]
        if not isinstance(val, Texture):
            if not isinstance(val, np.ndarray) and not isinstance(cached_val, np.ndarray):
                if cached_val == val:
                    return
            else:
                if np.array_equal(val, cached_val):
                    return

        self.uniform_cache[name] = val

        uniform = self.uniforms[name]
        self.gl.useProgram(self._program)
        self._set_gl_uniform(uniform, val)

    def _set_gl_uniform(self, uniform: WebGLUniform, val):
        """The actual `gl.uniform*`/`gl.uniformMatrix*` dispatch - thin
        instance wrapper around the module-level set_gl_uniform() below
        (see its own docstring), kept so existing call sites within this
        class don't need to change."""
        set_gl_uniform(self.gl, uniform.location, uniform.type, val)

    def set_buffer(self, name: str, buffer):
        """Not supported - WebGL2Generator's empty CAPABILITIES already
        rejects any FBUSL `@buffer` block before a shader referencing one
        could compile, so this should never actually be reached; kept as
        a clear error rather than silently doing nothing if it somehow
        is."""
        raise NotImplementedError(
            "Uniform buffer blocks aren't supported by the web backend yet."
        )

    def _bind_textures(self):
        """Binds every currently-cached sampler2D uniform to a texture
        unit - the WebGL2 equivalent of GLShader._bind_textures(), minus
        the texture-*stack* (sampler2DArray) path, which the web backend
        doesn't implement yet (see graphics/webgl/texture.py)."""
        gl = self.gl
        texture_manager = get_service('renderer').texture_manager
        for name, uniform in self.uniforms.items():
            if uniform.type != gl.SAMPLER_2D:
                continue

            texture = self.uniform_cache.get(name)
            if not isinstance(texture, Texture):
                continue

            slot = texture_manager.bind_texture(texture.id)
            if slot is None:
                continue

            gl.uniform1i(uniform.location, slot)

            rect = texture.uv_rect
            uv_rect_name = f"_ENGINE_{name}_uv_rect"
            if uv_rect_name in self.uniforms:
                gl.uniform4f(self.uniforms[uv_rect_name].location, rect[0], rect[1], rect[2], rect[3])

    def use(self):
        """Activates this shader's program, updates the `TIME` builtin
        uniform if declared, and binds every cached texture uniform.

        Resets the texture manager's slot allocation here (not just from
        Renderer.draw_mesh()) so a caller that draws directly - shader.use()
        + mesh.draw(), bypassing draw_mesh() entirely, as phonon's
        VisualizerPipeline does for its ping-pong fullscreen quad - still
        gets a clean, fully-unbound set of texture units every draw. See
        WebGL2TextureManager.begin_draw()'s own docstring for why a stale
        binding left over from a path that skips this causes WebGL2's
        "Feedback loop formed between Framebuffer and active Texture"
        error."""
        gl = self.gl
        gl.useProgram(self._program)

        if 'TIME' in self.uniforms:
            gl.uniform1f(self.uniforms['TIME'].location, get_time())

        get_service('renderer').texture_manager.begin_draw()
        self._bind_textures()


def _vec_components(val, length: int):
    """Normalizes a uniform value accepted by check_val_type() (a Color/
    Vector/Vector3/tuple/list/ndarray) into a plain `length`-tuple of
    floats, for the vector `gl.uniform*f` calls above. `length` picks
    which of Color's two component tuples applies (`float_normalized` -
    3 components - vs `float_normalized_a` - 4, alpha included) since a
    Color can back either a vec3 or a vec4 uniform depending on what the
    shader actually declared."""
    if isinstance(val, Color):
        components = val.float_normalized_a if length == 4 else val.float_normalized
        return tuple(components)[:length]
    if isinstance(val, (Vector, Vector3)):
        return tuple(val)
    return tuple(float(c) for c in val)


def set_gl_uniform(gl, loc, t, val):
    """The actual `gl.uniform*`/`gl.uniformMatrix*` type dispatch, shared
    by WebGL2Shader._set_gl_uniform() (an already-introspected uniform on
    an ordinary shader) and WebGL2ComputeShader (graphics/webgl/compute.py -
    a compute/raytrace kernel's own uniforms, introspected the same way but
    with no per-shader wrapper object of its own) - mirrors
    gl33/shader.py's own module-level set_gl_uniform() being shared with
    GLComputeShader for the same reason."""
    if t == gl.SAMPLER_2D or t == gl.SAMPLER_2D_ARRAY:
        # A sampler uniform's *real* value (the texture unit it's bound
        # to) isn't known yet at set_uniform() time - `val` here is still
        # the Texture object itself, cached for _bind_textures() (see
        # WebGL2Shader.use()) to actually resolve into a unit and push via
        # this same call, later, once a unit is allocated for this draw.
        # Only an already-resolved int slot is pushed now; a bare Texture
        # is silently a no-op at this point, not an error.
        if isinstance(val, int):
            gl.uniform1i(loc, val)
    elif t == gl.INT:
        gl.uniform1i(loc, int(val))
    elif t == gl.BOOL:
        gl.uniform1i(loc, 1 if val else 0)
    elif t == gl.FLOAT:
        gl.uniform1f(loc, float(val))
    elif t == gl.INT_VEC2:
        gl.uniform2i(loc, int(val[0]), int(val[1]))
    elif t == gl.INT_VEC3:
        gl.uniform3i(loc, int(val[0]), int(val[1]), int(val[2]))
    elif t == gl.INT_VEC4:
        gl.uniform4i(loc, int(val[0]), int(val[1]), int(val[2]), int(val[3]))
    elif t == gl.FLOAT_VEC2:
        x, y = _vec_components(val, 2)
        gl.uniform2f(loc, x, y)
    elif t == gl.FLOAT_VEC3:
        x, y, z = _vec_components(val, 3)
        gl.uniform3f(loc, x, y, z)
    elif t == gl.FLOAT_VEC4:
        x, y, z, w = _vec_components(val, 4)
        gl.uniform4f(loc, x, y, z, w)
    elif t == gl.FLOAT_MAT2:
        gl.uniformMatrix2fv(loc, False, to_js_matrix(val))
    elif t == gl.FLOAT_MAT3:
        gl.uniformMatrix3fv(loc, False, to_js_matrix(val))
    elif t == gl.FLOAT_MAT4:
        gl.uniformMatrix4fv(loc, False, to_js_matrix(val))
