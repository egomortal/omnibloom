#!/usr/bin/env python3
"""OMNI_TAB_VOLUME_V1 (2026-11-16): per-tab volume, 0-100 % in 10 % steps (next to the existing per-tab mute).
E.g. keep a background music tab at 20 % while a video plays in another tab at 100 %.

What the user sees
  - "Now playing" (OMNI_MEDIA_CONTROLS_V1) gets two rows after "Speed" (OMNI_PLAYBACK_SPEED_V1), before the mute row:
      "Volume  < 70% >"                 D-pad left / right: 10 % quieter / louder (stops at 0 % / 100 %);
                                         Cross: back to 100 %. Notice "Volume: 70%".
      "Remember for this site   Off"     Cross: on / off. On: the tab's volume is stored for the site
                                         (/data/omni/site-volume.txt) and every tab of that site starts at it.
                                         Private tabs: remembered until Omni closes, in memory only, and never shown
                                         to or read by normal tabs (normal tabs never read private choices, private
                                         tabs never read the saved file). Disabled ("-") on pages without an http(s) host.
    While the tab is muted the Volume row says so in its detail ("Muted: ..."); mute and volume are independent
    (WebKit: effectiveMuted || effectiveVolume), so unmuting comes back at the chosen volume.
  - Per tab for the session (memory only, keyed by Tab::omniMediaIdentity): a value set in a tab stays with that tab
    when it navigates elsewhere; a tab with no value of its own follows the remembered site value, else 100 %.
  - Tabs panel: no row / button. Checked: Triangle = mute (OMNI_TAB_AUDIO_V1), D-pad left / right = pin
    (OMNI_PINNED_TABS_V1), hold-Cross = groups (OMNI_TAB_GROUPS_V1), Cross / Square / Circle taken, L1 / R1 page the
    panel: nothing free, so Now playing only.

How (checked in this tree)
  WKPageSetMediaVolume(page, 0..1) (WKPagePrivate.h:100, defined in UIProcess/API/C/WKPage.cpp next to WKPageSetMuted,
  WK_EXPORT, compiled into the static OmniEngine like the WKPageSetMuted the tab mute already links) ->
  WebPageProxy::setMediaVolume (caches m_mediaVolume, returns early when unchanged, sends WebPage::SetMediaVolume;
  WebPageCreationParameters::mediaVolume re-sends it when the web process is relaunched) -> Page::setMediaVolume ->
  every HTMLMediaElement::mediaVolumeDidChange -> updateVolume -> MediaPlayer::setVolume(effectiveVolume()), where
  effectiveVolume = element volume x page media volume (m_volumeLocked is iOS-only, false here). ENABLE_WEB_AUDIO is 0
  in this build, so all page sound is media elements.
  Omni's own players follow it: OmniMSEPlayer (hole-punch / HW decode: setVolume -> m_audioRing->setGain, applied as it
  plays and refreshed every tick), OmniHlsPlayer (ring gain), OmniProgressivePlayer and OmniMediaPlayer (gain per
  chunk) all implement setVolume; OmniHwService only decodes video, the audio is mixed in the player in the web
  process, so there is no separate volume path. Page volume does not change element.volume, so page scripts (YouTube's
  slider), the fullscreen D-pad up / down (YouTube's keys) and the sleep timer's fade (element volume script) multiply
  with it. At 0 % the page still reports IsPlayingAudio (canProduceAudio reads element volume), so Now playing keeps
  finding the tab.
  When it is applied: on a change (one call), on every media-state change of a tab (ui.isPlayingAudioDidChange: a new
  WKPageRef from an unloaded / restored tab, or a navigation to a remembered site, gets its volume as sound starts;
  the UI-process early return makes repeats free), and from omniF3Tick at most every 500 ms only while something is
  set (no tab value, nothing remembered: the tick returns at once). A tab never touched at 100 % gets no call.

Pure part: engine/entry/OmniTabVolume.h (no SDL / WebKit): steps, labels, notices, resolve order, remember toggle,
the site file format (parse / serialize, caps), the apply decision, the 500 ms poll. Tested by tools/test_tab_volume.cpp:
  g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_tab_volume.cpp -o t && ./t
Shell side: engine/entry/OmniTabVolumeShell.h (included from OmniFeatures3.h just before OmniPlaybackSpeedShell.h, so
before OmniMediaControlsShell.h whose omniNpBuild / omniNpInput call omniTvNpRows / omniTvNpInput).

Anchors (exactly once each; MARK makes each file idempotent; all insert-before / insert-after, except the
isPlayingAudioDidChange line, which gets one more call):
  OmniBrowser.cpp           the OmniPlaybackSpeed.h include line (pure include after it); the omniSpShortcut forward
                            declaration (ours after it); the ui.isPlayingAudioDidChange line as playback speed left it.
  OmniFeatures3.h           the OmniPlaybackSpeedShell.h include line (our shell before it); the omniTaTick(now) line of
                            omniF3Tick (our tick after it).
  OmniMediaControlsShell.h  the omniSpNpRow(p, *t) line of omniNpBuild (our rows after it); the omniSpInput line at the
                            head of omniNpInput (ours after it).
Order: apply_media_controls.py rewrites OmniMediaControlsShell.h whenever it differs, and the anchors are playback
speed's lines: run AFTER apply_playback_speed.py (checked). Uses Tab::omniTaMuted / omniIconSpeaker (apply_tab_audio.py).
usage: apply_tab_volume.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_TAB_VOLUME_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_TAB_VOLUME_V1: the pure part of per-tab volume (no SDL, no WebKit). The shell side is OmniTabVolumeShell.h;
// the reasons are in tools/apply_tab_volume.py. Tested on the host with g++ (test_tab_volume.cpp).
#pragma once
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <map>
#include <string>

namespace OmniTabVolume {

constexpr int kStep = 10;
constexpr int kFull = 100;
constexpr int kUnset = -1;                 // a tab with no value of its own
constexpr int kRowVolume = 42;             // Now playing rows (MC rows 1..8, sleep timer 40, speed 41)
constexpr int kRowRemember = 43;
constexpr uint32_t kPollMs = 500;
constexpr const char* kFileName = "site-volume.txt";
constexpr const char* kHeader = "omni-site-volume-1";
constexpr size_t kMaxSites = 500;
constexpr long kMaxFileBytes = 64 * 1024;
constexpr size_t kMaxSiteLen = 253;

// Nearest 10 % step in 0..100 (anything out of range is clamped).
inline int clampPct(int pct)
{
    if (pct <= 0) return 0;
    if (pct >= kFull) return kFull;
    return (pct + kStep / 2) / kStep * kStep;
}
// D-pad: one step (dir -1 / +1), stopping at 0 % / 100 %.
inline int step(int pct, int dir) { return clampPct(clampPct(pct) + (dir > 0 ? kStep : dir < 0 ? -kStep : 0)); }
inline float gain(int pct) { return float(clampPct(pct)) / 100.0f; }
inline std::string label(int pct) { return std::to_string(clampPct(pct)) + "%"; }
inline std::string notice(int pct) { return "Volume: " + label(pct); }
inline const char* rememberLabel() { return "Remember for this site"; }
inline const char* rememberValue(bool on) { return on ? "On" : "Off"; }
inline std::string rememberDetail(const std::string& site, bool privateTab)
{
    if (site.empty()) return "Only for web sites";
    return privateTab ? "Private tab: until Omni closes, private tabs only" : "Tabs of " + site + " start at this volume";
}
inline const char* mutedDetail() { return "Muted: the tab plays at this volume when unmuted"; }

// What a tab plays at: its own value, else the remembered site value, else 100 %.
inline int resolve(int tabPct, bool siteHas, int sitePct)
{
    if (tabPct >= 0) return clampPct(tabPct);
    return siteHas ? clampPct(sitePct) : kFull;
}

// A site key as OmniMediaControls::site() gives it ("example.com", "[::1]"): one line, no tab, no spaces.
inline bool validSite(const std::string& s)
{
    if (s.empty() || s.size() > kMaxSiteLen) return false;
    for (unsigned char c : s) if (c <= ' ' || c == 0x7f) return false;
    return true;
}

// Remembered volumes per site (the saved file for normal tabs; a second, memory-only one for private tabs).
class Sites {
public:
    bool get(const std::string& site, int& pct) const
    {
        auto it = m_.find(site);
        if (it == m_.end()) return false;
        pct = it->second;
        return true;
    }
    bool has(const std::string& site) const { return m_.count(site) != 0; }
    // false: not stored (bad key, or full and the site is new)
    bool set(const std::string& site, int pct)
    {
        if (!validSite(site)) return false;
        if (m_.size() >= kMaxSites && !m_.count(site)) return false;
        m_[site] = clampPct(pct);
        return true;
    }
    bool erase(const std::string& site) { return m_.erase(site) != 0; }
    bool empty() const { return m_.empty(); }
    size_t size() const { return m_.size(); }
    const std::map<std::string, int>& all() const { return m_; }
private:
    std::map<std::string, int> m_;
};

// "omni-site-volume-1\n<site>\t<pct>\n..." (another header: nothing is read; bad lines are skipped).
inline Sites parse(const std::string& text)
{
    Sites out;
    size_t pos = 0;
    bool first = true;
    while (pos < text.size()) {
        size_t nl = text.find('\n', pos);
        if (nl == std::string::npos) nl = text.size();
        std::string line = text.substr(pos, nl - pos);
        pos = nl + 1;
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (first) { first = false; if (line != kHeader) return out; continue; }
        const size_t tab = line.find('\t');
        if (tab == std::string::npos) continue;
        const std::string site = line.substr(0, tab), num = line.substr(tab + 1);
        if (num.empty() || num.size() > 3) continue;
        bool digits = true;
        for (char c : num) if (c < '0' || c > '9') digits = false;
        if (!digits) continue;
        const int pct = std::atoi(num.c_str());
        if (pct > kFull) continue;
        out.set(site, pct);
    }
    return out;
}
inline std::string serialize(const Sites& s)
{
    std::string out = std::string(kHeader) + "\n";
    for (const auto& kv : s.all()) out += kv.first + "\t" + std::to_string(kv.second) + "\n";
    return out;
}

// A press on the Volume row: the tab's value; also the site's while it is remembered.
inline int setVolume(Sites& sites, const std::string& site, int& tabPct, int pct)
{
    tabPct = clampPct(pct);
    if (!site.empty() && sites.has(site)) sites.set(site, tabPct);
    return tabPct;
}
enum class Remember { kOn, kOff, kFull, kNoSite };
// Cross on "Remember for this site". Forgetting keeps this tab at the volume it plays at now.
inline Remember toggleRemember(Sites& sites, const std::string& site, int& tabPct)
{
    if (!validSite(site)) return Remember::kNoSite;
    int cur = kFull;
    if (sites.get(site, cur)) {
        if (tabPct < 0) tabPct = cur;
        sites.erase(site);
        return Remember::kOff;
    }
    return sites.set(site, resolve(tabPct, false, 0)) ? Remember::kOn : Remember::kFull;
}
inline std::string rememberNotice(Remember r, const std::string& site, bool privateTab)
{
    switch (r) {
    case Remember::kOn: return "Volume remembered for " + site + (privateTab ? " (until Omni closes)" : "");
    case Remember::kOff: return "Volume for " + site + " forgotten";
    case Remember::kFull: return "Too many sites remembered";
    default: return "Only for web sites";
    }
}
// Should WKPageSetMediaVolume be called? (page: the tab's page now; applied*: what the last call set)
inline bool needsApply(const void* appliedPage, int appliedPct, const void* page, int pct, bool force)
{
    if (!page) return false;
    return force || page != appliedPage || clampPct(pct) != appliedPct;
}
// A tab with nothing set that plays at 100 %: no call at all (WebPageProxy starts at 1).
inline bool untouched(bool hasEntry, int pct) { return !hasEntry && clampPct(pct) == kFull; }

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

} // namespace OmniTabVolume
'''

SHELL = r'''// OMNI_TAB_VOLUME_V1: per-tab volume (shell side). Included from OmniFeatures3.h (inside OmniBrowser.cpp's anonymous
// namespace, just before OmniPlaybackSpeedShell.h, so before OmniMediaControlsShell.h, whose omniNpBuild / omniNpInput
// call omniTvNpRows / omniTvNpInput). The pure part is OmniTabVolume.h; the reasons are in tools/apply_tab_volume.py.
// Main thread only; the site file is written by omniIoQueue; nothing is injected into pages.
#pragma once

namespace OTVL = OmniTabVolume;
struct OmniTvTab {
    int pct = OTVL::kUnset;                // the tab's own value (per tab, this session)
    WKPageRef page = nullptr;              // the page the last WKPageSetMediaVolume went to
    int applied = -1;                      // and the value it set
};
static std::map<uintptr_t, OmniTvTab> omniTvTabs;   // by Tab::omniMediaIdentity
static OTVL::Sites omniTvSaved;                      // site-volume.txt (normal tabs only)
static OTVL::Sites omniTvPrivate;                    // private tabs: this run only, never written, never read by normal tabs
static bool omniTvLoaded = false;
static OTVL::Poll omniTvPoll;

static void omniTvLoad()
{
    if (omniTvLoaded) return;
    omniTvLoaded = true;
    FILE* f = fopen(omniData(OTVL::kFileName).c_str(), "rb");
    if (!f) return;
    std::string text;
    char buf[4096];
    size_t n;
    while ((n = fread(buf, 1, sizeof buf, f)) > 0 && long(text.size()) < OTVL::kMaxFileBytes) text.append(buf, n);
    fclose(f);
    omniTvSaved = OTVL::parse(text);
}
static void omniTvWrite()
{
    if (omniTestMode()) return;
    omniIoQueue(omniData(OTVL::kFileName), OTVL::serialize(omniTvSaved), false);
}
static std::string omniTvSite(const Tab& t) { return OmniMediaControls::site(t.url); }
static OTVL::Sites& omniTvSites(const Tab& t) { return t.omniPrivate ? omniTvPrivate : omniTvSaved; }
static int omniTvPct(const Tab& t)
{
    omniTvLoad();
    auto it = omniTvTabs.find(t.omniMediaIdentity);
    const int own = it == omniTvTabs.end() ? OTVL::kUnset : it->second.pct;
    if (own >= 0) return OTVL::clampPct(own);
    int sitePct = OTVL::kFull;
    const std::string site = omniTvSite(t);
    const bool has = !site.empty() && omniTvSites(t).get(site, sitePct);
    return OTVL::resolve(own, has, sitePct);
}
// force: call even when the last call set the same value on this WKPageRef (WebPageProxy returns early if unchanged).
static void omniTvApply(Tab& t, bool force)
{
    if (!t.page || t.crashed) return;
    const int pct = omniTvPct(t);
    auto it = omniTvTabs.find(t.omniMediaIdentity);
    if (OTVL::untouched(it != omniTvTabs.end(), pct)) return;
    if (it == omniTvTabs.end()) it = omniTvTabs.emplace(t.omniMediaIdentity, OmniTvTab()).first;
    OmniTvTab& e = it->second;
    if (!OTVL::needsApply(e.page, e.applied, t.page, pct, force)) return;
    WKPageSetMediaVolume(t.page, OTVL::gain(pct));
    e.page = t.page;
    e.applied = OTVL::clampPct(pct);
}

// --- per pass (omniF3Tick): a new page of a tab, a navigation to a remembered site ------------------------------------
static void omniTvTick(uint32_t now)
{
    if (!omniTvPoll.due(now)) return;
    omniTvLoad();
    if (omniTvTabs.empty() && omniTvSaved.empty() && omniTvPrivate.empty()) return;   // nothing set: nothing to do
    for (auto it = omniTvTabs.begin(); it != omniTvTabs.end();) {   // closed tabs
        bool open = false;
        for (auto& t : tabs) if (t->omniMediaIdentity == it->first) { open = true; break; }
        it = open ? std::next(it) : omniTvTabs.erase(it);
    }
    for (auto& t : tabs) omniTvApply(*t, false);
}
// ui.isPlayingAudioDidChange: sound starts / stops in a tab -> its volume (again; free when unchanged).
static void omniTvMediaChanged(WKPageRef page)
{
    Tab* t = omniTabForPage(page);
    if (t) omniTvApply(*t, true);
}

// --- Now playing (OMNI_MEDIA_CONTROLS_V1) ---------------------------------------------------------------------------
static void omniTvNpRows(OmniFxPanel& p, const Tab& t)
{
    OmniFxRow r; r.id = OTVL::kRowVolume; r.label = "Volume"; r.value = OTVL::label(omniTvPct(t)); r.stepper = true;
    if (t.omniTaMuted) r.detail = OTVL::mutedDetail();   // OMNI_TAB_AUDIO_V1 mute stays separate
    p.rows.push_back(r);
    const std::string site = omniTvSite(t);
    OmniFxRow m; m.id = OTVL::kRowRemember; m.label = OTVL::rememberLabel(); m.enabled = !site.empty();
    m.value = site.empty() ? std::string("-") : std::string(OTVL::rememberValue(omniTvSites(t).has(site)));
    m.detail = OTVL::rememberDetail(site, t.omniPrivate);
    p.rows.push_back(m);
}
static bool omniTvNpOwns(int id) { return id == OTVL::kRowVolume || id == OTVL::kRowRemember; }
// Volume: D-pad left / right one step, Cross 100 %. Remember: Cross. false: not ours (the panel's own keys).
static bool omniTvNpInput(uintptr_t key, int id, int b)
{
    const bool left = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT, right = b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT;
    if (b != SDL_CONTROLLER_BUTTON_A && !(id == OTVL::kRowVolume && (left || right))) return false;
    Tab* t = nullptr;
    if (key) for (auto& x : tabs) if (x->omniMediaIdentity == key) { t = x.get(); break; }
    if (!t) { notice("That tab is closed"); return true; }
    omniTvLoad();
    const std::string site = omniTvSite(*t);
    OTVL::Sites& sites = omniTvSites(*t);
    const bool saved = !t->omniPrivate;
    if (id == OTVL::kRowVolume) {
        const int cur = omniTvPct(*t);
        const int next = b == SDL_CONTROLLER_BUTTON_A ? OTVL::kFull : OTVL::step(cur, right ? 1 : -1);
        if (next == cur) { notice(OTVL::notice(cur)); return true; }   // at 0 % / 100 % already
        const bool remembered = !site.empty() && sites.has(site);
        OTVL::setVolume(sites, site, omniTvTabs[key].pct, next);
        if (remembered && saved) omniTvWrite();
        omniTvApply(*t, true);
        notice(OTVL::notice(next));
        fprintf(stderr, "OMNI TAB VOLUME: %d\n", next); fflush(stderr);
    } else {
        if (site.empty()) return true;
        const OTVL::Remember res = OTVL::toggleRemember(sites, site, omniTvTabs[key].pct);
        if (saved && (res == OTVL::Remember::kOn || res == OTVL::Remember::kOff)) omniTvWrite();
        omniTvApply(*t, true);
        notice(OTVL::rememberNotice(res, site, t->omniPrivate));
    }
    if (!omniFxStack.empty()) omniFxRefresh(); else omniShellDirty = true;
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniPlaybackSpeed.h" // OMNI_PLAYBACK_SPEED_V1: playback speed steps, memory, script (pure)\n',
         '#include "OmniPlaybackSpeed.h" // OMNI_PLAYBACK_SPEED_V1: playback speed steps, memory, script (pure)\n'
         '#include "OmniTabVolume.h" // OMNI_TAB_VOLUME_V1: per-tab volume steps, site file, remember (pure)\n'),
        ('static void omniSpShortcut();                   // OMNI_PLAYBACK_SPEED_V1: touchpad in fullscreen: the next speed\n',
         'static void omniSpShortcut();                   // OMNI_PLAYBACK_SPEED_V1: touchpad in fullscreen: the next speed\n'
         'static void omniTvMediaChanged(WKPageRef page); // OMNI_TAB_VOLUME_V1 (OmniTabVolumeShell.h): the tab\'s volume as sound starts\n'),
        ('    ui.isPlayingAudioDidChange = [](WKPageRef page, const void*) { omniSavedMediaChanged(page); omniNpMediaChanged(page); omniSpMediaChanged(page); }; // OMNI_MEDIA_CONTROLS_V1; OMNI_PLAYBACK_SPEED_V1\n',
         '    ui.isPlayingAudioDidChange = [](WKPageRef page, const void*) { omniSavedMediaChanged(page); omniNpMediaChanged(page); omniSpMediaChanged(page); omniTvMediaChanged(page); }; // OMNI_MEDIA_CONTROLS_V1; OMNI_PLAYBACK_SPEED_V1; OMNI_TAB_VOLUME_V1\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniPlaybackSpeedShell.h" // OMNI_PLAYBACK_SPEED_V1 (before media controls: its panel calls ours)\n',
         '#include "OmniTabVolumeShell.h" // OMNI_TAB_VOLUME_V1 (before media controls: its panel calls ours)\n'
         '#include "OmniPlaybackSpeedShell.h" // OMNI_PLAYBACK_SPEED_V1 (before media controls: its panel calls ours)\n'),
        ('    omniTaTick(now);    // OMNI_TAB_AUDIO_V1: media state every 500 ms\n',
         '    omniTaTick(now);    // OMNI_TAB_AUDIO_V1: media state every 500 ms\n'
         '    omniTvTick(now);    /* OMNI_TAB_VOLUME_V1: per-tab volume onto new pages / remembered sites (500 ms, only while set) */\n'),
    ],
    'OmniMediaControlsShell.h': [
        ('    omniSpNpRow(p, *t); // OMNI_PLAYBACK_SPEED_V1: "Speed  < 1x >"\n',
         '    omniSpNpRow(p, *t); // OMNI_PLAYBACK_SPEED_V1: "Speed  < 1x >"\n'
         '    omniTvNpRows(p, *t); /* OMNI_TAB_VOLUME_V1: "Volume  < 70% >", "Remember for this site" */\n'),
        ('    if (r.id == omniSpNpRowId) return omniSpInput(omniNpKey, b); // OMNI_PLAYBACK_SPEED_V1: Cross / D-pad left-right\n',
         '    if (r.id == omniSpNpRowId) return omniSpInput(omniNpKey, b); // OMNI_PLAYBACK_SPEED_V1: Cross / D-pad left-right\n'
         '    if (omniTvNpOwns(r.id)) return omniTvNpInput(omniNpKey, r.id, b); /* OMNI_TAB_VOLUME_V1: D-pad left-right, Cross */\n'),
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
    mcs = (root / 'OmniMediaControlsShell.h').read_bytes().decode('utf-8')
    if 'OMNI_PLAYBACK_SPEED_V1' not in mcs:
        sys.exit('OmniMediaControlsShell.h: OMNI_PLAYBACK_SPEED_V1 missing: apply_playback_speed.py first')
    if 'OMNI_TAB_AUDIO_V1' not in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8'):
        sys.exit('OmniBrowser.cpp: OMNI_TAB_AUDIO_V1 missing: apply_tab_audio.py first')
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniTabVolume.h', PURE, 'OmniPlaybackSpeed.h'),
            write_new('OmniTabVolumeShell.h', SHELL, 'OmniPlaybackSpeedShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
