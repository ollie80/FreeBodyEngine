from datetime import datetime
from functools import wraps
from FreeBodyEngine.core.service import Service
from FreeBodyEngine import get_main, SUPRESS_LOGS, SUPRESS_ERRORS, SUPRESS_WARNINGS, TERMINAL_WINDOW, get_service, get_flag
from FreeBodyEngine.core.files import FileResource 
import os
import inspect
import json
import traceback

colors = {
    "black": 30, "red": 31, "green": 32, "yellow": 33, "blue": 34,
    "magenta": 35, "cyan": 36, "white": 37, "reset": 0
}

def get_timestamp() -> str:
    """Returns the current local time as "YYYY-MM-DD HH:MM:SS.mmm"."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

def print_colored(*text: str, color='reset'):
    """Prints `text` (concatenated with no separator) wrapped in the ANSI
    escape code for `color` (see `colors`)."""
    s = "".join(f"\033[{colors[color]}m{t}\033[0m" for t in text)
    print(s)

class Logger(Service):
    """The engine's central logging service (registered as "logger").
    Keeps an in-memory history of every log/warning/error (capped at
    `max_history_length`, oldest dropped first) and, once the "files"
    service is available, also mirrors each entry as a line of
    `user://log.jsonl`."""

    def __init__(self, max_history_length=10000):
        """Sets up an empty log history, and reads the SUPRESS_ERRORS/
        SUPRESS_WARNINGS/SUPRESS_LOGS flags to decide which message types
        are silenced."""
        super().__init__('logger')
        self.history: list[dict] = []
        self.max_history_length = max_history_length
        self.next_id = 1
        self.supress = {
            "ERROR": get_flag(SUPRESS_ERRORS, False),
            "WARNING": get_flag(SUPRESS_WARNINGS, False),
            "DEBUG": get_flag(SUPRESS_LOGS, False)
        }
        self.log_file = None


    def _write_json_log(self, log_entry: dict):
        self.log_file.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    def _store_log(self, type_: str, msg: str):
        if get_service('files') != None:
            if self.log_file == None:
                self.log_file: FileResource = get_service('files').get_file('user://log.jsonl')
                self.log_file.clear()

            tb = None

            if type_ in ("ERROR", "WARNING"):
                tb = traceback.format_stack()[:-2]

            log_entry = {
                "id": self.next_id,
                "timestamp": get_timestamp(),
                "type": type_,
                "message": msg,
                "traceback": tb
            }

            self.history.append(log_entry)
            self._write_json_log(log_entry)

            if len(self.history) > self.max_history_length:
                self.history.pop(0)

            
            self.next_id += 1
            return log_entry["id"]

    def log(self, *msg, color: str = "reset"):
        """Logs `msg` (joined with spaces) to the console in `color`, unless
        DEBUG logs are suppressed. Returns the new entry's log id."""
        if not self.supress["DEBUG"]:
            full_msg = " ".join(str(m) for m in msg)
            log_id = self._store_log("DEBUG", full_msg)
            self._print(*msg, color=color)
            return log_id

    def error(self, msg):
        """Logs `msg` as an ERROR (printed in red) and records a stack
        trace for it, unless errors are suppressed. Returns the new entry's
        log id."""
        if not self.supress["ERROR"]:
            log_id = self._store_log("ERROR", msg)
            self._print(f"ERROR [{log_id}]: {msg}", color="red")
            return log_id

    def warning(self, msg):
        """Logs `msg` as a WARNING (printed in yellow) and records a stack
        trace for it, unless warnings are suppressed. Returns the new
        entry's log id."""
        if not self.supress["WARNING"]:
            log_id = self._store_log("WARNING", msg)
            self._print(f"WARNING [{log_id}]: {msg}", color="yellow")
            return log_id

    def _print(self, *msg, color: str):
        """Prints to the console like `print_colored()`, except under
        fb.TERMINAL_WINDOW - there, stdout IS the rendered display (see
        core/window/terminal.py's TerminalWindow.draw()), so an ordinary
        print would land in the middle of its cursor-positioned ANSI
        output and corrupt the frame. Every message is still recorded via
        _store_log() regardless (in-memory history + user://log.jsonl),
        just not echoed to the console live."""
        if get_flag(TERMINAL_WINDOW, False):
            return
        print_colored(*msg, color=color)

    def get_traceback(self, log_id: int):
        """Returns the recorded stack trace for the ERROR/WARNING entry with
        id `log_id`, or a "No log found" message if no entry has that id."""
        entry = next((e for e in self.history if e["id"] == log_id), None)
        if entry:
            return "".join(entry["traceback"] or [])
        return f"No log found for ID {log_id}"

    def get_history(self):
        """Returns the whole in-memory log history, formatted one line per entry."""
        return "\n".join(f"[{e['timestamp']}] {e['type']} [{e['id']}]: {e['message']}" for e in self.history)