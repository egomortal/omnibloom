// SPDX-License-Identifier: GPL-3.0-or-later
// Call sequence and parameters: tools/vdec-probe (console-verified, 10/10
// formats bit-exact), after EVO-PLAYER-PS5 and OpenNOW-PS5 (GPL-3.0).
#include "OmniHwBackend.h"
#include "OmniSceVideodec2.h"
#include <cstring>
#include <dlfcn.h>
#include <mutex>
#include <cstdio>
#ifdef __PROSPERO__
#include <sys/param.h>
#include <sys/cpuset.h>
#include <sys/sysctl.h>
#include <sys/user.h>
#include <sys/stat.h>
#endif
#include <unistd.h>
#include <vector>

extern "C" {
int      sceSysmoduleLoadModule(uint16_t id);
int64_t  sceKernelGetDirectMemorySize(void);
int      sceKernelAllocateDirectMemory(int64_t, int64_t, size_t, size_t, int, int64_t*);
int      sceKernelMapDirectMemory(void**, size_t, int, int, int64_t, size_t);
int      sceKernelReleaseDirectMemory(int64_t, size_t);
int      sceKernelMunmap(void*, size_t);
int      sceKernelMapNamedFlexibleMemory(void**, size_t, int, int, const char*);
int      sceKernelAvailableFlexibleMemorySize(size_t*);
#ifdef __PROSPERO__
int      sceKernelAvailableDirectMemorySize(int64_t, int64_t, size_t, int64_t*, size_t*); // OMNI_HOLEPUNCH_V5
#endif
}

