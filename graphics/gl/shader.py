from FreeBodyEngine.graphics.fbusl.generator import Generator
from FreeBodyEngine.graphics.fbusl.ast_nodes import *
from FreeBodyEngine.graphics.shader import Shader

class GLShader(Shader):
    def __init__(self):
        pass


class GLGenerator(Generator):
    """
    GLSL implementation of the FBUSL code generator. 
    """
    def __init__(self, tree):
        self.tree = tree
        self.precisions = {"high": "highp", "med": "mediump", "low": "lowp"}
        self.default_precision = "high"
    
    def generate(self, default_precision="high") -> str:
        self.default_precision = default_precision
        string = ""
        string += "#version 330 core\n"

        for child in self.tree.children:
            string += str(self.generate_node(child))
        return string
    
    def generate_node(self, node: Node):
        if isinstance(node, UniformDecl):
            return self.generate_uniform(node)
        elif isinstance(node, InputDecl):
            return self.generate_input(node)
        elif isinstance(node, OutputDecl):
            return self.generate_output(node)
        elif isinstance(node, Define):
            return self.generate_definition(node)
        elif isinstance(node, Expression):
            return self.generate_expression(node)
        elif isinstance(node, FuncDecl):
            return self.generate_function(node)
        elif isinstance(node, (Int, Float)):
            return node.value
        elif isinstance(node, Set):
            return self.generate_set(node)
        elif isinstance(node, Return):
            return self.generate_return(node)
        elif isinstance(node, StructDecl):
            return self.generate_struct(node)
        elif isinstance(node, VarDecl):
            return self.generate_var(node)
        return None

    def generate_var(self, node: VarDecl):
        prec = f"{self.precisions[self.default_precision]}"
        if node.precision != None:
            prec = f"{self.precisions[node.precision]}"
        return f"\n {prec} {node.type} {node.name} = {self.generate_node(node.val)};\n"


    def generate_input(self, node: InputDecl) -> str:
        if node.precision != None:
            prec = f"{self.precisions[node.precision]}"
        return f"\nuniform {prec} {node.type} {node.name};\n"
    
    def generate_output(self, node: OutputDecl) -> str:
        prec = f"{self.precisions[self.default_precision]}"
        if node.precision != None:
            prec = f"{self.precisions[node.precision]}"
        return f"\nuniform {prec} {node.type} {node.name};\n"
    
    def generate_uniform(self, node: UniformDecl) -> str:
        prec = f"{self.precisions[self.default_precision]}"
        if node.precision != None:
            prec = f"{self.precisions[node.precision]}"
        return f"\nuniform {prec} {node.type} {node.name};\n"
    
    def generate_definition(self, node: Define) -> str:
        return f"#define {node.name} {node.val}\n"


    def generate_param(self, node: Param) -> str:
        return f"{node.type} {node.name}"     

    def generate_set(self, node: Set):
        return f"{node.ident.name} = {self.generate_node(node.value)}"

    def generate_return(self, node: Return):
        return f"return {self.generate_node(node.expr)}"            
    
    def generate_function(self, node: FuncDecl) -> str:
        r = "\n"
        params = ""
        i = 0
        for param in node.params:
            params += f"{param.type} {param.name}"
            if i < len(node.params) - 1:
                params += ", "  
            i += 1
        r += f"{node.return_type} {str(node.name)}({params})" + " {\n"
        
        for b_node in node.body:
            r += f"    {self.generate_node(b_node)};\n"
        r += "};"

        return r

    def generate_method(self, node: StructMethod):
        prec = ""
        if node.precision != None:
            prec = f"{self.precisions[node.precision]} "
        return f"   {prec}{node.type} {node.name};"

    def generate_struct(self, node: StructDecl) -> str:
        r = "\n"
        methods = ""
        for method in node.methods:
            methods += f"{self.generate_method(method)}\n"
        r += f"struct {node.name}" + " {\n"
        r += methods
        r += "};\n"
        
        return r


    def generate_expression(self, node: Expression) -> str:
        r = ""
        if isinstance(node, BinOp):
            left = self.generate_node(node.left)
            right = self.generate_node(node.right)
            r += str(left) + str(node.op) + str(right)
        return r
