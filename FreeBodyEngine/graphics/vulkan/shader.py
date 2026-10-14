"""VulkanShader - the Shader interface for vertex+fragment pairs (plus an
optional geometry stage) compiled by FBUSL's SPIR-V backend.

A geometry stage runs natively when the device has the geometryShader
feature, with the pipeline's input topology taken from its `input=`.

Uniforms live in a CPU-side copy of the shared uniform block (see
SPIRVGenerator.graphics_layout()); set_uniform() packs into it, and every
draw copies the current bytes into that frame's uniform ring - which is
what makes "set a uniform, draw, set it again, draw" behave as it does in
GL even though Vulkan runs the draws later.

Values are packed exactly as GL44's glUniform* calls would read them,
matrices included: GL44 passes numpy matrices with transpose=GL_FALSE, so
the array's raw memory is taken as column-major - each row of the numpy
array becomes a column. The engine's matrices are built for that, so it's
reproduced here rather than "corrected".
"""
import itertools
import struct

import numpy as np
import vulkan as vk

import fbusl
from fbusl import ShaderType
from fbusl.injector import Injector
from fbusl.parser import Lexer, Parser
from fbusl.semantic import SemanticAnalyser
from fbusl import geometry as fbusl_geometry

from FreeBodyEngine import error as fb_error, warning, get_service, get_time
from FreeBodyEngine.graphics.shader import Shader
from FreeBodyEngine.graphics.color import Color
from FreeBodyEngine.graphics.texture import Texture, TextureStack
from FreeBodyEngine.graphics.image import Image
from FreeBodyEngine.math import Vector, Vector3
from FreeBodyEngine.graphics.vulkan.generator import SPIRVGenerator


def _source_text(source):
    if source is None or isinstance(source, str):
        return source, None
    return source.read(), getattr(getattr(source, "data", None), "path", None)


def _front(source, stage, injector):
    text, path = _source_text(source)
    injector.initialize(stage)
    tree = injector.ast_inject(Parser(Lexer(injector.source_inject(text), path).tokenize()).parse())
    SemanticAnalyser(tree, stage, injector.get_builtins()).analyse()
    return tree


# A geometry stage's `input=` -> the topology its pipeline assembles.
GEOMETRY_TOPOLOGIES = {
    "points": vk.VK_PRIMITIVE_TOPOLOGY_POINT_LIST,
    "lines": vk.VK_PRIMITIVE_TOPOLOGY_LINE_LIST,
    "lines_adjacency": vk.VK_PRIMITIVE_TOPOLOGY_LINE_LIST_WITH_ADJACENCY,
    "triangles": vk.VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST,
    "triangles_adjacency": vk.VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST_WITH_ADJACENCY,
}


def _vec(value, n):
    if isinstance(value, Color):
        values = value.float_normalized_a if n == 4 else value.float_normalized
        return [float(v) for v in values[:n]]
    if isinstance(value, Vector3):
        return [float(value.x), float(value.y), float(value.z)][:n]
    if isinstance(value, Vector):
        return [float(value.x), float(value.y)][:n]
    return [float(v) for v in list(value)[:n]]


def pack_uniform(t, value) -> bytes:
    if isinstance(t, tuple):
        _, element, length = t
        out = b""
        for item in list(value)[:length]:
            chunk = pack_uniform(element, item)
            out += chunk + b"\0" * (-len(chunk) % 16)
        return out
    if t in ("int", "bool"):
        return struct.pack("<i", int(value))
    if t == "float":
        return struct.pack("<f", float(value))
    if t in ("ivec2", "ivec3"):
        n = int(t[-1])
        return struct.pack(f"<{n}i", *(int(v) for v in list(value)[:n]))
    if t in ("vec2", "vec3", "vec4"):
        n = int(t[-1])
        return struct.pack(f"<{n}f", *_vec(value, n))
    if t in ("mat2", "mat3", "mat4"):
        n = int(t[-1])
        flat = np.asarray(value, dtype=np.float32).reshape(-1)
        out = b""
        for col in range(n):  # GL44: raw memory read as columns
            column = flat[col * n:(col + 1) * n].tobytes()
            out += column + b"\0" * (16 - len(column))
        return out
    raise TypeError(f"can't pack a uniform of type {t}")


DESCRIPTOR_TYPES = {
    "uniform_buffer": vk.VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER_DYNAMIC,
    "sampler": vk.VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER,
    "storage_buffer": vk.VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,
}
LIST_TOPOLOGIES = {
    "points": vk.VK_PRIMITIVE_TOPOLOGY_POINT_LIST,
    "lines": vk.VK_PRIMITIVE_TOPOLOGY_LINE_LIST,
    "triangles": vk.VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST,
}


