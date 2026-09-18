"""The WebGL2 "compute" backend: same fullscreen-fragment-pass emulation as
graphics/gl33/compute.py (WebGL2, like GL 3.3, has no glDispatchCompute/
SSBOs/image-load-store either) - one output pixel per logical invocation,
inputs read via buffer-texture-emulated `texelFetch` (see graphics/webgl/
buffer.py's WebGL2TextureBuffer and graphics/webgl/generator.py's
buffer-block/raytrace codegen for why that's a 2D data texture here rather
than a real GL_TEXTURE_BUFFER), outputs written to float framebuffer
attachments. Mirrors GLComputeShader/GLRaytraceShader class-for-class and
method-for-method - the only real differences throughout are mechanical:
PyOpenGL's `glFoo(...)` global-state calls become `self.gl.foo(...)` calls
against this canvas's WebGL2RenderingContext, same as every other
graphics/webgl/*.py module (see shader.py's own docstring).
"""
import re

import numpy as np

from fbusl import compile, ShaderType
from fbusl.injector import Injector

from FreeBodyEngine.graphics.compute import ComputeShader
from FreeBodyEngine.graphics.framebuffer import AttachmentType, AttachmentFormat
from FreeBodyEngine.graphics.webgl.buffer import WebGL2TextureBuffer
from FreeBodyEngine.graphics.webgl.framebuffer import WebGL2Framebuffer
from FreeBodyEngine.graphics.webgl.generator import WebGL2Generator
from FreeBodyEngine.graphics.webgl.shader import create_shader_program, set_gl_uniform, WebGLUniform
from FreeBodyEngine import get_service, get_time, error as fb_error, warning


_FULLSCREEN_VERT_SRC = """#version 300 es
void main() {
    vec2 pos = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
    gl_Position = vec4(pos * 2.0 - 1.0, 0.0, 1.0);
}
"""

# Matches the `out <type> <name>;` lines WebGL2Generator.generate_inout()
# emits for a compute/raytrace shader's `@output` fields (optionally
# preceded by a `layout(location=N)` qualifier) - identical shape to
# GL33Generator's own output declarations, so the same regex applies
# unchanged (duplicated rather than imported from graphics.gl33.compute:
# that module does `from OpenGL.GL import *` at its own top level, which
# would crash immediately under Pyodide the moment anything imports it,
# even just for this constant - see graphics/gl33/__init__.py's own
# platform guard for the same reasoning one level up).
_OUTPUT_DECL_RE = re.compile(r"^\s*(?:layout\([^)]*\)\s*)?out\s+(\w+)\s+(\w+)\s*;", re.MULTILINE)

GLSL_OUTPUT_FORMAT = {
    "float": AttachmentFormat.R32F,
    "vec2": AttachmentFormat.RG32F,
    "vec4": AttachmentFormat.RGBA32F,
}


