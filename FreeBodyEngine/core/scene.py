from FreeBodyEngine.utils import abstractmethod
import uuid
from typing import TYPE_CHECKING

from FreeBodyEngine.core.node import RootNode, Node
from FreeBodyEngine.core.camera import Camera2D

if TYPE_CHECKING:
    from FreeBodyEngine.core.main import Main

class Scene:
    """
    A generic scene object. The Scene's purpose is to manage entities and handle interaction with the Main object. 
    """
    def __init__(self, name: str):
        self.name = name
        self.root = RootNode(self)
        self.isinitialized: bool = False
        self.camera = None
        
    def _initialize(self, main: "Main"):
        self.main = main
        self.main.scenes[self.name] = self
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

    def on_draw(self):
        pass

    def _draw(self):
        self.on_draw()
        
        self.main.graphics.draw(self.camera)
