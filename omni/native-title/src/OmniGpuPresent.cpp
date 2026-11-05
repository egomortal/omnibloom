// SPDX-License-Identifier: GPL-3.0-or-later
// OMNI_GPU_PRESENT_V1 (GPU Stage A part 2, omni-native-s2-gpu, v5): Omni's frames go to the screen through RADV
// Vulkan (VK_KHR_display + swapchain) instead of SDL's CPU tiling + sceVideoOut flip. Title-side module.
//
// How it plugs in without touching the shell (OmniBrowser.cpp):
//  - the title link wraps SDL_Init, SDL_Quit, SDL_UpdateWindowSurface and SDL_UpdateWindowSurfaceRects;
//  - SDL's own sceVideoOut* references are renamed to omni_gp_sceVideoOut* in the title's copy of the SDL
//    archive (llvm-objcopy --redefine-sym, prep.py): with the GPU present active they are inert stand-ins, so
//    SDL never opens VideoOut (RADV owns it); otherwise they call the real functions unchanged;
//  - the hole-punch (OmniHwService.cpp) asks omni_gpu_present_stage_video() to copy the video runs of the
//    frame on the GPU (from the pinned layer) instead of writing them with the CPU.
//
// Off unless /data/omni/gpu-present.flag exists. Every check (instance, display, plane, swapchain, formats,
// blit support, a first black frame) runs in SDL_Init before SDL opens anything; any failure tears Vulkan
// down and SDL's present runs exactly as before. Flag words (optional):
//   mailbox      MAILBOX present mode when offered (default FIFO: Omni's pacing assumes a flip per vblank)
//   out=match    (default) the display mode equal to the canvas when listed, else the largest; GPU scales
//   out=2160 / out=1080 / out=1440   that output height when listed (canvas scaled by the GPU)
//   novideo      the CPU keeps writing the video into the frame (GPU present only)
//   noverify     skip the differential check of the first frames
//   import / staging   force the frame source (default: import the SDL surface, staging copy on failure)
// Log: /data/omni/native/gpu-present.log.
#include <vulkan/vulkan.h>

#include <algorithm>
#include <atomic>
#include <cerrno>
#include <cmath>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <string>
#include <thread>
#include <time.h>
#include <signal.h>
#include <unistd.h>
#include <vector>

#pragma GCC diagnostic ignored "-Wmissing-field-initializers"

#ifdef OMNI_GPU_PRESENT_HOST_TEST
#define OMNI_GP_PROC(instance, name) vkGetInstanceProcAddr(instance, name)
static const char* const kLogPath = "gpu-present.log";
static const char* const kFlagPath = "gpu-present.flag";
#else
extern "C" VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL vk_icdGetInstanceProcAddr(VkInstance, const char*) __attribute__((weak));
#define OMNI_GP_PROC(instance, name) (vk_icdGetInstanceProcAddr ? vk_icdGetInstanceProcAddr(instance, name) : nullptr)
static const char* const kLogPath = "/data/omni/native/gpu-present.log";
static const char* const kFlagPath = "/data/omni/gpu-present.flag";
#endif