namespace OmniMedia::Hw {
namespace {
constexpr unsigned inputSlots = 4, frameSlots = 8;
constexpr size_t inputBytes = 8u << 20;
size_t align16k(size_t v) { return (v + 0x3fffu) & ~size_t(0x3fffu); }

// CPUs the calling thread may run on (low 64 bits), 0 if unknown. OpenNOW-PS5
// found that QueryDecoderMemoryInfo refuses a worker mask outside them.
uint64_t threadCpus()
{
#ifdef __PROSPERO__
    cpuset_t set {};
    if (cpuset_getaffinity(CPU_LEVEL_WHICH, CPU_WHICH_TID, -1, sizeof(uint64_t), &set)) return 0;
    uint64_t mask = 0; memcpy(&mask, &set, sizeof mask); return mask;
#else
    return 0x1fff;
#endif
}

struct Api {
    PFN_QueryComputeMemoryInfo QueryComputeMemoryInfo = nullptr;
    PFN_AllocateComputeQueue AllocateComputeQueue = nullptr;
    PFN_ReleaseComputeQueue ReleaseComputeQueue = nullptr;
    PFN_QueryDecoderMemoryInfo QueryDecoderMemoryInfo = nullptr;
    PFN_CreateDecoder CreateDecoder = nullptr;
    PFN_DeleteDecoder DeleteDecoder = nullptr;
    PFN_Reset Reset = nullptr;
    PFN_Decode Decode = nullptr;
    PFN_Flush Flush = nullptr;
} api;
std::once_flag initOnce;
int initResult = -1;
std::string initDetail = "not initialized";
std::mutex queueLock;
void* queue = nullptr;
void* queueMem = nullptr; size_t queueMemSize = 0; int64_t queueMemStart = -1;
bool queueReleased = false; // released for app exit; never allocate again

void cacheFlush(const void* p, size_t n)
{
#if defined(__x86_64__)
    const uint8_t* b = reinterpret_cast<const uint8_t*>(uintptr_t(p) & ~uintptr_t(63));
    for (const uint8_t* e = static_cast<const uint8_t*>(p) + n; b < e; b += 64) __builtin_ia32_clflush(b);
    __builtin_ia32_mfence();
#else
    (void)p; (void)n;
#endif
}

// Allocate a compute queue on a given pipe/queue slot. Queues are never
// released (releasing and re-allocating hung on the console).
int allocQueue(uint16_t pipe, uint16_t slot, void** out)
{
    SceVideodec2ComputeMemoryInfo cm; memset(&cm, 0, sizeof cm); cm.size = sizeof cm;
    int rc = api.QueryComputeMemoryInfo(&cm);
    if (rc) return rc;
    size_t size = align16k(cm.cpu_gpu_size);
    int64_t start = -1; void* addr = nullptr;
    rc = sceKernelAllocateDirectMemory(0, sceKernelGetDirectMemorySize(), size, 0x4000, 12, &start);
    if (rc) return rc;
    rc = sceKernelMapDirectMemory(&addr, size, 0x33, 0, start, 0x4000);
    if (rc || !addr) { sceKernelReleaseDirectMemory(start, size); return rc ? rc : -1; }
    cm.cpu_gpu = addr; cm.cpu_gpu_size = size;
    SceVideodec2ComputeConfigInfo cc; memset(&cc, 0, sizeof cc); cc.size = sizeof cc;
    cc.pipe_id = pipe; cc.queue_id = slot;
    rc = api.AllocateComputeQueue(&cc, &cm, out);
    if (rc || !*out) { *out = nullptr; sceKernelMunmap(addr, size); sceKernelReleaseDirectMemory(start, size); return rc ? rc : -1; }
    queueMem = addr; queueMemSize = size; queueMemStart = start;
    return 0;
}

// Once per process; the queue is never released (see header).
int ensureQueue()
{
    std::lock_guard<std::mutex> lock(queueLock);
    if (queue) return 0;
    if (queueReleased) return -1;
    int rc = allocQueue(0, 0, &queue);
    fprintf(stderr, "OMNI HW BACKEND: compute queue pipe 0 queue 0 -> 0x%08x (%p)\n", unsigned(rc), queue);
    return rc;
}

// Minimal decoder configuration for a capability query.
SceVideodec2DecoderConfigInfo probeConfig(uint32_t codecType, uint32_t profile, uint32_t level, int w, int h, void* q)
{
    SceVideodec2DecoderConfigInfo c; memset(&c, 0, sizeof c);
    c.size = sizeof c; c.resource_type = SCE_VIDEODEC2_RESOURCE_COMPUTE;
    c.codec_type = codecType; c.profile = profile; c.max_level = level;
    c.max_width = w; c.max_height = h; c.max_dpb_frames = SCE_VIDEODEC2_AUTO_FRAMES; c.pipeline_depth = 4;
    c.compute_queue = reinterpret_cast<uint64_t>(q); c.cpu_affinity = 0x3f; c.cpu_priority = 700; c.optimize_progressive = 1;
    return c;
}

// --- Diagnostics (v58) -------------------------------------------------------
// /data/omni/hw-decode-mode.txt: "lazy" (default) or "timeline <delayMs> <periodMs>".
// Timeline allocates the compute queue <delayMs> after startup from the service
// thread and re-checks QueryDecoderMemoryInfo every <periodMs>, logging each
// change with free flexible memory and the process thread count, so the step
// of Omni's startup that makes the decoder refuse can be located.
struct Diag { bool preload = false, vmwatch = false; int lastThreads = 0; bool timeline = false; int delayMs = 0, periodMs = 500; bool queueTried = false; int lastRc = 1; double lastQuery = 0, lastBeat = 0; } diag;

void readMode()
{
    // Words, any order: "timeline <delayMs> <periodMs>", "preload", "vmwatch".
    if (FILE* f = fopen("/data/omni/hw-decode-mode.txt", "r")) {
        char word[32] = {};
        while (fscanf(f, "%31s", word) == 1) {
            if (!strcmp(word, "timeline")) {
                int d = 0, per = 500;
                if (fscanf(f, "%d %d", &d, &per) < 1) d = 0;
                diag.timeline = true; diag.delayMs = d < 0 ? 0 : d; diag.periodMs = per < 50 ? 50 : per;
            } else if (!strcmp(word, "preload")) diag.preload = true;
            else if (!strcmp(word, "vmwatch")) diag.vmwatch = true;
        }
        fclose(f);
    }
}

size_t flexibleKiB()
{
#ifdef __PROSPERO__
    size_t f = 0;
    if (sceKernelAvailableFlexibleMemorySize(&f)) return 0;
    return f >> 10;
#else
    return 0;
#endif
}

int threadCount()
{
#ifdef __PROSPERO__
    // KERN_PROC_INC_THREAD is refused (ENOENT) on the console; the process record
    // works (1096 bytes there, the SDK's 1088 plus a tail) and ki_numthreads is
    // at the SDK offset (console-checked: 6 for main + 5 threads).
    int mib[4] = { CTL_KERN, KERN_PROC, KERN_PROC_PID, int(getpid()) };
    std::vector<uint8_t> buf(sizeof(kinfo_proc) + 4096);
    size_t len = buf.size();
    if (sysctl(mib, 4, buf.data(), &len, nullptr, 0) || len < sizeof(kinfo_proc)) return -1;
    kinfo_proc kp; memcpy(&kp, buf.data(), sizeof kp);
    return kp.ki_numthreads;
#else
    return -1;
#endif
}
}

// --- Address-space diagnostics (v59) ------------------------------------------
// The decoder's first Query loads a hidden codec module (libSceVdec*.native.sprx)
// into the module area (0x80000000..0x200000000 on the console). In Omni's UI
// process that load failed with ENOMEM because the address space was full, and
// thread creation failed with EAGAIN the same way. dumpVm() writes the whole map
// to /data/omni/run/vmmap-<pid>-<tag>.txt and logs a one-line summary.
struct VmInfo { void* start; void* end; int64_t offset; int32_t prot, type; uint8_t flags; char name[32]; };
static_assert(sizeof(VmInfo) == 72, "SceKernelVirtualQueryInfo is 72 bytes on the console");
}
extern "C" int sceKernelVirtualQuery(const void*, int, OmniMedia::Hw::VmInfo*, size_t);
namespace OmniMedia::Hw {
namespace {
void dumpVm(const char* tag)
{
#ifdef __PROSPERO__
    mkdir("/data/omni/run", 0777);
    char path[128];
    snprintf(path, sizeof path, "/data/omni/run/vmmap-%d-%s.txt", int(getpid()), tag);
    FILE* f = fopen(path, "w");
    struct Area { const char* name; uintptr_t lo, hi; size_t used = 0, largestGap = 0; uintptr_t cursor; } areas[] = {
        { "low", 0, 0x80000000ull, 0, 0, 0 }, { "modules", 0x80000000ull, 0x200000000ull, 0, 0, 0 },
        { "heap", 0x200000000ull, 0x700000000ull, 0, 0, 0 }, { "stacks", 0x700000000ull, 0x7f0000000ull, 0, 0, 0 },
        { "high", 0x7f0000000ull, 0x10000000000ull, 0, 0, 0 } };
    for (auto& a : areas) a.cursor = a.lo;
    uintptr_t addr = 0; int n = 0; VmInfo q;
    while (n < 200000) {
        memset(&q, 0, sizeof q);
        if (sceKernelVirtualQuery(reinterpret_cast<void*>(addr), 1, &q, sizeof q)) break;
        uintptr_t s = reinterpret_cast<uintptr_t>(q.start), e = reinterpret_cast<uintptr_t>(q.end);
        if (e <= s) break;
        if (f) fprintf(f, "%lx %lx %lu %x %d %02x %.32s\n", (unsigned long)s, (unsigned long)e, (unsigned long)((e - s) >> 10), unsigned(q.prot), q.type, q.flags, q.name);
        for (auto& a : areas) {
            uintptr_t cs = s > a.lo ? s : a.lo, ce = e < a.hi ? e : a.hi;
            if (ce <= cs) continue;
            if (cs > a.cursor && cs - a.cursor > a.largestGap) a.largestGap = cs - a.cursor;
            a.used += ce - cs; a.cursor = ce;
        }
        addr = e; n++;
    }
    for (auto& a : areas) if (a.hi > a.cursor && a.hi - a.cursor > a.largestGap) a.largestGap = a.hi - a.cursor;
    if (f) fclose(f);
    char line[512]; int len = snprintf(line, sizeof line, "OMNI HW VM: %s %d regions (%s);", tag, n, path);
    for (auto& a : areas)
        len += snprintf(line + len, sizeof line - size_t(len), " %s used %zuMiB largest-free %zuMiB;", a.name, a.used >> 20, a.largestGap >> 20);
    fprintf(stderr, "%s flexible=%zuKiB threads=%d\n", line, flexibleKiB(), threadCount());
#else
    (void)tag;
#endif
}

// Load the codec modules now, while the module area still has room, so later
// Queries do not have to (console: after this no Query loads anything new).
void preloadCodecModules()
{
    const char* names[] = { "libSceVdecSavc2.native.sprx", "libSceVdecShevc.native.sprx", "libSceVdecSvp9.native.sprx" };
    char line[256]; int len = snprintf(line, sizeof line, "OMNI HW BACKEND: codec modules");
    for (const char* n : names) {
        void* h = dlopen(n, RTLD_LAZY | RTLD_GLOBAL);
        len += snprintf(line + len, sizeof line - size_t(len), " %s=%s", n + 10, h ? "ok" : "FAILED");
    }
    fprintf(stderr, "%s\n", line);
}
}

bool backendQueueReady()   // OMNI_PERF_B_V5
{
    std::lock_guard<std::mutex> lock(queueLock);
    return queue != nullptr && !queueReleased;
}

void backendDiagnosticTick(double sinceStartMs)
{
    // vmwatch: one address-space map per thread count, so the last file before a
    // thread-creation failure shows what had run out.
    if (diag.vmwatch && sinceStartMs < 120000) {
        int n = threadCount();
        if (n > 0 && n != diag.lastThreads) {
            diag.lastThreads = n;
            char tag[32]; snprintf(tag, sizeof tag, "threads-%02d", n);
            dumpVm(tag);
        }
    }
    if (!diag.timeline || !backendAvailable() || sinceStartMs > 180000) return;
    if (sinceStartMs < diag.delayMs) return;
    if (!diag.queueTried) {
        diag.queueTried = true;
        size_t before = flexibleKiB(); int threads = threadCount();
        int rc = ensureQueue();
        fprintf(stderr, "OMNI HW TIMELINE: t=%.0fms queue -> 0x%08x flexible %zu->%zuKiB threads=%d\n",
                sinceStartMs, unsigned(rc), before, flexibleKiB(), threads);
    }
    if (!queue || sinceStartMs - diag.lastQuery < diag.periodMs) return;
    diag.lastQuery = sinceStartMs;
    SceVideodec2DecoderConfigInfo c = probeConfig(SCE_VIDEODEC2_CODEC_AVC, 100, 51, 1280, 736, queue);
    SceVideodec2DecoderMemoryInfo m; memset(&m, 0, sizeof m); m.size = sizeof m;
    int rc = api.QueryDecoderMemoryInfo(&c, &m);
    if (rc != diag.lastRc || sinceStartMs - diag.lastBeat >= 5000) {
        fprintf(stderr, "OMNI HW TIMELINE: t=%.0fms query avc 1280x736 -> 0x%08x%s flexible=%zuKiB threads=%d threadCpus=0x%llx\n",
                sinceStartMs, unsigned(rc), rc != diag.lastRc ? " (changed)" : "", flexibleKiB(), threadCount(),
                (unsigned long long)threadCpus());
        if (rc && rc != diag.lastRc) dumpVm("timeline-fail");
        diag.lastRc = rc; diag.lastBeat = sinceStartMs;
    }
}

int backendInitialize(std::string& detail)
{
    std::call_once(initOnce, [] {
        int sm = sceSysmoduleLoadModule(SCE_SYSMODULE_VIDEODEC2);
        if (sm) { initResult = sm; initDetail = "sceSysmoduleLoadModule(207) refused"; return; }
        dlopen("libSceAgcDriver.sprx", RTLD_LAZY); // libSceVideodec2's GPU imports
        dlopen("libSceAgc.sprx", RTLD_LAZY);
        void* lib = dlopen("libSceVideodec2.sprx", RTLD_LAZY);
        if (!lib) { initResult = -1; initDetail = "dlopen libSceVideodec2 failed"; return; }
#define SYM(n) if (!(*reinterpret_cast<void**>(&api.n) = dlsym(lib, "sceVideodec2" #n))) { initResult = -2; initDetail = "missing sceVideodec2" #n; return; }
        SYM(QueryComputeMemoryInfo) SYM(AllocateComputeQueue) SYM(ReleaseComputeQueue) SYM(QueryDecoderMemoryInfo)
        SYM(CreateDecoder) SYM(DeleteDecoder) SYM(Reset) SYM(Decode) SYM(Flush)
#undef SYM
        initResult = 0; initDetail = "ok";
        readMode();
        if (diag.preload) preloadCodecModules();
        fprintf(stderr, "OMNI HW BACKEND: mode %s%s%s (delay %d ms, period %d ms) flexible=%zuKiB threads=%d\n",
                diag.timeline ? "timeline" : "lazy", diag.preload ? " preload" : "", diag.vmwatch ? " vmwatch" : "",
                diag.delayMs, diag.periodMs, flexibleKiB(), threadCount());
        dumpVm("startup");
    });
    detail = initDetail;
    return initResult;
}

bool backendAvailable() { return initResult == 0; }

// ---- OMNI_DECODER_MEMORY_REPORT_V1 (see OmniHwBackend.h) ----------------------------------
}
#ifdef __PROSPERO__
extern "C" int sceKernelAvailableDirectMemorySize(int64_t, int64_t, size_t, int64_t*, size_t*);
#endif
namespace OmniMedia::Hw {
namespace {
bool memoryReportAgain = false;   // the queries needed a compute queue: again at the first open
double mib(double bytes) { return bytes / 1048576; }
}

bool backendMemoryReportWanted()
{
    if (const char* env = getenv("OMNI_DECODER_MEMORY_REPORT")) return env[0] == '1';
#ifdef __PROSPERO__
    return !access("/data/omni/decoder-memory-report.flag", F_OK);
#else
    return false;
#endif
}

void backendMemoryReport(const char* when)
{
    if (!backendAvailable()) return;
    void* q;
    { std::lock_guard<std::mutex> lock(queueLock); q = queue; }
    struct Config { const char* name; uint32_t codec, profile, level; int w, h, depth; };
    // Levels as Omni's open() uses them (AVC x10, HEVC x30, VP9 x10), plus H.264 4.2 and 5.1 at 2160p.
    static const Config configs[] = {
        { "H.264 High L4.2 1080p", SCE_VIDEODEC2_CODEC_AVC, 100, 42, 1920, 1080, 8 },
        { "H.264 High L5.1 1080p (Omni <=1080p)", SCE_VIDEODEC2_CODEC_AVC, 100, 51, 1920, 1080, 8 },
        { "H.264 High L5.1 2160p", SCE_VIDEODEC2_CODEC_AVC, 100, 51, 3840, 2160, 8 },
        { "H.264 High L5.2 2160p (Omni >1080p)", SCE_VIDEODEC2_CODEC_AVC, 100, 52, 3840, 2160, 8 },
        { "HEVC Main L4.1 1080p (Omni <=1080p)", SCE_VIDEODEC2_CODEC_HEVC, 1, 123, 1920, 1080, 8 },
        { "HEVC Main L5.1 2160p (Omni >1080p)", SCE_VIDEODEC2_CODEC_HEVC, 1, 153, 3840, 2160, 8 },
        { "HEVC Main10 L5.1 2160p (Omni >1080p)", SCE_VIDEODEC2_CODEC_HEVC, 2, 153, 3840, 2160, 10 },
        { "VP9 P0 L5.1 2160p (Omni >1080p)", SCE_VIDEODEC2_CODEC_VP9, 0, 51, 3840, 2160, 8 },
        { "VP9 P2 L5.1 2160p", SCE_VIDEODEC2_CODEC_VP9, 2, 51, 3840, 2160, 10 },
        { "VP9 P2 L4.1 2160p (Omni 10-bit)", SCE_VIDEODEC2_CODEC_VP9, 2, 41, 3840, 2160, 10 },
    };
    fprintf(stderr, "OMNI HW MEMORY: report at %s: QueryDecoderMemoryInfo only (compute queue: %s); "
        "\"opened by Omni\" = what Backend::open would allocate: flexible = cpu_size, direct = gpu_size + cpu_gpu_size + %u output frames + %u x %zu MiB input\n",
        when, q ? "the one in use" : "none allocated yet, queries without one", frameSlots, inputSlots, inputBytes >> 20);
    unsigned refused = 0;
    for (const auto& k : configs) {
        SceVideodec2DecoderConfigInfo c = probeConfig(k.codec, k.profile, k.level, (k.w + 15) & ~15, (k.h + 31) & ~31, q);
        c.pipeline_depth = k.depth > 8 ? 1 : 4;   // as Backend::open
        SceVideodec2DecoderMemoryInfo m; memset(&m, 0, sizeof m); m.size = sizeof m;
        const int rc = api.QueryDecoderMemoryInfo(&c, &m);
        if (rc) {
            ++refused;
            fprintf(stderr, "OMNI HW MEMORY: %-38s %dx%d codec=%u profile=%u level=%u pipeline=%u -> 0x%08x (refused)\n",
                k.name, c.max_width, c.max_height, c.codec_type, c.profile, c.max_level, c.pipeline_depth, unsigned(rc));
            continue;
        }
        const size_t frame = align16k(m.max_frame_size);
        const size_t direct = align16k(m.gpu_size) + align16k(m.cpu_gpu_size) + size_t(frameSlots) * frame + size_t(inputSlots) * inputBytes;
        fprintf(stderr, "OMNI HW MEMORY: %-38s %dx%d pipeline=%u -> ok cpu_size=%.2f MiB gpu_size=%.2f MiB cpu_gpu_size=%.2f MiB max_frame_size=%.2f MiB frame_alignment=%u; opened by Omni: flexible %.1f MiB, direct %.1f MiB (frames %u x %.2f MiB)\n",
            k.name, c.max_width, c.max_height, c.pipeline_depth, mib(double(m.cpu_size)), mib(double(m.gpu_size)), mib(double(m.cpu_gpu_size)),
            mib(double(m.max_frame_size)), m.frame_alignment, mib(double(align16k(m.cpu_size))), mib(double(direct)), frameSlots, mib(double(frame)));
    }
    size_t flexible = 0;
    const bool flexibleKnown = !sceKernelAvailableFlexibleMemorySize(&flexible);
    char largest[48] = "unknown";
#ifdef __PROSPERO__
    int64_t at = 0; size_t block = 0;
    if (!sceKernelAvailableDirectMemorySize(0, sceKernelGetDirectMemorySize(), 0x4000, &at, &block)) snprintf(largest, sizeof largest, "%.1f MiB", mib(double(block)));
#endif
    fprintf(stderr, "OMNI HW MEMORY: process: available flexible %s%.1f MiB, direct memory size %.1f MiB, largest free direct block %s\n",
        flexibleKnown ? "" : "(query failed) ", mib(double(flexible)), mib(double(sceKernelGetDirectMemorySize())), largest);
    if (refused && !q) {
        memoryReportAgain = true;
        fprintf(stderr, "OMNI HW MEMORY: %u quer%s refused without a compute queue: the report runs again when the first stream has allocated one\n",
            refused, refused == 1 ? "y" : "ies");
    }
    fflush(stderr);
}

// App exit: give the compute queue back (EVO's teardown order: decoders first,
// then the queue, then its memory). A process exiting with the queue/decoders
// still held took the whole console down (2026-10-19, second YouTube run).
// `blocking` false (crash handler) never waits for the lock.
int backendReleaseQueue(bool blocking)
{
    std::unique_lock<std::mutex> lock(queueLock, std::defer_lock);
    if (blocking) lock.lock();
    else if (!lock.try_lock()) return -2;
    queueReleased = true;
    if (!queue) return 0;
    int rc = api.ReleaseComputeQueue ? api.ReleaseComputeQueue(queue) : -1;
    queue = nullptr;
    if (!rc && queueMem) {
        sceKernelMunmap(queueMem, queueMemSize);
        sceKernelReleaseDirectMemory(queueMemStart, queueMemSize);
    }
    queueMem = nullptr; queueMemSize = 0; queueMemStart = -1;
    return rc;
}

// OMNI_HOLEPUNCH_V5 (see OmniHwBackend.h)
void* backendDirectAlloc(size_t size, int64_t& start, int* rc, const char** stage)   // OMNI_HOLEPUNCH_V5_REV2: rc, stage
{
    start = -1;
    void* addr = nullptr;
    int r = size ? sceKernelAllocateDirectMemory(0, sceKernelGetDirectMemorySize(), size, 0x4000, 12, &start) : -1;
    if (r) { start = -1; if (rc) *rc = r; if (stage) *stage = "AllocateDirectMemory"; return nullptr; }
    r = sceKernelMapDirectMemory(&addr, size, 0x33, 0, start, 0x4000);
    if (r || !addr) { sceKernelReleaseDirectMemory(start, size); start = -1; if (rc) *rc = r ? r : -1; if (stage) *stage = "MapDirectMemory"; return nullptr; }
    return addr;
}

void backendDirectFree(void* addr, size_t size, int64_t start)
{
    if (addr) sceKernelMunmap(addr, size);
    if (start >= 0) sceKernelReleaseDirectMemory(start, size);
}

size_t backendDirectAvailable()
{
#ifdef __PROSPERO__
    int64_t at = 0; size_t size = 0;
    if (sceKernelAvailableDirectMemorySize(0, sceKernelGetDirectMemorySize(), 0x4000, &at, &size)) return 0;
    return size;
#else
    return 0;
#endif
}

Backend::~Backend() { close(); }

int Backend::allocDirect(Mem& m, size_t size, int prot)
{
    m = {}; m.size = size;
    if (!size) return 0;
    int rc = sceKernelAllocateDirectMemory(0, sceKernelGetDirectMemorySize(), size, 0x4000, 12, &m.start);
    if (rc) { m.start = -1; return rc; }
    rc = sceKernelMapDirectMemory(&m.addr, size, prot, 0, m.start, 0x4000);
    if (rc || !m.addr) { sceKernelReleaseDirectMemory(m.start, size); m = {}; return rc ? rc : -1; }
    return 0;
}

void Backend::freeDirect(Mem& m)
{
    if (m.addr) sceKernelMunmap(m.addr, m.size);
    if (m.start >= 0) sceKernelReleaseDirectMemory(m.start, m.size);
    m = {};
}

int Backend::open(Codec codec, int profile, int depth, int w, int h, std::string& stage)
{
    stage = "close previous";
    if (int rc = close()) return rc;
    stage = "module";
    if (!backendAvailable()) return -1;
    if (w <= 0 || h <= 0 || w > 4096 || h > 2304) { stage = "dimensions"; return -1; }
    stage = "compute queue";
    if (int rc = ensureQueue()) return rc;
    if (memoryReportAgain) { memoryReportAgain = false; backendMemoryReport("first stream open (compute queue allocated)"); } // OMNI_DECODER_MEMORY_REPORT_V1
    // EVO's hardware-verified values: AVC level x10, HEVC x30, VP9 x10.
    SceVideodec2DecoderConfigInfo c; memset(&c, 0, sizeof c);
    c.size = sizeof c;
    c.resource_type = SCE_VIDEODEC2_RESOURCE_COMPUTE;
    const bool big = w > 1920 || h > 1088;
    switch (codec) {
    case Codec::H264: c.codec_type = SCE_VIDEODEC2_CODEC_AVC; c.profile = 100; c.max_level = big ? 52 : 51; break;
    case Codec::HEVC: c.codec_type = SCE_VIDEODEC2_CODEC_HEVC; c.profile = depth > 8 ? 2 : 1; c.max_level = big ? 153 : 123; break;
    case Codec::VP9: c.codec_type = SCE_VIDEODEC2_CODEC_VP9; c.profile = depth > 8 ? 2 : 0; c.max_level = (big && depth == 8) ? 51 : 41; break;
    }
    (void)profile;
    c.max_width = (w + 15) & ~15; c.max_height = (h + 31) & ~31;
    c.max_dpb_frames = SCE_VIDEODEC2_AUTO_FRAMES;
    c.pipeline_depth = depth > 8 ? 1 : 4;
    c.compute_queue = reinterpret_cast<uint64_t>(queue);
    c.cpu_affinity = 0x3f; c.cpu_priority = 700; c.optimize_progressive = 1;

    SceVideodec2DecoderMemoryInfo m; memset(&m, 0, sizeof m); m.size = sizeof m;
    stage = "QueryDecoderMemoryInfo";
    fprintf(stderr, "OMNI HW BACKEND: open %dx%d %d-bit codec %d queue=%p flexible=%zuKiB threads=%d\n",
            w, h, depth, int(codec), queue, flexibleKiB(), threadCount());
    // The first configuration is the console-verified one (vdec probe). If a
    // process refuses it (seen in Omni's UI process: 0x811d0200), try variants
    // in order and log each, keeping the first the decoder accepts.
    const uint64_t cpus = threadCpus();
    struct Variant { uint64_t affinity; int32_t dpb; uint32_t depth; const char* why; };
    const Variant variants[] = {
        { 0x3f, SCE_VIDEODEC2_AUTO_FRAMES, c.pipeline_depth, "verified" },
        { cpus & 0x1fff, SCE_VIDEODEC2_AUTO_FRAMES, c.pipeline_depth, "thread cpus" },
        { 0x3f, codec == Codec::H264 ? 4 : 6, c.pipeline_depth, "explicit dpb" },
        { 0x3f, SCE_VIDEODEC2_AUTO_FRAMES, 1, "depth 1" },
        { cpus & 0x1fff, codec == Codec::H264 ? 4 : 6, 1, "thread cpus, dpb, depth 1" },
    };
    int rc = -1;
    for (const auto& v : variants) {
        if (!v.affinity) continue;
        c.cpu_affinity = v.affinity; c.max_dpb_frames = v.dpb; c.pipeline_depth = v.depth;
        memset(&m, 0, sizeof m); m.size = sizeof m;
        rc = api.QueryDecoderMemoryInfo(&c, &m);
        fprintf(stderr, "OMNI HW BACKEND: QueryDecoderMemoryInfo %s affinity=0x%llx dpb=%d depth=%u codec=%u profile=%u level=%u %dx%d threadCpus=0x%llx -> 0x%08x\n",
                v.why, (unsigned long long)c.cpu_affinity, c.max_dpb_frames, c.pipeline_depth, c.codec_type, c.profile,
                c.max_level, c.max_width, c.max_height, (unsigned long long)cpus, unsigned(rc));
        if (!rc) break;
    }
    if (rc) {
        // Seen in Omni's UI process: the codec module could not be loaded on demand
        // (rtld load_prx ENOMEM, address space full). Record the address space.
        dumpVm("query-fail");
        return rc;
    }
    frameSize_ = align16k(m.max_frame_size);
    if (!frameSize_ || m.frame_alignment > 0x4000) { stage = "memory info"; return -1; }
    if (m.cpu_size) {
        cpuSize_ = align16k(m.cpu_size);
        stage = "MapNamedFlexibleMemory";
        if (int rc = sceKernelMapNamedFlexibleMemory(&cpu_, cpuSize_, 0x03, 0, "OmniHwDecoder")) { cpu_ = nullptr; cpuSize_ = 0; return rc; }
    }
    m.cpu = cpu_; m.cpu_size = cpuSize_;
    stage = "alloc(gpu)";     if (int rc = allocDirect(gpu_, align16k(m.gpu_size), 0x33)) { close(); return rc; }
    stage = "alloc(cpu_gpu)"; if (int rc = allocDirect(cpuGpu_, align16k(m.cpu_gpu_size), 0x33)) { close(); return rc; }
    stage = "alloc(input)";   if (int rc = allocDirect(input_, inputBytes * inputSlots, 0x33)) { close(); return rc; }
    stage = "alloc(frames)";  if (int rc = allocDirect(frames_, frameSize_ * frameSlots, 0x33)) { close(); return rc; }
    m.gpu = gpu_.addr; m.gpu_size = gpu_.size; m.cpu_gpu = cpuGpu_.addr; m.cpu_gpu_size = cpuGpu_.size;
    stage = "CreateDecoder";
    if (int rc = api.CreateDecoder(&c, &m, &decoder_)) { decoder_ = nullptr; close(); return rc; }
    if (!decoder_) { close(); return -1; }
    stage = "Reset";
    if (int rc = api.Reset(decoder_)) { close(); return rc; }
    codec_ = codec; width_ = w; height_ = h; bitDepth_ = depth; ring_ = 0;
    stage = "ok";
    return 0;
}

bool Backend::fill(const void* raw, Picture& p)
{
    auto* o = static_cast<const SceVideodec2OutputInfo*>(raw);
    const uint8_t* base = static_cast<const uint8_t*>(frames_.addr);
    const uint8_t* buf = static_cast<const uint8_t*>(o->buffer);
    const size_t bps = bitDepth_ > 8 ? 2 : 1;
    const size_t pitch = o->pitch_bytes ? o->pitch_bytes : size_t(o->pitch) * bps;
    const size_t need = pitch * o->height * 3 / 2;
    if (buf < base || buf + need > base + frames_.size || o->buffer_size < need
        || o->width < uint32_t(width_) || o->height < uint32_t(height_) || pitch < size_t(width_) * bps)
        return false;
    cacheFlush(buf, need);
    p.data = buf; p.size = need; p.width = o->width; p.codedHeight = o->height;
    p.pitchBytes = uint32_t(pitch); p.bitDepth = uint32_t(bitDepth_); p.notDisplayed = o->not_displayed;
    return true;
}

int Backend::decode(const uint8_t* au, size_t size, uint64_t pts, Picture& p, bool& got)
{
    got = false; p = {};
    if (!decoder_) return -1;
    if (!au || !size || size > inputBytes) return -2;
    uint8_t* slot = static_cast<uint8_t*>(input_.addr) + size_t(ring_ % inputSlots) * inputBytes;
    memcpy(slot, au, size);
    cacheFlush(slot, size);
    SceVideodec2InputData in; SceVideodec2FrameBuffer fb; SceVideodec2OutputInfo out;
    memset(&in, 0, sizeof in); memset(&fb, 0, sizeof fb); memset(&out, 0, sizeof out);
    in.size = sizeof in; in.au = slot; in.au_size = size; in.pts = pts; in.dts = UINT64_MAX;
    fb.size = sizeof fb; fb.buffer = static_cast<uint8_t*>(frames_.addr) + size_t(ring_ % frameSlots) * frameSize_;
    fb.buffer_size = frameSize_; out.size = sizeof out;
    ring_++;
    int rc = api.Decode(decoder_, &in, &fb, &out);
    if (rc) return rc;
    if (out.valid && out.picture_count) {
        if (!fill(&out, p)) return -3;
        got = true;
    }
    return 0;
}

int Backend::flushOne(Picture& p, bool& got)
{
    got = false; p = {};
    if (!decoder_) return -1;
    SceVideodec2FrameBuffer fb; SceVideodec2OutputInfo out;
    memset(&fb, 0, sizeof fb); memset(&out, 0, sizeof out);
    fb.size = sizeof fb; fb.buffer = static_cast<uint8_t*>(frames_.addr) + size_t(ring_ % frameSlots) * frameSize_;
    fb.buffer_size = frameSize_; out.size = sizeof out;
    ring_++;
    int rc = api.Flush(decoder_, &fb, &out);
    if (rc) return rc;
    if (out.valid && out.picture_count) {
        if (!fill(&out, p)) return -3;
        got = true;
    }
    return 0;
}

int Backend::reset()
{
    if (!decoder_) return -1;
    ring_ = 0;
    return api.Reset(decoder_);
}

int Backend::close()
{
    if (decoder_) {
        if (int rc = api.DeleteDecoder(decoder_)) return rc; // keep memory mapped if it refuses
        decoder_ = nullptr;
    }
    freeDirect(frames_); freeDirect(input_); freeDirect(cpuGpu_); freeDirect(gpu_);
    if (cpu_) { sceKernelMunmap(cpu_, cpuSize_); cpu_ = nullptr; cpuSize_ = 0; }
    frameSize_ = 0;
    return 0;
}

}
