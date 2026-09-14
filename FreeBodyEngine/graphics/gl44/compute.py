"""The GL44 "compute" backend: real GL_COMPUTE_SHADER stages dispatched via
glDispatchCompute, with SSBOs for `buffer` blocks and image2D/imageStore for
`@output` fields - no fullscreen-quad emulation needed (see
graphics/gl33/compute.py for that emulation and why GL33 needs it).

Same public interface as GLComputeShader (graphics/gl33/compute.py) - code
written against ComputeShader doesn't change when swapping which backend
constructs it.
"""
import math

import numpy as np
from OpenGL.GL import *

from fbusl import compile, ShaderType
from fbusl.injector import Injector

from FreeBodyEngine.graphics.compute import ComputeShader
from FreeBodyEngine.graphics.gl44.generator import GL44Generator, IMAGE_FORMAT
from FreeBodyEngine.graphics.gl44.buffer import SSBOBuffer
from FreeBodyEngine import get_service, get_time, error as fb_error, warning


GL_IMAGE_FORMAT_ENUM = {
    "r32f": GL_R32F,
    "r32i": GL_R32I,
    "rg32f": GL_RG32F,
    "rgba32f": GL_RGBA32F,
}

# (glGetTexImage format, glGetTexImage type, channel count) per image format -
# what to read a given @output field's texture back as.
GL_IMAGE_READ_FORMAT = {
    "r32f": (GL_RED, GL_FLOAT, 1),
    "r32i": (GL_RED_INTEGER, GL_INT, 1),
    "rg32f": (GL_RG, GL_FLOAT, 2),
    "rgba32f": (GL_RGBA, GL_FLOAT, 4),
}


