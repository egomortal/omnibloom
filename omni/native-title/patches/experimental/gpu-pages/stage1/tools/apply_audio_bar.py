#!/usr/bin/env python3
"""OMNI_AUDIO_BAR_V1 (2026-11-16): the mini audio bar: background music / podcasts stay in view while browsing.

Why a bar and not a mini video player: the video plane is drawn under the ACTIVE page only, and a hidden tab drops its
plane (OMNI_TAB_MEDIA_RELEASE_V1), so a picture of a background tab cannot be shown. Sound can play on there with
Browser settings > "Background audio" = Keep playing audio (OMNI_BG_AUDIO_V1; Off: hidden video pauses after 1.5 s).

What the user sees
  - While another tab (not the shown one) plays sound, a small pill sits centred just above the hints bar:
        [speaker]  <title>                               1:05 / 4:00     L2 + Right: Pause
    title: the page's Media Session metadata title (+ " - artist") when it has any, else the page's title, else the
    tab title; a private tab shows "Private tab" instead. Time: elapsed / duration, "12:31 (live)" for streams.
    Paused with the chord: two bars instead of the speaker and "L2 + Right: Play"; the bar stays (up to 5 min) so
    the tab can be resumed. Xbox names: "LT + Right".
  - Shown only when "Background audio" is Keep playing audio AND "Show mini audio bar" is On, the sounding tab is
    not muted (tab mute, OMNI_TAB_AUDIO_V1) and not the shown tab; never in full screen, over the keyboard or the
    classic settings panel. Panels, dialogs, the toast and the pointer draw over it. It is not focusable: the D-pad,
    Cross and the pointer never stop on it.
  - Controls: L2 + D-pad right = play / pause the bar's tab (only while the bar shows; otherwise D-pad right with L2
    held is Forward as before). Free: omniL2Chord takes D-pad up / down + the face buttons, the tab switcher L1 / R1,
    the magnifier L3, the screenshot R3, the button map only face-button L2 chords (checked in the patched tree and
    every apply_*.py; apply_tab_switcher.py says "L2 + D-pad left / right is not a chord"). Next track, seek, mute:
    Options > Now playing (OMNI_MEDIA_CONTROLS_V1), which already reaches background tabs. Controls guide: a row in
    "Quick actions".
  - Browser settings, right after "Background audio": "Show mini audio bar"  On (default) / Off; Cross or D-pad
    left / right toggles, a notice confirms. Its detail says it needs Background audio while that is Off.
  - Private tabs: only "Private tab" is drawn; nothing is stored (all state in memory; the only file is the Off flag).

Update cost (nothing per frame)
  - omniAbrTick (omniF3Tick): every 500 ms, WebKit's cached media state of each tab (WKPageGetMediaState: no IPC),
    as OMNI_TAB_AUDIO_V1 does. The Background audio flag is stat()ed only while some tab plays behind, at most every
    5 s; the Off flag once (and after a toggle).
  - Page script: Now playing's own (OmniMediaControls::script, kProbe: element state + navigator.mediaSession
    metadata + document.title), ONE when the bar's tab changes, then every 5 s at most while the bar shows; never more
    than one out (8 s abandon); answers to an older tab are dropped. Elapsed time between answers is extrapolated
    while WebKit says the tab plays. The chord sends the same script with kToggle (its answer is used the same way).
  - Drawing: what the bar shows (title / time / hint / state / visible) is compared every check; a change marks only
    the bar's rows for the next draw, like the perf overlay (OMNI_PERF_A_S4 regional plan: omniAbrPlan + close();
    the regional draw redraws the bar when its rows are redrawn). About one draw a second while playing (the clock).
  - Interface size (OMNI_UI_SCALE_V1): drawn in an OmniUisZoomScope at omniUisZoom() like the toast (omniUisToast):
    pill, text and icon grow together, the pill keeps 16 px to the screen edges, the title takes what is left and is
    cut with an ellipsis (omniLabel maxW), so text always fits.

Pure part: engine/entry/OmniAudioBar.h (no SDL / WebKit; includes OmniMediaControls.h): tab choice, paused-tab rule,
script schedule, texts, time extrapolation, layout and rows. Tested by tools/test_audio_bar.cpp:
    g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_audio_bar.cpp -o t && ./t [<tree>]
  (with <tree>: also checks the patched files: hooks in the right places and order).
Shell side: engine/entry/OmniAudioBarShell.h (included from OmniFeatures3.h after OmniBgAudioShell.h).
Storage: /data/omni/audio-bar-off.flag (present = Off). Ids: Browser settings row 894; alias OABR, prefix omniAbr (grep of
the patched tree and every apply_*.py, 2026-11-16: 894 unused; 834-844, 845-893, 895-899, 900+ taken; checked again
before the first apply: refuses if another file uses them).

Anchors (whole lines, exactly once each; MARK makes each file idempotent):
  entry/OmniBrowser.cpp        the OmniBgAudio.h include line (pure include after it); "static void omniPoDraw();"
                               (rows / plan / draw declarations after it); omniPlanDraw's "omniPoRegional = false; ..."
                               line and its "close(omniPoRow0, ...)" line (ours after each); the regional draw's
                               omniDrawToast() line (bar before it); the whole draw's "omniDrawBars(); omniDrawToast();"
                               pair (bar between); omniL2Chord's "if (!omniL2Held || !bit) return false;" (chord after).
  entry/OmniBrowserSettings.h  "static bool omniBgaSettingsInput(int b);" (declarations after it); the
                               omniBgaSettingsRow(p) line (row after it); the omniBgaRowId input line (ours before it).
  entry/OmniFeatures3.h        the OmniBgAudioShell.h include line; the omniDlpTick(now) line of omniF3Tick.
  entry/OmniControlsHelp.h     the L2 + L1 / R1 (tab switcher) row (ours after it).
Apply AFTER apply_bg_audio.py, apply_media_controls.py, apply_perf_overlay.py, apply_ui_scale.py, apply_l2_chords.py,
apply_dl_progress.py and apply_tab_switcher.py (their lines are anchors); last in the recipe is fine.
usage: apply_audio_bar.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_AUDIO_BAR_V1'
if len(sys.argv) != 2:
    sys.exit('usage: apply_audio_bar.py <engine tree>')
root = Path(sys.argv[1]) / 'engine'
TAKEN = (r'(?<![\w.])894(?![\w.])', r'\bOABR\b', r'\bomniAbr[A-Z]', r'\bOmniAudioBar')

PURE = r'''// OMNI_AUDIO_BAR_V1: the pure part of the mini audio bar (no SDL, no WebKit). The shell side is OmniAudioBarShell.h;
// the reasons are in tools/apply_audio_bar.py. Tested on the host with g++ (tools/test_audio_bar.cpp).
// A small pill above the hints bar while ANOTHER tab plays sound in the background ("Background audio" on): that tab's
// title (Media Session metadata, else the page title; "Private tab" for private tabs), elapsed time and the
// play / pause state; L2 + D-pad right plays / pauses it. Nothing is focusable, nothing is stored but the Off flag.
#pragma once
#include "OmniMediaControls.h"
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <string>
#include <vector>

namespace OmniAudioBar {

namespace MC = OmniMediaControls;

constexpr int kRowId = 894;                  // Browser settings row (after "Background audio", 835)
constexpr const char* kOffFlagName = "audio-bar-off.flag";   // in /data/omni; present: the user turned the bar Off
constexpr uint32_t kCheckMs = 500;           // tab media states (WebKit's cached UI-process state) at most this often
constexpr uint32_t kRefreshMs = 5000;        // one metadata / position script at most this often while the bar shows
constexpr uint32_t kAbandonMs = 8000;        // a script still unanswered then is given up
constexpr uint32_t kSettingReadMs = 5000;    // the Background audio flag is stat()ed at most this often (only while needed)
constexpr uint32_t kPausedKeepMs = 300000;   // a tab paused with the chord keeps the bar (to resume it) this long
constexpr uint32_t kSettleMs = 3000;         // WebKit's media state may still say "playing" this long after the pause
constexpr size_t kTitleMax = 160;            // bytes (the label clips to its room anyway)

// --- which tab ---------------------------------------------------------------------------------------------------
struct Candidate { uintptr_t key = 0; bool active = false, audible = false, muted = false, usable = true; };
inline bool enabled(bool backgroundAudioOn, bool userOff) { return backgroundAudioOn && !userOff; }
inline bool playingBehind(const Candidate& c) { return c.usable && !c.active && c.audible && !c.muted; }
// The tab the bar shows (0: none): the one shown now while it still plays behind (no flapping between two), else the
// first tab playing sound behind the shown tab, else the tab paused with the chord (pausedFresh) while still behind.
inline uintptr_t pick(const std::vector<Candidate>& tabs, uintptr_t current, uintptr_t paused, bool pausedFresh)
{
    if (current) for (const auto& c : tabs) if (c.key == current && playingBehind(c)) return current;
    for (const auto& c : tabs) if (playingBehind(c)) return c.key;
    if (paused && pausedFresh)
        for (const auto& c : tabs) if (c.key == paused && c.usable && !c.active && !c.muted) return paused;
    return 0;
}
// Keep remembering the chord-paused tab? Only while it is the one shown, young enough, and not playing again for real.
inline bool keepPaused(uintptr_t paused, uint32_t pausedAge, uintptr_t shown, bool shownAudible)
{
    if (!paused || pausedAge >= kPausedKeepMs || shown != paused) return false;
    return !(shownAudible && pausedAge >= kSettleMs);
}
// One script when the shown tab changes, then every kRefreshMs at most; one at a time (an old one is given up after
// kAbandonMs; a tab change sends at once, the old answer is dropped by its generation).
inline bool fetchDue(uintptr_t shown, uintptr_t fetchedKey, uint32_t lastAnswerAt, bool inFlight, uint32_t sentAt, uint32_t now)
{
    if (!shown) return false;
    if (shown != fetchedKey) return true;
    if (inFlight && now - sentAt < kAbandonMs) return false;
    return now - lastAnswerAt >= kRefreshMs;
}

// --- texts -------------------------------------------------------------------------------------------------------
inline std::string title(const MC::Info& info, bool answered, const std::string& tabTitle, bool privateTab)
{
    if (privateTab) return "Private tab";
    const MC::Info none;
    std::string t = MC::displayTitle(answered ? info : none, tabTitle);
    const std::string artist = answered ? MC::trim(info.artist) : std::string();
    if (!artist.empty()) t += " - " + artist;
    std::string out;
    for (char c : t) out += (c == '\n' || c == '\r' || c == '\t') ? ' ' : c;
    return MC::clip(out, kTitleMax);
}
// The position now: the answer's, moved on by the time since it came while the tab plays (WebKit's state).
inline double elapsed(const MC::Info& info, uint32_t answeredAt, uint32_t now, bool playing)
{
    if (!info.ok || info.state == MC::kNone || !(info.position >= 0)) return -1;
    double p = info.position;
    if (playing && info.state == MC::kPlaying) p += double(now - answeredAt) / 1000.0;
    if (info.duration > 0) p = std::min(p, info.duration);
    return p;
}
// "1:05 / 4:00", "12:31 (live)", "1:05"; "" before an answer or without media.
inline std::string timeText(const MC::Info& info, bool answered, uint32_t answeredAt, uint32_t now, bool playing)
{
    if (!answered || !info.ok || info.state == MC::kNone) return std::string();
    const double p = elapsed(info, answeredAt, now, playing);
    if (info.duration == MC::kLive) return p >= 0 ? MC::clock(p) + " (live)" : std::string("Live");
    const std::string at = p >= 0 ? MC::clock(p) : std::string("0:00");
    return info.duration > 0 ? at + " / " + MC::clock(info.duration) : (p >= 0 ? at : std::string());
}
inline std::string hint(bool ps, bool playing) { return std::string(ps ? "L2" : "LT") + " + Right: " + (playing ? "Pause" : "Play"); }

inline const char* settingLabel() { return "Show mini audio bar"; }
inline const char* settingValue(bool on) { return on ? "On" : "Off"; }
inline const char* settingDetail(bool on, bool backgroundAudio, bool ps)
{
    if (!backgroundAudio) return "Shows only while Background audio keeps another tab playing";
    if (!on) return "On: another tab's sound shows its title and time above the hints";
    return ps ? "Another tab playing sound: title and time above the hints; L2 + Right pauses"
              : "Another tab playing sound: title and time above the hints; LT + Right pauses";
}
inline const char* toggledNotice(bool on) { return on ? "Mini audio bar on" : "Mini audio bar off"; }
inline const char* failedNotice() { return "Mini audio bar: couldn't save the setting"; }

// --- what a draw shows (the shell compares it each check: a change asks for a draw of the bar's rows only) ----------
struct Shown {
    bool visible = false, playing = false;
    std::string title, time, hint;
    bool operator==(const Shown& o) const
    {
        return visible == o.visible && (!visible || (playing == o.playing && title == o.title && time == o.time && hint == o.hint));
    }
    bool operator!=(const Shown& o) const { return !(*this == o); }
};

// --- layout (in the layout space of the zoom being drawn: OUIS::zoomedW(z) wide, base = OUIS::toZoomed(pageBottom, z))
constexpr int kBarW = 640, kBarH = 40, kGapAbove = 16, kSideMargin = 16, kShadowPad = 10;
constexpr int kIconX = 24, kTextX = 44, kPadR = 18, kHintMaxW = 170, kTimeMaxW = 150, kGap = 14, kMinTitleW = 40;
struct Geo { int x = 0, y = 0, w = 0, h = 0; };
inline Geo geometry(int layoutW, int base)
{
    Geo g;
    g.w = std::max(0, std::min(kBarW, layoutW - 2 * kSideMargin));
    g.h = kBarH;
    g.x = (layoutW - g.w) / 2;
    g.y = base - kGapAbove - kBarH;
    return g;
}
// Canvas rows [r0, r1) the bar and its shadow cover; scale = displayScale * zoom (pixels per layout px of the zoom).
inline void canvasRows(const Geo& g, double scale, int canvasH, int& r0, int& r1)
{
    r0 = std::max(0, int(std::floor((g.y - kShadowPad) * scale)));
    r1 = std::min(canvasH, int(std::ceil((g.y + g.h + kShadowPad) * scale)));
    if (r1 <= r0) r0 = r1 = 0;
}

} // namespace OmniAudioBar
'''

SHELL = r'''// OMNI_AUDIO_BAR_V1: the mini audio bar (shell side). Included from OmniFeatures3.h (inside OmniBrowser.cpp's anonymous
// namespace) after OmniBgAudioShell.h; uses Now playing's helpers (OmniMediaControlsShell.h: omniNpTab, omniNpMedia and
// its page script). The pure part is OmniAudioBar.h; the reasons are in tools/apply_audio_bar.py. Main thread only.
// Cost: omniAbrTick looks at WebKit's cached media state of each tab every 500 ms (no IPC); the Background audio flag is
// stat()ed at most every 5 s and only while some tab plays behind; one page script when the shown tab changes, then
// every 5 s at most while the bar shows; a draw of the bar's rows only when what it shows changes (about once a second
// while playing: the clock). Nothing is drawn or run per frame for it beyond that.
#pragma once

namespace OABR = OmniAudioBar;
static_assert(OABR::kRowId == omniAbrRowId, "OMNI_AUDIO_BAR_V1: row id");

static uintptr_t omniAbrKey = 0;           // the shown tab (Tab::omniMediaIdentity), 0: no bar
static uintptr_t omniAbrFetchedKey = 0;    // the tab the last script went to
static MC::Info omniAbrInfo;               // its last answer (memory only)
static bool omniAbrAnswered = false;
static uint32_t omniAbrAnsweredAt = 0, omniAbrSentAt = 0, omniAbrCheckAt = 0, omniAbrBgReadAt = 0, omniAbrPausedAt = 0;
static bool omniAbrInFlight = false, omniAbrForce = true, omniAbrDirty = false;
static uintptr_t omniAbrGen = 0;           // answers to older scripts are dropped
static MC::Action omniAbrAction = MC::kProbe;
static uintptr_t omniAbrPausedKey = 0;     // paused with the chord: the bar stays to resume it (kPausedKeepMs)
static int omniAbrUserOff = -1, omniAbrBgOn = -1;   // -1: not read yet
static OABR::Shown omniAbrShown;           // what the next draw shows
static int omniAbrDrawn0 = 0, omniAbrDrawn1 = 0;   // canvas rows the bar was last drawn on

static bool omniAbrUserOffNow()
{
    if (omniAbrUserOff < 0) omniAbrUserOff = access(omniData(OABR::kOffFlagName).c_str(), F_OK) == 0;
    return omniAbrUserOff == 1;
}
static bool omniAbrBgAudioNow(uint32_t now)
{
    if (omniAbrBgOn < 0 || now - omniAbrBgReadAt >= OABR::kSettingReadMs) { omniAbrBgOn = omniBgaOn(); omniAbrBgReadAt = now; }
    return omniAbrBgOn == 1;
}
static bool omniAbrVisibleNow() { return omniAbrShown.visible && omniAbrKey && !editing && !settingsOpen && !pageFullscreen && canvas; }

// One evaluate in the shown tab: Now playing's script (read, or play / pause) and its answer.
static void omniAbrRun(MC::Action action, uint32_t now)
{
    Tab* t = omniNpTab(omniAbrKey);
    if (!t || !t->page || t->crashed) return;
    omniAbrAction = action;
    omniAbrFetchedKey = omniAbrKey;
    omniAbrSentAt = now;
    omniAbrInFlight = true;
    const uintptr_t gen = ++omniAbrGen;
    auto js = adoptWK(WKStringCreateWithUTF8CString(MC::script(action, omniAbrInfo.src).c_str()));
    WKPageEvaluateJavaScriptInMainFrame(t->page, js.get(), reinterpret_cast<void*>(gen), [](WKTypeRef result, WKErrorRef error, void* ctx) {
        if (reinterpret_cast<uintptr_t>(ctx) != omniAbrGen) return;   // the tab changed or a newer script is out
        omniAbrInFlight = false;
        const uint32_t at = SDL_GetTicks();
        const MC::Info i = MC::parse(omniFxResultString(result, error));
        if (i.ok) { omniAbrInfo = i; omniAbrAnswered = true; }
        omniAbrAnsweredAt = at;   // also a failed answer: the next try waits kRefreshMs
        if (omniAbrAction == MC::kToggle) {
            const std::string msg = MC::resultNotice(MC::kToggle, i);
            if (!msg.empty()) notice(msg);
            if (i.ok && i.state == MC::kPaused) { omniAbrPausedKey = omniAbrKey; omniAbrPausedAt = at; }
            else if (i.ok && i.state == MC::kPlaying) omniAbrPausedKey = 0;
        }
        omniAbrForce = true;   // the next tick shows the answer
    });
}

// From omniF3Tick: which tab, its script, what the bar shows (a change marks the bar's rows for the next draw).
static void omniAbrTick(uint32_t now)
{
    if (!omniAbrForce && now - omniAbrCheckAt < OABR::kCheckMs) return;
    omniAbrForce = false;
    omniAbrCheckAt = now;
    std::vector<OABR::Candidate> c;
    bool behind = false;
    for (auto& t : tabs) {
        OABR::Candidate k;
        k.key = t->omniMediaIdentity; k.active = t.get() == active();
        k.audible = omniNpMedia(*t) & kWKMediaIsPlayingAudio;   // WebKit's cached state (no IPC)
        k.muted = t->omniTaMuted;
        k.usable = t->page && !t->crashed && t->omniLazyURL.empty();
        behind = behind || OABR::playingBehind(k) || (omniAbrPausedKey && k.key == omniAbrPausedKey);
        c.push_back(k);
    }
    const uint32_t pausedAge = now - omniAbrPausedAt;
    uintptr_t key = 0;
    if (behind && OABR::enabled(omniAbrBgAudioNow(now), omniAbrUserOffNow()))
        key = OABR::pick(c, omniAbrKey, omniAbrPausedKey, omniAbrPausedKey && pausedAge < OABR::kPausedKeepMs);
    Tab* t = omniNpTab(key);
    const bool playing = t && (omniNpMedia(*t) & kWKMediaIsPlayingAudio);
    if (!OABR::keepPaused(omniAbrPausedKey, pausedAge, key, playing)) omniAbrPausedKey = 0;
    if (key != omniAbrKey) {   // another tab (or none): forget the old answer, drop a script still out
        omniAbrKey = key;
        omniAbrInfo = MC::Info();
        omniAbrAnswered = omniAbrInFlight = false;
        omniAbrFetchedKey = 0;
        ++omniAbrGen;
        if (key) fprintf(stderr, "OMNI AUDIOBAR: showing a background tab%s\n", t && t->omniPrivate ? " (private)" : "");
        else fprintf(stderr, "OMNI AUDIOBAR: hidden\n");
        fflush(stderr);
    }
    OABR::Shown s;
    s.visible = t && !editing && !settingsOpen && !pageFullscreen;
    if (s.visible) {
        if (OABR::fetchDue(key, omniAbrFetchedKey, omniAbrAnsweredAt, omniAbrInFlight, omniAbrSentAt, now)) omniAbrRun(MC::kProbe, now);
        s.playing = playing;
        s.title = OABR::title(omniAbrInfo, omniAbrAnswered, t->title, t->omniPrivate);
        s.time = OABR::timeText(omniAbrInfo, omniAbrAnswered, omniAbrAnsweredAt, now, playing);
        s.hint = OABR::hint(playStationIcons, playing);
    }
    if (s != omniAbrShown) { omniAbrShown = s; omniAbrDirty = true; omniShellDirty = true; }
}

// The bar's canvas rows now (0, 0: not shown). The bar is drawn zoomed like the toast (OMNI_UI_SCALE_V1).
static void omniAbrRows(int& y0, int& y1)
{
    y0 = y1 = 0;
    if (!omniAbrVisibleNow()) return;
    const double z = omniUisZoom();
    const OABR::Geo g = OABR::geometry(OUIS::zoomedW(z), OUIS::toZoomed(omniPageBottom(), z));
    OABR::canvasRows(g, displayScale * z, canvas->h, y0, y1);
}
// omniPlanDraw (OMNI_PERF_A_S4): what the bar shows changed: its old and new rows only (perf overlay's pattern).
static bool omniAbrPlan(std::vector<uint8_t>& changed)
{
    if (!omniAbrDirty) return false;
    const int h = int(changed.size());
    int y0 = 0, y1 = 0;
    omniAbrRows(y0, y1);
    omniAbrRow0 = y0; omniAbrRow1 = y1;
    auto mark = [&](int a, int b) { a = std::max(a, 0); b = std::min(b, h); if (b > a) memset(changed.data() + a, 1, size_t(b - a)); };
    mark(omniAbrDrawn0, omniAbrDrawn1);
    mark(y0, y1);
    if (y1 <= y0) { omniAbrDrawn0 = omniAbrDrawn1 = 0; omniAbrDirty = false; }   // hidden: the page rows come back, nothing to draw
    return true;
}
// draw(): after the bars (whole frame), or on a regional draw that redraws its rows; under the toast, panels, pointer.
static void omniAbrDraw()
{
    omniAbrDirty = false;
    omniAbrRows(omniAbrDrawn0, omniAbrDrawn1);
    omniAbrRow0 = omniAbrDrawn0; omniAbrRow1 = omniAbrDrawn1;
    if (omniAbrDrawn1 <= omniAbrDrawn0) return;
    const OABR::Shown& s = omniAbrShown;
    const OmniTheme& T = omniTheme();
    const double z = omniUisZoom();
    const int base = omniPageBottom();
    OmniUisZoomScope uisZoom(z);   // OMNI_UI_SCALE_V1: the pill, its text and icon grow together (1: nothing)
    const OABR::Geo g = OABR::geometry(OUIS::zoomedW(z), OUIS::toZoomed(base, z));
    omniShadow(g.x, g.y, g.w, g.h, g.h / 2, 8, 90, 2);
    fillRounded(g.x, g.y, g.w, g.h, g.h / 2, omniMix(T.raised, T.line, 0.6f));
    fillRounded(g.x + 1, g.y + 1, g.w - 2, g.h - 2, g.h / 2 - 1, T.raised);
    const float cy = g.y + g.h / 2.f;
    if (s.playing) omniIcon(omniIconSpeaker, float(g.x + OABR::kIconX), cy, T.accent);
    else { fill(g.x + OABR::kIconX - 6, int(cy) - 7, 4, 14, T.inkDim); fill(g.x + OABR::kIconX + 2, int(cy) - 7, 4, 14, T.inkDim); }   // paused
    int right = g.x + g.w - OABR::kPadR;
    right -= omniLabel(s.hint, float(right), cy, omniCaption, T.inkFaint, 2, OABR::kHintMaxW) + OABR::kGap;
    if (!s.time.empty()) right -= omniLabel(s.time, float(right), cy, omniCaption, T.inkDim, 2, OABR::kTimeMaxW) + OABR::kGap;
    const int tx = g.x + OABR::kTextX;
    if (right - tx >= OABR::kMinTitleW) omniLabel(s.title, float(tx), cy, omniSmallBold, T.ink, 0, right - tx);
}

// omniL2Chord: L2 + D-pad right while the bar shows: play / pause its tab (free chord: L2 + D-pad left / right was none).
static bool omniAbrChord(int button)
{
    if (button != SDL_CONTROLLER_BUTTON_DPAD_RIGHT || !omniAbrVisibleNow() || !active() || omniOverlayOpen()) return false;
    if (!omniNpTab(omniAbrKey)) return false;
    omniAbrRun(MC::kToggle, SDL_GetTicks());
    fprintf(stderr, "OMNI AUDIOBAR: play / pause (L2 + Right)\n");
    fflush(stderr);
    return true;
}

// Browser settings > "Show mini audio bar" (after "Background audio"). The only state is the Off flag.
static void omniAbrSettingsRow(OmniFxPanel& p)
{
    const bool on = !omniAbrUserOffNow();
    OmniFxRow r; r.id = omniAbrRowId; r.label = OABR::settingLabel(); r.value = OABR::settingValue(on);
    r.stepper = true; r.detail = OABR::settingDetail(on, omniBgaOn(), playStationIcons);
    p.rows.push_back(r);
}
static bool omniAbrSettingsInput(int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A && b != SDL_CONTROLLER_BUTTON_DPAD_LEFT && b != SDL_CONTROLLER_BUTTON_DPAD_RIGHT) return false;
    const std::string flag = omniData(OABR::kOffFlagName);
    const bool on = omniAbrUserOffNow();   // Off now: turning it On
    if (on) unlink(flag.c_str());
    else if (FILE* f = fopen(flag.c_str(), "w")) { fputs("1\n", f); fclose(f); }
    omniAbrUserOff = -1;
    omniAbrBgOn = -1;   // read Background audio again too
    omniAbrForce = true;
    const bool ok = omniAbrUserOffNow() != on;
    notice(ok ? OABR::toggledNotice(on) : OABR::failedNotice());
    fprintf(stderr, "OMNI AUDIOBAR: setting %s%s\n", on ? "on" : "off", ok ? "" : " (flag write failed)");
    fflush(stderr);
    return true;
}
'''

EDITS = {
    'entry/OmniBrowser.cpp': [
        ('#include "OmniBgAudio.h" // OMNI_BG_AUDIO_V1: Background audio setting (pure)\n',
         '#include "OmniBgAudio.h" // OMNI_BG_AUDIO_V1: Background audio setting (pure)\n'
         '#include "OmniAudioBar.h" // OMNI_AUDIO_BAR_V1: mini audio bar (pure)\n'),
        ('static void omniPoDraw();\n',
         'static void omniPoDraw();\n'
         '/* OMNI_AUDIO_BAR_V1 (OmniAudioBarShell.h): the mini audio bar\'s canvas rows (0, 0: none) for the regional plan. */\n'
         'static int omniAbrRow0 = 0, omniAbrRow1 = 0;\n'
         'static bool omniAbrRegional = false;          /* this regional plan redraws the bar */\n'
         'static bool omniAbrPlan(std::vector<uint8_t>& changed);\n'
         'static void omniAbrDraw();\n'),
        ('    omniPoRegional = false; if (omniPoMode && omniPoPlan(R)) changed = true; /* OMNI_PERF_OVERLAY_V1: new numbers: the box rows only */\n',
         '    omniPoRegional = false; if (omniPoMode && omniPoPlan(R)) changed = true; /* OMNI_PERF_OVERLAY_V1: new numbers: the box rows only */\n'
         '    omniAbrRegional = false; if (omniAbrPlan(R)) changed = true; /* OMNI_AUDIO_BAR_V1: the bar changed: its rows only */\n'),
        ('        close(omniPoRow0, omniPoRow1, omniPoRegional); /* OMNI_PERF_OVERLAY_V1: the box is re-blended whole */\n',
         '        close(omniPoRow0, omniPoRow1, omniPoRegional); /* OMNI_PERF_OVERLAY_V1: the box is re-blended whole */\n'
         '        close(omniAbrRow0, omniAbrRow1, omniAbrRegional); /* OMNI_AUDIO_BAR_V1: the bar is redrawn whole */\n'),
        ('        omniDrawToast();   // shows nothing (planned only while the status is "Ready"); keeps its state as in every draw\n',
         '        if (omniAbrRegional) omniAbrDraw(); /* OMNI_AUDIO_BAR_V1: over the page rows and the hints bar, under the pointer */\n'
         '        omniDrawToast();   // shows nothing (planned only while the status is "Ready"); keeps its state as in every draw\n'),
        ('    omniDrawBars();\n'
         '    omniDrawToast();\n',
         '    omniDrawBars();\n'
         '    omniAbrDraw(); // OMNI_AUDIO_BAR_V1: the mini audio bar above the hints bar (under the toast and panels)\n'
         '    omniDrawToast();\n'),
        ('    if (!omniL2Held || !bit) return false;\n',
         '    if (!omniL2Held || !bit) return false;\n'
         '    if (omniAbrChord(event.button)) { omniL2ChordUsed = true; omniL2Swallow |= bit; return true; } // OMNI_AUDIO_BAR_V1: L2 + D-pad right\n'),
    ],
    'entry/OmniBrowserSettings.h': [
        ('static bool omniBgaSettingsInput(int b);\n',
         'static bool omniBgaSettingsInput(int b);\n'
         'constexpr int omniAbrRowId = 894; // OMNI_AUDIO_BAR_V1 (OmniAudioBarShell.h): Show mini audio bar\n'
         'static void omniAbrSettingsRow(OmniFxPanel& p);\n'
         'static bool omniAbrSettingsInput(int b);\n'),
        ('    omniBgaSettingsRow(p); // OMNI_BG_AUDIO_V1: Background audio (Off / Keep playing audio)\n',
         '    omniBgaSettingsRow(p); // OMNI_BG_AUDIO_V1: Background audio (Off / Keep playing audio)\n'
         '    omniAbrSettingsRow(p); // OMNI_AUDIO_BAR_V1: Show mini audio bar (On / Off)\n'),
        ('    if (r.id == omniBgaRowId) return omniBgaSettingsInput(b); // OMNI_BG_AUDIO_V1\n',
         '    if (r.id == omniAbrRowId) return omniAbrSettingsInput(b); // OMNI_AUDIO_BAR_V1\n'
         '    if (r.id == omniBgaRowId) return omniBgaSettingsInput(b); // OMNI_BG_AUDIO_V1\n'),
    ],
    'entry/OmniFeatures3.h': [
        ('#include "OmniBgAudioShell.h" // OMNI_BG_AUDIO_V1\n',
         '#include "OmniBgAudioShell.h" // OMNI_BG_AUDIO_V1\n'
         '#include "OmniAudioBarShell.h" // OMNI_AUDIO_BAR_V1 (after Background audio and Now playing: uses both)\n'),
        ('    omniDlpTick(now);   // OMNI_DL_PROGRESS_V1: Downloads progress (polls only while jobs run / after a hand-over)\n',
         '    omniDlpTick(now);   // OMNI_DL_PROGRESS_V1: Downloads progress (polls only while jobs run / after a hand-over)\n'
         '    omniAbrTick(now);   // OMNI_AUDIO_BAR_V1: media states every 500 ms, one script per 5 s while the bar shows\n'),
    ],
    'entry/OmniControlsHelp.h': [
        ('    { kQuick, { gL2, gShoulders }, \'+\', false, "Quick tab switcher (most recent first)", "Keep {L2} held: {L1} / {R1} or D-pad choose, let go; {Circle} cancels", "omniTswChord (OMNI_TAB_SWITCHER_V1)" },\n',
         '    { kQuick, { gL2, gShoulders }, \'+\', false, "Quick tab switcher (most recent first)", "Keep {L2} held: {L1} / {R1} or D-pad choose, let go; {Circle} cancels", "omniTswChord (OMNI_TAB_SWITCHER_V1)" },\n'
         '    { kQuick, { gL2, gDpadH }, \'+\', false, "Mini audio bar: play / pause", "{L2} + D-pad right while the bar shows another tab\'s sound", "omniAbrChord (OMNI_AUDIO_BAR_V1)" },\n'),
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
    """Before the first apply: no engine file and no other apply_*.py may use our row id / names."""
    if any(MARK in (root / n).read_bytes().decode('utf-8') for n in EDITS):
        return
    me = Path(__file__).resolve()
    places = [p for d in ('entry', 'media') if (root / d).is_dir() for p in (root / d).iterdir()
              if p.suffix in ('.h', '.cpp', '.inc') and p.name not in ('OmniAudioBar.h', 'OmniAudioBarShell.h')]
    places += [p for p in me.parent.glob('apply_*.py') if p.resolve() != me and p.name != 'apply_controls_help.py'
        and MARK not in p.read_text(encoding='utf-8', errors='replace')]   # OMNI_SIBLING_SKIP: guide / dependent patches
    for p in places:
        s = p.read_bytes().decode('utf-8', 'replace')
        if p.suffix == '.py':   # sibling script: names in its code only; the row id counts in the engine tree only
            s = code_only(s)
        else:
            s = cpp_code(s)
        for pat in (TAKEN[1:] if p.suffix == '.py' else TAKEN[:1] if p.name in GUIDE else TAKEN):
            m = re.search(pat, s)
            if m:
                sys.exit('%s already uses %r (line %d): pick other ids' % (p.name, m.group(0), s.count('\n', 0, m.start()) + 1))


def main():
    for f, need, tool in (('entry/OmniBrowserSettings.h', 'OMNI_BG_AUDIO_V1', 'apply_bg_audio.py'),
                          ('entry/OmniFeatures3.h', 'OMNI_BG_AUDIO_V1', 'apply_bg_audio.py'),
                          ('entry/OmniFeatures3.h', 'OMNI_MEDIA_CONTROLS_V1', 'apply_media_controls.py'),
                          ('entry/OmniFeatures3.h', 'OMNI_DL_PROGRESS_V1', 'apply_dl_progress.py'),
                          ('entry/OmniBrowser.cpp', 'OMNI_PERF_OVERLAY_V1', 'apply_perf_overlay.py'),
                          ('entry/OmniBrowser.cpp', 'OMNI_UI_SCALE_V1', 'apply_ui_scale.py'),
                          ('entry/OmniBrowser.cpp', 'OMNI_L2_CHORDS_V1', 'apply_l2_chords.py'),
                          ('entry/OmniControlsHelp.h', 'OMNI_TAB_SWITCHER_V1', 'apply_tab_switcher.py')):
        if need not in (root / f).read_bytes().decode('utf-8'):
            sys.exit('%s: %s missing: %s first' % (f, need, tool))
    ids_free()
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('entry/OmniAudioBar.h', PURE, 'entry/OmniBgAudio.h'),
            write_new('entry/OmniAudioBarShell.h', SHELL, 'entry/OmniBgAudioShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
