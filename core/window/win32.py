from FreeBodyEngine.utils import abstractmethod
from FreeBodyEngine.core.window import Window
from typing import TYPE_CHECKING, Union, Literal

if TYPE_CHECKING:
    from FreeBodyEngine.core.main import Main

import ctypes
import win32gui
import win32con
import win32api



class Win32Window(Window):
    """
    The Win32 implmentation of the window class. Supports both OpenGL and Vulkan renderers.
    """
    def __init__(self, main: 'Main', size: tuple[int, int], window_type, display=0):
        super().__init__(main, size, 'win32', display)
        # Register window class
        hInstance = win32api.GetModuleHandle()
        className = "Win32WindowClass"

        self._window_class = win32gui.WNDCLASS()
        self._window_class.lpfnWndProc = self.wnd_proc
        self._window_class.hInstance = hInstance
        self._window_class.lpszClassName = className
        self._atom = win32gui.RegisterClass(self._window_class)

        # Create the window
        self._window = win32gui.CreateWindow(
            self._atom,
            main.name, # title
            win32con.WS_OVERLAPPEDWINDOW, # style
            100, 100, size[0], size[1], # x, y, width, height
            0, 0, hInstance, None
        )

        # Show the window
        win32gui.ShowWindow(self._window, win32con.SW_SHOWNORMAL)
        win32gui.UpdateWindow(self._window)
        self.hdc = win32gui.GetDC(self._window)

    def wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == win32con.WM_DESTROY:
            win32gui.PostQuitMessage(0)
            self.close()
            return 0
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)


    def set_cursor(self, cursor):
        win32gui.SetCursor()

    def _create_cursor(self, image):
        pass

    def close(self):
        self.main.quit()
    
    def draw(self):
        ctypes.windll.gdi32.SwapBuffers(self.hdc)
    

    def update(self, dt):
        exists = win32gui.IsWindow(self._window)

        if not exists:
            self.close()

        win32gui.PumpWaitingMessages()