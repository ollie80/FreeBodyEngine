import sys
from FreeBodyEngine.core.update import UpdateCoordinator
from FreeBodyEngine.core.service import ServiceLocator
from FreeBodyEngine.core.flags import GlobalFlags
from FreeBodyEngine.core.profiler import Profiler
from FreeBodyEngine.core.time import Time
from FreeBodyEngine import _get_pre_flags, register_event_callback, QUIT, PROFILER, get_flag
import cProfile
import pstats

class Main:
    """The engine's top-level singleton - owns global flags, timing, the
    update-loop coordinator, and the service locator, and drives the main
    loop via `run()`. Constructing one registers it as the module-level
    "main object" (`FreeBodyEngine._set_main`), which is what
    `fb.get_main()`/`fb.get_service()`/etc. all resolve against."""

    def __init__(self):
        """Sets up flags (seeded from any `fb.set_flag()` calls made before
        the engine existed), timing, the update coordinator, and the
        service locator, and registers itself as the global `Main`
        instance. Also wires the QUIT event to `self.quit`, so
        `fb.fbquit()`/emitting QUIT stops the main loop."""
        from FreeBodyEngine import _set_main
        pre_flags = _get_pre_flags()

        _set_main(self)

        self.flags = GlobalFlags(pre_flags)
        self.time = Time()
        self.updater = UpdateCoordinator(self.time)
        self.services = ServiceLocator()
        
        self.running = True
        
        register_event_callback(QUIT, self.quit)


    def quit(self):
        """Stops the main loop after its current iteration finishes."""
        self.running = False

    def run(self):
        """Runs the engine's main loop until `quit()` is called: advances
        time and drives every registered update phase through
        `self.updater` each iteration. Wraps each iteration in a `Profiler`
        start/stop if the PROFILER flag is set.

        Under Pyodide (`sys.platform == "emscripten"` - a browser tab, see
        utils.get_platform()'s docstring) this delegates to `_run_web()`
        instead of looping here directly - see that method for why a
        blocking `while` loop is fundamentally incompatible with a browser
        tab at all, not just a style difference."""
        if sys.platform == "emscripten":
            self._run_web()
            return

        if get_flag(PROFILER, False):
            profiler = Profiler()

        while self.running:

            self.time.update()

            if get_flag(PROFILER, False):

                profiler.start()

            self.updater.update()

            if get_flag(PROFILER, False):

                profiler.stop()

        if get_flag(PROFILER, False):
            profiler.close()

    def _run_web(self):
        """The browser-tab equivalent of run()'s blocking `while self.
        running` loop: a real `while` here would never yield back to the
        browser at all, which would freeze the tab solid on the very first
        iteration (a browser only repaints, delivers input, or runs *any*
        other JS between tasks it was already given - a synchronous
        infinite loop inside one task starves all of that forever, forever
        being the operative word since nothing ever gets to interrupt a
        WASM `while` loop from outside).

        The fix is the standard one for porting a native game loop to the
        web: turn each iteration into its own `requestAnimationFrame`
        callback that reschedules itself, so control genuinely returns to
        the browser between frames the exact same way a native OS's own
        event loop gets a turn between this engine's frames there. `run()`
        itself returns immediately after kicking off the first frame -
        the project's main.py finishes executing right after calling
        `main.run()`, same as it always looks from the game code's side,
        but the engine keeps running because the browser keeps calling
        this callback, not because anything here is still blocking."""
        import js
        from pyodide.ffi import create_proxy

        if get_flag(PROFILER, False):
            profiler = Profiler()
        else:
            profiler = None

        frame_count = [0]

        def frame(_timestamp):
            if not self.running:
                return

            self.time.update()

            if profiler is not None:
                profiler.start()

            frame_count[0] += 1
            if frame_count[0] <= 5 or frame_count[0] % 60 == 0:
                from FreeBodyEngine import warning as _dbg
                _dbg(f"[DEBUG frame] #{frame_count[0]} starting updater.update()")

            try:
                self.updater.update()
            except Exception as e:
                from FreeBodyEngine import warning as _dbg
                import traceback
                _dbg(f"[DEBUG frame] EXCEPTION in updater.update(): {e}\n{traceback.format_exc()}")
                raise

            if frame_count[0] <= 5 or frame_count[0] % 60 == 0:
                from FreeBodyEngine import warning as _dbg
                _dbg(f"[DEBUG frame] #{frame_count[0]} finished updater.update()")

            if profiler is not None:
                profiler.stop()

            if self.running:
                js.window.requestAnimationFrame(create_proxy(frame))
            elif profiler is not None:
                profiler.close()

        js.window.requestAnimationFrame(create_proxy(frame))