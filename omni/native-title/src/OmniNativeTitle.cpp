// Omni as a native PS5 title, Stage 0 (omni-native-s0; s0c: close handling; s2-gpu: GPU video/present shutdown on exit and close): boot log, import check, stop-after phases,
// memory and GPU probes, the exit route, and the dlopen/dlsym shim for the title.
// Only this (UI) process is the title PPSA99732; WebProcess/NetworkProcess stay the existing
// /data/omni/omni-engine.elf payload, started over 127.0.0.1:9021 (NativeLauncherState.cpp).
// SPDX-License-Identifier: GPL-3.0-or-later
#include <atomic>
#include <cerrno>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <new>
#include <pthread.h>
#include <signal.h>
#include <dirent.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#include <vulkan/vulkan.h>
#include <SDL2/SDL.h>

extern "C" {
int32_t sceKernelConfiguredFlexibleMemorySize(size_t*);
int32_t sceKernelAvailableFlexibleMemorySize(size_t*);
size_t sceKernelGetDirectMemorySize(void);
int32_t sceKernelAvailableDirectMemorySize(off_t, off_t, size_t, off_t*, size_t*);
int sceSysmoduleLoadModule(uint16_t);
int sceKernelGetModuleList(int*, size_t, size_t*);
int sceKernelDlsym(int, const char*, void**);
// The system function (an import): linked with --wrap=sceSystemServiceLoadExec.
int __real_sceSystemServiceLoadExec(const char*, const char**);
// Omni's own sceSystemServiceLoadExec (OmniMain.cpp: releases the decoder and the audio relay,
// then calls the system one); renamed to this in the title's copy of OmniMain.o (s0b: was
// __wrap_sceSystemServiceLoadExec in s0; the wrap is now ours, below, so Omni's own Exit path
// also stops the child launcher first).
int omni_impl_sceSystemServiceLoadExec(const char*, const char**);
// NativeLauncherState.cpp (s0b): stop spawning children, wait for in-flight ones to finish loading.
void omni_native_children_stop(int maxMs);
unsigned omni_native_check_imports(void (*log)(const char*, ...)); // generated (import_check.cpp)
int __real_main(int, char**, char**);
int omni_launcher_prespawn(const char*, int);
int omni_launcher_spares_pending(void);
void omni_native_log(const char*, ...);
// s0c: NativeLauncherState.cpp
void omni_native_children_stop(int maxMs);
int __real_sigaction(int, const struct sigaction*, struct sigaction*);
}

// ---------------------------------------------------------------- boot log
// /data/omni/native/boot.log, every line timestamped and fsync'd (survives a console restart);
// three generations: boot.log (this launch), boot.log.1, boot.log.2.
namespace {
int g_boot = -1;
struct timespec g_t0;
pthread_mutex_t g_bootLock = PTHREAD_MUTEX_INITIALIZER;
char g_stopAfter[16] = "page";
enum Phase { kMemory = 0, kGpu = 1, kChildren = 2, kPage = 3 };
int g_stopPhase = kPage;

void bootOpen()
{
    clock_gettime(CLOCK_MONOTONIC, &g_t0);
    mkdir("/data/omni", 0777);
    mkdir("/data/omni/native", 0777);
    rename("/data/omni/native/boot.log.1", "/data/omni/native/boot.log.2");
    rename("/data/omni/native/boot.log", "/data/omni/native/boot.log.1");
    g_boot = open("/data/omni/native/boot.log", O_WRONLY | O_CREAT | O_TRUNC | O_APPEND, 0666);   // jit2: O_APPEND, so the children's crash lines (OMNI_CRASH_V2) are never written over
}
}

extern "C" void omni_native_log(const char* format, ...)
{
    char line[1024];
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    double t = (now.tv_sec - g_t0.tv_sec) + (now.tv_nsec - g_t0.tv_nsec) / 1e9;
    int used = snprintf(line, sizeof line, "[%9.3f] ", t);
    va_list args;
    va_start(args, format);
    int n = vsnprintf(line + used, sizeof line - used - 2, format, args);
    va_end(args);
    if (n < 0) n = 0;
    used += n < int(sizeof line - used - 2) ? n : int(sizeof line - used - 2);
    if (used && line[used - 1] != '\n') line[used++] = '\n';
    // s0c: trylock, so a line from a signal handler never deadlocks on a lock its own thread holds.
    bool locked = false;
    for (int i = 0; i < 20 && !(locked = !pthread_mutex_trylock(&g_bootLock)); ++i) usleep(500);
    if (g_boot >= 0) { (void)!write(g_boot, line, used); fsync(g_boot); }
    if (locked) pthread_mutex_unlock(&g_bootLock);
}

