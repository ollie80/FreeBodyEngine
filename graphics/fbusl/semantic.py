from FreeBodyEngine.graphics.fbusl.ast_nodes import *

class GenericVar:
    def __init__(self, name: str, type: str, value = None):
        self.name = name
        self.type = type

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

class Definition:
    def __init__(self, name, val):self.name=name;self.val=val;
    def __repr__(self):
        return "Definition"

class SemanticAnalyser:
    def __init__(self, tree: Tree):
        self.tree = tree
        self.exsisting_vars: dict[str, Var] = {}
    
    def analyse(self):
        for node in self.tree.children:
            self.analyse_node(node)
        print("Semantics Passed Successfuly!")

    def analyse_node(self, node: Node):
        if isinstance(node, FuncDecl):
            self.analyse_function(node)
        if isinstance(node, (VarDecl, UniformDecl, InputDecl, OutputDecl, Define)):
            self.analyse_var(node)
        if isinstance(node, StructDecl):
            self.analyse_struct(node)
        if isinstance(node, (Set, SetMethod)):
            self.analyse_setter(node)
        if isinstance(node, Expression):
            self.analyse_expression(node)
    
    def var_exsists(self, ident: str):
        if ident not in self.exsisting_vars.keys(): raise NameError(f"No variable with name {ident}.")

    def analyse_setter(self, node: Node):
        if isinstance(node, Set):
            var_name = node.ident.name

            if isinstance(self.exsisting_vars[var_name], (Output, Var)):    
                self.var_exsists(var_name)

                set_type = self.get_node_type(node.value)
                var_type = self.exsisting_vars[var_name].type
                if set_type != var_type:

                    raise ValueError(f"Cannot set '{var_name}' with type '{var_type}' to type '{set_type}'")
            else:
                raise ValueError(f"Cannot set value of {self.exsisting_vars[var_name].__repr__()}")
    
    def analyse_struct(self, node: StructDecl):
        methods = []
        for method in node.methods:
            if method.name not in methods:
                methods.append(method.name)
            else:
                raise SyntaxError(f'Struct "{node.name}" already has method "{method.name}".')
            
    def analyse_var(self, node: Node):
        if node.name not in self.exsisting_vars.keys():
            if isinstance(node, UniformDecl):
                self.exsisting_vars[node.name] = Uniform(node.name, node.type)
            elif isinstance(node, InputDecl):
                self.exsisting_vars[node.name] = Input(node.name, node.type)
            elif isinstance(node, OutputDecl):
                self.exsisting_vars[node.name] = Output(node.name, node.type)
            elif isinstance(node, VarDecl):
                self.exsisting_vars[node.name] = Var(node.name, node.type, node.val)
            elif isinstance(node, Define):
                self.exsisting_vars[node.name] = Definition(node.name, node.val)
            
        else:
            raise SyntaxError(f"{self.exsisting_vars[node.name].__repr__()} '{node.name}' already exsists")
                

    def analyse_expression(self, node: Node):
        if isinstance(node, BinOp):
            left_type = self.get_node_type(node.left)
            right_type = self.get_node_type(node.right)
            if right_type != left_type:
                raise ValueError(f"Cannot use operator '{node.op}' between types of {left_type} and {right_type}")

    def get_node_type(self, node: Node):
        if isinstance(node, Expression):
            return self.get_expression_type(node)
        elif isinstance(node, Return):
            return self.get_return_type(node)    
        elif isinstance(node, Int):
            return "int"
        elif isinstance(node, Float):
            return "float"

    def get_expression_type(self, node: Expression):
        if isinstance(node, BinOp):
            left = self.get_node_type(node.left)
            right = self.get_node_type(node.right)
            if left == right:
                return self.get_node_type(node.right)
            else:
                raise ValueError(f"Cannot use operator '{node.op}' between types of '{left}' and '{right}'")

    def get_return_type(self, node: Return):
        return self.get_node_type(node.expr)

    def analyse_function(self, node: FuncDecl):
        for b_node in node.body:
            if isinstance(b_node, Return):
                b_node_return = self.get_return_type(b_node) 
                if b_node_return != node.return_type:
                    raise ValueError(f"Function does not return correct type of: '{node.return_type}', instead returning '{b_node_return}'")
            self.analyse_node(b_node)