from FreeBodyEngine.ui.manager import UIManager
from FreeBodyEngine.ui.renderer import UIRenderer


def get_ui_renderer():
    """Returns the right 'ui_renderer' Service class for how this session
    is running - TerminalUIRenderer under `fb.TERMINAL_WINDOW`, the normal
    GL-based UIRenderer otherwise.

    Dispatches on the TERMINAL_WINDOW *flag*, not utils.get_platform() the
    way core.window.get_window()/graphics.get_renderer()/audio.
    get_audio_manager() dispatch on OS/platform - terminal mode is an
    explicit opt-in choice layered on top of a normal desktop platform
    (see core/window/__init__.py's get_window(), which checks this exact
    same flag alongside TEST_WINDOW/HEADLESS/etc.), not a distinct host
    environment the way web/android are.

    Existing projects that instantiate `UIRenderer()` directly (the only
    way to get one before this existed) keep working unchanged - this is
    an added convenience for new code that wants to stay backend-agnostic
    the same way `fb.core.window.get_window()()` already lets project code
    avoid hardcoding a platform-specific window class."""
    from FreeBodyEngine import get_flag, TERMINAL_WINDOW

    if get_flag(TERMINAL_WINDOW, False):
        from FreeBodyEngine.ui.terminal_renderer import TerminalUIRenderer
        return TerminalUIRenderer

    return UIRenderer


_resolved_element_classes = None


def _resolve_element_classes():
    """Picks UIElement/RootElement's actual implementation - the compiled
    C++ Node-backed one (ui.native_element) or the pure-Python one
    (ui.element) - and caches the choice for the rest of the process.

    Deliberately lazy (called the first time UIElement/RootElement is
    actually accessed, via this module's __getattr__ below - see PEP 562)
    rather than decided at import time: FreeBodyEngine/__init__.py imports
    this package eagerly (`from FreeBodyEngine import ui`) as part of
    `import FreeBodyEngine` itself, before a project has any chance to
    call fb.set_flag(fb.NATIVE_UI, ...) - an eager decision here would
    permanently lock in the default before that flag could ever take
    effect. get_ui_renderer() above sidesteps the same problem by being a
    function callers invoke explicitly, after flags are set; UIElement is
    constructed directly at hundreds of call sites across every project
    built on this engine, so it can't become a function without breaking
    every one of them - this lazy-attribute approach gets the same
    "decided after flags are set" property without changing how
    UIElement/RootElement are used anywhere.

    Native is the default everywhere except get_platform() == "web" (a
    compiled Python extension can't exist there at all - see
    ui/native_element.py's own docstring), and silently falls back to the
    pure-Python implementation if the native module simply hasn't been
    built yet (scripts/build_native.py) even where the flag/platform would
    otherwise choose it - an engine dev without a C++ toolchain handy, or
    a downstream install without a prebuilt wheel yet, still gets a
    working engine rather than an ImportError."""
    global _resolved_element_classes
    if _resolved_element_classes is not None:
        return _resolved_element_classes

    from FreeBodyEngine import get_flag, NATIVE_UI, warning
    from FreeBodyEngine.utils import get_platform

    use_native = get_flag(NATIVE_UI, get_platform() != "web")

    if use_native:
        try:
            from FreeBodyEngine.ui.native_element import UIElement, RootElement
            print("[FreeBodyEngine] UI backend: native (C++/pybind11) - FreeBodyEngine.ui.native_element")
            _resolved_element_classes = (UIElement, RootElement)
            return _resolved_element_classes
        except ImportError as e:
            # A silent fallback is the right *behavior* here (see this
            # function's own docstring on why: an engine dev without a
            # C++ toolchain, or a downstream install missing a prebuilt
            # wheel, should still get a working engine) - but silent
            # doesn't mean invisible. Without this warning, a native
            # build that fails to import for any reason (missing
            # cpp_scripts/, a real ABI mismatch, a missing shared
            # library the compiled extension itself depends on - e.g.
            # libc++_shared.so on Android) falls back to pure Python with
            # zero observable signal that it happened at all - confirmed
            # to actually cause real confusion once: an Android build
            # that "worked" but showed none of the expected native
            # speedup, with nothing in logcat pointing at why.
            warning(f"[FreeBodyEngine] Native UI requested but unavailable ({e}) - falling back to the pure-Python UIElement (FreeBodyEngine.ui.element).")

    from FreeBodyEngine.ui.element import UIElement, RootElement
    _resolved_element_classes = (UIElement, RootElement)
    return _resolved_element_classes


def __getattr__(name):
    if name in ("UIElement", "RootElement"):
        ui_element, root_element = _resolve_element_classes()
        return {"UIElement": ui_element, "RootElement": root_element}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["UIManager", "UIElement", "RootElement", "UIRenderer", "get_ui_renderer"]