// ---------------------------------------------------------------- closing marker (s0c)
// /data/omni/native/closing-<title pid>: the native child engine (omni-engine-child.elf,
// OMNI_NATIVE_CHILD_V1) polls it every 100 ms and leaves at once; it also leaves when the title's
// pid is gone (for a close the title never sees, e.g. SIGKILL). Async-signal-safe.
static void markClosing()
{
    unlink("/data/hub/runtime/omni.json");   // s2 OMNI_HUB_CARDS_V1: Bloom Core sees Omni as not running (async-signal-safe)
    char path[64];
    snprintf(path, sizeof path, "/data/omni/native/closing-%d", int(getpid()));
    int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0666);
    if (fd >= 0) { (void)!write(fd, "1\n", 2); fsync(fd); close(fd); }
}
static void removeStaleClosingMarkers()
{
    if (DIR* d = opendir("/data/omni/native")) {
        while (struct dirent* e = readdir(d)) {
            if (strncmp(e->d_name, "closing-", 8)) continue;
            char path[300];
            snprintf(path, sizeof path, "/data/omni/native/%s", e->d_name);
            unlink(path);
        }
        closedir(d);
    }
}

// ---------------------------------------------------------------- termination signals (s0c)
// The PS button "Close" (and app replacement) may end the title with SIGTERM/SIGHUP/SIGINT. s0b had
// no handler of its own and Omni's (OmniMain.cpp omniHwReleaseOnTerm: decoder release, then the
// default action) logged nothing, so a close left no trace and the console went down (2026-11-02
// 12:44:21, children still alive). Now: log it, mark closing (children leave within ~100 ms),
// give them 150 ms, then chain to Omni's handler (decoders + compute queue) or the default action.
// Omni installs its handler later (main): __wrap_sigaction records it instead of replacing ours.
namespace {
struct sigaction g_appTerm[64];
volatile sig_atomic_t g_haveApp[64];
volatile sig_atomic_t g_terminating = 0;
}
static bool isTermSignal(int s) { return s == SIGTERM || s == SIGHUP || s == SIGINT; }
extern "C" void omni_gpu_signal_close() __attribute__((weak));   // OMNI_GPU_PRESENT_V1: async-signal-safe flag
extern "C" int omni_gpu_signal_wait(int ms) __attribute__((weak));  // OMNI_GPU_PRESENT_V1: bounded wait for its teardown
static void nativeOnTerm(int sig)
{
    if (g_terminating) { struct sigaction d {}; d.sa_handler = SIG_DFL; sigemptyset(&d.sa_mask); __real_sigaction(sig, &d, nullptr); raise(sig); return; }
    g_terminating = 1;
    omni_native_log("close: signal %d received (PS button close or app replacement); marking closing", sig);
    markClosing();
    if (omni_gpu_signal_close) omni_gpu_signal_close();   // OMNI_GPU_PRESENT_V1: its thread frees swapchain/display/device meanwhile
    usleep(150000);
    if (omni_gpu_signal_wait) omni_native_log("close: GPU present teardown %s", omni_gpu_signal_wait(300) ? "done (or not on)" : "not finished in 300 ms (left to the system)");
    omni_native_log("close: children given 150 ms; %s", g_haveApp[sig] ? "chaining to Omni's handler (decoder + compute queue release, then the default action)" : "default action");
    struct sigaction d {};
    d.sa_handler = SIG_DFL;
    sigemptyset(&d.sa_mask);
    if (g_haveApp[sig]) {
        struct sigaction app = g_appTerm[sig];
        if (app.sa_flags & SA_RESETHAND) __real_sigaction(sig, &d, nullptr);
        if (app.sa_handler != SIG_DFL && app.sa_handler != SIG_IGN) { app.sa_handler(sig); }
    }
    __real_sigaction(sig, &d, nullptr);
    omni_native_log("close: raising %d with the default action", sig);
    raise(sig);
}
static void installTermHandlers()
{
    static const int kSignals[] = { SIGTERM, SIGHUP, SIGINT };
    for (int sig : kSignals) {
        struct sigaction a {};
        a.sa_handler = nativeOnTerm;
        sigemptyset(&a.sa_mask);
        int rc = __real_sigaction(sig, &a, nullptr);
        if (rc) omni_native_log("close: sigaction(%d) failed errno=%d", sig, errno);
    }
    omni_native_log("close: termination handlers installed (SIGTERM, SIGHUP, SIGINT)");
}
extern "C" int __wrap_sigaction(int sig, const struct sigaction* act, struct sigaction* old)
{
    if (sig > 0 && sig < 64 && isTermSignal(sig)) {
        if (old) __real_sigaction(sig, nullptr, old);
        if (act) {
            g_appTerm[sig] = *act;
            g_haveApp[sig] = 1;
            omni_native_log("close: Omni's handler for signal %d recorded (runs after the title's close steps)", sig);
        }
        return 0;
    }
    return __real_sigaction(sig, act, old);
}

