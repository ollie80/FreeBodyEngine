from FreeBodyEngine.graphics.fbusl.generator import Generator
from FreeBodyEngine.graphics.fbusl.ast_nodes import *
from FreeBodyEngine.graphics.shader import Shader
from FreeBodyEngine.graphics.fbusl import compile as compile_fbusl
from FreeBodyEngine import error as fb_error
from OpenGL.GL import *
from dataclasses import dataclass
import numpy
from FreeBodyEngine.math import Vector, Vector3


@dataclass
class GLUniform:
    location: any
    size: int
    type: str

def create_shader_program(vertex_src, fragment_src):
    vertex_shader = compile_shader(vertex_src, GL_VERTEX_SHADER)
    fragment_shader = compile_shader(fragment_src, GL_FRAGMENT_SHADER)

    program = glCreateProgram()
    glAttachShader(program, vertex_shader)
    glAttachShader(program, fragment_shader)
    glLinkProgram(program)

    if glGetProgramiv(program, GL_LINK_STATUS) != GL_TRUE:
        error = glGetProgramInfoLog(program).decode()
        raise RuntimeError(f"Shader link error:\n{error}")

    glDeleteShader(vertex_shader)
    glDeleteShader(fragment_shader)

    return program

def compile_shader(source, shader_type):
    shader = glCreateShader(shader_type)
    print(source)
    glShaderSource(shader, source)
    glCompileShader(shader)

    if glGetShaderiv(shader, GL_COMPILE_STATUS) != GL_TRUE:
        error = glGetShaderInfoLog(shader).decode()
        raise RuntimeError(f"Shader compile error:\n{error}")

    return shader

def create_fbusl_shader(fbusl_source):
    return 


class GLShader(Shader):
    def __init__(self, vertex_source, fragment_source):
        compiled_vert = compile_fbusl(vertex_source, GLGenerator)
        compiled_frag = compile_fbusl(fragment_source, GLGenerator)
        print(compiled_vert)
        super().__init__(compiled_vert, compiled_frag)
        
        self._shader = create_shader_program(self.vertex_source, self.fragment_source)
        self.uniforms = self._shader
        
        self.uniforms: dict[str, GLUniform] = {}
        self.setup_uniforms()

    def setup_uniforms(self):
        count = glGetProgramiv(self._shader, GL_ACTIVE_UNIFORMS)

        for i in range(count):
            name, size, type = glGetActiveUniform(self._shader, i)
            location = glGetUniformLocation(self._shader, name)

            self.uniforms[name] = GLUniform(location, size, type)

    def check_val_type(self, val: str, type: str, name: str):
        if type == GL_INT:
            if isinstance(val, int):
                return

        elif type == GL_INT_VEC2:
            if isinstance(val, (tuple, list, Vector)):
                return

        elif type == GL_INT_VEC3:
            if isinstance(val, (tuple, list, Vector3)):
                return

        elif type == GL_INT_VEC4:
            if isinstance(val, (tuple, list)):
                return

        elif type == GL_FLOAT:
            if isinstance(val, (float, int)):
                return
            
        elif type == GL_FLOAT_VEC2:
            if isinstance(val, (tuple, list, Vector)):
                return

        elif type == GL_FLOAT_VEC3:
            if isinstance(val, (tuple, list, Vector3)):
                return

        elif type == GL_FLOAT_VEC4:
            if isinstance(val, (tuple, list)):
                return

        elif type == GL_FLOAT_MAT2:
            if isinstance(val, numpy.ndarray):
                return

        elif type == GL_FLOAT_MAT3:
            if isinstance(val, numpy.ndarray):
                return

        elif type == GL_FLOAT_MAT4:
            if isinstance(val, numpy.ndarray):
                return

        fb_error(f'Cannot set uniform "{name}" of type "{type}" to value of type "{val.__class__.__name__}"')

    def set_uniform(self, name: str, val: any):
        if name in self.uniforms.keys():
            uniform = self.get_uniform(name)
            type = uniform.type
            if type == GL_INT and self.check_val_type(val, type, name):
                glUniform1i(uniform.location, val)
                
            elif type == GL_FLOAT and self.check_val_type(val, type, name):
                glUniform1f(uniform.location, val)
            
            elif type == GL_BOOL and self.check_val_type(val, type, name):
                glUniform1f(uniform.location, val)
            
            elif type == GL_FLOAT_VEC2 and self.check_val_type(val, type, name):
                glUniform2f(uniform.location, val[0], val[1])
            
            elif type == GL_FLOAT_VEC3 and self.check_val_type(val, type, name):
                glUniform3f(uniform.location, val[0], val[1], val[2])
            
            elif type == GL_FLOAT_VEC4 and self.check_val_type(val, type, name):
                glUniform4f(uniform.location, val[0], val[1], val[2], val[3])
            
            elif type == GL_INT_VEC2 and self.check_val_type(val, type, name):
                glUniform2f(uniform.location, val[0], val[1])
            
            elif type == GL_INT_VEC3 and self.check_val_type(val, type, name):
                glUniform3f(uniform.location, val[0], val[1], val[2])
            
            elif type == GL_INT_VEC4 and self.check_val_type(val, type, name):
                glUniform4f(uniform.location, val[0], val[1], val[2], val[3])

            elif type == GL_FLOAT_MAT2 and self.check_val_type(val, type, name):
                glUniformMatrix2fv(uniform.location, val) # Matricies use numpy arrays
            
            elif type == GL_FLOAT_MAT3 and self.check_val_type(val, type, name):
                glUniformMatrix3fv(uniform.location, val)
            
            elif type == GL_FLOAT_MAT4 and self.check_val_type(val, type, name):
                glUniformMatrix4fv(uniform.location, val)
            
    def get_uniform(self, name: str):
        return self.uniforms[name]

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
        prec = f"{self.precisions[self.default_precision]}"
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

    def generate_method(self, node: StructField):
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
