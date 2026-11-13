// omni-gpu-pages stage 1 (OMNI_GPU_PAGES_STAGE1_V1): the delivery policy for composited page frames.
// SPDX-License-Identifier: GPL-3.0-or-later
//
// In stage 1 the WebProcess composites on the GPU (threaded compositor, TextureMapper) and delivers each
// finished frame to the UI process as an ordinary DrawingAreaProxy::Update bitmap, so the UI process stays in
// backing-store mode and Omni's shell (WKPagePaint, the 4K compose, hole-punch) is untouched. This header is
// the one decision the delivery makes, kept free of WebKit types so the host gate compiles the same text:
//
//   - at most ONE update in flight to the UI process (the UI acks each with DisplayDidRefresh);
//   - a frame finished while one is in flight replaces any frame already waiting: the newest wins, and the
//     replaced one is counted as coalesced, never queued -- a slow UI costs frames, never latency;
//   - the compositor itself is never held: it gets frameDone() as soon as its pixels are read back, so the
//     page's own rendering loop no longer waits for the shell (the omni-jank finding);
//   - an ack that never comes is bounded: after kAckTimeoutMs the in-flight slot is reclaimed and counted,
//     so a lost DisplayDidRefresh can stall delivery for at most that long instead of forever;
//   - intervals between delivered frames go into the omni-jank histogram's exact buckets, so a stage-1 run's
//     "OMNI GPUPAGES phist" sits row for row beside a non-composited run's "OMNI JANK phist".
// Main thread only: every call happens on the WebProcess main run loop.
#pragma once
#include <cstdint>
#include <cstdio>

namespace OmniGpuPages {

static constexpr int kBuckets = 8;
static constexpr double kEdge[kBuckets] = { 8.4, 16.8, 25.0, 33.4, 50.0, 100.0, 200.0, 1e18 };   // == omni-jank omniJkEdge
static constexpr const char* kEdgeName[kBuckets] = { "<=8.3", "<=16.7", "<=25", "<=33", "<=50", "<=100", "<=200", ">200" };
static constexpr double kAckTimeoutMs = 1000.0;

struct Stat {
    uint64_t n = 0; double total = 0, max = 0;
    void add(double v) { ++n; total += v; if (v > max) max = v; }
    double mean() const { return n ? total / n : 0; }
};

struct Hist {
    uint32_t b[kBuckets] = {}; uint32_t count = 0; double total = 0, max = 0;
    uint32_t over25 = 0, over50 = 0, over100 = 0;
    void add(double ms)
    {
        int i = 0;
        while (i < kBuckets - 1 && ms > kEdge[i]) ++i;
        ++b[i]; ++count; total += ms; if (ms > max) max = ms;
        over25 += ms > 25.0; over50 += ms > 50.0; over100 += ms > 100.0;
    }
    // upper edge of the bucket holding the q-th quantile (the same "p50<=" the jank sink prints)
    double quantileEdge(double q) const
    {
        if (!count) return 0;
        uint32_t want = static_cast<uint32_t>(q * count + 0.999999), seen = 0;
        for (int i = 0; i < kBuckets; ++i) { seen += b[i]; if (seen >= want) return kEdge[i] >= 1e17 ? max : kEdge[i]; }
        return max;
    }
};

struct Delivery {
    bool inFlight = false, havePending = false;
    double sentAtMs = 0, lastDeliveredMs = -1;
    uint64_t composited = 0, delivered = 0, coalesced = 0, ackTimeouts = 0, acks = 0;
    Stat rtt, readback;
    Hist interval;

    // A finished frame is offered. true: send it now (it is now the one in flight). false: it is held as the
    // pending frame (the caller keeps exactly one, replacing any older one).
    bool offer(double nowMs)
    {
        ++composited;
        if (inFlight && nowMs - sentAtMs > kAckTimeoutMs) {   // the ack never came: reclaim the slot
            ++ackTimeouts;
            inFlight = false;
        }
        if (inFlight) {
            if (havePending) ++coalesced;
            havePending = true;
            return false;
        }
        if (havePending) { ++coalesced; havePending = false; }   // a newer frame supersedes a held one
        send(nowMs);
        return true;
    }
    // The UI process acked the in-flight update. true: send the held frame now.
    bool acked(double nowMs)
    {
        if (!inFlight) return false;                            // a stray or late ack: nothing to do
        ++acks;
        rtt.add(nowMs - sentAtMs);
        inFlight = false;
        if (!havePending) return false;
        havePending = false;
        send(nowMs);
        return true;
    }
    void send(double nowMs)
    {
        inFlight = true; sentAtMs = nowMs; ++delivered;
        if (lastDeliveredMs >= 0) interval.add(nowMs - lastDeliveredMs);
        lastDeliveredMs = nowMs;
    }
    // Windowed like the jank sink (it resets its histograms after every 5 s report): the interval histogram and the
    // readback / round-trip stats start again; composited/delivered/coalesced/ackTimeouts stay cumulative.
    void resetWindow() { interval = Hist { }; readback = Stat { }; rtt = Stat { }; }
    // Same shape as the jank sink's line, so analyze_gpupages.py reads both.
    int format(char* out, unsigned size) const
    {
        int len = snprintf(out, size, "OMNI GPUPAGES phist frames=%u dt mean=%.1f max=%.1f p50<=%.1f p95<=%.1f b:",
            interval.count, interval.count ? interval.total / interval.count : 0.0, interval.max,
            interval.quantileEdge(0.50), interval.quantileEdge(0.95));
        for (int i = 0; i < kBuckets && len > 0 && len < static_cast<int>(size); ++i)
            len += snprintf(out + len, size - len, "%s%s=%u", i ? "," : "", kEdgeName[i], interval.b[i]);
        if (len > 0 && len < static_cast<int>(size))
            len += snprintf(out + len, size - len,
                " | long >25/>50/>100 %u/%u/%u | composited=%llu delivered=%llu coalesced=%llu ackTimeouts=%llu"
                " | readback mean=%.2f max=%.2f | deliver rtt mean=%.1f max=%.1f n=%llu",
                interval.over25, interval.over50, interval.over100,
                static_cast<unsigned long long>(composited), static_cast<unsigned long long>(delivered),
                static_cast<unsigned long long>(coalesced), static_cast<unsigned long long>(ackTimeouts),
                readback.mean(), readback.max, rtt.mean(), rtt.max, static_cast<unsigned long long>(rtt.n));
        return len;
    }
};

} // namespace OmniGpuPages