# Pipelines and descriptor sets are cached by shader id, so ids are never
# reused: id(self) is, once a shader is garbage-collected, and a new one
# would inherit its pipelines - other stages, other interface.
_IDS = itertools.count(1)


def _parse_only(source, stage, injector):
    """Injected and parsed but not analysed - for the geometry emulation
    transform, which analyses the program it builds."""
    text, path = _source_text(source)
    injector.initialize(stage)
    tree = injector.ast_inject(Parser(Lexer(injector.source_inject(text), path).tokenize()).parse())
    return tree, dict(injector.get_builtins() or {})


def _create_set_layout(device, bindings, stages):
    layout_bindings = [vk.VkDescriptorSetLayoutBinding(
        binding=b["binding"], descriptorType=DESCRIPTOR_TYPES[b["kind"]], descriptorCount=1, stageFlags=stages)
        for b in bindings]
    set_layout = vk.vkCreateDescriptorSetLayout(device, vk.VkDescriptorSetLayoutCreateInfo(
        bindingCount=len(layout_bindings), pBindings=layout_bindings or None), None)
    pipeline_layout = vk.vkCreatePipelineLayout(device, vk.VkPipelineLayoutCreateInfo(
        setLayoutCount=1, pSetLayouts=[set_layout]), None)
    return set_layout, pipeline_layout


class _GeometryCompute:
    """The compute pre-pass of a compute-emulated geometry stage: its
    pipeline, its own uniform block (the user's uniforms land here as well
    as in the graphics one - see VulkanShader._write), and the buffers it
    appends primitives to, grown as draws need them."""

    def __init__(self, shader, program, builtins):
        SemanticAnalyser(program, ShaderType.COMPUTE, builtins).analyse()
        gen = SPIRVGenerator(program, ShaderType.COMPUTE)
        self.code = gen.generate()
        self._module_dump = gen.m
        refl = gen.reflection
        self.uniforms = dict(refl["uniforms"])
        self.uniform_size = refl["uniform_size"]
        self.bindings = list(refl["bindings"])
        self.ubo_binding = next((b["binding"] for b in self.bindings if b["kind"] == "uniform_buffer"), None)
        self.uniform_bytes = bytearray(self.uniform_size)
        self.ctx = shader.renderer.ctx
        self.out = None
        self.draw = None
        self.capacity = 0
        self.id = next(_IDS)
        device = self.ctx.device
        self.module = vk.vkCreateShaderModule(device, vk.VkShaderModuleCreateInfo(
            codeSize=len(self.code), pCode=self.code), None)
        self.set_layout, self.pipeline_layout = _create_set_layout(device, self.bindings, vk.VK_SHADER_STAGE_COMPUTE_BIT)
        stage = vk.VkPipelineShaderStageCreateInfo(stage=vk.VK_SHADER_STAGE_COMPUTE_BIT, module=self.module,
                                                   pName="main")
        self.pipeline = vk.vkCreateComputePipelines(device, None, 1, [vk.VkComputePipelineCreateInfo(
            stage=stage, layout=self.pipeline_layout)], None)[0]

    def ensure_capacity(self, renderer, vertices: int, stride_floats: int):
        from FreeBodyEngine.graphics.vulkan.context import Buffer
        if self.draw is None:
            self.draw = Buffer(self.ctx, 16, vk.VK_BUFFER_USAGE_STORAGE_BUFFER_BIT
                               | vk.VK_BUFFER_USAGE_INDIRECT_BUFFER_BIT | vk.VK_BUFFER_USAGE_TRANSFER_DST_BIT)
        if vertices > self.capacity:
            if self.out is not None:
                renderer.defer_destroy(self.out)
            self.capacity = max(vertices, self.capacity * 2, 64)
            self.out = Buffer(self.ctx, self.capacity * stride_floats * 4,
                              vk.VK_BUFFER_USAGE_STORAGE_BUFFER_BIT | vk.VK_BUFFER_USAGE_VERTEX_BUFFER_BIT,
                              host_visible=False)

    def destroy(self):
        device = self.ctx.device
        vk.vkDestroyPipeline(device, self.pipeline, None)
        vk.vkDestroyPipelineLayout(device, self.pipeline_layout, None)
        vk.vkDestroyDescriptorSetLayout(device, self.set_layout, None)
        vk.vkDestroyShaderModule(device, self.module, None)
        for buf in (self.out, self.draw):
            if buf is not None:
                buf.destroy()


