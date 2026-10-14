"""Hardware acceleration structures (VK_KHR_acceleration_structure).

A bottom-level structure (BLAS) is one mesh's triangles, built into
whatever BVH the GPU vendor uses. A top-level structure (TLAS) is the
scene: a list of instances, each a BLAS plus a transform and a custom
index. That custom index is what FBUSL's `RayHit.instance` reports, so a
shader can look the hit object's material and geometry up by it.

    blas = build_blas(ctx, positions_buffer, vertex_count, index_buffer, triangle_count)
    tlas = build_tlas(ctx, [Instance(blas, transform, custom_index=0), ...])

Vertex buffers are read with a 16-byte stride - vec4 positions, xyz used -
so the same buffer can also be bound to a shader as an FBUSL `vec4[]`
buffer field without a second copy.

Each structure keeps its scratch memory and build inputs, so it can be
rebuilt in place - `rebuild(cmd)` re-reads its (possibly rewritten)
vertex or instance buffer into the same storage, with no allocation. That's
what makes animating a scene every frame affordable.
"""
import struct
from dataclasses import dataclass

import numpy as np
import vulkan as vk
from vulkan import ffi

from FreeBodyEngine.graphics.vulkan.context import Buffer

AS_STORAGE = vk.VK_BUFFER_USAGE_ACCELERATION_STRUCTURE_STORAGE_BIT_KHR
AS_INPUT = vk.VK_BUFFER_USAGE_ACCELERATION_STRUCTURE_BUILD_INPUT_READ_ONLY_BIT_KHR
VERTEX_STRIDE = 16


class AccelerationStructure:
    def __init__(self, ctx, handle, buffer: Buffer, level: str, build_info, range_infos, scratch: Buffer,
                 owned_inputs: list):
        self.ctx = ctx
        self.handle = handle
        self.buffer = buffer
        self.level = level
        # Everything a rebuild needs, kept alive with the structure: the
        # build description (whose geometry points at the input buffers by
        # device address), its range, and scratch memory.
        self._build_info = build_info
        self._range_infos = range_infos
        self._scratch = scratch
        self._owned_inputs = owned_inputs
        info = vk.VkAccelerationStructureDeviceAddressInfoKHR(accelerationStructure=handle)
        self.address = int(ctx.raw_fn("vkGetAccelerationStructureDeviceAddressKHR")(ctx.device, ffi.addressof(info)))

    def rebuild(self, cmd):
        """Records a full rebuild into this structure's existing storage,
        from whatever its input buffer holds now. The primitive count must
        not have changed. A TLAS over a rebuilt BLAS has to be rebuilt
        after it, in the same or a later submission."""
        # _range_infos is (the range struct, the pointer array into it) -
        # both kept so the array never points at freed memory.
        _record_build(self.ctx, cmd, self._build_info, self._range_infos[1])

    def destroy(self):
        if self.handle is not None:
            self.ctx.fn("vkDestroyAccelerationStructureKHR")(self.ctx.device, self.handle, None)
            self.buffer.destroy()
            self._scratch.destroy()
            for buf in self._owned_inputs:
                buf.destroy()
            self.handle = None


@dataclass
class Instance:
    blas: AccelerationStructure
    transform: np.ndarray  # 4x4 or 3x4, row-major, object -> world
    custom_index: int = 0
    mask: int = 0xFF


def _scratch_alignment(ctx) -> int:
    if not hasattr(ctx, "_as_scratch_alignment"):
        accel_props = vk.VkPhysicalDeviceAccelerationStructurePropertiesKHR()
        vk.vkGetPhysicalDeviceProperties2(ctx.physical_device, vk.VkPhysicalDeviceProperties2(pNext=accel_props))
        ctx._as_scratch_alignment = max(int(accel_props.minAccelerationStructureScratchOffsetAlignment), 1)
    return ctx._as_scratch_alignment


def _record_build(ctx, cmd, build_info, range_infos):
    ctx.fn("vkCmdBuildAccelerationStructuresKHR")(cmd, 1, [build_info], range_infos)
    # Later builds (a TLAS over this BLAS) and shaders read the result.
    ctx.memory_barrier(cmd, vk.VK_PIPELINE_STAGE_ACCELERATION_STRUCTURE_BUILD_BIT_KHR,
                       vk.VK_PIPELINE_STAGE_ACCELERATION_STRUCTURE_BUILD_BIT_KHR | vk.VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,
                       vk.VK_ACCESS_ACCELERATION_STRUCTURE_WRITE_BIT_KHR,
                       vk.VK_ACCESS_ACCELERATION_STRUCTURE_READ_BIT_KHR)


