#!/usr/bin/env python3
"""WS-A "shell present" (OMNI_PERF_A_*) onto a clean copy of dl2-candidate-53's entry/OmniBrowser.cpp.
Every replacement must match exactly once (the script stops if the source drifted). CRLF is kept."""
import sys, pathlib
path = pathlib.Path(sys.argv[1])
rowover = pathlib.Path(sys.argv[2]).read_text()
raw = path.read_bytes().decode('utf-8')
assert '\r\n' in raw
src = raw.replace('\r\n', '\n')
def rep(old, new, count=1):
    global src
    n = src.count(old)
    if n != count:
        sys.exit(f'patch: expected {count} match(es), found {n}:\n{old[:300]}')
    src = src.replace(old, new)

# ---------------------------------------------------------------- 1. WS-B hook declaration (outside the anonymous namespace)
rep('''extern "C" int omniHDROutputPQ(); // OMNI_HDR_PORT_V1
''', '''extern "C" int omniHDROutputPQ(); // OMNI_HDR_PORT_V1
// OMNI_PERF_A_HOOK (for the video service, WS-B): set by the service when it can show a new video picture without a new canvas
// (the presenter owns the fullscreen video pixels). The shell main thread calls it only when the one reason to draw is the
// video plane (holePunchPoll() true, nothing else changed); nonzero skips that draw. nullptr (default): draw as before.
extern "C" int (*omniShellVideoOnlyDrawSkip)(void);
// OMNI_PERF_A_COUNTER: the reason mask (omniDr* bits, OmniBrowser.cpp) of the shell's latest draw decision (diagnostics).
extern "C" unsigned omniShellLastDrawReasons;
''')

# ---------------------------------------------------------------- 2. dirty flags with reasons, kill switches, early state
rep('''// OMNI_SHELL_DRAW_V1: what changed since the last presented frame.
static bool omniPageDirty = true, omniShellDirty = true;
''', '''// OMNI_SHELL_DRAW_V1: what changed since the last presented frame.
// OMNI_PERF_A_COUNTER: why the shell draws. `omniShellDirty = true` records the phase of tick() it happens in (WebKit:
// outside tick, i.e. callbacks and other timers); tick() adds the page, video, refresh and busy reasons itself. Aggregated
// and logged once per 5 s ("draw reasons (5 s): ..."), never per frame.
enum : unsigned {
    omniDrFirst = 1u << 0, omniDrPageFull = 1u << 1, omniDrPagePartial = 1u << 2, omniDrSafety = 1u << 3,
    omniDrVideo = 1u << 4, omniDrRefresh = 1u << 5, omniDrBusy = 1u << 6, omniDrSpinner = 1u << 7,
    omniDrStyle = 1u << 8, omniDrInput = 1u << 9, omniDrAxis = 1u << 10, omniDrStick = 1u << 11,
    omniDrWebKit = 1u << 12, omniDrFeature = 1u << 13, omniDrSignature = 1u << 14 };
constexpr int omniDrCount = 15;
static unsigned omniDirtyPhase = omniDrWebKit;   // the reason `omniShellDirty = true` records now
static unsigned omniDrawReasons = 0;             // since the last draw decision
struct OmniDirtyFlag {
    bool on = false;
    OmniDirtyFlag& operator=(bool v) { on = v; if (v) omniDrawReasons |= omniDirtyPhase; return *this; }
    OmniDirtyFlag& operator=(const OmniDirtyFlag& o) { return *this = o.on; }
    operator bool() const { return on; }
};
static bool omniPageDirty = true;
static OmniDirtyFlag omniShellDirty { true };
static void omniMarkDirty(unsigned reason) { omniDrawReasons |= reason; omniShellDirty.on = true; }
// OMNI_PERF_A_*: kill switches, read once: /data/omni/perf-a-disabled.flag (all) or perf-a-<item>-disabled.flag.
enum { omniPerfS1, omniPerfS3, omniPerfS4, omniPerfS5, omniPerfS6, omniPerfS7, omniPerfS2, omniPerfS8, omniPerfCount };
static bool omniPerfOn(int item)
{
    static int state[omniPerfCount] = {};   // 0 not read yet, 1 on, 2 off
    if (!state[item]) {
        static const char* const names[omniPerfCount] = { "s1", "s3", "s4", "s5", "s6", "s7", "s2", "s8" };
        char flag[96];
        snprintf(flag, sizeof flag, "/data/omni/perf-a-%s-disabled.flag", names[item]);
        state[item] = access("/data/omni/perf-a-disabled.flag", F_OK) == 0 || access(flag, F_OK) == 0 ? 2 : 1;
    }
    return state[item] == 1;
}
// OMNI_FAST_PAGE_V1 half-resolution page (declared here for OMNI_PERF_A_S5).
static std::vector<uint32_t> omniPageSmall;
// OMNI_PERF_A_S5: the 4K page buffer (`pixels`) lags the half-resolution one; the canvas is filled straight from omniPageSmall,
// and omniEnsurePixels() brings `pixels` up to date for the few readers that need it (video compose, preview capture).
static bool omniPixelsStale = false;
static void omniEnsurePixels();
static bool omniSmoothDrawOn(); // OMNI_SMOOTH_DRAW_V1 (defined with the page copy)
// OMNI_PERF_A_HOOK, merge point for WS-B (ws-b-1: media/OmniHwService.h declares OmniMedia::Hw::holePunchPresenterOwnsVideo()):
// true while the presenter shows the fullscreen video by itself. Set OMNI_PERF_A_WS_B to 1 when merging with ws-b-1;
// at 0 (this build, against 53's media headers) it is always false and nothing changes.
#ifndef OMNI_PERF_A_WS_B
#define OMNI_PERF_A_WS_B 0
#endif
static bool omniPresenterOwnsVideo()
{
#if OMNI_PERF_A_WS_B
    return OmniMedia::Hw::holePunchPresenterOwnsVideo();
#else
    return false;
#endif
}
// OMNI_PERF_A_S4: page rows (in page-buffer rows) WebKit's pixels changed in since the last drawn frame.
struct OmniRows { int y0 = 0, y1 = 0; bool any() const { return y1 > y0; } void add(int a, int b) { if (b <= a) return; if (!any()) { y0 = a; y1 = b; } else { y0 = std::min(y0, a); y1 = std::max(y1, b); } } };
static OmniRows omniPageDamage;
// OMNI_PERF_A_COUNTER: aggregated over 5 s.
struct OmniDrawCensus {
    uint32_t since = 0;
    unsigned ticks = 0, draws = 0, full = 0, regional = 0, regionalRows = 0, nothing = 0, reused = 0, idle = 0, videoSkips = 0, busyKept = 0;
    unsigned reason[omniDrCount] = {};
    unsigned paints = 0, over20 = 0, over100 = 0, over400 = 0, deferred = 0, slowArmed = 0, safety = 0, safetyChanged = 0, realigns = 0, watchdog = 0, forced = 0;
    double paintMs = 0, paintMax = 0;
};
static OmniDrawCensus omniCensus;
''')

# ---------------------------------------------------------------- 3. Tab: S1 per-tab backoff
rep('''    std::string omniPendingLoad;  // re-issued with another user agent (next tick)
};''', '''    std::string omniPendingLoad;  // re-issued with another user agent (next tick)
    uint32_t omniSlowUntil = 0, omniSlowBackoff = 0; // OMNI_PERF_A_S1: a WKPagePaint blocked (>= 100 ms): no page paint before omniSlowUntil
    // OMNI_PERF_A_S1 (ws-a-1b): WebKit reported pixels since this tab was shown (its backing store exists); when a wait for that
    // began; how many watchdog paints were tried without a report (each waits longer: 2, 4, 8 s).
    bool omniShownReported = false, omniEverReported = false;
    uint32_t omniWaitSince = 0, omniNoReportTries = 0;
};''')

# ---------------------------------------------------------------- 4. buffers reassigned: `pixels` is what is shown
rep('''    pixels.assign(size_t(renderWidth) * renderPageHeight * 4, 0);
    pageSurface''', '''    pixels.assign(size_t(renderWidth) * renderPageHeight * 4, 0);
    omniPixelsStale = false; // OMNI_PERF_A_S5
    pageSurface''')
rep('''    pixels.assign(size_t(renderWidth) * renderPageHeight * 4, 255);
    pageSurface''', '''    pixels.assign(size_t(renderWidth) * renderPageHeight * 4, 255);
    omniPixelsStale = false; // OMNI_PERF_A_S5
    pageSurface''')
