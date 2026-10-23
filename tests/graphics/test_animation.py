"""Tests for AnimationPlayer.

A frame with a duration of 0 took nothing off the elapsed time while the loop
test used a small floor, so a looping animation of 0-duration frames never left
update() and hung the game.
"""
import threading

from FreeBodyEngine.graphics.animation import Animation, AnimationFrame, AnimationPlayer, AnimationSet


def _player(durations, loop=True):
    frames = [AnimationFrame(texture=None, duration=d) for d in durations]
    return AnimationPlayer(AnimationSet({'run': Animation('run', frames, loop)}))


def test_zero_duration_frames_do_not_hang():
    player = _player([0.0, 0.0])
    worker = threading.Thread(target=player.update, args=(0.1,), daemon=True)
    worker.start()
    worker.join(timeout=2.0)
    assert not worker.is_alive(), "update() never returned"


def test_frames_still_advance_by_their_durations():
    player = _player([0.1, 0.2, 0.3])
    player.update(0.15)
    assert player.frame_index == 1
    player.update(0.2)
    assert player.frame_index == 2
    player.update(0.3)
    assert player.frame_index == 0
