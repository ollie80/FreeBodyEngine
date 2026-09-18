import numpy as np

from js import AudioContext, Float32Array, Uint8Array

from pyodide.http import pyfetch

from FreeBodyEngine.audio.sound import AudioManager, Sound


class PyodideAudioManager(AudioManager):
    """Browser/Pyodide audio implementation using Web Audio API."""

    def __init__(self):
        super().__init__()

        self.sample_rate = 48000
        self.channels = 2

        try:
            self.context = AudioContext.new({
                "sampleRate": self.sample_rate,
                "latencyHint": "interactive",
            })

        except Exception:
            self.context = AudioContext.new({
                "latencyHint": "interactive",
            })

        self.sample_rate = int(
            self.context.sampleRate
        )

        self.master_gain = (
            self.context.createGain()
        )

        self.master_gain.gain.value = (
            self.volume
        )

        self.master_gain.connect(
            self.context.destination
        )

    async def resume(self):
        """Resumes the browser audio context."""

        if self.context.state != "running":
            await self.context.resume()

    def _set_backend_volume(self, volume):
        self.master_gain.gain.value = volume

    async def create_sound(self, data):
        sound = Sound(self)

        await sound.load(data)

        return sound

    def stop_all(self):
        for sound in list(self.sounds):
            sound.stop()

        self.sounds.clear()

    async def shutdown(self):
        self.running = False

        self.stop_all()

        try:
            self.master_gain.disconnect()
        except Exception:
            pass

        try:
            await self.context.close()
        except Exception:
            pass


