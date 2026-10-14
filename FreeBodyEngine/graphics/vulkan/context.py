"""The Vulkan device everything else in graphics/vulkan runs on: instance,
physical-device selection, logical device (Vulkan 1.3, with hardware
ray tracing when the GPU has it), one queue, and buffer/image helpers.

Works with or without a window. Pass a GLFW window handle and it also
creates a presentation surface (see swapchain.py); leave it out and you
get a headless compute device - which is how the shader tests run.

Hardware ray tracing here means VK_KHR_acceleration_structure (the GPU
builds and stores BVHs) plus VK_KHR_ray_query (any shader stage can trace
against them). A device without them still rasterizes and runs compute
shaders; only raytrace shaders need it (`ctx.ray_tracing`), and they say
so rather than quietly falling back - there's no software path.
"""
import types

import vulkan as vk
from vulkan import ffi
from vulkan._vulkan import lib

# The `vulkan` package (1.3.275) defines these two as None - aliases its
# generator never resolved - so they're spelled out from the spec.
BUFFER_USAGE_DEVICE_ADDRESS = 0x00020000      # VK_BUFFER_USAGE_SHADER_DEVICE_ADDRESS_BIT
MEMORY_ALLOCATE_DEVICE_ADDRESS = 0x00000002   # VK_MEMORY_ALLOCATE_DEVICE_ADDRESS_BIT

# Enabled when the device has them: hardware ray tracing for raytrace
# shaders. Rasterizing and compute only need Vulkan 1.3.
RAY_TRACING_EXTENSIONS = [
    "VK_KHR_acceleration_structure",
    "VK_KHR_ray_query",
    "VK_KHR_deferred_host_operations",  # required by acceleration_structure
]
MIN_API_VERSION = (1, 3)


def _api_version(props):
    v = props.apiVersion
    return ((v >> 22) & 0x7F, (v >> 12) & 0x3FF)


def _device_name(props):
    name = props.deviceName
    return name if isinstance(name, str) else ffi.string(name).decode()


def probe():
    """(device name, has ray tracing) for the best Vulkan 1.3 device here,
    or None - no loader, no driver, or no capable GPU. Creates only an
    instance (no device or window), so it's cheap enough to run while
    choosing a renderer."""
    instance = None
    try:
        app_info = vk.VkApplicationInfo(pApplicationName="FreeBodyEngine probe", applicationVersion=1,
                                        pEngineName="FreeBodyEngine", engineVersion=1,
                                        apiVersion=vk.VK_MAKE_VERSION(1, 3, 0))
        instance = vk.vkCreateInstance(vk.VkInstanceCreateInfo(pApplicationInfo=app_info), None)
        best = None
        for device in vk.vkEnumeratePhysicalDevices(instance):
            rank = _rank_device(device)
            if rank is not None and (best is None or rank[0] < best[0]):
                best = rank
        return None if best is None else (best[1], best[2])
    except Exception:
        return None
    finally:
        if instance is not None:
            vk.vkDestroyInstance(instance, None)


def _rank_device(device):
    """(sort key, name, has ray tracing) for a usable device, else None."""
    props = vk.vkGetPhysicalDeviceProperties(device)
    if _api_version(props) < MIN_API_VERSION:
        return None
    wanted = vk.VK_QUEUE_GRAPHICS_BIT | vk.VK_QUEUE_COMPUTE_BIT
    if not any(f.queueFlags & wanted == wanted for f in vk.vkGetPhysicalDeviceQueueFamilyProperties(device)):
        return None
    available = {e.extensionName for e in vk.vkEnumerateDeviceExtensionProperties(device, None)}
    ray_tracing = all(e in available for e in RAY_TRACING_EXTENSIONS)
    order = {vk.VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU: 0, vk.VK_PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU: 1}
    key = (order.get(props.deviceType, 2), 0 if ray_tracing else 1)
    return key, _device_name(props), ray_tracing


def _plain(value):
    """A cffi scalar or fixed array as plain Python (int, float, list)."""
    try:
        return [v for v in value]
    except TypeError:
        return value


class VulkanError(RuntimeError):
    pass


