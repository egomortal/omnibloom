#include "OmniDiagnosticMode.h"
// SPDX-License-Identifier: GPL-3.0-or-later
#include "OmniHwService.h"
#include "OmniCpuPixelBuffer.h"
#include "OmniFrameCadence.h" // V9: timestamp quantization hysteresis
#include "OmniHwBackend.h"
#include "OmniHwBitstream.h" // OMNI_HOLEPUNCH_COLOUR_V1: colourMatrix
#include "OmniHwPlatform.h"
#include "OmniHwProtocol.h"
#include <atomic>
#include <cerrno>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <deque>
#include <condition_variable> // OMNI_HOLEPUNCH_V7_REV2: the log writer
#include <string>
#include <thread>
#include <algorithm> // OMNI_HOLEPUNCH_V1
#include <cmath>     // OMNI_HOLEPUNCH_V4
#include <memory>
#include <mutex>
#include <map>       // OMNI_HOLEPUNCH_V5
#define OMNI_HOLE_V5_QUEUE 1 // OMNI_HOLEPUNCH_V5: this file has its decoded-picture queue (the decoder memory report reads the budget)
#include <fcntl.h>
#include <poll.h>
#include <pthread.h>
#include <csignal>  // OMNI_HOLEPUNCH_V7_REFLIP: the stall stack sample
#include <sched.h>  // OMNI_HOLEPUNCH_V7_REFLIP: thread priorities and CPUs (logged), sched_yield
#ifdef __PROSPERO__
#include <pthread_np.h>
#include <sys/cpuset.h>
#endif
#include <dlfcn.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/resource.h>
#include <vector>
#include <functional> // OMNI_FAST_UPSCALE_V2
#include <immintrin.h> // OMNI_HOLEPUNCH_MIX_SIMD_V1
#ifndef OMNI_HW_NO_SWSCALE
extern "C" {
#include <libswscale/swscale.h>
#include <libavutil/frame.h>   // OMNI_SWS_BANDS_V1
#include <libavutil/buffer.h>
}
#endif

