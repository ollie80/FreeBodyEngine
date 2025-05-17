from FreeBodyEngine.core.scene import Scene
from FreeBodyEngine.graphics.manager import GraphicsManager
from FreeBodyEngine.core.window import GLFWWindow, SDLWindow
from FreeBodyEngine.graphics.gl.renderer import Renderer as GLRenderer
from FreeBodyEngine.core.window import Window

from typing import Union, Literal
import pygame
from sys import exit
from FreeBodyEngine.utils import abstractmethod

def create_window(main: 'Main', graphics_api, size, title, display) -> Window:
    if graphics_api == "opengl":
        SDLWindow(main, size, graphics_api, title, display)

    elif graphics_api == "vulkan":
        pass

def create_renderer(main, graphics_api) -> GraphicsManager:
    if graphics_api == "opengl":
        return GraphicsManager(main, GLRenderer())

class Main:
    """
    The main object. Runs the game, and handles files, graphics, input and events.  
    
    :param name: Name of the game, mainly used for window title, and save files.
    :type name: str

    :param window_size: The size of the window that will be created.
    :type window_size: tuple[int, int]
    
    :param fps: The maximum FPS (frames per second) that the game can run at.
    :type fps: int
    
    :param display: The display that the window will be created in.
    :type display: int
    
    :param dev: Option to start in developer mode. WARNING, if the game is not built and this is set to False, the file manager will not work.
    :type dev: bool

    :param pygame_flags: Flags that will be passed onto pygame during window creation.
    :type pygame_flags: int
    """
    def __init__(self, name: str = "New Game", window_size: tuple = [800, 800], fps: int = 69, display: int = 0, dev: bool = False, graphics_api: Union[Literal["opengl"] | Literal["vulkan"] | Literal["directx"] | Literal["metal"]] = "opengl"):
        self.name = name

        # scenes
        self.scenes: dict[str, Scene] = {}
        self.active_scene: Scene = None
    
        # system managers
        self.audio = None

        self.fps = fps

        # caption
        dev_mode = ""
        if dev:
            dev_mode = "DEV_MODE"

        # create window
        self.window = create_window(self, graphics_api, window_size, self.name + dev_mode, display)


    def add(self, scene: Scene):
        """
        Adds a scene and initializes it.

        :param scene: The scene to be added.
        :type scene: Scene
        """
        scene._initialize(self)

    def remove(self, name: str):
        """
        Removes a scene.

        :param name: Name of the scene.
        :type name: str
        """
        del self.scenes[name]

    def change_scene(self, name: str):
        self._set_scene(name)

    def _set_scene(self, name: str):
        self.active_scene = self.scenes[name]
        

    def quit(self):
        self.on_quit()
        self.window.close()
        exit()
    
    def _event_loop(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.quit()
            if event.type == pygame.WINDOWRESIZED:
                self.window_size = self.screen.size

            self.event_loop(event)

    @abstractmethod
    def event_loop(self, event):
        pass

    @abstractmethod
    def on_quit(self):
        pass

    def run(self):
        while True:

            if self.active_scene != None:
                self.active_scene._update(0.1)
                


        
