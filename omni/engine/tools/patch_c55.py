#!/usr/bin/env python3
"""dl2-candidate-55: ws-a-1b's entry/OmniBrowser.cpp -> 55's (exact-match replacements, CRLF kept).
usage: patch_c55.py <ws-a-1b OmniBrowser.cpp> <output>"""
import sys
src = open(sys.argv[1], 'rb').read()
assert b'\r\n' in src and src.count(b'\n') == src.count(b'\r\n'), 'expected CRLF throughout'
R = []
# 1. WS-B merge: omniPresenterOwnsVideo() uses ws-b-1's holePunchPresenterOwnsVideo() (54's media/OmniHwService.h).
R.append(("""// true while the presenter shows the fullscreen video by itself. Set OMNI_PERF_A_WS_B to 1 when merging with ws-b-1;
// at 0 (this build, against 53's media headers) it is always false and nothing changes.
#ifndef OMNI_PERF_A_WS_B
#define OMNI_PERF_A_WS_B 0
#endif""", """// true while the presenter shows the fullscreen video by itself. Set OMNI_PERF_A_WS_B to 1 when merging with ws-b-1;
// at 0 it is always false. dl2-candidate-55 (= 54 with ws-b-1): 1.
#ifndef OMNI_PERF_A_WS_B
#define OMNI_PERF_A_WS_B 1
#endif"""))
# 2. (a) cause 1: SDL posts a raw joystick event (SDL_JOYAXISMOTION, ...) next to every game-controller event. Those were
#    recorded as `input`, a reason S4 does not know, so every tick with stick noise was a whole draw (counter: input == axis
#    in every line, regional 0). Raw joystick, sensor and touchpad-motion events are handled nowhere: no visible change.
R.append(("""        // OMNI_PERF_A_COUNTER: stick motion by itself changes nothing drawn (the stick tick moves the pointer, WebKit reports scrolling)
        omniDirtyPhase = event.type == SDL_CONTROLLERAXISMOTION && event.caxis.axis != SDL_CONTROLLER_AXIS_TRIGGERLEFT
            && event.caxis.axis != SDL_CONTROLLER_AXIS_TRIGGERRIGHT ? omniDrAxis : omniDrInput;""",
"""        // OMNI_PERF_A_COUNTER: stick motion by itself changes nothing drawn (the stick tick moves the pointer, WebKit reports scrolling)
        // dl2-candidate-55: so do the raw joystick events SDL posts next to every game-controller event (SDL_JOYAXISMOTION with
        // every stick change: they were `input`, which S4 does not know, so no draw was ever regional), sensor updates and
        // touchpad motion (handled nowhere in the shell).
        const bool omniInvisibleEvent = (event.type == SDL_CONTROLLERAXISMOTION && event.caxis.axis != SDL_CONTROLLER_AXIS_TRIGGERLEFT
            && event.caxis.axis != SDL_CONTROLLER_AXIS_TRIGGERRIGHT) || event.type == SDL_JOYAXISMOTION || event.type == SDL_JOYBALLMOTION
            || event.type == SDL_JOYHATMOTION || event.type == SDL_JOYBUTTONDOWN || event.type == SDL_JOYBUTTONUP
            || event.type == SDL_JOYBATTERYUPDATED || event.type == SDL_CONTROLLERSENSORUPDATE || event.type == SDL_SENSORUPDATE
            || event.type == SDL_CONTROLLERTOUCHPADMOTION;
        omniDirtyPhase = omniInvisibleEvent ? omniDrAxis : omniDrInput;"""))
# 3. (a) cause 3: the stick tick marks the frame dirty while the left stick is held past its dead zone even when the pointer
#    cannot move (clamped at a screen edge): `stick` on every tick of the fullscreen video run, a whole 4K draw each.
R.append(("""        omniDirtyPhase = omniDrStick; // OMNI_PERF_A_COUNTER: pointer motion (OMNI_PERF_A_S4 redraws its rows), right-stick scrolling
        omniFxStickTick(); // OMNI_FEATURES_V1: acceleration, link snapping, right stick both axes (was 16 px per pass)
        omniDirtyPhase = omniDrInput;""",
"""        omniDirtyPhase = omniDrStick; // OMNI_PERF_A_COUNTER: pointer motion (OMNI_PERF_A_S4 redraws its rows), right-stick scrolling
        const float omniPx = pointerX, omniPy = pointerY;
        const bool omniDirtyBefore = omniShellDirty.on;
        const unsigned omniReasonsBefore = omniDrawReasons;
        omniFxStickTick(); // OMNI_FEATURES_V1: acceleration, link snapping, right stick both axes (was 16 px per pass)
        // dl2-candidate-55: the stick tick's own redraw is for the pointer; a pointer that did not move (stick held against a
        // screen edge) needs none. A scrolled menu or dialog (its own redraw) keeps it.
        if (omniPerfOn(omniPerfS3) && pointerX == omniPx && pointerY == omniPy && !omniOverlayOpen() && !omniModalCurrent()) {
            const unsigned added = omniDrawReasons & ~omniReasonsBefore & ~unsigned(omniDrStick);
            omniDrawReasons = omniReasonsBefore | added;
            omniShellDirty.on = omniDirtyBefore || added;
        }
        omniDirtyPhase = omniDrInput;"""))
