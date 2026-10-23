from FreeBodyEngine.utils import abstractmethod
import uuid
from typing import TYPE_CHECKING

from FreeBodyEngine.core.node import RootNode, Node
from FreeBodyEngine.core.camera import Camera2D
from FreeBodyEngine.core.update import UpdatePhase
from FreeBodyEngine.core.service import Service
from FreeBodyEngine import register_service_update, unregister_service_update, get_service, warning


if TYPE_CHECKING:
    from FreeBodyEngine.core.main import Main

def add_scene(scene: 'Scene'):
    """Registers `scene` with the `scene_manager` service. Shorthand for
    `get_service('scene_manager').add_scene(scene)`."""
    get_service('scene_manager').add_scene(scene)

def set_scene(name: str):
    """Makes the scene named `name` the active one. Shorthand for
    `get_service('scene_manager').set_scene(name)`."""
    get_service('scene_manager').set_scene(name)

def remove_scene(name: str):
    """Unregisters the scene named `name`. Shorthand for
    `get_service('scene_manager').remove_scene(name)`."""
    get_service('scene_manager').remove_scene(name)

class SceneManager(Service):
    """Service that owns every registered `Scene` and drives the update/
    physics of whichever one is active; only one scene updates at a time."""
    def __init__(self):
        """Registers this service under the name `"scene_manager"`."""
        super().__init__('scene_manager')
        self.scenes: dict[str, 'Scene'] = {}
        self.active_scene: str | None = None

    def on_initialize(self):
        """Hooks this manager's `update`/`physics_update` into the engine's
        UPDATE and PHYSICS update phases."""
        register_service_update(UpdatePhase.UPDATE, self.update)
        register_service_update(UpdatePhase.PHYSICS, self.physics_update)

    def on_destroy(self):
        """Unhooks `update`/`physics_update` from the engine's update
        phases."""
        unregister_service_update(UpdatePhase.UPDATE, self.update)
        unregister_service_update(UpdatePhase.PHYSICS, self.physics_update)

    def get_active(self) -> 'Scene':
        """Returns the currently active `Scene`, or None if none is set."""
        return self.scenes.get(self.active_scene, None)

    def add_scene(self, scene: 'Scene'):
        """Registers `scene` under its name and initializes it
        immediately, regardless of whether it becomes the active scene."""
        self.scenes[scene.name] = scene
        scene._initialize()

    def set_scene(self, name: str):
        """Makes the scene named `name` the active one, calling on_exit() on
        the scene that was active and on_enter() on the new one. Warns and
        changes nothing if no scene by that name has been added - it used to
        switch to it anyway, leaving nothing active at all."""
        if name not in self.scenes:
            warning(f'Cannot set scene "{name}": no scene by that name has been added.')
            return
        if name == self.active_scene:
            return
        previous = self.get_active()
        if previous is not None:
            previous.on_exit()
        self.active_scene = name
        self.scenes[name].on_enter()

    def remove_scene(self, name: str):
        """Unregisters the scene named `name`, clearing `active_scene` too
        (with its on_exit()) if it was the active one."""
        scene = self.scenes.pop(name, None)
        if scene is not None and self.active_scene == name:
            self.active_scene = None
            scene.on_exit()

    def physics_update(self):
        """Runs the active scene's physics step, if there is one."""
        if self.active_scene:
            self.scenes[self.active_scene]._physics_process()

    def update(self):
        """Runs the active scene's update step, if there is one."""
        if self.active_scene:
            self.scenes[self.active_scene]._update()


    

