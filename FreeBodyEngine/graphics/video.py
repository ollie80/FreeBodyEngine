"""Video decoded to a texture.

Deliberately minimal. This decodes a file to RGB frames and keeps a GPU
texture filled with the newest one - no audio, no playback controls, no
format negotiation. Anything that wants video *and* sound plays the
sound separately; keeping them apart is what removes the entire
synchronisation problem, and the one caller this was written for
(phonon's visualizer) is already playing different audio to the video
it's showing.

The decoding reuses the ffmpeg plumbing in audio/streaming.py rather
than restating it: finding the binary, and the LD_LIBRARY_PATH dance
Android's bundled build needs, are ffmpeg problems rather than audio
ones, and both took real debugging to get right. They stay where they
are until something other than these two needs them.

Frames are *dropped* rather than queued when the consumer falls
behind. That's the opposite of the audio decoder next door, where a
dropped buffer is an audible gap - here the consumer is the render
loop, and a stale frame for one frame is invisible while a stall is
not.
"""
import subprocess
import threading
from collections import deque

from FreeBodyEngine import warning, get_service
from FreeBodyEngine.audio.streaming import _android_bin, _ffmpeg_library_path

# How many decoded frames to hold. Two: one being shown, one ready.
# Any more is latency rather than smoothness, and frames are large
# enough that a deep queue is real memory.
_QUEUE_DEPTH = 2


class VideoTexture:
    """Keeps a GPU texture filled with the current frame of a video.

    Construct it, call update() once per frame on the main thread, and
    use `.texture` wherever a Texture goes.
    """

    def __init__(self, path: str, size: tuple[int, int] = (256, 144),
                 fps: int = 12, loop: bool = True):
        self.path = path
        self.width, self.height = size
        self.fps = fps
        self.loop = loop
        self.frame_bytes = self.width * self.height * 3

        self._frames: deque = deque(maxlen=_QUEUE_DEPTH)
        self._lock = threading.Lock()
        self._closed = False
        self._process = None
        self._generation = 0
        self.texture = None
        self.frames_shown = 0

        manager = self._texture_manager()
        if manager is None or not hasattr(manager, "create_stream_texture"):
            warning("VideoTexture: this renderer has no stream textures - no video.")
            return

        self.texture = manager.create_stream_texture(self.width, self.height, 3)
        self._spawn(0.0)
        self._feeder = threading.Thread(target=self._feed, daemon=True)
        self._feeder.start()

    @staticmethod
    def _texture_manager():
        renderer = get_service("graphics_renderer") or get_service("renderer")
        if renderer is None:
            pipeline = get_service("graphics")
            renderer = getattr(pipeline, "renderer", None)
        return getattr(renderer, "texture_manager", None)

    # -- decoding -------------------------------------------------------------

    def _spawn(self, start_seconds: float):
        """Starts ffmpeg producing raw frames at exactly our size.

        Both dimensions are forced, and the source is scaled up to cover
        and then cropped. rawvideo carries no framing - a reader takes
        exactly width*height*3 bytes per frame - so the size has to be
        known rather than discovered, and forcing it here avoids a
        separate ffprobe just to learn the aspect ratio. Cropping to
        fill is also what a full-frame backdrop wants; letterbox bars
        would have to be dealt with by every caller instead.

        vflip because GL textures are bottom-up. ffmpeg does it for
        free in the same filter chain; doing it in Python would be a
        copy per frame forever.
        """
        self._terminate()
        binary = _android_bin("ffmpeg") or "ffmpeg"
        scope = _ffmpeg_library_path(binary) if _android_bin("ffmpeg") else None

        # -re paces the decode to the video's own timeline. Without it
        # ffmpeg decodes as fast as the pipe drains, which with a
        # two-frame queue is as fast as the CPU goes: the video plays
        # several times too fast *and* burns a core doing it. Pacing in
        # update() instead would mean the same wasted decoding with the
        # extra frames thrown away.
        args = [binary, "-v", "error", "-re"]
        if self.loop:
            # Songs outrun their videos routinely - they are different
            # uploads of different lengths. Looping costs nothing and
            # beats freezing on a final frame.
            args += ["-stream_loop", "-1"]
        if start_seconds > 0:
            args += ["-ss", f"{start_seconds:.3f}"]
        args += [
            "-i", self.path, "-an",
            "-vf", (f"scale={self.width}:{self.height}:force_original_aspect_ratio=increase,"
                    f"crop={self.width}:{self.height},vflip"),
            "-r", str(self.fps),
            "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
        ]
        try:
            if scope is not None:
                with scope:
                    self._process = subprocess.Popen(
                        args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            else:
                self._process = subprocess.Popen(
                    args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except FileNotFoundError:
            warning("VideoTexture: ffmpeg not found - no video.")
            self._process = None

    def _terminate(self):
        if self._process is not None:
            try:
                self._process.kill()
                if self._process.stdout is not None:
                    self._process.stdout.close()
            except Exception:
                pass
            self._process = None

    def _feed(self):
        """Reads whole frames, with the lock released across the read.

        The read blocks on a pipe, and update() takes the same lock from
        the render loop - holding it across I/O would stall drawing for
        as long as the decoder took. The generation counter is what lets
        a read that was already in flight when a seek respawned the
        process be recognised and dropped, instead of a frame from the
        old position appearing after the new one.
        """
        while not self._closed:
            with self._lock:
                generation = self._generation
                process = self._process
            if process is None or process.stdout is None:
                return

            try:
                data = process.stdout.read(self.frame_bytes)
            except Exception:
                data = None

            if not data or len(data) != self.frame_bytes:
                with self._lock:
                    if generation == self._generation:
                        self._process = None
                return  # end of stream (or a short final read)

            with self._lock:
                if generation != self._generation:
                    continue  # seeked mid-read; this frame is from the old position
                self._frames.append(data)

    # -- consuming ------------------------------------------------------------

    def update(self) -> bool:
        """Uploads the newest decoded frame, if there is one.

        Main thread only - it touches GL. Returns whether anything was
        uploaded, so a caller can tell a still video from a stopped one.
        """
        if self.texture is None:
            return False
        with self._lock:
            frame = self._frames.pop() if self._frames else None
            self._frames.clear()  # anything older is already stale
        if frame is None:
            return False

        manager = self._texture_manager()
        if manager is None:
            return False
        if manager.update_stream_texture(self.texture.id, frame):
            self.frames_shown += 1
            return True
        return False

    def seek(self, seconds: float):
        """Restarts decoding from `seconds`.

        Respawns the process, which is not cheap - this is for jumping
        somewhere, not for tracking a position. A caller that wants to
        follow along should start at roughly the right place once and
        let it run.
        """
        with self._lock:
            self._generation += 1
            self._frames.clear()
        self._spawn(max(0.0, seconds))
        if not self._closed and (not hasattr(self, "_feeder") or not self._feeder.is_alive()):
            self._feeder = threading.Thread(target=self._feed, daemon=True)
            self._feeder.start()

    @property
    def running(self) -> bool:
        return self._process is not None and not self._closed

    def close(self):
        self._closed = True
        self._terminate()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
