"""Tests for UpdateCoordinator's frame pacing.

The frame accumulator had no cap. Every frame slower than the frame cap left
its overrun behind, and once the game sped up again it drew back-to-back with
no limit until all of it was paid off.
"""
from FreeBodyEngine.core.update import UpdateCoordinator, UpdatePhase


class FakeTime:
    def __init__(self):
        self.delta_time = 0.0
        self.frame_delta_time = 0.0

    def frame(self):
        pass

    def tick(self):
        pass


def _draws(updater, clock, delta, seconds):
    clock.delta_time = delta
    drawn = 0
    for _ in range(round(seconds / delta)):
        drawn += updater.update()
    return drawn


def test_slow_stretch_does_not_leave_uncapped_frames_behind():
    clock = FakeTime()
    updater = UpdateCoordinator(clock)
    updater.register(UpdatePhase.DRAW, lambda: None)
    fps = 1 / updater.update_timestep

    _draws(updater, clock, 1 / 30, 10.0)            # ten seconds below the cap
    drawn = _draws(updater, clock, 1 / 1000, 1.0)    # then the game is fast again

    assert drawn <= fps + 2
