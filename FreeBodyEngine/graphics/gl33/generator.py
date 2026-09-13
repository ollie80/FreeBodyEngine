import fbusl
from FreeBodyEngine.graphics.texture import MAX_TEXTURE_STACK_SIZE


IMPLEMENTATIONS = {
    "sample": {
        "kind": "function",
        "source": f"""

vec4 sample(sampler2DArray tex_array, int index, vec2 texcoords, vec4 uv_rect_array[{MAX_TEXTURE_STACK_SIZE}]) {{
    vec3 _BUILTIN_FUNC_uv = vec3(uv_rect_array[index].xy + texcoords * uv_rect_array[index].zw, float(index));
    return texture(tex_array, _BUILTIN_FUNC_uv);
}}

vec4 sample(sampler2D tex, vec2 texcoords, vec4 uv_rect) {{
    vec2 _BUILTIN_FUNC_uv = uv_rect.xy + texcoords * uv_rect.zw;
    return texture(tex, _BUILTIN_FUNC_uv);
}}\n""",
        "call": {
            "$args[0].type$==texture": "sample($args[0]$, $args[1]$, _ENGINE_$args[0]$_uv_rect)",
            "$args[0].type$==textureStack": "sample($args[0]$, $args[1]$, $args[2]$, _ENGINE_$args[0]$_uv_rect)"
        }
    },
    "VERTEX_POSITION": {"kind": "variable", "replace": "gl_Position"},
    "INSTANCE_ID": {"kind": "variable", "replace": "gl_InstanceID"},
    "VERTEX_INDEX": {"kind": "variable", "replace": "gl_VertexID"},
    "TIME": {'kind': "uniform", 'source': 'uniform float TIME;\n'},
    "texture": {"kind": "type", "replace": "sampler2D"},
    # GL33 has no true image-load-store binding points (GL_ARB_shader_image_
    # load_store is 4.2) - reads are backed by an ordinary texture instead
    # (matches the "compute.image_read" capability), sampled via a direct
    # texelFetch rather than a filtered `sample()`. There's no matching
    # "image_store" IMPLEMENTATIONS entry: "compute.image_write" isn't in
    # GL33Generator.CAPABILITIES, so require() rejects that call before
    # codegen ever needs a lowering for it.
    "image": {"kind": "type", "replace": "sampler2D"},
    "image_load": {"kind": "function", "call": {"": "texelFetch($args[0]$, $args[1]$, 0)"}},
    "textureStack": {"kind": "type", "replace": "sampler2DArray"},
    "round": {"kind": "function", "call": {"": "int(round($args[0]$))"}},
    "EmitVertex": {"kind": "function", "call": {"": "EmitVertex()"}},
    "EndPrimitive": {"kind": "function", "call": {"": "EndPrimitive()"}},
    "input_position": {"kind": "function", "call": {"": "gl_in[$args[0]$].gl_Position"}},
    "DISPATCH_SIZE": {"kind": "uniform", "source": "uniform ivec3 DISPATCH_SIZE;\n"},
    "NUM_WORKGROUPS": {"kind": "uniform", "source": "uniform ivec3 NUM_WORKGROUPS;\n"},
    }

# Component count of each scalar/vector GLSL type, for packing a struct's
# fields into consecutive float slots (4 per buffer-texture texel) when it's
# used as a `buffer` block's element type.
_COMPONENT_COUNTS = {"float": 1, "int": 1, "bool": 1, "vec2": 2, "vec3": 3, "vec4": 4}
_COMPONENT_LETTERS = "xyzw"


