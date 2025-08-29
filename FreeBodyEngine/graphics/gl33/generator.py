import fbusl

# implements builtins
IMPLEMENTATIONS = {
    "sample": {
        "kind": "function",
        "source": f"""

vec4 sample(sampler2DArray tex_array, int index, vec2 texcoords, vec4 uv_rect_array[{fbusl.MAX_TEXTURE_ARRAY_SIZE}])""" + """ {
    vec3 uv = vec3(uv_rect_array[index].xy + texcoords * uv_rect_array[index].zw, index);
    return texture(tex_array, uv);
};

vec4 sample(sampler2D tex, vec2 texcoords, vec4 uv_rect) {
    vec2 uv = uv_rect.xy + texcoords * uv_rect.zw;
    return texture(tex, uv);
};\n""",
        'call': {"$args[0].type$==sampler2D": "sample($args[0]$, $args[1]$, _ENGINE_$args[0]$_uv_rect)", "$args[0].type$==sampler2DArray": "sample($args[0]$, $args[1]$, $args[2]$, _ENGINE_$args[0]$_uv_rect)"}
    }, 
    "VERTEX_POSITION": {
        "kind": "variable",
        "replace": "gl_Position"
    }, 
    "INSTANCE_ID": {
        "kind": "variable",
        "replace": "gl_InstanceID"
    }, 
    "texture": {
        "kind": "type",
        "replace": "sampler2D"
    },
    "textureArray": {
        "kind": "type",
        "replace": "sampler2DArray"
    }
}

