from FreeBodyEngine.utils import abstractmethod
from FreeBodyEngine.core.window import Window, Cursor
from FreeBodyEngine.core.window.win32cursor import build_cursor_from_pil
from typing import TYPE_CHECKING, Union, Literal

if TYPE_CHECKING:
    from FreeBodyEngine.core.main import Main
    from FreeBodyEngine.graphics.image import Image

import ctypes
import win32gui
import win32con
import win32api


user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LR_DEFAULTSIZE = 0x00000040
LR_LOADFROMFILE = 0x00000010
LR_CREATEDIBSECTION = 0x00002000
IMAGE_CURSOR = 2

class Win32Cursor(Cursor):
    """
    The Win32 implementation of the cursor class. Converts image into .cur file format and sets up for use with Win32.
    """
    def __init__(self, image: 'Image'):
        self.image = image
        self.handle = build_cursor_from_pil(self.image._image)

class Win32Window(Window):
    """
    The Win32 implmentation of the window class. Supports both OpenGL and Vulkan renderers.
    """
    def __init__(self, main: 'Main', size: tuple[int, int], window_type, display=0):
        super().__init__(main, size, 'win32', display)
        # Register window class
        hInstance = win32api.GetModuleHandle()
        className = "Win32WindowClass"
        self._is_ready = False

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # SYSTEM_DPI_AWARE
        except:
            ctypes.windll.user32.SetProcessDPIAware()  # fallback

        self._window_class = win32gui.WNDCLASS()
        self._window_class.lpfnWndProc = self.wnd_proc
        self._window_class.hInstance = hInstance
        self._window_class.lpszClassName = className
        self._atom = win32gui.RegisterClass(self._window_class)
        self._window_class.style = win32con.CS_OWNDC

        # Create the window
        self._window = win32gui.CreateWindow(
            self._atom,
            main.name, # title
            win32con.WS_OVERLAPPEDWINDOW, # style
            0, 0, size[0], size[1], # x, y, width, height
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
        if msg == win32con.WM_PAINT:
            self._is_ready = True
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def _set_cursor(self, cursor: Win32Cursor):
        win32gui.SetCursor(cursor.handle)

    def _create_cursor(self, image: 'Image'):
        return Win32Cursor(image)

    def is_ready(self):
        return self._is_ready

    @property
    def size(self):
        rect = win32gui.GetWindowRect(self._window)
        return (rect[2], rect[3])
    
    @size.setter
    def size(self, new: tuple[int, int]):
        rect = win32gui.GetWindowRect(self._window)
        
        win32gui.MoveWindow(self._window, rect[0], rect[1], *new, True)

    @property
    def position(self) -> tuple[int, int]:
        rect = win32gui.GetWindowRect(self._window)
        return (rect[0], rect[0])
    
    @property
    def position(self, new: tuple[int, int]):
        rect = win32gui.GetWindowRect(self._window)
        win32gui.MoveWindow(self._window, rect[0], rect[1], *new, True)
        

    def close(self):
        win32gui.ReleaseDC(self._window, self.hdc)
        win32gui.DestroyWindow(self._window)
        self.main.quit()

    def draw(self):
        ctypes.windll.gdi32.SwapBuffers(self.hdc)

    def update(self):
        exists = win32gui.IsWindow(self._window)

        if not exists:
            self.close()

        win32gui.PumpWaitingMessages()