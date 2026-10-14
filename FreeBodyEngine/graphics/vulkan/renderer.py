"""VulkanRenderer - the 'renderer' service on Vulkan: the full Renderer
interface (meshes, materials, framebuffers, textures, text and UI through
their usual engine paths) plus compute/raytrace work with hardware ray
tracing (compute.py).

How GL's immediate-mode model maps onto Vulkan here:

  * A frame is one command buffer, opened by the first thing that needs
    the GPU and submitted at the end of the frame (UpdatePhase.LATE).
  * The "bound framebuffer" is a target - the window's own color+depth
    images, or a VulkanFramebuffer. Rendering into it begins lazily at
    the first draw/clear and ends whenever the target, its draw buffers,
    or an image's layout has to change.
  * A draw snapshots the current shader's uniform bytes into a per-frame
    ring buffer and its textures into a descriptor set, so setting
    uniforms between draws behaves as it does in GL.
  * Pipelines are built on demand and cached by shader, vertex layout,
    topology, blend mode, depth state and target formats.
  * Anything that has to see finished results mid-frame (a readback, an
    upload into a texture this frame already uses) submits what's been
    recorded so far and waits, then carries on in a fresh command buffer.

Everything keeps OpenGL's conventions - clip space, bottom-left memory
origin, uploads flipped as GL44 flips them - so engine and project code
written for GL renders identically. The one flip happens when the
window's image is copied to the swapchain at the end of the frame.
"""
import numpy as np
import vulkan as vk

from FreeBodyEngine import get_service, service_exists, register_service_update, unregister_service_update, warning
from FreeBodyEngine.core.update import UpdatePhase
from FreeBodyEngine.graphics.renderer import Renderer
from FreeBodyEngine.graphics.material import BlendMode
from FreeBodyEngine.graphics.texture import Texture, TextureStack
from FreeBodyEngine.graphics.vulkan.context import VulkanContext, Buffer
from FreeBodyEngine.graphics.vulkan.swapchain import Presenter
from FreeBodyEngine.graphics.vulkan.image import GpuImage, VulkanImage, FORMAT_INFO
from FreeBodyEngine.graphics.vulkan.mesh import VulkanMesh
from FreeBodyEngine.graphics.vulkan.framebuffer import VulkanFramebuffer
from FreeBodyEngine.graphics.vulkan.texture import VulkanTextureManager, SAMPLED
from FreeBodyEngine.graphics.vulkan.shader import VulkanShader

UINT64_MAX = 0xFFFFFFFFFFFFFFFF
COLOR_ATTACHMENT = vk.VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL
DEPTH_ATTACHMENT = vk.VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL
SHADER_READ = vk.VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL
TRANSFER_SRC = vk.VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL
TRANSFER_DST = vk.VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL
UNIFORM_RING_SIZE = 32 * 1024 * 1024
VERTEX_RING_SIZE = 16 * 1024 * 1024
INSTANCE_FORMAT = vk.VK_FORMAT_R32G32B32A32_SFLOAT
FLOAT_FORMATS = {1: vk.VK_FORMAT_R32_SFLOAT, 2: vk.VK_FORMAT_R32G32_SFLOAT, 3: vk.VK_FORMAT_R32G32B32_SFLOAT,
                 4: vk.VK_FORMAT_R32G32B32A32_SFLOAT}  # instance inputs are vec4s (UI rects, matrix columns)


class _WindowTarget:
    """The window's own color and depth images - what GL calls
    framebuffer 0. Presented by copying (and flipping) to the swapchain."""
    draw_buffers = ["color"]

    def __init__(self, ctx, size):
        self.width, self.height = max(size[0], 1), max(size[1], 1)
        self.color = GpuImage(ctx, self.width, self.height, vk.VK_FORMAT_R8G8B8A8_UNORM,
                              vk.VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | SAMPLED)
        self.depth = GpuImage(ctx, self.width, self.height, vk.VK_FORMAT_D32_SFLOAT,
                              vk.VK_IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT)

    def render_targets(self):
        return [self.color]

    def depth_target(self):
        return self.depth


