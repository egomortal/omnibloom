"""OMNI_C56_VIDEOFIX1: python3 tools/patch_c56_videofix1.py <dl2-candidate-56 entry/OmniBrowser.cpp> <output>
Exact-match replacements (each must match once), CRLF kept."""
import sys
src = open(sys.argv[1], 'rb').read().decode('utf-8')
assert '\r\n' in src
reps = [
# 1. kill switch + helper next to the WS-B predicate
("""static bool omniPresenterOwnsVideo()
{
#if OMNI_PERF_A_WS_B
    return OmniMedia::Hw::holePunchPresenterOwnsVideo();
#else
    return false;
#endif
}
""",
"""static bool omniPresenterOwnsVideo()
{
#if OMNI_PERF_A_WS_B
    return OmniMedia::Hw::holePunchPresenterOwnsVideo();
#else
    return false;
#endif
}
// OMNI_C56_VIDEOFIX1: while a video uses the plane, the shell keeps 54's page-paint and refresh cadence (see tick()).
// Kill switch: /data/omni/c56-videofix-disabled.flag (55/56 behaviour).
static bool omniVideoFixOn()
{
    static const bool on = access("/data/omni/c56-videofix-disabled.flag", F_OK) != 0;
    return on;
}
"""),
# 2. page safety-net paint: 500 ms while a video uses the plane
("""    const uint32_t omniSafetyMs = omniS1 ? 10000 : 500;
""",
"""    // OMNI_C56_VIDEOFIX1: while a video uses the plane WebKit reports little or nothing (fullscreen HDR: no report in 10 minutes),
    // and 54's 500 ms full paint was what brought the page's changes in (the fullscreen media-control bar fading out). With the
    // 10 s net the faded bar stayed in the canvas for the whole run (c55-hdrauto-1: `PQ refused for a translucent area` ~298 per
    // window, 8-bit copies made, re-flips 7.5 ms instead of 2.2 ms: 429 dropped). 500 ms again while the plane is in use; while
    // the presenter owns a fullscreen video the paint draws only if the page really changed (half-size page compared), so the
    // fullscreen draw rate stays low.
    const bool omniVideoFix = omniVideoFixOn() && OmniMedia::Hw::holePunchActive();
    const bool omniVideoOwned = omniVideoFix && pageFullscreen && omniPresenterOwnsVideo();
    if (omniVideoFix) { static bool noted = false; if (!noted) { noted = true; log("video fix (OMNI_C56_VIDEOFIX1): page paint every 500 ms and the shell refresh while a video uses the plane"); } }
    const uint32_t omniSafetyMs = omniS1 && !omniVideoFix ? 10000 : 500;
"""),
# 3. the safety-net compare also while the presenter owns a fullscreen video
("""    const bool omniCompare = omniPaintNow && omniS1 && omniSafetyOnly && omniPageScale < 1 && !OmniMedia::Hw::holePunchActive()
""",
"""    const bool omniCompare = omniPaintNow && omniS1 && omniSafetyOnly && omniPageScale < 1 && (!OmniMedia::Hw::holePunchActive() || omniVideoOwned) // OMNI_C56_VIDEOFIX1
"""),
# 4. the refresh: 54's period while a video uses the plane and the presenter does not own it, timed from the last real draw
("""    const uint32_t omniRefreshMs = (pageFullscreen && OmniMedia::Hw::holePunchActive()) || omniPerfOn(omniPerfS3) ? 1000 : 100;
    const bool omniRefreshDue = omniNow - omniLastDraw >= omniRefreshMs;
""",
"""    // OMNI_C56_VIDEOFIX1: omniLastDraw is also moved by ticks that draw nothing (stick noise: raw joystick events arrive several
    // times a second), so the 1 s refresh never came due and the only draws left with a video on the plane were the 2 s
    // watchdog. The video start-up hand-shake and OMNI_SKIP_COMPOSE ("a wrong skip costs at most the shell's own timer") rely on
    // that timer: c55-seq-1 "no picture presented for 1001 ms ... presents=2 shown=0", pacing off, 418 shown. While a video uses
    // the plane and the presenter does not own it (windowed, or fullscreen before the presenter takes it): 54's period (100 ms
    // windowed, 1 s fullscreen), timed from the last real draw.
    static uint32_t omniVideoFixLastDraw = 0;
    const bool omniVideoTimer = omniVideoFix && !omniVideoOwned;
    const uint32_t omniRefreshMs = omniVideoTimer ? (pageFullscreen ? 1000u : 100u)
        : ((pageFullscreen && OmniMedia::Hw::holePunchActive()) || omniPerfOn(omniPerfS3) ? 1000u : 100u);
    const bool omniRefreshDue = (omniVideoTimer ? omniNow - omniVideoFixLastDraw : omniNow - omniLastDraw) >= omniRefreshMs;
"""),
# 5. stamp real draws
("""    ++omniCensus.draws; ++(omniPlan == 1 ? omniCensus.regional : omniCensus.full);
""",
"""    ++omniCensus.draws; ++(omniPlan == 1 ? omniCensus.regional : omniCensus.full);
    omniVideoFixLastDraw = omniNow; // OMNI_C56_VIDEOFIX1
"""),
]
for old, new in reps:
    o = old.replace('\n', '\r\n'); n = new.replace('\n', '\r\n')
    c = src.count(o)
    assert c == 1, (c, old[:80])
    src = src.replace(o, n)
open(sys.argv[2], 'wb').write(src.encode('utf-8'))
print('patched', len(reps), 'replacements')