// ---------------------------------------------------------------- system status (s0c, diagnostic)
// Logs every change of sceSystemServiceGetStatus (event count, system UI overlaid, background) and
// every system event (type + first bytes), to learn what a title is told before a close. Both are
// resolved optionally (dlsym shim), so a missing function only disables this.
namespace { int (*g_getStatus)(void*); int (*g_receiveEvent)(void*); }
static void* statusWatch(void*)
{
    static unsigned char status[4096], previous[8], event[65536];
    for (unsigned n = 0;; ++n) {
        memset(status, 0, 16);
        int rc = g_getStatus(status);
        if (rc == 0 && memcmp(status, previous, 8)) {
            int32_t count; memcpy(&count, status, 4);
            omni_native_log("status: events=%d systemUiOverlaid=%d background=%d cpuMode7=%d", int(count), status[4], status[5], status[6]);
            memcpy(previous, status, 8);
            for (int i = 0; i < count && i < 8 && g_receiveEvent; ++i) {
                memset(event, 0, 64);
                int e = g_receiveEvent(event);
                int32_t type; memcpy(&type, event, 4);
                omni_native_log("status: event rc=0x%x type=0x%x data %02x%02x%02x%02x %02x%02x%02x%02x", unsigned(e), unsigned(type),
                    event[4], event[5], event[6], event[7], event[8], event[9], event[10], event[11]);
            }
        } else if (rc && n == 0) omni_native_log("status: sceSystemServiceGetStatus=0x%x; watcher stops", unsigned(rc));
        if (rc && n == 0) return nullptr;
        usleep(200000);
    }
}
extern "C" void* dlsym(void*, const char*);
static void statusWatchStart()
{
    g_getStatus = reinterpret_cast<int (*)(void*)>(dlsym(nullptr, "sceSystemServiceGetStatus"));
    g_receiveEvent = reinterpret_cast<int (*)(void*)>(dlsym(nullptr, "sceSystemServiceReceiveEvent"));
    if (!g_getStatus) { omni_native_log("status: sceSystemServiceGetStatus unavailable; no status log"); return; }
    pthread_t t; pthread_attr_t attr;
    pthread_attr_init(&attr); pthread_attr_setstacksize(&attr, 256 * 1024); pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED);
    int e = pthread_create(&t, &attr, statusWatch, nullptr);
    pthread_attr_destroy(&attr);
    omni_native_log("status: watcher %s (ReceiveEvent %s)", e ? "FAILED" : "started", g_receiveEvent ? "available" : "unavailable");
}

