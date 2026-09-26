"""Log persistence for the external profiler - every snapshot received
from a target app's ProfilerServer is appended as one JSON line to a
timestamped file, so a session can be reviewed later (or fed to some
other tool - it's just JSONL) instead of only ever existing on screen
for as long as the window's open."""
import json
import os
import time

# ~/.local/share/freebody/profiler_logs on Linux (and the platform-
# appropriate equivalent elsewhere, via os.path.expanduser) - alongside
# where this engine's other real user-level state already lives (see
# reference to phonon's own ~/.local/share/phonon/ cache), not dumped
# into the current working directory.
LOG_DIR = os.path.join(os.path.expanduser("~"), ".local", "share", "freebody", "profiler_logs")


class ProfilerLog:
    """One session's worth of received snapshots, appended to disk as
    they arrive (not buffered in memory and written once at the end - a
    profiler session that's still running when something goes wrong
    shouldn't lose everything logged before that point)."""

    def __init__(self, log_dir: str = LOG_DIR):
        os.makedirs(log_dir, exist_ok=True)
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        self.path = os.path.join(log_dir, f"profile-{timestamp}.jsonl")
        self._file = open(self.path, "a", encoding="utf-8")

    def write(self, snapshot: dict):
        self._file.write(json.dumps(snapshot) + "\n")
        self._file.flush()

    def close(self):
        try:
            self._file.close()
        except OSError:
            pass
