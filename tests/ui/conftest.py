"""Fixtures for running UI tests against both backends - the pure-Python
elements (ui/element.py) and the native ones (ui/native_element.py), when
the compiled module is built.

No engine is running here, so the services the UI asks for (window, mouse)
and the frame time are faked.
"""
import pytest

from FreeBodyEngine.math import Vector
import FreeBodyEngine.ui.base as base_module
import FreeBodyEngine.ui.element as py_backend
import FreeBodyEngine.ui.manager as manager_module

try:
    import FreeBodyEngine.ui.native_element as native_backend
except ImportError:
    native_backend = None


class FakeWindow:
    content_scale = 1.0
    framebuffer_size = (800, 600)

    def __init__(self):
        self.keys_down = set()
        self.clipboard = None
        self.safe_area_insets = (0.0, 0.0, 0.0, 0.0)

    def _get_key_down(self, key):
        return key in self.keys_down

    def get_clipboard_text(self):
        return self.clipboard


class FakeMouse:
    def __init__(self):
        self.position = Vector(0, 0)
        self.pressed = self.down = self.released = self.dragging = False

    def get_pressed(self, button):
        return self.pressed

    def get_down(self, button):
        return self.down

    def get_released(self, button):
        return self.released

    def get_dragging(self, button):
        return self.dragging

    def get_scroll_delta(self):
        return Vector(0, 0)

    def set_cursor(self, shape):
        pass


@pytest.fixture
def services(monkeypatch):
    found = {"window": FakeWindow(), "mouse": FakeMouse()}

    def get_service(name):
        return found.get(name)

    for module in (base_module, py_backend, manager_module, native_backend):
        if module is not None:
            monkeypatch.setattr(module, "get_service", get_service)
    monkeypatch.setattr(base_module, "delta", lambda: 0.5)
    return found


BACKENDS = [pytest.param(py_backend, id="python"),
            pytest.param(native_backend, id="native",
                         marks=pytest.mark.skipif(native_backend is None, reason="native UI module not built"))]


@pytest.fixture(params=BACKENDS)
def ui(request, services):
    """The backend module under test - ui.UIElement / ui.RootElement."""
    return request.param


@pytest.fixture
def fake_text(monkeypatch):
    """Stands in for the real font pipeline when "auto" measures text: 10px
    per character at any size, one line as tall as the font size."""
    def measure(styles):
        if styles.get("font") is None:
            return None
        return (len(styles.get("text") or "") * 10.0, float(styles.get("font_size", 24)))
    monkeypatch.setattr(py_backend, "measure_text", measure)


@pytest.fixture
def builders(ui, monkeypatch, fake_text):
    """FreeBodyEngine.ui.builders, building elements of the backend under
    test."""
    import FreeBodyEngine.ui.builders as module
    monkeypatch.setattr(module, "_element_class", lambda: ui.UIElement)
    return module


@pytest.fixture
def make_manager(ui):
    """Builds a UIManager whose tree uses the backend under test."""
    def make(styles=None):
        manager = manager_module.UIManager()
        manager._RootElement = ui.RootElement
        manager._UIElement = ui.UIElement
        manager.root = ui.RootElement(800, 600, styles)
        return manager
    return make
