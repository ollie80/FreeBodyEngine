from FreeBodyEngine.graphics.fbusl.generator import Generator
from FreeBodyEngine.graphics.fbusl.ast_nodes import *
from FreeBodyEngine.graphics.fbusl.semantic import SemanticAnalyser 
from FreeBodyEngine.graphics.shader import Shader
from FreeBodyEngine.math import Vector, Vector3
from FreeBodyEngine import error as fb_error
from FreeBodyEngine.graphics.gl33.image import Image
from FreeBodyEngine.graphics.texture import Texture
from OpenGL.GL import *
import numpy as np
from FreeBodyEngine.graphics.color import Color

from dataclasses import dataclass
import numpy
from typing import Union

GL_TYPE_NAMES = {
    GL_INT: "int",
    GL_INT_VEC2: "ivec2",
    GL_INT_VEC3: "ivec3",
    GL_INT_VEC4: "ivec4",
    GL_FLOAT: "float",
    GL_FLOAT_VEC2: "vec2",
    GL_FLOAT_VEC3: "vec3",
    GL_FLOAT_VEC4: "vec4",
    GL_FLOAT_MAT2: "mat2",
    GL_FLOAT_MAT3: "mat3",
    GL_FLOAT_MAT4: "mat4",
    GL_BOOL: "bool",
    GL_SAMPLER_2D: "sampler2D",
}

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

    return program

def compile_shader(source, shader_type):
    shader = glCreateShader(shader_type)
    glShaderSource(shader, source)
    glCompileShader(shader)

    if glGetShaderiv(shader, GL_COMPILE_STATUS) != GL_TRUE:
        error = glGetShaderInfoLog(shader).decode()
        raise RuntimeError(f"Shader compile error:\n{error}")

    return shader


