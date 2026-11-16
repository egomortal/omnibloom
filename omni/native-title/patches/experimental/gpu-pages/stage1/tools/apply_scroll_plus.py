#!/usr/bin/env python3
"""OMNI_SCROLL_PLUS_V1 (2026-11-16): better page scrolling with the controller.

What existed (audited in the patched tree, 2026-11-16)
  - Right stick: vertical + horizontal scrolling (OmniPointerFeel.h omniFxStickTick: wheel events of `v * 55` px per
    main-loop pass, linear, after the radial dead zone of "Stick dead zone"); no speed setting.
  - D-pad up / down: scroll(+-140) (button()); mouse wheel: scroll(wheel.y * 80). All go through scroll() ->
    omniPageWheel -> WKPageHandleWheelEvent at the pointer.
  - No page up / down, no jump to top / bottom, no position indicator, no smooth-scrolling choice. WebKit's
    ScrollAnimatorEnabled defaults to false on this port (PORT=PlayStation in the build's CMakeCache; the yaml default
    is true only for GTK / WPE / Mac), so wheel scrolling has never been animated.
  - Lists / dialogs (omniModalScrollBy, History, the Tabs panel) have their own L1 / R1 paging; untouched.

What the user sees
  - Browser settings, after "D-pad left / right":
        "Scroll speed"       Slow / Normal / Fast   (Normal = exactly the old feel; D-pad changes, Cross steps,
                                                     Triangle resets)
        "Smooth scrolling"   Off / On               (WebKit's own scroll animation for wheel / stick / D-pad and
                                                     for the L2 jumps below; applies to open tabs at once)
    Speed changes the right stick's curve (Slow: gentler curve, 38 px at full tilt; Fast: as fine as Normal near the
    centre, 95 px at full tilt; Normal: v * 55) and the D-pad step (100 / 140 / 220 px).
  - Hold L2 and push the right stick up / down: one screen up / down (87.5 % of the scroll box under the pointer,
    or of the page). Keep it pushed 0.6 s: to the top / bottom. While L2 is held the stick does nothing else.
  - While scrolling, a thin bar on the right edge of the page shows where you are (thumb = visible part); it stays
    0.7 s after the last scroll and fades out over 0.3 s. Pages that fit, full-screen video, menus: no bar.

Why hold L2 + right stick (checked in the patched tree after the whole chain, 2026-11-16)
  - Controls guide (OmniControlsHelp.h): L2 rows are L2 + Square / Triangle / Cross / Circle / D-pad up-down / R3 /
    L3, L2 alone (Saved links, Media downloads on), L2 / R2 caret by word (keyboard only); the tab switcher adds
    L2 + L1 / R1. No row uses L2 with a stick.
  - Readers of the right stick (grep SDL_CONTROLLER_AXIS_RIGHTX / RIGHTY): omniFxStickTick (browsing scroll, the hook
    point), omniKbTick (keyboard open only; omniFxStickTick does not run then), omniStickRadius / dead zone helpers,
    OmniGamepad.h (the web Gamepad API pass-through, unchanged). Readers of the L2 axis (TRIGGERLEFT): omniL2Track /
    omniSavedAxis (L2 tap -> saved links: every chord sets omniL2ChordUsed, so do we), omniQaShotChord (+R3),
    omniMagL2 (+L3), omniKbTick (keyboard only), OmniGamepad.h. None reads L2 together with the right stick.
  - Stick clicks are taken (R3 close tab, L3 add shortcut / add-on switch), R2 sends to Media downloads, L1 / R1
    switch tabs, touchpad translates, so no plain button was free for page / end jumps.
  - The tab switcher strip, dialogs, Browser settings, the keyboard and full-screen video keep the stick as before
    (omniOverlayOpen() / editing / settingsOpen / pageFullscreen: the gesture is off and normal scrolling runs).

Position bar: where the numbers come from (no polling)
  - WebKit's C API has no scroll-position getter (WKPage.h: only IsPinnedToTop/BottomSide); WKPageUIClient's
    pageDidScroll (WebPage::pageDidScroll -> WebPageProxy -> API::UIClient; fired by WebChromeClient::scroll /
    invalidateContentsForSlowScroll for the main frame; accelerated compositing is off in Omni, so main-thread
    scrolling) says "the main frame scrolled" without a position. It was unset (ui.pageDidScroll nowhere in the tree).
  - So: on pageDidScroll for the active tab, only within 600 ms of controller / wheel scrolling (scroll() notes it),
    one tiny script answers "w,top,scrollHeight,innerHeight"; at most one in flight and one per 90 ms (a scroll during
    the gap is remembered and asked once the gap passes; a query that never answers stops blocking after 1.5 s).
    The L2 jump script answers its own destination (also for a scroll box inside the page). Scrolling an inner box with
    the stick does not fire pageDidScroll: no bar there (only after an L2 jump).
  - Drawn as a non-blocking overlay layer (like the find bar): open only while shown, so the shell's regional draw
    stays as before the rest of the time; redraws are asked only while it fades (300 ms) or appears / goes.

Smooth scrolling: WKPreferencesSet/GetBoolValueForKeyForTesting(preferences, "ScrollAnimatorEnabled") (declared in
WKPreferencesRefPrivate.h, defined in WKPreferences.cpp next to WKPreferencesSetFullScreenEnabled, which Omni links;
"ForTesting" is only its name: WebPreferences::setBoolValueForKey -> update() -> every page's preferencesDidChange).
Never chosen: WebKit's default is left alone (no call). Every tab uses the one `preferences` object (newTab() and
the private-tab path both call WKPageConfigurationSetPreferences(config, preferences)). The L2 jumps pass
behavior 'smooth' / 'instant' to scrollTo by the same value (WebCore's ScrollBehavior enum has "instant").

Settings rows: ids 840 (Scroll speed) and 841 (Smooth scrolling); checked unused in every tools/apply_*.py and
every engine/entry file (this script refuses to run if either appears there). They are dispatched first in
omniFxSettingsInput (before the >= 300 / >= 900 ranges). Saved in /data/omni/scroll-plus.txt ("speed<TAB>0-2",
"smooth<TAB>0|1"; written through omniIoQueue). Test modes (omniTestMode()) keep Normal speed, the WebKit default, no bar
and no gesture.

Pure part: engine/entry/OmniScrollPlus.h (no SDL / WebKit): speed curves, D-pad step, settings file, the L2 + stick
gesture, the jump / metrics scripts, metrics parsing, bar geometry, fade, query throttle. Tested by
tools/test_scroll_plus.cpp:
    g++ -std=c++20 -Wall -Wextra -Werror -I<tree>/engine/entry test_scroll_plus.cpp -o t && ./t
Shell side: engine/entry/OmniScrollPlusShell.h (included from OmniFeatures3.h after OmniTabSwitcherShell.h).

Anchors (exactly once each; MARK makes each file idempotent; each file keeps its line endings):
  OmniBrowser.cpp       the OmniHistoryPlus.h include line (pure include after it, file scope);
                        `static bool omniOverlayScroll(double amount);` (forward declarations before it);
                        `    omniPageWheel(amount);` in scroll() (note the user scroll before it);
                        button()'s D-pad down / up scroll(-140) / scroll(140) lines (the speed's step);
                        `    omniF2InstallUI(ui); ...` in newTab() (ui.pageDidScroll before it);
                        `    WKPreferencesSetFullScreenEnabled(preferences.get(), true);` (the saved smooth choice after).
  OmniPointerFeel.h     omniFxStickTick's wheel line and side line (curve; L2 gesture first).
  OmniFeatures3.h       the OmniTabSwitcherShell.h include line (OmniScrollPlusShell.h after it);
                        omniF3Tick's omniOrTick line (omniScpTick after it).
  OmniBrowserSettings.h the omniPfSettingsInput declaration (ids + declarations after it); the "D-pad left / right"
                        row (rows after it); omniFxSettingsInput's omniPfRowId line (dispatch before it).
Apply AFTER apply_l2_chords.py (base T), apply_offline_retry.py, apply_pad_feedback.py and apply_tab_switcher.py.
r2 (OMNI_SCROLL_PLUS_V1_R2, REV): omniScpBrowsing() is false while the PDF reader owns the triggers
(omniPdfvOwnsTriggers, OMNI_PDF_VIEWER_V1: L2 / R2 zoom there), so holding L2 to zoom out never pages the reader.
Compiled in when OmniPdfViewer.h exists (apply_pdf_viewer.py runs later in the chain and declares the function in
OmniBrowser.cpp before OmniFeatures3.h). Only OmniScrollPlusShell.h changes (rewritten whole: an r1 tree upgrades).
usage: apply_scroll_plus.py <engine tree>   (re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_SCROLL_PLUS_V1'
REV = 'OMNI_SCROLL_PLUS_V1_R2'   # r2: no L2 gesture in the PDF reader (shell only)
root = Path(sys.argv[1]) / 'engine' / 'entry'
TOOLS = Path(__file__).resolve().parent
ROW_IDS = (840, 841)

PURE = r'''// OMNI_SCROLL_PLUS_V1: the pure part of better controller scrolling: the scroll-speed curve for the right stick and the
// D-pad step, the L2 + right stick gesture (flick: one screen up / down; keep holding: top / bottom), the one-shot page
// script that does a page / end jump, the scroll metrics it answers, the position bar's geometry and fade, the
// metrics-query throttle and scroll-plus.txt. No SDL, no WebKit. Shell side: OmniScrollPlusShell.h; the reasons are in
// tools/apply_scroll_plus.py. Tested on the host with g++ (test_scroll_plus.cpp).
#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string>

namespace OmniScrollPlus {

// --- speed -----------------------------------------------------------------------------------------------------------
enum Speed : int { kSlow, kNormal, kFast, kSpeedCount };
inline const char* speedName(int s)
{
    static const char* const n[kSpeedCount] = { "Slow", "Normal", "Fast" };
    return n[std::clamp(s, 0, int(kSpeedCount) - 1)];
}
// Right stick, per main-loop pass: v is the dead-zone-rescaled axis (-1..1, OmniPointerFeel.h's `wheel` / `side`).
// Normal is exactly what Omni always did (v * 55, linear). Slow: a gentler curve (fine near the centre) topping out at
// 38 px; Fast: slow near the centre like Normal, 95 px at full tilt. The sign follows v.
constexpr float kNormalGain = 55.f;
inline float stickAmount(float v, int speed)
{
    if (!(v == v) || v == 0.f) return 0.f;
    const float a = std::min(1.f, std::fabs(v));
    float m;
    switch (std::clamp(speed, 0, int(kSpeedCount) - 1)) {
    case kSlow: m = 38.f * std::pow(a, 1.5f); break;
    case kFast: m = 95.f * std::pow(a, 1.35f); break;
    default: return v * kNormalGain;   // unchanged (including |v| slightly above 1 if a caller passes it)
    }
    return v < 0 ? -m : m;
}
// D-pad up / down while browsing (button(): scroll(+-140) before).
inline int dpadStep(int speed)
{
    static const int s[kSpeedCount] = { 100, 140, 220 };
    return s[std::clamp(speed, 0, int(kSpeedCount) - 1)];
}

// --- settings file (/data/omni/scroll-plus.txt: "speed\t<0-2>\nsmooth\t<0|1>\n"; smooth absent: WebKit's default) ---
struct Settings {
    int speed = kNormal;
    int smooth = -1;   // -1: never chosen (WebKit's own default is left alone), 0 off, 1 on
};
inline Settings parse(const std::string& text)
{
    Settings s;
    size_t i = 0;
    while (i < text.size()) {
        size_t e = text.find('\n', i);
        if (e == std::string::npos) e = text.size();
        std::string line = text.substr(i, e - i);
        i = e + 1;
        while (!line.empty() && (line.back() == '\r' || line.back() == ' ')) line.pop_back();
        const size_t t = line.find('\t');
        if (t == std::string::npos) continue;
        const std::string k = line.substr(0, t), v = line.substr(t + 1);
        if (v.empty() || v.size() > 3 || v.find_first_not_of("0123456789") != std::string::npos) continue;
        const int n = atoi(v.c_str());
        if (k == "speed" && n >= 0 && n < kSpeedCount) s.speed = n;
        else if (k == "smooth" && (n == 0 || n == 1)) s.smooth = n;
    }
    return s;
}
inline std::string serialize(const Settings& s)
{
    std::string out = "speed\t" + std::to_string(std::clamp(s.speed, 0, int(kSpeedCount) - 1)) + "\n";
    if (s.smooth == 0 || s.smooth == 1) out += "smooth\t" + std::to_string(s.smooth) + "\n";
    return out;
}
inline Settings stepSpeed(Settings s, int dir)   // D-pad left / right (no wrap); Cross (dir 0): next, wrapping
{
    if (dir == 0) s.speed = (std::clamp(s.speed, 0, int(kSpeedCount) - 1) + 1) % kSpeedCount;
    else s.speed = std::clamp(s.speed + (dir < 0 ? -1 : 1), 0, int(kSpeedCount) - 1);
    return s;
}

// --- L2 + right stick gesture ---------------------------------------------------------------------------------------
enum Action : int { aNone, aPageUp, aPageDown, aTop, aBottom };
constexpr float kFlick = 0.55f;      // |v| that fires the page step (once per push)
constexpr float kRearm = 0.30f;      // back under this: the next push fires again
constexpr uint32_t kHoldMs = 600;    // still pushed this long after the page step: to the top / bottom
// v < 0 is the stick pushed up (SDL's Y axis): page up / top.
struct Gesture {
    int dir = 0;              // the push that fired (-1 up, 1 down), 0: armed
    uint32_t since = 0;       // when it fired
    bool jumped = false;      // the hold already went to the end
    void reset() { dir = 0; since = 0; jumped = false; }
    Action update(float v, uint32_t now)
    {
        const float a = std::fabs(v);
        if (dir == 0) {
            if (a < kFlick) return aNone;
            dir = v < 0 ? -1 : 1; since = now; jumped = false;
            return dir < 0 ? aPageUp : aPageDown;
        }
        if (a < kRearm || (v < 0 ? -1 : 1) != dir) {   // let go (or pushed the other way through the centre)
            const int was = dir;
            reset();
            if (a >= kFlick && (v < 0 ? -1 : 1) != was) return update(v, now);
            return aNone;
        }
        if (!jumped && a >= kFlick && uint32_t(now - since) >= kHoldMs) { jumped = true; return dir < 0 ? aTop : aBottom; }
        return aNone;
    }
};
// The script's mode: -1 / 1 one screen up / down, -2 / 2 top / bottom, 0 nothing.
inline int mode(Action a) { return a == aPageUp ? -1 : a == aPageDown ? 1 : a == aTop ? -2 : a == aBottom ? 2 : 0; }

// --- page script (one per L2 + stick action; never polled) ----------------------------------------------------------
// It picks the scroll box under the pointer (the nearest scrollable ancestor of elementFromPoint, else the document),
// scrolls it one screen (87.5 %, at least 40 px) or to its top / bottom, smooth or instant, and answers where it is
// going: "w|e,<top>,<scrollHeight>,<clientHeight>" (w = the document), or "" when it failed.
constexpr double kPageFraction = 0.875;
inline std::string jumpScript(int m, double cssX, double cssY, bool smooth)
{
    std::string js = "(function(X,Y,M,S){try{var d=document,se=d.scrollingElement||d.documentElement,e=d.elementFromPoint(X,Y),t=null;"
        "for(;e&&e!==d.body&&e!==d.documentElement;e=e.parentElement){var o=getComputedStyle(e).overflowY;"
        "if((o==='auto'||o==='scroll'||o==='overlay')&&e.scrollHeight>e.clientHeight+1){t=e;break;}}"
        "var w=!t,ch=w?innerHeight:t.clientHeight,sh=w?se.scrollHeight:t.scrollHeight,cur=w?scrollY:t.scrollTop,max=Math.max(0,sh-ch);"
        "var to=M===-2?0:M===2?max:Math.min(max,Math.max(0,cur+M*Math.max(40,ch*";
    char frac[32];
    snprintf(frac, sizeof frac, "%.3f", kPageFraction);
    js += frac;
    js += ")));var p={top:to,behavior:S?'smooth':'instant'};if(w)window.scrollTo(p);else t.scrollTo(p);"
          "return(w?'w':'e')+','+Math.round(to)+','+Math.round(sh)+','+Math.round(ch);}catch(x){return'';}})(";
    char args[96];
    snprintf(args, sizeof args, "%.1f,%.1f,%d,%d)", std::isfinite(cssX) ? cssX : 0.0, std::isfinite(cssY) ? cssY : 0.0,
             std::clamp(m, -2, 2), smooth ? 1 : 0);
    js += args;
    return js;
}
// After the main frame scrolled (WebKit's pageDidScroll, only while the user is scrolling): the document's metrics.
inline const char* metricsScript()
{
    return "(function(){var e=document.scrollingElement||document.documentElement;"
           "return 'w,'+Math.round(e.scrollTop)+','+Math.round(e.scrollHeight)+','+Math.round(innerHeight);})()";
}
struct Metrics {
    bool valid = false;
    bool document = true;     // the document (w) or a scroll box (e)
    double top = 0, height = 0, client = 0;
};
inline Metrics parseMetrics(const std::string& s)
{
    Metrics m;
    if (s.size() < 7 || s.size() > 64 || (s[0] != 'w' && s[0] != 'e') || s[1] != ',') return m;
    double v[3];
    size_t i = 2;
    for (int k = 0; k < 3; ++k) {
        const size_t e = k < 2 ? s.find(',', i) : s.size();
        if (e == std::string::npos || e == i) return m;
        const std::string part = s.substr(i, e - i);
        if (part.find_first_not_of("-0123456789") != std::string::npos) return m;
        v[k] = atof(part.c_str());
        i = e + 1;
    }
    if (v[1] < 0 || v[2] <= 0 || v[1] > 1e8) return m;
    m.valid = true; m.document = s[0] == 'w';
    m.top = std::clamp(v[0], 0.0, std::max(0.0, v[1] - v[2])); m.height = v[1]; m.client = v[2];
    return m;
}
inline bool scrollable(const Metrics& m) { return m.valid && m.height > m.client + 1; }

// --- position bar --------------------------------------------------------------------------------------------------
// A thin rounded track on the right edge of the page area with a thumb sized by the visible fraction. Layout px.
constexpr int kBarW = 6, kBarMargin = 6, kBarInset = 10, kMinThumb = 28;
struct Bar { bool shown = false; int x = 0, trackY = 0, trackH = 0, thumbY = 0, thumbH = 0; };
inline Bar bar(const Metrics& m, int pageTop, int pageBottom, int rightEdge)
{
    Bar b;
    const int y0 = pageTop + kBarInset, y1 = pageBottom - kBarInset;
    if (!scrollable(m) || y1 - y0 < kMinThumb * 2 || rightEdge < kBarW + kBarMargin) return b;
    b.shown = true;
    b.x = rightEdge - kBarMargin - kBarW;
    b.trackY = y0; b.trackH = y1 - y0;
    const double frac = std::clamp(m.client / m.height, 0.0, 1.0);
    b.thumbH = std::clamp(int(std::lround(b.trackH * frac)), kMinThumb, b.trackH);
    const double range = m.height - m.client, pos = range > 0 ? std::clamp(m.top / range, 0.0, 1.0) : 0.0;
    b.thumbY = b.trackY + int(std::lround((b.trackH - b.thumbH) * pos));
    return b;
}
// Fully shown for 700 ms after the last scroll, then gone over 300 ms (1 s in all).
constexpr uint32_t kHoldShownMs = 700, kFadeMs = 300;
inline uint8_t alpha(uint32_t sinceLastScrollMs)
{
    if (sinceLastScrollMs <= kHoldShownMs) return 255;
    if (sinceLastScrollMs >= kHoldShownMs + kFadeMs) return 0;
    return uint8_t(255 - (255 * (sinceLastScrollMs - kHoldShownMs)) / kFadeMs);
}
inline uint8_t scaled(uint8_t base, uint8_t a) { return uint8_t((unsigned(base) * a + 127) / 255); }

// --- metrics queries: event-driven (pageDidScroll / a jump's answer), one in flight, at most one per 90 ms ---------
constexpr uint32_t kUserWindowMs = 600;   // a pageDidScroll counts only this soon after the controller / wheel scrolled
constexpr uint32_t kQueryGapMs = 90;
constexpr uint32_t kStaleMs = 1500;
struct Throttle {
    bool inFlight = false, pending = false, any = false;
    uint32_t last = 0;
    // A scroll happened: send now (true) or remember it for later (pending).
    bool want(uint32_t now)
    {
        if (!inFlight && (!any || uint32_t(now - last) >= kQueryGapMs)) { inFlight = true; any = true; last = now; pending = false; return true; }
        pending = true;
        return false;
    }
    void answered() { inFlight = false; }
    // From the tick: a remembered scroll whose gap has passed (only ever after a real scroll: no polling). A query that
    // never came back (a hung page) stops counting as in flight after kStaleMs.
    bool due(uint32_t now)
    {
        if (inFlight && uint32_t(now - last) >= kStaleMs) inFlight = false;
        if (!pending || inFlight || uint32_t(now - last) < kQueryGapMs) return false;
        inFlight = true; last = now; pending = false;
        return true;
    }
    void reset() { inFlight = pending = false; }
};
inline bool userScrolling(uint32_t now, uint32_t lastInput, bool anyInput) { return anyInput && uint32_t(now - lastInput) <= kUserWindowMs; }

} // namespace OmniScrollPlus
'''

SHELL = r'''// OMNI_SCROLL_PLUS_V1: better controller scrolling (shell side). Included from OmniFeatures3.h (inside OmniBrowser.cpp's
// anonymous namespace, after OmniTabSwitcherShell.h). The pure part is OmniScrollPlus.h; the reasons are in
// tools/apply_scroll_plus.py. Main thread only (WebKit's callbacks come on the main run loop).
//   - Scroll speed (Browser settings): the right stick's curve and the D-pad step (Normal = as before).
//   - Smooth scrolling (Browser settings): WebKit's ScrollAnimatorEnabled preference (off on this port until chosen).
//   - Hold L2 + push the right stick up / down: one screen up / down; keep it pushed: to the top / bottom.
//   - A thin position bar on the right edge while scrolling, gone 1 s after the last scroll. Its numbers come from one
//     tiny script after WebKit reports a main-frame scroll (pageDidScroll) that follows controller / wheel input,
//     at most one in flight and one per 90 ms, and from the L2 jump script's own answer. Nothing is polled.
#pragma once

namespace OSCP = OmniScrollPlus;

static OSCP::Settings omniScp;
static bool omniScpLoaded = false;
static OSCP::Gesture omniScpGesture;
static OSCP::Throttle omniScpQuery;
static OSCP::Metrics omniScpMetrics;
static const void* omniScpMetricsTab = nullptr;   // the tab omniScpMetrics belong to
static uint32_t omniScpLastInput = 0, omniScpShownAt = 0, omniScpGen = 1;
static bool omniScpAnyInput = false, omniScpEverShown = false, omniScpVisible = false;
static const void* omniScpTabSeen = nullptr;      // the active tab at the last tick (a switch drops the bar)

static void omniScpLoad()
{
    if (omniScpLoaded) return;
    omniScpLoaded = true;
    std::string text;
    if (FILE* f = fopen(omniData("scroll-plus.txt").c_str(), "r")) {
        char buf[256];
        const size_t n = fread(buf, 1, sizeof buf, f);
        fclose(f);
        text.assign(buf, n);
    }
    omniScp = OSCP::parse(text);
}
static void omniScpSave() { omniIoQueue(omniData("scroll-plus.txt"), OSCP::serialize(omniScp), false); }
static int omniScpSpeed() { if (omniTestMode()) return OSCP::kNormal; omniScpLoad(); return omniScp.speed; }
// OmniPointerFeel.h (right stick, both axes) and button() (D-pad up / down).
static float omniScpCurve(float v) { return OSCP::stickAmount(v, omniScpSpeed()); }
static int omniScpDpadStep() { return OSCP::dpadStep(omniScpSpeed()); }

// --- smooth scrolling: WebKit's own preference (shared by every tab: newTab() and private tabs use `preferences`) ----
static WKRetainPtr<WKStringRef> omniScpSmoothKey() { return adoptWK(WKStringCreateWithUTF8CString("ScrollAnimatorEnabled")); }
static bool omniScpSmoothOn()
{
    if (!preferences.get()) return false;
    return WKPreferencesGetBoolValueForKeyForTesting(preferences.get(), omniScpSmoothKey().get());
}
static void omniScpSmoothSet(bool on)
{
    if (!preferences.get()) return;
    WKPreferencesSetBoolValueForKeyForTesting(preferences.get(), on, omniScpSmoothKey().get());   // updates open pages too
    fprintf(stderr, "OMNI SCROLL PLUS: smooth scrolling %s\n", on ? "on" : "off"); fflush(stderr);
}
// main(), after the preferences are made: only a choice the user made (none: WebKit's default stays).
static void omniScpApplySmooth()
{
    if (omniTestMode()) return;
    omniScpLoad();
    if (omniScp.smooth == 0 || omniScp.smooth == 1) omniScpSmoothSet(omniScp.smooth == 1);
}

// --- input -----------------------------------------------------------------------------------------------------------
// scroll(): every page scroll from the controller or a mouse wheel (not the find bar, not scripts).
static void omniScpNoteScroll() { omniScpLastInput = SDL_GetTicks(); omniScpAnyInput = true; }
static bool omniScpBrowsing()
{
#if __has_include("OmniPdfViewer.h")
    if (omniPdfvOwnsTriggers()) return false;   // OMNI_SCROLL_PLUS_V1_R2: L2 / R2 zoom the PDF reader
#endif
    return active() && !active()->crashed && !editing && !pageEditing && !settingsOpen && !pageFullscreen && !omniOverlayOpen() && !omniTestMode();
}
static void omniScpTake(WKTypeRef result, WKErrorRef error, void* context)
{
    if (uint32_t(reinterpret_cast<uintptr_t>(context)) != omniScpGen || !active()) return;   // another tab since
    const OSCP::Metrics m = OSCP::parseMetrics(omniFxResultString(result, error));
    if (!m.valid) return;
    omniScpMetrics = m;
    omniScpMetricsTab = active();
    omniScpShownAt = SDL_GetTicks();
    omniScpEverShown = true;
    omniShellDirty = true;
}
static void omniScpAsk()
{
    Tab* t = active();
    if (!t) { omniScpQuery.answered(); return; }
    auto src = adoptWK(WKStringCreateWithUTF8CString(OSCP::metricsScript()));
    WKPageEvaluateJavaScriptInMainFrame(t->page, src.get(), reinterpret_cast<void*>(uintptr_t(omniScpGen)), [](WKTypeRef result, WKErrorRef error, void* context) {
        omniScpQuery.answered();
        omniScpTake(result, error, context);
    });
}
// WebKit's pageDidScroll (main frame only; no position in it): the bar's numbers, when the user is the one scrolling.
static void omniScpDidScroll(WKPageRef page)
{
    Tab* t = active();
    if (!t || t->page != page || omniTestMode()) return;
    const uint32_t now = SDL_GetTicks();
    if (!OSCP::userScrolling(now, omniScpLastInput, omniScpAnyInput)) return;
    if (omniScpEverShown && omniScpMetricsTab == t) omniScpShownAt = now;   // keeps the bar up while it moves
    if (omniScpQuery.want(now)) omniScpAsk();
}
// L2 + right stick: one screen / the end, in the scroll box under the pointer.
static void omniScpRun(OSCP::Action a)
{
    Tab* t = active();
    if (!t || OSCP::mode(a) == 0) return;
    if (t->omniPaintHold.active) { t->omniPaintHold.cancel(); omniShellDirty = true; return; }   // as omniPageWheel
    const double k = omniFxCssPerLayout(t);
    const float py = std::clamp(pointerY, float(omniPageTop()), float(std::max(omniPageTop(), omniPageBottom() - 1)));
    const std::string js = OSCP::jumpScript(OSCP::mode(a), pointerX * k, (py - omniPageTop()) * k, omniScpSmoothOn());
    auto src = adoptWK(WKStringCreateWithUTF8CString(js.c_str()));
    WKPageEvaluateJavaScriptInMainFrame(t->page, src.get(), reinterpret_cast<void*>(uintptr_t(omniScpGen)), omniScpTake);
    omniScpNoteScroll();
    fprintf(stderr, "OMNI SCROLL PLUS: %s\n", a == OSCP::aPageUp ? "page up" : a == OSCP::aPageDown ? "page down" : a == OSCP::aTop ? "top" : "bottom");
    fflush(stderr);
}
// omniFxStickTick, every pass with the keyboard closed: true while L2 is held on a plain page (the stick pages there
// instead of scrolling). The L2 release is then not a saved-links tap.
static bool omniScpStick(float wheel)
{
    if (!omniL2Held || !controller || !omniScpBrowsing()) { omniScpGesture.reset(); return false; }
    const OSCP::Action a = omniScpGesture.update(wheel, SDL_GetTicks());
    if (a != OSCP::aNone) {
        omniL2ChordUsed = true;   // OMNI_L2_CHORDS_V1
        omniChromeScroll();
        omniScpRun(a);
        omniShellDirty = true;
    }
    return true;
}

// --- position bar ----------------------------------------------------------------------------------------------------
static bool omniScpShown(uint32_t now)
{
    return omniScpEverShown && omniScpMetrics.valid && active() && omniScpMetricsTab == active() && !pageFullscreen && !settingsOpen
        && !editing && !omniOverlayOpen() && OSCP::scrollable(omniScpMetrics) && OSCP::alpha(now - omniScpShownAt) > 0;
}
// omniF3Tick: a remembered query, a tab switch, and redraws only while the bar fades (or appears / goes).
static void omniScpTick(uint32_t now)
{
    if (active() != omniScpTabSeen) {   // another tab: its bar starts from nothing; late answers are ignored
        omniScpTabSeen = active();
        ++omniScpGen;
        omniScpMetrics = OSCP::Metrics();
        omniScpQuery.reset();
        omniScpGesture.reset();
    }
    if (omniScpQuery.due(now)) omniScpAsk();
    const bool shown = omniScpShown(now);
    if (shown != omniScpVisible || (shown && OSCP::alpha(now - omniScpShownAt) < 255)) omniShellDirty = true;
    omniScpVisible = shown;
}
static void omniScpDraw()
{
    const uint32_t now = SDL_GetTicks();
    if (!omniScpShown(now)) return;
    const OSCP::Bar b = OSCP::bar(omniScpMetrics, omniPageTop(), omniPageBottom(), width);
    if (!b.shown) return;
    const uint8_t a = OSCP::alpha(now - omniScpShownAt);
    const OmniTheme& T = omniTheme();
    fillRounded(b.x, b.trackY, OSCP::kBarW, b.trackH, OSCP::kBarW / 2, T.bg, OSCP::scaled(120, a));
    fillRounded(b.x, b.thumbY, OSCP::kBarW, b.thumbH, OSCP::kBarW / 2, T.accent, OSCP::scaled(235, a));
}
// Not blocking: the page keeps every input; it is only drawn (with the other overlays, above the bars).
[[maybe_unused]] static const bool omniScpLayers = [] {
    omniOverlayLayers().push_back({ [] { return omniScpShown(SDL_GetTicks()); }, nullptr, nullptr, nullptr, omniScpDraw, false });
    return true;
}();

// --- Browser settings rows (omniScpRowSpeed / omniScpRowSmooth, OmniBrowserSettings.h) --------------------------------
static void omniScpSettingsRows(OmniFxPanel& p)
{
    omniScpLoad();
    OmniFxRow s; s.id = omniScpRowSpeed; s.label = "Scroll speed"; s.value = OSCP::speedName(omniScp.speed); s.stepper = true;
    p.rows.push_back(s);
    OmniFxRow m; m.id = omniScpRowSmooth; m.label = "Smooth scrolling"; m.value = omniScpSmoothOn() ? "On" : "Off"; m.stepper = true;
    p.rows.push_back(m);
}
// D-pad left / right change, Cross steps, Triangle resets (Normal / Off).
static bool omniScpSettingsInput(int id, int b)
{
    const bool left = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT, right = b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT;
    const bool cross = b == SDL_CONTROLLER_BUTTON_A, reset = b == SDL_CONTROLLER_BUTTON_Y;
    if (!left && !right && !cross && !reset) return false;
    omniScpLoad();
    if (id == omniScpRowSpeed) {
        if (reset) omniScp.speed = OSCP::kNormal;
        else omniScp = OSCP::stepSpeed(omniScp, cross ? 0 : left ? -1 : 1);
        omniScpSave();
        return true;
    }
    if (id != omniScpRowSmooth) return false;
    const bool on = reset ? false : !omniScpSmoothOn();
    omniScp.smooth = on ? 1 : 0;
    omniScpSave();
    omniScpSmoothSet(on);
    notice(on ? "Smooth scrolling on" : "Smooth scrolling off");
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniHistoryPlus.h" // OMNI_HISTORY_PLUS_V1: history search, day groups, range deletes (pure)\n',
         '#include "OmniHistoryPlus.h" // OMNI_HISTORY_PLUS_V1: history search, day groups, range deletes (pure)\n'
         '#include "OmniScrollPlus.h" // OMNI_SCROLL_PLUS_V1: scroll speed, L2 + right stick page / end, position bar (pure)\n'),
        ('static bool omniOverlayScroll(double amount);\n',
         '// OMNI_SCROLL_PLUS_V1 (definitions in OmniScrollPlusShell.h): speed, L2 + right stick, position bar, smooth scrolling.\n'
         'static void omniScpNoteScroll();\n'
         'static void omniScpDidScroll(WKPageRef page);\n'
         'static float omniScpCurve(float v);\n'
         'static int omniScpDpadStep();\n'
         'static bool omniScpStick(float wheel);\n'
         'static void omniScpApplySmooth();\n'
         'static bool omniOverlayScroll(double amount);\n'),
        ('    omniPageWheel(amount);\n',
         '    omniScpNoteScroll(); // OMNI_SCROLL_PLUS_V1: the position bar only follows scrolling the user did\n'
         '    omniPageWheel(amount);\n'),
        ('    else if (button == SDL_CONTROLLER_BUTTON_DPAD_DOWN) scroll(-140);\n'
         '    else if (button == SDL_CONTROLLER_BUTTON_DPAD_UP) scroll(140);\n',
         '    else if (button == SDL_CONTROLLER_BUTTON_DPAD_DOWN) scroll(-omniScpDpadStep()); // OMNI_SCROLL_PLUS_V1: 140 at Normal\n'
         '    else if (button == SDL_CONTROLLER_BUTTON_DPAD_UP) scroll(omniScpDpadStep());\n'),
        ('    omniF2InstallUI(ui); // OMNI_FEATURES_V2: file chooser + site permissions\n',
         '    ui.pageDidScroll = [](WKPageRef page, const void*) { omniScpDidScroll(page); }; // OMNI_SCROLL_PLUS_V1: position bar\n'
         '    omniF2InstallUI(ui); // OMNI_FEATURES_V2: file chooser + site permissions\n'),
        ('    WKPreferencesSetFullScreenEnabled(preferences.get(), true);\n',
         '    WKPreferencesSetFullScreenEnabled(preferences.get(), true);\n'
         '    omniScpApplySmooth(); // OMNI_SCROLL_PLUS_V1: the saved "Smooth scrolling" choice (none: WebKit default)\n'),
    ],
    'OmniPointerFeel.h': [
        ('    if (wheel) { omniChromeScroll(); scroll(-wheel * 55); } // OMNI_STYLE_V1\n',
         '    const bool omniScpL2 = omniScpStick(wheel); // OMNI_SCROLL_PLUS_V1: L2 held on a page: the stick pages / jumps instead\n'
         '    if (wheel && !omniScpL2) { omniChromeScroll(); scroll(-omniScpCurve(wheel)); } // OMNI_STYLE_V1; OMNI_SCROLL_PLUS_V1: speed (Normal = wheel * 55)\n'),
        ('    if (side && std::fabs(side) > std::fabs(wheel) * 0.6f) { omniChromeScroll(); omniFxHorizontalScroll(-side * 55); }\n',
         '    if (side && !omniScpL2 && std::fabs(side) > std::fabs(wheel) * 0.6f) { omniChromeScroll(); omniFxHorizontalScroll(-omniScpCurve(side)); } // OMNI_SCROLL_PLUS_V1\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniTabSwitcherShell.h" // OMNI_TAB_SWITCHER_V1 (after tab groups and pinned tabs: it reads both)\n',
         '#include "OmniTabSwitcherShell.h" // OMNI_TAB_SWITCHER_V1 (after tab groups and pinned tabs: it reads both)\n'
         '#include "OmniScrollPlusShell.h" // OMNI_SCROLL_PLUS_V1\n'),
        ('    omniOrTick(now);    // OMNI_OFFLINE_RETRY_V1: network watch while a tab is offline, staggered reloads\n',
         '    omniOrTick(now);    // OMNI_OFFLINE_RETRY_V1: network watch while a tab is offline, staggered reloads\n'
         '    omniScpTick(now);   // OMNI_SCROLL_PLUS_V1: position bar fade, a remembered metrics query (only after a scroll)\n'),
    ],
    'OmniBrowserSettings.h': [
        ('static bool omniPfSettingsInput(int b);\n',
         'static bool omniPfSettingsInput(int b);\n'
         'constexpr int omniScpRowSpeed = 840, omniScpRowSmooth = 841; // OMNI_SCROLL_PLUS_V1 (OmniScrollPlusShell.h)\n'
         'static void omniScpSettingsRows(OmniFxPanel& p);\n'
         'static bool omniScpSettingsInput(int id, int b);\n'),
        ('    add(omniFxSetDpad, "D-pad left / right", omniFxSet.dpad ? "Switch tabs" : "Back / forward", true);\n',
         '    add(omniFxSetDpad, "D-pad left / right", omniFxSet.dpad ? "Switch tabs" : "Back / forward", true);\n'
         '    omniScpSettingsRows(p); // OMNI_SCROLL_PLUS_V1: Scroll speed, Smooth scrolling\n'),
        ('    if (r.id == omniPfRowId) return omniPfSettingsInput(b); // OMNI_PAD_FEEDBACK_V1\n',
         '    if (r.id == omniScpRowSpeed || r.id == omniScpRowSmooth) return omniScpSettingsInput(r.id, b); // OMNI_SCROLL_PLUS_V1 (before the >= 300 rows)\n'
         '    if (r.id == omniPfRowId) return omniPfSettingsInput(b); // OMNI_PAD_FEEDBACK_V1\n'),
    ],
}
NEW_FILES = ('OmniScrollPlus.h', 'OmniScrollPlusShell.h')


def variants(old0, s):
    """The anchor with the file's own line endings (mixed files: whichever spelling is present)."""
    for e in ('\r\n', '\n'):
        old = old0.replace('\n', e)
        if s.count(old):
            return old, e
    return old0, '\n'