class Sound(Sound):
    """Browser sound implementation using Web Audio API."""

    def __init__(self, manager):
        super().__init__(manager)

        self.buffer = None
        self.gain = None
        self.source = None

        self.sample_rate = manager.sample_rate

        self._offset = 0.0
        self._started_at = 0.0

        self._generation = 0
        self._data_cache = None

    @property
    def data(self):
        """The full decoded PCM as a `(frames, channels)` float32 array -
        computed once (real work: one JS->Python copy per channel over
        the whole clip) and cached from then on. Desktop's Sound (see
        audio/sound_file.py) already stores its decoded audio this way
        natively; this backend decodes into a JS AudioBuffer instead (see
        load()), so anything that wants raw PCM - currently just phonon's
        visualizer, via analyze_async() - needs this converted
        explicitly rather than being able to read `self.buffer` the same
        way. Same copyFromChannel-based JS-to-numpy conversion
        _detect_leading_silence() already does over a capped window,
        just over the whole buffer and every channel here."""
        if self._data_cache is not None:
            return self._data_cache

        if self.buffer is None:
            return np.zeros((0, self.manager.channels), dtype=np.float32)

        frames = int(self.buffer.length)
        channels = int(self.buffer.numberOfChannels)
        out = np.zeros((frames, channels), dtype=np.float32)

        for channel_index in range(channels):
            js_data = Float32Array.new(frames)
            self.buffer.copyFromChannel(js_data, channel_index, 0)
            out[:, channel_index] = np.asarray(js_data.to_py(), dtype=np.float32)

        self._data_cache = out
        return out

    async def load(self, data):
        """Loads and decodes the audio.

        A string `data` is either a real URL (fetched over the network
        via pyfetch - Pyodide's own fetch() wrapper) or a path already
        sitting in Pyodide's virtual filesystem (e.g. a track this
        engine's own caller already downloaded to local disk - see
        phonon's PlaybackService._download(), which always hands
        create_sound() a plain cache-file path, never a URL). The two
        need genuinely different handling, not just different-looking
        strings to the same call: pyfetch() only understands network
        URLs - handed a filesystem path instead, Pyodide's fetch shim
        resolves it as same-origin and requests it over HTTP, which
        404s (there's no route serving `/home/pyodide/.cache/...`, that
        path was never meant to be fetched at all, just opened). A plain
        `open(data, "rb")` is what actually reads an already-local file
        under Pyodide's virtual FS - the same one _download() wrote it
        into - with no network involved either way."""

        if isinstance(data, str):
            if "://" in data:
                response = await pyfetch(data)

                response.raise_for_status()

                array_buffer = await response.buffer()
            else:
                with open(data, "rb") as f:
                    raw_bytes = f.read()

                array_buffer = Uint8Array.new(raw_bytes).buffer

        else:
            if hasattr(data, "buffer"):
                array_buffer = data.buffer
            else:
                array_buffer = data

        self.buffer = await (
            self.manager.context.decodeAudioData(
                array_buffer
            )
        )
        self._data_cache = None  # stale after any (re)load - see data's own docstring

        self.sample_rate = int(
            self.buffer.sampleRate
        )

        self.start_frame = (
            self._detect_leading_silence()
        )

        self._offset = (
            self.start_frame /
            self.sample_rate
        )

        self._create_gain()

        self.paused = False
        self.stopped = True

    def _create_gain(self):
        if self.gain is not None:
            try:
                self.gain.disconnect()
            except Exception:
                pass

        self.gain = (
            self.manager.context.createGain()
        )

        self.gain.gain.value = self.volume

        self.gain.connect(
            self.manager.master_gain
        )

    def _set_backend_volume(self, volume):
        if self.gain is not None:
            self.gain.gain.value = volume

    def _detect_leading_silence(
        self,
        threshold=0.01,
        max_skip_s=10.0,
    ):
        if self.buffer is None:
            return 0

        total_frames = int(
            self.buffer.length
        )

        if total_frames == 0:
            return 0

        max_frames = min(
            total_frames,
            int(
                max_skip_s *
                self.sample_rate
            ),
        )

        if max_frames <= 0:
            return 0

        channels = int(
            self.buffer.numberOfChannels
        )

        peak = np.zeros(
            max_frames,
            dtype=np.float32,
        )

        for channel_index in range(channels):
            js_data = Float32Array.new(
                max_frames
            )

            self.buffer.copyFromChannel(
                js_data,
                channel_index,
                0,
            )

            channel = np.asarray(
                js_data.to_py(),
                dtype=np.float32,
            )

            np.maximum(
                peak,
                np.abs(channel),
                out=peak,
            )

        above = np.nonzero(
            peak > threshold
        )[0]

        if len(above) == 0:
            return 0

        return int(above[0])

    def _current_position(self):
        if (
            self.buffer is None
            or self.paused
            or self.stopped
            or self.source is None
        ):
            return self._offset

        elapsed = (
            float(
                self.manager.context.currentTime
            )
            - self._started_at
        )

        position = self._offset + elapsed

        return min(
            position,
            float(self.buffer.duration),
        )

    def _source_finished(self, generation):
        if generation != self._generation:
            return

        if self.stopped or self.paused:
            return

        self.stopped = True
        self.paused = False

        self._offset = float(
            self.buffer.duration
        )

        self.source = None

        self.manager.remove_sound(self)

    def _create_source(self):
        self.source = (
            self.manager.context
            .createBufferSource()
        )

        self.source.buffer = self.buffer

        self.source.connect(
            self.gain
        )

        self._generation += 1

        generation = self._generation

        def on_ended(event=None):
            # The browser invokes onended with the Event object (per the
            # standard DOM event-handler calling convention) - a
            # zero-argument callback here raised "on_ended() takes 0
            # positional arguments but 1 was given" the instant any
            # track finished playing, which meant this Sound never
            # actually reached _source_finished() to flip `stopped` -
            # naturally reaching the end of a track was silently inert
            # on web (no auto-advance, no LOOP_TRACK restart) even
            # though nothing higher up ever saw an error for it.
            self._source_finished(
                generation
            )

        self.source.onended = on_ended

    async def play(self):
        if self.buffer is None:
            raise RuntimeError(
                "Sound has not been loaded"
            )

        await self.manager.resume()

        if self.stopped:
            self._offset = (
                self.start_frame /
                self.sample_rate
            )

        if (
            self._offset >=
            float(self.buffer.duration)
        ):
            self._offset = (
                self.start_frame /
                self.sample_rate
            )

        self.stopped = False
        self.paused = False

        self._create_source()

        self._started_at = float(
            self.manager.context.currentTime
        )

        self.source.start(
            0,
            self._offset,
        )

        self.manager.add_sound(self)

    def pause(self):
        if self.buffer is None:
            return

        if (
            self.stopped
            or self.paused
        ):
            return

        self._offset = (
            self._current_position()
        )

        self.paused = True

        self._generation += 1

        if self.source is not None:
            try:
                self.source.stop()
            except Exception:
                pass

            try:
                self.source.disconnect()
            except Exception:
                pass

            self.source = None

    def stop(self):
        self._generation += 1

        if self.source is not None:
            try:
                self.source.stop()
            except Exception:
                pass

            try:
                self.source.disconnect()
            except Exception:
                pass

            self.source = None

        self.stopped = True
        self.paused = False

        self._offset = (
            self.start_frame /
            self.sample_rate
        )

        self.manager.remove_sound(self)

    def seek(self, position_s):
        if self.buffer is None:
            return

        duration = float(
            self.buffer.duration
        )

        if position_s <= 0:
            position_s = (
                self.start_frame /
                self.sample_rate
            )
        else:
            position_s = max(
                0.0,
                min(
                    float(position_s),
                    duration,
                ),
            )

        was_playing = (
            not self.stopped
            and not self.paused
        )

        if was_playing:
            self._generation += 1

            if self.source is not None:
                try:
                    self.source.stop()
                except Exception:
                    pass

                try:
                    self.source.disconnect()
                except Exception:
                    pass

                self.source = None

        self._offset = position_s

        if self._offset < duration:
            self.stopped = False
        else:
            self.stopped = True

        if was_playing:
            self.paused = False

            self._create_source()

            self._started_at = float(
                self.manager.context.currentTime
            )

            self.source.start(
                0,
                self._offset,
            )

            self.manager.add_sound(self)

    @property
    def duration(self):
        if self.buffer is None:
            return 0.0

        return float(
            self.buffer.duration
        )

    @property
    def position_s(self):
        return self._current_position()
