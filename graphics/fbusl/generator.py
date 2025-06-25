from FreeBodyEngine.graphics.fbusl.ast_nodes import *
from FreeBodyEngine.utils import abstractmethod
from FreeBodyEngine.graphics.fbusl.semantic import SemanticAnalyser

class Generator:
    """
    The code generator for FBUSL ASTs.
    """
    def __init__(self, tree: Tree, analyser: SemanticAnalyser):
        self.tree = tree
        self.analyser = analyser

    @abstractmethod
    def generate(self) -> str:
        pass