def check(name, edits):
    s = (root / name).read_bytes().decode('utf-8')
    if MARK in s:
        return
    for old0, _ in edits:
        old, _e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))


def patch(name, edits):
    p = root / name
    s = p.read_bytes().decode('utf-8')
    if MARK in s:
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


# The Controls guide's table names other patches' handlers by design: never a name clash (numbers still count there).
GUIDE = ('OmniControlsHelp.h', 'OmniControlsHelpShell.h')
_CPP_TOK = re.compile(r'//[^\n]*|/\*.*?\*/|R"([^()\\\s"]{0,16})\(.*?\)\1"|"(?:\\.|[^"\\\n])*"' + r"|'(?:\\.|[^'\\\n])*'", re.S)


def cpp_code(s):
    """C/C++ text without its // and /* */ comments (string, char and raw string literals kept; newlines kept, so line
    numbers stay): an id or name in another patch's notes (e.g. "834-839" in a generated header) is not a use."""
    return _CPP_TOK.sub(lambda m: m.group(0) if m.group(0)[0] in 'R"\'' else '\n' * m.group(0).count('\n'), s)


def ids_free():
    """Refuse when a settings row id we add is used in any entry file. Sibling apply_*.py files are not scanned: their
    notes list other patches' ids, and a numeric hit there would stop the title build."""
    pat = re.compile(r'(?<![\w.])(%s)(?![\w.])' % '|'.join(str(i) for i in ROW_IDS))
    hits = []
    for p in sorted(root.iterdir()):
        if p.suffix not in ('.h', '.cpp', '.inc') or p.name in NEW_FILES:
            continue
        s = p.read_text('utf-8', 'replace')
        if MARK in s:
            s = '\n'.join(l for l in s.splitlines() if MARK not in l)
        for n, line in enumerate(cpp_code(s).split('\n'), 1):
            if pat.search(line):
                hits.append('%s:%d' % (p.name, n))
    if hits:
        sys.exit('settings row ids %s are taken: %s' % (ROW_IDS, ', '.join(hits[:12])))