rep('''    std::fill(pixels.begin(), pixels.end(), 255);
    omniEverydayActivated();''', '''    std::fill(pixels.begin(), pixels.end(), 255);
    omniPixelsStale = false; // OMNI_PERF_A_S5: the white page is what shows until the tab's first paint
    active()->omniShownReported = false; active()->omniWaitSince = 0; active()->omniNoReportTries = 0; // OMNI_PERF_A_S1: wait for its report
    omniEverydayActivated();''')

# ---------------------------------------------------------------- 5. spinner: its own reason; WS-B merge point (presenter owns the video)
rep('''    if ((anyLoading || omniProgressAlpha > 0) && now - omniLastDraw >= 33) omniShellDirty = true;   // ~30 Hz spinner
    if (!omniToastText.empty() && (now - omniToastSince < 240 || (statusUntil && omniToastText == status && int32_t(statusUntil - now) < 420)))
        omniShellDirty = true;   // toast fading in or out
    if (omniToastError && !omniToastText.empty() && now - omniToastSince >= omniToastErrorMs - 420 && now - omniToastSince < omniToastErrorMs + 100)
        omniShellDirty = true;   // OMNI_POLISH_V1: error toast fading out''', '''    // OMNI_PERF_A_HOOK (WS-B OMNI_PERF_B_V2): a fullscreen video the presenter shows by itself hides the bars, the spinner and
    // the toast (draw()'s fullscreen branch draws none of them): their animations need no 4K draw there.
    const bool omniVideoOwnsScreen = pageFullscreen && omniPresenterOwnsVideo();
    if ((anyLoading || omniProgressAlpha > 0) && now - omniLastDraw >= 33 && !omniVideoOwnsScreen) omniMarkDirty(omniDrSpinner);   // ~30 Hz spinner (OMNI_PERF_A_COUNTER: own reason)
    if (!omniToastText.empty() && !omniVideoOwnsScreen && (now - omniToastSince < 240 || (statusUntil && omniToastText == status && int32_t(statusUntil - now) < 420)))
        omniShellDirty = true;   // toast fading in or out
    if (omniToastError && !omniToastText.empty() && !omniVideoOwnsScreen && now - omniToastSince >= omniToastErrorMs - 420 && now - omniToastSince < omniToastErrorMs + 100)
        omniShellDirty = true;   // OMNI_POLISH_V1: error toast fading out''')

# ---------------------------------------------------------------- 5b. S1: the active tab reported pixels (its backing store is up to date)
rep('''        if (info != active()) return;
        ++omniSplit.dirtyCalls;''', '''        if (info != active()) return;
        { Tab* t = active(); t->omniShownReported = t->omniEverReported = true; t->omniNoReportTries = 0; } // OMNI_PERF_A_S1
        ++omniSplit.dirtyCalls;''')

# ---------------------------------------------------------------- 6. presenter state: damage rect, vblank stamp
rep('''static bool omniPresentBusy = false, omniPresentStop = false, omniPresentFailed = false;
''', '''static bool omniPresentBusy = false, omniPresentStop = false, omniPresentFailed = false;
static SDL_Rect omniPresentDamage {};          // OMNI_PERF_A_S2: rows the handed-off canvas changed (guarded by omniPresentLock)
static bool omniPresentDamaged = false;        // false: tile the whole frame
static std::atomic<uint64_t> omniVblankAt { 0 }; // OMNI_PERF_A_S8: performance counter when the presenter's last flip returned
''')

ROWOVER = rowover

