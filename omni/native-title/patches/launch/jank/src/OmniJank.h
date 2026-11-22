// SPDX-License-Identifier: GPL-3.0-or-later
// OMNI_JANK_V1 (diagnostic, Omni jank pass 2026-11-09): frame-time histograms for the SHELL's present loop
// (the title's tick) with per-long-frame attribution to the phases the shell already measures.
//
// Two histograms per window:
//   interval - tick start to tick start. This is what a viewer sees: a 100 ms interval is a visible hitch
//              whatever the shell did in it (a long tick, or the run loop busy elsewhere: WebKit IPC, timers).
//   work     - how long tick() itself ran.
// Buckets: <=8.3, <=16.7, <=25, <=33, <=50, <=100, <=200, >200 ms. Long frames are counted at >25, >50, >100 ms
// and each long frame's phase split is summed, so "what the main thread was doing in the long frames" is a
// number, not a guess. Phases are the ones the shell already times: page paint (WKPagePaint), draw (the 4K
// compose), present (hand-off + the bounded wait for the presenter's vblank), input (SDL poll + gamepad),
// blocker (the uBlock poll), video (hole-punch poll), feature/other, and outside (interval - work).
//
// Everything here is a no-op unless /data/omni/jank.flag exists when the shell first asks (one raw open()).
// Kill switch: delete the flag. Nothing is changed when the flag is absent; no timer, no allocation, no thread.
#pragma once
#include <algorithm>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstring>
#ifndef OMNI_JANK_HOST_TEST
#include <fcntl.h>
#include <unistd.h>
#endif

namespace OmniJank {

enum Phase { PhPagePaint = 0, PhDraw, PhPresent, PhInput, PhBlocker, PhVideo, PhFeature, PhOutside, PhCount };

inline const char* phaseName(int p)
{
    static const char* const names[PhCount] = { "paint", "draw", "present", "input", "blocker", "video", "feature", "outside" };
    return p >= 0 && p < PhCount ? names[p] : "?";
}

static constexpr int BucketCount = 8;

inline double bucketEdge(int i)
{
    static const double e[BucketCount] = { 8.4, 16.8, 25.0, 33.4, 50.0, 100.0, 200.0, 1e18 };
    return e[i >= 0 && i < BucketCount ? i : BucketCount - 1];
}

inline const char* bucketName(int i)
{
    static const char* const n[BucketCount] = { "<=8.3", "<=16.7", "<=25", "<=33", "<=50", "<=100", "<=200", ">200" };
    return n[i >= 0 && i < BucketCount ? i : BucketCount - 1];
}

struct Hist {
    uint32_t n[BucketCount] = {};
    uint32_t count = 0;
    double total = 0, max = 0;

    static int bucket(double ms)
    {
        for (int i = 0; i < BucketCount; ++i)
            if (ms <= bucketEdge(i))
                return i;
        return BucketCount - 1;
    }
    void add(double ms)
    {
        if (!(ms >= 0) || ms > 1e9)
            return;   // a bad clock reading never enters the histogram
        ++n[bucket(ms)];
        ++count;
        total += ms;
        max = std::max(max, ms);
    }
    double mean() const { return count ? total / count : 0; }
    // The highest bucket edge that at least `fraction` of the frames are at or below (a coarse quantile:
    // a histogram cannot give a true percentile, and saying so is the point of returning an edge).
    double quantileEdge(double fraction) const
    {
        if (!count)
            return 0;
        uint32_t want = uint32_t(double(count) * fraction);
        if (want < 1)
            want = 1;
        uint32_t seen = 0;
        for (int i = 0; i < BucketCount; ++i) {
            seen += n[i];
            if (seen >= want)
                return bucketEdge(i);
        }
        return max;
    }
    uint32_t over(double ms) const
    {
        uint32_t s = 0;
        for (int i = 0; i < BucketCount; ++i)
            if (bucketEdge(i) > ms)
                s += n[i];
        return s;
    }
    void reset() { *this = Hist(); }
};

struct Frame {
    double interval = 0;            // tick start to tick start
    double work = 0;                // tick() itself
    double phase[PhCount] = {};
    bool hasInterval = false;      // false on the first frame after a start or a clock reset: no interval sample
    bool drew = false, painted = false, presented = false, full = false, regional = false, pageBlocked = false;

