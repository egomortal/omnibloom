// SPDX-License-Identifier: GPL-3.0-or-later
// OMNI_GPU_VIDEO_V1: see OmniGpuVideo.h. GPU Stage A of claude/OMNI-GPU-PLAN.md (G1: NV12 -> RGBA
// conversion and scaling moved off the service thread's CPU time).
// OMNI_GPU_VIDEO_V2 (omni-native-s3.2-video): the 4K60 path.
//  - enlargements follow the CPU's OMNI_FAST_UPSCALE rule (shader), so the differential test also runs on them:
//    V1 never verified (and so never used the GPU) for 1080p/1440p video on a 2160 canvas;
//  - no per-picture allocation: the picture goes through a persistent staging ring (3 slots, each with its own
//    fence; a slot is reused only after its fence), the layer it is written into is imported once and kept in a
//    small cache that the hole-punch empties for a layer before its memory goes (forget()), and the verify
//    read-back is a persistent buffer;
//  - preinit(): the native title's SDL_Init wrap brings RADV up here before any video decoder exists (Ex-Box's
//    editor: RADV must reserve its memory before Videodec2 takes its share);
//  - stats() for the per-second fps line (OmniGpuPresent.cpp).
// OMNI_GPU_VIDEO_V3 (omni-video-4k60): pace-queue pictures are imported once and read in place (no ring copy), and the
// GPU present's device and queue are shared (one RADV device in the title); see OmniGpuVideo.h.
//
// Rules from the plan's BSI lessons that apply here:
//  - timestampPeriod is read from the device and logged (RADV PS5 reported 10.000 ns);
//  - GPU timers are read after the fence the conversion already waits for (never a blocking query);
//  - every capability used is logged at set-up, two-call enumeration everywhere;
//  - the one pipeline is built at set-up (not on the first picture), with a persisted VkPipelineCache;
//  - GPU output is compared with the CPU path (differential test) before the GPU takes over;
//  - one flag file switches it, and any Vulkan error leaves the CPU path in charge.
#include "OmniGpuVideo.h"
#include "OmniGpuVideoShader.h"

#include <vulkan/vulkan.h>

#include <algorithm>
#include <atomic>
#include <cerrno>
#include <cmath>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <list>
#include <mutex>
#include <string>
#include <thread>
#include <time.h>
#include <unistd.h>
#include <vector>

// Vulkan create-info structs are zero-filled with only sType (and pNext) named.
#pragma GCC diagnostic ignored "-Wmissing-field-initializers"

#ifdef OMNI_GPU_VIDEO_HOST_TEST
// Host test (lavapipe): the Vulkan loader, files in the working directory.
#define OMNI_GPU_PROC(instance, name) vkGetInstanceProcAddr(instance, name)
static const char* flagPath() { const char* p = getenv("OMNI_GPU_FLAG"); return p ? p : "gpu-video.flag"; }
static const char* const kLogPath = "gpu-video.log";
static const char* const kCachePath = "gpu-video.pipeline-cache";
static const uint64_t kFenceTimeoutNs = 5000ull * 1000 * 1000;   // lavapipe is a CPU
#else
// Native title: RADV is linked statically as an ICD (as in OmniNativeTitle.cpp's GPU phase). Weak, so a
// link without RADV (big-app, child engine) still links and simply never turns the GPU path on.
extern "C" VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL vk_icdGetInstanceProcAddr(VkInstance, const char*) __attribute__((weak));
#define OMNI_GPU_PROC(instance, name) (vk_icdGetInstanceProcAddr ? vk_icdGetInstanceProcAddr(instance, name) : nullptr)
static const char* flagPath() { return "/data/omni/gpu-video.flag"; }
static const char* const kLogPath = "/data/omni/native/gpu-video.log";
static const char* const kCachePath = "/data/omni/native/gpu-video.pipeline-cache";
static const uint64_t kFenceTimeoutNs = 250ull * 1000 * 1000;   // a 4K picture takes ~1 ms on the GPU; 250 ms = hung
#endif

// OMNI_GPU_VIDEO_V3: the title's GPU present shares its device (OmniGpuPresent.cpp). Weak: absent outside the title.
extern "C" int omni_gpu_present_share(OmniGpuShare* out) __attribute__((weak));