class GL33Generator(fbusl.generator.Generator):
    """Emits GLSL 330 core. Compute/raytrace shaders are emulated as a
    fullscreen fragment-shader pass (see FreeBodyEngine.graphics.gl33.compute)
    rather than real GL compute shaders - GL 3.3 has neither. CAPABILITIES
    documents exactly what that emulation can and can't do; any FBUSL
    construct outside this set raises a clear error here rather than
    producing GLSL that looks plausible but doesn't actually work.
    """

    CAPABILITIES = frozenset({
        "compute.dispatch",
        "compute.invocation_id",
        "compute.buffer_read",
        "compute.image_read",
        "geometry.native",
        "raytrace.query_emulated",
    })

    def __init__(self, tree: list[fbusl.node.ASTNode], shader_type: fbusl.ShaderType = fbusl.ShaderType.FRAGMENT):
        """Sets up per-instance codegen state: input/output location counters
        (for `layout(location=...)`), the shared IMPLEMENTATIONS lookup
        table, and this shader's buffer blocks/struct defs indexed by name
        (used later by generate_buffer_block()/_generate_buffer_field_access()
        to resolve `Block.field[index]` accesses)."""
        super().__init__(tree, shader_type)
        self.tree = tree
        self.builtins = fbusl.builtins.BUILTINS
        self.input_index = 0
        self.output_index = 0
        self.implementations = IMPLEMENTATIONS

        self._buffer_blocks: dict[str, fbusl.node.BufferBlock] = {
            n.name: n for n in tree if isinstance(n, fbusl.node.BufferBlock)
        }
        self._struct_defs: dict[str, fbusl.node.StructDef] = {
            n.name: n for n in tree if isinstance(n, fbusl.node.StructDef)
        }

    def _stage_entry(self):
        return next(
            (n for n in self.tree if isinstance(n, fbusl.node.FunctionDef) and n.stage in ("compute", "raytrace")),
            None,
        )

    def _local_size(self) -> tuple[int, int, int]:
        entry = self._stage_entry()
        if entry is None:
            return (1, 1, 1)
        args = entry.stage_args
        return (
            int(args.get("local_size_x", 1)),
            int(args.get("local_size_y", 1)),
            int(args.get("local_size_z", 1)),
        )

    def _lookup_builtin_data(self, name: str) -> dict | None:
        merged = fbusl.builtins.BUILTINS.get("all", {}) | fbusl.builtins.BUILTINS.get(self.shader_type, {})
        return merged.get(name)

    def inject_implementation(self, source, implementations):
        """Appends every function/uniform IMPLEMENTATIONS entry's own GLSL
        source (e.g. `sample()`'s helper function, or the `TIME` uniform
        declaration) to `source`. Entries with no GLSL of their own (plain
        type/variable renames, or a "call" template with no "source") are
        skipped."""
        new_source = source
        for impl_name, data in implementations.items():
            if data.get("kind") == "function":
                new_source += data.get("source", "")
            
            if data.get('kind') == 'uniform':
                new_source += data.get('source', "")
    
        return new_source

    def generate(self):
        """Emits the full GLSL 330 source for `self.tree`: the version/
        extension header (plus a geometry-stage `layout(...)` line, and the
        raytrace ray-intrinsics if this shader is a raytrace stage), the
        IMPLEMENTATIONS' function/uniform injections, then one generated
        line per top-level AST node."""
        source = "#version 330 core\n#extension GL_ARB_separate_shader_objects : enable\n"

        if self.shader_type == fbusl.ShaderType.GEOMETRY:
            source += self._generate_geometry_layout()

        source = self.inject_implementation(source, self.implementations)

        if self.shader_type == fbusl.ShaderType.RAYTRACE:
            source += self._generate_raytrace_intrinsics()

        for node in self.tree:
            source += self.generate_node(node)
        return source

    def _generate_raytrace_intrinsics(self) -> str:
        """`make_ray`/`ray_aabb`/`ray_triangle`/`trace_ray` - an inline
        ray-query intrinsic implemented as software BVH traversal against
        buffer-texture scene data (see graphics/raytrace/bvh.py for the CPU
        side that builds `_ENGINE_bvh_aabb`/`_ENGINE_bvh_meta`/`_ENGINE_triangles`).
        `max_stack` (from `@raytrace(max_stack=...)`, default 32) is the fixed
        traversal-stack depth: GLSL 330 has no recursion or dynamically-sized
        arrays, so this can never be truly dynamic - a BVH deeper than
        `max_stack` silently drops the excess child pointers (and thus can
        miss intersections), which is a real, documented limit of this
        specific backend's raytrace emulation, not a runtime safeguard.

        `max_iterations` (from `@raytrace(max_iterations=...)`, default 4096)
        is a *separate* budget from `max_stack`: the explicit-stack loop
        below pops exactly one node per iteration, so a full traversal needs
        up to one iteration per BVH *node*, not per stack *level* - node
        count (2*leaves-1) can be orders of magnitude larger than tree depth
        for anything but a trivial scene. This used to be derived as
        `max_stack * 2`, which is a stack-depth-shaped budget applied to a
        node-count-shaped problem: any BVH with more nodes than that (a
        handful of moderately-tessellated objects gets there fast) hit the
        iteration cap before the stack ever emptied, silently truncating the
        traversal mid-tree and returning whatever incomplete "closest hit so
        far" it had - a real, valid triangle, just not necessarily the
        correct (or even a nearby) one, which reads as patches of noise on
        exactly the objects with enough geometry to trigger it.
        """
        entry = self._stage_entry()
        max_stack = int(entry.stage_args.get("max_stack", 32)) if entry is not None else 32
        max_iterations = int(entry.stage_args.get("max_iterations", 4096)) if entry is not None else 4096

        return f"""
struct Ray {{ vec3 origin; vec3 direction; }};
struct RayHit {{ float t; int prim; float u; float v; bool hit; }};

uniform samplerBuffer _ENGINE_bvh_aabb;
uniform isamplerBuffer _ENGINE_bvh_meta;
uniform samplerBuffer _ENGINE_triangles;

Ray make_ray(vec3 origin, vec3 direction) {{
    Ray r;
    r.origin = origin;
    r.direction = direction;
    return r;
}}

float ray_aabb(Ray ray, vec3 box_min, vec3 box_max) {{
    vec3 inv_d = 1.0 / ray.direction;
    vec3 t0 = (box_min - ray.origin) * inv_d;
    vec3 t1 = (box_max - ray.origin) * inv_d;
    vec3 tmin = min(t0, t1);
    vec3 tmax = max(t0, t1);
    float t_enter = max(max(tmin.x, tmin.y), tmin.z);
    float t_exit = min(min(tmax.x, tmax.y), tmax.z);
    return (t_exit >= max(t_enter, 0.0)) ? t_enter : -1.0;
}}

vec4 ray_triangle(Ray ray, vec3 v0, vec3 v1, vec3 v2) {{
    vec3 e1 = v1 - v0;
    vec3 e2 = v2 - v0;
    vec3 p = cross(ray.direction, e2);
    float det = dot(e1, p);
    if (abs(det) < 1e-8) {{
        return vec4(0.0);
    }}
    float inv_det = 1.0 / det;
    vec3 t_vec = ray.origin - v0;
    float u = dot(t_vec, p) * inv_det;
    if (u < 0.0 || u > 1.0) {{
        return vec4(0.0);
    }}
    vec3 q = cross(t_vec, e1);
    float vv = dot(ray.direction, q) * inv_det;
    if (vv < 0.0 || u + vv > 1.0) {{
        return vec4(0.0);
    }}
    float t = dot(e2, q) * inv_det;
    return vec4(t, u, vv, t > 1e-5 ? 1.0 : 0.0);
}}

RayHit trace_ray(Ray ray) {{
    RayHit result;
    result.hit = false;
    result.t = 1e30;

    int stack[{max_stack}];
    int sp = 0;
    stack[sp] = 0;
    sp = sp + 1;

    for (int iter = 0; iter < {max_iterations}; iter++) {{
        if (sp <= 0) {{
            break;
        }}
        sp = sp - 1;
        int nodeIdx = stack[sp];

        vec4 bmin = texelFetch(_ENGINE_bvh_aabb, nodeIdx * 2);
        vec4 bmax = texelFetch(_ENGINE_bvh_aabb, nodeIdx * 2 + 1);
        ivec4 meta = texelFetch(_ENGINE_bvh_meta, nodeIdx);

        float tHit = ray_aabb(ray, bmin.xyz, bmax.xyz);
        // ray_aabb's *only* "no intersection" sentinel is the literal -1.0
        // from its ternary's false branch - its true branch returns the
        // entry distance t_enter unclamped, which is legitimately negative
        // whenever the ray origin already lies inside the box along the
        // separating axis (e.g. a camera positioned within the scene's own
        // bounding box - the common case for a root node enclosing the
        // whole scene). Culling on `tHit < 0.0` instead of this exact
        // sentinel treated every such in-box origin as a miss, discarding
        // real intersections before the leaf/triangle test ever ran.
        if (tHit == -1.0 || tHit > result.t) {{
            continue;
        }}

        if (meta.w > 0) {{
            for (int i = 0; i < meta.w; i++) {{
                int triIdx = meta.z + i;
                vec4 tv0 = texelFetch(_ENGINE_triangles, triIdx * 3);
                vec4 tv1 = texelFetch(_ENGINE_triangles, triIdx * 3 + 1);
                vec4 tv2 = texelFetch(_ENGINE_triangles, triIdx * 3 + 2);
                vec4 hit = ray_triangle(ray, tv0.xyz, tv1.xyz, tv2.xyz);
                if (hit.w > 0.5 && hit.x < result.t) {{
                    result.t = hit.x;
                    result.u = hit.y;
                    result.v = hit.z;
                    result.prim = triIdx;
                    result.hit = true;
                }}
            }}
        }} else if (sp < {max_stack} - 1) {{
            stack[sp] = meta.x;
            sp = sp + 1;
            stack[sp] = meta.y;
            sp = sp + 1;
        }}
    }}

    return result;
}}
"""

    def _generate_geometry_layout(self) -> str:
        entry = next(
            (n for n in self.tree if isinstance(n, fbusl.node.FunctionDef) and n.stage == "geometry"),
            None,
        )
        if entry is None:
            return ""

        args = entry.stage_args
        return (
            f"layout({args['input']}) in;\n"
            f"layout({args['output']}, max_vertices={int(args['max_vertices'])}) out;\n"
        )

    def generate_node(self, node):
        """Dispatches `node` to the matching `generate_*` method based on its
        AST node type - the single entry point every codegen method
        (including this one, recursively) goes through to turn a sub-tree
        into GLSL text. A plain `str` node is passed through unchanged;
        any other node type with no lowering falls through to `""`."""

        if isinstance(node, fbusl.node.Identifier):
            return self.generate_identifier(node)
        elif isinstance(node, fbusl.node.FunctionDef):
            return self.generate_function(node)
        elif isinstance(node, fbusl.node.StructDef):
            return self.generate_struct(node)
        elif isinstance(node, (fbusl.node.Output, fbusl.node.Input, fbusl.node.Uniform)):
            return self.generate_inout(node)
        elif isinstance(node, fbusl.node.Define):
            return self.generate_define(node)
        elif isinstance(node, fbusl.node.Literal):
            return self.generate_literal(node)
        elif isinstance(node, fbusl.node.BinOp):
            return self.generate_binop(node)
        elif isinstance(node, fbusl.node.Setter):
            return self.generate_setter(node)
        elif isinstance(node, fbusl.node.FuncCall):
            return self.generate_function_call(node)
        elif isinstance(node, fbusl.node.MemberAccess):
            return self.generate_member_access(node)
        elif isinstance(node, fbusl.node.InlineIf):
            return self.generate_inline_if(node)
        elif isinstance(node, fbusl.node.Condition):
            return self.generate_condition(node)
        elif isinstance(node, fbusl.node.VarDecl):
            return self.generate_vardecl(node)
        elif isinstance(node, fbusl.node.UnaryOp):
            return self.generate_unary_op(node)
        elif isinstance(node, str):
            return node
        elif isinstance(node, fbusl.node.IfStatement):
            return self.generate_if_statement(node)
        elif isinstance(node, fbusl.node.WhileStatement):
            return self.generate_while(node)
        elif isinstance(node, fbusl.node.ArrayAccess):
            return self.generate_array_access(node)
        elif isinstance(node, fbusl.node.BufferBlock):
            return self.generate_buffer_block(node)
        elif isinstance(node, fbusl.node.SharedDecl):
            return self.generate_shared_decl(node)
        elif isinstance(node, fbusl.node.Return):
            return self.generate_return(node)
        return ""

    def generate_return(self, node: fbusl.node.Return):
        """Generates a `return` statement, bare if `node.expression` is None."""
        if node.expression is None:
            return "return"
        return f"return {self.generate_node(node.expression)}"

    def generate_array_access(self, node: fbusl.node.ArrayAccess):
        """Generates an indexing expression `base[index]`, special-casing
        `Block.field[index]` on a registered buffer block (see
        _generate_buffer_field_access) since that isn't a real GLSL struct/
        array access at the FBUSL level."""
        # `Block.field[index]` (a buffer block's field indexed by element) is
        # not real GLSL - `Block` only exists at the FBUSL level as a
        # namespace for a set of buffer-texture uniforms, it isn't an actual
        # GLSL struct instance - so it's special-cased here instead of going
        # through the ordinary MemberAccess codegen.
        if isinstance(node.base, fbusl.node.MemberAccess) and isinstance(node.base.base, fbusl.node.Identifier):
            block = self._buffer_blocks.get(node.base.base.value)
            if block is not None:
                return self._generate_buffer_field_access(block, node.base.member, node.index)

        base = self.generate_node(node.base)
        index = self.generate_node(node.index)
        return f"{base}[{index}]"

    def _buffer_field(self, block: fbusl.node.BufferBlock, field_name: str):
        return next(f for f in block.fields if f.name == field_name)

    def _generate_buffer_field_access(self, block: fbusl.node.BufferBlock, field_name: str, index_node):
        field = self._buffer_field(block, field_name)
        element_type = field.type["data"]["base_type"]
        uniform_name = f"_ENGINE_{block.name}_{field_name}"
        index_str = self.generate_node(index_node)

        if element_type in self._struct_defs:
            return f"_load_{element_type}_{block.name}_{field_name}({index_str})"

        swizzle = {"float": "x", "int": "x", "bool": "x", "vec2": "xy", "vec3": "xyz", "vec4": "xyzw"}.get(element_type, "x")
        access = f"texelFetch({uniform_name}, {index_str}).{swizzle}"
        if element_type == "int":
            return f"int({access})"
        if element_type == "bool":
            return f"bool({access})"
        return access

    def generate_shared_decl(self, node: fbusl.node.SharedDecl):
        """Generates a `shared` compute-shader variable declaration, after
        checking this backend actually has the "compute.shared_memory"
        capability."""
        self.require("compute.shared_memory", f"shared variable '{node.name}'", node.pos)
        base_type, array_suffix = self.resolve_type(node.type)
        return f"shared {base_type} {node.name}{array_suffix};\n"

    def _compute_struct_layout(self, struct_def: fbusl.node.StructDef):
        """Greedily packs a struct's scalar/vector fields, in declaration
        order, into consecutive float component slots (4 per buffer-texture
        texel), never splitting one field across two texels. Returns
        (layout, texel_stride) where layout is a list of
        (field_name, glsl_type, texel_index, component_offset, component_count).
        """
        layout = []
        slot = 0
        for field in struct_def.fields:
            base_type, _ = self.resolve_type(field.type)
            count = _COMPONENT_COUNTS.get(base_type, 1)
            texel_index, component_offset = divmod(slot, 4)
            if component_offset + count > 4:
                texel_index += 1
                component_offset = 0
                slot = texel_index * 4
            layout.append((field.name, base_type, texel_index, component_offset, count))
            slot += count
        texel_stride = max((slot + 3) // 4, 1)
        return layout, texel_stride

    def _generate_struct_field_loader(self, struct_name: str, block_name: str, field_name: str) -> str:
        struct_def = self._struct_defs[struct_name]
        layout, texel_stride = self._compute_struct_layout(struct_def)
        uniform_name = f"_ENGINE_{block_name}_{field_name}"
        func_name = f"_load_{struct_name}_{block_name}_{field_name}"

        lines = [f"{struct_name} {func_name}(int index) {{"]
        for t in range(texel_stride):
            lines.append(f"    vec4 t{t} = texelFetch({uniform_name}, index * {texel_stride} + {t});")
        lines.append(f"    {struct_name} result;")
        for name, base_type, texel_index, offset, count in layout:
            swizzle = _COMPONENT_LETTERS[offset:offset + count]
            expr = f"t{texel_index}.{swizzle}"
            if base_type == "int":
                expr = f"int({expr})"
            elif base_type == "bool":
                expr = f"bool({expr})"
            lines.append(f"    result.{name} = {expr};")
        lines.append("    return result;")
        lines.append("}")
        return "\n".join(lines) + "\n"

    def generate_buffer_block(self, node: fbusl.node.BufferBlock):
        """Generates the `uniform samplerBuffer` declarations (and, for
        struct-typed fields, the matching `_load_<struct>_<block>_<field>()`
        loader function) backing one BufferBlock's fields - GL33 has no
        real SSBOs, so every buffer field is read back via texelFetch on a
        buffer texture instead. Requires "compute.buffer_write" if the
        block isn't declared readonly, since this emulation can only ever
        read these buffers, never write them."""
        if node.qualifier != "readonly":
            self.require(
                "compute.buffer_write",
                f"buffer '{node.name}' declared {node.qualifier} (only readonly buffers are supported)",
                node.pos,
            )

        source = ""
        for field in node.fields:
            element_type = field.type["data"]["base_type"]
            uniform_name = f"_ENGINE_{node.name}_{field.name}"

            if element_type in self._struct_defs:
                # Struct fields are packed as float texels (ints included -
                # see _generate_struct_field_loader), so always a plain
                # samplerBuffer here, never isamplerBuffer.
                source += f"uniform samplerBuffer {uniform_name};\n"
                source += self._generate_struct_field_loader(element_type, node.name, field.name)
            else:
                source += f"uniform samplerBuffer {uniform_name};\n"

        return source

    def generate_while(self, node: fbusl.node.WhileStatement):
        """Generates a `while` loop, recursively generating each statement in its body."""
        source = f"\nwhile ({self.generate_node(node.condition)}) {{\n"
        for b_node in node.body:
            stmt = self.generate_node(b_node).rstrip(";")
            source += f"    {stmt};\n"
        source += "}"
        return source

    def generate_if_statement(self, node: fbusl.node.IfStatement):
        """Generates an `if`/`else if`/`else` chain, recursively generating
        `node.next_statement` (an `elif`/`else` link) to build the whole
        chain from a single `if` node."""
        type_map = {"elif": "else if", "else": "else", "if": "if"}
        source = f"\n{type_map[node.if_type]} "

        if node.condition is not None:
            source += f"({self.generate_node(node.condition)}) "

        source += "{\n"
        for b_node in node.body:
            stmt = self.generate_node(b_node).rstrip(";")
            source += f"    {stmt};\n"
        source += "}"

        if node.next_statement is not None:
            source += self.generate_if_statement(node.next_statement)
        
        return source

    def generate_unary_op(self, node):
        """Generates a unary expression (e.g. `-x`, `!flag`), parenthesizing the operand if it's itself a binary expression."""
        operand = self.generate_node(node.operand)
        if isinstance(node.operand, fbusl.node.BinOp):
            operand = f"({operand})"
        return f'{node.op}{operand}'

    def generate_inline_if(self, node):
        return f'{self.generate_node(node.condition)} ? {self.generate_node(node.then_expr)} : {self.generate_node(node.else_expr)}'

    def generate_vardecl(self, node):
        name = self.generate_node(node.name)
        node_type = self.get_glsl_type(node.type)
        value = self.generate_node(node.value)
        return f"{node_type} {name} = {value};"

    def generate_setter(self, node):
        left = self.generate_node(node.node)
        right = self.generate_node(node.value)
        return f"{left} = {right}"

    def generate_literal(self, node):
        if node.type == "int":
            return str(int(node.value))
        elif node.type == "float":
            return str(float(node.value))
        elif node.type == "bool":
            return "true" if node.value else "false"
        return str(node.value)

    def generate_identifier(self, node):
        # These three need the entry stage's local_size to derive, so they're
        # handled here rather than as a static IMPLEMENTATIONS "replace"
        # string. There are no real hardware workgroups behind them under
        # this backend's emulation, but the arithmetic is still correct and
        # useful (kernels can tile logical work by workgroup for locality),
        # which is why "compute.invocation_id" is a capability GL33 *does*
        # have, distinct from "compute.shared_memory"/"compute.barrier".
        if node.value == "GLOBAL_INVOCATION_ID":
            return "ivec3(int(gl_FragCoord.x), int(gl_FragCoord.y), 0)"
        if node.value in ("WORKGROUP_ID", "LOCAL_INVOCATION_ID"):
            lx, ly, _lz = self._local_size()
            if node.value == "WORKGROUP_ID":
                return f"ivec3(int(gl_FragCoord.x)/{lx}, int(gl_FragCoord.y)/{ly}, 0)"
            return f"ivec3(int(gl_FragCoord.x)%{lx}, int(gl_FragCoord.y)%{ly}, 0)"

        impl_data = self.implementations.get(node.value)
        if impl_data:
            kind = impl_data.get("kind")
            if kind == "variable":
                return impl_data.get("replace", node.value)
            elif kind == "type":
                return impl_data.get("replace", node.value)
        return node.value

    def generate_inout(self, node):
        qualifier = getattr(node, "qualifier", "")
        storage = ""
        layout = ""

        if isinstance(node, fbusl.node.Input):
            layout = f"layout(location={self.input_index}) "
            self.input_index += 1
            storage = "in"
        elif isinstance(node, fbusl.node.Output):
            layout = f"layout(location={self.output_index}) "
            self.output_index += 1
            storage = "out"
        elif isinstance(node, fbusl.node.Uniform):
            storage = "uniform"

        base_type, array_suffix = self.resolve_type(node.type)

        # A geometry stage receives one value per input-primitive vertex for
        # every `@input` field (e.g. an `input=triangles` stage gets 3 of
        # each), regardless of the field's own FBUSL type - so it's always a
        # GLSL unsized array here, on top of whatever array-ness the type
        # itself already has.
        if isinstance(node, fbusl.node.Input) and self.shader_type == fbusl.ShaderType.GEOMETRY:
            array_suffix += "[]"

        decl = f"{node.name}{array_suffix}"
        text = ""

        type_name = self.get_type_name(node.type)
        if storage == "uniform":
            if type_name == "texture":
                text += f"uniform vec4 _ENGINE_{node.name}_uv_rect;\n"
            elif type_name == "textureStack":
                text += f"uniform vec4 _ENGINE_{node.name}_uv_rect[{MAX_TEXTURE_STACK_SIZE}];\n"

        return f"{text}{layout}{qualifier + ' ' if qualifier else ''}{storage} {base_type} {decl};\n"

    def generate_define(self, node):
        return f"#define {node.name} {self.generate_node(node.value)}\n"

    def generate_binop(self, node):
        # The AST already encodes grouping/precedence via tree structure (an
        # explicitly-parenthesized sub-expression in FBUSL source parses to
        # exactly the same tree shape as one that just happens to bind that
        # way per FBUSL's own precedence table - the parser discards parens,
        # it doesn't record them). Emitting a nested BinOp without its own
        # parens would let GLSL's *own* precedence re-parse the flattened
        # text differently the moment a lower-precedence op is nested inside
        # a higher-precedence one (e.g. `(a + b) / c` naively flattened to
        # `a+b/c` silently becomes `a + (b/c)`) - so nested BinOp operands are
        # always parenthesized here, unconditionally, rather than trying to
        # reason about exactly when GLSL's precedence would agree.
        left = self.generate_node(node.left)
        if isinstance(node.left, fbusl.node.BinOp):
            left = f"({left})"

        right = self.generate_node(node.right)
        if isinstance(node.right, fbusl.node.BinOp):
            right = f"({right})"

        return f"{left}{node.op}{right}"

    def generate_struct(self, node):
        fields_text = ""
        for field in node.fields:
            fields_text += "    " + self.format_var(field.name, field.type) + "\n"
        return f"struct {node.name} {{\n{fields_text}}};\n"

    def generate_member_access(self, node):
        base = self.generate_node(node.base)
        return f"{base}.{node.member}"

    def generate_function(self, node):
        param_texts = [
            self.format_var(p.name, p.type).rstrip(";")
            for p in node.params
        ]
        params_str = ", ".join(param_texts)
        body_str = "\n".join(f"    {self.generate_node(b).rstrip(';')};" for b in node.body)
        return_type = self.get_glsl_type(node.type)
        return f"{return_type} {node.name}({params_str}) {{\n{body_str}\n}}\n"

    def generate_function_call(self, node):
        builtin_data = self._lookup_builtin_data(node.name)
        if builtin_data and "requires" in builtin_data:
            self.require(builtin_data["requires"], f"call to '{node.name}'", node.pos)

        impl_data = self.implementations.get(node.name)
        args_strs = [self.generate_node(arg) for arg in node.args]
        arg_types = [self.get_type_name(getattr(arg, "type", None)) for arg in node.args]
        if impl_data and impl_data.get("kind") == "function":
            call_template = impl_data.get("call", {})

            for cond_expr, template in call_template.items():

                # Unconditional function replacement
                if cond_expr == "":
                    call_text = template
                    for i, arg_str in enumerate(args_strs):
                        call_text = call_text.replace(f"$args[{i}]$", arg_str)
                    return call_text

                match = cond_expr.split("==")
                if len(match) == 2:
                    left, right = match
                    left = left.strip()
                    right = right.strip()

                    if left.startswith("$args[") and left.endswith("].type$"):
                        idx = int(left[6:-7])

                        if idx < len(arg_types) and arg_types[idx] == right:
                            call_text = template

                            for i, arg_str in enumerate(args_strs):
                                call_text = call_text.replace(
                                    f"$args[{i}]$", arg_str
                                )

                            return call_text

        return f"{node.name}({', '.join(args_strs)})"

    def format_var(self, name, type_annotation, qualifier="") -> str:
        base_type, array_suffix = self.resolve_type(type_annotation)
        declaration = f"{base_type} {name}{array_suffix};"
        if qualifier:
            return f"{qualifier} {declaration}"
        return declaration

    def resolve_type(self, type_annotation) -> tuple[str, str]:
        if type_annotation is None:
            return "void", ""

        if isinstance(type_annotation, str):
            impl_data = self.implementations.get(type_annotation)
            if impl_data and impl_data.get("kind") == "type":
                return impl_data.get("replace", type_annotation), ""
            return type_annotation, ""

        if isinstance(type_annotation, dict):
            if type_annotation.get("name") == "array":
                length = type_annotation["data"]["length"]
                base_type, nested_suffix = self.resolve_type(type_annotation["data"]["base_type"])
                return base_type, nested_suffix + f"[{length}]"

            type_name = type_annotation.get("name", "unknown")
            impl_data = self.implementations.get(type_name)
            if impl_data and impl_data.get("kind") == "type":
                return impl_data.get("replace", type_name), ""

            return type_name, ""

        return "unknown", ""

    def get_glsl_type(self, type_annotation) -> str:
        base_type, _ = self.resolve_type(type_annotation)
        return base_type

    def get_type_name(self, type_annotation) -> str:
        """Returns the original type name, either directly or from a type dict."""
        if type_annotation is None:
            return "void"
        if isinstance(type_annotation, str):
            return type_annotation
        if isinstance(type_annotation, dict):
            return type_annotation.get("name", "unknown")
        return "unknown"
