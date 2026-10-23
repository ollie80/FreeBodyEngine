"""Tests for GLFWMouse cursor locking.

lock_position()/unlock_position() were never implemented on GLFWMouse - the
mouse of the default desktop window - so they raised NotImplementedError.
"""
import pytest

glfw = pytest.importorskip('glfw')


@pytest.fixture
def mouse():
    if not glfw.init():
        pytest.skip('GLFW cannot start here (no display)')
    glfw.window_hint(glfw.VISIBLE, glfw.FALSE)
    handle = glfw.create_window(64, 64, 'mouse test', None, None)
    if not handle:
        glfw.terminate()
        pytest.skip('GLFW cannot create a window here')

    from FreeBodyEngine.core.window.glfw import GLFWMouse

    class Window:
        _window = handle

    yield GLFWMouse(Window())
    glfw.destroy_window(handle)
    glfw.terminate()


def test_lock_and_unlock(mouse):
    handle = mouse.window._window
    mouse.lock_position()
    assert glfw.get_input_mode(handle, glfw.CURSOR) == glfw.CURSOR_DISABLED
    mouse.unlock_position()
    assert glfw.get_input_mode(handle, glfw.CURSOR) == glfw.CURSOR_NORMAL
