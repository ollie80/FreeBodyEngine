import sys
from FreeBodyEngine.core.update import UpdateCoordinator
from FreeBodyEngine.core.service import ServiceLocator
from FreeBodyEngine.core.flags import GlobalFlags
from FreeBodyEngine.core.time import Time
from FreeBodyEngine import _get_pre_flags, register_event_callback, QUIT, PROFILE_LAUNCH, get_flag
import cProfile
import pstats

class Main:
    def __init__(self):
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
        self.running = False

    def run(self):
        profile = get_flag(PROFILE_LAUNCH, False)
        if profile:
            profiler = cProfile.Profile()
            profiler.enable()

        while self.running:
            self.time.update()
            self.updater.update()

        if profile:
            profiler.disable()
            stats = pstats.Stats(profiler)
            stats.sort_stats('cumtime').print_stats("FreeBodyEngine", 20)