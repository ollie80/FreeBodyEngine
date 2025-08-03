from FreeBodyEngine.graphics import fbusl
from FreeBodyEngine import get_main
from typing import Literal
import sys


def compile(source, generator_class: type[fbusl.generator.Generator], injector: fbusl.injector.Injector, shader_type: Literal["frag", "vert"], buffer_index: int, file_path=""):
    inj = injector
    inj.init(shader_type, file_path)

    source = inj.pre_lexer_inject(source)
    tokens = fbusl.parser.tokenize(source, file_path)
    parser = fbusl.parser.FBUSLParser(tokens, file_path)
    ast = parser.parse()

    analyser = fbusl.semantic.SemanticAnalyser(ast, injector.get_builtins(), file_path)
    
    ast = analyser.analyse()

    ast = inj._pre_generation_inject(ast)
    
    generator = generator_class(ast, analyser, buffer_index)
    generated_code, data = generator.generate()
    
    with open(f"test.{shader_type}", 'w') as f:
        f.write(generated_code)
    
    return generated_code, data