extern "C" int omniHDRFormatPQ(); // OMNI_HDR_PORT_V1
extern "C" int omniHDRPQAvailable();   // OMNI_HDR_AUTO_V1 (OmniMain10Bridge.cpp)
extern "C" int omniHDRConvert10(const uint16_t*,size_t,size_t,const uint16_t*,size_t,size_t,const uint16_t*,size_t,size_t,int,int,uint32_t*,size_t,size_t,uint32_t);
extern "C" int omniSDLDirectTileHDR(const void*,int,int,int,const void*,int,const uint32_t*,size_t,const uint32_t*,const uint32_t*,size_t,int) __attribute__((weak));
extern "C" int omniMain10SdrConvert(const uint16_t*,size_t,size_t,const uint16_t*,size_t,size_t,const uint16_t*,size_t,size_t,int,int,uint32_t*,size_t,size_t,uint32_t,int);
extern "C" int omniSDLDirectTile(const void*,int,int,int,const void*,int,const uint32_t*,size_t,const uint32_t*,const uint32_t*,size_t,int) __attribute__((weak));
extern "C" void omniPipelineScope(int, long long, long long, long long) __attribute__((weak));
struct OmniServiceTraceScope {
 long long kind, detail;
 OmniServiceTraceScope(long long k, long long d=0):kind(k),detail(d) { if(omniPipelineScope) omniPipelineScope(40,kind,detail,0); }
 ~OmniServiceTraceScope() { if(omniPipelineScope) omniPipelineScope(41,kind,detail,0); }
};
// OMNI_FAST_PAGE_V1: canvas pixels per page view pixel (2 when the page is painted at half resolution).
static std::atomic<double> omniHoleViewScale { 1.0 };
namespace OmniMedia::Hw {
namespace {
struct TraceRecord { int64_t timeUs,event,a,b,c,d; };
constexpr unsigned traceCapacity=524288;
TraceRecord traceRecords[traceCapacity];
std::atomic<bool> traceReady[traceCapacity] {};
std::atomic<unsigned> traceNext {0};
std::atomic<bool> traceEnabled {false};
bool enduranceTrace = false;
bool compactEnduranceTrace = false;
std::atomic<int> compactDirectState{-1}, compactFastState{-1};
bool focusTrace = false;
std::atomic<bool> focusActive {false};
// Diagnostic only: retain detail around the 23 unresolved historical media positions.
// No rolling global detail buffer; two seconds of context on each side captures
// clock delivery before selection. Event 33 advances this switch once per frame.
constexpr int64_t focusWindows[][2] = {{0,12000000}, {21000000,25000000}, {31000000,33000000},{51133000,55633000},{70033000,74033000},{190033000,197883000},{334000000,338000000},{442567000,449050000},{453783000,458017000},{478000000,482000000},{516783000,520783000}};
bool focusContains(int64_t pts) {
 for (auto& w : focusWindows) if (pts>=w[0] && pts<=w[1]) return true;
 return false;
}

}
void diagnosticTraceStart() { compactEnduranceTrace = !access("/data/omni/media-thirty-minute-selftest.flag",F_OK); focusTrace = !access("/data/omni/presentation-focus-selftest.flag",F_OK); enduranceTrace = !access("/data/omni/media-endurance-selftest.flag",F_OK); if (!access("/data/omni/pipeline-trace.flag",F_OK) && access("/data/omni/pipeline-trace-disabled.flag",F_OK)) { traceEnabled.store(true); diagnosticTrace(1,getpid(),traceCapacity); } }
void diagnosticTrace(int64_t event,int64_t a,int64_t b,int64_t c,int64_t d) {
 if (!traceEnabled.load(std::memory_order_relaxed)) return;
 // Outside these windows retain exactly the previous endurance event subset.
 if (focusTrace && event==33) {
  bool active=focusContains(a);
  if (focusActive.exchange(active,std::memory_order_relaxed)!=active)
   diagnosticTrace(140,active,a,b,0);
 }
 const bool focused=focusTrace && focusActive.load(std::memory_order_relaxed);
 const bool focusDetail=focused && (event==5 || event==6 || event==8 ||
     event==20 || event==24 || event==25 || event==88 || event==89 ||
     event==90 || event==91 || event==95 || event==110 || event==117 ||
     event==118 || (event>=122 && event<=125) || (event>=141 && event<=149) ||
     ((event==40 || event==41) && a==70));
 // Ten-minute validation retains every submit/completion and direct-use marker,
 // without overflowing the fixed trace buffer with unrelated callback scopes.
 // Short comparisons retain the complete original trace schema and capacity.
 if (compactEnduranceTrace) {
   // Existing bounded 30-minute research trace: retain every completed flip and
   // prepared identity; preserve path transitions without filling the buffer.
   if (event==130 && compactDirectState.exchange(int(b))==int(b)) return;
   if (event==164 && compactFastState.exchange(int(b))==int(b)) return;
   if (!(event==1 || event==7 || event==21 || event==23 || event==33 || event==130 || event==131 || event==144 || event==164 || (event==41 && a==71))) return;
 } else if ((enduranceTrace || focusTrace) && !focusDetail && event!=140 && !(event==1 || event==7 || event==21 || event==22 ||
     event==23 || event==33 || event==130 || event==131 ||
     ((event==40 || event==41) && (a==71 || a==72)))) return;
 unsigned i=traceNext.fetch_add(1,std::memory_order_relaxed); if(i>=traceCapacity)return;
 timespec ts;clock_gettime(CLOCK_MONOTONIC,&ts);
 traceRecords[i]={int64_t(ts.tv_sec)*1000000+ts.tv_nsec/1000,event,a,b,c,d};
 traceReady[i].store(true,std::memory_order_release);
}
void diagnosticTraceDump() {
 if(!traceEnabled.exchange(false))return;
 unsigned n=traceNext.load();char path[128];snprintf(path,sizeof path,"/data/omni/pipeline-trace-%d.bin",int(getpid()));
 FILE* f=fopen(path,"wb");if(!f)return;
 TraceRecord h={0,0,n,n>traceCapacity?n-traceCapacity:0,traceCapacity,sizeof(TraceRecord)};fwrite(&h,sizeof h,1,f);
 for(unsigned i=0;i<std::min(n,traceCapacity);++i)if(traceReady[i].load(std::memory_order_acquire))fwrite(&traceRecords[i],sizeof(TraceRecord),1,f);
 fclose(f);
}
namespace {
using Wire::Message;
using Wire::Type;

// ---- OMNI_HOLEPUNCH_V7_REV2: log lines off the service, presenter and main threads ------------
// Console v92: a line on stderr took up to 200 ms (logLineMaxMs=200.9; the shell's log() fsyncs
// the same file), and V7 wrote 5-6 lines per pacing window from the service thread: blocked for
// ~1.2 s, it sent no pacing report and the player's 1 s safety net turned pacing off (with the
// kill switch too: the lines were written either way). With V7 on, every line of this file goes
// into a queue (64 lines; more are counted and dropped, never waited for) and one writer thread
// puts it on fd 2 with write(2), holding no stdio lock while the sink is slow. The writer starts
// at the first line and inherits that thread's scheduling (never above the UI main thread's).
// V7 off: v90's fprintf on the calling thread, unchanged.
bool v7On();
struct V7Log {
    std::mutex lock;
    std::condition_variable wake, idle;
    std::deque<std::pair<int64_t, std::string>> queue;   // (queued at, us; the line with its newline)
    bool started = false, writing = false;
    unsigned dropped = 0;
    std::atomic<int64_t> writeMaxUs { 0 }, lagMaxUs { 0 };
    std::atomic<unsigned> lines { 0 }, droppedWindow { 0 };
    std::atomic<uint64_t> bytes { 0 };
};
V7Log& v7Log() { static V7Log* log = new V7Log; return *log; }   // never destroyed: the writer may outlive exit's destructors
int64_t v7MonoUs() { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return int64_t(t.tv_sec) * 1000000 + t.tv_nsec / 1000; }
void v7AtomicMax(std::atomic<int64_t>& a, int64_t v) { int64_t seen = a.load(std::memory_order_relaxed); while (v > seen && !a.compare_exchange_weak(seen, v, std::memory_order_relaxed)) { } }
void v7WriteAll(const char* p, size_t n)
{
    while (n) {
        const ssize_t w = write(fileno(stderr), p, n); // OMNI_V7_LOGFD_FIX: OmniMain freopen()s stderr onto the per-process log, which need not be fd 2
        if (w < 0) { if (errno == EINTR) continue; return; }
        p += w; n -= size_t(w);
    }
}
void v7LogMain()
{
    V7Log& log = v7Log();
    for (;;) {
        std::pair<int64_t, std::string> line; unsigned dropped;
        {
            std::unique_lock<std::mutex> l(log.lock);
            log.writing = false;
            if (log.queue.empty()) log.idle.notify_all();
            log.wake.wait(l, [&] { return !log.queue.empty() || log.dropped; });
            dropped = log.dropped; log.dropped = 0;
            if (!log.queue.empty()) { line = std::move(log.queue.front()); log.queue.pop_front(); }
            log.writing = true;
        }
        if (dropped) {
            char text[128];
            const int n = snprintf(text, sizeof text, "OMNI HOLEPUNCH: %u log line(s) dropped (the log was slower than the lines)\n", dropped);
            v7WriteAll(text, size_t(std::max(0, n)));
            log.droppedWindow.fetch_add(dropped, std::memory_order_relaxed);
        }
        if (line.second.empty()) continue;
        const int64_t from = v7MonoUs();
        v7WriteAll(line.second.data(), line.second.size());
        const int64_t to = v7MonoUs();
        v7AtomicMax(log.writeMaxUs, to - from); v7AtomicMax(log.lagMaxUs, to - line.first);
        log.lines.fetch_add(1, std::memory_order_relaxed); log.bytes.fetch_add(line.second.size(), std::memory_order_relaxed);
    }
}
void v7LogPush(std::string&& line)
{
    V7Log& log = v7Log();
    bool start = false;
    {
        std::lock_guard<std::mutex> l(log.lock);
        if (log.queue.size() >= 64) ++log.dropped;
        else log.queue.emplace_back(v7MonoUs(), std::move(line));
        start = !log.started; log.started = true;
    }
    if (start) {
        pthread_t writer; // OMNI_V7_NOEXCEPT_FIX: this build has no C++ exceptions, so no std::thread/try here
        if (pthread_create(&writer, nullptr, [](void*) -> void* { v7LogMain(); return nullptr; }, nullptr) == 0) pthread_detach(writer);
        else {   // no thread: write here, as before
            std::deque<std::pair<int64_t, std::string>> lines;
            { std::lock_guard<std::mutex> l(log.lock); lines.swap(log.queue); log.started = false; }
            for (auto& q : lines) v7WriteAll(q.second.data(), q.second.size());
            return;
        }
    }
    log.wake.notify_one();
}
void v7LogFormat(const char* prefix, const char* fmt, va_list ap)
{
    char text[2048];
    const int n = vsnprintf(text, sizeof text, fmt, ap);
    if (n < 0) return;
    std::string line(prefix);
    line.append(text, std::min<size_t>(size_t(n), sizeof text - 1));
    line += '\n';
    v7LogPush(std::move(line));
}
// Waits (at most ms) until every queued line is written: the service's exit.
void v7LogDrain(int ms)
{
    V7Log& log = v7Log();
    std::unique_lock<std::mutex> l(log.lock);
    if (!log.started) return;
    log.idle.wait_for(l, std::chrono::milliseconds(ms), [&] { return log.queue.empty() && !log.writing && !log.dropped; });
}

void note(const char* fmt, ...) __attribute__((format(printf, 1, 2)));
void note(const char* fmt, ...)
{
    if (v7On()) { va_list ap; va_start(ap, fmt); v7LogFormat("OMNI HW SERVICE: ", fmt, ap); va_end(ap); return; }   // OMNI_HOLEPUNCH_V7_REV2
    va_list ap; va_start(ap, fmt);
    fprintf(stderr, "OMNI HW SERVICE: "); vfprintf(stderr, fmt, ap); fputc('\n', stderr);
    va_end(ap); fflush(stderr);
}

size_t alignUp(size_t v, size_t a) { return (v + a - 1) / a * a; }

struct Pending { int64_t pts; bool nonDisplaying; };

// OMNI_HOLEPUNCH_V5_REV2: a log line from the allocator below (holeNote is defined further down).
void holeNoteRaw(const char* fmt, ...) __attribute__((format(printf, 1, 2)));
void holeNoteRaw(const char* fmt, ...)
{
    if (v7On()) { va_list ap; va_start(ap, fmt); v7LogFormat("OMNI HOLEPUNCH: ", fmt, ap); va_end(ap); return; }   // OMNI_HOLEPUNCH_V7_REV2
    va_list ap; va_start(ap, fmt);
    fprintf(stderr, "OMNI HOLEPUNCH: "); vfprintf(stderr, fmt, ap); fputc('\n', stderr);
    va_end(ap); fflush(stderr);
}

// ---- OMNI_HOLEPUNCH_V5: decoded pictures waiting for their vblank live in direct memory -------
// A picture must be copied out of the decoder: its output ring (OmniHwBackend: 8 buffers) is
// written again 8 decodes later. V4 kept up to 8 copies (40 MB) in the UI process's flexible
// heap, which has ~1 GiB for everything. V5 queues ~3 s of them, so they go to direct memory
// (~12 GB in the big-app UI process; the decoder itself uses a few hundred MB of it), one
// mapping per picture buffer, bounded by paceDirectBudget. Buffers of 1 MiB or more come from
// there while paceDirectOn; smaller ones, and any the kernel refuses, from the heap.
std::atomic<bool> paceDirectOn { false };
std::atomic<size_t> paceDirectBytes { 0 };
std::atomic<uint64_t> paceDirectRefusals { 0 };
std::atomic<unsigned> paceDirectRefusalLogs { 0 };   // OMNI_HOLEPUNCH_V5_REV2: the first refusals, with rc
std::mutex paceDirectLock;
std::map<void*, std::pair<size_t, int64_t>> paceDirectMaps;   // address -> (size, direct start)
template <class T> struct PaceAlloc {
    using value_type = T;
    PaceAlloc() = default;
    template <class U> PaceAlloc(const PaceAlloc<U>&) { }
    T* allocate(size_t n)
    {
        const size_t bytes = n * sizeof(T);
        // OMNI_HOLEPUNCH_V5_REV2: every queued picture (rev 1 took only those of 1 MiB and up, so a
        // 640x360 queue, 338 KiB a picture, stayed on the heap and directMiB read 0).
        if (paceDirectOn.load(std::memory_order_relaxed) && bytes >= (64u << 10)) {
            const size_t size = alignUp(bytes, 0x4000);
            int64_t start = -1;
            int rc = 0; const char* stage = "";
            if (void* p = backendDirectAlloc(size, start, &rc, &stage)) {
                std::lock_guard<std::mutex> l(paceDirectLock);
                paceDirectMaps[p] = { size, start };
                paceDirectBytes += size;
                return static_cast<T*>(p);
            }
            paceDirectRefusals++;
            if (paceDirectRefusalLogs.fetch_add(1) < 3)
                holeNoteRaw("direct memory refused a %zu-byte picture buffer: %s -> 0x%08x (%zu bytes mapped so far); heap copy", size, stage, unsigned(rc), size_t(paceDirectBytes.load()));
        }
        return static_cast<T*>(::operator new(bytes));
    }
    void deallocate(T* p, size_t)
    {
        {
            std::lock_guard<std::mutex> l(paceDirectLock);
            auto it = paceDirectMaps.find(p);
            if (it != paceDirectMaps.end()) {
                const auto [size, start] = it->second;
                paceDirectMaps.erase(it);
                paceDirectBytes -= size;
                backendDirectFree(p, size, start);
                return;
            }
        }
        ::operator delete(p);
    }
    // OMNI_HOLEPUNCH_V5_REV2: resize() leaves the bytes as they are (holeSplitPlanes writes every
    // picture byte; fresh direct memory is zeroed by the kernel): no memset of 1-24 MB per buffer.
    template <class U> void construct(U* p) noexcept { ::new (static_cast<void*>(p)) U; }
    template <class U, class... A> void construct(U* p, A&&... a) { ::new (static_cast<void*>(p)) U(std::forward<A>(a)...); }
    template <class U> bool operator==(const PaceAlloc<U>&) const { return true; }
    template <class U> bool operator!=(const PaceAlloc<U>&) const { return false; }
};
using PaceBuf = std::vector<uint8_t, PaceAlloc<uint8_t>>;
constexpr size_t paceDirectBudget = size_t(1) << 30;   // decoded pictures queued, direct memory
constexpr unsigned paceMaxFramesV5 = 240;               // 4 s at 60 fps
constexpr int64_t paceAheadUs = 3000000;                // decode until ~3 s ahead of the clock

// ---- OMNI_HOLEPUNCH_V4: types of the shell-side frame pacing (see "pacing" below) ----------
struct PacedFrame { PaceBuf planes; int w = 0, h = 0, depth = 8; int64_t mediaUs = 0; int64_t pts = 0; double queuedMs = 0; };   // OMNI_HOLEPUNCH_V5: PaceBuf, pts; V7: queuedMs
// The player's playback clock (HoleClock), extrapolated between its updates.
struct PaceClock {
    bool valid = false, playing = false;
    double rate = 1;
    int64_t posUs = 0, anchorUs = 0, limitUs = INT64_MAX;
    double holdUs = 2e6;   // OMNI_HOLEPUNCH_V5: 4 s (the player may not tick for 2-3 s)
    // Media time (us) at wall time tMs (CLOCK_MONOTONIC ms). Without updates it holds after
    // holdUs (V4: 2 s).
    int64_t at(double tMs) const
    {
        if (!playing) return std::min(posUs, limitUs);
        const double dt = std::min(tMs * 1000 - double(anchorUs), holdUs);
        return std::min(posUs + int64_t(dt * rate), limitUs);
    }
    // Wall time (ms) at which the clock reaches mediaUs; HUGE_VAL when it does not run there.
    double wallMs(int64_t mediaUs) const
    {
        if (!valid || !playing || rate <= 0 || mediaUs > limitUs) return HUGE_VAL;
        return (double(anchorUs) + double(mediaUs - posUs) / rate) / 1000;
    }
};

struct Channel {
    int index = 0;
    int serverFd = -1, clientFd = -1;
    uint32_t generation = 0;
    bool connected = false;
    Backend decoder;
    int shmFd = -1; uint8_t* shm = nullptr; size_t shmSize = 0;
    uint32_t slotOffset = 0, slotSize = 0;
    bool slotBusy[Wire::outputSlots] = {};
    std::deque<Message> waiting;      // Submit/Drain held until an output slot is free
    std::deque<Pending> pending;      // shown submissions not yet emitted, pts-sorted
    bool draining = false;
    bool failed = false;
    int width = 0, height = 0;                // OMNI_HOLEPUNCH_V1: visible size (Configure)
    uint32_t colour = 0;                      // OMNI_HOLEPUNCH_COLOUR_V1: Configure.f
    Message slotFrame[Wire::outputSlots];     // the Frame message sent for each busy slot
    int holeAnswer = 0;                       // last HoleState sent: 1 shown, -1 refused, 0 none
    uint32_t holeShown = 0, holePresents = 0; // OMNI_HOLEPUNCH_V2: acks sent / Presents handled
    double holeLastFrameMs = 0;               // last Present(slot) handled
    bool holeQuietLogged = false;             // "no picture" logged for the current gap
    // OMNI_HOLEPUNCH_V4: pacing (service thread only). While paceOn, decoded pictures of this
    // channel go to `paced` (no slot, no Frame message) and are shown by the shell by `clock`.
    bool paceOn = false;
    int paceAnswer = 0;                       // last HolePacing status sent: 1 pacing, -1 refused
    unsigned paceCap = 0;                     // queue room (frames) for this stream's picture size
    std::deque<PacedFrame> paced;             // decoded, not converted yet; media order
    std::vector<PaceBuf> pacedSpare;          // OMNI_HOLEPUNCH_V5: PaceBuf
    PaceClock clock;                          // invalid after a Flush until a new generation
    uint32_t paceGen = 0;
    bool paceGenSeen = false, posterPending = false;   // posterPending: after a Flush, the first picture shows at once
    int64_t discardUs = INT64_MIN;
    int tbNum = 1, tbDen = 1;                 // time base of the frame pts
    uint64_t paceDecoded = 0, paceDroppedRaw = 0, paceDiscarded = 0, paceReportedShown = ~0ull;
    double paceReportMs = 0;
    // OMNI_HOLEPUNCH_V5
    uint32_t consumedCount = 0, consumedSent = 0;   // Submits consumed since Configure/Flush; last told
    bool runnable = false;                    // runWaiting stopped for time with work it can do
    bool paceV5 = false;                      // this pacing run uses V5's queue (holeV5FlagEnabled)
    int64_t playFromUs = 0;                   // OMNI_HOLEPUNCH_V5_REV3: anchor of the update that started the clock (generation, play, hold released)
    size_t paceFrameBytes = 0;                // one queued picture (planar copy)
    int bitDepth = 8;                         // Configure
    // OMNI_PERF_B_V5 (service thread): the decoder of this channel is being opened on the configure worker (v5Msg);
    // the channel's messages meanwhile wait in v5Held, in order, and are handled when the open is done.
    bool v8FirstShownSent = false;   // OMNI_PERF_B_V8: the first picture of this generation was reported
    double v8ConfiguredMs = 0;       // OMNI_PERF_B_V8: the last Configure (a stream opened then may be a quality switch's)
    bool v5Configuring = false;
    Message v5Msg;
    std::deque<Message> v5Held;
    int v5Rc = 0; std::string v5Stage; double v5StartedMs = 0;   // the worker's result (under v5w.m until handed back)
};

std::atomic<bool> running { false };
std::atomic<bool> threadDone { false };
pthread_t thread;
Channel channels[Wire::maxChannels];
std::atomic<size_t> liveStreamBytes[Wire::maxChannels]; // OMNI_TAB_MEDIA_RELEASE_V1: shared memory of each open stream (0: none), for openDecoderCount
std::string dir;

unsigned busySlots(const Channel& c)   // OMNI_HOLEPUNCH_V2
{
    unsigned n = 0;
    for (bool b : c.slotBusy) n += b;
    return n;
}

// ---- OMNI_HOLEPUNCH_V1: the shell's video plane --------------------------------------------
// Threads: the service thread (serviceMain) is the only one that ever reads an output slot.
// For Present(slot) it copies the visible picture out of the slot, converts it to a layer at
// the on-screen size (one swscale pass) and frees the slot before it handles the next
// message, so a slot is never read after the decoder may reuse it. The shell's main thread
// blends the page over the newest layer (holePunchCompose). Layers change hands only under
// plane.lock, and each layer's pixels are written by one thread at a time.
struct HoleRect {
    int x = 0, y = 0, w = 0, h = 0;
    bool operator!=(const HoleRect& o) const { return x != o.x || y != o.y || w != o.w || h != o.h; }
};
struct HoleLayer {
    CpuPixelBuffer px; int w = 0, h = 0; uint64_t epoch = 0;
    // OMNI_HDR_PORT_V1: PQ pixels (packed 10:10:10:2) beside the RGBA8 image, which stays the
    // compose/fallback contract. Only filled while the display runs in PQ.
    CpuPixelBuffer hdrPx; bool hdrValid = false;
    uint64_t v8Seq = 0;   // OMNI_HOLEPUNCH_V8_CADENCE (under plane.lock): stamped when holePaceSelect makes it current
    bool v8First = false;   // OMNI_HOLEPUNCH_V8_CADENCE: the first picture of its generation (a seek's target): flipped as it is
    // OMNI_HOLEPUNCH_V4: a paced picture's media time and its planar source (snapshots and
    // rescales use the picture on screen; rawW 0 = none). raw is written by the service thread
    // only while the layer is not current.
    int64_t mediaUs = INT64_MIN;
    PaceBuf raw; int rawW = 0, rawH = 0, rawDepth = 8;   // OMNI_HOLEPUNCH_V5: PaceBuf
    int stride = 0;   // OMNI_HOLEPUNCH_COLOUR_V1: bytes per row of px (whole 16-pixel groups)
    // OMNI_PERF_B_V3: px holds this picture's RGBA8 image (2), is being made by the service (1), or was not made (0:
    // skipped while the PQ set shows the video fullscreen). Readers other than the service go through holeLayerPx().
    // v3Colour / v3SwapRB: what the service needs to make it later (holeSdrInto) from `raw`.
    mutable std::atomic<int> pxState { 2 };
    mutable std::mutex pxMutex;
    uint32_t v3Colour = 0; bool v3SwapRB = false;
};

struct HolePlane {
    std::mutex lock;                         // guards the fields up to `version`
    bool attached = false, swapRB = false;   // swapRB: canvas bytes are R,G,B,A (else B,G,R,A)
    int owner = -1;                          // channel whose video is shown; -1 none
    uint64_t epoch = 0;                      // +1 per new owner: older layers are never shown
    HoleRect rect;                           // newest rect of the owner's video, view pixels
    std::unique_ptr<HoleLayer> ready;        // newest converted picture not yet composed
    std::vector<std::unique_ptr<HoleLayer>> spare;
    uint64_t frames = 0, shown = 0, dropped = 0, rectUpdates = 0, refused = 0, composes = 0;
    double convertMs = 0, composeMs = 0;
    unsigned logLines = 0;
    std::atomic<uint64_t> version { 0 };     // bumped on every change the shell must draw
    // Service thread only.
    std::vector<uint8_t> planes;             // last presented picture, planar 4:2:0
    int srcW = 0, srcH = 0, depth = 8, layerW = 0, layerH = 0;
    bool haveFrame = false;
    bool rescalePending = false;             // OMNI_HOLEPUNCH_V2: rect size changed without a picture
    double lastRescaleMs = 0;
    uint64_t rescales = 0, rescalesSkipped = 0;
#ifndef OMNI_HW_NO_SWSCALE
    SwsContext* sws = nullptr;
    int swsKey[7] = {};   // OMNI_HOLEPUNCH_COLOUR_V1: what sws was made for (sizes, formats, colour)
    int swsLoggedColour = -1;
#endif
    // Shell main thread only.
    std::unique_ptr<HoleLayer> current;
    // OMNI_HOLEPUNCH_V8_CADENCE (under lock): the picture a compose is blending, from then to the
    // hand-off: the presenter may make a newer one current meanwhile; this one is kept off `spare`
    // (where the service would reuse it) until the hand-off has checked the canvas against it.
    const HoleLayer* pinned = nullptr;
    std::unique_ptr<HoleLayer> pinnedRetired;
    // OMNI_PERF_B_V1 (under lock): a record-only canvas (holePunchCompose wrote no video pixels into it) went to the
    // presenter: the picture it was composed with stays allocated (off `spare`) until holePunchBeforeFlip has put
    // video into that frame (its fallback picture). planeDiscard() keeps it in flipPinRetired meanwhile.
    const HoleLayer* flipPin = nullptr;
    std::unique_ptr<HoleLayer> flipPinRetired;
    // OMNI_PERF_B_V8 (under lock): the owner's stream ended for a quality switch (Configure on the same channel, or a
    // close while another stream of this process is open): its last picture stays on screen (owner, epoch, current
    // kept; pacing stopped) until the next stream presents (same epoch: no blank frame), or 1 s (then released).
    int holdOwner = -1; double holdUntilMs = 0;
    uint64_t v8Seq = 0;   // OMNI_HOLEPUNCH_V8_CADENCE (under lock): +1 per picture made current (HoleLayer::v8Seq)
    uint64_t seenVersion = 0;
    // OMNI_HOLEPUNCH_V4, under lock: the owner's converted frames waiting for their vblank, and
    // the clock that times them (copied from the owner channel).
    std::deque<std::unique_ptr<HoleLayer>> paced;
    PaceClock clock;
    FrameCadence cadence; // guarded by plane.lock; reset on generation changes
    bool startupPresentationReady = false; // V133: presenter acknowledged a valid handoff in this generation; plane.lock
    uint32_t startupGeneration = 0;
    bool pacing = false, shownInGen = false;  // shownInGen: a paced picture shown since the last generation change
    bool posterPending = false;               // after a Flush: show the first picture at once (the seek target)
    uint64_t pacedShown = 0, pacedDropped = 0, pacedLate = 0;
    // OMNI_HOLEPUNCH_V4, service thread only: `planes`' media time and the 5 s pacing log window.
    int64_t planesMediaUs = INT64_MIN;
    double paceWindowMs = 0, paceQueueSum = 0, paceDriftMaxMs = 0, paceConvertMs = 0;
    uint64_t paceWinShown = 0, paceWinDropped = 0, paceWinLate = 0, paceQueueSamples = 0, paceConverts = 0;
    unsigned paceUpdates = 0, paceLogLines = 0;
    double paceAheadMinMs = HUGE_VAL;         // OMNI_HOLEPUNCH_V5: least decoded media ahead of the clock in the window
    // OMNI_HOLEPUNCH_V5_REV2: clockDriftMs split: the largest correction by an update less than 1 s
    // after the previous one with the clock short of its limit (a real disagreement), and how
    // many updates came after a longer gap or a clock stopped at the end of the buffered range
    // (the player's playhead was not extrapolated there: those corrections are expected).
    double paceDriftSteadyMs = 0;
    unsigned paceDriftGapUpdates = 0;
    // OMNI_HOLEPUNCH_V5_REV3: the first 1.5 s after the clock starts (start, seek, hold released) are
    // settling, not steady: audio takes over as the master clock then (one correction by the
    // output's start-up latency). Reported on their own.
    double paceDriftSettleMs = 0;
};
HolePlane plane;

// ---- OMNI_HOLEPUNCH_V4: pacing ---------------------------------------------------------------
// The WebProcess may tick its player at ~5 Hz (youtube.com watch page), so it no longer picks
// the frame to show. While a channel paces, every picture it decodes is copied (planar 4:2:0)
// into a short queue with its media time; the service thread converts each one about two
// vblanks before it is due, and the shell's compose shows the newest converted picture due at
// the vblank the canvas will be flipped on. Late pictures are dropped here; the player only
// keeps feeding access units and sends its clock (HoleClock).
std::atomic<int64_t> vblankUs { 0 };          // last presenter flip (holePunchVblank), us
constexpr double vblankMs = 1000.0 / 60, composeLeadMs = 4;
constexpr size_t paceQueueBytes = 40u << 20;  // decoded frames waiting, whatever their size
constexpr unsigned paceMaxFrames = 8, paceAhead = 2;

// OMNI_HOLEPUNCH_V7_REFLIP: the display's period as measured from the flips (0: not yet, or V7
// off); 59.94 Hz is 16.683 ms, not 1000 / 60.
std::atomic<int64_t> v7VblankNs { 0 };
double vblankPeriodMs() { const int64_t ns = v7VblankNs.load(std::memory_order_relaxed); return ns ? double(ns) / 1e6 : vblankMs; }
// The first vblank at or after tMs: from the presenter's last flip (REQ-4), else unknown phase.
// OMNI_HOLEPUNCH_V8_CADENCE: a point of the display's vblank grid, from the flips' returns: a return
// is never early, only late by a wake-up, so the grid follows the earliest ones (0: none yet).
bool v8On();
std::atomic<int64_t> v8GridUs { 0 };
double vblankAfter(double tMs)
{
    if (v8On()) {
        const int64_t grid = v8GridUs.load(std::memory_order_relaxed);
        const double g = double(grid) / 1000, period = vblankPeriodMs();
        if (grid && std::fabs(tMs - g) < 1000) return g + std::ceil((tMs - g) / period - 1e-6) * period;
    }
    const double last = double(vblankUs.load(std::memory_order_relaxed)) / 1000, period = vblankPeriodMs();   // V7: measured
    if (last > 0 && tMs >= last && tMs - last < 1000) return last + std::ceil((tMs - last) / period) * period;
    return tMs + period / 2;   // 60 Hz cadence, phase unknown: half a period away on average
}
bool vblankReported() { const double last = double(vblankUs.load(std::memory_order_relaxed)) / 1000; return last > 0 && nowMs() - last < 1000; }

// ---- OMNI_HOLEPUNCH_V7_REFLIP ----------------------------------------------------------------
// Console v87/v91: the shell's main thread stops for 70-290 ms at a time (page script, the main
// loop) and every picture due meanwhile is lost: it alone composes. With V7 the presenter
// thread (OMNI_SHELL_PRESENT_V1; patch-shell-holepunch-v7.py) wakes just before each vblank
// while a paced video plays and, when the main thread has not ticked for v7StallMs, puts the
// newest due picture into the last presented frame itself and flips it. holePunchCompose (V7 on)
// records which canvas pixels it took from the video (runs of hole pixels) and the translucent
// page pixels over it (with their page values); a re-flip changes those pixels only where the
// frame still holds exactly what that compose wrote there, so the page and anything the shell
// drew after the compose (bars, pointer, dialogs) are kept. No new thread; nothing more on the
// main thread than the record. Kill switch: /data/omni/holepunch-v7-disabled.flag (host:
// OMNI_HOLEPUNCH_V7=0): every V7 path is off (v90's behaviour); the counters still log.
// OMNI_HOLEPUNCH_V7_REV2: the kill switch now covers everything V7 added (no V7 line, counter,
// clock read, phase or thread query: v90 exactly). A re-flip no longer reads the screen surface
// (console v92: 8.3 ms average, 81 ms max for ~240K pixels: uncached memory): at the hand-off
// (holePunchHandOff, omniPresentFrame) the main thread checks the record against the finished
// canvas, which is cached, and keeps the pixels that still hold what the compose wrote; a re-flip
// then only writes those. Log lines go through the writer thread (above).
bool holeV7FlagEnabled()
{
    if (const char* env = getenv("OMNI_HOLEPUNCH_V7")) return env[0] != '0';
#ifdef __PROSPERO__
    return access("/data/omni/holepunch-v7-disabled.flag", F_OK) != 0;
#else
    return true;
#endif
}
bool v7On() { static const bool on = holeV7FlagEnabled(); return on; }
// ---- OMNI_HOLEPUNCH_V8_CADENCE ----------------------------------------------------------------
// Console v96, 1080p60 (BBB): 274-290 of 300 shown per 5 s, 10-27 "cadence" drops. V5 rev 3 picks
// the picture when the shell's main thread composes, for the vblank it guesses the canvas will
// reach, and that thread runs on a free 60 Hz timer: against the 59.94 Hz display its hand-offs
// drift through every phase (v96: 274-289 hand-offs per 299.7 vblanks), so now and then a vblank
// gets no new canvas (the picture due there is dropped by the next compose) or a canvas lands one
// vblank later than guessed. V8 ties the choice to the vblanks themselves:
//  - the presenter wakes 3 ms before every vblank while a paced video plays (V7: 8 ms, and only
//    with the main thread stalled); when no canvas has come for that vblank and a newer picture
//    is due there, it writes that picture into the frame (the V7 re-flip; 0.5 ms at 1080p on the
//    console) and flips it, whether the main thread is stalled or not;
//  - the main thread composes the picture due at the coming vblank (not one guessed 4 ms ahead),
//    and at the hand-off (holePunchHandOff) brings the canvas up to the picture due at the vblank
//    its flip will reach: the flip lead is learned from where the flips really land;
//  - the content's rate is the mean frame interval (V7 took the smallest: 16 ms steps of a 60 fps
//    stream with millisecond timestamps read as 62.50 fps, and rateMismatch followed it).
// So a picture is dropped only when the display is slower than the content (60.00 fps on 59.94
// Hz: one per ~16.7 s, counted as rateMismatch) or a vblank really had no flip (counted).
// Kill switch: /data/omni/holepunch-v8-disabled.flag (host: OMNI_HOLEPUNCH_V8=0): V7 rev 2
// exactly; and V7's flag turns V8 off too (v90).
bool holeV8FlagEnabled()
{
    if (const char* env = getenv("OMNI_HOLEPUNCH_V8")) return env[0] != '0';
#ifdef __PROSPERO__
    return access("/data/omni/holepunch-v8-disabled.flag", F_OK) != 0;
#else
    return true;
#endif
}
bool v8On() { static const bool on = v7On() && holeV8FlagEnabled(); return on; }
// V9 retains V8 as an A/B fallback without rebuilding.
bool v9On()
{
    static const bool enabled = [] {
        if (const char* env = getenv("OMNI_HOLEPUNCH_V9")) return env[0] != '0';
#ifdef __PROSPERO__
        return access("/data/omni/holepunch-v9-disabled.flag", F_OK) != 0;
#else
        return true;
#endif
    }();
    return v8On() && enabled;
}

constexpr double v8MarginMs = 3, v8MarginMaxMs = 3.8;   // the presenter decides 3 to 3.8 ms before a vblank
// The flip call's set-up time, as learned from the hand-offs: one handed off less than this before
// a vblank reaches the next one. A flip that lands on the first vblank after its hand-off although
// it came less than the estimate before it lowers the estimate to just below that gap; one that
// lands on the second although it came more before raises it to just above (0.5 ms at most per flip).
std::atomic<int64_t> v8LeadUs { 1000 };
std::atomic<int64_t> v8TargetUs { 0 };    // the vblank the pending flip should reach (0: none)
std::atomic<bool> v8TargetHandOff { false };   // set by a hand-off (the lead is learned from those)
std::atomic<int64_t> v8HandOffAtUs { 0 }, v8FirstUs { 0 };   // the call that set the target (hand-off, before-flip, re-flip) and the first vblank after it
std::atomic<bool> v8BeforeFlipSeen { false };   // the presenter calls holePunchBeforeFlip (patch-shell-holepunch-v8.py): it, not the hand-off, sets a canvas's target
std::atomic<unsigned> v8BeforeFlips { 0 };
std::atomic<unsigned> v8CadenceReflips { 0 }, v8StallReflips { 0 }, v8Reselects { 0 }, v8FlipsLate { 0 }, v8FlipsEarly { 0 }, v8ReflipWaits { 0 };
std::atomic<int64_t> v8StepUs { 0 }; std::atomic<unsigned> v8Steps { 0 };
// What the presenter must fit before the flip call: a hand-off it may have to wait for (compose no
// longer: it blends a pinned picture without v7ComposeLock), its own re-flip. Recent maxima (each new
// value, or the last one decaying by 1/64 per call); the compose's for the log.
std::atomic<int64_t> v8ComposeUs { 1000 }, v8HandOffCostUs { 500 }, v8ReflipCostUs { 500 };
void v8Recent(std::atomic<int64_t>& a, int64_t v) { const int64_t old = a.load(std::memory_order_relaxed); a.store(std::max(v, old - old / 64), std::memory_order_relaxed); }   // the content's frame interval: sum and count of steps between shown pictures
constexpr double v7StallMs = 25;   // no tick for this long: the main thread is busy (it ticks at 60 Hz)
constexpr double v7MarginMs = 8;   // the presenter asks this long before a vblank (select + blend + flip)
std::mutex v7ComposeLock;          // V7 on: holePunchCompose (main thread) vs holePunchReflip (presenter)
// What the last compose wrote from the video (under v7ComposeLock): canvas rows of hole pixels as
// (y, x, n) and translucent page pixels (y * width + x, page B,G,R,A).
struct V7Record {
    const HoleLayer* layer = nullptr;   // the picture composed (plane.current then)
    bool valid = false, swapRB = false;
    int width = 0, height = 0, lx = 0, ly = 0;
    std::vector<uint32_t> runs, mixPos, mixPage;
    std::vector<uint32_t> mixOut;   // OMNI_HOLEPUNCH_V7_REV2: what the compose wrote there (checked at the hand-off)
    bool handedOff = false;         // OMNI_HOLEPUNCH_V7_REV2: checked by a hand-off already
    // OMNI_PERF_B_V7: the translucent pixels as spans (first index into mixPos / mixPage / mixOut, length), each inside
    // one row with consecutive x: the hand-off and the re-flips walk spans instead of finding them pixel by pixel.
    std::vector<uint32_t> mixSpans;
    // OMNI_PERF_B_V1: record only. The canvas holds 0 (B,G,R,A all zero) at every recorded pixel (hole runs and
    // translucent pixels) instead of video; mixOut is empty (expected value 0). The presenter writes the video.
    bool recordOnly = false;
};
V7Record v7Record;
// OMNI_HOLEPUNCH_V7_REV2 (under v7ComposeLock): what the frame on screen took from the video: the
// record's pixels that the finished canvas still held at the hand-off; shownUs: the picture there.
struct V7Live {
    bool valid = false, swapRB = false;
    int width = 0, height = 0, lx = 0, ly = 0, w = 0, h = 0;
    int64_t shownUs = INT64_MIN;
    uint64_t v8ShownSeq = 0;   // OMNI_HOLEPUNCH_V8_CADENCE: that picture's v8Seq
    bool v8First = false;      // and its v8First: not brought up before its flip
    uint64_t epoch = 0;   // the plane's owner then: another owner's frame is not this one
    std::vector<uint32_t> runs, mixPos, mixPage;
    std::vector<uint32_t> mixSpans;   // OMNI_PERF_B_V7: (first index, length) per span of mixPos
    bool recordOnly = false;          // OMNI_PERF_B_V1: the canvas this describes holds no video pixels
};
V7Live v7Live;
// ---- OMNI_PERF_B (WS-B perfectionist pass): kill switches and the 5 s "pacing B" counters ------------------
// Each item has a kill switch file in /data/omni (read once): perf-b-v1-disabled.flag (record-only compose),
// perf-b-v2-disabled.flag (holePunchPresenterOwnsVideo() always false), perf-b-v3-disabled.flag (8-bit copy always
// made), perf-b-v5-disabled.flag (decoder configure on the service thread), perf-b-v7-disabled.flag (mix spans off),
// perf-b-v6-disabled.flag (upscale rows: the previous loop).
bool pbFlagOff(const char* path) { return access(path, F_OK) == 0; }
bool v7SpansOn() { static const bool on = !pbFlagOff("/data/omni/perf-b-v7-disabled.flag"); return on; }
bool v1On() { static const bool on = v7SpansOn() && !pbFlagOff("/data/omni/perf-b-v1-disabled.flag"); return on; }
bool v2On() { static const bool on = !pbFlagOff("/data/omni/perf-b-v2-disabled.flag"); return on; }
bool v3On() { static const bool on = v1On() && !pbFlagOff("/data/omni/perf-b-v3-disabled.flag"); return on; }
bool v5On() { static const bool on = !pbFlagOff("/data/omni/perf-b-v5-disabled.flag"); return on; }
bool v6On() { static const bool on = !pbFlagOff("/data/omni/perf-b-v6-disabled.flag"); return on; }
// Why holePunchPoll asked the shell to draw (or not), per window.
std::atomic<unsigned> pbPollVersion { 0 }, pbPollPoster { 0 }, pbPollNoPresenter { 0 }, pbPollLive { 0 }, pbPollSkipBusy { 0 }, pbPollSkipLive { 0 };
// V1: composes by kind and their cost; hand-offs of record-only canvases; before-flip fallbacks.
std::atomic<unsigned> pbComposeRecord { 0 }, pbComposeBlend { 0 }, pbHandOffRecordOnly { 0 }, pbRecordFilled { 0 }, pbFlipPinFallback { 0 }, pbFlipNoPicture { 0 };
std::atomic<int64_t> pbComposeRecordUs { 0 }, pbComposeBlendUs { 0 }, pbPrepareUs { 0 }; std::atomic<unsigned> pbPrepares { 0 };
std::atomic<bool> pbLiveRecordOnly { false };   // v7Live.recordOnly, readable without v7ComposeLock (set by the hand-off)
std::atomic<bool> v1LastComposeRecordOnly { false };
// V2: the presenter shows every new picture of a full-canvas video by itself (set by the hand-off).
std::atomic<bool> pbOwnsVideo { false };
// V3: 8-bit copies skipped / made later by the service / made on demand by a reader; PQ flips with a large
// translucent area (pxState 0: no 8-bit copy to fall back on); PQ refused for a large translucent area.
std::atomic<unsigned> pbV3Skipped { 0 }, pbV3Backfilled { 0 }, pbV3Lazy { 0 }, pbV3PqForced { 0 }, pbPqRefusedMix { 0 }, pbPqRefusedMixMax { 0 };
std::atomic<int64_t> v3PqShownUs { 0 }, v3SdrNeededUs { 0 };   // monotonic us: the PQ set last showed the video / an 8-bit copy was last needed
// V5: configures run on the configure worker, their longest time, messages held meanwhile.
std::atomic<unsigned> pbV5Async { 0 }, pbV5Sync { 0 }, pbV5Deferred { 0 }; std::atomic<int64_t> pbV5MaxUs { 0 };

// Presenter-thread-only identity: a newly handed-off picture is not necessarily
// already displayed. Empty-queue deferral is legal only for a successful repeat.
uint64_t v143PreparedSeq = 0, v143PreparedEpoch = 0;
uint64_t v143CompletedSeq = 0, v143CompletedEpoch = 0;
// Two approved production counters. Successful video completions only, not
// refresh periods, decoded frames, or attempted submissions. No new clock reads.
std::atomic<uint64_t> hudCompleted {0}, hudRepeats {0}, hudDecoderErrors {0};
std::atomic<bool> hudEnabled {false}, hudActive {false}, hudDecoderFailed {false};
std::atomic<uint64_t> hudDrops {0};
std::atomic<int> hudWidth {0}, hudHeight {0}, hudCodec {-1};
// Existing service thread owns channel data. Publish once per second; a busy
// plane is skipped rather than making a stats reader block video work.
void publishPlaybackStats(double now) {
    static double next = 0;
    if (!hudEnabled.load(std::memory_order_relaxed) || now < next) return;
    next = now + 1000;
    std::unique_lock<std::mutex> guard(plane.lock,std::try_to_lock);
    if (!guard.owns_lock()) return;
    const int owner=plane.owner;
    const bool active=plane.attached && owner>=0 && owner<int(Wire::maxChannels);
    hudActive.store(active,std::memory_order_relaxed);
    if (!active) { hudWidth.store(0); hudHeight.store(0); hudCodec.store(-1); hudDrops.store(0); hudDecoderFailed.store(false); return; }
    const auto& c=channels[owner];
    if (c.v5Configuring) return;   // OMNI_PERF_B_V5: the worker owns the decoder now
    hudCodec.store(int(c.decoder.codec()),std::memory_order_relaxed);
    hudWidth.store(c.width,std::memory_order_relaxed); hudHeight.store(c.height,std::memory_order_relaxed);
    hudDrops.store(plane.pacedDropped+c.paceDroppedRaw,std::memory_order_relaxed);
    hudDecoderFailed.store(c.failed,std::memory_order_relaxed);
}

// UI-thread staging; published only under both existing presentation/compose locks.
V7Live v130PendingLive;
bool v130PendingReady = false;
const uint8_t* v130PendingCanvas = nullptr;
std::atomic<int64_t> v7HandOffUs { 0 }, v7HandOffMaxUs { 0 };
std::atomic<unsigned> v7HandOffs { 0 };
// OMNI_HOLEPUNCH_4K_MASK_V1: the caps were 8192 runs and 1M translucent pixels (sized below 4K). A 4K
// fullscreen player whose controls fade in over the lower third has ~2.8M translucent pixels: past the
// cap, re-flips left the bottom ~20% of the picture seconds old (user report, 2026-10-26). Now the
// whole 3840x2160 canvas fits (vectors grow only to what a compose actually records).
constexpr size_t v7MaxRuns = 3 * (size_t(1) << 22), v7MaxMix = size_t(3840) * 2160;
// Counters, per 5 s window (pacing V7 line). Shell side: atomics; service side: plain.
std::atomic<int64_t> v7PollUs { 0 }, v7PollGapMaxUs { 0 }, v7StallUs { 0 }, v7ReflipUs { 0 }, v7ReflipMaxUs { 0 };
std::atomic<unsigned> v7Stalls { 0 }, v7Reflips { 0 }, v7ReflipBusy { 0 }, v7ReflipStale { 0 }, v7ReflipPixelsK { 0 };
unsigned v7RawShellBehind = 0, v7RawDecodedLate = 0, v7RawOther = 0;   // service thread only
// Drops at the select, by reason: the shell was stalled (no tick for 25 ms, or the presenter
// showing it), at a normal cadence (rate mismatch, timing), or older than the one on screen.
std::atomic<unsigned> v7DropStall { 0 }, v7DropCadence { 0 }, v7DropStale { 0 };
int64_t v7TickGapUs = 0;            // shell main thread: the gap before its current tick
bool v7SelectByPresenter = false;   // under plane.lock: holePaceSelect called by holePunchReflip
std::atomic<int64_t> v7FrameUs { 0 };   // media time between shown pictures (the content's rate)
// The display's real refresh, from the presenter's flips (each 1-4 vblanks apart).
std::atomic<int64_t> v7FlipSpanUs { 0 }, v7FlipVblanks { 0 };
int64_t v7RunSpanUs = 0, v7RunVblanks = 0;   // service thread: the same since the start (a finer average)
double v7MismatchBudget = 0;        // service thread: rate-mismatch drops expected and not yet seen
// The shell main thread's phases (holePunchShellPhase) between two ticks, and the window's longest stall.
constexpr int v7Phases = 6;
int v7Phase = 0; int64_t v7PhaseSinceUs = 0; int64_t v7PhaseUs[v7Phases] = {}; bool v7PhaseSeen = false;   // main thread
std::mutex v7TraceLock;
int64_t v7StallLongestUs = 0, v7StallPhaseUs[v7Phases] = {};   // under v7TraceLock
std::atomic<int> v7PhaseNow { 0 };   // the phase, for the stack sample (read by the main thread's own signal handler)
// Stack sample of the stalled main thread (presenter-triggered, at most 6 per run).
pthread_t v7MainThread {}; std::atomic<bool> v7MainKnown { false };
std::atomic<unsigned> v7Samples { 0 }; std::atomic<int64_t> v7SampleUs { 0 };
uintptr_t v7ImageBase = 0, v7CodeEnd = 0; bool v7SampleReady = false, v7SampleTried = false;
int (*v7VirtualQuery)(const void*, int, void*, size_t) = nullptr;
// The shell's stalls, the service's busy bursts (decode-ahead after a segment arrives) and slow
// page copies on one clock (nowMs), per window; and the threads' priorities and CPUs.
struct V7Event { int64_t atUs = 0, durUs = 0; int kind = 0; unsigned count = 0; };   // kind 0 shell stall, 1 service burst, 2 slow page paint
std::vector<V7Event> v7Events;   // under v7TraceLock, at most 24 per window
void v7Event(int64_t atUs, int64_t durUs, int kind, unsigned count)
{
    std::lock_guard<std::mutex> l(v7TraceLock);
    if (v7Events.size() < 24) v7Events.push_back({ atUs, durUs, kind, count });
}
// WKPagePaint (phase 4), main thread: calls, the longest, those over 50 ms, and those over 50 ms after
// 10 s or more without one (WebKit discards the backing store after 10 s; the next paint then waits
// for the WebProcess, up to 500 ms: DrawingAreaProxyCoordinatedGraphics::forceUpdateIfNeeded).
std::atomic<unsigned> v7Paints { 0 }, v7PaintsSlow { 0 }, v7PaintsSlowAfterIdle { 0 };
std::atomic<int64_t> v7PaintMaxUs { 0 };
int64_t v7PaintLastUs = 0;   // main thread: the previous paint's start
double v7ServiceStartMs = 0;  // the timeline's zero
unsigned v7ServiceYields = 0, v7ServiceSleeps = 0;   // service thread only
double v7OpMaxMs = 0; const char* v7OpMaxWhat = "none";   // service thread only: the longest single operation of the window
void v7Op(double ms, const char* what) { if (ms > v7OpMaxMs) { v7OpMaxMs = ms; v7OpMaxWhat = what; } }
const char* v7MessageName(unsigned type)
{
    switch (Type(type)) {
    case Type::Submit: return "submit (decode)";
    case Type::Configure: return "configure (decoder init)";
    case Type::Flush: return "flush";
    case Type::Drain: return "drain";
    case Type::Present: return "hole present";
    case Type::Release: return "release";
    case Type::Close: return "close";
    case Type::HoleClock: return "hole clock";
    default: return "other message";
    }
}
struct V7Thread { std::atomic<bool> known { false }; int policy = 0, priority = 0, cpuError = 0; unsigned long long cpus = 0; };
V7Thread v7MainThreadInfo, v7ServiceThreadInfo, v7PresenterThreadInfo;
void v7NoteThread(V7Thread& t)
{
    if (t.known.load(std::memory_order_relaxed)) return;
    sched_param param {}; int policy = 0;
    pthread_getschedparam(pthread_self(), &policy, &param);
    t.policy = policy; t.priority = param.sched_priority;
    unsigned long long mask = 0;
#ifdef __PROSPERO__
    // OMNI_HOLEPUNCH_V7_REV2: the set's size must be the kernel's (ERANGE, 34, otherwise: v92 with the
    // SDK's cpuset_t, v96 with 128 bytes): 8 to 128 bytes are tried; bit i of word i / 64 is CPU i.
    // Then Sony's scePthreadGetaffinity (a 64-bit mask), if libkernel has it.
    uint64_t bits[16] = {};
    int e = ERANGE;
    for (size_t bytes = 8; bytes <= sizeof bits && e == ERANGE; bytes *= 2) {
        std::fill(bits, bits + 16, 0);
        e = cpuset_getaffinity(CPU_LEVEL_WHICH, CPU_WHICH_TID, -1, bytes, reinterpret_cast<cpuset_t*>(bits)) ? errno : 0;
    }
    if (e) {
        using GetAffinity = int (*)(pthread_t, uint64_t*);
        if (auto get = reinterpret_cast<GetAffinity>(dlsym(RTLD_DEFAULT, "scePthreadGetaffinity"))) {
            uint64_t m = 0;
            const int r = get(pthread_self(), &m);
            if (!r) { bits[0] = m; e = 0; } else e = r;   // Sony error codes are negative (0x8002xxxx)
        }
    }
    if (!e) mask = bits[0];
#else
    cpu_set_t set;
    CPU_ZERO(&set);
    const int e = pthread_getaffinity_np(pthread_self(), sizeof set, &set);
    if (!e) for (int i = 0; i < 64; i++) if (CPU_ISSET(i, &set)) mask |= 1ull << i;
#endif
    t.cpus = mask; t.cpuError = e;
    t.known.store(true, std::memory_order_release);
}
void v7Max(std::atomic<int64_t>& a, int64_t v)
{
    int64_t seen = a.load(std::memory_order_relaxed);
    while (v > seen && !a.compare_exchange_weak(seen, v, std::memory_order_relaxed)) { }
}

// OMNI_HOLEPUNCH_V5: one queued picture: planar 4:2:0 copy of the visible picture, plus the
// 64 bytes swscale may read past it.
size_t holePaceFrameBytes(const Channel& c)
{
    const size_t bps = c.bitDepth > 8 ? 2 : 1;
    const size_t cw = size_t(c.width + 1) / 2, ch = size_t(c.height + 1) / 2;
    return (size_t(c.width) * c.height + 2 * cw * ch) * bps + 64;
}
size_t holePaceBudget()   // OMNI_HOLEPUNCH_V5: direct memory for the queue
{
    const size_t available = backendDirectAvailable();   // 0: unknown (host)
    return available ? std::min(paceDirectBudget, available / 2) : paceDirectBudget;
}

unsigned holePaceCapacity(const Channel& c)
{
    if (holeV5FlagEnabled()) {   // OMNI_HOLEPUNCH_V5: by memory budget (~3 s is the time target)
        const size_t frame = holePaceFrameBytes(c);
        return c.slotSize && frame ? unsigned(std::min<size_t>(paceMaxFramesV5, holePaceBudget() / frame)) : 0;
    }
    return c.slotSize ? unsigned(std::min<size_t>(paceMaxFrames, paceQueueBytes / c.slotSize)) : 0;
}

void holePaceRecycle(Channel& c, PaceBuf&& planes)   // OMNI_HOLEPUNCH_V5: PaceBuf, 8 spares
{
    if (c.pacedSpare.size() < (c.paceV5 ? 32u : 2u)) c.pacedSpare.push_back(std::move(planes));   // V5_REV2: 32 (was 8): fewer mappings made and dropped per refill
}

// The channel stops pacing and its queue goes (plane released, stream closed). Service thread.
// OMNI_HOLEPUNCH_V5: keepBacklog (plane released while a V5 queue paced): the decoded pictures
// stay and go back to the player (holePaceReturn); they are seconds of the video.
void holePaceClear(Channel& c, bool keepBacklog = false)
{
    c.paceOn = false; c.paceAnswer = 0; c.clock.valid = false; c.paceGenSeen = false;
    if (keepBacklog && c.paceV5) return;
    c.paceDiscarded += c.paced.size();
    c.paced.clear(); c.pacedSpare.clear();
}

void holeNote(const char* fmt, ...) __attribute__((format(printf, 1, 2)));
void holeNote(const char* fmt, ...)
{
    if (v7On()) { va_list ap; va_start(ap, fmt); v7LogFormat("OMNI HOLEPUNCH: ", fmt, ap); va_end(ap); return; }   // OMNI_HOLEPUNCH_V7_REV2: the writer thread
    va_list ap; va_start(ap, fmt);
    fprintf(stderr, "OMNI HOLEPUNCH: "); vfprintf(stderr, fmt, ap); fputc('\n', stderr);
    va_end(ap); fflush(stderr);
}

bool v8HoldOn() { static const bool on = !pbFlagOff("/data/omni/perf-b-v8-disabled.flag"); return on; }   // OMNI_PERF_B_V8
// Gives the plane back when its owner hides the video or its channel closes.
// OMNI_PERF_B_V8: hold 1 = a quality switch may follow: keep the last picture (see HolePlane::holdOwner); 0 = as
// before, but a hold already running for this channel goes on (its stream's other ends: hide, close, reset); 2 = now.
bool v8OtherStreamOpen(const Channel& c);
void holeRelease(int channel, const char* why, int hold = 0)
{
    if (channel >= 0 && channel < int(Wire::maxChannels) && plane.owner == channel) holePaceClear(channels[channel], true); // OMNI_HOLEPUNCH_V4 (V5: backlog kept)
    std::lock_guard<std::mutex> l(plane.lock);
    if (channel < 0 || plane.owner != channel) return;
    const bool keepHold = hold == 0 && plane.holdOwner == channel && nowMs() <= plane.holdUntilMs;
    if ((hold == 1 || keepHold) && v8HoldOn() && plane.attached && plane.current && plane.current->epoch == plane.epoch) {   // OMNI_PERF_B_V8
        if (plane.holdOwner != channel) {
            plane.holdOwner = channel; plane.holdUntilMs = nowMs() + 1000;
            if (plane.logLines < 40) { ++plane.logLines; holeNote("channel %d: stream ended (%s); its last picture stays until the next stream's first (1 s at most)", channel, why); }
        }
        plane.haveFrame = false;
        pbOwnsVideo.store(false, std::memory_order_relaxed);
        if (plane.ready) plane.spare.push_back(std::move(plane.ready));
        for (auto& layer : plane.paced) plane.spare.push_back(std::move(layer));
        plane.paced.clear(); plane.pacing = false; plane.clock.valid = false; plane.shownInGen = plane.posterPending = false;
        return;
    }
    plane.holdOwner = -1;
    plane.owner = -1;
    plane.haveFrame = false;
    pbOwnsVideo.store(false, std::memory_order_relaxed);   // OMNI_PERF_B_V2
    if (plane.ready) plane.spare.push_back(std::move(plane.ready));
    for (auto& layer : plane.paced) plane.spare.push_back(std::move(layer));   // OMNI_HOLEPUNCH_V4
    plane.paced.clear(); plane.pacing = false; plane.clock.valid = false; plane.shownInGen = plane.posterPending = false;
    for (auto& layer : plane.spare) if (layer) { PaceBuf().swap(layer->raw); layer->rawW = 0; }   // OMNI_HOLEPUNCH_V5: direct memory back
    plane.version++;
    if (plane.logLines < 40) {
        ++plane.logLines;
        holeNote("channel %d released the video plane (%s); frames=%llu shown=%llu dropped=%llu rectUpdates=%llu",
            channel, why, (unsigned long long)plane.frames, (unsigned long long)plane.shown,
            (unsigned long long)plane.dropped, (unsigned long long)plane.rectUpdates);
    }
}

// The visible picture of a slot as planar 4:2:0 (U and V split): the input of swscale's
// planar path, as in the WebProcess conversion. 10-bit samples are low-aligned (yuv420p10le).
// OMNI_HOLEPUNCH_V4: split out of holeCopyPlanes, shared with the pacing queue.
template <class Buffer>   // OMNI_HOLEPUNCH_V5: std::vector or PaceBuf
void holeSplitPlanes(Buffer& out, const uint8_t* y, size_t pitch, size_t coded, size_t bps, int w, int h)
{
    const int cw = (w + 1) / 2, ch = (h + 1) / 2;
    const size_t yBytes = size_t(w) * h * bps, cBytes = size_t(cw) * ch * bps;
    out.resize(yBytes + 2 * cBytes + 64);   // OMNI_HOLEPUNCH_COLOUR_V1: swscale's SIMD reads up to 8 samples past a row
    uint8_t* dy = out.data();
    for (int r = 0; r < h; r++) memcpy(dy + size_t(r) * w * bps, y + pitch * size_t(r), size_t(w) * bps);
    const uint8_t* uv = y + pitch * coded;
    for (int r = 0; r < ch; r++) {
        const uint8_t* s = uv + pitch * size_t(std::min(r, int(coded / 2) - 1));
        if (bps == 2) {
            const uint16_t* s16 = reinterpret_cast<const uint16_t*>(s);
            uint16_t* du = reinterpret_cast<uint16_t*>(dy + yBytes) + size_t(r) * cw;
            uint16_t* dv = reinterpret_cast<uint16_t*>(dy + yBytes + cBytes) + size_t(r) * cw;
            for (int i = 0; i < cw; i++) { du[i] = s16[2 * i]; dv[i] = s16[2 * i + 1]; }
        } else {
            uint8_t* du = dy + yBytes + size_t(r) * cw;
            uint8_t* dv = dy + yBytes + cBytes + size_t(r) * cw;
            for (int i = 0; i < cw; i++) { du[i] = s[2 * i]; dv[i] = s[2 * i + 1]; }
        }
    }
}
bool holePlanesFit(size_t pitch, size_t coded, size_t bps, int w, int h, size_t bytes)   // OMNI_HOLEPUNCH_V4
{
    const int cw = (w + 1) / 2;
    return w >= 2 && h >= 2 && coded >= size_t(h) && pitch >= size_t(2 * cw) * bps && pitch * coded * 3 / 2 <= bytes;
}
bool holeCopyPlanes(const uint8_t* y, const Message& f, int w, int h, size_t slotSize)
{
    const size_t bps = f.e > 8 ? 2 : 1, pitch = f.d, coded = f.c;
    if (int(f.b) < w || !holePlanesFit(pitch, coded, bps, w, h, slotSize))
        return false;
    holeSplitPlanes(plane.planes, y, pitch, coded, bps, w, h);
    plane.srcW = w; plane.srcH = h; plane.depth = bps == 2 ? 10 : 8; plane.haveFrame = true;
    plane.planesMediaUs = INT64_MIN;   // OMNI_HOLEPUNCH_V4: a V1 present carries no media time
    return true;
}

// Converts the last picture to a w x h layer in the canvas channel order and makes it the
// newest one. Service thread.
// OMNI_HOLEPUNCH_V4: with `paced`, that picture is converted and the layer joins the paced
// queue (taking the picture's planes along); else the last presented picture.
// OMNI_FAST_UPSCALE_V1: video shown larger than its own size (1080p or 1440p on a 4K screen) is
// converted at its own size through the fast paths and enlarged by nearest-pixel mapping (exact
// 2x/3x = each pixel repeated), instead of the general bilinear scaler, which cost more than a
// 60 fps frame at 4K and made 1440p YouTube drop ~40% of frames.
// OMNI_FAST_UPSCALE_V2: a small persistent pool (3 helpers + the calling thread) splits one frame
// into row bands. Created once; the console limits threads, so never per frame.
namespace {
struct OmniBandPool {
    static constexpr int kHelpers = 3;
    static constexpr bool kSequential = true;
    std::mutex m; std::condition_variable go, idle; std::function<void(int)> job; unsigned gen = 0; int pending = 0;
    OmniBandPool()
    {
        if (kSequential) return;   // no helper threads at all
        // Helpers take the creating (video service) thread's scheduling, so they are not starved.
        sched_param param {}; int policy = 0; pthread_getschedparam(pthread_self(), &policy, &param);
        for (int i = 0; i < kHelpers; ++i)
            std::thread([this, i, policy, param] {
                pthread_setschedparam(pthread_self(), policy, &param);
                unsigned seen = 0;
                for (;;) {
                    std::function<void(int)> j;
                    { std::unique_lock<std::mutex> l(m); go.wait(l, [&] { return gen != seen; }); seen = gen; j = job; }
                    j(i + 1);
                    { std::lock_guard<std::mutex> l(m); if (--pending == 0) idle.notify_one(); }
                }
            }).detach();
    }
    void run(const std::function<void(int)>& f)   // f(band) for band 0..kHelpers; band 0 on the caller
    {
        // OMNI_FAST_UPSCALE_V3: the helper threads stalled the video thread on the console (Sintel froze after
        // one frame), so bands run one after another on the caller until the pool is instrumented.
        if (kSequential) { for (int b = 0; b <= kHelpers; ++b) f(b); return; }
        { std::lock_guard<std::mutex> l(m); job = f; pending = kHelpers; ++gen; }
        go.notify_all();
        f(0);
        std::unique_lock<std::mutex> l(m); idle.wait(l, [&] { return pending == 0; });
    }
};
OmniBandPool& omniBandPool() { static OmniBandPool p; return p; }
}
// OMNI_PERF_B_V6: the upscale's output rows without helper threads (the band pool stays sequential: its threads
// stopped the browser in candidates 32/33). Columns doubled 8 at a time; rows written with streaming stores (the layer
// is only ever read back with streaming loads), so the 33 MB of a 4K picture do not evict the service's cache.
__attribute__((target("avx2"))) static void omniDouble32(uint32_t* d, const uint32_t* s, int n)
{
    const __m256i lo = _mm256_setr_epi32(0, 0, 1, 1, 2, 2, 3, 3), hi = _mm256_setr_epi32(4, 4, 5, 5, 6, 6, 7, 7);
    int x = 0;
    for (; x + 8 <= n; x += 8) {
        const __m256i v = _mm256_loadu_si256(reinterpret_cast<const __m256i*>(s + x));
        _mm256_storeu_si256(reinterpret_cast<__m256i*>(d + 2 * x), _mm256_permutevar8x32_epi32(v, lo));
        _mm256_storeu_si256(reinterpret_cast<__m256i*>(d + 2 * x + 8), _mm256_permutevar8x32_epi32(v, hi));
    }
    for (; x < n; ++x) { d[2 * x] = s[x]; d[2 * x + 1] = s[x]; }
}
__attribute__((target("avx2"))) static void omniStreamRow(uint8_t* d, const uint8_t* s, size_t bytes)
{
    if (reinterpret_cast<uintptr_t>(d) & 31) { memcpy(d, s, bytes); return; }
    size_t i = 0;
    for (; i + 64 <= bytes; i += 64) {
        _mm256_stream_si256(reinterpret_cast<__m256i*>(d + i), _mm256_loadu_si256(reinterpret_cast<const __m256i*>(s + i)));
        _mm256_stream_si256(reinterpret_cast<__m256i*>(d + i + 32), _mm256_loadu_si256(reinterpret_cast<const __m256i*>(s + i + 32)));
    }
    if (i < bytes) memcpy(d + i, s + i, bytes - i);
}
static bool omniConvertIntegerUpscale(const uint8_t* const src[4], const int srcStride[4], int srcW, int srcH, int srcFormat, int dstFormat,
    size_t bps, uint32_t colour, bool swapRB, int w, int h, uint8_t* out, int outStride)
{
    static std::mutex one; std::lock_guard<std::mutex> oneAtATime(one);   // shared contexts + one pool job
    struct Ctx { SwsContext* sws = nullptr; int key[5] {}; std::vector<uint32_t> buf; };
    static thread_local Ctx c;
    const int sstride = (srcW + 15) / 16 * 16;   // whole 16-pixel groups (swscale edge note above)
    c.buf.resize(size_t(sstride) * srcH);
    const int cw = (srcW + 1) / 2, ch = (srcH + 1) / 2;
    bool ok = false;
    if (bps == 2)
        ok = omniMain10SdrConvert(reinterpret_cast<const uint16_t*>(src[0]), size_t(srcW) * srcH, srcW,
            reinterpret_cast<const uint16_t*>(src[1]), size_t(cw) * ch, cw, reinterpret_cast<const uint16_t*>(src[2]), size_t(cw) * ch, cw,
            srcW, srcH, c.buf.data(), c.buf.size(), sstride, colour, swapRB);
    constexpr int kBands = OmniBandPool::kHelpers + 1;
    if (!ok) {   // unscaled 4:2:0 -> RGB. Each band is its own small image with its own context:
                 // swscale refuses a slice that does not start at row 0 ("Slices start in the middle").
        const int band = (srcH / kBands + 1) & ~1;   // even rows: chroma rows stay aligned to bands
        static SwsContext* ctx[kBands] {}; static int ctxKey[6] {};
        const int key[6] = { srcW, srcH, srcFormat, dstFormat, int(colourMatrix(colour, srcH) | (colourFullRange(colour) ? 0x100 : 0)), band };
        if (memcmp(key, ctxKey, sizeof key)) {
            for (int b = 0; b < kBands; ++b) {
                if (ctx[b]) sws_freeContext(ctx[b]);
                const int y0 = std::min(srcH, b * band), y1 = b == kBands - 1 ? srcH : std::min(srcH, (b + 1) * band);
                ctx[b] = y1 > y0 ? sws_getContext(srcW, y1 - y0, AVPixelFormat(srcFormat), srcW, y1 - y0, AVPixelFormat(dstFormat), SWS_BILINEAR, nullptr, nullptr, nullptr) : nullptr;
                if (y1 > y0 && !ctx[b]) { memset(ctxKey, 0, sizeof ctxKey); return false; }
                if (ctx[b]) sws_setColorspaceDetails(ctx[b], sws_getCoefficients(colourMatrix(colour, srcH)), colourFullRange(colour),
                    sws_getCoefficients(SWS_CS_DEFAULT), 1, 0, 1 << 16, 1 << 16);
            }
            memcpy(ctxKey, key, sizeof key);
        }
        std::atomic<int> rows { 0 };
        omniBandPool().run([&](int b) {
            const int y0 = std::min(srcH, b * band), y1 = b == kBands - 1 ? srcH : std::min(srcH, (b + 1) * band);
            if (y1 <= y0 || !ctx[b]) return;
            const uint8_t* bsrc[4] = { src[0] + size_t(y0) * srcStride[0], src[1] + size_t(y0 / 2) * srcStride[1], src[2] + size_t(y0 / 2) * srcStride[2], nullptr };
            uint8_t* bdst[4] = { reinterpret_cast<uint8_t*>(c.buf.data() + size_t(y0) * sstride), nullptr, nullptr, nullptr };
            int bdstStride[4] = { sstride * 4, 0, 0, 0 };
            rows += sws_scale(ctx[b], bsrc, srcStride, 0, y1 - y0, bdst, bdstStride);
        });
        ok = rows.load() == srcH;
    }
    if (!ok) return false;
    static thread_local std::vector<int> xs; static thread_local int xsKey[2] {};
    if (xsKey[0] != srcW || xsKey[1] != w) {   // source column for every output column, centre-aligned
        xs.resize(w); for (int x = 0; x < w; ++x) xs[x] = std::min(srcW - 1, int((int64_t(2 * x + 1) * srcW) / (2 * w)));
        xsKey[0] = srcW; xsKey[1] = w;
    }
    // The output is a video layer in direct memory: fast to write, very slow to read back. Each
    // output row is built in an ordinary scratch row and only ever written (never re-read) there.
    const std::vector<int>& cols = xs; const uint32_t* buf = c.buf.data();
    const int oband = (h + kBands - 1) / kBands;
    omniBandPool().run([&](int b) {
        static thread_local std::vector<uint32_t> scratch; scratch.resize(w);
        uint32_t* d = scratch.data(); int prev = -1;
        for (int y = b * oband, end = std::min(h, (b + 1) * oband); y < end; ++y) {
            const int sy = std::min(srcH - 1, int((int64_t(2 * y + 1) * srcH) / (2 * h)));
            if (sy != prev) {
                prev = sy; const uint32_t* s = buf + size_t(sy) * sstride;
                if (w == 2 * srcW && v6On()) omniDouble32(d, s, srcW);   // OMNI_PERF_B_V6
                else if (w == 2 * srcW) for (int x = 0; x < srcW; ++x) { const uint32_t v = s[x]; d[2 * x] = v; d[2 * x + 1] = v; }
                else for (int x = 0; x < w; ++x) d[x] = s[cols[x]];
            }
            if (v6On()) omniStreamRow(out + size_t(y) * outStride, reinterpret_cast<const uint8_t*>(d), size_t(w) * 4);   // OMNI_PERF_B_V6
            else memcpy(out + size_t(y) * outStride, d, size_t(w) * 4);
        }
        _mm_sfence();   // OMNI_PERF_B_V6: the streamed rows are visible before the layer is published
    });
    return true;
}
// OMNI_SWS_BANDS_V1: a scaled conversion (4K video in a window: 3840x2160 -> 3072x1728, ~12.7 ms on one
// core, with 60 pictures a second to convert) split into 4 bands of OUTPUT rows. Each band has its own
// full-size context and asks swscale for only its rows (sws_receive_slice), so results are the same as
// one call. Threads are created per frame with the caller's scheduling (helpers at a lower priority
// starved behind the video thread before; OMNI_HDR_BANDS_V1 works this way). swscale's own thread pool
// is not used for the same reason. Kill switch: /data/omni/sws-bands-disabled.flag.
static void omniSwsNoFree(void*, uint8_t*) {}
namespace {
struct OmniSwsBand { SwsContext* c; AVFrame* in; AVFrame* out; int y0, y1, srcH; bool ok; };
static void omniSwsBandRun(OmniSwsBand& b)
{
    b.ok = b.y1 <= b.y0 || (sws_frame_start(b.c, b.out, b.in) >= 0 && sws_send_slice(b.c, 0, unsigned(b.srcH)) >= 0
        && sws_receive_slice(b.c, unsigned(b.y0), unsigned(b.y1 - b.y0)) >= 0);
    if (b.y1 > b.y0) sws_frame_end(b.c);
}
static void* omniSwsBandThread(void* p) { omniSwsBandRun(*static_cast<OmniSwsBand*>(p)); return nullptr; }
}
static bool omniSwsBands(int srcW, int srcH, int srcFormat, int w, int h, int dstFormat, uint32_t colour,
    const uint8_t* const src[4], const int srcStride[4], uint8_t* dst, int dstStride)
{
    static const bool off = access("/data/omni/sws-bands-disabled.flag", F_OK) == 0;
    if (off || h < 256 || srcH < 2) return false;
    constexpr int kBands = 4;
    static SwsContext* ctx[kBands] {}; static int ctxKey[7] {};
    const int key[7] = { srcW, srcH, srcFormat, w, h, dstFormat, int(colourMatrix(colour, srcH) | (colourFullRange(colour) ? 0x100 : 0)) };
    if (memcmp(key, ctxKey, sizeof key)) {
        memset(ctxKey, 0, sizeof ctxKey);
        for (int b = 0; b < kBands; ++b) {
            if (ctx[b]) sws_freeContext(ctx[b]);
            ctx[b] = sws_getContext(srcW, srcH, AVPixelFormat(srcFormat), w, h, AVPixelFormat(dstFormat), SWS_BILINEAR, nullptr, nullptr, nullptr);
            if (!ctx[b]) return false;
            sws_setColorspaceDetails(ctx[b], sws_getCoefficients(colourMatrix(colour, srcH)), colourFullRange(colour),
                sws_getCoefficients(SWS_CS_DEFAULT), 1, 0, 1 << 16, 1 << 16);
        }
        memcpy(ctxKey, key, sizeof key);
        holeNote("scaled conversion in %d bands: %dx%d -> %dx%d", kBands, srcW, srcH, w, h);
    }
    const int align = std::max(1, int(sws_receive_slice_alignment(ctx[0])));
    const int step = ((h + kBands - 1) / kBands + align - 1) / align * align;
    const int cw = (srcW + 1) / 2, ch = (srcH + 1) / 2;
    const size_t bps = srcFormat == AV_PIX_FMT_YUV420P10LE ? 2 : 1;
    const size_t planeBytes[3] = { size_t(srcStride[0]) * srcH, size_t(srcStride[1]) * ch, size_t(srcStride[2]) * ch };
    (void)cw; (void)bps;
    OmniSwsBand band[kBands] {}; bool ready = true;
    for (int b = 0; b < kBands; ++b) {
        AVFrame* in = av_frame_alloc(); AVFrame* out = av_frame_alloc();
        band[b] = { ctx[b], in, out, std::min(h, b * step), std::min(h, (b + 1) * step), srcH, false };
        if (!in || !out) { ready = false; continue; }
        in->format = srcFormat; in->width = srcW; in->height = srcH;
        for (int i = 0; i < 3; ++i) {
            in->data[i] = const_cast<uint8_t*>(src[i]); in->linesize[i] = srcStride[i];
            in->buf[i] = av_buffer_create(const_cast<uint8_t*>(src[i]), planeBytes[i], omniSwsNoFree, nullptr, AV_BUFFER_FLAG_READONLY);
            ready = ready && in->buf[i];
        }
        out->format = dstFormat; out->width = w; out->height = h; out->data[0] = dst; out->linesize[0] = dstStride;
        out->buf[0] = av_buffer_create(dst, size_t(dstStride) * h, omniSwsNoFree, nullptr, 0);
        ready = ready && out->buf[0];
    }
    bool ok = ready;
    if (ready) {
        pthread_t t[kBands]; bool started[kBands] = {};
        pthread_attr_t attr; const bool attrOk = pthread_attr_init(&attr) == 0 && pthread_attr_setinheritsched(&attr, PTHREAD_INHERIT_SCHED) == 0;
        for (int b = 1; b < kBands; ++b) started[b] = attrOk && pthread_create(&t[b], &attr, omniSwsBandThread, &band[b]) == 0;
        if (attrOk) pthread_attr_destroy(&attr);
        omniSwsBandRun(band[0]);
        for (int b = 1; b < kBands; ++b) { if (started[b]) pthread_join(t[b], nullptr); else omniSwsBandRun(band[b]); }
        for (int b = 0; b < kBands; ++b) ok = ok && band[b].ok;
        static int fails = 0; if (!ok && fails++ < 4) holeNote("scaled conversion bands failed; one-call fallback");
    }
    for (int b = 0; b < kBands; ++b) { av_frame_free(&band[b].in); av_frame_free(&band[b].out); }
    return ok;
}
// ---- OMNI_PERF_B_V3: the RGBA8 copy of an HDR picture only when something can show it ----------------------
// While the display's PQ set shows a full-screen HDR video (auto mode) and the shell composes record-only (V1), nothing
// reads a picture's RGBA8 image (px): the presenter tiles hdrPx and blends translucent page pixels in PQ. The ~5.4 ms
// 8-bit pass per 4K picture is then skipped (pxState 0). Whoever needs px later (a frame that cannot go to the PQ set,
// e.g. a large translucent control bar) marks the need (v3SdrNeededUs): the service makes the copy again for new
// pictures, makes it for the queued ones that lack it (holeV3Backfill, oldest first), and a reader that still finds
// none makes it itself (holeLayerPx, one call of swscale on its own context: the safety net, counted as lazy).
bool v3SkipNow(const HoleLayer& layer, int w, int h)   // service thread
{
    if (!v3On() || !layer.hdrValid || omniHDRFormatPQ() || !omniHDRPQAvailable() || int64_t(w) * h <= int64_t(2560) * 1440) return false;
    if (!v1LastComposeRecordOnly.load(std::memory_order_relaxed)) return false;
    const int64_t now = v7MonoUs(), shown = v3PqShownUs.load(std::memory_order_relaxed), need = v3SdrNeededUs.load(std::memory_order_relaxed);
    return shown && now - shown < 500000 && (!need || now - need > 2000000);
}
#ifndef OMNI_HW_NO_SWSCALE
// The source of a layer's picture (raw: planar 4:2:0, as holeSplitPlanes writes it). False when it has none.
bool holeRawSource(const HoleLayer& L, const uint8_t* src[4], int srcStride[4], int& srcFormat, int& dstFormat)
{
    const int srcW = L.rawW, srcH = L.rawH, cw = (srcW + 1) / 2, ch = (srcH + 1) / 2;
    const size_t bps = L.rawDepth > 8 ? 2 : 1;
    if (srcW <= 0 || srcH <= 0 || L.w != srcW || L.h != srcH || L.raw.size() < (size_t(srcW) * srcH + 2 * size_t(cw) * ch) * bps) return false;
    const uint8_t* yp = L.raw.data(); const uint8_t* up = yp + size_t(srcW) * srcH * bps;
    src[0] = yp; src[1] = up; src[2] = up + size_t(cw) * ch * bps; src[3] = nullptr;
    srcStride[0] = int(srcW * bps); srcStride[1] = srcStride[2] = int(cw * bps); srcStride[3] = 0;
    srcFormat = bps == 2 ? AV_PIX_FMT_YUV420P10LE : AV_PIX_FMT_YUV420P; dstFormat = L.v3SwapRB ? AV_PIX_FMT_RGBA : AV_PIX_FMT_BGRA;
    return true;
}
// One swscale call on a context of the calling thread (never plane.sws or the band contexts: those are the service's).
bool holeSdrOwnContext(HoleLayer& L)
{
    const uint8_t* src[4]; int srcStride[4]; int srcFormat, dstFormat;
    if (!holeRawSource(L, src, srcStride, srcFormat, dstFormat)) return false;
    struct Ctx { SwsContext* sws = nullptr; int key[6] {}; ~Ctx() { if (sws) sws_freeContext(sws); } };
    static thread_local Ctx c;
    const int key[6] = { L.rawW, L.rawH, srcFormat, dstFormat, int(colourMatrix(L.v3Colour, L.rawH) | (colourFullRange(L.v3Colour) ? 0x100 : 0)), 1 };
    if (!c.sws || memcmp(key, c.key, sizeof key)) {
        if (c.sws) sws_freeContext(c.sws);
        c.sws = sws_getContext(L.rawW, L.rawH, AVPixelFormat(srcFormat), L.w, L.h, AVPixelFormat(dstFormat), SWS_BILINEAR, nullptr, nullptr, nullptr);
        if (!c.sws) return false;
        sws_setColorspaceDetails(c.sws, sws_getCoefficients(colourMatrix(L.v3Colour, L.rawH)), colourFullRange(L.v3Colour),
            sws_getCoefficients(SWS_CS_DEFAULT), 1, 0, 1 << 16, 1 << 16);
        memcpy(c.key, key, sizeof key);
    }
    uint8_t* dst[4] = { L.px.data(), nullptr, nullptr, nullptr }; int dstStride[4] = { L.stride, 0, 0, 0 };
    return sws_scale(c.sws, src, srcStride, 0, L.rawH, dst, dstStride) == L.h;
}
#endif
// Service thread: the copy holeConvert skipped, made as holeConvert makes it (bands; then the thread's own context).
bool holeSdrInto(HoleLayer& L)
{
#ifdef OMNI_HW_NO_SWSCALE
    (void)L; return false;
#else
    const uint8_t* src[4]; int srcStride[4]; int srcFormat, dstFormat;
    if (!holeRawSource(L, src, srcStride, srcFormat, dstFormat)) return false;
    if (omniSwsBands(L.rawW, L.rawH, srcFormat, L.w, L.h, dstFormat, L.v3Colour, src, srcStride, L.px.data(), L.stride)) return true;
    return holeSdrOwnContext(L);
#endif
}
// Any thread but the service: px of a layer, made first if it was skipped (waits for the service when it is making it).
const uint8_t* holeLayerPx(const HoleLayer* l)
{
    if (l->pxState.load(std::memory_order_acquire) == 2) return l->px.data();
    v3SdrNeededUs.store(v7MonoUs(), std::memory_order_relaxed);
    std::lock_guard<std::mutex> made(l->pxMutex);
    if (l->pxState.load(std::memory_order_acquire) != 2) {
        HoleLayer& L = const_cast<HoleLayer&>(*l);   // only px and pxState change, under pxMutex
#ifndef OMNI_HW_NO_SWSCALE
        if (!holeSdrOwnContext(L))
#endif
            for (int y = 0; y < L.h; ++y) memset(L.px.data() + size_t(y) * size_t(L.stride), 0, size_t(L.w) * 4);   // no source left: black, never stale memory
        L.pxState.store(2, std::memory_order_release);
        pbV3Lazy.fetch_add(1, std::memory_order_relaxed);
    }
    return l->px.data();
}
// Service thread (holePaceStep): while an 8-bit copy was needed in the last 2 s, the picture on screen and the queued
// ones lacking it get it, oldest first, at most 3 per loop (~5 ms each at 4K) so decoding and conversion go on.
void holeV3Backfill()
{
    const int64_t need = v3SdrNeededUs.load(std::memory_order_relaxed);
    if (!need || v7MonoUs() - need > 2000000) return;
    HoleLayer* todo[3]; int n = 0;
    {
        std::lock_guard<std::mutex> l(plane.lock);
        auto want = [&](HoleLayer* L) { if (L && n < 3 && L->pxState.load(std::memory_order_relaxed) == 0) todo[n++] = L; };
        want(plane.current.get());
        for (auto& L : plane.paced) want(L.get());
    }
    // Layers stay allocated: only this thread takes them off `spare` for reuse, and none is freed meanwhile.
    for (int i = 0; i < n; ++i) {
        HoleLayer& L = *todo[i];
        std::lock_guard<std::mutex> made(L.pxMutex);
        if (L.pxState.load(std::memory_order_acquire) != 0) continue;
        L.pxState.store(1, std::memory_order_release);
        if (!holeSdrInto(L)) for (int y = 0; y < L.h; ++y) memset(L.px.data() + size_t(y) * size_t(L.stride), 0, size_t(L.w) * 4);
        L.pxState.store(2, std::memory_order_release);
        pbV3Backfilled.fetch_add(1, std::memory_order_relaxed);
    }
}
// OMNI_PERF_B_V1 (under plane.lock): a layer the shell is done with goes back to `spare`, unless it is the picture of
// a record-only canvas whose before-flip has not run yet (plane.flipPin): that one waits in flipPinRetired.
void planeDiscard(std::unique_ptr<HoleLayer>&& p)
{
    if (!p) return;
    if (p.get() == plane.flipPin) { if (plane.flipPinRetired) plane.spare.push_back(std::move(plane.flipPinRetired)); plane.flipPinRetired = std::move(p); return; }
    plane.spare.push_back(std::move(p));
}
void planeReleaseFlipPin()   // under plane.lock
{
    plane.flipPin = nullptr;
    if (plane.flipPinRetired) plane.spare.push_back(std::move(plane.flipPinRetired));
}

bool holeConvert(int w, int h, bool swapRB, PacedFrame* paced = nullptr, uint64_t resizedSeq = 0, bool resizedFirst = false)
{
#ifdef OMNI_HW_NO_SWSCALE
    (void)w; (void)h; (void)swapRB; (void)paced;
    return false;
#else
    OmniServiceTraceScope wholeSetup(60);
    std::unique_ptr<HoleLayer> layer;
    {
        if(omniPipelineScope) omniPipelineScope(40,61,0,0);
        std::lock_guard<std::mutex> l(plane.lock);
        if(omniPipelineScope) omniPipelineScope(41,61,0,0);
        if (!plane.spare.empty()) { layer = std::move(plane.spare.back()); plane.spare.pop_back(); }
    }
    if (!layer) { OmniServiceTraceScope alloc(62); layer = std::make_unique<HoleLayer>(); }
    layer->w = w; layer->h = h;
    // OMNI_HOLEPUNCH_COLOUR_V1: rows of whole 16-pixel groups. swscale's unscaled 4:2:0 -> RGB
    // path leaves the last w % 8 pixels of every row unwritten when the stride is exactly w * 4
    // (stale pixels at the right edge of a 1:1 plane, e.g. 854 wide); compose reads the stride.
    layer->stride = (w + 15) / 16 * 16 * 4;
    { OmniServiceTraceScope resize(63, size_t(layer->stride) * h); if (!layer->px.ensure(size_t(layer->stride) * h)) return false; }
    const double started = nowMs();
    const int srcW = paced ? paced->w : plane.srcW, srcH = paced ? paced->h : plane.srcH;   // OMNI_HOLEPUNCH_V4
    const size_t bps = (paced ? paced->depth : plane.depth) > 8 ? 2 : 1;
    const int cw = (srcW + 1) / 2, ch = (srcH + 1) / 2;
    // OMNI_HOLEPUNCH_COLOUR_V1: the owner stream's matrix and range (swscale's default is BT.601
    // limited; HD video is BT.709), set once per context.
    const uint32_t colour = plane.owner >= 0 ? channels[plane.owner].colour : 0;
    const int srcFormat = bps == 2 ? AV_PIX_FMT_YUV420P10LE : AV_PIX_FMT_YUV420P, dstFormat = swapRB ? AV_PIX_FMT_RGBA : AV_PIX_FMT_BGRA;
    const int key[7] = { srcW, srcH, srcFormat, w, h, dstFormat, int(colourMatrix(colour, srcH) | (colourFullRange(colour) ? 0x100 : 0)) };
    if (!plane.sws || memcmp(key, plane.swsKey, sizeof key)) {
        if (plane.sws) sws_freeContext(plane.sws);
        plane.sws = sws_getContext(srcW, srcH, AVPixelFormat(srcFormat), w, h, AVPixelFormat(dstFormat), SWS_BILINEAR, nullptr, nullptr, nullptr);
        if (plane.sws) {
            sws_setColorspaceDetails(plane.sws, sws_getCoefficients(colourMatrix(colour, srcH)), colourFullRange(colour),
                sws_getCoefficients(SWS_CS_DEFAULT), 1, 0, 1 << 16, 1 << 16);
            memcpy(plane.swsKey, key, sizeof key);
            if (key[6] != plane.swsLoggedColour && plane.logLines < 40) {   // once per colour, not per rect size
                ++plane.logLines; plane.swsLoggedColour = key[6];
                holeNote("conversion %dx%d -> %dx%d, matrix %d, %s range", srcW, srcH, w, h, colourMatrix(colour, srcH), colourFullRange(colour) ? "full" : "limited");
            }
        }
    }
    // OMNI_HDR_LEAN_V1: the PQ layer first. While the display is PQ and the native-size picture converts,
    // nothing shows the RGBA8 image: compose copies it into the canvas and the hand-off compares the canvas
    // with it (equal either way), the HDR tiler reads hdrPx. So the 8-bit pass (~6 ms at 4K) is skipped.
    // /data/omni/hdr-keep-sdr-copy.flag restores the double conversion.
    const double tPre = nowMs();   // OMNI_CONVERT_TIMING_V1 (diagnostic)
    layer->hdrValid = false;
    if ((omniHDRFormatPQ() || omniHDRPQAvailable()) && bps == 2 && srcW == w && srcH == h   // OMNI_HDR_AUTO_V1: also for the PQ set
        && colourPrimaries(colour) == 9 && colourTransfer(colour) == 16 && colourMatrix(colour, srcH) == 9) {
        const uint16_t* y16 = reinterpret_cast<const uint16_t*>(paced ? paced->planes.data() : plane.planes.data());
        const size_t yn = size_t(srcW) * srcH, cn = size_t(cw) * ch;
        if (layer->hdrPx.ensure(size_t(layer->stride) * h))
            layer->hdrValid = omniHDRConvert10(y16, yn, srcW, y16 + yn, cn, cw, y16 + yn + cn, cn, cw, w, h,
                reinterpret_cast<uint32_t*>(layer->hdrPx.data()), size_t(layer->stride) * h / 4, layer->stride / 4, colour);
    }
    if (omniHDRFormatPQ() && bps == 2) {   // OMNI_HDR_DIAG_V1: why (not) the PQ layer, once per distinct decision
        static uint64_t lastKey = ~0ull; static unsigned notes = 0;
        const uint64_t key = (uint64_t(srcW == w && srcH == h) << 40) | (uint64_t(colourPrimaries(colour) & 255) << 32) | (uint64_t(colourTransfer(colour) & 255) << 24)
            | (uint64_t(colourMatrix(colour, srcH) & 255) << 16) | (uint64_t(layer->hdrValid) << 8);
        if (key != lastKey && notes < 16) { lastKey = key; ++notes;
            holeNote("HDR decision: src %dx%d layer %dx%d primaries %d transfer %d matrix %d word %08x -> PQ layer %s (%.2f ms so far)", srcW, srcH, w, h,
                colourPrimaries(colour), colourTransfer(colour), colourMatrix(colour, srcH), colour, layer->hdrValid ? "made" : "not made", nowMs() - started); }
    }
    const double tHdr = nowMs();
    static const bool keepSdrCopy = access("/data/omni/hdr-keep-sdr-copy.flag", F_OK) == 0;
    bool ok = layer->hdrValid && !keepSdrCopy && omniHDRFormatPQ();   // OMNI_HDR_AUTO_V1: auto mode keeps the SDR copy (shown when not fullscreen)
    layer->pxState.store(2, std::memory_order_relaxed); layer->v3Colour = colour; layer->v3SwapRB = swapRB;   // OMNI_PERF_B_V3 (fixed PQ: px unread, as before)
    if (!ok && paced && v3SkipNow(*layer, w, h)) { ok = true; layer->pxState.store(0, std::memory_order_relaxed); pbV3Skipped.fetch_add(1, std::memory_order_relaxed); }
    if (plane.sws && !ok) {
        const uint8_t* yp = paced ? paced->planes.data() : plane.planes.data();
        const uint8_t* up = yp + size_t(srcW) * srcH * bps;
        const uint8_t* src[4] = { yp, up, up + size_t(cw) * ch * bps, nullptr };
        int srcStride[4] = { int(srcW * bps), int(cw * bps), int(cw * bps), 0 };
        uint8_t* dst[4] = { layer->px.data(), nullptr, nullptr, nullptr };
        int dstStride[4] = { layer->stride, 0, 0, 0 };   // OMNI_HOLEPUNCH_COLOUR_V1
        // Guarded d0648ba SDR conversion; all rejected cases retain the existing scaler.
        bool fast=false;
        if(bps==2 && srcW==w && srcH==h) fast=omniMain10SdrConvert(
            reinterpret_cast<const uint16_t*>(src[0]),size_t(srcW)*srcH,srcW,
            reinterpret_cast<const uint16_t*>(src[1]),size_t(cw)*ch,cw,
            reinterpret_cast<const uint16_t*>(src[2]),size_t(cw)*ch,cw,w,h,
            reinterpret_cast<uint32_t*>(dst[0]),size_t(layer->stride)*h/4,layer->stride/4,colour,swapRB);
        // OMNI_FAST_UPSCALE_V1: any enlargement skips the general scaler (shrinking keeps it)
        const bool enlarge = !fast && srcW > 0 && srcH > 0 && w >= srcW && h >= srcH && (w > srcW || h > srcH);
        bool upscaled = enlarge && omniConvertIntegerUpscale(src, srcStride, srcW, srcH, srcFormat, dstFormat, bps, colour, swapRB, w, h, dst[0], dstStride[0]);
        if (upscaled) { static int notes = 0; if (notes++ < 4) holeNote("fast upscale %dx%d -> %dx%d", srcW, srcH, w, h); }
        ok = fast || upscaled || omniSwsBands(srcW, srcH, srcFormat, w, h, dstFormat, colour, src, srcStride, dst[0], dstStride[0])   // OMNI_SWS_BANDS_V1
            || sws_scale(plane.sws, src, srcStride, 0, srcH, dst, dstStride) == h;
        diagnosticTrace(164,paced?paced->mediaUs:INT64_MIN,fast,srcFormat,dstFormat);

    }
    {   // OMNI_CONVERT_TIMING_V1: setup / PQ / 8-bit split, 300-conversion averages
        static double aSet = 0, aHdr = 0, aSdr = 0; static unsigned n = 0, notes = 0;
        const double tEnd = nowMs(); aSet += tPre - started; aHdr += tHdr - tPre; aSdr += tEnd - tHdr;
        if (++n == 300) { if (notes++ < 20) holeNote("convert split (300 avg): setup %.2f PQ %.2f 8-bit %.2f ms (layer %dx%d, PQ %s)", aSet / 300, aHdr / 300, aSdr / 300, w, h, layer->hdrValid ? "made" : "no"); aSet = aHdr = aSdr = 0; n = 0; }
    }
    const double ms = nowMs() - started;
    std::lock_guard<std::mutex> l(plane.lock);
    if (!ok) { plane.spare.push_back(std::move(layer)); return false; }
    layer->epoch = plane.epoch;
    layer->mediaUs = plane.planesMediaUs;   // OMNI_HOLEPUNCH_V4
    layer->rawW = 0;
    if (paced) {
        diagnosticTrace(5,paced->mediaUs,int64_t(ms*1000),w,h);
        // shown at its time by holePaceSelect; no redraw yet
        layer->mediaUs = paced->mediaUs;
        std::swap(layer->raw, paced->planes);
        layer->rawW = paced->w; layer->rawH = paced->h; layer->rawDepth = paced->depth;
        plane.paced.push_back(std::move(layer));
        plane.layerW = w; plane.layerH = h;
        plane.paceConvertMs += ms; plane.paceConverts++;
        if (v7On()) v7Op(ms, "convert");   // OMNI_HOLEPUNCH_V7_REFLIP (V7_REV2: V7 on only)
        return true;
    }
    if (resizedSeq) {
        // Resize the SAME held poster; preserve identity and raw planes for
        // subsequent fullscreen transitions instead of waiting for frame two.
        layer->v8Seq = resizedSeq; layer->v8First = resizedFirst;
        layer->raw.assign(plane.planes.begin(), plane.planes.end());
        layer->rawW = srcW; layer->rawH = srcH; layer->rawDepth = plane.depth;
        diagnosticTrace(166,layer->mediaUs,resizedSeq,w,h);
    }
    if (plane.ready) { plane.spare.push_back(std::move(plane.ready)); plane.dropped++; }
    plane.ready = std::move(layer);
    plane.layerW = w; plane.layerH = h;
    plane.convertMs += ms;
    plane.version++;
    return true;
#endif
}

// Present for channel `index`: frame/slot null = rect only (claim or move). Service thread.
bool holePresent(int index, const Message* frame, const uint8_t* slot, size_t slotSize, int w, int h,
    const HoleRect& r, std::string& why)
{
    bool pacedPoster = false;
    bool swapRB = false;
    {
        std::lock_guard<std::mutex> l(plane.lock);
        if (!plane.attached) why = "shell has no video plane";
        else if (plane.owner >= 0 && plane.owner != index && plane.holdOwner != plane.owner) why = "another video is shown";   // OMNI_PERF_B_V8: a held picture is taken over
        else if (r.w < 2 || r.h < 2 || r.w > Wire::holeMaxSide || r.h > Wire::holeMaxSide || int64_t(r.w) * r.h > Wire::holeMaxPixels)
            why = "video rect out of range";
        if (!why.empty()) {
            plane.refused++;
            if (plane.logLines < 40) { ++plane.logLines; holeNote("refused channel %d: %s (rect %dx%d at %d,%d)", index, why.c_str(), r.w, r.h, r.x, r.y); }
            if (plane.owner != index) return false;
        }
        if (why.empty() && plane.holdOwner >= 0) {   // OMNI_PERF_B_V8: the next stream: same epoch, the held picture shows until its first
            if (plane.logLines < 40) { ++plane.logLines; holeNote("channel %d takes over the held picture of channel %d", index, plane.holdOwner); }
            plane.owner = index; plane.holdOwner = -1; plane.haveFrame = false; plane.version++;
        }
        if (why.empty() && plane.owner != index) {
            plane.owner = index;
            plane.epoch++;
            plane.haveFrame = false;            // never show the previous owner's picture
            plane.version++;
            if (plane.logLines < 40) { ++plane.logLines; holeNote("channel %d shows its video under the page (rect %dx%d at %d,%d)", index, r.w, r.h, r.x, r.y); }
        } else if (why.empty() && plane.rect != r && !frame) {
            plane.rectUpdates++;
        }
        if (why.empty() && plane.rect != r) { plane.rect = r; plane.version++; }
        swapRB = plane.swapRB;
        pacedPoster = plane.pacing && plane.current && plane.current->rawW
            && plane.current->epoch == plane.epoch;
    }
    if (!why.empty()) { holeRelease(index, why.c_str()); return false; }
    if (frame && !holeCopyPlanes(slot, *frame, w, h, slotSize)) { why = "picture layout"; holeRelease(index, why.c_str()); return false; }
    // OMNI_HOLEPUNCH_V2: a rect-only size change is rescaled later (holeRescaleTick), at most
    // every 50 ms: during a re-layout every tick brings a new size, and a full conversion per
    // rect update put this thread behind its clients.
    if (!frame && (plane.haveFrame || pacedPoster) && (r.w != plane.layerW || r.h != plane.layerH)) {
        if (plane.rescalePending) plane.rescalesSkipped++;
        plane.rescalePending = true;
    }
    if (frame && plane.haveFrame) {
        plane.rescalePending = false;
        if (!holeConvert(r.w, r.h, swapRB)) { why = "conversion failed"; holeRelease(index, why.c_str()); return false; }
    }
    if (frame) {
        std::lock_guard<std::mutex> l(plane.lock);
        plane.frames++;
        if (!(plane.frames % 300) && plane.logLines < 40) {
            ++plane.logLines;
            holeNote("shell frames=%llu shown=%llu dropped=%llu rectUpdates=%llu refused=%llu convertAvgMs=%.2f composeAvgMs=%.2f layer=%dx%d source=%dx%d rescales=%llu coalesced=%llu busySlots=%u/%u",
                (unsigned long long)plane.frames, (unsigned long long)plane.shown, (unsigned long long)plane.dropped,
                (unsigned long long)plane.rectUpdates, (unsigned long long)plane.refused, plane.convertMs / plane.frames,
                plane.composes ? plane.composeMs / plane.composes : 0.0, plane.layerW, plane.layerH, plane.srcW, plane.srcH,
                (unsigned long long)plane.rescales, (unsigned long long)plane.rescalesSkipped, busySlots(channels[index]), Wire::outputSlots);
        }
    }
    return true;
}

// OMNI_HOLEPUNCH_V2: one client that stopped reading must not stop this thread (and with
// it every other channel). Wait at most 200 ms for room, then close that channel: the
// client sees EOF and falls back to software decoding.
bool sendMsg(Channel& c, const Message& m)
{
    const char* p = reinterpret_cast<const char*>(&m);
    size_t left = sizeof m;
    const double deadline = nowMs() + 200;
    while (left) {
        ssize_t n = send(c.serverFd, p, left, MSG_DONTWAIT);
        if (n < 0 && errno == EINTR) continue;
        if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
            pollfd pfd { c.serverFd, POLLOUT, 0 };
            const int wait = int(deadline - nowMs());
            if (wait > 0 && poll(&pfd, 1, wait) >= 0) continue;
            note("channel %d: client not reading for 200 ms; closing the channel", c.index);
            shutdown(c.serverFd, SHUT_RDWR);   // the poll loop sees EOF and resets the channel
            return false;
        }
        if (n <= 0) return false;
        p += n; left -= size_t(n);
    }
    return true;
}

// OMNI_HOLEPUNCH_V4: for reports a later one replaces: skipped when the socket is full.
bool trySendMsg(Channel& c, const Message& m)
{
    pollfd pfd { c.serverFd, POLLOUT, 0 };
    if (poll(&pfd, 1, 0) != 1 || !(pfd.revents & POLLOUT)) return false;
    return sendMsg(c, m);
}

void sendError(Channel& c, int rc, const std::string& stage)
{
    hudDecoderErrors.fetch_add(1,std::memory_order_relaxed); // existing error path only; user-approved counter
    Message m; m.type = Type::Error; m.status = rc ? rc : -1;
    snprintf(m.text, sizeof m.text, "%s", stage.c_str());
    note("channel %d error rc=0x%08x at %s", c.index, unsigned(m.status), m.text);
    c.failed = true;
    sendMsg(c, m);
}

void writeRendezvous()
{
    std::string text = "omni-hw 1\npid " + std::to_string(getpid()) + "\n";
    for (auto& c : channels)
        text += "channel " + std::to_string(c.index) + " " + std::to_string(c.generation) + " " + std::to_string(c.clientFd) + "\n";
    std::string tmp = dir + "/service.tmp", path = dir + "/service";
    FILE* f = fopen(tmp.c_str(), "w");
    if (!f) return;
    fputs(text.c_str(), f); fflush(f); fsync(fileno(f)); fclose(f);
    rename(tmp.c_str(), path.c_str());
}

void v5Wait(Channel& c);   // OMNI_PERF_B_V5
void releaseStream(Channel& c, bool closeDecoder = true)   // OMNI_PERF_B_V5: closeDecoder false: the worker's open closes it
{
    if (c.index >= 0 && unsigned(c.index) < unsigned(Wire::maxChannels)) liveStreamBytes[c.index].store(0, std::memory_order_relaxed); // OMNI_TAB_MEDIA_RELEASE_V1
    if (closeDecoder) { v5Wait(c); c.decoder.close(); }
    if (c.shm) { munmap(c.shm, c.shmSize); c.shm = nullptr; }
    if (c.shmFd >= 0) { close(c.shmFd); c.shmFd = -1; }
    c.shmSize = 0; c.slotOffset = c.slotSize = 0;
    for (bool& b : c.slotBusy) b = false;
    c.waiting.clear(); c.pending.clear(); c.draining = false; c.failed = false;
    c.consumedCount = c.consumedSent = 0; c.runnable = false; // OMNI_HOLEPUNCH_V5
    c.holeAnswer = 0; // OMNI_HOLEPUNCH_V1 (the plane itself is released by the callers)
    c.holeShown = c.holePresents = 0; c.holeLastFrameMs = 0; c.holeQuietLogged = false; // OMNI_HOLEPUNCH_V2
    holePaceClear(c); c.discardUs = INT64_MIN; c.posterPending = false; c.paceCap = 0; // OMNI_HOLEPUNCH_V4
}

// New socket pair + generation; the old client end is gone with its process
// or was closed by Close. Called at start and whenever a client leaves.
bool resetChannel(Channel& c)
{
    holeRelease(c.index, "decode channel closed"); // OMNI_HOLEPUNCH_V1
    releaseStream(c);   // OMNI_PERF_B_V5: waits for an open of this channel still running on the worker
    if (c.serverFd >= 0) close(c.serverFd);
    if (c.clientFd >= 0) close(c.clientFd);
    c.serverFd = c.clientFd = -1; c.connected = false;
    int sv[2];
    // CLOEXEC: a process this one starts must not inherit channel ends, or a
    // client's close would never reach us as EOF.
    if (socketpair(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0, sv)) { note("socketpair failed errno=%d", errno); return false; }
    c.serverFd = sv[0]; c.clientFd = sv[1];
    // OMNI_HOLEPUNCH_V3: headroom for a client whose main thread is busy for a while (FreeBSD's
    // AF_UNIX default is ~8 KB, ~85 messages). Best effort; the bounded sends (V2) remain.
    for (int fd : sv) {
        int bytes = 64 * 1024;
        setsockopt(fd, SOL_SOCKET, SO_SNDBUF, &bytes, sizeof bytes);
        setsockopt(fd, SOL_SOCKET, SO_RCVBUF, &bytes, sizeof bytes);
    }
    c.generation++;
    unlink((dir + "/claim-" + std::to_string(c.index)).c_str());
    return true;
}

bool freeSlot(Channel& c, uint32_t& slot)
{
    for (uint32_t i = 0; i < Wire::outputSlots; i++) if (!c.slotBusy[i]) { slot = i; return true; }
    return false;
}

// OMNI_HOLEPUNCH_V4: pts (track time base) -> media microseconds.
int64_t holePaceMediaUs(const Channel& c, int64_t pts)
{
    if (c.tbNum <= 0 || c.tbDen <= 0) return pts;
    const __int128 v = __int128(pts) * c.tbNum * 1000000 / c.tbDen;
    return v > INT64_MAX ? INT64_MAX : v < INT64_MIN + 1 ? INT64_MIN + 1 : int64_t(v);
}

// OMNI_HOLEPUNCH_V4: no room for one more paced picture: the next decode waits (runWaiting
// resumes it when the shell has shown or dropped one).
// OMNI_HOLEPUNCH_V5_REV3: the next picture goes to the shell's queue, not to an output slot: a
// decode needs no free slot. Before, pictures the player held in all six slots (decoded before
// pacing began, ahead of a held playhead) stopped paced decoding until the playhead hold timed out.
bool holePaceQueues(const Channel& c) { return c.paceOn && plane.owner == c.index; }
bool holePaceFull(const Channel& c)
{
    if (!c.paceOn || plane.owner != c.index) return false;   // owner: written on this thread only
    if (c.paced.size() >= c.paceCap) return true;
    // OMNI_HOLEPUNCH_V5: and ~3 s of pictures ahead of the clock are enough (by media time).
    return c.paceV5 && c.clock.valid && !c.paced.empty() && c.paced.back().mediaUs - c.clock.at(nowMs()) >= paceAheadUs;
}
// OMNI_HOLEPUNCH_V5: decoded pictures of an ended V5 pacing run wait to go back to the player
// (holePaceReturn); later pictures must not overtake them.
bool holePaceBacklog(const Channel& c) { return c.paceV5 && !c.paceOn && !c.paced.empty(); }

// OMNI_HOLEPUNCH_V4: while the channel paces, its pictures go to the queue (no slot, no Frame
// message). True when the picture was taken (queued, or discarded: before the seek target,
// decode-only, without a timestamp).
bool holePaceEmit(Channel& c, const Picture& p)
{
    if (!c.paceOn || plane.owner != c.index) return false;
    c.paceDecoded++;
    int64_t pts = INT64_MIN;
    bool nonDisplaying = false;
    if (!c.pending.empty()) {
        pts = c.pending.front().pts; nonDisplaying = c.pending.front().nonDisplaying;
        c.pending.pop_front();
    }
    const size_t bps = p.bitDepth > 8 ? 2 : 1;
    const int64_t mediaUs = pts == INT64_MIN ? INT64_MIN : holePaceMediaUs(c, pts);
    if (nonDisplaying || pts == INT64_MIN || (c.discardUs != INT64_MIN && mediaUs + 1 < c.discardUs)
        || !holePlanesFit(p.pitchBytes, p.codedHeight, bps, c.width, c.height, p.size)) {
        c.paceDiscarded++;
        return true;
    }
    PacedFrame f;
    if (!c.pacedSpare.empty()) { f.planes = std::move(c.pacedSpare.back()); c.pacedSpare.pop_back(); }
    const uint64_t refusals = paceDirectRefusals.load();   // OMNI_HOLEPUNCH_V5
    holeSplitPlanes(f.planes, p.data, p.pitchBytes, p.codedHeight, bps, c.width, c.height);
    if (paceDirectRefusals.load() != refusals && c.paceCap > 3) {   // no more direct memory: stop growing
        c.paceCap = unsigned(std::max<size_t>(3, c.paced.size() + 1));
        if (plane.logLines < 40) { ++plane.logLines; holeNote("channel %d: direct memory refused a queued picture; queue capped at %u frames (heap copy for this one)", c.index, c.paceCap); }
    }
    f.w = c.width; f.h = c.height; f.depth = bps == 2 ? 10 : 8; f.mediaUs = mediaUs; f.pts = pts;
    if (v7On()) f.queuedMs = nowMs();   // OMNI_HOLEPUNCH_V7_REFLIP: raw drop reasons (V7_REV2: V7 on only)
    c.paced.push_back(std::move(f));
    diagnosticTrace(3,mediaUs,c.paced.size(),c.waiting.size(),c.index);
    return true;
}

// Copy a decoded picture into a shared slot and tell the client. Caller
// guarantees a free slot.
void emit(Channel& c, const Picture& p)
{
    diagnosticTrace(2,c.index,c.pending.empty()?INT64_MIN:holePaceMediaUs(c,c.pending.front().pts),p.notDisplayed,c.pending.size());
    if (p.notDisplayed) return;          // VP9 hidden-frame output (console-verified flag)
    if (holePaceEmit(c, p)) return;      // OMNI_HOLEPUNCH_V4: queued for the shell
    uint32_t slot = 0;
    if (!freeSlot(c, slot)) { if (!c.pending.empty()) c.pending.pop_front(); return; }   // OMNI_HOLEPUNCH_V5_REV3: never into a busy slot
    if (p.size > c.slotSize) { sendError(c, -10, "picture larger than slot"); return; }
    memcpy(c.shm + c.slotOffset + size_t(slot) * c.slotSize, p.data, p.size);
    c.slotBusy[slot] = true;
    Message m; m.type = Type::Frame;
    m.a = slot; m.b = uint32_t(c.decoder.width()); m.c = p.codedHeight; m.d = p.pitchBytes; m.e = p.bitDepth;
    c.slotFrame[slot] = m; // OMNI_HOLEPUNCH_V1
    // Pictures leave in display order: pair with the smallest pending pts.
    if (!c.pending.empty()) {
        m.pts = c.pending.front().pts;
        m.f = c.pending.front().nonDisplaying ? Wire::FrameNonDisplaying : 0;
        c.pending.pop_front();
    } else {
        m.pts = INT64_MIN;
    }
    sendMsg(c, m);
}

// ---- OMNI_PERF_B_V5: decoder configure off the service thread ---------------------------------------------
// Backend::open (QueryDecoderMemoryInfo, direct memory, CreateDecoder: 57-324 ms measured) ran on the one service
// thread, so every other channel's decoding, conversions and pacing stopped meanwhile (start-up, quality switches on a
// second channel, a tab's video coming back). Now one configure worker thread, created once (never per call), with
// the service thread's scheduling, opens the decoder; the service thread answers Configured when it is done. The
// channel's other messages wait (in order) meanwhile. Only once the process's compute queue exists (the first open
// stays on the service thread). Backend is used by one thread at a time: the worker only while v5Configuring, the
// service thread never then (v5Wait before any close). Kill switch: /data/omni/perf-b-v5-disabled.flag.
struct V5Worker {
    std::mutex m; std::condition_variable work, idle;
    std::deque<Channel*> jobs, done;
    int wake[2] = { -1, -1 };
    int state = 0;   // 0 not started, 1 running, -1 could not start (configures stay on the service thread)
};
V5Worker v5w;
Codec v5Codec(const Message& in) { return in.a == 0 ? Codec::H264 : in.a == 1 ? Codec::HEVC : Codec::VP9; }
void* v5WorkerMain(void*)
{
    for (;;) {
        Channel* c;
        { std::unique_lock<std::mutex> l(v5w.m); v5w.work.wait(l, [] { return !v5w.jobs.empty(); }); c = v5w.jobs.front(); }
        const Message in = c->v5Msg;
        std::string stage;
        const int rc = c->decoder.open(v5Codec(in), int(in.b), in.c > 8 ? 10 : 8, int(in.d), int(in.e), stage);
        {
            std::lock_guard<std::mutex> l(v5w.m);
            c->v5Rc = rc; c->v5Stage = stage;
            v5w.jobs.pop_front(); v5w.done.push_back(c);
        }
        v5w.idle.notify_all();
        const char b = 1; (void)!write(v5w.wake[1], &b, 1);
    }
    return nullptr;
}
bool v5Start()   // service thread
{
    if (v5w.state) return v5w.state > 0;
    v5w.state = -1;
    if (pipe(v5w.wake)) { v5w.wake[0] = v5w.wake[1] = -1; return false; }
    for (int fd : v5w.wake) { fcntl(fd, F_SETFL, fcntl(fd, F_GETFL) | O_NONBLOCK); fcntl(fd, F_SETFD, FD_CLOEXEC); }
    pthread_attr_t attr; pthread_t t;
    bool ok = pthread_attr_init(&attr) == 0;
    ok = ok && pthread_attr_setinheritsched(&attr, PTHREAD_INHERIT_SCHED) == 0 && pthread_attr_setstacksize(&attr, 512 * 1024) == 0
        && pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED) == 0 && pthread_create(&t, &attr, v5WorkerMain, nullptr) == 0;
    pthread_attr_destroy(&attr);
    if (!ok) { close(v5w.wake[0]); close(v5w.wake[1]); v5w.wake[0] = v5w.wake[1] = -1; note("configure worker not started; configures stay on the service thread"); return false; }
    v5w.state = 1;
    note("configure worker started (decoder opens off the service thread)");
    return true;
}
// Service thread: the channel's open (if one is running) is over before the channel's decoder is touched again.
void v5Wait(Channel& c)
{
    if (!c.v5Configuring) return;
    std::unique_lock<std::mutex> l(v5w.m);
    v5w.idle.wait(l, [&] { return std::find(v5w.jobs.begin(), v5w.jobs.end(), &c) == v5w.jobs.end(); });
    v5w.done.erase(std::remove(v5w.done.begin(), v5w.done.end(), &c), v5w.done.end());
    c.v5Configuring = false; c.v5Held.clear();   // nobody waits for this answer any more (closed, reset)
}
void handleConfigureFinish(Channel& c, const Message& in, int rc, const std::string& stage);
// Service thread: Configure goes to the worker (false: handle it here, as before).
bool v5BeginConfigure(Channel& c, const Message& in)
{
    if (!v5On() || !backendQueueReady() || !v5Start()) { pbV5Sync.fetch_add(1, std::memory_order_relaxed); return false; }
    releaseStream(c, false);   // all but the decoder (the open closes the previous one first, on the worker)
    c.width = int(in.d); c.height = int(in.e); c.bitDepth = in.c > 8 ? 10 : 8; c.colour = in.f;   // as handleConfigure
    c.v5Configuring = true; c.v5Msg = in; c.v5StartedMs = nowMs();
    { std::lock_guard<std::mutex> l(v5w.m); v5w.jobs.push_back(&c); }
    v5w.work.notify_one();
    pbV5Async.fetch_add(1, std::memory_order_relaxed);
    return true;
}
void handle(Channel& c, const Message& in);
// Service thread, every loop: finished opens are answered, then the messages held for them handled.
void v5Complete()
{
    if (v5w.state <= 0) return;
    char sink[64]; while (read(v5w.wake[0], sink, sizeof sink) > 0) { }
    std::deque<Channel*> finished;
    std::vector<std::pair<int, std::string>> results;
    { std::lock_guard<std::mutex> l(v5w.m); finished.swap(v5w.done); for (Channel* c : finished) results.emplace_back(c->v5Rc, c->v5Stage); }
    for (size_t i = 0; i < finished.size(); ++i) {
        Channel& c = *finished[i];
        if (!c.v5Configuring) continue;
        c.v5Configuring = false;
        v7AtomicMax(pbV5MaxUs, int64_t((nowMs() - c.v5StartedMs) * 1000));
        handleConfigureFinish(c, c.v5Msg, results[i].first, results[i].second);
        while (!c.v5Configuring && !c.v5Held.empty()) { const Message m = c.v5Held.front(); c.v5Held.pop_front(); handle(c, m); }
    }
}

