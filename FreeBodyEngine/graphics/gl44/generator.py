"""GLSL 440 core code generator - the GL44 backend's key difference from
GL33 is that compute/raytrace shaders here are REAL GL_COMPUTE_SHADER
stages (GL 4.3+ has actual glDispatchCompute, writable SSBOs, and image
load/store), not GL33's fullscreen-fragment-shader emulation. Vertex/
fragment/geometry codegen, expressions, literals, control flow, etc. don't
change at all between GL 3.3 and 4.4, so this subclasses GL33Generator and
inherits all of that unchanged - only what compute/raytrace/buffer
semantics actually need to differ is overridden here.
"""
import fbusl
from FreeBodyEngine.graphics.gl33.generator import GL33Generator


# Valid GLSL image formats are 1/2/4-component only (no rgb32f) - vec3
# outputs would need to either waste a 4th channel or be rejected; rejected
# for now since neither shipped kernel needs one. Also used by gl44/compute.py
# (via GL44ComputeShader) to pick the matching glGetTexImage format/type.
IMAGE_FORMAT = {
    "float": "r32f",
    "int": "r32i",
    "vec2": "rg32f",
    "vec4": "rgba32f",
}


class GL44Generator(GL33Generator):
    """Emits GLSL 440 core. Subclasses GL33Generator and inherits its vertex/
    fragment/geometry codegen unchanged (only the emitted `#version` line
    differs there); compute/raytrace shaders are overridden here to target a
    real GL_COMPUTE_SHADER stage - real SSBOs and image2D/imageStore instead
    of GL33's fullscreen-fragment-shader emulation with buffer-texture reads
    - which is why CAPABILITIES additionally advertises
    "compute.buffer_write", "compute.image_write", "compute.shared_memory",
    "compute.barrier" and "compute.atomics" on top of GL33's set."""
    CAPABILITIES = frozenset({
        "compute.dispatch",
        "compute.invocation_id",
        "compute.buffer_read",
        "compute.buffer_write",
        "compute.image_read",
        "compute.image_write",
        "compute.shared_memory",
        "compute.barrier",
        "compute.atomics",
        "geometry.native",
        "raytrace.query_emulated",
    })

    def __init__(self, tree, shader_type=fbusl.ShaderType.FRAGMENT):
        """Sets up GL44-specific codegen state on top of GL33Generator's:
        a private copy of `implementations` with `sample()` renamed to
        `_ENGINE_sample()` (GLSL reserves `sample` as a keyword from version
        4.0 on, so GL33's unrenamed helper is a hard syntax error under
        `#version 440`); `_output_fields`, so a compute/raytrace `Setter`
        targeting an `@output` field can be recognized and lowered to
        `imageStore()`; and `image_bindings`, populated the first time
        `generate()` runs for a compute/raytrace stage so
        GL44ComputeShader can read back the same unit numbers baked into
        the emitted `layout(binding=N)` declarations."""
        super().__init__(tree, shader_type)

        # GLSL has reserved `sample` as a keyword since desktop GL 4.0
        # (ARB_sample_shading's `sample in vec2 x;` qualifier) - GL33's
        # `sample()` texture-lookup helper function, used by every FBUSL
        # `sample(...)` call site in vertex/fragment/geometry shaders (not
        # just compute), is perfectly legal GLSL 330 but a hard syntax
        # error under #version 440. Shallow-copy `implementations` (a
        # module-level dict this class otherwise shares by reference with
        # GL33Generator - self.implementations = IMPLEMENTATIONS in its
        # __init__) before rewriting this one entry, so GL33 isn't affected.
        self.implementations = dict(self.implementations)
        sample_impl = self.implementations["sample"]
        self.implementations["sample"] = {
            "kind": "function",
            "source": sample_impl["source"].replace("vec4 sample(", "vec4 _ENGINE_sample("),
            "call": {
                cond: template.replace("sample(", "_ENGINE_sample(", 1)
                for cond, template in sample_impl["call"].items()
            },
        }

        # Every `@output` field's name, so a Setter targeting one (only
        # meaningful in a compute/raytrace stage - vertex/fragment/geometry
        # keep GL33's real `out` variables and inherited Setter codegen) is
        # recognized and lowered to imageStore() instead of a plain `=`.
        self._output_fields = {n.name: n for n in tree if isinstance(n, fbusl.node.Output)}
        # Assigned once, in declaration order, the first time generate() for
        # a compute/raytrace stage runs - GL44ComputeShader reads this same
        # mapping back off the generator instance after compiling, so the
        # image unit numbers baked into the GLSL (layout(binding=N)) and the
        # units it calls glBindImageTexture(N, ...) on always agree.
        self.image_bindings: dict[str, int] = {}

    # ---- vertex/fragment/geometry: identical to GL33, only the version differs ----

    def generate(self):
        """Emits the full GLSL source for `self.tree`: a real compute-shader
        stage (`_generate_compute()`) for COMPUTE/RAYTRACE, or GL33's
        vertex/fragment/geometry codegen otherwise - with `#version 330
        core` swapped for `#version 440 core` in that inherited output,
        since nothing else about that codegen path differs between the two
        backends."""
        if self.shader_type in (fbusl.ShaderType.COMPUTE, fbusl.ShaderType.RAYTRACE):
            return self._generate_compute()
        source = super().generate()
        return source.replace("#version 330 core", "#version 440 core", 1)

    # ---- compute/raytrace: a real compute shader stage ----

    def _generate_compute(self):
        lx, ly, lz = self._local_size()
        source = "#version 440 core\n"
        source += f"layout(local_size_x={lx}, local_size_y={ly}, local_size_z={lz}) in;\n\n"
        source = self.inject_implementation(source, self.implementations)

        if self.shader_type == fbusl.ShaderType.RAYTRACE:
            source += self._generate_raytrace_intrinsics()

        for node in self.tree:
            source += self.generate_node(node)

        return source

    def generate_identifier(self, node):
        """Lowers the three compute "invocation id" builtins to GL 4.4's
        real `gl_GlobalInvocationID`/`gl_WorkGroupID`/`gl_LocalInvocationID`
        (genuinely `uvec3`, cast to `ivec3` to match what FBUSL's semantic
        analyser already typed them as) rather than GL33's gl_FragCoord-
        derived arithmetic emulation. Any other identifier falls through to
        GL33Generator's IMPLEMENTATIONS-table lookup."""
        # Real GLSL compute builtins (all genuinely uvec3) instead of
        # GL33's gl_FragCoord-derived arithmetic - cast to ivec3 to match
        # what FBUSL's semantic analyser already typed these as, so
        # expressions mixing them with ordinary int/ivec3 values still work.
        if node.value == "GLOBAL_INVOCATION_ID":
            return "ivec3(gl_GlobalInvocationID)"
        if node.value == "WORKGROUP_ID":
            return "ivec3(gl_WorkGroupID)"
        if node.value == "LOCAL_INVOCATION_ID":
            return "ivec3(gl_LocalInvocationID)"
        return super().generate_identifier(node)

    def generate_inout(self, node):
        """Routes a compute/raytrace `@output` field to
        `_generate_image_output()` (a real `image2D`/`iimage2D` binding, not
        a GLSL `out` variable); every other `in`/`out`/`uniform` declaration,
        in any stage, falls through to GL33Generator's implementation
        unchanged."""
        if self.shader_type in (fbusl.ShaderType.COMPUTE, fbusl.ShaderType.RAYTRACE) and isinstance(node, fbusl.node.Output):
            return self._generate_image_output(node)
        return super().generate_inout(node)

    def _generate_image_output(self, node: fbusl.node.Output) -> str:
        glsl_type = self.get_type_name(node.type)
        image_format = IMAGE_FORMAT.get(glsl_type)
        if image_format is None:
            fbusl.fbusl_error(
                f"@output '{node.name}: {glsl_type}' can't be written from a compute/raytrace "
                f"stage - only float/int/vec2/vec4 are supported image formats.",
                node.pos,
            )
        binding = len(self.image_bindings)
        self.image_bindings[node.name] = binding
        image_type = "iimage2D" if glsl_type == "int" else "image2D"
        return f"layout({image_format}, binding={binding}) uniform {image_type} {node.name};\n"

    def generate_setter(self, node: fbusl.node.Setter):
        """In a compute/raytrace stage, lowers an assignment to a known
        `@output` field into an `imageStore()` call (padding the value out
        to a `vec4`/`ivec4` per `_pad_to_vec4()`, and indexing by
        `gl_GlobalInvocationID.xy`) instead of GLSL's plain `=`, since a
        compute `@output` is a bound image, not a writable `out` variable.
        Every other assignment, in any stage, falls through to
        GL33Generator's plain `left = right` codegen."""
        if self.shader_type in (fbusl.ShaderType.COMPUTE, fbusl.ShaderType.RAYTRACE):
            target_name = getattr(node.node, "value", None)
            if target_name in self._output_fields:
                glsl_type = self.get_type_name(self._output_fields[target_name].type)
                value = self._pad_to_vec4(self.generate_node(node.value), glsl_type)
                store_fn = "imageStore"
                coord = "ivec2(gl_GlobalInvocationID.xy)"
                if glsl_type == "int":
                    return f"{store_fn}({target_name}, {coord}, ivec4({self.generate_node(node.value)}, 0, 0, 0))"
                return f"{store_fn}({target_name}, {coord}, {value})"
        return super().generate_setter(node)

    def _pad_to_vec4(self, expr: str, glsl_type: str) -> str:
        if glsl_type == "vec4":
            return expr
        if glsl_type == "vec2":
            return f"vec4({expr}, 0.0, 0.0)"
        return f"vec4({expr}, 0.0, 0.0, 0.0)"  # float

    # ---- real SSBOs instead of GL33's samplerBuffer/texelFetch emulation ----

    def generate_buffer_block(self, node: fbusl.node.BufferBlock):
        """Generates a `layout(std430) buffer` block declaration (a real
        SSBO) for one BufferBlock's fields, each as a native GLSL unsized
        array (`<type> <field>[];`) - unlike GL33, which has no real SSBOs
        and instead emulates buffer reads via `samplerBuffer`/`texelFetch`.
        No `require()` gate is needed here (unlike GL33's
        generate_buffer_block()): "compute.buffer_write" is a real
        capability of this backend, so a non-readonly buffer is simply
        generated as such rather than rejected. Struct-typed fields aren't
        supported yet and raise an FBUSL error."""
        # No `require()` gate here (unlike GL33) - "compute.buffer_write" is
        # a real capability of this backend, so a non-readonly buffer is
        # simply generated as such rather than rejected.
        qualifier = "" if node.qualifier == "readwrite" else node.qualifier + " "
        lines = [f"layout(std430) {qualifier}buffer _ENGINE_block_{node.name} {{"]
        for field in node.fields:
            element_type = field.type["data"]["base_type"]
            if element_type in self._struct_defs:
                fbusl.fbusl_error(
                    f"buffer '{node.name}.{field.name}': struct-typed buffer fields aren't "
                    f"supported by the GL44 backend yet.",
                    node.pos,
                )
            lines.append(f"    {element_type} {field.name}[];")
        lines.append(f"}} {node.name};")
        return "\n".join(lines) + "\n"

    def _generate_buffer_field_access(self, block: fbusl.node.BufferBlock, field_name: str, index_node):
        # SSBOs support native GLSL array indexing directly - no
        # texelFetch/swizzle emulation needed, and (unlike GL33) this same
        # expression is valid as an assignment target too, so a Setter
        # writing to `Block.field[index]` "just works" through the ordinary
        # generate_setter() path with no extra handling.
        index_str = self.generate_node(index_node)
        return f"{block.name}.{field_name}[{index_str}]"
