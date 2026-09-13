from enum import Enum, auto
from FreeBodyEngine.utils import abstractmethod

class AttachmentType(Enum):
    """What a framebuffer attachment is used for - a sampled color output, or
    a depth/stencil buffer (or combined depth+stencil) that participates in
    depth testing but generally isn't sampled directly."""
    COLOR = auto()
    DEPTH = auto()
    STENCIL = auto()
    DEPTH_STENCIL = auto()

class AttachmentFormat(Enum):
    """GPU pixel formats available for a framebuffer attachment - color
    formats (paired with AttachmentType.COLOR) and depth/stencil formats
    (paired with the corresponding AttachmentType)."""
    R8 = auto()
    RGBA8 = auto()
    RGBA16F = auto()
    RGBA32F = auto()
    RGB10_A2 = auto()

    # Single/dual-channel float formats - compute-emulation outputs (a scalar
    # or vec2 result per invocation) don't need a full RGBA32F attachment.
    R32F = auto()
    RG32F = auto()

    DEPTH24 = auto()
    DEPTH32F = auto()

    STENCIL8 = auto()

    DEPTH24_STENCIL8 = auto()


class Framebuffer:
    """Backend-agnostic render target: a set of named attachments (color/
    depth/stencil, in whatever formats requested) a Renderer can draw into
    instead of the screen - used for G-buffer passes, compute-shader
    emulation (see graphics/compute.py), and offscreen rendering generally."""
    def __init__(self, width, height, attachments: dict[str, tuple[AttachmentType, AttachmentFormat]]):
        """Records the requested `width`/`height`/`attachments` - creating
        the actual GPU-side textures/renderbuffers for them is left to a
        concrete subclass."""
        self.width = width
        self.height = height
        self.attachments = attachments

    @abstractmethod
    def resize(self, size: tuple[int, int]):
        """Changes the size of the framebuffer."""
        pass

    @abstractmethod
    def draw(self, attachment, size: tuple[int,int] = None):
        """Draws the selected attachment to the currently bound framebuffer."""
        pass

    @abstractmethod
    def clear_color_attachment(self, name: str, value: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)):
        """Clears one color attachment to `value`, independent of whatever
        color the last `Renderer.clear()` call used - needed because a
        single `glClearColor`/`glClear(GL_COLOR_BUFFER_BIT)` clears every
        bound draw buffer to the *same* color, which is wrong for a
        G-buffer channel like world position/normal where "nothing was
        rasterized here" needs to be distinguishable from the scene's
        actual background color (e.g. via this channel's alpha, left at 0
        only where a fragment shader never touched it)."""
        pass

    @abstractmethod
    def get_attachment_texture(attachment_name: str):
        """Returns the backend-specific texture object backing the
        `attachment_name` color attachment."""
        pass

    @abstractmethod
    def read(self, attachment_name: str):
        """Reads back one color attachment's pixels as a (height, width,
        channels) float32 array. A synchronous GPU->CPU stall - fine for
        compute-emulation result readback, not for anything per-frame."""
        pass

    @abstractmethod
    def unbind(self):
        """Unbinds the framebuffer."""

    @abstractmethod
    def bind(self):
        """Binds the framebuffer to allow for drawing."""
        pass
