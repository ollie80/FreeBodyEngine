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
        start/stop if the PROFILER flag is set."""
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