import sys
import time

class Profiler:
    def __init__(self):
        sys.setprofile(self.profile)
        self._active = False
        self.frame_calls = {}     
        self.calls = {}     

    def start(self):
        self._active = True

    def stop(self):
        self._active = False

        def format_float(x: float):
            return f'{x[1]:.3f}'

        sorted_frame_calls = [(x[0], format_float(x)) if format_float(x) != '0.000' else None for x in sorted(self.frame_calls.items())]
        sorted_calls = [(x[0], format_float(x)) if format_float(x) != '0.000' else None for x in sorted(self.calls.items())]

        print(sorted_frame_calls)
        print(sorted_calls)
        
        self.calls = {}

    def profile(self, frame, event, args):
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
        self._active = False
