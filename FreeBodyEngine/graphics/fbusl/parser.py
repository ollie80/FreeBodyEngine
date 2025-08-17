from typing import List
import re
from FreeBodyEngine.graphics.fbusl import fbusl_error, Position
from typing import List, Optional
from enum import Enum, auto
from FreeBodyEngine.graphics.fbusl.node import *
import sys


class Token:
    def __init__(self, kind: str, value, pos: Position = Position()):
        self.kind = kind
        self.value = value
        self.pos = pos

    def __repr__(self):
        return f"Token({self.kind}, {repr(self.value)})"


class TokenType(Enum):
    ARROW = auto()
    DECORATOR = auto()
    qualifier = auto()
    KEYWORD = auto()
    IDENT = auto()
    FLOAT = auto()
    INT = auto()
    BOOL = auto()
    SYMBOL = auto()
    OPERATOR = auto()
    WHITESPACE = auto()
    NEWLINE = auto()
    COMMENT = auto()
    INDENT = auto()
    DEDENT = auto()


TOKEN_TYPES = [
    (TokenType.NEWLINE, r"\n"),  # newlines first
    (TokenType.WHITESPACE, r"[ \t]+"),  # only spaces and tabs
    (TokenType.ARROW, r"->"),
    (TokenType.DECORATOR, r"@(?:uniform|input|output|define)"),
    (TokenType.qualifier, r"(low|med|flat|high)"),
    (TokenType.KEYWORD, r"\b(def|return|struct|if|buffer|elif|else|not|and|or)\b"),
    (TokenType.BOOL, r"(True|False)"),
    (TokenType.IDENT, r"[a-zA-Z_][a-zA-Z0-9_]*"),
    (TokenType.FLOAT, r"\d(?:_?\d)*\.\d(?:_?\d)*"),
    (TokenType.INT, r"\d(?:_?\d)*"),
    (TokenType.SYMBOL, r"[{}()[\]:,\.]"),
    (TokenType.OPERATOR, r"(\+=|-=|\*=|/=|=|\+|-|\*|/|==|!=|<=|>=|<|>)"),
    (TokenType.COMMENT, r"#.*"),
]

TOKEN_REGEX = [(kind, re.compile(pattern)) for kind, pattern in TOKEN_TYPES]


