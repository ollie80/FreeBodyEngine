"""FBUSL -> SPIR-V, for the Vulkan backend.

Unlike the GLSL backends (gl33/gl44 generator.py), which print source for
a driver to compile, this emits a finished SPIR-V binary straight from
FBUSL's type-annotated AST - there's no glslang or shaderc in the
toolchain, and none needed. `generate()` returns the module as `bytes`.

Scope: compute, raytrace, vertex, geometry and fragment stages. The
graphics stages follow the GL backends' conventions exactly, so the
engine's shaders run unchanged:
stage inputs/outputs get locations in declaration order (that's how a
vertex shader's outputs meet a fragment shader's inputs, and how mesh
attributes meet vertex inputs), `texture` uniforms are combined image
samplers read through sample() with the engine's `_ENGINE_<name>_uv_rect`
remap, and VERTEX_POSITION is written in OpenGL remap - the depth is
remapped from GL's -1..1 to Vulkan's 0..1 on the way out of whichever
stage feeds the rasterizer (the geometry stage when there is one, so it
still reads GL clip space from the vertex stage). A geometry stage gets
each @input as an array with one element per input-primitive vertex and
input_position(i) for the vertex positions, as GL's gl_in[] gives it.
All stages of a shader share one uniform block and one set of sampler
bindings, computed across them by graphics_layout(), so a single
descriptor set layout serves the pipeline.

A raytrace stage gets real hardware ray tracing: `trace_ray()` and
`trace_shadow()` lower to SPV_KHR_ray_query against a top-level
acceleration structure, rather than the software BVH walk the GL backends
emulate. That's FBUSL's own model for ray tracing (an inline query from a
compute-style kernel - see fbusl/builtins.py), and it's exactly what
VK_KHR_ray_query provides.

Resource interface (all descriptor set 0), recorded in `self.reflection`
for VulkanComputeShader to bind by name:

    binding 0..   the uniform block - every @uniform (plus TIME and
                  DISPATCH_SIZE, if used), std140, one buffer. Offsets are
                  in reflection["uniforms"].
    then          one storage image per @output, in declaration order,
                  written at GLOBAL_INVOCATION_ID.xy like GL44 does.
    then          one readable storage image per `image`-typed @uniform
                  (rgba32f), read with image_load(img, coord).
    then          one storage buffer per `buffer` field ("Block.field") -
                  one per field, not one per block, because only a block's
                  last member can be a runtime-sized array.
    last          the acceleration structure ("scene"), if trace_ray or
                  trace_shadow is used.
"""
import fbusl
from fbusl.node import (
    ArrayAccess, BinOp, BufferBlock, Define, FuncCall, FunctionDef, Identifier, IfStatement,
    InlineIf, Input, Literal, MemberAccess, Output, Return, Setter, SharedDecl, StructDef,
    UnaryOp, Uniform, VarDecl, WhileStatement,
)
from FreeBodyEngine.graphics.texture import MAX_TEXTURE_STACK_SIZE
from FreeBodyEngine.graphics.vulkan import spirv as sv
from FreeBodyEngine.graphics.vulkan.spirv import Instruction

VECTORS = {
    "vec2": ("float", 2), "vec3": ("float", 3), "vec4": ("float", 4),
    "ivec2": ("int", 2), "ivec3": ("int", 3), "uvec3": ("uint", 3),
}
MATRICES = {"mat2": 2, "mat3": 3, "mat4": 4}
SWIZZLE = {"x": 0, "y": 1, "z": 2, "w": 3}

# Image format for each @output type - GL44's table (gl44/generator.py),
# kept identical so the same kernel writes the same thing on both.
IMAGE_FORMAT = {"float": "r32f", "int": "r32i", "vec2": "rg32f", "vec4": "rgba32f"}

# trace_ray/trace_shadow ray flags.
RAY_FLAG_OPAQUE = 0x1
RAY_FLAG_TERMINATE_ON_FIRST_HIT = 0x4

# Vertices per input primitive, for a geometry stage's input arrays.
GEOMETRY_INPUT_VERTICES = {"points": 1, "lines": 2, "lines_adjacency": 4, "triangles": 3,
                           "triangles_adjacency": 6}


def _walk(node):
    """Every AST node under `node` (a node or a list of them), including
    the ones FBUSL doesn't keep in `children` - conditions, setter
    targets, return values."""
    if node is None:
        return
    if isinstance(node, list):
        for item in node:
            yield from _walk(item)
        return
    if not hasattr(node, "children"):
        return
    yield node
    for child in node.children:
        yield from _walk(child)
    if isinstance(node, FunctionDef):
        yield from _walk(node.body)
    if isinstance(node, (IfStatement, WhileStatement)):
        yield from _walk(node.condition)
    if isinstance(node, Setter):
        yield from _walk(node.node)
    if isinstance(node, Return):
        yield from _walk(node.expression)


def _norm(raw):
    """A declared type as the generator tracks it: a plain name, or
    ("array", element, length)."""
    if raw is None:
        return "void"
    if isinstance(raw, tuple):
        return raw
    if isinstance(raw, dict):
        if raw.get("name") == "array":
            data = raw["data"]
            return ("array", _norm(data["base_type"]), int(data["length"]))
        return raw.get("name", "unknown")
    return raw


class _Function:
    """Codegen state for the function currently being emitted."""

    def __init__(self, return_type):
        self.return_type = return_type
        self.vars: dict[str, tuple[int, object]] = {}  # name -> (pointer id, type)
        self.var_decls: list[Instruction] = []  # OpVariables, all hoisted to the entry block
        self.body: list[Instruction] = []
        self.terminated = False
        self.raw_types: dict[str, object] = {}  # declared types from the semantic scope