def _build(ctx, as_type: int, geometry, primitive_count: int, level: str, owned_inputs=()) -> AccelerationStructure:
    device = ctx.device
    build_info = vk.VkAccelerationStructureBuildGeometryInfoKHR(
        type=as_type,
        flags=vk.VK_BUILD_ACCELERATION_STRUCTURE_PREFER_FAST_TRACE_BIT_KHR,
        mode=vk.VK_BUILD_ACCELERATION_STRUCTURE_MODE_BUILD_KHR,
        geometryCount=1, pGeometries=[geometry])
    sizes = ctx.fn("vkGetAccelerationStructureBuildSizesKHR")(
        device, vk.VK_ACCELERATION_STRUCTURE_BUILD_TYPE_DEVICE_KHR, build_info,
        ffi.new("uint32_t[]", [primitive_count]))

    storage = Buffer(ctx, sizes.accelerationStructureSize, AS_STORAGE, host_visible=False)
    handle = ctx.fn("vkCreateAccelerationStructureKHR")(device, vk.VkAccelerationStructureCreateInfoKHR(
        buffer=storage.handle, size=sizes.accelerationStructureSize, type=as_type), None)

    align = _scratch_alignment(ctx)
    scratch = Buffer(ctx, sizes.buildScratchSize + align, vk.VK_BUFFER_USAGE_STORAGE_BUFFER_BIT, host_visible=False)
    scratch_address = -(-scratch.address // align) * align

    build_info.dstAccelerationStructure = handle
    build_info.scratchData = vk.VkDeviceOrHostAddressKHR(deviceAddress=scratch_address)
    range_info = ffi.new("VkAccelerationStructureBuildRangeInfoKHR*", {
        "primitiveCount": primitive_count, "primitiveOffset": 0, "firstVertex": 0, "transformOffset": 0})
    range_infos = ffi.new("VkAccelerationStructureBuildRangeInfoKHR*[]", [range_info])

    with ctx.commands() as cmd:
        _record_build(ctx, cmd, build_info, range_infos)
    # `geometry` is copied into build_info's array but its own Python
    # object owns nothing build_info needs, so build_info alone is kept.
    return AccelerationStructure(ctx, handle, storage, level, build_info, (range_info, range_infos), scratch,
                                 list(owned_inputs))


def build_blas(ctx, vertices: Buffer, vertex_count: int, indices: Buffer, triangle_count: int,
               first_vertex: int = 0, first_index: int = 0) -> AccelerationStructure:
    """`vertices`: vec4 positions (16-byte stride, w ignored). `indices`:
    uint32, three per triangle, relative to `first_vertex`. Both need
    AS_INPUT in their usage. The offsets let many meshes share one pair of
    buffers - the same pair the shader reads normals and indices from."""
    triangles = vk.VkAccelerationStructureGeometryTrianglesDataKHR(
        vertexFormat=vk.VK_FORMAT_R32G32B32_SFLOAT,
        vertexData=vk.VkDeviceOrHostAddressConstKHR(deviceAddress=vertices.address + first_vertex * VERTEX_STRIDE),
        vertexStride=VERTEX_STRIDE, maxVertex=max(vertex_count - 1, 0),
        indexType=vk.VK_INDEX_TYPE_UINT32,
        indexData=vk.VkDeviceOrHostAddressConstKHR(deviceAddress=indices.address + first_index * 4))
    geometry = vk.VkAccelerationStructureGeometryKHR(
        geometryType=vk.VK_GEOMETRY_TYPE_TRIANGLES_KHR,
        geometry=vk.VkAccelerationStructureGeometryDataKHR(triangles=triangles),
        flags=vk.VK_GEOMETRY_OPAQUE_BIT_KHR)
    return _build(ctx, vk.VK_ACCELERATION_STRUCTURE_TYPE_BOTTOM_LEVEL_KHR, geometry, triangle_count, "bottom")


def pack_instances(instances: list[Instance]) -> bytes:
    """VkAccelerationStructureInstanceKHR, 64 bytes each: a row-major 3x4
    transform, then customIndex:24|mask:8, sbtOffset:24|flags:8, and the
    BLAS's device address."""
    flags = vk.VK_GEOMETRY_INSTANCE_TRIANGLE_FACING_CULL_DISABLE_BIT_KHR
    out = bytearray()
    for inst in instances:
        m = np.asarray(inst.transform, dtype=np.float32)
        m = m[:3, :4] if m.shape == (4, 4) else m.reshape(3, 4)
        out += m.tobytes()
        out += struct.pack("<IIQ", (inst.custom_index & 0xFFFFFF) | ((inst.mask & 0xFF) << 24),
                           (flags & 0xFF) << 24, inst.blas.address)
    return bytes(out)


def build_tlas(ctx, instances: list[Instance]) -> AccelerationStructure:
    data = pack_instances(instances)
    instance_buffer = ctx.buffer_from(data, AS_INPUT)
    geometry = vk.VkAccelerationStructureGeometryKHR(
        geometryType=vk.VK_GEOMETRY_TYPE_INSTANCES_KHR,
        geometry=vk.VkAccelerationStructureGeometryDataKHR(
            instances=vk.VkAccelerationStructureGeometryInstancesDataKHR(
                arrayOfPointers=vk.VK_FALSE,
                data=vk.VkDeviceOrHostAddressConstKHR(deviceAddress=instance_buffer.address))),
        flags=vk.VK_GEOMETRY_OPAQUE_BIT_KHR)
    # The instance buffer stays with the TLAS - a rebuild reads it again.
    return _build(ctx, vk.VK_ACCELERATION_STRUCTURE_TYPE_TOP_LEVEL_KHR, geometry, len(instances), "top",
                  owned_inputs=[instance_buffer])
