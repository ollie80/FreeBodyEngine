"""Android audio backend, built on a raw SDL audio output device (PySDL2's
`sdl2.audio` bindings) plus `pyogg` for incremental Ogg/Vorbis decode.

This used to decode a whole track into an in-memory float32 PCM array
upfront via SDL2_mixer's `Mix_LoadWAV_RW` (see git history), the same
"decode everything, then play a slice of it" shape as sound_file.py's
desktop backend. That's fine on desktop, where a track's full decoded size
is a rounding error against available RAM - on a real Android device it
was confirmed live to actually crash the app: a single ordinary track's
full decode (48kHz stereo float32 - roughly 1.5MB per second of audio, so
tens to hundreds of MB for one song) was enough, combined with the rest of
the running system, to drive the device into severe swap thrashing, and
Android's own low-memory-killer terminated the app outright
(`lmkd: ... reason: device is low on swap ... and thrashing (302%)`)
roughly 10-15 seconds into playback every time.

Architecture instead mirrors sound_file.py's *pull* model directly - a
single persistent output device with one mixing callback that pulls
`get_frames(n)` from every active Sound and sums them, matching
`SoundFileAudioManager.callback()` almost exactly - except:

- `sounddevice` (desktop's stream implementation, wrapping PortAudio) has
  no Android backend at all, so this manager opens a raw SDL audio device
  (`SDL_OpenAudioDevice`) instead, via a ctypes `SDL_AudioCallback` kept
  alive on `self` for the same GC-safety reason graphics/gl33/renderer.py's
  own module-level GLDEBUGPROC callback is (SDL doesn't keep a CFUNCTYPE
  instance alive on the C side's behalf).
- Each Sound decodes incrementally instead of upfront: a background daemon
  thread keeps a short (`_STREAM_LOOKAHEAD_SECONDS`) rolling buffer of
  already-decoded PCM topped up via `pyogg.VorbisFileStream.get_buffer()`
  (a few KB at a time, straight from libvorbisfile - already bundled for
  this build's ffmpeg Vorbis encoder, see the local ffmpeg p4a recipe
  override), and `get_frames()` (called from the realtime audio callback,
  so it must never block on I/O) just pops off the front of that buffer.
  This bounds this backend's own memory use to a few MB *regardless of
  track length*, the actual fix for the crash above - not just a smaller
  version of the same unbounded-by-duration problem.
- Seeking calls libvorbisfile's own `ov_time_seek` directly (real
  decoder-level seeking, not just an index into an in-memory array) and
  discards + refills the rolling buffer from the new position.

Every project already using this engine's Android audio only ever
produces/plays Vorbis (`.ogg`) - see phonon's own `playback_service.py`,
which requests exactly that from yt-dlp's FFmpegExtractAudio specifically
because it's what this backend (and libsndfile, desktop's) can decode -
so Vorbis-only support here isn't a narrowing from before; SDL2_mixer's
Mix_LoadWAV_RW never supported anything else either in practice.

Known gap, same category as core/window/android.py's own Activity-lifecycle
gap: `position_s` is derived from how many frames have actually been
handed to the mixing callback via get_frames(), not queried from the audio
driver's own play cursor - accurate enough for a UI scrub bar (and, unlike
the old wall-clock-estimate approach, immune to the device's audio clock
and Python's monotonic clock disagreeing), but does assume the callback
is invoked at a steady rate.
"""
import ctypes
import os
import tempfile
import threading
import time

import numpy as np
import sdl2
import pyogg

from FreeBodyEngine.audio.sound import AudioManager, Sound as BaseSound

SAMPLE_RATE = 48000
CHANNELS = 2
CHUNK_SIZE = 1024

# How far ahead of the current playback position each Sound's background
# feeder thread is allowed to decode - the whole point of this module (see
# its own docstring): bounds memory use to a few MB per active Sound
# regardless of how long the track actually is.
_STREAM_LOOKAHEAD_SECONDS = 4.0

# _detect_leading_silence() only ever needs to look at the first few
# seconds of a track - capped the same way the old in-memory-array
# version's own max_skip_s was, not something this rewrite changed.
_LEADING_SILENCE_LOOKAHEAD_SECONDS = 10.0


