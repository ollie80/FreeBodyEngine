from FreeBodyEngine.utils import abstractmethod
from FreeBodyEngine import emit_event
from FreeBodyEngine.core.window import Window, Cursor, WINDOW_RESIZE
from FreeBodyEngine.core.window.win32cursor import build_cursor_from_pil
from typing import TYPE_CHECKING, Union, Literal
from FreeBodyEngine.core.service import Service
from FreeBodyEngine.core.input import Key

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
        """Builds a Win32 HCURSOR from `image`'s PIL image via build_cursor_from_pil()."""
        self.image = image
        self.handle = build_cursor_from_pil(self.image._image)

class Win32Window(Window):
    """
    The Win32 implmentation of the window class. Supports both OpenGL and Vulkan renderers.
    """
    def __init__(self, size: tuple[int, int], title):
        """Registers a Win32 window class and creates the window, marking the process DPI-aware first.

        DPI awareness is set via SetProcessDpiAwareness (falling back to the
        older SetProcessDPIAware if that API isn't available) before window
        creation, since Windows decides scaling behavior for a window based
        on the process's DPI-awareness state at creation time.
        """
        super().__init__(size, title)
        self.window_type = 'win32'

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
        

        self._window = win32gui.CreateWindow(
            self._atom,
            title, # title
            win32con.WS_OVERLAPPEDWINDOW, # style
            0, 0, size[0], size[1], # x, y, width, height
            0, 0, hInstance, None
        )

        win32gui.ShowWindow(self._window, win32con.SW_SHOWNORMAL)
        win32gui.UpdateWindow(self._window)
        self.hdc = win32gui.GetDC(self._window)
    
    

    def wnd_proc(self, hwnd, msg, wparam, lparam):
        """The window's WNDPROC - handles WM_DESTROY (closes the window), WM_PAINT (marks the window ready) and WM_SIZE (emits WINDOW_RESIZE), passing everything else to DefWindowProc."""
        if msg == win32con.WM_DESTROY:
            win32gui.PostQuitMessage(0)
            self.close()
            return 0
        
        if msg == win32con.WM_PAINT:
            self._is_ready = True

        if msg == win32con.WM_SIZE:
            rect = win32gui.GetClientRect(hwnd)

            width  = rect[2] - rect[0]
            height = rect[3] - rect[1]
            size = (width, height)
            
            emit_event(WINDOW_RESIZE, size)

        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def _set_cursor(self, cursor: Win32Cursor):
        win32gui.SetCursor(cursor.handle)
        

    def _create_cursor(self, image: 'Image'):
        return Win32Cursor(image)

    def is_ready(self):
        """True once the window has received its first WM_PAINT."""
        return self._is_ready

    @property
    def size(self):
        """The window's size, in pixels, as (right, bottom) of its window rect."""
        rect = win32gui.GetWindowRect(self._window)
        return (rect[2], rect[3])

    @size.setter
    def size(self, new: tuple[int, int]):
        """Resizes the window to `new` (width, height), in pixels, keeping its current top-left position."""

        rect = win32gui.GetWindowRect(self._window)

        win32gui.MoveWindow(self._window, rect[0], rect[1], *new, True)

    def create_mouse(self):
        """Not yet implemented - returns a bare `Service('mouse')` placeholder rather than a working Mouse."""
        return Service('mouse')

    @property
    def position(self) -> tuple[int, int]:
        """The window's position on screen, in pixels."""
        rect = win32gui.GetWindowRect(self._window)
        return (rect[0], rect[0])

    @property
    def position(self, new: tuple[int, int]):
        """Moves the window to `new` (x, y), in pixels, keeping its current size."""
        rect = win32gui.GetWindowRect(self._window)
        win32gui.MoveWindow(self._window, rect[0], rect[1], *new, True)

    def _get_key_down(self, key):
        return False

    def close(self):
        """Releases the window's device context and destroys the window."""
        win32gui.ReleaseDC(self._window, self.hdc)
        win32gui.DestroyWindow(self._window)
        self.main.quit()

    def draw(self):
        """Swaps the window's GDI buffers to present the frame."""
        ctypes.windll.gdi32.SwapBuffers(self.hdc)

    def update(self):
        """Closes the window if its native handle has become invalid, then pumps any waiting Win32 messages."""
        exists = win32gui.IsWindow(self._window)

        if not exists:
            self.close()

        win32gui.PumpWaitingMessages()