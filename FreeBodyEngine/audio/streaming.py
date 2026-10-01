"""Streaming audio support shared by every platform backend.

Two things live here, both of which exist so playback can begin before a
track has finished arriving.

`FfmpegDecoder` turns any source ffmpeg can open - a local file in any
format, or an http(s) URL - into successive chunks of interleaved int16
at a forced rate and channel count. Forcing the output format is what
makes it drop-in: there is nothing to probe and no remixing left for the
caller.

`StreamingSound` is a Sound that plays from one of those, holding only a
few seconds of decoded audio at a time instead of the whole track. A
background feeder keeps that buffer topped up; the realtime callback only
ever pops from it and never touches I/O.

This module deliberately imports nothing platform-specific. The Android
backend has its own Sound (it also needs libvorbisfile, for the format it
was originally built around) and borrows only the decoder from here; the
desktop backend keeps its whole-file array Sound for local files and uses
StreamingSound when handed a URL.
"""
import os
import subprocess
import threading
import time

import numpy as np

from FreeBodyEngine.audio.sound import Sound as BaseSound

# Sent on URL sources. Not an attempt to be sneaky - it's what the
# resolver that produced the URL identifies as, and a mismatch between
# the two is what gets the request refused.
STREAM_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# How far ahead of the playhead the feeder decodes. The point of the
# exercise: a few MB per active Sound regardless of track length.
STREAM_LOOKAHEAD_SECONDS = 4.0


def is_url(source: str) -> bool:
    return source.startswith("http://") or source.startswith("https://")


def _android_bin(name: str) -> str | None:
    """Path to one of the binaries p4a's bootstrap unpacks into
    `.bin/` inside the app's private files dir (ANDROID_ARGUMENT is
    p4a's own env var for that directory). Returns None off-device or if
    this build didn't bundle it."""
    root = os.environ.get("ANDROID_ARGUMENT")
    if not root:
        return None
    path = os.path.join(root, ".bin", name)
    return path if os.path.exists(path) else None


_FFMPEG_EXEC_LOCK = threading.Lock()

# The libraries ffmpeg itself needs, deliberately excluding
# libssl/libcrypto - see _ffmpeg_library_path() for why that matters.
_FFMPEG_AV_LIBS = (
    "libavdevice.so", "libavfilter.so", "libavformat.so", "libavcodec.so",
    "libswresample.so", "libswscale.so", "libavutil.so",
    "libvorbis.so", "libvorbisenc.so", "libogg.so",
)


class _FfmpegLibraryPath:
    """Scopes LD_LIBRARY_PATH to a directory holding only the libraries
    ffmpeg needs, for exactly as long as it takes to exec it.

    Android loads its own /system/lib64/libsqlite.so into any exec'd
    process regardless of what that process links against, and that
    library binds OpenSSL symbols against whichever libcrypto the linker
    finds first. Point LD_LIBRARY_PATH at this app's full native lib
    directory (which ffmpeg needs, to find its own libav*.so) and it
    finds this app's OpenSSL 3.x - which no longer exports the 1.x-era
    symbol libsqlite wants - and ffmpeg dies at exec with a link error
    naming a library it has nothing to do with. Narrowing the path so
    libssl/libcrypto simply aren't on it lets the loader fall through to
    the system's own provider.

    The lock is not incidental: this mutates one process-wide variable,
    and two decoders starting at once would otherwise interleave their
    enter/exit and hand one of them the unnarrowed path."""

    def __init__(self, directory: str):
        self._directory = directory
        self._previous = None

    def __enter__(self):
        _FFMPEG_EXEC_LOCK.acquire()
        self._previous = os.environ.get("LD_LIBRARY_PATH")
        os.environ["LD_LIBRARY_PATH"] = self._directory
        return None

    def __exit__(self, *_exc_info):
        if self._previous is None:
            os.environ.pop("LD_LIBRARY_PATH", None)
        else:
            os.environ["LD_LIBRARY_PATH"] = self._previous
        _FFMPEG_EXEC_LOCK.release()
        return False


def _ffmpeg_library_path(ffmpeg_path: str):
    """Builds (once) a directory of symlinks to just the libraries
    ffmpeg needs, and returns a context manager scoping LD_LIBRARY_PATH
    to it. `.bin/ffmpeg` resolves into this install's real native lib
    directory, which is how that directory is discovered without any
    Android API."""
    native_dir = os.path.dirname(os.path.realpath(ffmpeg_path))
    curated = os.path.join(os.path.dirname(ffmpeg_path), "_avlibs")
    os.makedirs(curated, exist_ok=True)
    for name in _FFMPEG_AV_LIBS:
        source, link = os.path.join(native_dir, name), os.path.join(curated, name)
        if os.path.exists(source) and not os.path.exists(link):
            try:
                os.symlink(source, link)
            except OSError:
                pass
    return _FfmpegLibraryPath(curated)