class WebGL2ComputeShader(ComputeShader):
    """The WebGL2 implementation of ComputeShader. Fulfills the abstract
    dispatch()/bind_buffer()/set_uniform()/read_output()/get_output_texture()/
    blit_to_screen() contract entirely through the fullscreen-fragment-pass
    emulation described in this module's docstring, since WebGL2 has no
    real compute shaders to compile against."""
    _empty_vao = None

    def __init__(self, source, injector: Injector = None, shader_type: ShaderType = ShaderType.COMPUTE):
        """Compiles `source` via WebGL2Generator into a fragment shader,
        links it against the shared attributeless `_FULLSCREEN_VERT_SRC`
        vertex shader, and introspects the resulting program's active
        uniforms. Also regex-scans the generated fragment source for its
        `out <type> <name>;` declarations (see `_OUTPUT_DECL_RE`) to learn
        each `@output` field's name and GLSL type up front, since
        dispatch() needs that to build the matching framebuffer
        attachments later."""
        super().__init__(source, injector)
        self.gl = get_service('renderer').gl
        self.shader_type = shader_type

        frag_src = compile(source, shader_type, WebGL2Generator, self.injector)
        self._program = create_shader_program(self.gl, _FULLSCREEN_VERT_SRC, frag_src)

        self.uniforms: dict[str, WebGLUniform] = {}
        self._setup_uniforms()

        self._buffers: dict[str, WebGL2TextureBuffer] = {}
        self._buffer_units: dict[str, int] = {}
        self._next_unit = 0
        # unit -> (target, texture), re-applied at the top of every
        # dispatch() - see dispatch()'s own comment for why a one-time bind
        # here isn't enough on this backend.
        self._bound_textures: dict[int, tuple] = {}

        # findall() yields (glsl_type, name) pairs - inverted here since
        # everything downstream (dispatch()'s attachment map, format lookup)
        # keys off the output's *name*.
        self._outputs: dict[str, str] = {name: glsl_type for glsl_type, name in _OUTPUT_DECL_RE.findall(frag_src)}
        self._fbo: WebGL2Framebuffer | None = None
        self._size: tuple[int, int] | None = None

    def _get_empty_vao(self):
        # "Attributeless" fullscreen-triangle rendering (position derived
        # purely from gl_VertexID) needs no vertex buffers at all, but
        # WebGL2 still requires *some* VAO bound to issue a draw call -
        # same as desktop core GL (see GLComputeShader._get_empty_vao()).
        # Instance-level, not class-level like GL33's own classmethod
        # version: that one memoizes on the class because desktop GL's
        # context is truly global process-wide state, but this needs a
        # live `self.gl` (this canvas's specific WebGL2RenderingContext)
        # to create it, which only exists once an instance does.
        if WebGL2ComputeShader._empty_vao is None:
            WebGL2ComputeShader._empty_vao = self.gl.createVertexArray()
        return WebGL2ComputeShader._empty_vao

    def _setup_uniforms(self):
        gl = self.gl
        count = gl.getProgramParameter(self._program, gl.ACTIVE_UNIFORMS)
        for i in range(count):
            info = gl.getActiveUniform(self._program, i)
            name = str(info.name)
            if name.endswith("[0]"):
                name = name[:-3]
            location = gl.getUniformLocation(self._program, name)
            self.uniforms[name] = WebGLUniform(location, int(info.size), int(info.type))

    def bind_texture(self, uniform_name: str, texture):
        """Binds an ordinary 2D `Texture` (e.g. one wrapping a rasterized
        G-buffer attachment via TextureManager.wrap_external_texture) to a
        `texture`-typed `@uniform` in this kernel's source, so it can be
        read with the `sample()`/`fb_sample()` builtin - the same binding
        an ordinary shader's Material.use() does (see
        WebGL2Shader._bind_textures), just invoked directly rather than
        driven by material property data.

        Deliberately does NOT go through TextureManager.bind_texture()/
        _allocate_slot() - see GLComputeShader.bind_texture()'s own
        docstring for exactly why (this kernel's own `_next_unit`/
        `_buffer_units` counter needs to stay independent of whatever the
        ordinary draw-call texture manager is doing for other shaders,
        the same reasoning applies unchanged on this backend)."""
        if uniform_name not in self.uniforms:
            warning(f"Compute shader has no uniform named '{uniform_name}'")
            return

        gl = self.gl
        unit = self._buffer_units.get(uniform_name)
        if unit is None:
            unit = self._next_unit
            self._next_unit += 1
            self._buffer_units[uniform_name] = unit

        target, gl_texture = texture.manager._get_gl_texture(texture.id)
        gl.activeTexture(gl.TEXTURE0 + unit)
        gl.bindTexture(target, gl_texture)
        self._bound_textures[unit] = (target, gl_texture)

        gl.useProgram(self._program)
        gl.uniform1i(self.uniforms[uniform_name].location, unit)

        uv_rect_name = f"_ENGINE_{uniform_name}_uv_rect"
        if uv_rect_name in self.uniforms:
            rect = texture.uv_rect
            gl.uniform4f(self.uniforms[uv_rect_name].location, rect[0], rect[1], rect[2], rect[3])

    def _bind_texture_buffer(self, uniform_name: str, buffer: WebGL2TextureBuffer):
        if uniform_name not in self.uniforms:
            warning(f"Compute shader has no uniform named '{uniform_name}'")
            return

        gl = self.gl
        unit = self._buffer_units.get(uniform_name)
        if unit is None:
            unit = self._next_unit
            self._next_unit += 1
            self._buffer_units[uniform_name] = unit

        buffer.bind(unit)
        self._buffers[uniform_name] = buffer
        self._bound_textures[unit] = (gl.TEXTURE_2D, buffer.tex)

        gl.useProgram(self._program)
        gl.uniform1i(self.uniforms[uniform_name].location, unit)

    def bind_buffer(self, block: str, field: str, buffer: WebGL2TextureBuffer):
        """Binds `buffer` to the `field` of a `buffer <block>:` block
        declared in the kernel's source (the GLSL uniform this lowers to
        is named `_ENGINE_<block>_<field>`, matching
        WebGL2Generator.generate_buffer_block())."""
        self._bind_texture_buffer(f"_ENGINE_{block}_{field}", buffer)

    def set_uniform(self, name: str, value):
        """Sets uniform `name` on this kernel's program to `value`, via the
        same set_gl_uniform() type-dispatch table WebGL2Shader.set_uniform()
        uses. Warns instead of raising if `name` isn't an active uniform."""
        if name not in self.uniforms:
            warning(f"Uniform '{name}' not found in compute shader")
            return
        self.gl.useProgram(self._program)
        set_gl_uniform(self.gl, self.uniforms[name].location, self.uniforms[name].type, value)

    def dispatch(self, width: int, height: int):
        """Emulates one dispatch over a `width` x `height` logical
        invocation grid as a single fullscreen draw - see
        GLComputeShader.dispatch()'s own docstring for the full mechanism,
        identical here down to the shared attributeless VAO trick, just
        issued through `self.gl` instead of PyOpenGL's global-state
        calls."""
        gl = self.gl
        if self._fbo is None or self._size != (width, height):
            attachments = {
                name: (AttachmentType.COLOR, GLSL_OUTPUT_FORMAT.get(glsl_type, AttachmentFormat.RGBA32F))
                for name, glsl_type in self._outputs.items()
            }
            self._fbo = WebGL2Framebuffer(width, height, attachments)
            self._size = (width, height)

        self._fbo.bind()
        gl.useProgram(self._program)

        # Every texture unit this kernel uses (buffer textures bound once
        # by upload_scene()/bind_buffer(), G-buffer wraps bound by
        # bind_texture()) needs re-binding here, every dispatch - unlike
        # desktop's GLComputeShader, which puts its buffer textures on the
        # real GL_TEXTURE_BUFFER target (an independent binding point per
        # unit, untouched by anything else), this backend's buffer
        # textures share the ordinary GL_TEXTURE_2D target with every
        # material texture in the scene. WebGL2TextureManager.begin_draw()
        # freely rebinds GL_TEXTURE_2D on units 0, 1, 2, ... for every
        # ordinary mesh/composite draw earlier in the same frame, with no
        # awareness that this kernel considers those same unit numbers
        # permanently its own - by the time this LATE-phase dispatch()
        # runs, a unit this kernel bound once at upload_scene() time (e.g.
        # bvh_meta's integer texture) has almost certainly been clobbered
        # by an unrelated float/normalized material texture, which then
        # fails GLSL's sampler/texture type check the moment this kernel's
        # isampler2D tries to read it ("Mismatch between texture format
        # and sampler type").
        for unit, (target, texture) in self._bound_textures.items():
            gl.activeTexture(gl.TEXTURE0 + unit)
            gl.bindTexture(target, texture)

        if "DISPATCH_SIZE" in self.uniforms:
            gl.uniform3i(self.uniforms["DISPATCH_SIZE"].location, width, height, 1)

        if "TIME" in self.uniforms:
            # Matches WebGL2Shader.use()'s handling of the same builtin, so
            # a compute/raytrace kernel can animate against TIME exactly
            # like an ordinary vertex/fragment shader does.
            gl.uniform1f(self.uniforms["TIME"].location, get_time())

        gl.disable(gl.DEPTH_TEST)
        gl.bindVertexArray(self._get_empty_vao())
        gl.drawArrays(gl.TRIANGLES, 0, 3)
        gl.bindVertexArray(None)

        self._fbo.unbind()

    def read_output(self, name: str) -> np.ndarray:
        """Synchronously reads back the `@output` field `name`'s results via
        the backing FBO's `read()` (a GPU->CPU stall - see
        WebGL2Framebuffer.read). Requires dispatch() to have already run
        at least once, since that's what creates the FBO."""
        if self._fbo is None:
            fb_error("Cannot read a compute shader's output before dispatch() has run")
            return None
        return self._fbo.read(name)

    def get_output_texture(self, name: str):
        """Wraps the `@output` field `name`'s backing color attachment as
        an ordinary Texture (via TextureManager.wrap_external_texture), so
        a compute/raytrace result can flow into the normal material/sprite
        pipeline without a CPU readback. Requires dispatch() to have
        already run at least once, since that's what creates the FBO."""
        if self._fbo is None:
            fb_error("Cannot get a compute shader's output texture before dispatch() has run")
            return None
        gl_tex = self._fbo.get_attachment_texture(name)
        return get_service('renderer').texture_manager.wrap_external_texture(gl_tex)

    def blit_to_screen(self, name: str, size: tuple[int, int] = None):
        """Blits one @output field's result directly to whatever
        framebuffer is currently bound (the screen, if nothing else is
        bound) - the simplest way to show a compute/raytrace result on
        screen without wrapping it in a Sprite/Material. Mirrors
        WebGL2Framebuffer.draw(), which the rest of the engine already
        uses for showing a G-buffer channel."""
        if self._fbo is None:
            fb_error("Cannot blit a compute shader's output before dispatch() has run")
            return
        self._fbo.draw(name, size)

    def destroy(self):
        """Releases every WebGL2TextureBuffer this kernel bound (via
        bind_buffer()/upload_scene()) and deletes the underlying GL
        program. Does not delete the shared `_empty_vao` (class-level,
        reused across every WebGL2ComputeShader instance) or the backing
        FBO's own GL objects."""
        for buffer in self._buffers.values():
            buffer.destroy()
        self.gl.deleteProgram(self._program)


