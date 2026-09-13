import dataclasses
from typing import Optional

class StateMachine:
    """Runs a set of named `State`s, one active at a time - see `State` for
    how a state's function signals a transition to another state."""

    def __init__(self, states: dict[str, "State"]):
        """`states` maps state name -> `State`. Starts with no current
        state set (`current_state` is `''`, which won't match any entry in
        `states` until `set_state()` is called)."""
        self.states = states
        self.current_state = ''

    def run(self):
        """Calls the current state's `func`, if there is a current state
        and it defines one. Returns whatever `func` returns - per `State`'s
        contract, either the next state's name or nothing."""
        if self.current_state in self.states.keys():
            state = self.states[self.current_state]

            if state.func != None:

                return state.func()

    def exit(self):
        """Calls the current state's `exit` hook, if there is a current
        state and it defines one."""
        if self.current_state in self.states.keys():
            state = self.states[self.current_state]
            if state.exit != None:
                return state.exit()

    def enter(self):
        """Calls the current state's `enter` hook, if there is a current
        state and it defines one."""
        if self.current_state in self.states.keys():
            state = self.states[self.current_state]
            if state.enter != None:
                return state.enter()

    def set_state(self, state: str):
        """Transitions to `state`: exits the current state, switches
        `current_state`, then enters the new one."""
        self.exit()
        self.current_state = state
        self.enter()

    def update(self, dt):
        """Runs the current state's `func` and, if it returned a state
        name, transitions to that state.

        Note: `dt` is accepted but unused - the state machine itself isn't
        time-based, it only relays a state function's own return value into
        a transition."""
        val = self.run()
        if val != None:
            self.set_state(val)

@dataclasses.dataclass
class State:
    '''A Generic State, the state's function must return the name of the next state, otherwise it must not return anything.'''
    enter: Optional[callable] = None
    func: Optional[callable] = None
    exit: Optional[callable] = None