class GLShader(Shader):
    def __init__(self, vertex_source, fragment_source, injector):
        
        super().__init__(vertex_source, fragment_source, GLGenerator, injector)
        self._shader = create_shader_program(self.vertex_source, self.fragment_source)
        self.uniforms = self._shader
        
        self.uniforms: dict[str, GLUniform] = {}
        self.setup_uniforms()

        self.uniform_cache: dict[str, any] = {}
        
        for name in self.uniforms:
            self.uniform_cache[name] = None
                

    def setup_uniforms(self):
        count = glGetProgramiv(self._shader, GL_ACTIVE_UNIFORMS)

        for i in range(count):
            name, size, type = glGetActiveUniform(self._shader, i)
            name = name.tobytes().decode('utf-8').rstrip('\x00')
            location = glGetUniformLocation(self._shader, name)


            self.uniforms[name] = GLUniform(location, size, type)

    def check_val_type(self, val: any, gl_type: int, name: str) -> bool:

        def is_vec_of_length(obj, length, types=(int, float)):
            if isinstance(obj, (tuple, list, np.ndarray)) and len(obj) == length and all(isinstance(x, types) for x in obj):
                return True
            
            elif isinstance(obj, Color) and length >= 3:
                return True

            elif isinstance(obj, Vector) and length == 2:
                return True

            elif isinstance(obj, Vector3) and length == 3:
                return True


        if gl_type == GL_INT:
            if isinstance(val, int):
                return True

        elif gl_type == GL_INT_VEC2:
            if is_vec_of_length(val, 2, types=(int,)):
                return True

        elif gl_type == GL_INT_VEC3:
            if is_vec_of_length(val, 3, types=(int,)):
                return True

        elif gl_type == GL_INT_VEC4:
            return is_vec_of_length(val, 4, types=(int,))                
            
        elif gl_type == GL_BOOL:
            return isinstance(val, bool)
                

        elif gl_type == GL_FLOAT:
            return isinstance(val, (float, int))

        elif gl_type == GL_FLOAT_VEC2:
            if is_vec_of_length(val, 2):
                return True

        elif gl_type == GL_FLOAT_VEC3:
            if is_vec_of_length(val, 3):
                return True

        elif gl_type == GL_FLOAT_VEC4:
            if is_vec_of_length(val, 4):
                return True

        elif gl_type == GL_FLOAT_MAT2:
            if isinstance(val, np.ndarray) and val.shape == (2, 2):
                return True

        elif gl_type == GL_FLOAT_MAT3:
            if isinstance(val, np.ndarray) and val.shape == (3, 3):
                return True

        elif gl_type == GL_FLOAT_MAT4:
            if isinstance(val, np.ndarray) and val.shape == (4, 4):
                return True

        elif gl_type == GL_SAMPLER_2D:
            if isinstance(val, (int, Image)):
                return True

        fb_error(f'Cannot set uniform "{name}" of type "{GL_TYPE_NAMES.get(gl_type, "Unknown")}" to value of type "{type(val).__name__}"')
        return False


    def set_uniform(self, name: str, val: any):
        if name not in self.uniforms:
            fb_error(f"Uniform '{name}' not found in shader")
            return
        
        cached_val = self.uniform_cache[name] 
        if (not isinstance(val, np.ndarray)) and (not isinstance(cached_val, np.ndarray)):
            if cached_val == val:
                return
        else:
            if np.array_equal(val, cached_val):
                return


        self.uniform_cache[name] = val

        uniform = self.get_uniform(name)
        gl_type = uniform.type
        loc = uniform.location

        glUseProgram(self._shader)

        if not self.check_val_type(val, gl_type, name):
            return

        if gl_type == GL_INT:
            glUniform1i(loc, val)

        elif gl_type == GL_BOOL:
            glUniform1i(loc, int(val))

        elif gl_type == GL_FLOAT:
            glUniform1f(loc, float(val))

        elif gl_type == GL_INT_VEC2:
            glUniform2iv(loc, 1, val)

        elif gl_type == GL_INT_VEC3:
            glUniform3iv(loc, 1, val)

        elif gl_type == GL_INT_VEC4:
            glUniform4iv(loc, 1, val)

        elif gl_type == GL_FLOAT_VEC2:
            glUniform2f(loc, val[0], val[1])

        elif gl_type == GL_FLOAT_VEC3:
            if isinstance(val, Color):
                fn = val.float_normalized
                v0 = fn[0]
                v1 = fn[1]
                v2 = fn[2]
            else:
                v0 = val[0]
                v1 = val[1]
                v2 = val[2]
            
            glUniform3f(loc, v0, v1, v2)

        elif gl_type == GL_FLOAT_VEC4:
            
            if isinstance(val, Color):
                fn = val.float_normalized_a
                v0 = fn[0]
                v1 = fn[1]
                v2 = fn[2]
                v3 = fn[3]    
            else:
                v0 = val[0]
                v1 = val[1]
                v2 = val[2]
                v3 = val[3]
            
            glUniform4f(loc, v0, v1, v2, v3)

        elif gl_type == GL_FLOAT_MAT2:
            glUniformMatrix2fv(loc, 1, GL_FALSE, val)

        elif gl_type == GL_FLOAT_MAT3:
            glUniformMatrix3fv(loc, 1, GL_FALSE, val)

        elif gl_type == GL_FLOAT_MAT4:
            glUniformMatrix4fv(loc, 1, GL_FALSE, val)

        elif gl_type == GL_SAMPLER_2D:
            if not isinstance(val, Image):
                glUniform1i(loc, val)

    def get_uniform(self, name: str):
        return self.uniforms[name]

    def use(self):
        for name in self.uniforms: # reload texture slots
            if self.uniforms[name].type == GL_SAMPLER_2D:
                img = self.uniform_cache[name]
                if img != None and isinstance(img, Image):
                    glUniform1i(self.uniforms[name].location, img.texture.use())
                if img != None and isinstance(img, Texture):
                    glUniform1i(self.uniforms[name].location, img.use())

        glUseProgram(self._shader)
        

