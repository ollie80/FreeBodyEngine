import numpy as np
import sounddevice as sd
import soundfile as sf
import threading
import scipy.signal

from FreeBodyEngine.audio.sound import AudioManager, Sound


class SoundFileAudioManager(AudioManager):
    """Native audio implementation using sounddevice."""

    def __init__(self):
        super().__init__()

        self.sample_rate = 48000
        self.channels = 2

        self.lock = threading.Lock()

        self.stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            callback=self.callback,
            finished_callback=self.on_stream_finished,
            blocksize=1024,
            latency="low",
        )

        self.stream.start()

    def callback(self, outdata, frames, time_info, status):
        """Mixes all active sounds into the native output stream."""

        with self.lock:
            if not self.sounds:
                outdata.fill(0)
                return

            mix = np.zeros(
                (frames, self.channels),
                dtype="float32",
            )

            to_remove = []

            for sound in self.sounds:
                data = sound.get_frames(frames)

                if data is None:
                    to_remove.append(sound)
                    continue

                data = data * (
                    self.volume *
                    sound.volume
                )

                mix[:len(data)] += data

            for sound in to_remove:
                try:
                    self.sounds.remove(sound)
                except ValueError:
                    pass

            np.clip(
                mix,
                -1,
                1,
                out=mix,
            )

            outdata[:] = mix

    def on_stream_finished(self):
        pass

    def add_sound(self, sound):
        with self.lock:
            if sound not in self.sounds:
                self.sounds.append(sound)

    def remove_sound(self, sound):
        with self.lock:
            try:
                self.sounds.remove(sound)
            except ValueError:
                pass

    def create_sound(self, data):
        return Sound(data, self)

    def shutdown(self):
        self.running = False

        self.stream.stop()
        self.stream.close()


class Sound(Sound):
    """Native sound implementation using soundfile."""

    def __init__(self, data, manager):
        super().__init__(manager)

        data, sr = sf.read(
            data,
            dtype="float32",
            always_2d=True,
        )

        self.sample_rate = sr

        if sr != manager.sample_rate:
            data = resample_audio(
                data,
                sr,
                manager.sample_rate,
            )

            self.sample_rate = manager.sample_rate

        if (
            data.shape[1] == 1
            and manager.channels == 2
        ):
            data = np.repeat(
                data,
                2,
                axis=1,
            )

        self.data = data

        self.start_frame = self._detect_leading_silence()

        self.position = 0

        self.paused = False
        self.stopped = True

    def _detect_leading_silence(
        self,
        threshold=0.01,
        max_skip_s=10.0,
    ):
        max_frames = min(
            len(self.data),
            int(max_skip_s * self.sample_rate),
        )

        if max_frames == 0:
            return 0

        peak = np.max(
            np.abs(self.data[:max_frames]),
            axis=1,
        )

        above = np.nonzero(
            peak > threshold
        )[0]

        if len(above) == 0:
            return 0

        return int(above[0])

    def get_frames(self, num_frames):
        """Returns the next block of samples."""

        if self.paused or self.stopped:
            return np.zeros(
                (
                    num_frames,
                    self.manager.channels,
                ),
                dtype="float32",
            )

        end = self.position + num_frames

        chunk = self.data[
            self.position:end
        ]

        self.position = end

        if len(chunk) < num_frames:
            self.stopped = True

            pad = np.zeros(
                (
                    num_frames - len(chunk),
                    self.manager.channels,
                ),
                dtype="float32",
            )

            return np.vstack(
                (
                    chunk,
                    pad,
                )
            )

        return chunk

    def play(self):
        if self.stopped:
            self.position = self.start_frame

        self.stopped = False
        self.paused = False

        self.manager.add_sound(self)

    def pause(self):
        self.paused = True

    def stop(self):
        self.stopped = True
        self.paused = False
        self.position = self.start_frame

        self.manager.remove_sound(self)

    def seek(self, position_s):
        if position_s <= 0:
            frame = self.start_frame
        else:
            frame = max(
                0,
                min(
                    int(
                        position_s *
                        self.sample_rate
                    ),
                    len(self.data),
                ),
            )

        self.position = frame

        if frame < len(self.data):
            self.stopped = False

    @property
    def duration(self):
        return len(self.data) / self.sample_rate

    @property
    def position_s(self):
        return self.position / self.sample_rate


def resample_audio(
    data,
    orig_sr,
    target_sr,
):
    duration = data.shape[0] / orig_sr

    target_length = int(
        duration * target_sr
    )

    return scipy.signal.resample(
        data,
        target_length,
        axis=0,
    )