class AndroidAudioManager(AudioManager):
    """Raw-SDL-audio-device AudioManager for Android - see this module's
    own docstring for the overall approach."""

    def __init__(self):
        super().__init__()

        self.sample_rate = SAMPLE_RATE
        self.channels = CHANNELS
        self._lock = threading.Lock()

        if sdl2.SDL_WasInit(sdl2.SDL_INIT_AUDIO) == 0:
            if sdl2.SDL_InitSubSystem(sdl2.SDL_INIT_AUDIO) != 0:
                raise RuntimeError(f"SDL_InitSubSystem(AUDIO) failed: {sdl2.SDL_GetError().decode()}")

        desired = sdl2.SDL_AudioSpec(self.sample_rate, sdl2.AUDIO_F32SYS, self.channels, CHUNK_SIZE)
        # Kept alive on self - see this module's own docstring on why.
        self._callback_cb = sdl2.SDL_AudioCallback(self._callback)
        desired.callback = self._callback_cb

        obtained = sdl2.SDL_AudioSpec(0, 0, 0, 0)
        self.device = sdl2.SDL_OpenAudioDevice(None, 0, ctypes.byref(desired), ctypes.byref(obtained), 0)
        if self.device == 0:
            raise RuntimeError(f"SDL_OpenAudioDevice failed: {sdl2.SDL_GetError().decode()}")

        sdl2.SDL_PauseAudioDevice(self.device, 0)  # unpause - starts the callback firing

    def _callback(self, _userdata, stream, length):
        """Fired on SDL's own internal audio thread, not the engine's main
        thread - must stay fast and non-blocking (see get_frames() on each
        Sound: it only ever pops from an already-decoded buffer, never
        does I/O itself, for exactly this reason)."""
        frame_bytes = 4 * self.channels  # AUDIO_F32SYS
        num_frames = length // frame_bytes
        mix = np.zeros((num_frames, self.channels), dtype=np.float32)

        with self._lock:
            for sound in self.sounds:
                data = sound.get_frames(num_frames)
                if data is None:
                    continue
                mix[:len(data)] += data * (self.volume * sound.volume)

        np.clip(mix, -1.0, 1.0, out=mix)
        buf = np.ascontiguousarray(mix, dtype=np.float32).tobytes()
        ctypes.memmove(stream, buf, min(len(buf), length))

    def add_sound(self, sound):
        with self._lock:
            if sound not in self.sounds:
                self.sounds.append(sound)

    def remove_sound(self, sound):
        with self._lock:
            try:
                self.sounds.remove(sound)
            except ValueError:
                pass

    def create_sound(self, data):
        return Sound(data, self)

    def shutdown(self):
        self.running = False
        sdl2.SDL_CloseAudioDevice(self.device)


