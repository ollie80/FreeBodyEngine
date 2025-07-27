from FreeBodyEngine.utils import abstractmethod
import uuid
from typing import TYPE_CHECKING

from FreeBodyEngine.core.node import RootNode, Node
from FreeBodyEngine.core.camera import Camera2D
from FreeBodyEngine.core.service import Service
from FreeBodyEngine import register_service_update, unregister_service_update, get_service


if TYPE_CHECKING:
    from FreeBodyEngine.core.main import Main

def add_scene(scene: 'Scene'):
    get_service('scene_manager').add_scene(scene)

def set_scene(name: str):
    get_service('scene_manager').set_scene(name)

def remove_scene(name: str):
    get_service('scene_manager').remove_scene(name)

class SceneManager(Service):
    def __init__(self):
        super().__init__('scene_manager')
        self.scenes: dict[str, 'Scene'] = {}
        self.active_scene: str | None = None

    def on_initialize(self):
        register_service_update('update', self.update)
        register_service_update('physics', self.physics_update)

    def on_destroy(self):
        unregister_service_update('update', self.update)
        unregister_service_update('physics', self.physics_update)

    def get_active(self) -> 'Scene':
        return self.scenes.get(self.active_scene, None)
    
    def add_scene(self, scene: 'Scene'):
        self.scenes[scene.name] = scene
        scene._initialize()
    
    def set_scene(self, name: str):
        self.active_scene = name

    def remove_scene(self, name: str):
        self.scenes.pop(name, None)
        if self.active_scene == name:
            self.active_scene = None

    def physics_update(self):
        if self.active_scene:
            self.scenes[self.active_scene]._physics_process()

    def update(self):
        if self.active_scene:            
            self.scenes[self.active_scene]._update()


    

class Scene:
    """
    A generic scene object. The Scene's purpose is to manage entities and handle interaction with the Main object. 
    """
    def __init__(self, name: str):
        self.name = name
        self.root = RootNode(self)
        self.isinitialized: bool = False
        self.camera = None
        
    def _initialize(self):
        self.isinitialized = True
        self.on_initialize()

    def on_initialize(self):
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

        
