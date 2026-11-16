#!/usr/bin/env python3
"""OMNI_OLED_CARE_V1 (2026-11-16): "OLED care" - less burn-in on OLED TVs (backlog E26). The system screensaver has
no hook for a title, so Omni does it itself.

What the user sees
  - Browser settings, after "Colour filter":
        "OLED care"          Off / On (default Off)                  Cross or D-pad left / right
        "Dim screen after"   5 min / 10 min / 20 min (default 10)    shown while OLED care is On
  - While On:
      1. After 20 s without input the top bar, the bottom button bar and the pointer fade to ~15 % opacity (1.2 s
         smoothstep, in 8/256 steps; Reduce motion: at once). Any input brings them back at once (the same pass).
         Not while Browser settings, the keyboard or an Omni overlay / dialog is open.
      2. Every 3 min the static UI drawn by Omni (the top bar with tabs / toolbar / quick-access row, the bottom button
         bar) moves by up to +-2 px (layout px) along a slow 24-step path (72 min; at most 1 px per axis per step).
      3. After N min (the sub-setting) without input AND with nothing playing in any tab, the screen goes black with a
         dim clock (night light's omniNlMinute(): the same local time as the Night light rows) and "Press any button".
         The clock moves to a new spot every minute. Any button / key / click / stick / trigger / touchpad wakes it;
         that press, and its release, are swallowed (nothing else sees them: not Omni, not the page, not the web
         Gamepad API). Never while a full-screen video, game mode (when apply_game_mode.py is in the tree), a
         hole-punched video, or any tab's audio / video plays: the wait starts again when it stops. If something starts
         playing while dimmed, the dim ends by itself.
  - Saved in /data/omni/oled-care.txt (omniIoQueue): "on\\t0|1", "dim\\t5|10|20". Self-test modes: inert.

Where each part is applied (the least risky place, chosen after reading the present-side passes)
  apply_magnifier_present.py / apply_colour_filter_present.py add compute passes over the title's whole composed
  canvas (page, panels and video in one image). A present-side shift cannot tell Omni's bars from the page, so it
  would shift the page too; it would also need a new shader, a second title patch and the GPU present. So everything
  here is shell-side and NO present-side part is needed (no apply_oled_care_present.py):
  - Fade and shift: omniDrawTopBar / omniDrawHintBar are wrapped (omniOcBarBegin at the start, omniOcBarEnd at the
    end). Begin saves the canvas rows under the bar (only while faded); End moves the bar's pixels inside its own
    rows (the outer 3 px rows keep the hairline edges; the exposed strip repeats the bar's background) and blends the
    bar over the saved rows with omniFadeEnd's arithmetic. Both draw paths (whole frame, OMNI_PERF_A_S4 regional) and
    the slide (drawn in place, then rows moved) call these two functions, so every frame shows the same thing. Page
    content is never moved (the page rows are not touched). With the zero-copy page the saved rows are transparent:
    the blend leaves premultiplied colour, as omni_zc_page.comp expects.
  - Hit-testing is unchanged: clicks, hover and the planner use today's positions; the drawn bar is at most 2 px
    (layout) off, far inside every hit area (>= 24 px) - the "applied when the frame is composed" option.
  - Pointer: omniDrawPointer's alpha (the Pointer opacity setting) times the fade.
  - Overlays / panels / toasts are NOT shifted: they have no common rectangle (omniOverlayDraw draws each layer
    itself), they are open only while used (they stop the fade), and the dim covers them when left open.
  - Dim: draw() returns early (omniOcDimDraw, right after the regional decision is taken): an opaque black canvas +
    the clock, recorded as a whole frame and presented. Opaque pixels hide the zero-copy page (the shader composes
    the page only under alpha < 1). While the dim frame is on the screen and the minute is the same, nothing is
    drawn or presented at all. Night light / colour filter / magnifier passes still run over it (black stays black).
  - Every state change (fade step, new shift step, dim on / off, wake) calls omniMarkDirty(omniDrFeature): a reason
    the regional planner does not know, so that frame is drawn whole; the planner's buffer-age check then sees the
    whole frame and keeps drawing whole until every buffer holds the new state.
  - Input: omniOcEvent is asked first in the event loop (after the draw flag, before omniChromeEvent / game mode /
    the gamepad): every input event counts as activity; while dimmed it swallows everything ("continue").
  - Idle: own timestamps (omniLastInput misses controller buttons). omniOcTick (from omniF3Tick after omniNlTick).

Pure part: OmniOledCare.h (kept here in tools/ and copied to engine/entry): settings, Idle (fadeK / dimDue),
shiftAt / shiftStep, shiftBand / blendRow, clockSpot, WakeGate (wake + swallow rules), texts.
Tested by tools/test_oled_care.cpp:  g++ -std=c++20 -Wall -Wextra -I. test_oled_care.cpp -o t && ./t
Shell side: OmniOledCareShell.h (written by this script, included from OmniFeatures3.h after OmniNightLightShell.h).
Namespace alias OOLC. Row ids 958, 959 (dispatched before the ">= 900" features-2 line).
Anchors (each once; every file keeps its own line endings; MARK makes each file idempotent, re-run prints "already"):
  OmniBrowser.cpp        the OmniNightLight.h include line (+ our pure include); the omniRmOn() declaration (+ ours);
                         omniDrawTopBar's first lines and its last line (omniMqDraw); omniDrawHintBar's body;
                         omniDrawPointer's alpha line (replaced); the omniStickQuietEvent line of the event loop
                         (+ omniOcEvent); draw()'s "omniRegion.active = false;" (+ omniOcDimDraw).
  OmniBrowserSettings.h  the omniNlSettingsInput declaration; the omniCfSettingsRows call; the omniCfRowId dispatch.
  OmniFeatures3.h        the OmniNightLightShell.h include line; the omniNlTick line of omniF3Tick.
Apply AFTER apply_night_light.py, apply_colour_filter.py, apply_reduce_motion.py (their lines are anchors). Game mode
may come before or after (checked with __has_include, as OmniSiteListShell.h does).
usage: apply_oled_care.py <engine tree>
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_OLED_CARE_V1'
HERE = Path(__file__).resolve().parent
if len(sys.argv) != 2:
    sys.exit('usage: apply_oled_care.py <engine tree>')
root = Path(sys.argv[1]) / 'engine' / 'entry'
IDS = ('958', '959')
NAMES = ('OOLC', 'omniOc[A-Z]', 'OmniOledCare', 'oled-care')

SHELL = r'''// OMNI_OLED_CARE_V1: "OLED care" (shell side). Included from OmniFeatures3.h (inside OmniBrowser.cpp's anonymous
// namespace, after OmniNightLightShell.h: omniNlMinute() gives the clock's time). The pure part is OmniOledCare.h; the
// reasons (why everything is shell-side, hit-testing, the regional planner) are in tools/apply_oled_care.py.
// Main thread only; the file is written by omniIoQueue.
#pragma once

namespace OOLC = OmniOledCare;
static OOLC::Settings omniOc;
static bool omniOcLoaded = false;
static OOLC::Idle omniOcIdle;
static OOLC::WakeGate omniOcGate;
static uint32_t omniOcK = 256;                 // bars / pointer opacity of 256 (256: as drawn)
static int omniOcDxPx = 0, omniOcDyPx = 0;     // the static UI's shift now, canvas pixels
static int omniOcStep = -1;                    // shift step shown (-1: none yet)
static bool omniOcDimShown = false;            // the dim frame is on the screen
static int omniOcDimMinute = -1;               // the minute it shows
static uint32_t omniOcNextClock = 0;
static std::vector<uint32_t> omniOcUnder;      // canvas rows under the bar being drawn (only while faded)
static int omniOcRow0 = 0, omniOcRow1 = 0;     // the bar being drawn (omniOcBarBegin .. omniOcBarEnd)

static void omniOcLoad()
{
    if (omniOcLoaded) return;
    omniOcLoaded = true;
    FILE* f = fopen(omniData(OOLC::kFileName).c_str(), "rb");
    if (!f) return;
    std::string text;
    char buf[512];
    size_t n;
    while ((n = fread(buf, 1, sizeof buf, f)) > 0 && long(text.size()) < OOLC::kMaxFileBytes) text.append(buf, n);
    fclose(f);
    omniOc = OOLC::parse(text);
}
static void omniOcWrite()
{
    if (omniTestMode()) return;
    omniIoQueue(omniData(OOLC::kFileName), OOLC::serialize(omniOc), false);
}
static bool omniOcActive() { omniOcLoad(); return omniOc.on && !omniTestMode(); }
static bool omniOcGameMode()
{
#if __has_include("OmniGameModeShell.h")
    return omniGmOn;   // OMNI_GAME_MODE_V1 (declared with it in OmniBrowser.cpp)
#else
    return false;
#endif
}
// Anything playing in any tab (UI-process cached media state, no IPC), or the hole-punched video.
static bool omniOcPlaying()
{
    if (OmniMedia::Hw::holePunchActive()) return true;
    for (auto& t : tabs)
        if (t->page && !t->crashed && (WKPageGetMediaState(t->page) & (kWKMediaIsPlayingAudio | kWKMediaIsPlayingVideo))) return true;
    return false;
}
static void omniOcSetK(uint32_t k)
{
    if (k == omniOcK) return;
    omniOcK = k;
    if (k >= 256) std::vector<uint32_t>().swap(omniOcUnder);   // nothing kept while not faded
    omniMarkDirty(omniDrFeature);   // a whole frame (see apply_oled_care.py)
}
static void omniOcSetDim(bool on)
{
    if (omniOcGate.dimmed() == on) return;
    omniOcGate.setDimmed(on);
    omniOcDimShown = false; omniOcDimMinute = -1;
    omniMarkDirty(omniDrFeature);
}

// From omniF3Tick (every pass). Off: one comparison after the first call.
static void omniOcTick(uint32_t now)
{
    if (!omniOcActive()) {
        if (omniOcK != 256 || omniOcDxPx || omniOcDyPx || omniOcGate.dimmed()) {
            omniOcGate.setDimmed(false); omniOcDimShown = false;
            omniOcDxPx = omniOcDyPx = 0; omniOcStep = -1;
            omniOcSetK(256);
            omniMarkDirty(omniDrFeature);
        }
        return;
    }
    // 1. the fade (not while a panel, the keyboard or an overlay is open)
    const bool panel = editing || settingsOpen || omniOverlayOpen();
    omniOcSetK(panel ? 256u : omniOcIdle.fadeK(now, omniRmOn()));
    // 2. the shift
    const int step = OOLC::shiftStep(now);
    if (step != omniOcStep) {
        omniOcStep = step;
        const OOLC::Offset o = OOLC::shiftAt(step);
        const int dx = OOLC::toCanvas(o.dx, displayScale), dy = OOLC::toCanvas(o.dy, displayScale);
        if (dx != omniOcDxPx || dy != omniOcDyPx) { omniOcDxPx = dx; omniOcDyPx = dy; omniMarkDirty(omniDrFeature); }
    }
    // 3. the dim (never over a full-screen video, game mode or anything playing)
    const bool blocked = pageFullscreen || omniOcGameMode() || omniOcPlaying();
    if (blocked) omniOcIdle.block(now);
    if (omniOcGate.dimmed()) {
        if (blocked) omniOcSetDim(false);
        else if (int32_t(now - omniOcNextClock) >= 0) {   // the clock: checked once a second, drawn when the minute changes
            omniOcNextClock = now + 1000;
            if (omniNlMinute() != omniOcDimMinute) { omniOcDimShown = false; omniMarkDirty(omniDrFeature); }
        }
    } else if (!blocked && omniOcIdle.dimDue(now, omniOc.dimMinutes)) {
        omniOcSetDim(true);
    }
}

// From the event loop, first (after the draw flag). true: the event is swallowed (the loop goes on to the next one).
static bool omniOcEvent(const SDL_Event& e)
{
    if (!omniOcGate.dimmed() && !omniOcGate.pending() && !omniOcActive()) return false;
    OOLC::Ev v;
    using K = OOLC::Kind;
    switch (e.type) {
    case SDL_CONTROLLERBUTTONDOWN: v = { K::Button, int(e.cbutton.which), int(e.cbutton.button) }; break;
    case SDL_CONTROLLERBUTTONUP: v = { K::ButtonUp, int(e.cbutton.which), int(e.cbutton.button) }; break;
    case SDL_KEYDOWN: v = { K::Key, 0, int(e.key.keysym.scancode) }; break;
    case SDL_KEYUP: v = { K::KeyUp, 0, int(e.key.keysym.scancode) }; break;
    case SDL_TEXTINPUT: case SDL_TEXTEDITING: v = { K::Text }; break;
    case SDL_MOUSEBUTTONDOWN: v = { K::MouseDown, int(e.button.which), int(e.button.button) }; break;
    case SDL_MOUSEBUTTONUP: v = { K::MouseUp, int(e.button.which), int(e.button.button) }; break;
    case SDL_MOUSEMOTION: v = { K::Motion }; break;
    case SDL_MOUSEWHEEL: v = { K::Wheel }; break;
    case SDL_CONTROLLERTOUCHPADDOWN: v = { K::TouchDown, int(e.ctouchpad.which), e.ctouchpad.touchpad * 16 + e.ctouchpad.finger }; break;
    case SDL_CONTROLLERTOUCHPADUP: v = { K::TouchUp, int(e.ctouchpad.which), e.ctouchpad.touchpad * 16 + e.ctouchpad.finger }; break;
    case SDL_CONTROLLERTOUCHPADMOTION: v = { K::TouchMotion, int(e.ctouchpad.which) }; break;
    case SDL_CONTROLLERAXISMOTION:
        if (e.caxis.axis == SDL_CONTROLLER_AXIS_TRIGGERLEFT || e.caxis.axis == SDL_CONTROLLER_AXIS_TRIGGERRIGHT)
            v = { K::Trigger, int(e.caxis.which), int(e.caxis.axis), int(e.caxis.value) };
        else v = { omniStickAxisLive(e.caxis) ? K::Stick : K::Raw, int(e.caxis.which), int(e.caxis.axis) };   // drift is not input
        break;
    case SDL_JOYAXISMOTION: case SDL_JOYBALLMOTION: case SDL_JOYHATMOTION: case SDL_JOYBUTTONDOWN: case SDL_JOYBUTTONUP:
    case SDL_CONTROLLERSENSORUPDATE: case SDL_SENSORUPDATE: v = { K::Raw }; break;
    default: return false;   // window, quit, devices, app events: never swallowed
    }
    const uint32_t now = SDL_GetTicks();
    const OOLC::Result r = omniOcGate.handle(v, now);
    if (r.input) { omniOcIdle.input(now); if (omniOcK != 256) omniOcSetK(256); }   // the bars come back in this pass
    if (r.wake) { omniOcDimShown = false; omniOcDimMinute = -1; omniMarkDirty(omniDrFeature); }
    return r.swallow;
}

// --- drawing ------------------------------------------------------------------------------------------------------
// Around omniDrawTopBar / omniDrawHintBar: canvas rows [y0, y1) are the bar's.
static void omniOcBarBegin(int y0, int y1)
{
    omniOcRow0 = omniOcRow1 = 0;
    if ((omniOcK >= 256 && !omniOcDxPx && !omniOcDyPx) || !canvas || !omniPix().ok) return;
    y0 = std::max(0, y0); y1 = std::min(canvas->h, y1);
    if (y1 <= y0) return;
    omniOcRow0 = y0; omniOcRow1 = y1;
    if (omniOcK >= 256) return;
    const size_t w = size_t(canvas->w);
    omniOcUnder.resize(w * size_t(y1 - y0));
    for (int j = y0; j < y1; ++j) memcpy(omniOcUnder.data() + size_t(j - y0) * w, omniRow(j), w * 4);
}
static void omniOcBarEnd()
{
    if (omniOcRow1 <= omniOcRow0) return;
    const int y0 = omniOcRow0, rows = omniOcRow1 - omniOcRow0, w = canvas->w;
    omniOcRow0 = omniOcRow1 = 0;
    OOLC::shiftBand(omniRow(y0), size_t(canvas->pitch) / 4, w, rows, omniOcDxPx, omniOcDyPx, physical(3));
    if (omniOcK < 256 && omniOcUnder.size() == size_t(w) * size_t(rows))
        for (int j = 0; j < rows; ++j) OOLC::blendRow(omniRow(y0 + j), omniOcUnder.data() + size_t(j) * size_t(w), w, omniOcK);
}
static uint8_t omniOcPointerAlpha(uint8_t alpha) { return omniOcK >= 256 ? alpha : OOLC::pointerAlpha(alpha, omniOcK); }
// From draw(), before anything is drawn: true while dimmed (the frame is the black clock screen, or nothing at all
// when that screen is already shown for this minute).
static bool omniOcDimDraw()
{
    if (!omniOcGate.dimmed()) return false;
    const int minute = omniNlMinute();
    if (omniOcDimShown && minute == omniOcDimMinute) return true;
    omniOcDimMinute = minute;
    SDL_FillRect(canvas, nullptr, SDL_MapRGBA(canvas->format, 0, 0, 0, 255));
    const OOLC::Spot s = OOLC::clockSpot(minute, width, height, 200, 70);
    const SDL_Color clock { OOLC::kClockGrey, OOLC::kClockGrey, OOLC::kClockGrey, 255 }, hint { OOLC::kHintGrey, OOLC::kHintGrey, OOLC::kHintGrey, 255 };
    omniLabel(ONL::hhmm(minute), float(s.x), float(s.y - 12), omniTitle, clock, 1);
    omniLabel(OOLC::kWakeHint, float(s.x), float(s.y + 20), omniCaption, hint, 1);
    omniRegion.changedKnown = false;   // recorded as a whole frame: the next normal draw is whole too
    omniFrameRecord(false);
    omniPresentFrame();
    omniOcDimShown = true;
    return true;
}

// --- Browser settings rows ----------------------------------------------------------------------------------------
static void omniOcSettingsRows(OmniFxPanel& p)
{
    omniOcLoad();
    OmniFxRow r; r.id = omniOcRowOn; r.label = "OLED care"; r.value = OOLC::onValue(omniOc.on); r.stepper = true;
    r.detail = OOLC::onDetail(omniOc.on);
    p.rows.push_back(r);
    if (!omniOc.on) return;
    OmniFxRow d; d.id = omniOcRowDim; d.label = "Dim screen after"; d.value = OOLC::dimValue(omniOc.dimMinutes); d.stepper = true;
    d.detail = OOLC::kDimDetail;
    p.rows.push_back(d);
}
static bool omniOcSettingsInput(int id, int b)
{
    const bool left = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT;
    if (b != SDL_CONTROLLER_BUTTON_A && !left && b != SDL_CONTROLLER_BUTTON_DPAD_RIGHT) return false;
    omniOcLoad();
    if (id == omniOcRowOn) omniOc.on = !omniOc.on;
    else if (id == omniOcRowDim) omniOc.dimMinutes = OOLC::stepDim(omniOc.dimMinutes, left ? -1 : 1);
    else return false;
    omniOcIdle.input(SDL_GetTicks());
    omniOcWrite();
    omniFxRefresh();
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniNightLight.h" // OMNI_NIGHT_LIGHT_V1: Night light schedule, warmth, fade, night-light.txt (pure)\n',
         '#include "OmniNightLight.h" // OMNI_NIGHT_LIGHT_V1: Night light schedule, warmth, fade, night-light.txt (pure)\n'
         '#include "OmniOledCare.h" // OMNI_OLED_CARE_V1: OLED care idle fade, shift cycle, dim clock, wake rules (pure)\n'),
        ('static bool omniRmOn(); // OMNI_REDUCE_MOTION_V1: Browser settings > "Reduce motion" (OmniReduceMotionShell.h, cached)\n',
         'static bool omniRmOn(); // OMNI_REDUCE_MOTION_V1: Browser settings > "Reduce motion" (OmniReduceMotionShell.h, cached)\n'
         '// OMNI_OLED_CARE_V1 (OmniOledCareShell.h): bar fade + shift around the two bars, pointer fade, the dim, input first.\n'
         'static void omniOcBarBegin(int y0, int y1);\n'
         'static void omniOcBarEnd();\n'
         'static uint8_t omniOcPointerAlpha(uint8_t alpha);\n'
         'static bool omniOcDimDraw();\n'
         'static bool omniOcEvent(const SDL_Event& e);\n'),
        ('static void omniDrawTopBar()\n{\n    const OmniTheme& T = omniTheme();\n    fill(0, 0, width, 52, T.bg);\n',
         'static void omniDrawTopBar()\n{\n    const OmniTheme& T = omniTheme();\n'
         '    omniOcBarBegin(0, physical(omniTopH())); // OMNI_OLED_CARE_V1: rows under the bar (only while faded)\n'
         '    fill(0, 0, width, 52, T.bg);\n'),
        ('    omniMqDraw(); // OMNI_MQ_NATIVE_V1: own reserved row, never over page content\n}\n',
         '    omniMqDraw(); // OMNI_MQ_NATIVE_V1: own reserved row, never over page content\n'
         '    omniOcBarEnd(); // OMNI_OLED_CARE_V1: the bar shifted (3 min cycle) and faded (20 s idle)\n}\n'),
        ('static void omniDrawHintBar()\n{\n    omniHintBarBg(); // OMNI_HUD_ASTRA_V1\n'
         '    if (settingsOpen) omniSettingsHints(); else if (editing) omniKbHints(); else omniBrowseHints(); // OMNI_KEYBOARD_V2, OMNI_POLISH_V1 (was controllerHints())\n}\n',
         'static void omniDrawHintBar()\n{\n'
         '    omniOcBarBegin(physical(height - bottom), canvas->h); // OMNI_OLED_CARE_V1\n'
         '    omniHintBarBg(); // OMNI_HUD_ASTRA_V1\n'
         '    if (settingsOpen) omniSettingsHints(); else if (editing) omniKbHints(); else omniBrowseHints(); // OMNI_KEYBOARD_V2, OMNI_POLISH_V1 (was controllerHints())\n'
         '    omniOcBarEnd(); // OMNI_OLED_CARE_V1: shifted and faded as the top bar\n}\n'),
        ('        const uint8_t alpha = omniPtrAlpha(); // OMNI_POINTER_STYLE_V1: opacity setting\n',
         '        const uint8_t alpha = omniOcPointerAlpha(omniPtrAlpha()); // OMNI_POINTER_STYLE_V1: opacity setting; OMNI_OLED_CARE_V1: x the idle fade\n'),
        ('        if (!omniStickQuietEvent(event)) omniShellDirty = true; // OMNI_SHELL_DRAW_V1; OMNI_STICK_DEADZONE_V1: a stick inside its dead zone asks for nothing\n',
         '        if (!omniStickQuietEvent(event)) omniShellDirty = true; // OMNI_SHELL_DRAW_V1; OMNI_STICK_DEADZONE_V1: a stick inside its dead zone asks for nothing\n'
         '        if (omniOcEvent(event)) continue; // OMNI_OLED_CARE_V1: activity; while dimmed every input is swallowed (the waking press too)\n'),
        ('    const bool omniRegional = omniRegion.active && !pageFullscreen;\n    omniRegion.active = false;\n',
         '    const bool omniRegional = omniRegion.active && !pageFullscreen;\n    omniRegion.active = false;\n'
         '    if (omniOcDimDraw()) return; // OMNI_OLED_CARE_V1: the black clock screen (drawn and presented there, or already shown)\n'),
    ],
    'OmniBrowserSettings.h': [
        ('static bool omniNlSettingsInput(int id, int b);\n',
         'static bool omniNlSettingsInput(int id, int b);\n'
         'constexpr int omniOcRowOn = 958, omniOcRowDim = 959; // OMNI_OLED_CARE_V1 (OmniOledCareShell.h)\n'
         'static void omniOcSettingsRows(OmniFxPanel& p);\n'
         'static bool omniOcSettingsInput(int id, int b);\n'),
        ('    omniCfSettingsRows(p); // OMNI_COLOUR_FILTER_V1: Colour filter\n',
         '    omniCfSettingsRows(p); // OMNI_COLOUR_FILTER_V1: Colour filter\n'
         '    omniOcSettingsRows(p); // OMNI_OLED_CARE_V1: OLED care, Dim screen after\n'),
        ('    if (r.id == omniCfRowId) return omniCfSettingsInput(r.id, b); // OMNI_COLOUR_FILTER_V1 (before the >= 900 rows)\n',
         '    if (r.id == omniCfRowId) return omniCfSettingsInput(r.id, b); // OMNI_COLOUR_FILTER_V1 (before the >= 900 rows)\n'
         '    if (r.id == omniOcRowOn || r.id == omniOcRowDim) return omniOcSettingsInput(r.id, b); // OMNI_OLED_CARE_V1 (before the >= 900 rows)\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniNightLightShell.h" // OMNI_NIGHT_LIGHT_V1\n',
         '#include "OmniNightLightShell.h" // OMNI_NIGHT_LIGHT_V1\n'
         '#include "OmniOledCareShell.h" // OMNI_OLED_CARE_V1 (after night light: its clock)\n'),
        ('    omniNlTick(now);    // OMNI_NIGHT_LIGHT_V1: schedule check every second, the 2 s fade\n',
         '    omniNlTick(now);    // OMNI_NIGHT_LIGHT_V1: schedule check every second, the 2 s fade\n'
         '    omniOcTick(now);    // OMNI_OLED_CARE_V1: idle fade, shift step, the dim\n'),
    ],
}

NEEDS = {
    'OmniBrowser.cpp': ('OMNI_NIGHT_LIGHT_V1', 'OMNI_REDUCE_MOTION_V1', 'OMNI_POINTER_STYLE_V1'),
    'OmniBrowserSettings.h': ('OMNI_NIGHT_LIGHT_V1', 'OMNI_COLOUR_FILTER_V1'),
    'OmniFeatures3.h': ('OMNI_NIGHT_LIGHT_V1',),
}


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
SKIP_SIBLINGS = ('apply_controls_help.py',)
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
    mine = {'OmniOledCare.h', 'OmniOledCareShell.h'}
    for f in sorted(HERE.glob('apply_*.py')):
        if f.name == Path(__file__).name or f.name in SKIP_SIBLINGS:
            continue
        src = f.read_text(encoding='utf-8', errors='replace')
        if MARK in src:   # a copy or a later revision of this patch
            continue
        m = name.search(code_only(src))   # numeric ids: engine tree only (a sibling's notes list other patches' ids)
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
                sys.exit('%s: %s missing: apply its patch first' % (fname, need))
    if MARK not in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8'):
        ids_free()
    for fname, edits in EDITS.items():   # every anchor is checked before anything is written
        check(fname, edits)
    pure = (HERE / 'OmniOledCare.h').read_text(encoding='utf-8')
    if MARK not in pure:
        sys.exit('OmniOledCare.h: %s missing' % MARK)
    msgs = [write_new('OmniOledCare.h', pure, 'OmniNightLight.h'),
            write_new('OmniOledCareShell.h', SHELL, 'OmniNightLightShell.h')]
    msgs += [patch(fname, edits) for fname, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
