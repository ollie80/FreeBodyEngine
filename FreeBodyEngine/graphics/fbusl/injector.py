from FreeBodyEngine.graphics.fbusl.ast_nodes import *
from FreeBodyEngine.utils import abstractmethod
from typing import Literal


class Injector:
    """
    Injects into an FBUSL AST.
    """
    def __init__(self):
        self.tree: Tree = Tree()

    def init(self, shader_type: Literal['vert', 'frag'], file_path: str):
        self.shader_type = shader_type 
        self.file_path = file_path

    def get_builtins() -> dict[str, list]:
        return {}

    def pre_lexer_inject(self, source: str) -> str:
        "Modifies the raw shader source code text."
        return source


    def _pre_generation_inject(self, tree: Tree):
        self.tree = tree
        return self.pre_generation_inject()

    def pre_generation_inject(self) -> str:
        "Modifies the AST right before code generation."
        return self.tree

    def inject(self):
        return self.tree

    def replace_node(self, node: Node, new: Node):
        for node in self.tree.children:
            for name, value in vars(node).items():

                if isinstance(value, Node):
                    if value == node:
                        node.__setattr__(name, new)    
                        return
                    
                    self.replace_node(node, new)
        
    def find_nodes(self, attr_name, attr_val) -> Node:
        nodes = []

        for node in self.tree.children:
            for name, value in vars(node).items():

                if isinstance(value, Node):
                    nodes += self.find_nodes(attr_name, attr_val)

                if name == attr_name and value == attr_val:
                    nodes += node
        
        return nodes

