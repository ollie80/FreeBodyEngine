from typing import Literal, Callable
from FreeBodyEngine import get_flag, MAX_FPS, MAX_TPS, warning
from enum import Enum, auto
import traceback
import time

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

        # Per-callback timing, for FreeBodyEngine.core.perf_profiler's
        # PerformanceProfiler (or any other consumer) - off by default
        # (a single `if` check per callback when disabled, effectively
        # free) since most running games never read it. When enabled,
        # `last_frame_timings` holds the *previous complete* frame's
        # (phase -> [(label, seconds), ...]) breakdown, refreshed once
        # DRAW finishes each frame (see update()) - read from a LATE-phase
        # callback to see a whole frame's data with nothing missing.
        self.profiling_enabled = False
        self._frame_timings: dict[UpdatePhase, list] = {}
        self.last_frame_timings: dict[UpdatePhase, list] = {}

    def register(self, phase: UpdatePhase, callback: Callable, priority: int=0):
        """Registers `callback` to run during `phase`, ordered by
        `priority` (highest first) among other callbacks in the same phase."""
        self._phases[phase].append((priority, callback))
        self._phases[phase].sort(key=lambda x: x[0], reverse = True)

    def unregister(self, phase: UpdatePhase, callback: Callable):
        """Removes `callback` from `phase`'s registered callbacks."""
        self._phases[phase] = [(p, cb) for (p, cb) in self._phases[phase] if cb != callback]

    @staticmethod
    def _callback_label(callback: Callable) -> str:
        """A human-readable label for a registered callback - "ClassName.
        method_name" for the overwhelmingly common case (a bound method,
        e.g. register_service_update(UpdatePhase.DRAW, self.draw)), falling
        back to __qualname__/repr for a plain function or anything else
        bound methods' own __self__ introspection doesn't cover."""
        owner = getattr(callback, '__self__', None)
        name = getattr(callback, '__name__', None)
        if owner is not None and name is not None:
            return f"{owner.__class__.__name__}.{name}"
        return getattr(callback, '__qualname__', repr(callback))

    def _run(self, callback: Callable, phase: 'UpdatePhase' = None):
        """Calls `callback`, catching and logging (rather than propagating)
        any exception it raises.

        Previously nothing here caught anything: one exception in one
        callback - a bad style value, an unhandled API error shape,
        anything - propagated straight out of update() and killed the
        entire process, every frame/every service along with it, not just
        whatever was actually broken. That's a much harsher failure mode
        than users of an app built on this engine should ever see over a
        single bug in one screen; it's also not how other engines behave
        (Unity/Godot/Unreal all log a script error and keep the frame
        going rather than tearing down the whole session). Logged with a
        full traceback via `warning()` so the bug is still loud/visible in
        the console - just not fatal to everything else running.

        When `self.profiling_enabled` (and `phase` was given - always true
        for every real call site in update() below), timing wraps the
        whole call including any exception it raised - a callback that's
        slow *and* eventually crashes still cost that time, and `finally`
        makes sure it's still recorded either way."""
        t0 = time.perf_counter() if self.profiling_enabled else None
        try:
            callback()
        except Exception:
            message = f"Unhandled exception in update callback {callback!r}:\n{traceback.format_exc()}"
            try:
                warning(message)
            except Exception:
                # warning() itself needs the 'logger' service (and a Main
                # instance) to exist - true for the whole running app in
                # practice, but not necessarily for a callback that raises
                # before startup has gotten that far. The safety net can't
                # be allowed to raise its own new exception; falling back
                # to a bare print() keeps this method's one job (never
                # propagate) true unconditionally.
                print(message)
        finally:
            if t0 is not None and phase is not None:
                elapsed = time.perf_counter() - t0
                self._frame_timings.setdefault(phase, []).append((self._callback_label(callback), elapsed))

    def update(self) -> bool:
        """Advances the loop by one iteration: runs EARLY callbacks once,
        then PHYSICS callbacks as many times as `physics_timestep` fits
        into the accumulated delta time (ticking `self.time` after each),
        then - once a full `update_timestep` has accumulated - UPDATE then
        DRAW callbacks a single time (advancing `self.time`'s frame
        counter), then LATE callbacks once. Each callback runs through
        `_run()`, so one raising doesn't stop the rest from running this
        frame, or any future frame.

        Returns whether UPDATE/DRAW actually ran this call - Main.run()
        uses this to sleep when they didn't (see its own docstring for
        why that has to be real, not skipped): LATE callbacks (window.draw
        - the buffer swap - among them, registered generically by every
        Window backend) still run unconditionally every iteration
        regardless of this return value, same as always."""
        if self.profiling_enabled:
            self._frame_timings = {}

        for _, callback in self._phases[UpdatePhase.EARLY]:
            self._run(callback, UpdatePhase.EARLY)

        self.physics_accumulator += self.time.delta_time
        while self.physics_accumulator >= self.physics_timestep:
            for _, callback in self._phases[UpdatePhase.PHYSICS]:
                self._run(callback, UpdatePhase.PHYSICS)

            self.physics_accumulator -= self.physics_timestep
            self.time.tick()

        self.update_accumulator += self.time.delta_time
        did_draw = self.update_accumulator >= self.update_timestep
        if did_draw:
            for _, callback in self._phases[UpdatePhase.UPDATE]:
                self._run(callback, UpdatePhase.UPDATE)

            for _, callback in self._phases[UpdatePhase.DRAW]:
                self._run(callback, UpdatePhase.DRAW)

            self.update_accumulator -= self.update_timestep
            self.time.frame()

        # Published *before* LATE runs (not after) so a LATE-phase reader
        # (FreeBodyEngine.core.perf_profiler.PerformanceProfiler's own
        # update, registered here) sees a complete EARLY..DRAW breakdown
        # for real, with nothing missing - not last frame's, and not
        # partially this frame's. Deliberately still lets LATE callbacks'
        # own timings accumulate into the same _frame_timings dict after
        # this point (it's the same dict object, not a copy) - they just
        # won't be visible via last_frame_timings until *next* frame's
        # publish, which is fine: nothing needs to see its own timing.
        if self.profiling_enabled:
            self.last_frame_timings = self._frame_timings

        for _, callback in self._phases[UpdatePhase.LATE]:
            self._run(callback, UpdatePhase.LATE)

        return did_draw

        
