# Simple Shader Language Compiler: Lexer + Parser

from typing import List
import re
from FreeBodyEngine.graphics.fbusl.ast_nodes import *
from FreeBodyEngine.graphics.fbusl import throw_error

class Token:
    def __init__(self, kind: str, value, pos: int):
        self.kind = kind
        self.value = value
        self.pos = pos
    def __repr__(self):
        return f"Token({self.kind}, {repr(self.value)})"

TOKEN_TYPES = [
    ("ARROW", r"->"),
    ("DECORATOR", r"@(?:uniform|input|output|define)"),
    ("PRECISION", r"(low|med|high)"),
    ("KEYWORD", r"\b(def|return|struct)\b"),
    ("TYPE", r"\b(void|float|int|vec2|vec3|bool|vec4|mat2|mat3|mat4|struct)\b"),
    ("IDENT", r"[a-zA-Z_][a-zA-Z0-9_]*"),
    ("FLOAT", r"\d+\.\d+"),
    ("INT", r"\d+"),
    ("SYMBOL", r"[{}():,\.]"),
    ("OPERATOR", r"(\+=|-=|\*=|/=|=|\+|-|\*|/)"),
    ("WHITESPACE", r"[ \t]+"),
    ("COMMENT", r"#.*"),
]
def tokenize(code: str, file_path) -> List[Token]:
    tokens = []
    indent_stack = [0]
    lines = code.splitlines()

    for line_num, line in enumerate(lines, start=1):
        # Skip empty or comment-only lines
        if re.match(r"^\s*$", line) or re.match(r"^\s*#", line):
            continue

        # Handle indentation
        indent_match = re.match(r"[ \t]*", line)
        indent_str = indent_match.group(0)
        indent = len(indent_str.replace('\t', '    '))  # convert tabs to spaces

        if indent > indent_stack[-1]:
            tokens.append(Token("INDENT", indent, pos=line_num))
            indent_stack.append(indent)
        elif indent < indent_stack[-1]:
            while indent < indent_stack[-1]:
                indent_stack.pop()
                tokens.append(Token("DEDENT", indent_stack[-1], pos=line_num))
            if indent != indent_stack[-1]:
                throw_error(f"Inconsistent indentation: expected {indent_stack[-1]}, got {indent}", line_num, file_path)

        # Tokenize the line
        pos = len(indent_str)
        line_length = len(line)
        while pos < line_length:
            for kind, pattern in TOKEN_TYPES:
                match = re.match(pattern, line[pos:])
                if match:
                    value = match.group(0)
                    if kind == "WHITESPACE":
                        pos += len(value)
                        break
                    elif kind == "COMMENT":
                        pos = line_length  # skip the rest of the line
                        break
                    else:
                        token = Token(kind, value, pos=line_num)
                        tokens.append(token)
                        pos += len(value)
                        break
            else:
                throw_error(f"Unexpected character {line[pos]!r}", line_num, file_path)

        tokens.append(Token("NEWLINE", "\\n", pos=line_num))

    # Close remaining indents
    while len(indent_stack) > 1:
        indent_stack.pop()
        tokens.append(Token("DEDENT", indent_stack[-1], pos=line_num + 1))

    return tokens

