"""The GL33 "compute" backend: since GL 3.3 has no glDispatchCompute/SSBOs/
image-load-store, a dispatch is emulated as a single fullscreen draw through
the fixed vertex+fragment pipeline - one output pixel (one draw of the
fullscreen triangle, rasterized to a `width` x `height` viewport) per logical
invocation. Inputs are `buffer` blocks read via buffer-texture `texelFetch`;
outputs are `@output` fields written to float framebuffer attachments (see
FreeBodyEngine.graphics.gl33.generator.GL33Generator and its CAPABILITIES for
exactly what this backend can and can't express).
"""
import re

import numpy as np
from OpenGL.GL import *

from fbusl import compile, ShaderType
from fbusl.injector import Injector

from FreeBodyEngine.graphics.compute import ComputeShader
from FreeBodyEngine.graphics.framebuffer import AttachmentType, AttachmentFormat
from FreeBodyEngine.graphics.gl33.buffer import TextureBuffer
from FreeBodyEngine.graphics.gl33.framebuffer import GLFramebuffer
from FreeBodyEngine.graphics.gl33.generator import GL33Generator
from FreeBodyEngine.graphics.gl33.shader import create_shader_program, set_gl_uniform, GLUniform
from FreeBodyEngine import get_service, get_time, error as fb_error, warning


_FULLSCREEN_VERT_SRC = """
#version 330 core
void main() {
    vec2 pos = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
    gl_Position = vec4(pos * 2.0 - 1.0, 0.0, 1.0);
}
"""

# Matches the `out <type> <name>;` lines GL33Generator.generate_inout() emits
# for a compute/raytrace shader's `@output` fields (optionally preceded by a
# `layout(location=N)` qualifier).
_OUTPUT_DECL_RE = re.compile(r"^\s*(?:layout\([^)]*\)\s*)?out\s+(\w+)\s+(\w+)\s*;", re.MULTILINE)

GLSL_OUTPUT_FORMAT = {
    "float": AttachmentFormat.R32F,
    "vec2": AttachmentFormat.RG32F,
    "vec4": AttachmentFormat.RGBA32F,
}


