from typing import TYPE_CHECKING, Union
from FreeBodyEngine import warning, get_main

from enum import Enum, auto
from dataclasses import dataclass



if TYPE_CHECKING:
    from FreeBodyEngine.core.main import Main
    from FreeBodyEngine.core.window.generic import Window

import re
from FreeBodyEngine.math import Vector
import operator


class Key(Enum):
    A = auto()
    B = auto()
    C = auto()
    D = auto()
    E = auto()
    F = auto()
    G = auto()
    H = auto()
    I = auto()
    J = auto()
    K = auto()
    L = auto()
    M = auto()
    N = auto()
    O = auto()
    P = auto()
    Q = auto()
    R = auto()
    S = auto()
    T = auto()
    U = auto()
    V = auto()
    W = auto()
    X = auto()
    Y = auto()
    Z = auto()

    ONE = auto()
    TWO = auto()
    THREE = auto()
    FOUR = auto()
    FIVE = auto()
    SIX = auto()
    SEVEN = auto()
    EIGHT = auto()
    NINE = auto()
    ZERO = auto()

    MINUS = auto()
    EQUAL = auto()
    LEFT_BRACKET = auto()
    RIGHT_BRACKET = auto()
    BACKSLASH = auto()
    SEMICOLON = auto()
    APOSTROPHE = auto()
    TILDE = auto()
    COMMA = auto()
    PERIOD = auto()
    SLASH = auto()

    SPACE = auto()
    RETURN = auto()
    ENTER = RETURN
    BACKSPACE = auto()
    TAB = auto()
    ESCAPE = auto()
    CAPS_LOCK = auto()

    L_CTRL = auto()
    R_CTRL = auto()
    L_SHIFT = auto()
    R_SHIFT = auto()
    L_ALT = auto()
    R_ALT = auto()
    L_SUPER = auto()
    R_SUPER = auto()

    INSERT = auto()
    DELETE = auto()
    HOME = auto()
    END = auto()
    PG_UP = auto()
    PG_DOWN = auto()
    UP = auto()
    DOWN = auto()
    LEFT = auto()
    RIGHT = auto()

    F1 = auto()
    F2 = auto()
    F3 = auto()
    F4 = auto()
    F5 = auto()
    F6 = auto()
    F7 = auto()
    F8 = auto()
    F9 = auto()
    F10 = auto()
    F11 = auto()
    F12 = auto()
    F13 = auto()
    F14 = auto()
    F15 = auto()
    F16 = auto()
    F17 = auto()
    F18 = auto()
    F19 = auto()
    F20 = auto()
    F21 = auto()
    F22 = auto()
    F23 = auto()
    F24 = auto()

    NUMPAD_0 = auto()
    NUMPAD_1 = auto()
    NUMPAD_2 = auto()
    NUMPAD_3 = auto()
    NUMPAD_4 = auto()
    NUMPAD_5 = auto()
    NUMPAD_6 = auto()
    NUMPAD_7 = auto()
    NUMPAD_8 = auto()
    NUMPAD_9 = auto()
    NUMPAD_DECIMAL = auto()
    NUMPAD_DIVIDE = auto()
    NUMPAD_MULTIPLY = auto()
    NUMPAD_SUBTRACT = auto()
    NUMPAD_ADD = auto()
    NUMPAD_ENTER = auto()

class GamepadButton(Enum):
    A = auto()
    B = auto()
    X = auto()
    Y = auto()

    LB = auto()
    RB = auto()

    LS_DOWN = auto() 
    RS_DOWN = auto() 

    DPAD_UP = auto()
    DPAD_RIGHT = auto()
    DPAD_DOWN = auto()
    DPAD_LEFT = auto()

    GUIDE = auto()

class GamepadAxis(Enum):
    LEFT_X = auto()
    LEFT_Y = auto()
    RIGHT_X = auto()
    RIGHT_Y = auto()

    LEFT_TRIGGER = auto()
    RIGHT_TRIGGER = auto()