class WebGL2RaytraceShader(WebGL2ComputeShader):
    """A `@raytrace` kernel: the same fullscreen-pass dispatch mechanism as
    WebGL2ComputeShader, plus scene data (a BVH and its triangles) uploaded
    as buffer-texture-emulated 2D data textures for the generated
    `trace_ray()` to walk. See graphics/raytrace/bvh.py for the CPU-side
    BVH builder that produces `bvh_aabb`/`bvh_meta` in the layout this
    expects - identical to GLRaytraceShader's own contract, just backed by
    WebGL2TextureBuffer instead of TextureBuffer."""

    def __init__(self, source, injector: Injector = None):
        """Compiles `source` as a RAYTRACE-stage kernel (so WebGL2Generator
        emits the `trace_ray()`/`make_ray()`/etc. intrinsics), leaving the
        scene buffer slots unset until upload_scene() fills them in."""
        super().__init__(source, injector, shader_type=ShaderType.RAYTRACE)
        self._bvh_aabb: WebGL2TextureBuffer | None = None
        self._bvh_meta: WebGL2TextureBuffer | None = None
        self._triangles: WebGL2TextureBuffer | None = None

    def upload_scene(self, bvh_aabb: np.ndarray, bvh_meta: np.ndarray, triangles: np.ndarray):
        """`bvh_aabb`: (num_nodes*2, 4) float32. `bvh_meta`: (num_nodes, 4)
        int32 (left_child, right_child, first_prim, prim_count).
        `triangles`: (num_triangles, 3, 3) or (num_triangles*3, 3) float32
        vertex positions, in the order `bvh_meta`'s (first_prim,
        prim_count) ranges index into - i.e. already reordered by the BVH
        builder, not the original input order. Same contract as
        GLRaytraceShader.upload_scene()."""
        triangles = np.asarray(triangles, dtype=np.float32).reshape(-1, 3)
        padded_triangles = np.zeros((triangles.shape[0], 4), dtype=np.float32)
        padded_triangles[:, :3] = triangles

        self._bvh_aabb = WebGL2TextureBuffer(np.asarray(bvh_aabb, dtype=np.float32))
        self._bvh_meta = WebGL2TextureBuffer(np.asarray(bvh_meta, dtype=np.int32))
        self._triangles = WebGL2TextureBuffer(padded_triangles)

        # _bind_texture_buffer() already registers each buffer in
        # self._buffers, so the base class's destroy() covers cleanup here -
        # no need to also destroy self._bvh_aabb/_bvh_meta/_triangles directly.
        self._bind_texture_buffer("_ENGINE_bvh_aabb", self._bvh_aabb)
        self._bind_texture_buffer("_ENGINE_bvh_meta", self._bvh_meta)
        self._bind_texture_buffer("_ENGINE_triangles", self._triangles)