void handleConfigure(Channel& c, const Message& in)
{
    releaseStream(c);
    Codec codec = in.a == 0 ? Codec::H264 : in.a == 1 ? Codec::HEVC : Codec::VP9;
    int depth = in.c > 8 ? 10 : 8, w = int(in.d), h = int(in.e);
    c.width = w; c.height = h; // OMNI_HOLEPUNCH_V1
    c.bitDepth = depth;        // OMNI_HOLEPUNCH_V5
    c.colour = in.f;           // OMNI_HOLEPUNCH_COLOUR_V1
    std::string stage;
    int rc = c.decoder.open(codec, int(in.b), depth, w, h, stage);
    handleConfigureFinish(c, in, rc, stage);
}
void handleConfigureFinish(Channel& c, const Message& in, int rc, const std::string& stage)   // OMNI_PERF_B_V5: the part after the open
{
    const int depth = in.c > 8 ? 10 : 8, w = int(in.d), h = int(in.e);
    Message out; out.type = Type::Configured;
    if (rc) {
        out.status = rc; snprintf(out.text, sizeof out.text, "%s", stage.c_str());
        note("channel %d open failed rc=0x%08x at %s (%dx%d %d-bit codec %u)", c.index, unsigned(rc), stage.c_str(), w, h, depth, in.a);
        sendMsg(c, out);
        return;
    }
    const size_t bps = depth > 8 ? 2 : 1;
    c.slotSize = uint32_t(alignUp(alignUp(size_t(w) * bps, 256) * alignUp(size_t(h), 32) * 3 / 2, 4096));
    c.slotOffset = Wire::inputRingBytes;   // OMNI_HOLEPUNCH_V5: input ring first
    c.shmSize = c.slotOffset + size_t(c.slotSize) * Wire::outputSlots;
    c.shmFd = shmCreate(c.shmSize);
    if (c.shmFd >= 0) {
        void* p = mmap(nullptr, c.shmSize, PROT_READ | PROT_WRITE, MAP_SHARED, c.shmFd, 0);
        c.shm = p == MAP_FAILED ? nullptr : static_cast<uint8_t*>(p);
    }
    if (!c.shm) {
        out.status = -errno ? -errno : -1; snprintf(out.text, sizeof out.text, "shared memory");
        sendMsg(c, out); releaseStream(c); return;
    }
    out.a = uint32_t(c.shmFd); out.b = uint32_t(c.shmSize); out.c = 0;
    out.d = c.slotOffset; out.e = c.slotSize; out.f = Wire::outputSlots;
    snprintf(out.text, sizeof out.text, "ok");
    if (c.index >= 0 && unsigned(c.index) < unsigned(Wire::maxChannels)) liveStreamBytes[c.index].store(c.shmSize, std::memory_order_relaxed); // OMNI_TAB_MEDIA_RELEASE_V1
    note("channel %d open %dx%d %d-bit codec %u, shm %zu bytes", c.index, w, h, depth, in.a, c.shmSize);
    sendMsg(c, out);
}