# ---------------------------------------------------------------- 7. frame bookkeeping, draw plan, shell signature (before the presenter)
rep('''// OMNI_SHELL_PRESENT_V1 -------------------------------------------------------------------
static void omniPresenterMain()
''', '''// OMNI_PERF_A_S4 / S2 ----------------------------------------------------------------------
// Which rows each drawn frame changed. Canvas and screen buffers are exchanged at every 4K hand-off, so the canvas a draw
// starts from holds an older frame: a regional draw redraws the rows changed since that frame (buffer age), and the SDL
// tiler is given the rows changed since the frame on screen (its own per-buffer pending rect covers its other buffer).
struct OmniFrameRows { uint32_t frame = 0; bool full = true; uint64_t key = 0; std::vector<uint8_t> rows; };
static OmniFrameRows omniFrames[4];
static uint32_t omniFrameNo = 0;                       // frames drawn so far
static uint32_t omniCanvasHolds = 0, omniScreenHolds = 0; // frame in canvas->pixels / screen->pixels (0: unknown)
static bool omniCanvasPending = false;                 // OMNI_PERF_A_S7: the canvas holds a drawn frame the presenter was too busy to take
static int omniHoleFrames = 0;                         // full draws still owed after a hole-punched video was shown
static SDL_Rect omniPointerLast { 0, 0, 0, 0 };        // where the last drawn frame has the pointer
// rows: what the next draw redraws (regional). changed: what the next frame changes against the last drawn one, when every cause is
// known (changedKnown); a whole draw for any other reason records "everything changed".
struct OmniRegion { bool active = false, topBar = false, bottomBar = false, fadeTop = false, fadeBottom = false, pointer = false, changedKnown = false; std::vector<uint8_t> rows, changed; };
static OmniRegion omniRegion;                          // set by tick() for the next draw() only
// Bars, their soft edges over the page and the page rows between them, as omniDrawBars() draws them (bars shown or hidden).
struct OmniZones { bool bars = false; int topEnd = 0, fadeTop0 = 0, fadeTopRows = 0, bottom0 = 0, fadeBot0 = 0, fadeBotRows = 0; };
static OmniZones omniZones()
{
    OmniZones z;
    const float shown = omniAutoHideActive() ? omniChromeShown : 1.f;
    if (shown < 1) return z;
    z.bars = true;
    z.topEnd = std::min(physical(top), canvas->h);
    z.fadeTop0 = int(top * shown * displayScale + 0.5); z.fadeTopRows = physical(5);
    const int y0 = std::min(physical(height - bottom), canvas->h), rows = canvas->h - y0;
    const int visible = std::min(rows, int(bottom * shown * displayScale + 0.5));
    z.bottom0 = canvas->h - visible;
    z.fadeBot0 = canvas->h - visible - physical(4); z.fadeBotRows = physical(4);
    return z;
}
static SDL_Rect omniPointerRect()
{
    SDL_Surface* sprite = omniPointerSprite();
    if (!sprite) return { 0, 0, 0, 0 };
    const int m = int(omniPointerMargin * displayScale + 0.5);
    return { int(pointerX * displayScale + 0.5) - m, int(pointerY * displayScale + 0.5) - m, sprite->w, sprite->h };
}
// Layout the frame was drawn with: a regional draw needs the same.
static uint64_t omniFrameKey()
{
    const OmniZones z = omniZones();
    return uint64_t(uint32_t(int(omniPageTopF() * displayScale + 0.5))) | (uint64_t(z.bars) << 20) | (uint64_t(omniAutoHideActive()) << 21)
        | (uint64_t(pageFullscreen) << 22) | (uint64_t(uint32_t(omniThemeIndex) & 255) << 24) | (uint64_t(uint32_t(renderPageHeight)) << 32)
        | (uint64_t(uint32_t(canvas ? canvas->h : 0) & 0xffff) << 48);
}
// After each draw(): which rows this frame changed against the previous one (everything unless tick() planned it with every
// cause known). A whole draw planned that way (e.g. because the canvas was too old) still records only the rows that changed.
static void omniFrameRecord(bool regional)
{
    (void)regional;
    OmniFrameRows& f = omniFrames[++omniFrameNo % 4];
    f.frame = omniFrameNo;
    f.key = omniFrameKey();
    f.full = !omniRegion.changedKnown || int(omniRegion.changed.size()) != (canvas ? canvas->h : 0);
    if (OmniMedia::Hw::holePunchActive()) { omniHoleFrames = 3; f.full = true; }
    else if (omniHoleFrames > 0) { --omniHoleFrames; f.full = true; }
    if (!f.full) f.rows = omniRegion.changed;
    omniRegion.changedKnown = false;
    omniCanvasHolds = omniFrameNo;
    omniPointerLast = omniPointerRect();
    omniPageDamage = OmniRows();
}
// Under omniPresentLock, after the canvas became the screen (exchange) or was copied there: the tiler's damage rows.
static void omniHandOffRecord(bool exchanged)
{
    const uint32_t f = omniCanvasHolds;
    bool full = !omniPerfOn(omniPerfS2) || !f || !omniScreenHolds || f <= omniScreenHolds || f - omniScreenHolds > 3 || OmniMedia::Hw::holePunchActive();
    int y0 = canvas->h, y1 = 0;
    for (uint32_t g = omniScreenHolds + 1; !full && g <= f; ++g) {
        const OmniFrameRows& r = omniFrames[g % 4];
        if (r.frame != g || r.full || int(r.rows.size()) != canvas->h) { full = true; break; }
        for (int y = 0; y < canvas->h; ++y) if (r.rows[y]) { y0 = std::min(y0, y); y1 = std::max(y1, y + 1); }
    }
    omniPresentDamaged = !full;
    if (!full) { if (y1 <= y0) { y0 = 0; y1 = 1; } omniPresentDamage = { 0, y0, canvas->w, y1 - y0 }; }
    // While a video uses the plane the presenter rewrites that buffer (re-flips): its frame is unknown afterwards.
    const uint32_t shown = OmniMedia::Hw::holePunchActive() ? 0 : f;
    if (exchanged) omniCanvasHolds = omniScreenHolds;
    omniScreenHolds = shown;
    omniCanvasPending = false;
}
// Decides how tick() draws: 0 the whole frame (as before), 1 only omniRegion's rows (OMNI_PERF_A_S4), 2 nothing (no visible change).
static int omniPlanDraw(unsigned reasons)
{
    omniRegion.active = omniRegion.topBar = omniRegion.bottomBar = omniRegion.fadeTop = omniRegion.fadeBottom = omniRegion.pointer = false;
    omniRegion.changedKnown = false;
    if (!omniPerfOn(omniPerfS4) || !canvas || canvas == screen) return 0;
    // Only causes whose effect is known: page pixels, the pointer, the loading spinner (top bar), the 1 s refresh (bars).
    // (The refresh is known only with S3: without the shell signature it is the only thing that shows a status change.)
    const unsigned known = omniDrPagePartial | omniDrPageFull | omniDrSafety | omniDrSpinner | omniDrAxis | omniDrStick
        | (omniPerfOn(omniPerfS3) ? omniDrRefresh : 0u);
    if (reasons & ~known) return 0;
    if (!omniSmoothDrawOn() || canvas->format->format != SDL_PIXELFORMAT_ABGR8888 || renderWidth != canvas->w || pageFullscreen
        || OmniMedia::Hw::holePunchActive() || omniHoleFrames > 0 || editing || settingsOpen || omniStatsPanel.enabled || status != "Ready"
        || !active() || !active()->message.empty() || omniModalCurrent() || !omniPointerSprite())
        return 0;
    if (omniAutoHideActive() && omniChromeShown != 0.f && omniChromeShown != 1.f) return 0;   // bars sliding
    for (auto& layer : omniOverlayLayers()) if (layer.open()) return 0;
    const int h = canvas->h;
    const uint64_t key = omniFrameKey();
    if (!omniFrameNo || omniFrames[omniFrameNo % 4].frame != omniFrameNo || omniFrames[omniFrameNo % 4].key != key) return 0;   // layout changed
    const OmniZones z = omniZones();
    std::vector<uint8_t>& R = omniRegion.changed;
    R.assign(size_t(h), 0);
    auto mark = [h](int a, int b) { a = std::max(a, 0); b = std::min(b, h); if (b > a) memset(R.data() + a, 1, size_t(b - a)); };
    // What changed since the last drawn frame.
    bool changed = false;
    const int pageY = int(omniPageTopF() * displayScale + 0.5);
    if (omniPageDamage.any()) {
        int a = pageY + omniPageDamage.y0, b = pageY + omniPageDamage.y1;
        if (z.bars) { a = std::max(a, z.topEnd); b = std::min(b, z.bottom0); }   // rows under opaque bars never show the page
        if (b > a) { mark(a, b); changed = true; }
    }
    if ((reasons & omniDrSpinner) && z.bars) { mark(0, z.topEnd); changed = true; }
    if ((reasons & omniDrRefresh) && z.bars) { mark(0, z.topEnd); mark(z.bottom0, h); changed = true; }
    const SDL_Rect p = omniPointerRect();
    const bool moved = p.x != omniPointerLast.x || p.y != omniPointerLast.y || p.w != omniPointerLast.w || p.h != omniPointerLast.h;
    if (moved) {
        // Over a bar the pointer changes hover rings: the whole frame then.
        auto overBars = [&z](const SDL_Rect& r) { return z.bars && r.h > 0 && (r.y < z.topEnd || r.y + r.h > z.bottom0); };
        if (overBars(p) || overBars(omniPointerLast)) return 0;
        mark(p.y, p.y + p.h); mark(omniPointerLast.y, omniPointerLast.y + omniPointerLast.h);
        changed = true;
    }
    if (!changed) return 2;
    omniRegion.changedKnown = true;   // from here on a whole draw still records only these rows
    // Rows to redraw: these, and those changed since the frame the canvas holds (buffer age).
    omniRegion.rows = R;
    std::vector<uint8_t>& D = omniRegion.rows;
    if (!omniCanvasHolds || omniCanvasHolds > omniFrameNo || omniFrameNo - omniCanvasHolds > 3) return 0;
    for (uint32_t g = omniCanvasHolds + 1; g <= omniFrameNo; ++g) {
        const OmniFrameRows& r = omniFrames[g % 4];
        if (r.frame != g || r.full || r.key != key || int(r.rows.size()) != h) return 0;
        for (int y = 0; y < h; ++y) D[y] |= r.rows[y];
    }
    auto markD = [h](int a, int b) { a = std::max(a, 0); b = std::min(b, h); if (b > a) memset(D.data() + a, 1, size_t(b - a)); };
    auto touches = [h](int a, int b) { a = std::max(a, 0); b = std::min(b, h); for (int y = a; y < b; ++y) if (D[y]) return true; return false; };
    // Close over what overlaps: a bar is redrawn whole, a soft edge (blended over the page) is re-applied whole, the pointer
    // (blended over everything) is redrawn on rows that are all redrawn.
    for (bool grew = true; grew;) {
        grew = false;
        auto close = [&](int a, int b, bool& flag) { if (b > a && !flag && touches(a, b)) { markD(a, b); flag = true; grew = true; } };
        if (z.bars) {
            close(0, z.topEnd, omniRegion.topBar);
            close(z.fadeTop0, z.fadeTop0 + z.fadeTopRows, omniRegion.fadeTop);
            close(z.bottom0, h, omniRegion.bottomBar);
            close(z.fadeBot0, z.fadeBot0 + z.fadeBotRows, omniRegion.fadeBottom);
        }
        close(p.y, p.y + p.h, omniRegion.pointer);
    }
    unsigned count = 0;
    for (int y = 0; y < h; ++y) count += D[y];
    if (count >= unsigned(h)) return 0;   // every row: the whole draw is the same work
    omniCensus.regionalRows += count;
    omniRegion.active = true;
    return 1;
}
// OMNI_PERF_A_S3: what the bars, toast and panels show, hashed once per tick (a few microseconds). A change draws at once;
// the refresh that used to run every 100 ms for state changes that set no flag runs once a second.
static uint64_t omniShellSignature()
{
    uint64_t h = 1469598103934665603ull;
    auto mix = [&h](const void* p, size_t n) { const uint8_t* b = static_cast<const uint8_t*>(p); for (size_t i = 0; i < n; ++i) { h ^= b[i]; h *= 1099511628211ull; } };
    auto text = [&mix](const std::string& s) { const size_t n = s.size(); mix(&n, sizeof n); mix(s.data(), n); };
    auto flag = [&mix](bool v) { const uint8_t b = v; mix(&b, 1); };
    text(status); flag(statusUntil != 0); text(address);
    const size_t count = tabs.size(); mix(&count, sizeof count); mix(&selected, sizeof selected);
    for (auto& t : tabs) { text(t->title); text(t->url); text(t->message); flag(t->loading); flag(t->crashed); flag(t->omniPrivate); }
    flag(editing); flag(pageEditing); flag(settingsOpen); flag(pageFullscreen); flag(SDL_GetTicks() < fullscreenHintUntil);
    mix(&omniThemeIndex, sizeof omniThemeIndex); flag(playStationIcons); flag(omniStatsPanel.enabled); flag(omniAutoHide);
    flag(omniBlockerEnabled()); flag(omniBlockerFailed());
    if (Tab* t = active()) { flag(WKPageCanGoBack(t->page)); flag(WKPageCanGoForward(t->page)); }
    for (auto& layer : omniOverlayLayers()) flag(layer.open());
    flag(omniModalCurrent() != nullptr);
    return h;
}
// OMNI_PERF_A_S8: the free 1/60 s timer beats against the 59.94 Hz display (two ticks share one vblank every ~17 s). The timer
// runs at the display's period and, when its phase has drifted more than 2 ms from 1 ms after the presenter's last flip,
// one tick is moved there (at most every 250 ms, only while the presenter flips).
static WTF::RunLoop::Timer* omniRefreshTimer = nullptr;
static constexpr double omniVblankMs = 1001.0 / 60;
static void omniVblankAlign()
{
    static bool realigning = false;
    static Uint64 lastAlign = 0;
    // ws-a-1b: restarting the refresh timer is opt-in (/data/omni/perf-a-s8-align.flag): a timer that is not re-armed would stop
    // the shell silently. Without the flag the timer only runs at the display's period.
    static const bool alignWanted = access("/data/omni/perf-a-s8-align.flag", F_OK) == 0;
    if (!omniRefreshTimer || !omniPerfOn(omniPerfS8) || !alignWanted) return;
    if (realigning) { realigning = false; omniRefreshTimer->startRepeating(WTF::Seconds(omniVblankMs / 1000)); return; }
    const Uint64 now = SDL_GetPerformanceCounter(), v = omniVblankAt.load(std::memory_order_relaxed);
    const double f = double(SDL_GetPerformanceFrequency());
    if (!v || now < v) return;
    const double since = 1000.0 * double(now - v) / f;
    if (since > 100 || (lastAlign && 1000.0 * double(now - lastAlign) / f < 250)) return;
    const double phase = std::fmod(since, omniVblankMs), target = 1.0;
    double err = phase - target;
    if (err > omniVblankMs / 2) err -= omniVblankMs; else if (err <= -omniVblankMs / 2) err += omniVblankMs;
    if (std::fabs(err) <= 2.0) return;
    double delay = omniVblankMs - phase + target;
    if (delay < 4) delay += omniVblankMs;
    lastAlign = now; realigning = true; ++omniCensus.realigns;
    omniRefreshTimer->startOneShot(WTF::Seconds(delay / 1000));
}
// OMNI_PERF_A_COUNTER: once per 5 s, through the engine's log writer thread.
static void omniCensusTick()
{
    static unsigned lines = 0;
    const uint32_t now = SDL_GetTicks();
    ++omniCensus.ticks;
    if (!omniCensus.since) { omniCensus.since = now; return; }
    if (now - omniCensus.since < 5000) return;
    OmniDrawCensus& c = omniCensus;
    if (omniReleaseDiagnostics() && lines < 1500 && (c.draws || c.paints || c.deferred || c.reused)) {
        ++lines;
        const unsigned* r = c.reason;
        char line[640];
        snprintf(line, sizeof line, "draw reasons (5 s): ticks %u draws %u (full %u, regional %u avg %u rows) nothing %u reused %u idle %u videoSkip %u busyKept %u"
            " | first %u page %u partial %u safety %u video %u refresh %u busy %u spinner %u style %u input %u axis %u stick %u webkit %u feature %u signature %u"
            " | WKPagePaint %u avg %.2f max %.1f ms (>20 %u, >100 %u, >400 %u) deferred %u slow %u watchdog %u | safety %u changed %u | forced %u realign %u",
            c.ticks, c.draws, c.full, c.regional, c.regional ? c.regionalRows / c.regional : 0, c.nothing, c.reused, c.idle, c.videoSkips, c.busyKept,
            r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], r[11], r[12], r[13], r[14],
            c.paints, c.paints ? c.paintMs / c.paints : 0.0, c.paintMax, c.over20, c.over100, c.over400, c.deferred, c.slowArmed, c.watchdog, c.safety, c.safetyChanged, c.forced, c.realigns);
        log(line);
    }
    // ws-a-1b: a heartbeat in every mode (once a minute, at most 60 lines), so an idle shell can be told from a stopped one.
    static uint32_t beatAt = 0; static unsigned beats = 0, beatTicks = 0, beatDraws = 0, beatPaints = 0, beatBlocked = 0;
    beatTicks += c.ticks; beatDraws += c.draws; beatPaints += c.paints; beatBlocked += c.over100;
    if (!beatAt) beatAt = now;
    if (now - beatAt >= 60000) {
        if (beats++ < 60) { char line[200]; snprintf(line, sizeof line, "shell alive (60 s): ticks %u draws %u page paints %u (blocked %u)", beatTicks, beatDraws, beatPaints, beatBlocked); log(line); }
        beatAt = now; beatTicks = beatDraws = beatPaints = beatBlocked = 0;
    }
    omniCensus = OmniDrawCensus();
    omniCensus.since = now;
}

// OMNI_SHELL_PRESENT_V1 -------------------------------------------------------------------
static void omniPresenterMain()
''')

