import fbusl
from FreeBodyEngine.graphics.gl33.generator import GL33Generator, IMPLEMENTATIONS, _COMPONENT_LETTERS
from FreeBodyEngine.graphics.texture import MAX_TEXTURE_STACK_SIZE

# GL33Generator's own "sample" IMPLEMENTATIONS entry (see that module),
# renamed from `sample` to `fb_sample` throughout - GLSL ES 3.00 (WebGL2's
# shading language) reserves `sample` as a future keyword (desktop GLSL
# 330 does not), so a shader using FBUSL's `sample()` builtin failed to
# compile with "illegal use of reserved word" the instant it emitted
# GL33Generator's verbatim helper-function source unchanged. Everything
# else about this entry (the two overloads, the uv_rect indexing logic,
# the "call" templates FBUSL's codegen substitutes a real `sample(...)`
# call with) is identical to GL33Generator's - only the actual GLSL
# function name differs.
_WEBGL2_IMPLEMENTATIONS = {
    **IMPLEMENTATIONS,
    "sample": {
        "kind": "function",
        "source": f"""

vec4 fb_sample(sampler2DArray tex_array, int index, vec2 texcoords, vec4 uv_rect_array[{MAX_TEXTURE_STACK_SIZE}]) {{
    vec3 _BUILTIN_FUNC_uv = vec3(uv_rect_array[index].xy + texcoords * uv_rect_array[index].zw, float(index));
    return texture(tex_array, _BUILTIN_FUNC_uv);
}}

vec4 fb_sample(sampler2D tex, vec2 texcoords, vec4 uv_rect) {{
    vec2 _BUILTIN_FUNC_uv = uv_rect.xy + texcoords * uv_rect.zw;
    return texture(tex, _BUILTIN_FUNC_uv);
}}\n""",
        "call": {
            "$args[0].type$==texture": "fb_sample($args[0]$, $args[1]$, _ENGINE_$args[0]$_uv_rect)",
            "$args[0].type$==textureStack": "fb_sample($args[0]$, $args[1]$, $args[2]$, _ENGINE_$args[0]$_uv_rect)",
        },
    },
}


