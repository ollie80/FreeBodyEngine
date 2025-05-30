# Simple Shader Language Compiler: Lexer + Parser

from typing import List
import re
from FreeBodyEngine.graphics.fbusl.ast_nodes import *
# 

import re
from typing import List

# Token class
class Token:
    def __init__(self, kind: str, value, pos: tuple[int, int]):
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
    ("OPERATOR", r"[=+*/\-]"),
    ("WHITESPACE", r"[ \t]+"),
    ("COMMENT", r"#.*"),
]
def tokenize(code: str, filepath: str) -> List[Token]:
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
            tokens.append(Token("INDENT", indent, pos=(line_num, 1)))
            indent_stack.append(indent)
        elif indent < indent_stack[-1]:
            while indent < indent_stack[-1]:
                indent_stack.pop()
                tokens.append(Token("DEDENT", indent_stack[-1], pos=(line_num, 1)))
            if indent != indent_stack[-1]:
                raise SyntaxError(f"{filepath}:{line_num}:1: Inconsistent indentation: expected {indent_stack[-1]}, got {indent}")

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
                        token = Token(kind, value, pos=(line_num, pos + 1))
                        tokens.append(token)
                        pos += len(value)
                        break
            else:
                raise SyntaxError(f"{filepath}:{line_num}:{pos + 1}: Unexpected character {line[pos]!r}")

        tokens.append(Token("NEWLINE", "\\n", pos=(line_num, len(line) + 1)))

    # Close remaining indents
    while len(indent_stack) > 1:
        indent_stack.pop()
        tokens.append(Token("DEDENT", indent_stack[-1], pos=(line_num + 1, 1)))

    return tokens

class FBUSLParser:
    """Parses FBUSL code into an AST."""
    def __init__(self, tokens, file_path):
        self.tokens: list[Token] = tokens
        self.index = 0
        self.file_path = file_path

    def error(self, msg, tok: Token):
        raise SyntaxError(msg + f" in {self.file_path}, line {tok.pos[0]} ")

    def peek(self) -> Token:
        return self.tokens[self.index]

    def expect(self, kind: str, value: str = None):

        tok = self.peek()

        if value != None:
            if tok.value != value:
                self.error(f"Expected token of kind '{kind}' with value of {value}, instead got '{tok.kind}' '{tok.value}'.", tok)
        
        if tok.kind != kind:
            self.error(f"Expected token of kind '{kind}', instead got kind '{tok.kind}'.", tok)
    
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
            print(tree)


    def parse_next(self) -> Node:
        tok = self.peek()
        if tok.kind == "NEWLINE":
            self.consume()
        if tok.kind == "KEYWORD":
            if tok.value == "def":
                return self.parse_function()
            
            elif tok.value == "struct":
                return self.parse_struct()
            
        elif tok.kind == "PRECISION" or tok.kind == "IDENT":
            return self.parse_var()
        
        elif tok.kind == "DECORATOR":
            return self.parse_decorator()

    def parse_decorator(self):
        decorator = self.expect('DECORATOR').value
        if decorator == "define":
            self.expect('NEWLINE')
            return self.parse_var()

        elif decorator == 'output':
            pass

    def parse_function(self):
        pass

    def parse_param(self) -> Param:
        name = self.expect('IDENT')
        self.expect("SYMBOL", ":")
        type = self.expect("TYPE")

        return Param(name, type)

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
        self.expect("OPERATOR", ":")

        type = self.expect("TYPE").value

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
        
            if self.peek().kind == "IDENT":
                self.parse_get()
            
            elif self.peek().kind in ["INT", "FLOAT"]:
                self.parse_math()
            
    def parse_math(self):
        pass

    def parse_get(self) -> Identifier:
        name = self.expect('IDENT').value
        if self.peek().kind == "SYMBOL" and self.peek().value == ".":
            self.expect("SYMBOL", ":")
            field_name = self.expect
            return MethodIdentifier(name, field_name)

        return Identifier(name)
    
    
    
    def parse_field(self) -> StructField:
        precision = None
        if self.peek().kind == "PRECISION":
            precision = self.expect('PRECISION').value
            

        name = self.expect('IDENT').value
        self.expect("SYMBOL", ":")
        type = self.expect("TYPE").value
        return StructField(name, type, precision)

    def parse_struct(self) -> StructDecl:
        self.expect('KEYWORD', 'struct')
        name = self.expect('IDENT').value
        self.expect('SYMBOL', ":")
        self.expect('NEWLINE')
        self.expect('INDENT')

        methods = []
        while self.peek().kind != "DEDENT":
            methods.append(self.parse_method())

        return StructDecl(name, methods)

    
class GLSLParser:
    """Parses GLSL into FBUSL."""