// Returns false when the message must wait for a free output slot.
bool process(Channel& c, const Message& in)
{
    if (c.failed && in.type != Type::Flush && in.type != Type::Configure && in.type != Type::Release) return true;
    switch (in.type) {
    case Type::Submit: {
        uint32_t slot;
        if ((!holePaceQueues(c) && !freeSlot(c, slot)) || holePaceFull(c) || holePaceBacklog(c)) return false;   // OMNI_HOLEPUNCH_V4: or the shell's queue (V5: or a backlog; V5_REV3: no slot while queued)
        // OMNI_HOLEPUNCH_V5: a = offset in the input ring, b = size
        if (!c.decoder.isOpen() || in.b == 0 || in.b > Wire::inputMaxAu || in.a > Wire::inputRingBytes - in.b) { sendError(c, -11, "bad submit"); return true; }
        const uint8_t* au = c.shm + in.a;
        Picture pic; bool got = false;
        int rc = c.decoder.decode(au, in.b, uint64_t(in.pts), pic, got);
        c.consumedCount++;   // OMNI_HOLEPUNCH_V5: told in one Consumed per service loop (holeFlushConsumed)
        if (rc) { sendError(c, rc, "Decode"); return true; }
        if (!(in.c & Wire::Hidden)) {
            Pending p { in.pts, (in.c & Wire::NonDisplaying) != 0 };
            auto it = c.pending.begin();
            while (it != c.pending.end() && it->pts <= p.pts) ++it;
            c.pending.insert(it, p);
        }
        if (got) emit(c, pic);
        return true;
    }
    case Type::Drain: {
        for (;;) {
            uint32_t slot;
            if ((!holePaceQueues(c) && !freeSlot(c, slot)) || holePaceFull(c) || holePaceBacklog(c)) return false;    // resume after a Release (V4: or a shown frame; V5: backlog; V5_REV3)
            Picture pic; bool got = false;
            int rc = c.decoder.flushOne(pic, got);
            if (rc) { sendError(c, rc, "Flush"); return true; }
            if (!got) break;
            emit(c, pic);
        }
        c.pending.clear();
        Message m; m.type = Type::Drained; sendMsg(c, m);
        return true;
    }
    default:
        return true;
    }
}

// OMNI_HOLEPUNCH_V5: a V5 pacing run ended (pacing off, plane released) with decoded pictures still
// queued: they go back to the player first, oldest first, as ordinary Frame messages (NV12 /
// 16-bit two-plane in output slots, as decoded), so a paint path or the per-tick presents (V3)
// carry on from where the shell stopped instead of seconds later. Submits wait meanwhile
// (holePaceBacklog). True when nothing is left.
bool holePaceReturn(Channel& c)
{
    while (holePaceBacklog(c)) {
        uint32_t slot;
        if (!c.shm || !freeSlot(c, slot)) return false;   // the next Release resumes it (runWaiting)
        PacedFrame f = std::move(c.paced.front());
        c.paced.pop_front();
        const size_t bps = f.depth > 8 ? 2 : 1;
        const int w = f.w, h = f.h, cw = (w + 1) / 2, ch = (h + 1) / 2;
        const size_t pitch = alignUp(size_t(w) * bps, 256), coded = size_t(h + (h & 1));
        if (pitch * coded * 3 / 2 > c.slotSize || f.planes.size() < (size_t(w) * h + 2 * size_t(cw) * ch) * bps) { c.paceDiscarded++; continue; }
        uint8_t* y = c.shm + c.slotOffset + size_t(slot) * c.slotSize;
        const uint8_t* sy = f.planes.data();
        const uint8_t* su = sy + size_t(w) * h * bps;
        const uint8_t* sv = su + size_t(cw) * ch * bps;
        for (int r = 0; r < h; r++) memcpy(y + pitch * size_t(r), sy + size_t(r) * w * bps, size_t(w) * bps);
        for (int r = 0; r < ch; r++) {
            uint8_t* d = y + pitch * coded + pitch * size_t(r);
            for (int i = 0; i < cw; i++) {
                memcpy(d + (2 * size_t(i)) * bps, su + (size_t(r) * cw + size_t(i)) * bps, bps);
                memcpy(d + (2 * size_t(i) + 1) * bps, sv + (size_t(r) * cw + size_t(i)) * bps, bps);
            }
        }
        Message m; m.type = Type::Frame;
        m.a = slot; m.b = uint32_t(w); m.c = uint32_t(coded); m.d = uint32_t(pitch); m.e = bps == 2 ? 10 : 8; m.f = 0; m.pts = f.pts;
        c.slotBusy[slot] = true;
        c.slotFrame[slot] = m;
        holePaceRecycle(c, std::move(f.planes));
        if (!sendMsg(c, m)) return false;
    }
    return true;
}

void holeFlushConsumed(Channel& c);
// OMNI_HOLEPUNCH_V5: at most ~8 ms per call, so a refill of seconds of pictures after a stall of
// the player does not hold up the conversions due meanwhile; the service loop goes on at once
// (runnable). Once a V5 queue holds 1 s ahead of the clock, one message per call: the loop
// looks for due conversions between every two decodes. Consumed goes out after every decode
// (when the socket has room), as V4's did: the client must learn early how far decoding got.
void runWaiting(Channel& c)
{
    if (!holePaceReturn(c)) { c.runnable = false; return; }   // OMNI_HOLEPUNCH_V5: the backlog first
    const double now = nowMs();
    const bool ahead = c.paceOn && c.paceV5 && c.clock.valid && !c.paced.empty() && c.paced.back().mediaUs - c.clock.at(now) >= 1000000;
    const double until = ahead ? now : now + (v7On() ? 2 : 8);   // OMNI_HOLEPUNCH_V7_REFLIP: 2 ms of decodes at a time (V5: 8)
    c.runnable = false;
    for (;;) {
        if (c.waiting.empty()) break;
        const bool timed = v7On();   // OMNI_HOLEPUNCH_V7_REV2: V7 on only
        const double opStarted = timed ? nowMs() : 0;
        const bool done = process(c, c.waiting.front());
        if (timed) v7Op(nowMs() - opStarted, "held submit (decode)");   // OMNI_HOLEPUNCH_V7_REFLIP
        if (!done) break;
        c.waiting.pop_front();
        holeFlushConsumed(c);
        if (!c.waiting.empty() && nowMs() > until) { c.runnable = true; return; }
    }
}

// OMNI_HOLEPUNCH_V5: the cumulative Consumed, without waiting: a client whose main thread is busy
// for seconds finds one message, not one per access unit (and never a closed channel).
void holeFlushConsumed(Channel& c)
{
    if (c.serverFd < 0 || c.consumedSent == c.consumedCount) return;
    Message m; m.type = Type::Consumed; m.a = c.consumedCount;
    if (trySendMsg(c, m)) c.consumedSent = c.consumedCount;
}

// OMNI_HOLEPUNCH_V2: rect-only size changes, coalesced; `idle` = nothing else to read.
void holeRescaleTick(bool idle)
{
    if (!plane.rescalePending) return;
    const double now = nowMs();
    if (!idle && now - plane.lastRescaleMs < 50) return;
    HoleRect r; bool swapRB; int owner;
    {
        std::lock_guard<std::mutex> l(plane.lock);
        r = plane.rect; swapRB = plane.swapRB; owner = plane.owner;
    }
    plane.rescalePending = false;
    uint64_t resizedSeq = 0; bool resizedFirst = false;
    if (owner >= 0 && plane.pacing) {   // OMNI_HOLEPUNCH_V4: playing, the next frame comes at the new size
        if (!channels[owner].clock.valid || channels[owner].clock.playing) return;
        std::lock_guard<std::mutex> l(plane.lock);   // paused: the picture on screen
        const HoleLayer* cur = plane.current.get();
        if (!cur || !cur->rawW || cur->epoch != plane.epoch) return;
        plane.planes.assign(cur->raw.begin(), cur->raw.end());
        plane.srcW = cur->rawW; plane.srcH = cur->rawH; plane.depth = cur->rawDepth;
        resizedSeq = cur->v8Seq; resizedFirst = cur->v8First;
        plane.planesMediaUs = cur->mediaUs; plane.haveFrame = true;
    }
    if (owner < 0 || !plane.haveFrame || (r.w == plane.layerW && r.h == plane.layerH)) return;
    plane.lastRescaleMs = now;
    plane.rescales++;
    if (!holeConvert(r.w, r.h, swapRB, nullptr, resizedSeq, resizedFirst)) holeRelease(owner, "rescale failed");
}

// OMNI_HOLEPUNCH_V2: the owner's channel got no picture for a while: say what it holds.
void holeWatchdog()
{
    int owner;
    int held = -1;   // OMNI_PERF_B_V8
    { std::lock_guard<std::mutex> l(plane.lock); owner = plane.owner; if (plane.holdOwner >= 0 && nowMs() > plane.holdUntilMs) held = plane.holdOwner; }
    if (held >= 0) { holeRelease(held, "held picture: no next stream within 1 s", 2); return; }
    if (owner < 0) return;
    Channel& c = channels[owner];
    if (!c.holeLastFrameMs || c.holeQuietLogged || nowMs() - c.holeLastFrameMs < 1000) return;
    c.holeQuietLogged = true;
    if (plane.logLines >= 40) return;
    ++plane.logLines;
    holeNote("channel %d: no picture presented for %.0f ms (paused, or the player stalled); busySlots=%u/%u waitingSubmits=%zu pendingPts=%zu presents=%u shown=%u",
        c.index, nowMs() - c.holeLastFrameMs, busySlots(c), Wire::outputSlots, c.waiting.size(), c.pending.size(), c.holePresents, c.holeShown);
}

// ---- OMNI_HOLEPUNCH_V4: pacing on the service thread ----------------------------------------
// HolePacing to the player: when shown changed (at most every 100 ms) and every 250 ms.
void holePaceReport(Channel& c, double now, bool force = false)
{
    if (!c.paceOn && !force) return;
    uint64_t shown, dropped, late; size_t waiting; int64_t media, newestLayer;
    uint32_t startupFlags = 0, startupGeneration = 0;
    {
        std::lock_guard<std::mutex> l(plane.lock);
        if (plane.owner == c.index && plane.pacing && plane.clock.valid) {
            startupFlags = 1 | (plane.startupPresentationReady ? 6 : 0);
            // Selection is not readiness: this only breaks the held-poster/page-hole
            // circular wait. Bits 0..2 still require a valid awake presenter.
            if (plane.shownInGen) startupFlags |= 8;
            startupGeneration = plane.startupGeneration;
        }
        shown = plane.pacedShown; dropped = plane.pacedDropped; late = plane.pacedLate; waiting = plane.paced.size();
        media = plane.current ? plane.current->mediaUs : INT64_MIN;
        newestLayer = plane.paced.empty() ? INT64_MIN : plane.paced.back()->mediaUs;   // OMNI_HOLEPUNCH_V5_REV2
    }
    const bool changed = shown != c.paceReportedShown;
    if (changed) { c.holeLastFrameMs = now; c.holeQuietLogged = false; }   // V2 service watchdog
    // OMNI_PERF_B_V8: the first picture of a generation is on screen: say so at once (once per generation), not after
    // the 100 ms report throttle: the player ends its switch / start hold on it.
    if (!(startupFlags & 8)) c.v8FirstShownSent = false;
    const bool firstShown = (startupFlags & 8) && !c.v8FirstShownSent && v8HoldOn();
    if (!force && !firstShown && !(changed && now - c.paceReportMs >= 100) && now - c.paceReportMs < 250) return;
    Message m; m.type = Type::HolePacing; m.status = c.paceOn ? 0 : -1;
    m.a = uint32_t(shown); m.b = uint32_t(dropped + c.paceDroppedRaw); m.c = uint32_t(late);
    m.d = uint32_t(waiting + c.paced.size()); m.e = uint32_t(c.paceDecoded); m.f = c.paceCap; m.pts = media;
    // OMNI_HOLEPUNCH_V5_REV2: g = decoded media queued ahead of the clock, ms (the player's start hold)
    const int64_t newest = std::max(c.paced.empty() ? INT64_MIN : c.paced.back().mediaUs, newestLayer);
    if (c.clock.valid && newest != INT64_MIN) m.g = uint32_t(std::clamp<int64_t>((newest - c.clock.at(now)) / 1000, 0, 600000));
    snprintf(m.text, sizeof m.text, "%s", c.paceOn ? "ok" : "stopped");
    memcpy(m.text + 16, &startupFlags, sizeof startupFlags);
    memcpy(m.text + 20, &startupGeneration, sizeof startupGeneration);
    diagnosticTrace(115,c.index,startupFlags,startupGeneration,c.clock.playing);
    if (force ? sendMsg(c, m) : trySendMsg(c, m)) { diagnosticTrace(113,c.index,c.paceOn,c.paced.size(),c.clock.playing); c.paceReportMs = now; c.paceReportedShown = shown; if (startupFlags & 8) c.v8FirstShownSent = true; }
}