# 4. (a) cause 2: a tick whose only reasons change nothing drawn (stick noise) still drew the whole frame whenever S4 could not
#    plan (fullscreen, a video on the plane, a panel open): 20-30 whole 4K draws/s in the fullscreen video run. Now nothing
#    (counted `nothing`), in every mode; the 2 s watchdog still draws a whole frame. A due refresh is a reason of its own.
R.append(("""    unsigned omniReasons = omniDrawReasons | (firstFrame ? omniDrFirst : 0u);
    if (!omniPageCopied && !omniShellDirty && !firstFrame) omniReasons |= omniDrRefresh;""",
"""    unsigned omniReasons = omniDrawReasons | (firstFrame ? omniDrFirst : 0u);
    if (!omniPageCopied && !firstFrame && (!omniShellDirty || (omniRefreshDue && omniPerfOn(omniPerfS3)))) omniReasons |= omniDrRefresh;   // dl2-candidate-55: also beside stick noise
    // dl2-candidate-55: only causes that change nothing drawn (stick noise, raw joystick events): no draw in any mode.
    const bool omniInvisibleOnly = omniPerfOn(omniPerfS3) && !firstFrame && omniReasons && !(omniReasons & ~unsigned(omniDrAxis));"""))
R.append(("""    // OMNI_PERF_A_HOOK: only the video plane changed and the video service shows that picture by itself.
    if (omniReasons == omniDrVideo && omniShellVideoOnlyDrawSkip && omniShellVideoOnlyDrawSkip()) {""",
"""    // OMNI_PERF_A_HOOK: only the video plane changed and the video service shows that picture by itself.
    // dl2-candidate-55: left unwired (nullptr). With ws-b-1's V2 the poll asks for a draw while the presenter owns the video only
    // for a new rect / owner / poster or a stale live mask, and each of those needs a new canvas; picture-only draws are already
    // gone at the source (`video` 0-1 per 5 s in the counter). The fullscreen draws were stick noise (fixed above).
    if (omniReasons == omniDrVideo && omniShellVideoOnlyDrawSkip && omniShellVideoOnlyDrawSkip()) {"""))
R.append(("""    int omniPlan = firstFrame ? 0 : omniPlanDraw(omniReasons); // OMNI_PERF_A_S4""",
"""    int omniPlan = firstFrame ? 0 : omniInvisibleOnly ? 2 : omniPlanDraw(omniReasons); // OMNI_PERF_A_S4
    if (omniInvisibleOnly) { omniRegion.active = false; omniRegion.changedKnown = false; }"""))
R.append(("""    if (omniPlan == 2) {   // nothing visible changed (stick noise, a refresh with the bars hidden, a page rect under the bars)
        ++omniCensus.nothing;
        omniPageDamage = OmniRows();""",
"""    if (omniPlan == 2) {   // nothing visible changed (stick noise, a refresh with the bars hidden, a page rect under the bars)
        ++omniCensus.nothing;
        if (!omniInvisibleOnly) omniPageDamage = OmniRows();   // dl2-candidate-55: not planned: keep any page rows for the next draw"""))
# 5. (a) main cause: the "decor" overlay layer (private-tab badges, OMNI_EVERYDAY_V1) reports open() == !pageFullscreen, i.e.
#    always open outside fullscreen, and S4's gate refused any open layer: no draw could ever be regional (and in fullscreen the
#    pageFullscreen gate refuses). The decor layer only draws badges on the top bar's tabs: the gate ignores it and a regional
#    draw that redraws the top bar draws the badges again (same order as the whole frame: after bars and toast, before the pointer).
R.append(("""    for (auto& layer : omniOverlayLayers()) if (layer.open()) return 0;
    const int h = canvas->h;""",
"""    for (auto& layer : omniOverlayLayers()) if (layer.open != omniDecorOpen && layer.open()) { ++omniCensus.whole[3]; return 0; }   // dl2-candidate-55: decor is always "open" (see draw())
    const int h = canvas->h;"""))
