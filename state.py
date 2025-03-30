import dataclasses
from typing import Optional

class StateMachine:
    def __init__(self, states: dict[str, "State"]):
        self.states = states
        self.current_state = ''

    def run(self):
        if self.current_state in self.states.keys():
            state = self.states[self.current_state]

            if state.func != None:
                
                return state.func()
        
    def exit(self):
        if self.current_state in self.states.keys():
            state = self.states[self.current_state]
            if state.exit != None:
                return state.exit()

    def enter(self):
        if self.current_state in self.states.keys():
            state = self.states[self.current_state]
            if state.enter != None:
                return state.enter()

    def set_state(self, state: str):
        self.exit()
        self.current_state = state
        self.enter()
        
    def update(self, dt):
        val = self.run()
        if val != None:
            self.set_state(val)

@dataclasses.dataclass
class State:
    '''A Generic State, the state's function must return the name of the next state, otherwise it must not return anything.'''
    enter: Optional[callable] = None
    func: Optional[callable] = None
    exit: Optional[callable] = None