// ---------------------------------------------------------------- leaving
// A title must never call exit/_exit (SIGSYS: PS5-HOMEBREW-PLATFORM-NOTES section 18). It asks the
// shell to end it with sceSystemServiceLoadExec("exit") and waits.
// s0b: every route out (Omni's Exit menu, stop-after, exit()/return from main) passes here or through
// __wrap_sceSystemServiceLoadExec: stop the launcher's refill and let in-flight children finish
// loading first. A child still loading when the title is gone found its parent dead, dropped its
// spare ticket and started as a second UI process (s0 run c: 6 orphan payloads).
extern "C" void omni_gpu_video_shutdown() __attribute__((weak));   // OMNI_GPU_VIDEO_V1 (OmniGpuVideo.cpp)
extern "C" void omni_gpu_present_shutdown() __attribute__((weak));   // OMNI_GPU_PRESENT_V1 (OmniGpuPresent.cpp)
extern "C" int __wrap_sceSystemServiceLoadExec(const char* path, const char** argv)
{
    omni_native_children_stop(10000);
    markClosing(); // s0c: the native children leave (they also would on IPC close)
    if (omni_gpu_present_shutdown) omni_gpu_present_shutdown();   // OMNI_GPU_PRESENT_V1: no-op unless the GPU present is on (SDL_Quit usually did it)
    if (omni_gpu_video_shutdown) { omni_gpu_video_shutdown(); omni_native_log("exit: GPU video objects freed (if it was on)"); }   // OMNI_GPU_VIDEO_V1
    omni_native_log("exit: closing marked; Omni's LoadExec (decoder + audio release) next");
    return omni_impl_sceSystemServiceLoadExec(path, argv);
}
[[noreturn]] static void nativeLeave(int status, const char* why, bool throughOmni)
{
    omni_native_log("exit: status=%d reason=%s route=%s", status, why, throughOmni ? "Omni LoadExec hook" : "system LoadExec");
    omni_native_children_stop(10000);
    auto volatile system = &__real_sceSystemServiceLoadExec;
    if (!system) {
        omni_native_log("exit: sceSystemServiceLoadExec import missing; waiting for the shell (close the title with PS button)");
    } else {
        if (!throughOmni) markClosing();
        int rc = throughOmni ? __wrap_sceSystemServiceLoadExec("exit", nullptr) : system("exit", nullptr);
        omni_native_log("exit: LoadExec returned 0x%x; waiting for the shell to end the process", unsigned(rc));
    }
    for (;;) sleep(1);
}
static std::atomic<bool> g_mainStarted { false };
extern "C" void catchReturnFromMain(int status) { nativeLeave(status, "return from main", g_mainStarted.load()); }
extern "C" [[noreturn]] void __wrap_exit(int status) { nativeLeave(status, "exit()", g_mainStarted.load()); }
extern "C" [[noreturn]] void __wrap__exit(int status) { nativeLeave(status, "_exit()", g_mainStarted.load()); }
extern "C" [[noreturn]] void __wrap__Exit(int status) { nativeLeave(status, "_Exit()", g_mainStarted.load()); }

// ---------------------------------------------------------------- start (before WebKit's constructors)
static void logLine(const char* format, ...)
{
    char text[512];
    va_list args;
    va_start(args, format);
    vsnprintf(text, sizeof text, format, args);
    va_end(args);
    omni_native_log("%s", text);
}

__attribute__((constructor(101))) static void nativeStart()
{
    bootOpen();
    omni_native_log("Omni native title (omni-native-s0c, PPSA99732) pid=%d uid=%d euid=%d", int(getpid()), int(getuid()), int(geteuid()));
    if (FILE* f = fopen("/data/omni/native/stop-after.txt", "r")) {
        char word[16] = {};
        if (fscanf(f, "%15s", word) == 1) {
            static const char* const names[] = { "memory", "gpu", "children", "page" };
            int found = -1;
            for (int i = 0; i < 4; ++i) if (!strcmp(word, names[i])) found = i;
            if (found >= 0) { g_stopPhase = found; strcpy(g_stopAfter, names[found]); }
            else omni_native_log("stop-after: unknown phase '%s' (memory|gpu|children|page); running everything", word);
        }
        fclose(f);
    }
    omni_native_log("stop-after: %s", g_stopAfter);
    removeStaleClosingMarkers();
    unsigned missing = omni_native_check_imports(logLine);
    if (missing) nativeLeave(3, "missing imports (see [import] lines)", false);
    installTermHandlers();
}

// ---------------------------------------------------------------- phases
static void phaseMemory()
{
    size_t configured = 0, available = 0;
    int a = sceKernelConfiguredFlexibleMemorySize(&configured);
    int b = sceKernelAvailableFlexibleMemorySize(&available);
    size_t direct = sceKernelGetDirectMemorySize();
    off_t start = 0; size_t largest = 0;
    int c = sceKernelAvailableDirectMemorySize(0, off_t(direct), 16 << 10, &start, &largest);
    omni_native_log("memory: flexible configured=%zu MiB (0x%x) available=%zu MiB (0x%x); direct total=%zu MiB largest free=%zu MiB at 0x%llx (0x%x)",
        configured >> 20, unsigned(a), available >> 20, unsigned(b), direct >> 20, largest >> 20, (unsigned long long)start, unsigned(c));
    char* big = new (std::nothrow) char[64u << 20];
    if (big) { for (size_t i = 0; i < (64u << 20); i += 4096) big[i] = char(i); }
    omni_native_log("memory: 64 MiB new %s", big ? "ok (touched)" : "FAILED");
    delete[] big;
    // The pattern that threw std::bad_alloc on 2026-10-20 (~3 MiB C++ allocations, ~777 MiB flexible free).
    enum { kCount = 96, kSize = 3 << 20 };
    static char* blocks[kCount];
    int ok = 0;
    for (int i = 0; i < kCount; ++i) {
        blocks[i] = new (std::nothrow) char[kSize];
        if (!blocks[i]) break;
        memset(blocks[i], 0x5a, 4096); blocks[i][kSize - 1] = 1; ++ok;
    }
    for (int i = 0; i < ok; ++i) delete[] blocks[i];
    sceKernelAvailableFlexibleMemorySize(&available);
    omni_native_log("memory: 3 MiB x %d new: %d ok%s; flexible available after free=%zu MiB", int(kCount), ok, ok == kCount ? "" : " (FAILED)", available >> 20);
}

