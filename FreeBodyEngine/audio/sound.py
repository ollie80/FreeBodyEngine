import time
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

        # Set by _note_frames_consumed() - see _interpolated_position_s().
        self._last_block_frames = 0
        self._last_block_at = None

    def _note_frames_consumed(self, num_frames: int):
        """Called by a backend's get_frames() with the block size it was
        just asked for, so position can be interpolated between callbacks."""
        self._last_block_frames = num_frames
        self._last_block_at = time.monotonic()

    def _interpolated_position_s(self, consumed_frames: int, sample_rate: int) -> float:
        """Playback position that advances smoothly, instead of in one
        jump per audio callback.

        `consumed_frames` only changes when the audio device asks for
        more samples - every 21ms at this engine's block size, and
        considerably less often where the OS hands back a bigger buffer
        than was asked for. Anything sampling position per rendered
        frame therefore reads a staircase, and re-reads the same step
        several frames running. That's what limited the visualizer's
        effective sample rate: not how finely the track was analyzed
        (~86 points/second), but how coarsely it was asked *when*.

        The count is also a block ahead of what's audible - those frames
        have been handed to the device, not played yet - so one block is
        subtracted and then wall-clock time since the callback is added
        back. At the instant of a callback that lands on the audio just
        starting to play; a full block later it lands on the next
        callback's value, which is where the staircase would have jumped
        to anyway. Clamped to one block so a paused or starved stream
        can't run away."""
        base = consumed_frames / sample_rate
        if self.paused or self.stopped or self._last_block_at is None or not self._last_block_frames:
            return base

        block_s = self._last_block_frames / sample_rate
        elapsed = min(max(time.monotonic() - self._last_block_at, 0.0), block_s)
        return max(0.0, base - block_s + elapsed)

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
