"""The Vulkan compute and raytrace backend - the ComputeShader interface
(graphics/compute.py) on top of FBUSL's SPIR-V generator.

Same public surface as GL44ComputeShader (graphics/gl44/compute.py), so
code written against fb.graphics.create_compute_shader() /
create_raytrace_shader() / create_compute_buffer() doesn't change when
the session runs on Vulkan (fb.graphics.use_vulkan()):

    shader = fb.graphics.create_raytrace_shader(source)
    shader.upload_scene(None, None, triangles)
    shader.bind_buffer("Scene", "colors", fb.graphics.create_compute_buffer(colors))
    shader.set_uniform("exposure", 1.0)
    shader.dispatch(width, height)
    shader.blit_to_screen("image")

What's different underneath: a raytrace shader's trace_ray()/trace_shadow()
are real hardware ray queries against an acceleration structure the GPU
builds from the uploaded triangles, rather than the software BVH walk the
GL backends emulate - so upload_scene() ignores the bvh_aabb/bvh_meta
arrays the GL backends need (pass None), and RayHit.prim is the index of
the triangle in the order given.

Resource names and binding numbers come from SPIRVGenerator's reflection -
see generator.py's module docstring for the layout. Every buffer *field*
is its own binding, which is why bind_buffer() takes block and field.
"""
import struct

import numpy as np
import vulkan as vk

from fbusl import ShaderType
from fbusl.injector import Injector
from fbusl.optimizer import Optimizer
from fbusl.parser import Lexer, Parser
from fbusl.semantic import SemanticAnalyser

from FreeBodyEngine import get_service, get_time, warning, error as fb_error
from FreeBodyEngine.graphics.compute import ComputeShader
from FreeBodyEngine.graphics.vulkan.accel import AS_INPUT, Instance, build_blas, build_tlas
from FreeBodyEngine.graphics.vulkan.context import StorageImage
from FreeBodyEngine.graphics.vulkan.generator import SPIRVGenerator

# VK_WHOLE_SIZE is ~0ULL; the package stores it as -1, which cffi refuses
# to put in an unsigned field.
WHOLE_SIZE = 0xFFFFFFFFFFFFFFFF

DESCRIPTOR_TYPES = {
    "uniform_buffer": vk.VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER,
    "storage_image": vk.VK_DESCRIPTOR_TYPE_STORAGE_IMAGE,
    "storage_buffer": vk.VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,
    "acceleration_structure": vk.VK_DESCRIPTOR_TYPE_ACCELERATION_STRUCTURE_KHR,
}

# @output image format -> (VkFormat, numpy dtype, channels).
IMAGE_FORMATS = {
    "r32f": (vk.VK_FORMAT_R32_SFLOAT, np.float32, 1),
    "r32i": (vk.VK_FORMAT_R32_SINT, np.int32, 1),
    "rg32f": (vk.VK_FORMAT_R32G32_SFLOAT, np.float32, 2),
    "rgba32f": (vk.VK_FORMAT_R32G32B32A32_SFLOAT, np.float32, 4),
}


def _context():
    renderer = get_service("renderer")
    ctx = getattr(renderer, "ctx", None)
    if ctx is None:
        raise RuntimeError("The Vulkan compute backend needs VulkanRenderer as the 'renderer' service.")
    return ctx


def _submit_timed(ctx, record, dispatches: int = 0):
    """Records `record(cmd)` between GPU timestamps, submits, waits, and
    reports the GPU time to the renderer - which is where the profiler
    (core/profiler_server.py) reads it from."""
    timer = ctx.gpu_timer
    with ctx.commands() as cmd:
        timer.begin(cmd)
        record(cmd)
        timer.end(cmd)
    note = getattr(get_service("renderer"), "note_gpu_work", None)
    if note is not None:
        note(timer.read(), dispatches)


