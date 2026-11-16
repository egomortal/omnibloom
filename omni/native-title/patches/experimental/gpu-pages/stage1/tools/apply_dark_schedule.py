#!/usr/bin/env python3
"""OMNI_DARK_SCHEDULE_V1 (2026-11-16): Browser settings > "Dark mode" gets a fourth choice, "Night light schedule".

What the user sees
  - Browser settings > "Dark mode" cycles Off / Natural / Forced / Night light schedule (was Off / Natural / Forced).
    "Night light schedule": Forced dark pages during the Night light window (the "Night light from" / "until" hours,
    wrapping past midnight, e.g. 21:00-07:00), Off outside it. The row's value says "Night light schedule (dark now)" /
    "(light now)"; its detail line names the hours and the next switch:
        "Dark 21:00-07:00: on now, until 07:00 (console time 23:14)"
    and, when Night light itself is not on "Scheduled" (its from / until rows are only shown then):
        "...; set the hours with Night light: Scheduled"
    The hours are Night light's own (night-light.txt): there is one schedule, not two. The window is used whatever
    Night light's own mode is (Off / On / Scheduled only decide the warm tint).
  - At the boundary open pages switch without a reload and a notice says so:
        "Dark pages on until 07:00 (night light schedule)" / "Dark pages off until 21:00 (night light schedule)"
  - Per-site choices (site-dark.txt: Always dark / Never dark) keep priority over the schedule, as they do over
    Natural / Forced. Site settings shows "Default (schedule, dark now)" / "Default (schedule, light now)".
  - Stored in dark-style.txt as 3 (0 Off, 1 Natural, 2 Forced as before). An older build reading 3 falls back to the
    old browser-more.txt "dark" switch (written 0 for the schedule), i.e. Off.

How it works (the existing OMNI_FEATURES_V3 / OMNI_DARK_CHOICE_V1 mechanism, unchanged)
  omniDarkStyle() is what every dark decision asks (omniDkWant / omniDkForced / the config script / the per-site
  toggle). It now returns the EFFECTIVE style: the stored choice, except 3 -> 2 (Forced) inside the window, 0 outside.
  The window state is a cached bool (omniDscNight), refreshed once a second by omniDscTick from Night light's own
  clock (omniNlMinute: tm_gmtoff, else tz-offset.json, else UTC) and schedule (OmniNightLight::inWindow): no second
  clock, no second schedule. When it flips, omniDkChanged() runs, which already
    1. pushes a new versioned config user script (new documents),
    2. sets <html data-omni-dark=on|off / data-omni-dark-force> in every open tab (WKPageEvaluateJavaScriptInMainFrame;
       the isolated "omni-dark" script watches that attribute and adds / removes the filter at once), and
    3. within 300 ms omniDkTick flips WKPageSetUseDarkAppearanceForTesting per tab (prefers-color-scheme).
  So no reload is needed. The dark user scripts are installed on demand (OMNI_FEATURES_V3_FIX1: only once something is
  dark); with the schedule chosen they are installed at once, also in the daytime, so pages opened before nightfall
  already carry the script and switch live (cost in the day: the script's observers, want() false, no filter).

Sites with their own dark theme (already handled by the existing script; nothing new needed)
  Forced mode = "ask, then darken what stays light": WKPageSetUseDarkAppearanceForTesting(page, true) makes the page's
  prefers-color-scheme: dark rules match (WebKit's real appearance; OMNI_DARK_APPEARANCE_EMU_V1 also answers JS
  matchMedia), and the filter is skipped when the page is dark by itself or declares dark support (color-scheme,
  <meta name=color-scheme>, prefers-color-scheme rules: OMNI_DARK_STANDARD_V1).
  What this port exposes (checked the engine's WebKit tree (s1/webkit) UIProcess/API/C): only the per-page
  WKPageSetUseDarkAppearanceForTesting (WKPagePrivate.h). There is no WKPreferences color-scheme / useDarkAppearance
  setter (WKPreferencesSetPunchOutWhiteBackgroundsInDarkMode is the only "dark" preference, unrelated).

Pure part: engine/entry/OmniDarkSchedule.h (needs only OmniNightLight.h): choices, effective style, cycling, window
check, texts. Tested by tools/test_dark_schedule.cpp:
    g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_dark_schedule.cpp -o t && ./t
Shell side: engine/entry/OmniDarkScheduleShell.h (included from OmniFeatures3.h after OmniNightLightShell.h).

Anchors (exactly once each; MARK makes each file idempotent):
  OmniBrowser.cpp     the OmniNightLight.h include line (apply_night_light.py's): the pure include after it.
  OmniDarkPages.h     the omniDarkStyleCache declaration; the dark-style.txt fscanf line; the
                      "if (omniDarkStyleCache >= 0) return omniDarkStyleCache;" line; the omniDarkStyleName line
                      (replaced: its two callers now use ODSC texts, so it would be an unused static);
                      the clamp line, the F3 save + omniDkChanged() pair and the two notice lines of
                      omniDarkStyleSet; the omniDarkStyleStep line; the "bool any = omniDarkStyle() > 0;" install
                      check of omniDkTick (mid-line, /* */ comment only).
  OmniFeatures3.h     the OmniNightLightShell.h include line; the site-row value line (OMNI_DARK_CHOICE_V1); the
                      "Dark mode" settings row line; the omniDkTick(now) line of omniF3Tick (omniDscTick goes before
                      it, so the effective style is fresh when omniDkTick reads it).
No new row / tile ids (the existing "Dark mode" row, omniF3SetDark, gets the fourth value).
Apply AFTER apply_dark_qa.py (OMNI_DARK_CHOICE_V1) and apply_night_light.py.
usage: apply_dark_schedule.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_DARK_SCHEDULE_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_DARK_SCHEDULE_V1: the pure part of Dark mode "Night light schedule" (no SDL, no WebKit). The schedule and
// its clock are Night light's (OmniNightLight.h); the shell side is OmniDarkScheduleShell.h; the reasons are in
// tools/apply_dark_schedule.py. Tested on the host with g++ (tools/test_dark_schedule.cpp).
#pragma once
#include <algorithm>
#include <string>
#include "OmniNightLight.h"

namespace OmniDarkSchedule {

// dark-style.txt values: 0..2 are OMNI_DARK_CHOICE_V1's, 3 is new.
constexpr int kOff = 0, kNatural = 1, kForced = 2, kSchedule = 3, kChoices = 4;

inline bool validChoice(int v) { return v >= kOff && v < kChoices; }
inline int clampChoice(int v) { return std::clamp(v, int(kOff), kChoices - 1); }
// What the dark-page code acts on (0 Off, 1 Natural, 2 Forced): the schedule is Forced inside the window, Off outside.
inline int effective(int choice, bool night)
{
    choice = clampChoice(choice);
    return choice == kSchedule ? (night ? kForced : kOff) : choice;
}
// Settings row: Left / Right step, Cross steps forward (wraps both ways).
inline int step(int choice, int dir) { return (clampChoice(choice) + (dir < 0 ? kChoices - 1 : 1)) % kChoices; }
// Night light's window, whatever Night light's own mode is (its mode only decides the warm tint).
inline bool nightNow(const OmniNightLight::Settings& s, int minute) { return OmniNightLight::inWindow(minute, s.start, s.end); }
inline bool emptyWindow(int start, int end) { return OmniNightLight::wrapMinute(start) == OmniNightLight::wrapMinute(end); }

// --- texts ------------------------------------------------------------------------------------------------------
inline const char* choiceName(int c)
{
    switch (clampChoice(c)) {
    case kNatural: return "Natural";
    case kForced: return "Forced";
    case kSchedule: return "Night light schedule";
    default: return "Off";
    }
}
inline std::string choiceValue(int c, bool night)
{
    if (clampChoice(c) != kSchedule) return choiceName(c);
    return std::string(choiceName(c)) + (night ? " (dark now)" : " (light now)");
}
inline std::string hours(int start, int end) { return OmniNightLight::hhmm(start) + "-" + OmniNightLight::hhmm(end); }
// The detail line under the Dark mode row (schedule chosen).
inline std::string detail(int start, int end, int minute, bool nightLightScheduled)
{
    std::string t;
    if (emptyWindow(start, end)) t = "Night light from and until are the same time: never dark";
    else {
        const bool on = OmniNightLight::inWindow(minute, start, end);
        t = "Dark " + hours(start, end) + (on ? ": on now, until " + OmniNightLight::hhmm(end) : ": off now, starts at " + OmniNightLight::hhmm(start))
            + " (console time " + OmniNightLight::hhmm(minute) + ")";
    }
    if (!nightLightScheduled) t += "; set the hours with Night light: Scheduled";
    return t;
}
// The notice when the choice changes.
inline std::string setNotice(int c, bool night, int start, int end)
{
    std::string t = std::string("Dark mode: ") + choiceName(c);
    switch (clampChoice(c)) {
    case kNatural: return t + " (sites with a dark theme use it)";
    case kForced: return t + " (every page dark)";
    case kSchedule:
        if (emptyWindow(start, end)) return t + " (from and until are the same time: never dark)";
        return t + " (every page dark " + hours(start, end) + (night ? ", on now)" : ", off now)");
    default: return t;
    }
}
// The notice at a schedule boundary.
inline std::string edgeNotice(bool night, int start, int end)
{
    return night ? "Dark pages on until " + OmniNightLight::hhmm(end) + " (night light schedule)"
                 : "Dark pages off until " + OmniNightLight::hhmm(start) + " (night light schedule)";
}
// Site settings > "Dark page on this site" when the site has no choice of its own.
inline const char* siteDefault(int c, bool night)
{
    switch (clampChoice(c)) {
    case kNatural: return "Default (natural)";
    case kForced: return "Default (forced)";
    case kSchedule: return night ? "Default (schedule, dark now)" : "Default (schedule, light now)";
    default: return "Default (off)";
    }
}

// Boundary detection for the shell's once-a-second check: the first sample only records.
class Edge {
public:
    bool changed(bool night)
    {
        const int n = night ? 1 : 0;
        const bool c = last_ >= 0 && last_ != n;
        last_ = n;
        return c;
    }
    void reset() { last_ = -1; }
private:
    int last_ = -1;
};

} // namespace OmniDarkSchedule
'''

SHELL = r'''// OMNI_DARK_SCHEDULE_V1: Dark mode "Night light schedule" (shell side). Included from OmniFeatures3.h (inside
// OmniBrowser.cpp's anonymous namespace, after OmniNightLightShell.h: it uses omniNl / omniNlLoad / omniNlMinute).
// The pure part is OmniDarkSchedule.h; omniDarkStyle() (OmniDarkPages.h) returns the effective style from
// omniDscNight; the reasons are in tools/apply_dark_schedule.py. Main thread only.
#pragma once

static ODSC::Edge omniDscEdge;
static uint32_t omniDscNext = 0;

// The window state now (Night light's clock and hours). Called lazily by omniDarkStyle() and once a second below.
static void omniDscRefresh()
{
    omniNlLoad();
    omniDscNight = ODSC::nightNow(omniNl, omniNlMinute());
    omniDscReady = true;
}
static std::string omniDscSetNotice(int choice)
{
    omniNlLoad();
    return ODSC::setNotice(choice, omniDscNight, omniNl.start, omniNl.end);
}
static std::string omniDscValue()
{
    const int c = omniDarkChoice();
    if (c == ODSC::kSchedule && !omniDscReady) omniDscRefresh();
    return ODSC::choiceValue(c, omniDscNight);
}
static std::string omniDscDetail()
{
    omniNlLoad();
    return ODSC::detail(omniNl.start, omniNl.end, omniNlMinute(), omniNl.mode == ONL::kScheduled);
}
// From omniF3Tick, before omniDkTick. Not the schedule: one comparison a second. At a boundary: the existing
// omniDkChanged() (config script for new pages, data-omni-dark on open pages, dark appearance within 300 ms).
static void omniDscTick(uint32_t now)
{
    if (omniTestMode() || int32_t(now - omniDscNext) < 0) return;
    omniDscNext = now + 1000;
    if (omniDarkChoice() != ODSC::kSchedule) { omniDscEdge.reset(); return; }
    omniDscRefresh();
    if (!omniDscEdge.changed(omniDscNight)) return;
    omniDkChanged();
    notice(ODSC::edgeNotice(omniDscNight, omniNl.start, omniNl.end));
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniNightLight.h" // OMNI_NIGHT_LIGHT_V1: Night light schedule, warmth, fade, night-light.txt (pure)\n',
         '#include "OmniNightLight.h" // OMNI_NIGHT_LIGHT_V1: Night light schedule, warmth, fade, night-light.txt (pure)\n'
         '#include "OmniDarkSchedule.h" // OMNI_DARK_SCHEDULE_V1: Dark mode "Night light schedule" (pure)\n'),
    ],
    'OmniDarkPages.h': [
        ('static int omniDarkStyleCache = -2;\n',
         'static int omniDarkStyleCache = -2;\n'
         'namespace ODSC = OmniDarkSchedule; // OMNI_DARK_SCHEDULE_V1: 3 = Forced inside the Night light window, Off outside\n'
         'static bool omniDscNight = false, omniDscReady = false;   // OMNI_DARK_SCHEDULE_V1: window state (OmniDarkScheduleShell.h)\n'
         'static void omniDscRefresh();\n'
         'static std::string omniDscSetNotice(int choice);\n'),
        ('            if (fscanf(f, "%d", &v) == 1 && v >= 0 && v <= 2) omniDarkStyleCache = v;\n',
         '            if (fscanf(f, "%d", &v) == 1 && ODSC::validChoice(v)) omniDarkStyleCache = v; /* OMNI_DARK_SCHEDULE_V1: 0..3 */\n'),
        ('    if (omniDarkStyleCache >= 0) return omniDarkStyleCache;\n',
         '    if (omniDarkStyleCache >= 0) {   /* OMNI_DARK_SCHEDULE_V1: the effective style (the schedule -> 2 or 0) */\n'
         '        if (omniDarkStyleCache == ODSC::kSchedule && !omniDscReady) omniDscRefresh();\n'
         '        return ODSC::effective(omniDarkStyleCache, omniDscNight);\n'
         '    }\n'),
        ('static const char* omniDarkStyleName(int s) { return s == 1 ? "Natural" : s == 2 ? "Forced" : "Off"; }\n',
         '// OMNI_DARK_SCHEDULE_V1: the names are ODSC::choiceName (omniDarkStyleName had no other caller left).\n'
         '// The stored choice (0..3); omniDarkStyle() is the effective style (0..2).\n'
         'static int omniDarkChoice() { const int e = omniDarkStyle(); return omniDarkStyleCache >= 0 ? omniDarkStyleCache : e; }\n'),
        ('    omniDarkStyleCache = std::clamp(s, 0, 2);\n',
         '    omniDarkStyleCache = ODSC::clampChoice(s); /* OMNI_DARK_SCHEDULE_V1: 0..3 */\n'),
        ('    omniF3Load(); omniF3Set.dark = omniDarkStyleCache == 2; omniF3Save();\n    omniDkChanged();\n',
         '    omniF3Load(); omniF3Set.dark = omniDarkStyleCache == 2; omniF3Save();\n'
         '    if (omniDarkStyleCache == ODSC::kSchedule) omniDscRefresh(); /* OMNI_DARK_SCHEDULE_V1 */\n'
         '    omniDkChanged();\n'),
        ('    notice(std::string("Dark mode: ") + omniDarkStyleName(omniDarkStyleCache)\n'
         '        + (omniDarkStyleCache == 1 ? " (sites with a dark theme use it)" : omniDarkStyleCache == 2 ? " (every page dark)" : ""));\n',
         '    notice(omniDscSetNotice(omniDarkStyleCache)); /* OMNI_DARK_SCHEDULE_V1 (the old texts for 0..2) */\n'),
        ('static void omniDarkStyleStep(int dir) { omniDarkStyleSet((omniDarkStyle() + (dir < 0 ? 2 : 1)) % 3); }\n',
         'static void omniDarkStyleStep(int dir) { omniDarkStyleSet(ODSC::step(omniDarkChoice(), dir)); } /* OMNI_DARK_SCHEDULE_V1: 4 choices */\n'),
        ('bool any = omniDarkStyle() > 0; /* OMNI_DARK_CHOICE_V1 */',
         'bool any = omniDarkStyle() > 0 || omniDarkChoice() == ODSC::kSchedule; /* OMNI_DARK_CHOICE_V1 */ /* OMNI_DARK_SCHEDULE_V1: installed by day too, so nightfall switches open pages live */'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniNightLightShell.h" // OMNI_NIGHT_LIGHT_V1\n',
         '#include "OmniNightLightShell.h" // OMNI_NIGHT_LIGHT_V1\n'
         '#include "OmniDarkScheduleShell.h" // OMNI_DARK_SCHEDULE_V1 (after Night light: its clock and hours)\n'),
        ('    r.value = host.empty() ? std::string("-") : s == 1 ? "Always dark" : s == 0 ? "Never dark" : omniDarkStyle() == 2 ? "Default (forced)" : omniDarkStyle() == 1 ? "Default (natural)" : "Default (off)"; // OMNI_DARK_CHOICE_V1\n',
         '    r.value = host.empty() ? std::string("-") : s == 1 ? "Always dark" : s == 0 ? "Never dark" : ODSC::siteDefault(omniDarkChoice(), omniDscNight); // OMNI_DARK_CHOICE_V1 + OMNI_DARK_SCHEDULE_V1\n'),
        ('    add(omniF3SetDark, "Dark mode", omniDarkStyleName(omniDarkStyle()), true); // OMNI_DARK_CHOICE_V1: Off / Natural / Forced\n',
         '    add(omniF3SetDark, "Dark mode", omniDscValue(), true); // OMNI_DARK_CHOICE_V1: Off / Natural / Forced + OMNI_DARK_SCHEDULE_V1: Night light schedule\n'
         '    if (omniDarkChoice() == ODSC::kSchedule) p.rows.back().detail = omniDscDetail(); // OMNI_DARK_SCHEDULE_V1\n'),
        ('    omniDkTick(now);\n',
         '    omniDscTick(now);   // OMNI_DARK_SCHEDULE_V1: Night light window check every second (before omniDkTick)\n'
         '    omniDkTick(now);\n'),
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
    dp = (root / 'OmniDarkPages.h').read_bytes().decode('utf-8')
    if 'OMNI_DARK_CHOICE_V1' not in dp:
        sys.exit('OmniDarkPages.h: OMNI_DARK_CHOICE_V1 missing: apply_dark_qa.py first')
    if 'OMNI_NIGHT_LIGHT_V1' not in (root / 'OmniFeatures3.h').read_bytes().decode('utf-8'):
        sys.exit('OmniFeatures3.h: OMNI_NIGHT_LIGHT_V1 missing: apply_night_light.py first')
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniDarkSchedule.h', PURE, 'OmniNightLight.h'),
            write_new('OmniDarkScheduleShell.h', SHELL, 'OmniNightLightShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
