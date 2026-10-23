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


def test_just_pressed_only_on_the_first_frame():
    inp = _input()
    seen = []
    for down in (False, True, True, False, True):
        inp.window.down = down
        inp.update()
        seen.append(inp.get_action_just_pressed('jump'))
    assert seen == [False, True, False, False, True]


def test_axis_and_vector():
    inp = Input(Input.parse_actions({'left': ['A'], 'right': ['D'], 'up': ['W'], 'down': ['S']}))

    class Keys(FakeWindow):
        held = set()

        def _get_key_down(self, key):
            return key in self.held

    from FreeBodyEngine.core.input import CHARACTERSTRINGMAP
    inp.window = Keys()
    inp.window.held = {CHARACTERSTRINGMAP['D'], CHARACTERSTRINGMAP['W']}
    inp.update()
    assert inp.get_axis('left', 'right') == 1.0
    assert tuple(inp.get_vector('left', 'right', 'down', 'up')) == (1.0, 1.0)


def test_unknown_action_is_false_and_warns_once_with_a_suggestion(capsys):
    """It returned None and warned every call, so a typo surfaced as a
    TypeError in get_vector() or a condition that was never true."""
    inp = _input()
    inp.update()
    assert inp.get_action_pressed('jupm') is False
    assert inp.get_action_strength('jupm') == 0.0
    out = capsys.readouterr().out
    assert out.count('does not exist') == 1
    assert 'Did you mean "jump"' in out


def test_default_actions_when_none_are_given():
    inp = Input()
    assert {'left', 'right', 'up', 'down', 'accept', 'cancel'} <= set(inp.actions)
    assert Input({'fire': []}).actions.keys() == {'fire'}


def test_bind_action_adds_bindings():
    """It was an empty stub."""
    inp = _input()
    inp.bind_action('jump', ['W'])
    inp.bind_action('dash', ['L_SHIFT'])
    assert len(inp.actions['jump']) == 2
    assert 'dash' in inp.actions
