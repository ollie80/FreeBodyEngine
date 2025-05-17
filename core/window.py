import glfw
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Union, Literal
import sdl2

if TYPE_CHECKING:
    from FreeBodyEngine.core.main import Main


class Window(ABC):
    """
    The generic window class. Its purpose is to abstract window management, also to provide input to the input manager.
    """
    def __init__(self, main: 'Main', size: tuple[int, int], graphics_api: str, title="FreeBodyEngine", display=None):
        self.main = main

    @abstractmethod
    def set_size(self, size: tuple[int, int]):
        pass

    @abstractmethod
    def close(self):
        pass

    @abstractmethod
    def update(self, dt):
        pass

class SDLWindow:
    """
    The SDL2 implementation of the window class. Supports OpenGL or Vulkan contexts.
    """
    def __init__(self, main: 'Main', size: tuple[int, int],  graphics_api=Union[Literal["opengL"] | Literal["vulkan"]], title="FreeBodyEngine", display=0):
        # Initialize SDL video subsystem
        if sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO) != 0:
            raise RuntimeError(f"SDL_Init Error: {sdl2.SDL_GetError().decode()}")
        
        self.main = main
        self.size = size
        self.title = title

        if graphics_api == "vulkan":
            graphics = sdl2.SDL_WINDOW_VULKAN
        elif graphics_api == "opengl":
            graphics = sdl2.SDL_WINDOW_OPENGL
        
        # Create SDL window
        self._window = sdl2.SDL_CreateWindow(
            title.encode('utf-8'),
            sdl2.SDL_WINDOWPOS_CENTERED,
            sdl2.SDL_WINDOWPOS_CENTERED,
            size[0],
            size[1],
            sdl2.SDL_WINDOW_SHOWN | graphics  # or SDL_WINDOW_OPENGL if you want OpenGL
        )
        
        if not self._window:
            raise RuntimeError(f"SDL_CreateWindow Error: {sdl2.SDL_GetError().decode()}")
        
        

    def set_size(self, size: tuple[int, int]):
        sdl2.SDL_SetWindowSize(self._window, size[0], size[1])
        self.size = size

    def close(self):
        sdl2.SDL_DestroyWindow(self._window)
        sdl2.SDL_Quit()

    def update(self, dt):
        # Poll SDL events
        events = sdl2.SDL_Event()
        while sdl2.SDL_PollEvent(events) != 0:
            if events.type == sdl2.SDL_QUIT:
                self.main.quit()

class GLFWWindow(Window):
    """
    The GLFW implementation of the window class. Supports both Vulkan, OpenGL and OpenGL ES renderers.
    """
    def __init__(self, main: 'Main', size: tuple[int, int], title="FreeBodyEngine", display=None):
        if not glfw.init():
            raise RuntimeError("GLFW init failed")
        glfw.window_hint(glfw.CLIENT_API, glfw.NO_API)  # no default context
        self._window = glfw.create_window(size[0], size[1], title, None, None)
        self.main = main
        if not self._window:
            glfw.terminate()
            raise RuntimeError("Failed to create GLFW window")
        glfw.show_window(self._window)

    def set_size(self, size: tuple[int, int]):
        glfw.set_window_size(self._window, size[0], size[1])

    def close(self):
        glfw.destroy_window(self._window)
        glfw.terminate()

    def update(self, dt):
        if glfw.window_should_close(self._window):
            self.main.quit()
            print("close")
        glfw.poll_events()