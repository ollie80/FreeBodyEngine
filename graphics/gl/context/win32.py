import ctypes
from ctypes import wintypes
import win32gui
import win32con

class PIXELFORMATDESCRIPTOR(ctypes.Structure):
    _fields_ = [
        ('nSize', wintypes.WORD),
        ('nVersion', wintypes.WORD),
        ('dwFlags', wintypes.DWORD),
        ('iPixelType', wintypes.BYTE),
        ('cColorBits', wintypes.BYTE),
        ('cRedBits', wintypes.BYTE),
        ('cRedShift', wintypes.BYTE),
        ('cGreenBits', wintypes.BYTE),
        ('cGreenShift', wintypes.BYTE),
        ('cBlueBits', wintypes.BYTE),
        ('cBlueShift', wintypes.BYTE),
        ('cAlphaBits', wintypes.BYTE),
        ('cAlphaShift', wintypes.BYTE),
        ('cAccumBits', wintypes.BYTE),
        ('cAccumRedBits', wintypes.BYTE),
        ('cAccumGreenBits', wintypes.BYTE),
        ('cAccumBlueBits', wintypes.BYTE),
        ('cAccumAlphaBits', wintypes.BYTE),
        ('cDepthBits', wintypes.BYTE),
        ('cStencilBits', wintypes.BYTE),
        ('cAuxBuffers', wintypes.BYTE),
        ('iLayerType', wintypes.BYTE),
        ('bReserved', wintypes.BYTE),
        ('dwLayerMask', wintypes.DWORD),
        ('dwVisibleMask', wintypes.DWORD),
        ('dwDamageMask', wintypes.DWORD),
    ]



# Pixel format flags
PFD_DRAW_TO_WINDOW = 0x00000004
PFD_SUPPORT_OPENGL = 0x00000020
PFD_DOUBLEBUFFER   = 0x00000001
PFD_TYPE_RGBA      = 0
PFD_MAIN_PLANE     = 0

def format_error(err_code):
    buf = ctypes.create_unicode_buffer(256)
    ctypes.windll.kernel32.FormatMessageW(
        0x00001000,  # FORMAT_MESSAGE_FROM_SYSTEM
        None,
        err_code,
        0,
        buf,
        len(buf),
        None
    )
    return buf.value.strip()


def create_context(hwnd):
    hdc = win32gui.GetDC(hwnd)
    
    # Set up the pixel format descriptor
    pfd = PIXELFORMATDESCRIPTOR()
    pfd.nSize = ctypes.sizeof(PIXELFORMATDESCRIPTOR)
    pfd.nVersion = 1
    pfd.dwFlags = PFD_DRAW_TO_WINDOW | PFD_SUPPORT_OPENGL | PFD_DOUBLEBUFFER
    pfd.iPixelType = PFD_TYPE_RGBA
    pfd.cColorBits = 32
    pfd.cRedBits = 8
    pfd.cGreenBits = 8
    pfd.cBlueBits = 8
    pfd.cAlphaBits = 8
    pfd.cDepthBits = 24
    pfd.cStencilBits = 8
    pfd.iLayerType = PFD_MAIN_PLANE
    pfd.nSize = ctypes.sizeof(PIXELFORMATDESCRIPTOR)
    pfd.nVersion = 1
    pfd.dwFlags = PFD_DRAW_TO_WINDOW | PFD_SUPPORT_OPENGL | PFD_DOUBLEBUFFER
    pfd.iPixelType = PFD_TYPE_RGBA
    pfd.cColorBits = 32
    pfd.cDepthBits = 24
    pfd.iLayerType = PFD_MAIN_PLANE

    gdi32 = ctypes.WinDLL('gdi32')
    pixel_format = gdi32.ChoosePixelFormat(hdc, ctypes.byref(pfd))
    if pixel_format == 0:
        raise RuntimeError("ChoosePixelFormat failed")

    if not gdi32.SetPixelFormat(hdc, pixel_format, ctypes.byref(pfd)):
        raise RuntimeError("SetPixelFormat failed")

    opengl32 = ctypes.WinDLL('opengl32')

    # Define HGLRC manually
    HGLRC = ctypes.c_void_p

    # Load and define wglCreateContext
    wglCreateContext = opengl32.wglCreateContext
    wglCreateContext.argtypes = [wintypes.HDC]
    wglCreateContext.restype = HGLRC

    # Load and define wglMakeCurrent
    wglMakeCurrent = opengl32.wglMakeCurrent
    wglMakeCurrent.argtypes = [wintypes.HDC, HGLRC]
    wglMakeCurrent.restype = wintypes.BOOL

    # Create and activate context
    hrc = wglCreateContext(hdc)
    
    if not hrc:

        err = ctypes.windll.kernel32.GetLastError()
        raise RuntimeError(f"wglCreateContext failed with error code: {format_error(err)}")

    if not wglMakeCurrent(hdc, hrc):
        raise RuntimeError("wglMakeCurrent failed")

    return hrc