class GL44ComputeShader(ComputeShader):
    """The GL 4.4 implementation of ComputeShader: compiles FBUSL straight to
    a real GL_COMPUTE_SHADER and runs it via glDispatchCompute, with `buffer`
    blocks backed by real SSBOs and `@output` fields written through
    image2D/imageStore rather than GL33's fullscreen-draw + framebuffer-
    attachment emulation (see graphics/gl33/compute.py)."""
    def __init__(self, source, injector: Injector = None, shader_type: ShaderType = ShaderType.COMPUTE):
        """Compiles `source` (keeping the GL44Generator instance around via
        `_compile_and_keep_generator`, since its `image_bindings` mapping is
        needed after compiling) into a linked compute program, introspects
        its uniforms, and records each `@output` field's image unit/format so
        `dispatch()` can (re)create backing textures sized to whatever
        width/height it's called with."""
        super().__init__(source, injector)
        self.shader_type = shader_type

        # fbusl.compile() only returns the generated source, not the
        # generator instance - construct one separately, using the exact
        # same source/injector handling compile() does, so
        # generator.image_bindings (assigned during generate()) reflects
        # the *same* compile that produced `compute_src` below, not a
        # stale/different one.
        self._generator = self._compile_and_keep_generator(source, shader_type)
        compute_src = self._last_generated_source

        self._program = self._build_program(compute_src)
        self.local_size = self._generator._local_size()

        self.uniforms = {}
        self._setup_uniforms()

        self._buffers: dict[str, SSBOBuffer] = {}
        self._image_units: dict[str, int] = dict(self._generator.image_bindings)
        self._output_formats: dict[str, str] = {
            name: IMAGE_FORMAT[self._generator.get_type_name(self._generator._output_fields[name].type)]
            for name in self._image_units
        }
        self._output_textures: dict[str, int] = {}
        self._size: tuple[int, int] | None = None

    def _compile_and_keep_generator(self, source, shader_type):
        """Mirrors fbusl.compiler.compile() step for step, but keeps the
        Generator instance instead of discarding it - GL44ComputeShader
        needs its image_bindings mapping after compiling."""
        from fbusl.parser import Lexer, Parser
        from fbusl.semantic import SemanticAnalyser
        from fbusl.optimizer import Optimizer

        injector = self.injector
        injector.initialize(shader_type)
        if not isinstance(source, str):
            path = source.data.path
            source_text = source.read()
        else:
            path = None
            source_text = source

        lexer = Lexer(injector.source_inject(source_text), path)
        tokens = lexer.tokenize()
        parser = Parser(tokens)
        tree = injector.ast_inject(parser.parse())

        semantics = SemanticAnalyser(tree, shader_type, injector.get_builtins())
        semantics.analyse()

        tree = Optimizer(tree).optimize()

        generator = GL44Generator(tree, shader_type)
        self._last_generated_source = generator.generate()
        return generator

    def _build_program(self, compute_src: str) -> int:
        shader = glCreateShader(GL_COMPUTE_SHADER)
        glShaderSource(shader, compute_src)
        glCompileShader(shader)
        if glGetShaderiv(shader, GL_COMPILE_STATUS) != GL_TRUE:
            log = glGetShaderInfoLog(shader).decode()
            raise RuntimeError(f"Compute shader compile error:\n{log}\n\nSource:\n{compute_src}")

        program = glCreateProgram()
        glAttachShader(program, shader)
        glLinkProgram(program)
        if glGetProgramiv(program, GL_LINK_STATUS) != GL_TRUE:
            log = glGetProgramInfoLog(program).decode()
            raise RuntimeError(f"Compute shader link error:\n{log}")

        glDeleteShader(shader)
        return program

    def _setup_uniforms(self):
        from FreeBodyEngine.graphics.gl44.shader import GL44Uniform
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
            self.uniforms[name] = GL44Uniform(location, size, gl_type)

    def bind_buffer(self, block: str, field: str, buffer: SSBOBuffer):
        """Binds `buffer` to the `block` (the `field` argument is kept only
        for interface parity with GLComputeShader - a real SSBO backs the
        *whole* block at once, not one field, since GLSL native array
        indexing means every field of the block lives in the same backing
        buffer)."""
        block_name = f"_ENGINE_block_{block}"
        index = glGetProgramResourceIndex(self._program, GL_SHADER_STORAGE_BLOCK, block_name)
        if index == GL_INVALID_INDEX:
            warning(f"Compute shader has no buffer block named '{block}'")
            return

        binding = len(self._buffers)
        glShaderStorageBlockBinding(self._program, index, binding)
        buffer.bind(binding)
        self._buffers[block] = buffer

    def set_uniform(self, name: str, value):
        """Sets uniform `name` on this kernel's program, via the same
        glUniform*-dispatch table GL44Shader uses (`set_gl_uniform`)."""
        from FreeBodyEngine.graphics.gl44.shader import set_gl_uniform
        if name not in self.uniforms:
            warning(f"Uniform '{name}' not found in compute shader")
            return
        glUseProgram(self._program)
        set_gl_uniform(self.uniforms[name].location, self.uniforms[name].type, value)

    def _ensure_output_textures(self, width: int, height: int):
        if self._size == (width, height):
            return

        for tex in self._output_textures.values():
            glDeleteTextures(1, [tex])
        self._output_textures.clear()

        for name, image_fmt in self._output_formats.items():
            tex = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, tex)
            glTexStorage2D(GL_TEXTURE_2D, 1, GL_IMAGE_FORMAT_ENUM[image_fmt], width, height)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
            self._output_textures[name] = tex

        self._size = (width, height)

    def dispatch(self, width: int, height: int):
        """Runs the kernel once per (x, y) in [0, width) x [0, height): binds
        each `@output` field's backing texture as an image unit
        (`glBindImageTexture`, recreating them first if `width`/`height`
        changed since the last dispatch), sets the `DISPATCH_SIZE`/`TIME`
        builtins if the kernel declares them, and issues
        `glDispatchCompute` with enough work groups (rounded up) to cover
        the requested size. Ends with a full `glMemoryBarrier`, since - unlike
        GL33's fixed-pipeline emulation, where a draw call's output is
        already ordered before whatever runs after it - SSBO writes and
        image stores here aren't otherwise guaranteed visible to a
        subsequent read."""
        self._ensure_output_textures(width, height)

        glUseProgram(self._program)

        for name, tex in self._output_textures.items():
            unit = self._image_units[name]
            image_fmt = GL_IMAGE_FORMAT_ENUM[self._output_formats[name]]
            glBindImageTexture(unit, tex, 0, GL_FALSE, 0, GL_WRITE_ONLY, image_fmt)

        if "DISPATCH_SIZE" in self.uniforms:
            glUniform3i(self.uniforms["DISPATCH_SIZE"].location, width, height, 1)
        if "TIME" in self.uniforms:
            glUniform1f(self.uniforms["TIME"].location, get_time())

        lx, ly, lz = self.local_size
        groups_x = max(1, math.ceil(width / lx))
        groups_y = max(1, math.ceil(height / ly))
        glDispatchCompute(groups_x, groups_y, 1)

        # SSBO writes and image stores aren't guaranteed visible to a
        # subsequent read (a glReadPixels/glGetTexImage, or another
        # dispatch's SSBO read) without an explicit barrier - unlike GL33's
        # emulation, where the fixed-function fragment pipeline's own
        # ordering already guarantees a draw call's output is complete
        # before anything after it runs.
        glMemoryBarrier(GL_ALL_BARRIER_BITS)

    def read_output(self, name: str) -> np.ndarray:
        """Synchronously reads back `@output` field `name`'s texture
        (`glGetTexImage`) into a `(height, width, channels)` numpy array,
        typed int32 or float32 to match the field's declared image format."""
        if name not in self._output_textures:
            fb_error(f"Compute shader has no @output named '{name}'")
            return None

        image_fmt = self._output_formats[name]
        fmt, typ, channels = GL_IMAGE_READ_FORMAT[image_fmt]
        width, height = self._size

        glBindTexture(GL_TEXTURE_2D, self._output_textures[name])
        dtype = np.int32 if typ == GL_INT else np.float32
        raw = glGetTexImage(GL_TEXTURE_2D, 0, fmt, typ)
        return np.frombuffer(raw, dtype=dtype).reshape(height, width, channels)

    def get_output_texture(self, name: str):
        """Exposes `@output` field `name`'s backing GL texture as an
        engine-level Texture (via TextureManager.wrap_external_texture), so a
        compute result can feed into the ordinary material/rendering
        pipeline without a CPU readback."""
        from FreeBodyEngine.graphics.texture import Texture
        if name not in self._output_textures:
            fb_error(f"Compute shader has no @output named '{name}'")
            return None
        return get_service('renderer').texture_manager.wrap_external_texture(self._output_textures[name])

    def blit_to_screen(self, name: str, size: tuple[int, int] = None):
        """Blits `@output` field `name`'s texture directly to whatever
        framebuffer is currently bound (0 = the screen), optionally scaling
        to `size`. Wraps the output texture in a scratch one-off read FBO
        just for the blit rather than pulling in the full Framebuffer class,
        since Framebuffer always creates (and owns) its own textures instead
        of wrapping an existing one."""
        if name not in self._output_textures:
            fb_error(f"Compute shader has no @output named '{name}'")
            return

        width, height = self._size
        size = (width, height) if size is None else size

        # glBlitFramebuffer needs an FBO to read *from* - wrap the output
        # texture in a scratch one-off FBO just for the blit rather than
        # pulling in the full Framebuffer class, which always creates (and
        # owns) its own textures instead of wrapping an existing one.
        fbo = glGenFramebuffers(1)
        glBindFramebuffer(GL_READ_FRAMEBUFFER, fbo)
        glFramebufferTexture2D(GL_READ_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, self._output_textures[name], 0)
        glReadBuffer(GL_COLOR_ATTACHMENT0)

        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, 0)
        glBlitFramebuffer(0, 0, width, height, 0, 0, size[0], size[1], GL_COLOR_BUFFER_BIT, GL_NEAREST)

        glBindFramebuffer(GL_READ_FRAMEBUFFER, 0)
        glDeleteFramebuffers(1, [fbo])

    def destroy(self):
        """Releases every GPU resource this kernel owns: its SSBOs, its
        `@output` backing textures, and the linked compute program itself."""
        for buffer in self._buffers.values():
            buffer.destroy()
        for tex in self._output_textures.values():
            glDeleteTextures(1, [tex])
        glDeleteProgram(self._program)