class GLComputeShader(ComputeShader):
    """The GL 3.3 implementation of ComputeShader. Fulfills the abstract
    dispatch()/bind_buffer()/set_uniform()/read_output()/get_output_texture()/
    blit_to_screen() contract entirely through the fullscreen-fragment-pass
    emulation described in this module's docstring, since GL 3.3 has no real
    compute shaders to compile against."""
    _empty_vao = None

    def __init__(self, source, injector: Injector = None, shader_type: ShaderType = ShaderType.COMPUTE):
        """Compiles `source` via GL33Generator into a fragment shader, links
        it against the shared attributeless `_FULLSCREEN_VERT_SRC` vertex
        shader, and introspects the resulting program's active uniforms.
        Also regex-scans the generated fragment source for its `out <type>
        <name>;` declarations (see `_OUTPUT_DECL_RE`) to learn each
        `@output` field's name and GLSL type up front, since dispatch()
        needs that to build the matching framebuffer attachments later."""
        super().__init__(source, injector)
        self.shader_type = shader_type

        frag_src = compile(source, shader_type, GL33Generator, self.injector)
        self._program = create_shader_program(_FULLSCREEN_VERT_SRC, frag_src)

        self.uniforms: dict[str, GLUniform] = {}
        self._setup_uniforms()

        self._buffers: dict[str, TextureBuffer] = {}
        self._buffer_units: dict[str, int] = {}
        self._next_unit = 0

        # findall() yields (glsl_type, name) pairs - inverted here since
        # everything downstream (dispatch()'s attachment map, format lookup)
        # keys off the output's *name*.
        self._outputs: dict[str, str] = {name: glsl_type for glsl_type, name in _OUTPUT_DECL_RE.findall(frag_src)}
        self._fbo: GLFramebuffer | None = None
        self._size: tuple[int, int] | None = None

    @classmethod
    def _get_empty_vao(cls):
        # "Attributeless" fullscreen-triangle rendering (position derived
        # purely from gl_VertexID) needs no vertex buffers at all, but core
        # GL still requires *some* VAO bound to issue a draw call.
        if cls._empty_vao is None:
            cls._empty_vao = glGenVertexArrays(1)
        return cls._empty_vao

    def _setup_uniforms(self):
        count = glGetProgramiv(self._program, GL_ACTIVE_UNIFORMS)
        for i in range(count):
            name, size, gl_type = glGetActiveUniform(self._program, i)
            if isinstance(name, np.ndarray):
                name = name.tobytes().split(b'\x00', 1)[0].decode('utf-8')
            elif isinstance(name, bytes):
                name = name.split(b'\x00', 1)[0].decode('utf-8')
            else:
                name = name.rstrip('\x00')
            location = glGetUniformLocation(self._program, name)
            self.uniforms[name] = GLUniform(location, size, gl_type)

    def bind_texture(self, uniform_name: str, texture):
        """Binds an ordinary 2D `Texture` (e.g. one wrapping a rasterized
        G-buffer attachment via TextureManager.wrap_external_texture) to a
        `texture`-typed `@uniform` in this kernel's source, so it can be
        read with the `sample()` builtin - the same binding a regular
        fragment shader's Material.use() does (see GLShader._bind_textures),
        just invoked directly rather than driven by material property data.

        Deliberately does NOT go through TextureManager.bind_texture()/
        _allocate_slot() - that slot counter is reset and reallocated from 0
        by every single GLShader.draw_mesh() call (see its begin_draw()),
        completely independent of this kernel's own `_next_unit`/
        `_buffer_units` bookkeeping in _bind_texture_buffer() below. Buffer
        textures (bvh_aabb/bvh_meta/triangles) are bound once at
        upload_scene() time and never rebound, so if this used
        TextureManager's counter too, whatever unit the *last mesh drawn
        that frame* happened to leave it at could easily collide with one of
        those - two active samplers of different types (samplerBuffer vs.
        sampler2D) bound to the same unit, which is a GL_INVALID_OPERATION
        at draw time. Continuing this kernel's own counter instead keeps
        every uniform this program has ever bound at a distinct, stable
        unit for the program's whole lifetime."""
        if uniform_name not in self.uniforms:
            warning(f"Compute shader has no uniform named '{uniform_name}'")
            return

        unit = self._buffer_units.get(uniform_name)
        if unit is None:
            unit = self._next_unit
            self._next_unit += 1
            self._buffer_units[uniform_name] = unit

        target, gl_texture_id = texture.manager._get_gl_texture(texture.id)
        glActiveTexture(GL_TEXTURE0 + unit)
        glBindTexture(target, gl_texture_id)

        glUseProgram(self._program)
        glUniform1i(self.uniforms[uniform_name].location, unit)

        uv_rect_name = f"_ENGINE_{uniform_name}_uv_rect"
        if uv_rect_name in self.uniforms:
            rect = texture.uv_rect
            glUniform4f(self.uniforms[uv_rect_name].location, rect[0], rect[1], rect[2], rect[3])

    def _bind_texture_buffer(self, uniform_name: str, buffer: TextureBuffer):
        if uniform_name not in self.uniforms:
            warning(f"Compute shader has no uniform named '{uniform_name}'")
            return

        unit = self._buffer_units.get(uniform_name)
        if unit is None:
            unit = self._next_unit
            self._next_unit += 1
            self._buffer_units[uniform_name] = unit

        buffer.bind(unit)
        self._buffers[uniform_name] = buffer

        glUseProgram(self._program)
        glUniform1i(self.uniforms[uniform_name].location, unit)

    def bind_buffer(self, block: str, field: str, buffer: TextureBuffer):
        """Binds `buffer` to the `field` of a `buffer <block>:` block declared
        in the kernel's source (the GLSL uniform this lowers to is named
        `_ENGINE_<block>_<field>`, matching GL33Generator.generate_buffer_block)."""
        self._bind_texture_buffer(f"_ENGINE_{block}_{field}", buffer)

    def set_uniform(self, name: str, value):
        """Sets uniform `name` on this kernel's program to `value`, via the
        same set_gl_uniform() type-dispatch table GLShader.set_uniform()
        uses. Warns instead of raising if `name` isn't an active uniform."""
        if name not in self.uniforms:
            warning(f"Uniform '{name}' not found in compute shader")
            return
        glUseProgram(self._program)
        set_gl_uniform(self.uniforms[name].location, self.uniforms[name].type, value)

    def dispatch(self, width: int, height: int):
        """Emulates one dispatch over a `width` x `height` logical invocation
        grid as a single fullscreen draw: (re)creates the backing FBO (one
        float attachment per `@output` field, sized to `width`/`height`)
        only when the size actually changed, binds it, updates the
        `DISPATCH_SIZE`/`TIME` builtin uniforms if the kernel declared them,
        disables depth testing (there's no depth buffer here, and a stale
        depth-test state could otherwise discard the fullscreen triangle),
        and issues `glDrawArrays(GL_TRIANGLES, 0, 3)` against the shared
        attributeless VAO - the vertex shader derives full-screen coverage
        purely from `gl_VertexID`, so one triangle covers every pixel and the
        fragment shader runs exactly once per output pixel, i.e. once per
        logical invocation."""
        if self._fbo is None or self._size != (width, height):
            attachments = {
                name: (AttachmentType.COLOR, GLSL_OUTPUT_FORMAT.get(glsl_type, AttachmentFormat.RGBA32F))
                for name, glsl_type in self._outputs.items()
            }
            self._fbo = GLFramebuffer(width, height, attachments)
            self._size = (width, height)

        self._fbo.bind()
        glUseProgram(self._program)

        if "DISPATCH_SIZE" in self.uniforms:
            glUniform3i(self.uniforms["DISPATCH_SIZE"].location, width, height, 1)

        if "TIME" in self.uniforms:
            # Matches GLShader.use()'s handling of the same builtin, so a
            # compute/raytrace kernel can animate against TIME exactly like
            # an ordinary vertex/fragment shader does.
            glUniform1f(self.uniforms["TIME"].location, get_time())

        glDisable(GL_DEPTH_TEST)
        glBindVertexArray(self._get_empty_vao())
        glDrawArrays(GL_TRIANGLES, 0, 3)
        glBindVertexArray(0)

        self._fbo.unbind()

    def read_output(self, name: str) -> np.ndarray:
        """Synchronously reads back the `@output` field `name`'s results via
        the backing FBO's `read()` (a GPU->CPU stall - see Framebuffer.read).
        Requires dispatch() to have already run at least once, since that's
        what creates the FBO."""
        if self._fbo is None:
            fb_error("Cannot read a compute shader's output before dispatch() has run")
            return None
        return self._fbo.read(name)

    def get_output_texture(self, name: str):
        """Wraps the `@output` field `name`'s backing color attachment as an
        ordinary Texture (via TextureManager.wrap_external_texture), so a
        compute/raytrace result can flow into the normal material/sprite
        pipeline without a CPU readback. Requires dispatch() to have already
        run at least once, since that's what creates the FBO."""
        if self._fbo is None:
            fb_error("Cannot get a compute shader's output texture before dispatch() has run")
            return None
        gl_tex_id = self._fbo.get_attachment_texture(name)
        return get_service('renderer').texture_manager.wrap_external_texture(gl_tex_id)

    def blit_to_screen(self, name: str, size: tuple[int, int] = None):
        """Blits one @output field's result directly to whatever framebuffer
        is currently bound (0 = the screen, if nothing else is bound) - the
        simplest way to show a compute/raytrace result on screen without
        wrapping it in a Sprite/Material. Mirrors Framebuffer.draw(), which
        the rest of the engine already uses for showing a G-buffer channel."""
        if self._fbo is None:
            fb_error("Cannot blit a compute shader's output before dispatch() has run")
            return
        self._fbo.draw(name, size)

    def destroy(self):
        """Releases every TextureBuffer this kernel bound (via bind_buffer()/
        upload_scene()) and deletes the underlying GL program. Does not
        delete the shared `_empty_vao` (class-level, reused across every
        GLComputeShader instance) or the backing FBO's own GL objects."""
        for buffer in self._buffers.values():
            buffer.destroy()
        glDeleteProgram(self._program)