def compile_spirv(source, shader_type=ShaderType.COMPUTE, injector: Injector | None = None):
    """FBUSL -> (SPIR-V bytes, reflection, module). The same steps as
    fbusl.compile(), kept separate so the generator - and with it the
    binding layout - is still in hand afterwards."""
    injector = injector or Injector()
    injector.initialize(shader_type)
    path = None
    if not isinstance(source, str):
        path = source.data.path
        source = source.read()
    tokens = Lexer(injector.source_inject(source), path).tokenize()
    tree = injector.ast_inject(Parser(tokens).parse())
    SemanticAnalyser(tree, shader_type, injector.get_builtins()).analyse()
    tree = Optimizer(tree).optimize()
    generator = SPIRVGenerator(tree, shader_type)
    code = generator.generate()
    return code, generator.reflection, generator.m


def pack_std140(t, value) -> bytes:
    """Bytes for one uniform of FBUSL type `t`, laid out as std140 wants
    it - matrices as vec4-strided columns (column-major), arrays with a
    16-byte element stride, everything else tightly packed."""
    if isinstance(t, tuple):
        _, element, length = t
        out = b""
        for item in list(value)[:length]:
            chunk = pack_std140(element, item)
            out += chunk + b"\0" * (-len(chunk) % 16)
        return out
    if t == "int":
        return struct.pack("<i", int(value))
    if t == "float":
        return struct.pack("<f", float(value))
    if t in ("ivec2", "ivec3"):
        return struct.pack(f"<{t[-1]}i", *(int(v) for v in value))
    if t in ("vec2", "vec3", "vec4"):
        return struct.pack(f"<{t[-1]}f", *(float(v) for v in value))
    if t in ("mat2", "mat3", "mat4"):
        n = int(t[-1])
        m = np.asarray(value, dtype=np.float32).reshape(n, n)
        out = b""
        for col in range(n):
            column = m[:, col].tobytes()
            out += column + b"\0" * (16 - len(column))
        return out
    raise TypeError(f"can't pack a uniform of type {t}")


class VulkanComputeBuffer:
    """What create_compute_buffer() returns under Vulkan: a storage buffer
    a kernel can read and write, holding a numpy array. Host-visible, so
    read_back() and update() are plain memory copies."""

    def __init__(self, data: np.ndarray):
        self.ctx = _context()
        data = np.ascontiguousarray(data)
        self.dtype, self.shape = data.dtype, data.shape
        self._buffer = self.ctx.buffer(data.nbytes, vk.VK_BUFFER_USAGE_STORAGE_BUFFER_BIT)
        self._buffer.write(data.tobytes())

    @property
    def handle(self):
        return self._buffer.handle

    def update(self, data: np.ndarray, offset: int = 0):
        self._buffer.write(np.ascontiguousarray(data).tobytes(), offset)

    def read_back(self) -> np.ndarray:
        nbytes = int(np.prod(self.shape)) * self.dtype.itemsize
        return np.frombuffer(self._buffer.read(nbytes), dtype=self.dtype).reshape(self.shape).copy()

    def destroy(self):
        self._buffer.destroy()


