from enum import Enum, auto
from FreeBodyEngine.utils import abstractmethod

class AttachmentType(Enum):
    COLOR = auto()
    DEPTH = auto()
    STENCIL = auto()
    DEPTH_STENCIL = auto()

class AttachmentFormat(Enum):
    R8 = auto()
    RGBA8 = auto()
    RGBA16F = auto()
    RGBA32F = auto()
    RGB10_A2 = auto()

    DEPTH24 = auto()
    DEPTH32F = auto()
    
    STENCIL8 = auto()

    DEPTH24_STENCIL8 = auto()


class Framebuffer:
    def __init__(self, width, height, attachments: dict[str, tuple[AttachmentType, AttachmentFormat]]):
        self.width = width
        self.height = height
        self.attachments = attachments

    @abstractmethod
    def resize(self):
        """Changes the size of the framebuffer."""
        pass

    @abstractmethod
    def draw(self, attachment):
        """Draws the selected attachment to the currently bound framebuffer."""
        pass

    @abstractmethod
    def get_attachment_texture(attachment_name: str):
        pass

    @abstractmethod
    def unbind(self):
        """Unbinds the framebuffer."""

    @abstractmethod
    def bind(self):
        """Binds the framebuffer to allow for drawing."""
        pass
