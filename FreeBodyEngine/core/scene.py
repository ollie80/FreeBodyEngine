from FreeBodyEngine.utils import abstractmethod
import uuid
from typing import TYPE_CHECKING

from FreeBodyEngine.core.node import RootNode, Node
from FreeBodyEngine.core.camera import Camera2D
from FreeBodyEngine.core.update import UpdatePhase
from FreeBodyEngine.core.service import Service
from FreeBodyEngine import register_service_update, unregister_service_update, get_service


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
        """Makes the scene named `name` the active one. Doesn't check that
        a scene with that name has been added."""
        self.active_scene = name

    def remove_scene(self, name: str):
        """Unregisters the scene named `name`, clearing `active_scene` too
        if it was the active one."""
        self.scenes.pop(name, None)
        if self.active_scene == name:
            self.active_scene = None

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
        self.root = RootNode(self)
        self.isinitialized: bool = False
        self.camera = None

    def _initialize(self):
        self.isinitialized = True
        self.on_initialize()

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
        self.root.remove(ids)

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

        for node in physics_nodes:
            node._check_collisions()

        
