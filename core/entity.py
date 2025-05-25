from FreeBodyEngine.core.scene import Scene
from FreeBodyEngine.math import Vector 
from FreeBodyEngine.utils import abstractmethod
import uuid

class Entity:
    """
    A generic entity class.

    :param position: The world position of the entity.
    :type position: Vector
    """
    def __init__(self, position: Vector):
        self.position = position
        self.is_initialized = False
        
    
    def _initialize(self, scene: Scene):
        self.is_initialized = True
        self.scene = scene

        self.id = uuid.uuid4()
        while self.id in self.scene.entities: # ensures id isn't already used  
            self.id = uuid.uuid4() 
        
        self.scene.entities[self.id] = self

        self.on_initialize()

    @abstractmethod
    def on_initialize(self):
        pass

    @property
    def center(self):
        return self.position + (self.size / 2)  # Calculates center from position    
    
    @center.setter
    def center(self, new_center):
        self.position = new_center - (self.size / 2)  # Adjusts position based on new center

    def kill(self):
        """
        Removes the entity from its scene.
        """
        if self in self.scene.entities:
            self.scene.entities.remove(self)
        self.on_kill()

    def update(self):
        self.on_update()
        

    
    @abstractmethod
    def on_event_loop(self, event):
        pass
    
    @abstractmethod
    def on_kill(self):
        pass

    @abstractmethod
    def on_draw(self): 
        pass

    @abstractmethod
    def on_post_update(self):
        pass

    @abstractmethod
    def on_update(self, dt):
        pass

