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
from FreeBodyEngine.graphics.material import BlendMode
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
    """One queued draw, recorded via Renderer.submit() and issued later by
    Renderer.flush() rather than immediately - this indirection is what lets
    flush() sort/group calls (by blend mode for correct transparency, and by
    material/mesh to cut redundant state changes) instead of drawing in
    whatever order the scene tree happened to be walked."""
    mesh: 'Mesh'
    transform: 'Transform'
    material: 'Material'
    camera: 'Camera'

    @property
    def blend_mode(self) -> BlendMode:
        return self.material.blend_mode

    def camera_distance(self) -> float:
        """Squared distance from the camera to this call's world position -
        used to sort transparent calls back-to-front. Squared (not sqrt'd)
        since only the relative order matters, not the actual distance."""
        pos = self.transform.position
        cam_pos = self.camera.world_transform.position
        dx = pos.x - cam_pos.x
        dy = pos.y - cam_pos.y
        dz = getattr(pos, 'z', 0.0) - getattr(cam_pos, 'z', 0.0)
        return dx * dx + dy * dy + dz * dz

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
        self._current_blend_mode: BlendMode = BlendMode.OPAQUE


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

    def submit(self, mesh: 'Mesh', material: 'Material', transform: 'Transform', camera: 'Camera'):
        """Queues a draw instead of issuing it immediately - see
        flush_opaque()/flush_transparent()."""
        self.calls.append(Call(mesh, transform, material, camera))

    def flush_opaque(self):
        """Draws and dequeues every OPAQUE/ADDITIVE Call currently queued
        (leaving any TRANSPARENT ones queued - see flush_transparent()),
        grouped by (material, mesh) - via graphics.instancing.
        group_by_state() - purely to cut redundant glUseProgram/uniform/
        texture-bind churn between consecutive draws that share a material
        (state-minimizing batching, not GPU instancing - see
        graphics/instancing.py's module docstring for why real
        per-instance-transform instancing isn't part of this). Drawn with
        depth testing/writing on; ADDITIVE still writes depth (e.g. a glow
        effect should still occlude/be occluded) while blending
        additively, unlike TRANSPARENT.

        Split from flush_transparent() (rather than one combined flush())
        because a deferred pipeline needs a framebuffer rebind between the
        two - see PBRPipeline.draw(): opaque calls render into the
        multi-attachment G-buffer, and only after that pipeline's own
        lighting composite pass runs do transparent calls get drawn,
        forward-shaded onto the composite's single 'lit' output.
        """
        from FreeBodyEngine.graphics.instancing import group_by_state

        opaque = [c for c in self.calls if c.blend_mode in (BlendMode.OPAQUE, BlendMode.ADDITIVE)]
        self.calls = [c for c in self.calls if c.blend_mode == BlendMode.TRANSPARENT]

        for group in group_by_state(opaque):
            mode = group[0].blend_mode
            self.set_blend_mode(mode)
            for call in group:
                self._draw_call(call)

        self.set_blend_mode(BlendMode.OPAQUE)

    def flush_transparent(self):
        """Draws and dequeues every TRANSPARENT Call currently queued,
        individually (no state-minimizing grouping - see flush_opaque()),
        sorted back-to-front by camera distance (the only order that
        composites correctly without per-pixel order-independent blending),
        with alpha blending on and depth *testing* on but depth *writing*
        off, so transparent objects don't occlude each other incorrectly or
        block opaque geometry drawn earlier."""
        transparent = [c for c in self.calls if c.blend_mode == BlendMode.TRANSPARENT]
        self.calls = [c for c in self.calls if c.blend_mode != BlendMode.TRANSPARENT]

        transparent.sort(key=lambda c: c.camera_distance(), reverse=True)
        if transparent:
            self.set_blend_mode(BlendMode.TRANSPARENT)
            for call in transparent:
                self._draw_call(call)
            self.set_blend_mode(BlendMode.OPAQUE)

    def _draw_call(self, call: Call):
        """Sets `call.material`'s model/view/proj uniforms from
        `call.transform`/`call.camera` and draws `call.mesh` - the actual
        per-call work flush() drives once calls are grouped/sorted."""
        call.material.shader['model'] = call.transform.model
        call.material.shader['view'] = call.camera.view_matrix
        call.material.shader['proj'] = call.camera.proj_matrix
        self.draw_mesh(call.mesh, call.material)

    @abstractmethod
    def set_blend_mode(self, mode: BlendMode):
        """Configures blending for subsequent draws: OPAQUE disables
        blending entirely (and enables depth writes), TRANSPARENT enables
        standard alpha blending with depth writes off (but depth testing
        still on), ADDITIVE enables additive blending with depth writes on.
        Called by flush() between groups, so a backend only needs to change
        actual GL state when `mode` differs from what's already active."""
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
    def draw_mesh_instanced(self, mesh: 'Mesh', material: 'Material', model_matrices: np.ndarray, camera: 'Camera'):
        """Draws len(model_matrices) copies of `mesh` in a single GPU
        instanced draw call, one per row of `model_matrices` (shape
        (N, 4, 4)), using `material`. Not currently wired into flush()'s
        automatic batching - see graphics/instancing.py's module docstring
        for why. Real infrastructure for a caller that wants to submit
        genuine GPU instancing explicitly."""
        pass

    @abstractmethod
    def draw_mesh(self, mesh: 'Mesh', material: 'Material'):
        """Draws `mesh` once, using `material`'s currently bound shader and uniforms."""
        pass

    def set_scissor(self, x: int, y: int, width: int, height: int):
        """Restricts drawing to the (x, y, width, height) rectangle - top-
        left origin, Y-down pixels, matching ui/renderer.py's own screen-
        space convention - until the next set_scissor()/clear_scissor().
        Concrete no-op default: a backend that doesn't override this (e.g.
        DummyRenderer) just draws unclipped rather than raising, since
        unclipped drawing is a correctness-preserving fallback (UIRenderer's
        scroll-container clipping is a visual nicety, not something other
        engine code depends on) - GL33Renderer/GL44Renderer override it
        with a real glScissor."""
        pass

    def clear_scissor(self):
        """Undoes set_scissor(), restoring unclipped drawing. See
        set_scissor()'s docstring for why this defaults to a no-op."""
        pass

    def enable_depth_testing(self):
        """Enables GL_DEPTH_TEST (GL33Renderer/GL44Renderer). Concrete
        no-op default so calling this is always safe regardless of
        backend, matching set_scissor()'s reasoning."""
        pass

    def disable_depth_testing(self):
        """Disables GL_DEPTH_TEST (GL33Renderer/GL44Renderer). UIRenderer
        calls this before drawing every frame - see its own comment for
        why a 2D UI overlay can't share the 3D pipeline's depth-test state."""
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