class Buffer:
    """A VkBuffer with its own dedicated allocation. Fine at this scale -
    a path-traced scene has a handful of buffers, not thousands."""

    def __init__(self, ctx: "VulkanContext", size: int, usage: int, host_visible: bool = True):
        self.ctx = ctx
        self.size = max(int(size), 4)
        usage |= BUFFER_USAGE_DEVICE_ADDRESS
        self.handle = vk.vkCreateBuffer(ctx.device, vk.VkBufferCreateInfo(
            size=self.size, usage=usage, sharingMode=vk.VK_SHARING_MODE_EXCLUSIVE), None)
        requirements = vk.vkGetBufferMemoryRequirements(ctx.device, self.handle)
        if host_visible:
            # Prefer memory that's both in VRAM and CPU-mappable (resizable
            # BAR) - a buffer a kernel reads and writes every frame is far
            # faster there than in system RAM across the bus - and fall back
            # to plain host-visible memory where there isn't any, or where
            # that heap is full (without resizable BAR it's only 256 MB).
            host = vk.VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | vk.VK_MEMORY_PROPERTY_HOST_COHERENT_BIT
            candidates = ctx.memory_types(requirements.memoryTypeBits, host | vk.VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT)
            candidates += [i for i in ctx.memory_types(requirements.memoryTypeBits, host) if i not in candidates]
        else:
            candidates = ctx.memory_types(requirements.memoryTypeBits, vk.VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT)
        if not candidates:
            raise VulkanError("no suitable memory type for a buffer")
        flags = vk.VkMemoryAllocateFlagsInfo(flags=MEMORY_ALLOCATE_DEVICE_ADDRESS)
        for n, memory_type in enumerate(candidates):
            try:
                self.memory = vk.vkAllocateMemory(ctx.device, vk.VkMemoryAllocateInfo(
                    pNext=flags, allocationSize=requirements.size, memoryTypeIndex=memory_type), None)
                break
            except vk.VkErrorOutOfDeviceMemory:
                if n == len(candidates) - 1:
                    raise
        vk.vkBindBufferMemory(ctx.device, self.handle, self.memory, 0)
        self.host_visible = host_visible
        self._address = None
        # Mapped once for the buffer's whole life (coherent memory, so no
        # flushes): map/unmap on every write showed up in profiles of
        # buffers updated every frame.
        self._mapped = vk.vkMapMemory(ctx.device, self.memory, 0, self.size, 0) if host_visible else None

    @property
    def address(self) -> int:
        if self._address is None:
            # Straight to the C function: the package's wrapper mistakes the
            # info struct for an output parameter and returns it instead of
            # the address.
            info = vk.VkBufferDeviceAddressInfo(buffer=self.handle)
            self._address = int(lib.vkGetBufferDeviceAddress(self.ctx.device, ffi.addressof(info)))
        return self._address

    def write(self, data, offset: int = 0):
        raw = bytes(data) if not isinstance(data, (bytes, bytearray)) else data
        if len(raw) + offset > self.size:
            raise VulkanError(f"write of {len(raw)} bytes at {offset} overflows a {self.size}-byte buffer")
        self._mapped[offset:offset + len(raw)] = raw

    def read(self, size: int | None = None, offset: int = 0) -> bytes:
        size = self.size - offset if size is None else size
        return bytes(self._mapped[offset:offset + size])

    def destroy(self):
        if self.handle is not None:
            if self._mapped is not None:
                vk.vkUnmapMemory(self.ctx.device, self.memory)
                self._mapped = None
            vk.vkDestroyBuffer(self.ctx.device, self.handle, None)
            vk.vkFreeMemory(self.ctx.device, self.memory, None)
            self.handle = None


