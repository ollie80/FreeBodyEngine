from FreeBodyEngine.graphics.fbusl.ast_nodes import *
from FreeBodyEngine.graphics.fbusl import fbusl_error

class GenericVar:
    def __init__(self, name: Identifier | str, type: str, value=None):
        # Accept either an Identifier node or string for name
        if isinstance(name, Identifier):
            self.name = name.name
            self.ident = name
        else:
            self.name = name
            self.ident = Identifier(None, name)
        self.type = type
        self.value = value

    def __repr__(self):
        return "Variable"

class Var(GenericVar):
    pass

class Uniform(GenericVar):
    def __repr__(self):
        return "Uniform"

class Input(Uniform):
    def __repr__(self):
        return "Input"

class Output(Uniform):
    def __repr__(self):
        return f"Output({self.name} type={self.type})"

class Function:
    def __init__(self, name: Identifier | str, return_type, params):
        if isinstance(name, Identifier):
            self.name = name.name
            self.ident = name
        else:
            self.name = name
            self.ident = Identifier(None, name)
        self.params = params  # dict param_name -> type
        self.return_type = return_type

    def __repr__(self):
        return "Function"

class Struct:
    def __init__(self, name: str, attributes: list[dict[str, Type]]):
        self.name = Identifier(None, name)
        self.attributes = attributes

    def __repr__(self):
        return "Struct"

class FuncCall(Node):
    def __init__(self, pos, name: Identifier | str, args):
        super().__init__(pos)
        self.name = name
        self.args = args

class StructCall(Node):
    def __init__(self, pos, name: Identifier | str, args, ismat):
        super().__init__(pos)
        self.ismat = ismat
        self.name = name
        self.args = args

class Definition:
    def __init__(self, name: Identifier | str, val):
        if isinstance(name, Identifier):
            self.name = name.name
            self.ident = name
        else:
            self.name = name
            self.ident = Identifier(None, name)
        self.val = val

    def __repr__(self):
        return "Definition"

class Scope:
    def __init__(self, parent=None, file_path=None):
        self.symbols: dict[str, GenericVar] = {}
        self.parent: Scope | None = parent
        self.file_path = file_path

    def define(self, var: GenericVar):
        if var.name in self.symbols:
            raise SyntaxError(f"{var.__repr__()} '{var.name}' already exists in current scope.")
        self.symbols[var.name] = var

    def lookup(self, name: str, pos) -> GenericVar:
        if name in self.symbols:
            return self.symbols[name]
        if self.parent:
            return self.parent.lookup(name, pos)
        fbusl_error(f"'{name}' not defined", pos, self.file_path)

    def __contains__(self, name: str):
        return name in self.symbols or (self.parent and name in self.parent)

