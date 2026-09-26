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
        """Builds `inheritance_hierarchy` (the class's MRO, base-first, as
        class name strings) up front so `inherits_from` can do plain string
        lookups instead of walking the MRO on every call."""
        self.inheritance_hierarchy = [cls.__name__ for cls in self.__class__.__mro__ if cls != object]
        self.inheritance_hierarchy.reverse()
        self.scene: 'Scene'
        self.is_initialized = False
        self.children: dict[uuid.UUID, Node] = {}
        self.id = 0

    def remove(self, *ids):
        """Removes the children with the given ids."""
        for id in ids:
            if id in self.children.keys():
                del self.children[id]

    def add(self, *nodes: 'Node'):
        """
        Adds any amount of nodes to the given nodes children.
        """
        for node in nodes:
            if self.is_initialized:
                node._initialize(self)
            self.children[node.id] = node
    
    def find_nodes_with_type(self, type: str) -> list['Node']:
        """Recursively collects every node in this subtree (self included)
        whose `inheritance_hierarchy` contains `type`."""
        found = []
        if self.inherits_from(type):
            found.append(self)
        for child in self.children:
            found += self.children[child].find_nodes_with_type(type)
        return found

    def update(self):
        """Runs `on_update` on this node, then recursively updates every
        child."""
        self.on_update()
        for node in self.children:
            self.children[node].update()

    def inherits_from(self, *type: str) -> bool:
        """Returns whether this node's class or any of its base classes
        matches one of the given class name(s)."""
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
            """Recursively renders `node_dict` (as produced by `get_tree_dict()`) into an indented ASCII tree (`└──`/`├──` branches, `│` continuation bars), matching the classic `tree` command's layout."""
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
        """Called every frame during `update`; override to add per-frame
        behavior. No-op by default."""
        pass

    def kill(self):
        """Removes this node from the tree. No-op by default - `Node`
        overrides this to actually detach from its parent."""
        pass

    def __repr__(self):
        return f"{self.__class__.__name__}"

class RootNode(GenericNode):
    """
    A root node object.
    """
    def __init__(self, scene: 'Scene'):
        """A root node is considered initialized as soon as it's built,
        unlike a regular `Node` which only initializes once attached to a
        parent - a root has no parent to attach to."""
        super().__init__()
        self.is_initialized = True
        self.scene: 'Scene' = scene

    def kill(self):
        """Refuses to kill the root node, logging a warning instead."""
        warning("Cannot kill a root node.")

    
class Node(GenericNode):
    """
    The Node class.
    """
    def __init__(self):
        """A freshly-constructed `Node` is not yet part of the tree -
        `is_initialized` stays False, and `scene`/`parent` are unset, until
        it's added to another node via `add()` and `_initialize()` runs."""
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
        """Called once this node has been attached to its parent and
        `self.scene`/`self.parent` are set; override to add setup logic
        that depends on the tree. No-op by default."""
        pass

    def kill(self):
        """
        Removes the node from its parent.
        """
        if self.id in self.parent.children.keys():
            self.parent.remove(self.id)
        self.on_kill()


    def on_event_loop(self, event):
        """Hook meant for handling input/window events; not currently
        invoked by anything in the engine. No-op by default."""
        pass

    def on_kill(self):
        """Called after this node has been removed from its parent by
        `kill`; override to add teardown logic. No-op by default."""
        pass

    def on_draw(self):
        """Hook meant for custom per-node draw logic (overridden by e.g.
        `Sprite2D`), but not currently called by the tree traversal or the
        renderer - rendering instead goes through `find_nodes_with_type`
        elsewhere. No-op by default."""
        pass

    def on_post_update(self):
        """Hook meant to run once every node's update has finished for the
        frame; not currently invoked by anything in the engine. No-op by
        default."""
        pass

    def on_pre_update(self):
        """Hook meant to run before any node's update runs for the frame;
        not currently invoked by anything in the engine. No-op by
        default."""
        pass

    def on_update(self):
        """Called every frame during `update`; override to add per-frame
        behavior. No-op by default."""
        pass

class Node2D(Node):
    """A `Node` with a 2D `Transform`, requiring a `Node2D` (or root)
    parent so `world_transform` can compose up the tree."""
    def __init__(self, position: Vector = Vector(), rotation: float = 0.0, scale: Vector = Vector(1, 1)):
        """Sets `parental_requirement` to `"Node2D"`, so `_initialize`
        warns if this node ends up under a non-`Node2D` parent."""
        super().__init__()
        self.parental_requirement = "Node2D"

        self.transform = Transform(position, rotation, scale)

    @property
    def world_transform(self):
        """This node's transform composed with its ancestors', giving its
        transform in world space rather than parent-local space. Falls
        back to the local transform unchanged if the parent isn't a
        `Node2D` (e.g. it's the scene's `RootNode`)."""
        if self.parent.inherits_from('Node2D'):
            return self.transform.compose_with(self.parent.world_transform)
        else:
            return self.transform

    @property
    def world_position(self) -> Vector:
        """Shorthand for `self.world_transform.position`."""
        return self.world_transform.position

    @property
    def world_rotation(self) -> float:
        """Shorthand for `self.world_transform.rotation`."""
        return self.world_transform.rotation

class Node3D(Node):
    """A `Node` with a 3D `Transform3`, requiring a `Node3D` (or root)
    parent so `world_transform` can compose up the tree."""
    def __init__(self, position: Vector3 = Vector3(), rotation: Vector3 = Vector3(), scale: Vector3 = Vector3(1, 1, 1)):
        """Sets `parental_requirement` to `"Node3D"`, so `_initialize`
        warns if this node ends up under a non-`Node3D` parent."""
        super().__init__()
        self.parental_requirement = "Node3D"

        self.transform = Transform3(position, rotation, scale)

    @property
    def world_transform(self):
        """This node's transform composed with its ancestors', giving its
        transform in world space rather than parent-local space. Falls
        back to the local transform unchanged if the parent isn't a
        `Node3D` (e.g. it's the scene's `RootNode`)."""
        if self.parent.inherits_from('Node3D'):
            return self.transform.compose_with(self.parent.world_transform)
        else:
            return self.transform