# ---------------------------------------------------------------- 8. presenter: damage rect (S2), vblank stamps (S8)
rep('''                reflipResult = SDL_UpdateWindowSurface(window);   // tile + flip + wait for vblank, as for a canvas
                OmniMedia::Hw::holePunchVblank(!reflipResult);
''', '''                reflipResult = SDL_UpdateWindowSurface(window);   // tile + flip + wait for vblank, as for a canvas
                OmniMedia::Hw::holePunchVblank(!reflipResult);
                if (!reflipResult) omniVblankAt.store(SDL_GetPerformanceCounter(), std::memory_order_relaxed); // OMNI_PERF_A_S8
''')
rep('''        if (omniPresentStop) return;
        lock.unlock();
        // OMNI_HOLEPUNCH_V8_CADENCE: the video picture due at the vblank this flip reaches, as of now
        OmniMedia::Hw::holePunchBeforeFlip(static_cast<uint8_t*>(screen->pixels), screen->pitch, screen->w, screen->h);
        const auto started = SDL_GetPerformanceCounter();
        OmniMedia::Hw::diagnosticTrace(22,0);
        const int result = SDL_UpdateWindowSurface(window);   // tile + flip + wait for vblank
        OmniMedia::Hw::holePunchVblank(!result);
''', '''        if (omniPresentStop) return;
        const SDL_Rect damage = omniPresentDamage; const bool damaged = omniPresentDamaged; // OMNI_PERF_A_S2: this canvas's changed rows
        lock.unlock();
        // OMNI_HOLEPUNCH_V8_CADENCE: the video picture due at the vblank this flip reaches, as of now
        OmniMedia::Hw::holePunchBeforeFlip(static_cast<uint8_t*>(screen->pixels), screen->pitch, screen->w, screen->h);
        const auto started = SDL_GetPerformanceCounter();
        OmniMedia::Hw::diagnosticTrace(22,0);
        const int result = damaged ? SDL_UpdateWindowSurfaceRects(window, &damage, 1) : SDL_UpdateWindowSurface(window);   // tile (changed rows) + flip + wait for vblank
        OmniMedia::Hw::holePunchVblank(!result);
        if (!result) omniVblankAt.store(SDL_GetPerformanceCounter(), std::memory_order_relaxed); // OMNI_PERF_A_S8
''')

# ---------------------------------------------------------------- 9. hand-off: keep a canvas the presenter was too busy for (S7); bookkeeping (S2/S4)
rep('''    if (omniPresentBusy) {
        // Still flipping the previous frame: draw and present again on the next tick.
        ++omniPresentSkips;
        omniShellDirty = true;
        return;
    }''', '''    if (omniPresentBusy) {
        ++omniPresentSkips;
        // OMNI_PERF_A_S7: still flipping the previous frame. The finished canvas is handed off on the next tick unless something
        // changes meanwhile (was: drawn again from scratch, 30 % of 52 ms draws with a translucent control bar).
        if (omniPerfOn(omniPerfS7)) { omniCanvasPending = true; ++omniCensus.busyKept; return; }
        omniMarkDirty(omniDrBusy);   // as before: draw and present again on the next tick
        return;
    }''')
