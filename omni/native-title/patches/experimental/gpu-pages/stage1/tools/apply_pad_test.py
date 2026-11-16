#!/usr/bin/env python3
"""OMNI_PAD_TEST_V1 (2026-11-16): "Controller test" page: every button, both sticks with Omni's dead zone, drift.

What the user sees
  - Options > More: a row "Controller test" right after "Browser tools" (disabled when Omni's built-in pages are off).
    Cross opens omni://pages/controller/index.html (pages bundle controller/) in a new tab (in the shown tab when it is
    the new-tab page or no new tab is possible).
  - The page shows, live: every button (lit while held: face buttons, D-pad, L1 / R1, L3 / R3, Create, Options, PS, mic,
    touchpad press), both sticks as a dot in a circle with a trail and the raw SDL values (-32768..32767), the dead-zone
    circle Omni really uses (OmniPointerFeel.h omniStickDzLeft / omniStickDzRight at the "Stick dead zone" setting's
    size), triggers as bars (% and raw 0..32767), touchpad press and finger positions, battery (SDL power level; "Not
    reported by the console" when SDL says unknown).
  - Drift: when a stick rests (never past half travel) for 3 s, "Drift at rest: 4.2% (x 3.0%, y 2.9%)" = the largest
    distance from the centre over those 3 s. With both sticks measured, a text suggestion names the smallest
    "Stick dead zone" size that clears both by 3 % (or says the current one fits / Extra large is not enough), pointing
    at Browser settings > Stick dead zone. The setting is never changed by the page (text only; no new setting).
  - While the page is shown and nothing of Omni's is open over it, the controller is the page's alone: no Omni shortcut
    fires (no hold Cross, L1 / R1 tab switching, L2 chords, trigger taps, button map, R3 close tab, pointer / scrolling;
    the pointer is hidden). Two ways out: Options opens Omni's menu as everywhere (the menu then takes the controller
    as usual; closing it gives the controller back to the page), and holding Circle for 1 s leaves the page (Back, or
    the start page when the tab has no earlier page); the page shows the hold's progress. A USB keyboard is untouched.

Input path (checked in the tree): OMNI_GAMEPAD_V1 (OmniGamepad.h) does name omni://pages tabs as the Gamepad API's
  target (omniGamepadTick excludes only the Master Control origin and YouTube TV), but only while "Web pages can use the
  controller" is on, it has no touchpad button (omniGpButton maps no SDL_CONTROLLER_BUTTON_TOUCHPAD), no touch points,
  no battery and no raw values. So the shell pushes the state itself: OmniPadTestShell.h reads SDL (the active pad,
  `controller`) and calls window.omniPadTest(<numbers-only JSON>) through WKPageEvaluateJavaScriptInMainFrame, only
  while the controller page is the shown tab and the take-over is active, on change, at most 30 times a second
  (OPADT::Pusher: 34 ms apart, one evaluation in flight, a 1 s heartbeat that also re-reads the battery). No page text
  ever reaches the script. The page falls back to navigator.getGamepads() when no push came for 2.5 s (a desktop
  browser while developing; the touchpad / battery rows say they need Omni).
Input gate: game mode's take-over (apply_game_mode.py) is reused as it is built: the same event-loop slot (a line right
  after omniGmEvent's: true = the event is the page's alone, the Gamepad API still gets it), the same "Omni UI over the
  page" test (omniGmUiOpen) and the same stick-tick gate (the `!omniGmTakesPad()` line, + `&& !omniPadtTakesPad()`).
  On switching on / off: omniShoulderReset() + a fresh hold-Cross state, as game mode does. The hold's Circle release
  after leaving is swallowed (hold Circle is Back on release elsewhere: OMNI_BF_LIST_V1).

Pure part: engine/entry/OmniPadTest.h (ids, page address, push JSON, rate limiter, leave hold, gate verdict), tested by
  tools/test_pad_test.cpp:  g++ -std=c++20 -Wall -Wextra -Werror -I<tree>/engine/entry test_pad_test.cpp -o t && ./t
Page: pages bundle controller/ (index.html, style.css, model.js, app.js; routes.json entry), tested by
  tools/test_pad_test_page.cjs (node, fake input + fake document).
Shell part: engine/entry/OmniPadTestShell.h (included from OmniBrowser.cpp after OmniPdfViewerShell.h, i.e. after
  OmniPages.h and OmniFeatures3.h's game-mode shell). Alias OPADT, names omniPadt*. Id: Options row 8612 (checked unused
  in every apply_*.py and the tree; >= 900, so its quick-menu hook sits before the `r.id >= 900` line).

Anchors (whole lines, exactly once each; MARK makes each file idempotent; line endings kept):
  OmniBrowser.cpp   the omniGmOn declaration (omniPadtOn + omniPadtTick declaration after); the OmniGameMode.h include
                    (pure include after); the OmniPdfViewerShell.h include (shell include after); omniDrawPointer's
                    game-mode line (pointer hidden after); the omniGmEvent line of the event loop (ours after); the stick
                    tick's game-mode `if` (replaced: + && !omniPadtTakesPad())
  OmniFeatures3.h   the omniGmTick line of omniF3Tick (omniPadtTick after)
  OmniQuickMenu.h   the omniBflQuickAction declaration (ours after); the "Browser tools" add() line (row after); the
                    omniBflQuickAction input line (ours after)
Apply AFTER apply_game_mode.py (its lines are anchors and its gate is reused).
usage: apply_pad_test.py <engine tree>   (re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_PAD_TEST_V1'
HERE = Path(__file__).resolve().parent
if len(sys.argv) != 2:
    sys.exit('usage: apply_pad_test.py <engine tree>')
root = Path(sys.argv[1]) / 'engine' / 'entry'
IDS = ('8612',)
NAMES = ('OPADT', 'omniPadt', 'OmniPadTest', 'OMNI_PAD_TEST')

PURE = r'''// OMNI_PAD_TEST_V1: the pure part of the Controller test page's shell side (no SDL, no WebKit). The shell side is
// OmniPadTestShell.h, the page is the pages bundle's controller/; the reasons are in tools/apply_pad_test.py.
// Tested on the host with g++ (tools/test_pad_test.cpp).
#pragma once
#include <cstdint>
#include <string>

namespace OmniPadTest {

constexpr int kQuickRowId = 8612;                 // Options > More: "Controller test"
constexpr const char* kPagePath = "controller/index.html";       // as omniPagesOpen takes it
constexpr const char* kPagePrefix = "omni://pages/controller/";
constexpr uint32_t kPushMinMs = 34;               // at most 30 pushes a second
constexpr uint32_t kHeartbeatMs = 1000;           // an unchanged state is sent again (and the battery read) once a second
constexpr uint32_t kStaleMs = 500;                // a push whose answer never came: the next one may go after this
constexpr uint32_t kLeaveHoldMs = 1000;           // Circle held this long leaves the page
constexpr int kButtons = 21, kAxes = 6, kFingers = 2, kSizes = 4;
// SDL_GameControllerButton values (static_assert'ed in the shell)
constexpr int kCross = 0, kCircle = 1, kOptions = 6, kTouchpad = 20;

inline bool isPage(const std::string& url) { return url.compare(0, std::char_traits<char>::length(kPagePrefix), kPagePrefix) == 0; }

struct Snap {
    bool pad = false;                  // a controller is connected
    uint32_t buttons = 0;              // bit n = SDL button n held
    int axes[kAxes] = {};              // SDL raw: sticks -32768..32767, triggers 0..32767
    bool touch[kFingers] = {};
    int tx[kFingers] = {}, ty[kFingers] = {};   // 0..1000
    int battery = -1;                  // SDL_JoystickPowerLevel (-1 unknown .. 4 wired)
    int dz = 1;                        // the "Stick dead zone" setting's index
    int dzl[kSizes] = {}, dzr[kSizes] = {};     // radii per size, 1/10000 of full travel
    int holdMs = 0;                    // Circle held for (100 ms steps), 0 none
    bool operator==(const Snap& o) const
    {
        if (pad != o.pad || buttons != o.buttons || battery != o.battery || dz != o.dz || holdMs != o.holdMs) return false;
        for (int i = 0; i < kAxes; ++i) if (axes[i] != o.axes[i]) return false;
        for (int i = 0; i < kFingers; ++i) if (touch[i] != o.touch[i] || tx[i] != o.tx[i] || ty[i] != o.ty[i]) return false;
        for (int i = 0; i < kSizes; ++i) if (dzl[i] != o.dzl[i] || dzr[i] != o.dzr[i]) return false;
        return true;
    }
    bool operator!=(const Snap& o) const { return !(*this == o); }
};

inline int clampi(int v, int lo, int hi) { return v < lo ? lo : v > hi ? hi : v; }

// Numbers only (nothing from a page or a URL): {"v":1,"pad":1,"b":..,"ax":[..],"tp":[[on,x,y],..],"bat":..,"dz":..,"dzl":[..],"dzr":[..],"hold":..}
inline std::string json(const Snap& s)
{
    std::string o = "{\"v\":1,\"pad\":" + std::string(s.pad ? "1" : "0") + ",\"b\":" + std::to_string(s.buttons) + ",\"ax\":[";
    for (int i = 0; i < kAxes; ++i) o += (i ? "," : "") + std::to_string(clampi(s.axes[i], -32768, 32767));
    o += "],\"tp\":[";
    for (int i = 0; i < kFingers; ++i)
        o += std::string(i ? "," : "") + "[" + (s.touch[i] ? "1" : "0") + "," + std::to_string(clampi(s.tx[i], 0, 1000)) + ","
            + std::to_string(clampi(s.ty[i], 0, 1000)) + "]";
    o += "],\"bat\":" + std::to_string(clampi(s.battery, -1, 4)) + ",\"dz\":" + std::to_string(clampi(s.dz, 0, kSizes - 1)) + ",\"dzl\":[";
    for (int i = 0; i < kSizes; ++i) o += (i ? "," : "") + std::to_string(clampi(s.dzl[i], 1, 9999));
    o += "],\"dzr\":[";
    for (int i = 0; i < kSizes; ++i) o += (i ? "," : "") + std::to_string(clampi(s.dzr[i], 1, 9999));
    return o + "],\"hold\":" + std::to_string(clampi(s.holdMs, 0, 5000)) + "}";
}
// The one script the shell runs in the page: '1' = the page took it.
inline std::string script(const Snap& s)
{
    return "(function(){var f=window.omniPadTest;return typeof f==='function'&&f(" + json(s) + ")===true?'1':'0'})()";
}

// When to push: on change, at most every kPushMinMs, one evaluation in flight (kStaleMs gives up on a lost answer),
// a heartbeat every kHeartbeatMs.
class Pusher {
public:
    bool due(uint32_t now, bool changed) const
    {
        if (!m_sent) return true;
        const uint32_t since = now - m_at;
        if (m_pending && since < kStaleMs) return false;
        if (since < kPushMinMs) return false;
        return changed || since >= kHeartbeatMs;
    }
    void sent(uint32_t now) { m_sent = true; m_pending = true; m_at = now; }
    void answered() { m_pending = false; }
    void reset() { m_sent = false; m_pending = false; m_at = 0; }
private:
    bool m_sent = false, m_pending = false;
    uint32_t m_at = 0;
};

// Holding Circle (one pad) for kLeaveHoldMs leaves the page; the hold's own release is swallowed afterwards.
class LeaveHold {
public:
    // Every Circle edge while the take-over is active.
    void edge(int pad, bool down, uint32_t now)
    {
        if (down) { if (m_pad < 0) { m_pad = pad; m_since = now; } return; }
        if (pad == m_pad) reset();
    }
    bool due(uint32_t now) const { return m_pad >= 0 && !m_drain && uint32_t(now - m_since) >= kLeaveHoldMs; }
    void fired() { m_drain = true; }
    bool draining() const { return m_drain; }
    // Take-over off (the page left): true = swallow this button event (the hold's release).
    bool swallowAfter(int pad, int button, bool down)
    {
        if (!m_drain || pad != m_pad || button != kCircle) return false;
        if (!down) reset();
        return true;
    }
    int heldMs(uint32_t now) const   // for the page's progress bar, 100 ms steps (fewer pushes)
    {
        if (m_pad < 0 || m_drain) return 0;
        const uint32_t d = now - m_since;
        return int(d >= kLeaveHoldMs ? kLeaveHoldMs : d / 100 * 100);
    }
    void reset() { m_pad = -1; m_since = 0; m_drain = false; }
private:
    int m_pad = -1;
    uint32_t m_since = 0;
    bool m_drain = false;
};

// The take-over's verdict for one controller event (true = the page's alone; Omni does nothing with it).
enum Kind : int { kButtonEvent, kAxisEvent, kTouchEvent, kOtherEvent };
inline bool swallow(Kind k, int button)
{
    if (k == kButtonEvent) return button != kOptions;   // Options: Omni's menu, as everywhere
    return k == kAxisEvent || k == kTouchEvent;
}

inline const char* leftNotice(bool ps) { return ps ? "Left the controller test (held Circle)" : "Left the controller test (held B)"; }

} // namespace OmniPadTest
'''

SHELL = r'''// OMNI_PAD_TEST_V1: the Controller test page (shell side). Included from OmniBrowser.cpp after OmniPdfViewerShell.h
// (after OmniPages.h and the game-mode shell, inside OmniBrowser.cpp's anonymous namespace). The pure part is
// OmniPadTest.h, the page the pages bundle's controller/; the reasons are in tools/apply_pad_test.py. Main thread only.
// omniPadtOn (OmniBrowser.cpp, next to omniGmOn): the page is the shown tab. omniPadtTick (from omniF3Tick) switches it,
// leaves on the Circle hold and pushes the pad's state; the event loop asks omniPadtEvent right after omniGmEvent.
#pragma once

namespace OPADT = OmniPadTest;
static_assert(OPADT::kCross == int(SDL_CONTROLLER_BUTTON_A) && OPADT::kCircle == int(SDL_CONTROLLER_BUTTON_B)
    && OPADT::kOptions == int(SDL_CONTROLLER_BUTTON_START) && OPADT::kTouchpad == int(SDL_CONTROLLER_BUTTON_TOUCHPAD)
    && OPADT::kButtons <= int(SDL_CONTROLLER_BUTTON_MAX) && OPADT::kButtons <= 32, "OMNI_PAD_TEST_V1: SDL button indices");
static_assert(int(SDL_JOYSTICK_POWER_UNKNOWN) == -1 && int(SDL_JOYSTICK_POWER_WIRED) == 4, "OMNI_PAD_TEST_V1: SDL power levels");
static_assert(sizeof(omniStickDzLeft) / sizeof(omniStickDzLeft[0]) == OPADT::kSizes
    && sizeof(omniStickDzRight) / sizeof(omniStickDzRight[0]) == OPADT::kSizes, "OMNI_PAD_TEST_V1: dead-zone sizes");

static OPADT::Pusher omniPadtPusher;
static OPADT::LeaveHold omniPadtHold;
static OPADT::Snap omniPadtLast;
static WKPageRef omniPadtLastPage = nullptr;
static int omniPadtBattery = -1;
static uint32_t omniPadtBatteryAt = 0;
static bool omniPadtBatteryKnown = false;
static uintptr_t omniPadtGen = 0;

static bool omniPadtShown(Tab* t)
{
    return t && !t->crashed && t->omniPagesTab && OPADT::isPage(t->url) && omniShoulderFocused && !pageFullscreen && !omniTestMode();
}
// The take-over: the page is shown and nothing of Omni's is over it (game mode's own test).
static bool omniPadtTakesPad() { return omniPadtOn && !omniGmUiOpen(); }

static void omniPadtSwitch(bool on)
{
    omniPadtOn = on;
    if (!omniPadtHold.draining()) omniPadtHold.reset();
    omniPadtPusher.reset();
    omniPadtLastPage = nullptr;
    omniPadtBatteryKnown = false;
    omniShoulderReset();              // L1 / R1 / trigger states start from neutral again
    omniFxHoldState = OmniFxHold();   // no half-done hold Cross
    omniShellDirty = true;
    fprintf(stderr, "OMNI_PAD_TEST_V1: controller test %s\n", on ? "shown (Omni shortcuts off but Options / hold Circle)" : "left"); fflush(stderr);
}

static OPADT::Snap omniPadtRead(uint32_t now)
{
    OPADT::Snap s;
    s.dz = omniStickDzIndex();
    for (int i = 0; i < OPADT::kSizes; ++i) {
        s.dzl[i] = int(std::lround(omniStickDzLeft[i] * 10000.f));
        s.dzr[i] = int(std::lround(omniStickDzRight[i] * 10000.f));
    }
    s.holdMs = omniPadtHold.heldMs(now);
    SDL_GameController* c = controller;
    if (!c || !SDL_GameControllerGetAttached(c)) return s;
    s.pad = true;
    for (int b = 0; b < OPADT::kButtons; ++b)
        if (SDL_GameControllerGetButton(c, static_cast<SDL_GameControllerButton>(b))) s.buttons |= 1u << b;
    for (int a = 0; a < OPADT::kAxes; ++a) s.axes[a] = SDL_GameControllerGetAxis(c, static_cast<SDL_GameControllerAxis>(a));
    if (SDL_GameControllerGetNumTouchpads(c) > 0)
        for (int f = 0; f < OPADT::kFingers && f < SDL_GameControllerGetNumTouchpadFingers(c, 0); ++f) {
            Uint8 down = 0; float x = 0, y = 0, pressure = 0;
            if (SDL_GameControllerGetTouchpadFinger(c, 0, f, &down, &x, &y, &pressure) || !down) continue;
            s.touch[f] = true; s.tx[f] = int(x * 1000.f + 0.5f); s.ty[f] = int(y * 1000.f + 0.5f);
        }
    if (!omniPadtBatteryKnown || uint32_t(now - omniPadtBatteryAt) >= OPADT::kHeartbeatMs) {   // at most once a second
        omniPadtBatteryKnown = true; omniPadtBatteryAt = now;
        SDL_Joystick* j = SDL_GameControllerGetJoystick(c);
        omniPadtBattery = j ? int(SDL_JoystickCurrentPowerLevel(j)) : -1;
    }
    s.battery = omniPadtBattery;
    return s;
}
static void omniPadtPushDone(WKTypeRef, WKErrorRef, void* context)
{
    if (reinterpret_cast<uintptr_t>(context) == omniPadtGen) omniPadtPusher.answered();
}
static void omniPadtPush(Tab* t, uint32_t now)
{
    const OPADT::Snap s = omniPadtRead(now);
    const bool changed = s != omniPadtLast || t->page != omniPadtLastPage;
    if (!omniPadtPusher.due(now, changed)) return;
    omniPadtLast = s;
    omniPadtLastPage = t->page;
    omniPadtPusher.sent(now);
    auto source = adoptWK(WKStringCreateWithUTF8CString(OPADT::script(s).c_str()));
    WKPageEvaluateJavaScriptInMainFrame(t->page, source.get(), reinterpret_cast<void*>(++omniPadtGen), omniPadtPushDone);
}
static void omniPadtLeave(Tab* t)
{
    omniPadtHold.fired();
    notice(OPADT::leftNotice(playStationIcons));
    if (WKPageCanGoBack(t->page)) WKPageGoBack(t->page);
    else if (!omniPagesNewTab(t)) omniFxHome();
}

// omniF3Tick(): the page shown or not, the Circle hold, the push.
static void omniPadtTick(uint32_t now)
{
    Tab* t = active();
    const bool want = omniPadtShown(t);
    if (want != omniPadtOn) omniPadtSwitch(want);
    if (!omniPadtTakesPad()) {
        if (omniPadtOn && !omniPadtHold.draining()) omniPadtHold.reset();   // Omni's menu took the controller
        return;
    }
    if (omniPadtHold.due(now)) { omniPadtLeave(t); return; }
    omniPadtPush(t, now);
}

// The event loop, right after omniGmEvent: true = the event is the page's alone (the caller still feeds the Gamepad API).
static bool omniPadtEvent(const SDL_Event& e)
{
    const bool button = e.type == SDL_CONTROLLERBUTTONDOWN || e.type == SDL_CONTROLLERBUTTONUP;
    if (!omniPadtTakesPad())
        return button && omniPadtHold.swallowAfter(int(e.cbutton.which), e.cbutton.button, e.type == SDL_CONTROLLERBUTTONDOWN);
    if (e.type == SDL_CONTROLLERDEVICEREMOVED) { omniPadtHold.reset(); return false; }
    if (button) {
        if (e.cbutton.button == SDL_CONTROLLER_BUTTON_B) omniPadtHold.edge(int(e.cbutton.which), e.type == SDL_CONTROLLERBUTTONDOWN, SDL_GetTicks());
        return OPADT::swallow(OPADT::kButtonEvent, e.cbutton.button);
    }
    if (e.type == SDL_CONTROLLERAXISMOTION) return OPADT::swallow(OPADT::kAxisEvent, -1);
    if (e.type == SDL_CONTROLLERTOUCHPADDOWN || e.type == SDL_CONTROLLERTOUCHPADUP || e.type == SDL_CONTROLLERTOUCHPADMOTION)
        return OPADT::swallow(OPADT::kTouchEvent, -1);
    return false;
}

// --- Options > More: "Controller test" ------------------------------------------------------------------------------
static void omniPadtQuickRow(OmniFxPanel& p)
{
    OmniFxRow r; r.id = OPADT::kQuickRowId; r.label = "Controller test";
    r.enabled = omniPagesEnabled() && active() != nullptr;
    r.value = r.enabled ? std::string("Buttons, sticks, drift") : std::string();
    p.rows.push_back(r);
}
static bool omniPadtQuickAction(int id)
{
    if (id != OPADT::kQuickRowId) return false;
    omniFxCloseAll();
    Tab* t = active();
    if (!t || OPADT::isPage(t->url)) return true;
    Tab* target = t->omniNewTabPage || omniF3TabsFull() ? t : newTab();
    if (!target) target = t;
    if (!omniPagesOpen(target, OPADT::kPagePath)) notice("Controller test needs Omni's built-in pages");
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('static bool omniGmOn = false;                // OMNI_GAME_MODE_V1: the shown tab is in game mode (OmniGameModeShell.h, omniGmTick)\n',
         'static bool omniGmOn = false;                // OMNI_GAME_MODE_V1: the shown tab is in game mode (OmniGameModeShell.h, omniGmTick)\n'
         'static bool omniPadtOn = false;              // OMNI_PAD_TEST_V1: the Controller test page is the shown tab (OmniPadTestShell.h)\n'
         'static void omniPadtTick(uint32_t now);      // OMNI_PAD_TEST_V1: from omniF3Tick\n'),
        ('#include "OmniGameMode.h" // OMNI_GAME_MODE_V1: Game mode per site (pure)\n',
         '#include "OmniGameMode.h" // OMNI_GAME_MODE_V1: Game mode per site (pure)\n'
         '#include "OmniPadTest.h" // OMNI_PAD_TEST_V1: Controller test page (pure)\n'),
        ('#include "OmniPdfViewerShell.h" /* OMNI_PDF_VIEWER_V1: PDFs open in the reader (after OmniPages.h) */\n',
         '#include "OmniPdfViewerShell.h" /* OMNI_PDF_VIEWER_V1: PDFs open in the reader (after OmniPages.h) */\n'
         '#include "OmniPadTestShell.h" /* OMNI_PAD_TEST_V1: Controller test page (after OmniPages.h and the game-mode shell) */\n'),
        ('    if (omniGmOn) return; // OMNI_GAME_MODE_V1: no pointer in game mode\n',
         '    if (omniGmOn) return; // OMNI_GAME_MODE_V1: no pointer in game mode\n'
         '    if (omniPadtOn && !settingsOpen && !omniOverlayOpen()) return; // OMNI_PAD_TEST_V1: no pointer on the Controller test page\n'),
        ('        if (omniGmEvent(event)) { omniSleepWake(event.type); omniGamepadEvent(event); continue; } // OMNI_GAME_MODE_V1: the page\'s alone (exit chord: omniGmTick)\n',
         '        if (omniGmEvent(event)) { omniSleepWake(event.type); omniGamepadEvent(event); continue; } // OMNI_GAME_MODE_V1: the page\'s alone (exit chord: omniGmTick)\n'
         '        if (omniPadtEvent(event)) { omniSleepWake(event.type); omniGamepadEvent(event); continue; } // OMNI_PAD_TEST_V1: the Controller test page\'s alone (Options / hold Circle: omniPadtTick)\n'),
        ('    if (controller && !editing && !omniGmTakesPad()) { // OMNI_GAME_MODE_V1: the sticks are the page\'s in game mode\n',
         '    if (controller && !editing && !omniGmTakesPad() && !omniPadtTakesPad()) { // OMNI_GAME_MODE_V1: the sticks are the page\'s in game mode; OMNI_PAD_TEST_V1: and on the Controller test page\n'),
    ],
    'OmniFeatures3.h': [
        ('    omniGmTick(now);    // OMNI_GAME_MODE_V1: game mode of the shown tab, the exit chord\n',
         '    omniGmTick(now);    // OMNI_GAME_MODE_V1: game mode of the shown tab, the exit chord\n'
         '    omniPadtTick(now);  // OMNI_PAD_TEST_V1: Controller test page: take-over, hold Circle to leave, state push (<= 30 Hz)\n'),
    ],
    'OmniQuickMenu.h': [
        ('static bool omniBflQuickAction(int id); // OMNI_BF_LIST_V1\n',
         'static bool omniBflQuickAction(int id); // OMNI_BF_LIST_V1\n'
         'static void omniPadtQuickRow(OmniFxPanel& p); // OMNI_PAD_TEST_V1 (OmniPadTestShell.h): Controller test (More)\n'
         'static bool omniPadtQuickAction(int id); // OMNI_PAD_TEST_V1\n'),
        ('    add(omniQmTools, "Browser tools", true);\n',
         '    add(omniQmTools, "Browser tools", true);\n'
         '    omniPadtQuickRow(p); // OMNI_PAD_TEST_V1: Controller test\n'),
        ('    if (omniBflQuickAction(r.id)) return true; // OMNI_BF_LIST_V1: Back history (before the >= 900 rows)\n',
         '    if (omniBflQuickAction(r.id)) return true; // OMNI_BF_LIST_V1: Back history (before the >= 900 rows)\n'
         '    if (omniPadtQuickAction(r.id)) return true; // OMNI_PAD_TEST_V1: Controller test (before the >= 900 rows)\n'),
    ],
}
NEEDS = {'OmniBrowser.cpp': ('OMNI_GAME_MODE_V1', 'OMNI_PDF_VIEWER_V1', 'OMNI_GAMEPAD_V1', 'OMNI_STICK_DEADZONE_V1'),
         'OmniFeatures3.h': ('OMNI_GAME_MODE_V1',),
         'OmniQuickMenu.h': ('OMNI_BF_LIST_V1',)}


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
    data = text.replace('\r\n', '\n').replace('\n', nl).encode('utf-8')
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


def code_only(src):
    """A sibling apply_*.py without its comments and module docstring (line numbers kept): names mentioned only in its
    notes are not a use. Numeric ids are never looked for in siblings (their notes list other patches' id ranges)."""
    import io
    import tokenize
    cut, first = [], True
    try:
        for t in tokenize.generate_tokens(io.StringIO(src).readline):
            if t.type == tokenize.COMMENT or (first and t.type == tokenize.STRING):
                cut.append((t.start, t.end))
            if t.type not in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT,
                              tokenize.ENCODING):
                first = False
    except (tokenize.TokenError, SyntaxError):
        return ''.join(r for r in src.splitlines(True) if not r.lstrip().startswith('#'))
    starts = [0] + [i + 1 for i, c in enumerate(src) if c == '\n']   # tokenize's rows end at '\n' only
    out = list(src)
    for (r0, c0), (r1, c1) in cut:
        for i in range(starts[r0 - 1] + c0, starts[r1 - 1] + c1):
            if out[i] not in '\r\n':
                out[i] = ' '
    return ''.join(out)