// RADV is linked statically as an ICD: entry points come from vk_icdGetInstanceProcAddr (as
// Ex-Box's AV2 smoke title, title-smoke/main.c).
extern "C" VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL vk_icdGetInstanceProcAddr(VkInstance, const char*);
#define OMNI_VK(instance, name) reinterpret_cast<PFN_##name>(vk_icdGetInstanceProcAddr(instance, #name))

static void phaseGpu()
{
    // SDL owns VideoOut (as in the browser); Vulkan gets an instance and a device but no surface,
    // so there is exactly one VideoOut owner.
    int sdl = SDL_Init(SDL_INIT_VIDEO);
    SDL_Window* window = sdl ? nullptr : SDL_CreateWindow("omni-native-s0", 0, 0, 1920, 1080, SDL_WINDOW_FULLSCREEN);
    omni_native_log("gpu: SDL_Init=%d window=%p (%s)", sdl, (void*)window, window ? "VideoOut open" : SDL_GetError());
    auto createInstance = OMNI_VK(VK_NULL_HANDLE, vkCreateInstance);
    if (!createInstance) { omni_native_log("gpu: vk_icdGetInstanceProcAddr gave no vkCreateInstance"); }
    VkApplicationInfo app {};
    app.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO;
    app.pApplicationName = "Omni";
    app.pEngineName = "OmniEngine";
    app.apiVersion = VK_API_VERSION_1_3;
    VkInstanceCreateInfo ici {};
    ici.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO;
    ici.pApplicationInfo = &app;
    VkInstance instance = VK_NULL_HANDLE;
    VkResult r = createInstance ? createInstance(&ici, nullptr, &instance) : VK_ERROR_INITIALIZATION_FAILED;
    omni_native_log("gpu: vkCreateInstance=%d", int(r));
    VkDevice device = VK_NULL_HANDLE;
    PFN_vkDestroyDevice destroyDevice = nullptr;
    PFN_vkDeviceWaitIdle waitIdle = nullptr;
    if (r == VK_SUCCESS) {
        auto enumerate = OMNI_VK(instance, vkEnumeratePhysicalDevices);
        auto properties = OMNI_VK(instance, vkGetPhysicalDeviceProperties);
        auto extensionsOf = OMNI_VK(instance, vkEnumerateDeviceExtensionProperties);
        auto queueFamilies = OMNI_VK(instance, vkGetPhysicalDeviceQueueFamilyProperties);
        auto createDevice = OMNI_VK(instance, vkCreateDevice);
        auto deviceProc = OMNI_VK(instance, vkGetDeviceProcAddr);
        uint32_t count = 0;
        VkPhysicalDevice physical[4] = {};
        if (enumerate) { enumerate(instance, &count, nullptr); if (count > 4) count = 4; r = enumerate(instance, &count, physical); }
        omni_native_log("gpu: physical devices=%u (%d)", count, int(r));
        if (count && properties && extensionsOf && queueFamilies && createDevice && deviceProc) {
            VkPhysicalDeviceProperties p {};
            properties(physical[0], &p);
            omni_native_log("gpu: device '%s' api %u.%u.%u driver 0x%x timestampPeriod=%.3f", p.deviceName,
                VK_API_VERSION_MAJOR(p.apiVersion), VK_API_VERSION_MINOR(p.apiVersion), VK_API_VERSION_PATCH(p.apiVersion),
                p.driverVersion, double(p.limits.timestampPeriod));
            uint32_t extensions = 0;
            extensionsOf(physical[0], nullptr, &extensions, nullptr);
            VkExtensionProperties* list = new (std::nothrow) VkExtensionProperties[extensions ? extensions : 1];
            if (list) {
                extensionsOf(physical[0], nullptr, &extensions, list);
                omni_native_log("gpu: %u device extensions", extensions);
                for (uint32_t i = 0; i < extensions; ++i) omni_native_log("gpu:   %s", list[i].extensionName);
                delete[] list;
            }
            uint32_t families = 0;
            queueFamilies(physical[0], &families, nullptr);
            float priority = 1.0f;
            VkDeviceQueueCreateInfo qci {};
            qci.sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO;
            qci.queueFamilyIndex = 0;
            qci.queueCount = 1;
            qci.pQueuePriorities = &priority;
            VkDeviceCreateInfo dci {};
            dci.sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO;
            dci.queueCreateInfoCount = 1;
            dci.pQueueCreateInfos = &qci;
            r = createDevice(physical[0], &dci, nullptr, &device);
            omni_native_log("gpu: queue families=%u; vkCreateDevice=%d %s", families, int(r), r == VK_SUCCESS ? "(RADV device up alongside SDL VideoOut)" : "");
            if (device) {
                destroyDevice = reinterpret_cast<PFN_vkDestroyDevice>(deviceProc(device, "vkDestroyDevice"));
                waitIdle = reinterpret_cast<PFN_vkDeviceWaitIdle>(deviceProc(device, "vkDeviceWaitIdle"));
            }
        } else if (count) omni_native_log("gpu: an instance-level entry point is missing");
    }
    // Ex-Box's teardown order: wait idle, (no pool/fences/semaphores/swapchain here), device, (no surface), instance.
    if (device && waitIdle) { waitIdle(device); omni_native_log("gpu: teardown: device idle"); }
    if (device && destroyDevice) { destroyDevice(device, nullptr); omni_native_log("gpu: teardown: device destroyed"); }
    if (instance) { auto destroy = OMNI_VK(instance, vkDestroyInstance); if (destroy) destroy(instance, nullptr); omni_native_log("gpu: teardown: instance destroyed"); }
    if (window) SDL_DestroyWindow(window);
    if (!sdl) SDL_QuitSubSystem(SDL_INIT_VIDEO);
    omni_native_log("gpu: teardown: SDL video closed");
}