rep('''    OmniMedia::Hw::diagnosticTrace(106,exchange,canvas->w,canvas->h);
    if (exchange)
        std::swap(canvas->pixels, screen->pixels);
    else if (canvas->pitch == screen->pitch)
        memcpy(screen->pixels, canvas->pixels, size_t(canvas->pitch) * canvas->h);
    else
        for (int row = 0; row < canvas->h; ++row)
            memcpy(static_cast<uint8_t*>(screen->pixels) + size_t(row) * screen->pitch,
                static_cast<const uint8_t*>(canvas->pixels) + size_t(row) * canvas->pitch, size_t(canvas->w) * 4);
''', '''    OmniMedia::Hw::diagnosticTrace(106,exchange,canvas->w,canvas->h);
    if (exchange)
        std::swap(canvas->pixels, screen->pixels);
    else if (canvas->pitch == screen->pitch)
        memcpy(screen->pixels, canvas->pixels, size_t(canvas->pitch) * canvas->h);
    else
        for (int row = 0; row < canvas->h; ++row)
            memcpy(static_cast<uint8_t*>(screen->pixels) + size_t(row) * screen->pitch,
                static_cast<const uint8_t*>(canvas->pixels) + size_t(row) * canvas->pitch, size_t(canvas->w) * 4);
    omniHandOffRecord(exchange); // OMNI_PERF_A_S2/S4: rows the tiler must take; which frame each buffer now holds
''')

# ---------------------------------------------------------------- 10. page buffer -> canvas (S5 one pass, S6 vector blend, S4 row ranges)
rep('''// half-size image (cleared the same way the caller clears the full buffer) and each pixel is doubled.
static std::vector<uint32_t> omniPageSmall;
''', '''// half-size image (cleared the same way the caller clears the full buffer) and each pixel is doubled.
// (omniPageSmall is declared near the top: OMNI_PERF_A_S5)
''')
rep('''static void omniPageToCanvas(const SDL_Rect& dst, SDL_Color bg)
{
    const Uint32 bgPixel = SDL_MapRGBA(canvas->format, bg.r, bg.g, bg.b, bg.a);
    const int y0 = std::max(0, dst.y), y1 = std::min(canvas->h, dst.y + renderPageHeight);
    // around the page: background (bars and dialogs draw over it next)
    if (y0 > 0) { SDL_Rect r { 0, 0, canvas->w, y0 }; SDL_FillRect(canvas, &r, bgPixel); }
    if (y1 < canvas->h) { SDL_Rect r { 0, y1, canvas->w, canvas->h - y1 }; SDL_FillRect(canvas, &r, bgPixel); }
    const bool fast = omniSmoothDrawOn() && dst.x == 0 && canvas->format->format == SDL_PIXELFORMAT_ABGR8888 && renderWidth <= canvas->w;
    if (!fast) {
        SDL_Rect r { 0, y0, canvas->w, y1 - y0 }; SDL_FillRect(canvas, &r, bgPixel);
        SDL_Rect d = dst; SDL_BlitSurface(pageSurface, nullptr, canvas, &d);
        return;
    }
    if (renderWidth < canvas->w) { SDL_Rect r { renderWidth, y0, canvas->w - renderWidth, y1 - y0 }; SDL_FillRect(canvas, &r, bgPixel); }
    const uint32_t* src = reinterpret_cast<const uint32_t*>(pixels.data());
    for (int y = y0; y < y1; ++y) {
        uint32_t* d = reinterpret_cast<uint32_t*>(static_cast<uint8_t*>(canvas->pixels) + size_t(y) * canvas->pitch);
        if (omniCopyRowOpaque(d, src + size_t(y - dst.y) * renderWidth, renderWidth)) continue;
        SDL_Rect fr { 0, y, renderWidth, 1 }; SDL_FillRect(canvas, &fr, bgPixel);   // a row with transparency: as before
        SDL_Rect sr { 0, y - dst.y, renderWidth, 1 }, dr { 0, y, 0, 0 }; SDL_BlitSurface(pageSurface, &sr, canvas, &dr);
    }
}
''', ROWOVER + '''// Canvas rows [a, b) from the page buffer (the whole frame: 0, canvas->h). OMNI_PERF_A_S5: from the half-resolution page when the
// 4K buffer lags it (doubled, swapped and copied in one pass; odd rows copy the row above). OMNI_PERF_A_S6: rows with transparency
// (a hole-punched video under the page) are blended 8 pixels at a time with SDL's arithmetic instead of SDL fill + blit per row.
static void omniPageToCanvasRows(const SDL_Rect& dst, SDL_Color bg, int a, int b)
{
    const Uint32 bgPixel = SDL_MapRGBA(canvas->format, bg.r, bg.g, bg.b, bg.a);
    a = std::max(a, 0); b = std::min(b, canvas->h);
    if (b <= a) return;
    const int y0 = std::max(0, dst.y), y1 = std::min(canvas->h, dst.y + renderPageHeight);
    // around the page: background (bars and dialogs draw over it next)
    if (y0 > a) { SDL_Rect r { 0, a, canvas->w, std::min(y0, b) - a }; if (r.h > 0) SDL_FillRect(canvas, &r, bgPixel); }
    if (y1 < b) { const int s = std::max(y1, a); SDL_Rect r { 0, s, canvas->w, b - s }; if (r.h > 0) SDL_FillRect(canvas, &r, bgPixel); }
    const int ra = std::max(a, y0), rb = std::min(b, y1);
    if (rb <= ra) return;
    const bool fast = omniSmoothDrawOn() && dst.x == 0 && canvas->format->format == SDL_PIXELFORMAT_ABGR8888 && renderWidth <= canvas->w;
    if (!fast) {   // as before (the whole page; a regional draw is never planned without the fast path)
        omniEnsurePixels();
        SDL_Rect r { 0, y0, canvas->w, y1 - y0 }; SDL_FillRect(canvas, &r, bgPixel);
        SDL_Rect d = dst; SDL_BlitSurface(pageSurface, nullptr, canvas, &d);
        return;
    }
    if (renderWidth < canvas->w) { SDL_Rect r { renderWidth, ra, canvas->w - renderWidth, rb - ra }; SDL_FillRect(canvas, &r, bgPixel); }
    auto row = [](int y) { return reinterpret_cast<uint32_t*>(static_cast<uint8_t*>(canvas->pixels) + size_t(y) * canvas->pitch); };
    const int sw = (renderWidth + 1) / 2;
    if (omniPixelsStale && omniPageSmall.size() >= size_t(sw) * ((renderPageHeight + 1) / 2)) {   // OMNI_PERF_A_S5
        int previous = -1;
        for (int y = ra; y < rb; ++y) {
            const int source = (y - dst.y) / 2;
            uint32_t* d = row(y);
            if (source == previous) { memcpy(d, row(y - 1), size_t(renderWidth) * 4); continue; }
            previous = source;
            omniRowOver<true>(d, omniPageSmall.data() + size_t(source) * sw, renderWidth, bgPixel);
        }
        return;
    }
    omniEnsurePixels();
    const bool blend = omniPerfOn(omniPerfS6);
    const uint32_t* src = reinterpret_cast<const uint32_t*>(pixels.data());
    for (int y = ra; y < rb; ++y) {
        uint32_t* d = row(y);
        if (blend) { omniRowOver<false>(d, src + size_t(y - dst.y) * renderWidth, renderWidth, bgPixel); continue; }   // OMNI_PERF_A_S6
        if (omniCopyRowOpaque(d, src + size_t(y - dst.y) * renderWidth, renderWidth)) continue;
        SDL_Rect fr { 0, y, renderWidth, 1 }; SDL_FillRect(canvas, &fr, bgPixel);   // a row with transparency: as before
        SDL_Rect sr { 0, y - dst.y, renderWidth, 1 }, dr { 0, y, 0, 0 }; SDL_BlitSurface(pageSurface, &sr, canvas, &dr);
    }
}
static void omniPageToCanvas(const SDL_Rect& dst, SDL_Color bg) { omniPageToCanvasRows(dst, bg, 0, canvas->h); }
// OMNI_PERF_A_S5: the 4K page buffer for its readers (video compose, preview capture): every row doubled from the half-size page.
static void omniEnsurePixels()
{
    if (!omniPixelsStale) return;
    omniPixelsStale = false;
    const int sw = (renderWidth + 1) / 2;
    if (omniPageSmall.size() < size_t(sw) * ((renderPageHeight + 1) / 2) || pixels.size() < size_t(renderWidth) * renderPageHeight * 4) return;
    uint32_t* dst = reinterpret_cast<uint32_t*>(pixels.data());
    for (int y = 0; y < renderPageHeight; ++y) {
        uint32_t* d = dst + size_t(y) * renderWidth;
        if (y & 1) { memcpy(d, d - renderWidth, size_t(renderWidth) * 4); continue; }
        omniDoubleRow(d, omniPageSmall.data() + size_t(y / 2) * sw, renderWidth);
    }
}
// OMNI_PERF_A_COUNTER / S1: every WKPagePaint timed. One that blocks (>= 100 ms: the web process has not answered for its backing
// store) stops page paints on that tab for 500 ms, doubling up to 2 s while it keeps blocking; a fast one resets that.
static void omniPagePaintTimed(unsigned char* buffer, WKSize size, WKRect rect)
{
    Tab* tab = active();
    const Uint64 t0 = SDL_GetPerformanceCounter();
    WKPagePaint(tab->page, buffer, size, rect);
    const double ms = omniMsSince(t0);
    OmniDrawCensus& c = omniCensus;
    ++c.paints; c.paintMs += ms; c.paintMax = std::max(c.paintMax, ms);
    if (ms > 20) ++c.over20;
    if (ms > 100) ++c.over100;
    if (ms > 400) ++c.over400;
    if (!omniPerfOn(omniPerfS1)) return;
    if (ms >= 100) {
        static unsigned notes = 0;
        tab->omniSlowBackoff = tab->omniSlowBackoff ? std::min<uint32_t>(tab->omniSlowBackoff * 2, 2000) : 500;
        tab->omniSlowUntil = SDL_GetTicks() + tab->omniSlowBackoff;
        ++c.slowArmed;
        if (notes++ < 30) { char line[160]; snprintf(line, sizeof line, "page paint blocked %.0f ms: no page paint on this tab for %u ms", ms, tab->omniSlowBackoff); log(line); }
    } else if (ms < 20) tab->omniSlowBackoff = 0;
}
''')

