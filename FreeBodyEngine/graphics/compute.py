"""Backend-agnostic GPU compute dispatch.

On a backend with real hardware compute (a future GL4.4/Vulkan/Metal
generator), a concrete ComputeShader would compile straight to a real compute
shader and issue a real dispatch. GL33 (graphics/gl33/compute.py) has neither,
so it emulates a dispatch as a fullscreen draw through the fixed vertex+
fragment pipeline - one output pixel per invocation, storage buffers read via
buffer textures, results written to float framebuffer attachments. Either
way, code written against this interface doesn't change.
"""
from FreeBodyEngine.utils import abstractmethod
from fbusl.injector import Injector

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import numpy as np
    from FreeBodyEngine.graphics.buffer import Buffer
    from FreeBodyEngine.graphics.texture import Texture


class ComputeShader:
    """Backend-agnostic GPU compute-kernel handle, compiled from FBUSL
    `source`. See the module docstring above for how GL33 emulates
    dispatch() vs. a backend with real hardware compute support."""
    def __init__(self, source, injector: Injector = None):
        """Stores the kernel's FBUSL `source` and `injector`; compiling it
        into a runnable kernel is left to a concrete subclass's
        constructor."""
        self.injector = injector or Injector()
        self.source = source

    @abstractmethod
    def dispatch(self, width: int, height: int):
        """Runs the kernel once per (x, y) in [0, width) x [0, height)."""
        pass

    @abstractmethod
    def bind_buffer(self, name: str, buffer: 'Buffer'):
        """Binds a storage buffer to the `buffer` block declared as `name`."""
        pass

    @abstractmethod
    def set_uniform(self, name: str, value):
        """Sets uniform `name` to `value` for this kernel."""
        pass

    @abstractmethod
    def read_output(self, name: str) -> 'np.ndarray':
        """Synchronous CPU readback of one `@output` field's results."""
        pass

    @abstractmethod
    def get_output_texture(self, name: str) -> 'Texture':
        """Exposes one `@output` field's results as a Texture, for chaining
        into the ordinary rendering/material pipeline without a readback."""
        pass

    @abstractmethod
    def blit_to_screen(self, name: str, size: tuple[int, int] = None):
        """Draws one `@output` field's result directly to the currently
        bound framebuffer - the simplest way to show a result on screen."""
        pass