class _Ring:
    """A per-frame bump allocator in one host-visible buffer."""

    def __init__(self, ctx, size, usage, alignment):
        self.buffer = Buffer(ctx, size, usage)
        self.size, self.alignment, self.offset = size, max(int(alignment), 4), 0

    def alloc(self, data: bytes):
        offset = -(-self.offset // self.alignment) * self.alignment
        if offset + len(data) > self.size:
            return None
        self.buffer.write(data, offset)
        self.offset = offset + len(data)
        return offset


class _Transient:
    """Vertex data that lives in the frame's vertex ring for one draw
    (lines). _draw() places it, along with the draw's other ring data."""

    def __init__(self, ring, data, fmt, stride, count, topology):
        self.ring, self.data, self.offset = ring, data, 0
        self.formats = [(fmt, stride)]
        self.vertex_count, self.index_stream, self.topology = count, None, topology

    def stream_buffers(self):
        return [self.ring.buffer]

    def stream_offsets(self):
        return [self.offset]


def _not_supported(name):
    def method(self, *args, **kwargs):
        raise NotImplementedError(f"VulkanRenderer.{name}() isn't implemented yet.")
    method.__name__ = name
    return method


class VulkanRenderer(Renderer):
    def __init__(self, vsync: bool = True):
        super().__init__()
        self.vsync = vsync
        self.mesh_class = VulkanMesh
        self.ctx = None
        self.window = None
        self.presenter = None
        self.frame_index = 0
        self.current_shader = None
        self.line_shader = None
        self.target = None  # None means the window
        self.viewport = (1, 1)
        self.scissor = None
        self.depth_test = False
        self.total_draw_calls = 0
        self.last_gpu_ms = None
        self._frame_gpu_ns = 0.0
        self._frame_timed = False
        self._frame_active = False
        self._rendering_key = None
        self._rendering_formats = ((), vk.VK_FORMAT_UNDEFINED)
        self._pipelines: dict = {}
        self._descriptor_cache: dict = {}
        self._deferred: list = []
        self._flush_count = 0

    # == lifecycle ============================================================

    def on_initialize(self):
        super().on_initialize()
        if service_exists("window"):
            self.window = get_service("window")
            if not getattr(self.window, "vulkan", False):
                raise RuntimeError(
                    "VulkanRenderer needs a GLFW window created without an OpenGL context - this "
                    "window was made for OpenGL. Use fb.core.window.get_window() and "
                    "fb.graphics.get_renderer() together (they agree via fb.graphics.use_vulkan()), "
                    "and set FORCE_RENDERER, if at all, before creating the window.")
            self.ctx = VulkanContext(self.window._window)
            size = self.window.framebuffer_size
            self.presenter = Presenter(self.ctx, size, self.vsync)
        else:
            self.ctx = VulkanContext()
            size = (1, 1)
        ctx = self.ctx
        self.window_target = _WindowTarget(ctx, size)
        self.viewport = self.window_target.width, self.window_target.height
        self.texture_manager = VulkanTextureManager(ctx)
        self.cmd = vk.vkAllocateCommandBuffers(ctx.device, vk.VkCommandBufferAllocateInfo(
            commandPool=ctx.command_pool, level=vk.VK_COMMAND_BUFFER_LEVEL_PRIMARY, commandBufferCount=1))[0]
        self.fence = vk.vkCreateFence(ctx.device, vk.VkFenceCreateInfo(), None)
        pool_sizes = [
            vk.VkDescriptorPoolSize(type=vk.VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER_DYNAMIC, descriptorCount=8192),
            vk.VkDescriptorPoolSize(type=vk.VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, descriptorCount=32768),
            vk.VkDescriptorPoolSize(type=vk.VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, descriptorCount=16384)]
        self.descriptor_pool = vk.vkCreateDescriptorPool(ctx.device, vk.VkDescriptorPoolCreateInfo(
            maxSets=8192, poolSizeCount=len(pool_sizes), pPoolSizes=pool_sizes), None)
        limits = ctx.limits
        self.uniform_ring = _Ring(ctx, UNIFORM_RING_SIZE, vk.VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT,
                                  limits.minUniformBufferOffsetAlignment)
        self.vertex_ring = _Ring(ctx, VERTEX_RING_SIZE, vk.VK_BUFFER_USAGE_VERTEX_BUFFER_BIT, 16)
        # Bound to storage-buffer bindings with nothing to read (an
        # emulated geometry stage's index buffer, for an unindexed mesh).
        self._empty_storage = Buffer(ctx, 16, vk.VK_BUFFER_USAGE_STORAGE_BUFFER_BIT)
        self._white = GpuImage(ctx, 1, 1, vk.VK_FORMAT_R8G8B8A8_UNORM, SAMPLED)
        self._white.upload(b"\xff\xff\xff\xff")
        self._white_array = GpuImage(ctx, 1, 1, vk.VK_FORMAT_R8G8B8A8_UNORM, SAMPLED, array_view=True)
        self._white_array.upload(b"\xff\xff\xff\xff")
        register_service_update(UpdatePhase.LATE, self.present, priority=1000)

    def on_destroy(self):
        unregister_service_update(UpdatePhase.LATE, self.present)
        super().on_destroy()
        if self.ctx is None:
            return
        ctx = self.ctx
        ctx.wait_idle()
        self._frame_active = False
        self._run_deferred()
        for pipeline in self._pipelines.values():
            vk.vkDestroyPipeline(ctx.device, pipeline, None)
        self.texture_manager.destroy()
        for image in (self._white, self._white_array, self.window_target.color, self.window_target.depth):
            image.destroy()
        self.uniform_ring.buffer.destroy()
        self.vertex_ring.buffer.destroy()
        self._empty_storage.destroy()
        vk.vkDestroyDescriptorPool(ctx.device, self.descriptor_pool, None)
        vk.vkDestroyFence(ctx.device, self.fence, None)
        if self.presenter is not None:
            self.presenter.destroy()
        ctx.destroy()
        self.ctx = None

    def destroy(self):
        self.on_destroy()

    @property
    def device_name(self) -> str:
        return self.ctx.device_name

    def defer_destroy(self, obj):
        """Destroys `obj` once no recorded command can still be using it."""
        if self._frame_active:
            self._deferred.append(obj)
        else:
            obj.destroy()

    def _run_deferred(self):
        deferred, self._deferred = self._deferred, []
        for obj in deferred:
            obj.destroy()

    # == the frame ============================================================

    def _ensure_frame(self):
        if self._frame_active:
            return self.cmd
        self.frame_index += 1
        self._begin_cmd()
        self._frame_active = True
        return self.cmd

    def _begin_cmd(self):
        vk.vkResetCommandBuffer(self.cmd, 0)
        vk.vkBeginCommandBuffer(self.cmd, vk.VkCommandBufferBeginInfo(
            flags=vk.VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT))
        vk.vkResetDescriptorPool(self.ctx.device, self.descriptor_pool, 0)
        self._descriptor_cache.clear()
        self.uniform_ring.offset = 0
        self.vertex_ring.offset = 0
        self.ctx.gpu_timer.begin(self.cmd)

    def _submit_and_wait(self):
        ctx = self.ctx
        ctx.gpu_timer.end(self.cmd)
        vk.vkEndCommandBuffer(self.cmd)
        vk.vkQueueSubmit(ctx.queue, 1, [vk.VkSubmitInfo(commandBufferCount=1, pCommandBuffers=[self.cmd])],
                         self.fence)
        vk.vkWaitForFences(ctx.device, 1, [self.fence], vk.VK_TRUE, UINT64_MAX)
        vk.vkResetFences(ctx.device, 1, [self.fence])
        self._note_frame_time()

    def _note_frame_time(self):
        ns = self.ctx.gpu_timer.read()
        if ns is not None:
            self._frame_gpu_ns += ns
            self._frame_timed = True

    def flush(self):
        """Submits everything recorded so far and waits for it, keeping the
        frame open - for work that must see finished results now."""
        if not self._frame_active:
            return
        self._end_rendering()
        self._submit_and_wait()
        self._run_deferred()
        self._begin_cmd()
        self._flush_count += 1

    def before_upload(self, image):
        """Called before a CPU upload into an existing texture: anything
        already recorded this frame runs first, as it would have in GL."""
        self.flush()

    def present(self):
        """UpdatePhase.LATE: finishes the frame and shows the window image."""
        if not self._frame_active:
            return
        cmd = self._ensure_frame()
        self._end_rendering()
        win = self.window_target

        index = self.presenter.acquire(self.window.framebuffer_size) if self.presenter is not None else None
        if index is None:
            self._submit_and_wait()
        else:
            target = self.presenter.images[index]
            win.color.transition(cmd, TRANSFER_SRC)
            self.ctx.image_barrier(cmd, target, vk.VK_IMAGE_LAYOUT_UNDEFINED, TRANSFER_DST, 0,
                                   vk.VK_ACCESS_TRANSFER_WRITE_BIT, vk.VK_PIPELINE_STAGE_TRANSFER_BIT,
                                   vk.VK_PIPELINE_STAGE_TRANSFER_BIT)
            w, h = self.presenter.extent
            # The one flip: memory row 0 is the bottom here, and the top on
            # a swapchain image.
            blit = vk.VkImageBlit(
                srcSubresource=self.ctx.color_layers(),
                srcOffsets=[vk.VkOffset3D(0, win.height, 0), vk.VkOffset3D(win.width, 0, 1)],
                dstSubresource=self.ctx.color_layers(),
                dstOffsets=[vk.VkOffset3D(0, 0, 0), vk.VkOffset3D(w, h, 1)])
            vk.vkCmdBlitImage(cmd, win.color.handle, TRANSFER_SRC, target, TRANSFER_DST, 1, [blit],
                              vk.VK_FILTER_LINEAR)
            self.ctx.image_barrier(cmd, target, TRANSFER_DST, vk.VK_IMAGE_LAYOUT_PRESENT_SRC_KHR,
                                   vk.VK_ACCESS_TRANSFER_WRITE_BIT, 0, vk.VK_PIPELINE_STAGE_TRANSFER_BIT,
                                   vk.VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT)
            self.ctx.gpu_timer.end(cmd)
            vk.vkEndCommandBuffer(cmd)
            self.presenter.submit_and_present(cmd, index, self.window.framebuffer_size, self.fence)
            vk.vkResetFences(self.ctx.device, 1, [self.fence])
            self._note_frame_time()
        self._frame_active = False
        self._run_deferred()

    # == targets ==============================================================

    def _target(self):
        return self.window_target if self.target is None else self.target

    def set_target(self, framebuffer, size):
        self.target = framebuffer
        t = self._target()
        self.viewport = (size[0], size[1]) if size is not None else (t.width, t.height)

    def target_changed(self, framebuffer):
        if self._rendering_key is not None and self._rendering_key[0] is framebuffer:
            self._end_rendering()

    def bind_window_framebuffer(self, size):
        self.set_target(None, size)

    def get_active_framebuffer(self):
        return (self.target, self.viewport)

    def bind_active_framebuffer(self, handle):
        if handle is not None:
            self.target, self.viewport = handle

    def _begin_rendering(self):
        cmd = self._ensure_frame()
        target = self._target()
        colors = target.render_targets()  # None: an attachment not drawn to right now
        depth = target.depth_target()
        key = (target, tuple(id(c) if c is not None else None for c in colors), id(depth) if depth else None)
        if self._rendering_key == key:
            return cmd
        self._end_rendering()
        for image in colors:
            if image is not None:
                image.transition(cmd, COLOR_ATTACHMENT)
        if depth is not None:
            depth.transition(cmd, DEPTH_ATTACHMENT)
        # Successive renderings into the same attachments still need
        # ordering between them.
        self.ctx.memory_barrier(
            cmd, vk.VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT | vk.VK_PIPELINE_STAGE_LATE_FRAGMENT_TESTS_BIT,
            vk.VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT | vk.VK_PIPELINE_STAGE_EARLY_FRAGMENT_TESTS_BIT,
            vk.VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT | vk.VK_ACCESS_DEPTH_STENCIL_ATTACHMENT_WRITE_BIT,
            vk.VK_ACCESS_COLOR_ATTACHMENT_READ_BIT | vk.VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT
            | vk.VK_ACCESS_DEPTH_STENCIL_ATTACHMENT_READ_BIT | vk.VK_ACCESS_DEPTH_STENCIL_ATTACHMENT_WRITE_BIT)
        # A null view keeps the slot - output n still reaches attachment n -
        # and discards what's written to it.
        color_infos = [vk.VkRenderingAttachmentInfo(
            imageView=image.view if image is not None else None, imageLayout=COLOR_ATTACHMENT,
            loadOp=vk.VK_ATTACHMENT_LOAD_OP_LOAD, storeOp=vk.VK_ATTACHMENT_STORE_OP_STORE) for image in colors]
        depth_info = None
        if depth is not None:
            depth_info = vk.VkRenderingAttachmentInfo(
                imageView=depth.view, imageLayout=DEPTH_ATTACHMENT, loadOp=vk.VK_ATTACHMENT_LOAD_OP_LOAD,
                storeOp=vk.VK_ATTACHMENT_STORE_OP_STORE)
        area = vk.VkRect2D(offset=vk.VkOffset2D(0, 0), extent=vk.VkExtent2D(target.width, target.height))
        info = vk.VkRenderingInfo(renderArea=area, layerCount=1,
                                  colorAttachmentCount=len(color_infos), pColorAttachments=color_infos or None,
                                  pDepthAttachment=depth_info)
        vk.vkCmdBeginRendering(cmd, info)
        self._rendering_key = key
        self._rendering_formats = (tuple(c.format if c is not None else vk.VK_FORMAT_UNDEFINED for c in colors),
                                   depth.format if depth else vk.VK_FORMAT_UNDEFINED)
        return cmd

    def _end_rendering(self):
        if self._rendering_key is not None:
            vk.vkCmdEndRendering(self.cmd)
            self._rendering_key = None

    # == state ================================================================

    def set_blend_mode(self, mode: BlendMode):
        self._current_blend_mode = mode

    def enable_depth_testing(self):
        self.depth_test = True

    def disable_depth_testing(self):
        self.depth_test = False

    def set_scissor(self, x, y, width, height):
        self.scissor = (int(x), int(y), int(width), int(height))

    def clear_scissor(self):
        self.scissor = None

    def resize(self, size):
        if self.ctx is None or size[0] == 0 or size[1] == 0:
            return
        self.flush()
        self.ctx.wait_idle()
        if self.presenter is not None:
            self.presenter.recreate(size)
        old = self.window_target
        self.window_target = _WindowTarget(self.ctx, size)
        self.defer_destroy(old.color)
        self.defer_destroy(old.depth)
        if self.target is None:
            self.viewport = (self.window_target.width, self.window_target.height)

    def _scissor_rect(self, target):
        """The current scissor as a VkRect2D clamped to `target` - the
        whole target when there's none."""
        if self.scissor is None:
            return vk.VkRect2D(offset=vk.VkOffset2D(0, 0), extent=vk.VkExtent2D(target.width, target.height))
        x, y, w, h = self.scissor
        # Top-left, Y-down in -> bottom-left memory rows, flipped against
        # the window's height exactly as GL44 does.
        fb_height = self.window.framebuffer_size[1] if self.window is not None else target.height
        sy = fb_height - y - h
        x0, y0 = min(max(x, 0), target.width), min(max(sy, 0), target.height)
        return vk.VkRect2D(offset=vk.VkOffset2D(x0, y0),
                           extent=vk.VkExtent2D(max(min(x + w, target.width) - x0, 0),
                                                max(min(sy + h, target.height) - y0, 0)))

    # == clearing / copying ===================================================

    def clear(self, color):
        cmd = self._begin_rendering()
        target = self._target()
        rgba = color.float_normalized_a if hasattr(color, "float_normalized_a") else tuple(color)
        attachments = [vk.VkClearAttachment(
            aspectMask=vk.VK_IMAGE_ASPECT_COLOR_BIT, colorAttachment=i,
            clearValue=vk.VkClearValue(color=vk.VkClearColorValue(float32=[float(c) for c in rgba])))
            for i, image in enumerate(target.render_targets()) if image is not None]
        depth = target.depth_target()
        if depth is not None:
            attachments.append(vk.VkClearAttachment(
                aspectMask=depth.aspect, clearValue=vk.VkClearValue(
                    depthStencil=vk.VkClearDepthStencilValue(depth=1.0, stencil=0))))
        # Scissored, as glClear is - UIRenderer clears just its dirty rect.
        area = self._scissor_rect(target)
        if attachments and area.extent.width > 0 and area.extent.height > 0:
            rect = vk.VkClearRect(rect=area, baseArrayLayer=0, layerCount=1)
            vk.vkCmdClearAttachments(cmd, len(attachments), attachments, 1, [rect])

    def clear_attachment(self, framebuffer, name, value):
        target = self._target()
        value = [float(v) for v in value]
        if target is framebuffer and name in framebuffer.draw_buffers:
            cmd = self._begin_rendering()
            rect = vk.VkClearRect(rect=vk.VkRect2D(offset=vk.VkOffset2D(0, 0),
                                                   extent=vk.VkExtent2D(framebuffer.width, framebuffer.height)),
                                  baseArrayLayer=0, layerCount=1)
            vk.vkCmdClearAttachments(cmd, 1, [vk.VkClearAttachment(
                aspectMask=vk.VK_IMAGE_ASPECT_COLOR_BIT, colorAttachment=framebuffer.color_names.index(name),
                clearValue=vk.VkClearValue(color=vk.VkClearColorValue(float32=value)))], 1, [rect])
            return
        cmd = self._ensure_frame()
        self._end_rendering()
        image = framebuffer.images[name].gpu
        image.transition(cmd, TRANSFER_DST)
        vk.vkCmdClearColorImage(cmd, image.handle, TRANSFER_DST, vk.VkClearColorValue(float32=value), 1,
                                [self.ctx.color_range()])

    def _blit(self, cmd, src, dst, flip=False, size=None, linear=False):
        if hasattr(src, "transition"):
            src.transition(cmd, TRANSFER_SRC)
            src_layout = TRANSFER_SRC
        else:
            # A compute kernel's StorageImage, which stays in GENERAL.
            src_layout = vk.VK_IMAGE_LAYOUT_GENERAL
            self.ctx.memory_barrier(cmd, vk.VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, vk.VK_PIPELINE_STAGE_TRANSFER_BIT,
                                    vk.VK_ACCESS_MEMORY_WRITE_BIT, vk.VK_ACCESS_TRANSFER_READ_BIT)
        dst.transition(cmd, TRANSFER_DST)
        w, h = size or (dst.width, dst.height)
        src_offsets = ([vk.VkOffset3D(0, src.height, 0), vk.VkOffset3D(src.width, 0, 1)] if flip
                       else [vk.VkOffset3D(0, 0, 0), vk.VkOffset3D(src.width, src.height, 1)])
        vk.vkCmdBlitImage(cmd, src.handle, src_layout, dst.handle, TRANSFER_DST, 1, [vk.VkImageBlit(
            srcSubresource=self.ctx.color_layers(), srcOffsets=src_offsets,
            dstSubresource=self.ctx.color_layers(), dstOffsets=[vk.VkOffset3D(0, 0, 0), vk.VkOffset3D(w, h, 1)])],
            vk.VK_FILTER_LINEAR if linear else vk.VK_FILTER_NEAREST)

    def blit_to_window(self, image, size):
        cmd = self._ensure_frame()
        self._end_rendering()
        self._blit(cmd, image, self.window_target.color, size=size)

    def read_image(self, image, as_float: bool = False):
        """Copies an image back to the CPU as (height, width, channels)."""
        bpp, channels, dtype = FORMAT_INFO.get(image.format, (4, 4, np.uint8))
        self.flush()
        staging = Buffer(self.ctx, image.width * image.height * bpp, vk.VK_BUFFER_USAGE_TRANSFER_DST_BIT)
        with self.ctx.commands() as cmd:
            image.transition(cmd, TRANSFER_SRC)
            vk.vkCmdCopyImageToBuffer(cmd, image.handle, TRANSFER_SRC, staging.handle, 1, [vk.VkBufferImageCopy(
                bufferOffset=0, bufferRowLength=0, bufferImageHeight=0,
                imageSubresource=vk.VkImageSubresourceLayers(aspectMask=image.view_aspect, mipLevel=0,
                                                             baseArrayLayer=0, layerCount=1),
                imageOffset=vk.VkOffset3D(0, 0, 0), imageExtent=vk.VkExtent3D(image.width, image.height, 1))])
        raw = staging.read()
        staging.destroy()
        pixels = np.frombuffer(raw, dtype=dtype or np.uint8).reshape(image.height, image.width, -1)
        if as_float:
            pixels = pixels.astype(np.float32) / (255.0 if pixels.dtype == np.uint8 else 1.0)
        return pixels

    # == drawing ==============================================================

    def draw_mesh(self, mesh, material):
        material.use()
        material.shader.use()
        mesh.draw()

    def draw_current(self, mesh):
        if self.current_shader is None:
            warning("A mesh was drawn with no shader in use.")
            return
        self._draw(mesh, self.current_shader)

    def draw_mesh_instanced(self, mesh, material, model_matrices, camera):
        material.shader["view"] = camera.view_matrix
        material.shader["proj"] = camera.proj_matrix
        material.use()
        material.shader.use()
        data = np.ascontiguousarray(model_matrices, dtype=np.float32)
        self._draw(mesh, material.shader, instance=(data.tobytes(), 64), instance_count=len(data))

    def draw_ui_background_instances(self, mesh, material, instance_data):
        self.total_draw_calls += 1
        material.use()
        material.shader.use()
        data = np.ascontiguousarray(instance_data, dtype=np.float32)
        self._draw(mesh, material.shader, instance=(data.tobytes(), data.shape[1] * 4), instance_count=len(data))

    def draw_line(self, start, end, width, color):
        vertices = np.array([-start[0], start[1], -end[0], end[1]], dtype=np.float32).tobytes()
        shader = self._line_shader()
        shader.set_uniform("line_color", color)
        shader.use()
        self._draw(_Transient(self.vertex_ring, vertices, vk.VK_FORMAT_R32G32_SFLOAT, 8, 2,
                              vk.VK_PRIMITIVE_TOPOLOGY_LINE_LIST), shader)

    def _line_shader(self):
        # Loaded on first use: a headless renderer has no files service.
        if self.line_shader is None:
            from FreeBodyEngine.core.files import get_file
            self.line_shader = self.load_shader(get_file("engine://shader/line.fbvert").read(),
                                                get_file("engine://shader/line.fbfrag").read())
        return self.line_shader

    def draw_circle(self, radius, position, color):
        pass  # GL44 doesn't draw circles either

    def _sampled_images(self, shader):
        images = []
        tm = self.texture_manager
        for name, binding in shader.sampler_bindings.items():
            value = shader.textures.get(name)
            gpu = sampler = None
            if isinstance(value, (Texture, TextureStack)):
                gpu, sampler = tm.resolve(value.id)
            if gpu is None:
                gpu = self._white_array if binding.get("texture_kind") == "textureStack" else self._white
                sampler = tm.sampler(False, False, True)
            images.append((binding["binding"], gpu, sampler))
        return images

    def _ring_alloc(self, ring, data):
        offset = ring.alloc(data)
        if offset is None:
            # Full for this frame: run what's recorded so far, which frees
            # both rings, and carry on.
            self.flush()
            offset = ring.alloc(data)
            if offset is None:
                raise RuntimeError(f"{len(data)} bytes don't fit in a {ring.size}-byte per-frame ring")
        return offset

    def _draw(self, mesh, shader, instance=None, instance_count=1):
        emulation = getattr(shader, "emulation", None)
        if emulation is not None:
            return self._draw_emulated_geometry(mesh, shader, emulation, instance_count)
        cmd = self._ensure_frame()
        # Ring space first, before anything for this draw is recorded: a
        # flush to make room starts a new command buffer and empties both
        # rings, so if one happens partway, everything is placed again.
        for _ in range(2):
            flushes = self._flush_count
            ubo_offset = (self._ring_alloc(self.uniform_ring, bytes(shader.uniform_bytes))
                          if shader.ubo_binding is not None else None)
            inst_offset = self._ring_alloc(self.vertex_ring, instance[0]) if instance is not None else None
            if isinstance(mesh, _Transient):
                mesh.offset = self._ring_alloc(self.vertex_ring, mesh.data)
            if self._flush_count == flushes:
                break
        images = self._prepare_images(shader)
        cmd = self._begin_rendering()

        # Vertex layout: shader input i reads mesh attribute i; inputs past
        # the mesh's attributes read per-instance vec4s (GL44's
        # base_location + column convention).
        n_attr = len(mesh.formats)
        n_inputs = len(shader.inputs)
        mesh_inputs = min(n_inputs, n_attr)
        if n_inputs > n_attr and instance is None:
            warning(f"Shader expects {n_inputs} vertex inputs, mesh has {n_attr} attributes - draw skipped.")
            return
        vertex_desc = tuple(mesh.formats[i] for i in range(mesh_inputs))
        instance_desc = (n_inputs - mesh_inputs, instance[1]) if instance is not None and n_inputs > n_attr else None
        topology = getattr(shader, "topology", None) or mesh.topology
        self._bind_graphics(cmd, shader, vertex_desc, instance_desc, topology, ubo_offset, images)

        buffers = mesh.stream_buffers()[:mesh_inputs]
        offsets = list(mesh.stream_offsets())[:mesh_inputs] if hasattr(mesh, "stream_offsets") else [0] * len(buffers)
        handles = [b.handle for b in buffers]
        if instance_desc is not None:
            handles.append(self.vertex_ring.buffer.handle)
            offsets.append(inst_offset)
        if handles:
            vk.vkCmdBindVertexBuffers(cmd, 0, len(handles), handles, offsets)
        if mesh.index_stream is not None:
            vk.vkCmdBindIndexBuffer(cmd, mesh.index_stream.buffer.handle, 0, mesh.index_vk_type)
            vk.vkCmdDrawIndexed(cmd, mesh.index_count, instance_count, 0, 0, 0)
        else:
            vk.vkCmdDraw(cmd, mesh.vertex_count, instance_count, 0, 0)

    def _prepare_images(self, shader):
        """The shader's textures, each moved to SHADER_READ - which ends
        any rendering in progress if one wasn't there yet."""
        images = self._sampled_images(shader)
        for _, gpu, _ in images:
            if hasattr(gpu, "transition") and gpu.layout != SHADER_READ:
                self._end_rendering()
                gpu.transition(self.cmd, SHADER_READ)
        return images

    def _bind_graphics(self, cmd, shader, vertex_desc, instance_desc, topology, ubo_offset, images, storage=None):
        """Pipeline, viewport, scissor and descriptor set for a draw, with
        rendering already begun."""
        blend = self._current_blend_mode or BlendMode.OPAQUE
        color_formats, depth_format = self._rendering_formats
        depth_test = self.depth_test and depth_format != vk.VK_FORMAT_UNDEFINED
        pipeline = self._pipeline(shader, vertex_desc, instance_desc, topology, blend, depth_test,
                                  color_formats, depth_format)
        vk.vkCmdBindPipeline(cmd, vk.VK_PIPELINE_BIND_POINT_GRAPHICS, pipeline)
        vw, vh = self.viewport
        vk.vkCmdSetViewport(cmd, 0, 1, [vk.VkViewport(x=0, y=0, width=max(vw, 1), height=max(vh, 1),
                                                      minDepth=0.0, maxDepth=1.0)])
        vk.vkCmdSetScissor(cmd, 0, 1, [self._scissor_rect(self._target())])
        dynamic_offsets = [] if ubo_offset is None else [ubo_offset]
        descriptor = self._descriptor_set(shader, images, storage)
        if descriptor is not None:
            vk.vkCmdBindDescriptorSets(cmd, vk.VK_PIPELINE_BIND_POINT_GRAPHICS, shader.pipeline_layout, 0, 1,
                                       [descriptor], len(dynamic_offsets), dynamic_offsets or None)

    def _draw_emulated_geometry(self, mesh, shader, em, instance_count):
        """A geometry stage the device can't run, emulated as
        fbusl.geometry describes: "pull" draws `primitives * slots` vertices
        that fetch the mesh from storage buffers; "compute" first runs a
        pre-pass that appends the emitted primitives to a buffer laid out
        as an indirect draw, then draws exactly those."""
        if isinstance(mesh, _Transient):
            warning("Lines can't be drawn through a geometry shader.")
            return
        if len(mesh.formats) < len(em.attributes):
            warning(f"The geometry shader's vertex stage reads {len(em.attributes)} attributes, the mesh has "
                    f"{len(mesh.formats)} - draw skipped.")
            return
        indexed = mesh.index_stream is not None
        prims = (mesh.index_count if indexed else mesh.vertex_count) // em.input_vertices
        if prims <= 0 or instance_count <= 0:
            return
        shader._write("_gs_prim_count", prims)
        shader._write("_gs_index_mode", 0 if not indexed else 1 if mesh.index_vk_type == vk.VK_INDEX_TYPE_UINT16 else 2)
        streams = mesh.stream_buffers()
        storage = {"gs_index.data": mesh.index_stream.buffer if indexed else self._empty_storage}
        for i, (name, *_rest) in enumerate(em.attributes):
            storage[f"gs_attr_{name}.data"] = streams[i]

        compute = shader.geometry_compute
        if compute is not None:
            capacity = prims * em.max_primitives * em.output_vertices
            compute.ensure_capacity(self, capacity, em.stride)
            shader._write("_gs_capacity", capacity)

        self._ensure_frame()
        for _ in range(2):
            flushes = self._flush_count
            ubo_offset = (self._ring_alloc(self.uniform_ring, bytes(shader.uniform_bytes))
                          if shader.ubo_binding is not None else None)
            compute_ubo = (self._ring_alloc(self.uniform_ring, bytes(compute.uniform_bytes))
                           if compute is not None and compute.ubo_binding is not None else None)
            if self._flush_count == flushes:
                break
        cmd = self.cmd

        if compute is not None:
            self._end_rendering()
            ctx = self.ctx
            # The previous draw from these buffers has to be done with them.
            ctx.memory_barrier(cmd, vk.VK_PIPELINE_STAGE_VERTEX_INPUT_BIT | vk.VK_PIPELINE_STAGE_DRAW_INDIRECT_BIT,
                               vk.VK_PIPELINE_STAGE_TRANSFER_BIT | vk.VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,
                               vk.VK_ACCESS_VERTEX_ATTRIBUTE_READ_BIT | vk.VK_ACCESS_INDIRECT_COMMAND_READ_BIT,
                               vk.VK_ACCESS_TRANSFER_WRITE_BIT | vk.VK_ACCESS_SHADER_READ_BIT
                               | vk.VK_ACCESS_SHADER_WRITE_BIT)
            # {vertex count, instance count, first vertex, first instance};
            # the pre-pass adds to the vertex count.
            command = vk.ffi.new("uint32_t[4]", [0, instance_count, 0, 0])  # the binding wants a pointer, not bytes
            vk.vkCmdUpdateBuffer(cmd, compute.draw.handle, 0, 16, command)
            ctx.memory_barrier(cmd, vk.VK_PIPELINE_STAGE_TRANSFER_BIT, vk.VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,
                               vk.VK_ACCESS_TRANSFER_WRITE_BIT,
                               vk.VK_ACCESS_SHADER_READ_BIT | vk.VK_ACCESS_SHADER_WRITE_BIT)
            compute_storage = dict(storage)
            compute_storage["gs_out.data"] = compute.out
            compute_storage["gs_draw.data"] = compute.draw
            descriptor = self._descriptor_set(compute, (), compute_storage)
            vk.vkCmdBindPipeline(cmd, vk.VK_PIPELINE_BIND_POINT_COMPUTE, compute.pipeline)
            offsets = [] if compute_ubo is None else [compute_ubo]
            vk.vkCmdBindDescriptorSets(cmd, vk.VK_PIPELINE_BIND_POINT_COMPUTE, compute.pipeline_layout, 0, 1,
                                       [descriptor], len(offsets), offsets or None)
            vk.vkCmdDispatch(cmd, -(-prims // em.local_size), 1, 1)
            ctx.memory_barrier(cmd, vk.VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,
                               vk.VK_PIPELINE_STAGE_VERTEX_INPUT_BIT | vk.VK_PIPELINE_STAGE_DRAW_INDIRECT_BIT,
                               vk.VK_ACCESS_SHADER_WRITE_BIT,
                               vk.VK_ACCESS_VERTEX_ATTRIBUTE_READ_BIT | vk.VK_ACCESS_INDIRECT_COMMAND_READ_BIT)

        images = self._prepare_images(shader)
        cmd = self._begin_rendering()
        if compute is not None:
            stride = em.stride * 4
            vertex_desc = ((vk.VK_FORMAT_R32G32B32A32_SFLOAT, stride),) + tuple(
                (FLOAT_FORMATS[n], stride) for _, _, _, n in em.outputs)
            offsets = [0] + [offset * 4 for _, _, offset, _ in em.outputs]
            self._bind_graphics(cmd, shader, vertex_desc, None, shader.topology, ubo_offset, images)
            vk.vkCmdBindVertexBuffers(cmd, 0, len(offsets), [compute.out.handle] * len(offsets), offsets)
            vk.vkCmdDrawIndirect(cmd, compute.draw.handle, 0, 1, 16)
        else:
            self._bind_graphics(cmd, shader, (), None, shader.topology, ubo_offset, images, storage)
            vk.vkCmdDraw(cmd, prims * em.slots, instance_count, 0, 0)

    def _descriptor_set(self, owner, images, storage=None):
        """A descriptor set for `owner` (a VulkanShader, or a geometry
        stage's compute pre-pass): the uniform ring as its dynamic uniform
        buffer, `images` as [(binding, image, sampler)], and `storage` as
        {binding name: Buffer} - one built per frame for each combination."""
        if not owner.bindings:
            return None
        storage = storage or {}
        key = (owner.id, tuple((id(g), id(s)) for _, g, s in images),
               tuple(sorted((name, id(buf)) for name, buf in storage.items())))
        cached = self._descriptor_cache.get(key)
        if cached is not None:
            return cached
        ctx = self.ctx
        descriptor = vk.vkAllocateDescriptorSets(ctx.device, vk.VkDescriptorSetAllocateInfo(
            descriptorPool=self.descriptor_pool, descriptorSetCount=1, pSetLayouts=[owner.set_layout]))[0]
        writes, keep = [], []
        if owner.ubo_binding is not None:
            info = [vk.VkDescriptorBufferInfo(buffer=self.uniform_ring.buffer.handle, offset=0,
                                              range=max(owner.uniform_size, 16))]
            keep.append(info)
            writes.append(vk.VkWriteDescriptorSet(
                dstSet=descriptor, dstBinding=owner.ubo_binding, dstArrayElement=0, descriptorCount=1,
                descriptorType=vk.VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER_DYNAMIC, pBufferInfo=info))
        for binding, gpu, sampler in images:
            layout = SHADER_READ if hasattr(gpu, "transition") else vk.VK_IMAGE_LAYOUT_GENERAL
            info = [vk.VkDescriptorImageInfo(sampler=sampler, imageView=gpu.view, imageLayout=layout)]
            keep.append(info)
            writes.append(vk.VkWriteDescriptorSet(
                dstSet=descriptor, dstBinding=binding, dstArrayElement=0, descriptorCount=1,
                descriptorType=vk.VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, pImageInfo=info))
        for b in owner.bindings:
            if b["kind"] != "storage_buffer":
                continue
            buf = storage.get(b["name"], self._empty_storage)
            info = [vk.VkDescriptorBufferInfo(buffer=buf.handle, offset=0, range=UINT64_MAX)]
            keep.append(info)
            writes.append(vk.VkWriteDescriptorSet(
                dstSet=descriptor, dstBinding=b["binding"], dstArrayElement=0, descriptorCount=1,
                descriptorType=vk.VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, pBufferInfo=info))
        vk.vkUpdateDescriptorSets(ctx.device, len(writes), writes, 0, None)
        self._descriptor_cache[key] = descriptor
        return descriptor

    def forget_pipelines(self, shader):
        for key in [k for k in self._pipelines if k[0] == shader.id]:
            self.defer_destroy(_Pipeline(self.ctx, self._pipelines.pop(key)))

    def _pipeline(self, shader, vertex_desc, instance_desc, topology, blend, depth_test, color_formats, depth_format):
        key = (shader.id, vertex_desc, instance_desc, topology, blend, depth_test, color_formats, depth_format)
        pipeline = self._pipelines.get(key)
        if pipeline is not None:
            return pipeline
        device = self.ctx.device
        bindings, attributes = [], []
        for location, (fmt, stride) in enumerate(vertex_desc):
            bindings.append(vk.VkVertexInputBindingDescription(
                binding=location, stride=stride, inputRate=vk.VK_VERTEX_INPUT_RATE_VERTEX))
            attributes.append(vk.VkVertexInputAttributeDescription(location=location, binding=location,
                                                                   format=fmt, offset=0))
        if instance_desc is not None:
            count, stride = instance_desc
            binding = len(vertex_desc)
            bindings.append(vk.VkVertexInputBindingDescription(
                binding=binding, stride=stride, inputRate=vk.VK_VERTEX_INPUT_RATE_INSTANCE))
            for k in range(count):
                attributes.append(vk.VkVertexInputAttributeDescription(
                    location=binding + k, binding=binding, format=INSTANCE_FORMAT, offset=k * 16))

        if blend == BlendMode.OPAQUE:
            attachment_blend = dict(blendEnable=vk.VK_FALSE)
        else:
            dst = vk.VK_BLEND_FACTOR_ONE if blend == BlendMode.ADDITIVE else vk.VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA
            attachment_blend = dict(blendEnable=vk.VK_TRUE,
                                    srcColorBlendFactor=vk.VK_BLEND_FACTOR_SRC_ALPHA, dstColorBlendFactor=dst,
                                    colorBlendOp=vk.VK_BLEND_OP_ADD,
                                    srcAlphaBlendFactor=vk.VK_BLEND_FACTOR_SRC_ALPHA, dstAlphaBlendFactor=dst,
                                    alphaBlendOp=vk.VK_BLEND_OP_ADD)
        write_mask = (vk.VK_COLOR_COMPONENT_R_BIT | vk.VK_COLOR_COMPONENT_G_BIT
                      | vk.VK_COLOR_COMPONENT_B_BIT | vk.VK_COLOR_COMPONENT_A_BIT)
        blends = [vk.VkPipelineColorBlendAttachmentState(colorWriteMask=write_mask, **attachment_blend)
                  for _ in color_formats]

        # Every nested struct is held in a local until the call returns -
        # see context.py on the `vulkan` package's lifetime rules.
        vertex_stage = vk.VkPipelineShaderStageCreateInfo(stage=vk.VK_SHADER_STAGE_VERTEX_BIT,
                                                          module=shader.vertex_module, pName="main")
        fragment_stage = vk.VkPipelineShaderStageCreateInfo(stage=vk.VK_SHADER_STAGE_FRAGMENT_BIT,
                                                            module=shader.fragment_module, pName="main")
        vertex_input = vk.VkPipelineVertexInputStateCreateInfo(
            vertexBindingDescriptionCount=len(bindings), pVertexBindingDescriptions=bindings or None,
            vertexAttributeDescriptionCount=len(attributes), pVertexAttributeDescriptions=attributes or None)
        assembly = vk.VkPipelineInputAssemblyStateCreateInfo(topology=topology)
        viewport = vk.VkPipelineViewportStateCreateInfo(viewportCount=1, scissorCount=1)
        raster = vk.VkPipelineRasterizationStateCreateInfo(
            polygonMode=vk.VK_POLYGON_MODE_FILL, cullMode=vk.VK_CULL_MODE_NONE,
            frontFace=vk.VK_FRONT_FACE_COUNTER_CLOCKWISE, lineWidth=1.0)
        multisample = vk.VkPipelineMultisampleStateCreateInfo(rasterizationSamples=vk.VK_SAMPLE_COUNT_1_BIT)
        depth = vk.VkPipelineDepthStencilStateCreateInfo(
            depthTestEnable=vk.VK_TRUE if depth_test else vk.VK_FALSE,
            depthWriteEnable=vk.VK_TRUE if depth_test and blend != BlendMode.TRANSPARENT else vk.VK_FALSE,
            depthCompareOp=vk.VK_COMPARE_OP_LESS)
        color_blend = vk.VkPipelineColorBlendStateCreateInfo(attachmentCount=len(blends),
                                                             pAttachments=blends or None)
        dynamic_states = [vk.VK_DYNAMIC_STATE_VIEWPORT, vk.VK_DYNAMIC_STATE_SCISSOR]
        dynamic = vk.VkPipelineDynamicStateCreateInfo(dynamicStateCount=2, pDynamicStates=dynamic_states)
        stencil_format = depth_format if depth_format == vk.VK_FORMAT_D32_SFLOAT_S8_UINT else vk.VK_FORMAT_UNDEFINED
        color_list = list(color_formats)
        rendering = vk.VkPipelineRenderingCreateInfo(
            colorAttachmentCount=len(color_list), pColorAttachmentFormats=color_list or None,
            depthAttachmentFormat=depth_format, stencilAttachmentFormat=stencil_format)
        stages = [vertex_stage, fragment_stage]
        geometry_stage = None
        if getattr(shader, "geometry_module", None) is not None:
            geometry_stage = vk.VkPipelineShaderStageCreateInfo(stage=vk.VK_SHADER_STAGE_GEOMETRY_BIT,
                                                                module=shader.geometry_module, pName="main")
            stages.insert(1, geometry_stage)
        info = vk.VkGraphicsPipelineCreateInfo(
            pNext=rendering, stageCount=len(stages), pStages=stages,
            pVertexInputState=vertex_input, pInputAssemblyState=assembly, pViewportState=viewport,
            pRasterizationState=raster, pMultisampleState=multisample, pDepthStencilState=depth,
            pColorBlendState=color_blend, pDynamicState=dynamic, layout=shader.pipeline_layout)
        try:
            pipeline = vk.vkCreateGraphicsPipelines(device, None, 1, [info], None)[0]
        except vk.VkError as e:
            raise RuntimeError(f"The driver rejected a graphics pipeline ({e!r}). Vertex module:\n"
                               f"{shader._vertex_module_dump.dump()}\nFragment module:\n"
                               f"{shader._fragment_module_dump.dump()}") from e
        self._pipelines[key] = pipeline
        return pipeline

    # == resources ============================================================

    def load_shader(self, vertex, fragment, injector=None, geometry=None):
        return VulkanShader(vertex, fragment, injector, geometry)

    def get_mesh_class(self):
        return VulkanMesh

    def get_image_class(self):
        return VulkanImage

    def load_image(self, texture):
        return VulkanImage(texture)

    def load_image_from_atlas(self, data):
        return VulkanImage(data)

    @property
    def create_framebuffer(self):
        return VulkanFramebuffer

    def create_buffer(self, data):
        return _UniformData(data)

    def get_max_buffer_size(self) -> int:
        return int(self.ctx.limits.maxUniformBufferRange)

    load_material = _not_supported("load_material")

    # == compute presentation & profiling =====================================

    def present_image(self, image):
        """A compute kernel's @output drawn to the window (blit_to_screen()),
        in order with everything else - UI drawn after it lands on top.
        Compute images are top-down, so this copy flips into the window's
        bottom-up image and the final flip turns it upright again."""
        cmd = self._ensure_frame()
        self._end_rendering()
        self._blit(cmd, image, self.window_target.color, flip=True, linear=True)

    def note_gpu_work(self, nanoseconds, dispatches: int = 0):
        self.total_draw_calls += dispatches
        if nanoseconds is not None:
            self._frame_gpu_ns += nanoseconds
            self._frame_timed = True

    def begin_gpu_query(self):
        pass  # frame and dispatch time are measured as they're submitted

    def end_gpu_query(self):
        if self._frame_timed:
            self.last_gpu_ms = self._frame_gpu_ns / 1_000_000.0
        elif self.ctx is not None and not self.ctx.gpu_timer.supported:
            self.last_gpu_ms = None
        else:
            self.last_gpu_ms = 0.0
        self._frame_gpu_ns = 0.0
        self._frame_timed = False


class _Pipeline:
    def __init__(self, ctx, pipeline):
        self.ctx, self.pipeline = ctx, pipeline

    def destroy(self):
        vk.vkDestroyPipeline(self.ctx.device, self.pipeline, None)


class _UniformData:
    """create_buffer()'s result: data a shader could read as a uniform
    block. Shader.set_buffer() isn't supported on Vulkan yet, so this only
    holds the data."""

    def __init__(self, data):
        self.data = data

    def set_data(self, data):
        self.data = data

    def get_data(self):
        return self.data

    def update(self, data, offset=0):
        pass

    def bind(self, *args):
        pass

    def unbind(self):
        pass

    def destroy(self):
        pass