CHARACTERSTRINGMAP = {
    "A": Key.A, "B": Key.B, "C": Key.C, "D": Key.D, "E": Key.E, "F": Key.F,
    "G": Key.G, "H": Key.H, "I": Key.I, "J": Key.J, "K": Key.K, "L": Key.L,
    "M": Key.M, "N": Key.N, "O": Key.O, "P": Key.P, "Q": Key.Q, "R": Key.R,
    "S": Key.S, "T": Key.T, "U": Key.U, "V": Key.V, "W": Key.W, "X": Key.X,
    "Y": Key.Y, "Z": Key.Z,

    "1": Key.ONE, "2": Key.TWO, "3": Key.THREE, "4": Key.FOUR, "5": Key.FIVE,
    "6": Key.SIX, "7": Key.SEVEN, "8": Key.EIGHT, "9": Key.NINE, "0": Key.ZERO,

    "MINUS": Key.MINUS,
    "EQUAL": Key.EQUAL,
    "LEFT_BRACKET": Key.LEFT_BRACKET,
    "RIGHT_BRACKET": Key.RIGHT_BRACKET,
    "BACKSLASH": Key.BACKSLASH,
    "SEMICOLON": Key.SEMICOLON,
    "APOSTROPHE": Key.APOSTROPHE,
    "TILDE": Key.TILDE,
    "COMMA": Key.COMMA,
    "PERIOD": Key.PERIOD,
    "SLASH": Key.SLASH,

    "SPACE": Key.SPACE,
    "RETURN": Key.RETURN,
    "ENTER": Key.RETURN,
    "BACKSPACE": Key.BACKSPACE,
    "TAB": Key.TAB,
    "ESCAPE": Key.ESCAPE,
    "CAPS_LOCK": Key.CAPS_LOCK,

    "L_CTRL": Key.L_CTRL,
    "R_CTRL": Key.R_CTRL,
    "L_SHIFT": Key.L_SHIFT,
    "R_SHIFT": Key.R_SHIFT,
    "L_ALT": Key.L_ALT,
    "R_ALT": Key.R_ALT,
    "L_SUPER": Key.L_SUPER,
    "R_SUPER": Key.R_SUPER,

    "INSERT": Key.INSERT,
    "DELETE": Key.DELETE,
    "HOME": Key.HOME,
    "END": Key.END,
    "PG_UP": Key.PG_UP,
    "PG_DOWN": Key.PG_DOWN,
    "UP": Key.UP,
    "DOWN": Key.DOWN,
    "LEFT": Key.LEFT,
    "RIGHT": Key.RIGHT,

    "F1": Key.F1, "F2": Key.F2, "F3": Key.F3, "F4": Key.F4, "F5": Key.F5,
    "F6": Key.F6, "F7": Key.F7, "F8": Key.F8, "F9": Key.F9, "F10": Key.F10,
    "F11": Key.F11, "F12": Key.F12, "F13": Key.F13, "F14": Key.F14,
    "F15": Key.F15, "F16": Key.F16, "F17": Key.F17, "F18": Key.F18,
    "F19": Key.F19, "F20": Key.F20, "F21": Key.F21, "F22": Key.F22,
    "F23": Key.F23, "F24": Key.F24,

    "NUMPAD_0": Key.NUMPAD_0,
    "NUMPAD_1": Key.NUMPAD_1,
    "NUMPAD_2": Key.NUMPAD_2,
    "NUMPAD_3": Key.NUMPAD_3,
    "NUMPAD_4": Key.NUMPAD_4,
    "NUMPAD_5": Key.NUMPAD_5,
    "NUMPAD_6": Key.NUMPAD_6,
    "NUMPAD_7": Key.NUMPAD_7,
    "NUMPAD_8": Key.NUMPAD_8,
    "NUMPAD_9": Key.NUMPAD_9,
    "NUMPAD_DECIMAL": Key.NUMPAD_DECIMAL,
    "NUMPAD_DIVIDE": Key.NUMPAD_DIVIDE,
    "NUMPAD_MULTIPLY": Key.NUMPAD_MULTIPLY,
    "NUMPAD_SUBTRACT": Key.NUMPAD_SUBTRACT,
    "NUMPAD_ADD": Key.NUMPAD_ADD,
    "NUMPAD_ENTER": Key.NUMPAD_ENTER,

    "GAMEPAD_A": GamepadButton.A,
    "GAMEPAD_B": GamepadButton.B,
    "GAMEPAD_X": GamepadButton.X,
    "GAMEPAD_Y": GamepadButton.Y,
    "GAMEPAD_LB": GamepadButton.LB,
    "GAMEPAD_RB": GamepadButton.RB,
    "GAMEPAD_LS": GamepadButton.LS_DOWN,
    "GAMEPAD_RS": GamepadButton.RS_DOWN,
    "DPAD_UP": GamepadButton.DPAD_UP,
    "DPAD_RIGHT": GamepadButton.DPAD_RIGHT,
    "DPAD_DOWN": GamepadButton.DPAD_DOWN,
    "GUIDE": GamepadButton.GUIDE,

    "AXIS_LEFT_X": GamepadAxis.LEFT_X,
    "AXIS_LEFT_Y": GamepadAxis.LEFT_Y,
    "AXIS_RIGHT_X": GamepadAxis.RIGHT_X,
    "AXIS_RIGHT_Y": GamepadAxis.RIGHT_Y,
    "AXIS_LEFT_TRIGGER": GamepadAxis.LEFT_TRIGGER,
    "AXIS_RIGHT_TRIGGER": GamepadAxis.RIGHT_TRIGGER,
}