R.append(("""        omniDrawToast();   // shows nothing (planned only while the status is "Ready"); keeps its state as in every draw
        if (omniRegion.pointer) omniDrawPointer();""",
"""        omniDrawToast();   // shows nothing (planned only while the status is "Ready"); keeps its state as in every draw
        if (omniRegion.topBar && omniDecorOpen()) omniDecorDraw();   // dl2-candidate-55: private-tab badges over the redrawn top bar
        if (omniRegion.pointer) omniDrawPointer();"""))
# 6. counter: why a draw could not be regional (one line per 5 s next to "draw reasons", only when S4 refused something).
R.append(("""    double paintMs = 0, paintMax = 0;
};
static OmniDrawCensus omniCensus;""",
"""    double paintMs = 0, paintMax = 0;
    unsigned whole[8] = {};   // dl2-candidate-55: S4 refused: cause, mode, sliding, overlay, layout, hover, age, allRows
};
static OmniDrawCensus omniCensus;"""))
R.append(("""    if (reasons & ~known) return 0;""", """    if (reasons & ~known) { ++omniCensus.whole[0]; return 0; }"""))
R.append(("""        || !active() || !active()->message.empty() || omniModalCurrent() || !omniPointerSprite())
        return 0;
    if (omniAutoHideActive() && omniChromeShown != 0.f && omniChromeShown != 1.f) return 0;   // bars sliding""",
"""        || !active() || !active()->message.empty() || omniModalCurrent() || !omniPointerSprite())
        { ++omniCensus.whole[1]; return 0; }
    if (omniAutoHideActive() && omniChromeShown != 0.f && omniChromeShown != 1.f) { ++omniCensus.whole[2]; return 0; }   // bars sliding"""))
R.append(("""    if (!omniFrameNo || omniFrames[omniFrameNo % 4].frame != omniFrameNo || omniFrames[omniFrameNo % 4].key != key) return 0;   // layout changed""",
"""    if (!omniFrameNo || omniFrames[omniFrameNo % 4].frame != omniFrameNo || omniFrames[omniFrameNo % 4].key != key) { ++omniCensus.whole[4]; return 0; }   // layout changed"""))
R.append(("""        if (overBars(p) || overBars(omniPointerLast)) return 0;""", """        if (overBars(p) || overBars(omniPointerLast)) { ++omniCensus.whole[5]; return 0; }"""))
R.append(("""    if (!omniCanvasHolds || omniCanvasHolds > omniFrameNo || omniFrameNo - omniCanvasHolds > 3) return 0;""",
"""    if (!omniCanvasHolds || omniCanvasHolds > omniFrameNo || omniFrameNo - omniCanvasHolds > 3) { ++omniCensus.whole[6]; return 0; }"""))
R.append(("""        if (r.frame != g || r.full || r.key != key || int(r.rows.size()) != h) return 0;""",
"""        if (r.frame != g || r.full || r.key != key || int(r.rows.size()) != h) { ++omniCensus.whole[6]; return 0; }"""))
R.append(("""    if (count >= unsigned(h)) return 0;   // every row: the whole draw is the same work""",
"""    if (count >= unsigned(h)) { ++omniCensus.whole[7]; return 0; }   // every row: the whole draw is the same work"""))
R.append(("""            c.paints, c.paints ? c.paintMs / c.paints : 0.0, c.paintMax, c.over20, c.over100, c.over400, c.deferred, c.slowArmed, c.watchdog, c.safety, c.safetyChanged, c.forced, c.realigns);
        log(line);""",
"""            c.paints, c.paints ? c.paintMs / c.paints : 0.0, c.paintMax, c.over20, c.over100, c.over400, c.deferred, c.slowArmed, c.watchdog, c.safety, c.safetyChanged, c.forced, c.realigns);
        log(line);
        const unsigned* g = c.whole;   // dl2-candidate-55
        if (g[0] || g[1] || g[2] || g[3] || g[4] || g[5] || g[6] || g[7]) {
            char why[200];
            snprintf(why, sizeof why, "regional refused (5 s): cause %u mode %u sliding %u overlay %u layout %u hover %u age %u allRows %u", g[0], g[1], g[2], g[3], g[4], g[5], g[6], g[7]);
            log(why);
        }"""))
for old, new in R:
    o = old.replace('\n', '\r\n').encode(); n = new.replace('\n', '\r\n').encode()
    c = src.count(o)
    assert c == 1, ('not exactly once (%d): ' % c) + old[:80]
    src = src.replace(o, n)
open(sys.argv[2], 'wb').write(src)
print('patched', len(R), 'replacements ->', sys.argv[2])
