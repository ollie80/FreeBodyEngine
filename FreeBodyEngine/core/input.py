from typing import TYPE_CHECKING, Union
from FreeBodyEngine.core.update import UpdatePhase
from FreeBodyEngine import (
    warning,
    get_main,
    get_service,
    register_service_update,
    unregister_service_update,
    register_event,
    unregister_event,
    emit_event,
)

from enum import Enum, auto
from dataclasses import dataclass

KEY_PRESS = "ENGINE_key_press"
KEY_REPEAT = "ENGINE_key_repeat" 
KEY_RELEASE = "ENGINE_key_release"

if TYPE_CHECKING:
    from FreeBodyEngine.core.main import Main
    from FreeBodyEngine.core.window.generic import Window

import re
from FreeBodyEngine.math import Vector
import operator
from FreeBodyEngine.core.service import Service


class Key(Enum):
    """Engine-level keyboard key identifiers, independent of any windowing backend - each backend (GLFW/X11/Wayland) translates its own native key codes to/from these values."""
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
    """Engine-level gamepad button identifiers, independent of any windowing backend's native gamepad mapping."""
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
    """Engine-level gamepad analog axis identifiers (sticks and triggers), independent of any windowing backend's native gamepad mapping."""
    LEFT_X = auto()
    LEFT_Y = auto()
    RIGHT_X = auto()
    RIGHT_Y = auto()

    LEFT_TRIGGER = auto()
    RIGHT_TRIGGER = auto()


CHARACTERSTRINGMAP = {
    "A": Key.A,
    "B": Key.B,
    "C": Key.C,
    "D": Key.D,
    "E": Key.E,
    "F": Key.F,
    "G": Key.G,
    "H": Key.H,
    "I": Key.I,
    "J": Key.J,
    "K": Key.K,
    "L": Key.L,
    "M": Key.M,
    "N": Key.N,
    "O": Key.O,
    "P": Key.P,
    "Q": Key.Q,
    "R": Key.R,
    "S": Key.S,
    "T": Key.T,
    "U": Key.U,
    "V": Key.V,
    "W": Key.W,
    "X": Key.X,
    "Y": Key.Y,
    "Z": Key.Z,
    "1": Key.ONE,
    "2": Key.TWO,
    "3": Key.THREE,
    "4": Key.FOUR,
    "5": Key.FIVE,
    "6": Key.SIX,
    "7": Key.SEVEN,
    "8": Key.EIGHT,
    "9": Key.NINE,
    "0": Key.ZERO,
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
    "F1": Key.F1,
    "F2": Key.F2,
    "F3": Key.F3,
    "F4": Key.F4,
    "F5": Key.F5,
    "F6": Key.F6,
    "F7": Key.F7,
    "F8": Key.F8,
    "F9": Key.F9,
    "F10": Key.F10,
    "F11": Key.F11,
    "F12": Key.F12,
    "F13": Key.F13,
    "F14": Key.F14,
    "F15": Key.F15,
    "F16": Key.F16,
    "F17": Key.F17,
    "F18": Key.F18,
    "F19": Key.F19,
    "F20": Key.F20,
    "F21": Key.F21,
    "F22": Key.F22,
    "F23": Key.F23,
    "F24": Key.F24,
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
    "DPAD_LEFT": GamepadButton.DPAD_LEFT,
    "GUIDE": GamepadButton.GUIDE,
    "AXIS_LEFT_X": GamepadAxis.LEFT_X,
    "AXIS_LEFT_Y": GamepadAxis.LEFT_Y,
    "AXIS_RIGHT_X": GamepadAxis.RIGHT_X,
    "AXIS_RIGHT_Y": GamepadAxis.RIGHT_Y,
    "AXIS_LEFT_TRIGGER": GamepadAxis.LEFT_TRIGGER,
    "AXIS_RIGHT_TRIGGER": GamepadAxis.RIGHT_TRIGGER,
}


class KeyCallbackType(Enum):
    """Distinguishes the kind of key event being dispatched through Input._key_callback()."""
    PRESS = auto()
    RELEASE = auto()
    REPEAT = auto()


