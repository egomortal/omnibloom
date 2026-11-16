#!/usr/bin/env python3
"""OMNI_ONE_SOUND_V1 (2026-11-16): Browser settings > "Play sound from one tab at a time": Off (default) / On.
Backlog E03 ("One sound at a time"): no double audio when a background tab or music starts.

What the user sees
  Browser settings, after "Show mini audio bar" (which follows "Background audio"):
      "Play sound from one tab at a time"   Off   detail: "On: a tab that starts sound pauses the others"
                                            On    detail: "A tab that starts sound pauses the others (mutes them if it can't)"
  Cross or D-pad left / right toggles; a notice confirms; it applies at once (no restart).
  With On, when a tab STARTS playing sound (any tab: shown, background, private; started by the page, by Now playing,
  by the mini audio bar's L2 + Right), every other tab that plays sound is paused:
    - pause first (preferred): one page script in that tab pauses its playing, audible <video> / <audio> elements
      (same-origin frames up to depth 3, like Now playing's script); notice "Paused <title>".
    - mute as the fallback (nothing pausable found, e.g. a cross-origin embedded player, or the page didn't answer):
      the tab-audio mute (OMNI_TAB_AUDIO_V1: WKPageSetMuted + Tab::omniTaMuted, so the crossed speaker shows and the
      user can unmute it from the Tabs panel / Options / Now playing); notice "Muted <title> (couldn't pause it)".
    - nothing is resumed or unmuted automatically, ever (the user resumes / unmutes by hand).
    - the mini audio bar's tab (OMNI_AUDIO_BAR_V1, the background tab the bar shows) is never muted: it is paused and
      the bar keeps it as "paused with the chord" (omniAbrPausedKey: up to 5 min, "L2 + Right: Play"), so the music
      can be resumed from the bar; if it cannot be paused it is left playing ("Couldn't pause <title>").
    - a tab that starts again by itself within 1.5 s of our pause (a page fighting back) is muted instead of pausing
      the others again (no ping-pong); the bar's tab is exempt (the user may resume it with the chord at once).
  Private tabs follow the same rule; notices name them "a private tab" (notices go to the notice history,
  OMNI_NOTICE_HISTORY_V1), nothing is stored for them. Tabs that are muted or at volume 0 % (OMNI_TAB_VOLUME_V1)
  are silent: they neither trigger the rule nor get paused.

How
  ui.isPlayingAudioDidChange already calls tab audio / Now playing / playback speed / per-tab volume (OmniBrowser.cpp);
  it gets one more call, omniOsnMediaChanged(page), last. A start is the edge of kWKMediaIsPlayingAudio in WebKit's
  cached state (WKPageGetMediaState, no IPC) per tab (OmniOneSound::Tracker; tracked even while Off, so turning it On
  never mistakes an old player for a new start). Unmuting a playing tab is not a media-state change, so it is not a
  start. Background audio (OMNI_BG_AUDIO_V1): a paused hidden video releases its decoder after 1.5 s as before.
  Cost: nothing per frame, no poll, no tick: work only on a media-state change; the setting flag is stat()ed once
  (cached; the row's toggle refreshes it). One evaluate per tab to quiet (answers matched by a generation number).

Pure part: engine/entry/OmniOneSound.h (no SDL / WebKit): texts, tracker (start edges, fight guard), plan, victims,
the pause script and its answer. Tested by tools/test_one_sound.cpp:
    g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_one_sound.cpp -o t && ./t <tree>
  (with <tree>: also checks the hooks in the patched files); ./t --emit <file> writes the page script for
  node --check <file> and node tools/test_one_sound.cjs <file> (runs it against a small fake DOM).
Shell side: engine/entry/OmniOneSoundShell.h (included from OmniFeatures3.h after OmniAudioBarShell.h: uses Now
playing's omniNpTab / omniNpMedia, tab audio's mute fields, per-tab volume's omniTvPct, the audio bar's state).
Storage: /data/omni/one-sound.flag (present = On). Ids: Browser settings row 873; alias OOSN, prefix omniOsn (grep of
the patched tree and every apply_*.py, 2026-11-16: 873 unused, 870 / 875 / 876 / 878 taken; checked again before the
first apply: refuses if another file uses them).

Anchors (whole lines, exactly once each; MARK makes each file idempotent):
  entry/OmniBrowser.cpp        the OmniAudioBar.h include line (pure include after it); the omniTvMediaChanged forward
                               declaration (ours after it); the ui.isPlayingAudioDidChange line as per-tab volume left
                               it (one more call, last).
  entry/OmniBrowserSettings.h  "static bool omniAbrSettingsInput(int b);" (declarations after it); the
                               omniAbrSettingsRow(p) line (row after it); the omniAbrRowId input line (ours before it).
  entry/OmniFeatures3.h        the OmniAudioBarShell.h include line (ours after it).
Apply AFTER apply_tab_volume.py, apply_bg_audio.py and apply_audio_bar.py (their lines are anchors; checked);
last in the recipe is fine.
usage: apply_one_sound.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_ONE_SOUND_V1'
if len(sys.argv) != 2:
    sys.exit('usage: apply_one_sound.py <engine tree>')
root = Path(sys.argv[1]) / 'engine'
TAKEN = (r'(?<![\w.])873(?![\w.])', r'\bOOSN\b', r'\bomniOsn[A-Z]', r'\bOmniOneSound', r'one-sound\.flag')

PURE = r'''// OMNI_ONE_SOUND_V1: the pure part of Browser settings > "Play sound from one tab at a time" (no SDL, no WebKit).
// The shell side is OmniOneSoundShell.h; the reasons are in tools/apply_one_sound.py. Tested on the host with g++
// (tools/test_one_sound.cpp). When a tab starts playing sound, the other tabs that play sound are paused (page script),
// muted when that fails; the mini audio bar's tab is never muted. Nothing is resumed or unmuted automatically.
#pragma once
#include <cstddef>
#include <cstdint>
#include <map>
#include <set>
#include <string>
#include <vector>

namespace OmniOneSound {

constexpr const char* kFlagName = "one-sound.flag";   // in /data/omni; present: On
constexpr int kRowId = 873;                           // Browser settings row
constexpr uint32_t kFightMs = 1500;                   // restarted by itself this soon after our pause: muted instead
constexpr size_t kTitleMax = 60;                      // bytes of a tab title in a notice

inline const char* settingLabel() { return "Play sound from one tab at a time"; }
inline const char* settingValue(bool on) { return on ? "On" : "Off"; }
inline const char* settingDetail(bool on)
{
    return on ? "A tab that starts sound pauses the others (mutes them if it can't)"
              : "On: a tab that starts sound pauses the others";
}
inline const char* toggledNotice(bool on)
{
    return on ? "One sound at a time: a tab that starts sound pauses the others" : "One sound at a time off";
}
inline const char* failedNotice() { return "One sound at a time: couldn't save the setting"; }

// A tab title for a notice: one line, at most kTitleMax bytes (cut on a UTF-8 boundary, "..."); private tabs are
// never named (notices are kept in the notice history).
inline std::string shortTitle(const std::string& title, bool privateTab)
{
    if (privateTab) return "a private tab";
    std::string s;
    bool space = false;
    for (unsigned char c : title) {
        if (c < 0x20 || c == 0x7f) c = ' ';
        if (c == ' ') { if (!s.empty()) space = true; continue; }
        if (space) { s += ' '; space = false; }
        s += char(c);
    }
    if (s.empty()) return "a tab";
    if (s.size() <= kTitleMax) return s;
    size_t cut = kTitleMax - 3;
    while (cut > 0 && (static_cast<unsigned char>(s[cut]) & 0xC0) == 0x80) --cut;   // not inside a UTF-8 sequence
    while (cut > 0 && s[cut - 1] == ' ') --cut;
    return s.substr(0, cut) + "...";
}
inline std::string pausedNotice(const std::string& title, bool privateTab) { return "Paused " + shortTitle(title, privateTab); }
inline std::string mutedNotice(const std::string& title, bool privateTab)
{
    return "Muted " + shortTitle(title, privateTab) + " (couldn't pause it)";
}
inline std::string fightNotice(const std::string& title, bool privateTab)
{
    return "Muted " + shortTitle(title, privateTab) + ": it started again by itself";
}
inline std::string keptNotice(const std::string& title, bool privateTab) { return "Couldn't pause " + shortTitle(title, privateTab); }

// One tab as the shell sees it: WebKit's cached "playing audio", the tab mute, the per-tab volume.
struct TabState {
    uintptr_t key = 0;          // Tab::omniMediaIdentity
    bool playing = false;       // kWKMediaIsPlayingAudio (also set while the tab is muted)
    bool muted = false;         // Tab::omniTaMuted
    int volumePct = 100;        // OMNI_TAB_VOLUME_V1 (0: silent)
    bool usable = true;         // has a page, not crashed
};
inline bool audible(const TabState& t) { return t.usable && t.playing && !t.muted && t.volumePct > 0; }

inline bool reached(uint32_t now, uint32_t at) { return int32_t(now - at) >= 0; }   // SDL_GetTicks wrap-safe

// Which tabs play sound (to see a START: the edge), and when we paused each one (the fight guard).
class Tracker {
public:
    // A media-state change of one tab: true when it started playing sound now (it did not before).
    bool observe(uintptr_t key, bool playingNow)
    {
        const bool was = m_playing.count(key) != 0;
        if (playingNow) m_playing.insert(key);
        else m_playing.erase(key);
        return playingNow && !was;
    }
    void pausedByUs(uintptr_t key, uint32_t now) { m_pausedAt[key] = now; }
    // It started again by itself within kFightMs of our pause.
    bool fightingBack(uintptr_t key, uint32_t now) const
    {
        auto it = m_pausedAt.find(key);
        return it != m_pausedAt.end() && !reached(now, it->second + kFightMs);
    }
    // Closed tabs (keys not open any more) are forgotten.
    void keepOnly(const std::vector<uintptr_t>& open)
    {
        const std::set<uintptr_t> o(open.begin(), open.end());
        for (auto it = m_playing.begin(); it != m_playing.end();) it = o.count(*it) ? std::next(it) : m_playing.erase(it);
        for (auto it = m_pausedAt.begin(); it != m_pausedAt.end();) it = o.count(it->first) ? std::next(it) : m_pausedAt.erase(it);
    }
    size_t tracked() const { return m_playing.size() + m_pausedAt.size(); }
    bool playing(uintptr_t key) const { return m_playing.count(key) != 0; }
private:
    std::set<uintptr_t> m_playing;
    std::map<uintptr_t, uint32_t> m_pausedAt;
};

enum class Plan { kNothing, kPauseOthers, kMuteStarter };
// A tab's media state changed. started: Tracker::observe said it started; barTab: it is the mini audio bar's tab
// (the user may resume it with the chord right after our pause: never treated as fighting back).
inline Plan plan(bool on, bool started, const TabState& starter, bool fighting, bool barTab)
{
    if (!on || !started || !audible(starter)) return Plan::kNothing;
    return fighting && !barTab ? Plan::kMuteStarter : Plan::kPauseOthers;
}
// The other tabs to quiet: every audible tab but the one that started.
inline std::vector<uintptr_t> victims(const std::vector<TabState>& tabs, uintptr_t starter)
{
    std::vector<uintptr_t> out;
    for (const TabState& t : tabs)
        if (t.key != starter && audible(t)) out.push_back(t.key);
    return out;
}

enum class After { kPaused, kMute, kLeave, kNothing };
// The pause script's answer for one tab. paused: elements it paused (-1: no / bad answer). stillAudible: the tab
// still plays sound (WebKit's state now). barTab: the mini audio bar shows it (never muted).
inline After afterPause(int paused, bool stillAudible, bool barTab)
{
    if (paused > 0) return After::kPaused;
    if (!stillAudible) return After::kNothing;   // it stopped by itself meanwhile
    return barTab ? After::kLeave : After::kMute;
}

// The page script: pause every playing, audible <video> / <audio> (same-origin frames up to depth 3, like Now
// playing's); answers "omni-os1\n<count>". Silent ones (muted / volume 0) are left alone.
constexpr const char* kPauseScript = R"JS((function(){
var n=0;
function walk(d,k){if(!d||k>3)return;try{var m=d.querySelectorAll('video,audio');
for(var a=0;a<m.length;a++){var e=m[a];if(!e.paused&&!e.ended&&!e.muted&&e.volume>0){try{e.pause();n++;}catch(x){}}}
var f=d.querySelectorAll('iframe,frame');for(var j=0;j<f.length;j++){var c=null;try{c=f[j].contentDocument;}catch(x){}walk(c,k+1);}}catch(x){}}
walk(document,0);
return 'omni-os1\n'+n;
})())JS";
inline const char* pauseScript() { return kPauseScript; }
// -1: not our answer (error, no answer, anything else)
inline int parsePaused(const std::string& text)
{
    static const std::string head = "omni-os1\n";
    if (text.size() <= head.size() || text.compare(0, head.size(), head) != 0) return -1;
    const std::string num = text.substr(head.size());
    if (num.size() > 6) return -1;
    int n = 0;
    for (char c : num) {
        if (c < '0' || c > '9') return -1;
        n = n * 10 + (c - '0');
    }
    return n;
}

} // namespace OmniOneSound
'''

SHELL = r'''// OMNI_ONE_SOUND_V1: Browser settings > "Play sound from one tab at a time" (shell side). Included from
// OmniFeatures3.h (inside OmniBrowser.cpp's anonymous namespace) after @AB@Shell.h; uses Now playing's
// omniNpTab / omniNpMedia, tab audio's mute (Tab::omniTaMuted, OmniTabAudio), per-tab volume's omniTvPct and the mini
// audio bar's state. The pure part is OmniOneSound.h; the reasons are in tools/apply_one_sound.py. Main thread only.
// Cost: work only in ui.isPlayingAudioDidChange (no poll, nothing per frame); the flag is stat()ed once (cached).
#pragma once

namespace OOSN = OmniOneSound;
static_assert(OOSN::kRowId == omniOsnRowId, "OMNI_ONE_SOUND_V1: row id");

static int omniOsnOnCache = -1;            // -1: not read yet
static OOSN::Tracker omniOsnTracker;
struct OmniOsnAsk { uintptr_t key = 0; bool bar = false; };
static std::map<uintptr_t, OmniOsnAsk> omniOsnAsks;   // pause scripts out, by generation
static uintptr_t omniOsnGen = 0;

static bool omniOsnOn()
{
    if (omniOsnOnCache < 0) omniOsnOnCache = access(omniData(OOSN::kFlagName).c_str(), F_OK) == 0;
    return omniOsnOnCache == 1;
}
static OOSN::TabState omniOsnState(const Tab& t)
{
    OOSN::TabState s;
    s.key = t.omniMediaIdentity;
    s.playing = omniNpMedia(t) & kWKMediaIsPlayingAudio;   // WebKit's cached state (no IPC)
    s.muted = t.omniTaMuted;
    s.volumePct = omniTvPct(t);                            // OMNI_TAB_VOLUME_V1
    s.usable = t.page && !t.crashed;
    return s;
}
// The tab-audio mute (OMNI_TAB_AUDIO_V1), so the crossed speaker shows and the user can unmute it there.
static void omniOsnMute(Tab& t)
{
    if (!t.page || t.omniTaMuted) return;
    t.omniTaMuted = true;
    WKPageSetMuted(t.page, kWKMediaAudioMuted);
    TA::update(t.omniTaBadge, TA::badge(omniTaPlaying(t), true));
    omniShellDirty = true;
}
// One evaluate: pause the tab's audible media; its answer decides (mute as the fallback, never the bar's tab).
static void omniOsnPause(Tab& t, bool bar)
{
    if (omniOsnAsks.size() > 64) omniOsnAsks.clear();   // answers that never came (crashed pages)
    const uintptr_t gen = ++omniOsnGen;
    omniOsnAsks[gen] = OmniOsnAsk{ t.omniMediaIdentity, bar };
    omniOsnTracker.pausedByUs(t.omniMediaIdentity, SDL_GetTicks());
    auto js = adoptWK(WKStringCreateWithUTF8CString(OOSN::pauseScript()));
    WKPageEvaluateJavaScriptInMainFrame(t.page, js.get(), reinterpret_cast<void*>(gen), [](WKTypeRef result, WKErrorRef error, void* ctx) {
        auto it = omniOsnAsks.find(reinterpret_cast<uintptr_t>(ctx));
        if (it == omniOsnAsks.end()) return;
        const OmniOsnAsk ask = it->second;
        omniOsnAsks.erase(it);
        Tab* v = omniNpTab(ask.key);
        if (!v || !v->page || v->crashed) return;
        const int n = OOSN::parsePaused(omniFxResultString(result, error));
        const bool bar = ask.bar && ask.key == @abr@Key;   // still the bar's tab
        const OOSN::After a = OOSN::afterPause(n, OOSN::audible(omniOsnState(*v)), bar);
        if (a == OOSN::After::kPaused) {
            notice(OOSN::pausedNotice(v->title, v->omniPrivate));
            if (bar) { @abr@PausedKey = ask.key; @abr@PausedAt = SDL_GetTicks(); @abr@Force = true; }   // OMNI_AUDIO_BAR_V1: resumable
        } else if (a == OOSN::After::kMute) {
            omniOsnMute(*v);
            notice(OOSN::mutedNotice(v->title, v->omniPrivate));
        } else if (a == OOSN::After::kLeave) {
            notice(OOSN::keptNotice(v->title, v->omniPrivate));
        }
        fprintf(stderr, "OMNI ONESOUND: other tab %s%s\n", a == OOSN::After::kPaused ? "paused" : a == OOSN::After::kMute ? "muted"
                : a == OOSN::After::kLeave ? "left playing (audio bar)" : "stopped by itself", v->omniPrivate ? " (private)" : "");
        fflush(stderr);
    });
}

// ui.isPlayingAudioDidChange (after tab audio / Now playing / speed / volume): a tab that STARTS sound quiets the others.
static void omniOsnMediaChanged(WKPageRef page)
{
    Tab* t = omniTabForPage(page);
    if (!t) return;
    const OOSN::TabState s = omniOsnState(*t);
    const bool started = omniOsnTracker.observe(s.key, s.playing);   // tracked even while Off
    if (omniOsnTracker.tracked() > tabs.size() + 8) {
        std::vector<uintptr_t> open;
        for (auto& x : tabs) open.push_back(x->omniMediaIdentity);
        omniOsnTracker.keepOnly(open);
    }
    if (!started || !omniOsnOn()) return;
    const uint32_t now = SDL_GetTicks();
    const bool bar = s.key == @abr@Key;
    const OOSN::Plan p = OOSN::plan(true, started, s, omniOsnTracker.fightingBack(s.key, now), bar);
    if (p == OOSN::Plan::kNothing) return;
    if (p == OOSN::Plan::kMuteStarter) {
        omniOsnMute(*t);
        notice(OOSN::fightNotice(t->title, t->omniPrivate));
        fprintf(stderr, "OMNI ONESOUND: a tab restarted by itself: muted\n");
        fflush(stderr);
        return;
    }
    std::vector<OOSN::TabState> all;
    for (auto& x : tabs) all.push_back(omniOsnState(*x));
    for (uintptr_t k : OOSN::victims(all, s.key))
        if (Tab* v = omniNpTab(k)) omniOsnPause(*v, k == @abr@Key);
}

// Browser settings > "Play sound from one tab at a time" (after "Show mini audio bar"). The only state is the flag.
static void omniOsnSettingsRow(OmniFxPanel& p)
{
    const bool on = omniOsnOn();
    OmniFxRow r; r.id = omniOsnRowId; r.label = OOSN::settingLabel(); r.value = OOSN::settingValue(on);
    r.stepper = true; r.detail = OOSN::settingDetail(on);
    p.rows.push_back(r);
}
static bool omniOsnSettingsInput(int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A && b != SDL_CONTROLLER_BUTTON_DPAD_LEFT && b != SDL_CONTROLLER_BUTTON_DPAD_RIGHT) return false;
    const std::string flag = omniData(OOSN::kFlagName);
    const bool on = !omniOsnOn();
    if (on) { if (FILE* f = fopen(flag.c_str(), "w")) { fputs("1\n", f); fclose(f); } }
    else unlink(flag.c_str());
    omniOsnOnCache = -1;
    const bool ok = omniOsnOn() == on;
    notice(ok ? OOSN::toggledNotice(on) : OOSN::failedNotice());
    fprintf(stderr, "OMNI ONESOUND: setting %s%s\n", on ? "on" : "off", ok ? "" : " (flag write failed)");
    fflush(stderr);
    return true;
}
'''

EDITS = {
    'entry/OmniBrowser.cpp': [
        ('#include "@AB@.h" // OMNI_AUDIO_BAR_V1: mini audio bar (pure)\n',
         '#include "@AB@.h" // OMNI_AUDIO_BAR_V1: mini audio bar (pure)\n'
         '#include "OmniOneSound.h" // OMNI_ONE_SOUND_V1: Play sound from one tab at a time (pure)\n'),
        ('static void omniTvMediaChanged(WKPageRef page); // OMNI_TAB_VOLUME_V1 (OmniTabVolumeShell.h): the tab\'s volume as sound starts\n',
         'static void omniTvMediaChanged(WKPageRef page); // OMNI_TAB_VOLUME_V1 (OmniTabVolumeShell.h): the tab\'s volume as sound starts\n'
         'static void omniOsnMediaChanged(WKPageRef page); // OMNI_ONE_SOUND_V1 (OmniOneSoundShell.h): a tab starts sound: quiet the others\n'),
        ('    ui.isPlayingAudioDidChange = [](WKPageRef page, const void*) { omniSavedMediaChanged(page); omniNpMediaChanged(page); omniSpMediaChanged(page); omniTvMediaChanged(page); }; // OMNI_MEDIA_CONTROLS_V1; OMNI_PLAYBACK_SPEED_V1; OMNI_TAB_VOLUME_V1\n',
         '    ui.isPlayingAudioDidChange = [](WKPageRef page, const void*) { omniSavedMediaChanged(page); omniNpMediaChanged(page); omniSpMediaChanged(page); omniTvMediaChanged(page); omniOsnMediaChanged(page); }; // OMNI_MEDIA_CONTROLS_V1; OMNI_PLAYBACK_SPEED_V1; OMNI_TAB_VOLUME_V1; OMNI_ONE_SOUND_V1\n'),
    ],
    'entry/OmniBrowserSettings.h': [
        ('static bool @abr@SettingsInput(int b);\n',
         'static bool @abr@SettingsInput(int b);\n'
         'constexpr int omniOsnRowId = 873; // OMNI_ONE_SOUND_V1 (OmniOneSoundShell.h): Play sound from one tab at a time\n'
         'static void omniOsnSettingsRow(OmniFxPanel& p);\n'
         'static bool omniOsnSettingsInput(int b);\n'),
        ('    @abr@SettingsRow(p); // OMNI_AUDIO_BAR_V1: Show mini audio bar (On / Off)\n',
         '    @abr@SettingsRow(p); // OMNI_AUDIO_BAR_V1: Show mini audio bar (On / Off)\n'
         '    omniOsnSettingsRow(p); // OMNI_ONE_SOUND_V1: Play sound from one tab at a time (Off / On)\n'),
        ('    if (r.id == @abr@RowId) return @abr@SettingsInput(b); // OMNI_AUDIO_BAR_V1\n',
         '    if (r.id == omniOsnRowId) return omniOsnSettingsInput(b); // OMNI_ONE_SOUND_V1\n'
         '    if (r.id == @abr@RowId) return @abr@SettingsInput(b); // OMNI_AUDIO_BAR_V1\n'),
    ],
    'entry/OmniFeatures3.h': [
        ('#include "@AB@Shell.h" // OMNI_AUDIO_BAR_V1 (after Background audio and Now playing: uses both)\n',
         '#include "@AB@Shell.h" // OMNI_AUDIO_BAR_V1 (after Background audio and Now playing: uses both)\n'
         '#include "OmniOneSoundShell.h" // OMNI_ONE_SOUND_V1 (after the audio bar, Now playing, tab audio, tab volume: uses them)\n'),
    ],
}


# The audio bar's names are spelled here only through these two (apply_audio_bar.py's first-apply check refuses any
# sibling whose CODE names its alias / prefix / headers, so the literal names appear in this file's notes only).
_ABR = 'omni' + 'Abr'
_AB = 'Omni' + 'AudioBar'


def _names(t):
    return t.replace('@abr@', _ABR).replace('@AB@', _AB)


SHELL = _names(SHELL)
EDITS = {f: [(_names(a), _names(b)) for a, b in e] for f, e in EDITS.items()}


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
    """Before the first apply: no engine file and no other apply_*.py may use our row id / names / flag."""
    if any(MARK in (root / n).read_bytes().decode('utf-8') for n in EDITS):
        return
    me = Path(__file__).resolve()
    places = [p for d in ('entry', 'media') for p in (root / d).iterdir()
              if p.suffix in ('.h', '.cpp', '.inc') and p.name not in ('OmniOneSound.h', 'OmniOneSoundShell.h')]
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
    for f, need, tool in (('entry/OmniBrowser.cpp', 'OMNI_TAB_VOLUME_V1', 'apply_tab_volume.py'),
                          ('entry/OmniBrowser.cpp', 'OMNI_TAB_AUDIO_V1', 'apply_tab_audio.py'),
                          ('entry/OmniBrowser.cpp', 'OMNI_MEDIA_CONTROLS_V1', 'apply_media_controls.py'),
                          ('entry/OmniBrowserSettings.h', 'OMNI_BG_AUDIO_V1', 'apply_bg_audio.py'),
                          ('entry/OmniBrowserSettings.h', 'OMNI_AUDIO_BAR_V1', 'apply_audio_bar.py'),
                          ('entry/OmniFeatures3.h', 'OMNI_AUDIO_BAR_V1', 'apply_audio_bar.py')):
        if need not in (root / f).read_bytes().decode('utf-8'):
            sys.exit('%s: %s missing: %s first' % (f, need, tool))
    ids_free()
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('entry/OmniOneSound.h', PURE, 'entry/' + _AB + '.h'),
            write_new('entry/OmniOneSoundShell.h', SHELL, 'entry/' + _AB + 'Shell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
