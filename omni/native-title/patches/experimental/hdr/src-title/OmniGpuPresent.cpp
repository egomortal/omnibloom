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
//
// OMNI_GPU_PRESENT_V2 (omni-native-s3.2-video), the 4K60 video path:
//  - no per-frame allocation: the SDL window surface is imported once (kept while the surface stays the same), the
//    hole-punch's layers are imported once each (the hole-punch calls omni_gpu_present_forget() before a layer's
//    memory goes), and when an import is refused the persistent staging buffer mirrors the surface, copying only the
//    damaged rows (SDL_UpdateWindowSurfaceRects' rects plus the video rectangle) instead of the whole frame;
//  - GPU timers in a ring of 3 query pairs, read 2 presents late without waiting;
//  - init order: SDL_Init brings RADV up here first, then OmniGpuVideo's device (omni_gpu_video_preinit), all
//    before any video decoder exists (Ex-Box's editor finding);
//  - OMNI_VIDEO_FPS_V1: one line per second in /data/omni/native/video-fps.log (decoded, shown, dropped, presents,
//    present interval, CPU and GPU time, GPU video conversions), for the GPU present and for SDL's own present;
//  - HDR, phase 2 (flag word `hdr`, default off): BT.2020 PQ output when the display offers HDR10 (ST 2084) and
//    Omni's HDR setting is on (/data/omni/hdr-auto.flag or hdr-presenter-test.flag); the SDR frame (page and video)
//    is mapped to PQ with SDR white at 203 nits (`hdrwhite=N`) by a compute pass, checked against a CPU reference
//    at set-up. Flag words: hdr, hdrwhite=N; failsetup (fails the set-up on purpose: the fallback check).
//
// OMNI_GPU_PRESENT_V3 (omni-video-4k60):
//  - one RADV device: omni_gpu_present_share() hands this device and queue to OmniGpuVideo (V3), so the title no longer
//    brings up a second device for the video; every vkQueueSubmit / vkQueuePresentKHR / vkDeviceWaitIdle on the shared
//    queue holds g_queueLock (Vulkan's external synchronisation rule), and teardown shuts the video module down first;
//  - OMNI_GPU_SURFACE_PAIR_V1 + OMNI_GPU_REGION_REUSE_V1 (Astra's 2026-11-04 proposals): the two SDL canvases the shell
//    exchanges are both kept imported (329 re-imports in 10 s before), and the video copy regions reuse one vector;
//  - FIFO stays the default on purpose: the hole-punch's V8 presenter picks "the picture due at the vblank this flip
//    reaches", which needs one flip per vblank and a blocking acquire (MAILBOX would let a later present replace a
//    queued one and break that accounting; it remains a flag word for experiments);
//  - OMNI_VIDEO_FPS_V2: the per-second line adds the GPU video's in-place / ring-copy counts, the shared-device state,
//    the present mode and the number of present intervals over 25 ms (a missed vblank at 60 Hz).
//
// OMNI_GPU_PRESENT_V4 (omni-native-s3.5-hdr), real HDR10 output:
//  - Omni's HDR setting (Off default / Auto / On, video-hdr-preference.txt) decides (OmniHdrPolicy::resolveMode); the
//    flag word `hdr` (+ hdr-auto.flag) still means On when no setting is saved, `hdrauto` means Auto;
//  - the HDR10 swapchain: A2B10G10R10 + VK_COLOR_SPACE_HDR10_ST2084_EXT, offered by the title's private RADV VideoOut
//    WSI member (Ex-Box PPSA99736's, console-shown SDR -> PQ -> SDR); every format the surface offers is logged and the
//    choice is deliberate; a refused HDR swapchain (or a failed first HDR frame) falls back to SDR at once, with the reason
//    in gpu-present.log; flag word `hdrfail` refuses it on purpose (the fallback test);
//  - page and UI: the SDR canvas -> BT.2020 PQ with SDR white at 203 nits (V2's checked pass), so menus are not blinding;
//  - HDR10 video: the hole-punch stages the picture's PQ layer (written by OmniGpuVideo V4 in the same GPU pass); after the
//    PQ pass its opaque video runs are copied over the canvas's, so PQ samples pass straight through (no tone mapping);
//    translucent (mix) pixels over the video keep the SDR mapping. HLG sources arrive already converted to PQ;
//  - Auto: HDR10 output only while an HDR video with a PQ layer fills the screen (0.5 s on, 1.5 s off), else SDR;
//  - omni_gpu_present_hdr_state() (0 SDR / 1 armed / 2 HDR now) for the hole-punch and the shell (what sites are told);
//  - OMNI_VIDEO_FPS_V3: the fps line adds out_mode, src_tf, src_bits, hdr_setting, hdr_switches, pq_frames;
//  - after a switch the VideoOut output range is logged (exbox_presenter_probe, from the WSI member; 1 SDR, 2 HDR).
#include <vulkan/vulkan.h>
#include "../engine/media/OmniHdrPreference.h"
#include "OmniHdrPolicy.h"
#include "../engine/media/OmniVideoStats.h"
#include "OmniPqOutShader.h"   // V2 HDR: SPIR-V of omni_pq_out.comp

#include <algorithm>
#include <atomic>
#include <cerrno>
#include <cmath>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <list>
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
[[maybe_unused]] static const char* const kFlagPath = "gpu-present.flag";
#else
extern "C" VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL vk_icdGetInstanceProcAddr(VkInstance, const char*) __attribute__((weak));
#define OMNI_GP_PROC(instance, name) (vk_icdGetInstanceProcAddr ? vk_icdGetInstanceProcAddr(instance, name) : nullptr)
static const char* const kLogPath = "/data/omni/native/gpu-present.log";
static const char* const kFlagPath = "/data/omni/gpu-present.flag";
#endif

// OMNI_GPU_PRESENT_V3: the queue is shared with OmniGpuVideo (V3); its submissions and presents are serialised here.
static std::mutex g_queueLock;
static void queueLock() { g_queueLock.lock(); }
static void queueUnlock() { g_queueLock.unlock(); }
extern "C" void omni_gpu_video_shutdown() __attribute__((weak));

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
    // V2 HDR (optional: loaded only for the PQ pass)
    VKFN(vkCreateImageView); VKFN(vkDestroyImageView); VKFN(vkCreateShaderModule); VKFN(vkDestroyShaderModule);
    VKFN(vkCreateDescriptorSetLayout); VKFN(vkDestroyDescriptorSetLayout); VKFN(vkCreatePipelineLayout); VKFN(vkDestroyPipelineLayout);
    VKFN(vkCreateComputePipelines); VKFN(vkDestroyPipeline); VKFN(vkCreateDescriptorPool); VKFN(vkDestroyDescriptorPool);
    VKFN(vkAllocateDescriptorSets); VKFN(vkUpdateDescriptorSets); VKFN(vkCmdBindPipeline); VKFN(vkCmdBindDescriptorSets);
    VKFN(vkCmdPushConstants); VKFN(vkCmdDispatch); VKFN(vkFlushMappedMemoryRanges);
};

struct Buf { VkBuffer buffer = VK_NULL_HANDLE; VkDeviceMemory memory = VK_NULL_HANDLE; VkDeviceSize size = 0; void* mapped = nullptr; bool coherent = true; bool imported = false; };
struct Img { VkImage image = VK_NULL_HANDLE; VkDeviceMemory memory = VK_NULL_HANDLE; uint32_t w = 0, h = 0; VkFormat format = VK_FORMAT_UNDEFINED; VkImageLayout layout = VK_IMAGE_LAYOUT_UNDEFINED; };

// The video runs the hole-punch staged for the next present (OmniHwService.cpp, presenter thread).
struct VideoStage {
    bool valid = false;
    const uint8_t* px = nullptr; size_t bytes = 0; int stride = 0, lx = 0, ly = 0, w = 0, h = 0;
    std::vector<uint32_t> runs;   // y, x, n triplets, canvas coordinates
    void (*release)(void*) = nullptr; void* cookie = nullptr;
    const uint8_t* pq = nullptr; size_t pqBytes = 0; uint32_t info = 0;   // V4: the picture's PQ layer (same stride), source info
};
static_assert(OmniHdrPolicy::kA2B10G10R10 == VK_FORMAT_A2B10G10R10_UNORM_PACK32 && OmniHdrPolicy::kA2R10G10B10 == VK_FORMAT_A2R10G10B10_UNORM_PACK32
              && OmniHdrPolicy::kHdr10St2084 == VK_COLOR_SPACE_HDR10_ST2084_EXT, "OmniHdrPolicy's Vulkan values");

enum State { kOff = 0, kActive = 1, kFailed = 2, kStopped = 3 };

