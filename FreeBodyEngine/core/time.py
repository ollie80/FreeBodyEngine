import time
from FreeBodyEngine import delta, physics_delta, warning, get_main, register_service_update, unregister_service_update, get_service, service_exists
from functools import wraps
from FreeBodyEngine.core.update import UpdatePhase
from FreeBodyEngine.core.service import Service

class Time:
    """Tracks wall-clock delta time, elapsed time, and frame/tick rates for the engine's main loop (see UpdateCoordinator in core/update.py, which drives update()/tick()/frame())."""
    def __init__(self):
        """Starts the clock and zeroes all timing/counter state."""
        self._start_time = time.time()
        self._last_time = self._start_time
        self.delta_time = 0.0
        self.unscaled_delta_time = 0.0
        self.time_scale = 1.0
        self.total_time = 0.0
        self.frame_count = 0
        self._frame_times = []
        self._tick_times = []

    def get_time(self):
        """Returns the total time elapsed since this Time was created, in seconds."""
        return self.total_time

    def get_fps(self):
        """Returns the number of frames rendered in the last second (see frame())."""
        return len(self._frame_times)

    def get_tps(self):
        """Returns the number of physics ticks run in the last second (see tick())."""
        return len(self._tick_times)

    def frame(self):
        """Records that a frame was just rendered, for get_fps() - call once per rendered frame."""
        current_time = time.time()

        self._frame_times.append(current_time)
        one_second_ago = current_time - 1.0
        while self._frame_times and self._frame_times[0] < one_second_ago:
            self._frame_times.pop(0)

    def tick(self):
        """Records that a physics tick was just run, for get_tps() - call once per physics step."""
        current_time = time.time()

        self._tick_times.append(current_time)
        one_second_ago = current_time - 1.0
        while self._tick_times and self._tick_times[0] < one_second_ago:
            self._tick_times.pop(0)

    def update(self):
        """Advances the clock by one main-loop iteration: recomputes `delta_time` (scaled by `time_scale` and clamped to 0.1s, so a long stall - a debugger break, a slow load - can't make a single step simulate more than 0.1 simulated seconds) and `unscaled_delta_time`, and warns if the step took unusually long."""
        current_time = time.time()

        raw_delta = current_time - self._last_time

        self.unscaled_delta_time = raw_delta
        self.delta_time = min(raw_delta * self.time_scale, 0.1)
        self.total_time = current_time - self._start_time
        self._last_time = current_time
        self.frame_count += 1

        if self.delta_time > 0.07:
            warning(f'Delta time spike: {self.delta_time}')

class CooldownManager(Service):
    """Tracks the remaining time on every active @cooldown/@physics_cooldown-decorated call, keyed by `id(self)` of the instance the decorated method was called on."""
    def __init__(self):
        """Sets up empty cooldown-tracking dicts for both the frame-time and physics-time decorators."""
        super().__init__('cooldown_manager')
        self.cooldowns: dict[str, float] = {}
        self.physics_cooldowns = {}

    def on_initialize(self):
        """Registers update() and physics_update() to run every frame's UPDATE phase and every physics step, respectively."""
        register_service_update(UpdatePhase.UPDATE, self.update)
        register_service_update(UpdatePhase.PHYSICS, self.physics_update)

    def update(self):
        """Counts down every tracked @cooldown entry by this frame's delta time."""
        for cooldown in self.cooldowns:
            self.cooldowns[cooldown] = self.cooldowns[cooldown] - delta()

    def physics_update(self):
        """Counts down every tracked @physics_cooldown entry by one physics step's delta time."""
        for cooldown in self.physics_cooldowns:
            self.physics_cooldowns[cooldown] = self.physics_cooldowns[cooldown] - physics_delta()

    def on_destroy(self):
        """Unregisters update() and physics_update() from their update phases."""
        unregister_service_update(UpdatePhase.UPDATE, self.update)
        unregister_service_update(UpdatePhase.PHYSICS, self.physics_update)

def cooldown(seconds: float):
    """Decorator to add a cooldown to functions."""
    def decorator(method):

        def wrapper(self, *args, **kwargs):
            if service_exists('cooldown_manager'):
                id_ = id(self)
                manager = get_service('cooldown_manager')

                if id_ in manager.cooldowns:
                    if manager.cooldowns[id_] <= 0:
                        manager.cooldowns[id_] = seconds
                        return method(self, *args, **kwargs)
                else:
                    manager.cooldowns[id_] = seconds
                    return method(self, *args, **kwargs)

            return
        return wrapper
    return decorator

def physics_cooldown(seconds: float):
    """Decorator to add a cooldown to physics based functions. """
    def decorator(method):
        
        @wraps(method)
        def wrapper(self, *args, **kwargs):
            id_ = id(self)

            manager = get_service('cooldown_manager')
            if id_ in manager.physics_cooldowns:
                if manager.physics_cooldowns[id_] <= 0:
                    return method(self, *args, **kwargs)
            else:
                manager.physics_cooldowns[id_] = seconds

            return
        return wrapper
    return decorator