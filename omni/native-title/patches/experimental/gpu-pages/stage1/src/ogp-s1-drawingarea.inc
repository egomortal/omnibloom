extern "C" void omni_tc_snapshot(char*, unsigned long) __attribute__((weak));   // ThreadedCompositor.cpp (OMNI_GPUPAGES_TCPROBE_V1)
// OMNI_GPUPAGES_DLADDR_V3: global scope (a weak declaration inside a namespace resolved to null before)
extern "C" void omni_gpu_pages_s1_dladdr_window(int) __attribute__((weak));
#include <errno.h>
// omni-gpu-pages stage 1 (OMNI_GPU_PAGES_STAGE1_V1): the WebProcess side of GPU compositing, part 1 of 2.
// SPDX-License-Identifier: GPL-3.0-or-later (this file); WebKit's own files keep their licences.
// Included once, into DrawingAreaCoordinatedGraphics.cpp, after its own includes. No WebKit header changes.
//
// What stage 1 is: the page is composited on the GPU in this process (WebKit's own threaded compositor and
// TextureMapper, with CPU-rastered tiles), and every finished frame reaches the UI process as an ordinary
// DrawingAreaProxy::Update bitmap. The UI process never leaves backing-store mode: Omni's shell, WKPagePaint,
// the 4K compose and the hole-punch path do not change at all. What goes away is the reason the omni-jank pass
// found for long page frames: the page's own rendering loop no longer waits for the shell's DisplayDidRefresh.
//
// This part: (1) the process-wide GL display, created lazily the first time a page needs it, from our own
// statically linked Mesa (EGL surfaceless + Zink) on RADV as a gpu-broker client of the title; (2) the
// per-page delivery state; (3) the stats line the A/B reads. Part 2 (ogp-s1-surface.inc) renders into an
// offscreen framebuffer and reads it back. Default OFF: /data/omni/gpu-pages-stage1.flag turns it on and
// /data/omni/gpu-pages-stage1-off.flag is the kill switch. Any failure leaves accelerated compositing off for
// the whole process, which is today's behaviour; nothing here can reach the sharedDisplay() RELEASE_ASSERT.

#include OGP_S1_POLICY_H
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <WebCore/GLContext.h>
#include <WebCore/GLDisplay.h>
#include <WebCore/PlatformDisplay.h>
#include <GLES2/gl2.h>
#include <atomic>
#include <cstring>
#include <pthread.h>
#include <time.h>
#include <unistd.h>
#include <unordered_map>
#include <wtf/NeverDestroyed.h>

// ogp-s1-child.c. WEAK: WebKit's own in-tree OmniEngine link (ninja) does not contain that object, only the stage-1
// child link does; there they are null and stage 1 simply reports off.
extern "C" int omni_gpu_pages_s1_enabled(void) __attribute__((weak));
extern "C" int omni_gpu_pages_s1_bind(char* why, unsigned long size) __attribute__((weak));