class FfmpegDecoder:
    """Anything else, decoded by the bundled ffmpeg into raw int16.

    Output format is *forced* rather than discovered - a fixed rate and
    the channel count the mixer wants - so there is nothing to probe and
    no remixing left to do downstream. Seeking restarts the process with
    `-ss`, which is the only way to seek a pipe; that costs a respawn,
    but seeks are rare next to the steady read this does otherwise."""

    READ_SIZE = 32768

    def __init__(self, path: str, channels: int, sample_rate: int):
        self._path = path
        self.channels = channels
        self.sample_rate = sample_rate
        self._binary = _android_bin("ffmpeg") or "ffmpeg"
        self._scope = (_ffmpeg_library_path(self._binary)
                       if _android_bin("ffmpeg") else None)
        self.is_url = is_url(path)
        # A URL is deliberately not probed. ffprobe would mean a second
        # trip over the network - on a cold host, a second wait for the
        # same track to be produced - to learn something the caller
        # already knows: PlaybackService takes its duration from the
        # track's own catalog metadata, not from the Sound (see its
        # duration_s property), so nothing downstream reads this.
        self.duration = 0.0 if self.is_url else self._probe_duration()
        self._process = None
        self._spawn(0.0)

    def _run(self, args):
        if self._scope is not None:
            with self._scope:
                return subprocess.run(args, capture_output=True)
        return subprocess.run(args, capture_output=True)

    def _probe_duration(self) -> float:
        probe = _android_bin("ffprobe") or "ffprobe"
        try:
            result = self._run([
                probe, "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", self._path,
            ])
            return max(0.0, float(result.stdout.decode().strip()))
        except Exception:
            # Without a duration the seek bar has no scale, but playback
            # itself is unaffected - better than refusing the track.
            return 0.0

    def _spawn(self, start_seconds: float):
        self._terminate()
        args = [self._binary, "-v", "error"]
        if self.is_url:
            # Survive the kind of interruption a phone's wifi produces
            # routinely. Without these ffmpeg treats a dropped
            # connection as end-of-input and the track simply stops.
            args += ["-reconnect", "1", "-reconnect_streamed", "1",
                     "-reconnect_delay_max", "5"]
            # A default ffmpeg User-Agent gets refused outright by some
            # CDNs - notably the one serving media on the hostless path,
            # where the URL is fetched directly rather than through the
            # tool that negotiated it.
            args += ["-user_agent", STREAM_USER_AGENT]
        if start_seconds > 0:
            # Placed before -i so it seeks by asking for a byte range
            # rather than decoding and discarding everything up to that
            # point - the host answers Range requests, so this is a
            # genuine seek over the network.
            args += ["-ss", f"{start_seconds:.3f}"]
        args += ["-i", self._path, "-vn",
                 "-f", "s16le", "-ar", str(self.sample_rate),
                 "-ac", str(self.channels), "pipe:1"]
        # stderr is kept, not discarded. If ffmpeg can't decode this
        # file the pipe simply closes, which upstream reads as a clean
        # end-of-stream - the track would appear to play and instantly
        # finish, in silence, with nothing logged anywhere. Holding on
        # to stderr is what lets read() explain that instead.
        if self._scope is not None:
            with self._scope:
                self._process = subprocess.Popen(
                    args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        else:
            self._process = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self._produced_any = False

    def _terminate(self):
        if self._process is not None:
            try:
                self._process.kill()
                self._process.stdout.close()
            except Exception:
                pass
            self._process = None

    def read(self):
        if self._process is None or self._process.stdout is None:
            return None
        chunk = self._process.stdout.read(self.READ_SIZE)
        if chunk:
            self._produced_any = True
            return chunk

        # Nothing at all ever came out: this wasn't the end of a track,
        # it was a decode that never started. Say why.
        if not self._produced_any:
            from FreeBodyEngine import warning
            detail = ""
            try:
                detail = (self._process.stderr.read() or b"").decode("utf-8", "replace").strip()
            except Exception:
                pass
            warning(
                f"ffmpeg decoded no audio from {os.path.basename(self._path)} "
                f"- this track will play as silence. {detail or '(no stderr)'}"
            )
            self._produced_any = True  # only complain once per decoder
        return None

    def seek(self, seconds: float):
        self._spawn(max(0.0, seconds))

    def close(self):
        self._terminate()




class StreamingSound(BaseSound):
    """A Sound that decodes as it plays, from a file or a URL.

    Duration is not discovered here. A network source isn't probed (see
    FfmpegDecoder), and phonon takes a track's length from its catalog
    metadata rather than from the audio - so this reports 0.0 and lets
    the caller supply something better."""

    def __init__(self, source: str, manager):
        super().__init__(manager)
        self.manager = manager
        self._out_channels = manager.channels
        self.sample_rate = manager.sample_rate

        self._decoder = FfmpegDecoder(source, self._out_channels, self.sample_rate)

        # Guards the buffer and every call into the decoder - the feeder
        # thread, the audio callback and a seek all reach for these, and
        # a seek respawns the decoder's subprocess underneath the others.
        self._state_lock = threading.Lock()
        self._buffer = np.empty((0, self._out_channels), dtype=np.float32)
        self._eof = False
        self._closed = False
        self._consumed_frames = 0
        # See _feed_loop(): lets a read started before a seek be
        # recognised as stale rather than applied or read as EOF.
        self._generation = 0

        self.start_frame = 0
        self.position = 0
        self.paused = False
        self.stopped = True

        self._feeder = threading.Thread(target=self._feed_loop, daemon=True)
        self._feeder.start()

    # -- decode --------------------------------------------------------------

    def _decode(self, raw):
        """Raw decoder bytes as float32 frames. Pure conversion, so it
        runs outside the lock."""
        pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        usable = (len(pcm) // self._out_channels) * self._out_channels
        return pcm[:usable].reshape(-1, self._out_channels)

    def _feed_loop(self):
        """Decodes ahead of the audio callback, with the lock released
        across the read.

        Holding it there is a realtime bug: get_frames() runs on the
        audio callback and takes the same lock, so a blocking network
        read would stall playback for as long as the network took. The
        generation counter is what makes releasing it safe - a seek
        respawns the decoder, and any read already in flight then
        belongs to a stream nobody is listening to, whose empty return
        would otherwise be mistaken for end-of-input."""
        while not self._closed:
            with self._state_lock:
                buffered = len(self._buffer) / self.sample_rate
                at_eof = self._eof
                generation = self._generation
                decoder = self._decoder

            if at_eof or buffered >= STREAM_LOOKAHEAD_SECONDS:
                time.sleep(0.05)
                continue

            try:
                raw = decoder.read()
            except Exception:
                raw = None

            pcm = self._decode(raw) if raw else None

            with self._state_lock:
                if generation != self._generation:
                    continue  # seeked mid-read - this data is stale
                if pcm is None:
                    self._eof = True
                else:
                    self._buffer = (np.concatenate((self._buffer, pcm), axis=0)
                                    if len(self._buffer) else pcm)

    # -- playback ------------------------------------------------------------

    def get_frames(self, num_frames):
        """Called from the realtime audio callback - pops only what the
        feeder has already decoded, never blocks on I/O."""
        silence = np.zeros((num_frames, self._out_channels), dtype=np.float32)
        if self.paused or self.stopped:
            return silence

        with self._state_lock:
            available = len(self._buffer)
            if available == 0:
                if self._eof:
                    self.stopped = True
                    return silence
                # Underrun: the network hasn't kept up. Silence for this
                # block is the right answer - the alternative is
                # reporting the track finished, which would skip it.
                return silence
            take = min(available, num_frames)
            chunk = self._buffer[:take]
            self._buffer = self._buffer[take:]

        self._consumed_frames += take
        self.position = self._consumed_frames
        self._note_frames_consumed(num_frames)

        if take < num_frames:
            pad = np.zeros((num_frames - take, self._out_channels), dtype=np.float32)
            return np.vstack((chunk, pad))
        return chunk

    def play(self):
        """Starts, or restarts a sound that has already run out.

        The restart matters for loop-track. PlaybackService loops a
        track by calling play() again on the sound that just finished,
        on the understanding that play() rewinds - which the other
        backends do by resetting an index. This one has no index to
        reset: the decoder has reached the end of its input and the
        buffer is empty, so without an explicit seek the sound reports
        finished again on the very next callback. Loop-track on a
        streamed track became a silent spin, re-triggering end-of-track
        every frame and never playing anything.

        Only when it's actually exhausted. A sound that is simply
        stopped but still has a decoder and a buffer - a preloaded one,
        most of all - must not be rewound here, or every track change
        would throw away the buffering done ahead of it.
        """
        with self._state_lock:
            exhausted = self._eof and len(self._buffer) == 0
        if exhausted:
            self.seek(0.0)

        self.stopped = False
        self.paused = False
        self.manager.add_sound(self)

    def pause(self):
        self.paused = True

    def stop(self):
        self.stopped = True
        self.paused = False
        self.manager.remove_sound(self)

    def seek(self, position_s):
        position_s = max(0.0, position_s)
        with self._state_lock:
            self._generation += 1
            self._decoder.seek(position_s)
            self._buffer = np.empty((0, self._out_channels), dtype=np.float32)
            self._eof = False
        self._consumed_frames = int(position_s * self.sample_rate)
        self.position = self._consumed_frames
        self.stopped = False

    @property
    def duration(self):
        return self._decoder.duration

    @property
    def position_s(self):
        return self._interpolated_position_s(self._consumed_frames, self.sample_rate)

    def __del__(self):
        self._closed = True
        try:
            self._decoder.close()
        except Exception:
            pass