// OMNI_HOLEPUNCH_V7_REV2: the window's V7 lines (service thread, V7 on): one with the counters; one
// with what took 100 ms or more (shell stalls, service bursts, slow page copies, where the main
// thread spent its longest stall), only when there was some; the threads once.
void holeV7Log(double now)
{
    const unsigned reflips = v7Reflips.exchange(0), handOffs = v7HandOffs.exchange(0);
    const int64_t reflipUs = v7ReflipUs.exchange(0), handOffUs = v7HandOffUs.exchange(0);
    // Display refresh measured from the flips; the content's rate from the shown pictures. A
    // picture must go now and then only when the content is faster than the display (60.00 fps
    // on 59.94 Hz: one every ~16.7 s): those cadence drops are counted as rate mismatch.
    int64_t frameUs = v7FrameUs.load();
    if (v8On()) {   // OMNI_HOLEPUNCH_V8_CADENCE: the mean step of the window (V7: the smallest)
        const int64_t sum = v8StepUs.exchange(0); const unsigned n = v8Steps.exchange(0);
        if (n >= 10) frameUs = sum / n;
    }
    const int64_t span = v7FlipSpanUs.exchange(0), vblanks = v7FlipVblanks.exchange(0);
    v7RunSpanUs += span; v7RunVblanks += vblanks;
    const double hz = span > 0 && vblanks >= 120 ? 1e6 * double(vblanks) / double(span) : 0, fps = frameUs > 0 ? 1e6 / double(frameUs) : 0;
    const double runHz = v7RunSpanUs > 0 && v7RunVblanks >= 600 ? 1e6 * double(v7RunVblanks) / double(v7RunSpanUs) : 0;
    const unsigned stall = v7DropStall.exchange(0), cadence = v7DropCadence.exchange(0), stale = v7DropStale.exchange(0);
    const double displayHz = runHz > 0 ? runHz : hz;
    if (runHz > 59.4 && runHz < 60.6) v7VblankNs.store(int64_t(1e9 / runHz), std::memory_order_relaxed);   // vblankAfter uses it from now on
    if (displayHz > 0 && fps > displayHz && fps < 2 * displayHz) v7MismatchBudget += (fps - displayHz) * (now - plane.paceWindowMs) / 1000;
    const unsigned mismatch = unsigned(std::min<double>(cadence, std::floor(v7MismatchBudget + 0.5)));
    v7MismatchBudget = std::max(0.0, v7MismatchBudget - mismatch);
    V7Log& log = v7Log();
    holeNote("pacing V7: reflips=%u (avgMs=%.2f maxMs=%.2f) busy=%u stale=%u, hand-offs %u (avgMs=%.2f maxMs=%.2f); ticks: longestGapMs=%.0f stalls>50ms=%u stalledMs=%.0f; "
        "raw drops: shellBehind=%u decodedLate=%u other=%u; select drops: stalled=%u cadence=%u (rateMismatch=%u) stale=%u; display %.3f Hz, content %.2f fps; "
        "service: yields=%u sleeps=%u longestOpMs=%.1f (%s); page paints=%u maxMs=%.1f over50ms=%u afterIdle=%u; log: lines=%u bytes=%llu writeMaxMs=%.1f lagMaxMs=%.1f dropped=%u",
        reflips, reflips ? double(reflipUs) / 1000 / reflips : 0.0, double(v7ReflipMaxUs.exchange(0)) / 1000, v7ReflipBusy.exchange(0), v7ReflipStale.exchange(0),
        handOffs, handOffs ? double(handOffUs) / 1000 / handOffs : 0.0, double(v7HandOffMaxUs.exchange(0)) / 1000,
        double(v7PollGapMaxUs.exchange(0)) / 1000, v7Stalls.exchange(0), double(v7StallUs.exchange(0)) / 1000,
        v7RawShellBehind, v7RawDecodedLate, v7RawOther, stall, cadence, mismatch, stale, displayHz, fps,
        v7ServiceYields, v7ServiceSleeps, v7OpMaxMs, v7OpMaxWhat,
        v7Paints.exchange(0), double(v7PaintMaxUs.exchange(0)) / 1000, v7PaintsSlow.exchange(0), v7PaintsSlowAfterIdle.exchange(0),
        log.lines.exchange(0), (unsigned long long)log.bytes.exchange(0), double(log.writeMaxUs.exchange(0)) / 1000, double(log.lagMaxUs.exchange(0)) / 1000, log.droppedWindow.exchange(0));
    v7RawShellBehind = v7RawDecodedLate = v7RawOther = 0;
    v7ServiceYields = v7ServiceSleeps = 0; v7OpMaxMs = 0; v7OpMaxWhat = "none";
    if (v8On())   // OMNI_HOLEPUNCH_V8_CADENCE
        holeNote("pacing V8: presenter flips of the due picture: %u without a canvas (%u more with the main thread stalled), %u waited for a hand-off; canvases brought up to a newer picture: %u at the hand-off, %u before the flip; "
            "flips one vblank late %u, early %u; flip lead %.1f ms, compose %.1f ms, hand-off %.1f ms, re-flip %.1f ms (recent maxima); content %.3f fps (mean interval), display %.3f Hz",
            v8CadenceReflips.exchange(0), v8StallReflips.exchange(0), v8ReflipWaits.exchange(0), v8Reselects.exchange(0), v8BeforeFlips.exchange(0), v8FlipsLate.exchange(0), v8FlipsEarly.exchange(0),
            double(v8LeadUs.load()) / 1000, double(v8ComposeUs.load()) / 1000, double(v8HandOffCostUs.load()) / 1000, double(v8ReflipCostUs.load()) / 1000, fps, displayHz);
    {   // OMNI_PERF_B: one aggregated line per window (no per-frame logging)
        const unsigned cr = pbComposeRecord.exchange(0), cb = pbComposeBlend.exchange(0), pr = pbPrepares.exchange(0);
        const int64_t cru = pbComposeRecordUs.exchange(0), cbu = pbComposeBlendUs.exchange(0), pru = pbPrepareUs.exchange(0);
        holeNote("pacing B: draws asked by the plane: changed=%u poster=%u no-presenter=%u mask-stale=%u, not asked (presenter busy %u, mask current %u); presenter owns the video %s; "
            "composes record-only %u (avgMs=%.2f) blended %u (avgMs=%.2f); mask checks %u (avgMs=%.2f); record-only hand-offs %u, filled by the shell %u, before-flip used the composed picture %u, frames without a picture %u; "
            "8-bit copies skipped %u, made later %u, made on demand %u; PQ frames with a large translucent area %u; PQ refused for a translucent area %u (largest %u px); "
            "configures on the worker %u, on the service thread %u (longest %.1f ms), messages held %u",
            pbPollVersion.exchange(0), pbPollPoster.exchange(0), pbPollNoPresenter.exchange(0), pbPollLive.exchange(0), pbPollSkipBusy.exchange(0), pbPollSkipLive.exchange(0),
            pbOwnsVideo.load() ? "yes" : "no", cr, cr ? double(cru) / 1000 / cr : 0.0, cb, cb ? double(cbu) / 1000 / cb : 0.0, pr, pr ? double(pru) / 1000 / pr : 0.0,
            pbHandOffRecordOnly.exchange(0), pbRecordFilled.exchange(0), pbFlipPinFallback.exchange(0), pbFlipNoPicture.exchange(0),
            pbV3Skipped.exchange(0), pbV3Backfilled.exchange(0), pbV3Lazy.exchange(0), pbV3PqForced.exchange(0), pbPqRefusedMix.exchange(0), pbPqRefusedMixMax.exchange(0),
            pbV5Async.exchange(0), pbV5Sync.exchange(0), double(pbV5MaxUs.exchange(0)) / 1000, pbV5Deferred.exchange(0));
    }
    static bool threadsLogged = false;
    if (!threadsLogged && v7MainThreadInfo.known.load(std::memory_order_acquire) && v7ServiceThreadInfo.known.load(std::memory_order_acquire)) {
        threadsLogged = true;
        const bool presenter = v7PresenterThreadInfo.known.load(std::memory_order_acquire);
        holeNote("pacing V7 threads: UI main priority %d policy %d CPUs 0x%llx (error %d); service priority %d policy %d CPUs 0x%llx (error %d); presenter %s%d policy %d CPUs 0x%llx (error %d)",
            v7MainThreadInfo.priority, v7MainThreadInfo.policy, v7MainThreadInfo.cpus, v7MainThreadInfo.cpuError,
            v7ServiceThreadInfo.priority, v7ServiceThreadInfo.policy, v7ServiceThreadInfo.cpus, v7ServiceThreadInfo.cpuError,
            presenter ? "priority " : "(not seen yet) priority ", presenter ? v7PresenterThreadInfo.priority : 0, presenter ? v7PresenterThreadInfo.policy : 0,
            presenter ? v7PresenterThreadInfo.cpus : 0ull, presenter ? v7PresenterThreadInfo.cpuError : 0);
    }
    std::vector<V7Event> events;
    int64_t longest, phase[v7Phases];
    {
        std::lock_guard<std::mutex> l(v7TraceLock);
        events.swap(v7Events);
        longest = v7StallLongestUs; std::copy(v7StallPhaseUs, v7StallPhaseUs + v7Phases, phase); v7StallLongestUs = 0;
    }
    std::string stalls, bursts, paints;
    unsigned counts[3] = {};
    char item[48];
    for (const auto& e : events) {
        if (e.kind != 2 && e.durUs < 100000) continue;
        if (++counts[e.kind] > 8) continue;
        const double at = double(e.atUs) / 1000 - v7ServiceStartMs, dur = double(e.durUs) / 1000;
        if (e.kind == 1) snprintf(item, sizeof item, " %.0f+%.0f(%u msgs)", at, dur, e.count);
        else snprintf(item, sizeof item, " %.0f+%.0f", at, dur);
        (e.kind == 0 ? stalls : e.kind == 1 ? bursts : paints) += item;
    }
    if (!stalls.empty() || !bursts.empty() || !paints.empty() || longest >= 100000)
        holeNote("pacing V7 timeline (ms since the service started, start+duration, 100 ms or more): shell stalls:%s; service bursts:%s; page paints over 50 ms:%s; "
            "longest stall %.0f ms: outside tick %.0f (run loop: WebKit IPC, callbacks, timers), tick %.0f, uBlock %.0f, input %.0f, page paint %.0f, draw %.0f",
            stalls.empty() ? " none" : stalls.c_str(), bursts.empty() ? " none" : bursts.c_str(), paints.empty() ? " none" : paints.c_str(),
            double(longest) / 1000, double(phase[0]) / 1000, double(phase[1]) / 1000, double(phase[2]) / 1000, double(phase[3]) / 1000, double(phase[4]) / 1000, double(phase[5]) / 1000);
}

// The 5 s pacing line (window counts).
void holePaceLog(Channel& c, double now, size_t layers)
{
    plane.paceQueueSum += double(c.paced.size() + layers); plane.paceQueueSamples++;
    if (c.clock.valid && c.clock.playing)   // OMNI_HOLEPUNCH_V5
        plane.paceAheadMinMs = std::min(plane.paceAheadMinMs, c.paced.empty() ? 0.0 : double(c.paced.back().mediaUs - c.clock.at(now)) / 1000);
    if (now - plane.paceWindowMs < 5000) return;
    uint64_t shown, dropped, late;
    { std::lock_guard<std::mutex> l(plane.lock); shown = plane.pacedShown; dropped = plane.pacedDropped; late = plane.pacedLate; }
    dropped += c.paceDroppedRaw;
    if (plane.paceWindowMs && plane.paceLogLines < 240 && omniReleaseDiagnostics()) {
        ++plane.paceLogLines;
        holeNote("pacing shown=%llu dropped=%llu late=%llu queueAvg=%.1f clockDriftMs=%.1f updates=%u (%.1f s, channel %d, capacity %u, vblank %s, convertAvgMs=%.2f, discarded=%llu, playing=%d, aheadMinMs=%.0f, directMiB=%.0f, driftSteadyMs=%.1f, driftAfterGap=%u, driftSettleMs=%.1f)",
            (unsigned long long)(shown - plane.paceWinShown), (unsigned long long)(dropped - plane.paceWinDropped),
            (unsigned long long)(late - plane.paceWinLate), plane.paceQueueSamples ? plane.paceQueueSum / double(plane.paceQueueSamples) : 0.0,
            plane.paceDriftMaxMs, plane.paceUpdates, (now - plane.paceWindowMs) / 1000, c.index, c.paceCap,
            vblankReported() ? "presenter" : "estimated", plane.paceConverts ? plane.paceConvertMs / double(plane.paceConverts) : 0.0,
            (unsigned long long)c.paceDiscarded, c.clock.playing, std::isfinite(plane.paceAheadMinMs) ? plane.paceAheadMinMs : -1.0,
            double(paceDirectBytes.load()) / 1048576, plane.paceDriftSteadyMs, plane.paceDriftGapUpdates, plane.paceDriftSettleMs);   // OMNI_HOLEPUNCH_V5, V5_REV2, V5_REV3
        if (v7On()) holeV7Log(now);   // OMNI_HOLEPUNCH_V7_REV2: two short lines at most (V7 off: none, as v90)
    }
    plane.paceAheadMinMs = HUGE_VAL;
    plane.paceDriftSteadyMs = 0; plane.paceDriftGapUpdates = 0;   // OMNI_HOLEPUNCH_V5_REV2
    plane.paceDriftSettleMs = 0;   // OMNI_HOLEPUNCH_V5_REV3
    plane.paceWindowMs = now; plane.paceWinShown = shown; plane.paceWinDropped = dropped; plane.paceWinLate = late;
    plane.paceQueueSum = 0; plane.paceQueueSamples = 0; plane.paceDriftMaxMs = 0; plane.paceUpdates = 0;
    plane.paceConvertMs = 0; plane.paceConverts = 0;
}

// Converts the owner's queued pictures about two vblanks before they are due; drops those a
// newer one replaces before their first vblank. Runs after every poll.
void holePaceStep()
{
    // Submits held for queue room resume whenever it appears (shown, dropped, discarded, pacing
    // off, plane released): cheap when they still have to wait.
    for (auto& ch : channels) if (!ch.waiting.empty() || holePaceBacklog(ch)) runWaiting(ch);   // OMNI_HOLEPUNCH_V5: or a backlog
    holeV3Backfill();   // OMNI_PERF_B_V3
    const int owner = plane.owner;   // written on this thread only
    if (owner < 0) return;
    Channel& c = channels[owner];
    size_t layers;
    { std::lock_guard<std::mutex> l(plane.lock); layers = plane.paced.size(); }
    if (!c.paceOn && (c.paced.empty() || c.paceV5)) {   // OMNI_HOLEPUNCH_V5: a backlog goes back to the player, not to the screen
        if (plane.pacing && !layers) { std::lock_guard<std::mutex> l(plane.lock); plane.pacing = false; }   // played out
        return;
    }
    const double now = nowMs();
    diagnosticTrace(8,c.paced.size(),layers,c.clock.valid?c.clock.at(now):INT64_MIN,c.clock.playing);
    bool freed = false;
    if (c.clock.valid) {
        const int64_t next = c.clock.at(vblankAfter(now) + vblankMs / 2);   // due at the next vblank
        const int64_t horizon = c.clock.at(now + 2.5 * vblankMs);
        while (!c.paced.empty()) {
            if (c.paced.size() >= 2 && c.paced[1].mediaUs <= next) {   // replaced before its first vblank
                // OMNI_HOLEPUNCH_V7_REFLIP: why: the shell had not taken the converted ones (queue
                // full), the picture was decoded after it was due, or else
                if (!v7On()) { }   // OMNI_HOLEPUNCH_V7_REV2: V7 on only
                else if (layers >= paceAhead) v7RawShellBehind++;
                else if (c.paced.front().queuedMs > c.clock.wallMs(c.paced.front().mediaUs)) v7RawDecodedLate++;
                else v7RawOther++;
                diagnosticTrace(7,c.paced.front().mediaUs,3,layers,next);
                holePaceRecycle(c, std::move(c.paced.front().planes)); c.paced.pop_front();
                c.paceDroppedRaw++; freed = true;
                continue;
            }
            if (layers >= paceAhead || (!c.posterPending && c.paced.front().mediaUs > horizon)) break;
            PacedFrame f = std::move(c.paced.front());
            c.paced.pop_front(); freed = true;
            HoleRect r; bool swapRB;
            { std::lock_guard<std::mutex> l(plane.lock); r = plane.rect; swapRB = plane.swapRB; }
            diagnosticTrace(4,f.mediaUs,r.w,r.h,c.paced.size());
            if (!holeConvert(r.w, r.h, swapRB, &f)) { holeRelease(owner, "conversion failed"); return; }
            holePaceRecycle(c, std::move(f.planes));   // the layer's previous source buffer
            c.posterPending = false; layers++;
        }
    }
    if (freed) runWaiting(c);
    holePaceReport(c, now);
    holePaceLog(c, now, layers);
}

// Poll timeout: wake when the next queued picture is due for conversion.
int holePaceTimeoutMs(int base)
{
    const int owner = plane.owner;
    if (owner < 0) return base;
    const Channel& c = channels[owner];
    if (!c.clock.valid || c.paced.empty()) return base;
    size_t layers;
    { std::lock_guard<std::mutex> l(plane.lock); layers = plane.paced.size(); }
    if (layers >= paceAhead) return std::min(base, int(vblankMs / 2));
    if (c.posterPending) return 0;   // the first picture after a seek: convert now
    const double ms = c.clock.wallMs(c.paced.front().mediaUs) - 2.5 * vblankMs - nowMs();
    return ms >= base ? base : ms <= 1 ? 1 : int(ms);
}

// clockSnapshot: the picture last converted, as NV12 / 16-bit two-plane in a free slot.
void holeSnapshot(Channel& c)
{
    uint32_t slot;
    if (!c.shm || !freeSlot(c, slot)) return;   // asked again later
    Message m; m.type = Type::Frame;
    {
        std::lock_guard<std::mutex> l(plane.lock);   // the picture on screen (its source planes); copied, then sent unlocked
        const HoleLayer* cur = plane.current.get();
        if (!cur || !cur->rawW || cur->epoch != plane.epoch || cur->rawW != c.width) return;
        const size_t bps = cur->rawDepth > 8 ? 2 : 1;
        const int w = cur->rawW, h = cur->rawH, cw = (w + 1) / 2, ch = (h + 1) / 2;
        const size_t pitch = alignUp(size_t(w) * bps, 256), coded = size_t(h + (h & 1));
        if (pitch * coded * 3 / 2 > c.slotSize) return;
        uint8_t* y = c.shm + c.slotOffset + size_t(slot) * c.slotSize;
        const uint8_t* sy = cur->raw.data();
        const uint8_t* su = sy + size_t(w) * h * bps;
        const uint8_t* sv = su + size_t(cw) * ch * bps;
        for (int r = 0; r < h; r++) memcpy(y + pitch * size_t(r), sy + size_t(r) * w * bps, size_t(w) * bps);
        for (int r = 0; r < ch; r++) {
            uint8_t* d = y + pitch * coded + pitch * size_t(r);
            for (int i = 0; i < cw; i++) {
                memcpy(d + (2 * size_t(i)) * bps, su + (size_t(r) * cw + size_t(i)) * bps, bps);
                memcpy(d + (2 * size_t(i) + 1) * bps, sv + (size_t(r) * cw + size_t(i)) * bps, bps);
            }
        }
        m.a = slot; m.b = uint32_t(w); m.c = uint32_t(coded); m.d = uint32_t(pitch); m.e = bps == 2 ? 10 : 8;
    }
    m.f = Wire::FrameSnapshot; m.pts = INT64_MIN;
    c.slotBusy[slot] = true;
    c.slotFrame[slot] = m;
    sendMsg(c, m);
}

// HoleClock from the player (fields in OmniHwProtocol.h).
void handleClock(Channel& c, const Message& in)
{
    diagnosticTrace(110,c.index,in.a,in.pts,int64_t(uint64_t(in.e)<<32|in.d));
    int32_t offsets[8]; memcpy(offsets, in.text + 16, sizeof offsets);
    int64_t stages[8]; const int64_t traceAnchor = int64_t(uint64_t(in.e)<<32|in.d);
    for (unsigned i = 0; i < 8; ++i) stages[i] = offsets[i] == INT32_MIN ? 0 : traceAnchor + offsets[i];
    diagnosticTrace(120,stages[0],stages[1],stages[2],stages[3]);
    diagnosticTrace(121,stages[4],stages[5],stages[6],stages[7]);
    const bool paced = in.a & Wire::clockPaced;
    bool owner;
    { std::lock_guard<std::mutex> l(plane.lock); owner = plane.attached && plane.owner == c.index; }
    if (paced && !c.paceOn) {
        const char* why = !owner ? "video plane not held" : !holePacingFlagEnabled() ? "disabled by holepunch-pacing-disabled.flag"
            : holePaceCapacity(c) < 3 ? "pictures too large for the pacing queue" : nullptr;
        if (why) {
            if (c.paceAnswer != -1) {
                c.paceAnswer = -1;
                Message m; m.type = Type::HolePacing; m.status = -1; snprintf(m.text, sizeof m.text, "%s", why);
                sendMsg(c, m);
                if (plane.logLines < 40) { ++plane.logLines; holeNote("channel %d: pacing refused (%s)", c.index, why); }
            }
            return;
        }
        c.paceOn = true; c.paceAnswer = 1; c.paceCap = holePaceCapacity(c);
        c.paceV5 = holeV5FlagEnabled(); c.paceFrameBytes = holePaceFrameBytes(c);   // OMNI_HOLEPUNCH_V5
        paceDirectOn = c.paceV5;
        // V134: a held startup needs one initial presentation without advancing the clock.
        // Reuse the existing seek/poster path; subsequent frames keep their normal deadlines.
        c.paceGenSeen = false; c.clock.valid = false; c.posterPending = !(in.a & Wire::clockPlaying);
        { std::lock_guard<std::mutex> l(plane.lock); plane.pacing = true; plane.posterPending = c.posterPending; }
        plane.paceWindowMs = 0;
        if (plane.logLines < 40) {
            ++plane.logLines;
            holeNote("channel %d: the shell paces this video (queue %u frames, vblank %s)", c.index, c.paceCap, vblankReported() ? "from the presenter" : "estimated");
            if (c.paceV5)   // OMNI_HOLEPUNCH_V5: what one queued picture costs and where it lives
                holeNote("channel %d: V5 queue: %zu bytes per picture (%dx%d %d-bit planar copy), up to %u pictures = %.0f MiB of direct memory (budget %.0f MiB, largest free block %s), decoded until %.1f s ahead of the clock, clock held %.0f s without updates",
                    c.index, c.paceFrameBytes, c.width, c.height, c.bitDepth, c.paceCap, double(c.paceFrameBytes) * c.paceCap / 1048576,
                    double(holePaceBudget()) / 1048576, backendDirectAvailable() ? (std::to_string(backendDirectAvailable() >> 20) + " MiB").c_str() : "unknown",
                    paceAheadUs / 1e6, 4.0);
        }
        holePaceReport(c, nowMs(), true);
    } else if (!paced && c.paceOn) {
        c.paceOn = false; c.paceAnswer = 0;   // new pictures go to the player again; queued ones still play out
        if (plane.logLines < 40) { ++plane.logLines; holeNote(c.paceV5 ? "channel %d: pacing off (%zu decoded frames go back to the player)" : "channel %d: pacing off (%zu decoded frames play out)", c.index, c.paced.size()); }
    }
    if (!owner) return;
    PaceClock k;
    k.playing = in.a & Wire::clockPlaying;
    k.rate = double(in.c) / 65536;
    k.anchorUs = int64_t(uint64_t(in.e) << 32 | in.d);
    k.posUs = in.pts;
    if (in.a & Wire::clockLimit) memcpy(&k.limitUs, in.text + 8, sizeof k.limitUs);
    if (in.f && in.g) { c.tbNum = int(in.f); c.tbDen = int(in.g); }
    const bool newGen = !c.paceGenSeen || in.b != c.paceGen;
    if (!newGen && c.clock.valid && c.clock.playing && k.playing)   // the correction this update makes
    {
        const double drift = std::fabs(double(k.posUs - c.clock.at(double(k.anchorUs) / 1000)) / 1000);
        plane.paceDriftMaxMs = std::max(plane.paceDriftMaxMs, drift);
        const double gapUs = double(k.anchorUs - c.clock.anchorUs);   // OMNI_HOLEPUNCH_V5_REV2
        if (double(k.anchorUs - c.playFromUs) < 1.5e6) plane.paceDriftSettleMs = std::max(plane.paceDriftSettleMs, drift);   // OMNI_HOLEPUNCH_V5_REV3
        else if (gapUs <= 1e6 && c.clock.at(double(k.anchorUs) / 1000) < c.clock.limitUs) plane.paceDriftSteadyMs = std::max(plane.paceDriftSteadyMs, drift);
        else plane.paceDriftGapUpdates++;
    }
    plane.paceUpdates++;
    if (k.playing && (newGen || !c.clock.valid || !c.clock.playing)) c.playFromUs = k.anchorUs;   // OMNI_HOLEPUNCH_V5_REV3
    if (newGen) {
        c.paceGen = in.b; c.paceGenSeen = true; c.discardUs = INT64_MIN;
        std::lock_guard<std::mutex> l(plane.lock);
        plane.shownInGen = false;
        plane.startupPresentationReady = false; plane.startupGeneration = in.b;
    }
    k.valid = newGen || c.clock.valid;   // after a Flush, only a new generation makes it valid
    k.holdUs = c.paceV5 ? 4e6 : 2e6;     // OMNI_HOLEPUNCH_V5
    if (in.a & Wire::clockDiscard) {
        memcpy(&c.discardUs, in.text, sizeof c.discardUs);
        while (!c.paced.empty() && c.paced.front().mediaUs + 1 < c.discardUs) {
            holePaceRecycle(c, std::move(c.paced.front().planes)); c.paced.pop_front(); c.paceDiscarded++;
        }
    }
    if (focusActive.load(std::memory_order_relaxed)) {
        diagnosticTrace(144,c.index,c.clock.at(double(k.anchorUs)/1000),k.posUs,k.anchorUs);
        diagnosticTrace(145,c.index,in.b,int64_t(k.rate*1000000),k.valid);
    }
    diagnosticTrace(117,c.index,c.clock.playing,k.playing,k.posUs);
    c.clock = k;
    { std::lock_guard<std::mutex> l(plane.lock); plane.clock = k;
      diagnosticTrace(118,c.index,k.playing,k.at(nowMs()),k.anchorUs); }
    if (in.a & Wire::clockSnapshot) holeSnapshot(c);
}

// Flush: pictures decoded before it are stale, and so is the clock until the player sends
// the generation that follows the seek or flush.
void holePaceFlush(Channel& c)
{
    c.paceDiscarded += c.paced.size();
    while (!c.paced.empty()) { holePaceRecycle(c, std::move(c.paced.front().planes)); c.paced.pop_front(); }
    c.clock.valid = false;
    c.posterPending = true;
    c.discardUs = INT64_MIN;   // OMNI_HOLEPUNCH_V5_REV3: the old target must not drop pictures decoded before the new clock arrives
    std::lock_guard<std::mutex> l(plane.lock);
    if (plane.owner != c.index) return;
    for (auto& layer : plane.paced) plane.spare.push_back(std::move(layer));
    plane.paced.clear();
    plane.clock.valid = false;
    plane.posterPending = true;
}

// OMNI_HOLEPUNCH_V1: Present from a WebProcess player (fields in OmniHwProtocol.h).
void handlePresent(Channel& c, const Message& in)
{
    if (in.a == Wire::presentHide) { holeRelease(c.index, "hidden by the player", v8OtherStreamOpen(c) ? 1 : 0); c.holeAnswer = 0; return; }   // OMNI_PERF_B_V8
    const bool keep = in.a == Wire::presentKeep;
    if (!keep && (in.a >= Wire::outputSlots || !c.slotBusy[in.a] || !c.shm)) {   // not a slot this client holds
        static unsigned ignoredLogs = 0;   // OMNI_HOLEPUNCH_V2: say so (V1 dropped it silently)
        if (ignoredLogs++ < 12) holeNote("channel %d: Present for slot %u ignored (slot not held by the client; busySlots=%u/%u)", c.index, in.a, busySlots(c), Wire::outputSlots);
        return;
    }
    const double vs = omniHoleViewScale.load(std::memory_order_relaxed); // OMNI_FAST_PAGE_V1: view -> canvas pixels
    const HoleRect r { int32_t(std::lround(int32_t(in.b) * vs)), int32_t(std::lround(int32_t(in.c) * vs)),
                       int32_t(std::lround(int32_t(in.d) * vs)), int32_t(std::lround(int32_t(in.e) * vs)) };
    std::string why;
    const unsigned busyBefore = busySlots(c);
    const double started = nowMs();
    const bool shown = holePresent(c.index, keep ? nullptr : &c.slotFrame[in.a],
        keep ? nullptr : c.shm + c.slotOffset + size_t(in.a) * c.slotSize, c.slotSize, c.width, c.height, r, why);
    if (!keep) { c.slotBusy[in.a] = false; runWaiting(c); }   // the slot is never read after this
    // OMNI_HOLEPUNCH_V2: the first Presents of each channel, with its slot state.
    if (++c.holePresents <= 12) {
        holeNote("channel %d present #%u %s%u rect=%dx%d at %d,%d busySlots=%u/%u waitingSubmits=%zu -> %s (%.1f ms)",
            c.index, c.holePresents, keep ? "rect-only" : "slot=", keep ? 0u : in.a, r.w, r.h, r.x, r.y, busyBefore,
            Wire::outputSlots, c.waiting.size(), shown ? "ok" : why.c_str(), nowMs() - started);
    }
    if (!keep && shown) {   // OMNI_HOLEPUNCH_V2: the player's proof that the shell has the frame
        c.holeLastFrameMs = nowMs(); c.holeQuietLogged = false;
        Message ack; ack.type = Type::HoleShown; ack.a = ++c.holeShown; ack.pts = in.pts;
        diagnosticTrace(111,c.index,ack.a,ack.pts,0); // converted/accepted, NOT a completed flip
        sendMsg(c, ack);
    }
    if ((shown ? 1 : -1) != c.holeAnswer) {
        c.holeAnswer = shown ? 1 : -1;
        Message m; m.type = Type::HoleState; m.status = shown ? 0 : -1;
        m.a = shown && holePacingFlagEnabled() && holePaceCapacity(c) >= 3;   // OMNI_HOLEPUNCH_V4: pacing possible
        snprintf(m.text, sizeof m.text, "%s", shown ? "ok" : why.c_str());
        diagnosticTrace(112,c.index,m.status,m.a,0);
        sendMsg(c, m);
    }
}

// OMNI_PERF_B_V8: another channel has a stream (configured or being configured): a close may be a quality switch.
bool v8OtherStreamOpen(const Channel& c)
{
    const double now = nowMs();   // opened in the last 3 s: a switch in progress, not another tab's long-open stream
    for (const auto& o : channels) if (&o != &c && o.connected && (o.shm || o.v5Configuring) && now - o.v8ConfiguredMs < 3000) return true;
    return false;
}
void handle(Channel& c, const Message& in)
{
    if (c.v5Configuring) { c.v5Held.push_back(in); pbV5Deferred.fetch_add(1, std::memory_order_relaxed); return; }   // OMNI_PERF_B_V5: after the open
    switch (in.type) {
    case Type::Hello: {
        Message ack; ack.type = Type::HelloAck;
        ack.status = (in.b == c.generation && in.c == Wire::version) ? 0 : -1;
        c.connected = ack.status == 0;
        note("channel %d hello from pid %u gen %u -> %d", c.index, in.a, in.b, ack.status);
        sendMsg(c, ack);
        // The client holds its own duplicate now. Dropping ours is what lets
        // the client's exit show up as EOF on serverFd.
        if (c.connected && c.clientFd >= 0) { close(c.clientFd); c.clientFd = -1; writeRendezvous(); }
        break;
    }
    case Type::Configure: c.v8ConfiguredMs = nowMs(); holeRelease(c.index, "stream reconfigured", 1); if (!v5BeginConfigure(c, in)) handleConfigure(c, in); break; // OMNI_HOLEPUNCH_V1, OMNI_PERF_B_V5
    case Type::Present: handlePresent(c, in); break;                                                  // OMNI_HOLEPUNCH_V1
    case Type::HoleClock: handleClock(c, in); break;                                                  // OMNI_HOLEPUNCH_V4
    case Type::ShmMapped:
        if (c.shmFd >= 0) { close(c.shmFd); c.shmFd = -1; } // client holds its own copy now
        break;
    case Type::Submit: case Type::Drain:
        c.waiting.push_back(in);
        // OMNI_HOLEPUNCH_V5: while a V5 queue paces, the loop decodes (holePaceStep, ~8 ms at a time)
        // and this thread reads on: a client handing over seconds of access units at once must
        // not wait for each one to be decoded before it can send the next.
        if (c.paceOn && c.paceV5) c.runnable = true;
        else runWaiting(c);
        break;
    case Type::Release:
        if (in.a < Wire::outputSlots) c.slotBusy[in.a] = false;
        runWaiting(c);
        break;
    case Type::Flush: {
        c.waiting.clear(); c.pending.clear(); c.failed = false;
        c.consumedCount = c.consumedSent = 0; c.runnable = false;   // OMNI_HOLEPUNCH_V5: counted from 0 after Flushed
        holePaceFlush(c); // OMNI_HOLEPUNCH_V4
        int rc = c.decoder.isOpen() ? c.decoder.reset() : 0;
        Message m; m.type = Type::Flushed; m.status = rc; sendMsg(c, m);
        break;
    }
    case Type::Close:
        holeRelease(c.index, "stream closed", v8OtherStreamOpen(c) ? 1 : 0); // OMNI_HOLEPUNCH_V1 (OMNI_PERF_B_V8: hold when the next stream is open)
        releaseStream(c);
        break;
    default:
        break;
    }
}

void* serviceMain(void*)
{
    std::vector<Message> partialBuf(Wire::maxChannels);
    std::vector<size_t> partialLen(Wire::maxChannels, 0);
    std::vector<double> claimSince(Wire::maxChannels, 0);
    const double started = nowMs();
    v7ServiceStartMs = started; if (v7On()) v7NoteThread(v7ServiceThreadInfo);   // OMNI_HOLEPUNCH_V7_REFLIP (V7_REV2: V7 on only)
    double v7BusySince = 0, v7BusyLast = 0; unsigned v7BurstMessages = 0;
    while (running.load()) {
        const double serviceNow = nowMs(); // reuse the existing loop timestamp for the HUD
        backendDiagnosticTick(serviceNow - started);
        publishPlaybackStats(serviceNow);
        pollfd fds[Wire::maxChannels + 1];
        bool runnable = false;   // OMNI_HOLEPUNCH_V5
        for (auto& ch : channels) { holeFlushConsumed(ch); runnable |= ch.runnable; }
        for (uint32_t i = 0; i < Wire::maxChannels; i++) {
            const Channel& ch = channels[i];
            fds[i] = { ch.serverFd, short(POLLIN | (ch.consumedSent != ch.consumedCount ? POLLOUT : 0)), 0 };
        }
        fds[Wire::maxChannels] = { v5w.wake[0], POLLIN, 0 };   // OMNI_PERF_B_V5: a finished open wakes this loop (-1: ignored)
        int n = poll(fds, Wire::maxChannels + 1, runnable ? 0 : holePaceTimeoutMs(plane.rescalePending ? 10 : 100)); // OMNI_HOLEPUNCH_V2, V4, V5
        if (n > 0 && (fds[Wire::maxChannels].revents & POLLIN)) n--;   // not a channel message
        v5Complete();   // OMNI_PERF_B_V5
        if (n < 0 && errno != EINTR) break;
        // OMNI_HOLEPUNCH_V7_REFLIP: a run of wakes with work (messages, or decodes waiting) is a burst
        const bool v7Busy = v7On() && (n > 0 || runnable);   // OMNI_HOLEPUNCH_V7_REV2: V7 on only
        if (v7Busy && !v7BusySince) v7BusySince = nowMs();
        if (!v7Busy && v7BusySince) {
            if (v7BusyLast - v7BusySince >= 100) v7Event(int64_t(v7BusySince * 1000), int64_t((v7BusyLast - v7BusySince) * 1000), 1, v7BurstMessages);
            v7BusySince = 0; v7BurstMessages = 0;
        }
        bool rewrite = false;
        for (uint32_t i = 0; i < Wire::maxChannels; i++) {
            Channel& c = channels[i];
            // OMNI_HOLEPUNCH_V5: up to 64 messages per wake (V4: one), so a burst of Submits after a
            // stall of the client's main thread is taken in a few loops.
            for (int burst = 0; burst < 64 && (fds[i].revents & (POLLIN | POLLHUP | POLLERR)); burst++) {
                char* p = reinterpret_cast<char*>(&partialBuf[i]) + partialLen[i];
                ssize_t got = recv(c.serverFd, p, sizeof(Message) - partialLen[i], burst ? MSG_DONTWAIT : 0);
                if (got < 0 && burst && (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR)) break;   // all read
                if (got <= 0) {
                    // The client exited or closed. Its claim and socket die with it.
                    if (c.connected) note("channel %d client left", c.index);
                    resetChannel(c); partialLen[i] = 0; claimSince[i] = 0; rewrite = true;
                    break;
                }
                partialLen[i] += size_t(got);
                if (partialLen[i] == sizeof(Message)) {
                    partialLen[i] = 0;
                    // OMNI_HOLEPUNCH_V2: a slow message (a decoder call that blocks, a conversion)
                    // stalls every channel; name it.
                    static unsigned slowLogs = 0;
                    const double started = nowMs();
                    diagnosticTrace(9,unsigned(partialBuf[i].type),c.index,partialBuf[i].pts,c.waiting.size());
                    if (partialBuf[i].magic == Wire::magic) handle(c, partialBuf[i]);
                    diagnosticTrace(10,unsigned(partialBuf[i].type),c.index,partialBuf[i].pts,c.waiting.size());
                    const double took = nowMs() - started;
                    if (v7On()) { v7BurstMessages++; v7Op(took, v7MessageName(unsigned(partialBuf[i].type))); }   // OMNI_HOLEPUNCH_V7_REFLIP (V7_REV2: V7 on only)
                    if (took > 100 && slowLogs < 20) {
                        ++slowLogs;
                        note("channel %d: message type %u took %.0f ms (busySlots=%u/%u waitingSubmits=%zu)", c.index,
                            unsigned(partialBuf[i].type), took, busySlots(c), Wire::outputSlots, c.waiting.size());
                    }
                }
            }
            // A claim that never says Hello (client died mid-connect) frees the channel.
            if (!c.connected) {
                bool claimed = !access((dir + "/claim-" + std::to_string(i)).c_str(), F_OK);
                if (!claimed) claimSince[i] = 0;
                else if (!claimSince[i]) claimSince[i] = nowMs();
                else if (nowMs() - claimSince[i] > 5000) { note("channel %d stale claim", c.index); resetChannel(c); claimSince[i] = 0; rewrite = true; }
            }
        }
        if (rewrite) writeRendezvous();
        holeRescaleTick(n == 0 && !runnable);   // OMNI_HOLEPUNCH_V2 (V5: busy decoding is not idle)
        holePaceStep();            // OMNI_HOLEPUNCH_V4
        holeWatchdog();
        if (v7Busy) {   // OMNI_HOLEPUNCH_V7_REFLIP: after 4 ms of work in a row, let the UI main thread run
            v7BusyLast = nowMs();
            if (v7BusyLast - v7BusySince > (v8On() ? 1 : 2)) {   // OMNI_HOLEPUNCH_V8_CADENCE: 1 ms (the presenter acts every vblank now)
                const int64_t tickUs = v7PollUs.load(std::memory_order_relaxed);
                if (tickUs && int64_t(v7BusyLast * 1000) - tickUs > int64_t(v7StallMs * 1000)) { usleep(1000); v7ServiceSleeps++; }   // it has not ticked: maybe this thread keeps it off its core
                else { sched_yield(); v7ServiceYields++; }
            }
        }
    }
    threadDone = true;
    return nullptr;
}
}

