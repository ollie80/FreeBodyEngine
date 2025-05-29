from FreeBodyEngine.math import Vector 
from FreeBodyEngine.utils import abstractmethod
import uuid
from FreeBodyEngine import warning, log
from typing import Union

class GenericNode:
    """
    Base class of the Node Tree Node. 
    """
    def __init__(self):
        self.is_initialized = False
        self.children: dict[uuid.UUID, Node] = {}
        self.id = 1

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
    
    def find_nodes_with_type(self, type: type['Node']):
        found = []
        if isinstance(self, type):
            found.append(self)
        for child in self.children:
            found += self.children[child].find_nodes_with_type(type)
        return found

    def update(self):
        self.on_update()
        for node in self.children:
            self.children[node].update()

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

class RootNode(GenericNode):
    """
    A root node object.
    """
    def __init__(self):
        super().__init__()
        self.is_initialized = True

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
        self.id: uuid.UUID

        # Requirements are children that the node needs to function.
        self.requirements: list[type[Node]] = []
        self.parental_requirement: type[Node] = Node
        
    def _initialize(self, parent: GenericNode):
        self.is_initialized = True

        if not isinstance(parent, self.parental_requirement) and not isinstance(parent, RootNode):
            warning(f'Node "{self}" requires a parent node of "{self.parental_requirement}", instead got parent of type "{parent.__class__}".')

        for requirement in self.requirements:
                if not any(isinstance(child, requirement) for child in self.children):
                    warning(f"Node '{self}' is missing required child node '{requirement.__name__}'.")
        
        self.parent = parent

        for child in self.children:
            self.children[child]._initialize(self)

        self.id = uuid.uuid4()
        while self.id in self.parent.children: # ensures id isn't already used
            self.id = uuid.uuid4() 
        
        self.parent.children[self.id] = self

        self.on_initialize()

    def on_initialize(self):
        pass

    def kill(self):
        """
        Removes the entity from its scene.
        """
        if self in self.scene.entities:
            self.scene.entities.remove(self)
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
        self.parental_requirement = Node2D

        self.position = position # local position
        self.rotation = rotation 
        self.scale = scale

        
    @property
    def world_position(self):
        """
        Position of the node relative to the world (scene).
        """
        if isinstance(self.parent, Node2D):
            return self.parent.world_position + self.position
        else:
            return self.position

    @world_position.setter
    def world_position(self, new):
        if isinstance(self.parent, Node2D):
            self.position = new - self.parent.world_position
        
        else:
            self.position = new


    @property
    def world_rotation(self):
        """
        Rotation of the node relative to the world (scene).
        """
        if isinstance(self.parent, Node2D):
            return self.rotation + self.parent.world_rotation

        else:
            return self.rotation
        
    @world_rotation.setter
    def world_rotation(self, new):
        if isinstance(self.parent, Node2D):
            self.rotation = new - self.parent.world_rotation

        else:
            self.rotation = new
        

    @property
    def world_scale(self):
        """
        Scale of the node relative to the world (scene).
        """
        if isinstance(self.parent, Node2D):
            return self.scale + self.parent.world_scale
        
        else:
            return self.scale 
    
    @world_scale.setter
    def world_scale(self, new):
        if isinstance(self.parent, Node2D):
            self.scale = new - self.parent.world_scale
        else:
            self.scale = new
