from FreeBodyEngine.utils import abstractmethod
from FreeBodyEngine.math import Transform, Transform3, Vector, Vector3
from FreeBodyEngine import warning, log


from typing import Union, TYPE_CHECKING
if TYPE_CHECKING:
    from FreeBodyEngine.core.scene import Scene

import uuid

class GenericNode:
    """
    Base class of the Node Tree Node. 
    """
    def __init__(self):
        self.inheritance_hierarchy = [cls.__name__ for cls in self.__class__.__mro__ if cls != object]
        self.inheritance_hierarchy.reverse()
        self.scene: 'Scene'
        self.is_initialized = False
        self.children: dict[uuid.UUID, Node] = {}
        self.id = 0

    def remove(self, *ids):
        for id in ids:
            if id in self.children.keys():
                del self.children[ids]

    def add(self, *nodes: 'Node'):
        """
        Adds any amount of nodes to the given nodes children.
        """
        for node in nodes:
            if self.is_initialized:
                node._initialize(self)
            self.children[node.id] = node
    
    def find_nodes_with_type(self, type: str) -> list['Node']:
        found = []
        if self.inherits_from(type):
            found.append(self)
        for child in self.children:
            found += self.children[child].find_nodes_with_type(type)
        return found

    def update(self):
        self.on_update()
        for node in self.children:
            self.children[node].update()

    def inherits_from(self, *type: str) -> bool:
        for t in type:
            inherits = t in self.inheritance_hierarchy
            if inherits:
                return True
        return False

    def get_tree_dict(self):
        """
        Create a dictionary with this node's info and its children list.
        """
        return {
            "class": self.__class__.__name__,
            "id": self.id,
            "children": [child.get_tree_dict() for child in self.children.values()]
        }

    def log_tree(self):
        """
        Logs a node tree in human-readable tree format.
        """
        def build_tree_str(node_dict, prefix="", is_last=True):
            node_line = f"{node_dict['class']}"
            if prefix == "":
                # Root node, no branch prefix
                text = node_line + "\n"
            else:
                branch = "└── " if is_last else "├── "
                text = prefix + branch + node_line + "\n"

            children = node_dict.get("children", [])
            for i, child_dict in enumerate(children):
                last_child = (i == len(children) - 1)
                # If this node is last, add spaces for prefix, else add vertical line
                extension = "    " if is_last else "│   "
                text += build_tree_str(child_dict, prefix + extension, last_child)

            return text
        tree_dict = self.get_tree_dict()
        tree_str = build_tree_str(tree_dict)
        log(tree_str) 

    def on_update(self):
        pass

    def kill(self):
        pass

    def __repr__(self):
        return f"{self.__class__.__name__}"

class RootNode(GenericNode):
    """
    A root node object.
    """
    def __init__(self, scene: 'Scene'):
        super().__init__()
        self.is_initialized = True
        self.scene: 'Scene' = scene

    def kill(self):
        warning("Cannot kill a root node.")

    
class Node(GenericNode):
    """
    The Node class.
    """
    def __init__(self):
        super().__init__()
        self.is_initialized = False
        self.parent: GenericNode

        self.id: uuid.UUID = uuid.uuid4()

        # requirements are children that the node needs to function, not having a required child will raise a warning.
        self.requirements: list[str] = []
        self.parental_requirement: str = "Node"
        
    def _initialize(self, parent: GenericNode):
        self.is_initialized = True
        if not parent.inherits_from('RootNode', self.parental_requirement):
            warning(f'Node "{self}" requires a parent node of "{self.parental_requirement}" or "RootNode", instead got parent of type "{parent.__class__.__name__}".')

        for requirement in self.requirements:
                if not any(self.children[child].inherits_from(requirement) for child in self.children):
                    warning(f"Node '{self}' is missing required child node '{requirement}'.")
        
        self.scene = parent.scene
        self.parent = parent

        for child in self.children:
            self.children[child]._initialize(self)

        self.parent.children[self.id] = self

        self.on_initialize()

    def on_initialize(self):
        pass

    def kill(self):
        """
        Removes the node from its parent.
        """
        if self.id in self.parent.children.keys():
            self.parent.remove(self.id)
        self.on_kill()

    
    def on_event_loop(self, event):
        pass
    
    def on_kill(self):
        pass

    def on_draw(self): 
        pass

    def on_post_update(self):
        pass

    def on_pre_update(self):
        pass

    def on_update(self):
        pass

class Node2D(Node):
    def __init__(self, position: Vector = Vector(), rotation: float = 0.0, scale: Vector = Vector(1, 1)):
        super().__init__()
        self.parental_requirement = "Node2D"

        self.transform = Transform(position, rotation, scale)

    @property
    def world_transform(self):
        if self.parent.inherits_from('Node2D'):
            return self.transform.compose_with(self.parent.world_transform)
        else:
            return self.transform

class Node3D(Node):
    def __init__(self, position: Vector3 = Vector3(), rotation: Vector3 = Vector3(), scale: Vector3 = Vector3(1, 1, 1)):
        super().__init__()
        self.parental_requirement = "Node3D"

        self.transform = Transform3(position, rotation, scale)

    @property
    def world_transform(self):
        if self.parent.inherits_from('Node3D'):
            return self.transform.compose_with(self.parent.world_transform)
        else:
            return self.transform