// ---- OMNI_DECODER_MEMORY_REPORT_V1: the service's own buffers for a 2160p stream -------------
// Arithmetic from the constants in this file (nothing is allocated). The decoder's own share is
// backendMemoryReport's.
static void holeMemoryReport()
{
    const int w = 3840, h = 2160;
    const auto mib = [](double bytes) { return bytes / 1048576; };
    for (int depth : { 8, 10 }) {
        const size_t bps = depth > 8 ? 2 : 1;
        const size_t slot = alignUp(alignUp(size_t(w) * bps, 256) * alignUp(size_t(h), 32) * 3 / 2, 4096);   // handleConfigure
        const size_t planar = size_t(w) * h * 3 / 2 * bps + 64;   // one queued picture (holeSplitPlanes)
#ifdef OMNI_HOLE_V5_QUEUE
        const size_t input = Wire::inputRingBytes;
#else
        const size_t input = size_t(Wire::inputSlots) * Wire::inputSlotBytes;
#endif
        const size_t shm = input + slot * Wire::outputSlots;
        const unsigned v4 = unsigned(std::min<size_t>(paceMaxFrames, paceQueueBytes / slot));
        fprintf(stderr, "OMNI HW MEMORY: %dx%d %d-bit, service: shared memory per stream %.1f MiB (input %.1f MiB + %u output slots x %.1f MiB; mapped by the UI process and the WebProcess); "
            "V4 pacing queue %u picture(s) x %.1f MiB = %.1f MiB of flexible heap (budget %.0f MiB, max %u)%s; V1 plane source copy %.1f MiB flexible\n",
            w, h, depth, mib(double(shm)), mib(double(input)), Wire::outputSlots, mib(double(slot)), v4, mib(double(planar)), mib(double(v4) * double(planar)),
            mib(double(paceQueueBytes)), paceMaxFrames, v4 < 3 ? ", pacing refused (needs 3)" : "", mib(double(planar)));
#ifdef OMNI_HOLE_V5_QUEUE
        const size_t budget = holePaceBudget();
        const unsigned v5 = unsigned(std::min<size_t>(paceMaxFramesV5, budget / planar));
        fprintf(stderr, "OMNI HW MEMORY: %dx%d %d-bit, service: V5 pacing queue (direct memory) %u picture(s) x %.1f MiB = %.1f MiB (budget %.0f MiB, max %u) = %.1f s at 30 fps, %.1f s at 60 fps\n",
            w, h, depth, v5, mib(double(planar)), mib(double(v5) * double(planar)), mib(double(budget)), paceMaxFramesV5, v5 / 30.0, v5 / 60.0);
#endif
    }
    // Plane layers are converted to the on-screen size: at most the 3840x2160 canvas, RGBA (v103 native 4K limit).
    const double layer = double((3840 + 15) / 16 * 16 * 4) * 2160;
    fprintf(stderr, "OMNI HW MEMORY: shell plane layers (any source size): %.1f MiB each at maximum 3840x2160 RGBA, ~5 in use (on screen, ready, 2 converted ahead, 1 converting) = %.1f MiB flexible\n",
        mib(layer), mib(5 * layer));
    // OmniDisplay (OMNI_DISPLAY_V1, when applied; figures from its report): in player mode each
    // plane layer also keeps an 8-bit planar copy of its source; scanout buffers are direct.
    const double copy = 3840.0 * 2160 * 3 / 2;
    fprintf(stderr, "OMNI HW MEMORY: OmniDisplay player mode (when applied): source copy %.1f MiB per plane layer, ~4 layers = %.1f MiB flexible; scanout sets 84 MiB direct (its report: 2 x 3840x2160 + 2 x 1920x1080 RGBA, 2 MiB aligned)\n",
        mib(copy), mib(4 * copy));
    fflush(stderr);
}

int openDecoderCount(size_t* sharedBytes) // OMNI_TAB_MEDIA_RELEASE_V1
{
    int open = 0; size_t bytes = 0;
    for (auto& live : liveStreamBytes) { const size_t b = live.load(std::memory_order_relaxed); if (b) { ++open; bytes += b; } }
    if (sharedBytes) *sharedBytes = bytes;
    return open;
}

void shellLog(const char* message)
{
    std::string line("browser: "); line += message; line += '\n';
    v7LogPush(std::move(line));
}

bool serviceStart(std::string& detail)
{
    if (running.load()) { detail = "already running"; return true; }
    int rc = backendInitialize(detail);
    if (rc) { note("hardware decoder unavailable: %s (rc=0x%08x)", detail.c_str(), unsigned(rc)); return false; }
    if (backendMemoryReportWanted()) { backendMemoryReport("hw-service start"); holeMemoryReport(); } // OMNI_DECODER_MEMORY_REPORT_V1
    dir = rendezvousDir();
    ensureDir(dir);
    for (uint32_t i = 0; i < Wire::maxChannels; i++) {
        channels[i].index = int(i);
        if (!resetChannel(channels[i])) { detail = "socketpair"; return false; }
    }
    writeRendezvous();
    running = true;
    threadDone = false;
    pthread_attr_t attr; pthread_attr_init(&attr);
    pthread_attr_setstacksize(&attr, 512 * 1024);
    int e = pthread_create(&thread, &attr, serviceMain, nullptr);
    pthread_attr_destroy(&attr);
    if (e) { running = false; detail = "pthread_create"; return false; }
    detail = "running in pid " + std::to_string(getpid());
    note("%s, %u channels, rendezvous %s", detail.c_str(), Wire::maxChannels, dir.c_str());
    return true;
}

void serviceStop()
{
    if (!running.exchange(false)) return;
    pthread_join(thread, nullptr);
    if (v7On()) v7LogDrain(500);   // OMNI_HOLEPUNCH_V7_REV2: the lines still queued
    unlink((dir + "/service").c_str());
    for (auto& c : channels) {
        holeRelease(c.index, "service stopped", 2); // OMNI_HOLEPUNCH_V1
        releaseStream(c);
        if (c.serverFd >= 0) close(c.serverFd);
        if (c.clientFd >= 0) close(c.clientFd);
        c.serverFd = c.clientFd = -1;
        unlink((dir + "/claim-" + std::to_string(c.index)).c_str());
    }
}


bool serviceShutdownForExit(int waitMs, bool fromSignal)
{
    static std::atomic<bool> done { false };
    if (done.exchange(true)) return true;
    bool hadThread = running.exchange(false);
    if (hadThread) {
        if (pthread_equal(pthread_self(), thread)) return false; // crashed inside the service
        for (int waited = 0; !threadDone.load() && waited < waitMs; waited += 10) usleep(10000);
        if (!threadDone.load()) {
            if (!fromSignal) note("exit: service thread busy after %d ms; decoders left as they are", waitMs);
            return false;
        }
        pthread_join(thread, nullptr);
    }
    int open = 0;
    for (auto& c : channels) {
        if (fromSignal && c.v5Configuring) continue;   // OMNI_PERF_B_V5: being opened on the worker; never wait in a signal handler
        open += c.decoder.isOpen();
        releaseStream(c);            // DeleteDecoder + frees its memory (OMNI_PERF_B_V5: after an open still running)
    }
    int rc = backendReleaseQueue(!fromSignal);
    if (!fromSignal) {
        unlink((dir + "/service").c_str());
        note("exit: closed %d decoder(s), released compute queue -> 0x%08x", open, unsigned(rc));
        if (v7On()) v7LogDrain(300);   // OMNI_HOLEPUNCH_V7_REV2: the lines still queued
    }
    return rc == 0 || rc == -2;
}

// ---- OMNI_HOLEPUNCH_V1: shell side (main thread), see OmniHwService.h --------------------
bool holePunchAttach(int bytesPerPixel, int redShift, int greenShift, int blueShift)
{
    const char* why = nullptr;
    bool swapRB = false;
#ifdef OMNI_HW_NO_SWSCALE
    why = "built without swscale";
#endif
    if (!why && !holePunchFlagEnabled()) why = "disabled by holepunch-disabled.flag";
    if (!why && bytesPerPixel != 4) why = "canvas is not 32-bit";
    if (!why) {
        if (redShift == 16 && greenShift == 8 && blueShift == 0) swapRB = false;
        else if (redShift == 0 && greenShift == 8 && blueShift == 16) swapRB = true;
        else why = "unsupported canvas channel order";
    }
    std::lock_guard<std::mutex> l(plane.lock);
    plane.attached = !why;
    plane.swapRB = swapRB;
    if (why) holeNote("shell video plane off (%s); videos keep the paint path", why);
    else holeNote("shell video plane ready (canvas %s)", swapRB ? "RGBA" : "BGRA");
    return !why;
}

void holePunchSetViewScale(double canvasPerViewPixel) // OMNI_FAST_PAGE_V1
{
    omniHoleViewScale.store(canvasPerViewPixel > 0 ? canvasPerViewPixel : 1.0, std::memory_order_relaxed);
}
bool holePunchActive()
{
    std::lock_guard<std::mutex> l(plane.lock);
    return plane.attached && plane.owner >= 0;
}

bool holePunchPoll()
{
    if (v7On()) {   // OMNI_HOLEPUNCH_V7_REFLIP: the shell main thread ticks (the presenter steps in when it does not; V7_REV2: V7 on only)
        const int64_t now = int64_t(nowMs() * 1000), last = v7PollUs.exchange(now, std::memory_order_relaxed);
        v7TickGapUs = last ? now - last : 0;
        if (!v7MainKnown.load(std::memory_order_relaxed)) { v7MainThread = pthread_self(); v7MainKnown.store(true); v7NoteThread(v7MainThreadInfo); }
        if (v7PhaseSeen) { v7PhaseUs[v7Phase] += now - v7PhaseSinceUs; v7PhaseSinceUs = now; }
        if (last) {
            v7Max(v7PollGapMaxUs, now - last);
            if (now - last > 50000) { v7Stalls.fetch_add(1, std::memory_order_relaxed); v7StallUs.fetch_add(now - last, std::memory_order_relaxed); if (now - last >= 100000) v7Event(last, now - last, 0, 0); }
            if (now - last > 50000 && v7PhaseSeen) {   // where the main thread spent the stall
                std::lock_guard<std::mutex> l(v7TraceLock);
                if (now - last > v7StallLongestUs) { v7StallLongestUs = now - last; std::copy(v7PhaseUs, v7PhaseUs + v7Phases, v7StallPhaseUs); }
            }
        }
        std::fill(v7PhaseUs, v7PhaseUs + v7Phases, 0);
    }
    if (plane.version.load() != plane.seenVersion) { pbPollVersion.fetch_add(1, std::memory_order_relaxed); return true; }   // OMNI_PERF_B_V2: counted by reason
    // OMNI_HOLEPUNCH_V4: or a paced picture is due at the vblank a draw now would reach.
    std::lock_guard<std::mutex> l(plane.lock);
    if (!plane.attached || plane.owner < 0) pbOwnsVideo.store(false, std::memory_order_relaxed);   // OMNI_PERF_B_V2
    if (!plane.attached || plane.owner < 0 || !plane.clock.valid || plane.paced.empty()) return false;
    const bool due = plane.posterPending || plane.paced.front()->mediaUs <= plane.clock.at(vblankAfter(nowMs() + composeLeadMs) + vblankMs / 2);
    if (due && plane.posterPending) pbPollPoster.fetch_add(1, std::memory_order_relaxed);
    if (!due || plane.posterPending) return due;
    // OMNI_SKIP_COMPOSE_V1: only a new picture is due (no rect change, no page or shell change: those
    // draw anyway). When the presenter re-flips by itself (V8, the frame's video pixels described by a
    // live mask for this owner and size), the shell need not compose the whole video area again for it:
    // at 4K that was 8-23 ms of main-thread work per picture. The shell still draws on its own timers.
    // Kill switch: /data/omni/compose-every-picture.flag.
    static const bool everyPicture = access("/data/omni/compose-every-picture.flag", F_OK) == 0;
    if (everyPicture || !v8On() || !v8BeforeFlipSeen.load(std::memory_order_relaxed) || !plane.current) { pbPollNoPresenter.fetch_add(1, std::memory_order_relaxed); return true; }
    std::unique_lock<std::mutex> composing(v7ComposeLock, std::try_to_lock);
    // OMNI_SKIP_COMPOSE_V2: the presenter holds the lock while it re-flips (~10 ms of each frame with a translucent control
    // bar), so a busy lock is itself the sign it is showing the pictures: skip. (V1 composed then: ~60 ms main-thread draws.)
    // A wrong skip costs at most the shell's own timer (the next draw composes).
    if (!composing.owns_lock()) { pbPollSkipBusy.fetch_add(1, std::memory_order_relaxed); return false; }
    const V7Live& live = v7Live;
    const bool needed = !(live.valid && live.epoch == plane.epoch && live.w == plane.current->w && live.h == plane.current->h);
    (needed ? pbPollLive : pbPollSkipLive).fetch_add(1, std::memory_order_relaxed);
    return needed;
}
// OMNI_PERF_B_V2 (shell main thread): see OmniHwService.h.
bool holePunchPresenterOwnsVideo()
{
    static const bool on = v2On();
    return on && v8On() && v8BeforeFlipSeen.load(std::memory_order_relaxed) && pbOwnsVideo.load(std::memory_order_relaxed);
}
// (end OMNI_SKIP_COMPOSE_V1)

// OMNI_HOLEPUNCH_V4 (presenter thread): a flip just completed, i.e. a vblank passed.
void holePunchVblank(bool successful)
{
    if (successful && v143PreparedSeq) {
        hudCompleted.fetch_add(1,std::memory_order_relaxed);
        if (v143CompletedSeq==v143PreparedSeq && v143CompletedEpoch==v143PreparedEpoch)
            hudRepeats.fetch_add(1,std::memory_order_relaxed);
    }
    v143CompletedSeq = successful ? v143PreparedSeq : 0;
    v143CompletedEpoch = successful ? v143PreparedEpoch : 0;
    static unsigned cpuSamples = 0;
    if (!(++cpuSamples % 60)) {
        struct rusage usage {};
        if (!getrusage(RUSAGE_SELF, &usage)) diagnosticTrace(131,
            int64_t(usage.ru_utime.tv_sec)*1000000+usage.ru_utime.tv_usec,
            int64_t(usage.ru_stime.tv_sec)*1000000+usage.ru_stime.tv_usec,getpid(),0);
    }

    const int64_t now = int64_t(nowMs() * 1000);
    // OMNI_HOLEPUNCH_V7_REFLIP: the display's real period: flips 1-4 vblanks apart (59.94 Hz: 16683 us)
    const int64_t last = vblankUs.exchange(now, std::memory_order_relaxed);
    if (v7On() && last && now > last) {   // OMNI_HOLEPUNCH_V7_REV2: V7 on only
        const int64_t gap = now - last, n = (gap + 8341) / 16683;
        if (n >= 1 && n <= 4 && std::llabs(gap - n * 16683) < 3000) { v7FlipSpanUs.fetch_add(gap, std::memory_order_relaxed); v7FlipVblanks.fetch_add(n, std::memory_order_relaxed); }
    }
    if (v8On()) {   // OMNI_HOLEPUNCH_V8_CADENCE: the grid. An earlier return moves it there at once; it moves
        // later only by the least lateness of 60 returns in a row (all late: the period estimate's error)
        static int64_t windowMinUs = INT64_MAX; static unsigned windowN = 0;   // presenter thread only
        const int64_t grid = v8GridUs.load(std::memory_order_relaxed), period = int64_t(vblankPeriodMs() * 1000);
        if (!grid || std::llabs(now - grid) > 1000000) { v8GridUs.store(now, std::memory_order_relaxed); windowMinUs = INT64_MAX; windowN = 0; }
        else {
            const int64_t k = (now - grid + period / 2) / period, near = grid + k * period, d = now - near;
            if (d < 0) { v8GridUs.store(now, std::memory_order_relaxed); windowMinUs = INT64_MAX; windowN = 0; }
            else {
                v8GridUs.store(near, std::memory_order_relaxed);   // the same grid point, kept recent
                windowMinUs = std::min(windowMinUs, d);
                if (++windowN >= 60) { v8GridUs.store(near + windowMinUs, std::memory_order_relaxed); windowMinUs = INT64_MAX; windowN = 0; }
            }
        }
    }
    if (v8On()) {   // OMNI_HOLEPUNCH_V8_CADENCE: did the flip reach the vblank it was meant for?
        const int64_t target = v8TargetUs.exchange(0, std::memory_order_relaxed);
        const bool handOff = v8TargetHandOff.exchange(false, std::memory_order_relaxed);
        const int64_t half = int64_t(vblankPeriodMs() * 500), period = 2 * half;
        if (target && now > target + half) v8FlipsLate.fetch_add(1, std::memory_order_relaxed);
        else if (target && now < target - half) v8FlipsEarly.fetch_add(1, std::memory_order_relaxed);
        const int64_t grid = v8GridUs.load(std::memory_order_relaxed);
        const bool onTime = grid && ((now - grid) % period + period) % period < 2000;   // returned within 2 ms of a vblank (not a late wake-up)
        if (handOff && onTime) {   // the set-up time: from where this hand-off's flip landed
            const int64_t first = v8FirstUs.load(std::memory_order_relaxed), gap = first - v8HandOffAtUs.load(std::memory_order_relaxed);
            const int64_t lead = v8LeadUs.load(std::memory_order_relaxed);
            if (std::llabs(now - first) < half && gap < lead) v8LeadUs.store(std::max<int64_t>(200, gap - 50), std::memory_order_relaxed);   // made it with less
            else if (std::llabs(now - first - period) < half && gap >= lead)   // missed with more: up, by 0.5 ms at most per flip (one late wake-up is not the set-up time)
                v8LeadUs.store(std::min<int64_t>({ 8000, gap + 100, lead + 500 }), std::memory_order_relaxed);
        }
    }
}

void playbackStatsEnable(bool enabled) { hudEnabled.store(enabled,std::memory_order_relaxed); }
PlaybackStats playbackStats() {
    PlaybackStats s;
    s.decoderErrors=hudDecoderErrors.load(std::memory_order_relaxed);
    s.completed=hudCompleted.load(std::memory_order_relaxed); s.repeats=hudRepeats.load(std::memory_order_relaxed);
    s.completionUs=vblankUs.load(std::memory_order_relaxed);
    s.drops=hudDrops.load(std::memory_order_relaxed); s.width=hudWidth.load(std::memory_order_relaxed);
    s.height=hudHeight.load(std::memory_order_relaxed); s.codec=hudCodec.load(std::memory_order_relaxed); s.active=hudActive.load(std::memory_order_relaxed);
    s.decoderFailed=hudDecoderFailed.load(std::memory_order_relaxed); return s;
}

HolePacingStats holePunchPacingStats()   // OMNI_HOLEPUNCH_V4
{
    HolePacingStats st;
    std::lock_guard<std::mutex> l(plane.lock);
    st.pacing = plane.pacing; st.clockValid = plane.clock.valid; st.vblankReported = vblankReported();
    st.shown = plane.pacedShown; st.dropped = plane.pacedDropped; st.late = plane.pacedLate;
    st.waiting = unsigned(plane.paced.size());
    st.currentMediaUs = plane.current ? plane.current->mediaUs : INT64_MIN;
    st.clockUs = plane.clock.at(nowMs());
    return st;
}

namespace {
// OMNI_HOLEPUNCH_V4, shell main thread with plane.lock held: the newest paced picture due at the
// vblank this compose will be flipped on becomes the current one; older ones are dropped.
void holePaceSelect(double vblankAtMs = -1, int traceOrigin = 0)   // OMNI_HOLEPUNCH_V8_CADENCE: the vblank chosen for (V8); < 0: V5's guess
{
    diagnosticTrace(89, traceOrigin, plane.paced.size(), plane.current ? plane.current->mediaUs : INT64_MIN, int64_t(vblankAtMs*1000));
    if (focusActive.load(std::memory_order_relaxed)) {
        diagnosticTrace(141,traceOrigin,plane.paced.size(),plane.paced.empty()?INT64_MIN:plane.paced.front()->mediaUs,plane.clock.valid);
        diagnosticTrace(142,plane.current?plane.current->v8Seq:0,plane.cadence.diagnosticSelected(),int64_t(plane.cadence.diagnosticTargetMs()*1000),int64_t(vblankPeriodMs()*1000));
    }
    if (!plane.clock.valid || plane.paced.empty()) return;
    const int64_t due = vblankAtMs >= 0 ? plane.clock.at(vblankAtMs + vblankPeriodMs() / 2) : plane.clock.at(vblankAfter(nowMs() + composeLeadMs) + vblankMs / 2);
    const int64_t onScreen = plane.current ? plane.current->mediaUs : INT64_MIN;
    while (plane.shownInGen && onScreen != INT64_MIN && !plane.paced.empty() && plane.paced.front()->mediaUs <= onScreen) {
        diagnosticTrace(7,plane.paced.front()->mediaUs,1,plane.paced.size(),due);
        plane.spare.push_back(std::move(plane.paced.front())); plane.paced.pop_front(); plane.pacedDropped++;   // never step back
        if (v7On()) v7DropStale.fetch_add(1, std::memory_order_relaxed);   // OMNI_HOLEPUNCH_V7_REFLIP
    }
    size_t pick = SIZE_MAX;
    if (v9On() && vblankAtMs >= 0) {
        if (!plane.shownInGen || plane.posterPending) plane.cadence.reset();
        pick = plane.cadence.select(vblankAtMs, vblankPeriodMs(), due, plane.paced.size(),
            [](size_t i) { return plane.paced[i]->mediaUs; }, plane.posterPending);
    } else {
        for (size_t i = 0; i < plane.paced.size() && plane.paced[i]->mediaUs <= due; i++) pick = i;
        if (pick == SIZE_MAX && plane.posterPending && !plane.paced.empty()) pick = 0;
    }
    if (focusActive.load(std::memory_order_relaxed))
        diagnosticTrace(143,pick==SIZE_MAX?-1:int64_t(pick),due,plane.paced.empty()?INT64_MIN:plane.paced.front()->mediaUs,plane.posterPending);
    if (pick == SIZE_MAX) return;
    for (size_t i = 0; i < pick; i++) {
        diagnosticTrace(7,plane.paced.front()->mediaUs,2,plane.paced.size(),due);
        plane.spare.push_back(std::move(plane.paced.front())); plane.paced.pop_front(); plane.pacedDropped++;
        if (v7On() && plane.shownInGen && plane.clock.playing)   // OMNI_HOLEPUNCH_V7_REFLIP: why
            (v7SelectByPresenter || v7TickGapUs > int64_t(v7StallMs * 1000) ? v7DropStall : v7DropCadence).fetch_add(1, std::memory_order_relaxed);
    }
    auto layer = std::move(plane.paced.front());
    plane.paced.pop_front();
    if (v7On() && onScreen != INT64_MIN && layer->mediaUs > onScreen && plane.clock.playing) {   // OMNI_HOLEPUNCH_V7_REFLIP: the content's frame interval
        const int64_t step = layer->mediaUs - onScreen, known = v7FrameUs.load(std::memory_order_relaxed);
        if (step < 200000 && (!known || step < known * 3 / 2)) v7FrameUs.store(step, std::memory_order_relaxed);
        // OMNI_HOLEPUNCH_V8_CADENCE: the mean interval of single steps (a step of 1.5 intervals or more spans a drop)
        if (v8On() && step < 200000 && (!known || step < known * 3 / 2)) { v8StepUs.fetch_add(step, std::memory_order_relaxed); v8Steps.fetch_add(1, std::memory_order_relaxed); }
    }
    // Late: at least one vblank after the first one it was due at.
    if (plane.shownInGen && plane.clock.playing && double(due - layer->mediaUs) >= vblankMs * 1000 * plane.clock.rate + 1000) plane.pacedLate++;
    if (plane.current && plane.current.get() == plane.pinned) plane.pinnedRetired = std::move(plane.current);   // OMNI_HOLEPUNCH_V8_CADENCE: still being blended
    else if (plane.current) planeDiscard(std::move(plane.current));   // OMNI_PERF_B_V1: or kept for a record-only frame's before-flip
    plane.current = std::move(layer);
    if (v8On()) { plane.current->v8Seq = ++plane.v8Seq; plane.current->v8First = !plane.shownInGen; }   // OMNI_HOLEPUNCH_V8_CADENCE: newer = made current later, across seeks too
    diagnosticTrace(6,plane.current->mediaUs,plane.paced.size(),due,int64_t(vblankAtMs*1000));
    diagnosticTrace(95, plane.current->mediaUs, plane.current->v8Seq, traceOrigin, int64_t(vblankAtMs*1000));
    plane.pacedShown++; plane.shown++;
    plane.shownInGen = true; plane.posterPending = false;
}

// round(x / 255) for 0 <= x <= 255 * 255
inline unsigned div255(unsigned x) { x += 128; return (x + (x >> 8)) >> 8; }

// Page (premultiplied B,G,R,A) over video (canvas order, alpha 255) into the canvas. Runs
// of hole (alpha 0) and, on a B,G,R,A canvas, of opaque page are plain copies.
// OMNI_HOLEPUNCH_V7_REFLIP: with Record, the pixels taken from the video also go into v7Record
// (row y, first column x0); without it, the code is the one before.
// OMNI_HOLEPUNCH_MIX_SIMD_V1: premultiplied page (B,G,R,A) over video (canvas order), 8 pixels per step:
// out = page + div255(video * (255 - alpha)), saturated, alpha 255 -- the scalar formula bit for bit.
// Measured need: a 4K player's translucent control bar (~2.8M pixels) took ~30 ms per re-flip scalar.
__attribute__((target("avx2"))) static void omniBlendSpanAvx2(uint8_t* o, const uint8_t* page, const uint8_t* video, size_t n, bool swapRB)
{
    const __m256i swapMask = _mm256_setr_epi8(2,1,0,3, 6,5,4,7, 10,9,8,11, 14,13,12,15, 2,1,0,3, 6,5,4,7, 10,9,8,11, 14,13,12,15);
    const __m256i alphaMask = _mm256_setr_epi8(3,3,3,3, 7,7,7,7, 11,11,11,11, 15,15,15,15, 3,3,3,3, 7,7,7,7, 11,11,11,11, 15,15,15,15);
    const __m256i opaque = _mm256_set1_epi32(int(0xff000000u)), ones = _mm256_set1_epi8(-1), zero = _mm256_setzero_si256(), half = _mm256_set1_epi16(128);
    size_t i = 0;
    for (; i + 8 <= n; i += 8) {
        __m256i P = _mm256_loadu_si256(reinterpret_cast<const __m256i*>(page + 4 * i));
        const __m256i U = _mm256_loadu_si256(reinterpret_cast<const __m256i*>(video + 4 * i));
        const __m256i K = _mm256_sub_epi8(ones, _mm256_shuffle_epi8(P, alphaMask));   // 255 - a, every channel
        if (swapRB) P = _mm256_shuffle_epi8(P, swapMask);
        __m256i xl = _mm256_add_epi16(_mm256_mullo_epi16(_mm256_unpacklo_epi8(U, zero), _mm256_unpacklo_epi8(K, zero)), half);
        __m256i xh = _mm256_add_epi16(_mm256_mullo_epi16(_mm256_unpackhi_epi8(U, zero), _mm256_unpackhi_epi8(K, zero)), half);
        xl = _mm256_srli_epi16(_mm256_add_epi16(xl, _mm256_srli_epi16(xl, 8)), 8);
        xh = _mm256_srli_epi16(_mm256_add_epi16(xh, _mm256_srli_epi16(xh, 8)), 8);
        const __m256i lo = _mm256_add_epi16(_mm256_unpacklo_epi8(P, zero), xl), hi = _mm256_add_epi16(_mm256_unpackhi_epi8(P, zero), xh);
        _mm256_storeu_si256(reinterpret_cast<__m256i*>(o + 4 * i), _mm256_or_si256(_mm256_packus_epi16(lo, hi), opaque));
    }
    const int r = swapRB ? 0 : 2, b = swapRB ? 2 : 0;
    for (; i < n; ++i) {
        const uint8_t* sp = page + 4 * i; const uint8_t* u = video + 4 * i; uint8_t* d = o + 4 * i;
        const unsigned k = 255 - sp[3];
        d[b] = uint8_t(std::min(255u, sp[0] + div255(u[b] * k)));
        d[1] = uint8_t(std::min(255u, sp[1] + div255(u[1] * k)));
        d[r] = uint8_t(std::min(255u, sp[2] + div255(u[r] * k)));
        d[3] = 255;
    }
}
// OMNI_LAYER_READ_V1: video layers live in direct memory -- fast to write, slow to read with ordinary
// copies (the libc copy reads it a little at a time). Every read of a layer (compose, hand-off check,
// re-flip) goes through 32-byte streaming loads, as the tiler's own sweep does.
__attribute__((target("avx2"))) static void omniReadLayer(void* dst, const void* src, size_t bytes)
{
    uint8_t* d = static_cast<uint8_t*>(dst); const uint8_t* s = static_cast<const uint8_t*>(src);
    size_t head = (32 - (reinterpret_cast<uintptr_t>(s) & 31)) & 31; if (head > bytes) head = bytes;
    memcpy(d, s, head); d += head; s += head; bytes -= head;
    for (; bytes >= 128; bytes -= 128, s += 128, d += 128) {
        const __m256i a = _mm256_stream_load_si256(reinterpret_cast<const __m256i*>(s));
        const __m256i b = _mm256_stream_load_si256(reinterpret_cast<const __m256i*>(s + 32));
        const __m256i c = _mm256_stream_load_si256(reinterpret_cast<const __m256i*>(s + 64));
        const __m256i e = _mm256_stream_load_si256(reinterpret_cast<const __m256i*>(s + 96));
        _mm256_storeu_si256(reinterpret_cast<__m256i*>(d), a); _mm256_storeu_si256(reinterpret_cast<__m256i*>(d + 32), b);
        _mm256_storeu_si256(reinterpret_cast<__m256i*>(d + 64), c); _mm256_storeu_si256(reinterpret_cast<__m256i*>(d + 96), e);
    }
    for (; bytes >= 32; bytes -= 32, s += 32, d += 32) _mm256_storeu_si256(reinterpret_cast<__m256i*>(d), _mm256_stream_load_si256(reinterpret_cast<const __m256i*>(s)));
    memcpy(d, s, bytes);
}
static bool omniLayerEqual(const uint8_t* c, const uint8_t* v, size_t bytes)   // c: cached memory; v: a layer
{
    static thread_local std::vector<uint8_t> chunk; if (chunk.size() < 16384) chunk.resize(16384);
    for (size_t at = 0; at < bytes; at += 16384) {
        const size_t n = std::min<size_t>(16384, bytes - at);
        omniReadLayer(chunk.data(), v + at, n);
        if (memcmp(c + at, chunk.data(), n)) return false;
    }
    return true;
}
struct V7Record;
template <bool Record>
void holeBlendRowT(uint8_t* d, const uint8_t* p, const uint8_t* v, int n, bool swapRB, int y, int x0, V7Record* rec);
void holeBlendRow(uint8_t* d, const uint8_t* p, const uint8_t* v, int n, bool swapRB) { holeBlendRowT<false>(d, p, v, n, swapRB, 0, 0, nullptr); }
template <bool Record>
void holeBlendRowT(uint8_t* d, const uint8_t* p, const uint8_t* v, int n, bool swapRB, int y, int x0, V7Record* rec)
{
    static thread_local std::vector<uint8_t> vcache;   // OMNI_HOLEPUNCH_MIX_SPANS_V1
    size_t rowFirst = 0;   // OMNI_PERF_B_V7: spans never reach back into an earlier row
    if constexpr (Record) rowFirst = rec->mixPos.size();
    for (int i = 0; i < n;) {
        const unsigned a = p[4 * i + 3];
        if (!a || (a == 255 && !swapRB)) {
            int j = i + 1;
            while (j < n && p[4 * j + 3] == a) j++;
            if (a) memcpy(d + 4 * i, p + 4 * i, size_t(j - i) * 4); else omniReadLayer(d + 4 * i, v + 4 * i, size_t(j - i) * 4);   // OMNI_LAYER_READ_V1
            if constexpr (Record) {
                if (!a && rec->runs.size() + 3 <= v7MaxRuns) { rec->runs.push_back(uint32_t(y)); rec->runs.push_back(uint32_t(x0 + i)); rec->runs.push_back(uint32_t(j - i)); }
            }
            i = j;
            continue;
        }
        // OMNI_HOLEPUNCH_MIX_SIMD_V1: the whole span of translucent (and, on an RGBA canvas, opaque)
        // page pixels at once: the video span read once (wide loads), blended 8 pixels per step.
        int j = i + 1;
        while (j < n) { const unsigned aj = p[4 * j + 3]; if (!aj || (aj == 255 && !swapRB)) break; j++; }
        if (vcache.size() < size_t(j - i) * 4) vcache.resize(size_t(j - i) * 4);
        omniReadLayer(vcache.data(), v + 4 * i, size_t(j - i) * 4);   // OMNI_LAYER_READ_V1
        omniBlendSpanAvx2(d + 4 * i, p + 4 * i, vcache.data(), size_t(j - i), swapRB);
        if constexpr (Record) {   // V7_REV2: and what was written (mixOut), translucent pixels only
            bool anyOpaque = false;
            for (int q = i; q < j; ++q) if (p[4 * q + 3] == 255) { anyOpaque = true; break; }
            const size_t len = size_t(j - i), at = rec->mixPos.size();
            if (!anyOpaque && at + len <= v7MaxMix) {   // OMNI_HOLEPUNCH_MIX_SCAN_V1: the whole span at once
                rec->mixPos.resize(at + len); rec->mixPage.resize(at + len); rec->mixOut.resize(at + len);
                const uint32_t first = uint32_t(y) * uint32_t(rec->width) + uint32_t(x0 + i);
                for (size_t q = 0; q < len; ++q) rec->mixPos[at + q] = first + uint32_t(q);
                memcpy(rec->mixPage.data() + at, p + 4 * i, len * 4); memcpy(rec->mixOut.data() + at, d + 4 * i, len * 4);
                rec->mixSpans.push_back(uint32_t(at)); rec->mixSpans.push_back(uint32_t(len));   // OMNI_PERF_B_V7
            } else
            for (int q = i; q < j && rec->mixPos.size() < v7MaxMix; ++q) {
                if (p[4 * q + 3] == 255) continue;
                uint32_t page, out; memcpy(&page, p + 4 * q, 4); memcpy(&out, d + 4 * q, 4);
                rec->mixPos.push_back(uint32_t(y) * uint32_t(rec->width) + uint32_t(x0 + q)); rec->mixPage.push_back(page); rec->mixOut.push_back(out);
                const uint32_t idx = uint32_t(rec->mixPos.size() - 1);   // OMNI_PERF_B_V7: extend this row's last span, or start one
                const size_t ns = rec->mixSpans.size();
                if (ns >= 2 && rec->mixSpans[ns - 2] >= rowFirst && rec->mixSpans[ns - 2] + rec->mixSpans[ns - 1] == idx && rec->mixPos[idx - 1] + 1 == rec->mixPos[idx]) rec->mixSpans[ns - 1]++;
                else { rec->mixSpans.push_back(idx); rec->mixSpans.push_back(1); }
            }
        }
        i = j;
    }
}

// OMNI_HOLEPUNCH_V7_REFLIP: holeBlendRow, also recording (into v7Record) the pixels taken from the
// video: runs of hole pixels and translucent page pixels. Row y, first column x0 of the canvas.
void holeBlendRowRecord(uint8_t* d, const uint8_t* p, const uint8_t* v, int n, bool swapRB, int y, int x0)
{
    holeBlendRowT<true>(d, p, v, n, swapRB, y, x0, &v7Record);
}
// OMNI_PERF_B_V1: the end of the run of page pixels from i on that are all hole (kind 0: alpha 0), all opaque
// (kind 1: alpha 255) or all translucent (kind 2), 8 pixels per step.
__attribute__((target("avx2"))) static int omniAlphaRunEnd(const uint8_t* p, int i, int n, int kind)
{
    const __m256i zero = _mm256_setzero_si256(), full = _mm256_set1_epi32(255), ones = _mm256_set1_epi32(-1);
    for (; i + 8 <= n; i += 8) {
        const __m256i a = _mm256_srli_epi32(_mm256_loadu_si256(reinterpret_cast<const __m256i*>(p + 4 * i)), 24);
        const __m256i z = _mm256_cmpeq_epi32(a, zero), f = _mm256_cmpeq_epi32(a, full);
        const __m256i m = kind == 0 ? z : kind == 1 ? f : _mm256_andnot_si256(_mm256_or_si256(z, f), ones);
        const unsigned mask = unsigned(_mm256_movemask_ps(_mm256_castsi256_ps(m)));
        if (mask != 0xffu) return i + __builtin_ctz(~mask & 0xffu);
    }
    for (; i < n; ++i) {
        const unsigned a = p[4 * i + 3];
        if (kind == 0 ? a != 0 : kind == 1 ? a != 255 : (a == 0 || a == 255)) return i;
    }
    return n;
}
// OMNI_PERF_B_V1: true when `bytes` of cached memory are all zero.
__attribute__((target("avx2"))) static bool omniAllZero(const uint8_t* c, size_t bytes)
{
    size_t i = 0;
    for (; i + 128 <= bytes; i += 128) {
        const __m256i a = _mm256_or_si256(_mm256_loadu_si256(reinterpret_cast<const __m256i*>(c + i)), _mm256_loadu_si256(reinterpret_cast<const __m256i*>(c + i + 32)));
        const __m256i b = _mm256_or_si256(_mm256_loadu_si256(reinterpret_cast<const __m256i*>(c + i + 64)), _mm256_loadu_si256(reinterpret_cast<const __m256i*>(c + i + 96)));
        if (!_mm256_testz_si256(_mm256_or_si256(a, b), _mm256_or_si256(a, b))) return false;
    }
    for (; i < bytes; ++i) if (c[i]) return false;
    return true;
}
// OMNI_PERF_B_V1: record-only compose of one canvas row (y; first column x0; page row p over canvas row d, which
// already holds the page as the shell blitted it). Opaque page pixels stay as they are; hole runs go into the record
// as runs, translucent pixels as mix spans (position, page pixel); both are set to 0 in the canvas, so the hand-off
// can tell which of them the shell drew over afterwards. No video pixel is read or written here: the presenter
// writes the picture (holePunchBeforeFlip / re-flips). False when the record caps are reached.
bool holeRecordRowOnly(uint8_t* d, const uint8_t* p, int n, int y, int x0, V7Record& rec)
{
    for (int i = 0; i < n;) {
        const unsigned a = p[4 * i + 3];
        const int kind = a == 0 ? 0 : a == 255 ? 1 : 2;
        const int j = omniAlphaRunEnd(p, i + 1, n, kind);
        if (kind == 0) {
            if (rec.runs.size() + 3 > v7MaxRuns) return false;
            rec.runs.push_back(uint32_t(y)); rec.runs.push_back(uint32_t(x0 + i)); rec.runs.push_back(uint32_t(j - i));
            memset(d + 4 * size_t(i), 0, size_t(j - i) * 4);
        } else if (kind == 2) {
            const size_t len = size_t(j - i), at = rec.mixPos.size();
            if (at + len > v7MaxMix) return false;
            rec.mixPos.resize(at + len); rec.mixPage.resize(at + len);
            const uint32_t first = uint32_t(y) * uint32_t(rec.width) + uint32_t(x0 + i);
            for (size_t q = 0; q < len; ++q) rec.mixPos[at + q] = first + uint32_t(q);
            memcpy(rec.mixPage.data() + at, p + 4 * size_t(i), len * 4);
            rec.mixSpans.push_back(uint32_t(at)); rec.mixSpans.push_back(uint32_t(len));
            memset(d + 4 * size_t(i), 0, len * 4);
        }
        i = j;
    }
    return true;
}
// One translucent page pixel over video pixel u, as holeBlendRow writes it.
uint32_t holeBlendPixel(uint32_t page, const uint8_t* u, bool swapRB)
{
    uint8_t s[4], o[4];
    memcpy(s, &page, 4);
    const int r = swapRB ? 0 : 2, b = swapRB ? 2 : 0;
    const unsigned k = 255 - s[3];
    o[b] = uint8_t(std::min(255u, s[0] + div255(u[b] * k)));
    o[1] = uint8_t(std::min(255u, s[1] + div255(u[1] * k)));
    o[r] = uint8_t(std::min(255u, s[2] + div255(u[r] * k)));
    o[3] = 255;
    uint32_t out; memcpy(&out, o, 4);
    return out;
}
}