// Children phase: the UI's own start-up (OmniMain.cpp, browser mode) starts two spare
// WebProcess/NetworkProcess payloads over 127.0.0.1:9021 (omni_launcher_prespawn). This thread
// waits until both have loaded (or 30 s), logs it, and leaves through Omni's exit route.
static void* childrenWatch(void*)
{
    for (int i = 0; i < 300; ++i) {
        usleep(100000);
        int pending = omni_launcher_spares_pending();
        if (i % 10 == 0) omni_native_log("children: spares pending=%d after %.1f s", pending, i / 10.0);
        if (i >= 5 && pending == 0) { omni_native_log("children: both spares loaded (acknowledged by the loader children)"); nativeLeave(0, "stop-after=children", true); }
    }
    omni_native_log("children: spares still pending after 30 s (see process-*.log and the loader output)");
    nativeLeave(4, "stop-after=children timeout", true);
}

extern "C" int __wrap_main(int argc, char** argv, char** envp)
{
    omni_native_log("phase memory: start");
    phaseMemory();
    if (g_stopPhase == kMemory) nativeLeave(0, "stop-after=memory", false);
    omni_native_log("phase gpu: start");
    phaseGpu();
    if (g_stopPhase == kGpu) nativeLeave(0, "stop-after=gpu", false);
    if (access("/data/omni/browser-mode.flag", F_OK) == 0 && access("/data/omni/prespawn-disabled.flag", F_OK) != 0) {
        if (g_stopPhase == kChildren) {
            pthread_t t;
            pthread_attr_t attr;
            pthread_attr_init(&attr);
            pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED);
            pthread_create(&t, &attr, childrenWatch, nullptr);
            pthread_attr_destroy(&attr);
        }
    } else if (g_stopPhase == kChildren) {
        omni_native_log("children: browser-mode.flag missing or prespawn-disabled.flag present: Omni will not prespawn; stopping");
        nativeLeave(5, "stop-after=children without prespawn", false);
    }
    statusWatchStart();
    // s2 OMNI_HUB_CARDS_V1 (standard v1.1 items 4 and 14): Omni's live data for Bloom Core, rewritten on every start
    // (pids are reused after a reboot) and removed on every exit or close route that runs (markClosing).
    {
        struct stat hs {};
        if (!stat("/data/hub", &hs) && S_ISDIR(hs.st_mode)) {
            mkdir("/data/hub/runtime", 0777);
            char text[128];
            const int n = snprintf(text, sizeof text, "{\"id\":\"omni\",\"pid\":%d,\"started_at\":%ld}\n", int(getpid()), (long)time(nullptr));
            const int fd = open("/data/hub/runtime/omni.json.tmp", O_WRONLY | O_CREAT | O_TRUNC, 0666);
            if (fd >= 0) {
                const bool ok = n > 0 && write(fd, text, size_t(n)) == n;
                fsync(fd); close(fd);
                if (ok && !rename("/data/hub/runtime/omni.json.tmp", "/data/hub/runtime/omni.json")) omni_native_log("hub: runtime/omni.json written (pid %d)", int(getpid()));
            }
        }
    }
    omni_native_log("phase %s: entering Omni's main (UI process)", g_stopPhase == kChildren ? "children" : "page");
    g_mainStarted = true;
    return __real_main(argc, argv, envp);
}

