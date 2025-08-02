from FreeBodyEngine.graphics.fbusl.ast_nodes import *
from FreeBodyEngine.graphics.fbusl.semantic import Function
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

    def get_builtins(self) -> dict[str, list]:
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
    
    def find_main_function(self) -> FuncDecl | None:
        def recursive_search(node):
            if isinstance(node, FuncDecl) and node.name.name == "main":
                return node

            for value in vars(node).values():
                if isinstance(value, Node):
                    result = recursive_search(value)
                    if result:
                        return result
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, Node):
                            result = recursive_search(item)
                            if result:
                                return result
            return None

        for root in self.tree.children:
            result = recursive_search(root)
            if result:
                return result

        return None

    def replace_node(self, target: Node, replacement: Node):
        def recursive_replace(current: Node):
            for name, value in vars(current).items():
                if isinstance(value, Node):
                    if value is target:
                        setattr(current, name, replacement)
                    else:
                        recursive_replace(value)

                elif isinstance(value, list):
                    new_list = []
                    for item in value:
                        if isinstance(item, Node):
                            if item is target:
                                new_list.append(replacement)
                            else:
                                recursive_replace(item)
                                new_list.append(item)
                        else:
                            new_list.append(item)
                    setattr(current, name, new_list)

        for root in self.tree.children:
            recursive_replace(root)

    def find_parent(self, target: Node) -> Node | None:
        def recursive_search(current: Node):
            for name, value in vars(current).items():
                if isinstance(value, Node):
                    if value is target:
                        return current
                    result = recursive_search(value)
                    if result:
                        return result
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, Node):
                            if item is target:
                                return current
                            result = recursive_search(item)
                            if result:
                                return result
            return None

        for root in self.tree.children:
            result = recursive_search(root)
            if result:
                return result

        return None
    
    def find_nodes(self, attr_name, attr_val) -> list[Node]:
        nodes = []

        def recursive_search(node):
            if hasattr(node, attr_name) and getattr(node, attr_name) == attr_val:
                nodes.append(node)

            for name, value in vars(node).items():
                if isinstance(value, Node):
                    recursive_search(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, Node):
                            recursive_search(item)



        for node in self.tree.children:
            recursive_search(node)

        return nodes