class Gamepad:
    """Represents a single connected gamepad, identified by its backend-assigned `id`."""
    def __init__(self, id: int, window: "Window"):
        """Stores the gamepad's id and the window backend used to query its state."""
        self.id = id
        self.window = window

    def get_state(self):
        """Returns this gamepad's current button/axis state, as reported by the window backend."""
        return self.window._get_gamepad_state(self.id)


comparison_ops = {
    ">": operator.gt,
    "<": operator.lt,
    ">=": operator.ge,
    "<=": operator.le,
    "==": operator.eq,
    "!=": operator.ne,
}


@dataclass
class ActionCheck:
    """A comparison (`check_type`, e.g. ">") and threshold value (`val`) applied to a raw input's strength, letting an analog input (a gamepad axis/trigger) drive a digital or differently-thresholded action."""
    check_type: str
    val: str


class Action:
    """A single physical input (key/button/axis) bound to an action, with an optional threshold check - an action fires if any one of its bound Actions passes its check."""
    def __init__(
        self, input: Union[Key, GamepadAxis, GamepadButton], check: ActionCheck = None
    ):
        """Binds `input` to this action, optionally gated by `check` (no check means "pressed" is just `value > 0`)."""
        self.input = input
        self.check = check

    def check_val(self, val: float) -> bool:
        """Tests a raw input value against this binding's check, defaulting to "greater than zero" (a digital press) if no check was given."""
        if self.check == None:
            return val > 0.0
        else:
            return comparison_ops[self.check.check_type](val, float(self.check.val))

    def __str__(self):
        return f"ACTION {self.input}" if self.check == None else f"ACTION {self.input} {self.check.check_type} {self.check.val}"