class WebGL2Generator(GL33Generator):
    """Emits GLSL ES 3.00 (WebGL2's shading language) - inherits GL33Generator
    wholesale (the actual codegen for expressions/statements/functions is
    identical between desktop GLSL 330 and GLSL ES 300; they diverged from
    the same OpenGL ES lineage and neither this engine nor FBUSL uses any
    construct where they differ) and overrides only what actually differs:
    the version header, ES's mandatory float precision qualifier that
    desktop GLSL doesn't have at all, and the "sample" builtin's generated
    function name (see _WEBGL2_IMPLEMENTATIONS above - `sample` itself is
    a reserved word in GLSL ES, unlike desktop GLSL 330).

    CAPABILITIES covers everything GL33Generator's does *except*
    "geometry.native" - WebGL2 genuinely has no geometry shader stage at
    all (that's ES 3.2/desktop only), so `@geometry` still raises a clear
    FBUSL "capability not supported" error targeting web. Compute/raytrace
    support (buffer_read/dispatch/invocation_id/image_read/
    query_emulated), though, carries over just fine - GL33's own emulation
    of all of it is already built entirely from ordinary draw calls,
    framebuffers and textures (see graphics/gl33/compute.py's module
    docstring), none of which are desktop-only. The one piece that
    genuinely doesn't exist in WebGL2 is `samplerBuffer`/GL_TEXTURE_BUFFER
    itself (ES 3.2+/desktop-only, no WebGL2 extension exposes it) - see
    generate_buffer_block()/_generate_raytrace_intrinsics() below for the
    2D-data-texture emulation (graphics/webgl/buffer.py's
    WebGL2TextureBuffer) that replaces it.
    """

    CAPABILITIES = frozenset({
        "compute.dispatch",
        "compute.invocation_id",
        "compute.buffer_read",
        "compute.image_read",
        "raytrace.query_emulated",
    })

    def __init__(self, *args, **kwargs):
        """Same as GL33Generator.__init__(), except `self.implementations`
        is the WebGL2-specific table above (renamed "sample") instead of
        GL33Generator's own."""
        super().__init__(*args, **kwargs)
        self.implementations = _WEBGL2_IMPLEMENTATIONS

    def generate(self):
        """Same shape as GL33Generator.generate() - version/extension
        header, then IMPLEMENTATIONS injections, then (for a RAYTRACE
        stage) the ray-intrinsics, then one generated line per top-level
        AST node - but with a GLSL ES header instead of desktop GLSL's,
        no geometry-layout handling (CAPABILITIES above still has no
        "geometry.native", so reaching that FBUSL construct raises
        first), and the `_ENGINE_buf_idx()` overload pair every buffer-
        block/raytrace-intrinsic access below calls to turn a 1D index
        into this backend's 2D-data-texture coordinates."""
        source = "#version 300 es\n"
        # Fragment shaders in GLSL ES have no default precision for these
        # types the way desktop GLSL does - every fragment shader MUST
        # declare one itself or fails to compile outright. Declared
        # identically in *every* stage (not just fragment), and covering
        # every type IMPLEMENTATIONS' injected uniforms use (float, int -
        # DISPATCH_SIZE/NUM_WORKGROUPS are ivec3 - and both sampler
        # kinds), because GLSL ES additionally requires a uniform shared
        # between vertex and fragment stages to have the *same* precision
        # in both: vertex shaders default `int`/`ivec*` to highp while
        # fragment shaders have no default at all, so leaving `int`
        # undeclared here linked with "mismatching precision qualifiers"
        # on DISPATCH_SIZE the moment both stages saw that uniform
        # (injected into every shader regardless of whether it's actually
        # used - see inject_implementation()) at two different effective
        # precisions.
        source += (
            "precision highp float;\n"
            "precision highp int;\n"
            "precision highp sampler2D;\n"
            "precision highp sampler2DArray;\n"
            # isampler2D has no default precision either, same as every
            # other sampler kind in GLSL ES - needed unconditionally (not
            # just for a raytrace/compute shader) since _ENGINE_buf_idx()
            # right below declares an isampler2D-typed overload in every
            # shader, whether or not this particular one actually uses a
            # buffer block.
            "precision highp isampler2D;\n"
        )

        source = self.inject_implementation(source, self.implementations)

        # Always injected, whether or not this particular shader actually
        # declares a buffer block or raytrace stage - a couple of unused
        # GLSL functions cost nothing at runtime, and unconditional
        # injection means generate_buffer_block()/_generate_raytrace_
        # intrinsics() below never need to track "have I emitted this
        # already" across possibly-repeated calls. Two overloads (one per
        # sampler kind actually used - sampler2D for ordinary buffer
        # blocks and the raytrace scene's bvh_aabb/triangles, isampler2D
        # for bvh_meta's int data) since GLSL ES has no generic "any
        # sampler" parameter type; `textureSize()` reads this texture's
        # *actual* dimensions straight back from the GPU, so nothing here
        # needs a companion "width" uniform kept in sync with whatever
        # WebGL2TextureBuffer.set_data() decided at upload time.
        source += (
            "ivec2 _ENGINE_buf_idx(sampler2D tex, int i) { ivec2 sz = textureSize(tex, 0); return ivec2(i % sz.x, i / sz.x); }\n"
            "ivec2 _ENGINE_buf_idx(isampler2D tex, int i) { ivec2 sz = textureSize(tex, 0); return ivec2(i % sz.x, i / sz.x); }\n"
        )

        if self.shader_type == fbusl.ShaderType.RAYTRACE:
            source += self._generate_raytrace_intrinsics()

        for node in self.tree:
            source += self.generate_node(node)
        return source

    def generate_inout(self, node):
        """Same as GL33Generator.generate_inout(), except `layout(location=
        ...)` is only emitted where GLSL ES 3.00 core actually allows it:
        a vertex shader's `in` (attribute) declarations, and a fragment
        shader's `out` (color attachment) declarations. Desktop GLSL 330
        can put an explicit location on *every* in/out, including a
        vertex shader's `out` varyings and a fragment shader's matching
        `in` varyings, because GL33Generator's header enables
        `GL_ARB_separate_shader_objects` - WebGL2 has no equivalent
        extension at all, and ES 3.00 core requires varyings to match
        between stages by *name* instead, with no location qualifier on
        either side. Emitting one anyway compiled fine in isolation but
        failed exactly at the vertex stage (before this was ever caught)
        with "invalid layout qualifier: only valid on program inputs and
        outputs" - GLSL ES's own error wording for "not a real attribute/
        fragment-output".

        `self.input_index`/`self.output_index` still advance on every
        Input/Output regardless of whether a location actually gets
        printed, matching GL33Generator's own counting so mixed vertex/
        fragment field ordering behaves identically to desktop wherever a
        location *is* emitted."""
        qualifier = getattr(node, "qualifier", "")
        storage = ""
        layout = ""

        if isinstance(node, fbusl.node.Input):
            if self.shader_type == fbusl.ShaderType.VERTEX:
                layout = f"layout(location={self.input_index}) "
            self.input_index += 1
            storage = "in"
        elif isinstance(node, fbusl.node.Output):
            if self.shader_type == fbusl.ShaderType.FRAGMENT:
                layout = f"layout(location={self.output_index}) "
            self.output_index += 1
            storage = "out"
        elif isinstance(node, fbusl.node.Uniform):
            storage = "uniform"

        base_type, array_suffix = self.resolve_type(node.type)

        decl = f"{node.name}{array_suffix}"
        text = ""

        type_name = self.get_type_name(node.type)
        if storage == "uniform":
            if type_name == "texture":
                text += f"uniform vec4 _ENGINE_{node.name}_uv_rect;\n"
            elif type_name == "textureStack":
                text += f"uniform vec4 _ENGINE_{node.name}_uv_rect[{MAX_TEXTURE_STACK_SIZE}];\n"

        return f"{text}{layout}{qualifier + ' ' if qualifier else ''}{storage} {base_type} {decl};\n"

    def generate_buffer_block(self, node: fbusl.node.BufferBlock):
        """Same contract as GL33Generator.generate_buffer_block() (declares
        one uniform per field, plus a `_load_<struct>_<block>_<field>()`
        loader for struct-typed fields) but backed by `sampler2D` instead
        of `samplerBuffer` - see this module's own docstring and
        graphics/webgl/buffer.py's WebGL2TextureBuffer for why. Every
        field here is float data (even an int-typed struct field - see
        _generate_struct_field_loader's int() cast), matching
        GL33Generator's own choice to always use samplerBuffer (never
        isamplerBuffer) for ordinary buffer blocks; only the raytrace
        intrinsics' bvh_meta needs a real int texture (see
        _generate_raytrace_intrinsics)."""
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

            source += f"uniform sampler2D {uniform_name};\n"
            if element_type in self._struct_defs:
                source += self._generate_struct_field_loader(element_type, node.name, field.name)

        return source

    def _generate_buffer_field_access(self, block: fbusl.node.BufferBlock, field_name: str, index_node):
        """Same contract as GL33Generator._generate_buffer_field_access()
        - only the actual texelFetch call differs, indexing through
        `_ENGINE_buf_idx()` (see generate()) instead of samplerBuffer's
        native 1D indexing."""
        field = self._buffer_field(block, field_name)
        element_type = field.type["data"]["base_type"]
        uniform_name = f"_ENGINE_{block.name}_{field_name}"
        index_str = self.generate_node(index_node)

        if element_type in self._struct_defs:
            return f"_load_{element_type}_{block.name}_{field_name}({index_str})"

        swizzle = {"float": "x", "int": "x", "bool": "x", "vec2": "xy", "vec3": "xyz", "vec4": "xyzw"}.get(element_type, "x")
        access = f"texelFetch({uniform_name}, _ENGINE_buf_idx({uniform_name}, {index_str}), 0).{swizzle}"
        if element_type == "int":
            return f"int({access})"
        if element_type == "bool":
            return f"bool({access})"
        return access

    def _generate_struct_field_loader(self, struct_name: str, block_name: str, field_name: str) -> str:
        """Same contract/layout as GL33Generator._generate_struct_field_
        loader() (the same greedy 4-floats-per-texel packing, from the
        same _compute_struct_layout()) - only the texelFetch call itself
        differs, same as _generate_buffer_field_access() above."""
        struct_def = self._struct_defs[struct_name]
        layout, texel_stride = self._compute_struct_layout(struct_def)
        uniform_name = f"_ENGINE_{block_name}_{field_name}"
        func_name = f"_load_{struct_name}_{block_name}_{field_name}"

        lines = [f"{struct_name} {func_name}(int index) {{"]
        for t in range(texel_stride):
            lines.append(f"    vec4 t{t} = texelFetch({uniform_name}, _ENGINE_buf_idx({uniform_name}, index * {texel_stride} + {t}), 0);")
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

    def _generate_raytrace_intrinsics(self) -> str:
        """Same `make_ray`/`ray_aabb`/`ray_triangle`/`trace_ray` BVH-
        traversal intrinsic as GL33Generator's own (identical math,
        identical `max_stack`/`max_iterations` semantics - see that
        method's docstring for the full reasoning) - only the scene-data
        access differs: `sampler2D`/`isampler2D` 2D data textures (see
        graphics/webgl/buffer.py's WebGL2TextureBuffer) indexed through
        `_ENGINE_buf_idx()` instead of `samplerBuffer`/`isamplerBuffer`'s
        native 1D texelFetch."""
        entry = self._stage_entry()
        max_stack = int(entry.stage_args.get("max_stack", 32)) if entry is not None else 32
        max_iterations = int(entry.stage_args.get("max_iterations", 4096)) if entry is not None else 4096

        return f"""
struct Ray {{ vec3 origin; vec3 direction; }};
struct RayHit {{ float t; int prim; float u; float v; bool hit; }};

uniform sampler2D _ENGINE_bvh_aabb;
uniform isampler2D _ENGINE_bvh_meta;
uniform sampler2D _ENGINE_triangles;

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

        vec4 bmin = texelFetch(_ENGINE_bvh_aabb, _ENGINE_buf_idx(_ENGINE_bvh_aabb, nodeIdx * 2), 0);
        vec4 bmax = texelFetch(_ENGINE_bvh_aabb, _ENGINE_buf_idx(_ENGINE_bvh_aabb, nodeIdx * 2 + 1), 0);
        ivec4 meta = texelFetch(_ENGINE_bvh_meta, _ENGINE_buf_idx(_ENGINE_bvh_meta, nodeIdx), 0);

        float tHit = ray_aabb(ray, bmin.xyz, bmax.xyz);
        if (tHit == -1.0 || tHit > result.t) {{
            continue;
        }}

        if (meta.w > 0) {{
            for (int i = 0; i < meta.w; i++) {{
                int triIdx = meta.z + i;
                vec4 tv0 = texelFetch(_ENGINE_triangles, _ENGINE_buf_idx(_ENGINE_triangles, triIdx * 3), 0);
                vec4 tv1 = texelFetch(_ENGINE_triangles, _ENGINE_buf_idx(_ENGINE_triangles, triIdx * 3 + 1), 0);
                vec4 tv2 = texelFetch(_ENGINE_triangles, _ENGINE_buf_idx(_ENGINE_triangles, triIdx * 3 + 2), 0);
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