// ---------------------------------------------------------------- dlopen/dlsym for the title
// The payload SDK's dlopen/dlsym are not in a title. Omni's uses (OmniHwBackend.cpp, OmniMain.cpp,
// OmniCrash.h, OmniHwService.cpp, OmniLazyGraphics.cpp, support.cpp) go through these: system
// modules give a handle; symbols come from the linked imports first, then from the loaded
// modules' exports (sceKernelGetModuleList + sceKernelDlsym, as Ex-Box's optional_modules.cpp).
// Anything under /user (the optional GL libraries) is not mounted in a title: refused.
extern "C" {
int sceVideodec2QueryComputeMemoryInfo(); int sceVideodec2AllocateComputeQueue(); int sceVideodec2ReleaseComputeQueue();
int sceVideodec2QueryDecoderMemoryInfo(); int sceVideodec2CreateDecoder(); int sceVideodec2DeleteDecoder();
int sceVideodec2Reset(); int sceVideodec2Decode(); int sceVideodec2Flush();
int sceKernelVirtualQuery(const void*, int, void*, size_t);
int scePthreadGetaffinity(void*, uint64_t*);
}
namespace {
struct Linked { const char* name; void* address; };
Linked* linkedTable()
{
    static Linked table[] = {
#ifndef OMNI_S0_NO_VDEC_STUB
        { "sceVideodec2QueryComputeMemoryInfo", (void*)&sceVideodec2QueryComputeMemoryInfo },
        { "sceVideodec2AllocateComputeQueue", (void*)&sceVideodec2AllocateComputeQueue },
        { "sceVideodec2ReleaseComputeQueue", (void*)&sceVideodec2ReleaseComputeQueue },
        { "sceVideodec2QueryDecoderMemoryInfo", (void*)&sceVideodec2QueryDecoderMemoryInfo },
        { "sceVideodec2CreateDecoder", (void*)&sceVideodec2CreateDecoder },
        { "sceVideodec2DeleteDecoder", (void*)&sceVideodec2DeleteDecoder },
        { "sceVideodec2Reset", (void*)&sceVideodec2Reset },
        { "sceVideodec2Decode", (void*)&sceVideodec2Decode },
        { "sceVideodec2Flush", (void*)&sceVideodec2Flush },
#endif
        { "sceSystemServiceLoadExec", (void*)&__real_sceSystemServiceLoadExec },
        { "sceKernelVirtualQuery", (void*)&sceKernelVirtualQuery },
        { "scePthreadGetaffinity", (void*)&scePthreadGetaffinity },
        { nullptr, nullptr } };
    return table;
}
struct Handle { char name[64]; };
Handle g_handles[16];
int g_handleCount = 0;
pthread_mutex_t g_dlLock = PTHREAD_MUTEX_INITIALIZER;
const char* g_dlError = nullptr;
int g_selfHandle;
}

