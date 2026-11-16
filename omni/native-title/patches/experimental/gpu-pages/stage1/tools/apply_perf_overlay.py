#!/usr/bin/env python3
"""OMNI_PERF_OVERLAY_V1 (2026-11-16): an optional on-screen performance overlay (stutter / memory diagnosis on the TV).

What the user sees
  Browser settings > "Performance overlay"   < Off | Compact | Detailed >
      D-pad left / right steps (stops at both ends); Cross steps forward and wraps. Default Off.
  Options (quick menu) > Quick toggles > "Performance overlay" tile: Cross cycles Off -> Compact -> Detailed -> Off.
  A small dark, semi-transparent box in the top-right corner of the page area (below the top bar's height, so it never
  covers the address bar or tabs), numbers refreshed twice a second:
      Compact   one line    "16.7 ms  p95 18.3  |  60 fps  |  412 MiB"
      Detailed  six lines   Frame    16.7 ms avg  18.3 p95  33.4 max   (last 2 s)
                            Present  60 fps
                            Video    59.9 fps  3 dropped   / "none"
                            Memory   412 MiB used  1180 MiB free
                            Tabs     3 of 5 loaded  text cache 12.3 MiB (88)
                            Page     loading 63%  /  loaded
      A line turns amber / red when its number is bad (frame p95 > 17.5 / > 33.4 ms, present < 50 / < 25 fps while
      the page is drawing, free memory < 256 / < 128 MiB, video drops rising).

Counters (all already in the tree; nothing new is measured by other code)
  Frame time   tick start to tick start (the interval a viewer sees; the same measure as OMNI_JANK_V1's "interval"
               histogram). OMNI_JANK_V1 is off unless /data/omni/jank.flag and its window is 5 s of 8 coarse buckets
               (quantileEdge returns a bucket edge, not a percentile), so the overlay keeps its own ring: 512 samples of
               (performance counter, ms), fed only while the overlay is on; avg / exact p95 / max over the last 2 s are
               computed at the 2 Hz update (one 2 KB stack copy + nth_element, no allocation).
  Present fps  omniPresentFrame() calls (each hands a newly drawn canvas to the presenter), counted only while on.
  Video        OmniMedia::Hw::playbackStats() (OmniHwService.h "production HUD", atomics): new pictures =
               completed - repeats (holePunchVblank), drops = paced + raw drops of the owning channel, active.
               Those metadata atomics are published once a second by the service thread only while
               playbackStatsEnable(true): Detailed turns it on (and re-asserts it each update, since the existing
               "Playback stats" switch turns it off when it closes); leaving Detailed restores it to that switch's state.
  Memory       sceKernelConfiguredFlexibleMemorySize - sceKernelAvailableFlexibleMemorySize (the shell's flexible
               memory, as OMNI_TAB_MEMORY_VIEW_V1's Memory panel; both already imported). __PROSPERO__ only.
  Tabs         tabs.size() and omniTmIsUnloaded (OMNI_TAB_MEMORY's own test, as omniTmvLoaded).
  Text cache   omniTcCache.stats() (OMNI_TEXT_CACHE_CAP_V1): resident bytes and entries.
  Page         the active tab's loading flag and WKPageGetEstimatedProgress (the top bar's progress source). Bytes
               transferred are not exposed by the C API the shell uses: not shown.
  No new SCE import (import gate: imports-launch.txt already has both flexible-memory queries).

Cost
  Off: nothing is read, timed, allocated or drawn. Each hook is `if (omniPoMode)` on a static int (tick start, present,
  the draw paths) or a static bool reset (the regional planner); the 2 Hz tick returns on the same check after the
  setting was read once (one fopen of /data/omni/perf-overlay.txt <= 64 bytes, on the first omniF3Tick).
  On: per tick one counter read + one ring store; per present one increment. Twice a second: two kernel queries,
  a pass over the tabs, the 2 s summary, snprintf into fixed buffers; a line whose text changed is rendered again with
  SDL_ttf into the overlay's own surface (the only allocation, at most 6 surfaces twice a second, freed on the next
  change / Off). Every draw blends one rounded box and blits the cached surfaces (no string building, no cache lookup).
  Drawing: the new numbers request a draw without a draw reason (omniShellDirty.on); the regional planner
  (OMNI_PERF_A_S4) marks only the box's rows (old and new) and closes over them like the pointer, so an update
  redraws those rows, not the 4K frame; a regional draw that repaints any of the box's rows re-blends the whole box
  (semi-transparent: never blended twice). Whole draws (settings open, video hole punch, the 2 s watchdog while
  something asks for draws) draw it after the page and bars, below modals and the pointer.

Pure part: engine/entry/OmniPerfOverlay.h (no SDL / WebKit): modes, setting file text, the frame ring and its summary,
rates, the line texts and their warning levels, box geometry.
Tested by tools/test_perf_overlay.cpp:  g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_perf_overlay.cpp -o t && ./t
Shell side: engine/entry/OmniPerfOverlayShell.h, included from OmniFeatures3.h after OmniWebAppsShell.h.
Row id 898 in Browser settings, quick tile 946 (both unused in every apply_*.py and the tree; 897 Keep history,
945 Night light tile, 900+ Features V2).

Anchors (exactly once each; MARK makes each file idempotent; comments are /* */):
  OmniBrowser.cpp        the OmniTextCacheCap.h include (pure include after it); the omniStatsSurface line (state +
                         forward declarations after it: the planner, present and draw come before the shell include);
                         omniPresentFrame's OmniJankPresent line (present count); omniPlanDraw's "if (!changed) return 2;"
                         (box rows before it) and its pointer close (box close after it); draw()'s regional pointer line
                         (box before it) and the whole draw's omniOverlayDraw line (box before it); tick()'s
                         OmniJank::begin line (ring sample after it).
  OmniBrowserSettings.h  the omniHkRowId line (row id + declarations); the omniHkSettingsRow call (row after it); the
                         omniHkRowId input line (ours before it, so before the >= 300 rows).
  OmniQuickMenu.h        the omniNlQuickAction declaration (tile id + declarations); the omniNlQuickTiles call (tile
                         after it); the "case omniNlQuickId" group line (Quick toggles); the omniNlQuickAction input line
                         (ours before it, so before the >= 900 rows).
  OmniFeatures3.h        the OmniWebAppsShell.h include (shell include after it); the omniDlpTick line of omniF3Tick
                         (omniPoTick after it).
Apply AFTER apply_history_keep.py, apply_night_light.py, apply_web_apps.py, apply_dl_progress.py,
apply_text_cache_cap.py, apply_tab_memory_view.py (their lines are anchors / their symbols are used).
usage: apply_perf_overlay.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_PERF_OVERLAY_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_PERF_OVERLAY_V1: the pure part of the performance overlay (no SDL, no WebKit): the setting, the frame-time
// ring and its 2 s summary, rates, the overlay's line texts with warning levels, and its box geometry. The shell part
// is OmniPerfOverlayShell.h; reasons are in tools/apply_perf_overlay.py. Nothing here allocates.
#pragma once
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>

namespace OmniPerfOverlay {

enum Mode { Off = 0, Compact = 1, Detailed = 2, ModeCount = 3 };

constexpr const char* kFile = "perf-overlay.txt";
constexpr uint32_t kUpdateMs = 500;     // numbers at most twice a second
constexpr uint32_t kWindowMs = 2000;    // frame-time summary over the last 2 s
constexpr int kMaxLines = 6;
constexpr int kLineChars = 96;
constexpr const char* kRowLabel = "Performance overlay";

inline int clampMode(int m) { return m < Off ? Off : m > Detailed ? Detailed : m; }

inline const char* name(int m)
{
    switch (clampMode(m)) {
    case Compact: return "Compact";
    case Detailed: return "Detailed";
    default: return "Off";
    }
}

inline const char* token(int m)
{
    switch (clampMode(m)) {
    case Compact: return "compact";
    case Detailed: return "detailed";
    default: return "off";
    }
}

// perf-overlay.txt: one token line. Missing / unknown / empty: Off.
inline int parse(const std::string& text)
{
    size_t a = 0, b = text.size();
    while (a < b && (text[a] == ' ' || text[a] == '\t' || text[a] == '\r' || text[a] == '\n')) ++a;
    while (b > a && (text[b - 1] == ' ' || text[b - 1] == '\t' || text[b - 1] == '\r' || text[b - 1] == '\n')) --b;
    const std::string t = text.substr(a, b - a);
    if (t == "compact") return Compact;
    if (t == "detailed") return Detailed;
    return Off;
}

inline std::string serialize(int m) { return std::string(token(m)) + "\n"; }

// Settings stepper: left / right stop at both ends; Cross steps forward and wraps.
inline int step(int m, int dir, bool wrap)
{
    m = clampMode(m);
    if (wrap) return (m + 1) % ModeCount;
    return clampMode(m + (dir < 0 ? -1 : 1));
}
// Quick tile: Off -> Compact -> Detailed -> Off.
inline int quickNext(int m) { return (clampMode(m) + 1) % ModeCount; }

inline const char* rowDetail(int m)
{
    switch (clampMode(m)) {
    case Compact: return "Frame time, frames per second and memory in a corner";
    case Detailed: return "Frame time, present and video rates, memory, tabs, text cache, page load";
    default: return "Shows live performance numbers over the page";
    }
}

inline std::string changeNotice(int m)
{
    if (clampMode(m) == Off) return "Performance overlay off";
    return std::string("Performance overlay: ") + name(m);
}

// --- frame-time ring -------------------------------------------------------------------------------------------------
// (time stamp in performance-counter units, interval ms). Fixed storage; the oldest sample is overwritten.
struct Summary {
    unsigned count = 0;
    double avg = 0, p95 = 0, max = 0;
};

struct FrameRing {
    static constexpr unsigned kCap = 512;   // 2 s at up to 256 ticks/s
    uint64_t at[kCap] = {};
    float ms[kCap] = {};
    unsigned head = 0, size = 0;

    void clear() { head = size = 0; }
    void add(uint64_t stamp, double intervalMs)
    {
        if (!(intervalMs >= 0) || intervalMs > 60000) return;   // a bad clock reading never enters
        at[head] = stamp;
        ms[head] = float(intervalMs);
        head = (head + 1) % kCap;
        if (size < kCap) ++size;
    }
    // Samples stamped within `window` counter units before `now` (inclusive). p95: the sample at rank
    // ceil(0.95 * n) (nearest rank), exact over the window's samples.
    Summary summarize(uint64_t now, uint64_t window) const
    {
        float tmp[kCap];
        unsigned n = 0;
        double total = 0, mx = 0;
        for (unsigned k = 0; k < size; ++k) {
            const unsigned i = (head + kCap - 1 - k) % kCap;   // newest first
            if (at[i] > now || now - at[i] > window) break;     // older ones follow: stop
            tmp[n++] = ms[i];
            total += ms[i];
            mx = std::max(mx, double(ms[i]));
        }
        Summary s;
        s.count = n;
        if (!n) return s;
        s.avg = total / n;
        s.max = mx;
        unsigned rank = unsigned((95ull * n + 99) / 100);   // ceil(0.95 n), >= 1
        if (rank < 1) rank = 1;
        std::nth_element(tmp, tmp + (rank - 1), tmp + n);
        s.p95 = tmp[rank - 1];
        return s;
    }
};

// Events per second between two readings of a counter (0 when the time did not advance or the counter went back).
inline double rate(uint64_t before, uint64_t now, uint32_t elapsedMs)
{
    if (!elapsedMs || now < before) return 0;
    return double(now - before) * 1000.0 / double(elapsedMs);
}

// --- what one update shows ---------------------------------------------------------------------------------------------
struct Snapshot {
    Summary frame;
    double presentFps = 0;
    bool videoKnown = false, videoActive = false;
    double videoFps = 0;
    unsigned long long videoDrops = 0;
    bool videoDropsRising = false;
    long long usedMiB = -1, freeMiB = -1;   // -1: unknown (host, or the query failed)
    int loadedTabs = 0, totalTabs = 0;
    size_t textBytes = 0, textEntries = 0;
    bool hasPage = false, loading = false;
    int progressPct = 0;
};

struct Line {
    char text[kLineChars] = {};
    int level = 0;   // 0 normal, 1 warn (amber), 2 bad (red)
};

inline int frameLevel(const Summary& f)
{
    if (!f.count) return 0;
    return f.p95 > 33.4 ? 2 : f.p95 > 17.5 ? 1 : 0;
}
inline int memoryLevel(long long freeMiB)
{
    if (freeMiB < 0) return 0;
    return freeMiB < 128 ? 2 : freeMiB < 256 ? 1 : 0;
}
// A low present rate only matters while the shell is drawing continuously (idle pages present nothing, by design).
inline int presentLevel(double fps, bool busy)
{
    if (!busy) return 0;
    return fps < 25 ? 2 : fps < 50 ? 1 : 0;
}

// Fills `out` (kMaxLines entries) and returns how many lines the mode shows (0 for Off). `busy`: the page is
// loading or a video plays (the present rate is expected to be high).
inline int lines(const Snapshot& s, int mode, Line* out)
{
    mode = clampMode(mode);
    if (mode == Off || !out) return 0;
    for (int i = 0; i < kMaxLines; ++i) { out[i].text[0] = 0; out[i].level = 0; }
    const bool busy = s.loading || (s.videoKnown && s.videoActive);
    char mem[40];
    if (s.usedMiB >= 0) snprintf(mem, sizeof mem, "%lld MiB", s.usedMiB);
    else snprintf(mem, sizeof mem, "mem -");
    if (mode == Compact) {
        if (s.frame.count)
            snprintf(out[0].text, kLineChars, "%.1f ms  p95 %.1f  |  %.0f fps  |  %s", s.frame.avg, s.frame.p95, s.presentFps, mem);
        else
            snprintf(out[0].text, kLineChars, "-- ms  |  %.0f fps  |  %s", s.presentFps, mem);
        out[0].level = std::max(std::max(frameLevel(s.frame), memoryLevel(s.freeMiB)), presentLevel(s.presentFps, busy));
        return 1;
    }
    if (s.frame.count)
        snprintf(out[0].text, kLineChars, "Frame  %.1f ms avg  %.1f p95  %.1f max", s.frame.avg, s.frame.p95, s.frame.max);
    else
        snprintf(out[0].text, kLineChars, "Frame  --");
    out[0].level = frameLevel(s.frame);
    snprintf(out[1].text, kLineChars, "Present  %.0f fps", s.presentFps);
    out[1].level = presentLevel(s.presentFps, busy);
    if (!s.videoKnown || !s.videoActive) snprintf(out[2].text, kLineChars, "Video  none");
    else snprintf(out[2].text, kLineChars, "Video  %.1f fps  %llu dropped", s.videoFps, s.videoDrops);
    out[2].level = s.videoKnown && s.videoActive && s.videoDropsRising ? 1 : 0;
    if (s.usedMiB >= 0 && s.freeMiB >= 0) snprintf(out[3].text, kLineChars, "Memory  %lld MiB used  %lld MiB free", s.usedMiB, s.freeMiB);
    else snprintf(out[3].text, kLineChars, "Memory  --");
    out[3].level = memoryLevel(s.freeMiB);
    snprintf(out[4].text, kLineChars, "Tabs  %d of %d loaded  text cache %.1f MiB (%zu)", s.loadedTabs, s.totalTabs,
        double(s.textBytes) / (1024.0 * 1024.0), s.textEntries);
    if (!s.hasPage) snprintf(out[5].text, kLineChars, "Page  --");
    else if (s.loading) snprintf(out[5].text, kLineChars, "Page  loading %d%%", std::clamp(s.progressPct, 0, 100));
    else snprintf(out[5].text, kLineChars, "Page  loaded");
    return kMaxLines;
}

// --- geometry (layout pixels, 1280x720) ----------------------------------------------------------------------------
constexpr int kMargin = 12, kTopY = 164 + 12, kLineH = 20, kPadX = 10, kPadY = 6, kRadius = 8;
inline int boxW(int mode) { return clampMode(mode) == Detailed ? 400 : 320; }
inline int boxH(int count) { return count > 0 ? count * kLineH + 2 * kPadY : 0; }
inline int boxX(int mode, int layoutW) { return layoutW - kMargin - boxW(mode); }

} // namespace OmniPerfOverlay
'''

SHELL = r'''// OMNI_PERF_OVERLAY_V1: the performance overlay (shell side). Included from OmniFeatures3.h (inside OmniBrowser.cpp's
// anonymous namespace, after OmniWebAppsShell.h). The pure part is OmniPerfOverlay.h; the counters it reads and the
// cost rules are in tools/apply_perf_overlay.py. Main thread only. The state the planner / present / draw hooks test
// (omniPoMode, omniPoPresents, omniPoRow0/1, omniPoRegional) is declared near omniStatsSurface in OmniBrowser.cpp.
#pragma once
namespace OPRF = OmniPerfOverlay;
static bool omniPoRead = false;              // perf-overlay.txt read (once)
static OPRF::FrameRing omniPoRing;
static uint64_t omniPoLastStart = 0;         // previous tick start (performance counter); 0: none yet
static double omniPoFreq = 0;                // performance counter units per second
static uint32_t omniPoNextAt = 0, omniPoLastAt = 0;
static bool omniPoPrimed = false;            // the rate baselines below are valid
static unsigned long long omniPoPresentsWas = 0, omniPoVideoNewWas = 0, omniPoDropsWas = 0;
static OPRF::Line omniPoLines[OPRF::kMaxLines];
static int omniPoCount = 0;                  // lines shown
static SDL_Surface* omniPoText[OPRF::kMaxLines] = {};   // rendered once per text change
static int omniPoTextLevel[OPRF::kMaxLines] = {};
static bool omniPoDirty = false;             // new numbers not drawn yet
static int omniPoDrawn0 = 0, omniPoDrawn1 = 0;   // canvas rows the box was last drawn on

static void omniPoFrame(uint64_t start)   // tick start, only while on
{
    if (omniPoLastStart && start > omniPoLastStart && omniPoFreq > 0)
        omniPoRing.add(start, 1000.0 * double(start - omniPoLastStart) / omniPoFreq);
    omniPoLastStart = start;
}

static void omniPoFreeText()
{
    for (int i = 0; i < OPRF::kMaxLines; ++i) {
        if (omniPoText[i]) SDL_FreeSurface(omniPoText[i]);
        omniPoText[i] = nullptr;
        omniPoLines[i].text[0] = 0;
    }
    omniPoCount = 0;
}

// The box in canvas rows (with a pixel of slack for the rounded edge's blend).
static void omniPoRows(int& y0, int& y1)
{
    if (!omniPoMode || !omniPoCount || !canvas) { y0 = y1 = 0; return; }
    y0 = std::max(0, physical(OPRF::kTopY) - 1);
    y1 = std::min(canvas->h, physical(OPRF::kTopY + OPRF::boxH(omniPoCount)) + 1);
}

// omniPlanDraw: new numbers redraw the box's rows (where it was and where it is) and nothing else.
static bool omniPoPlan(std::vector<uint8_t>& changed)
{
    if (!omniPoDirty) return false;
    const int h = int(changed.size());
    int y0 = 0, y1 = 0;
    omniPoRows(y0, y1);
    omniPoRow0 = y0; omniPoRow1 = y1;
    auto mark = [&](int a, int b) { a = std::max(a, 0); b = std::min(b, h); if (b > a) memset(changed.data() + a, 1, size_t(b - a)); };
    mark(omniPoDrawn0, omniPoDrawn1);
    mark(y0, y1);
    return true;
}

static void omniPoDraw()
{
    if (!omniPoMode || !omniPoCount || !canvas) return;
    const int w = OPRF::boxW(omniPoMode), h = OPRF::boxH(omniPoCount);
    const int x = OPRF::boxX(omniPoMode, width), y = OPRF::kTopY;
    fillRounded(x, y, w, h, OPRF::kRadius, SDL_Color { 8, 10, 14, 255 }, 176);
    const int clip = physical(w - 2 * OPRF::kPadX);
    for (int i = 0; i < omniPoCount; ++i) {
        SDL_Surface* s = omniPoText[i];
        if (!s) continue;
        const int cy = y + OPRF::kPadY + i * OPRF::kLineH + OPRF::kLineH / 2;
        omniBlitText(s, physical(x + OPRF::kPadX), int(cy * displayScale + 0.5) - omniFaces[omniCaption].capMid, clip, 255);
    }
    omniPoRows(omniPoDrawn0, omniPoDrawn1);
    omniPoRow0 = omniPoDrawn0; omniPoRow1 = omniPoDrawn1;
    omniPoDirty = false;
}

static void omniPoRender(int i)
{
    if (omniPoText[i]) { SDL_FreeSurface(omniPoText[i]); omniPoText[i] = nullptr; }
    if (!omniPoLines[i].text[0] || !omniFaces[omniCaption].f) return;
    static const SDL_Color ink[3] = { { 232, 238, 244, 255 }, { 255, 196, 64, 255 }, { 255, 104, 96, 255 } };
    TTF_Font* face = omniFaces[omniCaption].f;   // ASCII only: no fallback face needed
    omniPoText[i] = TTF_RenderUTF8_Blended(face, omniPoLines[i].text, ink[std::clamp(omniPoLines[i].level, 0, 2)]);
    omniPoTextLevel[i] = omniPoLines[i].level;
}

static void omniPoSample(uint32_t now)
{
    OPRF::Snapshot s;
    const uint64_t counter = SDL_GetPerformanceCounter();
    s.frame = omniPoRing.summarize(counter, uint64_t(omniPoFreq * OPRF::kWindowMs / 1000.0));
    const uint32_t elapsed = omniPoPrimed ? now - omniPoLastAt : 0;
    s.presentFps = omniPoPrimed ? OPRF::rate(omniPoPresentsWas, omniPoPresents, elapsed) : 0;
    omniPoPresentsWas = omniPoPresents;
    if (omniPoMode == OPRF::Detailed) {
        OmniMedia::Hw::playbackStatsEnable(true);   // re-asserted: the Playback stats switch may have turned it off
        const auto st = OmniMedia::Hw::playbackStats();
        const unsigned long long fresh = st.completed >= st.repeats ? st.completed - st.repeats : 0;
        s.videoKnown = true;
        s.videoActive = st.active;
        s.videoFps = omniPoPrimed ? OPRF::rate(omniPoVideoNewWas, fresh, elapsed) : 0;
        s.videoDrops = st.drops;
        s.videoDropsRising = omniPoPrimed && st.drops > omniPoDropsWas;
        omniPoVideoNewWas = fresh;
        omniPoDropsWas = st.drops;
    }
#ifdef __PROSPERO__
    size_t configured = 0, available = 0;
    if (!sceKernelConfiguredFlexibleMemorySize(&configured) && !sceKernelAvailableFlexibleMemorySize(&available) && configured >= available) {
        s.usedMiB = (long long)((configured - available) >> 20);
        s.freeMiB = (long long)(available >> 20);
    }
#endif
    s.totalTabs = int(tabs.size());
    for (auto& t : tabs) if (!omniTmIsUnloaded(*t)) ++s.loadedTabs;
    const auto& tc = omniTcCache.stats();
    s.textBytes = tc.bytes; s.textEntries = tc.entries;
    if (Tab* t = active()) {
        s.hasPage = true;
        s.loading = t->loading && !t->crashed;
        if (s.loading && t->page) s.progressPct = int(WKPageGetEstimatedProgress(t->page) * 100.0 + 0.5);
    }
    omniPoLastAt = now;
    omniPoPrimed = true;
    OPRF::Line next[OPRF::kMaxLines];
    const int n = OPRF::lines(s, omniPoMode, next);
    bool any = n != omniPoCount;
    for (int i = 0; i < OPRF::kMaxLines; ++i) {
        if (i < n && (strcmp(next[i].text, omniPoLines[i].text) || next[i].level != omniPoLines[i].level || !omniPoText[i])) {
            omniPoLines[i] = next[i];
            omniPoRender(i);
            any = true;
        } else if (i >= n && omniPoText[i]) {
            SDL_FreeSurface(omniPoText[i]); omniPoText[i] = nullptr; omniPoLines[i].text[0] = 0;
            any = true;
        }
    }
    omniPoCount = n;
    if (any) { omniPoDirty = true; omniShellDirty.on = true; }   // a draw without a reason: the planner draws the box's rows
}

static void omniPoLoad()
{
    if (omniPoRead) return;
    omniPoRead = true;
    std::string text;
    if (FILE* f = fopen(omniData(OPRF::kFile).c_str(), "r")) {
        char buf[64];
        const size_t n = fread(buf, 1, sizeof(buf), f);
        text.assign(buf, n);
        fclose(f);
    }
    omniPoMode = OPRF::parse(text);
}

static void omniPoStart()
{
    omniPoFreq = double(SDL_GetPerformanceFrequency());
    omniPoRing.clear();
    omniPoLastStart = 0;
    omniPoPrimed = false;
    omniPoNextAt = SDL_GetTicks();   // first numbers on the next tick
}

static void omniPoTick(uint32_t now)   // from omniF3Tick
{
    if (!omniPoRead) { omniPoLoad(); if (omniPoMode) omniPoStart(); }
    if (!omniPoMode) return;
    if (int32_t(now - omniPoNextAt) < 0) return;
    omniPoNextAt = now + OPRF::kUpdateMs;
    omniPoSample(now);
}

static void omniPoSet(int mode)
{
    omniPoLoad();
    mode = OPRF::clampMode(mode);
    if (mode == omniPoMode) return;
    const int was = omniPoMode;
    omniPoMode = mode;
    omniIoQueue(omniData(OPRF::kFile), OPRF::serialize(mode), false);
    omniPoFreeText();   // the other mode's lines (re-rendered on the next update)
    omniPoDirty = false;
    omniPoRow0 = omniPoRow1 = 0;
    if (mode != OPRF::Detailed && was == OPRF::Detailed) OmniMedia::Hw::playbackStatsEnable(omniStatsPanel.enabled);
    if (mode) omniPoStart();
    omniShellDirty = true;   // a whole draw: the old box goes
}

// --- Browser settings > Performance overlay ------------------------------------------------------------------------
static void omniPoSettingsRow(OmniFxPanel& p)
{
    omniPoLoad();
    OmniFxRow r;
    r.id = omniPoRowId; r.label = OPRF::kRowLabel; r.value = OPRF::name(omniPoMode); r.stepper = true;
    r.detail = OPRF::rowDetail(omniPoMode);
    p.rows.push_back(r);
}
static bool omniPoSettingsInput(int b)
{
    const bool left = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT, right = b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT, a = b == SDL_CONTROLLER_BUTTON_A;
    if (!left && !right && !a) return false;
    omniPoLoad();
    const int k = OPRF::step(omniPoMode, left ? -1 : 1, a);
    if (k == omniPoMode) return true;
    omniPoSet(k);
    notice(OPRF::changeNotice(k));
    return true;
}

// --- Options > Quick toggles tile ---------------------------------------------------------------------------------
static void omniPoQuickTiles(OmniFxPanel& p)
{
    omniPoLoad();
    OmniFxRow r; r.id = omniPoQuickId; r.label = OPRF::kRowLabel; r.value = OPRF::name(omniPoMode);
    p.rows.push_back(r);
}
static bool omniPoQuickAction(int id)
{
    if (id != omniPoQuickId) return false;
    omniPoLoad();
    const int k = OPRF::quickNext(omniPoMode);
    omniPoSet(k);
    notice(OPRF::changeNotice(k));
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniTextCacheCap.h" // OMNI_TEXT_CACHE_CAP_V1: byte budget + LRU for rendered UI text (pure)\n',
         '#include "OmniTextCacheCap.h" // OMNI_TEXT_CACHE_CAP_V1: byte budget + LRU for rendered UI text (pure)\n'
         '#include "OmniPerfOverlay.h" /* OMNI_PERF_OVERLAY_V1: performance overlay: setting, frame ring, line texts (pure) */\n'),
        ('static SDL_Surface* omniStatsSurface=nullptr;\n',
         'static SDL_Surface* omniStatsSurface=nullptr;\n'
         '/* OMNI_PERF_OVERLAY_V1 (OmniPerfOverlayShell.h): every hook tests omniPoMode first; Off does no work. */\n'
         'static int omniPoMode = 0;                    /* 0 Off, 1 Compact, 2 Detailed */\n'
         'static unsigned long long omniPoPresents = 0; /* omniPresentFrame calls while on */\n'
         'static int omniPoRow0 = 0, omniPoRow1 = 0;    /* canvas rows of the box (0, 0: none) */\n'
         'static bool omniPoRegional = false;           /* this regional plan re-blends the box */\n'
         'static bool omniPoPlan(std::vector<uint8_t>& changed);\n'
         'static void omniPoDraw();\n'),
        ('        omniJankPresent { SDL_GetPerformanceCounter() }; // OMNI_JANK_V1\n',
         '        omniJankPresent { SDL_GetPerformanceCounter() }; // OMNI_JANK_V1\n'
         '    if (omniPoMode) ++omniPoPresents; /* OMNI_PERF_OVERLAY_V1: present rate */\n'),
        ('    if (!changed) return 2;\n',
         '    omniPoRegional = false; if (omniPoMode && omniPoPlan(R)) changed = true; /* OMNI_PERF_OVERLAY_V1: new numbers: the box rows only */\n'
         '    if (!changed) return 2;\n'),
        ('        close(p.y, p.y + p.h, omniRegion.pointer);\n',
         '        close(p.y, p.y + p.h, omniRegion.pointer);\n'
         '        close(omniPoRow0, omniPoRow1, omniPoRegional); /* OMNI_PERF_OVERLAY_V1: the box is re-blended whole */\n'),
        ('        if (omniRegion.pointer) omniDrawPointer();\n',
         '        if (omniPoRegional) omniPoDraw(); /* OMNI_PERF_OVERLAY_V1 */\n'
         '        if (omniRegion.pointer) omniDrawPointer();\n'),
        ('    omniOverlayDraw(); // OMNI_DIALOGS_V1: modals, menus and overlays above the shell\n',
         '    if (omniPoMode) omniPoDraw(); /* OMNI_PERF_OVERLAY_V1: below modals and the pointer */\n'
         '    omniOverlayDraw(); // OMNI_DIALOGS_V1: modals, menus and overlays above the shell\n'),
        ('    OmniJank::begin(frameStarted); // OMNI_JANK_V1\n',
         '    OmniJank::begin(frameStarted); // OMNI_JANK_V1\n'
         '    if (omniPoMode) omniPoFrame(frameStarted); /* OMNI_PERF_OVERLAY_V1: tick interval ring */\n'),
    ],
    'OmniBrowserSettings.h': [
        ('constexpr int omniHkRowId = 897; /* OMNI_HISTORY_KEEP_V1 (OmniHistoryKeepShell.h) */\n',
         'constexpr int omniHkRowId = 897; /* OMNI_HISTORY_KEEP_V1 (OmniHistoryKeepShell.h) */\n'
         'constexpr int omniPoRowId = 898; /* OMNI_PERF_OVERLAY_V1 (OmniPerfOverlayShell.h) */\n'
         'static void omniPoSettingsRow(OmniFxPanel& p);\n'
         'static bool omniPoSettingsInput(int b);\n'),
        ('    omniHkSettingsRow(p); /* OMNI_HISTORY_KEEP_V1: Keep history */\n',
         '    omniHkSettingsRow(p); /* OMNI_HISTORY_KEEP_V1: Keep history */\n'
         '    omniPoSettingsRow(p); /* OMNI_PERF_OVERLAY_V1: Performance overlay */\n'),
        ('    if (r.id == omniHkRowId) return omniHkSettingsInput(b); /* OMNI_HISTORY_KEEP_V1 (before the >= 300 rows) */\n',
         '    if (r.id == omniPoRowId) return omniPoSettingsInput(b); /* OMNI_PERF_OVERLAY_V1 (before the >= 300 rows) */\n'
         '    if (r.id == omniHkRowId) return omniHkSettingsInput(b); /* OMNI_HISTORY_KEEP_V1 (before the >= 300 rows) */\n'),
    ],
    'OmniQuickMenu.h': [
        ('static bool omniNlQuickAction(int id);\n',
         'static bool omniNlQuickAction(int id);\n'
         'constexpr int omniPoQuickId = 946; /* OMNI_PERF_OVERLAY_V1 (OmniPerfOverlayShell.h): Quick toggles tile */\n'
         'static void omniPoQuickTiles(OmniFxPanel& p);\n'
         'static bool omniPoQuickAction(int id);\n'),
        ('    omniNlQuickTiles(p); // OMNI_NIGHT_LIGHT_V1: Night light\n',
         '    omniNlQuickTiles(p); // OMNI_NIGHT_LIGHT_V1: Night light\n'
         '    omniPoQuickTiles(p); /* OMNI_PERF_OVERLAY_V1: Performance overlay */\n'),
        ('    case omniNlQuickId: return 2; // OMNI_NIGHT_LIGHT_V1: Quick toggles\n',
         '    case omniNlQuickId: return 2; // OMNI_NIGHT_LIGHT_V1: Quick toggles\n'
         '    case omniPoQuickId: return 2; /* OMNI_PERF_OVERLAY_V1: Quick toggles */\n'),
        ('    if (omniNlQuickAction(r.id)) return true; // OMNI_NIGHT_LIGHT_V1 (before the >= 900 rows)\n',
         '    if (omniPoQuickAction(r.id)) return true; /* OMNI_PERF_OVERLAY_V1 (before the >= 900 rows) */\n'
         '    if (omniNlQuickAction(r.id)) return true; // OMNI_NIGHT_LIGHT_V1 (before the >= 900 rows)\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniWebAppsShell.h" // OMNI_WEB_APPS_V1 (uses the pinned tabs\' close rule)\n',
         '#include "OmniWebAppsShell.h" // OMNI_WEB_APPS_V1 (uses the pinned tabs\' close rule)\n'
         '#include "OmniPerfOverlayShell.h" /* OMNI_PERF_OVERLAY_V1 */\n'),
        ('    omniDlpTick(now);   // OMNI_DL_PROGRESS_V1: Downloads progress (polls only while jobs run / after a hand-over)\n',
         '    omniDlpTick(now);   // OMNI_DL_PROGRESS_V1: Downloads progress (polls only while jobs run / after a hand-over)\n'
         '    omniPoTick(now);    /* OMNI_PERF_OVERLAY_V1: numbers at most twice a second (one check when Off) */\n'),
    ],
}


def variants(old0, s):
    """The anchor with the file's own line endings (mixed files: whichever spelling is present)."""
    for e in ('\r\n', '\n'):
        old = old0.replace('\n', e)
        if s.count(old):
            return old, e
    return old0, '\n'


