# Simple Shader Language Compiler: Lexer + Parser

from typing import List
import re
from FreeBodyEngine.graphics.fbusl.ast_nodes import *
from FreeBodyEngine.graphics.fbusl import fbusl_error

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
    ("KEYWORD", r"\b(def|return|struct|if|elif|else|not|and|or)\b"),
    ("COMPARISON", r"(==|!=|<=|>=|<|>)"),
    ("TYPE", r"\b(void|float|int|bool|sampler2D|sampler3D)\b"),
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
                fbusl_error(f"Inconsistent indentation: expected {indent_stack[-1]}, got {indent}", line_num, file_path)

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
                fbusl_error(f"Unexpected character {line[pos]!r}", line_num, file_path)

        tokens.append(Token("NEWLINE", "\\n", pos=line_num))

    # Close remaining indents
    while len(indent_stack) > 1:
        indent_stack.pop()
        tokens.append(Token("DEDENT", indent_stack[-1], pos=line_num + 1))

    return tokens

class FBUSLParser: # im so  sorry
    """Parses FBUSL code into an AST."""
    def __init__(self, tokens, file_path):
        self.tokens: list[Token] = tokens
        self.index = 0
        self.file_path = file_path
        


    def peek(self, offset = 0) -> Token:
        if not self.index + offset > len(self.tokens) - 1:
            return self.tokens[self.index + offset]
        return 0
    
    def expect(self, kind: str, value: str = None):
        
        tok = self.peek()

        if tok == 0:
            if value == None:
                fbusl_error(f"Missing '{kind}'", self.tokens[len(self.tokens)-1].pos, self.file_path)
            else:
                fbusl_error(f"Missing '{kind}' '{value}'", self.tokens[len(self.tokens)-1].pos, self.file_path)

        if value != None:
            if tok.value != value:
                fbusl_error(f"Expected token of kind '{kind}' with value of {value}, instead got '{tok.kind}' '{tok.value}'.", tok.pos, self.file_path)
        
        if tok.kind != kind:
            fbusl_error(f"Expected token of kind '{kind}', instead got kind '{tok.kind}' ", tok.pos, self.file_path)
    
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
            
            elif tok.value in ['if', 'elif', 'else']:
                return self.parse_if_statement()
            
        elif tok.kind == "TYPE":
            return self.parse_typecast()

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

    def parse_typecast(self):    
        type = self.expect("TYPE").value
        self.expect("SYMBOL", "(")
        target = self.parse_expression()
        self.expect("SYMBOL", ")")
        return TypeCast(target.pos, target, type)
    

    def parse_uniform(self):
        precision = None
        if self.peek().kind == "PRECISION":
            precision = self.expect('PRECISION').value
        
        name = self.expect('IDENT')
        self.expect('SYMBOL', ':')
        
        if self.peek().kind == "TYPE":
            type = self.expect('TYPE').value
        else:
            type = self.expect('IDENT').value

        return UniformDecl(name.pos, name.value, type, precision)

    def parse_if_statement(self):
        type = self.expect("KEYWORD")
        condition = None
        
        if type.value != "else":
            condition = self.parse_expression()
        self.expect('SYMBOL', ':')
        self.expect('NEWLINE')
        self.expect('INDENT')

        body = []
        while self.peek().kind != "DEDENT":
            body.append(self.parse_next())
            self.expect('NEWLINE')
        self.expect("DEDENT")

        if type.value == 'if':
            return IfStatement(type.pos, condition, body)    
        if type.value == 'elif':
            return ElseIfStatement(type.pos, condition, body)
        if type.value == 'else':
            return ElseStatement(type.pos, body)
        
    def parse_inout(self, inout_type: str):
        precision = None
        if self.peek().kind == "PRECISION":
            precision = self.expect('PRECISION').value
        
        name = self.expect('IDENT')
        self.expect('SYMBOL', ':')
        
        if self.peek().kind == "TYPE":
            type = self.expect('TYPE').value
        else:
            type = self.expect('IDENT').value

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
        return_type = None
        if self.peek().kind == "ARROW":
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
        type = self.consume().value

        return Param(name.pos, name.value, type)
    
    def parse_expression(self):
        expr = self.parse_logical_or()

        if self.peek().kind == "KEYWORD" and self.peek().value == "if":
            self.consume() 
            condition = self.parse_logical_or()
            self.expect("KEYWORD", "else")
            false_expr = self.parse_expression()
            return TernaryExpression(expr.pos, expr, false_expr, condition)

        return expr

    def parse_logical_or(self):
        left = self.parse_logical_and()
        while self.peek().kind == "KEYWORD" and self.peek().value == "or":
            self.consume()
            right = self.parse_logical_and()
            left = Or(left.pos, left, right)
        return left

    def parse_logical_and(self):
        left = self.parse_equality()
        while self.peek().kind == "KEYWORD" and self.peek().value == "and":
            self.consume()
            right = self.parse_equality()
            left = And(left.pos, left, right)
        return left

    def parse_equality(self):
        left = self.parse_condition()
        while self.peek().kind == "COMPARISON" and self.peek().value in ["==", "!="]:
            comparison = self.consume().value
            right = self.parse_condition()
            left = Condition(left.pos, left, right, comparison)
        return left

    def parse_condition(self):
        left = self.parse_term()
        while self.peek().kind == "COMPARISON" and self.peek().value in ["<", ">", "<=", ">="]:
            comparison = self.consume().value
            right = self.parse_term()
            left = Condition(left.pos, left, right, comparison)
        return left

    def parse_term(self):
        left = self.parse_factor()
        while self.peek().kind == "OPERATOR" and self.peek().value in ["+", "-"]:
            op = self.consume().value
            right = self.parse_factor()
            left = BinOp(left.pos, left, op, right)
        return left

    def parse_factor(self):
        left = self.parse_unary()
        while self.peek().kind == "OPERATOR" and self.peek().value in ["*", "/"]:
            op = self.consume().value
            right = self.parse_unary()
            left = BinOp(left.pos, left, op, right)
        return left

    def parse_unary(self):
        if self.peek().kind == "KEYWORD" and self.peek().value == "not":
            op_tok = self.consume()
            operand = self.parse_unary()
            return Not(op_tok.pos, operand)
        return self.parse_value()

    def parse_var(self):
        precision = None
        if self.peek().kind == "PRECISION":
            precision = self.expect('PRECISION').value
        name = self.expect('IDENT')
        
        if self.peek().value == ":":
            return self.parse_var_decl(name, precision)
        
        elif precision == None:
            return self.parse_var_set(name)
        
        else:
            fbusl_error('Cannot change precision of defined value', name.pos, self.file_path)

    def parse_var_decl(self, name, precision):
        self.expect("SYMBOL", ":")
        
        if self.peek().kind == "TYPE":
            type = self.expect('TYPE').value
        else:
            type = self.expect('IDENT').value

        val = None
        if self.peek().kind == 'OPERATOR' and self.peek().value == "=":
            self.consume()
            val = self.parse_expression()
            
        return VarDecl(name.pos, name.value, type, val, precision)

    def parse_var_set(self, name):
        self.expect("OPERATOR", "=")
        expression = None

        if self.peek().kind != "NEWLINE":
            expression = self.parse_expression()

        return Set(name.pos, Identifier(name.pos, name.value), expression)
            
    def parse_math(self):
        left = self.parse_value()
        while self.peek().kind == "OPERATOR" and self.peek().value in "+-*/":
            op = self.consume().value
            right = self.parse_value()
            left = BinOp(left.pos, left, op, right)
        return left

    def parse_value(self):
        tok = self.peek()
        if tok.kind == "INT":
            return Int(tok.pos, self.consume().value)
        elif tok.kind == "FLOAT":
            return Float(tok.pos, self.consume().value)
        elif tok.kind == "IDENT":
            return self.parse_get()
        elif tok.kind == "TYPE" and self.peek(1).value == "(":
            return self.parse_typecast()
        else:
            fbusl_error(f"Unexpected token '{tok.value}'", tok.pos, self.file_path)

    def parse_get(self) -> Node:
        node = Identifier(self.peek().pos, self.expect("IDENT").value)

        while self.peek().kind == "SYMBOL" and self.peek().value in [".", "("]:
            if self.peek().value == ".":
                self.expect("SYMBOL", ".")
                field = self.expect("IDENT").value
                node = MethodIdentifier(node.pos, node, field)

            elif self.peek().value == "(":
                self.expect("SYMBOL", "(")
                args = []
                while self.peek().value != ")":
                    if self.peek().value == ",":
                        self.consume()
                    args.append(Arg(node.pos, self.parse_expression()))
                self.expect("SYMBOL", ")")
                node = Call(node.pos, node.name, args)
        return node

    
    def parse_field(self) -> StructField:
        precision = None
        if self.peek().kind == "PRECISION":
            precision = self.expect('PRECISION').value
            
        name = self.expect('IDENT')
        self.expect("SYMBOL", ":")

        if self.peek().kind == "TYPE":
            type = self.expect('TYPE').value
        else:
            type = self.expect('IDENT').value

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