class GLRaytraceShader(GLComputeShader):
    """A `@raytrace` kernel: the same fullscreen-pass dispatch mechanism as
    GLComputeShader, plus scene data (a BVH and its triangles) uploaded as
    buffer textures for the generated `trace_ray()` to walk. See
    graphics/raytrace/bvh.py for the CPU-side BVH builder that produces
    `bvh_aabb`/`bvh_meta` in the layout this expects."""

    def __init__(self, source, injector: Injector = None):
        """Compiles `source` as a RAYTRACE-stage kernel (so GL33Generator
        emits the `trace_ray()`/`make_ray()`/etc. intrinsics), leaving the
        scene buffer-texture slots unset until upload_scene() fills them
        in."""
        super().__init__(source, injector, shader_type=ShaderType.RAYTRACE)
        self._bvh_aabb: TextureBuffer | None = None
        self._bvh_meta: TextureBuffer | None = None
        self._triangles: TextureBuffer | None = None

    def upload_scene(self, bvh_aabb: np.ndarray, bvh_meta: np.ndarray, triangles: np.ndarray):
        """`bvh_aabb`: (num_nodes*2, 4) float32. `bvh_meta`: (num_nodes, 4)
        int32 (left_child, right_child, first_prim, prim_count). `triangles`:
        (num_triangles, 3, 3) or (num_triangles*3, 3) float32 vertex
        positions, in the order `bvh_meta`'s (first_prim, prim_count) ranges
        index into - i.e. already reordered by the BVH builder, not the
        original input order."""
        triangles = np.asarray(triangles, dtype=np.float32).reshape(-1, 3)
        padded_triangles = np.zeros((triangles.shape[0], 4), dtype=np.float32)
        padded_triangles[:, :3] = triangles

        self._bvh_aabb = TextureBuffer(np.asarray(bvh_aabb, dtype=np.float32))
        self._bvh_meta = TextureBuffer(np.asarray(bvh_meta, dtype=np.int32))
        self._triangles = TextureBuffer(padded_triangles)

        # _bind_texture_buffer() already registers each buffer in
        # self._buffers, so the base class's destroy() covers cleanup here -
        # no need to also destroy self._bvh_aabb/_bvh_meta/_triangles directly.
        self._bind_texture_buffer("_ENGINE_bvh_aabb", self._bvh_aabb)
        self._bind_texture_buffer("_ENGINE_bvh_meta", self._bvh_meta)
        self._bind_texture_buffer("_ENGINE_triangles", self._triangles)