extern "C" void* dlopen(const char* path, int)
{
    if (!path) return &g_selfHandle;
    if (!strncmp(path, "/user/", 6)) {
        static std::atomic<int> logged { 0 };
        if (logged++ < 4) omni_native_log("dlopen: %s refused (/user is not mounted in a title)", path);
        g_dlError = "not available in the native title"; errno = ENOENT; return nullptr;
    }
    const char* base = strrchr(path, '/');
    base = base ? base + 1 : path;
    if (strncmp(base, "libSce", 6) || !strstr(base, ".sprx")) {
        omni_native_log("dlopen: %s refused (only system modules in the title)", path);
        g_dlError = "not available in the native title"; return nullptr;
    }
    pthread_mutex_lock(&g_dlLock);
    Handle* h = nullptr;
    for (int i = 0; i < g_handleCount; ++i) if (!strcmp(g_handles[i].name, base)) h = &g_handles[i];
    if (!h && g_handleCount < 16) { h = &g_handles[g_handleCount++]; snprintf(h->name, sizeof h->name, "%s", base); omni_native_log("dlopen: %s -> system module handle", base); }
    pthread_mutex_unlock(&g_dlLock);
    if (!h) g_dlError = "too many modules";
    return h;
}

extern "C" void* dlsym(void*, const char* name)
{
    if (!name) return nullptr;
    for (Linked* l = linkedTable(); l->name; ++l) {
        if (strcmp(l->name, name)) continue;
        void* volatile address = l->address;
        if (address) return address;
        omni_native_log("dlsym: %s is a linked import but unresolved; trying loaded modules", name);
        break;
    }
    auto volatile list = &sceKernelGetModuleList;
    auto volatile resolve = &sceKernelDlsym;
    if (list && resolve) {
        int handles[512] = {};
        size_t count = 0;
        if (!list(handles, 512, &count) && count <= 512) {
            for (size_t i = 0; i < count; ++i) {
                void* result = nullptr;
                if (!resolve(handles[i], name, &result) && result) { omni_native_log("dlsym: %s from module %d", name, handles[i]); return result; }
            }
        }
    }
    omni_native_log("dlsym: %s not found", name);
    g_dlError = "symbol not found";
    return nullptr;
}
extern "C" int dlclose(void*) { return 0; }
extern "C" char* dlerror(void) { const char* e = g_dlError; g_dlError = nullptr; return const_cast<char*>(e); }

// ---------------------------------------------------------------- optional keyboard / IME
// In a title these imports can be null (Ex-Box Q7d/Q8: RIP=0). Resolve them from the loaded
// modules after loading the public keyboard module; calls fail safely when absent.
namespace {
void* g_optional[7];
std::atomic<bool> g_optionalReady { false };
void optionalPrepare()
{
    if (g_optionalReady.exchange(true)) return;
    auto volatile load = &sceSysmoduleLoadModule;
    if (load) omni_native_log("optional: keyboard sysmodule 0x0106 rc=0x%x", unsigned(load(0x106)));
    static const char* const names[7] = { "sceKeyboardInit", "sceKeyboardOpen", "sceKeyboardReadState",
        "sceImeDialogInit", "sceImeDialogGetResult", "sceImeDialogTerm", "sceImeDialogGetStatus" };
    for (int i = 0; i < 7; ++i) g_optional[i] = dlsym(nullptr, names[i]);
}
}
extern "C" int __wrap_sceKeyboardInit() { optionalPrepare(); auto f = reinterpret_cast<int (*)()>(g_optional[0]); return f ? f() : -1; }
extern "C" int __wrap_sceKeyboardOpen(int u, int t, int i, void* p) { optionalPrepare(); auto f = reinterpret_cast<int (*)(int, int, int, void*)>(g_optional[1]); return f ? f(u, t, i, p) : -1; }
extern "C" int __wrap_sceKeyboardReadState(int h, void* p) { auto f = reinterpret_cast<int (*)(int, void*)>(g_optional[2]); return f ? f(h, p) : -1; }
extern "C" int __wrap_sceImeDialogInit(const void* p, void* o) { optionalPrepare(); auto f = reinterpret_cast<int (*)(const void*, void*)>(g_optional[3]); return f ? f(p, o) : -1; }
extern "C" int __wrap_sceImeDialogGetResult(void* p) { auto f = reinterpret_cast<int (*)(void*)>(g_optional[4]); return f ? f(p) : -1; }
extern "C" int __wrap_sceImeDialogTerm() { auto f = reinterpret_cast<int (*)()>(g_optional[5]); return f ? f() : -1; }
extern "C" int __wrap_sceImeDialogGetStatus() { auto f = reinterpret_cast<int (*)()>(g_optional[6]); return f ? f() : 0; }
