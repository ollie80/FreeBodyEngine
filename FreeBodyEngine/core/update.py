from typing import Literal, Callable
from FreeBodyEngine import get_flag, MAX_FPS, MAX_TPS
from enum import Enum, auto

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from FreeBodyEngine.core.time import Time

class UpdatePhase(Enum):
    """The phases a callback can hook into via
    `FreeBodyEngine.register_service_update`, run in this order by
    `UpdateCoordinator.update()` on every main-loop iteration: EARLY
    (always once), PHYSICS (zero or more times, at a fixed timestep),
    UPDATE then DRAW (at most once, throttled to the update timestep),
    LATE (always once)."""
    EARLY = auto()
    PHYSICS = auto()
    UPDATE = auto()
    DRAW = auto()
    LATE = auto()

class UpdateCoordinator:
    """Drives the main loop's fixed-timestep physics updates and framerate-
    capped update/draw updates, dispatching to callbacks registered per
    `UpdatePhase` (see `FreeBodyEngine.register_service_update`)."""

    def __init__(self, time: 'Time'):
        """Derives the physics/update timesteps from the MAX_TPS/MAX_FPS
        flags (defaulting to 69 each) and starts with no callbacks
        registered for any phase."""
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
        """Registers `callback` to run during `phase`, ordered by
        `priority` (highest first) among other callbacks in the same phase."""
        self._phases[phase].append((priority, callback))
        self._phases[phase].sort(key=lambda x: x[0], reverse = True)

    def unregister(self, phase: UpdatePhase, callback: Callable):
        """Removes `callback` from `phase`'s registered callbacks."""
        self._phases[phase] = [(p, cb) for (p, cb) in self._phases[phase] if cb != callback]

    def update(self):
        """Advances the loop by one iteration: runs EARLY callbacks once,
        then PHYSICS callbacks as many times as `physics_timestep` fits
        into the accumulated delta time (ticking `self.time` after each),
        then - once a full `update_timestep` has accumulated - UPDATE then
        DRAW callbacks a single time (advancing `self.time`'s frame
        counter), then LATE callbacks once."""
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

        
