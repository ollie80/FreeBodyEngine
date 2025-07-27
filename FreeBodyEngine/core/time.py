import time
from FreeBodyEngine import delta, physics_delta, get_main, register_service_update, unregister_service_update, get_service, service_exists
from functools import wraps
from FreeBodyEngine.core.service import Service


class Time:
    def __init__(self):
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
        return self.total_time

    def get_fps(self):
        return len(self._frame_times)

    def get_tps(self):
        return len(self._tick_times)
    
    def frame(self):
        current_time = time.time()
        
        self._frame_times.append(current_time)
        one_second_ago = current_time - 1.0
        while self._frame_times and self._frame_times[0] < one_second_ago:
            self._frame_times.pop(0)

    def tick(self):
        current_time = time.time()
        
        self._tick_times.append(current_time)
        one_second_ago = current_time - 1.0
        while self._tick_times and self._tick_times[0] < one_second_ago:
            self._tick_times.pop(0)

    def update(self):
        current_time = time.time()

        raw_delta = current_time - self._last_time

        self.unscaled_delta_time = raw_delta
        self.delta_time = raw_delta * self.time_scale
        self.total_time = current_time - self._start_time
        self._last_time = current_time
        self.frame_count += 1


class CooldownManager(Service):
    def __init__(self):
        super().__init__('cooldown_manager')
        self.cooldowns: dict[str, float] = {}
        self.physics_cooldowns = {}

    def on_initialize(self):
        register_service_update('early', self.update)

    def update(self):
        for cooldown in self.cooldowns:
            self.cooldowns[cooldown] = self.cooldowns[cooldown] - delta()
        
        for cooldown in self.physics_cooldowns:
            self.physics_cooldowns[cooldown] = self.physics_cooldowns[cooldown] - physics_delta()

    def on_destroy(self):
        unregister_service_update('early', self.update)

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