class SPIRVGenerator(fbusl.generator.Generator):
    CAPABILITIES = frozenset({
        "compute.dispatch",
        "compute.invocation_id",
        "compute.buffer_read",
        "compute.buffer_write",
        "compute.image_write",
        "compute.image_read",
        "compute.shared_memory",
        "compute.barrier",
        "compute.atomics",
        "raytrace.query_hardware",
        "geometry.native",
    })

    def __init__(self, tree, shader_type=fbusl.ShaderType.COMPUTE, layout: dict | None = None,
                 remap_depth: bool = True):
        """`layout` (graphics stages only): the uniform/sampler layout
        shared with the shader's other stages - see graphics_layout().
        `remap_depth`: whether VERTEX_POSITION gets Vulkan's depth range
        here - false for a vertex stage feeding a geometry stage."""
        super().__init__(tree, shader_type)
        self.layout = layout
        self.remap_depth = remap_depth
        self.input_positions = None  # geometry stage: gl_in[].gl_Position
        self.geometry_args = None
        self.stage_inputs: dict[str, tuple[int, object]] = {}
        self.stage_outputs: dict[str, tuple[int, object]] = {}
        self.samplers: dict[str, dict] = {}
        self.position_var = None
        self.m = sv.Module((1, 5))
        self.reflection: dict = {"bindings": [], "uniforms": {}, "uniform_size": 0, "local_size": (1, 1, 1)}
        self.structs: dict[str, list[tuple[str, object]]] = {}
        self.struct_ids: dict[str, int] = {}
        self.array_types: dict[tuple, int] = {}
        self.functions: dict[str, dict] = {}
        self.uniform_members: dict[str, tuple[int, object]] = {}  # name -> (member index, type)
        self.ubo_var = None
        self.ubo_member_types: list[int] = []
        self.outputs: dict[str, dict] = {}
        self.input_images: dict[str, dict] = {}
        self.buffers: dict[tuple[str, str], dict] = {}
        self.block_names: set[str] = set()
        self.shared: dict[str, tuple[int, object]] = {}
        self.privates: dict[str, tuple[int, object]] = {}
        self.private_inits: list[VarDecl] = []
        self.defines: dict[str, object] = {}
        self.builtin_vars: dict[str, int] = {}
        self.interface: list[int] = []
        self.tlas_var = None
        self.helpers: dict[str, int] = {}
        self.ctx: _Function | None = None
        self.next_binding = 0

    # == driver ================================================================

    def generate(self) -> bytes:
        if self.shader_type in (fbusl.ShaderType.VERTEX, fbusl.ShaderType.FRAGMENT, fbusl.ShaderType.GEOMETRY):
            return self._generate_graphics()
        if self.shader_type not in (fbusl.ShaderType.COMPUTE, fbusl.ShaderType.RAYTRACE):
            fbusl.fbusl_error(
                f"The SPIR-V backend generates compute, raytrace, vertex, geometry and fragment stages, not "
                f"{self.shader_type}.")

        entry = next((n for n in self.tree if isinstance(n, FunctionDef) and n.stage in ("compute", "raytrace")), None)
        if entry is None:
            fbusl.fbusl_error("A compute/raytrace shader needs a @compute or @raytrace entry function.")
        if entry.params or _norm(entry.type) != "void":
            fbusl.fbusl_error(f"Entry function '{entry.name}' must take no parameters and return nothing.", entry.pos)
        self.entry = entry
        args = entry.stage_args
        self.local_size = (int(args.get("local_size_x", 1)), int(args.get("local_size_y", 1)), int(args.get("local_size_z", 1)))
        self.reflection["local_size"] = self.local_size
        self.ray_tmin = float(args.get("ray_tmin", 1e-4))

        m = self.m
        m.capability(sv.CAP_SHADER)
        if self.shader_type == fbusl.ShaderType.RAYTRACE:
            m.capability(sv.CAP_RAY_QUERY)
            m.extension("SPV_KHR_ray_query")
        m.emit("memory_model", "MemoryModel", 0, 1)  # Logical, GLSL450

        self._declare_structs()
        self._declare_resources()
        self._declare_signatures()

        for node in self.tree:
            if isinstance(node, FunctionDef):
                self._function(node)

        for node in self.tree:
            if isinstance(node, (Input,)):
                fbusl.fbusl_error(f"@input '{node.name}' has no meaning in a compute/raytrace stage.", node.pos)

        main_id = self.functions[entry.name]["id"]
        m.emit("entry_points", "EntryPoint", sv.EXEC_GLCOMPUTE, main_id, "main", *self.interface)
        m.emit("execution_modes", "ExecutionMode", main_id, sv.MODE_LOCAL_SIZE, *self.local_size)
        return m.encode()

    def _generate_graphics(self) -> bytes:
        geometry = self.shader_type == fbusl.ShaderType.GEOMETRY
        if geometry:
            entry = next((n for n in self.tree if isinstance(n, FunctionDef) and n.stage == "geometry"), None)
            if entry is None:
                fbusl.fbusl_error("A geometry shader needs a @geometry(input=..., output=..., max_vertices=...) "
                                  "entry function.")
            self.geometry_args = entry.stage_args
        else:
            entry = next((n for n in self.tree if isinstance(n, FunctionDef) and n.name == "main"), None)
            if entry is None:
                fbusl.fbusl_error(f"A {self.shader_type} shader needs a `def main()`.")
        self.entry = entry
        self.local_size = (1, 1, 1)
        self.ray_tmin = 1e-4

        m = self.m
        m.capability(sv.CAP_SHADER)
        if geometry:
            m.capability(sv.CAP_GEOMETRY)
        m.emit("memory_model", "MemoryModel", 0, 1)  # Logical, GLSL450
        self._declare_structs()
        self._declare_graphics_resources()
        self._declare_globals()
        self._declare_signatures()
        for node in self.tree:
            if isinstance(node, FunctionDef):
                self._function(node)

        main_id = self.functions[entry.name]["id"]
        vertex = self.shader_type == fbusl.ShaderType.VERTEX
        model = sv.EXEC_VERTEX if vertex else sv.EXEC_GEOMETRY if geometry else sv.EXEC_FRAGMENT
        m.emit("entry_points", "EntryPoint", model, main_id, "main", *self.interface)
        if geometry:
            args = self.geometry_args
            m.emit("execution_modes", "ExecutionMode", main_id, sv.MODE_GEOMETRY_INPUT[args["input"]])
            m.emit("execution_modes", "ExecutionMode", main_id, sv.MODE_INVOCATIONS, 1)
            m.emit("execution_modes", "ExecutionMode", main_id, sv.MODE_GEOMETRY_OUTPUT[args["output"]])
            m.emit("execution_modes", "ExecutionMode", main_id, sv.MODE_OUTPUT_VERTICES,
                   int(args["max_vertices"]))
        elif not vertex:
            # Fragment coordinates measured from memory row 0 - the same row
            # GL calls the bottom, since nothing here flips the viewport.
            m.emit("execution_modes", "ExecutionMode", main_id, sv.MODE_ORIGIN_UPPER_LEFT)
        return m.encode()

    @staticmethod
    def graphics_layout(trees) -> dict:
        """The uniform block and sampler bindings for a vertex+fragment pair,
        shared by both stages: every non-texture @uniform from either (first
        declaration wins), a `_ENGINE_<name>_uv_rect` entry per texture -
        the sub-rect sample() remaps into, exactly as the GL backends do -
        and TIME if either stage reads it."""
        uniforms, samplers, seen = [], [], set()

        def add(name, t):
            if name not in seen:
                seen.add(name)
                uniforms.append((name, t))

        uses_time = False
        for tree in trees:
            for node in tree:
                if isinstance(node, Uniform):
                    t = _norm(node.type)
                    if t in ("texture", "textureStack"):
                        if node.name not in {s for s, _ in samplers}:
                            samplers.append((node.name, t))
                            add(f"_ENGINE_{node.name}_uv_rect",
                                "vec4" if t == "texture" else ("array", "vec4", MAX_TEXTURE_STACK_SIZE))
                    elif t != "image":
                        add(node.name, t)
            uses_time = uses_time or any(isinstance(n, Identifier) and n.value == "TIME" for n in _walk(tree))
        if uses_time:
            add("TIME", "float")
        return {"uniforms": uniforms, "samplers": samplers}

    # == declarations ==========================================================

    def _declare_structs(self):
        # Built-in structs first so user structs can contain them.
        if self.shader_type == fbusl.ShaderType.RAYTRACE:
            from fbusl.builtins import TYPES
            for name in ("Ray", "RayHit"):
                self.structs[name] = list(TYPES[name]["fields"].items())
        for node in self.tree:
            if isinstance(node, StructDef):
                self.structs[node.name] = [(f.name, _norm(f.type)) for f in node.fields]
        for name, fields in self.structs.items():
            struct_id = self.m.type_struct([self.type_id(t) for _, t in fields])
            self.struct_ids[name] = struct_id
            self.m.name(struct_id, name)
            for i, (field_name, _) in enumerate(fields):
                self.m.member_name(struct_id, i, field_name)

    def _binding(self, name: str, kind: str, **extra) -> int:
        binding = self.next_binding
        self.next_binding += 1
        self.reflection["bindings"].append({"name": name, "binding": binding, "kind": kind, **extra})
        return binding

    def _resource_var(self, pointer_type: int, storage: int, binding: int, name: str) -> int:
        var = self.m.global_variable(pointer_type, storage)
        self.m.decorate(var, sv.DEC_DESCRIPTOR_SET, 0)
        self.m.decorate(var, sv.DEC_BINDING, binding)
        self.m.name(var, name)
        self.interface.append(var)
        return var

    def _declare_resources(self):
        m = self.m
        # `image` uniforms are resources of their own (see the module
        # docstring), not members of the uniform block.
        uniforms = [n for n in self.tree if isinstance(n, Uniform) and _norm(n.type) != "image"]
        uniform_list = [(u.name, _norm(u.type), u.pos) for u in uniforms]
        # Engine-set builtins live in the same block, filled in by
        # VulkanComputeShader.dispatch() - DISPATCH_SIZE as a uniform rather
        # than derived from gl_NumWorkGroups, so it's the size the caller
        # asked for, not that size rounded up to whole work groups (the
        # same value GL44 passes).
        for builtin, builtin_type in (("TIME", "float"), ("DISPATCH_SIZE", "ivec3")):
            if self._uses_identifier(builtin) and not any(name == builtin for name, _, _ in uniform_list):
                uniform_list.append((builtin, builtin_type, None))

        self._declare_uniform_block(uniform_list)
        self._declare_compute_resources()

    def _declare_uniform_block(self, uniform_list):
        m = self.m
        if uniform_list:
            member_types, offsets, offset = [], [], 0
            for index, (name, t, pos) in enumerate(uniform_list):
                align, size = self._std140(t, pos)
                offset = -(-offset // align) * align
                offsets.append(offset)
                member_types.append(self._layout_type(t, std140=True))
                self.uniform_members[name] = (index, t)
                self.reflection["uniforms"][name] = {"offset": offset, "type": t, "size": size}
                offset += size
            self.reflection["uniform_size"] = -(-offset // 16) * 16
            block = m.type_struct(member_types)
            m.decorate(block, sv.DEC_BLOCK)
            m.name(block, "_Uniforms")
            for index, ((name, t, _), off) in enumerate(zip(uniform_list, offsets)):
                m.member_name(block, index, name)
                m.member_decorate(block, index, sv.DEC_OFFSET, off)
                self._matrix_decorations(block, index, t)
            self.ubo_member_types = member_types
            binding = self._binding("uniforms", "uniform_buffer", size=self.reflection["uniform_size"])
            self.ubo_var = self._resource_var(m.type_pointer(sv.STORAGE_UNIFORM, block), sv.STORAGE_UNIFORM, binding, "uniforms")

    def _declare_compute_resources(self):
        m = self.m
        for node in self.tree:
            if isinstance(node, Output):
                t = _norm(node.type)
                fmt = IMAGE_FORMAT.get(t)
                if fmt is None:
                    fbusl.fbusl_error(
                        f"@output '{node.name}: {t}' - a compute/raytrace output must be float, int, vec2 or vec4.",
                        node.pos)
                sampled = m.type_int() if t == "int" else m.type_float()
                image = m.type_image_storage_2d(sampled, fmt)
                binding = self._binding(node.name, "storage_image", format=fmt, type=t)
                var = self._resource_var(m.type_pointer(sv.STORAGE_UNIFORM_CONSTANT, image),
                                         sv.STORAGE_UNIFORM_CONSTANT, binding, node.name)
                self.outputs[node.name] = {"var": var, "image": image, "type": t}

        for node in self.tree:
            if isinstance(node, Uniform) and _norm(node.type) == "image":
                image = m.type_image_storage_2d(m.type_float(), "rgba32f")
                binding = self._binding(node.name, "storage_image", format="rgba32f", type="vec4", access="read")
                var = self._resource_var(m.type_pointer(sv.STORAGE_UNIFORM_CONSTANT, image),
                                         sv.STORAGE_UNIFORM_CONSTANT, binding, node.name)
                m.decorate(var, sv.DEC_NON_WRITABLE)
                self.input_images[node.name] = {"var": var, "image": image}

        self._declare_buffers()

        if self.shader_type == fbusl.ShaderType.RAYTRACE and (
                self._uses_call("trace_ray") or self._uses_call("trace_shadow")):
            accel = m.type_acceleration_structure()
            binding = self._binding("scene", "acceleration_structure")
            self.tlas_var = self._resource_var(m.type_pointer(sv.STORAGE_UNIFORM_CONSTANT, accel),
                                               sv.STORAGE_UNIFORM_CONSTANT, binding, "scene")
        self._declare_globals()

    def _declare_buffers(self):
        """One storage buffer per `buffer` field - in any stage (a graphics
        stage reads them too, e.g. emulated geometry shaders pulling mesh
        data)."""
        m = self.m
        for node in self.tree:
            if isinstance(node, BufferBlock):
                self.block_names.add(node.name)
                for field in node.fields:
                    raw = _norm(field.type)
                    element = raw[1] if isinstance(raw, tuple) else raw
                    if element in self.structs or element == "bool":
                        fbusl.fbusl_error(
                            f"buffer '{node.name}.{field.name}': {element} elements aren't supported "
                            f"by the SPIR-V backend - use scalar, vector or matrix fields.", node.pos)
                    stride = self._std430_stride(element, node.pos)
                    runtime = m.type_runtime_array(self.type_id(element))
                    m.decorate(runtime, sv.DEC_ARRAY_STRIDE, stride)
                    block = m.type_struct([runtime])
                    m.decorate(block, sv.DEC_BLOCK)
                    m.member_decorate(block, 0, sv.DEC_OFFSET, 0)
                    self._matrix_decorations(block, 0, element)
                    if node.qualifier == "readonly":
                        m.member_decorate(block, 0, sv.DEC_NON_WRITABLE)
                    elif node.qualifier == "writeonly":
                        m.member_decorate(block, 0, sv.DEC_NON_READABLE)
                    name = f"{node.name}.{field.name}"
                    m.name(block, f"_Buffer_{node.name}_{field.name}")
                    binding = self._binding(name, "storage_buffer", element=element, stride=stride,
                                            access=node.qualifier)
                    var = self._resource_var(m.type_pointer(sv.STORAGE_STORAGE_BUFFER, block),
                                             sv.STORAGE_STORAGE_BUFFER, binding, name)
                    self.buffers[(node.name, field.name)] = {"var": var, "element": element,
                                                             "access": node.qualifier}

    def _declare_graphics_resources(self):
        m = self.m
        layout = self.layout or self.graphics_layout([self.tree])
        self._declare_uniform_block([(name, t, None) for name, t in layout["uniforms"]])

        for name, kind in layout["samplers"]:
            image = m.type_image_sampled_2d(m.type_float(), arrayed=(kind == "textureStack"))
            sampled = m.type_sampled_image(image)
            binding = self._binding(name, "sampler", texture_kind=kind)
            var = self._resource_var(m.type_pointer(sv.STORAGE_UNIFORM_CONSTANT, sampled),
                                     sv.STORAGE_UNIFORM_CONSTANT, binding, name)
            self.samplers[name] = {"var": var, "type": sampled, "kind": kind}

        self._declare_buffers()

        fragment = self.shader_type == fbusl.ShaderType.FRAGMENT
        geometry = self.shader_type == fbusl.ShaderType.GEOMETRY
        per_primitive = GEOMETRY_INPUT_VERTICES[self.geometry_args["input"]] if geometry else None
        inputs = [n for n in self.tree if isinstance(n, Input)]
        for location, node in enumerate(inputs):
            t = _norm(node.type)
            if geometry:
                t = ("array", t, per_primitive)  # one value per input-primitive vertex
            var = m.global_variable(m.type_pointer(sv.STORAGE_INPUT, self.type_id(t)), sv.STORAGE_INPUT)
            m.decorate(var, sv.DEC_LOCATION, location)
            scalar = VECTORS[t][0] if t in VECTORS else t
            if fragment and scalar in ("int", "uint"):
                m.decorate(var, sv.DEC_FLAT)  # integers can't be interpolated
            m.name(var, node.name)
            self.interface.append(var)
            self.stage_inputs[node.name] = (var, t)
        self.reflection["inputs"] = [(n.name, _norm(n.type)) for n in inputs]

        outputs = [n for n in self.tree if isinstance(n, Output)]
        for location, node in enumerate(outputs):
            t = _norm(node.type)
            var = m.global_variable(m.type_pointer(sv.STORAGE_OUTPUT, self.type_id(t)), sv.STORAGE_OUTPUT)
            m.decorate(var, sv.DEC_LOCATION, location)
            m.name(var, node.name)
            self.interface.append(var)
            self.stage_outputs[node.name] = (var, t)
        self.reflection["outputs"] = [(n.name, _norm(n.type)) for n in outputs]

        if self.shader_type in (fbusl.ShaderType.VERTEX, fbusl.ShaderType.GEOMETRY):
            var = m.global_variable(m.type_pointer(sv.STORAGE_OUTPUT, self.type_id("vec4")), sv.STORAGE_OUTPUT)
            m.decorate(var, sv.DEC_BUILTIN, sv.BUILTIN_POSITION)
            m.name(var, "gl_Position")
            self.interface.append(var)
            self.position_var = var
        if geometry:
            t = ("array", "vec4", per_primitive)
            var = m.global_variable(m.type_pointer(sv.STORAGE_INPUT, self.type_id(t)), sv.STORAGE_INPUT)
            m.decorate(var, sv.DEC_BUILTIN, sv.BUILTIN_POSITION)
            m.name(var, "gl_in_Position")
            self.interface.append(var)
            self.input_positions = var

    def _declare_globals(self):
        m = self.m
        for node in self.tree:
            if isinstance(node, SharedDecl):
                t = _norm(node.type)
                var = m.global_variable(m.type_pointer(sv.STORAGE_WORKGROUP, self.type_id(t)), sv.STORAGE_WORKGROUP)
                m.name(var, node.name)
                self.interface.append(var)
                self.shared[node.name] = (var, t)
            elif isinstance(node, VarDecl):
                t = self._declared_global_type(node)
                var = m.global_variable(m.type_pointer(sv.STORAGE_PRIVATE, self.type_id(t)), sv.STORAGE_PRIVATE)
                m.name(var, node.name)
                self.interface.append(var)
                self.privates[node.name] = (var, t)
                if node.value is not None:
                    self.private_inits.append(node)
            elif isinstance(node, Define):
                self.defines[node.name] = node.value

    def _declared_global_type(self, node: VarDecl):
        return _norm(node.type)

    def _declare_signatures(self):
        m = self.m
        for node in self.tree:
            if not isinstance(node, FunctionDef):
                continue
            ret = _norm(node.type)
            params = []
            param_type_ids = []
            for p in node.params:
                t = _norm(p.type)
                by_ref = p.qualifier in ("out", "inout")
                params.append((p.name, t, p.qualifier))
                tid = self.type_id(t)
                param_type_ids.append(m.type_pointer(sv.STORAGE_FUNCTION, tid) if by_ref else tid)
            fn_type = m.type_function(self.type_id(ret), param_type_ids)
            fn_id = m.id()
            m.name(fn_id, node.name)
            self.functions[node.name] = {"id": fn_id, "ret": ret, "params": params,
                                         "param_type_ids": param_type_ids, "type": fn_type}

    # == types and layout ======================================================

    def type_id(self, t) -> int:
        m = self.m
        if isinstance(t, tuple):
            key = t
            if key not in self.array_types:
                self.array_types[key] = m.type_array(self.type_id(t[1]), t[2])
            return self.array_types[key]
        if t == "void":
            return m.type_void()
        if t == "bool":
            return m.type_bool()
        if t == "int":
            return m.type_int()
        if t == "uint":
            return m.type_int(signed=False)
        if t == "float":
            return m.type_float()
        if t in VECTORS:
            scalar, count = VECTORS[t]
            return m.type_vector(self.type_id(scalar), count)
        if t in MATRICES:
            n = MATRICES[t]
            return m.type_matrix(self.type_id(f"vec{n}"), n)
        if t in self.struct_ids:
            return self.struct_ids[t]
        fbusl.fbusl_error(f"The SPIR-V backend doesn't support the type '{t}' here.")

    def _layout_type(self, t, std140: bool) -> int:
        """Type id for a member of an explicitly laid-out block. Arrays get
        their own decorated declaration, separate from the undecorated one
        local variables use."""
        if isinstance(t, tuple):
            element = t[1]
            align, size = self._std140(element, None)
            stride = -(-size // 16) * 16 if std140 else size
            array = self.m.type_array(self.type_id(element), t[2])
            self.m.decorate(array, sv.DEC_ARRAY_STRIDE, stride)
            return array
        if t == "bool":
            return self.type_id("int")  # bool has no layout in a uniform block
        return self.type_id(t)

    def _matrix_decorations(self, struct_id, member, t):
        element = t[1] if isinstance(t, tuple) else t
        if element in MATRICES:
            self.m.member_decorate(struct_id, member, sv.DEC_COL_MAJOR)
            self.m.member_decorate(struct_id, member, sv.DEC_MATRIX_STRIDE, 16)

    def _std140(self, t, pos):
        """(alignment, size) under std140."""
        if isinstance(t, tuple):
            _, size = self._std140(t[1], pos)
            stride = -(-size // 16) * 16
            return 16, stride * t[2]
        if t in ("float", "int", "bool"):
            return 4, 4  # bool uniforms are stored as int - see _layout_type
        if t in ("vec2", "ivec2"):
            return 8, 8
        if t in ("vec3", "ivec3"):
            return 16, 12
        if t == "vec4":
            return 16, 16
        if t in MATRICES:
            return 16, 16 * MATRICES[t]
        fbusl.fbusl_error(f"@uniform of type '{t}' isn't supported by the SPIR-V backend.", pos or fbusl.Position())

    def _std430_stride(self, t, pos) -> int:
        strides = {"float": 4, "int": 4, "vec2": 8, "ivec2": 8, "vec3": 16, "ivec3": 16, "vec4": 16,
                   "mat2": 16, "mat3": 48, "mat4": 64}
        if t not in strides:
            fbusl.fbusl_error(f"buffer element type '{t}' isn't supported by the SPIR-V backend.", pos)
        return strides[t]

    # == AST queries ===========================================================

    def _walk(self, node):
        if node is None:
            return
        if isinstance(node, list):
            for item in node:
                yield from self._walk(item)
            return
        if not hasattr(node, "children"):
            return
        yield node
        for child in node.children:
            yield from self._walk(child)
        if isinstance(node, FunctionDef):
            yield from self._walk(node.body)
        if isinstance(node, (IfStatement, WhileStatement)):
            yield from self._walk(node.condition)
        if isinstance(node, Setter):
            yield from self._walk(node.node)
        if isinstance(node, Return):
            yield from self._walk(node.expression)

    def _uses_identifier(self, name) -> bool:
        return any(isinstance(n, Identifier) and n.value == name for n in self._walk(self.tree))

    def _uses_call(self, name) -> bool:
        return any(isinstance(n, FuncCall) and n.name == name for n in self._walk(self.tree))

    # == emission helpers ======================================================

    def emit(self, op, *operands):
        self.ctx.body.append(Instruction(op, list(operands)))

    def op(self, result_type: int, op: str, *operands) -> int:
        result = self.m.id()
        self.ctx.body.append(Instruction(op, [result_type, result, *operands]))
        return result

    def label(self, label_id: int):
        self.ctx.body.append(Instruction("Label", [label_id]))
        self.ctx.terminated = False

    def terminate(self, op, *operands):
        self.emit(op, *operands)
        self.ctx.terminated = True

    def ext(self, t, name: str, *args) -> int:
        return self.op(self.type_id(t), "ExtInst", self.m.glsl_std(), sv.GLSL[name], *args)

    def local_var(self, name: str, t, label: str | None = None) -> int:
        var = self.m.id()
        pointer = self.m.type_pointer(sv.STORAGE_FUNCTION, self.type_id(t))
        self.ctx.var_decls.append(Instruction("Variable", [pointer, var, sv.STORAGE_FUNCTION]))
        if label:
            self.m.name(var, label)
        return var

    def splat(self, value: int, vector_type) -> int:
        _, count = VECTORS[vector_type]
        return self.op(self.type_id(vector_type), "CompositeConstruct", *([value] * count))

    def builtin_input(self, name: str, builtin: int) -> int:
        var = self.builtin_vars.get(name)
        if var is None:
            m = self.m
            var = m.global_variable(m.type_pointer(sv.STORAGE_INPUT, self.type_id("uvec3")), sv.STORAGE_INPUT)
            m.decorate(var, sv.DEC_BUILTIN, builtin)
            m.name(var, name)
            self.interface.append(var)
            self.builtin_vars[name] = var
        return var

    def load_builtin_ivec3(self, name: str, builtin: int) -> int:
        var = self.builtin_input(name, builtin)
        u = self.op(self.type_id("uvec3"), "Load", var)
        return self.op(self.type_id("ivec3"), "Bitcast", u)

    # == functions =============================================================

    def _function(self, node: FunctionDef):
        sig = self.functions[node.name]
        ctx = _Function(sig["ret"])
        self.ctx = ctx
        if node.scope is not None:
            ctx.raw_types = {k: v["type"] for k, v in node.scope.variables.items()}

        header = [Instruction("Function", [self.type_id(sig["ret"]), sig["id"], 0, sig["type"]])]
        param_ids = []
        for (name, t, qualifier), type_id in zip(sig["params"], sig["param_type_ids"]):
            pid = self.m.id()
            header.append(Instruction("FunctionParameter", [type_id, pid]))
            param_ids.append(pid)
        entry_label = self.m.id()

        for (name, t, qualifier), pid in zip(sig["params"], param_ids):
            if qualifier in ("out", "inout"):
                ctx.vars[name] = (pid, t)
            else:
                var = self.local_var(name, t, name)
                self.emit("Store", var, pid)
                ctx.vars[name] = (var, t)

        if node is self.entry:
            for decl in self.private_inits:
                var, t = self.privates[decl.name]
                self.emit("Store", var, self.expr(decl.value)[0])

        self.block(node.body)

        if not ctx.terminated:
            if sig["ret"] == "void":
                self.terminate("Return")
            else:
                self.terminate("ReturnValue", self.m.undef(self.type_id(sig["ret"])))

        out = self.m.sections["functions"]
        out.extend(header)
        out.append(Instruction("Label", [entry_label]))
        out.extend(ctx.var_decls)
        out.extend(ctx.body)
        out.append(Instruction("FunctionEnd", []))
        self.ctx = None

        # Ray-query helpers are emitted after the function that first needs
        # them, each into a function context of its own.
        for helper in list(getattr(self, "_pending_helpers", [])):
            self._pending_helpers.remove(helper)
            helper()

    # == statements ============================================================

    def block(self, statements):
        for statement in statements:
            if self.ctx.terminated:
                break  # unreachable code after a return
            self.statement(statement)

    def statement(self, node):
        if isinstance(node, VarDecl):
            t = _norm(self.ctx.raw_types.get(node.name, node.type))
            var = self.local_var(node.name, t, node.name)
            self.ctx.vars[node.name] = (var, t)
            if node.value is not None:
                value, _ = self.expr(node.value)
                self.emit("Store", var, value)
        elif isinstance(node, Setter):
            self.assign(node)
        elif isinstance(node, IfStatement):
            self.if_statement(node)
        elif isinstance(node, WhileStatement):
            self.while_statement(node)
        elif isinstance(node, Return):
            if node.expression is None:
                self.terminate("Return")
            else:
                value, _ = self.expr(node.expression)
                self.terminate("ReturnValue", value)
        elif isinstance(node, (StructDef, BufferBlock, Uniform, Output, Input, SharedDecl, Define)):
            fbusl.fbusl_error("Declarations of this kind belong at the top level of a shader.", node.pos)
        else:
            self.expr(node)

    def if_statement(self, node: IfStatement):
        cond, _ = self.expr(node.condition)
        then_label, merge = self.m.id(), self.m.id()
        else_label = self.m.id() if node.next_statement is not None else merge
        self.emit("SelectionMerge", merge, 0)
        self.terminate("BranchConditional", cond, then_label, else_label)

        self.label(then_label)
        self.block(node.body)
        if not self.ctx.terminated:
            self.terminate("Branch", merge)

        nxt = node.next_statement
        if nxt is not None:
            self.label(else_label)
            if nxt.if_type == "else":
                self.block(nxt.body)
            else:
                self.if_statement(nxt)  # an elif is an if nested in the else
            if not self.ctx.terminated:
                self.terminate("Branch", merge)

        self.label(merge)

    def while_statement(self, node: WhileStatement):
        m = self.m
        header, cond_label, body_label, continue_label, merge = (m.id() for _ in range(5))
        self.terminate("Branch", header)
        self.label(header)
        self.emit("LoopMerge", merge, continue_label, 0)
        self.terminate("Branch", cond_label)
        self.label(cond_label)
        cond, _ = self.expr(node.condition)
        self.terminate("BranchConditional", cond, body_label, merge)
        self.label(body_label)
        self.block(node.body)
        if not self.ctx.terminated:
            self.terminate("Branch", continue_label)
        self.label(continue_label)
        self.terminate("Branch", header)
        self.label(merge)

    def assign(self, node: Setter):
        target = node.node
        if isinstance(target, Identifier) and target.value in self.outputs:
            self.image_write(target.value, node.value)
            return
        if (isinstance(target, Identifier) and target.value == "VERTEX_POSITION" and self.position_var is not None
                and self.remap_depth):
            # Engine shaders write OpenGL clip space; Vulkan's depth range is
            # 0..w rather than -w..w, so z becomes (z + w) / 2 on the way out.
            value, _ = self.expr(node.value)
            f = self.type_id("float")
            z = self.op(f, "CompositeExtract", value, 2)
            w = self.op(f, "CompositeExtract", value, 3)
            z = self.op(f, "FMul", self.op(f, "FAdd", z, w), self.m.constant_float(0.5))
            self.emit("Store", self.position_var, self.op(self.type_id("vec4"), "CompositeInsert", z, value, 2))
            return

        if isinstance(target, MemberAccess):
            base_type = self.type_of(target.base)
            if base_type in VECTORS and len(target.member) > 1:
                # Multi-component swizzle write: read, shuffle the new
                # components in, write back.
                ptr, t = self.ref(target.base)
                old = self.op(self.type_id(t), "Load", ptr)
                value, _ = self.expr(node.value)
                count = VECTORS[t][1]
                mapping = list(range(count))
                for i, ch in enumerate(target.member):
                    mapping[SWIZZLE[ch]] = count + i
                new = self.op(self.type_id(t), "VectorShuffle", old, value, *mapping)
                self.emit("Store", ptr, new)
                return

        ptr, t = self.ref(target)
        value, _ = self.expr(node.value)
        self.emit("Store", ptr, value)

    def image_write(self, name: str, value_node):
        out = self.outputs[name]
        image = self.op(out["image"], "Load", out["var"])
        gid = self.load_builtin_ivec3("gl_GlobalInvocationID", sv.BUILTIN_GLOBAL_INVOCATION_ID)
        coord = self.op(self.type_id("ivec2"), "VectorShuffle", gid, gid, 0, 1)
        value, t = self.expr(value_node)
        if t == "int":
            texel = self.op(self.m.type_vector(self.type_id("int"), 4), "CompositeConstruct",
                            value, self.m.constant_int(0), self.m.constant_int(0), self.m.constant_int(0))
        elif t == "vec4":
            texel = value
        else:
            zero = self.m.constant_float(0.0)
            pad = {"float": 3, "vec2": 2, "vec3": 1}[t]
            texel = self.op(self.type_id("vec4"), "CompositeConstruct", value, *([zero] * pad))
        self.emit("ImageWrite", image, coord, texel)

    # == lvalues ===============================================================

    def ref(self, node):
        """(pointer id, type) for an assignable expression."""
        m = self.m
        if isinstance(node, Identifier):
            name = node.value
            if name in self.ctx.vars:
                return self.ctx.vars[name]
            if name in self.shared:
                return self.shared[name]
            if name in self.privates:
                return self.privates[name]
            if name in self.stage_outputs:
                return self.stage_outputs[name]
            if name in self.stage_inputs:
                return self.stage_inputs[name]
            if name == "VERTEX_POSITION" and self.position_var is not None:
                return self.position_var, "vec4"
            if name in self.uniform_members:
                index, t = self.uniform_members[name]
                ptr = self.op(m.type_pointer(sv.STORAGE_UNIFORM, self.ubo_member_types[index]),
                              "AccessChain", self.ubo_var, m.constant_int(index))
                return ptr, t
            fbusl.fbusl_error(f"'{name}' can't be assigned to or addressed here.", node.pos)

        if isinstance(node, MemberAccess):
            ptr, t = self.ref(node.base)
            storage = self._storage_of(node.base)
            if t in self.structs:
                fields = self.structs[t]
                index = next(i for i, (f, _) in enumerate(fields) if f == node.member)
                ft = fields[index][1]
                return self.op(m.type_pointer(storage, self.type_id(ft)), "AccessChain", ptr,
                               m.constant_int(index)), ft
            if t in VECTORS and len(node.member) == 1:
                scalar = VECTORS[t][0]
                return self.op(m.type_pointer(storage, self.type_id(scalar)), "AccessChain", ptr,
                               m.constant_int(SWIZZLE[node.member])), scalar
            if t in MATRICES and node.member.startswith("col"):
                col = f"vec{MATRICES[t]}"
                return self.op(m.type_pointer(storage, self.type_id(col)), "AccessChain", ptr,
                               m.constant_int(int(node.member[3:]))), col
            fbusl.fbusl_error(f"Can't address '.{node.member}' on a {t}.", node.pos)

        if isinstance(node, ArrayAccess):
            index, index_type = self.expr(node.index)
            if index_type != "int":
                fbusl.fbusl_error("Array indices must be int.", node.pos)
            base = node.base
            if isinstance(base, MemberAccess) and isinstance(base.base, Identifier) and base.base.value in self.block_names:
                buf = self.buffers.get((base.base.value, base.member))
                if buf is None:
                    fbusl.fbusl_error(f"buffer '{base.base.value}' has no field '{base.member}'.", node.pos)
                element = buf["element"]
                ptr = self.op(m.type_pointer(sv.STORAGE_STORAGE_BUFFER, self.type_id(element)), "AccessChain",
                              buf["var"], m.constant_int(0), index)
                return ptr, element
            ptr, t = self.ref(base)
            if not isinstance(t, tuple):
                fbusl.fbusl_error(f"Can't index into a {t}.", node.pos)
            element = t[1]
            storage = self._storage_of(base)
            return self.op(m.type_pointer(storage, self.type_id(element)), "AccessChain", ptr, index), element

        fbusl.fbusl_error("This expression can't be assigned to.", node.pos)

    def _storage_of(self, node) -> int:
        while isinstance(node, (MemberAccess, ArrayAccess)):
            node = node.base
        name = node.value
        if name in self.ctx.vars:
            return sv.STORAGE_FUNCTION
        if name in self.shared:
            return sv.STORAGE_WORKGROUP
        if name in self.privates:
            return sv.STORAGE_PRIVATE
        if name in self.stage_outputs or name == "VERTEX_POSITION":
            return sv.STORAGE_OUTPUT
        if name in self.stage_inputs:
            return sv.STORAGE_INPUT
        if name in self.uniform_members:
            return sv.STORAGE_UNIFORM
        if name in self.block_names:
            return sv.STORAGE_STORAGE_BUFFER
        return sv.STORAGE_FUNCTION

    # == expressions ===========================================================

    def type_of(self, node):
        if isinstance(node, Identifier):
            name = node.value
            for table in (self.ctx.vars, self.shared, self.privates, self.stage_inputs, self.stage_outputs):
                if name in table:
                    return table[name][1]
            if name in self.uniform_members:
                return self.uniform_members[name][1]
        return _norm(node.type)

    def expr(self, node) -> tuple[int, object]:
        m = self.m
        if isinstance(node, Literal):
            if node.type == "bool":
                return m.constant_bool(node.value), "bool"
            if node.type == "int":
                return m.constant_int(node.value), "int"
            return m.constant_float(node.value), "float"
        if isinstance(node, Identifier):
            return self.identifier(node)
        if isinstance(node, BinOp):
            return self.binop(node)
        if isinstance(node, UnaryOp):
            return self.unary(node)
        if isinstance(node, InlineIf):
            cond, _ = self.expr(node.condition)
            a, t = self.expr(node.then_expr)
            b, _ = self.expr(node.else_expr)
            return self.op(self.type_id(t), "Select", cond, a, b), t
        if isinstance(node, MemberAccess):
            return self.member(node)
        if isinstance(node, ArrayAccess):
            ptr, t = self.ref(node)
            return self.op(self.type_id(t), "Load", ptr), t
        if isinstance(node, FuncCall):
            return self.call(node)
        if isinstance(node, Setter):
            self.assign(node)
            return self.expr(node.node)
        fbusl.fbusl_error(f"The SPIR-V backend can't generate a {type(node).__name__} expression.",
                          getattr(node, "pos", fbusl.Position()))

    def identifier(self, node: Identifier):
        name = node.value
        if name in self.stage_inputs or name in self.stage_outputs:
            var, t = self.stage_inputs.get(name) or self.stage_outputs[name]
            return self.op(self.type_id(t), "Load", var), t
        if name in ("VERTEX_INDEX", "INSTANCE_ID") and self.shader_type == fbusl.ShaderType.VERTEX:
            builtin = sv.BUILTIN_VERTEX_INDEX if name == "VERTEX_INDEX" else sv.BUILTIN_INSTANCE_INDEX
            var = self.builtin_vars.get(name)
            if var is None:
                m = self.m
                var = m.global_variable(m.type_pointer(sv.STORAGE_INPUT, self.type_id("int")), sv.STORAGE_INPUT)
                m.decorate(var, sv.DEC_BUILTIN, builtin)
                m.name(var, name)
                self.interface.append(var)
                self.builtin_vars[name] = var
            return self.op(self.type_id("int"), "Load", var), "int"
        if name == "VERTEX_POSITION" and self.position_var is not None:
            return self.op(self.type_id("vec4"), "Load", self.position_var), "vec4"
        if name in self.uniform_members and self.uniform_members[name][1] == "bool" and name not in self.ctx.vars:
            ptr, _ = self.ref(node)
            stored = self.op(self.type_id("int"), "Load", ptr)
            return self.op(self.type_id("bool"), "INotEqual", stored, self.m.constant_int(0)), "bool"
        if name in self.samplers:
            fbusl.fbusl_error(f"Texture '{name}' can only be used as sample()'s first argument.", node.pos)
        if name in self.ctx.vars or name in self.shared or name in self.privates or name in self.uniform_members:
            if name in self.uniform_members and isinstance(self.uniform_members[name][1], tuple):
                fbusl.fbusl_error(f"Index the uniform array '{name}' rather than reading it whole.", node.pos)
            ptr, t = self.ref(node)
            return self.op(self.type_id(t), "Load", ptr), t
        if name in self.defines:
            return self.expr(self.defines[name])
        if name == "GLOBAL_INVOCATION_ID":
            return self.load_builtin_ivec3("gl_GlobalInvocationID", sv.BUILTIN_GLOBAL_INVOCATION_ID), "ivec3"
        if name == "LOCAL_INVOCATION_ID":
            return self.load_builtin_ivec3("gl_LocalInvocationID", sv.BUILTIN_LOCAL_INVOCATION_ID), "ivec3"
        if name == "WORKGROUP_ID":
            return self.load_builtin_ivec3("gl_WorkGroupID", sv.BUILTIN_WORKGROUP_ID), "ivec3"
        if name == "NUM_WORKGROUPS":
            return self.load_builtin_ivec3("gl_NumWorkGroups", sv.BUILTIN_NUM_WORKGROUPS), "ivec3"
        if name in self.outputs:
            fbusl.fbusl_error(f"@output '{name}' is write-only in a compute/raytrace stage.", node.pos)
        fbusl.fbusl_error(f"Unknown identifier '{name}'.", node.pos)

    def member(self, node: MemberAccess):
        if isinstance(node.base, Identifier) and node.base.value in self.block_names:
            fbusl.fbusl_error(f"Index buffer fields: '{node.base.value}.{node.member}[i]'.", node.pos)
        base, t = self.expr(node.base)
        if t in VECTORS:
            scalar, count = VECTORS[t]
            indices = [SWIZZLE[ch] for ch in node.member]
            if len(indices) == 1:
                return self.op(self.type_id(scalar), "CompositeExtract", base, indices[0]), scalar
            prefix = {"float": "vec", "int": "ivec", "uint": "uvec"}[scalar]
            rt = f"{prefix}{len(indices)}"
            return self.op(self.type_id(rt), "VectorShuffle", base, base, *indices), rt
        if t in MATRICES and node.member.startswith("col"):
            col = f"vec{MATRICES[t]}"
            return self.op(self.type_id(col), "CompositeExtract", base, int(node.member[3:])), col
        if t in self.structs:
            fields = self.structs[t]
            index = next(i for i, (f, _) in enumerate(fields) if f == node.member)
            ft = fields[index][1]
            return self.op(self.type_id(ft), "CompositeExtract", base, index), ft
        fbusl.fbusl_error(f"Can't read '.{node.member}' from a {t}.", node.pos)

    _FLOAT_OPS = {"+": "FAdd", "-": "FSub", "*": "FMul", "/": "FDiv"}
    _INT_OPS = {"+": "IAdd", "-": "ISub", "*": "IMul", "/": "SDiv", "%": "SRem",
                "&": "BitwiseAnd", "|": "BitwiseOr", "^": "BitwiseXor",
                "<<": "ShiftLeftLogical", ">>": "ShiftRightArithmetic"}
    _FLOAT_CMP = {"<": "FOrdLessThan", "<=": "FOrdLessThanEqual", ">": "FOrdGreaterThan",
                  ">=": "FOrdGreaterThanEqual", "==": "FOrdEqual", "!=": "FUnordNotEqual"}
    _INT_CMP = {"<": "SLessThan", "<=": "SLessThanEqual", ">": "SGreaterThan",
                ">=": "SGreaterThanEqual", "==": "IEqual", "!=": "INotEqual"}

    def binop(self, node: BinOp):
        op = node.op
        a, lt = self.expr(node.left)
        b, rt = self.expr(node.right)
        bool_t = self.type_id("bool")

        if op in ("and", "or"):
            return self.op(bool_t, "LogicalAnd" if op == "and" else "LogicalOr", a, b), "bool"
        if op in self._FLOAT_CMP:
            if lt == "float":
                return self.op(bool_t, self._FLOAT_CMP[op], a, b), "bool"
            if lt == "int":
                return self.op(bool_t, self._INT_CMP[op], a, b), "bool"
            if lt == "bool" and op in ("==", "!="):
                return self.op(bool_t, "LogicalEqual" if op == "==" else "LogicalNotEqual", a, b), "bool"
            fbusl.fbusl_error(f"Can't compare {lt} with '{op}'.", node.pos)

        result = _norm(node.type)
        rid = self.type_id(result)
        if lt == "float" and rt == "float":
            return self.op(rid, self._FLOAT_OPS[op], a, b), result
        if lt == "int" and rt == "int":
            return self.op(rid, self._INT_OPS[op], a, b), result
        if lt in VECTORS and VECTORS[lt][0] == "float":
            if rt == lt:
                return self.op(rid, self._FLOAT_OPS[op], a, b), result
            if rt == "float":
                if op == "*":
                    return self.op(rid, "VectorTimesScalar", a, b), result
                return self.op(rid, self._FLOAT_OPS[op], a, self.splat(b, lt)), result
        if lt == "float" and rt in VECTORS and op == "*":
            return self.op(rid, "VectorTimesScalar", b, a), result
        if lt in MATRICES and op == "*":
            if rt == "float":
                return self.op(rid, "MatrixTimesScalar", a, b), result
            if rt in VECTORS:
                return self.op(rid, "MatrixTimesVector", a, b), result
            if rt in MATRICES:
                return self.op(rid, "MatrixTimesMatrix", a, b), result
        fbusl.fbusl_error(f"The SPIR-V backend can't do {lt} {op} {rt}.", node.pos)

    def unary(self, node: UnaryOp):
        value, t = self.expr(node.operand)
        if node.op == "+":
            return value, t
        if node.op == "not":
            return self.op(self.type_id("bool"), "LogicalNot", value), "bool"
        scalar = VECTORS[t][0] if t in VECTORS else t
        return self.op(self.type_id(t), "FNegate" if scalar == "float" else "SNegate", value), t

    # == calls =================================================================

    _UNARY_EXT = {"sqrt": "Sqrt", "floor": "Floor", "fract": "Fract", "sin": "Sin", "cos": "Cos",
                  "tan": "Tan", "sign": "FSign", "abs": "FAbs", "exp": "Exp", "log": "Log",
                  "acos": "Acos", "asin": "Asin", "normalize": "Normalize"}
    _UNSUPPORTED = {"image_store", "ray_aabb", "ray_triangle"}

    def call(self, node: FuncCall):
        name = node.name
        m = self.m
        if name in self._UNSUPPORTED:
            fbusl.fbusl_error(f"'{name}' isn't supported by the SPIR-V backend yet.", node.pos)

        if name in self.functions:
            return self.user_call(node)

        if name == "sample":
            return self.sample(node)

        if name in ("EmitVertex", "EndPrimitive", "input_position"):
            if self.shader_type != fbusl.ShaderType.GEOMETRY:
                fbusl.fbusl_error(f"'{name}' only exists in a geometry stage.", node.pos)
            if name == "input_position":
                index, _ = self.expr(node.args[0])
                ptr = self.op(m.type_pointer(sv.STORAGE_INPUT, self.type_id("vec4")), "AccessChain",
                              self.input_positions, index)
                return self.op(self.type_id("vec4"), "Load", ptr), "vec4"
            self.emit(name)
            return 0, "void"

        # Before the generic argument evaluation below: an image is a
        # resource, not a value that can be loaded on its own.
        if name == "image_load":
            img = node.args[0]
            if not (isinstance(img, Identifier) and img.value in self.input_images):
                fbusl.fbusl_error("image_load()'s first argument must be an `image` @uniform.", node.pos)
            info = self.input_images[img.value]
            coord, _ = self.expr(node.args[1])
            loaded = self.op(info["image"], "Load", info["var"])
            return self.op(self.type_id("vec4"), "ImageRead", loaded, coord), "vec4"

        data = fbusl.builtins.BUILTINS.get("all", {}) | fbusl.builtins.BUILTINS.get(self.shader_type, {})
        builtin = data.get(name)
        if builtin and "requires" in builtin:
            self.require(builtin["requires"], f"call to '{name}'", node.pos)

        args = [self.expr(a) for a in node.args]
        ids = [a[0] for a in args]
        types = [a[1] for a in args]
        result = _norm(node.type)

        if name in self.structs and name not in ("Ray", "RayHit") or name == "make_ray":
            struct = "Ray" if name == "make_ray" else name
            return self.op(self.type_id(struct), "CompositeConstruct", *ids), struct

        if name == "float":
            return self.op(self.type_id("float"), "ConvertSToF", ids[0]), "float"
        if name == "int":
            return self.op(self.type_id("int"), "ConvertFToS", ids[0]), "int"
        if name in VECTORS:
            if len(ids) == 1 and types[0] in ("float", "int"):
                return self.splat(ids[0], name), name
            return self.op(self.type_id(name), "CompositeConstruct", *ids), name
        if name in MATRICES:
            n = MATRICES[name]
            if len(ids) == 1 and types[0] == "float":
                zero = m.constant_float(0.0)
                cols = []
                for c in range(n):
                    parts = [ids[0] if r == c else zero for r in range(n)]
                    cols.append(self.op(self.type_id(f"vec{n}"), "CompositeConstruct", *parts))
                return self.op(self.type_id(name), "CompositeConstruct", *cols), name
            return self.op(self.type_id(name), "CompositeConstruct", *ids), name

        if name in self._UNARY_EXT:
            return self.ext(result, self._UNARY_EXT[name], ids[0]), result
        if name == "length":
            return self.ext("float", "Length", ids[0]), "float"
        if name == "dot":
            return self.op(self.type_id("float"), "Dot", ids[0], ids[1]), "float"
        if name == "cross":
            return self.ext("vec3", "Cross", ids[0], ids[1]), "vec3"
        if name == "reflect":
            return self.ext("vec3", "Reflect", ids[0], ids[1]), "vec3"
        if name == "refract":
            return self.ext("vec3", "Refract", ids[0], ids[1], ids[2]), "vec3"
        if name == "pow":
            return self.ext(result, "Pow", ids[0], ids[1]), result
        if name == "atan":  # atan(y, x), or atan(y_over_x)
            if len(ids) == 1:
                return self.ext("float", "Atan", ids[0]), "float"
            return self.ext("float", "Atan2", ids[0], ids[1]), "float"
        if name in ("max", "min"):
            scalar = VECTORS[types[0]][0] if types[0] in VECTORS else types[0]
            inst = {"max": "FMax", "min": "FMin"}[name] if scalar == "float" else {"max": "SMax", "min": "SMin"}[name]
            return self.ext(result, inst, ids[0], ids[1]), result
        if name == "clamp":
            lo, hi = ids[1], ids[2]
            if types[0] in VECTORS:
                lo, hi = self.splat(lo, types[0]), self.splat(hi, types[0])
            return self.ext(result, "FClamp", ids[0], lo, hi), result
        if name == "mix":
            a = ids[2]
            if types[0] in VECTORS and types[2] == "float":
                a = self.splat(a, types[0])
            return self.ext(result, "FMix", ids[0], ids[1], a), result
        if name == "smoothstep":
            return self.ext("float", "SmoothStep", ids[0], ids[1], ids[2]), "float"
        if name == "round":
            rounded = self.ext("float", "Round", ids[0])
            return self.op(self.type_id("int"), "ConvertFToS", rounded), "int"
        if name == "barrier":
            wg = m.constant_int(sv.SCOPE_WORKGROUP, signed=False)
            sem = m.constant_int(sv.SEMANTICS_ACQ_REL_WORKGROUP, signed=False)
            self.emit("ControlBarrier", wg, wg, sem)
            return 0, "void"
        if name.startswith("atomic_"):
            ptr, t = self.ref(node.args[0])
            scope = m.constant_int(sv.SCOPE_DEVICE, signed=False)
            sem = m.constant_int(0, signed=False)
            inst = {"atomic_add": "AtomicIAdd", "atomic_min": "AtomicSMin", "atomic_max": "AtomicSMax",
                    "atomic_exchange": "AtomicExchange"}[name]
            return self.op(self.type_id("int"), inst, ptr, scope, sem, ids[1]), "int"
        if name == "trace_ray":
            fn = self._helper("trace_ray", self._emit_trace_ray)
            return self.op(self.type_id("RayHit"), "FunctionCall", fn, ids[0]), "RayHit"
        if name == "trace_shadow":
            fn = self._helper("trace_shadow", self._emit_trace_shadow)
            return self.op(self.type_id("bool"), "FunctionCall", fn, ids[0], ids[1]), "bool"

        fbusl.fbusl_error(f"The SPIR-V backend has no lowering for '{name}'.", node.pos)

    def sample(self, node: FuncCall):
        """sample(tex, uv) / sample(stack, index, uv): reads through the
        texture's sub-rect - uv_rect.xy + uv * uv_rect.zw, with uv_rect the
        `_ENGINE_<name>_uv_rect` uniform the GL backends use too."""
        m = self.m
        tex = node.args[0]
        if not (isinstance(tex, Identifier) and tex.value in self.samplers):
            fbusl.fbusl_error("sample()'s first argument must be a `texture` or `textureStack` uniform.", node.pos)
        info = self.samplers[tex.value]
        vec2, vec4, f = self.type_id("vec2"), self.type_id("vec4"), self.type_id("float")
        rect_name = f"_ENGINE_{tex.value}_uv_rect"
        member, _ = self.uniform_members[rect_name]
        if info["kind"] == "texture":
            uv, _ = self.expr(node.args[1])
            ptr = self.op(m.type_pointer(sv.STORAGE_UNIFORM, vec4), "AccessChain", self.ubo_var, m.constant_int(member))
            index = None
        else:
            index, _ = self.expr(node.args[1])
            uv, _ = self.expr(node.args[2])
            ptr = self.op(m.type_pointer(sv.STORAGE_UNIFORM, vec4), "AccessChain", self.ubo_var,
                          m.constant_int(member), index)
        rect = self.op(vec4, "Load", ptr)
        origin = self.op(vec2, "VectorShuffle", rect, rect, 0, 1)
        extent = self.op(vec2, "VectorShuffle", rect, rect, 2, 3)
        coord = self.op(vec2, "FAdd", origin, self.op(vec2, "FMul", uv, extent))
        if index is not None:
            coord = self.op(self.type_id("vec3"), "CompositeConstruct", coord, self.op(f, "ConvertSToF", index))
        sampled = self.op(info["type"], "Load", info["var"])
        if self.shader_type == fbusl.ShaderType.FRAGMENT:
            return self.op(vec4, "ImageSampleImplicitLod", sampled, coord), "vec4"
        # No derivatives outside a fragment shader, so the mip level is explicit.
        return self.op(vec4, "ImageSampleExplicitLod", sampled, coord, sv.IMAGE_OPERAND_LOD,
                       m.constant_float(0.0)), "vec4"

    def user_call(self, node: FuncCall):
        sig = self.functions[node.name]
        operands, write_back = [], []
        for arg, (pname, t, qualifier) in zip(node.args, sig["params"]):
            if qualifier in ("out", "inout"):
                temp = self.local_var(f"_{node.name}_{pname}", t)
                if qualifier == "inout":
                    self.emit("Store", temp, self.expr(arg)[0])
                operands.append(temp)
                write_back.append((arg, temp, t))
            else:
                operands.append(self.expr(arg)[0])
        result = self.op(self.type_id(sig["ret"]), "FunctionCall", sig["id"], *operands)
        for arg, temp, t in write_back:
            ptr, _ = self.ref(arg)
            self.emit("Store", ptr, self.op(self.type_id(t), "Load", temp))
        return result, sig["ret"]

    # == ray queries ===========================================================

    def _helper(self, name, emitter) -> int:
        """Function id for a ray-query helper, emitted once the current
        function is finished (function ids can be referenced before their
        definition)."""
        if name not in self.helpers:
            self.helpers[name] = self.m.id()
            self.m.name(self.helpers[name], f"_fb_{name}")
            if not hasattr(self, "_pending_helpers"):
                self._pending_helpers = []
            self._pending_helpers.append(emitter)
        return self.helpers[name]

    def _ray_query(self, ray: int, flags: int, tmax: int) -> int:
        """Initializes a ray query, runs it to completion, and returns the
        query variable. Geometry is all opaque triangles, so there are no
        candidates for the shader to confirm - Proceed just has to be
        called until it says the traversal is done."""
        m = self.m
        query = m.id()
        self.ctx.var_decls.append(Instruction("Variable", [
            m.type_pointer(sv.STORAGE_FUNCTION, m.type_ray_query()), query, sv.STORAGE_FUNCTION]))
        accel = self.op(m.type_acceleration_structure(), "Load", self.tlas_var)
        origin = self.op(self.type_id("vec3"), "CompositeExtract", ray, 0)
        direction = self.op(self.type_id("vec3"), "CompositeExtract", ray, 1)
        self.emit("RayQueryInitializeKHR", query, accel, m.constant_int(flags, signed=False),
                  m.constant_int(0xFF, signed=False), origin, m.constant_float(self.ray_tmin), direction, tmax)

        header, cond_label, body_label, continue_label, merge = (m.id() for _ in range(5))
        self.terminate("Branch", header)
        self.label(header)
        self.emit("LoopMerge", merge, continue_label, 0)
        self.terminate("Branch", cond_label)
        self.label(cond_label)
        proceed = self.op(self.type_id("bool"), "RayQueryProceedKHR", query)
        self.terminate("BranchConditional", proceed, body_label, merge)
        self.label(body_label)
        self.terminate("Branch", continue_label)
        self.label(continue_label)
        self.terminate("Branch", header)
        self.label(merge)
        return query

    def _begin_helper(self, name, ret, params):
        fn_type = self.m.type_function(self.type_id(ret), [self.type_id(p) for p in params])
        self.ctx = _Function(ret)
        header = [Instruction("Function", [self.type_id(ret), self.helpers[name], 0, fn_type])]
        param_ids = []
        for p in params:
            pid = self.m.id()
            header.append(Instruction("FunctionParameter", [self.type_id(p), pid]))
            param_ids.append(pid)
        return header, param_ids

    def _end_helper(self, header):
        out = self.m.sections["functions"]
        out.extend(header)
        out.append(Instruction("Label", [self.m.id()]))
        out.extend(self.ctx.var_decls)
        out.extend(self.ctx.body)
        out.append(Instruction("FunctionEnd", []))
        self.ctx = None

    def _emit_trace_ray(self):
        m = self.m
        header, (ray,) = self._begin_helper("trace_ray", "RayHit", ["Ray"])
        query = self._ray_query(ray, RAY_FLAG_OPAQUE, m.constant_float(1e30))
        committed = m.constant_int(1)
        kind = self.op(m.type_int(signed=False), "RayQueryGetIntersectionTypeKHR", query, committed)
        hit = self.op(self.type_id("bool"), "INotEqual", kind, m.constant_int(0, signed=False))
        t = self.op(self.type_id("float"), "RayQueryGetIntersectionTKHR", query, committed)
        prim = self.op(self.type_id("int"), "RayQueryGetIntersectionPrimitiveIndexKHR", query, committed)
        bary = self.op(self.type_id("vec2"), "RayQueryGetIntersectionBarycentricsKHR", query, committed)
        instance = self.op(self.type_id("int"), "RayQueryGetIntersectionInstanceCustomIndexKHR", query, committed)
        # On a miss the committed values are undefined; match the GL
        # backends' t = 1e30 so `hit.t < max_t` style tests stay correct.
        t = self.op(self.type_id("float"), "Select", hit, t, m.constant_float(1e30))
        prim = self.op(self.type_id("int"), "Select", hit, prim, m.constant_int(0))
        instance = self.op(self.type_id("int"), "Select", hit, instance, m.constant_int(0))
        u = self.op(self.type_id("float"), "CompositeExtract", bary, 0)
        v = self.op(self.type_id("float"), "CompositeExtract", bary, 1)
        fields = {"t": t, "prim": prim, "u": u, "v": v, "hit": hit, "instance": instance}
        result = self.op(self.type_id("RayHit"), "CompositeConstruct",
                         *(fields[f] for f, _ in self.structs["RayHit"]))
        self.terminate("ReturnValue", result)
        self._end_helper(header)

    def _emit_trace_shadow(self):
        m = self.m
        header, (ray, max_t) = self._begin_helper("trace_shadow", "bool", ["Ray", "float"])
        query = self._ray_query(ray, RAY_FLAG_OPAQUE | RAY_FLAG_TERMINATE_ON_FIRST_HIT, max_t)
        kind = self.op(m.type_int(signed=False), "RayQueryGetIntersectionTypeKHR", query, m.constant_int(1))
        hit = self.op(self.type_id("bool"), "INotEqual", kind, m.constant_int(0, signed=False))
        self.terminate("ReturnValue", hit)
        self._end_helper(header)
