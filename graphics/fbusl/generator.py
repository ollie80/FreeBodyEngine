from FreeBodyEngine.graphics.fbusl.ast_nodes import *
from FreeBodyEngine.utils import abstractmethod

class Generator:
    """
    The code generator for FBUSL. Abstracted to allow easy addition of new graphics APIs. 
    """
    def __init__(self, tree: Tree):
        self.tree = tree

    @abstractmethod
    def generate(self) -> str:
        pass