class Lexer:
    def __init__(self, code: str, filename: str = None):
        self.code = code
        self.filename = filename
        self.pos = 0
        self.line = 1
        self.length = len(code)
        self.indents = [0]  # stack of indentation levels
        self._pending_tokens: List[Token] = []

    def next_token(self) -> Optional[Token]:
        if self._pending_tokens:
            return self._pending_tokens.pop(0)

        if self.pos >= self.length:
            if len(self.indents) > 1:
                self.indents.pop()
                return Token(TokenType.DEDENT, "", Position(self.line, self.filename))
            return None

        if self.code[self.pos] == "\n":
            self.pos += 1
            self.line += 1
            start_pos = self.pos
            while self.pos < self.length and self.code[self.pos] in " \t":
                self.pos += 1
            indent = self.pos - start_pos
            last_indent = self.indents[-1]

            if indent > last_indent:
                self.indents.append(indent)

                self._pending_tokens.append(
                    Token(TokenType.INDENT, "", Position(self.line, self.filename))
                )
            elif indent < last_indent:
                while len(self.indents) > 1 and indent < self.indents[-1]:
                    self.indents.pop()
                    self._pending_tokens.append(
                        Token(TokenType.DEDENT, "", Position(self.line, self.filename))
                    )

            return Token(
                TokenType.NEWLINE, "\n", Position(self.line - 1, self.filename)
            )

        if self.code[self.pos] == "#":
            while self.pos < self.length and self.code[self.pos] != "\n":
                self.pos += 1
            return self.next_token()

        for kind, pattern in TOKEN_REGEX:
            match = pattern.match(self.code, self.pos)
            if match:
                value = match.group(0)
                tok_pos = Position(self.line, self.filename)
                self.pos = match.end()
                if kind in (TokenType.WHITESPACE, TokenType.COMMENT):
                    return self.next_token()  # skip
                return Token(kind, value, tok_pos)

        fbusl_error(
            f"Unexpected character: {self.code[self.pos]}",
            Position(self.line, self.filename),
        )
        self.pos += 1
        return self.next_token()

    def tokenize(self) -> List[Token]:
        tokens = []
        while self.pos < self.length or self._pending_tokens:
            tok = self.next_token()
            if tok:
                tokens.append(tok)

        while len(self.indents) > 1:
            self.indents.pop()
            tokens.append(
                Token(TokenType.DEDENT, "", Position(self.line, self.filename))
            )

        return tokens


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.position = 0

        self.max_repeat_tokens = 5

    def peek(self) -> Token:
        """Return the current token without consuming it."""
        if self.position < len(self.tokens):
            return self.tokens[self.position]

        return Token("EOF", "", Position(self.position))

    def consume(self) -> Token:
        """Consume and return the current token."""
        tok = self.peek()
        self.position += 1
        return tok

    def expect(self, kind: str, value=None) -> Token:
        """
        Consume the current token if it matches the expected kind (and optionally value),
        otherwise raise an error.
        """
        tok = self.peek()
        if tok.kind != kind or (value is not None and tok.value != value):
            msg = f"Expected token {kind}"
            if value is not None:
                msg += f" with value {value}"
            msg += f', but got {tok.kind} ("{tok.value}")'
            fbusl_error(msg, self.get_current_pos())
        self.position += 1
        return tok

    def get_current_pos(self) -> Position:
        """Return the Position object of the current token."""
        tok = self.peek()
        return tok.pos

    def parse(self):
        last_tokens: list[Token] = []
        ast: list[ASTNode] = []

        while self.position < len(self.tokens):
            token = self.peek()
            node = self.parse_next()

            if node is None:
                self.consume()
                continue

            if isinstance(node, list):
                ast.extend(node)
            else:
                ast.append(node)

            last_tokens.append(token)

            if len(last_tokens) > self.max_repeat_tokens:
                last_tokens.pop(0)

            if len(last_tokens) > self.max_repeat_tokens and all(
                tok.kind == token.kind and tok.value == token.value
                for tok in last_tokens
            ):
                fbusl_error(
                    f"Too many repeats of token: {token}", self.get_current_pos()
                )

        return ast

    def parse_next(self):
        token = self.peek()

        if token.kind == TokenType.KEYWORD:
            if token.value == "def":
                pass

        if token.kind == TokenType.DECORATOR:
            return self.parse_decorator()

        if token.kind == TokenType.KEYWORD:
            if token.value == "def":
                return self.parse_function_def()

        if token.kind == TokenType.IDENT:
            return self.parse_identifier()

    def parse_type(self) -> dict:
        name = self.expect(TokenType.IDENT).value

        if self.peek().value == "[":

            self.expect(TokenType.SYMBOL, "[")
            length = self.expect(TokenType.INT).value
            self.expect(TokenType.SYMBOL, "]")

            return {"name": "array", "data": {"length": length, "base_type": name}}
        else:
            return {"name": name}

    def parse_function_def(self) -> FunctionDef:
        position = self.get_current_pos()
        self.expect(TokenType.KEYWORD, "def")

        name = self.expect(TokenType.IDENT).value
        self.expect(TokenType.SYMBOL, "(")

        params = []

        first = True
        while self.peek().value != ")":
            if not first:
                self.expect(TokenType.SYMBOL, ",")

            param_name = self.expect(TokenType.IDENT)
            param_type, param_qualifier = self.parse_type_and_qualifier()

            if param_qualifier not in ["in", "inout", "out", None]:
                fbusl_error(
                    'Function parameters can only have qualifiers of "in", "out", and "inout".',
                    position,
                )

            params.append(
                FunctionParam(param_name, param_type, param_qualifier, position)
            )

            first = False

        self.expect(TokenType.SYMBOL, ")")

        return_type = None
        if self.peek().kind == TokenType.ARROW:
            self.expect(TokenType.ARROW)
            return_type = self.parse_type()

        self.expect(TokenType.SYMBOL, ":")
        self.expect(TokenType.NEWLINE)
        self.expect(TokenType.INDENT)

        body = []

        while self.peek().kind != TokenType.DEDENT:
            node = self.parse_next()
            if node is None:
                self.consume()  # skip unknown or blank token
                continue
            print(node)

            if isinstance(node, list):
                body.extend(node)
            else:
                body.append(node)

            if self.peek().kind == TokenType.NEWLINE:
                self.consume()

        self.expect(TokenType.DEDENT)

        return FunctionDef(name, body, return_type, params)

    def parse_decorator(self) -> ASTNode:
        decorator_type = self.expect(TokenType.DECORATOR).value
        self.expect(TokenType.NEWLINE)

        decorators = []

        while self.peek().kind == TokenType.IDENT:
            position = self.get_current_pos()
            if decorator_type in ["@uniform", "@input", "@output"]:

                name = self.expect(TokenType.IDENT).value
                var_type, qualifier = self.parse_type_and_qualifier()

                dec_class_map = {
                    "@output": Output,
                    "@input": Input,
                    "@uniform": Uniform,
                }
                decorators.append(
                    dec_class_map[decorator_type](name, var_type, qualifier, position)
                )

            else:
                name = self.expect(TokenType.IDENT)

                self.expect(TokenType.OPERATOR, "=")

                val = self.parse_expression()

                decorators.append(Define(name, val, position))

            self.expect(TokenType.NEWLINE)

        return decorators

    def parse_type_and_qualifier(self) -> tuple[dict, str | None]:
        self.expect(TokenType.SYMBOL, ":")

        prec = None
        if self.peek().kind == TokenType.qualifier:
            prec = self.expect(TokenType.qualifier).value

        node_type = self.parse_type()

        return node_type, prec

    def parse_identifier(self) -> ASTNode:
        node = Identifier(self.consume().value, pos=self.get_current_pos())

        while True:
            tok = self.peek()

            if tok.kind == TokenType.SYMBOL and tok.value == ".":
                self.consume()
                member_tok = self.expect(TokenType.IDENT)
                node = MemberAccess(node, member_tok.value, pos=member_tok.pos)

            elif tok.kind == TokenType.SYMBOL and tok.value == "[":
                self.consume()
                index_expr = self.parse_expression()
                self.expect(TokenType.SYMBOL, "]")
                node = ArrayAccess(node, index_expr, pos=self.get_current_pos())

            elif tok.kind == TokenType.SYMBOL and tok.value == "(":
                self.consume()
                args = self.parse_call_args()
                self.expect(TokenType.SYMBOL, ")")
                node = FuncCall(node, args, pos=self.get_current_pos())

            elif tok.kind == TokenType.OPERATOR and tok.value == "=":
                self.consume()
                expr = self.parse_expression()
                node = Setter(node, expr, self.get_current_pos())

            elif tok.kind == TokenType.SYMBOL and tok.value == ":":
                self.parse_var_decl(node.value)

            else:
                break

        return node

    def parse_var_decl(self, name=None) -> ASTNode:
        pos = self.get_current_pos()

        if name == None:
            name = self.expect(TokenType.IDENT).value

        node_type, qualifier = self.parse_type_and_qualifier()

        value = None
        if self.peek().kind == TokenType.OPERATOR and self.peek().value == "=":
            self.consume()
            value = self.parse_expression()

        return VarDecl(
            name=name, var_type=node_type, value=value, qualifier=qualifier, pos=pos
        )

    def parse_literal(self) -> ASTNode:
        tok = self.consume()
        if tok.kind == TokenType.INT:
            return Literal(int(tok.value), pos=tok.pos)
        elif tok.kind == TokenType.FLOAT:
            return Literal(float(tok.value), pos=tok.pos)
        elif tok.kind == TokenType.KEYWORD and tok.value in ["true", "false"]:
            return Literal(tok.value == "true", pos=tok.pos)
        else:
            fbusl_error(f"Invalid literal: {tok.value}", tok.pos)

    def parse_identifier_expr(self) -> ASTNode:
        node = Identifier(self.consume().value)

        while True:
            tok = self.peek()

            if tok.kind == TokenType.SYMBOL and tok.value == ".":
                self.consume()
                member_tok = self.expect(TokenType.IDENT)
                node = MemberAccess(node, member_tok.value)

            elif tok.kind == TokenType.SYMBOL and tok.value == "[":
                self.consume()
                index_expr = self.parse_expression()
                self.expect(TokenType.SYMBOL, "]")
                node = ArrayAccess(node, index_expr)

            elif tok.kind == TokenType.SYMBOL and tok.value == "(":
                self.consume()
                args = self.parse_call_args()
                self.expect(TokenType.SYMBOL, ")")
                node = FuncCall(node, args)

            else:
                break

        return node

    def parse_call_args(self) -> List[ASTNode]:
        args = []
        tok = self.peek()
        if tok.kind == TokenType.SYMBOL and tok.value == ")":
            return args

        while True:
            arg = self.parse_expression()
            args.append(arg)
            tok = self.peek()
            if tok.kind == TokenType.SYMBOL and tok.value == ",":
                self.consume()
            else:
                break
        return args

    def parse_expression(self, precedence=0) -> ASTNode:
        left = self.parse_primary()

        while True:
            tok = self.peek()
            if tok.kind != TokenType.OPERATOR:
                break
            op = tok.value
            op_prec = self.get_operator_precedence(op)
            if op_prec < precedence:
                break
            self.consume()
            right = self.parse_expression(op_prec + 1)
            left = BinOp(left, op, right)

        return left

    def parse_primary(self) -> ASTNode:
        tok = self.peek()

        if tok.kind == TokenType.IDENT:
            return self.parse_identifier()

        elif tok.kind in (TokenType.INT, TokenType.FLOAT, TokenType.BOOL):
            return self.parse_literal()

        elif tok.kind == TokenType.SYMBOL and tok.value == "(":
            self.consume()  # consume "("
            expr = self.parse_expression()
            self.expect(TokenType.SYMBOL, ")")
            return expr

        elif tok.kind == TokenType.OPERATOR and tok.value in ("+", "-", "not"):
            op = self.consume().value
            operand = self.parse_primary()
            return UnaryOp(op, operand, pos=tok.pos)

        else:
            fbusl_error(
                f"Unexpected token in expression: {tok.kind} ({tok.value})", tok.pos
            )

    def get_operator_precedence(self, op: str) -> int:
        PRECEDENCE = {
            "*": 10,
            "/": 10,
            "%": 10,
            "+": 9,
            "-": 9,
            "<<": 8,
            ">>": 8,
            "<": 7,
            "<=": 7,
            ">": 7,
            ">=": 7,
            "==": 6,
            "!=": 6,
            "&": 5,
            "^": 4,
            "|": 3,
            "and": 2,
            "or": 1,
            "=": 0,
        }
        return PRECEDENCE.get(op, -1)