class Sound(BaseSound):
    """Streaming, `pyogg`-decoded Sound - see this module's own docstring
    for the overall approach and why it replaced a simpler in-memory-array
    one."""

    def __init__(self, data, manager: AndroidAudioManager):
        super().__init__(manager)

        # `data` is whatever a caller's create_sound(data) was handed -
        # playback_service.py always passes a real path to a file already
        # on disk (its own download cache), never an in-memory buffer, but
        # pyogg.VorbisFileStream needs a real path either way, so a
        # file-like/bytes caller gets spooled to a temp file first rather
        # than dropping that flexibility entirely.
        self._owns_temp_file = False
        if isinstance(data, str):
            self._path = data
        else:
            raw_bytes = data.getvalue() if hasattr(data, "getvalue") else data.read()
            fd, self._path = tempfile.mkstemp(suffix=".ogg")
            with os.fdopen(fd, "wb") as f:
                f.write(raw_bytes)
            self._owns_temp_file = True

        self._stream = pyogg.VorbisFileStream(self._path)
        self.sample_rate = self._stream.frequency
        self._src_channels = self._stream.channels
        self._out_channels = manager.channels

        self._duration = max(0.0, pyogg.vorbis.ov_time_total(self._stream.vf, -1))

        # Guards both `self._buffer`/`self._eof` AND every call into
        # `self._stream` (pyogg.VorbisFileStream isn't safe to touch from
        # two threads at once) - held by the feeder thread while decoding,
        # by get_frames() (the realtime audio callback) while popping, and
        # by _seek_to() while reseeking, so none of those three can ever
        # interleave with each other mid-operation.
        self._state_lock = threading.Lock()
        self._buffer = np.empty((0, self._out_channels), dtype=np.float32)
        self._eof = False
        self._closed = False
        self._consumed_frames = 0

        self._feeder = threading.Thread(target=self._feed_loop, daemon=True)
        self._feeder.start()

        self.start_frame = self._detect_leading_silence()
        self.position = self.start_frame

        self.paused = False
        self.stopped = True

    # -- decode ------------------------------------------------------------

    def _remix_channels(self, pcm):
        if self._src_channels == self._out_channels:
            return pcm
        if self._src_channels == 1 and self._out_channels == 2:
            return np.repeat(pcm, 2, axis=1)
        if pcm.shape[1] > self._out_channels:
            return pcm[:, :self._out_channels]
        return np.repeat(pcm, self._out_channels, axis=1)

    def _decode_one_chunk_locked(self):
        """Reads and appends one chunk from the underlying stream to
        `self._buffer`. Caller must already hold `self._state_lock`."""
        result = self._stream.get_buffer()
        if result is None:
            self._eof = True
            return

        raw_bytes, length = result
        pcm = np.frombuffer(raw_bytes[:length], dtype=np.int16).astype(np.float32) / 32768.0
        usable_samples = (len(pcm) // self._src_channels) * self._src_channels
        pcm = pcm[:usable_samples].reshape(-1, self._src_channels)
        pcm = self._remix_channels(pcm)
        self._buffer = np.concatenate((self._buffer, pcm), axis=0) if len(self._buffer) else pcm

    def _feed_loop(self):
        while not self._closed:
            with self._state_lock:
                have_seconds = len(self._buffer) / self.sample_rate
                at_eof = self._eof
                needs_more = not at_eof and have_seconds < _STREAM_LOOKAHEAD_SECONDS
                if needs_more:
                    self._decode_one_chunk_locked()
            if not needs_more:
                time.sleep(0.05)

    def _detect_leading_silence(self, threshold=0.01):
        """Waits (briefly, bounded) for enough of the stream to decode
        rather than reading the whole track upfront the way the old
        in-memory-array version of this did."""
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            with self._state_lock:
                have_seconds = len(self._buffer) / self.sample_rate
                at_eof = self._eof
            if at_eof or have_seconds >= _LEADING_SILENCE_LOOKAHEAD_SECONDS:
                break
            time.sleep(0.02)

        with self._state_lock:
            probe = self._buffer[:int(_LEADING_SILENCE_LOOKAHEAD_SECONDS * self.sample_rate)]

        if len(probe) == 0:
            return 0
        peak = np.max(np.abs(probe), axis=1)
        above = np.nonzero(peak > threshold)[0]
        return int(above[0]) if len(above) else 0

    # -- playback ------------------------------------------------------------

    def get_frames(self, num_frames):
        """Called from the realtime audio callback - must never block on
        I/O, only ever pops whatever the feeder thread has already
        decoded into `self._buffer`."""
        if self.paused or self.stopped:
            return np.zeros((num_frames, self._out_channels), dtype=np.float32)

        with self._state_lock:
            available = len(self._buffer)
            if available == 0 and self._eof:
                self.stopped = True
                return np.zeros((num_frames, self._out_channels), dtype=np.float32)
            take = min(available, num_frames)
            chunk = self._buffer[:take]
            self._buffer = self._buffer[take:]

        self._consumed_frames += take
        self.position = self._consumed_frames

        if take < num_frames:
            pad = np.zeros((num_frames - take, self._out_channels), dtype=np.float32)
            return np.vstack((chunk, pad)) if take else pad
        return chunk

    def _seek_to(self, position_s):
        position_s = max(0.0, position_s)
        with self._state_lock:
            pyogg.vorbis.ov_time_seek(self._stream.vf, position_s)
            self._buffer = np.empty((0, self._out_channels), dtype=np.float32)
            self._eof = False
        self._consumed_frames = int(position_s * self.sample_rate)
        self.position = self._consumed_frames

    def play(self):
        if self.stopped:
            self._seek_to(self.start_frame / self.sample_rate)
        self.stopped = False
        self.paused = False
        self.manager.add_sound(self)

    def pause(self):
        self.paused = True

    def stop(self):
        self._seek_to(self.start_frame / self.sample_rate)
        self.stopped = True
        self.paused = False
        self.manager.remove_sound(self)

    def seek(self, position_s):
        if position_s <= 0:
            target_s = self.start_frame / self.sample_rate
        else:
            target_s = max(0.0, min(position_s, self._duration))
        self._seek_to(target_s)
        self.stopped = target_s >= self._duration

    @property
    def duration(self):
        return self._duration

    @property
    def position_s(self):
        return self._consumed_frames / self.sample_rate

    def __del__(self):
        self._closed = True
        try:
            self._stream.clean_up()
        except Exception:
            pass
        if self._owns_temp_file:
            try:
                os.remove(self._path)
            except OSError:
                pass