def check(name, edits, mark=MARK):
    s = (root / name).read_bytes().decode('utf-8')
    if mark in s:
        return
    for old0, _ in edits:
        old, _e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))


def patch(name, edits, mark=MARK):
    p = root / name
    s = p.read_bytes().decode('utf-8')
    if mark in s:
        return name + ': already'
    for old0, new0 in edits:
        old, e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))
        s = s.replace(old, new0.replace('\n', e), 1)
    p.write_bytes(s.encode('utf-8'))
    return name + ': applied'


def write_new(name, text, like):
    raw = (root / like).read_bytes()
    nl = '\r\n' if raw.count(b'\r\n') * 2 > raw.count(b'\n') else '\n'
    data = text.replace('\n', nl).encode('utf-8')
    h = root / name
    if h.exists() and h.read_bytes() == data:
        return name + ': already'
    h.write_bytes(data)
    return name + ': written'


def main():
    for need, what in (('OmniBrowserSettings.h', 'OMNI_HISTORY_KEEP_V1'), ('OmniQuickMenu.h', 'OMNI_NIGHT_LIGHT_V1'),
                       ('OmniFeatures3.h', 'OMNI_WEB_APPS_V1'), ('OmniBrowser.cpp', 'OMNI_TEXT_CACHE_CAP_V1')):
        if what not in (root / need).read_bytes().decode('utf-8'):
            sys.exit('%s: %s missing: apply its tool first' % (need, what))
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniPerfOverlay.h', PURE, 'OmniTextCacheCap.h'),
            write_new('OmniPerfOverlayShell.h', SHELL, 'OmniTextCacheCap.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
