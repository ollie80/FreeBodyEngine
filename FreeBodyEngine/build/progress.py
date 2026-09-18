"""A minimal, dependency-free single-line terminal progress indicator for
the build pipeline. Two modes: determinate (a real 0..100% bar, for stages
where the total unit of work is known, e.g. bundling N asset files) and
indeterminate (an animated spinner, for stages like `pip install`/
PyInstaller where no real completion fraction is ever knowable). Only one
line is ever live on screen - each stage overwrites the previous one with
a carriage return rather than scrolling the terminal.
"""
import shutil
import sys
import threading
import time


class ProgressBar:
    """A single live status line for the build pipeline - see module docstring."""

    SPINNER_FRAMES = "|/-\\"
    BAR_WIDTH = 30
    SPIN_INTERVAL = 0.1

    def __init__(self, enabled: bool | None = None):
        """`enabled` defaults to whether stdout is a real terminal
        (`isatty()`) - disabled automatically when output is redirected to a
        file or pipe, where carriage-return-driven line overwriting would
        just produce garbled output."""
        self.enabled = sys.stdout.isatty() if enabled is None else enabled
        self._label = ""
        self._total: int | None = None
        self._current = 0
        self._frame = 0
        self._spin_thread: threading.Thread | None = None
        self._spin_stop = threading.Event()
        self._lock = threading.Lock()

    def _width(self) -> int:
        return shutil.get_terminal_size((80, 20)).columns - 1

    def _render(self):
        if not self.enabled:
            return
        with self._lock:
            if self._total:
                frac = min(1.0, self._current / self._total)
                filled = int(self.BAR_WIDTH * frac)
                bar = "#" * filled + "-" * (self.BAR_WIDTH - filled)
                line = f"\r[{bar}] {frac * 100:5.1f}%  {self._label}"
            else:
                spinner = self.SPINNER_FRAMES[self._frame % len(self.SPINNER_FRAMES)]
                line = f"\r{spinner}  {self._label}"
            sys.stdout.write(line.ljust(self._width()))
            sys.stdout.flush()

    def _spin(self):
        while not self._spin_stop.wait(self.SPIN_INTERVAL):
            self._frame += 1
            self._render()

    def _stop_spinner(self):
        if self._spin_thread is not None:
            self._spin_stop.set()
            self._spin_thread.join()
            self._spin_thread = None

    def stage(self, label: str, total: int | None = None):
        """Starts a new stage. `total=None` renders an indeterminate spinner;
        otherwise a real percentage bar driven by update()."""
        self._stop_spinner()
        self._label = label
        self._total = total
        self._current = 0
        if total is None:
            self._spin_stop.clear()
            self._spin_thread = threading.Thread(target=self._spin, daemon=True)
            self._spin_thread.start()
        self._render()

    def update(self, current: int, total: int | None = None):
        """Advances a determinate stage's progress."""
        self._current = current
        if total is not None:
            self._total = total
        self._render()

    def done(self, label: str | None = None):
        """Finalizes the current stage - the line is kept (not overwritten
        by the next stage's first render) so a scroll-back history of
        completed stages remains readable."""
        self._stop_spinner()
        final_label = label or self._label
        if not self.enabled:
            print(final_label)
            return
        sys.stdout.write("\r" + f"[done] {final_label}".ljust(self._width()) + "\n")
        sys.stdout.flush()

    def fail(self, message: str):
        """Reports a failure for the current stage and stops any spinner animation."""
        self._stop_spinner()
        if self.enabled:
            sys.stdout.write("\n")
        prefix = f"[failed] {self._label}: " if self._label else "[failed] "
        print(prefix + message)
