from FreeBodyEngine.core.scene import Scene
from FreeBodyEngine.graphics.manager import GraphicsManager
from FreeBodyEngine.core.window import Win32Window
from FreeBodyEngine.graphics.renderer import Renderer
from FreeBodyEngine.graphics.gl import GLRenderer
from FreeBodyEngine.core.window import Window
from FreeBodyEngine.core.files import FileManager
from FreeBodyEngine.core.logger import Logger
from FreeBodyEngine.core import Time
from FreeBodyEngine.graphics.color import Color
from FreeBodyEngine import log, warning
from FreeBodyEngine.utils import abstractmethod
from typing import Union, Literal
from sys import exit
import os
import json


def create_window(main: 'Main', window, size, title, display) -> Window:
    if window == "win32":
        return Win32Window(main, size, window, display)
    else:
        raise NotImplementedError(f"No window implemented with name {window}.")


def create_renderer(main, graphics_api) -> Renderer:
    if graphics_api == "opengl":
        return GLRenderer(main)

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
    def __init__(self, name: str = "New Game", window_size: tuple = [800, 800], fps: int = 69, display: int = 0, dev: bool = False, graphics_api: Union[Literal["opengl"] | Literal["vulkan"] | Literal["directx"] | Literal["metal"]] = "opengl", headless: bool = False):
        from FreeBodyEngine import _set_main
        _set_main(self)
        
        self.headless_mode = headless
        self.name = name
        
        # scenes
        self.scenes: dict[str, Scene] = {}
        self.active_scene: Scene = None
    
        # system managers
        self.audio = None
        self.logger = Logger()
        self.time = Time()

        if dev:
            if os.path.exists('build.json'): 
                build_settings = json.loads(open('build.json').read())
                asset_path = build_settings.get('assets', './assets')
            else:
                print('No build file found at ./build.json.')
            self.files = FileManager(self, asset_path, dev)
        else:
            self.files = FileManager(self, './dev/assets', dev)

        self.fps = fps

        # caption
        dev_mode = ""
        if dev:
            dev_mode = "DEV_MODE"

        # create window and graphics
        if not self.headless_mode:
            self.window = create_window(self, 'win32', window_size, self.name + dev_mode, display)
            self.renderer = create_renderer(self, graphics_api)
            self.graphics = GraphicsManager(self, self.renderer)

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
        log("Quiting game.")
        self.on_quit()
        exit(0)    

    def on_quit(self):
        pass

    def run(self):
        while True:
            
            self.time.update(self.fps)
            if not self.headless_mode:
                self.window.update()

            if self.active_scene != None:
                self.active_scene._update()
                self.on_update()
            self.logger.update()

    def on_update(self):
        pass
                


        
