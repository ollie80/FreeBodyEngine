"""Tests for Input's pressed/released tracking.

`released` used to be the whole of the previous poll's pressed set, so an
action read as released on every frame it was held after the first - "jump on
release" fired over and over while the key was down.
"""
from FreeBodyEngine.core.input import Input


class FakeWindow:
    def __init__(self):
        self.down = False

    def _get_key_down(self, key):
        return self.down

    def _get_gamepad_state(self, index):
        return {}


def _input():
    inp = Input(Input.parse_actions({'jump': ['SPACE']}))
    inp.window = FakeWindow()
    return inp


def _poll(inp, down):
    inp.window.down = down
    inp.update()
    return inp.get_action_pressed('jump'), inp.get_action_released('jump')


def test_released_only_on_the_poll_the_key_goes_up():
    inp = _input()
    states = [_poll(inp, down) for down in (False, True, True, True, False, False)]
    assert states == [
        (False, False),
        (True, False),
        (True, False),   # held - was reported released here
        (True, False),   # and here
        (False, True),   # actually let go
        (False, False),
    ]


def test_release_survives_until_a_frame_has_seen_it(monkeypatch):
    """Input polls every loop iteration, game code reads it only on iterations
    that draw. A release on an iteration that drew nothing has to still be
    there when the next frame's UPDATE runs."""
    inp = _input()
    drew = {'value': True}
    monkeypatch.setattr(Input, '_frame_seen_input', staticmethod(lambda: drew['value']))

    _poll(inp, True)
    _poll(inp, False)                       # released, no frame drawn yet
    drew['value'] = False
    assert _poll(inp, False) == (False, True)
    drew['value'] = True                    # a frame has now read it
    assert _poll(inp, False) == (False, False)