    int dominant() const
    {
        int best = PhOutside;
        double bestMs = -1;
        for (int i = 0; i < PhCount; ++i)
            if (phase[i] > bestMs) { bestMs = phase[i]; best = i; }
        return best;
    }
};

struct Window {
    Hist interval, work;
    uint32_t long25 = 0, long50 = 0, long100 = 0;
    double longPhase[PhCount] = {};     // phase ms summed over the frames whose interval was > 25 ms
    uint32_t dominated[PhCount] = {};   // how often each phase was the largest in a long frame
    uint32_t drew = 0, painted = 0, presented = 0, full = 0, regional = 0, pageBlocked = 0;
    double longestPhase[PhCount] = {};

    void add(const Frame& f)
    {
        if (f.hasInterval)
            interval.add(f.interval);
        work.add(f.work);
        if (f.drew) ++drew;
        if (f.painted) ++painted;
        if (f.presented) ++presented;
        if (f.full) ++full;
        if (f.regional) ++regional;
        if (f.pageBlocked) ++pageBlocked;
        for (int i = 0; i < PhCount; ++i)
            longestPhase[i] = std::max(longestPhase[i], f.phase[i]);
        if (f.interval > 25.0) {
            ++long25;
            if (f.interval > 50.0) ++long50;
            if (f.interval > 100.0) ++long100;
            for (int i = 0; i < PhCount; ++i)
                longPhase[i] += f.phase[i];
            ++dominated[f.dominant()];
        }
    }
    void reset() { *this = Window(); }

