import sys
from FreeBodyEngine.graphics import fbusl
from FreeBodyEngine import get_main


def compile(source, generator: type[fbusl.generator.Generator], injector: type[fbusl.injector.Injector], shader_type: str, file_path="C:\\Users\\Ollie\\Documents\\GitHub\\FreeBodyDev\\FreeBodyEngine\\engine_assets\\shader\\default_shader.fbfrag"):
    tokens = fbusl.parser.tokenize(source, file_path)
    parser = fbusl.parser.FBUSLParser(tokens, file_path)
    ast = parser.parse()


    analyser = fbusl.semantic.SemanticAnalyser(ast, injector.get_builtins(), file_path)
    ast = analyser.analyse()

    inj = injector(ast, shader_type, file_path)
    ast = inj.inject()

    gen = generator(ast, analyser)
    print(gen.generate())
    sys.exit()