import time

class Time:
    def __init__(self):
        self._start_time = time.time()
        self._last_time = self._start_time
        self.delta_time = 0.0
        self.unscaled_delta_time = 0.0
        self.time_scale = 1.0
        self.total_time = 0.0
        self.frame_count = 0
        self.fps = 0.0

    def update(self, fps_cap): 
        current_time = time.time()
        raw_delta = current_time - self._last_time
        
        if fps_cap != 0:
            min_frame_time = 1.0 / fps_cap
            if raw_delta < min_frame_time:
                time.sleep(min_frame_time - raw_delta)
                current_time = time.time()
                raw_delta = current_time - self._last_time
        

        self.unscaled_delta_time = raw_delta
        self.delta_time = raw_delta * self.time_scale
        self.total_time = current_time - self._start_time
        self._last_time = current_time
        self.frame_count += 1

        if self.delta_time > 0:
            self.fps = 1.0 / self.delta_time