class Scene:
    """
    A generic scene object. The Scene's purpose is to manage entities and handle interaction with the Main object. 
    """
    def __init__(self, name: str):
        """`name` is the key the scene is registered under with
        `SceneManager`/`add_scene`."""
        self.name = name
        # Every node in the scene by every class name it has - see _index().
        self._nodes_by_type: dict[str, dict] = {}
        self.root = RootNode(self)
        self.isinitialized: bool = False
        self.camera = None
        # Applied to every DYNAMIC and CHARACTER RigidBody2D, times its own
        # gravity_scale. Set Vector(0, 0) for a top-down game.
        from FreeBodyEngine.core.physics.world import GRAVITY
        self.gravity = GRAVITY.copy()

    def _initialize(self):
        self.isinitialized = True
        self.on_initialize()

    def on_enter(self):
        """Called each time this scene becomes the active one (set_scene()).
        on_initialize() runs once, when the scene is added; this runs on every
        switch to it. No-op by default."""
        pass

    def on_exit(self):
        """Called each time this scene stops being the active one - another
        was set, or it was removed. No-op by default."""
        pass

    # -- finding nodes ----------------------------------------------------

    def _index(self, node):
        """Records `node` under every class name in its hierarchy. Kept up to
        date as nodes join (Node._initialize) and leave (GenericNode._detach),
        so a whole-scene search is a lookup rather than a walk of the tree."""
        for name in node.inheritance_hierarchy:
            self._nodes_by_type.setdefault(name, {})[node.id] = node

    def _unindex(self, node):
        for name in node.inheritance_hierarchy:
            nodes = self._nodes_by_type.get(name)
            if nodes is not None:
                nodes.pop(node.id, None)

    def _indexed(self, name: str) -> list:
        """Every node in the scene with class `name` in its hierarchy, in the
        order they joined."""
        return list(self._nodes_by_type.get(name, {}).values())

    def find_all(self, kind) -> list:
        """Every node in the scene that is a `kind` - a class (subclasses
        included) or a class name."""
        return self.root.find_all(kind)

    def find(self, kind):
        """The first node in the scene that is a `kind`, or None."""
        return self.root.find(kind)

    def get_node(self, path: str):
        """The node at `path` from the scene root - "Player/Weapon". See
        GenericNode.get_node()."""
        return self.root.get_node(path)

    def on_initialize(self):
        """Called once, when the scene is added via `SceneManager.add_scene`;
        override to build the scene's initial node tree. No-op by
        default."""
        pass

    def add(self, *node: "Node"):
        """
        Adds the entity to the scene and initializes it. 
        
        :param entity: The entity to be added.
        :type entity: Entity
        """
        self.root.add(*node)
    
    def remove(self, *ids: uuid.UUID):
        """
        Removes the entity with the given id.

        :param id: The id of the entity.
        :type id: UUID
        """
        # Unpacked - passed as `ids`, the whole tuple was looked up as a
        # single id, matched nothing, and nothing was ever removed.
        self.root.remove(*ids)

    def on_update(self):
        """
        Called when the scene is updated.
        """
        pass

    def toggle_debug_visuals(self):
        """Toggles the debug-visualization child node of every `Collider2D`
        in the scene (added if missing, removed if present - see
        `Collider2D.toggle_debug_visuals`)."""
        nodes = []
        nodes += self.root.find_nodes_with_type('Collider2D')
        for node in nodes:
            node.toggle_debug_visuals()


    def _update(self):
        self.root.update()
        self.on_update()

    def _physics_process(self):
        physics_nodes = self.root.find_nodes_with_type('PhysicsBody')

        for node in physics_nodes:
            node.on_physics_process()

        for node in physics_nodes:
            node._integrate_forces()

        # Every collider's shape is synced to its node's world transform here,
        # immediately before the narrow phase. Collider2D.on_update() also does
        # this, but that runs in the UPDATE phase and PHYSICS runs *before*
        # UPDATE each iteration (and can tick several times per update), so
        # relying on it meant testing against wherever a shape was as of last
        # frame.
        #
        # On the very first frame it meant worse than stale: a Collider2D
        # builds its shape from its own *local* position, which is the origin
        # unless one was passed, so until the first UPDATE every collider in
        # the scene sat on top of each other at world (0, 0). A body that
        # happened to start near there was shoved out of that pile before it
        # ever drew a frame.
        #
        # PhysicsWorld.step() already does exactly this for RigidBody2D, for
        # the same reason - see its own comment.
        # Each collider's bounds are computed once here, with its transform,
        # and handed to every body: neither the list nor the bounds can change
        # during the narrow phase, and doing it per body meant a full tree walk
        # and a fresh bounding box per body per step.
        #
        # Colliders belonging to a RigidBody2D are left out: they are the other
        # system's, and it already ignores everything of this one's. Including
        # them made the separation one-way - an arcade body would collide with
        # a rigid body's collider and shove itself out of it, while the rigid
        # body felt nothing. A lantern swinging on a chain would walk its
        # owner across the room, and bullets would stop dead on it.
        colliders = []
        for collider in self.root.find_nodes_with_type('Collider2D'):
            collider.apply_transform()
            if collider.rigid_body is not None:
                continue
            aabb_min, aabb_max = collider.collision_shape.get_aabb()
            colliders.append((collider, aabb_min, aabb_max))

        for node in physics_nodes:
            node._check_collisions(colliders)

        # Coexists with the loop above rather than replacing it - a scene
        # can freely mix the older arcade-physics PhysicsBody with the
        # newer, joint-capable RigidBody2D system; they're discovered by
        # different node types and don't interact with each other.
        from FreeBodyEngine.core.physics.world import step as physics_world_step
        from FreeBodyEngine import physics_delta
        physics_world_step(self, physics_delta())