void holePunchCompose(uint8_t* canvas, int canvasPitch, int canvasWidth, int canvasHeight,
    int pageX, int pageY, const uint8_t* page, int pagePitch, int pageWidth, int pageHeight)
{
    // OMNI_HOLEPUNCH_V7_REFLIP: the presenter may re-flip meanwhile: one of the two at a time; what
    // this compose takes from the video is recorded for it
    std::unique_lock<std::mutex> v7Lock(v7ComposeLock, std::defer_lock);
    if (v7On()) { v7Lock.lock(); v7Record.valid = false; v7Record.handedOff = false; v7Record.runs.clear(); v7Record.mixPos.clear(); v7Record.mixPage.clear(); v7Record.mixOut.clear(); v7Record.mixSpans.clear(); v7Record.recordOnly = false; }
    plane.seenVersion = plane.version.load();
    HoleRect r;
    bool swapRB;
    bool pacing = false;   // OMNI_PERF_B_V1
    {
        std::lock_guard<std::mutex> l(plane.lock);
        plane.pinned = nullptr;   // OMNI_HOLEPUNCH_V8_CADENCE: a compose without a hand-off since
        if (plane.pinnedRetired) planeDiscard(std::move(plane.pinnedRetired));   // OMNI_PERF_B_V1: planeDiscard (flipPin)
        if (!plane.attached || plane.owner < 0) {
            if (plane.current) planeDiscard(std::move(plane.current));
            v1LastComposeRecordOnly.store(false, std::memory_order_relaxed);
            return;
        }
        if (plane.current && plane.current->epoch != plane.epoch) planeDiscard(std::move(plane.current));
        if (plane.ready) {
            if (plane.current) planeDiscard(std::move(plane.current));
            plane.current = std::move(plane.ready);
            plane.shown++;
        }
        pacing = plane.pacing;
        if (v8On()) holePaceSelect(vblankAfter(nowMs()), 1);   // OMNI_HOLEPUNCH_V8_CADENCE: the coming vblank (the hand-off moves it on)
        else holePaceSelect();   // OMNI_HOLEPUNCH_V4
        r = plane.rect;
        swapRB = plane.swapRB;
        if (v8On()) plane.pinned = plane.current.get();   // OMNI_HOLEPUNCH_V8_CADENCE: kept until the hand-off
    }
    const HoleLayer* layer = plane.current.get();
    // OMNI_HOLEPUNCH_V8_CADENCE: the blend reads only `layer` (pinned) and writes the canvas and the
    // record (this thread's): the presenter's re-flip need not wait for it.
    if (v8On() && v7Lock.owns_lock()) v7Lock.unlock();
    if (!layer || !canvas || !page) return;
    const double started = nowMs();
    // A layer still sized for the previous rect (rescale pending) is drawn at its own size.
    const int lx = pageX + r.x, ly = pageY + r.y;
    const int x0 = std::max({ lx, pageX, 0 }), y0 = std::max({ ly, pageY, 0 });
    const int x1 = std::min({ lx + layer->w, pageX + pageWidth, canvasWidth });
    const int y1 = std::min({ ly + layer->h, pageY + pageHeight, canvasHeight });
    if (v7On()) {   // OMNI_HOLEPUNCH_V7_REFLIP (V8: without v7ComposeLock)
        V7Record& rec = v7Record;
        rec.layer = layer; rec.swapRB = swapRB; rec.width = canvasWidth; rec.height = canvasHeight; rec.lx = lx; rec.ly = ly;
        // OMNI_PERF_B_V1: a paced video covering the whole canvas, shown by a presenter that writes every frame's video
        // pixels before it flips (V8 before-flip seen): the main thread records the mask only (11-23 ms at 4K -> ~3).
        const bool recordOnly = v1On() && v8On() && v8BeforeFlipSeen.load(std::memory_order_relaxed) && pacing
            && lx == 0 && ly == 0 && x0 == 0 && y0 == 0 && x1 == canvasWidth && y1 == canvasHeight
            && layer->w == canvasWidth && layer->h == canvasHeight && int64_t(canvasWidth) * canvasHeight > int64_t(2560) * 1440;
        bool recorded = false;
        if (recordOnly) {
            recorded = true;
            for (int y = y0; y < y1 && recorded; y++)
                recorded = holeRecordRowOnly(canvas + size_t(y) * canvasPitch, page + size_t(y - pageY) * pagePitch, x1 - x0, y, x0, rec);
            if (!recorded) { rec.runs.clear(); rec.mixPos.clear(); rec.mixPage.clear(); rec.mixSpans.clear(); }   // caps: blend every row below
        }
        rec.recordOnly = recorded;
        if (!recorded) {
            const uint8_t* px = holeLayerPx(layer);   // OMNI_PERF_B_V3
            for (int y = y0; y < y1; y++)
                holeBlendRowRecord(canvas + size_t(y) * canvasPitch + size_t(x0) * 4,
                    page + size_t(y - pageY) * pagePitch + size_t(x0 - pageX) * 4,
                    px + size_t(y - ly) * size_t(layer->stride) + size_t(x0 - lx) * 4, x1 - x0, swapRB, y, x0);
        }
        rec.valid = x1 > x0 && y1 > y0;
        v1LastComposeRecordOnly.store(recorded, std::memory_order_relaxed);
    } else {
    const uint8_t* px = holeLayerPx(layer);   // OMNI_PERF_B_V3
    for (int y = y0; y < y1; y++)
        holeBlendRow(canvas + size_t(y) * canvasPitch + size_t(x0) * 4,
            page + size_t(y - pageY) * pagePitch + size_t(x0 - pageX) * 4,
            px + size_t(y - ly) * size_t(layer->stride) + size_t(x0 - lx) * 4, x1 - x0, swapRB);   // OMNI_HOLEPUNCH_COLOUR_V1: stride
    }
    const double ms = nowMs() - started;
    { const bool ro = v7On() && v7Record.recordOnly; (ro ? pbComposeRecord : pbComposeBlend).fetch_add(1, std::memory_order_relaxed); (ro ? pbComposeRecordUs : pbComposeBlendUs).fetch_add(int64_t(ms * 1000), std::memory_order_relaxed); }   // OMNI_PERF_B_V1
    if (v8On()) v8Recent(v8ComposeUs, int64_t(ms * 1000));   // OMNI_HOLEPUNCH_V8_CADENCE: what a re-flip may wait for
    std::lock_guard<std::mutex> l(plane.lock);
    plane.composes++;
    plane.composeMs += ms;
}

// ---- OMNI_HOLEPUNCH_V7_REFLIP: the presenter thread ------------------------------------------
// OMNI_HOLEPUNCH_V7_REFLIP: the shell main thread's phases (patch-shell-stalltrace-v7.py).
void holePunchShellPhase(int phase)
{
    diagnosticTrace(28,phase);
    if (!v7On() || phase < 0 || phase >= v7Phases) return;   // OMNI_HOLEPUNCH_V7_REV2: V7 on only
    const int64_t now = int64_t(nowMs() * 1000);
    if (v7PhaseSeen) v7PhaseUs[v7Phase] += now - v7PhaseSinceUs;
    if (v7PhaseSeen && v7Phase == 4 && phase != 4) {   // a page copy (WKPagePaint) ended
        const int64_t took = now - v7PhaseSinceUs;
        v7Paints.fetch_add(1, std::memory_order_relaxed); v7Max(v7PaintMaxUs, took);
        if (took > 50000) {
            v7PaintsSlow.fetch_add(1, std::memory_order_relaxed);
            if (!v7PaintLastUs || v7PhaseSinceUs - v7PaintLastUs >= 10000000) v7PaintsSlowAfterIdle.fetch_add(1, std::memory_order_relaxed);
            v7Event(v7PhaseSinceUs, took, 2, 0);
        }
        v7PaintLastUs = v7PhaseSinceUs;
    }
    v7Phase = phase; v7PhaseSinceUs = now; v7PhaseSeen = true;
    v7PhaseNow.store(phase, std::memory_order_relaxed);
}

}
extern "C" __attribute__((weak)) char etext;   // end of code, from the linker (0 if absent)
namespace OmniMedia::Hw {
namespace {
#if defined(__clang__)
#define OMNI_V7_NO_SANITIZE __attribute__((no_sanitize("address", "thread", "undefined")))
#else
#define OMNI_V7_NO_SANITIZE __attribute__((no_sanitize_address, no_sanitize("thread", "undefined")))
#endif
char* v7Hex(char* p, uintptr_t v)
{
    *p++ = '0'; *p++ = 'x';
    for (int shift = 60; shift >= 0; shift -= 4) *p++ = "0123456789abcdef"[(v >> shift) & 15];
    *p++ = ' ';
    return p;
}
char* v7Dec(char* p, int64_t v)
{
    char digits[24]; int n = 0;
    if (v < 0) { *p++ = '-'; v = -v; }
    do { digits[n++] = char('0' + v % 10); v /= 10; } while (v && n < 20);
    while (n) *p++ = digits[--n];
    return p;
}
void v7Put(const char* text, char*& p) { while (*text) *p++ = *text++; }
// OMNI_HOLEPUNCH_V7_REV2: the handler's line (no write on the stalled thread: the sink can take
// 200 ms); the presenter passes it to the writer thread (v7SamplePublish). 0: empty.
char v7SampleText[1400];
std::atomic<int> v7SampleLen { 0 };
// On the stalled main thread itself (signal handler; async-signal-safe: write(2) only): the
// phase it is in and the code addresses on its stack (image offsets, innermost first), as the
// WebProcess watchdog (OMNI_HOLEPUNCH_V3) prints its player's.
OMNI_V7_NO_SANITIZE __attribute__((noinline)) void v7StackSignal(int)
{
    if (v7SampleLen.load(std::memory_order_acquire)) return;   // the last one is not written yet
    const int savedErrno = errno;
    volatile uintptr_t marker = 0;
    const uintptr_t sp = reinterpret_cast<uintptr_t>(&marker) & ~uintptr_t(7);
    uintptr_t end = sp + 16 * 1024;
    if (v7VirtualQuery) {
        struct { uintptr_t start, end, offset; int prot, type; unsigned char flags; char name[32]; } region {};
        if (!v7VirtualQuery(reinterpret_cast<const void*>(sp), 0, &region, sizeof region) && region.end > sp) end = std::min(region.end, sp + 64 * 1024);
    }
    struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts);
    const int64_t now = int64_t(ts.tv_sec) * 1000000 + ts.tv_nsec / 1000;
    static const char* const names[v7Phases] = { "outside tick (run loop)", "tick", "uBlock", "input", "page paint", "draw" };
    char* p = v7SampleText;
    v7Put("OMNI HOLEPUNCH: shell main thread stalled ", p); p = v7Dec(p, (now - v7PollUs.load(std::memory_order_relaxed)) / 1000);
    v7Put(" ms, in ", p); v7Put(names[std::clamp(v7PhaseNow.load(std::memory_order_relaxed), 0, v7Phases - 1)], p);
    v7Put("; stack (image offsets, innermost first): ", p);
    int found = 0;
    for (uintptr_t at = sp; at + 8 <= end && found < 48; at += 8) {   // 48 x 19 characters fit
        const uintptr_t v = *reinterpret_cast<const uintptr_t*>(at);
        if (v <= v7ImageBase || v >= v7CodeEnd) continue;
        p = v7Hex(p, v - v7ImageBase);
        ++found;
    }
    if (!found) v7Put("(nothing in the code range)", p);
    *p++ = '\n';
    v7SampleLen.store(int(p - v7SampleText), std::memory_order_release);
    errno = savedErrno;
}
void v7SamplePublish()   // presenter thread
{
    const int n = v7SampleLen.load(std::memory_order_acquire);
    if (n <= 0) return;
    v7LogPush(std::string(v7SampleText, size_t(n)));
    v7SampleLen.store(0, std::memory_order_release);
}
// Presenter thread: the main thread has not ticked for 150 ms or more: one stack sample (at most
// 6 per run, 10 s apart). SIGURG, only when nothing else handles it.
void v7SampleStalledMain(int64_t nowUs, int64_t stalledUs)
{
    if (stalledUs < 150000 || !v7MainKnown.load() || v7Samples.load() >= 6 || nowUs - v7SampleUs.load() < 10000000) return;
    if (!v7SampleTried) {
        v7SampleTried = true;
        struct sigaction previous {};
        if (sigaction(SIGURG, nullptr, &previous) || (previous.sa_handler != SIG_DFL && previous.sa_handler != SIG_IGN) || (previous.sa_flags & SA_SIGINFO)) {
            holeNote("shell stall stack samples off (SIGURG is in use)");
            return;
        }
        Dl_info image {};
        if (dladdr(reinterpret_cast<void*>(&holePunchShellPhase), &image)) v7ImageBase = reinterpret_cast<uintptr_t>(image.dli_fbase);
        const uintptr_t textEnd = reinterpret_cast<uintptr_t>(&etext);
        v7CodeEnd = textEnd > v7ImageBase ? textEnd : v7ImageBase + (256u << 20);
        v7VirtualQuery = reinterpret_cast<int (*)(const void*, int, void*, size_t)>(dlsym(RTLD_DEFAULT, "sceKernelVirtualQuery"));
        struct sigaction action {};
        sigemptyset(&action.sa_mask);
        action.sa_handler = v7StackSignal;
        action.sa_flags = SA_RESTART;
        v7SampleReady = !sigaction(SIGURG, &action, nullptr);
        holeNote("shell stall stack samples %s (image base %p, code to %p)", v7SampleReady ? "ready" : "off (sigaction failed)",
            reinterpret_cast<void*>(v7ImageBase), reinterpret_cast<void*>(v7CodeEnd));
    }
    if (!v7SampleReady) return;
    v7Samples.fetch_add(1); v7SampleUs.store(nowUs);
    pthread_kill(v7MainThread, SIGURG);
}
}

int holePunchReflipWaitMs()
{
    if (!v7On()) return -1;
    v7NoteThread(v7PresenterThreadInfo);
    bool largePlane = false;
    {
        std::lock_guard<std::mutex> l(plane.lock);
        if (!plane.attached || plane.owner < 0 || !plane.pacing || !plane.clock.valid || !plane.clock.playing) return -1;
        largePlane = int64_t(plane.rect.w) * plane.rect.h > int64_t(2560) * 1440;
    }
    const double now = nowMs();
    // Reserve measured preparation and handoff time before the predicted refresh,
    // plus 0.5 ms slack. The lower-resolution ceiling preserves the existing
    // UI handoff responsiveness; a universal fixed lead would ignore frame cost.
    // 4K copies can exceed the old 3.8 ms wake budget before flip submission even starts.
    // Keep the established <=1440p path; give larger planes measured preparation time,
    // bounded below one refresh period so the presenter cannot consume the whole cycle.
    const double maxMargin = largePlane ? std::max(v8MarginMaxMs, vblankPeriodMs() - 2.0) : v8MarginMaxMs;
    const double margin = v8On() ? std::clamp(double(v8LeadUs.load(std::memory_order_relaxed) + v8HandOffCostUs.load(std::memory_order_relaxed) + v8ReflipCostUs.load(std::memory_order_relaxed)) / 1000 + 0.5, v8MarginMs, maxMargin) : v7MarginMs;
    double at = vblankAfter(now) - margin;
    diagnosticTrace(90, v8GridUs.load(), int64_t(vblankPeriodMs()*1000), int64_t(margin*1000), int64_t(at*1000));
    int traceAdvances = 0;
    // The preparation deadline may have passed while the next vblank is still ahead.
    // Wake promptly; advancing a whole period here demonstrably skips that opportunity.
    at = std::max(at, now + 1.0); // v127: no whole-period delay after a missed wake deadline
    diagnosticTrace(91, int64_t(at*1000), int64_t(now*1000), traceAdvances, std::max(1, int(std::floor(at-now))));
    if (v8On()) return std::max(1, int(std::floor(at - now)));   // OMNI_HOLEPUNCH_V8_CADENCE: never after the margin (whole ms)
    return std::max(1, int(std::ceil(at - now)));
}

// OMNI_HOLEPUNCH_V7_REV2: a log line of the shell's presenter (OMNI PRESENT; it held omniPresentLock
// while v90 wrote it): V7 on, the writer thread writes it; off, written here as v90 did.
void holePunchLogLine(const char* line)
{
    if (!line) return;
    if (v7On()) { v7LogPush(std::string(line)); return; }
    fputs(line, stderr); fflush(stderr);
}

// Keep this opt-in until repeat, seek, overlay and long-session validation passes.
// Fusing the video copy with tiling removes a measured ~4.6 ms intermediate write;
// it must not change selection deadlines or permit the selected layer to be reused early.
// Experimental reduced-copy path. The caller keeps the existing compose ownership
// until the SDL helper has finished consuming the selected layer and live mask.
bool v139DirectEnabled()
{
    static const bool enabled = access("/data/omni/reduced-copy-test.flag", F_OK) == 0;
    return enabled && omniSDLDirectTile;
}
unsigned v8WriteLive(uint8_t* buf, int pitch, int width, const V7Live& live, const HoleLayer* now);
bool v139Direct(uint8_t* frame, int pitch, int width, int height, const V7Live& live, const HoleLayer* layer)
{
    if (!v139DirectEnabled() || !layer || !live.valid || !live.swapRB ||
        live.lx || live.ly || layer->w != width || layer->h != height ||
        int64_t(width)*height <= int64_t(2560)*1440 || layer->epoch != live.epoch)
        return false;
    // OMNI_HDR_AUTO_V1: a PQ layer at full size goes to the PQ buffer set (the flip shows real HDR); a large translucent
    // area over it (a control bar) is blended per pixel in PQ by the tiler, so that frame stays on the SDR set instead.
    if (!omniHDRFormatPQ() && omniHDRPQAvailable() && layer->hdrValid && omniSDLDirectTileHDR) {
        // OMNI_PERF_B_V3: a picture without its 8-bit copy (skipped while the PQ set showed the video) stays on the PQ set
        // even with a large translucent area, unless the service is making the copy right now (then that, below).
        const bool small = live.mixPos.size() <= 65536;
        int state = layer->pxState.load(std::memory_order_acquire);
        if (!small) {
            const unsigned px = unsigned(std::min<size_t>(live.mixPos.size(), 0xffffffffu));
            pbPqRefusedMix.fetch_add(1, std::memory_order_relaxed);
            unsigned seen = pbPqRefusedMixMax.load(std::memory_order_relaxed);
            while (px > seen && !pbPqRefusedMixMax.compare_exchange_weak(seen, px, std::memory_order_relaxed)) { }
            v3SdrNeededUs.store(v7MonoUs(), std::memory_order_relaxed);
            if (state == 1) {   // the service is making it: wait a little (about one conversion at most)
                const double until = nowMs() + 6;
                while (state == 1 && nowMs() < until) { usleep(200); state = layer->pxState.load(std::memory_order_acquire); }
            }
        }
        if (small || state != 2) {
            const int ok = omniSDLDirectTileHDR(frame, pitch, width, height, layer->hdrPx.data(), layer->stride,
                live.runs.data(), live.runs.size(), live.mixPos.data(), live.mixPage.data(), live.mixPos.size(), live.swapRB);
            diagnosticTrace(130, layer->mediaUs, ok, live.runs.size() / 3, live.mixPos.size());
            static unsigned notes = 0; if (notes < 6 && ok) { ++notes; holeNote("HDR auto: PQ set shows %dx%d HDR video", width, height); }
            if (ok && small) v3PqShownUs.store(v7MonoUs(), std::memory_order_relaxed);
            if (ok && !small) pbV3PqForced.fetch_add(1, std::memory_order_relaxed);
            if (ok) return true;
            v3SdrNeededUs.store(v7MonoUs(), std::memory_order_relaxed);
        }
    }
    if (omniHDRFormatPQ()) {   // OMNI_HDR_PORT_V1: the display is PQ: only the HDR tiler may write it
        if (!layer->hdrValid || !omniSDLDirectTileHDR) return false;
        const int ok = omniSDLDirectTileHDR(frame, pitch, width, height, layer->hdrPx.data(), layer->stride,
            live.runs.data(), live.runs.size(), live.mixPos.data(), live.mixPage.data(), live.mixPos.size(), live.swapRB);
        diagnosticTrace(130, layer->mediaUs, ok, live.runs.size() / 3, live.mixPos.size());
        return ok;
    }
    if (live.mixPos.size() > 65536) {
        // OMNI_HOLEPUNCH_MIX_TILE_V1: a large translucent area (a player's control bar at 4K, ~2.8M pixels)
        // made the tiler restore and blend millions of single pixels in tiled storage (~55 ms). Finish the
        // frame in the (cached) UI surface instead -- video runs copied, translucent spans blended 8 at a
        // time -- and tile that whole surface in one sweep: one run per row, nothing left to restore.
        static thread_local std::vector<uint32_t> fullRows;
        if (fullRows.size() != size_t(height) * 3) {
            fullRows.resize(size_t(height) * 3);
            for (int y = 0; y < height; ++y) { fullRows[3 * y] = uint32_t(y); fullRows[3 * y + 1] = 0; fullRows[3 * y + 2] = uint32_t(width); }
        }
        v8WriteLive(frame, pitch, width, live, layer);
        const int ok = omniSDLDirectTile(frame, pitch, width, height, frame, pitch, fullRows.data(), fullRows.size(), nullptr, nullptr, 0, live.swapRB);
        diagnosticTrace(130, layer->mediaUs, ok, live.runs.size() / 3, live.mixPos.size());
        return ok;
    }
    const int ok = omniSDLDirectTile(frame,pitch,width,height,holeLayerPx(layer),layer->stride,   // OMNI_PERF_B_V3: holeLayerPx
        live.runs.data(),live.runs.size(),live.mixPos.data(),live.mixPage.data(),live.mixPos.size(),live.swapRB);
    diagnosticTrace(130,layer->mediaUs,ok,live.runs.size()/3,live.mixPos.size());
    return ok;
}

// OMNI_HOLEPUNCH_V7_REV2 (shell main thread, omniPresentFrame, before the canvas goes to the
// presenter's frame; patch-shell-holepunch-v7-rev2.py): which of the last compose's pixels the
// finished canvas still holds (the shell may have drawn over some since: bars, pointer, dialogs).
// Cached memory, whole runs compared at once: ~0.1 ms at 960x540. The frame on screen is then
// described by v7Live; a re-flip writes only those pixels and reads nothing from the frame.
// OMNI_HOLEPUNCH_V8_CADENCE: picture `now` into the pixels v7Live describes (runs; translucent ones blended).
// OMNI_HOLEPUNCH_MIX_SPANS_V1: translucent page pixels over the video (a player's control-bar
// gradient) were written one 4-byte store at a time into the presenter's frame: at 4K with a
// gradient over the lower third (~2.8M pixels) a re-flip took ~55 ms. Consecutive positions on a
// row form a span: blended into a scratch row from the layer's row, then one memcpy into the frame.
static void omniWriteMixSpans(uint8_t* buf, int pitch, int width, const V7Live& live, const HoleLayer* now)
{
    // OMNI_HOLEPUNCH_MIX_SCAN_V1: span ends found by comparing against the row's end (a division per
    // pixel cost 17 ms of 26 at 2.8M pixels); blended straight into the frame (cached UI surface).
    static thread_local std::vector<uint32_t> vrow;
    const size_t stride = size_t(now->stride), n = live.mixPos.size();
    const uint32_t* pos = live.mixPos.data(); const uint32_t* page = live.mixPage.data();
    if (!n) return;   // OMNI_PERF_B_V3: no translucent pixel, no 8-bit copy needed here
    const double started = nowMs(); static double total = 0; static unsigned calls = 0;
    const uint8_t* px = holeLayerPx(now);   // OMNI_PERF_B_V3
    if (v7SpansOn()) {   // OMNI_PERF_B_V7: the spans the record found (no search per pixel)
        const uint32_t* sp = live.mixSpans.data(); const size_t ns = live.mixSpans.size();
        for (size_t s = 0; s + 1 < ns; s += 2) {
            const size_t k = sp[s], len = sp[s + 1];
            if (!len || k + len > n) continue;
            const uint32_t y = pos[k] / uint32_t(width), x = pos[k] - y * uint32_t(width);
            if (vrow.size() < len) vrow.resize(len);
            omniReadLayer(vrow.data(), px + size_t(int(y) - live.ly) * stride + size_t(int(x) - live.lx) * 4, len * 4);
            omniBlendSpanAvx2(buf + size_t(y) * size_t(pitch) + size_t(x) * 4, reinterpret_cast<const uint8_t*>(page + k), reinterpret_cast<const uint8_t*>(vrow.data()), len, live.swapRB);
        }
        total += nowMs() - started;
        if (++calls % 300 == 0 && calls <= 3000) { holeNote("translucent re-flip: %.2f ms avg for %zu pixels (%zu spans)", total / 300, n, ns / 2); total = 0; }
        return;
    }
    for (size_t k = 0; k < n;) {
        const uint32_t y = pos[k] / uint32_t(width), x = pos[k] - y * uint32_t(width), rowEnd = (y + 1) * uint32_t(width);
        size_t e = k + 1;
        while (e < n && pos[e] == pos[e - 1] + 1 && pos[e] < rowEnd) e++;
        const size_t len = e - k;
        if (vrow.size() < len) vrow.resize(len);
        omniReadLayer(vrow.data(), px + size_t(int(y) - live.ly) * stride + size_t(int(x) - live.lx) * 4, len * 4);
        omniBlendSpanAvx2(buf + size_t(y) * size_t(pitch) + size_t(x) * 4, reinterpret_cast<const uint8_t*>(page + k), reinterpret_cast<const uint8_t*>(vrow.data()), len, live.swapRB);
        k = e;
    }
    total += nowMs() - started;
    if (++calls % 300 == 0 && calls <= 3000) { holeNote("translucent re-flip: %.2f ms avg for %zu pixels", total / 300, n); total = 0; }   // first ~50 s only
}
// The hand-off's check of which translucent pixels the finished canvas still holds, by span.
std::vector<std::pair<uint32_t, uint32_t>> pbExtraMix;   // (position, page-order pixel); main thread (hand-off)
static inline uint32_t pbCanvasToPage(uint32_t c, bool swapRB) { return swapRB ? ((c & 0xff00ff00u) | ((c & 0xffu) << 16) | ((c >> 16) & 0xffu)) : c; }
static inline uint32_t pbOver(uint32_t a, uint32_t b)   // premultiplied a over b, any byte order (alpha in the top byte)
{
    const unsigned k = 255 - (a >> 24);
    uint32_t out = 0;
    for (int s = 0; s < 32; s += 8) out |= std::min(255u, ((a >> s) & 255u) + div255(((b >> s) & 255u) * k)) << s;
    return out;
}
template <typename Rec>
static void omniLiveMixFromRecord(const Rec& rec, const uint8_t* canvas, int pitch, int width, V7Live& live)
{
    if (v7SpansOn()) {   // OMNI_PERF_B_V7: span by span; a record-only canvas held 0 where the record is (V1)
        static const uint32_t zeros[64] = {};
        const size_t n = rec.mixPos.size(), ns = rec.mixSpans.size();
        auto keep = [&](size_t k, size_t len) {
            live.mixSpans.push_back(uint32_t(live.mixPos.size())); live.mixSpans.push_back(uint32_t(len));
            live.mixPos.insert(live.mixPos.end(), rec.mixPos.begin() + long(k), rec.mixPos.begin() + long(k + len));
            live.mixPage.insert(live.mixPage.end(), rec.mixPage.begin() + long(k), rec.mixPage.begin() + long(k + len));
        };
        for (size_t s = 0; s + 1 < ns; s += 2) {
            const size_t k = rec.mixSpans[s], len = rec.mixSpans[s + 1];
            if (!len || k + len > n) continue;
            const uint32_t y = rec.mixPos[k] / uint32_t(width), x = rec.mixPos[k] - y * uint32_t(width);
            const uint8_t* c = canvas + size_t(y) * size_t(pitch) + size_t(x) * 4;
            const bool same = rec.recordOnly ? omniAllZero(c, len * 4) : !memcmp(c, &rec.mixOut[k], len * 4);
            if (same) { keep(k, len); continue; }
            for (size_t i = 0; i < len;) {   // drawn over in part: the pieces still the record's
                auto match = [&](size_t q) { return !memcmp(c + q * 4, rec.recordOnly ? zeros : &rec.mixOut[k + q], 4); };
                if (!match(i)) {
                    if (rec.recordOnly) {   // OMNI_PERF_B_V1: the shell's pixel over the page's, both over the video
                        uint32_t u; memcpy(&u, c + i * 4, 4);
                        if ((u >> 24) != 255) pbExtraMix.emplace_back(rec.mixPos[k + i], pbOver(pbCanvasToPage(u, rec.swapRB), rec.mixPage[k + i]));
                    }
                    i++; continue;
                }
                size_t j = i + 1;
                while (j < len && match(j)) j++;
                keep(k + i, j - i);
                i = j;
            }
        }
        return;
    }
    const size_t n = rec.mixPos.size();
    for (size_t k = 0; k < n;) {
        size_t e = k + 1;
        const uint32_t y = rec.mixPos[k] / uint32_t(width), x = rec.mixPos[k] - y * uint32_t(width), rowEnd = (y + 1) * uint32_t(width);
        while (e < n && rec.mixPos[e] == rec.mixPos[e - 1] + 1 && rec.mixPos[e] < rowEnd) e++;   // OMNI_HOLEPUNCH_MIX_SCAN_V1
        const uint8_t* c = canvas + size_t(y) * size_t(pitch) + size_t(x) * 4;
        if (!memcmp(c, &rec.mixOut[k], (e - k) * 4)) {
            live.mixPos.insert(live.mixPos.end(), rec.mixPos.begin() + long(k), rec.mixPos.begin() + long(e));
            live.mixPage.insert(live.mixPage.end(), rec.mixPage.begin() + long(k), rec.mixPage.begin() + long(e));
        } else {
            for (size_t i = k; i < e; ++i)
                if (!memcmp(c + (i - k) * 4, &rec.mixOut[i], 4)) { live.mixPos.push_back(rec.mixPos[i]); live.mixPage.push_back(rec.mixPage[i]); }
        }
        k = e;
    }
}
unsigned v8WriteLive(uint8_t* buf, int pitch, int width, const V7Live& live, const HoleLayer* now)
{
    const size_t stride = size_t(now->stride);
    unsigned written = 0;
    diagnosticTrace(122, now->mediaUs, live.runs.size()/3, live.mixPos.size(), 0);
    const uint8_t* px = holeLayerPx(now);   // OMNI_PERF_B_V3
    for (size_t k = 0; k + 2 < live.runs.size(); k += 3) {
        const uint32_t y = live.runs[k], x = live.runs[k + 1], n = live.runs[k + 2];
        omniReadLayer(buf + size_t(y) * size_t(pitch) + size_t(x) * 4, px + size_t(int(y) - live.ly) * stride + size_t(int(x) - live.lx) * 4, size_t(n) * 4);
        written += n;
    }
    diagnosticTrace(123, now->mediaUs, written, live.mixPos.size(), 0);
    omniWriteMixSpans(buf, pitch, width, live, now); // OMNI_HOLEPUNCH_MIX_SPANS_V1
    diagnosticTrace(124, now->mediaUs, written, live.mixPos.size(), 0);
    return written + unsigned(live.mixPos.size());
}

