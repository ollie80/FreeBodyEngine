from FreeBodyEngine import delta, physics_delta


class Timer:
    def __init__(self, duration, physics=False):
        self.duration = duration
        self.physics = physics
        self.time_remaining = self.duration
        self.active = False
        self.complete = False

    def activate(self):
        """Resets the timer and starts it."""
        self.active = True
        self.complete = False
        self.time_remaining = self.duration

    def deactivate(self):
        self.active = False
        self.time_remaining = 0

    def update(self):
        if self.active:
            if not self.physics:
                self.time_remaining -= delta()
            else:
                self.time_remaining -= physics_delta()
        if self.time_remaining <= 0:
            self.deactivate()
            self.complete = True