# ---------------------------------------------------------------- 11. partial and full page paints: timed, S5 (no 4K doubling), damage rows
rep('''    if (!omniSmoothDrawOn()) return -1;
    rows = std::clamp(rows, 0, renderPageHeight);
    const bool half = omniPageScale < 1;''', '''    if (!omniSmoothDrawOn()) return -1;
    if (omniPixelsStale && OmniMedia::Hw::holePunchActive()) return -1;   // OMNI_PERF_A_S5: the compose needs the whole 4K buffer
    rows = std::clamp(rows, 0, renderPageHeight);
    const bool half = omniPageScale < 1;''')
rep('''    WKPagePaint(active()->page, reinterpret_cast<unsigned char*>(buf), WKSizeMake(bw, bh), WKRectMake(x0, y0, w, y1 - y0));
    bool same = true;
    for (int y = y0; y < y1 && same; ++y) same = !memcmp(saved.data() + size_t(y - y0) * w, buf + size_t(y) * bw + x0, size_t(w) * 4);
    if (same) return 0;
    if (half) {   // the doubled rows of that rect, as omniPaintPage does for all of them''', '''    omniPagePaintTimed(reinterpret_cast<unsigned char*>(buf), WKSizeMake(bw, bh), WKRectMake(x0, y0, w, y1 - y0)); // OMNI_PERF_A_COUNTER
    bool same = true;
    for (int y = y0; y < y1 && same; ++y) same = !memcmp(saved.data() + size_t(y - y0) * w, buf + size_t(y) * bw + x0, size_t(w) * 4);
    if (same) return 0;
    if (half) omniPageDamage.add(2 * y0, std::min(rows, 2 * y1)); else omniPageDamage.add(y0, y1); // OMNI_PERF_A_S4
    if (half && !omniPixelsStale) {   // the doubled rows of that rect, as omniPaintPage does for all of them (OMNI_PERF_A_S5: not while the canvas reads the half-size page)''')
rep('''    rows = std::clamp(rows, 0, renderPageHeight);
    if (omniPageScale >= 1) {
        WKPagePaint(active()->page, pixels.data(), WKSizeMake(renderWidth, renderPageHeight), WKRectMake(0, 0, renderWidth, rows));
        return;
    }
    const int sw = (renderWidth + 1) / 2, sh = (renderPageHeight + 1) / 2, sr = (rows + 1) / 2;
    omniPageSmall.resize(size_t(sw) * sh);
    std::fill(omniPageSmall.begin(), omniPageSmall.begin() + size_t(sw) * sr, OmniMedia::Hw::holePunchActive() ? 0u : 0xffffffffu);
    WKPagePaint(active()->page, reinterpret_cast<unsigned char*>(omniPageSmall.data()), WKSizeMake(sw, sh), WKRectMake(0, 0, sw, sr));
    uint32_t* dst = reinterpret_cast<uint32_t*>(pixels.data());''', '''    rows = std::clamp(rows, 0, renderPageHeight);
    omniPageDamage.add(0, renderPageHeight); // OMNI_PERF_A_S4
    if (omniPageScale >= 1) {
        omniPixelsStale = false;
        omniPagePaintTimed(pixels.data(), WKSizeMake(renderWidth, renderPageHeight), WKRectMake(0, 0, renderWidth, rows)); // OMNI_PERF_A_COUNTER
        return;
    }
    const int sw = (renderWidth + 1) / 2, sh = (renderPageHeight + 1) / 2, sr = (rows + 1) / 2;
    omniPageSmall.resize(size_t(sw) * sh);
    std::fill(omniPageSmall.begin(), omniPageSmall.begin() + size_t(sw) * sr, OmniMedia::Hw::holePunchActive() ? 0u : 0xffffffffu);
    omniPagePaintTimed(reinterpret_cast<unsigned char*>(omniPageSmall.data()), WKSizeMake(sw, sh), WKRectMake(0, 0, sw, sr)); // OMNI_PERF_A_COUNTER
    // OMNI_PERF_A_S5: no 4K copy (33 MB written per paint); the canvas reads the half-size page. Video under the page needs it.
    if (omniPerfOn(omniPerfS5) && omniSmoothDrawOn() && !OmniMedia::Hw::holePunchActive()) { omniPixelsStale = true; return; }
    if (omniPixelsStale) { omniEnsurePixels(); return; }   // every row, from the page just painted
    uint32_t* dst = reinterpret_cast<uint32_t*>(pixels.data());''')

# ---------------------------------------------------------------- 12. draw(): regional path (S4), 4K buffer for the compose (S5), frame record
rep('''    auto omniLap = [&omniT](double& acc) { const Uint64 now = SDL_GetPerformanceCounter(); acc += 1000.0 * double(now - omniT) / double(SDL_GetPerformanceFrequency()); omniT = now; };
    if (!pageFullscreen) {
''', '''    auto omniLap = [&omniT](double& acc) { const Uint64 now = SDL_GetPerformanceCounter(); acc += 1000.0 * double(now - omniT) / double(SDL_GetPerformanceFrequency()); omniT = now; };
    if (OmniMedia::Hw::holePunchActive()) omniEnsurePixels(); // OMNI_PERF_A_S5: the compose reads the 4K page buffer
    // OMNI_PERF_A_S4: tick() planned which rows changed (page rows, the pointer, the spinner's top bar): only those are drawn, in
    // the same order and with the same code as the whole frame (page, bars, their soft edges, toast, pointer).
    const bool omniRegional = omniRegion.active && !pageFullscreen;
    omniRegion.active = false;
    if (omniRegional) {
        const SDL_Rect destinationRect {0, int(omniPageTopF() * displayScale + 0.5), renderWidth, renderPageHeight};
        const std::vector<uint8_t>& rows = omniRegion.rows;
        for (int y = 0; y < canvas->h;) {
            if (!rows[y]) { ++y; continue; }
            int end = y;
            while (end < canvas->h && rows[end]) ++end;
            omniPageToCanvasRows(destinationRect, T.bg, y, end);
            y = end;
        }
        omniLap(omniSplit.blit);
        omniLap(omniSplit.compose);
        const OmniZones z = omniZones();
        if (omniRegion.topBar) omniDrawTopBar();
        if (omniRegion.fadeTop) omniFadeRows(z.fadeTop0, z.fadeTopRows, 70, 0);
        if (omniRegion.bottomBar) omniDrawHintBar();
        if (omniRegion.fadeBottom) omniFadeRows(z.fadeBot0, z.fadeBotRows, 0, 45);
        omniDrawToast();   // shows nothing (planned only while the status is "Ready"); keeps its state as in every draw
        if (omniRegion.pointer) omniDrawPointer();
    } else if (!pageFullscreen) {
''')
rep('''    if(omniStatsPanel.enabled && omniStatsSurface) {
        SDL_Rect where {physical(12),physical(12),0,0};
        SDL_BlitSurface(omniStatsSurface,nullptr,canvas,&where);
    }
    omniOverlayDraw(); // OMNI_DIALOGS_V1: modals, menus and overlays above the shell
    omniDrawPointer(); // OMNI_STYLE_V1: bigger pointer with a soft shadow
''', '''    if (!omniRegional) { // OMNI_PERF_A_S4: a regional draw is planned only with no panel, overlay or modal open (the pointer is drawn above)
    if(omniStatsPanel.enabled && omniStatsSurface) {
        SDL_Rect where {physical(12),physical(12),0,0};
        SDL_BlitSurface(omniStatsSurface,nullptr,canvas,&where);
    }
    omniOverlayDraw(); // OMNI_DIALOGS_V1: modals, menus and overlays above the shell
    omniDrawPointer(); // OMNI_STYLE_V1: bigger pointer with a soft shadow
    }
''')
rep('''        OmniLocalScope traceScope(21);
        unlink("/data/omni/capture-preview.flag");''', '''        OmniLocalScope traceScope(21);
        omniEnsurePixels(); // OMNI_PERF_A_S5: the page preview is the 4K page buffer
        unlink("/data/omni/capture-preview.flag");''')