// OMNI_PERF_B_V1: shell pixels drawn translucently over a record-only canvas's 0 placeholders. SDL's blend over
// (0,0,0,0) leaves the source premultiplied with its own alpha, so such a pixel is exactly a translucent layer over
// the video: it becomes a mix pixel of the mask (blended with every new picture), as page pixels are. Over a recorded
// translucent page pixel P the shell's U is first put over P (premultiplied over), so the result is U over P over video.
// The extra mix pixels into live (kept in raster order, as the tiler's per-pixel arrays were before).
static void pbMergeExtraMix(V7Live& live)
{
    if (pbExtraMix.empty()) return;
    std::vector<std::pair<uint32_t, uint32_t>> all; all.reserve(live.mixPos.size() + pbExtraMix.size());
    for (size_t i = 0; i < live.mixPos.size(); ++i) all.emplace_back(live.mixPos[i], live.mixPage[i]);
    all.insert(all.end(), pbExtraMix.begin(), pbExtraMix.end());
    pbExtraMix.clear();
    std::sort(all.begin(), all.end());
    live.mixPos.clear(); live.mixPage.clear(); live.mixSpans.clear();
    const uint32_t width = uint32_t(std::max(1, live.width));
    for (size_t i = 0; i < all.size(); ++i) {
        const uint32_t pos = all[i].first;
        if (i && pos == all[i - 1].first) continue;
        const size_t ns = live.mixSpans.size();
        if (ns && live.mixPos.back() + 1 == pos && pos % width) live.mixSpans[ns - 1]++;
        else { live.mixSpans.push_back(uint32_t(live.mixPos.size())); live.mixSpans.push_back(1); }
        live.mixPos.push_back(pos); live.mixPage.push_back(all[i].second);
    }
}
// OMNI_PERF_B_V1: the record's hole runs the finished canvas still holds, into live (runs cleared by the caller): a
// blended record is compared with the picture (as before), a record-only one with 0 (cached memory only).
static void holeLiveRunsFromRecord(const V7Record& rec, const uint8_t* canvas, int pitch, const HoleLayer* layer, V7Live& live)
{
    pbExtraMix.clear();
    const size_t stride = size_t(layer->stride);
    const uint8_t* px = rec.recordOnly ? nullptr : holeLayerPx(layer);   // OMNI_PERF_B_V3
    static const uint32_t zero = 0;
    for (size_t k = 0; k + 2 < rec.runs.size(); k += 3) {
        const uint32_t y = rec.runs[k], x = rec.runs[k + 1], n = rec.runs[k + 2];
        const uint8_t* c = canvas + size_t(y) * size_t(pitch) + size_t(x) * 4;
        const uint8_t* v = px ? px + size_t(int(y) - rec.ly) * stride + size_t(int(x) - rec.lx) * 4 : nullptr;
        if (px ? omniLayerEqual(c, v, size_t(n) * 4) : omniAllZero(c, size_t(n) * 4)) { live.runs.push_back(y); live.runs.push_back(x); live.runs.push_back(n); continue; }
        auto same = [&](uint32_t q) { return !memcmp(c + 4 * size_t(q), px ? v + 4 * size_t(q) : reinterpret_cast<const uint8_t*>(&zero), 4); };
        for (uint32_t i = 0; i < n;) {   // drawn over in part: keep the pieces still the video's
            if (!same(i)) {
                if (!px) {   // record-only: a translucent shell pixel over the video
                    uint32_t u; memcpy(&u, c + 4 * size_t(i), 4);
                    if ((u >> 24) != 255) pbExtraMix.emplace_back(y * uint32_t(rec.width) + x + i, pbCanvasToPage(u, rec.swapRB));
                }
                i++; continue;
            }
            uint32_t j = i + 1;
            while (j < n && same(j)) j++;
            live.runs.push_back(y); live.runs.push_back(x + i); live.runs.push_back(j - i);
            i = j;
        }
    }
}
// OMNI_PERF_B_V1: a record-only canvas whose mask cannot be handed to the presenter (the owner changed meanwhile, or
// no hand-off could be prepared): its recorded pixels get the composed picture here, as a blending compose writes
// them, so the frame never shows the 0 placeholders. The layer is rec.layer, still pinned (checked by the caller).
static void holeFillRecordOnly(uint8_t* canvas, int pitch, const V7Record& rec)
{
    const HoleLayer* L = rec.layer;
    if (!L) return;
    const uint8_t* px = holeLayerPx(L);
    const size_t stride = size_t(L->stride);
    for (size_t k = 0; k + 2 < rec.runs.size(); k += 3) {
        const uint32_t y = rec.runs[k], x = rec.runs[k + 1], n = rec.runs[k + 2];
        omniReadLayer(canvas + size_t(y) * size_t(pitch) + size_t(x) * 4, px + size_t(int(y) - rec.ly) * stride + size_t(int(x) - rec.lx) * 4, size_t(n) * 4);
    }
    static thread_local std::vector<uint32_t> vrow;
    for (size_t s = 0; s + 1 < rec.mixSpans.size(); s += 2) {
        const size_t k = rec.mixSpans[s], len = rec.mixSpans[s + 1];
        if (!len || k + len > rec.mixPos.size()) continue;
        const uint32_t y = rec.mixPos[k] / uint32_t(rec.width), x = rec.mixPos[k] - y * uint32_t(rec.width);
        if (vrow.size() < len) vrow.resize(len);
        omniReadLayer(vrow.data(), px + size_t(int(y) - rec.ly) * stride + size_t(int(x) - rec.lx) * 4, len * 4);
        omniBlendSpanAvx2(canvas + size_t(y) * size_t(pitch) + size_t(x) * 4, reinterpret_cast<const uint8_t*>(rec.mixPage.data() + k), reinterpret_cast<const uint8_t*>(vrow.data()), len, rec.swapRB);
    }
    pbRecordFilled.fetch_add(1, std::memory_order_relaxed);
}
// OMNI_PERF_B_V1/V2 (hand-off, under v7ComposeLock and plane.lock): what the presenter now owns.
static void holeHandOffPublish(const V7Live& live, const V7Record& rec)
{
    const bool recordOnly = live.valid && live.recordOnly;
    if (recordOnly) { planeReleaseFlipPin(); plane.flipPin = rec.layer; pbHandOffRecordOnly.fetch_add(1, std::memory_order_relaxed); }
    pbLiveRecordOnly.store(recordOnly, std::memory_order_release);
    pbOwnsVideo.store(live.valid && !live.lx && !live.ly && live.w == live.width && live.h == live.height
        && int64_t(live.w) * live.h > int64_t(2560) * 1440 && plane.pacing && plane.attached && plane.owner >= 0, std::memory_order_relaxed);
}

// Build the mask from the UI-owned canvas and its pinned immutable video layer.
// The presenter keeps using v7Live; only holePunchHandOff publishes the staged mask.
void holePunchPrepareHandOff(const uint8_t* canvas, int pitch, int width, int height)
{
    v130PendingReady = false;
    if (!v8On() || !canvas || !v8BeforeFlipSeen.load(std::memory_order_relaxed)) return;
    OmniServiceTraceScope prepareScope(96);
    V7Record& rec = v7Record; // UI-thread-owned, as in holePunchCompose
    const HoleLayer* layer = nullptr;
    {
        std::lock_guard<std::mutex> composing(v7ComposeLock);
        std::lock_guard<std::mutex> l(plane.lock);
        if (!rec.valid || rec.handedOff || rec.width != width || rec.height != height) return;
        layer = rec.layer;
        if (!layer || layer != plane.pinned || layer->epoch != plane.epoch ||
            int64_t(layer->w) * layer->h <= int64_t(2560) * 1440) return;
    }
    // The UI owns the pin until handoff or its next compose. Reflip retires a
    // pinned layer instead of recycling it, exactly as for unlocked composition.
    V7Live& live = v130PendingLive;
    const int64_t prepStarted = v7MonoUs();   // OMNI_PERF_B_V1
    live.runs.clear(); live.mixPos.clear(); live.mixPage.clear(); live.mixSpans.clear();
    holeLiveRunsFromRecord(rec, canvas, pitch, layer, live);   // OMNI_PERF_B_V1 (record-only: compared with 0)
    omniLiveMixFromRecord(rec, canvas, pitch, width, live); // OMNI_HOLEPUNCH_MIX_SPANS_V1
    live.width = width; pbMergeExtraMix(live);   // OMNI_PERF_B_V1
    live.width = width; live.height = height; live.lx = rec.lx; live.ly = rec.ly; live.w = layer->w; live.h = layer->h;
    live.swapRB = rec.swapRB; live.shownUs = layer->mediaUs; live.epoch = layer->epoch;
    live.v8ShownSeq = layer->v8Seq; live.v8First = layer->v8First;   // OMNI_HOLEPUNCH_V8_CADENCE
    live.valid = !live.runs.empty() || !live.mixPos.empty();
    live.recordOnly = rec.recordOnly;   // OMNI_PERF_B_V1
    pbPrepareUs.fetch_add(v7MonoUs() - prepStarted, std::memory_order_relaxed); pbPrepares.fetch_add(1, std::memory_order_relaxed);
    v130PendingCanvas = canvas;
    v130PendingReady = true;
}

void holePunchHandOff(const uint8_t* canvas, int pitch, int width, int height)
{
    if (!v7On() || !canvas) return;
    const int64_t started = v7MonoUs();
    if (omniPipelineScope) omniPipelineScope(40,90,0,0);
    std::lock_guard<std::mutex> composing(v7ComposeLock);
    if (omniPipelineScope) omniPipelineScope(41,90,0,0);
    OmniServiceTraceScope traceHandoff(91);
    V7Record& rec = v7Record;
    V7Live& live = v7Live;
    if (v130PendingReady && v130PendingCanvas == canvas &&
        v130PendingLive.width == width && v130PendingLive.height == height) {
        v130PendingReady = false;
        bool fill = false;   // OMNI_PERF_B_V1
        {
            std::lock_guard<std::mutex> l(plane.lock);
            if (rec.layer != plane.pinned || v130PendingLive.epoch != plane.epoch)
                v130PendingLive.valid = false;
            std::swap(live, v130PendingLive);
            rec.handedOff = true;
            // OMNI_PERF_B_V1: a record-only canvas the presenter will not fill gets its picture here (rec.layer still pinned)
            fill = rec.recordOnly && !live.valid && rec.layer && rec.layer == plane.pinned;
            if (rec.recordOnly && !live.valid && !fill) pbFlipNoPicture.fetch_add(1, std::memory_order_relaxed);
            if (!fill) {
                holeHandOffPublish(live, rec);
                plane.pinned = nullptr;
                if (plane.pinnedRetired) planeDiscard(std::move(plane.pinnedRetired));
            }
        }
        if (fill) {
            holeFillRecordOnly(const_cast<uint8_t*>(canvas), pitch, rec);   // the shell's own canvas (const only as passed)
            live.recordOnly = false;
            std::lock_guard<std::mutex> l(plane.lock);
            holeHandOffPublish(live, rec);
            plane.pinned = nullptr;
            if (plane.pinnedRetired) planeDiscard(std::move(plane.pinnedRetired));
        }
        const int64_t us = v7MonoUs() - started;
        v8Recent(v8HandOffCostUs, us);
        diagnosticTrace(88,live.shownUs,live.v8ShownSeq,live.valid,live.epoch);
        v7HandOffs.fetch_add(1, std::memory_order_relaxed);
        v7HandOffUs.fetch_add(us, std::memory_order_relaxed); v7Max(v7HandOffMaxUs, us);
        return;
    }
    live.valid = false;
    pbLiveRecordOnly.store(false, std::memory_order_release); pbOwnsVideo.store(false, std::memory_order_relaxed);   // OMNI_PERF_B_V1/V2
    const bool fresh = rec.valid && !rec.handedOff && rec.width == width && rec.height == height;
    rec.handedOff = true;   // a second hand-off without a compose: no video pixels known in it
    if (!fresh) return;
    const HoleLayer* layer;
    bool fillOnly = false;   // OMNI_PERF_B_V1
    {
        std::lock_guard<std::mutex> l(plane.lock);
        layer = plane.current.get();
        // OMNI_HOLEPUNCH_V8_CADENCE: the presenter may have made a newer picture current: the
        // canvas is checked against the compose's (pinned, still allocated); then brought up to date.
        if (v8On() && rec.layer && rec.layer == plane.pinned) layer = rec.layer;
        if (!layer || layer != rec.layer || layer->epoch != plane.epoch) {   // re-flipped meanwhile: the next compose
            fillOnly = rec.recordOnly && rec.layer && rec.layer == plane.pinned;   // OMNI_PERF_B_V1: never flip the 0 placeholders
            if (rec.recordOnly && !fillOnly) pbFlipNoPicture.fetch_add(1, std::memory_order_relaxed);
            if (!fillOnly) return;
        }
    }
    if (fillOnly) {
        holeFillRecordOnly(const_cast<uint8_t*>(canvas), pitch, rec);
        std::lock_guard<std::mutex> l(plane.lock);
        plane.pinned = nullptr;
        if (plane.pinnedRetired) planeDiscard(std::move(plane.pinnedRetired));
        return;
    }
    live.runs.clear(); live.mixPos.clear(); live.mixPage.clear(); live.mixSpans.clear();
    holeLiveRunsFromRecord(rec, canvas, pitch, layer, live);   // OMNI_PERF_B_V1
    omniLiveMixFromRecord(rec, canvas, pitch, width, live); // OMNI_HOLEPUNCH_MIX_SPANS_V1
    live.width = width; pbMergeExtraMix(live);   // OMNI_PERF_B_V1
    live.width = width; live.height = height; live.lx = rec.lx; live.ly = rec.ly; live.w = layer->w; live.h = layer->h;
    live.swapRB = rec.swapRB; live.shownUs = layer->mediaUs; live.epoch = layer->epoch;
    live.v8ShownSeq = layer->v8Seq; live.v8First = layer->v8First;   // OMNI_HOLEPUNCH_V8_CADENCE
    live.valid = !live.runs.empty() || !live.mixPos.empty();
    live.recordOnly = rec.recordOnly;   // OMNI_PERF_B_V1
    if (live.recordOnly && !live.valid) { holeFillRecordOnly(const_cast<uint8_t*>(canvas), pitch, rec); live.recordOnly = false; }
    if (v8On() && live.valid) {
        OmniServiceTraceScope traceReselect(92); // measurement only
        const bool presenterSelects = v8BeforeFlipSeen.load(std::memory_order_relaxed) && int64_t(live.w) * live.h > int64_t(2560) * 1440;
        // OMNI_HOLEPUNCH_V8_CADENCE: the picture due at the vblank this canvas's flip reaches
        const double handedAt = nowMs(), target = vblankAfter(handedAt + double(v8LeadUs.load(std::memory_order_relaxed)) / 1000);
        if (!v8BeforeFlipSeen.load(std::memory_order_relaxed)) { v8HandOffAtUs.store(int64_t(handedAt * 1000), std::memory_order_relaxed); v8FirstUs.store(int64_t(vblankAfter(handedAt) * 1000), std::memory_order_relaxed); }
        const HoleLayer* due = nullptr;
        {
            std::lock_guard<std::mutex> l(plane.lock);
            if (!presenterSelects && !live.v8First && plane.attached && plane.owner >= 0 && plane.pacing && plane.clock.valid && plane.clock.playing && !plane.ready && live.epoch == plane.epoch) {   // a seek's target: as composed
                holePaceSelect(target, 2);
                due = plane.current.get();
                if (due && (due->epoch != plane.epoch || due->v8Seq <= live.v8ShownSeq || due->w != live.w || due->h != live.h)) due = nullptr;
            }
        }
        // The canvas is the shell's own buffer (const here only as omniPresentFrame passes it).
        if (due) { v8WriteLive(const_cast<uint8_t*>(canvas), pitch, width, live, due); live.shownUs = due->mediaUs; live.v8ShownSeq = due->v8Seq; live.v8First = false; v8Reselects.fetch_add(1, std::memory_order_relaxed); }
        if (!v8BeforeFlipSeen.load(std::memory_order_relaxed)) { v8TargetUs.store(int64_t(target * 1000), std::memory_order_relaxed); v8TargetHandOff.store(true, std::memory_order_relaxed); }
        else v8HandOffAtUs.store(0, std::memory_order_relaxed);   // the before-flip call times it
    }
    if (v8On()) {   // the canvas no longer needs the compose's picture
        std::lock_guard<std::mutex> l(plane.lock);
        holeHandOffPublish(live, rec);   // OMNI_PERF_B_V1/V2 (a record-only canvas keeps its picture until the before-flip)
        plane.pinned = nullptr;
        if (plane.pinnedRetired) planeDiscard(std::move(plane.pinnedRetired));
    }
    const int64_t us = v7MonoUs() - started;
    if (v8On()) v8Recent(v8HandOffCostUs, us);   // OMNI_HOLEPUNCH_V8_CADENCE
    diagnosticTrace(88,live.shownUs,live.v8ShownSeq,live.valid,live.epoch);
    v7HandOffs.fetch_add(1, std::memory_order_relaxed); v7HandOffUs.fetch_add(us, std::memory_order_relaxed); v7Max(v7HandOffMaxUs, us);
}

// OMNI_HOLEPUNCH_V8_CADENCE (presenter thread, patch-shell-holepunch-v8.py): right before it flips a
// canvas the main thread handed off: the frame gets the picture due at the vblank this flip call will
// reach, as the presenter calls it (the main thread's hand-off guessed for the main thread's time; a
// presenter that wakes later, sharing a core with it, made that guess wrong); the set-up time is
// learned from these calls. V8 off: nothing.
// V143 opt-in polish: early canvas wakes have reused a completed frame while the
// next converted frame arrived 1.3-8.2 ms later, before the upcoming refresh. Wait
// only inside the existing preparation budget, never while holding either lock.
// UI pixels remain owned by the busy presenter; handoff, tiling and fallback are unchanged.
void v143WaitEmptyQueue(std::unique_lock<std::mutex>& composing, int width, int height, bool enabled)
{
    if (!enabled) return;
    if (!v139DirectEnabled() || !v143CompletedSeq || int64_t(width)*height <= int64_t(2560)*1440) {
        diagnosticTrace(148,-1,v143CompletedSeq,width,height); return;
    }
    auto compatible = [&] {
        const auto& live = v7Live;
        return live.valid && live.swapRB && !live.lx && !live.ly && !live.v8First &&
            live.width==width && live.height==height && live.w==width && live.h==height &&
            live.epoch==v143CompletedEpoch && live.v8ShownSeq==v143CompletedSeq &&
            plane.attached && plane.owner>=0 && plane.pacing && plane.clock.valid && plane.clock.playing &&
            plane.startupPresentationReady && plane.shownInGen && !plane.posterPending && !plane.ready &&
            plane.epoch==live.epoch && plane.current && plane.current->epoch==live.epoch &&
            plane.current->v8Seq==v143CompletedSeq;
    };
    {
        std::unique_lock<std::mutex> state(plane.lock,std::try_to_lock);
        if (!state.owns_lock()) { diagnosticTrace(148,-2,0,0,0); return; }
        // V144 scoped validation: report eligibility, not a relaxed gate. Preserve
        // rejection evidence so run-to-run noise cannot be credited to this wait.
        const auto& live=v7Live;
        const uint64_t bits = (uint64_t(live.valid)<<0) | (uint64_t(live.swapRB)<<1) |
            (uint64_t(!live.lx && !live.ly)<<2) | (uint64_t(!live.v8First)<<3) |
            (uint64_t(live.width==width && live.height==height && live.w==width && live.h==height)<<4) |
            (uint64_t(live.epoch==v143CompletedEpoch)<<5) | (uint64_t(live.v8ShownSeq==v143CompletedSeq)<<6) |
            (uint64_t(plane.attached)<<7) | (uint64_t(plane.owner>=0)<<8) | (uint64_t(plane.pacing)<<9) |
            (uint64_t(plane.clock.valid)<<10) | (uint64_t(plane.clock.playing)<<11) |
            (uint64_t(plane.startupPresentationReady)<<12) | (uint64_t(plane.shownInGen)<<13) |
            (uint64_t(!plane.posterPending)<<14) | (uint64_t(!plane.ready)<<15) |
            (uint64_t(plane.epoch==live.epoch)<<16) | (uint64_t(plane.current && plane.current->epoch==live.epoch)<<17) |
            (uint64_t(plane.current && plane.current->v8Seq==v143CompletedSeq)<<18) | (uint64_t(plane.paced.empty())<<19);
        diagnosticTrace(148,bits,live.v8ShownSeq,v143CompletedSeq,plane.current ? plane.current->v8Seq : 0);
        if (!compatible() || !plane.paced.empty()) return;
    }
    const double started=nowMs(), period=vblankPeriodMs();
    const double margin=std::clamp(double(v8LeadUs.load(std::memory_order_relaxed)+
        v8HandOffCostUs.load(std::memory_order_relaxed)+v8ReflipCostUs.load(std::memory_order_relaxed))/1000+0.5,
        v8MarginMs,std::max(v8MarginMaxMs,period-2.0));
    const double deadline=vblankAfter(started)-margin;
    if (deadline-started<0.25) { diagnosticTrace(149,int64_t((deadline-started)*1000),int64_t(started*1000),int64_t(margin*1000),v143CompletedSeq); return; }
    diagnosticTrace(146,int64_t(started*1000),int64_t(deadline*1000),v143CompletedSeq,int64_t(margin*1000));
    int reason=0; // 0 budget exhausted, 1 queue ready, 2 state changed, 3 compose busy at exit
    while (nowMs()<deadline) {
        if (composing.owns_lock()) composing.unlock();
        usleep(200);
        if (!composing.try_lock()) continue;
        std::unique_lock<std::mutex> state(plane.lock,std::try_to_lock);
        if (!state.owns_lock()) continue;
        if (!compatible()) { reason=2; break; }
        if (!plane.paced.empty()) { reason=1; break; }
    }
    if (!composing.owns_lock() && !composing.try_lock()) reason=3;
    diagnosticTrace(147,reason,int64_t((nowMs()-started)*1000),v143CompletedSeq,int64_t(deadline*1000));
}

void holePunchBeforeFlip(uint8_t* frame, int pitch, int width, int height)
{
    v143PreparedSeq = v143PreparedEpoch = 0;
    diagnosticTrace(125, 0, width, height, 0);
    if (!v8On() || !frame) return;
    v8BeforeFlipSeen.store(true, std::memory_order_relaxed);
    // OMNI_PERF_B_V1: a record-only canvas holds no video yet: this call must write it, so it waits for the lock
    // (held only briefly by others: the start of a compose, a mask check; a hand-off cannot run while this flips).
    const bool recordOnly = pbLiveRecordOnly.exchange(false, std::memory_order_acq_rel);
    std::unique_lock<std::mutex> composing(v7ComposeLock, std::try_to_lock);   // free: a hand-off waits for the presenter
    if (!composing.owns_lock() && recordOnly) composing.lock();
    if (!composing.owns_lock()) { diagnosticTrace(87,3,1,0,0); return; }
    static const bool waitEmptyQueue = access("/data/omni/empty-queue-wait-test.flag",F_OK)==0;
    v143WaitEmptyQueue(composing,width,height,waitEmptyQueue);
    if (!composing.owns_lock() && recordOnly) composing.lock();
    if (!composing.owns_lock()) return; // Preserve original try-lock/fallback behavior.
    V7Live& live = v7Live;
    const double callAt = nowMs(), target = vblankAfter(callAt + double(v8LeadUs.load(std::memory_order_relaxed)) / 1000);
    if (live.valid && live.width == width && live.height == height) {
        const HoleLayer* due = nullptr;
        {
            std::lock_guard<std::mutex> l(plane.lock);
            // V133: this runs on the awake presenter, after a valid handoff, even while playback is held.
            if (!plane.startupPresentationReady && live.v8ShownSeq && plane.attached && plane.owner >= 0 && plane.pacing && plane.clock.valid && live.epoch == plane.epoch) {
                plane.startupPresentationReady = true;
                diagnosticTrace(114,plane.owner,7,plane.startupGeneration,live.v8ShownSeq);
            }
            if (!live.v8First && plane.attached && plane.owner >= 0 && plane.pacing && plane.clock.valid && plane.clock.playing && !plane.ready && live.epoch == plane.epoch) {   // a seek's target: as composed
                holePaceSelect(target, 3);
                due = plane.current.get();
                if (due && (due->epoch != plane.epoch || due->v8Seq <= live.v8ShownSeq || due->w != live.w || due->h != live.h)) due = nullptr;
            }
        }
        // Even a repeated video frame needs a fresh tiled output after a canvas handoff.
        if (!due && (v139DirectEnabled() || live.recordOnly)) {   // OMNI_PERF_B_V1: a record-only frame always
            std::lock_guard<std::mutex> l(plane.lock);
            if (plane.current && plane.current->v8Seq == live.v8ShownSeq && plane.current->epoch == live.epoch)
                due = plane.current.get();
        }
        if (!due && live.recordOnly) {   // OMNI_PERF_B_V1: any picture of this owner and size; else the composed one (flipPin)
            std::lock_guard<std::mutex> l(plane.lock);
            const HoleLayer* cur = plane.current.get();
            if (cur && cur->epoch == live.epoch && cur->w == live.w && cur->h == live.h && cur->v8Seq >= live.v8ShownSeq) due = cur;
            else if (plane.flipPin && plane.flipPin->epoch == live.epoch && plane.flipPin->w == live.w && plane.flipPin->h == live.h) { due = plane.flipPin; pbFlipPinFallback.fetch_add(1, std::memory_order_relaxed); }
        }
        if (due) { if (!v139Direct(frame,pitch,width,height,live,due)) v8WriteLive(frame, pitch, width, live, due); live.shownUs = due->mediaUs; live.v8ShownSeq = due->v8Seq; live.v8First = false; v8BeforeFlips.fetch_add(1, std::memory_order_relaxed); }
        else if (live.recordOnly) pbFlipNoPicture.fetch_add(1, std::memory_order_relaxed);
    } else if (recordOnly) pbFlipNoPicture.fetch_add(1, std::memory_order_relaxed);
    if (recordOnly) { std::lock_guard<std::mutex> l(plane.lock); planeReleaseFlipPin(); }   // OMNI_PERF_B_V1: the frame has its video now
    const double at = nowMs();
    v8TargetUs.store(int64_t(vblankAfter(at + double(v8LeadUs.load(std::memory_order_relaxed)) / 1000) * 1000), std::memory_order_relaxed);
    v8HandOffAtUs.store(int64_t(at * 1000), std::memory_order_relaxed); v8FirstUs.store(int64_t(vblankAfter(at) * 1000), std::memory_order_relaxed);
    v8TargetHandOff.store(true, std::memory_order_relaxed);
    v143PreparedSeq = live.valid ? live.v8ShownSeq : 0; v143PreparedEpoch = live.epoch;
    diagnosticTrace(33,live.shownUs,live.valid ? int64_t(live.v8ShownSeq) : 0,v8TargetUs.load(),0);
}

bool holePunchReflip(uint8_t* frame, int pitch, int width, int height)
{
    v143PreparedSeq = v143PreparedEpoch = 0;
    diagnosticTrace(125, 1, width, height, 0);
    if (!v7On() || !frame) return false;
    v7SamplePublish();   // OMNI_HOLEPUNCH_V7_REV2: a stack sample the main thread wrote: to the log
    const double started = nowMs();
    const int64_t poll = v7PollUs.load(std::memory_order_relaxed);
    const bool stalled = poll && int64_t(started * 1000) - poll >= int64_t(v7StallMs * 1000);
    if (!stalled && !v8On()) return false;   // the main thread ticks: it draws itself (V8: the coming vblank needs its picture anyway)
    if (stalled) v7SampleStalledMain(int64_t(started * 1000), int64_t(started * 1000) - poll);   // what is it doing? (at most 6 samples)
    std::unique_lock<std::mutex> composing(v7ComposeLock, std::try_to_lock);
    if (v8On() && !composing.owns_lock()) {   // V8: a hand-off (or V8 off's compose) is short: wait for it while the flip can still make the vblank
        const double deadline = vblankAfter(started) - double(v8LeadUs.load(std::memory_order_relaxed) + v8ReflipCostUs.load(std::memory_order_relaxed)) / 1000 - 0.2;
        while (!composing.owns_lock() && nowMs() < deadline) { usleep(100); (void)composing.try_lock(); }
    }
    if (!composing.owns_lock()) { diagnosticTrace(87,4,1,0,0); v7ReflipBusy.fetch_add(1, std::memory_order_relaxed); return false; }   // it is composing now
    const int64_t waitedUs = int64_t((nowMs() - started) * 1000);
    if (v8On() && waitedUs > 200) v8ReflipWaits.fetch_add(1, std::memory_order_relaxed);
    V7Live& live = v7Live;
    if (!live.valid || live.width != width || live.height != height) return false;
    const HoleLayer* now = nullptr;
    {
        std::lock_guard<std::mutex> l(plane.lock);
        if (!plane.attached || plane.owner < 0 || !plane.pacing || !plane.clock.valid || !plane.clock.playing || plane.ready) return false;
        if (live.epoch != plane.epoch) { live.valid = false; pbOwnsVideo.store(false, std::memory_order_relaxed); return false; }   // another owner since the hand-off (OMNI_PERF_B_V2)
        v7SelectByPresenter = stalled;   // V8: a drop here is "stalled" only when the main thread is
        if (v8On()) holePaceSelect(vblankAfter(nowMs()), 4);   // OMNI_HOLEPUNCH_V8_CADENCE: the coming vblank's picture
        else holePaceSelect();   // the newest picture due at the next vblank (counted shown / dropped as by a compose)
        v7SelectByPresenter = false;
        now = plane.current.get();
        // OMNI_HOLEPUNCH_V8_CADENCE: newer by v8Seq: after a seek back the due picture's time is below the frame's
        if (!now || now->epoch != plane.epoch || (v8On() ? now->v8Seq <= live.v8ShownSeq : now->mediaUs <= live.shownUs)) return false;   // nothing newer than the frame's
        if (now->w != live.w || now->h != live.h) { v7ReflipStale.fetch_add(1, std::memory_order_relaxed); live.valid = false; pbOwnsVideo.store(false, std::memory_order_relaxed); return false; }   // resized: the next compose (OMNI_PERF_B_V2)
    }
    // plane.current changes only under v7ComposeLock (compose, re-flip): `now` stays while it is held.
    unsigned written = unsigned(size_t(width)*height);
    if (!v139Direct(frame,pitch,width,height,live,now)) {
    const size_t stride = size_t(now->stride);
    written = 0;
    diagnosticTrace(122, now->mediaUs, live.runs.size()/3, live.mixPos.size(), 1);
    const uint8_t* px = holeLayerPx(now);   // OMNI_PERF_B_V3
    for (size_t k = 0; k + 2 < live.runs.size(); k += 3) {
        const uint32_t y = live.runs[k], x = live.runs[k + 1], n = live.runs[k + 2];
        omniReadLayer(frame + size_t(y) * size_t(pitch) + size_t(x) * 4, px + size_t(int(y) - live.ly) * stride + size_t(int(x) - live.lx) * 4, size_t(n) * 4);
        written += n;
    }
    diagnosticTrace(123, now->mediaUs, written, live.mixPos.size(), 1);
    omniWriteMixSpans(frame, pitch, width, live, now); // OMNI_HOLEPUNCH_MIX_SPANS_V1
    diagnosticTrace(124, now->mediaUs, written, live.mixPos.size(), 1);
    written += unsigned(live.mixPos.size());
    }
    live.shownUs = now->mediaUs;
    if (v8On()) {   // OMNI_HOLEPUNCH_V8_CADENCE
        live.v8ShownSeq = now->v8Seq; live.v8First = now->v8First;
        (stalled ? v8StallReflips : v8CadenceReflips).fetch_add(1, std::memory_order_relaxed);
        const double callAt = nowMs();   // the flip call follows: the set-up time is learned from it too
        v8TargetUs.store(int64_t(vblankAfter(callAt) * 1000), std::memory_order_relaxed);
        v8HandOffAtUs.store(int64_t(callAt * 1000), std::memory_order_relaxed); v8FirstUs.store(int64_t(vblankAfter(callAt) * 1000), std::memory_order_relaxed);
        v8TargetHandOff.store(true, std::memory_order_relaxed);
    }
    const int64_t us = int64_t((nowMs() - started) * 1000);
    if (v8On()) v8Recent(v8ReflipCostUs, us - (waitedUs > 0 ? waitedUs : 0));   // OMNI_HOLEPUNCH_V8_CADENCE: the re-flip itself
    v7Reflips.fetch_add(1, std::memory_order_relaxed); v7ReflipUs.fetch_add(us, std::memory_order_relaxed); v7Max(v7ReflipMaxUs, us);
    v143PreparedSeq = live.v8ShownSeq; v143PreparedEpoch = live.epoch;
    diagnosticTrace(33,live.shownUs,live.v8ShownSeq,v8TargetUs.load(),1);
    v7ReflipPixelsK.fetch_add(written / 1000, std::memory_order_relaxed);
    return true;
}

}

