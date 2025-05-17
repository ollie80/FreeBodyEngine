from FreeBodyEngine.graphics import fbusl

# Example usage
if __name__ == "__main__":
    source_code = """
    uniform float time;
    uniform vec3 lightPos;
    uniform vec3 test;
    uniform vec3 hello;
    if
    """
    tokens = fbusl.parser.tokenize(source_code)
    print("TOKENS:", tokens)
    
    parser = fbusl.parser.Parser(tokens)
    ast = parser.parse()
    print("AST:", ast)
