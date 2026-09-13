from typing import TYPE_CHECKING
from FreeBodyEngine.utils import abstractmethod
from fbusl.injector import Injector 
from FreeBodyEngine import register_event_callback, unregister_event_callback
from FreeBodyEngine.core.window import FRAMEBUFFER_RESIZE

from dataclasses import dataclass


from FreeBodyEngine.graphics.image import Image
from FreeBodyEngine.graphics.buffer import Buffer
from FreeBodyEngine.graphics.mesh import Mesh
from FreeBodyEngine.graphics.framebuffer import AttachmentFormat, AttachmentType, Framebuffer
from FreeBodyEngine.graphics.texture import TextureManager, Texture
import numpy as np
from FreeBodyEngine.core.service import Service


if TYPE_CHECKING:
    from FreeBodyEngine.core.main import Main
    from FreeBodyEngine.graphics.material import Material
    from FreeBodyEngine.graphics.color import Color
    from FreeBodyEngine.core.camera import Camera2D, Camera
    from FreeBodyEngine.graphics.model.model import Model
    from FreeBodyEngine.math import Vector, Transform


@dataclass
class Call:
    """The parameters of a single draw call, bundled together so a call can
    be recorded and issued separately from where it's built."""
    mesh: 'Mesh'
    transform: 'Transform'
    material: 'Material'
    use_camera: bool
    camera: 'Camera'
    is_instanced: bool
    instances: int

class Renderer(Service):
    """Abstract base class for a graphics backend (GL33Renderer, GL44Renderer,
    DummyRenderer, ...). Registers itself as the 'renderer' service and
    defines the low-level resource-creation/drawing API a GraphicsPipeline
    drives to actually produce a frame; concrete subclasses fill in every
    `@abstractmethod` below for their own API (OpenGL, ...).
    """
    def __init__(self):
        """Registers as the 'renderer' service and creates the shared texture manager."""
        super().__init__('renderer')
        self.texture_manager = TextureManager()
        self.calls: list[Call] = []


    def on_initialize(self):
        """Subscribes resize() to the FRAMEBUFFER_RESIZE event, so every backend's viewport/surface stays in sync with the window without wiring this up itself."""
        register_event_callback(FRAMEBUFFER_RESIZE, self.resize)

    def on_destroy(self):
        """Unsubscribes resize() from the FRAMEBUFFER_RESIZE event."""
        unregister_event_callback(FRAMEBUFFER_RESIZE, self.resize)

    @abstractmethod
    def get_mesh_class(self) -> type[Mesh]:
        """Returns this backend's Mesh subclass, for code that needs to construct a mesh generically (e.g. mesh.create_static_mesh())."""
        pass

    @abstractmethod
    def get_image_class(self) -> type[Image]:
        """Returns this backend's Image subclass."""
        pass

    @abstractmethod
    def load_image(self, texture: 'Texture'):
        """Uploads `texture` to the GPU and returns a backend-specific Image wrapping it."""
        pass

    @abstractmethod
    def load_image_from_atlas(self, data):
        """Loads an Image from a pre-baked texture atlas entry."""
        pass

    @abstractmethod
    def load_material(self, data):
        """Builds a backend-specific Material from `data` (e.g. a parsed .fbmat file)."""
        pass

    @abstractmethod
    def load_shader(self, vertex, fragment, injector: Injector = Injector, geometry=None):
        """Compiles `vertex`/`fragment` (and optional `geometry`) FBUSL source into a backend-specific Shader, using `injector` to resolve engine-provided builtins."""
        pass

    @abstractmethod
    def create_buffer(self, data: np.ndarray) -> Buffer:
        """Creates a backend-specific Buffer already initialized with `data`."""
        pass

    @abstractmethod
    def get_max_buffer_size(self) -> int:
        """Returns the largest size, in bytes, this backend's buffer type can hold."""
        pass

    @property
    @abstractmethod
    def create_framebuffer(self) -> type[Framebuffer]:
        """Returns this backend's Framebuffer subclass (the class itself, not an instance - callers construct it themselves, passing their own width/height/attachments)."""
        pass

    @abstractmethod
    def clear(self, color: 'Color'):
        """Clears the currently bound framebuffer's color (and depth) buffers to `color`."""
        pass

    @abstractmethod
    def destroy(self):
        """Releases the backend's GPU context and resources."""
        pass

    @abstractmethod
    def resize(self, size: tuple[int, int]):
        """Updates the backend's viewport/surface to match the new framebuffer `size` (pixels). Called automatically on FRAMEBUFFER_RESIZE - see on_initialize()."""
        pass

    @abstractmethod
    def draw_line(self, start: tuple[float, float], end: tuple[float, float], width: float, color: 'Color'):
        """
        Draws a line between the first and second point.
        
        :param start: The starting point.
        :type start: tuple[float, float]
        :param end: The end point.
        :type end: tuple[float, float]
        :param width: The thickness of the line.
        :type width: float
        """
        pass

    @abstractmethod
    def draw_mesh_instanced(self, mesh: 'Mesh', instances: int, material: 'Material'):
        """Draws `instances` copies of `mesh` in a single instanced draw call, using `material`."""
        pass

    @abstractmethod
    def draw_mesh(self, mesh: 'Mesh', material: 'Material'):
        """Draws `mesh` once, using `material`'s currently bound shader and uniforms."""
        pass

    def draw_model(self, model: 'Model', transform: 'Transform', camera: 'Camera2D'):
        """Draws every sub-mesh of `model`, setting each one's mapped material's
        model/view/proj uniforms from `transform`/`camera` before delegating to
        draw_mesh() - the one piece of multi-mesh draw logic shared by every
        backend, so it lives here instead of being reimplemented per-renderer."""
        for mesh_name in model.meshes:
            mesh = model.meshes[mesh_name]

            material_name = model.material_map[mesh_name]
            material = model.materials[material_name]
            material.shader['model'] = transform.model
            material.shader['view'] = camera.view_matrix
            material.shader['proj'] = camera.proj_matrix

            self.draw_mesh(mesh, material)
    
    @abstractmethod
    def draw_circle(self, radius: float, position: tuple[float, float], color: 'Color'):
        """
        Draws a filled circle at the position.

        :param start: The center of the circle (NDC).
        :type start: tuple[float, float]
        :param radius: The radius of the circle (NDC).
        :type radius: float
        """
        pass