rep('''    omniLap(omniSplit.chrome);
    omniPresentFrame(); // OMNI_SHELL_PRESENT_V1
''', '''    omniLap(omniSplit.chrome);
    omniFrameRecord(omniRegional); // OMNI_PERF_A_S4/S2: the rows this frame changed
    omniPresentFrame(); // OMNI_SHELL_PRESENT_V1
''')

# ---------------------------------------------------------------- 13. tick(): reason phases
rep('''    OmniMedia::Hw::holePunchShellPhase(1);
    const auto frameStarted = SDL_GetPerformanceCounter();
''', '''    OmniMedia::Hw::holePunchShellPhase(1);
    const auto frameStarted = SDL_GetPerformanceCounter();
    struct OmniDirtyPhaseReset { ~OmniDirtyPhaseReset() { omniDirtyPhase = omniDrWebKit; } } omniDirtyPhaseReset; // OMNI_PERF_A_COUNTER: outside tick: WebKit
    omniDirtyPhase = omniDrFeature;
    omniVblankAlign(); // OMNI_PERF_A_S8
    omniCensusTick(); // OMNI_PERF_A_COUNTER
''')
rep('''    while (SDL_PollEvent(&event)) {
        omniShellDirty = true; // OMNI_SHELL_DRAW_V1
''', '''    while (SDL_PollEvent(&event)) {
        // OMNI_PERF_A_COUNTER: stick motion by itself changes nothing drawn (the stick tick moves the pointer, WebKit reports scrolling)
        omniDirtyPhase = event.type == SDL_CONTROLLERAXISMOTION && event.caxis.axis != SDL_CONTROLLER_AXIS_TRIGGERLEFT
            && event.caxis.axis != SDL_CONTROLLER_AXIS_TRIGGERRIGHT ? omniDrAxis : omniDrInput;
        omniShellDirty = true; // OMNI_SHELL_DRAW_V1
''')
rep('''        omniSavedTriggers.contextChanged(omniSavedContext());
    }
''', '''        omniSavedTriggers.contextChanged(omniSavedContext());
    }
    omniDirtyPhase = omniDrInput; // OMNI_PERF_A_COUNTER
''')
rep('''    if (controller && !editing) {
        omniFxStickTick(); // OMNI_FEATURES_V1: acceleration, link snapping, right stick both axes (was 16 px per pass)
''', '''    if (controller && !editing) {
        omniDirtyPhase = omniDrStick; // OMNI_PERF_A_COUNTER: pointer motion (OMNI_PERF_A_S4 redraws its rows), right-stick scrolling
        omniFxStickTick(); // OMNI_FEATURES_V1: acceleration, link snapping, right stick both axes (was 16 px per pass)
        omniDirtyPhase = omniDrInput;
''')
rep('''    omniStyleTick(); // OMNI_STYLE_V1: bar slide, progress bar, toast fades
''', '''    omniDirtyPhase = omniDrStyle; // OMNI_PERF_A_COUNTER
    omniStyleTick(); // OMNI_STYLE_V1: bar slide, progress bar, toast fades
    omniDirtyPhase = omniDrFeature;
''')

# ---------------------------------------------------------------- 14. tick(): page paints (S1), draw decision (S3, S7, S4, hook)
rep('''    bool omniPageCopied = false;
    // OMNI_DIRTY_PAINT_V1: only WebKit's reported rect changed (same tab, safety-net time not due): repaint just that.
    if (active() && !active()->crashed && omniViewDirty.any && !omniPageDirty && active() == omniLastActive
        && omniNow - omniLastPageCopy < 500 && !firstFrame) {''', '''    bool omniPageCopied = false;
    // OMNI_PERF_A_S1: WKPagePaint waits up to 500 ms for a backing store the web process has not produced yet (a busy, loading
    // page; a tab shown again after its store was discarded), and the 500 ms safety net called it again and again. Now: a page
    // that is loading is painted when it reports new pixels (a tab switch or a shell cause waits for that, at most 2 s); no
    // safety-net paint while it loads; after a paint that blocked, none on that tab for 0.5-2 s; the safety net (every 2 s,
    // idle pages only) draws only when the page really changed.
    Tab* const omniTab = active();
    const bool omniS1 = omniPerfOn(omniPerfS1);
    const bool omniSlow = omniS1 && omniTab && !firstFrame && int32_t(omniNow - omniTab->omniSlowUntil) < 0;
    // ws-a-1b: a safety-net paint on a page that has just loaded blocked 179/754 ms (its backing store was being replaced): the net
    // runs every 10 s (reports cover every update; `safety N changed N` in the counter says whether it is needed at all).
    const uint32_t omniSafetyMs = omniS1 ? 10000 : 500;
    const bool omniReported = omniViewDirty.any;
    // OMNI_DIRTY_PAINT_V1: only WebKit's reported rect changed (same tab, safety-net time not due): repaint just that.
    if (active() && !active()->crashed && omniViewDirty.any && !omniPageDirty && active() == omniLastActive
        && omniNow - omniLastPageCopy < omniSafetyMs && !firstFrame && !omniSlow) {''')
rep('''            if (partial == 0) ++omniSplit.unchanged; else omniPageCopied = true;
        }
    }
    if (omniViewDirty.any && !omniPageCopied) omniPageDirty = omniPageDirty || omniViewDirty.any;
    if (active() && !active()->crashed
        && (omniPageDirty || active() != omniLastActive || omniNow - omniLastPageCopy >= 500 || firstFrame)) {
        omniViewDirty = OmniViewDirty();''', '''            if (partial == 0) ++omniSplit.unchanged; else { omniPageCopied = true; omniDrawReasons |= omniDrPagePartial; }
        }
    }
    if (omniViewDirty.any && !omniPageCopied) omniPageDirty = omniPageDirty || omniViewDirty.any;
    const bool omniMustPaint = omniPageDirty || active() != omniLastActive || firstFrame;
    const bool omniSafetyOnly = !omniMustPaint && omniNow - omniLastPageCopy >= omniSafetyMs;
    bool omniPaintNow = active() && !active()->crashed && (omniMustPaint || omniSafetyOnly);
    if (omniPaintNow && omniS1 && !firstFrame) { // OMNI_PERF_A_S1
        Tab& t = *omniTab;
        // a loading page, or one without a report since it was shown, gets no safety-net paint (it reports its own changes)
        if (omniSafetyOnly) omniPaintNow = !omniSlow && !t.loading && t.omniShownReported;
        else {
            // Paint when WebKit has reported pixels since the tab was shown (its backing store exists then) and, while it loads,
            // with a report this tick. Watchdog: a page that never reports is painted anyway: after 300 ms for a tab that had a
            // backing store before, 2 s for a new one, then 4 s and 8 s between tries (a try that blocks also arms the backoff).
            bool wait = omniSlow || !t.omniShownReported || (!omniReported && t.loading);
            if (wait && !omniSlow) {
                if (!t.omniWaitSince) t.omniWaitSince = omniNow;
                const uint32_t limit = t.omniNoReportTries ? std::min<uint32_t>(2000u << std::min<uint32_t>(t.omniNoReportTries, 2u), 8000u)
                                                           : (t.omniEverReported ? 300u : 2000u);
                if (omniNow - t.omniWaitSince >= limit) { wait = false; if (!t.omniShownReported) ++t.omniNoReportTries; ++omniCensus.watchdog; }
            }
            if (wait) { ++omniCensus.deferred; omniPaintNow = false; }
            else t.omniWaitSince = 0;
        }
    }
    // the safety net on an idle page: draw only when the page really changed (OMNI_PERF_A_S1)
    const bool omniCompare = omniPaintNow && omniS1 && omniSafetyOnly && omniPageScale < 1 && !OmniMedia::Hw::holePunchActive()
        && omniPageSmall.size() == size_t((renderWidth + 1) / 2) * ((renderPageHeight + 1) / 2);
    static std::vector<uint32_t> omniSafetyBefore;
    if (omniCompare) omniSafetyBefore.assign(omniPageSmall.begin(), omniPageSmall.end());
    if (omniPaintNow) {
        omniViewDirty = OmniViewDirty();''')
