from FreeBodyEngine.core.time import Time
from typing import Literal, Callable

class UpdateCoordinator:
    def __init__(self, time: Time, max_fps: int = 60, max_tps:  int = 60):
        self.time = time
        self._phases = {
            "early": [],
            "physics": [],
            "update": [],
            "draw": [],
            "late": []
        }

        self.update_accumulator = 0
        self.physics_accumulator = 0
        
        self.physics_timestep = 1 / max_tps
        self.update_timestep = 1 / max_fps

    def register(self, phase: Literal["early", 'physics', "update", "draw", "late"], callback: Callable, priority: int=0):
        self._phases[phase].append((priority, callback))
        self._phases[phase].sort(key=lambda x: x[0])

    def unregister(self, phase: Literal["early", 'physics', "update", "draw", "late"], callback: Callable):
        self._phases[phase] = [(p, cb) for (p, cb) in self._phases[phase] if cb != callback]

    def update(self):
        for _, callback in self._phases['early']:
            callback()

        self.physics_accumulator += self.time.delta_time
        while self.physics_accumulator >= self.physics_timestep:
            for _, callback in self._phases['physics']:
                callback()
            
            self.physics_accumulator -= self.physics_timestep
            self.time.tick()

        self.update_accumulator += self.time.delta_time
        if self.update_accumulator >= self.update_timestep:
            for _, callback in self._phases['update']:
                callback()
            

            for _, callback in self._phases['draw']:
                callback()

            self.update_accumulator -= self.update_timestep
            self.time.frame()
        
        for _, callback in self._phases['late']:
            callback()