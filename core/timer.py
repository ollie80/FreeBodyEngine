
class Timer:
    def __init__(self, duration):
        self.duration = duration
        self.time_remaining = self.duration
        self.active = False
        self.complete = False

    def activate(self):
        self.active = True
        self.complete = False
        self.time_remaining = self.duration

    def deactivate(self):
        self.active = False
        self.time_remaining = 0

    def update(self, dt):
        if self.active:
            self.time_remaining -= dt
        if self.time_remaining <= 0:
            self.deactivate()
            self.complete = True


