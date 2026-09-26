"""GLESShader: GLShader (graphics/gl33/shader.py) with only its generator
swapped out - see GLShader's own docstring for why `generator_cls` exists
as an overridable class attribute in the first place. Every actual GL call
(program creation, uniform introspection/dispatch, texture binding) is
inherited unchanged, since GLES 3.0's core API covers all of it identically
to desktop GL 3.3.

WebGL2Generator (not a new GLES-specific generator) is reused directly:
WebGL2 *is* GLSL ES 3.00 under the hood (see its own module docstring in
graphics/webgl/generator.py) - it has no browser/JS dependency of its own,
it's pure FBUSL-to-text codegen, so the exact same generator that already
produces correct `#version 300 es`-headed, precision-qualified source for
a browser's WebGL2 context produces equally correct source for a native
GLES 3.0 context here."""
from FreeBodyEngine.graphics.gl33.shader import GLShader
from FreeBodyEngine.graphics.webgl.generator import WebGL2Generator


class GLESShader(GLShader):
    generator_cls = WebGL2Generator