class Gamepad:
    def __init__(self, id: int, window: 'Window'):
        self.id = id
        self.window = window

    def get_state(self):
        return self.window.get_gamepad_state(self.id)


comparison_ops = {
    '>': operator.gt,
    '<': operator.lt,
    '>=': operator.ge,
    '<=': operator.le,
    '==': operator.eq,
    '!=': operator.ne,
}

@dataclass
class ActionCheck:
    check_type: str 
    val: str

class Action:
    def __init__(self, input: Union[Key, GamepadAxis, GamepadButton], check: ActionCheck = None):
        self.input = input
        self.check = check

    def check_val(self, val: float) -> bool:
        if self.check == None:
            if val > 0.0:
                return True
            else:
                return False
        else:
            comparison_ops[self.check.check_type](val, self.check.val)
        
class Input:
    def __init__(self, main: 'Main', actions: dict[str, list[Action]], window: 'Window'):
        self.actions = actions
        self.pressed = {}
        self.pressed_set = set(self.pressed.keys())
        self.released = set()
        self.window = window

        self.gamepads = {}

    def set_actions(self, actions: dict[str, list[Action]]):
        self.actions = actions
        print(actions)


    def bind_action(self, name: str, inputs: list[Key]):
        pass

    def reset(self):
        self.pressed = {}
        self.released = set()

    def action_exists(self, name) -> bool:
        return name in self.actions.keys()

    def get_action_pressed(self, name) -> bool:
        if self.action_exists(name):
            return name in self.pressed_set
        else:
            warning(f'Action with name "{name}" does not exist.')

    def get_action_strength(self, name):
        if self.action_exists(name):
            return self.pressed[name]
        else:
            warning(f'Action with name "{name}" does not exist.')

    def get_action_released(self, name) -> bool:
        if self.action_exists(name):
            return name in self.released
        else:
            warning(f'Action with name "{name}" does not exist.')

    def get_vector(self, neg_x: str, pos_x: str, neg_y: str, pos_y: str):
        """Get a vector from the strengths of 4 actions."""
        x = self.get_action_strength(pos_x) - self.get_action_strength(neg_x)
        y = self.get_action_strength(pos_y) - self.get_action_strength(neg_y)

        return Vector(x, y)

    def _pressed_callback(self, name):
        pass

    def _released_callback(self, name):
        pass

    def update(self):
        input_vals = {}
        for name in self.actions:
            highest = 0.0
            pressed = False
            for action in self.actions[name]:
                if action.input not in input_vals:
                    input_vals[action.input] = self.window._get_key_down(action.input)
                if input_vals[action.input] > highest:
                    highest = input_vals[action.input]
                if pressed == False:
                    pressed = action.check_val(input_vals[action.input])
            self.pressed[name] = highest
            if pressed:
                self.pressed_set.add(name)

    @classmethod
    def parse_actions(self, source: dict[str, list[str]]):
        actions = {}
        for action in source:
            inputs = []
            for input in source[action]:
                match = re.match(r"^([A-Z0-9_]+)\s*([<>=!]+)?\s*([-\d\.]+)?$", input.strip())
                if not match:
                    raise ValueError(f"Invalid input string format: {input}")
                
                input_name = match.group(1)
                check_type = match.group(2) or ""
                val = match.group(3) or ""
                if check_type == "" or val == "":
                    check = None
                else:
                    check = ActionCheck(check_type, val)

                inputs.append(Action(CHARACTERSTRINGMAP[input_name], check))
            
            actions[action] = inputs
        return actions
    
def get_action_pressed(name: str) -> bool:
    return get_main().input.get_action_pressed(name)

def get_action_strength(name: str) -> float:
    return get_main().input.get_action_strength(name)

def get_action_released(name: str) -> bool:
    return get_main().input.get_action_released(name)

def get_vector(neg_x: str, pos_x: str, neg_y: str, pos_y: str) -> Vector:
    """Get a vector from the strengths of four actions."""
    return get_main().input.get_vector(neg_x, pos_x, neg_y, pos_y)