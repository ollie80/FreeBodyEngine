from datetime import datetime
from functools import wraps

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

class Logger:
    """
    The logger class replaces print statements and pytohn errors to work with the rest of FBE.

    :param max_history_length: The maximum length of log history that is stored in memory before being written to disk.
    :type max_history_length: int
    """
    def __init__(self, max_history_length = 250):
        self.history: list[tuple[str, str, str]] = []  # (timestamp, type, msg)
        self.max_history_length = max_history_length

    def store_log(type_: str):
        def decorator(func):
            @wraps(func)
            def wrapper(self, msg, *args, **kwargs):
                timestamp = get_timestamp()
                self.history.append((timestamp, type_, msg))
                return func(self, msg, *args, **kwargs)
            return wrapper
        return decorator
    
    @store_log('DEBUG')
    def log(self, *msg, color: str = "reset"):
        print_colored(*msg, color=color)

    @store_log("ERROR")
    def error(self, msg):
        print_colored(f"ERROR: {msg}", color="red")

    @store_log('WARNING')
    def warning(self, msg):
        print_colored(f"WARNING: {msg}", color="yellow")

    def get_history(self) -> str:
        return '\n'.join(f"[{ts}] {type_}: {msg}" for ts, type_, msg in self.history)

    def update(self):
        if len(self.history) > self.max_history_length:
            # write log data to disk
            
            self.history.clear()