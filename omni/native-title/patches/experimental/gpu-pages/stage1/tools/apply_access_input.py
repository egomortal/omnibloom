#!/usr/bin/env python3
"""OMNI_ACCESS_INPUT_V1 (2026-11-16): motor-accessibility options for Omni's holds and chords (Browser settings).

What the user sees
  Browser settings, after "Reduce motion" (D-pad left / right or Cross step, Triangle puts the row back to its default;
  saved in access-input.txt as "sticky-l2 off / hold-time normal / repeat-delay normal"):
      "Sticky L2"      Off / On
      "Hold time"      Normal / Long (0.9 s) / Short (0.3 s)
      "Repeat delay"   Normal / Long / Very long / No repeat
  Defaults are exactly today's timings (Normal routes to the old constants, the clock is SDL_GetTicks() itself).
  Test modes: always the defaults (self-tests measure the normal timings; the rows say so).

  Sticky L2 (On): tap L2 while browsing and let go with no chord used: a small "L2" chip ("LT" on Xbox pads) shows at
    the top left of the page and L2 counts as held for the next button: L2 + Square copy, Triangle paste, Cross Options,
    Circle Browser settings, D-pad up / down zoom, R3 screenshot, L3 magnifier, R1 / L1 the tab switcher, right stick
    page up / down (held: to the top / bottom), remapped L2 chords (OMNI_BUTTON_MAP_V1) - all through their own code,
    which sees omniL2Held (or, for the two that read the axis, omniOainLatched()). The latch ends with the next button
    press (any button: a non-chord button acts as usual and ends it), 3 s without one, a second L2 tap (its release is
    then an ordinary L2 let-go: with the tab switcher up, that shows the chosen tab), or leaving the browsing context.
    While the tab switcher strip is up or an L2 + stick push is still held, the latch waits (its 3 s restart after).
    Holding L2 as before still works the same.
    Trade-off: with Sticky L2 On, a plain L2 tap latches instead of being the Media downloads "saved links" tap
    (OMNI_L2_CHORDS_V1's omniL2Pending); with it Off nothing changes.
  Scope (only the browsing context latches; elsewhere L2 is untouched): an active, not crashed tab, no keyboard /
    page editing / text target, no Browser settings, not full screen (there L2 alone leaves full screen, as before),
    nothing over the page (omniOverlayOpen: panels, menus, modals, image viewer ...), no find bar, not YouTube TV keys,
    not the PDF reader owning the triggers, not game mode (when built), not a test mode. The latch only keeps
    omniL2Held true: the trigger axis itself is never faked, so the keyboard's L2 / R2 word moves, the PDF reader and
    image viewer zoom, YouTube TV, the Gamepad API (OmniGamepad.h) and game mode read the real L2 as before; and any of
    those contexts opening ends a latch at once (omniOainTick).

  Hold time: every hold detection goes through omniHoldMs(kind) (or, where the threshold sits inside another patch's
    pure struct, omniHoldClock(kind): that struct is fed a clock that runs normalMs / holdMs as fast, so its own
    `now - start >= normalMs` is met after holdMs real ms; 64-bit underneath, no wrap glitch):
      kind          today   Short  Long   site
      Cross         500     300    900    hold Cross: page menu, link menu, Tabs panel tab menu (OmniFeatures.h omniFxTick)
      Accent        450     300    900    hold Cross on a keyboard letter: accents (OKBL::kHoldMs; omniKblTick)
      Circle        500     300    900    hold Circle: Back history (OBFL::kHoldMs; OmniBfListShell.h begin / tick)
      AddonToggle   600     360    1080   hold on the add-ons quick row: on / off everywhere (OmniAddons.h omniAdTick)
      StickEnd      600     360    1080   L2 + right stick still pushed: top / bottom (OSCP::kHoldMs; omniScpStick)
      GameExit      1000    1000   1800   Options + Create: leave game mode (OGMM::kExitHoldMs; only when
                                          OmniGameModeShell.h is in the tree: never shorter, a game is left by accident)
    Not holds (left alone): the hold-Cross spinner's 150 ms show delay, the paint hold, notice timings, double-press
    windows, the L1 + R1 media chord (presses, no hold time), the PDF reader's L2 / R2 zoom repeat.

  Repeat delay (the keyboard's hold-to-repeat, OMNI_KEYBOARD_V2, omniKbButton / omniKbTick; nothing else in Omni
    auto-repeats a button): through omniRepeatMs(First | Rate, today's ms)
      held button         first 380 ms, then 60 / 90 (D-pad) / 150 (Square / Cross after 12)
      L2 / R2 word move   first 400 ms, then 110
      right-stick caret   first 380 ms, then 70
    Normal: unchanged. Long: first x1.75, rate x1.5. Very long: first x2.5, rate x2. No repeat: never repeats (press
    again; the stick caret moves again when pushed again).

Pure part: engine/entry/OmniAccessInput.h (from tools/OmniAccessInput.h: hold table, scaled clock, repeat table, the
  Sticky L2 state machine, access-input.txt, row texts). Tests: tools/test_access_input.cpp
  (g++ -std=c++20 -Wall -Wextra -Werror -I. test_access_input.cpp -o t && ./t [<tree>/engine/entry]; with the tree it
  also checks the replaced constants are today's and each site is routed).
Shell part: engine/entry/OmniAccessInputShell.h (written by this script; included from OmniBrowser.cpp after
  OmniBfListShell.h), namespace alias OAIN, names omniOain*, omniHoldMs, omniHoldClock, omniRepeatMs.
Ids: Browser settings rows 821 / 822 / 823 (OAIN::kRowSticky / kRowHold / kRowRepeat), checked unused in the tree's
  code (comments stripped); dispatched before the >= 300 rows.

Anchors (each exactly once; whole lines only, so no `//` ever lands after a line-prefix anchor; MARK makes each file
idempotent; CRLF / LF kept):
  OmniBrowser.cpp       the OmniBfList.h include line (pure include after); the ORMO alias line (OAIN alias +
                        declarations after); the OmniBfListShell.h include line (shell include after); omniKblTick's
                        OKBL::holdOpens line (replaced); omniKbButton's `omniKbRepeatNext = SDL_GetTicks() + 380;`,
                        omniKbTick's repeat / triggerNext / stickNext lines (replaced); omniL2Track's head (+ the sticky
                        axis hook); omniL2Chord's head (+ omniOainButton)
  OmniFeatures.h        omniQaShotChord's L2 axis line (+ latched); omniFxTick's `>= 500` hold line (replaced); the
                        omniBflTick(); call line in omniFxTick (+ omniOainTick)
  OmniMagnifierShell.h  omniMagL2's axis line (+ latched)
  OmniBfListShell.h     h.begin(..., SDL_GetTicks()) and the h.tick(SDL_GetTicks(), ...) line (scaled clock)
  OmniScrollPlusShell.h omniScpGesture.update(wheel, SDL_GetTicks()) (scaled clock)
  OmniAddons.h          omniAdTick's `now - omniAdHoldStart >= 600` line (replaced)
  OmniBrowserSettings.h the omniRmSettingsInput declaration (+ ours), the omniRmSettingsRow(p) call (+ rows), the
                        ORMO::kRowId dispatch line (ours before it)
  OmniSettingsSearch.h  the "animation" synonym line ("hold", "repeat", "accessibility" before it)
  OmniGameModeShell.h   (only when present) omniGmChord.due(now), .edge(..., SDL_GetTicks()), .swallowAfterExit(...)
Controls guide (OmniControlsHelp.h) is not edited here; the notes for it are in the report.
Apply LAST (after apply_bf_list.py, apply_reduce_motion.py, apply_tab_switcher.py, apply_scroll_plus.py,
  apply_magnifier.py, apply_quick_actions.py, apply_kb_layouts.py, apply_l2_chords.py, apply_settings_search.py and
  apply_game_mode.py when built): it touches thresholds those patches define. Re-run after apply_game_mode.py adds it.
usage: apply_access_input.py <engine tree>   (anchored, idempotent, keeps each file's line endings; re-run: "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_ACCESS_INPUT_V1'
HERE = Path(__file__).resolve().parent
if len(sys.argv) != 2:
    sys.exit('usage: apply_access_input.py <engine tree>')
root = Path(sys.argv[1]) / 'engine' / 'entry'
IDS = ('821', '822', '823')
NAMES = ('OAIN', 'omniOain', 'OmniAccessInput', 'OMNI_ACCESS_INPUT', 'omniHoldMs', 'omniHoldClock', 'omniRepeatMs',
         'access-input')

SHELL = r'''// OMNI_ACCESS_INPUT_V1: motor-accessibility input options (shell side): Browser settings > Sticky L2, Hold time,
// Repeat delay. Included from OmniBrowser.cpp after OmniBfListShell.h (the tab switcher, scroll plus, L2 chords and
// overlay layers are all defined by then). The pure part is OmniAccessInput.h (alias OAIN, declared next to ORMO in
// OmniBrowser.cpp with omniHoldMs / omniHoldClock / omniRepeatMs, which earlier code calls); the reasons are in
// tools/apply_access_input.py. Main thread only; the file is written by omniIoQueue.
#pragma once

static OAIN::Settings omniOainSet;
static bool omniOainLoaded = false;
static OAIN::Sticky omniOainSticky;
static OAIN::Clock omniOainClock;

// Cached after the first call (one file read): the holds and the keyboard ask often. Test modes: the defaults.
static const OAIN::Settings& omniOainSettings()
{
    if (!omniOainLoaded) {
        omniOainLoaded = true;
        if (!omniTestMode()) {
            if (FILE* f = fopen(omniData(OAIN::kFileName).c_str(), "rb")) {
                char buf[256];
                const size_t n = fread(buf, 1, sizeof buf, f);
                fclose(f);
                omniOainSet = OAIN::parse(std::string(buf, n));
            }
        }
    }
    return omniOainSet;
}

// --- Hold time ---------------------------------------------------------------------------------------------------------
static uint32_t omniHoldMs(OAIN::Hold kind) { return OAIN::holdMs(kind, omniOainSettings().hold); }
// For a threshold inside another patch's pure struct (fed instead of SDL_GetTicks()): at Normal it IS SDL_GetTicks().
static uint32_t omniHoldClock(OAIN::Hold kind)
{
    const uint32_t now = SDL_GetTicks();
    const uint64_t real = omniOainClock.unwrap(now);
    const uint32_t normal = OAIN::normalMs(kind), hold = omniHoldMs(kind);
    return hold == normal ? now : OAIN::scaledClock(real, normal, hold);
}

// --- Repeat delay --------------------------------------------------------------------------------------------------------
static uint32_t omniRepeatMs(OAIN::Rep kind, uint32_t normalMs) { return OAIN::repeatMs(omniOainSettings().repeat, kind, normalMs); }

// --- Sticky L2 -------------------------------------------------------------------------------------------------------------
static bool omniOainLatched() { return omniOainSticky.latched; }
// The browsing context: where L2 chords run and a plain L2 tap may latch.
static bool omniOainBrowsing()
{
    Tab* t = active();
    return t && !t->crashed && !editing && !pageEditing && !omniKbTarget && !settingsOpen && !pageFullscreen
        && !omniOverlayOpen() && !omniFindBarOpen() && !omniTestMode() && !omniYtTvKeysActive()
        && !omniPdfvOwnsTriggers()@GAME@;
}
static void omniOainEnded(OAIN::End e)
{
    if (e == OAIN::End::None) return;
    omniL2Held = false;      // the latch held it; the pad has been up since the tap
    omniL2Pending = false;
    omniShellDirty = true;
    fprintf(stderr, "OMNI ACCESS INPUT: sticky L2 %s\n", OAIN::endName(e)); fflush(stderr);
}
// From omniL2Track, first (every L2 axis event): true = handled here, omniL2Track does nothing more with it.
static bool omniOainL2Axis(const SDL_ControllerAxisEvent& event)
{
    const OAIN::AxisAct a = omniOainSticky.axis(event.value, omniL2Held, omniL2ChordUsed, omniOainSettings().stickyL2,
        omniOainBrowsing(), SDL_GetTicks());
    switch (a) {
    case OAIN::AxisAct::Pass: return false;
    case OAIN::AxisAct::Ignore: return true;
    case OAIN::AxisAct::Latch:   // a plain tap: L2 stays "held" for the chords; not a saved-links tap
        omniL2Pending = false;
        omniShellDirty = true;
        fprintf(stderr, "OMNI ACCESS INPUT: sticky L2 latched\n"); fflush(stderr);
        return true;
    case OAIN::AxisAct::Cancel:  // pressed again: physically held now; its release is a plain let-go (no saved-links tap)
        omniL2Held = true;
        omniL2ChordUsed = true;
        omniShellDirty = true;
        fprintf(stderr, "OMNI ACCESS INPUT: sticky L2 cancelled\n"); fflush(stderr);
        return true;
    }
    return false;
}
// From omniL2Chord, first (every button event): a press while latched ends the latch after this event's handlers ran.
static void omniOainButton(const SDL_ControllerButtonEvent& event)
{
    if (event.type == SDL_CONTROLLERBUTTONDOWN) omniOainSticky.button();
}
// From omniFxTick, every pass: used / 3 s / context left. The strip and a held L2 + stick push keep it.
static void omniOainTick()
{
    if (!omniOainSticky.latched) return;
    const bool busy = omniTsw.open || omniScpGesture.dir != 0;
    omniOainEnded(omniOainSticky.tick(SDL_GetTicks(), omniOainSettings().stickyL2, omniOainBrowsing(), omniL2ChordUsed, busy));
}
// The chip: top left of the page while latched (redrawn on latch / end only).
static void omniOainDraw()
{
    if (!omniOainSticky.latched) return;
    const OmniTheme& T = omniTheme();
    const int w = 58, h = 32, x = 18, y = omniPageTop() + 14;
    omniShadow(x, y, w, h, h / 2, 10, 110, 2);
    fillRounded(x, y, w, h, h / 2, T.accent);
    omniLabel(OAIN::chipLabel(playStationIcons), x + w / 2.f, y + h / 2.f, omniSmallBold, T.accentInk, 1);
}
[[maybe_unused]] static const bool omniOainLayers = [] {
    omniOverlayLayers().push_back({ omniOainLatched, nullptr, nullptr, nullptr, omniOainDraw, false });   // never blocks
    return true;
}();

// --- Browser settings rows (OAIN::kRowSticky .. kRowRepeat, declared in OmniBrowserSettings.h) ------------------------
static void omniOainSettingsRows(OmniFxPanel& p)
{
    const OAIN::Settings& s = omniOainSettings();
    for (int id : { OAIN::kRowSticky, OAIN::kRowHold, OAIN::kRowRepeat }) {
        OmniFxRow r;
        r.id = id;
        r.label = OAIN::rowLabel(id);
        r.value = OAIN::rowValue(id, s);
        r.stepper = true;
        r.detail = omniTestMode() ? std::string("Normal in test modes") : std::string(OAIN::rowDetail(id));
        p.rows.push_back(r);
    }
}
static bool omniOainSettingsInput(int id, int b)
{
    if (id != OAIN::kRowSticky && id != OAIN::kRowHold && id != OAIN::kRowRepeat) return false;
    if (b != SDL_CONTROLLER_BUTTON_DPAD_LEFT && b != SDL_CONTROLLER_BUTTON_DPAD_RIGHT && b != SDL_CONTROLLER_BUTTON_A
        && b != SDL_CONTROLLER_BUTTON_Y) return false;
    if (omniTestMode()) { notice("Input timings stay Normal in test modes"); return true; }
    const OAIN::Settings s = OAIN::step(omniOainSettings(), id, b == SDL_CONTROLLER_BUTTON_DPAD_LEFT ? -1 : 1,
        b == SDL_CONTROLLER_BUTTON_Y);   // Triangle: this row back to its default
    omniOainSet = s;
    omniOainLoaded = true;
    if (!s.stickyL2 && omniOainSticky.latched) { omniOainSticky.cancel(); omniOainEnded(OAIN::End::Context); }
    omniIoQueue(omniData(OAIN::kFileName), OAIN::serialize(s), false);
    omniShellDirty = true;
    omniFxRefresh();
    notice(OAIN::noticeText(id, s));
    return true;
}
'''
GAME_ON = ' && !omniGmOn'   # OMNI_GAME_MODE_V1 in the tree: game mode gives L2 to the page

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniBfList.h" // OMNI_BF_LIST_V1: Back history list model and hold timing (pure)\n',
         '#include "OmniBfList.h" // OMNI_BF_LIST_V1: Back history list model and hold timing (pure)\n'
         '#include "OmniAccessInput.h" // OMNI_ACCESS_INPUT_V1: hold time, repeat delay, Sticky L2 (pure)\n'),
        ('namespace ORMO = OmniReduceMotion; // OMNI_REDUCE_MOTION_V1\n',
         'namespace ORMO = OmniReduceMotion; // OMNI_REDUCE_MOTION_V1\n'
         'namespace OAIN = OmniAccessInput; // OMNI_ACCESS_INPUT_V1 (definitions in OmniAccessInputShell.h)\n'
         'static uint32_t omniHoldMs(OAIN::Hold kind); // OMNI_ACCESS_INPUT_V1: Browser settings > Hold time, per hold\n'
         'static uint32_t omniHoldClock(OAIN::Hold kind); // OMNI_ACCESS_INPUT_V1: SDL_GetTicks() at Normal, else scaled\n'
         'static uint32_t omniRepeatMs(OAIN::Rep kind, uint32_t normalMs); // OMNI_ACCESS_INPUT_V1: Repeat delay\n'
         'static bool omniOainLatched(); // OMNI_ACCESS_INPUT_V1: Sticky L2 latched (L2 counts as held)\n'
         'static bool omniOainL2Axis(const SDL_ControllerAxisEvent& event); // OMNI_ACCESS_INPUT_V1\n'
         'static void omniOainButton(const SDL_ControllerButtonEvent& event); // OMNI_ACCESS_INPUT_V1\n'
         'static void omniOainTick(); // OMNI_ACCESS_INPUT_V1\n'),
        ('#include "OmniBfListShell.h" /* OMNI_BF_LIST_V1: Back history (hold Circle, Options > Browse) */\n',
         '#include "OmniBfListShell.h" /* OMNI_BF_LIST_V1: Back history (hold Circle, Options > Browse) */\n'
         '#include "OmniAccessInputShell.h" /* OMNI_ACCESS_INPUT_V1: Sticky L2, Hold time, Repeat delay */\n'),
        ('    if (!OKBL::holdOpens(omniKbl.pendingSince, SDL_GetTicks())) return;\n',
         '    if (int32_t(SDL_GetTicks() - omniKbl.pendingSince) < int32_t(omniHoldMs(OAIN::Hold::Accent))) return; // OMNI_ACCESS_INPUT_V1: was OKBL::holdOpens (OKBL::kHoldMs = Normal)\n'),
        ('        omniKbRepeatNext = SDL_GetTicks() + 380;\n',
         '        omniKbRepeatNext = SDL_GetTicks() + omniRepeatMs(OAIN::Rep::First, 380); // OMNI_ACCESS_INPUT_V1: Repeat delay (was + 380)\n'),
        ('            omniKbRepeatNext = now + (words ? 150 : pad ? 90 : 60);\n',
         '            omniKbRepeatNext = now + omniRepeatMs(OAIN::Rep::Rate, words ? 150 : pad ? 90 : 60); // OMNI_ACCESS_INPUT_V1: Repeat delay\n'),
        ('            triggerNext[i] = now + (trigger[i] ? 110 : 400);\n',
         '            triggerNext[i] = now + omniRepeatMs(trigger[i] ? OAIN::Rep::Rate : OAIN::Rep::First, trigger[i] ? 110 : 400); // OMNI_ACCESS_INPUT_V1: Repeat delay\n'),
        ('        stickNext = now + (dir != stickDir ? 380 : 70);\n',
         '        stickNext = now + omniRepeatMs(dir != stickDir ? OAIN::Rep::First : OAIN::Rep::Rate, dir != stickDir ? 380 : 70); // OMNI_ACCESS_INPUT_V1: Repeat delay\n'),
        ('static void omniL2Track(const SDL_ControllerAxisEvent& event)\n{\n'
         '    if (event.axis != SDL_CONTROLLER_AXIS_TRIGGERLEFT) return;\n',
         'static void omniL2Track(const SDL_ControllerAxisEvent& event)\n{\n'
         '    if (event.axis != SDL_CONTROLLER_AXIS_TRIGGERLEFT) return;\n'
         '    if (omniOainL2Axis(event)) return; // OMNI_ACCESS_INPUT_V1: Sticky L2 (a plain tap latches; latched, the next press ends it)\n'),
        ('static bool omniL2Chord(const SDL_ControllerButtonEvent& event)\n{\n',
         'static bool omniL2Chord(const SDL_ControllerButtonEvent& event)\n{\n'
         '    omniOainButton(event); // OMNI_ACCESS_INPUT_V1: a press while Sticky L2 is latched ends the latch (after this event)\n'),
    ],
    'OmniFeatures.h': [
        ('    if (!pad || SDL_GameControllerGetAxis(pad, SDL_CONTROLLER_AXIS_TRIGGERLEFT) < 20000) return false;\n',
         '    if (!pad || (SDL_GameControllerGetAxis(pad, SDL_CONTROLLER_AXIS_TRIGGERLEFT) < 20000 && !omniOainLatched())) return false; // OMNI_ACCESS_INPUT_V1: or Sticky L2\n'),
        ('        else if (SDL_GetTicks() - h.start >= 500) { h.fired = true; omniShellDirty = true; if (!omniTgHoldFire()) omniFxContextQuery(); } // OMNI_TAB_GROUPS_V1: Tabs panel: the Group menu\n',
         '        else if (SDL_GetTicks() - h.start >= omniHoldMs(OAIN::Hold::Cross)) { h.fired = true; omniShellDirty = true; if (!omniTgHoldFire()) omniFxContextQuery(); } // OMNI_TAB_GROUPS_V1: Tabs panel: the Group menu; OMNI_ACCESS_INPUT_V1: Hold time (was 500)\n'),
        ("    omniBflTick(); // OMNI_BF_LIST_V1: hold Circle timer; drops the list's items once it is closed\n",
         "    omniBflTick(); // OMNI_BF_LIST_V1: hold Circle timer; drops the list's items once it is closed\n"
         '    omniOainTick(); // OMNI_ACCESS_INPUT_V1: Sticky L2 used / timed out / context left\n'),
    ],
    'OmniMagnifierShell.h': [
        ('    return pad && SDL_GameControllerGetAxis(pad, SDL_CONTROLLER_AXIS_TRIGGERLEFT) >= OMAG::kTriggerHeld;\n',
         '    return pad && (SDL_GameControllerGetAxis(pad, SDL_CONTROLLER_AXIS_TRIGGERLEFT) >= OMAG::kTriggerHeld || omniOainLatched()); // OMNI_ACCESS_INPUT_V1: or Sticky L2\n'),
    ],
    'OmniBfListShell.h': [
        ('        h.begin(int(event.which), SDL_GetTicks());\n',
         '        h.begin(int(event.which), omniHoldClock(OAIN::Hold::Circle)); // OMNI_ACCESS_INPUT_V1: Hold time (OBFL::kHoldMs on a scaled clock)\n'),
        ('        else omniBflResolve(h.tick(SDL_GetTicks(), SDL_GameControllerGetButton(pad, SDL_CONTROLLER_BUTTON_B) != 0));\n',
         '        else omniBflResolve(h.tick(omniHoldClock(OAIN::Hold::Circle), SDL_GameControllerGetButton(pad, SDL_CONTROLLER_BUTTON_B) != 0)); // OMNI_ACCESS_INPUT_V1\n'),
    ],
    'OmniScrollPlusShell.h': [
        ('    const OSCP::Action a = omniScpGesture.update(wheel, SDL_GetTicks());\n',
         '    const OSCP::Action a = omniScpGesture.update(wheel, omniHoldClock(OAIN::Hold::StickEnd)); // OMNI_ACCESS_INPUT_V1: Hold time (OSCP::kHoldMs on a scaled clock)\n'),
    ],
    'OmniAddons.h': [
        ('        else if (now - omniAdHoldStart >= 600) { omniAdHoldButton = -1; omniAdToggleGlobal(*q); if (omniFxPanelOpen()) omniFxRefresh(); }\n',
         '        else if (now - omniAdHoldStart >= omniHoldMs(OAIN::Hold::AddonToggle)) { omniAdHoldButton = -1; omniAdToggleGlobal(*q); if (omniFxPanelOpen()) omniFxRefresh(); } // OMNI_ACCESS_INPUT_V1: Hold time (was 600)\n'),
    ],
    'OmniBrowserSettings.h': [
        ('static bool omniRmSettingsInput(int b);\n',
         'static bool omniRmSettingsInput(int b);\n'
         'static void omniOainSettingsRows(OmniFxPanel& p); // OMNI_ACCESS_INPUT_V1: Sticky L2, Hold time, Repeat delay (OmniAccessInputShell.h, rows OAIN::kRowSticky .. kRowRepeat)\n'
         'static bool omniOainSettingsInput(int id, int b); // OMNI_ACCESS_INPUT_V1\n'),
        ('    omniRmSettingsRow(p); // OMNI_REDUCE_MOTION_V1: Reduce motion (Off / On)\n',
         '    omniRmSettingsRow(p); // OMNI_REDUCE_MOTION_V1: Reduce motion (Off / On)\n'
         '    omniOainSettingsRows(p); // OMNI_ACCESS_INPUT_V1: Sticky L2, Hold time, Repeat delay\n'),
        ('    if (r.id == ORMO::kRowId) return omniRmSettingsInput(b); // OMNI_REDUCE_MOTION_V1 (before the >= 300 rows)\n',
         '    if (r.id >= OAIN::kRowSticky && r.id <= OAIN::kRowRepeat) return omniOainSettingsInput(r.id, b); // OMNI_ACCESS_INPUT_V1 (before the >= 300 rows)\n'
         '    if (r.id == ORMO::kRowId) return omniRmSettingsInput(b); // OMNI_REDUCE_MOTION_V1 (before the >= 300 rows)\n'),
    ],
    'OmniSettingsSearch.h': [
        ('        { "animation", { "reduce motion", "smooth scrolling", nullptr } }, // OMNI_REDUCE_MOTION_V1\n',
         '        { "hold", { "hold time", "sticky l2", "repeat delay", nullptr } }, // OMNI_ACCESS_INPUT_V1\n'
         '        { "repeat", { "repeat delay", nullptr } }, // OMNI_ACCESS_INPUT_V1\n'
         '        { "accessibility", { "sticky l2", "hold time", "repeat delay", "reduce motion", "high contrast", "large pointer", nullptr } }, // OMNI_ACCESS_INPUT_V1\n'
         '        { "animation", { "reduce motion", "smooth scrolling", nullptr } }, // OMNI_REDUCE_MOTION_V1\n'),
    ],
}
EDITS_GAME = {
    'OmniGameModeShell.h': [
        ('    if (omniGmTakesPad() && omniGmChord.due(now)) omniGmExit(t);\n',
         '    (void)now; if (omniGmTakesPad() && omniGmChord.due(omniHoldClock(OAIN::Hold::GameExit))) omniGmExit(t); // OMNI_ACCESS_INPUT_V1: Hold time (OGMM::kExitHoldMs on a scaled clock)\n'),
        ('        if (!omniGmOn) return omniGmChord.swallowAfterExit(int(e.cbutton.which), b, down, SDL_GetTicks());\n',
         '        if (!omniGmOn) return omniGmChord.swallowAfterExit(int(e.cbutton.which), b, down, omniHoldClock(OAIN::Hold::GameExit)); // OMNI_ACCESS_INPUT_V1\n'),
        ('        omniGmChord.edge(int(e.cbutton.which), b, down, SDL_GetTicks());\n',
         '        omniGmChord.edge(int(e.cbutton.which), b, down, omniHoldClock(OAIN::Hold::GameExit)); // OMNI_ACCESS_INPUT_V1: the same clock as due()\n'),
    ],
}
NEEDS = {'OmniBrowser.cpp': ('OMNI_BF_LIST_V1', 'OMNI_REDUCE_MOTION_V1', 'OMNI_L2_CHORDS_V1', 'OMNI_TAB_SWITCHER_V1',
                             'OMNI_KB_LAYOUTS_V1', 'OMNI_KEYBOARD_V2'),
         'OmniFeatures.h': ('OMNI_BF_LIST_V1', 'OMNI_QUICK_ACTIONS_V1', 'OMNI_TAB_GROUPS_V1'),
         'OmniMagnifierShell.h': ('OMNI_MAGNIFIER_V1',),
         'OmniScrollPlusShell.h': ('OMNI_SCROLL_PLUS_V1',),
         'OmniTabSwitcherShell.h': ('OMNI_TAB_SWITCHER_V1',),
         'OmniAddons.h': ('omniAdHoldStart',),
         'OmniBrowserSettings.h': ('OMNI_REDUCE_MOTION_V1',),
         'OmniSettingsSearch.h': ('OMNI_REDUCE_MOTION_V1',)}


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
    mine = {'OmniAccessInput.h', 'OmniAccessInputShell.h'}
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
        if not (root / fname).exists():
            sys.exit('%s missing: apply its patch first' % fname)
        s = (root / fname).read_bytes().decode('utf-8')
        for need in needs:
            if need not in s:
                sys.exit('%s: %s missing: apply its patch first' % (fname, need))
    edits = dict(EDITS)
    game = root / 'OmniGameModeShell.h'
    game_on = game.exists() and 'OMNI_GAME_MODE_V1' in game.read_bytes().decode('utf-8')
    if game_on:
        edits.update(EDITS_GAME)
    if MARK not in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8'):
        ids_free()
    for fname, e in edits.items():   # every anchor is checked before anything is written
        check(fname, e)
    pure = (HERE / 'OmniAccessInput.h').read_text(encoding='utf-8')
    if MARK not in pure:
        sys.exit('OmniAccessInput.h: %s missing' % MARK)
    shell = SHELL.replace('@GAME@', GAME_ON if game_on else '')
    msgs = [write_new('OmniAccessInput.h', pure, 'OmniQuickMenu.h'),
            write_new('OmniAccessInputShell.h', shell, 'OmniFeatures.h')]
    msgs += [patch(fname, e) for fname, e in edits.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK
          + (' (game mode exit routed)' if game_on else ''))


main()