class FBUSLParser:
    """Parses FBUSL code into an AST."""
    def __init__(self, tokens, file_path):
        self.tokens: list[Token] = tokens
        self.index = 0
        self.file_path = file_path


    def peek(self) -> Token:
        return self.tokens[self.index]

    def expect(self, kind: str, value: str = None):

        tok = self.peek()

        if value != None:
            if tok.value != value:
                throw_error(f"Expected token of kind '{kind}' with value of {value}, instead got '{tok.kind}' '{tok.value}'.", tok.pos, self.file_path)
        
        if tok.kind != kind:
            throw_error(f"Expected token of kind '{kind}', instead got kind '{tok.kind}' ", tok.pos, self.file_path)
    
        self.consume()
        return tok

    def consume(self):
        tok = self.peek()
        self.index += 1
        return tok

    def parse(self) -> Tree:
        tree = Tree()
        while self.index < len(self.tokens):
            tree.children.append(self.parse_next())
        for node in tree.children:
            if node == None:
                tree.children.remove(node)
        return tree    

    def parse_next(self) -> Node:
        tok = self.peek()
        if tok.kind == "NEWLINE":
            self.consume()
        if tok.kind == "KEYWORD":
            if tok.value == "def":
                return self.parse_function()
            
            elif tok.value == "struct":
                return self.parse_struct()

            elif tok.value == 'return':
                return self.parse_return()
            
        elif tok.kind == "PRECISION" or tok.kind == "IDENT":
            return self.parse_var()
        
        elif tok.kind == "DECORATOR":
            return self.parse_decorator()

    def parse_decorator(self):
        decorator = self.expect('DECORATOR').value
        if decorator == "@define":
            self.expect('NEWLINE')
            return self.parse_definition()

        elif decorator == '@output':
            self.expect('NEWLINE')
            return self.parse_inout('out')
    
        elif decorator == '@input':
            self.expect('NEWLINE')
            return self.parse_inout('in')
    
        elif decorator == '@uniform':
            self.expect('NEWLINE')
            
            return self.parse_uniform()

    def parse_definition(self):
        name = self.expect('IDENT')
        self.expect('OPERATOR', '=')
        val = self.parse_expression()

        return Define(name.pos, name.value, val)

    def parse_uniform(self):
        precision = None
        if self.peek().kind == "PRECISION":
            precision = self.expect('PRECISION').value
        
        name = self.expect('IDENT')
        self.expect('SYMBOL', ':')
        
        type = self.expect('TYPE').value

        return UniformDecl(name.pos, name.value, type, precision)


    def parse_inout(self, inout_type: str):
        precision = None
        if self.peek().kind == "PRECISION":
            precision = self.expect('PRECISION').value
        
        name = self.expect('IDENT')
        self.expect('SYMBOL', ':')
        
        type = self.expect('TYPE').value

        if inout_type == "in":
            return InputDecl(name.pos, name.value, type, precision)
        elif inout_type == "out":
            return OutputDecl(name.pos, name.value, type, precision)

    def parse_return(self):
        pos = self.expect("KEYWORD", 'return').pos
        val = self.parse_expression()
        return Return(pos, val)

    def parse_function(self):
        self.expect("KEYWORD", "def")
        name = self.expect("IDENT")
        self.expect("SYMBOL", "(")

        params = []
        if self.peek().kind != "SYMBOL" or self.peek().value != ")":
            params.append(self.parse_param())
            while self.peek().kind == "SYMBOL" and self.peek().value == ",":
                self.consume()
                params.append(self.parse_param())
        self.expect("SYMBOL", ")")
        self.expect("ARROW", "->")
        return_type = self.expect("TYPE").value

        self.expect("SYMBOL", ":")
        self.expect("NEWLINE")
        self.expect("INDENT")

        body = []
        while self.peek().kind != "DEDENT":
            stmt = self.parse_next()
            
            if stmt:
                body.append(stmt)
        

        self.expect("DEDENT")
        return FuncDecl(name.pos, name.value, return_type, params, body)

    def parse_param(self) -> Param:
        name = self.expect('IDENT')
        self.expect("SYMBOL", ":")
        type = self.expect("TYPE").value

        return Param(name.pos, name.value, type)

    def parse_var(self):
        precision = None
        if self.peek().kind == "PRECISION":
            precision = self.expect('PRECISION').value
        name = self.expect('IDENT').value
        
        if self.peek().value == ":":
            return self.parse_var_decl(name, precision)
        
        elif precision == None:
            return self.parse_var_set(name)
        
    def parse_var_decl(self, name, precision):
        self.expect("SYMBOL", ":")

        type = self.expect("TYPE").value
        val = None
        if self.peek().kind == 'OPERATOR' and self.peek().value == "=":
            self.consume()
            val = self.parse_expression()
            
        return VarDecl(name, type, val, precision)

    def parse_var_set(self, name):
        self.expect("OPERATOR", "=")
        expression = None

        if self.peek().kind != "NEWLINE":
            expression = self.parse_expression()

        return Set(Identifier(name), expression)

    def parse_expression(self):
        while self.peek().kind != "NEWLINE":
            return self.parse_math()
            
    def parse_math(self):
        left = self.parse_value()
        while self.peek().kind == "OPERATOR" and self.peek().value in "+-*/":
            op = self.consume().value
            right = self.parse_value()
            left = BinOp(left, op, right)
        return left

    def parse_value(self):
        tok = self.peek()
        if tok.kind == "INT":
            return Int(tok.pos, self.consume().value)
        elif tok.kind == "FLOAT":
            return Float(tok.pos, self.consume().value)
        elif tok.kind == "IDENT":
            return self.parse_get()
        else:
            self.error("Unexpected token in expression", tok)

    def parse_get(self) -> Identifier:
        name = self.expect('IDENT')
        if self.peek().kind == "SYMBOL" and self.peek().value == ".":
            self.expect("SYMBOL", ":")
            field_name = self.expect
            return MethodIdentifier(name.pos, name.value, field_name)
        
        elif self.peek().kind == "SYMBOL" and self.peek().value == "(":
            self.expect("SYMBOL", "(")
            args = []
            while (self.peek().value != ")"):
                if self.peek().value == ",":
                    self.consume()
                args.append(FuncArg(self.parse_expression()))
            self.expect("SYMBOL", ")")
            return FuncCall(name.pos, name.value, args)

        return Identifier(name.pos, name.value)
    
    def parse_field(self) -> StructField:
        precision = None
        if self.peek().kind == "PRECISION":
            precision = self.expect('PRECISION').value
            
        name = self.expect('IDENT')
        self.expect("SYMBOL", ":")
        type = self.expect("TYPE").value
        return StructField(name.pos, name.value, type, precision)

    def parse_struct(self) -> StructDecl:
        self.expect('KEYWORD', 'struct')
        name = self.expect('IDENT')
        self.expect('SYMBOL', ":")
        self.expect('NEWLINE')
        self.expect('INDENT')

        fields = []
        while self.peek().kind != "DEDENT":

            fields.append(self.parse_field())
            if self.peek().kind == "NEWLINE":
                self.expect('NEWLINE')
        self.expect("DEDENT")        

        return StructDecl(name.pos, name.value, fields)

    
class GLSLParser:
    """Parses GLSL into an AST."""