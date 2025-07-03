import glfw
from FreeBodyEngine.core.window import Window, Cursor
from FreeBodyEngine.utils import abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from FreeBodyEngine.core.main import Main
    from FreeBodyEngine.graphics.image import Image

class GLFWWindow(Window):
    def __init__(self, main: 'Main', size: tuple[int, int], window_type: str, title="FreeBodyEngine", display=None):
        super().__init__(main, size, window_type, title, display)
        self._size = size
        self._title = title
        self._should_close = False

        if not glfw.init():
            raise RuntimeError("GLFW failed to initialize")
        
        if main.dev:
            debug = glfw.TRUE
        else:
            debug = glfw.FALSE
        glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 4)
        glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
        glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
        glfw.window_hint(glfw.OPENGL_DEBUG_CONTEXT, debug)

        self._window = glfw.create_window(size[0], size[1], title, None, None)
        if not self._window:
            glfw.terminate()
            raise RuntimeError("Failed to create GLFW window")

        glfw.make_context_current(self._window)
        glfw.set_window_size_callback(self._window, self.resize)


    @property
    def size(self) -> tuple[int, int]:
        return glfw.get_window_size(self._window)

    def resize(self, window, width, height):
        self._resize()

    @size.setter
    def size(self, new: tuple[int, int]):
        glfw.set_window_size(self._window, new[0], new[1])

    @property
    def position(self) -> tuple[int, int]:
        return glfw.get_window_pos(self._window)

    @position.setter
    def position(self, new: tuple[int, int]):
        glfw.set_window_pos(self._window, new[0], new[1])

    def is_ready(self) -> bool:
        return not glfw.window_should_close(self._window)

    def _create_cursor(self, image: 'Image'):
        pass

    def _set_cursor(self, cursor: 'Cursor'):
        pass

    def close(self):
        glfw.set_window_should_close(self._window, True)
        glfw.destroy_window(self._window)
        glfw.terminate()

    def draw(self):
        glfw.swap_buffers(self._window)

    def update(self):
        glfw.poll_events()
        if glfw.window_should_close(self._window):
            
            self.main.quit()
        