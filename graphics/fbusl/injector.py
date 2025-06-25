from FreeBodyEngine.graphics.fbusl.ast_nodes import *
from FreeBodyEngine.utils import abstractmethod
from typing import Literal


class Injector:
    """
    Injects into an FBUSL AST.
    """
    def __init__(self, tree, shader_type: Literal["vert", "frag"], file_path):
        self.tree: Tree = tree
        self.shader_type = shader_type 
        self.file_path = file_path

    @abstractmethod
    @classmethod
    def get_builtins() -> dict[str, list]:
        return {}

    def inject(self):
        return self.tree