// V2: an imported layer kept between frames (`dead`: forgotten while a present used it; freed after that present).
struct Cached { uintptr_t start = 0, end = 0; Buf b; VkDeviceSize offset = 0; uint64_t lastUse = 0; bool inUse = false, dead = false; };
constexpr size_t kMaxCachedLayers = 16;
constexpr int kQueryPairs = 3;
struct Rect { int x, y, w, h; };

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
    VkQueryPool queries = VK_NULL_HANDLE; int queryPair = 0; bool queryPending[kQueryPairs] = {};   // V2: ring of 3, read 2 presents late
    // canvas
    Img canvas; VkFormat canvasFormat = VK_FORMAT_R8G8B8A8_UNORM;
    Buf staging;   // persistent upload buffer (presents are synchronous: one is enough; kept, never per-upload)
    Buf readback;  // differential check
    // V2: the SDL surface imported once; staging mirror state; damage of the next present; imported layers
    // OMNI_GPU_SURFACE_PAIR_V1: SDL alternates two surfaces; exact pointer/size keys, bounded LRU.
    Buf frameImports[2]; const void* frameKeys[2] {}; size_t frameKeyBytes[2] {}; VkDeviceSize frameOffsets[2] {};
    uint64_t frameLastUse[2] {}, frameUseTick = 0; bool frameImportRefused = false;
    std::atomic<const void*> frameKeysSeen[2] {}; // lock-free FreeSurface hints; actual invalidation holds g.lock
    bool stagingValid = false; int stagingPitch = 0, stagingH = 0;
    bool damageFull = true; std::vector<Rect> damage;
    std::mutex cacheLock; std::list<Cached> layers; uint64_t useTick = 0;
    uint64_t frameHits = 0, layerHits = 0, stagingFull = 0, stagingRects = 0, forgets = 0;
    bool optDamage = false;
    // options
    bool optMailbox = false, optVideo = true, optVerify = true, optForceStaging = false, optForceImport = false;
    bool optHdr = false; int hdrWhite = 203;   // V2 phase 2
    bool optFailSetUp = false;   // V2: flag word failsetup (the console's fallback check)
    int optOutHeight = 0;   // 0 = match canvas
    int canvasHintW = 1920, canvasHintH = 1080;
    VideoStage video;
    std::vector<VkBufferImageCopy> videoRegions; // OMNI_GPU_REGION_REUSE_V1: retained scratch, protected by g.lock
    // checks / statistics
    int verifyPlain = 0, verifyVideo = 0;
    uint64_t presents = 0, imports = 0, importFails = 0, stagingCopies = 0, videoFrames = 0, videoRuns = 0;
    double sumCpu = 0, sumWait = 0, sumGpu = 0, maxCpu = 0, maxWait = 0, windowStart = 0; unsigned windowN = 0, windowLogs = 0, importFailLogs = 0;
    // live objects (lesson 8)
    std::atomic<long> liveBuffers { 0 }, liveImages { 0 }, liveMemory { 0 }, liveOwnKiB { 0 }, liveImportKiB { 0 };   // V2: atomic (forget runs on other threads)
    // V2 HDR (PQ output)
    bool hdr = false; Img pq; VkImageView canvasView = VK_NULL_HANDLE, pqView = VK_NULL_HANDLE;
    VkShaderModule pqShader = VK_NULL_HANDLE; VkDescriptorSetLayout pqSetLayout = VK_NULL_HANDLE; VkPipelineLayout pqLayout = VK_NULL_HANDLE;
    VkPipeline pqPipe = VK_NULL_HANDLE; VkDescriptorPool pqPool = VK_NULL_HANDLE; VkDescriptorSet pqSet = VK_NULL_HANDLE;
    Buf pqBuf;   // the packed PQ pixels (device memory), copied into `pq` for the blit
    // V4: `hdr` = HDR10 output now; pqArmed = the PQ pass is ready (canvas with a storage view, PQ image)
    bool pqArmed = false, hdrRefused = false, optHdrAuto = false, optHdrFail = false;
    OmniHdrPolicy::Mode hdrMode = OmniHdrPolicy::kOff; OmniHdrPolicy::AutoSwitch autoSw;
    std::atomic<int> hdrState { 0 };   // 0 SDR only, 1 armed (Auto, SDR now), 2 HDR10 output now
    std::atomic<uint32_t> srcInfo { 0 }; std::atomic<int64_t> srcInfoUs { 0 };
    unsigned hdrSwitches = 0; uint64_t pqFrames = 0; int rangeCheckIn = 0;
    VkFormat sdrFormat = VK_FORMAT_UNDEFINED, hdrFormat = VK_FORMAT_UNDEFINED; VkSurfaceCapabilitiesKHR caps {}; uint32_t imageCount = 2;
    std::vector<VkBufferImageCopy> pqRegions;   // retained scratch (as videoRegions)
    bool hung = false;
    double lastCpuMs = 0, lastGpuMs = -1;   // V2: for the fps line
    std::thread reaper;
    std::atomic<int64_t> presentSinceUs { 0 };   // watchdog: a present call in progress since (0 = none)
    std::atomic<bool> shared { false };   // V3: the device was handed to OmniGpuVideo (shut it down before ours goes)
};
Gp g;
void publishHdr()
{
    g.hdrState.store(g.hdr ? 2 : (g.pqArmed && g.hdrMode == OmniHdrPolicy::kAuto && !g.hdrRefused) ? 1 : 0, std::memory_order_release);
}

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
    if (b.memory) { g.vk.vkFreeMemory(g.device, b.memory, nullptr); g.liveMemory--; (b.imported ? g.liveImportKiB : g.liveOwnKiB) -= long(b.size / 1024); }
    b = Buf {};
}
void freeImg(Img& m)
{
    if (!g.device) { m = Img {}; return; }
    if (m.image) { g.vk.vkDestroyImage(g.device, m.image, nullptr); g.liveImages--; }
    if (m.memory) { g.vk.vkFreeMemory(g.device, m.memory, nullptr); g.liveMemory--; g.liveOwnKiB -= long(uint64_t(m.w) * m.h * 4 / 1024); }
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
    g.liveMemory++; b.size = size; g.liveOwnKiB += long(size / 1024);
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
            if (r == VK_SUCCESS) { g.liveMemory++; b.imported = true; b.size = end - start; g.liveImportKiB += long(b.size / 1024);
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

bool hdrEnsure(uint32_t w, uint32_t h);
bool ensureCanvas(uint32_t w, uint32_t h)
{
    if (g.canvas.image && g.canvas.w == w && g.canvas.h == h) return true;
    if (g.canvas.image) {
        plog(false, "canvas image %ux%u -> %ux%u", g.canvas.w, g.canvas.h, w, h);
        if (g.canvasView) { g.vk.vkDestroyImageView(g.device, g.canvasView, nullptr); g.canvasView = VK_NULL_HANDLE; }   // V2 HDR: the view goes first
        freeImg(g.canvas);
    }
    VkImageCreateInfo ii { VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO };
    ii.imageType = VK_IMAGE_TYPE_2D; ii.format = g.canvasFormat; ii.extent = { w, h, 1 }; ii.mipLevels = 1; ii.arrayLayers = 1;
    ii.samples = VK_SAMPLE_COUNT_1_BIT; ii.tiling = VK_IMAGE_TILING_OPTIMAL;
    ii.usage = VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT | (g.pqArmed ? VK_IMAGE_USAGE_STORAGE_BIT : 0u);   // V2: the PQ pass reads it (V4: armed)
    ii.sharingMode = VK_SHARING_MODE_EXCLUSIVE; ii.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
    if (g.vk.vkCreateImage(g.device, &ii, nullptr, &g.canvas.image) != VK_SUCCESS) return false;
    g.liveImages++;
    VkMemoryRequirements req {}; g.vk.vkGetImageMemoryRequirements(g.device, g.canvas.image, &req);
    int type = findMemory(req.memoryTypeBits, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT);
    if (type < 0) type = findMemory(req.memoryTypeBits, 0);
    VkMemoryAllocateInfo ai { VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO }; ai.allocationSize = req.size; ai.memoryTypeIndex = uint32_t(type);
    if (type < 0 || g.vk.vkAllocateMemory(g.device, &ai, nullptr, &g.canvas.memory) != VK_SUCCESS) { freeImg(g.canvas); return false; }
    g.liveMemory++; g.liveOwnKiB += long(uint64_t(w) * h * 4 / 1024);
    if (g.vk.vkBindImageMemory(g.device, g.canvas.image, g.canvas.memory, 0) != VK_SUCCESS) { freeImg(g.canvas); return false; }
    g.canvas.w = w; g.canvas.h = h; g.canvas.format = g.canvasFormat; g.canvas.layout = VK_IMAGE_LAYOUT_UNDEFINED;
    plog(false, "canvas image %ux%u format %d (%.1f MiB, memory type %d)", w, h, int(g.canvasFormat), req.size / 1048576.0, type);
    return !g.pqArmed || hdrEnsure(w, h);
}

// V2: the frame's source buffer: the SDL surface imported once (the same surface every frame), else the persistent
// staging mirror, where only the damaged rows are copied (the shell's rects plus the video rectangle).
// Caller holds g.lock; previous presents completed their fence. Never called after a hung present.
void clearFrameImports()
{
    for (size_t i = 0; i < 2; ++i) {
        freeBuf(g.frameImports[i]); g.frameKeys[i] = nullptr; g.frameKeyBytes[i] = 0;
        g.frameOffsets[i] = 0; g.frameLastUse[i] = 0; g.frameKeysSeen[i].store(nullptr, std::memory_order_release);
    }
}
bool frameSource(const uint8_t* pixels, int pitch, int w, int h, VkBuffer& buf, VkDeviceSize& off)
{
    const size_t bytes = size_t(pitch) * size_t(h);
    if (g.hostImport && !g.optForceStaging && !g.frameImportRefused) {
        for (size_t i = 0; i < 2; ++i)
            if (g.frameImports[i].buffer && g.frameKeys[i] == pixels && g.frameKeyBytes[i] == bytes) {
                buf = g.frameImports[i].buffer; off = g.frameOffsets[i]; g.frameLastUse[i] = ++g.frameUseTick;
                g.frameHits++; return true;
            }
        size_t slot = 2;
        // Re-size of the same pointer replaces its own slot; otherwise use empty, then least recent.
        for (size_t i = 0; i < 2; ++i) if (g.frameKeys[i] == pixels) { slot = i; break; }
        if (slot == 2) for (size_t i = 0; i < 2; ++i) if (!g.frameImports[i].buffer) { slot = i; break; }
        if (slot == 2) slot = g.frameLastUse[0] <= g.frameLastUse[1] ? 0 : 1;
        freeBuf(g.frameImports[slot]); g.frameKeys[slot] = nullptr; g.frameKeyBytes[slot] = 0;
        g.frameOffsets[slot] = 0; g.frameLastUse[slot] = 0; g.frameKeysSeen[slot].store(nullptr, std::memory_order_release);
        if (importHost(g.frameImports[slot], pixels, bytes, g.frameOffsets[slot])) {
            g.frameKeys[slot] = pixels; g.frameKeyBytes[slot] = bytes; g.frameLastUse[slot] = ++g.frameUseTick;
            g.frameKeysSeen[slot].store(pixels, std::memory_order_release);
            buf = g.frameImports[slot].buffer; off = g.frameOffsets[slot]; return true;
        }
        clearFrameImports(); // failed replacement must not leave a sibling import alive
        if (g.optForceImport) return false;
        g.frameImportRefused = true;
        plog(true, "the SDL surface import was refused: the persistent staging mirror is used from now on (damaged rows only)");
    }
    if (!g.staging.buffer || g.staging.size < bytes) {
        freeBuf(g.staging); g.stagingValid = false;
        if (!makeHostBuffer(g.staging, (bytes + 0xffff) & ~size_t(0xffff), false, VK_BUFFER_USAGE_TRANSFER_SRC_BIT)) { plog(true, "no staging buffer"); return false; }
    }
    uint8_t* m = static_cast<uint8_t*>(g.staging.mapped);
    if (!g.stagingValid || g.damageFull || g.stagingPitch != pitch || g.stagingH != h) {
        memcpy(m, pixels, bytes); g.stagingValid = true; g.stagingPitch = pitch; g.stagingH = h; g.stagingFull++;
    } else {
        for (const Rect& r : g.damage)
            for (int y = std::max(0, r.y); y < std::min(h, r.y + r.h); ++y) {
                const int x0 = std::max(0, r.x), x1 = std::min(w, r.x + r.w);
                if (x1 > x0) memcpy(m + size_t(y) * pitch + size_t(x0) * 4, pixels + size_t(y) * pitch + size_t(x0) * 4, size_t(x1 - x0) * 4);
            }
        g.stagingRects++;
    }
    if (!g.staging.coherent && g.vk.vkFlushMappedMemoryRanges) {
        VkMappedMemoryRange mr { VK_STRUCTURE_TYPE_MAPPED_MEMORY_RANGE }; mr.memory = g.staging.memory; mr.size = VK_WHOLE_SIZE;
        g.vk.vkFlushMappedMemoryRanges(g.device, 1, &mr);
    }
    g.stagingCopies++;
    buf = g.staging.buffer; off = 0;
    return true;
}

// V2: a layer imported once and kept (the hole-punch forgets it before its memory goes). nullptr: refused.
Cached* cachedLayer(const void* p, size_t bytes)
{
    if (!g.hostImport || !p || !bytes) return nullptr;
    const uintptr_t a = uintptr_t(g.importAlign);
    const uintptr_t start = uintptr_t(p) & ~(a - 1), end = (uintptr_t(p) + bytes + a - 1) & ~(a - 1);
    std::lock_guard<std::mutex> l(g.cacheLock);
    for (Cached& c : g.layers)
        if (!c.dead && c.start == start && c.end >= end) { c.inUse = true; c.lastUse = ++g.useTick; c.offset = uintptr_t(p) - start; g.layerHits++; return &c; }
    if (g.layers.size() >= kMaxCachedLayers) {
        auto old = g.layers.end();
        for (auto it = g.layers.begin(); it != g.layers.end(); ++it) if (!it->inUse && (old == g.layers.end() || it->lastUse < old->lastUse)) old = it;
        if (old != g.layers.end()) { freeBuf(old->b); g.layers.erase(old); }
    }
    Cached c; c.start = start; c.end = end;
    VkDeviceSize off = 0;
    if (!importHost(c.b, p, bytes, off)) return nullptr;
    c.offset = off; c.inUse = true; c.lastUse = ++g.useTick;
    g.layers.push_back(c);
    return &g.layers.back();
}
// After a present's fence: its layer is free again; forgotten ones go now.
void layersDone()
{
    std::lock_guard<std::mutex> l(g.cacheLock);
    for (auto it = g.layers.begin(); it != g.layers.end();) {
        it->inUse = false;
        if (it->dead) { freeBuf(it->b); it = g.layers.erase(it); } else ++it;
    }
}

// Records: source frame -> canvas image, staged video runs -> canvas image, [canvas -> read-back],
// canvas -> target (scaled, letterboxed to the canvas aspect). Target layout ends in `finalLayout`.
struct Recorded { Cached* layer = nullptr; bool video = false; bool readback = false; };
void recordPq(VkImage target, VkExtent2D tExt, VkImageLayout& tLayout, VkImageLayout finalLayout, int w, int h, bool video);
bool recordCompose(const uint8_t* pixels, int pitch, int w, int h, VkImage target, VkExtent2D tExt, VkImageLayout& tLayout, VkImageLayout finalLayout,
                   bool wantReadback, Recorded& rec)
{
    // the video rectangle is damaged too: the hole-punch writes its translucent (mix) pixels into the surface
    if (g.video.valid) g.damage.push_back(Rect { g.video.lx, g.video.ly, g.video.w, g.video.h });
    VkBuffer srcBuffer = VK_NULL_HANDLE; VkDeviceSize srcOff = 0;
    if (!frameSource(pixels, pitch, w, h, srcBuffer, srcOff)) return false;
    // video layer (pinned by OmniHwService until release()), imported once and kept
    rec.layer = g.video.valid && g.optVideo && !g.video.runs.empty() ? cachedLayer(g.video.px, g.video.bytes) : nullptr;
    rec.video = rec.layer != nullptr;
    const VkDeviceSize layerOff = rec.layer ? rec.layer->offset : 0;
    if (g.video.valid && g.optVideo && !rec.video && !g.video.runs.empty()) plog(false, "video layer import failed: this frame shows the canvas only in the video area");

    if (g.timers) g.vk.vkCmdResetQueryPool(g.cmd, g.queries, uint32_t(g.queryPair * 2), 2);
    if (g.timers) g.vk.vkCmdWriteTimestamp(g.cmd, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, g.queries, uint32_t(g.queryPair * 2));
    VkMemoryBarrier host { VK_STRUCTURE_TYPE_MEMORY_BARRIER }; host.srcAccessMask = VK_ACCESS_HOST_WRITE_BIT; host.dstAccessMask = VK_ACCESS_TRANSFER_READ_BIT;
    g.vk.vkCmdPipelineBarrier(g.cmd, VK_PIPELINE_STAGE_HOST_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 1, &host, 0, nullptr, 0, nullptr);
    barrier(g.canvas.image, VK_IMAGE_LAYOUT_UNDEFINED, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 0, VK_ACCESS_TRANSFER_WRITE_BIT, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT);
    VkBufferImageCopy whole {};
    whole.bufferOffset = srcOff; whole.bufferRowLength = uint32_t(pitch / 4); whole.bufferImageHeight = uint32_t(h);
    whole.imageSubresource = { VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1 }; whole.imageExtent = { uint32_t(w), uint32_t(h), 1 };
    g.vk.vkCmdCopyBufferToImage(g.cmd, srcBuffer, g.canvas.image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &whole);
    if (rec.video) {
        // the hole-punch, on the GPU: each run of video pixels comes straight from the layer (same channel order
        // as the canvas: holePunchAttach). Runs are clipped to the canvas and the layer.
        auto& regions = g.videoRegions; regions.clear(); regions.reserve(g.video.runs.size() / 3);
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
            g.vk.vkCmdCopyBufferToImage(g.cmd, rec.layer->b.buffer, g.canvas.image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, uint32_t(regions.size()), regions.data());
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
    if (g.hdr) {   // V2 phase 2: canvas -> PQ image (compute) -> target
        recordPq(target, tExt, tLayout, finalLayout, w, h, rec.video);
        if (g.timers) g.vk.vkCmdWriteTimestamp(g.cmd, VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT, g.queries, uint32_t(g.queryPair * 2 + 1));
        return true;
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

[[maybe_unused]] void logWindow(bool force)
{
    const double now = nowMs();
    if (!g.windowStart) g.windowStart = now;
    if (!force && (now - g.windowStart < 10000 || !g.windowN)) return;
    if (g.windowLogs++ < 200)
        plog(false, "10 s: presents %u, CPU in present avg %.2f ms (max %.2f), vblank wait avg %.2f ms (max %.2f), GPU %.3f ms; video frames %llu runs %llu; imports %llu (fails %llu) staging copies %llu; live buffers %ld images %ld memory objects %ld, own %.1f MiB, imported %.1f MiB",
            g.windowN, g.sumCpu / g.windowN, g.maxCpu, g.sumWait / g.windowN, g.maxWait, g.sumGpu / std::max(1u, g.windowN),
            (unsigned long long)g.videoFrames, (unsigned long long)g.videoRuns, (unsigned long long)g.imports, (unsigned long long)g.importFails,
            (unsigned long long)g.stagingCopies, g.liveBuffers.load(), g.liveImages.load(), g.liveMemory.load(), g.liveOwnKiB.load() / 1024.0, g.liveImportKiB.load() / 1024.0);
    g.windowStart = now; g.windowN = 0; g.sumCpu = g.sumWait = g.sumGpu = g.maxCpu = g.maxWait = 0;
}

// V2: the query pair written 2 presents ago, read without waiting (lesson 2); -1 = nothing ready.
[[maybe_unused]] double readOldTimer()
{
    if (!g.timers) return -1;
    const int old = (g.queryPair + 1) % kQueryPairs;   // the next pair to be reused is the oldest
    if (!g.queryPending[old]) return -1;
    uint64_t ts[2] = {};
    if (g.vk.vkGetQueryPoolResults(g.device, g.queries, uint32_t(old * 2), 2, sizeof ts, ts, sizeof ts[0], VK_QUERY_RESULT_64_BIT) != VK_SUCCESS) return -1;
    g.queryPending[old] = false;
    return ts[1] >= ts[0] ? double(ts[1] - ts[0]) * g.timestampNs / 1e6 : -1;
}

void releaseVideo()
{
    VideoStage& v = g.video;
    if (v.release) v.release(v.cookie);
    v.valid = false; v.release = nullptr; v.cookie = nullptr; v.px = nullptr; v.runs.clear(); v.pq = nullptr; v.pqBytes = 0; v.info = 0;
}


// ---- V2, HDR phase 2: the SDR frame -> BT.2020 PQ (common to the console and the host test) --------------------
struct PqPush { int32_t w, h; float white; int32_t pad; };
static_assert(sizeof(PqPush) == 16, "push constants of omni_pq_out.comp");
// CPU reference of omni_pq_out.comp (OmniHdrColour.h's formulas, double precision): one packed pixel.
uint32_t pqReference(uint8_t r8, uint8_t g8, uint8_t b8, double white)
{
    auto lin = [](double x) { return x <= 0.04045 ? x / 12.92 : std::pow((x + 0.055) / 1.055, 2.4); };
    auto pq = [](double nits) { const double m1 = 2610.0 / 16384, m2 = 2523.0 / 32, c1 = 3424.0 / 4096, c2 = 2413.0 / 128, c3 = 2392.0 / 128;
        const double p = std::pow(std::min(std::max(nits / 10000.0, 0.0), 1.0), m1); return std::pow((c1 + c2 * p) / (1 + c3 * p), m2); };
    const double r = lin(r8 / 255.0), gg = lin(g8 / 255.0), b = lin(b8 / 255.0);
    const double R = (0.6274038959 * r + 0.3292830384 * gg + 0.0433130657 * b) * white, G = (0.0690972894 * r + 0.9195403951 * gg + 0.0113623156 * b) * white,
                 B = (0.0163914389 * r + 0.0880133079 * gg + 0.8955952532 * b) * white;
    auto ten = [](double v) { return uint32_t(std::lround(std::min(std::max(v, 0.0), 1.0) * 1023)); };
    return ten(pq(R)) | (ten(pq(G)) << 10) | (ten(pq(B)) << 20) | 0xc0000000u;
}
bool loadHdrFns()
{
    return loadD(g.vk.vkCreateImageView, "vkCreateImageView") && loadD(g.vk.vkDestroyImageView, "vkDestroyImageView")
        && loadD(g.vk.vkCreateShaderModule, "vkCreateShaderModule") && loadD(g.vk.vkDestroyShaderModule, "vkDestroyShaderModule")
        && loadD(g.vk.vkCreateDescriptorSetLayout, "vkCreateDescriptorSetLayout") && loadD(g.vk.vkDestroyDescriptorSetLayout, "vkDestroyDescriptorSetLayout")
        && loadD(g.vk.vkCreatePipelineLayout, "vkCreatePipelineLayout") && loadD(g.vk.vkDestroyPipelineLayout, "vkDestroyPipelineLayout")
        && loadD(g.vk.vkCreateComputePipelines, "vkCreateComputePipelines") && loadD(g.vk.vkDestroyPipeline, "vkDestroyPipeline")
        && loadD(g.vk.vkCreateDescriptorPool, "vkCreateDescriptorPool") && loadD(g.vk.vkDestroyDescriptorPool, "vkDestroyDescriptorPool")
        && loadD(g.vk.vkAllocateDescriptorSets, "vkAllocateDescriptorSets") && loadD(g.vk.vkUpdateDescriptorSets, "vkUpdateDescriptorSets")
        && loadD(g.vk.vkCmdBindPipeline, "vkCmdBindPipeline") && loadD(g.vk.vkCmdBindDescriptorSets, "vkCmdBindDescriptorSets")
        && loadD(g.vk.vkCmdPushConstants, "vkCmdPushConstants") && loadD(g.vk.vkCmdDispatch, "vkCmdDispatch");
}
void hdrDestroy()
{
    if (!g.device) return;
    if (g.canvasView) g.vk.vkDestroyImageView(g.device, g.canvasView, nullptr);
    freeImg(g.pq); freeBuf(g.pqBuf);
    if (g.pqPipe) g.vk.vkDestroyPipeline(g.device, g.pqPipe, nullptr);
    if (g.pqLayout) g.vk.vkDestroyPipelineLayout(g.device, g.pqLayout, nullptr);
    if (g.pqSetLayout) g.vk.vkDestroyDescriptorSetLayout(g.device, g.pqSetLayout, nullptr);
    if (g.pqPool) g.vk.vkDestroyDescriptorPool(g.device, g.pqPool, nullptr);
    if (g.pqShader) g.vk.vkDestroyShaderModule(g.device, g.pqShader, nullptr);
    g.canvasView = VK_NULL_HANDLE; g.pqPipe = VK_NULL_HANDLE; g.pqLayout = VK_NULL_HANDLE; g.pqSetLayout = VK_NULL_HANDLE;
    g.pqPool = VK_NULL_HANDLE; g.pqSet = VK_NULL_HANDLE; g.pqShader = VK_NULL_HANDLE; g.hdr = false; g.pqArmed = false;
    publishHdr();
}
// The pipeline (once). The images/buffer follow the canvas size (hdrEnsure).
bool hdrSetUp()
{
    if (!loadHdrFns()) return false;
    VkShaderModuleCreateInfo smi { VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO }; smi.codeSize = sizeof kOmniPqOutSpv; smi.pCode = kOmniPqOutSpv;
    if (g.vk.vkCreateShaderModule(g.device, &smi, nullptr, &g.pqShader) != VK_SUCCESS) return false;
    VkDescriptorSetLayoutBinding b[2] {};
    b[0].binding = 0; b[0].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_IMAGE; b[0].descriptorCount = 1; b[0].stageFlags = VK_SHADER_STAGE_COMPUTE_BIT;
    b[1].binding = 1; b[1].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER; b[1].descriptorCount = 1; b[1].stageFlags = VK_SHADER_STAGE_COMPUTE_BIT;
    VkDescriptorSetLayoutCreateInfo dl { VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO }; dl.bindingCount = 2; dl.pBindings = b;
    if (g.vk.vkCreateDescriptorSetLayout(g.device, &dl, nullptr, &g.pqSetLayout) != VK_SUCCESS) return false;
    VkPushConstantRange range { VK_SHADER_STAGE_COMPUTE_BIT, 0, sizeof(PqPush) };
    VkPipelineLayoutCreateInfo pl { VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO }; pl.setLayoutCount = 1; pl.pSetLayouts = &g.pqSetLayout; pl.pushConstantRangeCount = 1; pl.pPushConstantRanges = &range;
    if (g.vk.vkCreatePipelineLayout(g.device, &pl, nullptr, &g.pqLayout) != VK_SUCCESS) return false;
    VkComputePipelineCreateInfo cp { VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO };
    cp.stage.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO; cp.stage.stage = VK_SHADER_STAGE_COMPUTE_BIT; cp.stage.module = g.pqShader; cp.stage.pName = "main"; cp.layout = g.pqLayout;
    if (g.vk.vkCreateComputePipelines(g.device, VK_NULL_HANDLE, 1, &cp, nullptr, &g.pqPipe) != VK_SUCCESS) return false;
    VkDescriptorPoolSize ps[2] = { { VK_DESCRIPTOR_TYPE_STORAGE_IMAGE, 1 }, { VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 1 } };
    VkDescriptorPoolCreateInfo dp { VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO }; dp.maxSets = 1; dp.poolSizeCount = 2; dp.pPoolSizes = ps;
    if (g.vk.vkCreateDescriptorPool(g.device, &dp, nullptr, &g.pqPool) != VK_SUCCESS) return false;
    VkDescriptorSetAllocateInfo da { VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO }; da.descriptorPool = g.pqPool; da.descriptorSetCount = 1; da.pSetLayouts = &g.pqSetLayout;
    return g.vk.vkAllocateDescriptorSets(g.device, &da, &g.pqSet) == VK_SUCCESS;
}
bool makeDeviceImage(Img& m, uint32_t w, uint32_t h, VkFormat f, VkImageUsageFlags usage)
{
    VkImageCreateInfo ii { VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO };
    ii.imageType = VK_IMAGE_TYPE_2D; ii.format = f; ii.extent = { w, h, 1 }; ii.mipLevels = 1; ii.arrayLayers = 1; ii.samples = VK_SAMPLE_COUNT_1_BIT;
    ii.tiling = VK_IMAGE_TILING_OPTIMAL; ii.usage = usage; ii.sharingMode = VK_SHARING_MODE_EXCLUSIVE; ii.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
    if (g.vk.vkCreateImage(g.device, &ii, nullptr, &m.image) != VK_SUCCESS) { m.image = VK_NULL_HANDLE; return false; }
    g.liveImages++;
    VkMemoryRequirements req {}; g.vk.vkGetImageMemoryRequirements(g.device, m.image, &req);
    int type = findMemory(req.memoryTypeBits, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT); if (type < 0) type = findMemory(req.memoryTypeBits, 0);
    VkMemoryAllocateInfo ai { VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO }; ai.allocationSize = req.size; ai.memoryTypeIndex = uint32_t(type);
    if (type < 0 || g.vk.vkAllocateMemory(g.device, &ai, nullptr, &m.memory) != VK_SUCCESS) { m.memory = VK_NULL_HANDLE; freeImg(m); return false; }
    g.liveMemory++; g.liveOwnKiB += long(uint64_t(w) * h * 4 / 1024);
    m.w = w; m.h = h; m.format = f; m.layout = VK_IMAGE_LAYOUT_UNDEFINED;
    if (g.vk.vkBindImageMemory(g.device, m.image, m.memory, 0) != VK_SUCCESS) { freeImg(m); return false; }
    return true;
}
bool hdrEnsure(uint32_t w, uint32_t h)
{
    if (g.canvasView) { g.vk.vkDestroyImageView(g.device, g.canvasView, nullptr); g.canvasView = VK_NULL_HANDLE; }
    freeImg(g.pq); freeBuf(g.pqBuf);
    VkImageViewCreateInfo vi { VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO }; vi.image = g.canvas.image; vi.viewType = VK_IMAGE_VIEW_TYPE_2D; vi.format = g.canvasFormat;
    vi.subresourceRange = { VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1 };
    if (g.vk.vkCreateImageView(g.device, &vi, nullptr, &g.canvasView) != VK_SUCCESS) { g.canvasView = VK_NULL_HANDLE; plog(true, "HDR: canvas view failed"); return false; }
    if (!makeDeviceImage(g.pq, w, h, VK_FORMAT_A2B10G10R10_UNORM_PACK32, VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT)) { plog(true, "HDR: PQ image failed"); return false; }
    VkBufferCreateInfo bi { VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO }; bi.size = VkDeviceSize(w) * h * 4; bi.usage = VK_BUFFER_USAGE_STORAGE_BUFFER_BIT | VK_BUFFER_USAGE_TRANSFER_SRC_BIT;
    if (g.vk.vkCreateBuffer(g.device, &bi, nullptr, &g.pqBuf.buffer) != VK_SUCCESS) { g.pqBuf.buffer = VK_NULL_HANDLE; return false; }
    g.liveBuffers++;
    VkMemoryRequirements req {}; g.vk.vkGetBufferMemoryRequirements(g.device, g.pqBuf.buffer, &req);
    int type = findMemory(req.memoryTypeBits, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT); if (type < 0) type = findMemory(req.memoryTypeBits, 0);
    VkMemoryAllocateInfo ai { VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO }; ai.allocationSize = req.size; ai.memoryTypeIndex = uint32_t(type);
    if (type < 0 || g.vk.vkAllocateMemory(g.device, &ai, nullptr, &g.pqBuf.memory) != VK_SUCCESS) { g.pqBuf.memory = VK_NULL_HANDLE; freeBuf(g.pqBuf); return false; }
    g.liveMemory++; g.pqBuf.size = bi.size; g.liveOwnKiB += long(bi.size / 1024);
    if (g.vk.vkBindBufferMemory(g.device, g.pqBuf.buffer, g.pqBuf.memory, 0) != VK_SUCCESS) { freeBuf(g.pqBuf); return false; }
    VkDescriptorImageInfo ii { VK_NULL_HANDLE, g.canvasView, VK_IMAGE_LAYOUT_GENERAL };
    VkDescriptorBufferInfo bo { g.pqBuf.buffer, 0, VK_WHOLE_SIZE };
    VkWriteDescriptorSet wr[2] {};
    wr[0].sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET; wr[0].dstSet = g.pqSet; wr[0].dstBinding = 0; wr[0].descriptorCount = 1; wr[0].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_IMAGE; wr[0].pImageInfo = &ii;
    wr[1].sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET; wr[1].dstSet = g.pqSet; wr[1].dstBinding = 1; wr[1].descriptorCount = 1; wr[1].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER; wr[1].pBufferInfo = &bo;
    g.vk.vkUpdateDescriptorSets(g.device, 2, wr, 0, nullptr);
    plog(false, "HDR: PQ image and buffer %ux%u", w, h);
    return true;
}
// Canvas (TRANSFER_SRC, composed) -> PQ buffer (compute) -> PQ image. Leaves the canvas in TRANSFER_SRC.
void recordPqPass(int w, int h)
{
    barrier(g.canvas.image, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, VK_IMAGE_LAYOUT_GENERAL, VK_ACCESS_TRANSFER_WRITE_BIT | VK_ACCESS_TRANSFER_READ_BIT, VK_ACCESS_SHADER_READ_BIT,
            VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT);
    g.vk.vkCmdBindPipeline(g.cmd, VK_PIPELINE_BIND_POINT_COMPUTE, g.pqPipe);
    g.vk.vkCmdBindDescriptorSets(g.cmd, VK_PIPELINE_BIND_POINT_COMPUTE, g.pqLayout, 0, 1, &g.pqSet, 0, nullptr);
    PqPush pc { w, h, float(g.hdrWhite), 0 };
    g.vk.vkCmdPushConstants(g.cmd, g.pqLayout, VK_SHADER_STAGE_COMPUTE_BIT, 0, sizeof pc, &pc);
    g.vk.vkCmdDispatch(g.cmd, uint32_t(w + 7) / 8, uint32_t(h + 7) / 8, 1);
    VkMemoryBarrier mb { VK_STRUCTURE_TYPE_MEMORY_BARRIER }; mb.srcAccessMask = VK_ACCESS_SHADER_WRITE_BIT; mb.dstAccessMask = VK_ACCESS_TRANSFER_READ_BIT;
    g.vk.vkCmdPipelineBarrier(g.cmd, VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 1, &mb, 0, nullptr, 0, nullptr);
    barrier(g.pq.image, VK_IMAGE_LAYOUT_UNDEFINED, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 0, VK_ACCESS_TRANSFER_WRITE_BIT, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT);
    VkBufferImageCopy c {}; c.bufferRowLength = uint32_t(w); c.imageSubresource = { VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1 }; c.imageExtent = { uint32_t(w), uint32_t(h), 1 };
    g.vk.vkCmdCopyBufferToImage(g.cmd, g.pqBuf.buffer, g.pq.image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &c);
    barrier(g.pq.image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, VK_ACCESS_TRANSFER_WRITE_BIT, VK_ACCESS_TRANSFER_READ_BIT,
            VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT);
    barrier(g.canvas.image, VK_IMAGE_LAYOUT_GENERAL, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, VK_ACCESS_SHADER_READ_BIT, VK_ACCESS_TRANSFER_READ_BIT,
            VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT);
}
// V4: HDR10 passthrough. The staged picture's PQ layer (written by OmniGpuVideo V4: PQ samples kept, HLG converted) is
// copied over the PQ image at the opaque video runs, after the SDR -> PQ pass; the translucent (mix) pixels and the page
// keep the 203-nit SDR mapping. A refused import leaves this frame's video SDR-mapped (counted).
void recordSourcePq(int w, int h)
{
    const VideoStage& v = g.video;
    if (!v.pq || !v.pqBytes) return;
    Cached* imported = cachedLayer(v.pq, v.pqBytes);   // a list entry: stays put; in use until layersDone()
    if (!imported) { static unsigned notes = 0; if (notes++ < 6) plog(true, "HDR: the PQ layer import failed: this frame's video stays SDR-mapped"); return; }
    const VkBuffer buffer = imported->b.buffer; const VkDeviceSize off = imported->offset;
    auto& regions = g.pqRegions; regions.clear(); regions.reserve(v.runs.size() / 3);
    for (size_t k = 0; k + 2 < v.runs.size(); k += 3) {
        const int y = int(v.runs[k]), x0 = int(v.runs[k + 1]); int n = int(v.runs[k + 2]);
        if (y < 0 || y >= h || x0 < 0 || x0 >= w || y - v.ly < 0 || y - v.ly >= v.h || x0 - v.lx < 0) continue;
        n = std::min({ n, w - x0, v.w - (x0 - v.lx) }); if (n <= 0) continue;
        VkBufferImageCopy c {};
        c.bufferOffset = off + VkDeviceSize(y - v.ly) * VkDeviceSize(v.stride) + VkDeviceSize(x0 - v.lx) * 4;
        c.bufferRowLength = uint32_t(v.stride / 4); c.bufferImageHeight = 1;
        c.imageSubresource = { VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1 }; c.imageOffset = { x0, y, 0 }; c.imageExtent = { uint32_t(n), 1, 1 };
        regions.push_back(c);
    }
    if (regions.empty()) return;
    VkMemoryBarrier host { VK_STRUCTURE_TYPE_MEMORY_BARRIER }; host.srcAccessMask = VK_ACCESS_HOST_WRITE_BIT; host.dstAccessMask = VK_ACCESS_TRANSFER_READ_BIT;
    g.vk.vkCmdPipelineBarrier(g.cmd, VK_PIPELINE_STAGE_HOST_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 1, &host, 0, nullptr, 0, nullptr);
    barrier(g.pq.image, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, VK_ACCESS_TRANSFER_WRITE_BIT | VK_ACCESS_TRANSFER_READ_BIT,
            VK_ACCESS_TRANSFER_WRITE_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT);
    g.vk.vkCmdCopyBufferToImage(g.cmd, buffer, g.pq.image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, uint32_t(regions.size()), regions.data());
    barrier(g.pq.image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, VK_ACCESS_TRANSFER_WRITE_BIT, VK_ACCESS_TRANSFER_READ_BIT,
            VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT);
    g.pqFrames++;
}
// The PQ pass, then the PQ image scaled to the target (letterboxed), as the SDR blit.
void recordPq(VkImage target, VkExtent2D tExt, VkImageLayout& tLayout, VkImageLayout finalLayout, int w, int h, bool video)
{
    recordPqPass(w, h);
    if (video) recordSourcePq(w, h);   // V4
    barrier(target, tLayout == VK_IMAGE_LAYOUT_PRESENT_SRC_KHR ? VK_IMAGE_LAYOUT_UNDEFINED : tLayout, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 0, VK_ACCESS_TRANSFER_WRITE_BIT,
            VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT);
    const double sx = double(tExt.width) / w, sy = double(tExt.height) / h, sc = std::min(sx, sy);
    const int dw = int(std::lround(w * sc)), dh = int(std::lround(h * sc)), dx = (int(tExt.width) - dw) / 2, dy = (int(tExt.height) - dh) / 2;
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
    g.vk.vkCmdBlitImage(g.cmd, g.pq.image, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, target, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &blit,
                        (dw == w && dh == h) ? VK_FILTER_NEAREST : VK_FILTER_LINEAR);
    barrier(target, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, finalLayout, VK_ACCESS_TRANSFER_WRITE_BIT,
            finalLayout == VK_IMAGE_LAYOUT_PRESENT_SRC_KHR ? 0 : VK_ACCESS_TRANSFER_READ_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT,
            finalLayout == VK_IMAGE_LAYOUT_PRESENT_SRC_KHR ? VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT : VK_PIPELINE_STAGE_TRANSFER_BIT);
    tLayout = finalLayout;
}
// Set-up check of the PQ pass against pqReference() on a pattern (every grey, colour ramps). Exact or 1 code off.
// Uses g.cmd / g.submitFence synchronously, before any present. Leaves the canvas at w x h.
bool hdrSelfTest(int w, int h, int* worstOut, long* offOut)
{
    if (!ensureCanvas(uint32_t(w), uint32_t(h))) return false;
    const size_t bytes = size_t(w) * h * 4;
    Buf up; if (!makeHostBuffer(up, bytes, false, VK_BUFFER_USAGE_TRANSFER_SRC_BIT)) return false;
    if (!g.readback.buffer || g.readback.size < bytes) { freeBuf(g.readback); if (!makeHostBuffer(g.readback, bytes, true, VK_BUFFER_USAGE_TRANSFER_DST_BIT)) { freeBuf(up); return false; } }
    uint8_t* px = static_cast<uint8_t*>(up.mapped);
    for (int y = 0; y < h; ++y) for (int x = 0; x < w; ++x) {
        uint8_t* p = px + (size_t(y) * w + x) * 4; const int v = (x + y * w) & 255;
        switch (y % 4) { case 0: p[0] = p[1] = p[2] = uint8_t(v); break; case 1: p[0] = uint8_t(v); p[1] = 0; p[2] = 0; break;
                         case 2: p[0] = 0; p[1] = uint8_t(v); p[2] = uint8_t(255 - v); break; default: p[0] = uint8_t(v); p[1] = uint8_t(v * 7); p[2] = uint8_t(v * 13); }
        p[3] = 255;
    }
    g.vk.vkResetCommandBuffer(g.cmd, 0);
    VkCommandBufferBeginInfo bi { VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO }; bi.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
    g.vk.vkBeginCommandBuffer(g.cmd, &bi);
    barrier(g.canvas.image, VK_IMAGE_LAYOUT_UNDEFINED, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 0, VK_ACCESS_TRANSFER_WRITE_BIT, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT);
    VkBufferImageCopy c {}; c.bufferRowLength = uint32_t(w); c.imageSubresource = { VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1 }; c.imageExtent = { uint32_t(w), uint32_t(h), 1 };
    g.vk.vkCmdCopyBufferToImage(g.cmd, up.buffer, g.canvas.image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &c);
    barrier(g.canvas.image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, VK_ACCESS_TRANSFER_WRITE_BIT, VK_ACCESS_TRANSFER_READ_BIT,
            VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT);
    recordPqPass(w, h);
    VkBufferImageCopy back {}; back.bufferRowLength = uint32_t(w); back.imageSubresource = { VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1 }; back.imageExtent = { uint32_t(w), uint32_t(h), 1 };
    g.vk.vkCmdCopyImageToBuffer(g.cmd, g.pq.image, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, g.readback.buffer, 1, &back);   // what the blit reads
    g.vk.vkEndCommandBuffer(g.cmd);
    VkSubmitInfo si { VK_STRUCTURE_TYPE_SUBMIT_INFO }; si.commandBufferCount = 1; si.pCommandBuffers = &g.cmd;
    g.vk.vkResetFences(g.device, 1, &g.submitFence);
    queueLock(); const VkResult sr = g.vk.vkQueueSubmit(g.queue, 1, &si, g.submitFence); queueUnlock();   // V3: shared queue
    bool ok = sr == VK_SUCCESS
        && g.vk.vkWaitForFences(g.device, 1, &g.submitFence, VK_TRUE, 5000ull * 1000 * 1000) == VK_SUCCESS;
    g.canvas.layout = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;
    int worst = 0; long off = 0;
    if (ok) {
        if (!g.readback.coherent) { VkMappedMemoryRange mr { VK_STRUCTURE_TYPE_MAPPED_MEMORY_RANGE }; mr.memory = g.readback.memory; mr.size = VK_WHOLE_SIZE; g.vk.vkInvalidateMappedMemoryRanges(g.device, 1, &mr); }
        const uint32_t* got = static_cast<const uint32_t*>(g.readback.mapped);
        for (size_t i = 0; i < size_t(w) * h; ++i) {
            const uint32_t want = pqReference(px[i * 4], px[i * 4 + 1], px[i * 4 + 2], g.hdrWhite);
            if (got[i] == want) continue;
            ++off;
            for (int s = 0; s < 30; s += 10) worst = std::max(worst, std::abs(int((got[i] >> s) & 1023) - int((want >> s) & 1023)));
            if ((got[i] >> 30) != 3) worst = 1024;
        }
    }
    freeBuf(up);
    if (worstOut) *worstOut = worst;
    if (offOut) *offOut = off;
    plog(true, "HDR self-test %dx%d (SDR white %d nits): %s, %ld of %d pixels off, worst %d codes -> %s", w, h, g.hdrWhite, ok ? "ran" : "FAILED to run", off, w * h, worst,
         ok && worst <= 1 ? "pass" : "FAIL");
    return ok && worst <= 1;
}

[[maybe_unused]] void teardownLocked(const char* why);

} // namespace

// V2: a layer's memory (OmniHwService.cpp) is about to be unmapped: drop its import. Any thread; never waits for a
// present (a present that still uses it frees it when its fence has signalled).
// The SDL surface's import goes the same way (the SDL_FreeSurface wrap; the host test): caller must not hold g.lock.
static void dropFrameImport(const void* p)
{
    if (!p || (p != g.frameKeysSeen[0].load(std::memory_order_acquire) && p != g.frameKeysSeen[1].load(std::memory_order_acquire))) return;
    std::lock_guard<std::mutex> l(g.lock); // a present in flight finishes first (presents are synchronous)
    if ((g.frameKeys[0] != p && g.frameKeys[1] != p) || g.hung) return;
    // The shell exchanges two SDL-owned canvas/window pixel pointers. Conservatively
    // discard both imports on either matching pointer before either allocation can be freed.
    plog(false, "the SDL window surface is freed: both cached frame imports go first");
    clearFrameImports();
}
extern "C" void omni_gpu_present_forget(const void* p)
{
    if (!p || !g.device) return;
    dropFrameImport(p);
    std::lock_guard<std::mutex> l(g.cacheLock);
    const uintptr_t at = uintptr_t(p);
    for (auto it = g.layers.begin(); it != g.layers.end();) {
        if (!it->dead && at >= it->start && at < it->end) {
            g.forgets++;
            if (it->inUse || g.hung) { it->dead = true; ++it; continue; }
            freeBuf(it->b); it = g.layers.erase(it); continue;
        }
        ++it;
    }
}

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
        else if (!strcmp(word, "hdr")) g.optHdr = true;   // V2 phase 2
        else if (!strcmp(word, "failsetup")) g.optFailSetUp = true;
        else if (!strcmp(word, "hdrauto")) g.optHdrAuto = true;   // V4: Auto when no HDR setting is saved
        else if (!strcmp(word, "hdrfail")) g.optHdrFail = true;   // V4: refuse the HDR10 swapchain on purpose (fallback test)
        else if (!strncmp(word, "hdrwhite=", 9)) g.hdrWhite = std::min(1000, std::max(80, atoi(word + 9)));
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
    queueLock();   // V3: the queue is shared with OmniGpuVideo; held for the submit and the present only
    VkResult r = g.vk.vkQueueSubmit(g.queue, 1, &si, g.submitFence);
    if (r != VK_SUCCESS) { queueUnlock(); plog(true, "vkQueueSubmit=%d", int(r)); return false; }
    VkPresentInfoKHR pi { VK_STRUCTURE_TYPE_PRESENT_INFO_KHR };
    pi.waitSemaphoreCount = 1; pi.pWaitSemaphores = &g.renderDone; pi.swapchainCount = 1; pi.pSwapchains = &g.swapchain; pi.pImageIndices = &g.acquired;
    VkPresentIdKHR pid { VK_STRUCTURE_TYPE_PRESENT_ID_KHR }; uint64_t id = ++g.presentId;
    if (g.presentWait) { pid.swapchainCount = 1; pid.pPresentIds = &id; pi.pNext = &pid; }
    r = g.vk.vkQueuePresentKHR(g.queue, &pi);
    queueUnlock();
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

// V4: a swapchain for SDR (g.sdrFormat, sRGB non-linear) or HDR10 (g.hdrFormat, HDR10_ST2084), replacing the current one
// (oldSwapchain, then destroyed: Ex-Box PPSA99736's proven order). *retired: the old one is gone (Vulkan retires it even
// when the creation fails; it is then destroyed here so the next attempt starts clean). Caller holds g.lock.
extern "C" int exbox_presenter_probe(uint32_t* range, int64_t* shown) __attribute__((weak));   // the private WSI member
bool makeSwapchain(bool hdr, bool* retired)
{
    *retired = false;
    if (hdr && g.optHdrFail) { plog(true, "HDR: the HDR10 swapchain is refused on purpose (flag word hdrfail: the fallback test)"); return false; }
    Api& vk = g.vk;
    if (g.swapchain) { queueLock(); vk.vkDeviceWaitIdle(g.device); queueUnlock(); }   // nothing of ours in flight on the old images
    VkSwapchainCreateInfoKHR sw { VK_STRUCTURE_TYPE_SWAPCHAIN_CREATE_INFO_KHR };
    sw.surface = g.surface; sw.minImageCount = g.caps.maxImageCount ? std::min(g.imageCount, g.caps.maxImageCount) : g.imageCount;
    sw.imageFormat = hdr ? g.hdrFormat : g.sdrFormat; sw.imageColorSpace = hdr ? VK_COLOR_SPACE_HDR10_ST2084_EXT : VK_COLOR_SPACE_SRGB_NONLINEAR_KHR;
    sw.imageExtent = g.extent; sw.imageArrayLayers = 1; sw.imageUsage = VK_IMAGE_USAGE_TRANSFER_DST_BIT; sw.imageSharingMode = VK_SHARING_MODE_EXCLUSIVE;
    sw.preTransform = VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR; sw.compositeAlpha = VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR;
    if (!(g.caps.supportedCompositeAlpha & VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR)) sw.compositeAlpha = VkCompositeAlphaFlagBitsKHR(g.caps.supportedCompositeAlpha & -g.caps.supportedCompositeAlpha);
    sw.presentMode = g.presentMode; sw.clipped = VK_TRUE; sw.oldSwapchain = g.swapchain;
    VkSwapchainKHR next = VK_NULL_HANDLE;
    const VkResult r = vk.vkCreateSwapchainKHR(g.device, &sw, nullptr, &next);
    if (g.swapchain) {   // retired either way
        *retired = true; vk.vkDestroySwapchainKHR(g.device, g.swapchain, nullptr); g.swapchain = VK_NULL_HANDLE;
        g.images.clear(); g.imageLayouts.clear(); g.acquired = UINT32_MAX;
    }
    if (r != VK_SUCCESS) { plog(true, "vkCreateSwapchainKHR(%s, format %d) = %d", hdr ? "HDR10 PQ" : "SDR", int(sw.imageFormat), int(r)); return false; }
    g.swapchain = next;
    uint32_t n = 0; vk.vkGetSwapchainImagesKHR(g.device, g.swapchain, &n, nullptr);
    g.images.resize(n); vk.vkGetSwapchainImagesKHR(g.device, g.swapchain, &n, g.images.data()); g.imageLayouts.assign(n, VK_IMAGE_LAYOUT_UNDEFINED);
    g.acquired = UINT32_MAX;
    g.hdr = hdr; publishHdr();
    g.rangeCheckIn = exbox_presenter_probe ? 30 : 0;   // the output range, 30 presents later
    plog(true, "swapchain: %s output, format %d, colour space %s, %u images %ux%u", hdr ? "HDR10 (BT.2020 PQ)" : "SDR", int(sw.imageFormat),
         hdr ? "HDR10_ST2084" : "SRGB_NONLINEAR", n, g.extent.width, g.extent.height);
    return true;
}
// V4: the output the setting wants, with the SDR fallback (OmniHdrPolicy::switchOutput). false: no swapchain at all.
bool setOutput(bool wantHdr, const char* why)
{
    bool refused = false, outHdr = false;
    const int rc = OmniHdrPolicy::switchOutput(wantHdr, g.swapchain != VK_NULL_HANDLE,
        [](bool hdr, bool* retired) { return makeSwapchain(hdr, retired); }, refused, outHdr);
    if (refused) {
        g.hdrRefused = true; g.hdr = outHdr; publishHdr();
        plog(true, "HDR: the HDR10 output was refused (%s): SDR output%s", why, rc == 0 ? "; HDR stays off for this run" : "");
    }
    if (rc < 0) { plog(true, "no swapchain could be made (%s)", why); return false; }
    return true;
}
// V4 Auto: once per present, before composing (caller holds g.lock). false: the output could not be restored.
bool autoTick(int canvasW, int canvasH)
{
    if (g.hdrMode != OmniHdrPolicy::kAuto || !g.pqArmed || g.hdrRefused) return true;
    const VideoStage& v = g.video;
    const bool eligible = v.valid && g.optVideo && v.pq && OmniHdrPolicy::fullscreen(v.lx, v.ly, v.w, v.h, canvasW, canvasH);
    const int d = g.autoSw.step(nowMs(), eligible, g.hdr);
    if (!d) return true;
    plog(true, "HDR Auto: %s (%s)", d > 0 ? "HDR10 output on" : "back to SDR output",
         d > 0 ? "an HDR video with a PQ layer has filled the screen for 0.5 s" : "no full-screen HDR video for 1.5 s");
    const bool ok = setOutput(d > 0, "Auto switch");
    if (ok) g.hdrSwitches++;
    return ok;
}
void rangeCheck()
{
    if (!g.rangeCheckIn || --g.rangeCheckIn || !exbox_presenter_probe) return;
    uint32_t range = 0; int64_t shown = 0;
    const int rc = exbox_presenter_probe(&range, &shown);
    plog(true, "VideoOut output range %u (1 SDR, 2 HDR; the console may report 2 for SDR when its HDR setting is Always On), query rc %d, flips shown %lld, %s output",
         range, rc, (long long)shown, g.hdr ? "HDR10" : "SDR");
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
    if (!autoTick(w, h)) return -1;   // V4
    if (!ensureCanvas(uint32_t(w), uint32_t(h))) { plog(true, "canvas image %dx%d failed", w, h); return -1; }
    if (g.acquired == UINT32_MAX) { double waited = 0; if (!acquireWait(waited)) return -1; }
    const bool videoNow = g.video.valid && g.optVideo && !g.video.runs.empty();
    const bool check = g.optVerify && ((!videoNow && g.verifyPlain < 3) || (videoNow && g.verifyVideo < 3));
    Recorded rec;
    if (!beginCmd()) return -1;
    VkImageLayout layout = g.imageLayouts[g.acquired];
    const bool composed = recordCompose(pixels, pitch, w, h, g.images[g.acquired], g.extent, layout, VK_IMAGE_LAYOUT_PRESENT_SRC_KHR, check, rec);
    g.damageFull = true; g.damage.clear();   // V2: the next present's damage starts empty (full unless the Rects wrap says)
    if (!composed) { g.vk.vkEndCommandBuffer(g.cmd); layersDone(); return -1; }
    if (g.vk.vkEndCommandBuffer(g.cmd) != VK_SUCCESS) { layersDone(); return -1; }
    const bool ok = submitAndWait();
    if (g.hung) return -1;   // nothing imported is released: the GPU may still read it
    if (g.timers) g.queryPending[g.queryPair] = true;
    const double gpuMs = readOldTimer(); g.queryPair = (g.queryPair + 1) % kQueryPairs;   // V2: 2 presents late, never waits
    g.lastGpuMs = gpuMs;
    if (ok && rec.readback) {
        const bool exact = verifyComposed(pixels, pitch, w, h, rec.video);
        if (rec.video) g.verifyVideo++; else g.verifyPlain++;
        if (!exact && rec.video && g.optVideo) { g.optVideo = false; plog(true, "video runs differ: the CPU writes the video again from now on"); }
        else if (!exact && !rec.video) { layersDone(); releaseVideo(); plog(true, "OFF: the presented frame differs from the canvas; present fails so Omni closes cleanly"); return -1; }
    }
    layersDone();   // the frame's fence has signalled: the layer is free (released on the GPU fence)
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
    g.presents++; g.windowN++; g.lastCpuMs = tCpu;
    rangeCheck();   // V4
    g.sumCpu += tCpu; g.maxCpu = std::max(g.maxCpu, tCpu); g.sumWait += waited; g.maxWait = std::max(g.maxWait, waited); g.sumGpu += std::max(0.0, gpuMs);
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
    plog(true, "start (OMNI_GPU_PRESENT_V4, omni-native-s3.5-hdr): canvas %dx%d (OMNI_SDL_HEIGHT=%s); options %s%s%s%s out=%d hdr=%s (white %d nits)", g.canvasHintW, g.canvasHintH, hEnv ? hEnv : "unset",
        g.optMailbox ? "mailbox " : "fifo ", g.optVideo ? "video " : "novideo ", g.optVerify ? "verify " : "noverify ",
        g.optForceStaging ? "staging" : g.optForceImport ? "import" : "import-or-staging", g.optOutHeight, g.optHdr ? "requested" : "off", g.hdrWhite);
    Api& vk = g.vk;
    if (g.optFailSetUp) { plog(true, "set-up failure forced by the flag word failsetup (fallback test)"); return false; }
    if (!loadI(VK_NULL_HANDLE, vk.vkCreateInstance, "vkCreateInstance") || !loadI(VK_NULL_HANDLE, vk.vkEnumerateInstanceExtensionProperties, "vkEnumerateInstanceExtensionProperties")) {
        plog(true, "no Vulkan driver linked"); return false; }
    uint32_t n = 0; vk.vkEnumerateInstanceExtensionProperties(nullptr, &n, nullptr);
    std::vector<VkExtensionProperties> iext(n); if (n) vk.vkEnumerateInstanceExtensionProperties(nullptr, &n, iext.data());
    bool hasDisplay = false, hasSurface = false, hasColourSpace = false;
    for (auto& e : iext) { plog(false, "instance extension %s", e.extensionName); hasDisplay |= !strcmp(e.extensionName, VK_KHR_DISPLAY_EXTENSION_NAME); hasSurface |= !strcmp(e.extensionName, VK_KHR_SURFACE_EXTENSION_NAME);
        hasColourSpace |= !strcmp(e.extensionName, VK_EXT_SWAPCHAIN_COLOR_SPACE_EXTENSION_NAME); }
    if (!hasDisplay || !hasSurface) { plog(true, "VK_KHR_display/VK_KHR_surface missing"); return false; }
    VkApplicationInfo app { VK_STRUCTURE_TYPE_APPLICATION_INFO }; app.pApplicationName = "Omni present"; app.pEngineName = "OmniGpuPresent"; app.apiVersion = VK_API_VERSION_1_3;
    // V4: Omni's HDR setting decides (OMNI_HDR_PREFERENCE_V1's file); legacy flag words only when none is saved.
    // (s3.4's code read the preference after computing hdrWanted, so a saved On never reached the swapchain: fixed.)
    {
        OmniHdrPreference::Value preference; OmniHdrPolicy::Inputs in;
        in.prefReadable = OmniHdrPreference::read("/data/omni/video-hdr-preference.txt", preference);
        in.prefExists = in.prefReadable && preference.exists; in.prefMode = preference.mode;
        in.flagHdr = g.optHdr; in.flagHdrAuto = g.optHdrAuto;
        in.legacySetting = access("/data/omni/hdr-auto.flag", F_OK) == 0 || access("/data/omni/hdr-presenter-test.flag", F_OK) == 0;
        const char* why = "";
        g.hdrMode = OmniHdrPolicy::resolveMode(in, &why);
        plog(true, "HDR setting: %s (%s); %s %s", OmniHdrPolicy::modeName(g.hdrMode), why, VK_EXT_SWAPCHAIN_COLOR_SPACE_EXTENSION_NAME, hasColourSpace ? "present" : "MISSING");
    }
    const bool hdrWanted = g.hdrMode != OmniHdrPolicy::kOff && hasColourSpace;
    const char* ie[3] = { VK_KHR_SURFACE_EXTENSION_NAME, VK_KHR_DISPLAY_EXTENSION_NAME, VK_EXT_SWAPCHAIN_COLOR_SPACE_EXTENSION_NAME };
    VkInstanceCreateInfo ici { VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO }; ici.pApplicationInfo = &app; ici.enabledExtensionCount = hdrWanted ? 3 : 2; ici.ppEnabledExtensionNames = ie;
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
    // V2: command buffer, fences and timers first (the HDR set-up check below submits work before the swapchain exists)
    VkCommandPoolCreateInfo cpi { VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO }; cpi.flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT; cpi.queueFamilyIndex = g.family;
    VkFenceCreateInfo fci { VK_STRUCTURE_TYPE_FENCE_CREATE_INFO }; VkSemaphoreCreateInfo smi { VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO };
    ok = vk.vkCreateCommandPool(g.device, &cpi, nullptr, &g.pool) == VK_SUCCESS;
    VkCommandBufferAllocateInfo cba { VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO }; cba.commandPool = g.pool; cba.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY; cba.commandBufferCount = 1;
    ok = ok && vk.vkAllocateCommandBuffers(g.device, &cba, &g.cmd) == VK_SUCCESS && vk.vkCreateFence(g.device, &fci, nullptr, &g.acquireFence) == VK_SUCCESS
        && vk.vkCreateFence(g.device, &fci, nullptr, &g.submitFence) == VK_SUCCESS && vk.vkCreateSemaphore(g.device, &smi, nullptr, &g.renderDone) == VK_SUCCESS;
    if (ok && g.timers) { VkQueryPoolCreateInfo q { VK_STRUCTURE_TYPE_QUERY_POOL_CREATE_INFO }; q.queryType = VK_QUERY_TYPE_TIMESTAMP; q.queryCount = 2 * kQueryPairs;
        if (vk.vkCreateQueryPool(g.device, &q, nullptr, &g.queries) != VK_SUCCESS) g.timers = false; }
    if (!ok) { plog(true, "command/fence/semaphore set-up failed"); return false; }

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
    g.sdrFormat = g.swapFormat;
    // V4: every surface format was logged above; HDR10 = a 10-bit ST 2084 format (A2B10G10R10 first), the PQ pass and its
    // set-up check. "Armed" = ready to show HDR10 (On: from the first frame; Auto: while an HDR video fills the screen).
    if (hdrWanted) {
        std::vector<uint32_t> fmts(n), spaces(n);
        for (uint32_t i = 0; i < n; ++i) { fmts[i] = uint32_t(sf[i].format); spaces[i] = uint32_t(sf[i].colorSpace); }
        const int hdrPick = OmniHdrPolicy::pickHdrFormat(fmts.data(), spaces.data(), n);
        VkFormatProperties pqF {}, swF {};
        vk.vkGetPhysicalDeviceFormatProperties(g.physical, VK_FORMAT_A2B10G10R10_UNORM_PACK32, &pqF);
        if (hdrPick >= 0) vk.vkGetPhysicalDeviceFormatProperties(g.physical, sf[hdrPick].format, &swF);
        const bool pqBlit = (pqF.optimalTilingFeatures & VK_FORMAT_FEATURE_BLIT_SRC_BIT) && (pqF.optimalTilingFeatures & VK_FORMAT_FEATURE_SAMPLED_IMAGE_FILTER_LINEAR_BIT)
            && (swF.optimalTilingFeatures & VK_FORMAT_FEATURE_BLIT_DST_BIT);
        VkFormatProperties cvF {}; vk.vkGetPhysicalDeviceFormatProperties(g.physical, VK_FORMAT_R8G8B8A8_UNORM, &cvF);
        const bool storage = cvF.optimalTilingFeatures & VK_FORMAT_FEATURE_STORAGE_IMAGE_BIT;
        if (hdrPick < 0) plog(true, "HDR: the display surface offers no 10-bit HDR10 (ST 2084) format (stock VideoOut WSI?): SDR output");
        else if (!pqBlit || !storage) plog(true, "HDR: blit %d / storage %d support missing: SDR output", int(pqBlit), int(storage));
        else if (isSrgb(g.sdrFormat)) plog(true, "HDR: the SDR format %d is sRGB-typed; the shared UNORM canvas needs a UNORM SDR format: SDR output", int(g.sdrFormat));
        else {
            g.canvasFormat = VK_FORMAT_R8G8B8A8_UNORM; g.pqArmed = true;
            int worst = 0; long off = 0;
            if (hdrSetUp() && hdrSelfTest(256, 64, &worst, &off)) {
                g.hdrFormat = sf[hdrPick].format;
                plog(true, "HDR: armed (%s): HDR10 format %d (surface format %d), colour space HDR10_ST2084, BT.2020 PQ, page and UI at SDR white %d nits, HDR10 video passed through",
                     OmniHdrPolicy::modeName(g.hdrMode), int(g.hdrFormat), hdrPick, g.hdrWhite);
            } else {
                plog(true, "HDR: the PQ pass failed its set-up check: SDR output");
                hdrDestroy(); freeImg(g.canvas); g.canvasFormat = isSrgb(g.swapFormat) ? VK_FORMAT_R8G8B8A8_SRGB : VK_FORMAT_R8G8B8A8_UNORM;
            }
        }
    }
    publishHdr();
    VkFormatProperties fpS {}, fpD {};
    vk.vkGetPhysicalDeviceFormatProperties(g.physical, g.canvasFormat, &fpS); vk.vkGetPhysicalDeviceFormatProperties(g.physical, g.swapFormat, &fpD);   // V4: the SDR blit (the HDR one was checked when armed)
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
    // V4: the swapchain through makeSwapchain (also used by Auto's switches): HDR10 from the start only with On
    g.caps = caps; g.imageCount = imageCount;
    if (!setOutput(g.pqArmed && g.hdrMode == OmniHdrPolicy::kOn, "start-up")) return false;
    // first frame: black at the canvas size, through the whole path (compose, blit, present, flip wait)
    std::vector<uint8_t> black(size_t(g.canvasHintW) * g.canvasHintH * 4, 0);
    for (size_t i = 3; i < black.size(); i += 4) black[i] = 255;
    if (presentLocked(black.data(), g.canvasHintW * 4, g.canvasHintW, g.canvasHintH)) {
        if (!g.hdr || g.hung) { plog(true, "first frame failed"); return false; }
        // V4: the first HDR10 frame failed (VideoOut refused the PQ buffers late?): SDR, and the black frame again
        plog(true, "HDR: the first HDR10 frame failed: SDR output");
        g.hdrRefused = true;
        if (!setOutput(false, "first HDR frame failed") || presentLocked(black.data(), g.canvasHintW * 4, g.canvasHintW, g.canvasHintH)) { plog(true, "first frame failed"); return false; }
        publishHdr();
    }
    plog(true, "READY in %.0f ms: %u swapchain images %ux%u, %s, %s output, frame source %s; layers imported once", nowMs() - t0, unsigned(g.images.size()), g.extent.width, g.extent.height,
        modeName(g.presentMode), g.hdr ? "HDR10 PQ" : "SDR", g.optForceStaging || !g.hostImport ? "staging mirror (damaged rows)" : "the SDL surface imported once (staging mirror if refused)");
    return true;
}

void teardownLocked(const char* why)
{
    if (g.torndown.exchange(true)) return;
    if (g.hung) { plog(true, "teardown (%s): GPU hung: objects left for the system", why); return; }
    std::vector<VkBufferImageCopy>().swap(g.videoRegions); // release CPU scratch at normal teardown
    std::vector<VkBufferImageCopy>().swap(g.pqRegions);   // V4
    // V3: the video module uses this device: it frees its objects first (waits for its own conversion, bounded).
    if (g.shared.exchange(false) && omni_gpu_video_shutdown) omni_gpu_video_shutdown();
    if (g.device) {
        { std::lock_guard<std::mutex> q(g_queueLock); g.vk.vkDeviceWaitIdle(g.device); }
        releaseVideo();
        hdrDestroy();   // its views first
        freeBuf(g.staging); freeBuf(g.readback); freeImg(g.canvas); clearFrameImports();
        { std::lock_guard<std::mutex> c(g.cacheLock); for (Cached& e : g.layers) freeBuf(e.b); g.layers.clear(); }
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
         why, (unsigned long long)g.presents, g.liveBuffers.load(), g.liveImages.load(), g.liveMemory.load());
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

// ---- OMNI_VIDEO_FPS_V1 (omni-native-s3.2-video): one line per second for the 4K60 gates ---------------------------
// On while gpu-present.flag, gpu-video.flag or video-fps.flag exists (checked at SDL_Init). Counts every present
// (the GPU present, or SDL's own when it is off) and reads the hole-punch's and OmniGpuVideo's totals (weak).
extern "C" int omni_hw_video_counters(uint64_t*, uint64_t*, uint64_t*, uint64_t*) __attribute__((weak));
extern "C" void omni_gpu_video_stats(uint64_t*, uint64_t*, uint64_t*) __attribute__((weak));
extern "C" void omni_gpu_video_stats2(uint64_t*, uint64_t*, int*) __attribute__((weak));   // OMNI_VIDEO_FPS_V2
extern "C" void omni_gpu_video_stats3(uint64_t*) __attribute__((weak));   // OMNI_VIDEO_FPS_V3 (OmniGpuVideo V4)
extern "C" int omni_gpu_video_preinit() __attribute__((weak));
static const char* const kFpsPath = "/data/omni/native/video-fps.log";
struct FpsWindow {
    std::mutex m; bool on = false; unsigned lines = 0;
    OmniVideoStatsSnapshot snapshot; bool previousTelemetryCounters = false;
    double start = 0, last = 0, sumInterval = 0, maxInterval = 0, sumCpu = 0, sumGpu = 0; unsigned n = 0, gpuN = 0, intervals = 0;
    uint64_t hw[4] {}, vid[3] {}; bool haveHw = false;
    unsigned late25 = 0; uint64_t vid2[2] {};   // OMNI_VIDEO_FPS_V2: intervals over 25 ms; in-place / ring-copy totals
    uint64_t pq = 0, vid3 = 0;   // OMNI_VIDEO_FPS_V3: PQ passthrough frames / PQ layers written, at the last line
};
static FpsWindow g_fps;
// OMNI_VIDEO_STATS_BRIDGE_V1. Bounded read; never waits on a present.
extern "C" int omni_video_stats_snapshot(OmniVideoStatsSnapshot* out)
{
    if (!out) return 0;
    std::unique_lock<std::mutex> lock(g_fps.m, std::try_to_lock);
    if (!lock.owns_lock() || g_fps.snapshot.atMs <= 0 || nowMs()-g_fps.snapshot.atMs > 2000) return 0;
    *out=g_fps.snapshot;
    return 1;
}

static void fpsStart()
{
    g_fps.on = access(kFlagPath, F_OK) == 0 || access("/data/omni/gpu-video.flag", F_OK) == 0 || access("/data/omni/video-fps.flag", F_OK) == 0;
    if (!g_fps.on) return;
    if (FILE* f = fopen(kFpsPath, "a")) {
        fprintf(f, "FPS-START t=%.3f build=omni-native-s3.5-hdr OMNI_VIDEO_FPS_V3 fields: path presents fps decoded shown dropped late interval_avg_ms interval_max_ms intervals_over_25ms present_cpu_ms present_gpu_ms video_gpu_pictures video_wall_ms video_gpu_ms video_in_place video_ring_copies shared_device mode out_mode src_tf src_bits hdr_setting hdr_switches pq_frames video_pq_layers\n", nowMs() / 1000.0);
        fclose(f);
    }
}
// After each present: path "gpu" (cpuMs = CPU in the GPU present, gpuMs its GPU time or -1) or "sdl" (cpuMs = SDL's
// whole present call, flip wait included; no GPU time).
static void fpsTick(const char* path, double cpuMs, double gpuMs)
{
    // Sampling is available without enabling disk logging.
    std::lock_guard<std::mutex> l(g_fps.m);
    FpsWindow& f = g_fps;
    const double now = nowMs();
    if (f.last) { const double iv = now - f.last; f.sumInterval += iv; f.maxInterval = std::max(f.maxInterval, iv); f.intervals++; if (iv > 25.0) f.late25++; }
    f.last = now; f.n++; f.sumCpu += cpuMs; if (gpuMs >= 0) { f.sumGpu += gpuMs; f.gpuN++; }
    if (!f.start) f.start = now;
    if (now - f.start < 1000) return;
    uint64_t hw[4] = {}, vid[3] = {};
    const bool haveHw = omni_hw_video_counters && omni_hw_video_counters(&hw[0], &hw[1], &hw[2], &hw[3]);
    if (omni_gpu_video_stats) omni_gpu_video_stats(&vid[0], &vid[1], &vid[2]);
    uint64_t vid2[2] = {}; int sharedDev = 0;
    if (omni_gpu_video_stats2) omni_gpu_video_stats2(&vid2[0], &vid2[1], &sharedDev);
    uint64_t vid3 = 0; if (omni_gpu_video_stats3) omni_gpu_video_stats3(&vid3);   // OMNI_VIDEO_FPS_V3
    // V3: the source of the video staged in the last 1.5 s (bits | transfer << 8): PQ / HLG / SDR, 8 / 10 bits; "-" = none
    const uint32_t si = g.srcInfo.load(std::memory_order_relaxed); const bool siFresh = si && int64_t(now * 1000) - g.srcInfoUs.load(std::memory_order_relaxed) < 1500000;
    const int tf = int((si >> 8) & 255);
    const char* srcTf = !siFresh ? "-" : tf == 16 ? "PQ" : tf == 18 ? "HLG" : "SDR";
    char srcBits[8]; if (siFresh) snprintf(srcBits, sizeof srcBits, "%u", si & 255u); else snprintf(srcBits, sizeof srcBits, "-");
    auto d = [](uint64_t now, uint64_t before) { return now >= before ? now - before : 0; };   // a new stream restarts its counts
    const double secs = (now - f.start) / 1000.0;
    const bool countsValid=haveHw && f.previousTelemetryCounters && hw[1]>=f.hw[1] && hw[2]>=f.hw[2];
    f.snapshot={now,secs,double(countsValid?hw[1]-f.hw[1]:0),double(countsValid?hw[2]-f.hw[2]:0),countsValid,!strcmp(path,"gpu"),!strcmp(path,"gpu")&&g.hdr};
    f.previousTelemetryCounters=haveHw;

    const uint64_t vp = d(vid[0], f.vid[0]);
    char gpuText[32]; if (f.gpuN) snprintf(gpuText, sizeof gpuText, "%.3f", f.sumGpu / f.gpuN); else snprintf(gpuText, sizeof gpuText, "-");
    if (f.on && f.lines++ < 20000)
        if (FILE* out = fopen(kFpsPath, "a")) {
            fprintf(out, "FPS t=%.3f path=%s out=%ux%u hdr=%d presents=%u fps=%.2f decoded=%llu shown=%llu dropped=%llu late=%llu interval_avg_ms=%.2f interval_max_ms=%.2f intervals_over_25ms=%u present_cpu_ms=%.3f present_gpu_ms=%s video_gpu_pictures=%llu video_wall_ms=%.3f video_gpu_ms=%.3f video_in_place=%llu video_ring_copies=%llu shared_device=%d mode=%s out_mode=%s src_tf=%s src_bits=%s hdr_setting=%s hdr_switches=%u pq_frames=%llu video_pq_layers=%llu%s\n",
                now / 1000.0, path, g.extent.width, g.extent.height, int(g.hdr), f.n, f.n / secs,
                (unsigned long long)(haveHw && f.haveHw ? d(hw[0], f.hw[0]) : 0), (unsigned long long)(haveHw && f.haveHw ? d(hw[1], f.hw[1]) : 0),
                (unsigned long long)(haveHw && f.haveHw ? d(hw[2], f.hw[2]) : 0), (unsigned long long)(haveHw && f.haveHw ? d(hw[3], f.hw[3]) : 0),
                f.intervals ? f.sumInterval / f.intervals : 0.0, f.maxInterval, f.late25, f.sumCpu / f.n, gpuText, (unsigned long long)vp,
                vp ? d(vid[1], f.vid[1]) / 1000.0 / double(vp) : 0.0, vp ? d(vid[2], f.vid[2]) / 1000.0 / double(vp) : 0.0,
                (unsigned long long)d(vid2[0], f.vid2[0]), (unsigned long long)d(vid2[1], f.vid2[1]), sharedDev,
                !strcmp(path, "gpu") ? modeName(g.presentMode) : "sdl-vblank",
                !strcmp(path, "gpu") && g.hdr ? "HDR" : "SDR", srcTf, srcBits, OmniHdrPolicy::modeName(g.hdrMode), g.hdrSwitches,
                (unsigned long long)(g.pqFrames - f.pq), (unsigned long long)(vid3 - std::min(vid3, f.vid3)),
                haveHw && f.haveHw ? "" : " (hole-punch counters busy or absent)");
            fclose(out);
        }
    if (haveHw) { memcpy(f.hw, hw, sizeof hw); f.haveHw = true; }
    memcpy(f.vid, vid, sizeof vid); memcpy(f.vid2, vid2, sizeof vid2); f.pq = g.pqFrames; f.vid3 = vid3;
    f.start = now; f.late25 = 0; f.n = f.gpuN = f.intervals = 0; f.sumInterval = f.maxInterval = f.sumCpu = f.sumGpu = 0;
}

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
    // V2 init order: RADV comes up (above, then OmniGpuVideo's device here) before any video decoder takes its share.
    static bool videoInitDone = false;
    if ((flags & kSDLInitVideo) && !videoInitDone && !(driver && !strcmp(driver, "dummy"))) {
        videoInitDone = true;
        if (omni_gpu_video_preinit) omni_gpu_video_preinit();
        fpsStart();
    }
    return __real_SDL_Init(flags);
}
// V2 (title link: --wrap=SDL_FreeSurface): the window surface's import goes before SDL frees the surface.
extern "C" void __real_SDL_FreeSurface(OmniSDLSurface*);
extern "C" void __wrap_SDL_FreeSurface(OmniSDLSurface* s)
{
    if (s && s->pixels) dropFrameImport(s->pixels);
    __real_SDL_FreeSurface(s);
}
extern "C" void __wrap_SDL_Quit(void)
{
    if (gpOwned()) { g.state.store(kStopped); std::lock_guard<std::mutex> l(g.lock); logWindow(true); teardownLocked("SDL_Quit (Omni's Exit)"); }
    __real_SDL_Quit();
}
static int gpPresentWindow(SDL_Window* window, const SDL_Rect* rects, int nRects)
{
    OmniSDLSurface* s = SDL_GetWindowSurface(window);
    if (!s || !s->pixels || !s->format) return SDL_SetError("GPU present: no window surface");
    if (s->format->format != kSDLPixelFormatABGR8888) return SDL_SetError("GPU present: window surface format 0x%x is not ABGR8888", s->format->format);
    std::lock_guard<std::mutex> l(g.lock);
    if (g.state.load() != kActive || g.torndown.load()) return SDL_SetError("GPU present stopped (see /data/omni/native/gpu-present.log)");
    // V2: the damage (used by the staging mirror only; the imported surface is copied whole on the GPU)
    g.damageFull = !rects || nRects <= 0; g.damage.clear();
    for (int i = 0; rects && i < nRects; ++i) g.damage.push_back(Rect { rects[i].x, rects[i].y, rects[i].w, rects[i].h });
    const int rc = presentLocked(static_cast<const uint8_t*>(s->pixels), s->pitch, s->w, s->h);
    if (!rc) fpsTick("gpu", g.lastCpuMs, g.lastGpuMs);
    if (rc) {
        g.state.store(kFailed);
        plog(true, "OFF at runtime after %llu presents: every later present fails, so Omni closes cleanly (SDL holds no real VideoOut to fall back to)", (unsigned long long)g.presents);
        return SDL_SetError("GPU present failed (see /data/omni/native/gpu-present.log)");
    }
    return 0;
}
extern "C" int __wrap_SDL_UpdateWindowSurface(SDL_Window* window)
{
    if (!gpOwned()) {
        const double t0 = nowMs(); const int rc = __real_SDL_UpdateWindowSurface(window);
        if (!rc) fpsTick("sdl", nowMs() - t0, -1);
        return rc;
    }
    return gpPresentWindow(window, nullptr, 0);
}
extern "C" int __wrap_SDL_UpdateWindowSurfaceRects(SDL_Window* window, const SDL_Rect* rects, int n)
{
    if (!gpOwned()) {
        const double t0 = nowMs(); const int rc = __real_SDL_UpdateWindowSurfaceRects(window, rects, n);
        if (!rc) fpsTick("sdl", nowMs() - t0, -1);
        return rc;
    }
    return gpPresentWindow(window, rects, n);   // the whole frame is composed; the rects only limit the staging mirror's copy
}

// ---- for the hole-punch (OmniHwService.cpp, weak there) and the title -----------------------------------
extern "C" int omni_gpu_present_active() { return g.state.load(std::memory_order_acquire) == kActive ? 1 : 0; }
// V4: with the picture's PQ layer (pq: same stride and size as px; used only while info bit 31 says it was written) and
// the source info word (bits | transfer << 8 | primaries << 16 | PQ layer valid << 31) for the fps line and Auto.
extern "C" int omni_gpu_present_stage_video_hdr(const void* px, size_t bytes, int stride, int lx, int ly, int w, int h,
                                                const uint32_t* runs, size_t runWords, const void* pq, size_t pqBytes, uint32_t info,
                                                void (*release)(void*), void* cookie)
{
    if (g.state.load(std::memory_order_acquire) != kActive || !g.optVideo || !g.hostImport || !px || !runWords || stride <= 0 || (stride & 3)) return 0;
    std::lock_guard<std::mutex> l(g.lock);
    if (!g.optVideo) return 0;
    if (g.video.valid) releaseVideo();   // a staged frame that was never presented
    VideoStage& v = g.video;
    v.px = static_cast<const uint8_t*>(px); v.bytes = bytes; v.stride = stride; v.lx = lx; v.ly = ly; v.w = w; v.h = h;
    v.runs.assign(runs, runs + runWords); v.release = release; v.cookie = cookie; v.valid = true;
    const bool pqOk = (info & 0x80000000u) && pq && h > 0 && pqBytes >= size_t(stride) * size_t(h);
    v.pq = pqOk ? static_cast<const uint8_t*>(pq) : nullptr; v.pqBytes = pqOk ? pqBytes : 0; v.info = info;
    if (info) { g.srcInfo.store(info, std::memory_order_relaxed); g.srcInfoUs.store(int64_t(nowMs() * 1000), std::memory_order_relaxed); }
    return 1;
}
extern "C" int omni_gpu_present_stage_video(const void* px, size_t bytes, int stride, int lx, int ly, int w, int h,
                                            const uint32_t* runs, size_t runWords, void (*release)(void*), void* cookie)
{
    return omni_gpu_present_stage_video_hdr(px, bytes, stride, lx, ly, w, h, runs, runWords, nullptr, 0, 0, release, cookie);
}
// V4: 0 SDR only, 1 armed (HDR Auto on an HDR10 display, SDR now), 2 HDR10 output now. The hole-punch makes PQ layers from 1.
extern "C" int omni_gpu_present_hdr_state()
{
    return g.state.load(std::memory_order_acquire) == kActive ? g.hdrState.load(std::memory_order_acquire) : 0;
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
        && HD(vkGetMemoryHostPointerPropertiesEXT) && HD(vkFlushMappedMemoryRanges);
    if (!ok) return false;
    vk.vkGetDeviceQueue(g.device, 0, 0, &g.queue);
    VkCommandPoolCreateInfo cpi { VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO }; cpi.flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT;
    vk.vkCreateCommandPool(g.device, &cpi, nullptr, &g.pool);
    VkCommandBufferAllocateInfo cba { VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO }; cba.commandPool = g.pool; cba.commandBufferCount = 1;
    vk.vkAllocateCommandBuffers(g.device, &cba, &g.cmd);
    VkFenceCreateInfo fci { VK_STRUCTURE_TYPE_FENCE_CREATE_INFO }; vk.vkCreateFence(g.device, &fci, nullptr, &g.submitFence);
    VkQueryPoolCreateInfo qp { VK_STRUCTURE_TYPE_QUERY_POOL_CREATE_INFO }; qp.queryType = VK_QUERY_TYPE_TIMESTAMP; qp.queryCount = 2 * kQueryPairs;
    vk.vkCreateQueryPool(g.device, &qp, nullptr, &g.queries);
    return true;
}
}
static void hostRelease(void* cookie) { ++*static_cast<int*>(cookie); }
// Composes one frame offscreen (same recordCompose as the console) into an outW x outH RGBA image read back to `out`.
// Returns the number of pixels of the 1:1 composed canvas that differ from the CPU expectation (-1 on error).
// V2: rects = damage of the next call (n < 0: full); hdr: PQ output (the target is A2B10G10R10, read back to `out`).
static std::vector<Rect> s_testDamage; static bool s_testDamageFull = true;
extern "C" void omni_gpu_present_test_damage(const int* rects, int n)
{
    s_testDamageFull = n < 0; s_testDamage.clear();
    for (int i = 0; i < n; ++i) s_testDamage.push_back(Rect { rects[4 * i], rects[4 * i + 1], rects[4 * i + 2], rects[4 * i + 3] });
}
extern "C" long omni_gpu_present_test_hdr_selftest(int white, int* worst, long* off)
{
    if (!g.device && !hostUp()) return -1;
    if (!g.pqPipe && !hdrSetUp()) return -1;
    g.hdr = true; g.pqArmed = true; g.hdrWhite = white;
    return hdrSelfTest(256, 64, worst, off) ? 0 : 1;
}
extern "C" void omni_gpu_present_test_hdr(int on, int white) { g.hdr = on != 0 && (g.pqPipe || hdrSetUp()); g.pqArmed = g.hdr; g.hdrWhite = white; if (g.canvas.image && !g.canvasView && g.hdr) { freeImg(g.canvas); } }
// V4: the PQ layer staged with the next omni_gpu_present_test() video (nullptr: none).
static const uint8_t* s_testPq = nullptr; static size_t s_testPqBytes = 0; static uint32_t s_testPqInfo = 0;
extern "C" void omni_gpu_present_test_source_pq(const void* pq, size_t bytes, uint32_t info) { s_testPq = static_cast<const uint8_t*>(pq); s_testPqBytes = bytes; s_testPqInfo = info; }
extern "C" void omni_gpu_present_test_pq_stats(uint64_t* pqFrames, size_t* pqRegionsCap) { *pqFrames = g.pqFrames; *pqRegionsCap = g.pqRegions.capacity(); }
extern "C" long omni_gpu_present_test_pq_reference(uint8_t r, uint8_t gg, uint8_t b, int white) { return long(pqReference(r, gg, b, white)); }
extern "C" long omni_gpu_present_test(const uint8_t* frame, int pitch, int w, int h, const uint8_t* layer, size_t layerBytes, int stride,
    int lx, int ly, int lw, int lh, const uint32_t* runs, size_t runWords, int outW, int outH, uint8_t* out, int forceStaging, int* released)
{
    if (!g.device && !hostUp()) return -1;
    g.optForceStaging = forceStaging != 0; g.optVideo = true;
    g.damageFull = s_testDamageFull; g.damage = s_testDamage; s_testDamageFull = true; s_testDamage.clear();
    if (!ensureCanvas(uint32_t(w), uint32_t(h))) return -1;
    Img target; VkImageCreateInfo ii { VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO };
    ii.imageType = VK_IMAGE_TYPE_2D; ii.format = g.hdr ? VK_FORMAT_A2B10G10R10_UNORM_PACK32 : VK_FORMAT_R8G8B8A8_UNORM; ii.extent = { uint32_t(outW), uint32_t(outH), 1 }; ii.mipLevels = 1; ii.arrayLayers = 1;
    ii.samples = VK_SAMPLE_COUNT_1_BIT; ii.tiling = VK_IMAGE_TILING_OPTIMAL; ii.usage = VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT;
    g.vk.vkCreateImage(g.device, &ii, nullptr, &target.image); g.liveImages++;
    VkMemoryRequirements req {}; g.vk.vkGetImageMemoryRequirements(g.device, target.image, &req);
    VkMemoryAllocateInfo ai { VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO }; ai.allocationSize = req.size; ai.memoryTypeIndex = uint32_t(findMemory(req.memoryTypeBits, 0));
    g.vk.vkAllocateMemory(g.device, &ai, nullptr, &target.memory); g.liveMemory++; g.vk.vkBindImageMemory(g.device, target.image, target.memory, 0);
    target.w = uint32_t(outW); target.h = uint32_t(outH);
    if (layer && runWords && released) {
        VideoStage& v = g.video; v.px = layer; v.bytes = layerBytes; v.stride = stride; v.lx = lx; v.ly = ly; v.w = lw; v.h = lh;
        v.runs.assign(runs, runs + runWords); v.release = hostRelease; v.cookie = released; v.valid = true;
        const bool pqOk = s_testPq && (s_testPqInfo & 0x80000000u) && s_testPqBytes >= size_t(stride) * size_t(lh);   // V4 (as the console stage)
        v.pq = pqOk ? s_testPq : nullptr; v.pqBytes = pqOk ? s_testPqBytes : 0; v.info = s_testPqInfo;
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
    g.vk.vkResetFences(g.device, 1, &g.submitFence); queueLock(); g.vk.vkQueueSubmit(g.queue, 1, &si, g.submitFence); queueUnlock();
    if (g.vk.vkWaitForFences(g.device, 1, &g.submitFence, VK_TRUE, 30ull * 1000 * 1000 * 1000) != VK_SUCCESS) return -1;
    long bad = 0;
    if (rec.readback) {
        // count differences against the CPU expectation (verifyComposed logs; recount here for the caller)
        const bool exact = verifyComposed(frame, pitch, w, h, rec.video);
        bad = exact ? 0 : 1;
    }
    memcpy(out, outBuf.mapped, size_t(outW) * outH * 4);
    g.damageFull = true; g.damage.clear();
    layersDone(); releaseVideo(); freeBuf(outBuf); freeImg(target);
    return bad;
}
extern "C" void omni_gpu_present_test_counts(long* buffers, long* images, long* memory) { *buffers = g.liveBuffers.load(); *images = g.liveImages.load(); *memory = g.liveMemory.load(); }
extern "C" void omni_gpu_present_test_cache(size_t* layers, uint64_t* frameHits, uint64_t* layerHits, uint64_t* stagingFull, uint64_t* stagingRects)
{
    std::lock_guard<std::mutex> l(g.cacheLock);
    *layers = g.layers.size(); *frameHits = g.frameHits; *layerHits = g.layerHits; *stagingFull = g.stagingFull; *stagingRects = g.stagingRects;
}
extern "C" void omni_gpu_present_test_frame_cache(size_t* count, uint64_t* imports, uint64_t* hits)
{
    std::lock_guard<std::mutex> l(g.lock);
    *count = size_t(g.frameImports[0].buffer != VK_NULL_HANDLE) + size_t(g.frameImports[1].buffer != VK_NULL_HANDLE);
    *imports = g.imports; *hits = g.frameHits;
}
extern "C" void omni_gpu_present_test_teardown(long* buffers, long* images, long* memory)   // everything the module made, then the live counts
{
    std::lock_guard<std::mutex> l(g.lock);
    std::vector<VkBufferImageCopy>().swap(g.videoRegions); // host teardown mirrors normal scratch release
    std::vector<VkBufferImageCopy>().swap(g.pqRegions);   // V4
    if (!g.device) return;
    if (g.shared.exchange(false) && omni_gpu_video_shutdown) omni_gpu_video_shutdown();   // V3: as the console teardown
    { std::lock_guard<std::mutex> q(g_queueLock); g.vk.vkDeviceWaitIdle(g.device); }
    releaseVideo();
    freeBuf(g.staging); freeBuf(g.readback); clearFrameImports();
    if (g.canvasView) { g.vk.vkDestroyImageView(g.device, g.canvasView, nullptr); g.canvasView = VK_NULL_HANDLE; }
    freeImg(g.canvas);
    { std::lock_guard<std::mutex> c(g.cacheLock); for (Cached& e : g.layers) freeBuf(e.b); g.layers.clear(); }
    hdrDestroy();
    *buffers = g.liveBuffers.load(); *images = g.liveImages.load(); *memory = g.liveMemory.load();
    if (g.queries) g.vk.vkDestroyQueryPool(g.device, g.queries, nullptr);
    if (g.submitFence) g.vk.vkDestroyFence(g.device, g.submitFence, nullptr);
    if (g.pool) g.vk.vkDestroyCommandPool(g.device, g.pool, nullptr);
    g.vk.vkDestroyDevice(g.device, nullptr); g.device = VK_NULL_HANDLE;
    g.vk.vkDestroyInstance(g.instance, nullptr); g.instance = VK_NULL_HANDLE;
}
#endif

// ---- OMNI_GPU_PRESENT_V3: the shared device (both builds) -----------------------------------------------------------
// Same layout as OmniGpuShare in engine/media/OmniGpuVideo.h (the title does not include the engine's media headers).
struct OmniGpuShare {
    void* instance; void* physical; void* device; void* queue;
    uint32_t family; uint32_t timestampBits; double timestampNs;
    uint64_t importAlign; int hostImport;
    void (*lock)(); void (*unlock)();
};
static_assert(sizeof(OmniGpuShare) == 80, "OmniGpuShare layout must match OmniGpuVideo.h");
// OmniGpuVideo's set-up (preinit, from __wrap_SDL_Init right after this module came up) adopts this device and queue.
// Offered only while the present is active (console) or its host test device exists; never after teardown.
extern "C" int omni_gpu_present_share(OmniGpuShare* out)
{
    if (!out) return 0;
    std::lock_guard<std::mutex> l(g.lock);
#ifndef OMNI_GPU_PRESENT_HOST_TEST
    if (g.state.load(std::memory_order_acquire) != kActive) return 0;
#endif
    if (g.torndown.load() || g.hung || !g.device || !g.queue || !g.instance || !g.physical) return 0;
    if (access("/data/omni/gpu-share-disabled.flag", F_OK) == 0) { plog(true, "device sharing refused (gpu-share-disabled.flag): the video makes its own device"); return 0; }
    *out = OmniGpuShare {};
    out->instance = g.instance; out->physical = g.physical; out->device = g.device; out->queue = g.queue;
    out->family = g.family; out->timestampBits = g.timers ? 64u : 0u; out->timestampNs = g.timestampNs;
    out->importAlign = uint64_t(g.importAlign); out->hostImport = g.hostImport ? 1 : 0;
    out->lock = queueLock; out->unlock = queueUnlock;
    g.shared.store(true);
    plog(true, "device shared with the video conversion (OMNI_GPU_PRESENT_V3: one RADV device, queue family %u, submissions serialised)", g.family);
    return 1;
}
#ifdef OMNI_GPU_PRESENT_HOST_TEST
extern "C" int omni_gpu_present_test_up() { std::lock_guard<std::mutex> l(g.lock); return g.device || hostUp() ? 1 : 0; }
extern "C" int omni_gpu_present_test_shared() { return g.shared.load() ? 1 : 0; }
#endif
