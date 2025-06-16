from FreeBodyEngine.graphics.fbusl.ast_nodes import *

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
    def __init__(self, name, return_type):
        self.name = name
        self.return_type = return_type

    def __repr__(self):
        return "Function"

class Definition:
    def __init__(self, name, val):
        self.name = name
        self.val = val

    def __repr__(self):
        return "Definition"


class Scope:
    def __init__(self, parent=None):
        self.symbols: dict[str, GenericVar] = {}
        self.parent: Scope | None = parent

    def define(self, var: GenericVar):
        if var.name in self.symbols:
            raise SyntaxError(f"{var.__repr__()} '{var.name}' already exists in current scope.")
        self.symbols[var.name] = var

    def lookup(self, name: str) -> GenericVar:
        if name in self.symbols:
            return self.symbols[name]
        if self.parent:
            return self.parent.lookup(name)
        raise NameError(f"No variable with name '{name}'.")

    def __contains__(self, name: str):
        return name in self.symbols or (self.parent and name in self.parent)


class SemanticAnalyser:
    def __init__(self, tree: Tree, file_path=None):
        self.tree = tree
        self.global_scope = Scope()
        self.current_scope = self.global_scope
        self.functions: dict[str, Function] = {}
        self.file_path = file_path

    def analyse(self):
        for node in self.tree.children:
            self.check_for_func(node)
        for node in self.tree.children:
            self.analyse_node(node)
        print("Semantics Passed Successfully!")

    def check_for_func(self, node):
        if isinstance(node, FuncDecl):
            self.functions[node.name] = Function(node.name, node.return_type)

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
        # Enter a new function scope
        function_scope = Scope(self.global_scope)
        self.current_scope = function_scope

        # Add parameters to the scope
        for param in node.params:
            param_var = Var(param.name, param.type)
            self.current_scope.define(param_var)

        # Analyse function body
        for stmt in node.body:
            if isinstance(stmt, Return):
                return_type = self.get_node_type(stmt)
                if return_type != node.return_type:
                    raise ValueError(
                        f"Function '{node.name}' should return '{node.return_type}', not '{return_type}'."
                    )
            self.analyse_node(stmt)

        # Restore global scope
        self.current_scope = self.global_scope

    def analyse_var(self, node: Node):
        if node.name in self.current_scope:
            raise SyntaxError(f"Variable '{node.name}' already defined in scope.")

        if isinstance(node, Define):
            value_type = self.get_node_type(node.val)
            var = Definition(node.name, node.val)
            var.type = value_type  # Attach inferred type
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
            var = self.current_scope.lookup(node.ident.name)
            if isinstance(var, (Output, Var)):
                value_type = self.get_node_type(node.value)
                if var.type != value_type:
                    raise ValueError(f"Type mismatch: Cannot assign {value_type} to {var.type}")
            else:
                raise ValueError(f"Cannot assign to {var.__repr__()}")

    def analyse_struct(self, node: StructDecl):
        seen = set()
        for method in node.methods:
            if method.name in seen:
                raise SyntaxError(f'Struct "{node.name}" already has method "{method.name}".')
            seen.add(method.name)

    def analyse_expression(self, node: Expression):
        if isinstance(node, BinOp):
            left = self.get_node_type(node.left)
            right = self.get_node_type(node.right)
            if left != right:
                raise ValueError(f"Operator '{node.op}' not supported between types '{left}' and '{right}'")

    def get_node_type(self, node: Node):
        if isinstance(node, Expression):
            return self.get_expression_type(node)
        elif isinstance(node, Return):
            return self.get_node_type(node.expr)
        elif isinstance(node, Int):
            return "int"
        elif isinstance(node, Float):
            return "float"
        elif isinstance(node, Identifier):
            return self.current_scope.lookup(node.name).type
        elif isinstance(node, FuncCall):
            return self.functions[node.name].return_type

    def get_expression_type(self, node: Expression):
        if isinstance(node, BinOp):
            left = self.get_node_type(node.left)
            right = self.get_node_type(node.right)
            if left == right:
                return left
            raise ValueError(f"Operator '{node.op}' used between mismatched types '{left}' and '{right}'")