class StorageImage:
    """A 2D image a compute shader writes (an FBUSL @output) and the
    presenter blits from. Kept in GENERAL layout for its whole life, which
    is the one layout both of those uses accept."""

    def __init__(self, ctx: "VulkanContext", width: int, height: int, fmt: int = vk.VK_FORMAT_R32G32B32A32_SFLOAT):
        self.ctx = ctx
        self.width, self.height, self.format = width, height, fmt
        self.handle = vk.vkCreateImage(ctx.device, vk.VkImageCreateInfo(
            imageType=vk.VK_IMAGE_TYPE_2D, format=fmt,
            extent=vk.VkExtent3D(width=width, height=height, depth=1),
            mipLevels=1, arrayLayers=1, samples=vk.VK_SAMPLE_COUNT_1_BIT,
            tiling=vk.VK_IMAGE_TILING_OPTIMAL,
            usage=(vk.VK_IMAGE_USAGE_STORAGE_BIT | vk.VK_IMAGE_USAGE_TRANSFER_SRC_BIT
                   | vk.VK_IMAGE_USAGE_TRANSFER_DST_BIT),
            sharingMode=vk.VK_SHARING_MODE_EXCLUSIVE, initialLayout=vk.VK_IMAGE_LAYOUT_UNDEFINED), None)
        requirements = vk.vkGetImageMemoryRequirements(ctx.device, self.handle)
        self.memory = vk.vkAllocateMemory(ctx.device, vk.VkMemoryAllocateInfo(
            allocationSize=requirements.size,
            memoryTypeIndex=ctx.memory_type(requirements.memoryTypeBits, vk.VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT)), None)
        vk.vkBindImageMemory(ctx.device, self.handle, self.memory, 0)
        self.view = vk.vkCreateImageView(ctx.device, vk.VkImageViewCreateInfo(
            image=self.handle, viewType=vk.VK_IMAGE_VIEW_TYPE_2D, format=fmt,
            subresourceRange=ctx.color_range()), None)
        with ctx.commands() as cmd:
            ctx.image_barrier(cmd, self.handle, vk.VK_IMAGE_LAYOUT_UNDEFINED, vk.VK_IMAGE_LAYOUT_GENERAL,
                              0, vk.VK_ACCESS_SHADER_WRITE_BIT,
                              vk.VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, vk.VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT)

    def read_raw(self, bytes_per_pixel: int = 16) -> bytes:
        """Copies the image back to the CPU, tightly packed rows. 16 bytes
        per pixel is rgba32f; pass the format's own size for others."""
        size = self.width * self.height * bytes_per_pixel
        staging = Buffer(self.ctx, size, vk.VK_BUFFER_USAGE_TRANSFER_DST_BIT)
        with self.ctx.commands() as cmd:
            self.ctx.memory_barrier(cmd, vk.VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, vk.VK_PIPELINE_STAGE_TRANSFER_BIT,
                                    vk.VK_ACCESS_SHADER_WRITE_BIT, vk.VK_ACCESS_TRANSFER_READ_BIT)
            vk.vkCmdCopyImageToBuffer(cmd, self.handle, vk.VK_IMAGE_LAYOUT_GENERAL, staging.handle, 1, [
                vk.VkBufferImageCopy(bufferOffset=0, bufferRowLength=0, bufferImageHeight=0,
                                     imageSubresource=self.ctx.color_layers(),
                                     imageOffset=vk.VkOffset3D(0, 0, 0),
                                     imageExtent=vk.VkExtent3D(self.width, self.height, 1))])
        data = staging.read(size)
        staging.destroy()
        return data

    def destroy(self):
        if self.handle is not None:
            vk.vkDestroyImageView(self.ctx.device, self.view, None)
            vk.vkDestroyImage(self.ctx.device, self.handle, None)
            vk.vkFreeMemory(self.ctx.device, self.memory, None)
            self.handle = None


