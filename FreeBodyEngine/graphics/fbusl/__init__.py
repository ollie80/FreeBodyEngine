"""
The FreeBody Universal Shader Language is a Transpiled Shader Language.
It includes features present in many shader languages so it can
be easily compiled into them.
"""

import sys


class Position:
    def __init__(self, line: int = 0, file: str = None):
        self.line = line
        self.file = file

    def __repr__(self):
        return f"{self.line}"

def fbusl_error(msg, position: Position=Position()):
    f = position.file
    if position.file == None:
        f = "Unkown File"
    print(f'\033[91mFBUSL ERROR: {msg} in file "{f}", line {position.line}.\033[0m')
    sys.exit()


from FreeBodyEngine.graphics.fbusl import parser
from FreeBodyEngine.graphics.fbusl import ast_nodes
from FreeBodyEngine.graphics.fbusl import injector
from FreeBodyEngine.graphics.fbusl import semantic
from FreeBodyEngine.graphics.fbusl import generator
from FreeBodyEngine.graphics.fbusl.compiler import compile



__all__ = ["fbusl_error", "parser", "ast_nodes", "semantic", "generator", "injector", "compile"]