namespace OmniGpuVideo {
namespace {

double nowMs()
{
    timespec ts {}; clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6;
}

std::atomic<void (*)(const char*)> g_note { nullptr };
std::mutex g_logLock;

void logLine(bool sync, const char* fmt, ...) __attribute__((format(printf, 2, 3)));
void logLine(bool sync, const char* fmt, ...)
{
    char line[1024];
    va_list ap; va_start(ap, fmt); vsnprintf(line, sizeof line, fmt, ap); va_end(ap);
    {
        std::lock_guard<std::mutex> l(g_logLock);
        if (FILE* f = fopen(kLogPath, "a")) {
            fprintf(f, "[%10.3f] %s\n", nowMs() / 1000.0, line);
            fflush(f);
            if (sync) fsync(fileno(f));
            fclose(f);
        }
    }
    if (auto n = g_note.load(std::memory_order_acquire)) {
        char tagged[1100]; snprintf(tagged, sizeof tagged, "gpu-video: %s", line); n(tagged);
    }
}

// ---- Vulkan entry points (instance and device level, looked up once) ----
struct Api {
    PFN_vkCreateInstance CreateInstance = nullptr;
    PFN_vkDestroyInstance DestroyInstance = nullptr;
    PFN_vkEnumeratePhysicalDevices EnumeratePhysicalDevices = nullptr;
    PFN_vkGetPhysicalDeviceProperties GetPhysicalDeviceProperties = nullptr;
    PFN_vkGetPhysicalDeviceProperties2 GetPhysicalDeviceProperties2 = nullptr;
    PFN_vkGetPhysicalDeviceMemoryProperties GetPhysicalDeviceMemoryProperties = nullptr;
    PFN_vkGetPhysicalDeviceQueueFamilyProperties GetPhysicalDeviceQueueFamilyProperties = nullptr;
    PFN_vkEnumerateDeviceExtensionProperties EnumerateDeviceExtensionProperties = nullptr;
    PFN_vkCreateDevice CreateDevice = nullptr;
    PFN_vkGetDeviceProcAddr GetDeviceProcAddr = nullptr;
    PFN_vkDestroyDevice DestroyDevice = nullptr;
    PFN_vkDeviceWaitIdle DeviceWaitIdle = nullptr;
    PFN_vkGetDeviceQueue GetDeviceQueue = nullptr;
    PFN_vkCreateShaderModule CreateShaderModule = nullptr;
    PFN_vkDestroyShaderModule DestroyShaderModule = nullptr;
    PFN_vkCreatePipelineCache CreatePipelineCache = nullptr;
    PFN_vkGetPipelineCacheData GetPipelineCacheData = nullptr;
    PFN_vkDestroyPipelineCache DestroyPipelineCache = nullptr;
    PFN_vkCreateDescriptorSetLayout CreateDescriptorSetLayout = nullptr;
    PFN_vkDestroyDescriptorSetLayout DestroyDescriptorSetLayout = nullptr;
    PFN_vkCreatePipelineLayout CreatePipelineLayout = nullptr;
    PFN_vkDestroyPipelineLayout DestroyPipelineLayout = nullptr;
    PFN_vkCreateComputePipelines CreateComputePipelines = nullptr;
    PFN_vkDestroyPipeline DestroyPipeline = nullptr;
    PFN_vkCreateDescriptorPool CreateDescriptorPool = nullptr;
    PFN_vkDestroyDescriptorPool DestroyDescriptorPool = nullptr;
    PFN_vkAllocateDescriptorSets AllocateDescriptorSets = nullptr;
    PFN_vkUpdateDescriptorSets UpdateDescriptorSets = nullptr;
    PFN_vkCreateCommandPool CreateCommandPool = nullptr;
    PFN_vkDestroyCommandPool DestroyCommandPool = nullptr;
    PFN_vkAllocateCommandBuffers AllocateCommandBuffers = nullptr;
    PFN_vkResetCommandBuffer ResetCommandBuffer = nullptr;
    PFN_vkBeginCommandBuffer BeginCommandBuffer = nullptr;
    PFN_vkEndCommandBuffer EndCommandBuffer = nullptr;
    PFN_vkCmdBindPipeline CmdBindPipeline = nullptr;
    PFN_vkCmdBindDescriptorSets CmdBindDescriptorSets = nullptr;
    PFN_vkCmdPushConstants CmdPushConstants = nullptr;
    PFN_vkCmdDispatch CmdDispatch = nullptr;
    PFN_vkCmdPipelineBarrier CmdPipelineBarrier = nullptr;
    PFN_vkCmdResetQueryPool CmdResetQueryPool = nullptr;
    PFN_vkCmdWriteTimestamp CmdWriteTimestamp = nullptr;
    PFN_vkCreateQueryPool CreateQueryPool = nullptr;
    PFN_vkDestroyQueryPool DestroyQueryPool = nullptr;
    PFN_vkGetQueryPoolResults GetQueryPoolResults = nullptr;
    PFN_vkCreateFence CreateFence = nullptr;
    PFN_vkDestroyFence DestroyFence = nullptr;
    PFN_vkResetFences ResetFences = nullptr;
    PFN_vkWaitForFences WaitForFences = nullptr;
    PFN_vkQueueSubmit QueueSubmit = nullptr;
    PFN_vkCreateBuffer CreateBuffer = nullptr;
    PFN_vkDestroyBuffer DestroyBuffer = nullptr;
    PFN_vkGetBufferMemoryRequirements GetBufferMemoryRequirements = nullptr;
    PFN_vkAllocateMemory AllocateMemory = nullptr;
    PFN_vkFreeMemory FreeMemory = nullptr;
    PFN_vkBindBufferMemory BindBufferMemory = nullptr;
    PFN_vkMapMemory MapMemory = nullptr;
    PFN_vkUnmapMemory UnmapMemory = nullptr;
    PFN_vkInvalidateMappedMemoryRanges InvalidateMappedMemoryRanges = nullptr;
    PFN_vkGetMemoryHostPointerPropertiesEXT GetMemoryHostPointerPropertiesEXT = nullptr;
    PFN_vkFlushMappedMemoryRanges FlushMappedMemoryRanges = nullptr;
};

// A buffer with its memory: imported (host pointer) or our own (mapped staging).
struct Buf {
    VkBuffer buffer = VK_NULL_HANDLE; VkDeviceMemory memory = VK_NULL_HANDLE;
    VkDeviceSize size = 0; void* mapped = nullptr; bool coherent = true;
};

struct Push {
    int32_t srcW, srcH, dstW, dstH, dstStrideWords, bps;
    uint32_t srcBase, dstBase;
    int32_t swapRB;
    float yOff, yMul, cMul, cMid, crR, cbG, crG, cbB;
    int32_t hdrMode; uint32_t hdrBase; float hlgPeak;   // V4: the PQ layer (omni_yuv_to_rgb.comp)
};
static_assert(sizeof(Push) == 80, "push constant block matches the shader");

enum State { kOff = 0, kStarting = 1, kReady = 2, kFailed = 3 };

// OMNI_GPU_VIDEO_V2: an imported layer, kept between pictures. `dead`: forgotten while a conversion used it
// (freed by that conversion when it ends).
struct Cached { uintptr_t start = 0, end = 0; Buf b; uint64_t lastUse = 0; bool inUse = false, dead = false; bool picture = false; };   // V3: picture = input planes
// One staging slot: the picture's planes are copied in; the slot's fence says when the GPU is done with it.
struct Slot { Buf in; VkCommandBuffer cmd = VK_NULL_HANDLE; VkFence fence = VK_NULL_HANDLE; bool pending = false; };
constexpr int kSlots = 3;
constexpr size_t kMaxCached = 16;
// V3: imported pace-queue pictures. The queue holds up to 240 pictures (paceMaxFramesV5) plus 8 spares; every one is a
// buffer of its own that stays mapped until PaceAlloc frees it (forget() first), so the cache covers the whole queue.
constexpr size_t kMaxCachedPictures = 288;

struct Gpu {
    std::atomic<int> state { kOff };
    std::mutex lock;   // one conversion at a time; shutdown waits on it
    Api vk;
    VkInstance instance = VK_NULL_HANDLE; VkPhysicalDevice physical = VK_NULL_HANDLE; VkDevice device = VK_NULL_HANDLE;
    VkQueue queue = VK_NULL_HANDLE; uint32_t family = 0;
    VkPhysicalDeviceMemoryProperties memory {};
    VkDeviceSize importAlign = 0; bool hostImport = false;
    double timestampNs = 0; bool timers = true;
    VkShaderModule shader = VK_NULL_HANDLE; VkPipelineCache cache = VK_NULL_HANDLE;
    VkDescriptorSetLayout setLayout = VK_NULL_HANDLE; VkPipelineLayout layout = VK_NULL_HANDLE; VkPipeline pipeline = VK_NULL_HANDLE;
    VkDescriptorPool pool = VK_NULL_HANDLE; VkDescriptorSet set = VK_NULL_HANDLE;
    VkCommandPool commands = VK_NULL_HANDLE;
    VkQueryPool queries = VK_NULL_HANDLE;
    Slot slots[kSlots]; int nextSlot = 0;   // V2: the staging ring (input planes)
    Buf stageOut;   // copy mode (and import fallback) for the layer; also the verify read-back. Persistent, grows only.
    std::mutex cacheLock; std::list<Cached> layers; uint64_t useTick = 0;   // a list: entries never move   // V2: imported layers
    long liveBuffers = 0, liveMemory = 0;   // V2: every VkBuffer / VkDeviceMemory this module holds (leak test)
    // options (flag file words)
    bool optCopy = false, optCompute = false, optVerify = true, optFailSetUp = false;
    // per bit depth (index bps - 1): 0 = not verified, 1 = verified, -1 = turned off
    int verified[2] = { 0, 0 };
    int verifyRuns[2] = { 0, 0 };
    std::atomic<bool> setUpDone { false };
    bool hung = false;   // a fence that never signalled: nothing is freed or reused
    // statistics (service thread)
    uint64_t pictures = 0, imports = 0, importFails = 0, copies = 0, failures = 0, cacheHits = 0, forgets = 0;
    // V2: totals for the per-second fps line (read from the present thread)
    std::atomic<uint64_t> statPictures { 0 }, statWallUs { 0 }, statGpuUs { 0 };
    // V3: pictures read in place / copied through the ring; the shared device (not ours to destroy)
    std::atomic<uint64_t> statInPlace { 0 }, statRingCopies { 0 };
    std::atomic<uint64_t> statHdr { 0 };   // V4: pictures whose PQ layer was written on the GPU
    unsigned hdrNotes = 0;
    bool shared = false; void (*qlock)() = nullptr; void (*qunlock)() = nullptr;
    uint64_t pictureImports = 0, pictureHits = 0;
    double sumWall = 0, sumGpu = 0, sumImport = 0, maxWall = 0; unsigned windowN = 0, windowLogs = 0;
    unsigned importFailLogs = 0;
};
Gpu g;

template <class T> bool load(VkInstance instance, T& fn, const char* name)
{
    fn = reinterpret_cast<T>(OMNI_GPU_PROC(instance, name));
    return fn != nullptr;
}
template <class T> bool loadDevice(T& fn, const char* name)
{
    fn = reinterpret_cast<T>(g.vk.GetDeviceProcAddr(g.device, name));
    if (!fn) logLine(false, "set-up: device entry point %s missing", name);
    return fn != nullptr;
}

int findMemory(uint32_t bits, VkMemoryPropertyFlags want, VkMemoryPropertyFlags avoid = 0)
{
    for (uint32_t i = 0; i < g.memory.memoryTypeCount; ++i)
        if ((bits & (1u << i)) && (g.memory.memoryTypes[i].propertyFlags & want) == want && !(g.memory.memoryTypes[i].propertyFlags & avoid))
            return int(i);
    return -1;
}

void freeBuf(Buf& b)
{
    if (b.mapped && g.vk.UnmapMemory) g.vk.UnmapMemory(g.device, b.memory);
    if (b.buffer) { g.vk.DestroyBuffer(g.device, b.buffer, nullptr); g.liveBuffers--; }
    if (b.memory) { g.vk.FreeMemory(g.device, b.memory, nullptr); g.liveMemory--; }
    b = Buf {};
}

// Our own mapped buffer (copy mode). Grows only.
bool ensureStage(Buf& b, VkDeviceSize size, bool readBack)
{
    if (b.buffer && b.size >= size) return true;
    freeBuf(b);
    size = (size + 0xffff) & ~VkDeviceSize(0xffff);
    VkBufferCreateInfo bi { VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO };
    bi.size = size; bi.usage = VK_BUFFER_USAGE_STORAGE_BUFFER_BIT; bi.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
    VkResult r = g.vk.CreateBuffer(g.device, &bi, nullptr, &b.buffer);
    if (r != VK_SUCCESS) { b.buffer = VK_NULL_HANDLE; logLine(true, "staging buffer %llu bytes: vkCreateBuffer=%d", (unsigned long long)size, int(r)); return false; }
    g.liveBuffers++;
    VkMemoryRequirements req {}; g.vk.GetBufferMemoryRequirements(g.device, b.buffer, &req);
    int type = -1;
    // read-back wants cached memory (uncached reads of 33 MB would cost more than the conversion)
    if (readBack) type = findMemory(req.memoryTypeBits, VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_CACHED_BIT);
    if (type < 0) type = findMemory(req.memoryTypeBits, VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
    if (type < 0) type = findMemory(req.memoryTypeBits, VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT);
    if (type < 0) { logLine(true, "staging buffer: no host-visible memory type (bits 0x%x)", req.memoryTypeBits); freeBuf(b); return false; }
    VkMemoryAllocateInfo ai { VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO };
    ai.allocationSize = req.size; ai.memoryTypeIndex = uint32_t(type);
    r = g.vk.AllocateMemory(g.device, &ai, nullptr, &b.memory);
    if (r == VK_SUCCESS) g.liveMemory++; else b.memory = VK_NULL_HANDLE;
    if (r == VK_SUCCESS) r = g.vk.BindBufferMemory(g.device, b.buffer, b.memory, 0);
    if (r == VK_SUCCESS) r = g.vk.MapMemory(g.device, b.memory, 0, VK_WHOLE_SIZE, 0, &b.mapped);
    if (r != VK_SUCCESS) { b.mapped = nullptr; logLine(true, "staging buffer %llu bytes, type %d: %d", (unsigned long long)size, type, int(r)); freeBuf(b); return false; }
    b.size = size; b.coherent = g.memory.memoryTypes[type].propertyFlags & VK_MEMORY_PROPERTY_HOST_COHERENT_BIT;
    logLine(false, "staging %s buffer: %.1f MiB, memory type %d (flags 0x%x)", readBack ? "output" : "input", size / 1048576.0, type,
        unsigned(g.memory.memoryTypes[type].propertyFlags));
    return true;
}

// Imports [p, p + bytes) rounded out to the import alignment. The memory must stay mapped until
// freeBuf (the conversion is synchronous and frees it before returning). offset = p - start.
bool importHost(Buf& b, const void* p, size_t bytes, uint32_t& offset)
{
    if (!g.hostImport || !p || !bytes) return false;
    const uintptr_t a = uintptr_t(g.importAlign);
    const uintptr_t start = uintptr_t(p) & ~(a - 1), end = (uintptr_t(p) + bytes + a - 1) & ~(a - 1);
    offset = uint32_t(uintptr_t(p) - start);
    VkMemoryHostPointerPropertiesEXT hp { VK_STRUCTURE_TYPE_MEMORY_HOST_POINTER_PROPERTIES_EXT };
    VkResult r = g.vk.GetMemoryHostPointerPropertiesEXT(g.device, VK_EXTERNAL_MEMORY_HANDLE_TYPE_HOST_ALLOCATION_BIT_EXT, reinterpret_cast<void*>(start), &hp);
    const char* stage = "host pointer properties";
    if (r == VK_SUCCESS) {
        VkExternalMemoryBufferCreateInfo ext { VK_STRUCTURE_TYPE_EXTERNAL_MEMORY_BUFFER_CREATE_INFO };
        ext.handleTypes = VK_EXTERNAL_MEMORY_HANDLE_TYPE_HOST_ALLOCATION_BIT_EXT;
        VkBufferCreateInfo bi { VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO, &ext };
        bi.size = end - start; bi.usage = VK_BUFFER_USAGE_STORAGE_BUFFER_BIT; bi.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
        stage = "vkCreateBuffer"; r = g.vk.CreateBuffer(g.device, &bi, nullptr, &b.buffer);
        if (r == VK_SUCCESS) g.liveBuffers++; else b.buffer = VK_NULL_HANDLE;
    }
    if (r == VK_SUCCESS) {
        VkMemoryRequirements req {}; g.vk.GetBufferMemoryRequirements(g.device, b.buffer, &req);
        int type = findMemory(req.memoryTypeBits & hp.memoryTypeBits, 0);
        stage = "memory type";
        if (type < 0 || req.size > end - start) r = VK_ERROR_FEATURE_NOT_PRESENT;
        else {
            VkImportMemoryHostPointerInfoEXT imp { VK_STRUCTURE_TYPE_IMPORT_MEMORY_HOST_POINTER_INFO_EXT };
            imp.handleType = VK_EXTERNAL_MEMORY_HANDLE_TYPE_HOST_ALLOCATION_BIT_EXT; imp.pHostPointer = reinterpret_cast<void*>(start);
            VkMemoryAllocateInfo ai { VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO, &imp };
            ai.allocationSize = end - start; ai.memoryTypeIndex = uint32_t(type);
            stage = "vkAllocateMemory(import)"; r = g.vk.AllocateMemory(g.device, &ai, nullptr, &b.memory);
            if (r == VK_SUCCESS) g.liveMemory++; else b.memory = VK_NULL_HANDLE;
            if (r == VK_SUCCESS) { stage = "vkBindBufferMemory"; r = g.vk.BindBufferMemory(g.device, b.buffer, b.memory, 0); }
        }
    }
    if (r != VK_SUCCESS) {
        g.importFails++;
        if (g.importFailLogs++ < 6)
            logLine(true, "import of %zu bytes at %p failed at %s (%d); this picture uses the staging copy", bytes, p, stage, int(r));
        freeBuf(b);
        return false;
    }
    b.size = end - start;
    g.imports++;
    return true;
}

// OMNI_GPU_VIDEO_V2: the layer import cache. A layer's memory (CpuPixelBuffer, mmap) stays at one address until
// the hole-punch grows or frees it, and it calls forget() first; so one import per layer serves every picture.
// Caller holds g.lock (one conversion at a time). Returns the entry, marked in use, or nullptr (staging copy).
Cached* cachedImport(const void* p, size_t bytes, uint32_t& offset, bool picture = false)
{
    if (!g.hostImport || !p || !bytes) return nullptr;
    const uintptr_t a = uintptr_t(g.importAlign);
    const uintptr_t start = uintptr_t(p) & ~(a - 1), end = (uintptr_t(p) + bytes + a - 1) & ~(a - 1);
    std::lock_guard<std::mutex> l(g.cacheLock);
    size_t sameKind = 0;
    for (Cached& c : g.layers) {
        if (c.picture != picture) continue;
        ++sameKind;
        // V3: an entry in use already (a picture whose planes sit inside the layer's range, never in practice) is not reused
        if (!c.dead && !c.inUse && c.start <= start && c.end >= end) {
            c.inUse = true; c.lastUse = ++g.useTick; offset = uint32_t(uintptr_t(p) - c.start); g.cacheHits++; if (picture) g.pictureHits++;
            return &c;
        }
    }
    if (sameKind >= (picture ? kMaxCachedPictures : kMaxCached)) {   // least recently used of this kind goes (we hold g.lock)
        auto old = g.layers.end();
        for (auto it = g.layers.begin(); it != g.layers.end(); ++it)
            if (it->picture == picture && !it->inUse && (old == g.layers.end() || it->lastUse < old->lastUse)) old = it;
        if (old != g.layers.end()) { freeBuf(old->b); g.layers.erase(old); }
    }
    Cached c; c.start = start; c.end = end; c.picture = picture;
    if (!importHost(c.b, p, bytes, offset)) {
        if (g.importFails >= 6 && g.imports == 0) { g.hostImport = false; logLine(true, "imports refused 6 times: the persistent staging buffers are used from now on"); }
        return nullptr;
    }
    if (picture) g.pictureImports++;
    c.inUse = true; c.lastUse = ++g.useTick;
    g.layers.push_back(c);
    return &g.layers.back();
}
// End of a conversion (g.lock held): entries are free again; forgotten ones go now (their fence has signalled).
void cacheDone()
{
    std::lock_guard<std::mutex> l(g.cacheLock);
    for (auto it = g.layers.begin(); it != g.layers.end();) {
        it->inUse = false;
        if (it->dead) { freeBuf(it->b); it = g.layers.erase(it); } else ++it;
    }
}

void fail(const char* fmt, ...) __attribute__((format(printf, 1, 2)));
void fail(const char* fmt, ...)
{
    char why[512];
    va_list ap; va_start(ap, fmt); vsnprintf(why, sizeof why, fmt, ap); va_end(ap);
    logLine(true, "OFF: %s; the CPU path converts every picture", why);
    g.state.store(kFailed, std::memory_order_release);
}

void readOptions()
{
    FILE* f = fopen(flagPath(), "r");
    if (!f) return;
    char word[64];
    while (fscanf(f, "%63s", word) == 1) {
        if (!strcmp(word, "copy")) g.optCopy = true;
        else if (!strcmp(word, "compute")) g.optCompute = true;
        else if (!strcmp(word, "noverify")) g.optVerify = false;
        else if (!strcmp(word, "notimer")) g.timers = false;
        else if (!strcmp(word, "failsetup")) g.optFailSetUp = true;   // V2: the console fallback gate
        else logLine(false, "flag file: unknown word '%s' (copy|compute|noverify|notimer|failsetup)", word);
    }
    fclose(f);
}

// OMNI_GPU_VIDEO_V3: adopt the GPU present's device and queue (one RADV device in the title). false: not offered.
bool sharedDevice()
{
    OmniGpuShare sh {};
    if (!omni_gpu_present_share || g.optCompute || !omni_gpu_present_share(&sh) || !sh.device || !sh.queue || !sh.lock || !sh.unlock) return false;
    Api& vk = g.vk;
    g.instance = static_cast<VkInstance>(sh.instance); g.physical = static_cast<VkPhysicalDevice>(sh.physical);
    if (!(load(g.instance, vk.GetDeviceProcAddr, "vkGetDeviceProcAddr") && load(g.instance, vk.GetPhysicalDeviceMemoryProperties, "vkGetPhysicalDeviceMemoryProperties")
          && load(g.instance, vk.GetPhysicalDeviceProperties2, "vkGetPhysicalDeviceProperties2"))) {
        logLine(true, "shared device: instance entry points missing; making a device of our own");
        g.instance = VK_NULL_HANDLE; g.physical = VK_NULL_HANDLE; return false;
    }
    g.device = static_cast<VkDevice>(sh.device); g.queue = static_cast<VkQueue>(sh.queue); g.family = sh.family;
    vk.GetPhysicalDeviceMemoryProperties(g.physical, &g.memory);
    g.timestampNs = sh.timestampNs; if (!sh.timestampBits) g.timers = false;
    g.importAlign = sh.importAlign;
    const long page = sysconf(_SC_PAGESIZE);
    g.hostImport = sh.hostImport && !g.optCopy && g.importAlign && (g.importAlign & (g.importAlign - 1)) == 0 && page > 0 && g.importAlign <= VkDeviceSize(page);
    g.qlock = sh.lock; g.qunlock = sh.unlock; g.shared = true;
    logLine(false, "device SHARED with the GPU present (queue family %u, timestampPeriod %.3f ns, %s): no second RADV device", g.family, g.timestampNs,
        g.hostImport ? "host imports" : "staging copies");
    return true;
}
bool failB(const char* fmt, ...) __attribute__((format(printf, 1, 2)));
bool failB(const char* fmt, ...)
{
    char why[512];
    va_list ap; va_start(ap, fmt); vsnprintf(why, sizeof why, fmt, ap); va_end(ap);
    fail("%s", why);
    return false;
}

// V2's own instance and device (V3: only when the GPU present does not share its device).
bool ownDevice(double t0)
{
    Api& vk = g.vk;
    VkResult r = VK_SUCCESS; bool ok = false;
    if (!load(VK_NULL_HANDLE, vk.CreateInstance, "vkCreateInstance")) return failB("no Vulkan driver linked (vk_icdGetInstanceProcAddr missing)");
    VkApplicationInfo app { VK_STRUCTURE_TYPE_APPLICATION_INFO };
    app.pApplicationName = "Omni video"; app.applicationVersion = 1;
    app.pEngineName = "OmniGpuVideo"; app.engineVersion = 1;   // deliberate: no driconf entry matches it
    app.apiVersion = VK_API_VERSION_1_3;
    VkInstanceCreateInfo ici { VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO };
    ici.pApplicationInfo = &app;
    r = vk.CreateInstance(&ici, nullptr, &g.instance);
    if (r != VK_SUCCESS) return failB("vkCreateInstance=%d", int(r));
    ok = load(g.instance, vk.DestroyInstance, "vkDestroyInstance") && load(g.instance, vk.EnumeratePhysicalDevices, "vkEnumeratePhysicalDevices")
        && load(g.instance, vk.GetPhysicalDeviceProperties, "vkGetPhysicalDeviceProperties") && load(g.instance, vk.GetPhysicalDeviceProperties2, "vkGetPhysicalDeviceProperties2")
        && load(g.instance, vk.GetPhysicalDeviceMemoryProperties, "vkGetPhysicalDeviceMemoryProperties")
        && load(g.instance, vk.GetPhysicalDeviceQueueFamilyProperties, "vkGetPhysicalDeviceQueueFamilyProperties")
        && load(g.instance, vk.EnumerateDeviceExtensionProperties, "vkEnumerateDeviceExtensionProperties")
        && load(g.instance, vk.CreateDevice, "vkCreateDevice") && load(g.instance, vk.GetDeviceProcAddr, "vkGetDeviceProcAddr");
    if (!ok) return failB("an instance-level entry point is missing");
    uint32_t count = 0;
    vk.EnumeratePhysicalDevices(g.instance, &count, nullptr);
    std::vector<VkPhysicalDevice> devices(count);
    r = count ? vk.EnumeratePhysicalDevices(g.instance, &count, devices.data()) : VK_ERROR_INITIALIZATION_FAILED;
    if (r != VK_SUCCESS || !count) return failB("no physical device (%d, count %u)", int(r), count);
    g.physical = devices[0];
    VkPhysicalDeviceExternalMemoryHostPropertiesEXT hostProps { VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_EXTERNAL_MEMORY_HOST_PROPERTIES_EXT };
    VkPhysicalDeviceProperties2 props2 { VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2, &hostProps };
    vk.GetPhysicalDeviceProperties2(g.physical, &props2);
    const VkPhysicalDeviceProperties& p = props2.properties;
    g.timestampNs = p.limits.timestampPeriod;
    vk.GetPhysicalDeviceMemoryProperties(g.physical, &g.memory);
    logLine(false, "device '%s' api %u.%u.%u driver 0x%x timestampPeriod=%.3f ns maxStorageBufferRange=%u maxPushConstants=%u maxWorkGroupInvocations=%u",
        p.deviceName, VK_API_VERSION_MAJOR(p.apiVersion), VK_API_VERSION_MINOR(p.apiVersion), VK_API_VERSION_PATCH(p.apiVersion), p.driverVersion,
        g.timestampNs, p.limits.maxStorageBufferRange, p.limits.maxPushConstantsSize, p.limits.maxComputeWorkGroupInvocations);
    for (uint32_t i = 0; i < g.memory.memoryTypeCount; ++i)
        logLine(false, "memory type %u: flags 0x%x heap %u (%.0f MiB)", i, unsigned(g.memory.memoryTypes[i].propertyFlags), g.memory.memoryTypes[i].heapIndex,
            g.memory.memoryHeaps[g.memory.memoryTypes[i].heapIndex].size / 1048576.0);
    uint32_t extCount = 0;
    vk.EnumerateDeviceExtensionProperties(g.physical, nullptr, &extCount, nullptr);
    std::vector<VkExtensionProperties> exts(extCount);
    if (extCount) vk.EnumerateDeviceExtensionProperties(g.physical, nullptr, &extCount, exts.data());
    bool hasHost = false;
    for (auto& e : exts) if (!strcmp(e.extensionName, VK_EXT_EXTERNAL_MEMORY_HOST_EXTENSION_NAME)) hasHost = true;
    g.importAlign = hostProps.minImportedHostPointerAlignment;
    const long page = sysconf(_SC_PAGESIZE);
    // Rounding out to the import alignment must stay inside pages the buffer already owns.
    g.hostImport = hasHost && !g.optCopy && g.importAlign && (g.importAlign & (g.importAlign - 1)) == 0 && page > 0 && g.importAlign <= VkDeviceSize(page);
    logLine(false, "%u device extensions; VK_EXT_external_memory_host %s, minImportedHostPointerAlignment=%llu, page %ld -> %s", extCount,
        hasHost ? "present" : "missing", (unsigned long long)g.importAlign, page, g.hostImport ? "import" : "staging copies");
    uint32_t families = 0;
    vk.GetPhysicalDeviceQueueFamilyProperties(g.physical, &families, nullptr);
    std::vector<VkQueueFamilyProperties> qf(families);
    if (families) vk.GetPhysicalDeviceQueueFamilyProperties(g.physical, &families, qf.data());
    int general = -1, computeOnly = -1;
    for (uint32_t i = 0; i < families; ++i) {
        logLine(false, "queue family %u: flags 0x%x count %u timestampValidBits %u", i, unsigned(qf[i].queueFlags), qf[i].queueCount, qf[i].timestampValidBits);
        const bool gfx = qf[i].queueFlags & VK_QUEUE_GRAPHICS_BIT, cmp = qf[i].queueFlags & VK_QUEUE_COMPUTE_BIT;
        if (gfx && cmp && general < 0) general = int(i);
        if (!gfx && cmp && computeOnly < 0) computeOnly = int(i);
    }
    int chosen = g.optCompute && computeOnly >= 0 ? computeOnly : general >= 0 ? general : computeOnly;
    if (chosen < 0) return failB("no queue family with compute");
    g.family = uint32_t(chosen);
    if (g.timers && qf[chosen].timestampValidBits == 0) { g.timers = false; logLine(false, "queue family %d has no timestamps: timer off", chosen); }
    const float priority = 0.5f;
    VkDeviceQueueCreateInfo qci { VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO };
    qci.queueFamilyIndex = g.family; qci.queueCount = 1; qci.pQueuePriorities = &priority;
    const char* enable[1] = { VK_EXT_EXTERNAL_MEMORY_HOST_EXTENSION_NAME };
    VkDeviceCreateInfo dci { VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO };
    dci.queueCreateInfoCount = 1; dci.pQueueCreateInfos = &qci;
    dci.enabledExtensionCount = hasHost ? 1 : 0; dci.ppEnabledExtensionNames = enable;
    r = vk.CreateDevice(g.physical, &dci, nullptr, &g.device);
    if (r != VK_SUCCESS) return failB("vkCreateDevice=%d (queue family %u)", int(r), g.family);
    logLine(false, "device up on queue family %u (%.0f ms)", g.family, nowMs() - t0);
    return true;
}

// The set-up thread. Everything up to the pipeline, so the first picture pays nothing.
void setUp()
{
    const double t0 = nowMs();
    readOptions();
    logLine(true, "set-up start (OMNI_GPU_VIDEO_V4; options: %s%s%s%s)", g.optCopy ? "copy " : "import ", g.optCompute ? "compute-queue " : "general-queue ",
        g.optVerify ? "verify " : "noverify ", g.timers ? "timer" : "notimer");
    Api& vk = g.vk;
    if (g.optFailSetUp) return fail("set-up failure forced by the flag word failsetup (fallback test)");
    if (!sharedDevice() && !ownDevice(t0)) return;
    bool ok = false; VkResult r = VK_SUCCESS;
    ok = loadDevice(vk.DestroyDevice, "vkDestroyDevice") && loadDevice(vk.DeviceWaitIdle, "vkDeviceWaitIdle") && loadDevice(vk.GetDeviceQueue, "vkGetDeviceQueue")
        && loadDevice(vk.CreateShaderModule, "vkCreateShaderModule") && loadDevice(vk.DestroyShaderModule, "vkDestroyShaderModule")
        && loadDevice(vk.CreatePipelineCache, "vkCreatePipelineCache") && loadDevice(vk.GetPipelineCacheData, "vkGetPipelineCacheData")
        && loadDevice(vk.DestroyPipelineCache, "vkDestroyPipelineCache")
        && loadDevice(vk.CreateDescriptorSetLayout, "vkCreateDescriptorSetLayout") && loadDevice(vk.DestroyDescriptorSetLayout, "vkDestroyDescriptorSetLayout")
        && loadDevice(vk.CreatePipelineLayout, "vkCreatePipelineLayout") && loadDevice(vk.DestroyPipelineLayout, "vkDestroyPipelineLayout")
        && loadDevice(vk.CreateComputePipelines, "vkCreateComputePipelines") && loadDevice(vk.DestroyPipeline, "vkDestroyPipeline")
        && loadDevice(vk.CreateDescriptorPool, "vkCreateDescriptorPool") && loadDevice(vk.DestroyDescriptorPool, "vkDestroyDescriptorPool")
        && loadDevice(vk.AllocateDescriptorSets, "vkAllocateDescriptorSets") && loadDevice(vk.UpdateDescriptorSets, "vkUpdateDescriptorSets")
        && loadDevice(vk.CreateCommandPool, "vkCreateCommandPool") && loadDevice(vk.DestroyCommandPool, "vkDestroyCommandPool")
        && loadDevice(vk.AllocateCommandBuffers, "vkAllocateCommandBuffers") && loadDevice(vk.ResetCommandBuffer, "vkResetCommandBuffer")
        && loadDevice(vk.BeginCommandBuffer, "vkBeginCommandBuffer") && loadDevice(vk.EndCommandBuffer, "vkEndCommandBuffer")
        && loadDevice(vk.CmdBindPipeline, "vkCmdBindPipeline") && loadDevice(vk.CmdBindDescriptorSets, "vkCmdBindDescriptorSets")
        && loadDevice(vk.CmdPushConstants, "vkCmdPushConstants") && loadDevice(vk.CmdDispatch, "vkCmdDispatch")
        && loadDevice(vk.CmdPipelineBarrier, "vkCmdPipelineBarrier") && loadDevice(vk.CmdResetQueryPool, "vkCmdResetQueryPool")
        && loadDevice(vk.CmdWriteTimestamp, "vkCmdWriteTimestamp") && loadDevice(vk.CreateQueryPool, "vkCreateQueryPool")
        && loadDevice(vk.DestroyQueryPool, "vkDestroyQueryPool") && loadDevice(vk.GetQueryPoolResults, "vkGetQueryPoolResults")
        && loadDevice(vk.CreateFence, "vkCreateFence") && loadDevice(vk.DestroyFence, "vkDestroyFence") && loadDevice(vk.ResetFences, "vkResetFences")
        && loadDevice(vk.WaitForFences, "vkWaitForFences") && loadDevice(vk.QueueSubmit, "vkQueueSubmit")
        && loadDevice(vk.CreateBuffer, "vkCreateBuffer") && loadDevice(vk.DestroyBuffer, "vkDestroyBuffer")
        && loadDevice(vk.GetBufferMemoryRequirements, "vkGetBufferMemoryRequirements") && loadDevice(vk.AllocateMemory, "vkAllocateMemory")
        && loadDevice(vk.FreeMemory, "vkFreeMemory") && loadDevice(vk.BindBufferMemory, "vkBindBufferMemory")
        && loadDevice(vk.MapMemory, "vkMapMemory") && loadDevice(vk.UnmapMemory, "vkUnmapMemory")
        && loadDevice(vk.InvalidateMappedMemoryRanges, "vkInvalidateMappedMemoryRanges") && loadDevice(vk.FlushMappedMemoryRanges, "vkFlushMappedMemoryRanges");
    if (!ok) return fail("a device-level entry point is missing");
    if (g.hostImport && !loadDevice(vk.GetMemoryHostPointerPropertiesEXT, "vkGetMemoryHostPointerPropertiesEXT")) g.hostImport = false;
    if (!g.shared) vk.GetDeviceQueue(g.device, g.family, 0, &g.queue);   // V3: the shared queue came with the device

    // pipeline (cache persisted so later runs skip the shader compile)
    std::vector<uint8_t> cacheData;
    if (FILE* f = fopen(kCachePath, "rb")) {
        uint8_t buf[65536]; size_t n;
        while ((n = fread(buf, 1, sizeof buf, f)) > 0 && cacheData.size() < (16u << 20)) cacheData.insert(cacheData.end(), buf, buf + n);
        fclose(f);
    }
    VkPipelineCacheCreateInfo pci { VK_STRUCTURE_TYPE_PIPELINE_CACHE_CREATE_INFO };
    pci.initialDataSize = cacheData.size(); pci.pInitialData = cacheData.empty() ? nullptr : cacheData.data();
    if (vk.CreatePipelineCache(g.device, &pci, nullptr, &g.cache) != VK_SUCCESS) {
        pci.initialDataSize = 0; pci.pInitialData = nullptr; cacheData.clear();
        vk.CreatePipelineCache(g.device, &pci, nullptr, &g.cache);
    }
    VkShaderModuleCreateInfo smi { VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO };
    smi.codeSize = sizeof kOmniYuvToRgbSpv; smi.pCode = kOmniYuvToRgbSpv;
    r = vk.CreateShaderModule(g.device, &smi, nullptr, &g.shader);
    if (r != VK_SUCCESS) return fail("vkCreateShaderModule=%d", int(r));
    VkDescriptorSetLayoutBinding bindings[3] {};   // V4: binding 2 = the PQ layer
    for (int i = 0; i < 3; ++i) { bindings[i].binding = uint32_t(i); bindings[i].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER; bindings[i].descriptorCount = 1; bindings[i].stageFlags = VK_SHADER_STAGE_COMPUTE_BIT; }
    VkDescriptorSetLayoutCreateInfo dli { VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO };
    dli.bindingCount = 3; dli.pBindings = bindings;
    r = vk.CreateDescriptorSetLayout(g.device, &dli, nullptr, &g.setLayout);
    VkPushConstantRange range { VK_SHADER_STAGE_COMPUTE_BIT, 0, sizeof(Push) };
    VkPipelineLayoutCreateInfo pli { VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO };
    pli.setLayoutCount = 1; pli.pSetLayouts = &g.setLayout; pli.pushConstantRangeCount = 1; pli.pPushConstantRanges = &range;
    if (r == VK_SUCCESS) r = vk.CreatePipelineLayout(g.device, &pli, nullptr, &g.layout);
    if (r != VK_SUCCESS) return fail("pipeline layout: %d", int(r));
    VkComputePipelineCreateInfo cpi { VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO };
    cpi.stage.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO; cpi.stage.stage = VK_SHADER_STAGE_COMPUTE_BIT;
    cpi.stage.module = g.shader; cpi.stage.pName = "main"; cpi.layout = g.layout;
    const double tp = nowMs();
    r = vk.CreateComputePipelines(g.device, g.cache, 1, &cpi, nullptr, &g.pipeline);
    if (r != VK_SUCCESS) return fail("vkCreateComputePipelines=%d", int(r));
    logLine(false, "pipeline built in %.1f ms (cache %zu bytes in)", nowMs() - tp, cacheData.size());
    size_t outSize = 0;
    if (vk.GetPipelineCacheData(g.device, g.cache, &outSize, nullptr) == VK_SUCCESS && outSize && outSize != cacheData.size()) {
        std::vector<uint8_t> out(outSize);
        if (vk.GetPipelineCacheData(g.device, g.cache, &outSize, out.data()) == VK_SUCCESS)
            if (FILE* f = fopen(kCachePath, "wb")) { fwrite(out.data(), 1, outSize, f); fclose(f); }
    }
    VkDescriptorPoolSize ps { VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 3 };
    VkDescriptorPoolCreateInfo dpi { VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO };
    dpi.maxSets = 1; dpi.poolSizeCount = 1; dpi.pPoolSizes = &ps;
    r = vk.CreateDescriptorPool(g.device, &dpi, nullptr, &g.pool);
    VkDescriptorSetAllocateInfo dsa { VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO };
    dsa.descriptorPool = g.pool; dsa.descriptorSetCount = 1; dsa.pSetLayouts = &g.setLayout;
    if (r == VK_SUCCESS) r = vk.AllocateDescriptorSets(g.device, &dsa, &g.set);
    VkCommandPoolCreateInfo cpo { VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO };
    cpo.flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT; cpo.queueFamilyIndex = g.family;
    if (r == VK_SUCCESS) r = vk.CreateCommandPool(g.device, &cpo, nullptr, &g.commands);
    VkCommandBufferAllocateInfo cba { VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO };
    cba.commandPool = g.commands; cba.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY; cba.commandBufferCount = 1;
    VkFenceCreateInfo fci { VK_STRUCTURE_TYPE_FENCE_CREATE_INFO };
    for (Slot& sl : g.slots) {   // V2: the staging ring (its buffers are made at the first picture's size, then kept)
        if (r == VK_SUCCESS) r = vk.AllocateCommandBuffers(g.device, &cba, &sl.cmd);
        if (r == VK_SUCCESS) r = vk.CreateFence(g.device, &fci, nullptr, &sl.fence);
    }
    if (r == VK_SUCCESS && g.timers) {
        VkQueryPoolCreateInfo qpi { VK_STRUCTURE_TYPE_QUERY_POOL_CREATE_INFO };
        qpi.queryType = VK_QUERY_TYPE_TIMESTAMP; qpi.queryCount = 2 * kSlots;
        if (vk.CreateQueryPool(g.device, &qpi, nullptr, &g.queries) != VK_SUCCESS) { g.timers = false; logLine(false, "no timestamp query pool: timer off"); }
    }
    if (r != VK_SUCCESS) return fail("descriptor/command/fence set-up: %d", int(r));
    int expected = kStarting;   // shutdown may have switched it off meanwhile
    if (g.state.compare_exchange_strong(expected, kReady, std::memory_order_acq_rel))
        logLine(true, "READY in %.0f ms (OMNI_GPU_VIDEO_V4: HDR10/HLG PQ layer on request; %s device, pace-queue pictures %s, %d-slot ring for the rest, %s, queue family %u, timer %s)", nowMs() - t0,
            g.shared ? "the present's shared" : "its own", g.hostImport ? "read in place (imported once)" : "copied (no host import)", kSlots,
            g.hostImport ? "layers imported once and cached" : "layers through a persistent staging buffer", g.family, g.timers ? "on" : "off");
}

void colourFor(const Job& j, Push& pc)
{
    double kr = 0.299, kb = 0.114;   // BT.601 (swscale's default for unknown codes)
    switch (j.matrix) {
    case 1: kr = 0.2126; kb = 0.0722; break;   // BT.709
    case 4: kr = 0.30; kb = 0.11; break;       // FCC
    case 7: kr = 0.212; kb = 0.087; break;     // SMPTE 240M
    case 9: case 10: kr = 0.2627; kb = 0.0593; break;   // BT.2020
    default: break;
    }
    const double kg = 1.0 - kr - kb;
    const double maxv = j.bps == 2 ? 1023.0 : 255.0, k = j.bps == 2 ? 4.0 : 1.0;
    if (j.fullRange) { pc.yOff = 0; pc.yMul = float(1.0 / maxv); pc.cMul = float(1.0 / maxv); }
    else { pc.yOff = float(16 * k); pc.yMul = float(1.0 / (219 * k)); pc.cMul = float(1.0 / (224 * k)); }
    pc.cMid = float(128 * k);
    pc.crR = float(2 * (1 - kr)); pc.cbB = float(2 * (1 - kb));
    pc.cbG = float(2 * kb * (1 - kb) / kg); pc.crG = float(2 * kr * (1 - kr) / kg);
    pc.hdrMode = 0; pc.hdrBase = 0; pc.hlgPeak = 1000.0f;
}

bool jobFits(const Job& j)
{
    if (!j.planes || !j.dst || j.srcW < 2 || j.srcH < 2 || j.dstW < 1 || j.dstH < 1 || (j.bps != 1 && j.bps != 2)) return false;
    if (j.srcW > 8192 || j.srcH > 8192 || j.dstW > 3840 || j.dstH > 2160 || j.dstStride < j.dstW * 4 || (j.dstStride & 3)) return false;
    const size_t cw = size_t(j.srcW + 1) / 2, ch = size_t(j.srcH + 1) / 2;
    const size_t need = (size_t(j.srcW) * j.srcH + 2 * cw * ch) * size_t(j.bps);
    return j.planesBytes >= need && j.dstBytes >= size_t(j.dstStride) * size_t(j.dstH);
}

// One conversion. toReadback: into the persistent read-back buffer (verify), else into j.dst (the layer, imported
// once and cached; a persistent staging buffer when the import is refused). Caller holds g.lock and state is kReady.
bool run(const Job& j, bool toReadback, bool countIt)
{
    const double t0 = nowMs();
    const size_t cw = size_t(j.srcW + 1) / 2, ch = size_t(j.srcH + 1) / 2;
    const size_t inBytes = (size_t(j.srcW) * j.srcH + 2 * cw * ch) * size_t(j.bps);
    const size_t dstBytes = size_t(j.dstStride) * size_t(j.dstH);
    Api& vk = g.vk;
    // the next ring slot (with synchronous conversions its fence has always signalled; checked anyway)
    Slot& sl = g.slots[g.nextSlot]; const int slotIndex = g.nextSlot; g.nextSlot = (g.nextSlot + 1) % kSlots;
    if (sl.pending) {
        VkResult w = vk.WaitForFences(g.device, 1, &sl.fence, VK_TRUE, kFenceTimeoutNs);
        if (w == VK_TIMEOUT) { g.hung = true; fail("staging slot %d still busy after %llu ms; GPU objects kept alive", slotIndex, (unsigned long long)(kFenceTimeoutNs / 1000000)); return false; }
        sl.pending = false;
    }
    // V3: a pace-queue picture (memory that stays mapped until forget()) is read in place: imported once, no copy.
    uint32_t inOff = 0;
    Cached* inPlace = j.planesPersistent && !toReadback ? cachedImport(j.planes, inBytes, inOff, true) : nullptr;
    if (inPlace && (inOff & 3)) { inPlace->inUse = false; inPlace = nullptr; inOff = 0; }   // (never: direct maps are page-aligned)
    if (!inPlace) {
        inOff = 0;
        if (!ensureStage(sl.in, inBytes + 64, false)) { cacheDone(); return false; }
        memcpy(sl.in.mapped, j.planes, inBytes);
        if (!sl.in.coherent) {
            VkMappedMemoryRange mr { VK_STRUCTURE_TYPE_MAPPED_MEMORY_RANGE }; mr.memory = sl.in.memory; mr.size = VK_WHOLE_SIZE;
            vk.FlushMappedMemoryRanges(g.device, 1, &mr);
        }
    }
    const Buf& srcB = inPlace ? inPlace->b : sl.in;
    uint32_t outOff = 0;
    Cached* layer = toReadback ? nullptr : cachedImport(j.dst, std::min(dstBytes, j.dstBytes), outOff);
    if (layer && (outOff & 3)) { cacheDone(); layer = nullptr; outOff = 0; }   // (never for page-aligned layers)
    const double tImport = nowMs();
    if (!layer && !ensureStage(g.stageOut, dstBytes, true)) { cacheDone(); return false; }
    const Buf& dstB = layer ? layer->b : g.stageOut;
    if (!layer) outOff = 0;
    // V4: the picture's PQ layer (HDR10 or HLG source), imported once like the RGBA8 layer; written in the same pass.
    // No import (refused, copy mode) = no PQ layer for this picture (hdrDone stays false; the caller shows SDR).
    uint32_t hdrOff = 0; Cached* hdrLayer = nullptr;
    if (j.hdrDst && (j.hdrMode == 1 || j.hdrMode == 2) && j.hdrDstBytes >= dstBytes) {
        hdrLayer = cachedImport(j.hdrDst, dstBytes, hdrOff);
        if (hdrLayer && (hdrOff & 3)) { hdrLayer->inUse = false; hdrLayer = nullptr; }
        if (!hdrLayer && g.hdrNotes < 6) { ++g.hdrNotes; logLine(true, "HDR: the PQ layer import was refused: this picture has no PQ layer (SDR mapping)"); }
    }

    VkDescriptorBufferInfo infos[3] = { { srcB.buffer, 0, VK_WHOLE_SIZE }, { dstB.buffer, 0, VK_WHOLE_SIZE }, { hdrLayer ? hdrLayer->b.buffer : dstB.buffer, 0, VK_WHOLE_SIZE } };
    VkWriteDescriptorSet writes[3] {};
    for (int i = 0; i < 3; ++i) {
        writes[i].sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET; writes[i].dstSet = g.set; writes[i].dstBinding = uint32_t(i);
        writes[i].descriptorCount = 1; writes[i].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER; writes[i].pBufferInfo = &infos[i];
    }
    g.vk.UpdateDescriptorSets(g.device, 3, writes, 0, nullptr);
    Push pc {};
    pc.srcW = j.srcW; pc.srcH = j.srcH; pc.dstW = j.dstW; pc.dstH = j.dstH; pc.dstStrideWords = j.dstStride / 4; pc.bps = j.bps;
    pc.srcBase = inOff; pc.dstBase = outOff / 4; pc.swapRB = j.swapRB ? 1 : 0;   // V3: srcBase in bytes (the shader's unit)
    colourFor(j, pc);
    if (hdrLayer) { pc.hdrMode = j.hdrMode; pc.hdrBase = hdrOff / 4; }

    const uint32_t q = uint32_t(slotIndex * 2);
    vk.ResetCommandBuffer(sl.cmd, 0);
    VkCommandBufferBeginInfo bi { VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO };
    bi.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
    vk.BeginCommandBuffer(sl.cmd, &bi);
    if (g.timers) { vk.CmdResetQueryPool(sl.cmd, g.queries, q, 2); vk.CmdWriteTimestamp(sl.cmd, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, g.queries, q); }
    VkMemoryBarrier hostWrites { VK_STRUCTURE_TYPE_MEMORY_BARRIER };
    hostWrites.srcAccessMask = VK_ACCESS_HOST_WRITE_BIT; hostWrites.dstAccessMask = VK_ACCESS_SHADER_READ_BIT;
    vk.CmdPipelineBarrier(sl.cmd, VK_PIPELINE_STAGE_HOST_BIT, VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, 0, 1, &hostWrites, 0, nullptr, 0, nullptr);
    vk.CmdBindPipeline(sl.cmd, VK_PIPELINE_BIND_POINT_COMPUTE, g.pipeline);
    vk.CmdBindDescriptorSets(sl.cmd, VK_PIPELINE_BIND_POINT_COMPUTE, g.layout, 0, 1, &g.set, 0, nullptr);
    vk.CmdPushConstants(sl.cmd, g.layout, VK_SHADER_STAGE_COMPUTE_BIT, 0, sizeof pc, &pc);
    vk.CmdDispatch(sl.cmd, uint32_t(j.dstW + 15) / 16, uint32_t(j.dstH + 7) / 8, 1);
    VkMemoryBarrier toHost { VK_STRUCTURE_TYPE_MEMORY_BARRIER };
    toHost.srcAccessMask = VK_ACCESS_SHADER_WRITE_BIT; toHost.dstAccessMask = VK_ACCESS_HOST_READ_BIT;
    vk.CmdPipelineBarrier(sl.cmd, VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, VK_PIPELINE_STAGE_HOST_BIT, 0, 1, &toHost, 0, nullptr, 0, nullptr);
    if (g.timers) vk.CmdWriteTimestamp(sl.cmd, VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT, g.queries, q + 1);
    VkResult r = vk.EndCommandBuffer(sl.cmd);
    VkSubmitInfo si { VK_STRUCTURE_TYPE_SUBMIT_INFO };
    si.commandBufferCount = 1; si.pCommandBuffers = &sl.cmd;
    if (r == VK_SUCCESS) r = vk.ResetFences(g.device, 1, &sl.fence);
    if (r == VK_SUCCESS) {
        if (g.qlock) g.qlock();   // V3: the shared queue (the present submits and presents on it too)
        r = vk.QueueSubmit(g.queue, 1, &si, sl.fence);
        if (g.qunlock) g.qunlock();
        if (r == VK_SUCCESS) sl.pending = true;
    }
    if (r == VK_SUCCESS) {
        // The layer must be complete before the hole-punch publishes it: this conversion waits for its own fence.
        r = vk.WaitForFences(g.device, 1, &sl.fence, VK_TRUE, kFenceTimeoutNs);
        if (r == VK_TIMEOUT) {
            // The GPU may still write into the imported layer: keep every object (nothing freed or reused)
            // and never submit again. The layer is handed back as "not converted" and the CPU redoes it.
            g.hung = true;
            fail("a conversion did not finish in %llu ms (%dx%d -> %dx%d); GPU objects kept alive, no further submissions", (unsigned long long)(kFenceTimeoutNs / 1000000), j.srcW, j.srcH, j.dstW, j.dstH);
            return false;
        }
        if (r == VK_SUCCESS) sl.pending = false;
    }
    cacheDone();   // the fence has signalled (or the submit failed): forgotten layers can go now
    if (r == VK_SUCCESS && hdrLayer) {
        if (j.hdrDone) *j.hdrDone = true;
        g.statHdr.fetch_add(1, std::memory_order_relaxed);
        if (g.hdrNotes < 6) { ++g.hdrNotes; logLine(true, "HDR: PQ layer written on the GPU (%s source, %dx%d -> %dx%d)", j.hdrMode == 1 ? "PQ (ST 2084)" : "HLG -> PQ", j.srcW, j.srcH, j.dstW, j.dstH); }
    }
    if (r != VK_SUCCESS) {
        g.failures++;
        fail("submit/wait: %d", int(r));
        return false;
    }
    if (!layer) {
        if (!g.stageOut.coherent) {
            VkMappedMemoryRange mr { VK_STRUCTURE_TYPE_MAPPED_MEMORY_RANGE };
            mr.memory = g.stageOut.memory; mr.offset = 0; mr.size = VK_WHOLE_SIZE;
            vk.InvalidateMappedMemoryRanges(g.device, 1, &mr);
        }
        if (!toReadback) {   // whole rows of visible pixels only: the stride padding of the layer is never read
            const uint8_t* s = static_cast<const uint8_t*>(g.stageOut.mapped);
            if (size_t(j.dstStride) == size_t(j.dstW) * 4) memcpy(j.dst, s, dstBytes);
            else for (int y = 0; y < j.dstH; ++y) memcpy(j.dst + size_t(y) * j.dstStride, s + size_t(y) * j.dstStride, size_t(j.dstW) * 4);
            if (countIt) g.copies++;
        }
    }
    double gpuMs = 0;
    if (g.timers) {   // the fence above has signalled: these results are ready (no WAIT flag: never blocks)
        uint64_t ts[2] = {};
        if (vk.GetQueryPoolResults(g.device, g.queries, q, 2, sizeof ts, ts, sizeof ts[0], VK_QUERY_RESULT_64_BIT) == VK_SUCCESS && ts[1] >= ts[0])
            gpuMs = double(ts[1] - ts[0]) * g.timestampNs / 1e6;
    }
    if (countIt) {
        const double wall = nowMs() - t0;
        g.statPictures.fetch_add(1, std::memory_order_relaxed);
        (inPlace ? g.statInPlace : g.statRingCopies).fetch_add(1, std::memory_order_relaxed);   // V3
        g.statWallUs.fetch_add(uint64_t(wall * 1000), std::memory_order_relaxed); g.statGpuUs.fetch_add(uint64_t(gpuMs * 1000), std::memory_order_relaxed);
        g.pictures++; g.sumWall += wall; g.sumGpu += gpuMs; g.sumImport += tImport - t0; g.maxWall = std::max(g.maxWall, wall);
        if (++g.windowN == 300) {
            if (g.windowLogs++ < 60)
                logLine(false, "300 pictures %dx%d%s -> %dx%d: wall avg %.2f ms (max %.2f, input + layer lookup %.2f), GPU %.2f ms; in place %llu, ring copies %llu; totals pictures=%llu imports=%llu (pictures %llu, hits %llu) cacheHits=%llu importFails=%llu copies=%llu forgets=%llu live buffers=%ld memory=%ld%s",
                    j.srcW, j.srcH, j.bps == 2 ? " 10-bit" : "", j.dstW, j.dstH, g.sumWall / 300, g.maxWall, g.sumImport / 300, g.sumGpu / 300,
                    (unsigned long long)g.statInPlace.load(), (unsigned long long)g.statRingCopies.load(),
                    (unsigned long long)g.pictures, (unsigned long long)g.imports, (unsigned long long)g.pictureImports, (unsigned long long)g.pictureHits,
                    (unsigned long long)g.cacheHits, (unsigned long long)g.importFails,
                    (unsigned long long)g.copies, (unsigned long long)g.forgets, g.liveBuffers, g.liveMemory, g.shared ? ", shared device" : "");
            g.windowN = 0; g.sumWall = g.sumGpu = g.sumImport = g.maxWall = 0;
        }
    }
    return true;
}

} // namespace

void setNote(void (*note)(const char*)) { g_note.store(note, std::memory_order_release); }

Plan plan(const Job& j)
{
    int s = g.state.load(std::memory_order_acquire);
    if (s == kOff) {
        static std::atomic<bool> checked { false };
        if (checked.exchange(true)) return kCpu;
        if (access(flagPath(), F_OK) != 0) { g.state.store(kFailed, std::memory_order_release); return kCpu; }   // flag absent: never again
        // preinit() did not run (no SDL_Init wrap): set up on a thread of its own, as V1 did
        g.state.store(kStarting, std::memory_order_release);
        std::thread([] { setUp(); g.setUpDone.store(true, std::memory_order_release); }).detach();
        return kCpu;
    }
    if (s != kReady || !jobFits(j)) return kCpu;
    const int d = j.bps - 1;
    if (g.verified[d] < 0) return kCpu;
    if (g.verified[d] > 0 || !g.optVerify) return kGpu;
    // Not verified yet for this depth: the CPU converts this picture as usual and the GPU result is compared with it.
    // V2: enlargements too (the shader follows the CPU's integer upscale), so a 2160 canvas verifies with 1080p video.
    return kVerify;
}

bool convert(const Job& j)
{
    std::lock_guard<std::mutex> l(g.lock);
    if (g.state.load(std::memory_order_acquire) != kReady || !jobFits(j)) return false;
    return run(j, false, true);
}

void verify(const Job& j)
{
    std::lock_guard<std::mutex> l(g.lock);
    if (g.state.load(std::memory_order_acquire) != kReady || !jobFits(j)) return;
    const int d = j.bps - 1;
    if (g.verified[d] != 0) return;
    const double t0 = nowMs();
    if (!run(j, true, false)) return;   // into the persistent read-back buffer
    const double gpuWall = nowMs() - t0;
    const uint8_t* s = static_cast<const uint8_t*>(g.stageOut.mapped);
    // compare the visible pixels (alpha included)
    uint64_t sum = 0, over4 = 0, over12 = 0; int worst = 0;
    const uint64_t n = uint64_t(j.dstW) * j.dstH * 4;
    for (int y = 0; y < j.dstH; ++y) {
        const uint8_t* a = j.dst + size_t(y) * j.dstStride; const uint8_t* b = s + size_t(y) * j.dstStride;
        for (int x = 0; x < j.dstW * 4; ++x) {
            const int e = std::abs(int(a[x]) - int(b[x]));
            sum += unsigned(e); worst = std::max(worst, e); over4 += e > 4; over12 += e > 12;
        }
    }
    const double mean = double(sum) / double(n), p4 = 100.0 * double(over4) / double(n), p12 = 100.0 * double(over12) / double(n);
    const bool shrink = j.dstW < j.srcW || j.dstH < j.srcH;
    // 1:1 and enlargements (V2: same rule as the CPU): rounding-level differences only. Shrinking: filters differ at edges.
    const bool pass = shrink ? (mean <= 2.5 && p12 <= 1.0) : (mean <= 1.0 && p12 <= 0.5);
    g.verifyRuns[d]++;
    logLine(true, "verify %d-bit %dx%d -> %dx%d (%s) matrix %d %s range: mean |diff| %.3f, >4: %.3f%%, >12: %.3f%%, worst %d, GPU wall %.2f ms -> %s (%d/3)",
        j.bps == 2 ? 10 : 8, j.srcW, j.srcH, j.dstW, j.dstH, shrink ? "shrink" : (j.dstW == j.srcW && j.dstH == j.srcH) ? "1:1" : "enlarge",
        j.matrix, j.fullRange ? "full" : "limited", mean, p4, p12, worst, gpuWall, pass ? "match" : "MISMATCH", g.verifyRuns[d]);
    if (!pass) { g.verified[d] = -1; logLine(true, "%d-bit pictures stay on the CPU for this run (GPU result differs)", j.bps == 2 ? 10 : 8); return; }
    if (g.verifyRuns[d] >= 3) { g.verified[d] = 1; logLine(true, "%d-bit pictures now convert on the GPU", j.bps == 2 ? 10 : 8); }
}

// OMNI_GPU_VIDEO_V2: [p, ...) is about to be unmapped (a layer grows or goes). Any thread, never blocks on a conversion.
void forget(const void* p)
{
    if (!p || g.state.load(std::memory_order_acquire) == kOff) return;
    std::lock_guard<std::mutex> l(g.cacheLock);
    const uintptr_t at = uintptr_t(p);
    for (auto it = g.layers.begin(); it != g.layers.end();) {
        if (at >= it->start && at < it->end && !it->dead) {
            g.forgets++;
            if (it->inUse || g.hung) { it->dead = true; ++it; continue; }   // a conversion still has it: freed when it ends
            freeBuf(it->b); it = g.layers.erase(it); continue;
        }
        ++it;
    }
}

bool preinit()
{
    int expected = kOff;
    if (access(flagPath(), F_OK) != 0) return false;
    if (!g.state.compare_exchange_strong(expected, kStarting, std::memory_order_acq_rel)) return g.state.load() == kReady;
    logLine(true, "preinit: RADV set-up now, before any video decoder (title start)");
    setUp();
    g.setUpDone.store(true, std::memory_order_release);
    return g.state.load(std::memory_order_acquire) == kReady;
}

void stats(uint64_t& pictures, uint64_t& wallUs, uint64_t& gpuUs)
{
    pictures = g.statPictures.load(std::memory_order_relaxed); wallUs = g.statWallUs.load(std::memory_order_relaxed); gpuUs = g.statGpuUs.load(std::memory_order_relaxed);
}

void stats2(uint64_t& inPlace, uint64_t& ringCopies, int& sharedDevice)
{
    inPlace = g.statInPlace.load(std::memory_order_relaxed); ringCopies = g.statRingCopies.load(std::memory_order_relaxed); sharedDevice = g.shared ? 1 : 0;
}

void stats3(uint64_t& hdrPictures) { hdrPictures = g.statHdr.load(std::memory_order_relaxed); }   // V4

void liveObjects(long& buffers, long& memory, size_t& cached)
{
    std::lock_guard<std::mutex> l(g.cacheLock);
    buffers = g.liveBuffers; memory = g.liveMemory; cached = g.layers.size();
}

} // namespace OmniGpuVideo

extern "C" int omni_gpu_video_preinit() { return OmniGpuVideo::preinit() ? 1 : 0; }
extern "C" void omni_gpu_video_forget(const void* p) { OmniGpuVideo::forget(p); }
extern "C" void omni_gpu_video_stats(uint64_t* pictures, uint64_t* wallUs, uint64_t* gpuUs) { OmniGpuVideo::stats(*pictures, *wallUs, *gpuUs); }
extern "C" void omni_gpu_video_stats2(uint64_t* inPlace, uint64_t* ringCopies, int* sharedDevice) { OmniGpuVideo::stats2(*inPlace, *ringCopies, *sharedDevice); }
extern "C" void omni_gpu_video_stats3(uint64_t* hdrPictures) { OmniGpuVideo::stats3(*hdrPictures); }   // V4

extern "C" void omni_gpu_video_shutdown()
{
    using namespace OmniGpuVideo;
    int s = g.state.exchange(kFailed, std::memory_order_acq_rel);
    if (s == kStarting) {   // let the set-up thread finish (bounded: 2 s), then tear down what it made
        for (int i = 0; i < 400 && !g.setUpDone.load(std::memory_order_acquire); ++i) usleep(5000);
        if (!g.setUpDone.load(std::memory_order_acquire)) { logLine(true, "shutdown: set-up still running after 2 s; left to the system"); return; }
    }
    std::lock_guard<std::mutex> l(g.lock);
    if (g.hung) { logLine(true, "shutdown: GPU was hung; objects left for the system to reclaim"); return; }
    if (!g.instance) return;
    Api& vk = g.vk;
    if (g.device) {
        // V3: a shared device's queue belongs to the present too (vkDeviceWaitIdle needs every queue externally
        // synchronised): wait for our own slot fences instead. Our own device: as V2.
        if (g.shared) { for (Slot& sl : g.slots) if (sl.pending && sl.fence) vk.WaitForFences(g.device, 1, &sl.fence, VK_TRUE, kFenceTimeoutNs); }
        else if (vk.DeviceWaitIdle) vk.DeviceWaitIdle(g.device);
        { std::lock_guard<std::mutex> c(g.cacheLock); for (Cached& e : g.layers) freeBuf(e.b); g.layers.clear(); }
        for (Slot& sl : g.slots) { freeBuf(sl.in); if (sl.fence) vk.DestroyFence(g.device, sl.fence, nullptr); sl = Slot {}; }
        freeBuf(g.stageOut);
        if (g.queries) vk.DestroyQueryPool(g.device, g.queries, nullptr);
        if (g.commands) vk.DestroyCommandPool(g.device, g.commands, nullptr);
        if (g.pool) vk.DestroyDescriptorPool(g.device, g.pool, nullptr);
        if (g.pipeline) vk.DestroyPipeline(g.device, g.pipeline, nullptr);
        if (g.layout) vk.DestroyPipelineLayout(g.device, g.layout, nullptr);
        if (g.setLayout) vk.DestroyDescriptorSetLayout(g.device, g.setLayout, nullptr);
        if (g.shader) vk.DestroyShaderModule(g.device, g.shader, nullptr);
        if (g.cache) vk.DestroyPipelineCache(g.device, g.cache, nullptr);
        if (!g.shared && vk.DestroyDevice) vk.DestroyDevice(g.device, nullptr);   // V3: the present destroys a shared device
        g.device = VK_NULL_HANDLE;
    }
    if (!g.shared && vk.DestroyInstance) vk.DestroyInstance(g.instance, nullptr);
    g.instance = VK_NULL_HANDLE;
    logLine(true, "shutdown: GPU objects freed%s (pictures=%llu imports=%llu cacheHits=%llu importFails=%llu copies=%llu forgets=%llu; live buffers=%ld memory=%ld)",
        g.shared ? " (shared device left to the present)" : "",
        (unsigned long long)g.pictures, (unsigned long long)g.imports, (unsigned long long)g.cacheHits, (unsigned long long)g.importFails,
        (unsigned long long)g.copies, (unsigned long long)g.forgets, g.liveBuffers, g.liveMemory);
}

#ifdef OMNI_GPU_VIDEO_HOST_TEST
extern "C" void omni_gpu_video_test_live(long* buffers, long* memory, size_t* cached) { OmniGpuVideo::liveObjects(*buffers, *memory, *cached); }
#endif
