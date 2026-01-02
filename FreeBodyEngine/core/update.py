from typing import Literal, Callable
from FreeBodyEngine import get_flag, MAX_FPS, MAX_TPS
from enum import Enum, auto

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from FreeBodyEngine.core.time import Time

class UpdatePhase(Enum):
    EARLY = auto()
    PHYSICS = auto()
    UPDATE = auto()
    DRAW = auto()
    LATE = auto()

class UpdateCoordinator:
    def __init__(self, time: 'Time'):
        self.time = time
        self._phases = {
            UpdatePhase.EARLY: [],
            UpdatePhase.PHYSICS: [],
            UpdatePhase.UPDATE: [],
            UpdatePhase.DRAW: [],
            UpdatePhase.LATE: []
        }

        self.update_accumulator = 0
        self.physics_accumulator = 0
        
        self.physics_timestep = 1 / get_flag(MAX_TPS, 69)
        self.update_timestep = 1 / get_flag(MAX_FPS, 69)

    def register(self, phase: UpdatePhase, callback: Callable, priority: int=0):
        self._phases[phase].append((priority, callback))
        self._phases[phase].sort(key=lambda x: x[0], reverse = True)

    def unregister(self, phase: UpdatePhase, callback: Callable):
        self._phases[phase] = [(p, cb) for (p, cb) in self._phases[phase] if cb != callback]

    def update(self):
        for _, callback in self._phases[UpdatePhase.EARLY]:
            callback()

        self.physics_accumulator += self.time.delta_time
        while self.physics_accumulator >= self.physics_timestep:
            for _, callback in self._phases[UpdatePhase.PHYSICS]:
                callback()
            
            self.physics_accumulator -= self.physics_timestep
            self.time.tick()

        self.update_accumulator += self.time.delta_time
        if self.update_accumulator >= self.update_timestep:
            for _, callback in self._phases[UpdatePhase.UPDATE]:
                callback()
            
            for _, callback in self._phases[UpdatePhase.DRAW]:
                callback()

            self.update_accumulator -= self.update_timestep
            self.time.frame()
        
        for _, callback in self._phases[UpdatePhase.LATE]:
            callback()