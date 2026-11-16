#!/usr/bin/env python3
"""OMNI_PAD_FEEDBACK_V1 (2026-11-16): "Controller light & rumble" - small DualSense touches, opt-in (default Off).

What the title can use (audited 2026-11-16, no import gate change needed):
  - SDL 2.30.12 (static libSDL2.a in the PS5 payload SDK). Its PS5 joystick driver (src/joystick/ps5/SDL_ps5joystick.c)
    reports SDL_JOYCAP_LED | SDL_JOYCAP_RUMBLE and implements
        PS5_JoystickSetLED  -> scePadSetLightBar(handle, {r, g, b, 255})
        PS5_JoystickRumble  -> scePadSetVibration(handle, {low/256, high/256})   (SDL's core stops it after the duration)
    so SDL_GameControllerSetLED / SDL_GameControllerRumble reach the pad. Both scePad functions are already in the
    launch title rc2's import list (titlefix-rc6/merge/imports-launch.txt: scePadSetLightBar, scePadSetVibration,
    scePadSetVibrationMode), and the SDL functions are static code: the rc6 import gate is unchanged.
  - NOT available: scePadResetLightBar (not imported). There is no way to read or reset the system colour, so
    "restore" is best effort: when the setting goes Off, on focus loss / background and at shutdown, a pad whose
    colour Omni changed gets OPAD::kRestore (the PS5's default blue) once. At exit SDL_Quit closes the pads
    (scePadClose), which is expected to hand the light bar back to the system (unverified on console).

What the user gets (Browser settings > "Controller light & rumble": Off (default) / On):
  Light bar (every pad that is attached; sent only when the wanted colour or the set of pads changes):
      page fullscreen (video)          -> off (0, 0, 0)
      private tab                      -> purple
      tab in a group (OMNI_TAB_GROUPS_V1) -> the group's colour (Blue / Red / Yellow / Green / Pink / Purple)
      otherwise                        -> the theme's accent colour
  Rumble (the active pad only, <= 80 ms, low strength, never continuous, at most one per second):
      the active tab's page failed to load, a pop-up was blocked (the notice shows), a download was handed to
      Downloads (it starts), the sleep timer fired (both the Small comforts and the Sleep timer chooser one).
  Nothing happens while Omni is not focused or in the self-test modes.

Pure part: engine/entry/OmniPadFeedback.h (no SDL / WebKit): context -> colour, light memo, rate limiter, cue table.
namespace OmniPadFeedback (alias OPAD in the shell). Tested by tools/test_pad_feedback.cpp:
    g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_pad_feedback.cpp -o t && ./t
Shell side: engine/entry/OmniPadFeedbackShell.h (included from OmniFeatures3.h after OmniPopupNoticeShell.h).
Storage: /data/omni/pad-feedback-on.flag (present = On). Ids: Browser settings row 837.

Anchors (exactly once each; MARK makes each file idempotent):
  OmniBrowser.cpp   the OmniPopupNotice.h include line (pure include); the "void failed(WKPageRef, ...)" line (forward
                    declarations before it); failed()'s omniFxRecordFailure line; omniDownloadDestination's
                    omniFxDownloadStarted line; the Small comforts sleep timer's Event::Fire line; the three focus /
                    background lines of the event loop; the omniEverydayShutdown line of the shutdown block.
  OmniBrowserSettings.h  the omniChSettingsInput declaration; the omniChSettingsRow(p) call; the
                    OmniControlsHelp::kSettingsRowId input line.
  OmniFeatures3.h   the OmniPopupNoticeShell.h include line; omniF3Tick's OMNI_SLEEP_TIMER_V1 omniStTick(now) line.
  OmniPopupNoticeShell.h  omniPnBlocked's "omniPnHint = OPN::noticeText(k);" line.
  OmniSleepTimerShell.h   omniStFire's "notice(OST::firedNotice());" line.
Apply AFTER apply_popup_notice.py, apply_sleep_timer.py, apply_tab_groups.py and apply_controls_help.py.
usage: apply_pad_feedback.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_PAD_FEEDBACK_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_PAD_FEEDBACK_V1: the pure part of "Controller light & rumble" (no SDL, no WebKit). The shell side is
// OmniPadFeedbackShell.h; the reasons are in tools/apply_pad_feedback.py. Tested on the host with g++
// (test_pad_feedback.cpp).
#pragma once
#include <cstddef>
#include <cstdint>

namespace OmniPadFeedback {

constexpr const char* kFlagName = "pad-feedback-on.flag";   // present: On (the default is Off)
constexpr uint32_t kCueGapMs = 1000;    // at most one rumble per second
constexpr uint32_t kCueMaxMs = 80;      // never longer
constexpr uint16_t kCueMaxStrength = 0x3000;   // of 0xFFFF (the PS5 driver sends value / 256: <= 48 of 255)

struct Rgb { uint8_t r = 0, g = 0, b = 0; };
inline bool same(const Rgb& a, const Rgb& b) { return a.r == b.r && a.g == b.g && a.b == b.b; }

constexpr Rgb kPrivate { 140, 60, 220 };   // private tab: purple
constexpr Rgb kOff { 0, 0, 0 };            // page fullscreen (video): light bar off
constexpr Rgb kRestore { 0, 0, 255 };      // no reset API: the PS5's default blue, sent once when we let go

// --- light bar: context -> colour ------------------------------------------------------------------------------------
struct Context {
    bool enabled = false;        // the setting
    bool focused = true;         // Omni is the foreground app
    bool fullscreen = false;     // a page is fullscreen (video)
    bool privateTab = false;     // the active tab is private
    bool grouped = false;        // the active tab is in a tab group
    Rgb group;                   // ... its colour
    Rgb accent;                  // the theme's accent colour
};
enum class Want { Leave, Set };  // Leave: Omni does not drive the light bar now
struct Light { Want want = Want::Leave; Rgb colour; };

inline Light choose(const Context& c)
{
    if (!c.enabled || !c.focused) return {};
    if (c.fullscreen) return { Want::Set, kOff };
    if (c.privateTab) return { Want::Set, kPrivate };
    if (c.grouped) return { Want::Set, c.group };
    return { Want::Set, c.accent };
}

// A signature of the attached pads (a new or reconnected pad gets the colour again).
inline uintptr_t padsSignature(const uintptr_t* pads, size_t n)
{
    uintptr_t s = 0x9e3779b9u;
    for (size_t i = 0; i < n; ++i) if (pads[i]) s = (s ^ pads[i]) * 0x100000001b3ull + i;
    return s;
}

// What was sent last. step() says what to send now (nothing when it would repeat the last colour to the same pads).
struct Memo { bool driving = false; Rgb last; uintptr_t pads = 0; };
enum class Send { Nothing, Colour, Restore };
inline Send step(Memo& m, const Light& want, uintptr_t pads)
{
    if (want.want == Want::Leave) {
        if (!m.driving) return Send::Nothing;
        m.driving = false;
        return Send::Restore;            // once, then the light bar is left alone
    }
    if (m.driving && same(m.last, want.colour) && m.pads == pads) return Send::Nothing;
    m.driving = true; m.last = want.colour; m.pads = pads;
    return Send::Colour;
}

// --- rumble ------------------------------------------------------------------------------------------------------
enum Cue { kLoadError = 1, kPopupBlocked = 2, kDownload = 3, kSleepTimer = 4 };
struct CueSpec { uint16_t low = 0, high = 0; uint32_t ms = 0; };
inline bool cueSpec(int cue, CueSpec& out)
{
    switch (cue) {
    case kLoadError: out = { 0x3000, 0x1800, 80 }; return true;   // a firmer double-motor tap
    case kPopupBlocked: out = { 0x0000, 0x2400, 40 }; return true; // a light high-motor tick
    case kDownload: out = { 0x1c00, 0x1c00, 50 }; return true;     // an even short tap
    case kSleepTimer: out = { 0x3000, 0x0000, 80 }; return true;   // a low-motor nudge
    }
    return false;
}

// At most one cue per kCueGapMs (wrap-safe on the 32-bit tick).
struct Limiter {
    bool any = false;
    uint32_t last = 0;
    bool allow(uint32_t now)
    {
        if (any && now - last < kCueGapMs) return false;
        any = true; last = now;
        return true;
    }
};

inline bool cueAllowed(bool enabled, bool focused, bool testMode) { return enabled && focused && !testMode; }

// --- texts -------------------------------------------------------------------------------------------------------
inline const char* settingLabel() { return "Controller light & rumble"; }
inline const char* settingValue(bool on) { return on ? "On" : "Off"; }
inline const char* settingDetail() { return "Light bar follows the tab; a short buzz on load errors, blocked pop-ups, downloads, sleep timer"; }
inline const char* toggledNotice(bool on)
{
    return on ? "Controller light & rumble on" : "Controller light & rumble off";
}

} // namespace OmniPadFeedback
'''

SHELL = r'''// OMNI_PAD_FEEDBACK_V1: "Controller light & rumble" (shell side). Included from OmniFeatures3.h (inside
// OmniBrowser.cpp's anonymous namespace) after OmniPopupNoticeShell.h. The pure part is OmniPadFeedback.h; the
// reasons are in tools/apply_pad_feedback.py. Main thread only. SDL_GameControllerSetLED / Rumble reach the pad through
// SDL's PS5 driver (scePadSetLightBar / scePadSetVibration, both already imported by the launch title).
#pragma once

namespace OPAD = OmniPadFeedback;
constexpr int omniPfMaxPads = int(sizeof(omniPads) / sizeof(omniPads[0]));
static int omniPfState = -1;               // -1: not read yet
static bool omniPfFocused = true;
static OPAD::Limiter omniPfLimit;
static OPAD::Memo omniPfMemo;

static bool omniPfOn()
{
    if (omniPfState < 0) omniPfState = access(omniData(OPAD::kFlagName).c_str(), F_OK) == 0 ? 1 : 0;
    return omniPfState == 1;
}
static uintptr_t omniPfPads()
{
    uintptr_t ids[omniPfMaxPads] = {};
    for (int i = 0; i < omniPfMaxPads; ++i)
        if (omniPads[i] && SDL_GameControllerGetAttached(omniPads[i])) ids[i] = reinterpret_cast<uintptr_t>(omniPads[i]);
    return OPAD::padsSignature(ids, size_t(omniPfMaxPads));
}
static void omniPfSend(OPAD::Rgb c)
{
    for (auto* p : omniPads)
        if (p && SDL_GameControllerGetAttached(p) && SDL_GameControllerHasLED(p)) SDL_GameControllerSetLED(p, c.r, c.g, c.b);
}
static void omniPfApply(const OPAD::Light& want)
{
    switch (OPAD::step(omniPfMemo, want, omniPfPads())) {
    case OPAD::Send::Colour: omniPfSend(omniPfMemo.last); break;
    case OPAD::Send::Restore: omniPfSend(OPAD::kRestore); break;
    case OPAD::Send::Nothing: break;
    }
}
static void omniPfStopRumble()
{
    for (auto* p : omniPads) if (p && SDL_GameControllerGetAttached(p)) SDL_GameControllerRumble(p, 0, 0, 0);
}
// omniF3Tick (every pass): the light bar follows the context; SDL is called only when the colour or the pads change.
static void omniPfTick()
{
    OPAD::Context c;
    c.enabled = omniPfOn() && !omniTestMode();
    c.focused = omniPfFocused;
    c.fullscreen = pageFullscreen;
    Tab* t = active();
    c.privateTab = t && t->omniPrivate;
    if (const OTG::Group* g = t ? OTG::groupFor(omniTgModel, t) : nullptr) {
        const OTG::Rgb gc = OTG::colour(g->colour);
        c.grouped = true; c.group = { gc.r, gc.g, gc.b };
    }
    const SDL_Color a = omniTheme().accent;
    c.accent = { a.r, a.g, a.b };
    omniPfApply(OPAD::choose(c));
}
// The event loop: focus lost / background lets go of the light bar (and stops a cue); focus back takes it again.
static void omniPfFocus(bool focused)
{
    omniPfFocused = focused;
    if (!focused) { omniPfStopRumble(); omniPfApply({}); }
}
// The shutdown block (pads still open): let go before SDL_Quit closes them.
static void omniPfShutdown()
{
    omniPfStopRumble();
    omniPfApply({});
}
// A short cue on the active pad (OPAD::Cue): <= 80 ms, low strength, at most one per second; SDL stops it itself.
static void omniPfCue(int cue)
{
    if (!OPAD::cueAllowed(omniPfOn(), omniPfFocused, omniTestMode())) return;
    OPAD::CueSpec s;
    if (!OPAD::cueSpec(cue, s)) return;
    if (!controller || !SDL_GameControllerGetAttached(controller) || !SDL_GameControllerHasRumble(controller)) return;
    if (!omniPfLimit.allow(SDL_GetTicks())) return;
    SDL_GameControllerRumble(controller, s.low, s.high, s.ms);
}

// --- Browser settings ---------------------------------------------------------------------------------------------
static void omniPfSettingsRow(OmniFxPanel& p)
{
    OmniFxRow r; r.id = omniPfRowId; r.label = OPAD::settingLabel(); r.value = OPAD::settingValue(omniPfOn());
    r.stepper = true; r.detail = OPAD::settingDetail();
    p.rows.push_back(r);
}
static bool omniPfSettingsInput(int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A && b != SDL_CONTROLLER_BUTTON_DPAD_LEFT && b != SDL_CONTROLLER_BUTTON_DPAD_RIGHT) return false;
    const std::string flag = omniData(OPAD::kFlagName);
    const bool on = !omniPfOn();
    if (on) { if (FILE* f = fopen(flag.c_str(), "w")) { fputs("1\n", f); fclose(f); } }
    else unlink(flag.c_str());
    omniPfState = on ? 1 : 0;
    if (!on) { omniPfStopRumble(); omniPfApply({}); }   // let go now (the tick takes over when On)
    notice(OPAD::toggledNotice(on));
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniPopupNotice.h" // OMNI_POPUP_NOTICE_V1: Pop-up blocked notice, popup-allow.txt (pure)\n',
         '#include "OmniPopupNotice.h" // OMNI_POPUP_NOTICE_V1: Pop-up blocked notice, popup-allow.txt (pure)\n'
         '#include "OmniPadFeedback.h" // OMNI_PAD_FEEDBACK_V1: Controller light & rumble (pure)\n'),
        ('void failed(WKPageRef, WKNavigationRef, WKErrorRef error, WKTypeRef, const void* info)\n',
         '// OMNI_PAD_FEEDBACK_V1 (OmniPadFeedbackShell.h): light bar by context, short rumble cues (OmniPadFeedback::Cue)\n'
         'static void omniPfCue(int cue);\n'
         'static void omniPfFocus(bool focused);\n'
         'static void omniPfShutdown();\n'
         'void failed(WKPageRef, WKNavigationRef, WKErrorRef error, WKTypeRef, const void* info)\n'),
        ('    omniFxRecordFailure(tab, error); // OMNI_FEATURES_V1: error panel (Retry / Back)\n',
         '    omniFxRecordFailure(tab, error); // OMNI_FEATURES_V1: error panel (Retry / Back)\n'
         '    if (&tab == active()) omniPfCue(1); // OMNI_PAD_FEEDBACK_V1: kLoadError\n'),
        ('    omniFxDownloadStarted(download, path); // OMNI_FEATURES_V1: downloads page\n',
         '    omniFxDownloadStarted(download, path); // OMNI_FEATURES_V1: downloads page\n'
         '    omniPfCue(3); // OMNI_PAD_FEEDBACK_V1: kDownload (handed to Downloads)\n'),
        ('    case OmniSmallComforts::SleepTimer::Event::Fire: omniSleepPauseAll(now); notice("Sleep timer: paused playback"); omniShellDirty = true; break;\n',
         '    case OmniSmallComforts::SleepTimer::Event::Fire: omniSleepPauseAll(now); notice("Sleep timer: paused playback"); omniShellDirty = true;\n'
         '        omniPfCue(4); // OMNI_PAD_FEEDBACK_V1: kSleepTimer\n'
         '        break;\n'),
        ('            omniShoulderFocused = false; omniShoulderReset();\n',
         '            omniShoulderFocused = false; omniShoulderReset();\n'
         '            omniPfFocus(false); // OMNI_PAD_FEEDBACK_V1: background: let go of the light bar\n'),
        ('            omniShoulderFocused = true; omniShoulderReset();\n',
         '            omniShoulderFocused = true; omniShoulderReset();\n'
         '            omniPfFocus(true); // OMNI_PAD_FEEDBACK_V1\n'),
        ('            omniShoulderFocused = event.window.event == SDL_WINDOWEVENT_FOCUS_GAINED; omniShoulderReset();\n',
         '            omniShoulderFocused = event.window.event == SDL_WINDOWEVENT_FOCUS_GAINED; omniShoulderReset();\n'
         '            omniPfFocus(event.window.event == SDL_WINDOWEVENT_FOCUS_GAINED); // OMNI_PAD_FEEDBACK_V1\n'),
        ('        omniEverydayShutdown(); // OMNI_EVERYDAY_V1: last session save, flush queued writes\n',
         '        omniPfShutdown(); // OMNI_PAD_FEEDBACK_V1: let go of the light bar, stop a cue (pads still open)\n'
         '        omniEverydayShutdown(); // OMNI_EVERYDAY_V1: last session save, flush queued writes\n'),
    ],
    'OmniBrowserSettings.h': [
        ('static bool omniChSettingsInput(int b);\n',
         'static bool omniChSettingsInput(int b);\n'
         'constexpr int omniPfRowId = 837; // OMNI_PAD_FEEDBACK_V1 (OmniPadFeedbackShell.h)\n'
         'static void omniPfSettingsRow(OmniFxPanel& p);\n'
         'static bool omniPfSettingsInput(int b);\n'),
        ('    omniChSettingsRow(p); // OMNI_CONTROLS_HELP_V1: Show controls guide\n',
         '    omniChSettingsRow(p); // OMNI_CONTROLS_HELP_V1: Show controls guide\n'
         '    omniPfSettingsRow(p); // OMNI_PAD_FEEDBACK_V1: Controller light & rumble (Off / On)\n'),
        ('    if (r.id == OmniControlsHelp::kSettingsRowId) return omniChSettingsInput(b); // OMNI_CONTROLS_HELP_V1\n',
         '    if (r.id == omniPfRowId) return omniPfSettingsInput(b); // OMNI_PAD_FEEDBACK_V1\n'
         '    if (r.id == OmniControlsHelp::kSettingsRowId) return omniChSettingsInput(b); // OMNI_CONTROLS_HELP_V1\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniPopupNoticeShell.h" // OMNI_POPUP_NOTICE_V1\n',
         '#include "OmniPopupNoticeShell.h" // OMNI_POPUP_NOTICE_V1\n'
         '#include "OmniPadFeedbackShell.h" // OMNI_PAD_FEEDBACK_V1\n'),
        ('    omniStTick(now);    // OMNI_SLEEP_TIMER_V1: countdown, fade (1 script/s), end-of-video probe (every 5 s)\n',
         '    omniStTick(now);    // OMNI_SLEEP_TIMER_V1: countdown, fade (1 script/s), end-of-video probe (every 5 s)\n'
         '    omniPfTick();       // OMNI_PAD_FEEDBACK_V1: light bar by context (SDL only on a change)\n'),
    ],
    'OmniPopupNoticeShell.h': [
        ('    omniPnHint = OPN::noticeText(k);\n',
         '    omniPnHint = OPN::noticeText(k);\n'
         '    omniPfCue(2); // OMNI_PAD_FEEDBACK_V1: kPopupBlocked (the notice shows)\n'),
    ],
    'OmniSleepTimerShell.h': [
        ('    notice(OST::firedNotice());\n',
         '    notice(OST::firedNotice());\n'
         '    omniPfCue(4); // OMNI_PAD_FEEDBACK_V1: kSleepTimer\n'),
    ],
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
    data = text.replace('\n', nl).encode('utf-8')
    h = root / name
    if h.exists() and h.read_bytes() == data:
        return name + ': already'
    h.write_bytes(data)
    return name + ': written'


def main():
    for f, need, tool in (('OmniFeatures3.h', 'OMNI_POPUP_NOTICE_V1', 'apply_popup_notice.py'),
                          ('OmniFeatures3.h', 'OMNI_SLEEP_TIMER_V1', 'apply_sleep_timer.py'),
                          ('OmniFeatures3.h', 'OMNI_TAB_GROUPS_V1', 'apply_tab_groups.py'),
                          ('OmniBrowserSettings.h', 'OMNI_CONTROLS_HELP_V1', 'apply_controls_help.py')):
        if need not in (root / f).read_bytes().decode('utf-8'):
            sys.exit('%s: %s missing: %s first' % (f, need, tool))
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniPadFeedback.h', PURE, 'OmniPopupNotice.h'),
            write_new('OmniPadFeedbackShell.h', SHELL, 'OmniPopupNoticeShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
