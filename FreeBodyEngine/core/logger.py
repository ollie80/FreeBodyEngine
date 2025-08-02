from datetime import datetime
from functools import wraps
from FreeBodyEngine.core.service import Service
from FreeBodyEngine import get_main, get_service, get_flag
import os
import inspect


colors = {
    "black": 30, "red": 31, "green": 32, "yellow": 33, "blue": 34, "magenta": 35, "cyan": 36, "white": 37, "reset": 0
}

def get_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

def print_colored(*text: str, color='reset'):
    s = ""
    for t in text:
        s += f"\033[{colors[color]}m" + str(t) + "\033[0m" 
    print(s)

class Logger(Service):
    """
    The logger class replaces print statements and python errors to work with the rest of FBE.

    :param max_history_length: The maximum length of log history that is stored in memory before being written to disk.
    :type max_history_length: int
    """
    def __init__(self, max_history_length = 250):
        super().__init__('logger')
        self.history: list[tuple[str, str, str]] = []  # (timestamp, type, msg)
        self.max_history_length = max_history_length
        self.dependencies.append('files')
        self.supress = {"ERROR": get_flag('SUPRESS_ERRORS', False), "WARNING": get_flag('SUPRESS_WARNINGS', False), "DEBUG": get_flag('SUPRESS_LOGS', False)}

    def store_log(type_: str):
        def decorator(func):
            @wraps(func)
            def wrapper(self, msg, *args, **kwargs):
                timestamp = get_timestamp()
                path = get_service('files').get_save_location()
                os.makedirs(path, exist_ok=True)
                with open(os.path.join(path, "log.txt"), 'a') as f:
                    f.write(f"[{timestamp}][{type_}] {msg}\n")

                return func(self, msg, *args, **kwargs)
            return wrapper
        return decorator
    
    @store_log('DEBUG')
    def log(self, *msg, color: str = "reset"):
        if not self.supress["DEBUG"]:

            print_colored(*msg, color=color)

    @store_log("ERROR")
    def error(self, msg):
        if not self.supress["ERROR"]:
            print_colored(f"ERROR: {msg}", color="red")

    @store_log('WARNING')
    def warning(self, msg):
        if not self.supress["WARNING"]:
            print_colored(f'WARNING: {msg}', color="yellow")
        

    def get_history(self) -> str:
        return '\n'.join(f"[{ts}] {type_}: {msg}" for ts, type_, msg in self.history)