class GLGenerator(Generator):
    """
    GLSL implementation of the FBUSL code generator. 
    """
    def __init__(self, tree, analyser: SemanticAnalyser):
        self.tree: Tree = tree
        self.analyser = analyser
        self.precisions = {"high": "highp", "med": "mediump", "low": "lowp"}
        self.default_precision = "high"
        self.input_index = -1
        self.output_index = -1

    def generate(self, default_precision="high") -> str:
        self.default_precision = default_precision
        string = "#version 330 core\n"

        for child in self.tree.children:
            string += str(self.generate_node(child))
        return string
    
    def generate_node(self, node: Node):
        if isinstance(node, UniformDecl):
            return self.generate_uniform(node)
        
        elif isinstance(node, InputDecl):
            return self.generate_input(node)
        
        elif isinstance(node, (Int, Float)):
            return str(node.value)
        
        elif isinstance(node, OutputDecl):
            return self.generate_output(node)
        
        elif isinstance(node, Define):
            return self.generate_definition(node)
        
        elif isinstance(node, Expression):
            return self.generate_expression(node)
        
        elif isinstance(node, FuncDecl):
            return self.generate_function(node)
        
        elif isinstance(node, Set):
            return self.generate_set(node)
        
        elif isinstance(node, Return):
            return self.generate_return(node)
        
        elif isinstance(node, StructDecl):
            return self.generate_struct(node)
        
        elif isinstance(node, VarDecl):
            return self.generate_var(node)

        elif isinstance(node, MethodIdentifier):
            return self.generate_field_identifier(node)

        elif isinstance(node, Identifier):
            return self.generate_identifier(node)
        
        elif isinstance(node, (IfStatement, ElseStatement)):
            return self.generate_if_statement(node)
        
        elif isinstance(node, TernaryExpression):
            return self.generate_ternary_expression(node)
        
        elif isinstance(node, Condition):
            return self.generate_condition(node)

        elif isinstance(node, TypeCast):
            return self.generate_typecast(node)

        elif isinstance(node, Call):
            return self.generate_call(node)



        return None
    
    def generate_call(self, node: Call):
        s = ""
        for i, arg in enumerate(node.args):
            s += self.generate_node(arg.val)
            if i < len(node.args) - 1:
                s += ', '
        return f"{node.name}({s})"

    def generate_identifier(self, node: Identifier):
        if node.name == "VERTEX_POSITION":
            s = "gl_Position"
        else:
            s = node.name
        
        return f"{s}"
    
    def generate_field_identifier(self, node: MethodIdentifier):        
        if node.struct:
            return f"{self.generate_node(node.struct)}.{node.method_name}"
        else:
            return f"{self.generate_node(node.struct)}[{node.method_name}]"

    def generate_var(self, node: VarDecl):
        prec = f"{node.precision} " if node.precision else ""
        return f"{prec}{node.type} {self.generate_node(node.name)} = {self.generate_node(node.val)}"

    def generate_input(self, node: InputDecl) -> str:
        self.input_index += 1
        prec = f" {node.precision} " if node.precision else " "
        return f"\nlayout(location = {self.input_index}) in{prec}{node.type} {node.name.name};\n"
    
    def generate_output(self, node: OutputDecl) -> str:
        self.output_index += 1
        prec = f" {node.precision} " if node.precision else " "
        return f"\nlayout(location = {self.output_index}) out{prec}{node.type} {node.name.name};\n"
    
    def generate_uniform(self, node: UniformDecl) -> str:
        prec = f" {node.precision} " if node.precision else " "
        return f"\nuniform{prec}{node.type} {node.name.name};\n"
    
    def generate_definition(self, node: Define) -> str:
        return f"#define {self.generate_node(node.name)} {self.generate_node(node.val)}\n"

    def generate_param(self, node: Param) -> str:
        return f"{node.type} {node.name}"

    def generate_set(self, node: Set):
        return f"{self.generate_node(node.ident)} = {self.generate_node(node.value)}"

    def generate_return(self, node: Return):
        return f"return {self.generate_node(node.expr)}"            
    
    def generate_if_statement(self, node: Union[IfStatement, ElseStatement]):
        body = ""
        for b_node in node.body:
            body += f"    {self.generate_node(b_node)};\n"

        if isinstance(node, ElseIfStatement):
            return f"else if ({self.generate_node(node.condition)})" + "{\n" + body + "    }"

        elif isinstance(node, IfStatement):
            return f"if ({self.generate_node(node.condition)})" + "{\n" + body + "    }"

        else:
            return "else {\n" + body + "    }"
    
    def generate_condition(self, node: Condition):
        return f"{self.generate_node(node.left)} {node.comparison} {self.generate_node(node.right)}"

    def generate_ternary_expression(self, node: TernaryExpression):
        return f"{self.generate_node(node.condition)} ? {self.generate_node(node.left)} : {self.generate_node(node.right)}"

    def generate_function(self, node: FuncDecl) -> str:
        r = "\n"
        params = ""
        for i, param in enumerate(node.params):
            params += f"{param.type} {param.name}"
            if i < len(node.params) - 1:
                params += ", "

        return_type = node.return_type if node.return_type is not None else "void"
        r += f"{return_type} {node.name.name}({params})" + " {\n"
        
        for b_node in node.body:
            r += f"    {self.generate_node(b_node)};\n"
        r += "};"

        return r

    def generate_typecast(self, node: TypeCast):
        return f"{node.type}({self.generate_node(node.target)})"

    def generate_method(self, node: StructField):
        prec = f"{self.precisions[node.precision]} " if node.precision else ""
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
