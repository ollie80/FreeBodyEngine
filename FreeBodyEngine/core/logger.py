from datetime import datetime
from functools import wraps
from FreeBodyEngine.core.service import Service
from FreeBodyEngine import get_main, get_service, get_flag
import os
import inspect
import json
import traceback

colors = {
    "black": 30, "red": 31, "green": 32, "yellow": 33, "blue": 34,
    "magenta": 35, "cyan": 36, "white": 37, "reset": 0
}

def get_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

def print_colored(*text: str, color='reset'):
    s = "".join(f"\033[{colors[color]}m{t}\033[0m" for t in text)
    print(s)

class Logger(Service):
    def __init__(self, max_history_length=250):
        super().__init__('logger')
        self.history: list[dict] = []
        self.max_history_length = max_history_length
        self.next_id = 1
        self.dependencies.append('files')
        self.supress = {
            "ERROR": get_flag('SUPRESS_ERRORS', False),
            "WARNING": get_flag('SUPRESS_WARNINGS', False),
            "DEBUG": get_flag('SUPRESS_LOGS', False)
        }

    def _clear_log(self):
        path = get_service('files').get_save_location()
        os.makedirs(path, exist_ok=True)
        open(os.path.join(path, "log.jsonl"), 'w')

    def _write_json_log(self, log_entry: dict):
        path = get_service('files').get_save_location()

        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, "log.jsonl"), 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    def _store_log(self, type_: str, msg: str):
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
        if not self.supress["DEBUG"]:
            full_msg = " ".join(str(m) for m in msg)
            log_id = self._store_log("DEBUG", full_msg)
            print_colored(*msg, color=color)
            return log_id

    def error(self, msg):
        if not self.supress["ERROR"]:
            log_id = self._store_log("ERROR", msg)
            print_colored(f"ERROR [{log_id}]: {msg}", color="red")
            return log_id

    def warning(self, msg):
        if not self.supress["WARNING"]:
            log_id = self._store_log("WARNING", msg)
            print_colored(f"WARNING [{log_id}]: {msg}", color="yellow")
            return log_id

    def get_traceback(self, log_id: int):
        entry = next((e for e in self.history if e["id"] == log_id), None)
        if entry:
            return "".join(entry["traceback"] or [])
        return f"No log found for ID {log_id}"

    def get_history(self):
        return "\n".join(f"[{e['timestamp']}] {e['type']} [{e['id']}]: {e['message']}" for e in self.history)
