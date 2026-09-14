import numpy as np
import sounddevice as sd
import soundfile as sf
import threading
import scipy.signal
from FreeBodyEngine.core.node import Node2D
from FreeBodyEngine.core.service import Service

class AudioManager(Service):
    """Engine service owning the audio output stream and mixing every
    currently-playing `Sound` into it in real time."""

    def __init__(self):
        """Opens and starts the output audio stream, ready to mix in sounds
        added via `add_sound`/`create_sound`."""
        super().__init__("audio")
        self.volume = 1.0 
        self.sounds = []  
        self.lock = threading.Lock()

        self.sample_rate = 44100
        self.channels = 2

        self.stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype='float32',
            callback=self.callback,
            finished_callback=self.on_stream_finished,
            blocksize=1024,
            latency='low'
        )
        self.stream.start()
        self.running = True

    def callback(self, outdata, frames, time_info, status):
        """`sounddevice` output stream callback, called from the audio thread
        to fill `outdata` with the next `frames` samples.

        Pulls `frames` samples from every active sound, scales each by the
        manager's master volume and the sound's own volume, sums them, drops
        any sound whose `get_frames` ran out of data, and clips the mix to
        [-1, 1] to avoid clipping artifacts overflowing the output format.
        Guarded by `self.lock` since sounds are added/removed from the main thread.
        """
        with self.lock:
            if not self.sounds:
                outdata.fill(0)
                return

            mix = np.zeros((frames, self.channels), dtype='float32')

            to_remove = []
            for sound in self.sounds:
                data = sound.get_frames(frames)
                if data is None:
                    to_remove.append(sound)
                    continue

                data = data * (self.volume * sound.volume)

                mix[:len(data)] += data

            for s in to_remove:
                self.sounds.remove(s)

            np.clip(mix, -1, 1, out=mix)

            outdata[:] = mix

    def on_stream_finished(self):
        """Callback passed to the output stream; currently a no-op."""
        pass

    def add_sound(self, sound):
        """Adds `sound` to the set of sounds being mixed into the output stream."""
        with self.lock:
            self.sounds.append(sound)

    def create_sound(self, data):
        """Creates a `Sound` from `data` (anything `soundfile.read` accepts,
        e.g. a path or file-like object), registered to this manager."""
        return Sound(data, self)

    def stop_all(self):
        """Stops every currently-playing sound."""
        with self.lock:
            self.sounds.clear()

    def shutdown(self):
        """Stops and closes the output audio stream."""
        self.running = False
        self.stream.stop()
        self.stream.close()


def resample_audio(data, orig_sr, target_sr):
    """Resamples `data` from `orig_sr` to `target_sr` using Fourier-method resampling."""
    duration = data.shape[0] / orig_sr
    target_length = int(duration * target_sr)
    resampled = scipy.signal.resample(data, target_length, axis=0)
    return resampled

class Sound:
    """A single loaded audio clip that can be played through an `AudioManager`.

    The whole clip is decoded and resampled/channel-matched up front in
    `__init__` (not streamed), and playback position/state is just an index
    into that in-memory array advanced by `get_frames`.
    """

    def __init__(self, data: any, manager: AudioManager):
        """Loads and, if needed, resamples/upmixes `data` to match `manager`'s
        stream format, ready to be played through it.

        Args:
            data (any): Anything `soundfile.read` accepts (e.g. a path or file-like object).
            manager: The `AudioManager` this sound will be played through -
                its sample rate/channel count is what `data` is converted to match.
        """
        data, sr = sf.read(data, dtype='float32', always_2d=True)
        self.manager = manager
        self.sample_rate = sr
        self.volume = 1.0

        if sr != manager.sample_rate:
            data = resample_audio(data, sr, manager.sample_rate)
            self.sample_rate = manager.sample_rate

        if data.shape[1] == 1 and manager.channels == 2:
            data = np.repeat(data, 2, axis=1)

        self.data = data
        self.position = 0  
        self.paused = False
        self.stopped = True

    def get_frames(self, num_frames):
        """Pulls the next `num_frames` samples from the current playback
        position and advances it, for `AudioManager.callback` to mix in.

        Returns silence (all zeros) without advancing playback if paused or
        stopped. If fewer than `num_frames` samples remain, pads the result
        with zeros to `num_frames` and marks the sound `stopped` - it won't
        yield any real audio again until `play()` resets its position.
        """
        if self.paused or self.stopped:
            return np.zeros((num_frames, self.manager.channels), dtype='float32')

        end = self.position + num_frames
        chunk = self.data[self.position:end]
        self.position = end

        if len(chunk) < num_frames:
            self.stopped = True
            
            # pad with zeros
            pad = np.zeros((num_frames - len(chunk), self.manager.channels), dtype='float32')
            return np.vstack((chunk, pad))

        return chunk

    def play(self):
        """Starts (or restarts) playback from the beginning, registering this
        sound with its manager if it isn't already being mixed."""
        if self in self.manager.sounds:
            self.position = 0
            self.stopped = False
            self.paused = False
        else:
            self.position = 0
            self.stopped = False
            self.paused = False
            self.manager.add_sound(self)

    def pause(self):
        """Pauses playback in place; `play()` resumes from the start, not where it paused."""
        self.paused = True

    def stop(self):
        """Stops playback and resets the position back to the start."""
        self.stopped = True
        self.position = 0