class VulkanComputeShader(ComputeShader):
    def __init__(self, source, injector: Injector = None, shader_type: ShaderType = ShaderType.COMPUTE):
        super().__init__(source, injector)
        self.shader_type = shader_type
        self.ctx = ctx = _context()
        self.code, self.reflection, self.module = compile_spirv(source, shader_type, self.injector)
        self.local_size = self.reflection["local_size"]
        self.bindings = {b["name"]: b for b in self.reflection["bindings"]}
        device = ctx.device

        # The package casts pCode to uint32_t* itself - it wants the bytes.
        self._module = vk.vkCreateShaderModule(device, vk.VkShaderModuleCreateInfo(
            codeSize=len(self.code), pCode=self.code), None)
        layout_bindings = [vk.VkDescriptorSetLayoutBinding(
            binding=b["binding"], descriptorType=DESCRIPTOR_TYPES[b["kind"]], descriptorCount=1,
            stageFlags=vk.VK_SHADER_STAGE_COMPUTE_BIT) for b in self.reflection["bindings"]]
        self._set_layout = vk.vkCreateDescriptorSetLayout(device, vk.VkDescriptorSetLayoutCreateInfo(
            bindingCount=len(layout_bindings), pBindings=layout_bindings or None), None)
        self._pipeline_layout = vk.vkCreatePipelineLayout(device, vk.VkPipelineLayoutCreateInfo(
            setLayoutCount=1, pSetLayouts=[self._set_layout]), None)
        # Held in a variable for the whole call: the package copies a nested
        # struct into its parent by value, but the "main" string it points
        # at is owned by the nested struct's Python object - a temporary,
        # which can be collected before the driver reads the name. That was
        # an intermittent VK_ERROR_INITIALIZATION_FAILED on valid SPIR-V.
        stage = vk.VkPipelineShaderStageCreateInfo(
            stage=vk.VK_SHADER_STAGE_COMPUTE_BIT, module=self._module, pName="main")
        try:
            self._pipeline = vk.vkCreateComputePipelines(device, None, 1, [vk.VkComputePipelineCreateInfo(
                stage=stage, layout=self._pipeline_layout)], None)[0]
        except vk.VkError as e:
            raise RuntimeError(f"The driver rejected the generated SPIR-V ({e!r}). Module:\n{self.module.dump()}") from e

        counts: dict[int, int] = {}
        for b in self.reflection["bindings"]:
            counts[DESCRIPTOR_TYPES[b["kind"]]] = counts.get(DESCRIPTOR_TYPES[b["kind"]], 0) + 1
        sizes = [vk.VkDescriptorPoolSize(type=t, descriptorCount=n) for t, n in counts.items()]
        self._pool = None
        self._descriptor_set = None
        if sizes:
            self._pool = vk.vkCreateDescriptorPool(device, vk.VkDescriptorPoolCreateInfo(
                maxSets=1, poolSizeCount=len(sizes), pPoolSizes=sizes), None)
            self._descriptor_set = vk.vkAllocateDescriptorSets(device, vk.VkDescriptorSetAllocateInfo(
                descriptorPool=self._pool, descriptorSetCount=1, pSetLayouts=[self._set_layout]))[0]

        self._uniform_buffer = None
        if "uniforms" in self.bindings:
            size = self.reflection["uniform_size"]
            self._uniform_buffer = ctx.buffer(size, vk.VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT)
            self._uniform_bytes = bytearray(size)
            self._write_descriptor("uniforms", self._uniform_buffer)

        self._buffers: dict[str, object] = {}
        # Written images only - `image` @uniforms (access "read") are inputs
        # the caller binds with bind_image().
        self._outputs = {b["name"]: b["format"] for b in self.reflection["bindings"]
                         if b["kind"] == "storage_image" and b.get("access") != "read"}
        self._output_images: dict[str, StorageImage] = {}
        self._size: tuple[int, int] | None = None

    # -- resources ---------------------------------------------------------------

    def _write_descriptor(self, name: str, resource):
        b = self.bindings[name]
        kind = b["kind"]
        write = dict(dstSet=self._descriptor_set, dstBinding=b["binding"], dstArrayElement=0,
                     descriptorCount=1, descriptorType=DESCRIPTOR_TYPES[kind])
        if kind in ("uniform_buffer", "storage_buffer"):
            write["pBufferInfo"] = [vk.VkDescriptorBufferInfo(buffer=resource.handle, offset=0, range=WHOLE_SIZE)]
        elif kind == "storage_image":
            write["pImageInfo"] = [vk.VkDescriptorImageInfo(imageView=resource.view, imageLayout=vk.VK_IMAGE_LAYOUT_GENERAL)]
        elif kind == "acceleration_structure":
            write["pNext"] = vk.VkWriteDescriptorSetAccelerationStructureKHR(
                accelerationStructureCount=1, pAccelerationStructures=[resource.handle])
        vk.vkUpdateDescriptorSets(self.ctx.device, 1, [vk.VkWriteDescriptorSet(**write)], 0, None)

    def bind_buffer(self, block: str, field: str, buffer: VulkanComputeBuffer):
        """Binds `buffer` (from create_compute_buffer()) to one field of a
        `buffer` block. Unlike GL44, where one SSBO backs a whole block,
        each field here is its own binding."""
        name = f"{block}.{field}"
        if name not in self.bindings:
            warning(f"Compute shader has no buffer field '{name}'")
            return
        self._write_descriptor(name, buffer)
        self._buffers[name] = buffer

    def bind_image(self, name: str, image: StorageImage):
        """Binds an rgba32f StorageImage - typically another kernel's
        @output - to an `image`-typed @uniform, for image_load()."""
        b = self.bindings.get(name)
        if b is None or b.get("access") != "read":
            warning(f"Compute shader has no `image` uniform named '{name}'")
            return
        self._write_descriptor(name, image)

    def output_image(self, name: str) -> StorageImage | None:
        """The StorageImage backing @output `name`, once dispatched."""
        return self._output_images.get(name)

    def set_uniform(self, name: str, value):
        info = self.reflection["uniforms"].get(name)
        if info is None:
            warning(f"Uniform '{name}' not found in compute shader")
            return
        data = pack_std140(info["type"], value)
        self._uniform_bytes[info["offset"]:info["offset"] + len(data)] = data
        self._uniform_buffer.write(bytes(self._uniform_bytes))

    def _ensure_output_images(self, width: int, height: int):
        if self._size == (width, height):
            return
        self.ctx.wait_idle()
        for image in self._output_images.values():
            image.destroy()
        self._output_images = {}
        for name, fmt in self._outputs.items():
            image = StorageImage(self.ctx, width, height, IMAGE_FORMATS[fmt][0])
            self._output_images[name] = image
            self._write_descriptor(name, image)
        self._size = (width, height)

    # -- running -----------------------------------------------------------------

    def record(self, cmd, width: int, height: int):
        """Records a dispatch covering width x height into `cmd` without
        submitting it - for callers batching several kernels into one
        submission. dispatch() is this plus a submit and a wait."""
        self._ensure_output_images(width, height)
        uniforms = self.reflection["uniforms"]
        if "DISPATCH_SIZE" in uniforms:
            self.set_uniform("DISPATCH_SIZE", (width, height, 1))
        if "TIME" in uniforms:
            self.set_uniform("TIME", get_time())
        vk.vkCmdBindPipeline(cmd, vk.VK_PIPELINE_BIND_POINT_COMPUTE, self._pipeline)
        if self._descriptor_set is not None:
            vk.vkCmdBindDescriptorSets(cmd, vk.VK_PIPELINE_BIND_POINT_COMPUTE, self._pipeline_layout,
                                       0, 1, [self._descriptor_set], 0, None)
        lx, ly, _ = self.local_size
        vk.vkCmdDispatch(cmd, max(1, -(-width // lx)), max(1, -(-height // ly)), 1)
        # Whatever reads the results next - another dispatch, a readback, a
        # blit to the screen - waits for these writes.
        self.ctx.memory_barrier(cmd, vk.VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,
                                vk.VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT | vk.VK_PIPELINE_STAGE_TRANSFER_BIT,
                                vk.VK_ACCESS_SHADER_WRITE_BIT,
                                vk.VK_ACCESS_SHADER_READ_BIT | vk.VK_ACCESS_SHADER_WRITE_BIT | vk.VK_ACCESS_TRANSFER_READ_BIT)

    def dispatch(self, width: int, height: int):
        """Runs the kernel once per (x, y) in [0, width) x [0, height) and
        waits for it, so results are ready to read straight after - the
        same contract as the GL backends."""
        _submit_timed(self.ctx, lambda cmd: self.record(cmd, width, height), dispatches=1)

    def read_output(self, name: str) -> np.ndarray:
        image = self._output_images.get(name)
        if image is None:
            fb_error(f"Compute shader has no @output named '{name}' (or it hasn't been dispatched yet)")
            return None
        _, dtype, channels = IMAGE_FORMATS[self._outputs[name]]
        return np.frombuffer(image.read_raw(channels * 4), dtype=dtype).reshape(
            image.height, image.width, channels).copy()

    def get_output_texture(self, name: str):
        raise NotImplementedError(
            "get_output_texture() isn't available under Vulkan yet - the engine's Texture/material "
            "system is OpenGL-only. Use blit_to_screen() or read_output().")

    def blit_to_screen(self, name: str, size: tuple[int, int] = None):
        """Shows `@output` field `name` in the window, scaled to fill it -
        presented by VulkanRenderer at the end of this frame."""
        image = self._output_images.get(name)
        if image is None:
            fb_error(f"Compute shader has no @output named '{name}' (or it hasn't been dispatched yet)")
            return
        get_service("renderer").present_image(image)

    def destroy(self):
        device = self.ctx.device
        self.ctx.wait_idle()
        for image in self._output_images.values():
            image.destroy()
        if self._uniform_buffer is not None:
            self._uniform_buffer.destroy()
        if self._pool is not None:
            vk.vkDestroyDescriptorPool(device, self._pool, None)
        vk.vkDestroyPipeline(device, self._pipeline, None)
        vk.vkDestroyPipelineLayout(device, self._pipeline_layout, None)
        vk.vkDestroyDescriptorSetLayout(device, self._set_layout, None)
        vk.vkDestroyShaderModule(device, self._module, None)


class VulkanRaytraceShader(VulkanComputeShader):
    """A `@raytrace` kernel with hardware ray tracing: upload_scene() builds
    an acceleration structure from the scene's triangles, and the kernel's
    trace_ray()/trace_shadow() calls become ray queries against it."""

    def __init__(self, source, injector: Injector = None):
        ctx = _context()
        if not ctx.ray_tracing:
            raise RuntimeError(
                f"Raytrace shaders need hardware ray tracing (VK_KHR_acceleration_structure + "
                f"VK_KHR_ray_query), which {ctx.device_name} doesn't support.")
        super().__init__(source, injector, shader_type=ShaderType.RAYTRACE)
        self._scene = []
        self._scene_vertices = None
        self._scene_count = 0

    def upload_scene(self, bvh_aabb, bvh_meta, triangles: np.ndarray):
        """`triangles`: (N, 3, 3) or (N*3, 3) float32 world-space vertex
        positions. `bvh_aabb`/`bvh_meta` are accepted for interface parity
        with the GL backends and ignored - the GPU builds its own BVH - so
        pass None. RayHit.prim is the index of a triangle in `triangles`,
        and RayHit.instance is always 0.

        Calling it again with the same number of triangles - an animated
        scene, every frame - rebuilds in place: the new positions are
        written over the old ones and both acceleration structures are
        rebuilt into their existing memory in one submission, with nothing
        allocated. A different count rebuilds everything from scratch."""
        if "scene" not in self.bindings:
            warning("upload_scene(): this kernel never calls trace_ray() or trace_shadow()")
            return
        ctx = self.ctx
        positions = np.asarray(triangles, dtype=np.float32).reshape(-1, 3)
        count = len(positions) // 3
        if count == 0:
            raise ValueError("upload_scene() needs at least one triangle")
        vertices = np.empty((len(positions), 4), np.float32)
        vertices[:, :3] = positions
        vertices[:, 3] = 1.0

        if count == self._scene_count and self._scene:
            tlas, blas = self._scene[0], self._scene[1]
            # No wait_idle() here: dispatch() waits for its own work, so no
            # trace can still be reading these - and waiting on the whole
            # queue would also wait for the last frame's present, i.e. for
            # vsync, every time the scene moves. (Callers batching through
            # record() submit themselves and must finish that work first.)
            self._scene_vertices.write(vertices.tobytes())

            def rebuild(cmd):
                blas.rebuild(cmd)
                tlas.rebuild(cmd)
            _submit_timed(ctx, rebuild)
            return

        ctx.wait_idle()
        for resource in self._scene:
            resource.destroy()
        vertex_buffer = ctx.buffer_from(vertices.tobytes(), AS_INPUT)
        index_buffer = ctx.buffer_from(np.arange(len(positions), dtype=np.uint32).tobytes(), AS_INPUT)
        blas = build_blas(ctx, vertex_buffer, len(positions), index_buffer, count)
        tlas = build_tlas(ctx, [Instance(blas, np.eye(4, dtype=np.float32), custom_index=0)])
        self._write_descriptor("scene", tlas)
        # The TLAS refers to the BLAS, which was built from these buffers -
        # all of it lives until the next upload.
        self._scene = [tlas, blas, vertex_buffer, index_buffer]
        self._scene_vertices = vertex_buffer
        self._scene_count = count

    def destroy(self):
        self.ctx.wait_idle()
        for resource in self._scene:
            resource.destroy()
        super().destroy()
