import fbusl
from FreeBodyEngine.graphics.texture import MAX_TEXTURE_STACK_SIZE


IMPLEMENTATIONS = {
    "sample": {
        "kind": "function",
        "source": f"""

vec4 sample(sampler2DArray tex_array, int index, vec2 texcoords, vec4 uv_rect_array[{MAX_TEXTURE_STACK_SIZE}]) {{
    vec3 _BUILTIN_FUNC_uv = vec3(uv_rect_array[index].xy + texcoords * uv_rect_array[index].zw, index);
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
    "texture": {"kind": "type", "replace": "sampler2D"},
    "textureStack": {"kind": "type", "replace": "sampler2DArray"}
}


class GL33Generator(fbusl.generator.Generator):
    def __init__(self, tree: list[fbusl.node.ASTNode]):
        super().__init__(tree)
        self.tree = tree
        self.builtins = fbusl.builtins.BUILTINS
        self.input_index = 0
        self.output_index = 0
        self.implementations = IMPLEMENTATIONS

    def inject_implementation(self, source, implementations):
        new_source = source
        for impl_name, data in implementations.items():
            if data.get("kind") == "function":
                new_source += data.get("source", "")
        return new_source

    def generate(self):
        source = "#version 330 core\n#extension GL_ARB_explicit_attrib_location : enable\n"
        source = self.inject_implementation(source, self.implementations)

        for node in self.tree:
            source += self.generate_node(node)
        return source

    def generate_node(self, node):
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
        elif isinstance(node, str):
            return node
        return ""

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
        return f"{self.generate_node(node.left)}{node.op}{self.generate_node(node.right)}"

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
        body_str = "\n".join(f"    {self.generate_node(b)};" for b in node.body)
        return_type = self.get_glsl_type(node.type)
        return f"{return_type} {node.name}({params_str}) {{\n{body_str}\n}}\n"

    def generate_function_call(self, node):
        impl_data = self.implementations.get(node.name)
        args_strs = [self.generate_node(arg) for arg in node.args]
        arg_types = [self.get_type_name(getattr(arg, "type", None)) for arg in node.args]
        if impl_data and impl_data.get("kind") == "function":
            call_template = impl_data.get("call", {})
            for cond_expr, template in call_template.items():
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
                                call_text = call_text.replace(f"$args[{i}]$", arg_str)
                            return call_text
            return f"{node.name}({', '.join(args_strs)})"
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
