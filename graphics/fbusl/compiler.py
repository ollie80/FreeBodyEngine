from FreeBodyEngine.graphics import fbusl
from FreeBodyEngine import get_main


def compile(source, generator: fbusl.generator.Generator, file_path="C:\\Users\\Ollie\\Documents\\GitHub\\FreeBodyDev\\FreeBodyEngine\\engine_assets\\shader\\default_shader.fbfrag"):
    tokens = fbusl.parser.tokenize(source, file_path)
    print("completed tokenization")
    parser = fbusl.parser.FBUSLParser(tokens, file_path)
    ast = parser.parse()
    print("completed parsing")

    analyser = fbusl.semantic.SemanticAnalyser(ast, file_path)
    analyser.analyse()
    print("completed analysis")

    # injector = fbusl.injector.Injector(ast)
    # ast = injector.inject()

    gen = generator(ast)
    
    print("AST: \n", gen.generate())
    get_main().quit()
    