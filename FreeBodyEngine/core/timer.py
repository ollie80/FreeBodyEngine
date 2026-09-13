from FreeBodyEngine import delta, physics_delta


class Timer:
    """A simple countdown timer - call update() every frame while active, and check `complete` once `time_remaining` reaches zero."""
    def __init__(self, duration, physics=False):
        """Creates the timer, inactive, counting down from `duration`. If `physics` is True, update() counts down using physics_delta() (the fixed physics step) instead of delta() (the variable frame time)."""
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
        """Stops the timer without marking it complete, and zeroes its remaining time."""
        self.active = False
        self.time_remaining = 0

    def update(self):
        """Counts down `time_remaining` by one frame's (or physics step's) delta while active, deactivating and setting `complete` once it runs out."""
        if self.active:
            if not self.physics:
                self.time_remaining -= delta()
            else:
                self.time_remaining -= physics_delta()
        if self.time_remaining <= 0:
            self.deactivate()
            self.complete = True