    // "OMNI JANK hist <tag> frames=N ..." - one line, no allocation.
    int line(char* out, size_t cap, const char* tag) const
    {
        if (!out || cap < 64)
            return 0;
        size_t len = 0;
        auto put = [&](const char* fmt, ...) {
            if (len + 1 >= cap)
                return;
            va_list ap;
            va_start(ap, fmt);
            int k = vsnprintf(out + len, cap - len, fmt, ap);
            va_end(ap);
            if (k > 0 && size_t(k) < cap - len)
                len += size_t(k);
            else
                len = cap - 1;
        };
        put("OMNI JANK hist %s frames=%u interval mean=%.1f max=%.1f p50<=%.1f p95<=%.1f",
            tag ? tag : "-", interval.count, interval.mean(), interval.max,
            interval.quantileEdge(0.50), interval.quantileEdge(0.95));
        put(" b:");
        for (int i = 0; i < BucketCount; ++i)
            put(" %s=%u", bucketName(i), interval.n[i]);
        put(" | long >25=%u >50=%u >100=%u", long25, long50, long100);
        put(" | work mean=%.1f max=%.1f >25=%u", work.mean(), work.max, work.over(25.0));
        put(" | in long frames:");
        for (int i = 0; i < PhCount; ++i)
            put(" %s=%.0f/%u", phaseName(i), longPhase[i], dominated[i]);
        put(" | drew=%u painted=%u presented=%u full=%u regional=%u pageBlocked=%u",
            drew, painted, presented, full, regional, pageBlocked);
        return int(len);
    }
};

// ---- runtime glue (shell) ------------------------------------------------------------------------------------
// The shell calls: on() once per decision, begin()/end() around tick(), add*() from the places it already times,
// and mark() for a harness label ("scroll", "load", "video"). Lines go through the sink the shell installs
// (the engine's log writer thread), or to stderr when none is installed.

struct Runtime {
    bool enabled = false;
    bool asked = false;
    void (*sink)(const char*) = nullptr;
    Frame frame;
    Window window;
    Window total;
    uint64_t lastStart = 0;         // performance-counter units
    double frequency = 1;
    uint32_t seq = 0;
    uint32_t longLines = 0;
    uint32_t histLines = 0;
    uint32_t reportMs = 5000;
    uint32_t lastReport = 0;
    char label[32] = "start";
};

inline Runtime& runtime()
{
    static Runtime r;
    return r;
}

inline void emit(const char* line)
{
    Runtime& r = runtime();
    if (r.sink)
        r.sink(line);
    else {
        fputs(line, stderr);
        fputc('\n', stderr);
        fflush(stderr);
    }
}

inline bool on()
{
    Runtime& r = runtime();
    if (r.asked)
        return r.enabled;
    r.asked = true;
#ifdef OMNI_JANK_HOST_TEST
    r.enabled = true;
#else
    int fd = ::open("/data/omni/jank.flag", O_RDONLY);
    r.enabled = fd >= 0;
    if (fd >= 0)
        ::close(fd);
#endif
    return r.enabled;
}

inline void setSink(void (*sink)(const char*), double performanceFrequency)
{
    Runtime& r = runtime();
    r.sink = sink;
    if (performanceFrequency > 0)
        r.frequency = performanceFrequency;
}

inline void mark(const char* what)
{
    if (!on())
        return;
    Runtime& r = runtime();
    char line[160];
    snprintf(line, sizeof line, "OMNI JANK mark %s at seq=%u", what ? what : "-", r.seq);
    emit(line);
    // A new section starts a new window so the harness can compare sections, and the running total is kept.
    if (r.window.interval.count) {
        char b[1200];
        if (r.window.line(b, sizeof b, r.label) > 0)
            emit(b);
    }
    r.window.reset();
    size_t i = 0;
    for (; what && what[i] && i + 1 < sizeof r.label; ++i)
        r.label[i] = (what[i] == ' ' || what[i] == '\n') ? '_' : what[i];
    r.label[i] = 0;
}

inline void begin(uint64_t startCounter)
{
    if (!on())
        return;
    Runtime& r = runtime();
    r.frame = Frame();
    if (r.lastStart && startCounter > r.lastStart) {
        r.frame.interval = 1000.0 * double(startCounter - r.lastStart) / r.frequency;
        r.frame.hasInterval = true;
    }
    r.lastStart = startCounter;
}

inline void addPhase(int phase, double ms)
{
    if (phase < 0 || phase >= PhCount || !(ms >= 0))
        return;
    Runtime& r = runtime();
    if (r.enabled)
        r.frame.phase[phase] += ms;
}

inline void state(bool drew, bool painted, bool presented, bool full, bool regional)
{
    Runtime& r = runtime();
    if (!r.enabled)
        return;
    r.frame.drew = drew;
    r.frame.painted = painted;
    r.frame.presented = presented;
    r.frame.full = full;
    r.frame.regional = regional;
}

inline void pageBlocked()
{
    Runtime& r = runtime();
    if (r.enabled)
        r.frame.pageBlocked = true;
}

// Called from a scope guard at the top of tick(), so every return path records the frame.
inline void end(uint64_t startCounter, uint64_t endCounter, uint32_t nowMs)
{
    Runtime& r = runtime();
    if (!r.enabled)
        return;
    ++r.seq;
    if (endCounter > startCounter)
        r.frame.work = 1000.0 * double(endCounter - startCounter) / r.frequency;
    double accounted = 0;
    for (int i = 0; i < PhOutside; ++i)
        accounted += r.frame.phase[i];
    r.frame.phase[PhFeature] = std::max(0.0, r.frame.work - accounted);
    r.frame.phase[PhOutside] = std::max(0.0, r.frame.interval - r.frame.work);
    r.window.add(r.frame);
    r.total.add(r.frame);
    if (r.frame.interval > 25.0 && r.longLines < 400) {
        ++r.longLines;
        char line[520];
        int len = snprintf(line, sizeof line,
            "OMNI JANK long seq=%u %s dt=%.1f work=%.1f dom=%s", r.seq, r.label, r.frame.interval, r.frame.work,
            phaseName(r.frame.dominant()));
        for (int i = 0; i < PhCount && len > 0 && len < int(sizeof line) - 24; ++i) {
            int k = snprintf(line + len, sizeof line - size_t(len), " %s=%.1f", phaseName(i), r.frame.phase[i]);
            if (k > 0)
                len += k;
        }
        if (len > 0 && len < int(sizeof line) - 48)
            snprintf(line + len, sizeof line - size_t(len), " drew=%d painted=%d presented=%d blocked=%d",
                r.frame.drew ? 1 : 0, r.frame.painted ? 1 : 0, r.frame.presented ? 1 : 0, r.frame.pageBlocked ? 1 : 0);
        emit(line);
    }
    if (!r.lastReport)
        r.lastReport = nowMs;
    else if (nowMs - r.lastReport >= r.reportMs) {
        r.lastReport = nowMs;
        if (r.histLines < 600) {
            ++r.histLines;
            char b[1200];
            if (r.window.line(b, sizeof b, r.label) > 0)
                emit(b);
        }
        r.window.reset();
    }
}

inline void dumpTotal()
{
    Runtime& r = runtime();
    if (!r.enabled)
        return;
    char b[1200];
    if (r.window.interval.count && r.window.line(b, sizeof b, r.label) > 0)
        emit(b);
    if (r.total.line(b, sizeof b, "TOTAL") > 0)
        emit(b);
}

} // namespace OmniJank
