// OMNI_PERF_OVERLAY_V1: host tests for engine/entry/OmniPerfOverlay.h (the pure part of the performance overlay).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_perf_overlay.cpp -o t && ./t
#include "OmniPerfOverlay.h"
#include <cmath>
#include <cstdio>
#include <cstring>

namespace P = OmniPerfOverlay;
static int failures = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)
static bool near(double a, double b, double e = 1e-6) { return std::fabs(a - b) <= e; }

int main()
{
    // setting text
    CHECK(P::parse("") == P::Off);
    CHECK(P::parse("compact\n") == P::Compact);
    CHECK(P::parse("  detailed\r\n") == P::Detailed);
    CHECK(P::parse("bogus") == P::Off);
    CHECK(P::parse("off") == P::Off);
    for (int m = 0; m < P::ModeCount; ++m) CHECK(P::parse(P::serialize(m)) == m);
    CHECK(P::clampMode(-3) == P::Off && P::clampMode(9) == P::Detailed);
    CHECK(!strcmp(P::name(P::Compact), "Compact") && !strcmp(P::name(P::Off), "Off") && !strcmp(P::name(7), "Detailed"));
    // stepper: ends stop, Cross wraps; quick tile cycles
    CHECK(P::step(P::Off, -1, false) == P::Off);
    CHECK(P::step(P::Off, 1, false) == P::Compact);
    CHECK(P::step(P::Detailed, 1, false) == P::Detailed);
    CHECK(P::step(P::Detailed, -1, false) == P::Compact);
    CHECK(P::step(P::Detailed, 1, true) == P::Off);
    CHECK(P::step(P::Compact, -1, true) == P::Detailed);
    CHECK(P::quickNext(P::Off) == P::Compact && P::quickNext(P::Compact) == P::Detailed && P::quickNext(P::Detailed) == P::Off);
    CHECK(P::changeNotice(P::Off) == "Performance overlay off");
    CHECK(P::changeNotice(P::Detailed) == "Performance overlay: Detailed");

    // ring: empty
    {
        P::FrameRing r;
        const P::Summary s = r.summarize(1000, 2000);
        CHECK(s.count == 0 && s.avg == 0 && s.p95 == 0 && s.max == 0);
    }
    // ring: 100 samples 1..100 ms inside the window -> avg 50.5, p95 = 95 (nearest rank), max 100
    {
        P::FrameRing r;
        for (int i = 1; i <= 100; ++i) r.add(uint64_t(i), double(101 - i));   // order must not matter
        const P::Summary s = r.summarize(100, 1000);
        CHECK(s.count == 100);
        CHECK(near(s.avg, 50.5));
        CHECK(near(s.p95, 95.0));
        CHECK(near(s.max, 100.0));
    }
    // ring: the window drops old samples (stamps in counter units)
    {
        P::FrameRing r;
        for (int i = 0; i < 10; ++i) r.add(uint64_t(i * 100), 100.0);   // old: stamps 0..900
        for (int i = 0; i < 5; ++i) r.add(uint64_t(5000 + i), 10.0);    // recent
        const P::Summary s = r.summarize(5004, 1000);
        CHECK(s.count == 5);
        CHECK(near(s.avg, 10.0) && near(s.max, 10.0) && near(s.p95, 10.0));
        const P::Summary all = r.summarize(5004, 100000);
        CHECK(all.count == 15 && near(all.max, 100.0));
    }
    // ring: one slow frame among 60 shows in max and avg, not p95
    {
        P::FrameRing r;
        for (int i = 0; i < 59; ++i) r.add(uint64_t(i + 1), 16.7);
        r.add(60, 120.0);
        const P::Summary s = r.summarize(60, 1000);
        CHECK(s.count == 60 && near(s.max, 120.0) && s.p95 < 17.0f && s.avg > 16.7 && s.avg < 19.0);
    }
    // ring: wraps at capacity, keeps the newest kCap, rejects bad readings
    {
        P::FrameRing r;
        for (unsigned i = 0; i < P::FrameRing::kCap + 100; ++i) r.add(uint64_t(i + 1), i < 100 ? 500.0 : 8.0);
        r.add(P::FrameRing::kCap + 200, -1.0);
        r.add(P::FrameRing::kCap + 200, 1e9);
        CHECK(r.size == P::FrameRing::kCap);
        const P::Summary s = r.summarize(P::FrameRing::kCap + 100, 1u << 30);
        CHECK(s.count == P::FrameRing::kCap && near(s.max, 8.0));
    }
    // ring: a stamp after `now` (clock read before the newest sample) stops the scan safely
    {
        P::FrameRing r;
        r.add(10, 5.0); r.add(20, 6.0);
        CHECK(r.summarize(15, 100).count == 0);
        CHECK(r.summarize(20, 100).count == 2);
    }

    // rate
    CHECK(near(P::rate(100, 160, 1000), 60.0));
    CHECK(near(P::rate(0, 30, 500), 60.0));
    CHECK(P::rate(10, 5, 500) == 0);
    CHECK(P::rate(10, 20, 0) == 0);

    // levels
    {
        P::Summary f; f.count = 10; f.p95 = 16.8; CHECK(P::frameLevel(f) == 0);
        f.p95 = 20; CHECK(P::frameLevel(f) == 1);
        f.p95 = 40; CHECK(P::frameLevel(f) == 2);
        P::Summary none; CHECK(P::frameLevel(none) == 0);
        CHECK(P::memoryLevel(-1) == 0 && P::memoryLevel(1000) == 0 && P::memoryLevel(200) == 1 && P::memoryLevel(100) == 2);
        CHECK(P::presentLevel(5, false) == 0 && P::presentLevel(60, true) == 0 && P::presentLevel(40, true) == 1 && P::presentLevel(10, true) == 2);
    }

    // lines
    P::Line out[P::kMaxLines];
    P::Snapshot s;
    CHECK(P::lines(s, P::Off, out) == 0);
    s.frame.count = 120; s.frame.avg = 16.66; s.frame.p95 = 18.31; s.frame.max = 33.4;
    s.presentFps = 59.6; s.usedMiB = 412; s.freeMiB = 1180;
    s.totalTabs = 5; s.loadedTabs = 3; s.textBytes = 12 * 1024 * 1024 + 300 * 1024; s.textEntries = 88;
    s.hasPage = true; s.loading = true; s.progressPct = 63;
    CHECK(P::lines(s, P::Compact, out) == 1);
    CHECK(!strcmp(out[0].text, "16.7 ms  p95 18.3  |  60 fps  |  412 MiB"));
    CHECK(out[0].level == 1);   // p95 over 17.5
    CHECK(P::lines(s, P::Detailed, out) == P::kMaxLines);
    CHECK(!strcmp(out[0].text, "Frame  16.7 ms avg  18.3 p95  33.4 max"));
    CHECK(!strcmp(out[1].text, "Present  60 fps"));
    CHECK(!strcmp(out[2].text, "Video  none"));
    CHECK(!strcmp(out[3].text, "Memory  412 MiB used  1180 MiB free"));
    CHECK(!strcmp(out[4].text, "Tabs  3 of 5 loaded  text cache 12.3 MiB (88)"));
    CHECK(!strcmp(out[5].text, "Page  loading 63%"));
    CHECK(out[0].level == 1 && out[1].level == 0 && out[3].level == 0);
    s.videoKnown = s.videoActive = true; s.videoFps = 59.94; s.videoDrops = 3; s.videoDropsRising = true;
    s.loading = false; s.freeMiB = 90;
    P::lines(s, P::Detailed, out);
    CHECK(!strcmp(out[2].text, "Video  59.9 fps  3 dropped") && out[2].level == 1);
    CHECK(!strcmp(out[5].text, "Page  loaded"));
    CHECK(out[3].level == 2);
    s.presentFps = 20;   // video playing: a low present rate is bad
    P::lines(s, P::Detailed, out);
    CHECK(out[1].level == 2);
    // unknown memory / no frames / no page
    P::Snapshot e;
    CHECK(P::lines(e, P::Compact, out) == 1 && !strcmp(out[0].text, "-- ms  |  0 fps  |  mem -") && out[0].level == 0);
    P::lines(e, P::Detailed, out);
    CHECK(!strcmp(out[0].text, "Frame  --") && !strcmp(out[3].text, "Memory  --") && !strcmp(out[5].text, "Page  --"));
    // extremes stay inside the fixed buffers (snprintf truncates, always terminated)
    P::Snapshot x;
    x.frame.count = 1; x.frame.avg = x.frame.p95 = x.frame.max = 59999.9; x.presentFps = 1e6;
    x.usedMiB = x.freeMiB = 9223372036854775807LL; x.totalTabs = x.loadedTabs = 2147483647;
    x.textBytes = size_t(-1); x.textEntries = size_t(-1); x.hasPage = x.loading = true; x.progressPct = 1000;
    x.videoKnown = x.videoActive = true; x.videoFps = 1e9; x.videoDrops = ~0ull;
    CHECK(P::lines(x, P::Detailed, out) == P::kMaxLines);
    for (int i = 0; i < P::kMaxLines; ++i) CHECK(strlen(out[i].text) < size_t(P::kLineChars));
    CHECK(!strcmp(out[5].text, "Page  loading 100%"));

    // geometry: the box fits right of centre, below the top bar, inside 1280x720
    for (int m = P::Compact; m <= P::Detailed; ++m) {
        CHECK(P::boxX(m, 1280) + P::boxW(m) == 1280 - P::kMargin);
        CHECK(P::boxX(m, 1280) > 640);
    }
    CHECK(P::boxH(0) == 0 && P::boxH(1) == 32 && P::kTopY + P::boxH(P::kMaxLines) < 720 - 32);
    // every line fits its box width at the caption face's ~7 px average advance
    P::lines(s, P::Detailed, out);
    for (int i = 0; i < P::kMaxLines; ++i) CHECK(int(strlen(out[i].text)) * 7 <= P::boxW(P::Detailed) - 2 * P::kPadX);

    printf("%s: %d checks, %d failed\n", failures ? "FAIL" : "ok", checks, failures);
    return failures ? 1 : 0;
}