namespace {

double nowMs() { timespec ts {}; clock_gettime(CLOCK_MONOTONIC, &ts); return ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6; }

std::mutex g_logLock;
void plog(bool sync, const char* fmt, ...) __attribute__((format(printf, 2, 3)));
void plog(bool sync, const char* fmt, ...)
{
    char line[1200];
    va_list ap; va_start(ap, fmt); vsnprintf(line, sizeof line, fmt, ap); va_end(ap);
    std::lock_guard<std::mutex> l(g_logLock);
    if (FILE* f = fopen(kLogPath, "a")) {
        fprintf(f, "[%10.3f] %s\n", nowMs() / 1000.0, line);
        fflush(f); if (sync) fsync(fileno(f)); fclose(f);
    }
    fprintf(stderr, "gpu-present: %s\n", line);
}

#define VKFN(name) PFN_##name name = nullptr
struct Api {
    VKFN(vkEnumerateInstanceExtensionProperties); VKFN(vkCreateInstance); VKFN(vkDestroyInstance);
    VKFN(vkEnumeratePhysicalDevices); VKFN(vkGetPhysicalDeviceProperties); VKFN(vkGetPhysicalDeviceProperties2);
    VKFN(vkGetPhysicalDeviceMemoryProperties); VKFN(vkGetPhysicalDeviceQueueFamilyProperties); VKFN(vkGetPhysicalDeviceFormatProperties);
    VKFN(vkEnumerateDeviceExtensionProperties); VKFN(vkCreateDevice); VKFN(vkGetDeviceProcAddr);
    // display / surface (instance level)
    VKFN(vkGetPhysicalDeviceDisplayPropertiesKHR); VKFN(vkGetDisplayModePropertiesKHR); VKFN(vkGetPhysicalDeviceDisplayPlanePropertiesKHR);
    VKFN(vkGetDisplayPlaneSupportedDisplaysKHR); VKFN(vkGetDisplayPlaneCapabilitiesKHR); VKFN(vkCreateDisplayPlaneSurfaceKHR);
    VKFN(vkDestroySurfaceKHR); VKFN(vkGetPhysicalDeviceSurfaceSupportKHR); VKFN(vkGetPhysicalDeviceSurfaceCapabilitiesKHR);
    VKFN(vkGetPhysicalDeviceSurfaceFormatsKHR); VKFN(vkGetPhysicalDeviceSurfacePresentModesKHR);
    // device level
    VKFN(vkDestroyDevice); VKFN(vkDeviceWaitIdle); VKFN(vkGetDeviceQueue); VKFN(vkCreateCommandPool); VKFN(vkDestroyCommandPool);
    VKFN(vkAllocateCommandBuffers); VKFN(vkResetCommandBuffer); VKFN(vkBeginCommandBuffer); VKFN(vkEndCommandBuffer);
    VKFN(vkCmdPipelineBarrier); VKFN(vkCmdCopyBufferToImage); VKFN(vkCmdCopyImageToBuffer); VKFN(vkCmdBlitImage); VKFN(vkCmdClearColorImage);
    VKFN(vkCmdResetQueryPool); VKFN(vkCmdWriteTimestamp); VKFN(vkCreateQueryPool); VKFN(vkDestroyQueryPool); VKFN(vkGetQueryPoolResults);
    VKFN(vkCreateFence); VKFN(vkDestroyFence); VKFN(vkResetFences); VKFN(vkWaitForFences); VKFN(vkGetFenceStatus);
    VKFN(vkCreateSemaphore); VKFN(vkDestroySemaphore); VKFN(vkQueueSubmit);
    VKFN(vkCreateBuffer); VKFN(vkDestroyBuffer); VKFN(vkGetBufferMemoryRequirements); VKFN(vkCreateImage); VKFN(vkDestroyImage);
    VKFN(vkGetImageMemoryRequirements); VKFN(vkAllocateMemory); VKFN(vkFreeMemory); VKFN(vkBindBufferMemory); VKFN(vkBindImageMemory);
    VKFN(vkMapMemory); VKFN(vkUnmapMemory); VKFN(vkInvalidateMappedMemoryRanges); VKFN(vkGetMemoryHostPointerPropertiesEXT);
    VKFN(vkCreateSwapchainKHR); VKFN(vkDestroySwapchainKHR); VKFN(vkGetSwapchainImagesKHR); VKFN(vkAcquireNextImageKHR); VKFN(vkQueuePresentKHR);
    VKFN(vkWaitForPresentKHR);
};

struct Buf { VkBuffer buffer = VK_NULL_HANDLE; VkDeviceMemory memory = VK_NULL_HANDLE; VkDeviceSize size = 0; void* mapped = nullptr; bool coherent = true; bool imported = false; };
struct Img { VkImage image = VK_NULL_HANDLE; VkDeviceMemory memory = VK_NULL_HANDLE; uint32_t w = 0, h = 0; VkFormat format = VK_FORMAT_UNDEFINED; VkImageLayout layout = VK_IMAGE_LAYOUT_UNDEFINED; };

// The video runs the hole-punch staged for the next present (OmniHwService.cpp, presenter thread).
struct VideoStage {
    bool valid = false;
    const uint8_t* px = nullptr; size_t bytes = 0; int stride = 0, lx = 0, ly = 0, w = 0, h = 0;
    std::vector<uint32_t> runs;   // y, x, n triplets, canvas coordinates
    void (*release)(void*) = nullptr; void* cookie = nullptr;
};

enum State { kOff = 0, kActive = 1, kFailed = 2, kStopped = 3 };

struct Gp {
    std::atomic<int> state { kOff };
    std::atomic<bool> signalClose { false }, torndown { false };
    std::mutex lock;
    Api vk;
    VkInstance instance = VK_NULL_HANDLE; VkPhysicalDevice physical = VK_NULL_HANDLE; VkDevice device = VK_NULL_HANDLE;
    VkQueue queue = VK_NULL_HANDLE; uint32_t family = 0;
    VkPhysicalDeviceMemoryProperties mem {};
    VkDeviceSize importAlign = 0; bool hostImport = false; bool presentWait = false;
    double timestampNs = 0; bool timers = true;
    // display
    VkSurfaceKHR surface = VK_NULL_HANDLE; VkSwapchainKHR swapchain = VK_NULL_HANDLE;
    std::vector<VkImage> images; std::vector<VkImageLayout> imageLayouts;
    VkFormat swapFormat = VK_FORMAT_UNDEFINED; VkExtent2D extent {}; VkPresentModeKHR presentMode = VK_PRESENT_MODE_FIFO_KHR;
    uint32_t acquired = UINT32_MAX; uint64_t presentId = 0;
    VkFence acquireFence = VK_NULL_HANDLE, submitFence = VK_NULL_HANDLE; VkSemaphore renderDone = VK_NULL_HANDLE;
    VkCommandPool pool = VK_NULL_HANDLE; VkCommandBuffer cmd = VK_NULL_HANDLE;
    VkQueryPool queries = VK_NULL_HANDLE; int queryPair = 0; bool queryPending[2] = { false, false };
    // canvas
    Img canvas; VkFormat canvasFormat = VK_FORMAT_R8G8B8A8_UNORM;
    Buf staging;   // persistent upload buffer (presents are synchronous: one is enough; kept, never per-upload)
    Buf readback;  // differential check
    // options
    bool optMailbox = false, optVideo = true, optVerify = true, optForceStaging = false, optForceImport = false;
    int optOutHeight = 0;   // 0 = match canvas
    int canvasHintW = 1920, canvasHintH = 1080;
    VideoStage video;
    // checks / statistics
    int verifyPlain = 0, verifyVideo = 0;
    uint64_t presents = 0, imports = 0, importFails = 0, stagingCopies = 0, videoFrames = 0, videoRuns = 0;
    double sumCpu = 0, sumWait = 0, sumGpu = 0, maxCpu = 0, maxWait = 0, windowStart = 0; unsigned windowN = 0, windowLogs = 0, importFailLogs = 0;
    // live objects (lesson 8)
    long liveBuffers = 0, liveImages = 0, liveMemory = 0; double liveOwnMiB = 0, liveImportMiB = 0;
    bool hung = false;
    std::thread reaper;
    std::atomic<int64_t> presentSinceUs { 0 };   // watchdog: a present call in progress since (0 = none)
};
Gp g;

template <class T> bool loadI(VkInstance i, T& fn, const char* name) { fn = reinterpret_cast<T>(OMNI_GP_PROC(i, name)); return fn != nullptr; }
template <class T> bool loadD(T& fn, const char* name) { fn = reinterpret_cast<T>(g.vk.vkGetDeviceProcAddr(g.device, name)); if (!fn) plog(false, "device entry point %s missing", name); return fn != nullptr; }

int findMemory(uint32_t bits, VkMemoryPropertyFlags want)
{
    for (uint32_t i = 0; i < g.mem.memoryTypeCount; ++i)
        if ((bits & (1u << i)) && (g.mem.memoryTypes[i].propertyFlags & want) == want) return int(i);
    return -1;
}

void freeBuf(Buf& b)
{
    if (!g.device) { b = Buf {}; return; }
    if (b.mapped) g.vk.vkUnmapMemory(g.device, b.memory);
    if (b.buffer) { g.vk.vkDestroyBuffer(g.device, b.buffer, nullptr); g.liveBuffers--; }
    if (b.memory) { g.vk.vkFreeMemory(g.device, b.memory, nullptr); g.liveMemory--; (b.imported ? g.liveImportMiB : g.liveOwnMiB) -= b.size / 1048576.0; }
    b = Buf {};
}
void freeImg(Img& m)
{
    if (!g.device) { m = Img {}; return; }
    if (m.image) { g.vk.vkDestroyImage(g.device, m.image, nullptr); g.liveImages--; }
    if (m.memory) { g.vk.vkFreeMemory(g.device, m.memory, nullptr); g.liveMemory--; g.liveOwnMiB -= double(m.w) * m.h * 4 / 1048576.0; }
    m = Img {};
}

bool makeHostBuffer(Buf& b, VkDeviceSize size, bool readBack, VkBufferUsageFlags usage)
{
    VkBufferCreateInfo bi { VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO };
    bi.size = size; bi.usage = usage; bi.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
    if (g.vk.vkCreateBuffer(g.device, &bi, nullptr, &b.buffer) != VK_SUCCESS) return false;
    g.liveBuffers++;
    VkMemoryRequirements req {}; g.vk.vkGetBufferMemoryRequirements(g.device, b.buffer, &req);
    int type = readBack ? findMemory(req.memoryTypeBits, VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_CACHED_BIT) : -1;
    if (type < 0) type = findMemory(req.memoryTypeBits, VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
    if (type < 0) type = findMemory(req.memoryTypeBits, VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT);
    if (type < 0) { freeBuf(b); return false; }
    VkMemoryAllocateInfo ai { VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO }; ai.allocationSize = req.size; ai.memoryTypeIndex = uint32_t(type);
    if (g.vk.vkAllocateMemory(g.device, &ai, nullptr, &b.memory) != VK_SUCCESS) { freeBuf(b); return false; }
    g.liveMemory++; b.size = size; g.liveOwnMiB += size / 1048576.0;
    if (g.vk.vkBindBufferMemory(g.device, b.buffer, b.memory, 0) != VK_SUCCESS || g.vk.vkMapMemory(g.device, b.memory, 0, VK_WHOLE_SIZE, 0, &b.mapped) != VK_SUCCESS) { freeBuf(b); return false; }
    b.coherent = g.mem.memoryTypes[type].propertyFlags & VK_MEMORY_PROPERTY_HOST_COHERENT_BIT;
    plog(false, "%s buffer %.1f MiB, memory type %d (flags 0x%x)", readBack ? "read-back" : "staging", size / 1048576.0, type, unsigned(g.mem.memoryTypes[type].propertyFlags));
    return true;
}

// [p, p + bytes) rounded out to the import alignment, which never exceeds the page size (checked at set-up),
// so the rounding stays inside pages the allocation owns. offset = p - start.
bool importHost(Buf& b, const void* p, size_t bytes, VkDeviceSize& offset)
{
    if (!g.hostImport || !p || !bytes) return false;
    const uintptr_t a = uintptr_t(g.importAlign);
    const uintptr_t start = uintptr_t(p) & ~(a - 1), end = (uintptr_t(p) + bytes + a - 1) & ~(a - 1);
    offset = uintptr_t(p) - start;
    VkMemoryHostPointerPropertiesEXT hp { VK_STRUCTURE_TYPE_MEMORY_HOST_POINTER_PROPERTIES_EXT };
    VkResult r = g.vk.vkGetMemoryHostPointerPropertiesEXT(g.device, VK_EXTERNAL_MEMORY_HANDLE_TYPE_HOST_ALLOCATION_BIT_EXT, reinterpret_cast<void*>(start), &hp);
    const char* stage = "host pointer properties";
    if (r == VK_SUCCESS) {
        VkExternalMemoryBufferCreateInfo ext { VK_STRUCTURE_TYPE_EXTERNAL_MEMORY_BUFFER_CREATE_INFO };
        ext.handleTypes = VK_EXTERNAL_MEMORY_HANDLE_TYPE_HOST_ALLOCATION_BIT_EXT;
        VkBufferCreateInfo bi { VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO, &ext };
        bi.size = end - start; bi.usage = VK_BUFFER_USAGE_TRANSFER_SRC_BIT; bi.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
        stage = "vkCreateBuffer"; r = g.vk.vkCreateBuffer(g.device, &bi, nullptr, &b.buffer);
        if (r == VK_SUCCESS) g.liveBuffers++;
    }
    if (r == VK_SUCCESS) {
        VkMemoryRequirements req {}; g.vk.vkGetBufferMemoryRequirements(g.device, b.buffer, &req);
        const int type = findMemory(req.memoryTypeBits & hp.memoryTypeBits, 0);
        stage = "memory type";
        if (type < 0 || req.size > end - start) r = VK_ERROR_FEATURE_NOT_PRESENT;
        else {
            VkImportMemoryHostPointerInfoEXT imp { VK_STRUCTURE_TYPE_IMPORT_MEMORY_HOST_POINTER_INFO_EXT };
            imp.handleType = VK_EXTERNAL_MEMORY_HANDLE_TYPE_HOST_ALLOCATION_BIT_EXT; imp.pHostPointer = reinterpret_cast<void*>(start);
            VkMemoryAllocateInfo ai { VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO, &imp }; ai.allocationSize = end - start; ai.memoryTypeIndex = uint32_t(type);
            stage = "vkAllocateMemory(import)"; r = g.vk.vkAllocateMemory(g.device, &ai, nullptr, &b.memory);
            if (r == VK_SUCCESS) { g.liveMemory++; b.imported = true; b.size = end - start; g.liveImportMiB += b.size / 1048576.0;
                stage = "vkBindBufferMemory"; r = g.vk.vkBindBufferMemory(g.device, b.buffer, b.memory, 0); }
        }
    }
    if (r != VK_SUCCESS) {
        g.importFails++;
        if (g.importFailLogs++ < 6) plog(true, "import of %zu bytes at %p failed at %s (%d): staging copy for this frame", bytes, p, stage, int(r));
        freeBuf(b); return false;
    }
    g.imports++;
    return true;
}

void barrier(VkImage image, VkImageLayout from, VkImageLayout to, VkAccessFlags srcA, VkAccessFlags dstA, VkPipelineStageFlags srcS, VkPipelineStageFlags dstS)
{
    VkImageMemoryBarrier b { VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER };
    b.oldLayout = from; b.newLayout = to; b.srcAccessMask = srcA; b.dstAccessMask = dstA;
    b.srcQueueFamilyIndex = b.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED; b.image = image;
    b.subresourceRange = { VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1 };
    g.vk.vkCmdPipelineBarrier(g.cmd, srcS, dstS, 0, 0, nullptr, 0, nullptr, 1, &b);
}

bool ensureCanvas(uint32_t w, uint32_t h)
{
    if (g.canvas.image && g.canvas.w == w && g.canvas.h == h) return true;
    if (g.canvas.image) { plog(false, "canvas image %ux%u -> %ux%u", g.canvas.w, g.canvas.h, w, h); freeImg(g.canvas); }
    VkImageCreateInfo ii { VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO };
    ii.imageType = VK_IMAGE_TYPE_2D; ii.format = g.canvasFormat; ii.extent = { w, h, 1 }; ii.mipLevels = 1; ii.arrayLayers = 1;
    ii.samples = VK_SAMPLE_COUNT_1_BIT; ii.tiling = VK_IMAGE_TILING_OPTIMAL;
    ii.usage = VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT; ii.sharingMode = VK_SHARING_MODE_EXCLUSIVE; ii.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
    if (g.vk.vkCreateImage(g.device, &ii, nullptr, &g.canvas.image) != VK_SUCCESS) return false;
    g.liveImages++;
    VkMemoryRequirements req {}; g.vk.vkGetImageMemoryRequirements(g.device, g.canvas.image, &req);
    int type = findMemory(req.memoryTypeBits, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT);
    if (type < 0) type = findMemory(req.memoryTypeBits, 0);
    VkMemoryAllocateInfo ai { VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO }; ai.allocationSize = req.size; ai.memoryTypeIndex = uint32_t(type);
    if (type < 0 || g.vk.vkAllocateMemory(g.device, &ai, nullptr, &g.canvas.memory) != VK_SUCCESS) { freeImg(g.canvas); return false; }
    g.liveMemory++; g.liveOwnMiB += double(w) * h * 4 / 1048576.0;
    if (g.vk.vkBindImageMemory(g.device, g.canvas.image, g.canvas.memory, 0) != VK_SUCCESS) { freeImg(g.canvas); return false; }
    g.canvas.w = w; g.canvas.h = h; g.canvas.format = g.canvasFormat; g.canvas.layout = VK_IMAGE_LAYOUT_UNDEFINED;
    plog(false, "canvas image %ux%u format %d (%.1f MiB, memory type %d)", w, h, int(g.canvasFormat), req.size / 1048576.0, type);
    return true;
}

// Records: source frame -> canvas image, staged video runs -> canvas image, [canvas -> read-back],
// canvas -> target (scaled, letterboxed to the canvas aspect). Target layout ends in `finalLayout`.
struct Recorded { Buf src, layer; bool srcImported = false; bool video = false; bool readback = false; };
bool recordCompose(const uint8_t* pixels, int pitch, int w, int h, VkImage target, VkExtent2D tExt, VkImageLayout& tLayout, VkImageLayout finalLayout,
                   bool wantReadback, Recorded& rec)
{
    const size_t frameBytes = size_t(pitch) * size_t(h);
    VkDeviceSize srcOff = 0;
    const bool tryImport = g.hostImport && !g.optForceStaging;
    rec.srcImported = tryImport && importHost(rec.src, pixels, frameBytes, srcOff);
    if (!rec.srcImported) {
        if (g.optForceImport && tryImport) return false;
        if (!g.staging.buffer || g.staging.size < frameBytes) {
            freeBuf(g.staging);
            if (!makeHostBuffer(g.staging, (frameBytes + 0xffff) & ~size_t(0xffff), false, VK_BUFFER_USAGE_TRANSFER_SRC_BIT)) { plog(true, "no staging buffer"); return false; }
        }
        memcpy(g.staging.mapped, pixels, frameBytes);
        g.stagingCopies++;
    }
    const VkBuffer srcBuffer = rec.srcImported ? rec.src.buffer : g.staging.buffer;
    // video layer (pinned by OmniHwService until release())
    VkDeviceSize layerOff = 0;
    rec.video = g.video.valid && g.optVideo && !g.video.runs.empty() && importHost(rec.layer, g.video.px, g.video.bytes, layerOff);
    if (g.video.valid && g.optVideo && !rec.video && !g.video.runs.empty()) plog(false, "video layer import failed: this frame shows the canvas only in the video area");

    if (g.timers) g.vk.vkCmdResetQueryPool(g.cmd, g.queries, uint32_t(g.queryPair * 2), 2);
    if (g.timers) g.vk.vkCmdWriteTimestamp(g.cmd, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, g.queries, uint32_t(g.queryPair * 2));
    VkMemoryBarrier host { VK_STRUCTURE_TYPE_MEMORY_BARRIER }; host.srcAccessMask = VK_ACCESS_HOST_WRITE_BIT; host.dstAccessMask = VK_ACCESS_TRANSFER_READ_BIT;
    g.vk.vkCmdPipelineBarrier(g.cmd, VK_PIPELINE_STAGE_HOST_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 1, &host, 0, nullptr, 0, nullptr);
    barrier(g.canvas.image, VK_IMAGE_LAYOUT_UNDEFINED, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 0, VK_ACCESS_TRANSFER_WRITE_BIT, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT);
    VkBufferImageCopy whole {};
    whole.bufferOffset = rec.srcImported ? srcOff : 0; whole.bufferRowLength = uint32_t(pitch / 4); whole.bufferImageHeight = uint32_t(h);
    whole.imageSubresource = { VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1 }; whole.imageExtent = { uint32_t(w), uint32_t(h), 1 };
    g.vk.vkCmdCopyBufferToImage(g.cmd, srcBuffer, g.canvas.image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &whole);
    if (rec.video) {
        // the hole-punch, on the GPU: each run of video pixels comes straight from the layer (same channel order
        // as the canvas: holePunchAttach). Runs are clipped to the canvas and the layer.
        std::vector<VkBufferImageCopy> regions; regions.reserve(g.video.runs.size() / 3);
        const VideoStage& v = g.video;
        for (size_t k = 0; k + 2 < v.runs.size(); k += 3) {
            const int y = int(v.runs[k]), x0 = int(v.runs[k + 1]); int n = int(v.runs[k + 2]);
            if (y < 0 || y >= h || x0 < 0 || x0 >= w || y - v.ly < 0 || y - v.ly >= v.h || x0 - v.lx < 0) continue;
            n = std::min({ n, w - x0, v.w - (x0 - v.lx) }); if (n <= 0) continue;
            VkBufferImageCopy c {};
            c.bufferOffset = layerOff + VkDeviceSize(y - v.ly) * VkDeviceSize(v.stride) + VkDeviceSize(x0 - v.lx) * 4;
            c.bufferRowLength = uint32_t(v.stride / 4); c.bufferImageHeight = 1;
            c.imageSubresource = { VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1 }; c.imageOffset = { x0, y, 0 }; c.imageExtent = { uint32_t(n), 1, 1 };
            regions.push_back(c);
        }
        if (!regions.empty()) {
            VkMemoryBarrier ww { VK_STRUCTURE_TYPE_MEMORY_BARRIER }; ww.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT; ww.dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
            g.vk.vkCmdPipelineBarrier(g.cmd, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 1, &ww, 0, nullptr, 0, nullptr);
            g.vk.vkCmdCopyBufferToImage(g.cmd, rec.layer.buffer, g.canvas.image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, uint32_t(regions.size()), regions.data());
            g.videoFrames++; g.videoRuns += regions.size();
        }
    }
    barrier(g.canvas.image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, VK_ACCESS_TRANSFER_WRITE_BIT, VK_ACCESS_TRANSFER_READ_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT);
    g.canvas.layout = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;
    rec.readback = false;
    if (wantReadback) {
        const VkDeviceSize need = VkDeviceSize(w) * h * 4;
        if (!g.readback.buffer || g.readback.size < need) { freeBuf(g.readback); makeHostBuffer(g.readback, need, true, VK_BUFFER_USAGE_TRANSFER_DST_BIT); }
        if (g.readback.buffer) {
            VkBufferImageCopy c {}; c.imageSubresource = { VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1 }; c.imageExtent = { uint32_t(w), uint32_t(h), 1 };
            g.vk.vkCmdCopyImageToBuffer(g.cmd, g.canvas.image, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, g.readback.buffer, 1, &c);
            rec.readback = true;
        }
    }
    // target: clear (letterbox bars), then the canvas scaled to fit with its aspect kept
    barrier(target, tLayout == VK_IMAGE_LAYOUT_PRESENT_SRC_KHR ? VK_IMAGE_LAYOUT_UNDEFINED : tLayout, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 0, VK_ACCESS_TRANSFER_WRITE_BIT,
            VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT);
    const double sx = double(tExt.width) / w, sy = double(tExt.height) / h, s = std::min(sx, sy);
    const int dw = int(std::lround(w * s)), dh = int(std::lround(h * s)), dx = (int(tExt.width) - dw) / 2, dy = (int(tExt.height) - dh) / 2;
    if (dw != int(tExt.width) || dh != int(tExt.height)) {
        VkClearColorValue black {}; black.float32[3] = 1.0f;
        VkImageSubresourceRange all { VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1 };
        g.vk.vkCmdClearColorImage(g.cmd, target, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, &black, 1, &all);
        VkMemoryBarrier ww { VK_STRUCTURE_TYPE_MEMORY_BARRIER }; ww.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT; ww.dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
        g.vk.vkCmdPipelineBarrier(g.cmd, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 1, &ww, 0, nullptr, 0, nullptr);
    }
    VkImageBlit blit {};
    blit.srcSubresource = { VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1 }; blit.srcOffsets[1] = { w, h, 1 };
    blit.dstSubresource = { VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1 }; blit.dstOffsets[0] = { dx, dy, 0 }; blit.dstOffsets[1] = { dx + dw, dy + dh, 1 };
    g.vk.vkCmdBlitImage(g.cmd, g.canvas.image, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, target, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &blit,
                        (dw == w && dh == h) ? VK_FILTER_NEAREST : VK_FILTER_LINEAR);
    barrier(target, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, finalLayout, VK_ACCESS_TRANSFER_WRITE_BIT,
            finalLayout == VK_IMAGE_LAYOUT_PRESENT_SRC_KHR ? 0 : VK_ACCESS_TRANSFER_READ_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT,
            finalLayout == VK_IMAGE_LAYOUT_PRESENT_SRC_KHR ? VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT : VK_PIPELINE_STAGE_TRANSFER_BIT);
    tLayout = finalLayout;
    if (g.timers) g.vk.vkCmdWriteTimestamp(g.cmd, VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT, g.queries, uint32_t(g.queryPair * 2 + 1));
    return true;
}

// Differential check of the composed canvas (before scaling) against what the CPU present path shows:
// the frame's pixels, with the staged video runs taken from the layer. Copies only: must be exact.
bool verifyComposed(const uint8_t* pixels, int pitch, int w, int h, bool withVideo)
{
    if (!g.readback.coherent) {
        VkMappedMemoryRange mr { VK_STRUCTURE_TYPE_MAPPED_MEMORY_RANGE }; mr.memory = g.readback.memory; mr.size = VK_WHOLE_SIZE;
        g.vk.vkInvalidateMappedMemoryRanges(g.device, 1, &mr);
    }
    const uint8_t* got = static_cast<const uint8_t*>(g.readback.mapped);
    std::vector<uint8_t> expect(size_t(w) * h * 4);
    for (int y = 0; y < h; ++y) memcpy(expect.data() + size_t(y) * w * 4, pixels + size_t(y) * pitch, size_t(w) * 4);
    size_t videoPx = 0;
    if (withVideo) {
        const VideoStage& v = g.video;
        for (size_t k = 0; k + 2 < v.runs.size(); k += 3) {
            const int y = int(v.runs[k]), x0 = int(v.runs[k + 1]); int n = int(v.runs[k + 2]);
            if (y < 0 || y >= h || x0 < 0 || x0 >= w || y - v.ly < 0 || y - v.ly >= v.h || x0 - v.lx < 0) continue;
            n = std::min({ n, w - x0, v.w - (x0 - v.lx) }); if (n <= 0) continue;
            memcpy(expect.data() + (size_t(y) * w + x0) * 4, v.px + size_t(y - v.ly) * v.stride + size_t(x0 - v.lx) * 4, size_t(n) * 4);
            videoPx += size_t(n);
        }
    }
    size_t bad = 0; int firstX = -1, firstY = -1;
    for (size_t i = 0; i < expect.size(); i += 4)
        if (memcmp(&expect[i], got + i, 4)) { if (!bad) { firstX = int((i / 4) % w); firstY = int((i / 4) / w); } ++bad; }
    plog(true, "verify %s frame %dx%d (%zu video pixels): %zu of %zu pixels differ%s", withVideo ? "video" : "plain", w, h, videoPx, bad, expect.size() / 4,
         bad ? "" : " -> exact");
    if (bad) plog(true, "first difference at %d,%d", firstX, firstY);
    return bad == 0;
}

void logWindow(bool force)
{
    const double now = nowMs();
    if (!g.windowStart) g.windowStart = now;
    if (!force && (now - g.windowStart < 10000 || !g.windowN)) return;
    if (g.windowLogs++ < 200)
        plog(false, "10 s: presents %u, CPU in present avg %.2f ms (max %.2f), vblank wait avg %.2f ms (max %.2f), GPU %.3f ms; video frames %llu runs %llu; imports %llu (fails %llu) staging copies %llu; live buffers %ld images %ld memory objects %ld, own %.1f MiB, imported %.1f MiB",
            g.windowN, g.sumCpu / g.windowN, g.maxCpu, g.sumWait / g.windowN, g.maxWait, g.sumGpu / std::max(1u, g.windowN),
            (unsigned long long)g.videoFrames, (unsigned long long)g.videoRuns, (unsigned long long)g.imports, (unsigned long long)g.importFails,
            (unsigned long long)g.stagingCopies, g.liveBuffers, g.liveImages, g.liveMemory, g.liveOwnMiB, g.liveImportMiB);
    g.windowStart = now; g.windowN = 0; g.sumCpu = g.sumWait = g.sumGpu = g.maxCpu = g.maxWait = 0;
}

// non-blocking read of the other query pair (lesson 2)
double readOtherTimer()
{
    if (!g.timers) return 0;
    const int other = g.queryPair ^ 1;
    if (!g.queryPending[other]) return 0;
    uint64_t ts[2] = {};
    if (g.vk.vkGetQueryPoolResults(g.device, g.queries, uint32_t(other * 2), 2, sizeof ts, ts, sizeof ts[0], VK_QUERY_RESULT_64_BIT) != VK_SUCCESS) return 0;
    g.queryPending[other] = false;
    return ts[1] >= ts[0] ? double(ts[1] - ts[0]) * g.timestampNs / 1e6 : 0;
}

void releaseVideo()
{
    VideoStage& v = g.video;
    if (v.release) v.release(v.cookie);
    v.valid = false; v.release = nullptr; v.cookie = nullptr; v.px = nullptr; v.runs.clear();
}

void teardownLocked(const char* why);

} // namespace

#ifndef OMNI_GPU_PRESENT_HOST_TEST
// ================================================================ console: display, swapchain, SDL hooks
extern "C" int sceSystemServiceHideSplashScreen(void);
namespace {

void readOptions()
{
    FILE* f = fopen(kFlagPath, "r");
    if (!f) return;
    char word[64];
    while (fscanf(f, "%63s", word) == 1) {
        if (!strcmp(word, "mailbox")) g.optMailbox = true;
        else if (!strcmp(word, "novideo")) g.optVideo = false;
        else if (!strcmp(word, "noverify")) g.optVerify = false;
        else if (!strcmp(word, "staging")) g.optForceStaging = true;
        else if (!strcmp(word, "import")) g.optForceImport = true;
        else if (!strncmp(word, "out=", 4)) g.optOutHeight = !strcmp(word + 4, "match") ? 0 : atoi(word + 4);
        else plog(false, "flag file: unknown word '%s'", word);
    }
    fclose(f);
}

const char* modeName(VkPresentModeKHR m)
{
    switch (m) { case VK_PRESENT_MODE_IMMEDIATE_KHR: return "IMMEDIATE"; case VK_PRESENT_MODE_MAILBOX_KHR: return "MAILBOX"; case VK_PRESENT_MODE_FIFO_KHR: return "FIFO";
    case VK_PRESENT_MODE_FIFO_RELAXED_KHR: return "FIFO_RELAXED"; default: return "other"; }
}
bool isSrgb(VkFormat f) { return f == VK_FORMAT_B8G8R8A8_SRGB || f == VK_FORMAT_R8G8B8A8_SRGB || f == VK_FORMAT_A8B8G8R8_SRGB_PACK32; }

// Acquire the next image and wait for it: with FIFO and two images this returns at the flip of the one
// just presented, which is what SDL's present did (SubmitFlip + wait for the flip event).
bool acquireWait(double& waitedMs)
{
    const double t = nowMs();
    g.vk.vkResetFences(g.device, 1, &g.acquireFence);
    VkResult r = g.vk.vkAcquireNextImageKHR(g.device, g.swapchain, 1000ull * 1000 * 1000, VK_NULL_HANDLE, g.acquireFence, &g.acquired);
    if (r == VK_SUCCESS || r == VK_SUBOPTIMAL_KHR) r = g.vk.vkWaitForFences(g.device, 1, &g.acquireFence, VK_TRUE, 1000ull * 1000 * 1000);
    waitedMs = nowMs() - t;
    if (r == VK_TIMEOUT) { g.hung = true; plog(true, "WATCHDOG: no swapchain image within 1 s (GPU or display stalled)"); return false; }
    if (r != VK_SUCCESS) { plog(true, "acquire: %d", int(r)); g.acquired = UINT32_MAX; return false; }
    return true;
}

bool submitAndWait()
{
    VkSubmitInfo si { VK_STRUCTURE_TYPE_SUBMIT_INFO };
    si.commandBufferCount = 1; si.pCommandBuffers = &g.cmd; si.signalSemaphoreCount = 1; si.pSignalSemaphores = &g.renderDone;
    g.vk.vkResetFences(g.device, 1, &g.submitFence);
    VkResult r = g.vk.vkQueueSubmit(g.queue, 1, &si, g.submitFence);
    if (r != VK_SUCCESS) { plog(true, "vkQueueSubmit=%d", int(r)); return false; }
    VkPresentInfoKHR pi { VK_STRUCTURE_TYPE_PRESENT_INFO_KHR };
    pi.waitSemaphoreCount = 1; pi.pWaitSemaphores = &g.renderDone; pi.swapchainCount = 1; pi.pSwapchains = &g.swapchain; pi.pImageIndices = &g.acquired;
    VkPresentIdKHR pid { VK_STRUCTURE_TYPE_PRESENT_ID_KHR }; uint64_t id = ++g.presentId;
    if (g.presentWait) { pid.swapchainCount = 1; pid.pPresentIds = &id; pi.pNext = &pid; }
    r = g.vk.vkQueuePresentKHR(g.queue, &pi);
    g.imageLayouts[g.acquired] = VK_IMAGE_LAYOUT_PRESENT_SRC_KHR;
    g.acquired = UINT32_MAX;
    if (r != VK_SUCCESS && r != VK_SUBOPTIMAL_KHR) { plog(true, "vkQueuePresentKHR=%d", int(r)); return false; }
    r = g.vk.vkWaitForFences(g.device, 1, &g.submitFence, VK_TRUE, 1000ull * 1000 * 1000);
    if (r == VK_TIMEOUT) { g.hung = true; plog(true, "WATCHDOG: a frame did not finish on the GPU within 1 s"); return false; }
    return r == VK_SUCCESS;
}

bool beginCmd()
{
    g.vk.vkResetCommandBuffer(g.cmd, 0);
    VkCommandBufferBeginInfo bi { VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO }; bi.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
    return g.vk.vkBeginCommandBuffer(g.cmd, &bi) == VK_SUCCESS;
}

// One frame: compose + present + wait for its flip. Caller holds g.lock.
int presentLockedImpl(const uint8_t* pixels, int pitch, int w, int h);
int presentLocked(const uint8_t* pixels, int pitch, int w, int h)
{
    g.presentSinceUs.store(int64_t(nowMs() * 1000) | 1);
    const int rc = presentLockedImpl(pixels, pitch, w, h);
    g.presentSinceUs.store(0);
    return rc;
}
int presentLockedImpl(const uint8_t* pixels, int pitch, int w, int h)
{
    const double t0 = nowMs();
    if (!ensureCanvas(uint32_t(w), uint32_t(h))) { plog(true, "canvas image %dx%d failed", w, h); return -1; }
    if (g.acquired == UINT32_MAX) { double waited = 0; if (!acquireWait(waited)) return -1; }
    const bool videoNow = g.video.valid && g.optVideo && !g.video.runs.empty();
    const bool check = g.optVerify && ((!videoNow && g.verifyPlain < 3) || (videoNow && g.verifyVideo < 3));
    Recorded rec;
    if (!beginCmd()) return -1;
    VkImageLayout layout = g.imageLayouts[g.acquired];
    if (!recordCompose(pixels, pitch, w, h, g.images[g.acquired], g.extent, layout, VK_IMAGE_LAYOUT_PRESENT_SRC_KHR, check, rec)) { g.vk.vkEndCommandBuffer(g.cmd); freeBuf(rec.src); freeBuf(rec.layer); return -1; }
    if (g.vk.vkEndCommandBuffer(g.cmd) != VK_SUCCESS) { freeBuf(rec.src); freeBuf(rec.layer); return -1; }
    const bool ok = submitAndWait();
    if (g.hung) return -1;   // nothing imported is released: the GPU may still read it
    if (g.timers) g.queryPending[g.queryPair] = true;
    const double gpuMs = readOtherTimer(); g.queryPair ^= 1;
    if (ok && rec.readback) {
        const bool exact = verifyComposed(pixels, pitch, w, h, rec.video);
        if (rec.video) g.verifyVideo++; else g.verifyPlain++;
        if (!exact && rec.video && g.optVideo) { g.optVideo = false; plog(true, "video runs differ: the CPU writes the video again from now on"); }
        else if (!exact && !rec.video) { freeBuf(rec.src); freeBuf(rec.layer); releaseVideo(); plog(true, "OFF: the presented frame differs from the canvas; present fails so Omni closes cleanly"); return -1; }
    }
    freeBuf(rec.src); freeBuf(rec.layer);
    releaseVideo();
    if (!ok) return -1;
    const double tCpu = nowMs() - t0;
    double waited = 0;
    if (g.presentWait && g.vk.vkWaitForPresentKHR) {
        const double t = nowMs();
        VkResult r = g.vk.vkWaitForPresentKHR(g.device, g.swapchain, g.presentId, 1000ull * 1000 * 1000);
        waited = nowMs() - t;
        if (r == VK_TIMEOUT) { g.hung = true; plog(true, "WATCHDOG: present %llu not shown within 1 s", (unsigned long long)g.presentId); return -1; }
        double w2 = 0; if (!acquireWait(w2)) return -1; waited += w2;
    } else if (!acquireWait(waited)) return -1;
    g.presents++; g.windowN++;
    g.sumCpu += tCpu; g.maxCpu = std::max(g.maxCpu, tCpu); g.sumWait += waited; g.maxWait = std::max(g.maxWait, waited); g.sumGpu += gpuMs;
    logWindow(false);
    return 0;
}

#define LOADI(name) loadI(g.instance, g.vk.name, #name)
bool bringUp()
{
    const double t0 = nowMs();
    readOptions();
    const char* hEnv = getenv("OMNI_SDL_HEIGHT");
    if (hEnv && !strcmp(hEnv, "1440")) { g.canvasHintW = 2560; g.canvasHintH = 1440; }
    else if (hEnv && !strcmp(hEnv, "2160")) { g.canvasHintW = 3840; g.canvasHintH = 2160; }
    plog(true, "start (OMNI_GPU_PRESENT_V1): canvas %dx%d (OMNI_SDL_HEIGHT=%s); options %s%s%s%s out=%d", g.canvasHintW, g.canvasHintH, hEnv ? hEnv : "unset",
        g.optMailbox ? "mailbox " : "fifo ", g.optVideo ? "video " : "novideo ", g.optVerify ? "verify " : "noverify ",
        g.optForceStaging ? "staging" : g.optForceImport ? "import" : "import-or-staging", g.optOutHeight);
    Api& vk = g.vk;
    if (!loadI(VK_NULL_HANDLE, vk.vkCreateInstance, "vkCreateInstance") || !loadI(VK_NULL_HANDLE, vk.vkEnumerateInstanceExtensionProperties, "vkEnumerateInstanceExtensionProperties")) {
        plog(true, "no Vulkan driver linked"); return false; }
    uint32_t n = 0; vk.vkEnumerateInstanceExtensionProperties(nullptr, &n, nullptr);
    std::vector<VkExtensionProperties> iext(n); if (n) vk.vkEnumerateInstanceExtensionProperties(nullptr, &n, iext.data());
    bool hasDisplay = false, hasSurface = false;
    for (auto& e : iext) { plog(false, "instance extension %s", e.extensionName); hasDisplay |= !strcmp(e.extensionName, VK_KHR_DISPLAY_EXTENSION_NAME); hasSurface |= !strcmp(e.extensionName, VK_KHR_SURFACE_EXTENSION_NAME); }
    if (!hasDisplay || !hasSurface) { plog(true, "VK_KHR_display/VK_KHR_surface missing"); return false; }
    VkApplicationInfo app { VK_STRUCTURE_TYPE_APPLICATION_INFO }; app.pApplicationName = "Omni present"; app.pEngineName = "OmniGpuPresent"; app.apiVersion = VK_API_VERSION_1_3;
    const char* ie[2] = { VK_KHR_SURFACE_EXTENSION_NAME, VK_KHR_DISPLAY_EXTENSION_NAME };
    VkInstanceCreateInfo ici { VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO }; ici.pApplicationInfo = &app; ici.enabledExtensionCount = 2; ici.ppEnabledExtensionNames = ie;
    VkResult r = vk.vkCreateInstance(&ici, nullptr, &g.instance);
    if (r != VK_SUCCESS) { plog(true, "vkCreateInstance=%d", int(r)); return false; }
    bool ok = LOADI(vkDestroyInstance) && LOADI(vkEnumeratePhysicalDevices) && LOADI(vkGetPhysicalDeviceProperties) && LOADI(vkGetPhysicalDeviceProperties2)
        && LOADI(vkGetPhysicalDeviceMemoryProperties) && LOADI(vkGetPhysicalDeviceQueueFamilyProperties) && LOADI(vkGetPhysicalDeviceFormatProperties)
        && LOADI(vkEnumerateDeviceExtensionProperties) && LOADI(vkCreateDevice) && LOADI(vkGetDeviceProcAddr)
        && LOADI(vkGetPhysicalDeviceDisplayPropertiesKHR) && LOADI(vkGetDisplayModePropertiesKHR) && LOADI(vkGetPhysicalDeviceDisplayPlanePropertiesKHR)
        && LOADI(vkGetDisplayPlaneSupportedDisplaysKHR) && LOADI(vkGetDisplayPlaneCapabilitiesKHR) && LOADI(vkCreateDisplayPlaneSurfaceKHR)
        && LOADI(vkDestroySurfaceKHR) && LOADI(vkGetPhysicalDeviceSurfaceSupportKHR) && LOADI(vkGetPhysicalDeviceSurfaceCapabilitiesKHR)
        && LOADI(vkGetPhysicalDeviceSurfaceFormatsKHR) && LOADI(vkGetPhysicalDeviceSurfacePresentModesKHR);
    if (!ok) { plog(true, "an instance entry point is missing"); return false; }
    n = 0; vk.vkEnumeratePhysicalDevices(g.instance, &n, nullptr);
    std::vector<VkPhysicalDevice> pds(n); if (n) vk.vkEnumeratePhysicalDevices(g.instance, &n, pds.data());
    if (!n) { plog(true, "no physical device"); return false; }
    g.physical = pds[0];
    VkPhysicalDeviceExternalMemoryHostPropertiesEXT hostProps { VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_EXTERNAL_MEMORY_HOST_PROPERTIES_EXT };
    VkPhysicalDeviceProperties2 p2 { VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2, &hostProps };
    vk.vkGetPhysicalDeviceProperties2(g.physical, &p2);
    g.timestampNs = p2.properties.limits.timestampPeriod;
    vk.vkGetPhysicalDeviceMemoryProperties(g.physical, &g.mem);
    plog(false, "device '%s' api %u.%u.%u timestampPeriod=%.3f ns", p2.properties.deviceName, VK_API_VERSION_MAJOR(p2.properties.apiVersion),
        VK_API_VERSION_MINOR(p2.properties.apiVersion), VK_API_VERSION_PATCH(p2.properties.apiVersion), g.timestampNs);
    for (uint32_t i = 0; i < g.mem.memoryTypeCount; ++i) plog(false, "memory type %u flags 0x%x heap %u", i, unsigned(g.mem.memoryTypes[i].propertyFlags), g.mem.memoryTypes[i].heapIndex);

    // displays, modes, planes (all logged)
    n = 0; vk.vkGetPhysicalDeviceDisplayPropertiesKHR(g.physical, &n, nullptr);
    std::vector<VkDisplayPropertiesKHR> displays(n); if (n) vk.vkGetPhysicalDeviceDisplayPropertiesKHR(g.physical, &n, displays.data());
    if (!n) { plog(true, "no display"); return false; }
    for (uint32_t i = 0; i < n; ++i) plog(false, "display %u '%s' %ux%u physical %ux%u mm", i, displays[i].displayName ? displays[i].displayName : "?",
        displays[i].physicalResolution.width, displays[i].physicalResolution.height, displays[i].physicalDimensions.width, displays[i].physicalDimensions.height);
    const VkDisplayKHR display = displays[0].display;
    n = 0; vk.vkGetDisplayModePropertiesKHR(g.physical, display, &n, nullptr);
    std::vector<VkDisplayModePropertiesKHR> modes(n); if (n) vk.vkGetDisplayModePropertiesKHR(g.physical, display, &n, modes.data());
    if (!n) { plog(true, "display has no modes"); return false; }
    int chosen = -1, largest = 0;
    const uint32_t wantH = g.optOutHeight > 0 ? uint32_t(g.optOutHeight) : uint32_t(g.canvasHintH);
    for (uint32_t i = 0; i < n; ++i) {
        const auto& m = modes[i].parameters;
        plog(false, "mode %u: %ux%u @ %.3f Hz", i, m.visibleRegion.width, m.visibleRegion.height, m.refreshRate / 1000.0);
        const auto& L = modes[largest].parameters;
        if (uint64_t(m.visibleRegion.width) * m.visibleRegion.height > uint64_t(L.visibleRegion.width) * L.visibleRegion.height
            || (m.visibleRegion.width == L.visibleRegion.width && m.visibleRegion.height == L.visibleRegion.height && m.refreshRate > L.refreshRate)) largest = int(i);
        if (m.visibleRegion.height == wantH && (chosen < 0 || std::abs(int(m.refreshRate) - 60000) < std::abs(int(modes[chosen].parameters.refreshRate) - 60000))) chosen = int(i);
    }
    if (chosen < 0) chosen = largest;
    const auto& mp = modes[chosen].parameters;
    g.extent = mp.visibleRegion;
    const bool scaled = g.extent.width != uint32_t(g.canvasHintW) || g.extent.height != uint32_t(g.canvasHintH);
    plog(true, "output mode %ux%u @ %.3f Hz (%s); scaling: canvas %dx%d -> %ux%u %s", g.extent.width, g.extent.height, mp.refreshRate / 1000.0,
        g.optOutHeight > 0 ? "requested height" : (g.extent.height == uint32_t(g.canvasHintH) ? "matches the canvas" : "canvas size not listed: largest mode"),
        g.canvasHintW, g.canvasHintH, g.extent.width, g.extent.height, scaled ? "(GPU linear scale, aspect kept)" : "(1:1, no scaling)");
    n = 0; vk.vkGetPhysicalDeviceDisplayPlanePropertiesKHR(g.physical, &n, nullptr);
    std::vector<VkDisplayPlanePropertiesKHR> planes(n); if (n) vk.vkGetPhysicalDeviceDisplayPlanePropertiesKHR(g.physical, &n, planes.data());
    int plane = -1;
    for (uint32_t i = 0; i < n && plane < 0; ++i) {
        uint32_t dn = 0; vk.vkGetDisplayPlaneSupportedDisplaysKHR(g.physical, i, &dn, nullptr);
        std::vector<VkDisplayKHR> ds(dn); if (dn) vk.vkGetDisplayPlaneSupportedDisplaysKHR(g.physical, i, &dn, ds.data());
        plog(false, "plane %u: %u displays, current stack index %u", i, dn, planes[i].currentStackIndex);
        for (auto d : ds) if (d == display) plane = int(i);
    }
    if (plane < 0) { plog(true, "no plane for display 0"); return false; }
    VkDisplayPlaneCapabilitiesKHR pc {}; vk.vkGetDisplayPlaneCapabilitiesKHR(g.physical, modes[chosen].displayMode, uint32_t(plane), &pc);
    VkDisplayPlaneAlphaFlagBitsKHR alpha = VK_DISPLAY_PLANE_ALPHA_OPAQUE_BIT_KHR;
    for (VkDisplayPlaneAlphaFlagBitsKHR a : { VK_DISPLAY_PLANE_ALPHA_OPAQUE_BIT_KHR, VK_DISPLAY_PLANE_ALPHA_GLOBAL_BIT_KHR, VK_DISPLAY_PLANE_ALPHA_PER_PIXEL_BIT_KHR, VK_DISPLAY_PLANE_ALPHA_PER_PIXEL_PREMULTIPLIED_BIT_KHR })
        if (pc.supportedAlpha & a) { alpha = a; break; }
    plog(false, "plane %d alpha modes 0x%x -> 0x%x (the frame is opaque)", plane, unsigned(pc.supportedAlpha), unsigned(alpha));

    // device with a graphics queue that can present
    n = 0; vk.vkGetPhysicalDeviceQueueFamilyProperties(g.physical, &n, nullptr);
    std::vector<VkQueueFamilyProperties> qf(n); if (n) vk.vkGetPhysicalDeviceQueueFamilyProperties(g.physical, &n, qf.data());
    sceSystemServiceHideSplashScreen();
    VkDisplaySurfaceCreateInfoKHR sci { VK_STRUCTURE_TYPE_DISPLAY_SURFACE_CREATE_INFO_KHR };
    sci.displayMode = modes[chosen].displayMode; sci.planeIndex = uint32_t(plane); sci.planeStackIndex = planes[plane].currentStackIndex;
    sci.transform = VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR; sci.globalAlpha = 1.0f; sci.alphaMode = alpha; sci.imageExtent = g.extent;
    r = vk.vkCreateDisplayPlaneSurfaceKHR(g.instance, &sci, nullptr, &g.surface);
    if (r != VK_SUCCESS) { plog(true, "vkCreateDisplayPlaneSurfaceKHR=%d", int(r)); return false; }
    int family = -1;
    for (uint32_t i = 0; i < n; ++i) {
        VkBool32 can = VK_FALSE; vk.vkGetPhysicalDeviceSurfaceSupportKHR(g.physical, i, g.surface, &can);
        plog(false, "queue family %u flags 0x%x count %u timestampValidBits %u present %d", i, unsigned(qf[i].queueFlags), qf[i].queueCount, qf[i].timestampValidBits, int(can));
        if (can && family < 0 && (qf[i].queueFlags & VK_QUEUE_GRAPHICS_BIT)) family = int(i);
    }
    if (family < 0) for (uint32_t i = 0; i < n && family < 0; ++i) { VkBool32 can = VK_FALSE; vk.vkGetPhysicalDeviceSurfaceSupportKHR(g.physical, i, g.surface, &can); if (can) family = int(i); }
    if (family < 0) { plog(true, "no queue family can present"); return false; }
    g.family = uint32_t(family);
    if (g.timers && !qf[family].timestampValidBits) g.timers = false;
    n = 0; vk.vkEnumerateDeviceExtensionProperties(g.physical, nullptr, &n, nullptr);
    std::vector<VkExtensionProperties> dext(n); if (n) vk.vkEnumerateDeviceExtensionProperties(g.physical, nullptr, &n, dext.data());
    bool hasSwap = false, hasHost = false, hasPresentId = false, hasPresentWait = false;
    for (auto& e : dext) {
        hasSwap |= !strcmp(e.extensionName, VK_KHR_SWAPCHAIN_EXTENSION_NAME); hasHost |= !strcmp(e.extensionName, VK_EXT_EXTERNAL_MEMORY_HOST_EXTENSION_NAME);
        hasPresentId |= !strcmp(e.extensionName, "VK_KHR_present_id"); hasPresentWait |= !strcmp(e.extensionName, "VK_KHR_present_wait");
    }
    if (!hasSwap) { plog(true, "VK_KHR_swapchain missing"); return false; }
    g.importAlign = hostProps.minImportedHostPointerAlignment;
    const long page = sysconf(_SC_PAGESIZE);
    g.hostImport = hasHost && g.importAlign && !(g.importAlign & (g.importAlign - 1)) && page > 0 && g.importAlign <= VkDeviceSize(page);
    std::vector<const char*> de { VK_KHR_SWAPCHAIN_EXTENSION_NAME };
    if (hasHost) de.push_back(VK_EXT_EXTERNAL_MEMORY_HOST_EXTENSION_NAME);
    VkPhysicalDevicePresentIdFeaturesKHR fid { VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PRESENT_ID_FEATURES_KHR };
    VkPhysicalDevicePresentWaitFeaturesKHR fwait { VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PRESENT_WAIT_FEATURES_KHR };
    const float prio = 1.0f;
    VkDeviceQueueCreateInfo qci { VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO }; qci.queueFamilyIndex = g.family; qci.queueCount = 1; qci.pQueuePriorities = &prio;
    VkDeviceCreateInfo dci { VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO }; dci.queueCreateInfoCount = 1; dci.pQueueCreateInfos = &qci;
    // present_wait only when the swapchain will hold more than 2 images (2 images: acquire already waits for the flip)
    VkSurfaceCapabilitiesKHR caps {}; vk.vkGetPhysicalDeviceSurfaceCapabilitiesKHR(g.physical, g.surface, &caps);
    const uint32_t imageCount = std::max(2u, caps.minImageCount);
    if (imageCount > 2 && hasPresentId && hasPresentWait) {
        de.push_back("VK_KHR_present_id"); de.push_back("VK_KHR_present_wait");
        fid.presentId = VK_TRUE; fwait.presentWait = VK_TRUE; fid.pNext = &fwait; dci.pNext = &fid; g.presentWait = true;
    }
    dci.enabledExtensionCount = uint32_t(de.size()); dci.ppEnabledExtensionNames = de.data();
    r = vk.vkCreateDevice(g.physical, &dci, nullptr, &g.device);
    if (r != VK_SUCCESS) { plog(true, "vkCreateDevice=%d", int(r)); return false; }
#define LOADD(name) loadD(g.vk.name, #name)
    ok = LOADD(vkDestroyDevice) && LOADD(vkDeviceWaitIdle) && LOADD(vkGetDeviceQueue) && LOADD(vkCreateCommandPool) && LOADD(vkDestroyCommandPool)
        && LOADD(vkAllocateCommandBuffers) && LOADD(vkResetCommandBuffer) && LOADD(vkBeginCommandBuffer) && LOADD(vkEndCommandBuffer)
        && LOADD(vkCmdPipelineBarrier) && LOADD(vkCmdCopyBufferToImage) && LOADD(vkCmdCopyImageToBuffer) && LOADD(vkCmdBlitImage) && LOADD(vkCmdClearColorImage)
        && LOADD(vkCmdResetQueryPool) && LOADD(vkCmdWriteTimestamp) && LOADD(vkCreateQueryPool) && LOADD(vkDestroyQueryPool) && LOADD(vkGetQueryPoolResults)
        && LOADD(vkCreateFence) && LOADD(vkDestroyFence) && LOADD(vkResetFences) && LOADD(vkWaitForFences) && LOADD(vkGetFenceStatus)
        && LOADD(vkCreateSemaphore) && LOADD(vkDestroySemaphore) && LOADD(vkQueueSubmit)
        && LOADD(vkCreateBuffer) && LOADD(vkDestroyBuffer) && LOADD(vkGetBufferMemoryRequirements) && LOADD(vkCreateImage) && LOADD(vkDestroyImage)
        && LOADD(vkGetImageMemoryRequirements) && LOADD(vkAllocateMemory) && LOADD(vkFreeMemory) && LOADD(vkBindBufferMemory) && LOADD(vkBindImageMemory)
        && LOADD(vkMapMemory) && LOADD(vkUnmapMemory) && LOADD(vkInvalidateMappedMemoryRanges)
        && LOADD(vkCreateSwapchainKHR) && LOADD(vkDestroySwapchainKHR) && LOADD(vkGetSwapchainImagesKHR) && LOADD(vkAcquireNextImageKHR) && LOADD(vkQueuePresentKHR);
    if (!ok) return false;
    if (g.hostImport && !LOADD(vkGetMemoryHostPointerPropertiesEXT)) g.hostImport = false;
    if (g.presentWait && !LOADD(vkWaitForPresentKHR)) g.presentWait = false;
    vk.vkGetDeviceQueue(g.device, g.family, 0, &g.queue);

    // surface formats / present modes, chosen on purpose (lesson 4) and sRGB tagged on purpose (lesson 3):
    // the canvas bytes are already sRGB-encoded, so a UNORM swapchain passes them through untouched; with
    // only *_SRGB swapchain formats the canvas image is *_SRGB too (blit decodes and re-encodes: no double encode).
    n = 0; vk.vkGetPhysicalDeviceSurfaceFormatsKHR(g.physical, g.surface, &n, nullptr);
    std::vector<VkSurfaceFormatKHR> sf(n); if (n) vk.vkGetPhysicalDeviceSurfaceFormatsKHR(g.physical, g.surface, &n, sf.data());
    int pick = -1;
    for (uint32_t i = 0; i < n; ++i) {
        plog(false, "surface format %u: format %d colour space %d", i, int(sf[i].format), int(sf[i].colorSpace));
        if (sf[i].colorSpace != VK_COLOR_SPACE_SRGB_NONLINEAR_KHR) continue;
        if ((sf[i].format == VK_FORMAT_B8G8R8A8_UNORM || sf[i].format == VK_FORMAT_R8G8B8A8_UNORM || sf[i].format == VK_FORMAT_A8B8G8R8_UNORM_PACK32) && (pick < 0 || isSrgb(sf[pick].format))) pick = int(i);
        else if (isSrgb(sf[i].format) && pick < 0) pick = int(i);
    }
    if (pick < 0) { plog(true, "no 8-bit sRGB-non-linear surface format"); return false; }
    g.swapFormat = sf[pick].format;
    g.canvasFormat = isSrgb(g.swapFormat) ? VK_FORMAT_R8G8B8A8_SRGB : VK_FORMAT_R8G8B8A8_UNORM;
    VkFormatProperties fpS {}, fpD {};
    vk.vkGetPhysicalDeviceFormatProperties(g.physical, g.canvasFormat, &fpS); vk.vkGetPhysicalDeviceFormatProperties(g.physical, g.swapFormat, &fpD);
    const bool blitOk = (fpS.optimalTilingFeatures & VK_FORMAT_FEATURE_BLIT_SRC_BIT) && (fpS.optimalTilingFeatures & VK_FORMAT_FEATURE_SAMPLED_IMAGE_FILTER_LINEAR_BIT)
        && (fpD.optimalTilingFeatures & VK_FORMAT_FEATURE_BLIT_DST_BIT);
    plog(true, "swapchain format %d, canvas image format %d (%s); blit src/linear/dst support %s", int(g.swapFormat), int(g.canvasFormat),
        isSrgb(g.swapFormat) ? "both sRGB: decode + encode, no double encode" : "both UNORM: sRGB bytes pass through", blitOk ? "yes" : "NO");
    if (!blitOk) return false;
    if (!(caps.supportedUsageFlags & VK_IMAGE_USAGE_TRANSFER_DST_BIT)) { plog(true, "swapchain images cannot be a transfer target (usage 0x%x)", unsigned(caps.supportedUsageFlags)); return false; }
    n = 0; vk.vkGetPhysicalDeviceSurfacePresentModesKHR(g.physical, g.surface, &n, nullptr);
    std::vector<VkPresentModeKHR> pm(n); if (n) vk.vkGetPhysicalDeviceSurfacePresentModesKHR(g.physical, g.surface, &n, pm.data());
    std::string list; bool hasMailbox = false, hasFifo = false;
    for (auto m : pm) { list += modeName(m); list += ' '; hasMailbox |= m == VK_PRESENT_MODE_MAILBOX_KHR; hasFifo |= m == VK_PRESENT_MODE_FIFO_KHR; }
    g.presentMode = (g.optMailbox && hasMailbox) ? VK_PRESENT_MODE_MAILBOX_KHR : VK_PRESENT_MODE_FIFO_KHR;
    plog(true, "present modes offered: %s-> %s (%s); images min %u max %u -> %u; vblank wait by %s", list.c_str(), modeName(g.presentMode),
        g.presentMode == VK_PRESENT_MODE_FIFO_KHR ? "a flip per vblank, as SDL's SubmitFlip + flip event" : "requested by the flag", caps.minImageCount, caps.maxImageCount,
        imageCount, g.presentWait ? "VK_KHR_present_wait" : imageCount == 2 ? "acquiring the next of 2 images" : "the swapchain queue only (no exact flip wait)");
    if (!hasFifo) { plog(true, "FIFO missing (required by Vulkan)"); return false; }
    VkSwapchainCreateInfoKHR sw { VK_STRUCTURE_TYPE_SWAPCHAIN_CREATE_INFO_KHR };
    sw.surface = g.surface; sw.minImageCount = caps.maxImageCount ? std::min(imageCount, caps.maxImageCount) : imageCount;
    sw.imageFormat = g.swapFormat; sw.imageColorSpace = VK_COLOR_SPACE_SRGB_NONLINEAR_KHR; sw.imageExtent = g.extent; sw.imageArrayLayers = 1;
    sw.imageUsage = VK_IMAGE_USAGE_TRANSFER_DST_BIT; sw.imageSharingMode = VK_SHARING_MODE_EXCLUSIVE;
    sw.preTransform = VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR; sw.compositeAlpha = VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR;
    if (!(caps.supportedCompositeAlpha & VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR)) sw.compositeAlpha = VkCompositeAlphaFlagBitsKHR(caps.supportedCompositeAlpha & -caps.supportedCompositeAlpha);
    sw.presentMode = g.presentMode; sw.clipped = VK_TRUE;
    r = vk.vkCreateSwapchainKHR(g.device, &sw, nullptr, &g.swapchain);
    if (r != VK_SUCCESS) { plog(true, "vkCreateSwapchainKHR=%d", int(r)); return false; }
    n = 0; vk.vkGetSwapchainImagesKHR(g.device, g.swapchain, &n, nullptr);
    g.images.resize(n); vk.vkGetSwapchainImagesKHR(g.device, g.swapchain, &n, g.images.data()); g.imageLayouts.assign(n, VK_IMAGE_LAYOUT_UNDEFINED);
    VkCommandPoolCreateInfo cpi { VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO }; cpi.flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT; cpi.queueFamilyIndex = g.family;
    VkFenceCreateInfo fci { VK_STRUCTURE_TYPE_FENCE_CREATE_INFO }; VkSemaphoreCreateInfo smi { VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO };
    ok = vk.vkCreateCommandPool(g.device, &cpi, nullptr, &g.pool) == VK_SUCCESS;
    VkCommandBufferAllocateInfo cba { VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO }; cba.commandPool = g.pool; cba.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY; cba.commandBufferCount = 1;
    ok = ok && vk.vkAllocateCommandBuffers(g.device, &cba, &g.cmd) == VK_SUCCESS && vk.vkCreateFence(g.device, &fci, nullptr, &g.acquireFence) == VK_SUCCESS
        && vk.vkCreateFence(g.device, &fci, nullptr, &g.submitFence) == VK_SUCCESS && vk.vkCreateSemaphore(g.device, &smi, nullptr, &g.renderDone) == VK_SUCCESS;
    if (ok && g.timers) { VkQueryPoolCreateInfo q { VK_STRUCTURE_TYPE_QUERY_POOL_CREATE_INFO }; q.queryType = VK_QUERY_TYPE_TIMESTAMP; q.queryCount = 4;
        if (vk.vkCreateQueryPool(g.device, &q, nullptr, &g.queries) != VK_SUCCESS) g.timers = false; }
    if (!ok) { plog(true, "command/fence/semaphore set-up failed"); return false; }
    // first frame: black at the canvas size, through the whole path (compose, blit, present, flip wait)
    std::vector<uint8_t> black(size_t(g.canvasHintW) * g.canvasHintH * 4, 0);
    for (size_t i = 3; i < black.size(); i += 4) black[i] = 255;
    if (presentLocked(black.data(), g.canvasHintW * 4, g.canvasHintW, g.canvasHintH)) { plog(true, "first frame failed"); return false; }
    plog(true, "READY in %.0f ms: %u swapchain images %ux%u, %s, frame source %s", nowMs() - t0, unsigned(g.images.size()), g.extent.width, g.extent.height,
        modeName(g.presentMode), g.optForceStaging || !g.hostImport ? "staging copy" : "import of the SDL surface (staging copy if refused)");
    return true;
}

void teardownLocked(const char* why)
{
    if (g.torndown.exchange(true)) return;
    if (g.hung) { plog(true, "teardown (%s): GPU hung: objects left for the system", why); return; }
    if (g.device) {
        g.vk.vkDeviceWaitIdle(g.device);
        releaseVideo();
        freeBuf(g.staging); freeBuf(g.readback); freeImg(g.canvas);
        if (g.queries) g.vk.vkDestroyQueryPool(g.device, g.queries, nullptr);
        if (g.renderDone) g.vk.vkDestroySemaphore(g.device, g.renderDone, nullptr);
        if (g.acquireFence) g.vk.vkDestroyFence(g.device, g.acquireFence, nullptr);
        if (g.submitFence) g.vk.vkDestroyFence(g.device, g.submitFence, nullptr);
        if (g.pool) g.vk.vkDestroyCommandPool(g.device, g.pool, nullptr);
        if (g.swapchain) g.vk.vkDestroySwapchainKHR(g.device, g.swapchain, nullptr);
        g.vk.vkDestroyDevice(g.device, nullptr); g.device = VK_NULL_HANDLE;
    }
    if (g.surface && g.vk.vkDestroySurfaceKHR) g.vk.vkDestroySurfaceKHR(g.instance, g.surface, nullptr);
    if (g.instance && g.vk.vkDestroyInstance) g.vk.vkDestroyInstance(g.instance, nullptr);
    g.surface = VK_NULL_HANDLE; g.instance = VK_NULL_HANDLE;
    plog(true, "teardown (%s): swapchain, display surface, device and instance destroyed; presents=%llu live buffers %ld images %ld memory %ld",
         why, (unsigned long long)g.presents, g.liveBuffers, g.liveImages, g.liveMemory);
}

// The PS-button close: the title's SIGTERM handler sets signalClose; this thread tears down outside the
// signal handler (waits for a present in flight, then frees everything, VideoOut included).
void reaperMain()
{
    bool watchdogFired = false;
    while (!g.torndown.load()) {
        // GPU hang watchdog: fences and acquires time out after 1 s inside the present; a driver call that never
        // returns (vkQueuePresentKHR) is caught here: after 5 s the title closes itself through its SIGTERM path
        // (children leave, decoders released, process ends; the system takes the display back).
        const int64_t since = g.presentSinceUs.load();
        if (since && !watchdogFired && int64_t(nowMs() * 1000) - since > 5000000) {
            watchdogFired = true; g.hung = true;
            plog(true, "WATCHDOG: a present has not returned for 5 s; closing the title through SIGTERM");
            kill(getpid(), SIGTERM);
        }
        if (g.signalClose.load()) {
            if (g.state.load() != kFailed) g.state.store(kStopped);
            std::unique_lock<std::mutex> l(g.lock, std::defer_lock);
            for (int i = 0; i < 100 && !l.try_lock(); ++i) usleep(2000);   // a present in flight takes <= ~1 frame
            if (!l.owns_lock()) { plog(true, "close: present still busy after 200 ms; left to the system"); g.torndown.store(true); return; }
            teardownLocked("PS-button close (signal)");
            return;
        }
        usleep(10000);
    }
}

} // namespace

// ---- SDL VideoOut stand-ins: SDL's references are renamed to these in the title's SDL copy -------------
struct OmniVideoOutAttr { uint8_t junk0[80]; };
extern "C" {
int sceVideoOutOpen(int, int, int, const void*);
void sceVideoOutClose(int);
int sceVideoOutAddFlipEvent(void*, int, void*);
int sceVideoOutSetFlipRate(int, int);
int sceVideoOutSubmitFlip(int, int, uint32_t, int64_t);
int sceVideoOutDeleteFlipEvent(void*, int);
void sceVideoOutSetBufferAttribute2(void*, uint64_t, uint32_t, uint32_t, uint32_t, uint64_t, uint32_t, uint64_t);
int sceVideoOutRegisterBuffers2(int, int, int, void*, int, void*, int, void*);
int sceVideoOutGetOutputStatus(int, void*);
}
static const int kFakeHandle = 0x6f6d;   // "om"
static uint64_t g_lastAttrFormat = 0;
static bool gpActive() { return g.state.load(std::memory_order_acquire) == kActive || g.state.load() == kStopped; }
// s2-gpu v5: true once set-up succeeded (SDL then holds the stand-in handle for the rest of the run). After a runtime
// failure SDL's own present must never run: its SubmitFlip is inert and its flip-event wait would never return.
static std::atomic<bool> g_everActive { false };
static bool gpOwned() { return g_everActive.load(std::memory_order_acquire); }
extern "C" int omni_gp_sceVideoOutOpen(int a, int b, int c, const void* d)
{
    if (gpActive()) { plog(false, "SDL asked for VideoOut: given a stand-in handle (RADV owns the display)"); return kFakeHandle; }
    return sceVideoOutOpen(a, b, c, d);
}
extern "C" void omni_gp_sceVideoOutClose(int h) { if (h == kFakeHandle) return; sceVideoOutClose(h); }
extern "C" int omni_gp_sceVideoOutAddFlipEvent(void* q, int h, void* u) { return h == kFakeHandle ? 0 : sceVideoOutAddFlipEvent(q, h, u); }
extern "C" int omni_gp_sceVideoOutSetFlipRate(int h, int r) { return h == kFakeHandle ? 0 : sceVideoOutSetFlipRate(h, r); }
extern "C" int omni_gp_sceVideoOutSubmitFlip(int h, int i, uint32_t m, int64_t a) { return h == kFakeHandle ? 0 : sceVideoOutSubmitFlip(h, i, m, a); }
extern "C" int omni_gp_sceVideoOutDeleteFlipEvent(void* q, int h) { return h == kFakeHandle ? 0 : sceVideoOutDeleteFlipEvent(q, h); }
extern "C" void omni_gp_sceVideoOutSetBufferAttribute2(void* attr, uint64_t fmt, uint32_t t, uint32_t w, uint32_t h, uint64_t o, uint32_t p, uint64_t x)
{
    g_lastAttrFormat = fmt;
    if (gpActive()) { memset(attr, 0, sizeof(OmniVideoOutAttr)); return; }
    sceVideoOutSetBufferAttribute2(attr, fmt, t, w, h, o, p, x);
}
extern "C" int omni_gp_sceVideoOutRegisterBuffers2(int h, int a, int b, void* bufs, int n, void* attr, int c, void* d)
{
    if (h != kFakeHandle) return sceVideoOutRegisterBuffers2(h, a, b, bufs, n, attr, c, d);
    // SDL tries an HDR (PQ) registration first when HDR is requested: refused here, so SDL keeps SDR, which is
    // all the GPU present shows (Stage A part 2 is SDR).
    if (g_lastAttrFormat == 0x8100070422000000ULL) { plog(false, "SDL's HDR buffer registration refused (GPU present is SDR)"); return int(0x80290001u); }
    return 0;
}
extern "C" int omni_gp_sceVideoOutGetOutputStatus(int h, void* status)
{
    if (h != kFakeHandle) return sceVideoOutGetOutputStatus(h, status);
    struct S { uint32_t resolution, range; uint64_t refresh, flags; uint32_t mode, reserved[5]; };
    S s {}; s.range = 1;   // SDR, as SDL expects for its SDR registration
    memcpy(status, &s, sizeof s);
    return 0;
}

// ---- SDL wraps (title link: --wrap=SDL_Init,SDL_Quit,SDL_UpdateWindowSurface,SDL_UpdateWindowSurfaceRects) ----
struct SDL_Window;
struct SDL_Rect { int x, y, w, h; };
struct OmniSDLPixelFormat { uint32_t format; };
struct OmniSDLSurface { uint32_t flags; OmniSDLPixelFormat* format; int w, h; int pitch; void* pixels; };   // SDL2 SDL_Surface prefix
extern "C" int __real_SDL_Init(uint32_t);
extern "C" void __real_SDL_Quit(void);
extern "C" int __real_SDL_UpdateWindowSurface(SDL_Window*);
extern "C" int __real_SDL_UpdateWindowSurfaceRects(SDL_Window*, const SDL_Rect*, int);
extern "C" OmniSDLSurface* SDL_GetWindowSurface(SDL_Window*);
extern "C" int SDL_SetError(const char*, ...);
extern "C" const char* SDL_GetHint(const char*);
static const uint32_t kSDLInitVideo = 0x20u, kSDLPixelFormatABGR8888 = 0x16762004u;

extern "C" int __wrap_SDL_Init(uint32_t flags)
{
    const char* driver = (flags & kSDLInitVideo) ? SDL_GetHint("SDL_VIDEODRIVER") : nullptr;
    if ((flags & kSDLInitVideo) && driver && !strcmp(driver, "dummy")) {
        if (g.state.load() == kOff && access(kFlagPath, F_OK) == 0) plog(true, "headless run (SDL dummy video driver): GPU present not used");
    } else if ((flags & kSDLInitVideo) && g.state.load() == kOff && access(kFlagPath, F_OK) == 0) {
        std::lock_guard<std::mutex> l(g.lock);
        if (bringUp()) {
            g.state.store(kActive, std::memory_order_release);
            g_everActive.store(true, std::memory_order_release);
            g.reaper = std::thread(reaperMain); g.reaper.detach();
        } else {
            plog(true, "OFF: set-up failed; tearing Vulkan down so SDL opens VideoOut and presents as before");
            g.hung = false; teardownLocked("set-up failed");
            g.state.store(kFailed, std::memory_order_release);
        }
    }
    return __real_SDL_Init(flags);
}
extern "C" void __wrap_SDL_Quit(void)
{
    if (gpOwned()) { g.state.store(kStopped); std::lock_guard<std::mutex> l(g.lock); logWindow(true); teardownLocked("SDL_Quit (Omni's Exit)"); }
    __real_SDL_Quit();
}
static int gpPresentWindow(SDL_Window* window)
{
    OmniSDLSurface* s = SDL_GetWindowSurface(window);
    if (!s || !s->pixels || !s->format) return SDL_SetError("GPU present: no window surface");
    if (s->format->format != kSDLPixelFormatABGR8888) return SDL_SetError("GPU present: window surface format 0x%x is not ABGR8888", s->format->format);
    std::lock_guard<std::mutex> l(g.lock);
    if (g.state.load() != kActive || g.torndown.load()) return SDL_SetError("GPU present stopped (see /data/omni/native/gpu-present.log)");
    const int rc = presentLocked(static_cast<const uint8_t*>(s->pixels), s->pitch, s->w, s->h);
    if (rc) {
        g.state.store(kFailed);
        plog(true, "OFF at runtime after %llu presents: every later present fails, so Omni closes cleanly (SDL holds no real VideoOut to fall back to)", (unsigned long long)g.presents);
        return SDL_SetError("GPU present failed (see /data/omni/native/gpu-present.log)");
    }
    return 0;
}
extern "C" int __wrap_SDL_UpdateWindowSurface(SDL_Window* window)
{
    if (!gpOwned()) return __real_SDL_UpdateWindowSurface(window);
    return gpPresentWindow(window);
}
extern "C" int __wrap_SDL_UpdateWindowSurfaceRects(SDL_Window* window, const SDL_Rect* rects, int n)
{
    if (!gpOwned()) return __real_SDL_UpdateWindowSurfaceRects(window, rects, n);
    return gpPresentWindow(window);   // the whole frame: the GPU copy is cheap and the source is imported
}

// ---- for the hole-punch (OmniHwService.cpp, weak there) and the title -----------------------------------
extern "C" int omni_gpu_present_active() { return g.state.load(std::memory_order_acquire) == kActive ? 1 : 0; }
extern "C" int omni_gpu_present_stage_video(const void* px, size_t bytes, int stride, int lx, int ly, int w, int h,
                                            const uint32_t* runs, size_t runWords, void (*release)(void*), void* cookie)
{
    if (g.state.load(std::memory_order_acquire) != kActive || !g.optVideo || !g.hostImport || !px || !runWords || stride <= 0 || (stride & 3)) return 0;
    std::lock_guard<std::mutex> l(g.lock);
    if (!g.optVideo) return 0;
    if (g.video.valid) releaseVideo();   // a staged frame that was never presented
    VideoStage& v = g.video;
    v.px = static_cast<const uint8_t*>(px); v.bytes = bytes; v.stride = stride; v.lx = lx; v.ly = ly; v.w = w; v.h = h;
    v.runs.assign(runs, runs + runWords); v.release = release; v.cookie = cookie; v.valid = true;
    return 1;
}
// SIGTERM path (OmniNativeTitle.cpp's handler): async-signal-safe; then waits (bounded) for the reaper.
extern "C" void omni_gpu_signal_close()
{
    if (!gpOwned()) return;
    g.signalClose.store(true);
}
extern "C" int omni_gpu_signal_wait(int ms)
{
    if (!g.signalClose.load()) return 1;
    for (int i = 0; i < ms / 5 && !g.torndown.load(); ++i) usleep(5000);
    return g.torndown.load() ? 1 : 0;
}
// Exit route (LoadExec hook), in case SDL_Quit was not reached.
extern "C" void omni_gpu_present_shutdown()
{
    if (!gpOwned()) return;
    g.state.store(kStopped);
    std::lock_guard<std::mutex> l(g.lock);
    teardownLocked("exit route");
}

#else  // OMNI_GPU_PRESENT_HOST_TEST
// ================================================================ host test: offscreen target (lavapipe)
namespace {
bool hostUp()
{
    Api& vk = g.vk;
    if (!loadI(VK_NULL_HANDLE, vk.vkCreateInstance, "vkCreateInstance")) return false;
    VkApplicationInfo app { VK_STRUCTURE_TYPE_APPLICATION_INFO }; app.apiVersion = VK_API_VERSION_1_3;
    VkInstanceCreateInfo ici { VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO }; ici.pApplicationInfo = &app;
    if (vk.vkCreateInstance(&ici, nullptr, &g.instance) != VK_SUCCESS) return false;
#define HI(name) loadI(g.instance, vk.name, #name)
    if (!(HI(vkDestroyInstance) && HI(vkEnumeratePhysicalDevices) && HI(vkGetPhysicalDeviceProperties2) && HI(vkGetPhysicalDeviceMemoryProperties)
        && HI(vkGetPhysicalDeviceQueueFamilyProperties) && HI(vkCreateDevice) && HI(vkGetDeviceProcAddr) && HI(vkGetPhysicalDeviceFormatProperties))) return false;
    uint32_t n = 1; vk.vkEnumeratePhysicalDevices(g.instance, &n, &g.physical);
    VkPhysicalDeviceExternalMemoryHostPropertiesEXT hp { VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_EXTERNAL_MEMORY_HOST_PROPERTIES_EXT };
    VkPhysicalDeviceProperties2 p2 { VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2, &hp }; vk.vkGetPhysicalDeviceProperties2(g.physical, &p2);
    g.timestampNs = p2.properties.limits.timestampPeriod; g.importAlign = hp.minImportedHostPointerAlignment; g.hostImport = g.importAlign && g.importAlign <= 4096;
    vk.vkGetPhysicalDeviceMemoryProperties(g.physical, &g.mem);
    const float prio = 1; VkDeviceQueueCreateInfo q { VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO }; q.queueCount = 1; q.pQueuePriorities = &prio;
    const char* de[1] = { VK_EXT_EXTERNAL_MEMORY_HOST_EXTENSION_NAME };
    VkDeviceCreateInfo d { VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO }; d.queueCreateInfoCount = 1; d.pQueueCreateInfos = &q; d.enabledExtensionCount = 1; d.ppEnabledExtensionNames = de;
    if (vk.vkCreateDevice(g.physical, &d, nullptr, &g.device) != VK_SUCCESS) return false;
#define HD(name) loadD(vk.name, #name)
    bool ok = HD(vkDestroyDevice) && HD(vkDeviceWaitIdle) && HD(vkGetDeviceQueue) && HD(vkCreateCommandPool) && HD(vkDestroyCommandPool) && HD(vkAllocateCommandBuffers)
        && HD(vkResetCommandBuffer) && HD(vkBeginCommandBuffer) && HD(vkEndCommandBuffer) && HD(vkCmdPipelineBarrier) && HD(vkCmdCopyBufferToImage) && HD(vkCmdCopyImageToBuffer)
        && HD(vkCmdBlitImage) && HD(vkCmdClearColorImage) && HD(vkCmdResetQueryPool) && HD(vkCmdWriteTimestamp) && HD(vkCreateQueryPool) && HD(vkDestroyQueryPool)
        && HD(vkGetQueryPoolResults) && HD(vkCreateFence) && HD(vkDestroyFence) && HD(vkResetFences) && HD(vkWaitForFences) && HD(vkQueueSubmit) && HD(vkCreateBuffer)
        && HD(vkDestroyBuffer) && HD(vkGetBufferMemoryRequirements) && HD(vkCreateImage) && HD(vkDestroyImage) && HD(vkGetImageMemoryRequirements) && HD(vkAllocateMemory)
        && HD(vkFreeMemory) && HD(vkBindBufferMemory) && HD(vkBindImageMemory) && HD(vkMapMemory) && HD(vkUnmapMemory) && HD(vkInvalidateMappedMemoryRanges)
        && HD(vkGetMemoryHostPointerPropertiesEXT);
    if (!ok) return false;
    vk.vkGetDeviceQueue(g.device, 0, 0, &g.queue);
    VkCommandPoolCreateInfo cpi { VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO }; cpi.flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT;
    vk.vkCreateCommandPool(g.device, &cpi, nullptr, &g.pool);
    VkCommandBufferAllocateInfo cba { VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO }; cba.commandPool = g.pool; cba.commandBufferCount = 1;
    vk.vkAllocateCommandBuffers(g.device, &cba, &g.cmd);
    VkFenceCreateInfo fci { VK_STRUCTURE_TYPE_FENCE_CREATE_INFO }; vk.vkCreateFence(g.device, &fci, nullptr, &g.submitFence);
    VkQueryPoolCreateInfo qp { VK_STRUCTURE_TYPE_QUERY_POOL_CREATE_INFO }; qp.queryType = VK_QUERY_TYPE_TIMESTAMP; qp.queryCount = 4;
    vk.vkCreateQueryPool(g.device, &qp, nullptr, &g.queries);
    return true;
}
}
static void hostRelease(void* cookie) { ++*static_cast<int*>(cookie); }
// Composes one frame offscreen (same recordCompose as the console) into an outW x outH RGBA image read back to `out`.
// Returns the number of pixels of the 1:1 composed canvas that differ from the CPU expectation (-1 on error).
extern "C" long omni_gpu_present_test(const uint8_t* frame, int pitch, int w, int h, const uint8_t* layer, size_t layerBytes, int stride,
    int lx, int ly, int lw, int lh, const uint32_t* runs, size_t runWords, int outW, int outH, uint8_t* out, int forceStaging, int* released)
{
    if (!g.device && !hostUp()) return -1;
    g.optForceStaging = forceStaging != 0; g.optVideo = true;
    if (!ensureCanvas(uint32_t(w), uint32_t(h))) return -1;
    Img target; VkImageCreateInfo ii { VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO };
    ii.imageType = VK_IMAGE_TYPE_2D; ii.format = VK_FORMAT_R8G8B8A8_UNORM; ii.extent = { uint32_t(outW), uint32_t(outH), 1 }; ii.mipLevels = 1; ii.arrayLayers = 1;
    ii.samples = VK_SAMPLE_COUNT_1_BIT; ii.tiling = VK_IMAGE_TILING_OPTIMAL; ii.usage = VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT;
    g.vk.vkCreateImage(g.device, &ii, nullptr, &target.image); g.liveImages++;
    VkMemoryRequirements req {}; g.vk.vkGetImageMemoryRequirements(g.device, target.image, &req);
    VkMemoryAllocateInfo ai { VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO }; ai.allocationSize = req.size; ai.memoryTypeIndex = uint32_t(findMemory(req.memoryTypeBits, 0));
    g.vk.vkAllocateMemory(g.device, &ai, nullptr, &target.memory); g.liveMemory++; g.vk.vkBindImageMemory(g.device, target.image, target.memory, 0);
    target.w = uint32_t(outW); target.h = uint32_t(outH);
    if (layer && runWords && released) {
        VideoStage& v = g.video; v.px = layer; v.bytes = layerBytes; v.stride = stride; v.lx = lx; v.ly = ly; v.w = lw; v.h = lh;
        v.runs.assign(runs, runs + runWords); v.release = hostRelease; v.cookie = released; v.valid = true;
    }
    Buf outBuf; makeHostBuffer(outBuf, VkDeviceSize(outW) * outH * 4, true, VK_BUFFER_USAGE_TRANSFER_DST_BIT);
    VkCommandBufferBeginInfo bi { VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO };
    g.vk.vkResetCommandBuffer(g.cmd, 0); g.vk.vkBeginCommandBuffer(g.cmd, &bi);
    Recorded rec; VkImageLayout lay = VK_IMAGE_LAYOUT_UNDEFINED;
    if (!recordCompose(frame, pitch, w, h, target.image, { uint32_t(outW), uint32_t(outH) }, lay, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, true, rec)) return -1;
    VkBufferImageCopy c {}; c.imageSubresource = { VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1 }; c.imageExtent = { uint32_t(outW), uint32_t(outH), 1 };
    g.vk.vkCmdCopyImageToBuffer(g.cmd, target.image, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, outBuf.buffer, 1, &c);
    g.vk.vkEndCommandBuffer(g.cmd);
    VkSubmitInfo si { VK_STRUCTURE_TYPE_SUBMIT_INFO }; si.commandBufferCount = 1; si.pCommandBuffers = &g.cmd;
    g.vk.vkResetFences(g.device, 1, &g.submitFence); g.vk.vkQueueSubmit(g.queue, 1, &si, g.submitFence);
    if (g.vk.vkWaitForFences(g.device, 1, &g.submitFence, VK_TRUE, 30ull * 1000 * 1000 * 1000) != VK_SUCCESS) return -1;
    long bad = 0;
    if (rec.readback) {
        // count differences against the CPU expectation (verifyComposed logs; recount here for the caller)
        const bool exact = verifyComposed(frame, pitch, w, h, rec.video);
        bad = exact ? 0 : 1;
    }
    memcpy(out, outBuf.mapped, size_t(outW) * outH * 4);
    freeBuf(rec.src); freeBuf(rec.layer); releaseVideo(); freeBuf(outBuf); freeImg(target);
    return bad;
}
extern "C" void omni_gpu_present_test_counts(long* buffers, long* images, long* memory) { *buffers = g.liveBuffers; *images = g.liveImages; *memory = g.liveMemory; }
#endif