namespace WebKit {
namespace OmniGpuPagesS1 {

static double nowMs()
{
    struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1e3 + t.tv_nsec / 1e6;
}

// A surfaceless display on our Mesa. WebKit's own PlatformDisplaySurfaceless is not compiled into this port
// (and would CRASH() on failure); this one only reports.
class Display final : public WebCore::PlatformDisplay {
public:
    explicit Display(Ref<WebCore::GLDisplay>&& display) : WebCore::PlatformDisplay(WTF::move(display)) { }
    Type type() const final { return Type::Surfaceless; }
};

static std::atomic<int> s_state { 0 };   // 0 not tried, 1 ready, -1 off or failed (read by the surface on its thread)

// EGL init + the probe context run on a 16 MiB helper thread, joined: CP-2 try 6 measured a loader child's main thread
// at 2048 KiB, and try 5 showed Mesa's shader compile overrunning a stack that size (radv_shader_object_create, ~99 KB
// frame, no stack probes). The shared display is installed back on the calling (main) thread.
struct InitResult { std::unique_ptr<Display> display; double tBind { 0 }, t0 { 0 }; bool ok { false }; };
static void* initOnBigStack(void* p)
{
    auto& r = *static_cast<InitResult*>(p);
    setenv("MESA_LOADER_DRIVER_OVERRIDE", "zink", 1);   // EGL: Zink on the no-DRM surfaceless path (OGP_SURFACELESS_ZINK_NO_DRM)
    setenv("MESA_SHADER_CACHE_DISABLE", "1", 0);
    const char* client = eglQueryString(EGL_NO_DISPLAY, EGL_EXTENSIONS);
    auto getPlatformDisplay = reinterpret_cast<PFNEGLGETPLATFORMDISPLAYEXTPROC>(eglGetProcAddress("eglGetPlatformDisplayEXT"));
    if (!client || !WebCore::GLContext::isExtensionSupported(client, "EGL_MESA_platform_surfaceless") || !getPlatformDisplay) {
        fprintf(stderr, "OMNI GPUPAGES child pid=%d: off: EGL offers no surfaceless platform (%s)\n", getpid(), client ? client : "no client extensions");
        return nullptr;
    }
    RefPtr glDisplay = WebCore::GLDisplay::create(getPlatformDisplay(EGL_PLATFORM_SURFACELESS_MESA, nullptr, nullptr));
    if (!glDisplay) {
        fprintf(stderr, "OMNI GPUPAGES child pid=%d: off: eglInitialize failed (%s)\n", getpid(), WebCore::GLContext::lastErrorString());
        return nullptr;
    }
    const char* displayExtensions = eglQueryString(glDisplay->eglDisplay(), EGL_EXTENSIONS);
    if (!displayExtensions || !WebCore::GLContext::isExtensionSupported(displayExtensions, "EGL_KHR_surfaceless_context")) {
        fprintf(stderr, "OMNI GPUPAGES child pid=%d: off: no EGL_KHR_surfaceless_context\n", getpid());
        return nullptr;
    }
    auto display = makeUnique<Display>(glDisplay.releaseNonNull());
    {   // prove a context works now, where a failure is a log line rather than a compositor-thread surprise later
        auto context = WebCore::GLContext::createOffscreen(*display);
        if (!context || !context->makeContextCurrent()) {
            fprintf(stderr, "OMNI GPUPAGES child pid=%d: off: no offscreen GL context (%s)\n", getpid(), WebCore::GLContext::lastErrorString());
            return nullptr;
        }
        fprintf(stderr, "OMNI GPUPAGES child pid=%d: ready: GL_RENDERER=%s GL_VERSION=%s bind=%.1fms display=%.1fms "
            "(compositing on, raster on the CPU: accelerated buffers stay off; EGL init on a 16 MiB thread)\n", getpid(),
            reinterpret_cast<const char*>(glGetString(GL_RENDERER)), reinterpret_cast<const char*>(glGetString(GL_VERSION)),
            r.tBind - r.t0, nowMs() - r.tBind);
    }
    r.display = std::move(display); r.ok = true;
    return nullptr;
}


// OMNI_GPUPAGES_HANGDOG_V1 (diagnostic): with stage 1 on, the WebProcess main thread was seen going silent (media and
// page frames stop while the compositor and the memory sampler still run). A helper thread pings the main RunLoop every
// 500 ms; when the main thread has not answered for 3 s it is sent SIGXCPU, whose handler (on the main thread) writes
// rip/rsp, the frame-pointer chain and code addresses found on the stack, as image offsets, to stderr. At most 4 dumps,
// 8 s apart. /data/omni/gpu-pages-hangdog-off.flag turns it off.
#include <signal.h>
#include <dlfcn.h>
#include <atomic>
extern "C" void omniGpuPagesSurfaceCounts(uint64_t* will, uint64_t* did);   // ogp-s1-surface.inc (OMNI_GPUPAGES_BEAT_V1)
namespace OmniGpuPagesHangdog {
static pthread_t s_main;
static uintptr_t s_base = 0, s_codeEnd = 0, s_stackLo = 0, s_stackHi = 0;
static std::atomic<double> s_answered { 0 };
static std::atomic<bool> s_pending { false };
static std::atomic<int> s_dumps { 0 };
extern "C" int pthread_attr_get_np(pthread_t, pthread_attr_t*) __attribute__((weak));

struct Out {
    char buf[600]; size_t n = 0;
    void c(char ch) { if (n < sizeof buf - 2) buf[n++] = ch; }
    void str(const char* t) { while (*t) c(*t++); }
    void hex(uintptr_t v) { c('0'); c('x'); bool on = false; for (int sh = 60; sh >= 0; sh -= 4) { int d = (v >> sh) & 15; if (d || on || !sh) { on = true; c("0123456789abcdef"[d]); } } c(' '); }
    void flush() { c('\n'); ssize_t r = write(2, buf, n); (void)r; n = 0; }
};
static bool inStack(uintptr_t a, size_t len) { return a >= s_stackLo && a + len <= s_stackHi; }
static void onSignal(int, siginfo_t*, void* context)
{
    const uintptr_t* w = static_cast<const uintptr_t*>(context) + 8;   // uc_mcontext at byte 64 (OmniCrash.h)
    const uintptr_t rip = w[20], rsp = w[23], rbp = w[9];
    Out o;
    o.str("OMNI GPUPAGES HANG main thread: rip-off="); o.hex(rip >= s_base ? rip - s_base : rip); o.str("rsp="); o.hex(rsp); o.str("base="); o.hex(s_base); o.flush();
    o.str("OMNI GPUPAGES HANG fp-chain:");
    uintptr_t fp = rbp; int k = 0;
    while (k < 40 && fp && !(fp & 7) && fp >= rsp && inStack(fp, 16)) {
        uintptr_t ret = reinterpret_cast<const uintptr_t*>(fp)[1], next = reinterpret_cast<const uintptr_t*>(fp)[0];
        if (ret > s_base && ret < s_codeEnd) { o.hex(ret - s_base); ++k; }
        if (k && !(k % 10)) { o.flush(); o.str("OMNI GPUPAGES HANG fp-chain:"); }
        if (next <= fp) break;
        fp = next;
    }
    o.flush();
    o.str("OMNI GPUPAGES HANG stack-scan:");
    int found = 0;
    uintptr_t end = rsp + 24 * 1024; if (end > s_stackHi) end = s_stackHi;
    for (uintptr_t a = rsp & ~uintptr_t(7); inStack(a, 8) && a + 8 <= end && found < 64; a += 8) {
        uintptr_t v = *reinterpret_cast<const uintptr_t*>(a);
        if (v <= s_base || v >= s_codeEnd) continue;
        o.hex(v - s_base);
        if (!(++found % 10)) { o.flush(); o.str("OMNI GPUPAGES HANG stack-scan:"); }
    }
    o.flush();
}
static void* watch(void*)
{
    double sentAt = 0, lastDump = 0, lastBeat = 0, pingMax = 0;
    uint64_t lastWill = 0, lastDid = 0;
    for (;;) {
        usleep(500 * 1000);
        double now = nowMs();
        if (now - lastBeat >= 5000) {   // OMNI_GPUPAGES_BEAT_V1
            uint64_t will = 0, did = 0;
            omniGpuPagesSurfaceCounts(&will, &did);
            fprintf(stderr, "OMNI GPUPAGES beat t=%.3f compositor will=%llu (+%llu) did=%llu (+%llu) mainPingMaxMs=%.0f pending=%d\n",
                now / 1000.0, (unsigned long long)will, (unsigned long long)(will - lastWill), (unsigned long long)did, (unsigned long long)(did - lastDid),
                pingMax, s_pending.load() ? 1 : 0);
            if (omni_tc_snapshot) { char tc[400]; omni_tc_snapshot(tc, sizeof tc); fprintf(stderr, "OMNI GPUPAGES beat %s\n", tc); }
            fflush(stderr);
            lastWill = will; lastDid = did; lastBeat = now; pingMax = 0;
        }
        if (s_pending.load() && now - sentAt > pingMax) pingMax = now - sentAt;
        if (!s_pending.load()) {
            s_pending = true; sentAt = now;
            RunLoop::mainSingleton().dispatch([] { s_answered = nowMs(); s_pending = false; });
            continue;
        }
        if (now - sentAt > 3000 && now - lastDump > 8000 && s_dumps.load() < 4) {
            ++s_dumps; lastDump = now;
            fprintf(stderr, "OMNI GPUPAGES HANG main thread silent %.0f ms (t=%.3f), dump %d\n", now - sentAt, now / 1000.0, s_dumps.load());
            fflush(stderr);
            pthread_kill(s_main, SIGXFSZ);
        }
    }
    return nullptr;
}
static void start()
{
    static bool started = false;
    if (started) return;
    if (!access("/data/omni/gpu-pages-hangdog-off.flag", F_OK)) { fprintf(stderr, "OMNI GPUPAGES hangdog off (flag)\n"); return; }
    started = true;
    s_main = pthread_self();
    Dl_info info { };
    uintptr_t self = reinterpret_cast<uintptr_t>(&onSignal);
    if (dladdr(reinterpret_cast<const void*>(&onSignal), &info) && info.dli_fbase) s_base = reinterpret_cast<uintptr_t>(info.dli_fbase);
    else if (self >= 0x200000000ull && self < 0x210000000ull) s_base = 0x200000000ull;   // the child's load base (crash log)
    else { fprintf(stderr, "OMNI GPUPAGES hangdog off: no image base (fn %#lx)\n", (unsigned long)self); return; }
    s_codeEnd = s_base + 0x7000000;
    void* addr = nullptr; size_t size = 0;
    if (pthread_attr_get_np) {
        pthread_attr_t a;
        if (!pthread_attr_init(&a)) {
            if (!pthread_attr_get_np(s_main, &a)) pthread_attr_getstack(&a, &addr, &size);
            pthread_attr_destroy(&a);
        }
    }
    if (addr && size) { s_stackLo = reinterpret_cast<uintptr_t>(addr); s_stackHi = s_stackLo + size; }
    else {   // fallback: 2 MiB below this frame, 32 KiB above it (the RunLoop frames above us)
        uintptr_t fp = reinterpret_cast<uintptr_t>(__builtin_frame_address(0));
        s_stackLo = fp - (2u << 20); s_stackHi = fp + (32u << 10);
        fprintf(stderr, "OMNI GPUPAGES hangdog: no stack bounds from pthread (get_np %s); using the frame address\n", pthread_attr_get_np ? "failed" : "missing");
    }
    struct sigaction sa { }; sa.sa_sigaction = onSignal; sa.sa_flags = SA_SIGINFO | SA_RESTART; sigemptyset(&sa.sa_mask);
    if (sigaction(SIGXFSZ, &sa, nullptr)) { fprintf(stderr, "OMNI GPUPAGES hangdog off: sigaction failed (%d)\n", errno); return; }
    pthread_t th; pthread_attr_t ta; pthread_attr_init(&ta); pthread_attr_setstacksize(&ta, 1u << 20);
    int rc = pthread_create(&th, &ta, watch, nullptr);
    if (!rc) pthread_detach(th); else fprintf(stderr, "OMNI GPUPAGES hangdog: thread failed (%d)\n", rc);
    pthread_attr_destroy(&ta);
    fprintf(stderr, "OMNI GPUPAGES hangdog on: base=%#lx stack %#lx..%#lx pid=%d\n", (unsigned long)s_base, (unsigned long)s_stackLo, (unsigned long)s_stackHi, getpid());
}
}

static bool ensureDisplay()
{
    int state = s_state.load();
    if (state) return state > 0;
    s_state = -1;
    if (!omni_gpu_pages_s1_enabled || !omni_gpu_pages_s1_bind || !omni_gpu_pages_s1_enabled())
        return false;   // the quiet, default path: no flag (or no stage-1 object in this link), nothing logged
    if (WebCore::PlatformDisplay::sharedDisplayIfExists()) {
        fprintf(stderr, "OMNI GPUPAGES child pid=%d: a shared display already exists; stage 1 stays off\n", getpid());
        return false;
    }
    InitResult r; r.t0 = nowMs();
    char why[200] = "";
    if (omni_gpu_pages_s1_bind(why, sizeof why)) {
        fprintf(stderr, "OMNI GPUPAGES child pid=%d: off for this process: %s\n", getpid(), why);
        return false;
    }
    r.tBind = nowMs();
    pthread_attr_t attr; pthread_attr_init(&attr); pthread_attr_setstacksize(&attr, 16u << 20);
    if (omni_gpu_pages_s1_dladdr_window) omni_gpu_pages_s1_dladdr_window(1);   // OMNI_GPUPAGES_DLADDR_V3: Mesa UUID only
    pthread_t th; int rc = pthread_create(&th, &attr, initOnBigStack, &r);
    pthread_attr_destroy(&attr);
    if (rc) { fprintf(stderr, "OMNI GPUPAGES child pid=%d: off: could not start the 16 MiB init thread (%d)\n", getpid(), rc); return false; }
    pthread_join(th, nullptr);
    if (omni_gpu_pages_s1_dladdr_window) omni_gpu_pages_s1_dladdr_window(0);
    fprintf(stderr, "OMNI GPUPAGES init t0=%.3f bind=%.1fms egl=%.1fms ok=%d pid=%d\n", r.t0 / 1000.0, r.tBind - r.t0, nowMs() - r.tBind, r.ok ? 1 : 0, getpid());
    fflush(stderr);
    if (!r.ok) return false;
    WebCore::PlatformDisplay::setSharedDisplay(std::move(r.display));
    s_state = 1;
    OmniGpuPagesHangdog::start();
    return true;
}

// OMNI_GPUPAGES_TILES_V1: frames are full or partial (changed 64x64 tiles only). Partial frames build on each other, so
// while one update is in flight they QUEUE (never replace one another) and go out merged into one Update on the ack.
// Anything dropped (resize, leaving compositing, an over-long queue) asks the compositor for a full frame, and partial
// frames are ignored until that full frame arrives.
struct QueuedFrame {
    Ref<WebCore::ShareableBitmap> bitmap;
    WebCore::IntSize deviceSize;
    WebCore::IntRect bounds;            // device pixels; the bitmap covers exactly this
    Vector<WebCore::IntRect> rects;     // device pixels, inside bounds
    bool full;
};
struct PageState {
    bool composited { false };
    bool waitingForFull { false };
    Vector<QueuedFrame> queue;
    OmniGpuPages::Delivery delivery;
    double lastLogMs { 0 };
    uint64_t sizeMismatch { 0 }, fullFrames { 0 }, partialFrames { 0 }, droppedPartial { 0 }, queueResets { 0 }, merged { 0 };
    double readBytes { 0 }, sentBytes { 0 };
    double mainMs { 0 }, mainMaxMs { 0 };   // main-thread time in deliver + ack (OMNI_GPUPAGES_TIMING_V1)
};
static std::atomic<bool> s_needFull { true };
static std::atomic<bool> s_partialOk { true };
static std::atomic<uint64_t> s_unchanged { 0 };
static constexpr size_t kQueueFrames = 8;
static constexpr double kQueueBytes = 96.0 * 1048576;

static std::unordered_map<uint64_t, PageState>& pages()
{
    static NeverDestroyed<std::unordered_map<uint64_t, PageState>> table;   // main thread only
    return table.get();
}

static void requestFull(PageState& state)
{
    state.queue.clear();
    state.waitingForFull = true;
    s_needFull = true;
}

static void maybeLog(PageState& state, double now)
{
    if (now - state.lastLogMs < 2000) return;
    state.lastLogMs = now;
    char line[700];
    state.delivery.format(line, sizeof line);
    fprintf(stderr, "%s sizeMismatch=%llu pid=%d\n", line, static_cast<unsigned long long>(state.sizeMismatch), getpid());
    fprintf(stderr, "OMNI GPUPAGES tiles full=%llu partial=%llu unchanged=%llu merged=%llu droppedPartial=%llu queueResets=%llu "
        "readMiB=%.1f sentMiB=%.1f partialOk=%d mainMs=%.1f mainMaxMs=%.1f t=%.3f pid=%d\n",
        static_cast<unsigned long long>(state.fullFrames), static_cast<unsigned long long>(state.partialFrames),
        static_cast<unsigned long long>(s_unchanged.load()), static_cast<unsigned long long>(state.merged),
        static_cast<unsigned long long>(state.droppedPartial), static_cast<unsigned long long>(state.queueResets),
        state.readBytes / 1048576.0, state.sentBytes / 1048576.0, s_partialOk.load() ? 1 : 0, state.mainMs, state.mainMaxMs, now / 1000.0, getpid());
    state.mainMaxMs = 0;
    fflush(stderr);
    state.delivery.resetWindow();
}

// OMNI_GPUPAGES_TILES_V3: the queue collapses into one frame instead of being thrown away when the UI is slow, so
// partial frames are never dropped for queue length. false: it could not (no memory); the caller asks for a full frame.
static bool collapseQueue(PageState& state)
{
    if (state.queue.size() < 2) return true;
    for (auto& f : state.queue)
        if (f.deviceSize != state.queue[0].deviceSize) return false;
    WebCore::IntRect bounds = state.queue[0].bounds;
    for (auto& f : state.queue) bounds.unite(f.bounds);
    RefPtr merged = WebCore::ShareableBitmap::create(WebCore::ShareableBitmapConfiguration { bounds.size() });
    if (!merged) return false;
    const size_t dstStride = merged->bytesPerRow();
    uint8_t* dst = merged->mutableSpan().data();
    WebCore::Region region;
    bool full = false;
    for (auto& f : state.queue) {
        full = full || f.full;
        const size_t srcStride = f.bitmap->bytesPerRow();
        const uint8_t* src = f.bitmap->span().data();
        for (auto& r : f.rects) {
            for (int y = 0; y < r.height(); ++y)
                memcpy(dst + static_cast<size_t>(r.y() - bounds.y() + y) * dstStride + static_cast<size_t>(r.x() - bounds.x()) * 4,
                    src + static_cast<size_t>(r.y() - f.bounds.y() + y) * srcStride + static_cast<size_t>(r.x() - f.bounds.x()) * 4,
                    static_cast<size_t>(r.width()) * 4);
            region.unite(r);
        }
    }
    Vector<WebCore::IntRect> rects;
    for (auto& r : region.rects()) rects.append(r);
    WebCore::IntSize deviceSize = state.queue[0].deviceSize;
    state.merged += state.queue.size() - 1;
    state.queue.clear();
    state.queue.append(QueuedFrame { merged.releaseNonNull(), deviceSize, bounds, WTF::move(rects), full });
    return true;
}

// Sends everything queued as ONE Update (one ack). false: nothing went out (no ack will come).
static bool sendQueued(WebPage& page, DrawingArea& drawingArea, PageState& state)
{
    if (state.queue.isEmpty()) return false;
    float scale = page.corePage()->deviceScaleFactor();
    WebCore::IntSize viewSize = page.size();
    WebCore::IntSize expected = viewSize;
    expected.scale(scale);
    const int s = static_cast<int>(scale);
    const bool integral = s >= 1 && static_cast<float>(s) == scale;
    s_partialOk = integral;
    for (auto& f : state.queue) {
        // a frame from before a resize: the UI would place it wrong. Partial rects must map exactly to view pixels.
        bool exact = f.full || (integral && !(f.bounds.x() % s) && !(f.bounds.y() % s) && !(f.bounds.width() % s) && !(f.bounds.height() % s));
        for (auto& r : f.rects) exact = exact && (f.full || (!(r.x() % s) && !(r.y() % s) && !(r.width() % s) && !(r.height() % s)));
        if (f.deviceSize != expected || !exact) {
            ++state.sizeMismatch;
            requestFull(state);
            return false;
        }
    }
    auto toView = [&](const WebCore::IntRect& r) {
        if (r.size() == expected && r.location() == WebCore::IntPoint()) return WebCore::IntRect(WebCore::IntPoint(), viewSize);
        return WebCore::IntRect(r.x() / s, r.y() / s, r.width() / s, r.height() / s);
    };
    if (!collapseQueue(state)) { requestFull(state); return false; }
    RefPtr<WebCore::ShareableBitmap> bitmap = state.queue[0].bitmap.ptr();
    WebCore::IntRect bounds = state.queue[0].bounds;
    Vector<WebCore::IntRect> rects = state.queue[0].rects;
    state.queue.clear();
    auto handle = bitmap->createHandle();
    if (!handle) { requestFull(state); return false; }
    UpdateInfo updateInfo;
    updateInfo.viewSize = viewSize;
    updateInfo.deviceScaleFactor = scale;
    updateInfo.updateRectBounds = toView(bounds);
    for (auto& r : rects) updateInfo.updateRects.append(toView(r));
    updateInfo.bitmapHandle = WTF::move(*handle);
    state.sentBytes += static_cast<double>(bitmap->sizeInBytes());
    page.send(Messages::DrawingAreaProxy::Update(0, WTF::move(updateInfo)), drawingArea.identifier().toUInt64(), { });
    return true;
}

// The UI process acked the update in flight (DisplayDidRefresh). Whatever queued meanwhile goes now, merged.
static void didRefresh(DrawingArea& drawingArea, WebPage& page)
{
    auto it = pages().find(drawingArea.identifier().toUInt64());
    if (it == pages().end() || !it->second.composited) return;
    auto& state = it->second;
    double now = nowMs();
    if (!state.delivery.acked(now)) return;
    if (!sendQueued(page, drawingArea, state))
        state.delivery.inFlight = false;
    double spent = nowMs() - now; state.mainMs += spent; if (spent > state.mainMaxMs) state.mainMaxMs = spent;
    maybeLog(state, now);
}

static void setComposited(DrawingArea& drawingArea, bool composited)
{
    auto& state = pages()[drawingArea.identifier().toUInt64()];
    state.composited = composited;
    if (!composited) { requestFull(state); state.delivery.inFlight = false; state.delivery.havePending = false; }
}

} // namespace OmniGpuPagesS1

// Read by ogp-s1-surface.inc on the compositing thread.
bool omniGpuPagesProcessReady() { return OmniGpuPagesS1::s_state.load() > 0; }
bool omniGpuPagesTakeFullRequest() { return OmniGpuPagesS1::s_needFull.exchange(false); }
bool omniGpuPagesPartialAllowed() { return OmniGpuPagesS1::s_partialOk.load(); }
void omniGpuPagesCountUnchanged() { ++OmniGpuPagesS1::s_unchanged; }

// From ogp-s1-surface.inc, dispatched to the main thread: one finished, read-back frame (full or partial) of one page.
void omniGpuPagesDeliverFrame(WebCore::PageIdentifier pageID, Ref<WebCore::ShareableBitmap>&& bitmap, WebCore::IntSize deviceSize,
    WebCore::IntRect deviceBounds, Vector<WebCore::IntRect>&& deviceRects, bool full, double readbackMs)
{
    using namespace OmniGpuPagesS1;
    RefPtr page = WebProcess::singleton().webPage(pageID);
    if (!page) { s_needFull = true; return; }
    auto* drawingArea = page->drawingArea();
    if (!drawingArea) { s_needFull = true; return; }
    auto& state = pages()[drawingArea->identifier().toUInt64()];
    if (!state.composited) { requestFull(state); return; }   // left compositing while this frame was in flight
    double now = nowMs();
    state.delivery.readback.add(readbackMs);
    state.readBytes += static_cast<double>(bitmap->sizeInBytes());
    if (full) { ++state.fullFrames; state.queue.clear(); state.waitingForFull = false; }
    else {
        ++state.partialFrames;
        if (state.waitingForFull) { ++state.droppedPartial; maybeLog(state, now); return; }
    }
    state.queue.append(QueuedFrame { WTF::move(bitmap), deviceSize, deviceBounds, WTF::move(deviceRects), full });
    double queued = 0;
    for (auto& f : state.queue) queued += static_cast<double>(f.bitmap->sizeInBytes());
    if ((state.queue.size() > kQueueFrames || queued > kQueueBytes) && collapseQueue(state)) {
        // the UI is behind: the queue is now one merged frame, nothing dropped
    } else if (state.queue.size() > kQueueFrames || queued > kQueueBytes) {   // could not merge: start again from a full frame
        ++state.queueResets;
        requestFull(state);
        maybeLog(state, now);
        return;
    }
    if (state.delivery.offer(now)) {
        if (!sendQueued(*page, *drawingArea, state))
            state.delivery.inFlight = false;   // nothing went out: no ack will come
    }
    double spent = nowMs() - now; state.mainMs += spent; if (spent > state.mainMaxMs) state.mainMaxMs = spent;
    maybeLog(state, now);
}

} // namespace WebKit
