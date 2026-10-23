"""Tests for EventManager.

emit() iterated the live callback set, so a callback that unregistered itself
- the usual shape of a one-shot listener - raised "Set changed size during
iteration". unregister_event() read an attribute Event never had and raised
AttributeError for every event that existed.
"""
from FreeBodyEngine.core.event import EventManager


def test_callback_can_unregister_itself_during_emit():
    events = EventManager()
    events.register_event('hit')
    calls = []

    def once():
        calls.append('once')
        events.unregister_callback('hit', once)

    def always():
        calls.append('always')

    events.register_callback('hit', once)
    events.register_callback('hit', always)

    events.emit('hit')
    events.emit('hit')
    assert sorted(calls) == ['always', 'always', 'once']


def test_callback_can_register_another_during_emit():
    events = EventManager()
    events.register_event('hit')
    calls = []

    def late():
        calls.append('late')

    def first():
        calls.append('first')
        events.register_callback('hit', late)

    events.register_callback('hit', first)
    events.emit('hit')
    assert calls == ['first']          # added mid-emit: runs from the next one
    events.emit('hit')
    assert sorted(calls) == ['first', 'first', 'late']


def test_callback_removed_earlier_in_the_same_emit_is_not_called():
    events = EventManager()
    events.register_event('hit')
    calls = []

    def a():
        calls.append('a')
        events.unregister_callback('hit', b)

    def b():
        calls.append('b')
        events.unregister_callback('hit', a)

    events.register_callback('hit', a)
    events.register_callback('hit', b)
    events.emit('hit')
    assert len(calls) == 1


def test_unregister_event():
    events = EventManager()
    events.register_category('input')
    events.register_event('key', 'input')
    events.unregister_event('key')
    assert 'key' not in events.events
    assert events.category_map['input'] == []
