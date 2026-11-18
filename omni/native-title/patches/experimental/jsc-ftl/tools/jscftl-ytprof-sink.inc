// ---- OMNI_YTPROF_V1 sink: exclusive (self) main-thread time per category, per main-frame page ----------------------
// jscftl port (2026-11-17) adds OMNI_YTPROF_WIN_V1: per-window deltas every 5 s and long main-thread tasks.
// Main thread only (others: OMNI_YP_* totals as "off:"). Lines go to fd 2 (the process log):
//   OMNI YTPROF nav  seq=N navAgo=<ms from navigation start to commit> url=...
//   OMNI YTPROF t    seq=N ms=<ms from navigation start> busy=<ms> task=<self ms>/<count> js=... (cumulative, every >=250 ms,
//                    first 30 s after a commit only)
//   OMNI YTPROF page seq=N dur=<ms> busy=<ms> <categories> off:<cat>=<ms>/<n> gc=<eden>/<full> url=... (at the next commit)
//   OMNI YTPROF w    seq=N ms=<ms from navigation start> win=<window ms> busy=<ms> tasks=<top-level n> long50=<n> long100=<n>
//                    max=<longest top-level ms> gcn=<eden>/<full> <categories: self ms/count in this window> (every >=5 s)
//   OMNI YTPROF long seq=N ms=<ms from navigation start at task end> dur=<ms> top=<cat> <non-zero categories: self ms/count>
//                    (each top-level main-thread scope >= 100 ms; at most 30 per window, the rest counted in w's long100)
// task = run-loop task self time not inside any other category ("other"); rupd count per window / win = rendering updates/s.
#include <atomic>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
static_assert(OMNI_YP_COUNT == 13, "OMNI_YTPROF categories");
namespace {
const char* const omniYpNames[OMNI_YP_COUNT] = { "task", "js", "compile", "gc", "sweep", "style", "layout", "paint", "raster", "decode", "parse", "cssparse", "rupd" };
std::atomic<int> omniYpOn { -1 };
struct OmniYpState {
    int depth; int stack[64]; int overflow; uint64_t last; uint64_t self[OMNI_YP_COUNT]; uint32_t n[OMNI_YP_COUNT];
    uint64_t markAt; uint64_t navStart; uint64_t lastSeries; unsigned seq; char url[160];
    // OMNI_YTPROF_WIN_V1
    uint64_t winStart; uint64_t wself[OMNI_YP_COUNT]; uint32_t wn[OMNI_YP_COUNT]; uint32_t wTasks, wLong50, wLong100, wLongLogged; uint64_t wMax;
    uint64_t topStart; int topCat; uint64_t tself[OMNI_YP_COUNT]; uint32_t tn[OMNI_YP_COUNT];
};
OmniYpState omniYp;
std::atomic<uint64_t> omniYpOffNs[OMNI_YP_COUNT];
std::atomic<uint32_t> omniYpOffN[OMNI_YP_COUNT];
std::atomic<uint32_t> omniYpGcCount[2];
std::atomic<uint32_t> omniYpGcWin[2];
inline uint64_t omniYpNow()
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return uint64_t(ts.tv_sec) * 1000000000ull + uint64_t(ts.tv_nsec);
}
void omniYpWrite(const char* b, int len)
{
    if (len <= 0)
        return;
    ssize_t r = ::write(2, b, size_t(len));
    (void)r;
}
int omniYpCatsOf(char* p, size_t cap, const uint64_t* self, const uint32_t* n, bool nonZeroOnly)
{
    size_t len = 0;
    for (int i = 0; i < OMNI_YP_COUNT; ++i) {
        if (nonZeroOnly && !n[i] && !self[i])
            continue;
        int k = snprintf(p + len, cap - len, " %s=%.1f/%u", omniYpNames[i], self[i] / 1e6, n[i]);
        if (k < 0 || size_t(k) >= cap - len)
            break;
        len += size_t(k);
    }
    return int(len);
}
int omniYpCats(char* p, size_t cap) { return omniYpCatsOf(p, cap, omniYp.self, omniYp.n, false); }
uint64_t omniYpSum(const uint64_t* self)
{
    uint64_t s = 0;
    for (int i = 0; i < OMNI_YP_COUNT; ++i)
        s += self[i];
    return s;
}
uint64_t omniYpBusy() { return omniYpSum(omniYp.self); }
double omniYpSinceNav(uint64_t t) { return omniYp.navStart ? (t - omniYp.navStart) / 1e6 : 0.0; }
void omniYpCharge(uint64_t t)
{
    if (omniYp.depth > 0) {
        int c = omniYp.stack[omniYp.depth - 1];
        uint64_t d = t - omniYp.last;
        omniYp.self[c] += d;
        omniYp.wself[c] += d; // OMNI_YTPROF_WIN_V1
        omniYp.tself[c] += d;
    }
    omniYp.last = t;
}
void omniYpSeries(uint64_t t)
{
    if (!omniYp.navStart || t - omniYp.lastSeries < 250000000ull || t - omniYp.markAt > 30000000000ull)
        return;
    omniYp.lastSeries = t;
    char b[1400];
    int len = snprintf(b, sizeof b, "OMNI YTPROF t seq=%u ms=%.0f busy=%.1f", omniYp.seq, (t - omniYp.navStart) / 1e6, omniYpBusy() / 1e6);
    if (len < 0 || len >= int(sizeof b) - 2)
        return;
    len += omniYpCats(b + len, sizeof b - 2 - size_t(len));
    b[len++] = '\n';
    omniYpWrite(b, len);
}
// OMNI_YTPROF_WIN_V1: the 5 s window line (emitted from the next main-thread push/pop after the window ends)
void omniYpWindow(uint64_t t)
{
    if (!omniYp.winStart) {
        omniYp.winStart = t;
        return;
    }
    if (t - omniYp.winStart < 5000000000ull)
        return;
    char b[1400];
    int len = snprintf(b, sizeof b, "OMNI YTPROF w seq=%u ms=%.0f win=%.0f busy=%.1f tasks=%u long50=%u long100=%u max=%.1f gcn=%u/%u",
        omniYp.seq, omniYpSinceNav(t), (t - omniYp.winStart) / 1e6, omniYpSum(omniYp.wself) / 1e6, omniYp.wTasks, omniYp.wLong50, omniYp.wLong100,
        omniYp.wMax / 1e6, omniYpGcWin[0].exchange(0, std::memory_order_relaxed), omniYpGcWin[1].exchange(0, std::memory_order_relaxed));
    if (len > 0 && len < int(sizeof b) - 2) {
        len += omniYpCatsOf(b + len, sizeof b - 2 - size_t(len), omniYp.wself, omniYp.wn, false);
        b[len++] = '\n';
        omniYpWrite(b, len);
    }
    memset(omniYp.wself, 0, sizeof omniYp.wself);
    memset(omniYp.wn, 0, sizeof omniYp.wn);
    omniYp.wTasks = omniYp.wLong50 = omniYp.wLong100 = omniYp.wLongLogged = 0;
    omniYp.wMax = 0;
    omniYp.winStart = t;
}
void omniYpTopBegin(uint64_t t, int c)
{
    omniYp.topStart = t;
    omniYp.topCat = c;
    memset(omniYp.tself, 0, sizeof omniYp.tself);
    memset(omniYp.tn, 0, sizeof omniYp.tn);
}
void omniYpTopEnd(uint64_t t)
{
    uint64_t d = t - omniYp.topStart;
    ++omniYp.wTasks;
    if (d > omniYp.wMax)
        omniYp.wMax = d;
    if (d < 50000000ull)
        return;
    ++omniYp.wLong50;
    if (d < 100000000ull)
        return;
    ++omniYp.wLong100;
    if (omniYp.wLongLogged >= 30)
        return;
    ++omniYp.wLongLogged;
    char b[1000];
    int len = snprintf(b, sizeof b, "OMNI YTPROF long seq=%u ms=%.0f dur=%.1f top=%s", omniYp.seq, omniYpSinceNav(t), d / 1e6, omniYpNames[omniYp.topCat]);
    if (len > 0 && len < int(sizeof b) - 2) {
        len += omniYpCatsOf(b + len, sizeof b - 2 - size_t(len), omniYp.tself, omniYp.tn, true);
        b[len++] = '\n';
        omniYpWrite(b, len);
    }
}
} // namespace

