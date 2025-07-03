from FreeBodyEngine.graphics import fbusl
from FreeBodyEngine import get_main
from typing import Literal
import sys


def compile(source, generator: type[fbusl.generator.Generator], injector: type[fbusl.injector.Injector], shader_type: Literal["frag", "vert"], file_path="C:\\Users\\Ollie\\Documents\\GitHub\\FreeBodyDev\\FreeBodyEngine\\engine_assets\\shader\\default_shader.fbvert"):
    tokens = fbusl.parser.tokenize(source, file_path)
    parser = fbusl.parser.FBUSLParser(tokens, file_path)
    ast = parser.parse()

    analyser = fbusl.semantic.SemanticAnalyser(ast, injector.get_builtins(shader_type), file_path)
    #ast = analyser.analyse()

    inj = injector(ast, shader_type, file_path)
    ast = inj.inject()    
    gen = generator(ast, analyser)
    g = gen.generate()
    with open(f"test.{shader_type}", 'w') as f:
        f.write(g)
    return g