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

# Token types (ignoring INDENT/DEDENT here — handled manually)
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
        indent = len(indent_str.replace('\t', '    '))  # Convert tabs to spaces

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

class Parser:
    def __init__(self):
        pass

            