extern "C" int omni_ytprof_on(void)
{
    int v = omniYpOn.load(std::memory_order_relaxed);
    if (v >= 0)
        return v;
    int fd = ::open("/data/omni/ytprof.flag", O_RDONLY);
    v = fd >= 0 ? 1 : 0;
    if (fd >= 0)
        ::close(fd);
    int expected = -1;
    if (omniYpOn.compare_exchange_strong(expected, v) && v) {
        char b[128];
        omniYpWrite(b, snprintf(b, sizeof b, "OMNI YTPROF on pid=%d (OMNI_YTPROF_V1 + OMNI_YTPROF_WIN_V1, w every 5 s, long >= 100 ms)\n", int(getpid())));
    }
    return omniYpOn.load(std::memory_order_relaxed);
}
extern "C" uint64_t omni_ytprof_now(void) { return omniYpNow(); }
extern "C" int omni_ytprof_push(int c)
{
    if (c < 0 || c >= OMNI_YP_COUNT || !WTF::isMainThread())
        return 0;
    uint64_t t = omniYpNow();
    omniYpCharge(t);
    if (omniYp.depth == 0 && !omniYp.overflow)
        omniYpTopBegin(t, c);
    if (omniYp.depth < 64)
        omniYp.stack[omniYp.depth++] = c;
    else
        ++omniYp.overflow;
    ++omniYp.n[c];
    ++omniYp.wn[c];
    ++omniYp.tn[c];
    omniYpSeries(t);
    omniYpWindow(t);
    return 1;
}
extern "C" void omni_ytprof_pop(int c)
{
    if (!WTF::isMainThread())
        return;
    uint64_t t = omniYpNow();
    omniYpCharge(t);
    if (omniYp.overflow > 0)
        --omniYp.overflow;
    else {
        for (int i = omniYp.depth - 1; i >= 0; --i) {
            if (omniYp.stack[i] == c) {
                memmove(&omniYp.stack[i], &omniYp.stack[i + 1], size_t(omniYp.depth - 1 - i) * sizeof(int));
                --omniYp.depth;
                if (omniYp.depth == 0)
                    omniYpTopEnd(t);
                break;
            }
        }
    }
    omniYpSeries(t);
    omniYpWindow(t);
}
extern "C" void omni_ytprof_offmain(int c, uint64_t ns)
{
    if (c < 0 || c >= OMNI_YP_COUNT)
        return;
    omniYpOffNs[c].fetch_add(ns, std::memory_order_relaxed);
    omniYpOffN[c].fetch_add(1, std::memory_order_relaxed);
}
extern "C" void omni_ytprof_gc(int full)
{
    if (omni_ytprof_on()) {
        omniYpGcCount[full ? 1 : 0].fetch_add(1, std::memory_order_relaxed);
        omniYpGcWin[full ? 1 : 0].fetch_add(1, std::memory_order_relaxed);
    }
}
extern "C" void omni_ytprof_mark(const char* url, double navAgoMs)
{
    if (omni_ytprof_on() != 1 || !WTF::isMainThread())
        return;
    uint64_t t = omniYpNow();
    omniYpCharge(t);
    char b[1800];
    int len = snprintf(b, sizeof b, "OMNI YTPROF page seq=%u dur=%.0f busy=%.1f", omniYp.seq, omniYp.navStart ? (t - omniYp.navStart) / 1e6 : 0.0, omniYpBusy() / 1e6);
    if (len > 0 && len < 1000) {
        len += omniYpCats(b + len, 1000 - size_t(len));
        for (int i = 0; i < OMNI_YP_COUNT; ++i) {
            uint64_t ns = omniYpOffNs[i].exchange(0, std::memory_order_relaxed);
            uint32_t n = omniYpOffN[i].exchange(0, std::memory_order_relaxed);
            if (n && len < 1500) {
                int k = snprintf(b + len, sizeof b - size_t(len), " off:%s=%.1f/%u", omniYpNames[i], ns / 1e6, n);
                if (k > 0 && k < int(sizeof b) - len)
                    len += k;
            }
        }
        int k = snprintf(b + len, sizeof b - size_t(len), " gc=%u/%u url=%.150s\n", omniYpGcCount[0].exchange(0), omniYpGcCount[1].exchange(0), omniYp.url);
        if (k > 0 && k < int(sizeof b) - len)
            len += k;
        omniYpWrite(b, len);
    }
    memset(omniYp.self, 0, sizeof omniYp.self);
    memset(omniYp.n, 0, sizeof omniYp.n);
    ++omniYp.seq;
    omniYp.markAt = t;
    if (!(navAgoMs > 0 && navAgoMs < 120000))
        navAgoMs = 0;
    omniYp.navStart = t - uint64_t(navAgoMs * 1e6);
    omniYp.lastSeries = 0;
    size_t i = 0;
    for (; url && url[i] && i + 1 < sizeof omniYp.url; ++i)
        omniYp.url[i] = (url[i] == ' ' || url[i] == '\n' || url[i] == '\r') ? '_' : url[i];
    omniYp.url[i] = 0;
    len = snprintf(b, sizeof b, "OMNI YTPROF nav seq=%u navAgo=%.0f url=%.150s\n", omniYp.seq, navAgoMs, omniYp.url);
    omniYpWrite(b, len);
}
