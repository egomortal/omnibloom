#!/usr/bin/env python3
"""OMNI_TAB_AUDIO_V1 (2026-11-16): show which tabs play sound, mute a tab.

What it does
  - Tab strip (four tabs or fewer: OmniBrowser.cpp omniDrawTopBar; more: omniF3DrawTabStrip in OmniTabMemory.h) and
    the Tabs panel (OmniTabsPage.h): a speaker icon on a tab whose page reports kWKMediaIsPlayingAudio, a crossed
    speaker on a tab the user muted (shown while muted, playing or not, so the tab can be found again to unmute).
  - Mute: WKPageSetMuted(page, kWKMediaAudioMuted) / kWKMediaNoneMuted (WKPagePrivate.h of this WebKit; the same calls
    the sleep timer uses). WebPageProxy keeps the state and sends it again when the web process is relaunched
    (WebPageCreationParameters::muted), and HTMLMediaElement still reports IsPlayingAudio while the page is muted
    (canProduceAudio is per element), so a muted, playing tab keeps its crossed speaker. Omni's players
    (OmniMediaPlayer, MSE, HLS, progressive) implement setMuted, so the page mute reaches them.
  - Controls: "Mute this tab" / "Unmute this tab" in the hold-Cross page menu (page rows) and in Options > Quick toggles
    (the menu stays open, the tile shows the new state). Tabs panel: Triangle mutes / unmutes the selected tab (Cross
    switches, Square closes, Circle backs: Triangle was the free face button there: omniFxTabsInput returned false for
    it and the panel layer swallowed it); the panel's face hints show "Mute tab" / "Unmute tab" on tab rows.
  - Per tab only, never saved (Tab::omniTaMuted; a new or restored tab starts unmuted).
  - Sleep timer: waking used to set kWKMediaNoneMuted on every tab it had muted: a tab the user muted now stays muted.
  - Cost: WKPageGetMediaState (UI-process cached state, no IPC) for each tab at most every 500 ms from omniF3Tick; the
    shell redraws only when a tab's badge changed (omniShellDirty).

Pure part: engine/entry/OmniTabAudio.h (no SDL/WebKit): badge, 500 ms poll, change detection, labels, icon slots in
both strips. Tested by tools/test_tab_audio.cpp:
  g++ -std=c++20 -I<tree>/engine/entry test_tab_audio.cpp -o t && ./t
Shell side: engine/entry/OmniTabAudioShell.h (included from OmniFeatures.h after OmniFeaturesPanel.h).

Anchors (exactly once each; MARK makes each file idempotent):
  OmniBrowser.cpp    the OmniReadingList.h include line; the end of struct Tab (omniWaitSince line + "};"); the icon
                     enum line (two new icons before omniIconCount) and the last icon shape (the D-pad V);
                     the <=4-tab title line (OMNI_POLISH_V1 private badge room); the omniSleepWake unmute line
  OmniTabMemory.h    the compact strip's title line
  OmniTabsPage.h     the omniF3TabRowValue line, the p.corner line, the Square (X) branch of omniFxTabsInput
  OmniContextMenu.h  the omniRlContextRows(p) line, the omniRlContextAction line
  OmniQuickMenu.h    the omniRlQuickTiles(p) line, the omniMqGroup "return 2" case line (Quick toggles), the
                     omniRlQuickAction line
  OmniFeatures.h     '#include "OmniFeaturesPanel.h"'
  OmniFeatures3.h    the omniRlTick(now) call in omniF3Tick
Apply AFTER apply_reading_list.py (its lines are anchors).
usage: apply_tab_audio.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_TAB_AUDIO_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_TAB_AUDIO_V1: the pure part of the tab sound badges and per-tab mute (no SDL, no WebKit). The shell side is
// OmniTabAudioShell.h; the reasons are in tools/apply_tab_audio.py. Tested on the host with g++ (test_tab_audio.cpp).
#pragma once
#include <cstdint>

namespace OmniTabAudio {

enum Badge : uint8_t { kNone = 0, kPlaying = 1, kMuted = 2 };
constexpr uint32_t kPollMs = 500;   // media state is read at most this often
constexpr int kTile = 440;          // Options tile / page-menu row id (reading list 420/421, add-ons 380/381, V3 301+,
                                    // quick access 700-799, V2 900+)

// A muted tab shows the crossed speaker whether or not it plays (so it can be found to unmute).
inline Badge badge(bool playingAudio, bool muted) { return muted ? kMuted : playingAudio ? kPlaying : kNone; }
// Stores the new badge; true when it changed (the strip is redrawn only then).
inline bool update(uint8_t& stored, Badge now)
{
    if (stored == uint8_t(now)) return false;
    stored = uint8_t(now);
    return true;
}
inline bool reached(uint32_t now, uint32_t at) { return int32_t(now - at) >= 0; }   // SDL_GetTicks wrap-safe
struct Poll {
    uint32_t next = 0;
    bool started = false;
    bool due(uint32_t now)
    {
        if (started && !reached(now, next)) return false;
        started = true;
        next = now + kPollMs;
        return true;
    }
};
inline const char* toggleLabel(bool muted) { return muted ? "Unmute this tab" : "Mute this tab"; }
inline const char* faceLabel(bool muted) { return muted ? "Unmute tab" : "Mute tab"; }
inline const char* toggledNotice(bool nowMuted) { return nowMuted ? "Tab muted" : "Tab sound on"; }
inline const char* rowValue(uint8_t b) { return b == kMuted ? "Muted" : b == kPlaying ? "Playing" : ""; }
// After the sleep timer: the tabs it muted get their sound back unless the user muted them.
inline bool mutedAfterSleep(bool userMuted) { return userMuted; }

// Where the speaker goes on a tab (layout units) and where the title must end.
struct Slot { int iconX, titleRight; };
// Four tabs or fewer: 232 px tabs at x; close cross centred at x + 218; a private tab's badge spans x + 142..202.
inline Slot fixedSlot(int x, bool priv, bool shown)
{
    const int end = x + (priv ? 136 : 202);   // the title's old right edge
    return shown ? Slot { end - 8, end - 24 } : Slot { end - 8, end };
}
// The compact strip: w px tabs at x; the close cross (when closable) centred at x + w - 14.
inline Slot compactSlot(int x, int w, bool closable, bool shown)
{
    const int end = x + w - (closable ? 30 : 10);
    return shown ? Slot { end - 10, end - 22 } : Slot { end - 10, end };
}

} // namespace OmniTabAudio
'''

SHELL = r'''// OMNI_TAB_AUDIO_V1: tab sound badges and per-tab mute (shell side). Included from OmniFeatures.h (inside
// OmniBrowser.cpp's anonymous namespace). The pure part is OmniTabAudio.h; the reasons are in tools/apply_tab_audio.py.
#pragma once

namespace TA = OmniTabAudio;
static TA::Poll omniTaPoll;

static bool omniTaPlaying(const Tab& t)
{
    // UI-process cached state (WebPageProxy::m_mediaState), no IPC; still set while the page is muted.
    return t.page && !t.crashed && (WKPageGetMediaState(t.page) & kWKMediaIsPlayingAudio);
}
static void omniTaToggle(Tab& t)
{
    t.omniTaMuted = !t.omniTaMuted;
    if (t.page) WKPageSetMuted(t.page, t.omniTaMuted ? kWKMediaAudioMuted : kWKMediaNoneMuted);
    TA::update(t.omniTaBadge, TA::badge(omniTaPlaying(t), t.omniTaMuted));
    notice(TA::toggledNotice(t.omniTaMuted));
    omniShellDirty = true;
}
static int omniTaIcon(uint8_t badge) { return badge == TA::kMuted ? omniIconSpeakerMuted : omniIconSpeaker; }

// --- per pass (omniF3Tick) -------------------------------------------------------------------------------------------
static void omniTaTick(uint32_t now)
{
    if (!omniTaPoll.due(now)) return;
    bool changed = false;
    for (auto& t : tabs) changed |= TA::update(t->omniTaBadge, TA::badge(omniTaPlaying(*t), t->omniTaMuted));
    if (changed) omniShellDirty = true;
}

// --- Tabs panel ------------------------------------------------------------------------------------------------------
static void omniTaTabRow(const Tab& t, OmniFxRow& r)
{
    if (!t.omniTaBadge) return;
    r.icon = omniTaIcon(t.omniTaBadge);
    if (r.value.empty()) r.value = TA::rowValue(t.omniTaBadge);
}
static void omniTaTabFaces(OmniFxPanel& p)
{
    if (p.sel >= 0 && p.sel < int(tabs.size()))
        p.faces = { { 0, "Switch" }, { 3, TA::faceLabel(tabs[size_t(p.sel)]->omniTaMuted) }, { 2, "Close tab" }, { 1, "Back" } };
    else p.faces = { { 0, "Switch" }, { 2, "Close tab" }, { 1, "Back" } };
}

// --- Options > Quick toggles, hold-Cross page menu --------------------------------------------------------------------
static OmniFxRow omniTaRow(bool withValue)
{
    Tab* t = active();
    const bool muted = t && t->omniTaMuted;
    OmniFxRow r; r.id = TA::kTile; r.label = TA::toggleLabel(muted); r.enabled = t != nullptr;
    r.icon = muted ? omniIconSpeakerMuted : omniIconSpeaker;
    if (withValue && t) r.value = TA::rowValue(t->omniTaBadge);
    return r;
}
static void omniTaQuickTiles(OmniFxPanel& p) { p.rows.push_back(omniTaRow(true)); }
static bool omniTaQuickAction(int id)
{
    if (id != TA::kTile) return false;
    if (Tab* t = active()) omniTaToggle(*t);   // the menu stays open (the tile shows the new state)
    return true;
}
static void omniTaContextRows(OmniFxPanel& p) { p.rows.push_back(omniTaRow(false)); }
static bool omniTaContextAction(int id)
{
    if (id != TA::kTile) return false;
    omniFxCloseAll();
    if (Tab* t = active()) omniTaToggle(*t);
    return true;
}
'''

ICON_ENUM_OLD = ('enum { omniIconBack, omniIconForward, omniIconReload, omniIconGear, omniIconPlus, omniIconClose, omniIconLock, omniIconShield,\n'
                 '    omniIconShieldHole, omniIconCheck, omniIconBang, omniIconAlert, omniIconDpad, omniIconDpadV, omniIconCount };\n')
ICON_ENUM_NEW = (
    '// OMNI_TAB_AUDIO_V1: speaker (cone + two waves) and the muted speaker (cone + a cross), 20 x 18.\n'
    'static float omniSdSpeakerCone(float x, float y)\n'
    '{\n'
    '    static const SDL_FPoint cone[4] = { { 5.2f, 6.4f }, { 10.2f, 2.8f }, { 10.2f, 15.2f }, { 5.2f, 11.6f } };\n'
    '    return std::min(omniSdBox(x, y, 4.2f, 9, 2.2f, 2.6f, 0.6f), omniSdPoly(cone, 4, x, y));\n'
    '}\n'
    'static float omniSdSpeakerWave(float x, float y, float R)\n'
    '{\n'
    '    const float cx = 10.2f, cy = 9, a = 0.85f;\n'
    '    if (std::fabs(std::atan2(y - cy, x - cx)) <= a) return std::fabs(std::hypot(x - cx, y - cy) - R) - 1.1f;\n'
    '    const float ex = cx + R * std::cos(a), ey = R * std::sin(a);\n'
    '    return std::min(std::hypot(x - ex, y - (cy - ey)), std::hypot(x - ex, y - (cy + ey))) - 1.1f;\n'
    '}\n'
    'enum { omniIconBack, omniIconForward, omniIconReload, omniIconGear, omniIconPlus, omniIconClose, omniIconLock, omniIconShield,\n'
    '    omniIconShieldHole, omniIconCheck, omniIconBang, omniIconAlert, omniIconDpad, omniIconDpadV,\n'
    '    omniIconSpeaker, omniIconSpeakerMuted, omniIconCount }; // OMNI_TAB_AUDIO_V1: the two speakers\n')
ICON_SHAPE_OLD = ('    { 24, 24, [](float x, float y) { return omniSdBox(x, y, 12, 12, 3.6f, 10.5f, 1.6f); } },\n'
                  '};\n')
ICON_SHAPE_NEW = ('    { 24, 24, [](float x, float y) { return omniSdBox(x, y, 12, 12, 3.6f, 10.5f, 1.6f); } },\n'
                  '    { 20, 18, [](float x, float y) { return std::min({ omniSdSpeakerCone(x, y), omniSdSpeakerWave(x, y, 3.8f), omniSdSpeakerWave(x, y, 7) }); } }, // ' + MARK + '\n'
                  '    { 20, 18, [](float x, float y) { return std::min({ omniSdSpeakerCone(x, y), omniSdSeg(x, y, 13.5f, 6.5f, 18.5f, 11.5f, 1.1f), omniSdSeg(x, y, 18.5f, 6.5f, 13.5f, 11.5f, 1.1f) }); } },\n'
                  '};\n')

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniReadingList.h" // OMNI_READING_LIST_V1: reading list index, caps, saved-page wrapper (pure)\n',
         '#include "OmniReadingList.h" // OMNI_READING_LIST_V1: reading list index, caps, saved-page wrapper (pure)\n'
         '#include "OmniTabAudio.h" // OMNI_TAB_AUDIO_V1: tab sound badges, per-tab mute (pure)\n'),
        ('    uint32_t omniWaitSince = 0, omniNoReportTries = 0;\n};\n',
         '    uint32_t omniWaitSince = 0, omniNoReportTries = 0;\n'
         '    bool omniTaMuted = false;  // OMNI_TAB_AUDIO_V1: the user muted this tab (per tab, never saved)\n'
         '    uint8_t omniTaBadge = 0;   // OMNI_TAB_AUDIO_V1: OmniTabAudio::Badge last drawn\n'
         '};\n'),
        (ICON_ENUM_OLD, ICON_ENUM_NEW),
        (ICON_SHAPE_OLD, ICON_SHAPE_NEW),
        ('        omniLabel(title, tx, 30, omniSmall, sel ? T.ink : T.inkDim, 0, int(x + (tab.omniPrivate ? 136 : 202) - tx)); // OMNI_POLISH_V1: room for the private badge\n',
         '        const OmniTabAudio::Slot omniTaSlot = OmniTabAudio::fixedSlot(x, tab.omniPrivate, tab.omniTaBadge != 0); // OMNI_TAB_AUDIO_V1\n'
         '        omniLabel(title, tx, 30, omniSmall, sel ? T.ink : T.inkDim, 0, int(omniTaSlot.titleRight - tx)); // OMNI_POLISH_V1: room for the private badge (and the speaker)\n'
         '        if (tab.omniTaBadge) omniIcon(tab.omniTaBadge == OmniTabAudio::kMuted ? omniIconSpeakerMuted : omniIconSpeaker, omniTaSlot.iconX, 30, sel ? T.ink : T.inkDim);\n'),
        ('        for (WKPageRef page : omniSleepMuted) if (t->page == page) WKPageSetMuted(page, kWKMediaNoneMuted);   // only tabs still open\n',
         '        for (WKPageRef page : omniSleepMuted) if (t->page == page)   // only tabs still open; OMNI_TAB_AUDIO_V1: a tab the user muted stays muted\n'
         '            WKPageSetMuted(page, OmniTabAudio::mutedAfterSleep(t->omniTaMuted) ? kWKMediaAudioMuted : kWKMediaNoneMuted);\n'),
    ],
    'OmniTabMemory.h': [
        ('        omniLabel(title, tx, 30, omniSmall, unloaded ? T.inkFaint : sel ? T.ink : T.inkDim, 0, int(x + w - (closable ? 30 : 10) - tx));\n',
         '        const OmniTabAudio::Slot omniTaSlot = OmniTabAudio::compactSlot(x, w, closable, tab.omniTaBadge != 0); // OMNI_TAB_AUDIO_V1\n'
         '        omniLabel(title, tx, 30, omniSmall, unloaded ? T.inkFaint : sel ? T.ink : T.inkDim, 0, int(omniTaSlot.titleRight - tx));\n'
         '        if (tab.omniTaBadge) omniIcon(tab.omniTaBadge == OmniTabAudio::kMuted ? omniIconSpeakerMuted : omniIconSpeaker, omniTaSlot.iconX, 30, sel ? T.ink : T.inkDim);\n'),
    ],
    'OmniTabsPage.h': [
        ('        omniF3TabRowValue(t, i == selected, r.value); // OMNI_FEATURES_V3: "Unloaded"\n',
         '        omniF3TabRowValue(t, i == selected, r.value); // OMNI_FEATURES_V3: "Unloaded"\n'
         '        omniTaTabRow(t, r); // OMNI_TAB_AUDIO_V1: speaker / crossed speaker, "Playing" / "Muted"\n'),
        ('    p.corner = std::to_string(tabs.size()) + " of " + std::to_string(omniF3TabLimit()); // OMNI_FEATURES_V3\n',
         '    p.corner = std::to_string(tabs.size()) + " of " + std::to_string(omniF3TabLimit()); // OMNI_FEATURES_V3\n'
         '    omniTaTabFaces(p); // OMNI_TAB_AUDIO_V1: Triangle "Mute tab" / "Unmute tab" on tab rows\n'),
        ('        if (b == SDL_CONTROLLER_BUTTON_X) {\n            const Tab* keep',
         '        if (b == SDL_CONTROLLER_BUTTON_Y) { omniTaToggle(*tabs[size_t(r.id)]); return true; } // OMNI_TAB_AUDIO_V1: Triangle mutes / unmutes\n'
         '        if (b == SDL_CONTROLLER_BUTTON_X) {\n            const Tab* keep'),
    ],
    'OmniContextMenu.h': [
        ('        omniRlContextRows(p); // OMNI_READING_LIST_V1: Save page for later\n',
         '        omniRlContextRows(p); // OMNI_READING_LIST_V1: Save page for later\n'
         '        omniTaContextRows(p); // OMNI_TAB_AUDIO_V1: Mute this tab / Unmute this tab\n'),
        ('    if (omniRlContextAction(r.id)) return true; // OMNI_READING_LIST_V1\n',
         '    if (omniRlContextAction(r.id)) return true; // OMNI_READING_LIST_V1\n'
         '    if (omniTaContextAction(r.id)) return true; // OMNI_TAB_AUDIO_V1\n'),
    ],
    'OmniQuickMenu.h': [
        ('    omniRlQuickTiles(p); // OMNI_READING_LIST_V1: Save page for later, Reading list\n',
         '    omniRlQuickTiles(p); // OMNI_READING_LIST_V1: Save page for later, Reading list\n'
         '    omniTaQuickTiles(p); // OMNI_TAB_AUDIO_V1: Mute this tab / Unmute this tab\n'),
        ('    case omniMqBlock: case 303: case omniQmZoomReset: return 2; // existing omniF3Dark; OMNI_SITE_ZOOM_V1: zoom row\n',
         '    case omniMqBlock: case 303: case omniQmZoomReset: return 2; // existing omniF3Dark; OMNI_SITE_ZOOM_V1: zoom row\n'
         '    case OmniTabAudio::kTile: return 2; // OMNI_TAB_AUDIO_V1: Quick toggles\n'),
        ('    if (omniRlQuickAction(r.id)) return true; // OMNI_READING_LIST_V1\n',
         '    if (omniRlQuickAction(r.id)) return true; // OMNI_READING_LIST_V1\n'
         '    if (omniTaQuickAction(r.id)) return true; // OMNI_TAB_AUDIO_V1\n'),
    ],
    'OmniFeatures.h': [
        ('#include "OmniFeaturesPanel.h"\n',
         '#include "OmniFeaturesPanel.h"\n#include "OmniTabAudioShell.h" // OMNI_TAB_AUDIO_V1\n'),
    ],
    'OmniFeatures3.h': [
        ('    omniRlTick(now);    // OMNI_READING_LIST_V1\n',
         '    omniRlTick(now);    // OMNI_READING_LIST_V1\n    omniTaTick(now);    // OMNI_TAB_AUDIO_V1: media state every 500 ms\n'),
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
    if 'OMNI_READING_LIST_V1' not in (root / 'OmniQuickMenu.h').read_bytes().decode('utf-8'):
        sys.exit('OmniQuickMenu.h: OMNI_READING_LIST_V1 missing: apply_reading_list.py first')
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [patch(name, edits) for name, edits in EDITS.items()]
    msgs.append(write_new('OmniTabAudio.h', PURE, 'OmniReadingList.h'))
    msgs.append(write_new('OmniTabAudioShell.h', SHELL, 'OmniFeatures.h'))
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
