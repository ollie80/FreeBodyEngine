"""Getting frames on screen: a VkSwapchainKHR on the window's surface.

The renderer never draws into swapchain images directly. Each frame it
records its own work (a compute dispatch writing a StorageImage), and
`Presenter.present()` blits that image into whichever swapchain image the
window gave us, converting the float result to the display's 8-bit format
on the way, then presents it. A blit is all a path tracer needs - there's
no rasterization here to want a render pass for.

One frame in flight: present() waits for the previous frame's fence
before recording the next. A path tracer is GPU-bound, so overlapping CPU
recording with the GPU would buy nothing measurable.
"""
import vulkan as vk

from FreeBodyEngine.graphics.vulkan.context import VulkanError

UINT64_MAX = 0xFFFFFFFFFFFFFFFF


class Presenter:
    def __init__(self, ctx, size: tuple[int, int], vsync: bool = True):
        self.ctx = ctx
        self.vsync = vsync
        self.swapchain = None
        self.images = []
        self.extent = (0, 0)
        device = ctx.device
        self.cmd = vk.vkAllocateCommandBuffers(device, vk.VkCommandBufferAllocateInfo(
            commandPool=ctx.command_pool, level=vk.VK_COMMAND_BUFFER_LEVEL_PRIMARY, commandBufferCount=1))[0]
        self.image_available = vk.vkCreateSemaphore(device, vk.VkSemaphoreCreateInfo(), None)
        self.render_finished: list = []
        self.fence = vk.vkCreateFence(device, vk.VkFenceCreateInfo(flags=vk.VK_FENCE_CREATE_SIGNALED_BIT), None)
        self._create(size)

    # -- swapchain -----------------------------------------------------------

    def _choose_format(self):
        formats = self.ctx.instance_fn("vkGetPhysicalDeviceSurfaceFormatsKHR")(self.ctx.physical_device, self.ctx.surface)
        for f in formats:
            if f.format == vk.VK_FORMAT_B8G8R8A8_UNORM and f.colorSpace == vk.VK_COLOR_SPACE_SRGB_NONLINEAR_KHR:
                return f
        return formats[0]

    def _create(self, size):
        ctx = self.ctx
        caps = ctx.instance_fn("vkGetPhysicalDeviceSurfaceCapabilitiesKHR")(ctx.physical_device, ctx.surface)
        if caps.currentExtent.width != 0xFFFFFFFF:
            width, height = caps.currentExtent.width, caps.currentExtent.height
        else:
            width = min(max(size[0], caps.minImageExtent.width), caps.maxImageExtent.width)
            height = min(max(size[1], caps.minImageExtent.height), caps.maxImageExtent.height)
        if width == 0 or height == 0:
            return  # minimized - try again next frame
        surface_format = self._choose_format()
        self.format = surface_format.format

        modes = ctx.instance_fn("vkGetPhysicalDeviceSurfacePresentModesKHR")(ctx.physical_device, ctx.surface)
        mode = vk.VK_PRESENT_MODE_FIFO_KHR
        if not self.vsync:
            for preferred in (vk.VK_PRESENT_MODE_MAILBOX_KHR, vk.VK_PRESENT_MODE_IMMEDIATE_KHR):
                if preferred in modes:
                    mode = preferred
                    break

        image_count = caps.minImageCount + 1
        if caps.maxImageCount:
            image_count = min(image_count, caps.maxImageCount)

        old = self.swapchain
        self.swapchain = ctx.fn("vkCreateSwapchainKHR")(ctx.device, vk.VkSwapchainCreateInfoKHR(
            surface=ctx.surface, minImageCount=image_count, imageFormat=surface_format.format,
            imageColorSpace=surface_format.colorSpace,
            imageExtent=vk.VkExtent2D(width=width, height=height), imageArrayLayers=1,
            imageUsage=vk.VK_IMAGE_USAGE_TRANSFER_DST_BIT | vk.VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT,
            imageSharingMode=vk.VK_SHARING_MODE_EXCLUSIVE, preTransform=caps.currentTransform,
            compositeAlpha=vk.VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR, presentMode=mode, clipped=vk.VK_TRUE,
            oldSwapchain=old), None)
        if old is not None:
            ctx.fn("vkDestroySwapchainKHR")(ctx.device, old, None)
        self.images = ctx.fn("vkGetSwapchainImagesKHR")(ctx.device, self.swapchain)
        for semaphore in self.render_finished:
            vk.vkDestroySemaphore(ctx.device, semaphore, None)
        # One per swapchain image: a semaphore handed to vkQueuePresentKHR
        # can't safely be reused until that image comes round again.
        self.render_finished = [vk.vkCreateSemaphore(ctx.device, vk.VkSemaphoreCreateInfo(), None)
                                for _ in self.images]
        self.extent = (width, height)

    def recreate(self, size):
        device = self.ctx.device
        vk.vkDeviceWaitIdle(device)
        # An acquire that reported SUBOPTIMAL still signalled this semaphore,
        # and nothing will now wait on it - a fresh one avoids handing an
        # already-signalled semaphore to the next acquire.
        vk.vkDestroySemaphore(device, self.image_available, None)
        self.image_available = vk.vkCreateSemaphore(device, vk.VkSemaphoreCreateInfo(), None)
        self._create(size)

    # -- frames --------------------------------------------------------------

    def acquire(self, window_size):
        """The index of the next swapchain image, or None when there isn't
        one to draw into this frame (minimized, or the swapchain just had
        to be rebuilt). Its readiness is signalled on image_available."""
        ctx = self.ctx
        if self.extent == (0, 0) or self.swapchain is None:
            self.recreate(window_size)
            return None
        try:
            return ctx.fn("vkAcquireNextImageKHR")(ctx.device, self.swapchain, UINT64_MAX,
                                                    self.image_available, None)
        except (vk.VkErrorOutOfDateKhr, vk.VkSuboptimalKhr):
            self.recreate(window_size)
            return None

    def submit_and_present(self, cmd, index, window_size, fence):
        """Submits `cmd` (which must leave swapchain image `index` in
        PRESENT_SRC), presents it, and waits for `fence`."""
        ctx = self.ctx
        finished = self.render_finished[index]
        submit = vk.VkSubmitInfo(
            waitSemaphoreCount=1, pWaitSemaphores=[self.image_available],
            pWaitDstStageMask=[vk.VK_PIPELINE_STAGE_TRANSFER_BIT],
            commandBufferCount=1, pCommandBuffers=[cmd],
            signalSemaphoreCount=1, pSignalSemaphores=[finished])
        vk.vkQueueSubmit(ctx.queue, 1, [submit], fence)
        present_info = vk.VkPresentInfoKHR(
            waitSemaphoreCount=1, pWaitSemaphores=[finished],
            swapchainCount=1, pSwapchains=[self.swapchain], pImageIndices=[index])
        try:
            ctx.fn("vkQueuePresentKHR")(ctx.queue, present_info)
        except (vk.VkErrorOutOfDateKhr, vk.VkSuboptimalKhr):
            vk.vkWaitForFences(ctx.device, 1, [fence], vk.VK_TRUE, UINT64_MAX)
            self.recreate(window_size)
            return
        vk.vkWaitForFences(ctx.device, 1, [fence], vk.VK_TRUE, UINT64_MAX)

    def present(self, record, source, window_size) -> bool:
        """Records `record(cmd)` (the frame's own GPU work), blits `source`
        (a StorageImage the work wrote) to the screen, and presents.
        Returns False when the frame was skipped (minimized, or the
        swapchain had to be rebuilt)."""
        ctx = self.ctx
        device = ctx.device
        if self.extent == (0, 0) or self.swapchain is None:
            self.recreate(window_size)
            return False

        vk.vkWaitForFences(device, 1, [self.fence], vk.VK_TRUE, UINT64_MAX)
        try:
            index = ctx.fn("vkAcquireNextImageKHR")(device, self.swapchain, UINT64_MAX,
                                                     self.image_available, None)
        except (vk.VkErrorOutOfDateKhr, vk.VkSuboptimalKhr):
            self.recreate(window_size)
            return False
        vk.vkResetFences(device, 1, [self.fence])

        cmd = self.cmd
        vk.vkResetCommandBuffer(cmd, 0)
        vk.vkBeginCommandBuffer(cmd, vk.VkCommandBufferBeginInfo(flags=vk.VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT))
        record(cmd)

        target = self.images[index]
        ctx.memory_barrier(cmd, vk.VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, vk.VK_PIPELINE_STAGE_TRANSFER_BIT,
                           vk.VK_ACCESS_SHADER_WRITE_BIT, vk.VK_ACCESS_TRANSFER_READ_BIT)
        ctx.image_barrier(cmd, target, vk.VK_IMAGE_LAYOUT_UNDEFINED, vk.VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
                          0, vk.VK_ACCESS_TRANSFER_WRITE_BIT,
                          vk.VK_PIPELINE_STAGE_TRANSFER_BIT, vk.VK_PIPELINE_STAGE_TRANSFER_BIT)
        w, h = self.extent
        blit = vk.VkImageBlit(
            srcSubresource=ctx.color_layers(),
            srcOffsets=[vk.VkOffset3D(0, 0, 0), vk.VkOffset3D(source.width, source.height, 1)],
            dstSubresource=ctx.color_layers(),
            dstOffsets=[vk.VkOffset3D(0, 0, 0), vk.VkOffset3D(w, h, 1)])
        vk.vkCmdBlitImage(cmd, source.handle, vk.VK_IMAGE_LAYOUT_GENERAL, target,
                          vk.VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, [blit], vk.VK_FILTER_LINEAR)
        ctx.image_barrier(cmd, target, vk.VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, vk.VK_IMAGE_LAYOUT_PRESENT_SRC_KHR,
                          vk.VK_ACCESS_TRANSFER_WRITE_BIT, 0,
                          vk.VK_PIPELINE_STAGE_TRANSFER_BIT, vk.VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT)
        # The source is written again next frame - make that wait for this
        # blit's read.
        ctx.memory_barrier(cmd, vk.VK_PIPELINE_STAGE_TRANSFER_BIT, vk.VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,
                           vk.VK_ACCESS_TRANSFER_READ_BIT, vk.VK_ACCESS_SHADER_WRITE_BIT)
        vk.vkEndCommandBuffer(cmd)

        finished = self.render_finished[index]
        submit = vk.VkSubmitInfo(
            waitSemaphoreCount=1, pWaitSemaphores=[self.image_available],
            pWaitDstStageMask=[vk.VK_PIPELINE_STAGE_TRANSFER_BIT],
            commandBufferCount=1, pCommandBuffers=[cmd],
            signalSemaphoreCount=1, pSignalSemaphores=[finished])
        vk.vkQueueSubmit(ctx.queue, 1, [submit], self.fence)

        present_info = vk.VkPresentInfoKHR(
            waitSemaphoreCount=1, pWaitSemaphores=[finished],
            swapchainCount=1, pSwapchains=[self.swapchain], pImageIndices=[index])
        try:
            ctx.fn("vkQueuePresentKHR")(ctx.queue, present_info)
        except (vk.VkErrorOutOfDateKhr, vk.VkSuboptimalKhr):
            self.recreate(window_size)
        # Wait for the blit before returning: the image it reads is a
        # kernel's @output, and the next frame's dispatch writes that same
        # image - possibly before this blit has run, if left in flight.
        vk.vkWaitForFences(device, 1, [self.fence], vk.VK_TRUE, UINT64_MAX)
        return True

    def destroy(self):
        device = self.ctx.device
        vk.vkDeviceWaitIdle(device)
        for semaphore in self.render_finished:
            vk.vkDestroySemaphore(device, semaphore, None)
        vk.vkDestroySemaphore(device, self.image_available, None)
        vk.vkDestroyFence(device, self.fence, None)
        if self.swapchain is not None:
            self.ctx.fn("vkDestroySwapchainKHR")(device, self.swapchain, None)
            self.swapchain = None
