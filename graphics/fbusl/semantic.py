from FreeBodyEngine.graphics.fbusl.ast_nodes import *
from FreeBodyEngine.graphics.fbusl import throw_error

class GenericVar:
    def __init__(self, name: str, type: str, value=None):
        self.name = name
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
        return "Output"

class Function:
    def __init__(self, name, return_type, pararms):
        self.name = name
        self.params = pararms
        self.return_type = return_type

    def __repr__(self):
        return "Function"

class FuncCall(Node):
    def __init__(self, pos, name, args):
        super().__init__(pos)
        self.name = name
        self.args = args
        

class StructCall(Node):
    def __init__(self, pos, name, args, ismat):
        super().__init__(pos)
        self.ismat = ismat
        self.name = name
        self.args = args

class Definition:
    def __init__(self, name, val):
        self.name = name
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
        throw_error(f"'{name}' not defined", pos, self.file_path)

    def __contains__(self, name: str):
        return name in self.symbols or (self.parent and name in self.parent)

class SemanticAnalyser:
    def __init__(self, tree: Tree, builtins: dict, file_path=None):
        self.tree = tree
        self.global_scope = Scope(file_path=file_path)
        self.current_scope = self.global_scope
        self.functions: dict[str, Function] = {}
        self.structs: dict[str, StructDecl] = {}

        self.file_path = file_path
        self.create_builtints(builtins)

    def create_builtints(self, builtins: dict):
        vars = builtins.get('vars', [])

        for var in vars:
            self.global_scope.define(Var(var, vars[var].get('type')))
        
        self.functions['round'] = (Function('round', 'float', {"x": "float"}))
        self.functions['texture'] = (Function('texture', 'vec4', {"sampler": 'sampler2D'}))
        

        # float vectors
        self.structs['vec2'] = (StructDecl(None, 'vec2', [StructField(None, 'x', 'float', None), StructField(None, 'y', 'float', None)]))
        self.structs['vec3'] = (StructDecl(None, 'vec3', [StructField(None, 'x', 'float', None), StructField(None, 'y', 'float', None), StructField(None, 'z', 'float', None)]))
        self.structs['vec4'] = (StructDecl(None, 'vec4', [StructField(None, 'x', 'float', None), StructField(None, 'y', 'float', None), StructField(None, 'z', 'float', None), StructField(None, 'w', 'float', None)]))


        # int vectors
        self.structs['ivec2'] = (StructDecl(None, 'ivec2', [StructField(None, 'x', 'int', None), StructField(None, 'y', 'int', None)]))
        self.structs['ivec3'] = (StructDecl(None, 'ivec3', [StructField(None, 'x', 'int', None), StructField(None, 'y', 'int', None), StructField(None, 'z', 'int', None)]))
        self.structs['ivec4'] = (StructDecl(None, 'ivec4', [StructField(None, 'x', 'int', None), StructField(None, 'y', 'int', None), StructField(None, 'z', 'int', None), StructField(None, 'w', 'int', None)]))

        # float matricies
        self.structs['mat2'] = (StructDecl(None, 'mat2', [StructField(None, 'col0', 'vec2', None), StructField(None, 'col1', 'vec2', None)]))
        self.structs['mat3'] = (StructDecl(None, 'mat3', [StructField(None, 'col0', 'vec3', None), StructField(None, 'col1', 'vec3', None), StructField(None, 'col2', 'vec3', None)]))
        self.structs['mat4'] = (StructDecl(None, 'mat4', [StructField(None, 'col0', 'vec4', None), StructField(None, 'col1', 'vec4', None), StructField(None, 'col2', 'vec4', None), StructField(None, 'col3', 'vec4', None)]))

    def analyse(self):
        for node in self.tree.children:
            self.check_for_func(node)
        for node in self.tree.children:
            self.analyse_node(node)
        return self.tree

    def check_for_func(self, node):
        if isinstance(node, FuncDecl):
            params = {}
            for param in node.params:
                params[param.name] = param.type
            self.functions[node.name] = Function(node.name, node.return_type, params)

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
                    throw_error(
                        f"Function '{node.name}' should return '{node.return_type}', not '{return_type}'",
                        node.pos, self.file_path
                    )
            self.analyse_node(stmt)

        self.current_scope = self.global_scope

    def analyse_call(self, node: Call):
        if node.name in self.functions.keys():
            index = self.tree.children.index(node)
            self.tree.children.remove(node)
            self.tree.children.insert(index, FuncCall(node.pos, node.name, node.args))

        struct = self.current_scope.lookup(node.name, node.pos) # throws error if not found
    
        index = self.tree.children.index(node)
        self.tree.children.remove(node)
        
        ismat = struct.type in ["mat2", "mat3", "mat4"]

        self.tree.children.insert(index, StructCall(node.pos, node.name, node.args, ismat))

    def analyse_field_identifier(self, node: MethodIdentifier):
        node.struct = node.struct

    def analyse_var(self, node: Node):
        if node.name in self.current_scope:
            throw_error(f"Variable '{node.name}' already defined in scope", node.pos, self.file_path)

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
        if isinstance(node, Set):
            if isinstance(node.ident, MethodIdentifier):
                struct_var = self.current_scope.lookup(node.ident.struct_name, node.pos)
                struct_type_name = struct_var.type
                if struct_type_name not in self.structs:
                    throw_error(f"'{struct_type_name}' is not a struct type", node.pos, self.file_path)
                struct_def = self.structs[struct_type_name]
                if node.ident.method_name not in struct_def.fields:
                    throw_error(f"Struct '{struct_type_name}' has no field '{node.ident.method_name}'", node.pos, self.file_path)
                expected_type = struct_def.fields[node.ident.method_name]
                value_type = self.get_node_type(node.value)
                if value_type != expected_type:
                    throw_error(f"Type mismatch: Cannot assign {value_type} to {expected_type}", node.pos, self.file_path)
            else:
                var = self.current_scope.lookup(node.ident.name, node.pos)
                if isinstance(var, (Output, Var)):
                    value_type = self.get_node_type(node.value)
                    if var.type != value_type:
                        throw_error(f"Type mismatch: Cannot assign {value_type} to {var.type}", node.pos, self.file_path)
                else:
                    throw_error(f"Cannot assign to {var.__repr__()}", node.pos, self.file_path)

    def analyse_struct(self, node: StructDecl):
        if node.name in self.structs:
            throw_error(f"Struct '{node.name}' already declared.", node.pos, self.file_path)

        field_map = {}
        for method in node.methods:
            if method.name in field_map:
                throw_error(f'Struct "{node.name}" already has field "{method.name}".', method.pos, self.file_path)
            field_map[method.name] = method.type

        node.fields = field_map
        self.structs[node.name] = node

    def analyse_expression(self, node: Expression):
        if isinstance(node, BinOp):
            left = self.get_node_type(node.left)
            right = self.get_node_type(node.right)
            if left != right:
                throw_error(f"Operator '{node.op}' not supported between types '{left}' and '{right}'", node.pos, self.file_path)

    def get_node_type(self, node: Node):
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
            return self.current_scope.lookup(node.name, node.pos).type
        elif isinstance(node, TypeCast):
            return node.type
        elif isinstance(node, TernaryExpression):
            return self.get_node_type(node.left)

        elif isinstance(node, Call):
            if node.name in self.functions.keys():
                return self.functions[node.name].return_type
            if node.name in self.structs.keys():
                return node.name
            else:
                throw_error(f"'{node.name}' not defined", node.pos, self.file_path)

    def get_field_type(self, node):
        struct_var = self.current_scope.lookup(node.struct_name, node.pos)
        struct_type_name = struct_var.type
        if struct_type_name not in self.structs:
            throw_error(f"'{struct_type_name}' is not a struct type", node.pos, self.file_path)
        struct_def = self.structs[struct_type_name]
        if node.method_name not in struct_def.fields:
            throw_error(f"Struct '{struct_type_name}' has no field '{node.method_name}'", node.pos, self.file_path)
        return struct_def.fields[node.method_name]

    def get_expression_type(self, node: Expression):
        if isinstance(node, BinOp):
            left = self.get_node_type(node.left)
            right = self.get_node_type(node.right)
            if left == right:
                return left
            throw_error(f"Operator '{node.op}' used between mismatched types '{left}' and '{right}'", node.pos, self.file_path)
