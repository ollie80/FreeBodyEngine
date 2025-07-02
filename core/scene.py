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

    def on_update(self, dt):
        """
        Called when the scene is updated.
        """
        pass

    def _update(self):
        self.root.update()

    def on_draw(self):
        pass

    def _draw(self):
        self.on_draw()
        
        self.main.graphics.draw(self.camera)

# class SceneTransition:
#     def __init__(self, main: "Main", vert, frag, duration, curve = engine.math.Linear()):
#         self.elapsed = 0
#         self.duration = duration 
#         self.time: int = 0
        
#         self._reversed = False

#         self.main = main
#         self.curve = curve

#         self.program = self.main.glCtx.program(vert, frag)
        
#         self.vao = engine.graphics.create_fullscreen_quad(self.main.glCtx, self.program)        

#     def update(self, dt):
#         if not self._reversed:
#             self.elapsed = min(self.elapsed + dt, self.duration) 
#             self.time = self.curve.get_value(self.elapsed/self.duration)

#             if self.time >= 1:
#                 self._reversed = True
#                 self.main._set_scene(self.main.transition_manager.new_scene)
#         else:
#             self.elapsed = max(self.elapsed - dt, 0)
#             if self.elapsed == 0:
#                 self.time = 0
#             else:
#                 self.time = self.curve.get_value(self.elapsed/self.duration)            
            
#             if self.time <= 0:
#                 self.main.transition_manager.current_transition = None        
        

#     def draw(self):
#         self.program['time'] = self.time
#         if "inverse" in self.program:
#             self.program['inverse'] = not self._reversed 
#         self.main.glCtx.screen.use()
#         self.vao.render(moderngl.TRIANGLE_STRIP)

# class FadeTransition(SceneTransition):
#     def __init__(self, main: "Main", duration: int):
#         super().__init__(main, main.files.load_text('engine/shader/graphics/empty.vert'), main.files.load_text('engine/shader/scene_transitions/fade.glsl'), duration, engine.math.EaseInOut())

# class StarWarsTransition(SceneTransition):
#     def __init__(self, main: "Main", duration: int):
#         super().__init__(main, main.files.load_text('engine/shader/graphics/uv.vert'), main.files.load_text('engine/shader/scene_transitions/starwars.glsl'), duration, engine.math.EaseInOut())

# class SceneTransitionManager:
#     def __init__(self, main: Main):
#         self.main = main
#         self.current_transition: SceneTransition = None
#         self.new_scene: str = None

#     def transition(self, transition: SceneTransition, new_scene: str):
#         self.current_transition = transition
#         self.new_scene = new_scene

#     def update(self, dt):
#         if self.current_transition:
#             self.current_transition.update(dt)

#     def draw(self):
#         if self.current_transition:
#             self.current_transition.draw()

# class SplashScreenScene(Scene):
#     def __init__(self, main: Main, duration: int, new_scene: str, texture: moderngl.Texture, color: str, transition=None):
#         self.timer = Timer(duration)
#         self.duration = duration
#         self.timer.activate()
#         self.transition = transition
#         super().__init__(main)
#         self.graphics.rendering_mode = "general"
#         self.camera.background_color.hex = color

#         self.new_scene = new_scene
#         aspect = engine.graphics.get_texture_aspect_ratio(texture)
#         self.ui.add(engine.ui.UIImage(self.ui, texture, {"anchor": "center", "height": "50%h", "aspect-ratio": aspect}))
        
#         self.started_transition = False

#     def on_update(self, dt):
#         self.timer.update(dt)
        
#         if self.timer.complete and not self.started_transition:
#             self.started_transition = True
#             if self.transition == None:
#                 transition =  StarWarsTransition(self.main, self.duration)
#             else:
#                 transition = self.transition
#             self.main.change_scene(self.new_scene, transition)
