from FreeBodyEngine.graphics import fbusl
from FreeBodyEngine import get_main
from typing import Literal
import sys
from enum import Enum, auto


class ShaderType:
    VERTEX = auto()
    FRAGMENT = auto()
    COMPUTE = auto()
    GEOMETRY = auto()


def compile(source):
    lexer = fbusl.parser.Lexer(source)
    tokens = lexer.tokenize()

    parser = fbusl.parser.Parser(tokens)
    parser.parse()


if __name__ == "__main__":
    txt = open("FreeBodyEngine/engine_assets/shader/default_shader.fbvert").read()
    compile(txt)