def main():
    need = (('OmniBrowser.cpp', 'OMNI_L2_CHORDS_V1', 'apply_l2_chords.py (base T)'),
            ('OmniFeatures3.h', 'OMNI_TAB_SWITCHER_V1', 'apply_tab_switcher.py'),
            ('OmniFeatures3.h', 'OMNI_OFFLINE_RETRY_V1', 'apply_offline_retry.py'),
            ('OmniBrowserSettings.h', 'OMNI_PAD_FEEDBACK_V1', 'apply_pad_feedback.py'))
    for name, mark, tool in need:
        if mark not in (root / name).read_bytes().decode('utf-8'):
            sys.exit('%s: %s missing: %s first' % (name, mark, tool))
    ob = (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8')
    if 'static bool omniL2Held' not in ob or 'omniL2ChordUsed' not in ob:
        sys.exit('OmniBrowser.cpp: omniL2Held / omniL2ChordUsed missing (OMNI_L2_CHORDS_V1)')
    if 'pageDidScroll' in ob and MARK not in ob:
        sys.exit('OmniBrowser.cpp: something already sets ui.pageDidScroll')
    ids_free()
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniScrollPlus.h', PURE, 'OmniTabSwitcher.h'),
            write_new('OmniScrollPlusShell.h', SHELL, 'OmniTabSwitcherShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK + ' (r2)')


main()
