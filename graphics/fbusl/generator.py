from FreeBodyEngine.graphics.fbusl.ast_nodes import *

class Generator:
    """
    The code generator for FBUSL. Abstracted to allow easy addition of new graphics APIs. 
    """
    def __init__(self, tree: Tree):
        self.tree = tree

    def generate(self) -> str:
        pass