class GL33Generator(fbusl.generator.Generator):
    def __init__(self, tree: list[fbusl.node.ASTNode]):
        super().__init__(tree)
        self.tree: list[fbusl.node.ASTNode]
        self.builtins = fbusl.builtins.BUILTINS
        self.input_index = 0
        self.output_index = 0
        self.implementations = IMPLEMENTATIONS

    def inject_implementation(self, source, implementations):
        new_source = source
        for impl_name, data in implementations.items():
            kind = data.get('kind')
            if kind == 'function':
                new_source += data.get('source', '')
        return new_source

    def generate(self):
        source = "#version 330 core\n"
        source = self.inject_implementation(source, self.implementations)

        for node in self.tree:
            source += self.generate_node(node)

        print(source)
        return source

    def generate_node(self, node: fbusl.node.ASTNode):
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

    def generate_inline_if(self, node: fbusl.node.InlineIf):
        return f'{self.generate_node(node.condition)} ? {self.generate_node(node.then_expr)} : {self.generate_node(node.else_expr)}'

    def generate_vardecl(self, node: fbusl.node.VarDecl):
        name = self.generate_node(node.name)
        node_type = self.get_glsl_type(node.type)

        val = self.generate_node(node.value)
        return f"{node_type} {name} = {val};"

    def generate_setter(self, node: fbusl.node.Setter):
        left = self.generate_node(node.node)
        print("LEFT: ", left)
        right = self.generate_node(node.value)
        print(right)
        return f"{left} = {right}" 

    def generate_literal(self, node: fbusl.node.Literal):
        if node.type == "int":
            return str(int(node.value))
        elif node.type == "float":
            return str(float(node.value))
        elif node.type == 'bool':
            return {False: "false", True: 'true'}.get(node.value)

    def generate_identifier(self, node: fbusl.node.Identifier) -> str:
        impl_data = self.implementations.get(node.value)
        if impl_data:
            kind = impl_data.get('kind')
            if kind == 'variable':
                return impl_data.get('replace', node.value)
            elif kind == 'type':
                return impl_data.get('replace', node.value)
        return node.value

    def generate_inout(self, node: fbusl.node.Output | fbusl.node.Input | fbusl.node.Uniform) -> str:
        qualifier = ""
        storage = ""
        layout = ""
        if isinstance(node, fbusl.node.Input):
            storage = "in"
            layout = f"layout(location = {self.input_index}) "
            self.input_index += 1
            if getattr(node, "qualifier", None):
                qualifier = node.qualifier + " "
        elif isinstance(node, fbusl.node.Output):
            storage = "out"
            layout = f"layout(location = {self.output_index}) "
            self.output_index += 1
            if getattr(node, "qualifier", None):
                qualifier = node.qualifier + " "
        elif isinstance(node, fbusl.node.Uniform):
            storage = "uniform"

        base_type, array_suffix = self.resolve_type(getattr(node, "type", None))

        decl = f"{node.name}{array_suffix}"
        text = ""
        if storage == 'uniform':
            if node.type.get('name') == 'texture' or (node.type.get('name') == 'array' and node.type.get('data').get('base_type', '') == 'texture'):
                uv_rect = f"{storage} vec4 _ENGINE_{node.name}_uv_rect{array_suffix};\n"
                text += uv_rect
            if node.type.get('name') == 'textureArray':
                uv_rect = f"{storage} vec4 _ENGINE_{node.name}_uv_rect[{fbusl.MAX_TEXTURE_ARRAY_SIZE}];"

        inout_text = ""
        inout_text += layout
        if qualifier:
            inout_text += qualifier
        inout_text += storage
        inout_text += f' {base_type} '
        inout_text += decl
        text += inout_text
        return text + ";\n"

    def generate_define(self, node: fbusl.node.Define) -> str:
        return f"#define {node.name} {self.generate_node(node.value)}\n"

    def generate_binop(self, node: fbusl.node.BinOp) -> str:
        left = self.generate_node(node.left)
        right = self.generate_node(node.right)
        return f"{left}{node.op}{right}"

    def generate_struct(self, node: fbusl.node.StructDef) -> str:
        fields_text = ""
        for field in node.fields:
            fields_text += "    " + self.format_var(field.name, field.type) + "\n"
        return f"struct {node.name} {{\n{fields_text}}};\n"

    def generate_member_access(self, node: fbusl.node.MemberAccess) -> str:
        base = self.generate_node(node.base)
        return f"{base}.{node.member}"

    def generate_function(self, node: fbusl.node.FunctionDef) -> str:
        param_texts = [
            self.format_var(p.name, p.type, qualifier="").rstrip(";")
            for p in node.params
        ]
        params_str = ", ".join(param_texts)
        body_str = "\n".join(f"    {self.generate_node(b)};" for b in node.body)
        return_type = self.get_glsl_type(node.type)
        return f"{return_type} {node.name}({params_str}) {{\n{body_str}\n}}\n"

    def generate_function_call(self, node: fbusl.node.FuncCall) -> str:
        impl_data = self.implementations.get(node.name)
        if impl_data and impl_data.get('kind') == 'function':
            call_template = impl_data.get('call')
            args_strs = [self.generate_node(arg) for arg in node.args]
            arg_types = [self.get_node_type(arg) for arg in node.args]
            print("ARG_TYPES: ", 
                  arg_types)
            if call_template:
                for cond_expr, template in call_template.items():
                    # parse conditions of the form "$args[i].type$==typename"
                    match = cond_expr.split("==")
                    if len(match) == 2:
                        left, right = match
                        left = left.strip()
                        right = right.strip()

                        if left.startswith("$args[") and left.endswith("].type$"):
                            idx = int(left[6:-7])
                            if idx < len(arg_types) and arg_types[idx] == right:
                                # condition matched, generate call
                                call_text = template
                                for i, arg_text in enumerate(args_strs):
                                    call_text = call_text.replace(f"$args[{i}]$", arg_text)
                                return call_text

                # fallback if no condition matches
                return f"{node.name}({', '.join(args_strs)})"

            # fallback if no 'call' entry
                return f"{node.name}({', '.join(args_strs)})"

            # fallback if no implementation
            return f"{node.name}({', '.join(args_strs)})"

    def format_var(self, name: str, type_annotation: dict | str | None, qualifier: str = "") -> str:
        base_type, array_suffix = self.resolve_type(type_annotation)
        decl = f"{base_type} {name}{array_suffix};"
        if qualifier:
            decl = f"{qualifier} {decl}"
        return decl

    def resolve_type(self, type_annotation: dict | str | None) -> tuple[str, str]:
        if type_annotation is None:
            return "void", ""

        if isinstance(type_annotation, str):
            impl_data = self.implementations.get(type_annotation)
            if impl_data and impl_data.get('kind') == 'type':
                return impl_data.get('replace', type_annotation), ""
            return type_annotation, ""

        if isinstance(type_annotation, dict):
            if type_annotation.get("name") == "array":
                length = type_annotation["data"]["length"]
                base_type, nested_suffix = self.resolve_type(type_annotation["data"]["base_type"])
                return base_type, nested_suffix + f"[{length}]"

            type_name = type_annotation.get("name", "unknown")
            impl_data = self.implementations.get(type_name)
            if impl_data and impl_data.get('kind') == 'type':
                return impl_data.get('replace', type_name), ""
            return type_name, ""

        return "unknown", ""

    def get_glsl_type(self, type_annotation: dict | str | None) -> str:
        base, _ = self.resolve_type(type_annotation)
        return base
    
    def get_node_type(self, node) -> str:
        if isinstance(node, fbusl.node.VarDecl):
            return self.get_glsl_type(node.type)
        elif isinstance(node, fbusl.node.Identifier):
            return self.get_glsl_type(node.type)
        elif isinstance(node, fbusl.node.Literal):
            return self.get_glsl_type(node.type)
        elif isinstance(node, fbusl.node.Setter):
            return self.get_node_type(node.value)
        elif isinstance(node, fbusl.node.BinOp):
            return self.get_binop_type(node.op, node.left, node.right, getattr(node, "pos", None))
        elif isinstance(node, fbusl.node.UnaryOp):
            return self.get_node_type(node.operand)

        elif isinstance(node, fbusl.node.MemberAccess):
            base_type = self.get_node_type(node.base)
            struct_def = self.types.get(base_type)
            if struct_def:
                field_type = struct_def.get("fields", {}).get(node.member)
                return self.get_glsl_type(field_type)
        elif isinstance(node, fbusl.node.FuncCall):
            fn = self.functions.get(node.name)
            if fn:
                return self.get_glsl_type(fn["type"])
        elif isinstance(node, fbusl.node.StructDef):
            return node.name
        elif hasattr(node, "type"):
            return self.get_glsl_type(node.type)
        return "unknown"

    def get_binop_type(self, op, left, right, pos) -> str:
        left_type = self.get_node_type(left)
        right_type = self.get_node_type(right)
        left_def = self.types.get(left_type, {})
        operations = left_def.get("operations", {})
        rules = operations.get(op, {})
        return rules.get(right_type)