class SemanticAnalyser:
    def __init__(self, tree: Tree, builtins: dict, shader_type, file_path=None):
        self.tree = tree
        self.shader_type = shader_type
        self.global_scope = Scope(file_path=file_path)
        self.current_scope = self.global_scope
        self.functions: dict[str, Function] = {}
        self.structs: dict[str, StructDecl] = {}

        self.file_path = file_path
        self.create_builtins(builtins)

    def create_builtins(self, builtins: dict):
        vars = builtins.get('vars', {})
        outputs = builtins.get('outputs', {})

        for output_name, output_info in outputs.items():
            self.global_scope.define(Output(output_name, output_info.get('type')))
            
        for var_name, var_type in vars.items():
            self.global_scope.define(Var(var_name, var_type))
        
        float_type = Type(0, Identifier(0, "float"))
        int_type = Type(0, Identifier(0, "int"))

        self.functions['round'] = Function('round', Type(0, Identifier(0, float_type)), {"x": float_type})
        self.functions['clamp'] = Function('clamp', Type(0, Identifier(0, float_type)), {"x": float_type})
        self.functions['texture'] = Function('texture', Type(0, Identifier(0, 'vec4')), {"sampler": Type(0, Identifier(0, 'sampler2D')), "sample_pos": Type(0, Identifier(0, 'vec2'))})
        
        self.global_scope.define(Output("VERTEX_POSITION", Type(0, Identifier(0, 'vec4'))))
        if self.shader_type == "vert":
            self.global_scope.define(Output("INSTANCE_ID", Type(0, Identifier(0, 'int'))))

        # Vector structs
        vec2_type = Type(0, Identifier(0, 'vec2'))
        self.structs['vec2'] = StructDecl(None, vec2_type, [
            StructField(None, 'x', float_type, None),
            StructField(None, 'y', float_type, None)
        ])

        vec3_type = Type(0, Identifier(0, 'vec3'))
        self.structs['vec3'] = StructDecl(None, vec3_type, [
            StructField(None, 'x', float_type, None),
            StructField(None, 'y', float_type, None),
            StructField(None, 'z', float_type, None)
        ])

        vec4_type = Type(0, Identifier(0, 'vec4'))
        self.structs['vec4'] = StructDecl(None, vec4_type, [
            StructField(None, 'x', float_type, None),
            StructField(None, 'y', float_type, None),
            StructField(None, 'z', float_type, None),
            StructField(None, 'w', float_type, None)
        ])

        # Int vectors
        self.structs['ivec2'] = StructDecl(None, Type(0, Identifier(0, 'ivec2')), [
            StructField(None, 'x', int_type, None),
            StructField(None, 'y', int_type, None)
        ])
        self.structs['ivec3'] = StructDecl(None, Type(0, Identifier(0, 'ivec3')), [
            StructField(None, 'x', int_type, None),
            StructField(None, 'y', int_type, None),
            StructField(None, 'z', int_type, None)
        ])
        self.structs['ivec4'] = StructDecl(None, Type(0, Identifier(0, 'ivec4')), [
            StructField(None, 'x', int_type, None),
            StructField(None, 'y', int_type, None),
            StructField(None, 'z', int_type, None),
            StructField(None, 'w', int_type, None)
        ])

        # Matrices  
        self.structs['mat2'] = StructDecl(None, Type(0, Identifier(0, 'mat2')), [
            StructField(None, 'col0', vec2_type, None),
            StructField(None, 'col1', vec2_type, None)
        ])
        self.structs['mat3'] = StructDecl(None, Type(0, Identifier(0, 'mat3')), [
            StructField(None, 'col0', vec3_type, None),
            StructField(None, 'col1', vec3_type, None),
            StructField(None, 'col2', vec3_type, None)
        ])
        self.structs['mat4'] = StructDecl(None, Type(0, Identifier(0, 'mat4')), [
            StructField(None, 'col0', vec4_type, None),
            StructField(None, 'col1', vec4_type, None),
            StructField(None, 'col2', vec4_type, None),
            StructField(None, 'col3', vec4_type, None)
        ])

    def analyse(self):
        for node in self.tree.children:
            if isinstance(node, FuncDecl):
                self.check_for_func(node)
            if isinstance(node, StructDecl):
                self.check_for_struct(node)

        for node in self.tree.children:
            self.analyse_node(node)

        return self.tree

    def check_for_func(self, node: FuncDecl):
        params = {}
        for param in node.params:
            params[param.name] = param.type
        self.functions[node.name.name] = Function(node.name, node.return_type, params)

    def check_for_struct(self, node: StructDecl):
        attributes = {}
        for attr in node.methods:
            attributes[attr.name.name] = attr.type
        self.structs[node.name.name] = Struct(node.name, attributes)


    def analyse_node(self, node: Node):
        if isinstance(node, FuncDecl):
            self.analyse_function(node)
        elif isinstance(node, (VarDecl, UniformDecl, InputDecl, OutputDecl, Define)):
            self.analyse_var(node)
        elif isinstance(node, StructDecl):
            self.analyse_struct(node)
        elif isinstance(node, (Set, SetMethod)):
            self.analyse_setter(node)
        elif isinstance(node, Expression):
            self.analyse_expression(node)
        elif isinstance(node, Return):
            self.analyse_node(node.expr)


    def analyse_function(self, node: FuncDecl):
        function_scope = Scope(self.global_scope)
        self.current_scope = function_scope

        for param in node.params:
            param_var = Var(param.name, param.type)
            self.current_scope.define(param_var)

        for stmt in node.body:
            if isinstance(stmt, Return):
                return_type = self.get_node_type(stmt)
                if return_type != node.return_type:
                    fbusl_error(
                        f"Function '{node.name.name}' should return '{node.return_type}', not '{return_type}'",
                        node.pos, self.file_path
                    )
            self.analyse_node(stmt)

        self.current_scope = self.global_scope

    def analyse_var(self, node: Node):
        var_name = node.name.name if hasattr(node, "name") and isinstance(node.name, Identifier) else node.name
        if var_name in self.current_scope:
            fbusl_error(f"Variable '{var_name}' already defined in scope", node.pos, self.file_path)

        if isinstance(node, Define):
            value_type = self.get_node_type(node.val)
            var = Definition(node.name, node.val)
            var.type = value_type
        else:
            var_class = {
                VarDecl: Var,
                UniformDecl: Uniform,
                InputDecl: Input,
                OutputDecl: Output,
            }.get(type(node), Var)
            var = var_class(node.name, node.type)
            
        self.current_scope.define(var)

    def analyse_setter(self, node: Node):
        if isinstance(node.ident, MethodIdentifier):
            struct_var = self.current_scope.lookup(node.ident.struct, node.pos)
            struct_type_name = struct_var.type
            if struct_type_name not in self.structs:
                fbusl_error(f"'{struct_type_name}' is not a struct type", node.pos, self.file_path)
            struct_def = self.structs[struct_type_name]

            if node.ident.method_name not in struct_def.fields:
                fbusl_error(f"Struct '{struct_type_name}' has no field '{node.ident.method_name}'", node.pos, self.file_path)

            expected_type = struct_def.fields[node.ident.method_name]
            value_type = self.get_node_type(node.value)
            if value_type != expected_type:
                
                fbusl_error(f"Type mismatch: Cannot assign {value_type} to {expected_type}", node.pos, self.file_path)

        else:
            var = self.current_scope.lookup(node.ident.name, node.pos)
            if isinstance(var, (Output, Var)):
                value_type = self.get_node_type(node.value)
                if var.type != value_type:
                    fbusl_error(f"Type mismatch: Cannot assign {value_type} to {var.type}", node.pos, self.file_path)
            else:
                fbusl_error(f"Cannot assign to {var.__repr__()}", node.pos, self.file_path)

    def analyse_struct(self, node: StructDecl):
        struct_name = node.name.name if isinstance(node.name, Identifier) else node.name
        if struct_name in self.structs:
            fbusl_error(f"Struct '{struct_name}' already declared.", node.pos, self.file_path)

        field_map = {}
        for method in node.methods:
            if method.name in field_map:
                fbusl_error(f'Struct "{struct_name}" already has field "{method.name}".', method.pos, self.file_path)
            field_map[method.name] = method.type

        node.fields = field_map
        self.structs[struct_name] = node

    def analyse_expression(self, node: Expression):
        if isinstance(node, BinOp):
            left = self.get_node_type(node.left)
            right = self.get_node_type(node.right)
            if left != right:
                fbusl_error(f"Operator '{node.op}' not supported between types '{left}' and '{right}'", node.pos, self.file_path)

    def get_node_type(self, node: Node)->Type:
        if isinstance(node, Expression):
            return self.get_expression_type(node)
        elif isinstance(node, Return):
            return self.get_node_type(node.expr)
        elif isinstance(node, Int):
            return "int"
        elif isinstance(node, Float):
            return "float"
        elif isinstance(node, MethodIdentifier):
            return self.get_field_type(node)
        elif isinstance(node, Identifier):
            var = self.current_scope.lookup(node.name, node.pos)
            return var.type
        elif isinstance(node, Get):
            if not node.array_access:
                var = self.current_scope.lookup(node.name.name, node.pos)
                return var.type
            else:
                var = self.current_scope.lookup(node.name.name, node.pos)
                return var.type.base_type()
        elif isinstance(node, MethodGet):
            if not node.array_access:
                struct = self.structs.get(node.struct_name)
                return struct.methods.get(node.name.name)
            
            else:
                struct = self.structs.get(node.struct_name)
                return struct.methods.get(node.name.name).base_type()

        
        elif isinstance(node, TypeCast):
            return node.type
        elif isinstance(node, TernaryExpression):
            return self.get_node_type(node.left)
        elif isinstance(node, Call):
            call_name = node.name.name if isinstance(node.name, Identifier) else node.name
            if call_name in self.functions:
                return self.functions[call_name].return_type
            if call_name in self.structs:
                
                return Type(node.pos, Identifier(node.pos, call_name))
            
            fbusl_error(f"'{call_name}' not defined", node.pos, self.file_path)
        else:
            fbusl_error(f"Cannot determine type of node {type(node).__name__}", getattr(node, 'pos', None), self.file_path)


    def get_field_type(self, node: MethodGet):
        struct_var = self.current_scope.lookup(node.struct, node.pos)
        struct_type_name = struct_var.type

        if struct_type_name not in self.structs:
            fbusl_error(f"'{struct_type_name}' is not a struct type", node.pos, self.file_path)
        
        struct_def = self.structs[struct_type_name]
        
        if node.method_name not in struct_def.fields:
            fbusl_error(f"Struct '{struct_type_name}' has no field '{node.method_name}'", node.pos, self.file_path)
        
        return struct_def.fields[node.method_name]

    def get_expression_type(self, node: Expression):
        if isinstance(node, BinOp):
            left = self.get_node_type(node.left)
            right = self.get_node_type(node.right)
            for i in range(2, 5):
                if left.name.name == f'mat{i}' and right.name.name == f'vec{i}':
                    return Type(node.pos, Identifier(node.pos, f'vec{i}'))
            
            if left == right:
                return left
            
            fbusl_error(f"Operator '{node.op}' used between mismatched types '{left}' and '{right}'", node.pos, self.file_path)
        
        elif isinstance(node, FuncCall):
            call_name = node.name.name if isinstance(node.name, Identifier) else node.name
            if call_name in self.functions:
                return self.functions[call_name].return_type
            fbusl_error(f"Function '{call_name}' not defined", node.pos, self.file_path)

        elif isinstance(node, StructCall):
            struct_name = node.name.name if isinstance(node.name, Identifier) else node.name
            if struct_name in self.structs:
                return struct_name
            fbusl_error(f"Struct '{struct_name}' not defined", node.pos, self.file_path)

        elif isinstance(node, Identifier):
            var = self.current_scope.lookup(node.name, node.pos)
            return var.type

        elif isinstance(node, MethodIdentifier):
            return self.get_field_type(node)

        elif isinstance(node, Int):
            return "int"

        elif isinstance(node, Float):
            return "float"

        elif isinstance(node, Bool):
            return "bool"

        elif isinstance(node, TypeCast):
            return node.type

        elif isinstance(node, TernaryExpression):
            left_type = self.get_node_type(node.left)
            right_type = self.get_node_type(node.right)
            if left_type != right_type:
                fbusl_error(f"Ternary branches have mismatched types '{left_type}' and '{right_type}'", node.pos, self.file_path)
            return left_type

        else:
            fbusl_error(f"Unknown expression type: {type(node).__name__}", getattr(node, 'pos', None), self.file_path)
