"""Drawing a depth attachment to the window.

A colour attachment reaches the screen through glBlitFramebuffer. A depth one
cannot: blitting GL_DEPTH_BUFFER_BIT writes the default framebuffer's *depth*
buffer, which is invisible, so there is nothing a blit can do here. Depth has
to be sampled and written as colour, which means a shader.

Both GL backends keep their own Framebuffer implementation but want identical
behaviour here, so the program lives in one place and each passes in its own
`#version` line. It is compiled on first use - a depth channel is a debugging
view that most runs never ask for, and nothing should pay for it until it is
actually looked at.

The contrast stretch matters more than it sounds. Depth is stored non-linearly
and, under the orthographic camera a 2D game uses, every sprite in the scene
sits in a very narrow band of it - drawn raw, the whole frame is one flat grey
and the view is useless. So the range actually present is measured once per
draw and stretched to fill black-to-white.
"""
from OpenGL.GL import *
import numpy as np


_VERTEX = """{version}
out vec2 vUV;
void main() {{
    // One oversized triangle, not a quad: three vertices derived from
    // gl_VertexID, so this needs no vertex buffer and no element buffer at
    // all - just a bound VAO, which core profiles require.
    vec2 p = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2));
    vUV = p;
    gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}}
"""

_FRAGMENT = """{version}
uniform sampler2D uDepth;
uniform vec2 uRange;
in vec2 vUV;
out vec4 fragColor;
void main() {{
    float d = texture(uDepth, vUV).r;
    float v = clamp((d - uRange.x) / max(uRange.y - uRange.x, 1e-6), 0.0, 1.0);
    // Near is bright. Depth stores nearer as smaller, so this inverts - a
    // depth view where the things closest to the camera are the ones that
    // stand out reads the way people expect.
    fragColor = vec4(1.0 - v, 1.0 - v, 1.0 - v, 1.0);
}}
"""


def _compile(kind, source):
    shader = glCreateShader(kind)
    glShaderSource(shader, source)
    glCompileShader(shader)
    if not glGetShaderiv(shader, GL_COMPILE_STATUS):
        log = glGetShaderInfoLog(shader)
        glDeleteShader(shader)
        raise RuntimeError(f'depth view shader failed to compile: {log}')
    return shader


class DepthView:
    """A lazily-built program that draws one depth texture to the screen."""

    def __init__(self, version: str = '#version 330 core'):
        self.version = version
        self._program = None
        self._vao = None
        self._depth_loc = None
        self._range_loc = None

    def _build(self):
        vertex = _compile(GL_VERTEX_SHADER, _VERTEX.format(version=self.version))
        fragment = _compile(GL_FRAGMENT_SHADER, _FRAGMENT.format(version=self.version))

        program = glCreateProgram()
        glAttachShader(program, vertex)
        glAttachShader(program, fragment)
        glLinkProgram(program)
        glDeleteShader(vertex)
        glDeleteShader(fragment)
        if not glGetProgramiv(program, GL_LINK_STATUS):
            log = glGetProgramInfoLog(program)
            glDeleteProgram(program)
            raise RuntimeError(f'depth view program failed to link: {log}')

        self._program = program
        self._depth_loc = glGetUniformLocation(program, 'uDepth')
        self._range_loc = glGetUniformLocation(program, 'uRange')
        self._vao = glGenVertexArrays(1)

    def _measure(self, texture):
        """The min and max depth actually present, so the stretch has
        something real to stretch between.

        A full read-back of the depth texture, which is a GPU sync point - and
        fine here, because this only runs while somebody is looking at the
        depth channel. Sampled on a grid rather than every texel so a 4K
        target costs the same as a small one.
        """
        glBindTexture(GL_TEXTURE_2D, texture)
        pixels = glGetTexImage(GL_TEXTURE_2D, 0, GL_DEPTH_COMPONENT, GL_FLOAT)
        glBindTexture(GL_TEXTURE_2D, 0)

        values = np.frombuffer(pixels, dtype=np.float32) if isinstance(
            pixels, bytes) else np.asarray(pixels, dtype=np.float32)
        values = values.ravel()[::17]
        # Texels nothing was drawn to sit at the far plane; including them
        # would peg the top of the range and flatten everything else.
        near = values[values < 1.0]
        if near.size == 0:
            return 0.0, 1.0
        low, high = float(near.min()), float(near.max())
        if high - low < 1e-6:
            # A scene all at one depth - a flat 2D room, which is most of
            # them. Nothing to stretch; show it mid-grey rather than
            # amplifying float noise into a storm.
            return low - 0.5, high + 0.5
        return low, high

    def draw(self, texture, size):
        """Draws `texture` across a `size` viewport of the current target."""
        if texture is None:
            return
        if self._program is None:
            self._build()

        low, high = self._measure(texture)

        previous_depth = glGetBooleanv(GL_DEPTH_TEST)
        previous_blend = glGetBooleanv(GL_BLEND)
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_BLEND)

        glViewport(0, 0, int(size[0]), int(size[1]))
        glUseProgram(self._program)
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, texture)
        glUniform1i(self._depth_loc, 0)
        glUniform2f(self._range_loc, low, high)

        glBindVertexArray(self._vao)
        glDrawArrays(GL_TRIANGLES, 0, 3)
        glBindVertexArray(0)

        glUseProgram(0)
        glBindTexture(GL_TEXTURE_2D, 0)
        if previous_depth:
            glEnable(GL_DEPTH_TEST)
        if previous_blend:
            glEnable(GL_BLEND)
