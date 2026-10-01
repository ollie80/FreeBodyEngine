"""Animated GIFs as a texture.

The sibling of graphics/video.py, and deliberately not the same thing.
A video is minutes long, arbitrarily large, and has to be decoded as it
plays; a GIF is a handful of small frames with per-frame delays baked
in, and PIL - already a dependency, already how every other image in
the engine is decoded - reads them without an ffmpeg process. So this
decodes the whole animation up front and then does nothing but pick
which frame to upload, which makes it cheap enough to have several on
screen at once (a wall of animated playlist covers being the case it
was written for).

Both share the stream-texture mechanism underneath: one texture
allocated once, its contents replaced per frame.
"""
import time

from FreeBodyEngine import warning, get_service

# What a GIF with a missing or zero frame delay animates at. GIFs in the
# wild rely on this constantly, and every browser picked the same
# number; matching it is what makes those files look the way their
# author saw them.
_DEFAULT_DELAY_S = 0.1

# A delay nothing honours. Frames below this are intended as "as fast as
# possible" rather than genuinely 100Hz, and drawing them at the file's
# nominal rate would just be a blur - clamped rather than dropped so the
# animation's total length stays roughly right.
_MIN_DELAY_S = 0.02


class GifTexture:
    """Keeps a GPU texture filled with the current frame of a GIF.

    Construct it, call update() once per frame on the main thread, and
    use `.texture` wherever a Texture goes - including as a UI element's
    `image` style, which is what this exists for (pair it with
    UIRenderer.repaint() so the element actually redraws; see
    _resolve_image).
    """

    def __init__(self, path: str, max_size: int | None = None, loop: bool = True):
        self.path = path
        self.loop = loop
        self.texture = None
        self.frames_shown = 0

        self._frames: list[bytes] = []
        self._delays: list[float] = []
        self._index = -1
        self._started_at = time.monotonic()

        decoded = self._decode(path, max_size)
        if decoded is None:
            return
        self.width, self.height = decoded

        manager = self._texture_manager()
        if manager is None or not hasattr(manager, "create_stream_texture"):
            warning("GifTexture: this renderer has no stream textures - no animation.")
            self._frames = []
            return
        self.texture = manager.create_stream_texture(self.width, self.height, 4)

    @staticmethod
    def _texture_manager():
        renderer = get_service("graphics_renderer") or get_service("renderer")
        if renderer is None:
            pipeline = get_service("graphics")
            renderer = getattr(pipeline, "renderer", None)
        return getattr(renderer, "texture_manager", None)

    # -- decoding -------------------------------------------------------------

    def _decode(self, path: str, max_size: int | None):
        """Reads every frame to raw RGBA bytes, once.

        Frames are composited by converting each one through RGBA rather
        than taking its raw palette data: a GIF frame is routinely a
        partial update of the one before it (that's most of how the
        format stays small), and PIL's seek() already applies that
        composition for us. Taking `.tobytes()` off the palette image
        instead would show the disposal artefacts the format is full of.

        Flipped both ways to match _create_standalone_texture, which is
        the orientation every other image in the UI is drawn at - the
        shader's own UVs are what make that the right answer, so a
        texture that doesn't match it appears upside down next to one
        that does.
        """
        try:
            from PIL import Image, ImageSequence
        except ImportError:
            warning("GifTexture: PIL is not available - no animation.")
            return None

        try:
            image = Image.open(path)
        except Exception as error:
            warning(f"GifTexture: could not open {path!r} ({error}).")
            return None

        width, height = image.size
        if max_size and max(width, height) > max_size:
            scale = max_size / max(width, height)
            width = max(1, round(width * scale))
            height = max(1, round(height * scale))

        for frame in ImageSequence.Iterator(image):
            delay = frame.info.get("duration", 0) / 1000.0 or _DEFAULT_DELAY_S
            converted = frame.convert("RGBA")
            if (converted.width, converted.height) != (width, height):
                converted = converted.resize((width, height), Image.Resampling.LANCZOS)
            converted = converted.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            converted = converted.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            self._frames.append(converted.tobytes())
            self._delays.append(max(_MIN_DELAY_S, delay))

        if not self._frames:
            warning(f"GifTexture: {path!r} has no frames.")
            return None
        return width, height

    # -- consuming ------------------------------------------------------------

    @property
    def duration(self) -> float:
        return sum(self._delays)

    def _frame_at(self, elapsed: float) -> int:
        """Which frame `elapsed` seconds in. Walks the delays rather than
        dividing: GIF frame delays are per-frame and routinely uneven
        (a long held pose then six fast ones), so there is no single
        frame duration to divide by."""
        total = self.duration
        if total <= 0:
            return 0
        if elapsed >= total and not self.loop:
            return len(self._frames) - 1
        elapsed %= total

        for index, delay in enumerate(self._delays):
            elapsed -= delay
            if elapsed < 0:
                return index
        return len(self._frames) - 1

    def update(self) -> bool:
        """Uploads the frame this moment calls for, if it isn't already
        up.

        Main thread only - it touches GL. Returns whether the texture
        changed, which is the signal a caller wants for whether to ask
        the UI to repaint: for most of a 10fps GIF's frames at 60Hz the
        answer is no, and repainting anyway would throw away the whole
        point of the UI's damage tracking.
        """
        if self.texture is None or not self._frames:
            return False

        index = self._frame_at(time.monotonic() - self._started_at)
        if index == self._index:
            return False

        manager = self._texture_manager()
        if manager is None:
            return False
        if not manager.update_stream_texture(self.texture.id, self._frames[index]):
            return False

        self._index = index
        self.frames_shown += 1
        return True

    def restart(self):
        self._started_at = time.monotonic()
        self._index = -1

    def close(self):
        """Frees the GPU texture and the decoded frames.

        Worth calling rather than leaving to garbage collection: the
        frames are raw RGBA, so a few dozen small covers held past their
        usefulness is tens of megabytes."""
        if self.texture is not None:
            manager = self._texture_manager()
            if manager is not None and hasattr(manager, "delete_stream_texture"):
                manager.delete_stream_texture(self.texture.id)
            self.texture = None
        self._frames = []
        self._delays = []
