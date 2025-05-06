
class Entity:
    def __init__(self, position: vector, scene, size=vector(32, 32), tag='none', anchor="center"):
        self.scene: Scene = scene
        self.tag = tag
        self.position = position
        self.screen_position = position
        self.components: list[Component] = []
        self.size = size
        
        self.anchor = anchor

    @property
    def center(self):
        return self.position + (self.size / 2)  # Calculates center from position    
    
    @center.setter
    def center(self, new_center):
        self.position = new_center - (self.size / 2)  # Adjusts position based on new center

    def kill(self):
        if self in self.scene.entities:
            self.scene.entities.remove(self)
        self.on_kill()

    def update(self, dt):
        self.on_update(dt)
        
        for component in self.components:
            component.update(dt)
        self.on_post_update()     
    
    def on_event_loop(self, event):
        pass
    
    def on_kill(self):
        pass
    
    def on_draw(self): 
        pass

    def on_post_update(self):
        pass

    def on_update(self, dt):
        pass
