import sys
import time

class Profiler:
    """A crude call-time profiler built on `sys.setprofile` - installed for
    the whole process as soon as a `Profiler` is constructed, but only
    actually records timings while active (between `start()` and `stop()`)."""

    def __init__(self):
        """Installs this instance as the process's global profile function.
        Nothing is recorded until `start()` is called, even though the hook
        is live immediately."""
        sys.setprofile(self.profile)
        self._active = False
        self.frame_calls = {}
        self.calls = {}

    def start(self):
        """Begins recording call timings."""
        self._active = True

    def stop(self):
        """Stops recording, prints the accumulated per-function call times
        (sorted by function name; entries under 1ms are omitted), and
        resets `self.calls` for the next run.

        Note: `self.frame_calls` is printed alongside `self.calls` but is
        never actually populated by `profile()` - it's always empty."""
        self._active = False

        def format_float(x: float):
            return f'{x[1]:.3f}'

        sorted_frame_calls = [(x[0], format_float(x)) if format_float(x) != '0.000' else None for x in sorted(self.frame_calls.items())]
        sorted_calls = [(x[0], format_float(x)) if format_float(x) != '0.000' else None for x in sorted(self.calls.items())]

        print(sorted_frame_calls)
        print(sorted_calls)
        
        self.calls = {}

    def profile(self, frame, event, args):
        """The `sys.setprofile` callback: on a "call" event, stashes a start
        timestamp on the frame's locals; on the matching "return" event,
        adds the elapsed time to `self.calls[function_name]`. A no-op while
        `self._active` is False."""
        if self._active:
                if event == "call":
                    frame.f_locals['_t0'] = time.perf_counter()
                elif event == "return":
                    t0 = frame.f_locals.pop('_t0', None)
                    if t0:
                        name = frame.f_code.co_name
                        if name not in self.calls:
                            self.calls[name] = 0
                        self.calls[name] += time.perf_counter() - t0

    def close(self):
        """Deactivates the profiler. Does not uninstall the `sys.setprofile`
        hook itself - `profile()` keeps running on every call/return event
        process-wide, just without recording anything."""
        self._active = False