class GpuTimer:
    """Measures how long the GPU spends on one command buffer: a timestamp
    written before and after the work, read back once the submission has
    finished. Every submission in this backend is synchronous (submit,
    then wait), so the result is available as soon as the work is done -
    no in-flight query bookkeeping needed.

        ctx.gpu_timer.begin(cmd); ...record work...; ctx.gpu_timer.end(cmd)
        ...submit and wait...
        nanoseconds = ctx.gpu_timer.read()
    """

    def __init__(self, ctx: "VulkanContext"):
        self.ctx = ctx
        props = vk.vkGetPhysicalDeviceProperties(ctx.physical_device)
        self.period_ns = float(props.limits.timestampPeriod)  # nanoseconds per tick
        family = vk.vkGetPhysicalDeviceQueueFamilyProperties(ctx.physical_device)[ctx.queue_family]
        self.valid_bits = int(family.timestampValidBits)
        self.supported = self.valid_bits > 0 and self.period_ns > 0
        self.pool = None
        if self.supported:
            self.pool = vk.vkCreateQueryPool(ctx.device, vk.VkQueryPoolCreateInfo(
                queryType=vk.VK_QUERY_TYPE_TIMESTAMP, queryCount=2), None)
        self._results = ffi.new("uint64_t[2]")

    def begin(self, cmd):
        if self.supported:
            vk.vkCmdResetQueryPool(cmd, self.pool, 0, 2)
            vk.vkCmdWriteTimestamp(cmd, vk.VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, self.pool, 0)

    def end(self, cmd):
        if self.supported:
            vk.vkCmdWriteTimestamp(cmd, vk.VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT, self.pool, 1)

    def read(self) -> float | None:
        """GPU time between begin() and end(), in nanoseconds, or None if
        the device can't timestamp on this queue."""
        if not self.supported:
            return None
        vk.vkGetQueryPoolResults(self.ctx.device, self.pool, 0, 2, 16, self._results, 8,
                                 vk.VK_QUERY_RESULT_64_BIT | vk.VK_QUERY_RESULT_WAIT_BIT)
        mask = (1 << self.valid_bits) - 1 if self.valid_bits < 64 else (1 << 64) - 1
        ticks = (int(self._results[1]) - int(self._results[0])) & mask
        return ticks * self.period_ns

    def destroy(self):
        if self.pool is not None:
            vk.vkDestroyQueryPool(self.ctx.device, self.pool, None)
            self.pool = None


class _Commands:
    """`with ctx.commands() as cmd:` - records into a fresh command buffer,
    then submits it and waits on exit. For setup work (uploads, builds),
    not per-frame rendering."""

    def __init__(self, ctx):
        self.ctx = ctx

    def __enter__(self):
        ctx = self.ctx
        self.cmd = vk.vkAllocateCommandBuffers(ctx.device, vk.VkCommandBufferAllocateInfo(
            commandPool=ctx.command_pool, level=vk.VK_COMMAND_BUFFER_LEVEL_PRIMARY, commandBufferCount=1))[0]
        vk.vkBeginCommandBuffer(self.cmd, vk.VkCommandBufferBeginInfo(
            flags=vk.VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT))
        return self.cmd

    def __exit__(self, exc_type, *_):
        ctx = self.ctx
        vk.vkEndCommandBuffer(self.cmd)
        if exc_type is None:
            fence = vk.vkCreateFence(ctx.device, vk.VkFenceCreateInfo(), None)
            vk.vkQueueSubmit(ctx.queue, 1, [vk.VkSubmitInfo(commandBufferCount=1, pCommandBuffers=[self.cmd])], fence)
            vk.vkWaitForFences(ctx.device, 1, [fence], vk.VK_TRUE, 0xFFFFFFFFFFFFFFFF)
            vk.vkDestroyFence(ctx.device, fence, None)
        vk.vkFreeCommandBuffers(ctx.device, ctx.command_pool, 1, [self.cmd])


