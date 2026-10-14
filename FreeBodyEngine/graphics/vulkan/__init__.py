"""Vulkan backend: a full renderer (meshes, materials, framebuffers,
textures, text, UI) plus the compute and raytrace API.

Chosen automatically on Windows and Linux when a Vulkan 1.3 GPU is present
(fb.graphics.use_vulkan()), or forced with
`fb.set_flag(fb.FORCE_RENDERER, "vulkan")`; GL is the fallback. Under it,
fb.graphics.create_compute_shader() / create_raytrace_shader() /
create_compute_buffer() return the implementations in compute.py, with the
same interface as the GL backends - and raytrace shaders get real hardware
ray tracing on GPUs that have it.

    generator.py   FBUSL -> SPIR-V (no external shader compiler)
    spirv.py       the SPIR-V module format
    context.py     device with VK_KHR_acceleration_structure + ray_query
    accel.py       acceleration structures (what trace_ray traces against)
    compute.py     VulkanComputeShader / VulkanRaytraceShader / buffers
    swapchain.py   the window's swapchain
    image.py       GPU images, layouts, uploads
    texture.py     VulkanTextureManager
    framebuffer.py VulkanFramebuffer
    mesh.py        VulkanMesh
    shader.py      VulkanShader (vertex + fragment)
    renderer.py    VulkanRenderer, the 'renderer' service
"""