rep('''        { const Uint64 t0 = SDL_GetPerformanceCounter(); omniPaintPage(omniPaintRows()); omniSplit.paint += omniMsSince(t0); ++omniSplit.paints; } // OMNI_STYLE_V1 OMNI_FAST_PAGE_V1 OMNI_SMOOTH_DRAW_V1
        OmniMedia::Hw::holePunchShellPhase(1);
    }
    if (OmniMedia::Hw::holePunchPoll()) omniShellDirty = true; // OMNI_HOLEPUNCH_V1: new video picture or rect
    // OMNI_SMOOTH_DRAW_V2: the 100 ms refresh keeps status text and spinners current; a fullscreen video shows neither, and each
    // of those draws composed the whole 4K frame (12-60 ms of main-thread work): once a second there.
    const uint32_t omniRefreshMs = pageFullscreen && OmniMedia::Hw::holePunchActive() ? 1000 : 100;
    if (!firstFrame && !omniPageCopied && !omniShellDirty && omniNow - omniLastDraw < omniRefreshMs)
        return;
    omniShellDirty = false;
    omniLastDraw = omniNow;
''', '''        { const Uint64 t0 = SDL_GetPerformanceCounter(); omniPaintPage(omniPaintRows()); omniSplit.paint += omniMsSince(t0); ++omniSplit.paints; } // OMNI_STYLE_V1 OMNI_FAST_PAGE_V1 OMNI_SMOOTH_DRAW_V1
        OmniMedia::Hw::holePunchShellPhase(1);
        if (omniCompare) {
            ++omniCensus.safety;
            if (memcmp(omniSafetyBefore.data(), omniPageSmall.data(), omniSafetyBefore.size() * 4)) { ++omniCensus.safetyChanged; omniDrawReasons |= omniDrSafety; }
            else { omniPageCopied = false; omniPageDamage = OmniRows(); }   // nothing new: nothing to draw
        } else omniDrawReasons |= omniDrPageFull;
    }
    { const double f = double(SDL_GetPerformanceFrequency()); omniGap.paint = 1000.0 * double(SDL_GetPerformanceCounter() - paintStarted) / f; } // ws-a-1b: page paint time in the gap line also when nothing is drawn
    omniDirtyPhase = omniDrVideo; // OMNI_PERF_A_COUNTER
    if (OmniMedia::Hw::holePunchPoll()) omniShellDirty = true; // OMNI_HOLEPUNCH_V1: new video picture or rect
    omniDirtyPhase = omniDrFeature;
    // OMNI_PERF_A_S3: what the bars, toast and panels show changed: draw now (no flag needed); the rest waits for the refresh.
    if (omniPerfOn(omniPerfS3)) {
        static uint64_t shown = 0;
        const uint64_t now = omniShellSignature();
        if (now != shown) { if (shown) omniMarkDirty(omniDrSignature); shown = now; }
    }
    // OMNI_SMOOTH_DRAW_V2: the 100 ms refresh keeps status text and spinners current; a fullscreen video shows neither, and each
    // of those draws composed the whole 4K frame (12-60 ms of main-thread work): once a second there.
    // OMNI_PERF_A_S3: once a second everywhere (state changes draw at once through the signature; the spinner has its own 30 Hz).
    const uint32_t omniRefreshMs = (pageFullscreen && OmniMedia::Hw::holePunchActive()) || omniPerfOn(omniPerfS3) ? 1000 : 100;
    const bool omniRefreshDue = omniNow - omniLastDraw >= omniRefreshMs;
    if (!firstFrame && !omniPageCopied && !omniShellDirty && !omniRefreshDue) {
        if (omniCanvasPending) { omniPresentFrame(); ++omniCensus.reused; }   // OMNI_PERF_A_S7: the kept canvas, not a new draw
        else ++omniCensus.idle;
        return;
    }
    unsigned omniReasons = omniDrawReasons | (firstFrame ? omniDrFirst : 0u);
    if (!omniPageCopied && !omniShellDirty && !firstFrame) omniReasons |= omniDrRefresh;
    omniDrawReasons = 0;
    omniShellDirty = false;
    omniLastDraw = omniNow;
    omniShellLastDrawReasons = omniReasons;
    // OMNI_PERF_A_HOOK: only the video plane changed and the video service shows that picture by itself.
    if (omniReasons == omniDrVideo && omniShellVideoOnlyDrawSkip && omniShellVideoOnlyDrawSkip()) {
        ++omniCensus.videoSkips;
        if (omniCanvasPending) { omniPresentFrame(); ++omniCensus.reused; }
        return;
    }
    int omniPlan = firstFrame ? 0 : omniPlanDraw(omniReasons); // OMNI_PERF_A_S4
    // ws-a-1b watchdog: whatever the plan says, the whole frame is drawn at least every 2 s while anything asks for a draw
    // (no stale pixel can outlive 2 s, whatever a regional plan or a "nothing changed" decision missed).
    static uint32_t omniLastFullDraw = 0;
    if (omniPlan != 0 && omniNow - omniLastFullDraw >= 2000) { omniPlan = 0; omniRegion.active = false; ++omniCensus.forced; }
    if (omniPlan == 0) omniLastFullDraw = omniNow;
    if (omniPlan == 2) {   // nothing visible changed (stick noise, a refresh with the bars hidden, a page rect under the bars)
        ++omniCensus.nothing;
        omniPageDamage = OmniRows();
        if (omniCanvasPending) { omniPresentFrame(); ++omniCensus.reused; }
        return;
    }
    ++omniCensus.draws; ++(omniPlan == 1 ? omniCensus.regional : omniCensus.full);
    for (int i = 0; i < omniDrCount; ++i) if (omniReasons & (1u << i)) ++omniCensus.reason[i];
''')

# ---------------------------------------------------------------- 15. timer at the display's period (S8); WS-B hook definition
rep('''    WTF::RunLoop::Timer refresh(WTF::Ref { WTF::RunLoop::mainSingleton() }, "OmniBrowser refresh"_s, [] { tick(nullptr); });
    refresh.startRepeating(WTF::Seconds(1.0 / 60)); // OMNI_SHELL_DRAW_V1 (was 30 Hz)
''', '''    WTF::RunLoop::Timer refresh(WTF::Ref { WTF::RunLoop::mainSingleton() }, "OmniBrowser refresh"_s, [] { tick(nullptr); });
    refresh.startRepeating(WTF::Seconds(omniPerfOn(omniPerfS8) ? omniVblankMs / 1000 : 1.0 / 60)); // OMNI_SHELL_DRAW_V1 (was 30 Hz); OMNI_PERF_A_S8: 59.94 Hz
    omniRefreshTimer = &refresh; // OMNI_PERF_A_S8: vblank phase (omniVblankAlign)
''')
rep('''    if (firstFrame) log("first frame: presented");
    firstFrame = false;
}
}
''', '''    if (firstFrame) log("first frame: presented");
    firstFrame = false;
}
}
// OMNI_PERF_A_HOOK / OMNI_PERF_A_COUNTER (declared at the top of this file)
extern "C" { int (*omniShellVideoOnlyDrawSkip)(void) = nullptr; unsigned omniShellLastDrawReasons = 0; }
''')

out = src.replace('\n', '\r\n')
path.write_bytes(out.encode('utf-8'))
print('patched', path)
