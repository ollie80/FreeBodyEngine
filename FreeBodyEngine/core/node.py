from FreeBodyEngine.utils import abstractmethod
from FreeBodyEngine.math import Transform, Transform3, Vector, Vector3
from FreeBodyEngine import warning, log


from typing import Union, TYPE_CHECKING
if TYPE_CHECKING:
    from FreeBodyEngine.core.scene import Scene

import uuid


def _is_kind(node, kind) -> bool:
    """Whether `node` is a `kind`: an instance of it (subclasses included)
    for a class, or a class in its hierarchy for a class name."""
    if isinstance(kind, str):
        return node.inherits_from(kind)
    return isinstance(node, kind)


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
        # What get_node() matches path segments against. The class name until
        # set - `player.name = "player"` - and it need not be unique; the
        # first child with a matching name wins.
        self.name: str = self.__class__.__name__

    def remove(self, *ids):
        """Removes the children with the given ids, telling each removed node
        and everything under it - see Node.kill()."""
        for id in ids:
            child = self.children.get(id)
            if child is not None:
                self._detach(child)

    def _detach(self, child: 'Node'):
        """Takes `child` out of the tree. Every node in its subtree leaves the
        scene's index and gets on_kill(), children before their parent, so a
        node's teardown can still rely on its own children being there."""
        del self.children[child.id]
        child._left_tree()

    def _left_tree(self):
        for grandchild in list(self.children.values()):
            grandchild._left_tree()
        scene = getattr(self, 'scene', None)
        if scene is not None and self.is_initialized:
            scene._unindex(self)
        self.is_initialized = False
        self.on_kill()

    def on_kill(self):
        """Called once this node has left the tree - when it, or any node
        above it, was killed or removed. Override to add teardown logic.
        No-op by default."""
        pass

    def add(self, *nodes: 'Node'):
        """
        Adds any amount of nodes to the given nodes children.
        """
        for node in nodes:
            # Known straight away, not only once this node is in a scene - so
            # get_node("..") and kill() work on a subtree being assembled
            # before it's added.
            node.parent = self
            if self.is_initialized:
                node._initialize(self)
            self.children[node.id] = node
    
    def get_node(self, path: str) -> 'Node | None':
        """The node at `path`, relative to this one: names separated by "/"
        ("Weapon/Muzzle"), with ".." for a parent. None if nothing matches.
        Names are `node.name`, the class name unless set."""
        node = self
        for part in path.split('/'):
            if part in ('', '.'):
                continue
            if part == '..':
                node = getattr(node, 'parent', None)
            else:
                node = next((child for child in node.children.values() if child.name == part), None)
            if node is None:
                return None
        return node

    def find_all(self, kind) -> list['Node']:
        """Every node under this one (not including it) that is a `kind` -
        a class, subclasses included, or a class name as a string."""
        found = []
        for child in list(self.children.values()):
            if _is_kind(child, kind):
                found.append(child)
            found += child.find_all(kind)
        return found

    def find(self, kind) -> 'Node | None':
        """The first node under this one that is a `kind` - see find_all().
        None if there is none."""
        for child in list(self.children.values()):
            if _is_kind(child, kind):
                return child
            match = child.find(kind)
            if match is not None:
                return match
        return None

    def find_nodes_with_type(self, type: str) -> list['Node']:
        """Recursively collects every node in this subtree (self included)
        whose `inheritance_hierarchy` contains `type`."""
        found = []
        if self.inherits_from(type):
            found.append(self)
        # Snapshot, for the same reason update() does - this is called from
        # inside update and physics, where a node may remove itself or add
        # another while the walk is in progress.
        for child in list(self.children.values()):
            found += child.find_nodes_with_type(type)
        return found

    def update(self):
        """Runs `on_update` on this node, then recursively updates every
        child.

        Children are iterated over a snapshot taken up front, because
        updating one routinely changes the set: a particle whose animation
        finished removes itself, a weapon adds a projectile, a tilemap
        rebuilds its collision colliders. Iterating the live dict raised
        "dictionary changed size during iteration" and lost the rest of the
        frame's updates - including, since the exception unwound the whole
        scene update, every node after the one that had changed.
        """
        self.on_update()
        for node in list(self.children.values()):
            # Skipped if an earlier sibling's update removed it this frame.
            if node.id in self.children:
                node.update()

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

    # The root answers whole-scene searches from the scene's type index rather
    # than walking the tree - see Scene._index(). The engine asks the root for
    # every collider and body several times a physics step.

    def find_nodes_with_type(self, type: str) -> list['Node']:
        if self.scene is None:
            return super().find_nodes_with_type(type)
        found = [self] if self.inherits_from(type) else []
        return found + self.scene._indexed(type)

    def find_all(self, kind) -> list['Node']:
        if self.scene is None:
            return super().find_all(kind)
        name = kind if isinstance(kind, str) else kind.__name__
        return [node for node in self.scene._indexed(name) if _is_kind(node, kind)]

    def find(self, kind) -> 'Node | None':
        found = self.find_all(kind)
        return found[0] if found else None

    
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
        # A tree may have no scene at all (a bare RootNode, as tests and tools
        # build) - it just isn't indexed.
        if self.scene is not None:
            self.scene._index(self)

        for child in list(self.children):
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
        Removes the node from its parent. It and every node under it get
        on_kill(), children first - children used to get nothing, and removing
        a node with remove() skipped on_kill() even for the node itself. A
        no-op for a node that isn't in a tree, so killing twice is safe.
        """
        parent = getattr(self, 'parent', None)
        if parent is not None and parent.children.get(self.id) is self:
            parent.remove(self.id)

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

        # Last composed world transform, and the inputs it was built from -
        # see world_transform.
        self._world_key = None
        self._world_value = None

    @property
    def world_transform(self):
        """This node's transform composed with its ancestors', giving its
        transform in world space rather than parent-local space. Falls
        back to the local transform unchanged if the parent isn't a
        `Node2D` (e.g. it's the scene's `RootNode`).

        Memoised on the values it is composed from. Composition is not cheap -
        two `to_matrix` calls (trigonometry plus a numpy allocation each), a
        matrix multiply, and a `from_matrix` decomposition (square roots and
        an atan2) - and this is read several times per node per frame, by the
        renderer, the physics step and anything asking where something is. A
        profile of a floor showed 365,920 compositions across 60 frames,
        2.66 seconds of cumulative time: the single largest cost in the frame.

        Keyed on the inputs rather than invalidated by a dirty flag. A flag
        would have to be set by every mutation of a transform, and a transform
        is mutable all the way down - `node.transform.position.x += 1` reaches
        past the Transform into a Vector's own attribute, so nothing short of
        wrapping both types could catch every write. Comparing the ten floats
        that actually determine the result cannot miss a change, however it was
        made, and is still a fraction of the cost of recomputing.
        """
        parent = self.parent
        if parent is None or not parent.inherits_from('Node2D'):
            return self.transform

        parent_world = parent.world_transform
        local = self.transform
        key = (local.position.x, local.position.y, local.rotation,
               local.scale.x, local.scale.y,
               parent_world.position.x, parent_world.position.y,
               parent_world.rotation,
               parent_world.scale.x, parent_world.scale.y)

        if key == self._world_key:
            return self._world_value

        value = local.compose_with(parent_world)
        self._world_key = key
        self._world_value = value
        return value

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
        if not self.parent.inherits_from('Node3D'):
            return self.transform
        # Memoised on what it is composed from, as Node2D's is (see there):
        # this node's own nine numbers and the parent's world transform -
        # which is itself memoised, so an unmoved chain hands back the same
        # object and is recognised by identity.
        parent_world = self.parent.world_transform
        t = self.transform
        key = (tuple(t.position), tuple(t.rotation), tuple(t.scale), id(parent_world),
               tuple(parent_world.position), tuple(parent_world.rotation), tuple(parent_world.scale))
        cached = self.__dict__.get('_world_cache')
        if cached is not None and cached[0] == key:
            return cached[1]
        world = t.compose_with(parent_world)
        self.__dict__['_world_cache'] = (key, world)
        return world