class Input(Service):
    """Central input service - polls the window backend every frame and turns raw key/gamepad state into named, engine-defined actions (each action can be bound to several physical inputs via `actions`)."""
    def __init__(self, actions: dict[str, list[Action]] = {}):
        """Stores the action bindings and sets up empty pressed/released tracking state."""
        super().__init__("input")
        self.dependencies.append("window")

        self.actions = actions
        self.pressed = {}
        self.pressed_set = set(self.pressed.keys())
        self.released = set()

        self.gamepads = {}

    def on_initialize(self):
        """Registers update() to run every frame's EARLY phase, grabs the 'window' service ('window' is a declared dependency, so it's guaranteed to already be registered), and registers the KEY_PRESS/KEY_RELEASE/KEY_REPEAT events _key_callback() emits - previously never registered anywhere, so anything subscribing to them with register_event_callback() (rather than just emitting/ignoring them, which emit_event() tolerates on an unregistered event) hit a raw KeyError. Input owns these constants, so it registers them, the same way Window.on_initialize() registers WINDOW_RESIZE/FRAMEBUFFER_RESIZE."""
        register_service_update(UpdatePhase.EARLY, self.update)
        self.window = get_service("window")
        register_event(KEY_PRESS)
        register_event(KEY_RELEASE)
        register_event(KEY_REPEAT)

    def on_destroy(self):
        """Unregisters update() from the EARLY update phase and the key events registered in on_initialize()."""
        unregister_service_update(UpdatePhase.EARLY, self.update)
        unregister_event(KEY_PRESS)
        unregister_event(KEY_RELEASE)
        unregister_event(KEY_REPEAT)

    def set_actions(self, actions: dict[str, list[Action]]):
        """Replaces the entire action-bindings dict."""
        self.actions = actions

    def bind_action(self, name: str, inputs: list[Key]):
        """Intended to add extra input bindings to an existing action at runtime - not yet implemented."""
        pass

    def reset(self):
        """Called at the start of each poll: carries this frame's still-pressed actions into `released` (so a released action reads True for exactly one frame), then clears `pressed`/`pressed_set` for update() to repopulate."""
        self.released = self.pressed_set.copy()
        self.pressed = {}
        self.pressed_set = set()

    def action_exists(self, name) -> bool:
        """Checks whether `name` is a registered action."""
        return name in self.actions.keys()

    def get_action_pressed(self, name) -> bool:
        """Returns whether `name` is currently pressed (held down this frame); warns and returns None if `name` isn't a registered action."""
        if self.action_exists(name):
            return name in self.pressed_set
        else:
            warning(f'Action with name "{name}" does not exist.')

    def get_action_strength(self, name):
        """Returns `name`'s current analog strength (the highest check-passing value among its bound inputs this frame); warns and returns None if `name` isn't a registered action."""
        if self.action_exists(name):
            return self.pressed[name]
        else:
            warning(f'Action with name "{name}" does not exist.')

    def get_action_released(self, name) -> bool:
        """Returns whether `name` was released this frame (it was pressed as of the last poll, but isn't anymore); warns and returns None if `name` isn't a registered action."""
        if self.action_exists(name):
            return name in self.released
        else:
            warning(f'Action with name "{name}" does not exist.')

    def get_vector(self, neg_x: str, pos_x: str, neg_y: str, pos_y: str):
        """Get a vector from the strengths of 4 actions."""
        x = self.get_action_strength(pos_x) - self.get_action_strength(neg_x)
        y = self.get_action_strength(pos_y) - self.get_action_strength(neg_y)
        
        return Vector(x, y)

    def _key_callback(self, key: Key, type: KeyCallbackType):
        if type == KeyCallbackType.PRESS:
            emit_event(KEY_PRESS, key)
        elif type == KeyCallbackType.RELEASE:
            emit_event(KEY_RELEASE, key)
        elif type == KeyCallbackType.REPEAT:
            emit_event(KEY_REPEAT, key)

    def update(self):
        """Polls the window backend's key and gamepad state and recomputes every registered action's pressed/strength state for this frame.

        Each distinct physical input is only read from the backend once per
        frame (cached in `input_vals`), even if several actions share it, so
        a key/axis bound to multiple actions doesn't get polled redundantly.
        """
        self.reset()
        input_vals = {}

        gamepad_state = self.window._get_gamepad_state(0)

        for name in self.actions:
            highest = 0.0
            pressed = False

            for action in self.actions[name]:
                if action.input not in input_vals:
                    if isinstance(action.input, Key):
                        input_vals[action.input] = self.window._get_key_down(action.input)
                    else:
                        input_vals[action.input] = gamepad_state[action.input]

                val = input_vals[action.input]

                if action.check_val(val):
                    pressed = True

                    if action.check == None:
                        strength = val
                    else:
                        if action.check.check_type in ("<", "<="):
                            strength = -val
                        else:
                            strength = val

                    if strength > highest:
                        highest = strength

            self.pressed[name] = highest
            if pressed:
                self.pressed_set.add(name)

    @classmethod
    def parse_actions(self, source: dict[str, list[str]]):
        """Parses an `actions.toml`-style config (`{action_name: ["INPUT_NAME", "INPUT_NAME OP VAL", ...]}`) into the `dict[str, list[Action]]` form `Input` uses at runtime.

        Each input string is an input name (a key from CHARACTERSTRINGMAP)
        optionally followed by a comparison operator and threshold value,
        e.g. `"AXIS_LEFT_X > 0.5"` for a thresholded gamepad axis, or
        `"SPACE"` alone for a plain digital press.

        Raises:
            ValueError: If an input string doesn't match the expected format.
        """
        actions = {}
        for action in source:
            inputs = []
            for input in source[action]:
                match = re.match(
                    r"^([A-Z0-9_]+)\s*([<>=!]+)?\s*([-\d\.]+)?$", input.strip())
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
    """Returns whether the action `name` is currently pressed."""
    return get_service("input").get_action_pressed(name)


def get_action_strength(name: str) -> float:
    """Returns the action `name`'s current analog strength."""
    return get_service("input").get_action_strength(name)


def get_action_released(name: str) -> bool:
    """Returns whether the action `name` was released this frame."""
    return get_service("input").get_action_released(name)


def get_action_vector(neg_x: str, pos_x: str, neg_y: str, pos_y: str) -> Vector:
    """Get a vector from the strengths of four actions."""
    return get_service("input").get_vector(neg_x, pos_x, neg_y, pos_y)