class VulkanContext:
    def __init__(self, glfw_window=None, app_name: str = "FreeBodyEngine"):
        self.surface = None
        self._fns: dict[str, object] = {}

        extensions = []
        if glfw_window is not None:
            import glfw
            extensions = list(glfw.get_required_instance_extensions())
        # Nested structs are kept in variables until the call returns - the
        # package ties the lifetime of a struct's strings and arrays to that
        # struct's own Python object, not to the parent it's copied into.
        app_info = vk.VkApplicationInfo(
            pApplicationName=app_name, applicationVersion=1,
            pEngineName="FreeBodyEngine", engineVersion=1, apiVersion=vk.VK_MAKE_VERSION(1, 3, 0))
        self.instance = vk.vkCreateInstance(vk.VkInstanceCreateInfo(
            pApplicationInfo=app_info,
            enabledExtensionCount=len(extensions), ppEnabledExtensionNames=extensions or None), None)

        if glfw_window is not None:
            self.surface = self._create_surface(glfw_window)

        self.physical_device, self.queue_family, self.ray_tracing = self._pick_device()
        props = vk.vkGetPhysicalDeviceProperties(self.physical_device)
        self.device_name = _device_name(props)
        # Copied out field by field: `props.limits` points into cffi memory
        # the package can free once `props` goes away, after which reads
        # return garbage (an alignment of 2e12 was seen, intermittently).
        self.limits = types.SimpleNamespace(**{
            name: _plain(getattr(props.limits, name)) for name in dir(props.limits)})
        self.memory_properties = vk.vkGetPhysicalDeviceMemoryProperties(self.physical_device)

        device_extensions = list(RAY_TRACING_EXTENSIONS) if self.ray_tracing else []
        if self.surface is not None:
            device_extensions.append("VK_KHR_swapchain")
        ray_query = vk.VkPhysicalDeviceRayQueryFeaturesKHR(rayQuery=vk.VK_TRUE)
        accel = vk.VkPhysicalDeviceAccelerationStructureFeaturesKHR(pNext=ray_query, accelerationStructure=vk.VK_TRUE)
        v12 = vk.VkPhysicalDeviceVulkan12Features(pNext=accel if self.ray_tracing else None,
                                                  bufferDeviceAddress=vk.VK_TRUE)
        # Dynamic rendering (core in 1.3): the rasterizer begins and ends
        # rendering into whatever's bound, the way GL draws into the bound
        # framebuffer - no render pass or VkFramebuffer objects to build.
        v13 = vk.VkPhysicalDeviceVulkan13Features(pNext=v12, dynamicRendering=vk.VK_TRUE)
        # Geometry shaders run natively when the GPU has them; otherwise
        # VulkanShader emulates them (see graphics/vulkan/shader.py).
        self.geometry_shader = bool(vk.vkGetPhysicalDeviceFeatures(self.physical_device).geometryShader)
        core = vk.VkPhysicalDeviceFeatures(geometryShader=vk.VK_TRUE if self.geometry_shader else vk.VK_FALSE)
        features = vk.VkPhysicalDeviceFeatures2(pNext=v13, features=core)
        queue_info = vk.VkDeviceQueueCreateInfo(
            queueFamilyIndex=self.queue_family, queueCount=1, pQueuePriorities=[1.0])
        self.device = vk.vkCreateDevice(self.physical_device, vk.VkDeviceCreateInfo(
            pNext=features,
            queueCreateInfoCount=1,
            pQueueCreateInfos=[queue_info],
            enabledExtensionCount=len(device_extensions), ppEnabledExtensionNames=device_extensions), None)
        self.queue = vk.vkGetDeviceQueue(self.device, self.queue_family, 0)
        self.command_pool = vk.vkCreateCommandPool(self.device, vk.VkCommandPoolCreateInfo(
            flags=vk.VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT, queueFamilyIndex=self.queue_family), None)
        self.gpu_timer = GpuTimer(self)

    # -- setup ---------------------------------------------------------------

    def _create_surface(self, glfw_window):
        import ctypes
        import glfw
        surface = ctypes.c_uint64(0)
        instance_handle = ctypes.c_void_p(int(ffi.cast("uintptr_t", self.instance)))
        result = glfw.create_window_surface(instance_handle, glfw_window, None, ctypes.byref(surface))
        if result != 0:
            raise VulkanError(f"glfwCreateWindowSurface failed ({result})")
        return ffi.cast("VkSurfaceKHR", surface.value)

    def _pick_device(self):
        candidates = []
        for device in vk.vkEnumeratePhysicalDevices(self.instance):
            rank = _rank_device(device)
            if rank is None:
                continue
            for index, family in enumerate(vk.vkGetPhysicalDeviceQueueFamilyProperties(device)):
                wanted = vk.VK_QUEUE_GRAPHICS_BIT | vk.VK_QUEUE_COMPUTE_BIT
                if family.queueFlags & wanted != wanted:
                    continue
                if self.surface is not None and not self.instance_fn("vkGetPhysicalDeviceSurfaceSupportKHR")(
                        device, index, self.surface):
                    continue
                candidates.append((rank[0], device, index, rank[2]))
                break
        if not candidates:
            raise VulkanError("No Vulkan 1.3 device with a graphics+compute queue"
                              + (" that can present to this window" if self.surface is not None else "") + ".")
        candidates.sort(key=lambda c: c[0])
        return candidates[0][1], candidates[0][2], candidates[0][3]

    # -- function loading ----------------------------------------------------

    def instance_fn(self, name: str):
        key = ("i", name)
        if key not in self._fns:
            self._fns[key] = vk.vkGetInstanceProcAddr(self.instance, name)
        return self._fns[key]

    def fn(self, name: str):
        """A device-level extension function (vkCreateAccelerationStructureKHR, ...)."""
        key = ("d", name)
        if key not in self._fns:
            self._fns[key] = vk.vkGetDeviceProcAddr(self.device, name)
        return self._fns[key]

    # -- helpers -------------------------------------------------------------

    def raw_fn(self, name: str):
        """A device function as a bare C function pointer, bypassing the
        package's Python wrapper - for the few whose wrappers are broken
        (the device-address queries; see Buffer.address)."""
        key = ("raw", name)
        if key not in self._fns:
            self._fns[key] = ffi.cast(f"PFN_{name}", lib.vkGetDeviceProcAddr(self.device, name.encode()))
        return self._fns[key]

    def memory_type(self, type_bits: int, props: int, fallback: int | None = None) -> int:
        mp = self.memory_properties
        for wanted in (props, fallback):
            if wanted is None:
                continue
            for i in range(mp.memoryTypeCount):
                if type_bits & (1 << i) and (mp.memoryTypes[i].propertyFlags & wanted) == wanted:
                    return i
        raise VulkanError(f"no memory type with properties {props:#x}")

    def memory_types(self, type_bits: int, props: int) -> list[int]:
        """Every memory type allowed by `type_bits` with all of `props`,
        in the driver's (preference) order."""
        mp = self.memory_properties
        return [i for i in range(mp.memoryTypeCount)
                if type_bits & (1 << i) and (mp.memoryTypes[i].propertyFlags & props) == props]

    def commands(self) -> _Commands:
        return _Commands(self)

    def buffer(self, size: int, usage: int, host_visible: bool = True) -> Buffer:
        return Buffer(self, size, usage, host_visible)

    def buffer_from(self, data: bytes, usage: int) -> Buffer:
        buf = Buffer(self, len(data), usage)
        buf.write(data)
        return buf

    @staticmethod
    def color_range():
        return vk.VkImageSubresourceRange(aspectMask=vk.VK_IMAGE_ASPECT_COLOR_BIT,
                                          baseMipLevel=0, levelCount=1, baseArrayLayer=0, layerCount=1)

    @staticmethod
    def color_layers():
        return vk.VkImageSubresourceLayers(aspectMask=vk.VK_IMAGE_ASPECT_COLOR_BIT,
                                           mipLevel=0, baseArrayLayer=0, layerCount=1)

    def image_barrier(self, cmd, image, old_layout, new_layout, src_access, dst_access, src_stage, dst_stage):
        vk.vkCmdPipelineBarrier(cmd, src_stage, dst_stage, 0, 0, None, 0, None, 1, [vk.VkImageMemoryBarrier(
            srcAccessMask=src_access, dstAccessMask=dst_access, oldLayout=old_layout, newLayout=new_layout,
            srcQueueFamilyIndex=vk.VK_QUEUE_FAMILY_IGNORED, dstQueueFamilyIndex=vk.VK_QUEUE_FAMILY_IGNORED,
            image=image, subresourceRange=self.color_range())])

    def memory_barrier(self, cmd, src_stage, dst_stage, src_access, dst_access):
        vk.vkCmdPipelineBarrier(cmd, src_stage, dst_stage, 0, 1, [vk.VkMemoryBarrier(
            srcAccessMask=src_access, dstAccessMask=dst_access)], 0, None, 0, None)

    def wait_idle(self):
        vk.vkDeviceWaitIdle(self.device)

    def destroy(self):
        if self.device is not None:
            vk.vkDeviceWaitIdle(self.device)
            self.gpu_timer.destroy()
            vk.vkDestroyCommandPool(self.device, self.command_pool, None)
            vk.vkDestroyDevice(self.device, None)
            self.device = None
        if self.surface is not None:
            self.instance_fn("vkDestroySurfaceKHR")(self.instance, self.surface, None)
            self.surface = None
        if self.instance is not None:
            vk.vkDestroyInstance(self.instance, None)
            self.instance = None