class VulkanShader(Shader):
    def __init__(self, vertex_source, fragment_source, injector=None, geometry_source=None):
        # Not Shader.__init__: that compiles each stage separately, and the
        # stages here have to agree on one uniform layout.
        self.data = {}
        self.renderer = get_service("renderer")
        self._compile(vertex_source, fragment_source, injector or Injector(), geometry_source)

    def _geometry_mode(self, vertex_tree, geometry_tree) -> str:
        """native when the device has geometry shaders, otherwise whichever
        emulation suits the shader (fbusl.geometry.choose_mode).
        fb.FORCE_GEOMETRY_MODE pins one, for comparing them."""
        from FreeBodyEngine import get_flag, FORCE_GEOMETRY_MODE
        forced = get_flag(FORCE_GEOMETRY_MODE, None)
        native = self.renderer.ctx.geometry_shader
        if forced in ("pull", "compute") or (forced == "native" and native):
            return forced
        if native:
            return "native"
        return fbusl_geometry.choose_mode(vertex_tree, geometry_tree, has_atomic_compute=True)

    def _compile(self, vertex_source, fragment_source, injector, geometry_source):
        self.vertex_source, self.fragment_source, self.geometry_source = (
            vertex_source, fragment_source, geometry_source)
        self.generator = SPIRVGenerator
        fragment_tree = _front(fragment_source, ShaderType.FRAGMENT, injector)

        self.topology = None  # None: the mesh's own
        self.geometry_mode = None
        self.emulation = None
        self.geometry_compute = None
        self.geometry_code = None
        self._geometry_module_dump = None
        remap_depth = True
        if geometry_source is None:
            vertex_tree = _front(vertex_source, ShaderType.VERTEX, injector)
            trees = [vertex_tree, fragment_tree]
        else:
            vertex_tree, vertex_builtins = _parse_only(vertex_source, ShaderType.VERTEX, injector)
            geometry_tree, geometry_builtins = _parse_only(geometry_source, ShaderType.GEOMETRY, injector)
            self.geometry_args = fbusl_geometry.geometry_args(geometry_tree)
            self.geometry_mode = mode = self._geometry_mode(vertex_tree, geometry_tree)
            if mode == "native":
                SemanticAnalyser(vertex_tree, ShaderType.VERTEX, vertex_builtins).analyse()
                SemanticAnalyser(geometry_tree, ShaderType.GEOMETRY, geometry_builtins).analyse()
                trees = [vertex_tree, fragment_tree, geometry_tree]
                self.topology = GEOMETRY_TOPOLOGIES[self.geometry_args["input"]]
                # The geometry stage, not the vertex stage, feeds the
                # rasterizer - so it's the one that remaps depth.
                remap_depth = False
            else:
                em = fbusl_geometry.emulate(vertex_tree, geometry_tree, mode)
                self.emulation = em
                self.topology = LIST_TOPOLOGIES[em.output_primitive]
                builtins = {**vertex_builtins, **geometry_builtins}
                if mode == "pull":
                    vertex_tree = em.program
                    SemanticAnalyser(vertex_tree, ShaderType.VERTEX, builtins).analyse()
                else:
                    self.geometry_compute = _GeometryCompute(self, em.program, builtins)
                    vertex_tree = em.passthrough
                    SemanticAnalyser(vertex_tree, ShaderType.VERTEX, vertex_builtins).analyse()
                trees = [vertex_tree, fragment_tree]

        layout = SPIRVGenerator.graphics_layout(trees)
        if self.geometry_mode == "native":
            geometry_gen = SPIRVGenerator(geometry_tree, ShaderType.GEOMETRY, layout)
            self.geometry_code = geometry_gen.generate()
            self._geometry_module_dump = geometry_gen.m
        vertex_gen = SPIRVGenerator(vertex_tree, ShaderType.VERTEX, layout, remap_depth=remap_depth)
        fragment_gen = SPIRVGenerator(fragment_tree, ShaderType.FRAGMENT, layout)
        self.vertex_code = vertex_gen.generate()
        self.fragment_code = fragment_gen.generate()
        self.fbusl_vertex_source, self.fbusl_fragment_source, self.fbusl_geometry_source = (
            self.vertex_code, self.fragment_code, self.geometry_code)
        self._vertex_module_dump = vertex_gen.m
        self._fragment_module_dump = fragment_gen.m

        refl = vertex_gen.reflection
        self.uniforms: dict[str, dict] = dict(refl["uniforms"])
        self.uniform_size = refl["uniform_size"]
        self.bindings = list(refl["bindings"])  # the same layout in every stage, by construction
        self.inputs = refl.get("inputs", [])  # [(name, type)] in location order
        self.output_count = len(fragment_gen.reflection.get("outputs", []))
        self.sampler_bindings = {b["name"]: b for b in self.bindings if b["kind"] == "sampler"}
        self.storage_bindings = {b["name"]: b["binding"] for b in self.bindings if b["kind"] == "storage_buffer"}
        self.ubo_binding = next((b["binding"] for b in self.bindings if b["kind"] == "uniform_buffer"), None)

        self.uniform_bytes = bytearray(self.uniform_size)
        self.textures: dict[str, object] = {}
        self.uniform_cache: dict[str, object] = {}
        self._warned: set = set()
        self.id = next(_IDS)
        self._create_vk_objects()

    def _create_vk_objects(self):
        device = self.renderer.ctx.device
        self.vertex_module = vk.vkCreateShaderModule(device, vk.VkShaderModuleCreateInfo(
            codeSize=len(self.vertex_code), pCode=self.vertex_code), None)
        self.fragment_module = vk.vkCreateShaderModule(device, vk.VkShaderModuleCreateInfo(
            codeSize=len(self.fragment_code), pCode=self.fragment_code), None)
        self.geometry_module = None
        stages = vk.VK_SHADER_STAGE_VERTEX_BIT | vk.VK_SHADER_STAGE_FRAGMENT_BIT
        if self.geometry_code is not None:
            self.geometry_module = vk.vkCreateShaderModule(device, vk.VkShaderModuleCreateInfo(
                codeSize=len(self.geometry_code), pCode=self.geometry_code), None)
            stages |= vk.VK_SHADER_STAGE_GEOMETRY_BIT
        self.set_layout, self.pipeline_layout = _create_set_layout(device, self.bindings, stages)

    def rebuild(self, injector=None, vertex_source=None, fragment_source=None, geometry_source=...):
        self.renderer.defer_destroy(_ShaderObjects(self))
        self._compile(self.vertex_source if vertex_source is None else vertex_source,
                      self.fragment_source if fragment_source is None else fragment_source,
                      injector or Injector(), self.geometry_source if geometry_source is ... else geometry_source)
        self.renderer.forget_pipelines(self)

    # -- uniforms ---------------------------------------------------------------------

    def _blocks(self):
        """Every uniform block this shader's values go to: the graphics one,
        and a compute-emulated geometry stage's own."""
        yield self.uniforms, self.uniform_bytes
        if self.geometry_compute is not None:
            yield self.geometry_compute.uniforms, self.geometry_compute.uniform_bytes

    def set_uniform(self, name: str, val):
        # Setting a uniform makes this the shader in use, as GL's
        # set_uniform does through glUseProgram - the PBR shadow pass sets
        # its matrices and draws without ever calling use().
        self.renderer.current_shader = self
        if name in self.sampler_bindings:
            if isinstance(val, Image):
                val = val.texture
            self.textures[name] = val
            self.uniform_cache[name] = val
            rect = f"_ENGINE_{name}_uv_rect"
            if rect in self.uniforms:
                if isinstance(val, TextureStack):
                    self._write(rect, [tuple(r) for r in val.uv_rects])
                elif isinstance(val, Texture):
                    self._write(rect, tuple(val.uv_rect))
            return
        if not any(name in uniforms for uniforms, _ in self._blocks()):
            if name not in self._warned:
                self._warned.add(name)
                fb_error(f"Uniform '{name}' not found in shader")
            return
        self.uniform_cache[name] = val
        self._write(name, val)

    def _write(self, name, val):
        for uniforms, data in self._blocks():
            info = uniforms.get(name)
            if info is None:
                continue
            try:
                packed = pack_uniform(info["type"], val)
            except (TypeError, ValueError) as e:
                fb_error(f'Cannot set uniform "{name}" of type "{info["type"]}" to {type(val).__name__}: {e}')
                return
            data[info["offset"]:info["offset"] + len(packed)] = packed

    def get_uniform(self, name: str):
        return self.uniforms.get(name) or self.sampler_bindings.get(name)

    def set_buffer(self, name: str, buffer):
        warning(f"Shader.set_buffer('{name}') isn't supported by the Vulkan backend.")

    def use(self):
        self._write("TIME", get_time())
        self.renderer.current_shader = self

    def destroy(self):
        self.renderer.defer_destroy(_ShaderObjects(self))


class _ShaderObjects:
    """A shader's Vulkan objects, destroyed together once no frame uses them."""

    def __init__(self, shader: VulkanShader):
        self.device = shader.renderer.ctx.device
        self.objects = (shader.vertex_module, shader.fragment_module, shader.set_layout, shader.pipeline_layout,
                        shader.geometry_module)
        self.compute = shader.geometry_compute

    def destroy(self):
        vertex, fragment, set_layout, pipeline_layout, geometry = self.objects
        vk.vkDestroyShaderModule(self.device, vertex, None)
        vk.vkDestroyShaderModule(self.device, fragment, None)
        if geometry is not None:
            vk.vkDestroyShaderModule(self.device, geometry, None)
        vk.vkDestroyPipelineLayout(self.device, pipeline_layout, None)
        vk.vkDestroyDescriptorSetLayout(self.device, set_layout, None)
        if self.compute is not None:
            self.compute.destroy()
