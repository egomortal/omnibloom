// OMNI_GPUPAGES_TCPROBE_V3 (diagnostic): event counts in the PlayStation ThreadedCompositor (ThreadedCompositorPlayStation.cpp)
// and LayerTreeHost (LayerTreeHostPlayStation.cpp, through omni_tc_count), read by the stage-1 heartbeat
// (ogp-s1-drawingarea.inc). With stage 1 on, the page's rendering updates (requestAnimationFrame) stopped while the
// compositor kept ticking. Included once, at the top of ThreadedCompositorPlayStation.cpp. Relaxed atomics only.
#include <atomic>
#include <cstdio>
#include <cstdint>
#include <time.h>
// U schedule, R render entry, C context-current failed, V viewport empty, W frame drawn, F frameComplete,
// D displayUpdateFired, S suspended, K commitSceneState, N renderNextFrame, B rendering update blocked (waiting for renderer)
static constexpr char kTcOrder[] = "URCVWFDSKNB";
static constexpr int kTcCount = sizeof kTcOrder - 1;
static std::atomic<uint64_t> s_tc[kTcCount];
static std::atomic<double> s_tcLast[kTcCount];
static inline void omniTcCount(char event)
{
    for (int i = 0; i < kTcCount; ++i) {
        if (kTcOrder[i] != event) continue;
        ++s_tc[i];
        struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
        s_tcLast[i] = t.tv_sec + t.tv_nsec / 1e9;
        return;
    }
}
extern "C" void omni_tc_count(char event) { omniTcCount(event); }   // for LayerTreeHostPlayStation.cpp
extern "C" void omni_tc_snapshot(char* buf, unsigned long size)
{
    auto n = [](int i) { return (unsigned long long)s_tc[i].load(); };
    snprintf(buf, size, "tc sched=%llu render=%llu ctxFail=%llu viewportEmpty=%llu drawn=%llu frameComplete=%llu displayUpdate=%llu suspended=%llu "
        "commit=%llu renderNextFrame=%llu blockedWaiting=%llu | last render=%.3f commit=%.3f renderNextFrame=%.3f blocked=%.3f",
        n(0), n(1), n(2), n(3), n(4), n(5), n(6), n(7), n(8), n(9), n(10),
        s_tcLast[1].load(), s_tcLast[8].load(), s_tcLast[9].load(), s_tcLast[10].load());
}
