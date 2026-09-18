from FreeBodyEngine.core.service import Service


class AudioManager(Service):
    """Generic engine-facing audio manager.

    Contains functionality that is independent of the actual audio backend.
    Platform-specific implementations inherit from this class.
    """

    def __init__(self):
        super().__init__("audio")

        self.volume = 1.0
        self.sounds = []
        self.running = True

    def add_sound(self, sound):
        """Adds a sound to the currently active sounds."""
        if sound not in self.sounds:
            self.sounds.append(sound)

    def remove_sound(self, sound):
        """Removes a sound from the currently active sounds."""
        try:
            self.sounds.remove(sound)
        except ValueError:
            pass

    def stop_all(self):
        """Stops every currently-playing sound."""
        for sound in list(self.sounds):
            sound.stop()

        self.sounds.clear()

    def set_volume(self, volume):
        """Sets the master volume."""
        self.volume = float(volume)
        self._set_backend_volume(self.volume)

    def _set_backend_volume(self, volume):
        """Backend-specific master-volume hook."""
        pass

    def create_sound(self, data):
        """Creates a backend-specific Sound."""
        raise NotImplementedError

    def shutdown(self):
        """Shuts down the backend."""
        self.running = False


class Sound:
    """Generic engine-facing representation of a sound.

    Backend implementations provide the actual decoding and playback.
    """

    def __init__(self, manager):
        self.manager = manager

        self.volume = 1.0

        self.start_frame = 0
        self.position = 0

        self.paused = False
        self.stopped = True

    def set_volume(self, volume):
        """Sets this sound's volume."""
        self.volume = float(volume)
        self._set_backend_volume(self.volume)

    def _set_backend_volume(self, volume):
        """Backend-specific volume hook."""
        pass

    def play(self):
        """Starts or resumes playback."""
        raise NotImplementedError

    def pause(self):
        """Pauses playback."""
        raise NotImplementedError

    def stop(self):
        """Stops playback and resets position."""
        raise NotImplementedError

    def seek(self, position_s):
        """Seeks to a position in seconds."""
        raise NotImplementedError

    @property
    def duration(self):
        """Total duration in seconds."""
        raise NotImplementedError

    @property
    def position_s(self):
        """Current playback position in seconds."""
        raise NotImplementedError
