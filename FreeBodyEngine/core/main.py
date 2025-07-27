from FreeBodyEngine.core.update import UpdateCoordinator
from FreeBodyEngine.core.service import ServiceLocator
from FreeBodyEngine.core.flags import GlobalFlags
from FreeBodyEngine.core.time import Time

class Main:
    def __init__(self, max_fps: int = 60, max_tps: int = 60):
        from FreeBodyEngine import _set_main
        _set_main(self)
        
        self.time = Time()
        self.updater = UpdateCoordinator(self.time, max_fps, max_tps)
        self.services = ServiceLocator()
        self.flags = GlobalFlags()
        self.running = True

    def quit(self):
        self.running = False

    def run(self):
        while self.running:
            self.time.update()
            self.updater.update()