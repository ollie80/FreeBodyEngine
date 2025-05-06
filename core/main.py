
class Main: 
    def __init__(self, SDL, window_size: tuple = [800, 800], starting_scene: Scene = None, flags=pygame.RESIZABLE, fps: int = 60, display: int = 0, asset_dir=str):
        pygame.init()
        
        self.game_name = "FreeBodyEngine"
        self.files = engine.files.FileManager(self, asset_dir)
        self.SDL = SDL
        self.window_size = window_size
        self.fps_cap = fps
        self.volume = 100
        self.fps_timer = engine.core.Timer(10)
        self.fps_timer.activate()
        self.screen = pygame.display.set_mode(self.window_size, flags, display=display)
        
        self.clock = pygame.time.Clock()
        self.dt = 0

        self.glCtx = moderngl.create_context()
        self.scenes: dict[str, Scene] = {}
        self.active_scene: Scene = None

        self.transition_manager = SceneTransitionManager(self)

    def event_loop(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                exit()
            if event.type == pygame.VIDEORESIZE:
                self.window_size = pygame.display.get_window_size()
                for scene in self.scenes:
                    self.scenes[scene].on_resize()
            self.on_event_loop(event)
            if self.active_scene:
                self.active_scene.event_loop(event)

    def on_event_loop(self, event):
        pass

    def add_scene(self, scene: Scene, name: str):
        self.scenes[name] = scene

    def remove_scene(self, name: str):
        if self.scenes[name] == self.active_scene:
            self.active_scene = None
        del self.scenes[name]

    def change_scene(self, name: str, transition: "SceneTransition" = None):
        if transition == None:
            self._set_scene(name)
        else:
            self.transition_manager.transition(transition, name)

    def _set_scene(self, name: str):
        self.active_scene = self.scenes[name]

    def has_scene(self, targetScene):
        for scene in self.scenes:
            if scene == targetScene:
                return True
        return False

    def run(self, profiler):
        total_fps = 0
        ticks = 0
        pygame.display.set_caption(f"Engine Dev       FPS: {round(self.clock.get_fps())}")

        if profiler:
            profiler_thread = threading.Thread(target=engine.debug.create_profiler_window, daemon=True)
            profiler_thread.start()
            
        while True: 
            dt = self.clock.tick(self.fps_cap) / 1000
            total_fps += self.clock.get_fps()
            ticks += 1
            self.fps_timer.update(dt)
            if self.fps_timer.complete:
                pygame.display.set_caption(f"Engine Dev       FPS: {round(total_fps/ticks)}")
                self.fps_timer.activate()
            self.event_loop()
            self.transition_manager.update(dt)

            if self.active_scene:
                self.active_scene.update(dt)
            self.transition_manager.draw()
            pygame.display.flip() 