def ids_free():
    """Before a first apply: no other patch or tree file uses this patch's ids or names."""
    word = re.compile(r'\b(%s)\b' % '|'.join(IDS))
    name = re.compile('|'.join(NAMES))
    mine = {'OmniPadTest.h', 'OmniPadTestShell.h'}
    for f in sorted(HERE.glob('apply_*.py')):
        if f.name == Path(__file__).name:
            continue
        if f.name == 'apply_controls_help.py' or MARK in f.read_text(encoding='utf-8', errors='replace'):   # OMNI_SIBLING_SKIP: the guide quotes names; a patch built on this one uses them
            continue
        t = code_only(f.read_text(encoding='utf-8', errors='replace'))
        m = name.search(t)   # numeric ids: engine tree only (a sibling's notes list other patches' ids)
        if m:
            sys.exit('%s already uses %r: pick other ids / names' % (f.name, m.group(0)))
    for f in sorted(root.iterdir()):
        if f.name in mine or f.suffix not in ('.h', '.cpp', '.inc'):
            continue
        t = f.read_bytes().decode('utf-8', errors='replace')
        c = cpp_code(t)
        m = word.search(c) or (None if f.name in GUIDE else name.search(c))
        if m and MARK not in t:
            sys.exit('%s already uses %r: pick other ids / names' % (f.name, m.group(0)))


def main():
    for fname, needs in NEEDS.items():
        s = (root / fname).read_bytes().decode('utf-8')
        for need in needs:
            if need not in s:
                sys.exit('%s: %s missing: apply its patch first (apply_game_mode.py comes before this one)' % (fname, need))
    if MARK not in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8'):
        ids_free()
    for fname, edits in EDITS.items():   # every anchor is checked before anything is written
        check(fname, edits)
    msgs = [write_new('OmniPadTest.h', PURE, 'OmniGameMode.h'),
            write_new('OmniPadTestShell.h', SHELL, 'OmniGameModeShell.h')]
    msgs += [patch(fname, edits) for fname, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
