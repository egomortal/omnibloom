#!/usr/bin/env python3
"""OMNI_SITE_MUTE_V1 (2026-11-16): Site settings > "Sound: Allow / Always mute" (backlog E08, "Always mute this site").

What the user sees
  - Site settings (Options > Site settings) has a new row right after "Autoplay on this site":
        "Sound"     Allow / Always mute / Always mute (this private session) / "-" on omni:// / about: / new-tab pages
    Cross or D-pad left / right switches it; a notice confirms ("Sound always muted on example.com" / "Sound allowed on
    example.com", + ", this private session only"). Open tabs showing that site follow at once.
  - When a tab commits a navigation to a muted site (WKPageNavigationClient didCommitNavigation), the tab is muted with
    the tab-audio mute (OMNI_TAB_AUDIO_V1: WKPageSetMuted(page, kWKMediaAudioMuted) + Tab::omniTaMuted), so the crossed
    speaker shows in both tab strips and the Tabs panel, and the tab can be unmuted the usual ways (Tabs panel Triangle,
    Options > Quick toggles, hold-Cross page menu). The shown tab gets the notice "Muted: example.com is set to Always
    mute"; background tabs only get the badge.
  - Unmuting such a tab by hand overrides the site setting for that tab only: later pages of the same site in that tab
    stay audible (other tabs and new tabs are still muted). Turning "Always mute" on again from Site settings ends the
    override.
  - Leaving the muted site (a navigation to another site, or to a new-tab / omni:// page) gives the tab its sound back,
    but only when it was this setting that muted it and the user did not unmute it meanwhile: a tab the user muted
    himself stays muted.
  - Private tabs follow the saved list; a choice made in a private tab is kept for this run only (Session, never
    written) and is never shown or applied in normal tabs.

Store: /data/omni/site-mute.txt ("omni-site-mute\\t1", "site\\t<host>" lines, at most 500), written through omniIoQueue
(never in test modes). Host key: lower case, "www." dropped while a dot remains, no port, IPv6 without brackets,
http / https only (the game-mode rule).

Pure part: engine/entry/OmniSiteMute.h (no SDL / WebKit): host key, store parse / serialize, per-site choice with the
private session, the per-tab decision at a commit and at a setting change (TabMute: which host this setting muted, which
host the user unmuted), texts. Tested by tools/test_site_mute.cpp:
    g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_site_mute.cpp -o t && ./t
Shell side: engine/entry/OmniSiteMuteShell.h (included from OmniFeatures3.h after OmniSiteClearShell.h, i.e. after
OmniTabAudioShell.h (OmniFeatures.h) and before OmniSiteListShell.h). Alias OSMU, names omniSmu*, Site settings row
776 (free in the tree and in every sibling's code on 2026-11-16; checked again before the first apply).
"Sites with custom settings" (OMNI_SITE_LIST_V1) can list the store the optional way it lists reader view / game mode:
the shell offers omniSmuSavedSites(), omniSmuSavedValue(key) and omniSmuSetSaved(key, on) (saved list only; writes and
updates open tabs); apply_site_list.py is not edited here.

Anchors (whole lines, exactly once each; MARK makes each file idempotent; line endings kept):
  OmniBrowser.cpp    the OmniTabAudio.h include line (pure include after it); the omniTaBadge line of struct Tab (the
                     per-tab state after it); the omniHoCommitted forward declaration (ours after it); the
                     omniHoCommitted(*tab) call in didCommitNavigation (ours after it).
  OmniQuickMenu.h    the omniApSiteInput declaration (row id + declarations after it); the omniApSiteRow(p, host) call
                     (our row after it); the omniApSiteRowId dispatch (ours before it).
  OmniFeatures3.h    the OmniSiteClearShell.h include line (ours after it).
Apply AFTER apply_tab_audio.py, apply_autoplay.py, apply_https_only.py and apply_site_clear.py (their lines are anchors).
usage: apply_site_mute.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_SITE_MUTE_V1'
HERE = Path(__file__).resolve().parent
if len(sys.argv) != 2:
    sys.exit('usage: apply_site_mute.py <engine tree>')
root = Path(sys.argv[1]) / 'engine' / 'entry'
IDS = ('776',)
NAMES = ('OSMU', 'omniSmu', 'OmniSiteMute', 'OMNI_SITE_MUTE', r'site-mute\.txt')

PURE = r'''// OMNI_SITE_MUTE_V1: the pure part of Site settings > "Sound: Allow / Always mute" (no SDL, no WebKit). The shell
// side is OmniSiteMuteShell.h; the reasons are in tools/apply_site_mute.py. Tested on the host with g++
// (test_site_mute.cpp).
#pragma once
#include <cstddef>
#include <set>
#include <string>

namespace OmniSiteMute {

constexpr size_t kMaxSites = 500, kHostMax = 253;
constexpr long kMaxFileBytes = 64L << 10;
constexpr const char* kFileName = "site-mute.txt";
constexpr const char* kHeader = "omni-site-mute\t1";
constexpr int kSiteRowId = 776;            // Site settings row (710-770 and 787 taken there)

struct Store { std::set<std::string> sites; };
struct Session {                           // private tabs only, this run only (never written)
    std::set<std::string> on, off;         // muted here / a saved site allowed here
    void clear() { on.clear(); off.clear(); }
};

inline char lower(char c) { return c >= 'A' && c <= 'Z' ? char(c + ('a' - 'A')) : c; }

// "https://WWW.Example.com:8443/x" -> "example.com"; "" when not http(s) or not a usable host.
inline std::string hostKey(const std::string& url)
{
    size_t p;
    std::string scheme;
    for (size_t i = 0; i < url.size() && i < 8; ++i) scheme += lower(url[i]);
    if (scheme.compare(0, 8, "https://") == 0) p = 8;
    else if (scheme.compare(0, 7, "http://") == 0) p = 7;
    else return std::string();
    size_t end = url.find_first_of("/?#", p);
    if (end == std::string::npos) end = url.size();
    const size_t at = url.rfind('@', end ? end - 1 : 0);
    if (at != std::string::npos && at >= p && at < end) p = at + 1;
    std::string host;
    bool v6 = false;
    if (p < end && url[p] == '[') {
        const size_t close = url.find(']', p);
        if (close == std::string::npos || close >= end) return std::string();
        host = url.substr(p + 1, close - p - 1);
        v6 = true;
    } else {
        const size_t colon = url.find(':', p);
        host = url.substr(p, (colon != std::string::npos && colon < end ? colon : end) - p);
    }
    for (auto& c : host) c = lower(c);
    while (!host.empty() && host.back() == '.') host.pop_back();
    if (host.empty() || host.size() > kHostMax) return std::string();
    for (char c : host) {
        const bool ok = v6 ? (c >= 'a' && c <= 'f') || (c >= '0' && c <= '9') || c == ':' || c == '.'
                           : (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '.' || c == '-' || c == '_';
        if (!ok) return std::string();
    }
    if (v6 && host.find(':') == std::string::npos) return std::string();
    if (host.find("..") != std::string::npos) return std::string();
    if (!v6 && host.compare(0, 4, "www.") == 0 && host.find('.', 4) != std::string::npos) host = host.substr(4);
    return host;
}
// A key as stored (the file is edited by hand at most): the same rules as hostKey on "https://<key>/".
inline bool validKey(const std::string& k)
{
    if (k.empty() || k.find_first_of("/?#@[]") != std::string::npos) return false;
    const std::string url = k.find(':') != std::string::npos ? "https://[" + k + "]/" : "https://" + k + "/";
    return hostKey(url) == k;
}

// Normal tabs: the saved list only. Private tabs: the saved list, then this session's choices.
inline bool enabled(const Store& s, const Session& x, const std::string& host, bool privateTab)
{
    if (host.empty()) return false;
    if (!privateTab) return s.sites.count(host) != 0;
    if (x.off.count(host)) return false;
    return s.sites.count(host) != 0 || x.on.count(host) != 0;
}
// True: the saved store changed (write it). full: the saved list already holds kMaxSites.
inline bool setSite(Store& s, Session& x, const std::string& host, bool on, bool privateTab, bool* full = nullptr)
{
    if (full) *full = false;
    if (host.empty()) return false;
    if (privateTab) {
        if (on) { x.off.erase(host); if (!s.sites.count(host)) x.on.insert(host); }
        else { x.on.erase(host); if (s.sites.count(host)) x.off.insert(host); }
        return false;
    }
    if (!on) return s.sites.erase(host) != 0;
    if (s.sites.count(host)) return false;
    if (s.sites.size() >= kMaxSites) { if (full) *full = true; return false; }
    s.sites.insert(host);
    return true;
}

inline Store parse(const std::string& text)
{
    Store s;
    size_t p = 0;
    bool first = true, ok = false;
    while (p < text.size()) {
        size_t e = text.find('\n', p);
        if (e == std::string::npos) e = text.size();
        std::string line = text.substr(p, e - p);
        p = e + 1;
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (first) { first = false; ok = line == kHeader; if (!ok) break; continue; }
        if (line.compare(0, 5, "site\t") == 0) {
            const std::string k = line.substr(5);
            if (validKey(k) && s.sites.size() < kMaxSites) s.sites.insert(k);
        }
    }
    if (!ok) return Store();
    return s;
}
inline std::string serialize(const Store& s)
{
    std::string out = std::string(kHeader) + "\n";
    for (const auto& k : s.sites) out += "site\t" + k + "\n";
    return out;
}

// --- one tab ---------------------------------------------------------------------------------------------------------
// by:   the host this setting muted the tab for ("" = the setting did not mute it, or the user unmuted it since).
// keep: the host the user unmuted by hand while this setting had muted it: that tab stays audible there.
struct TabMute { std::string by, keep; };
enum Act { kNothing = 0, kMute, kUnmute };

// The setting had muted the tab and the tab is no longer muted: the user unmuted it (the only way it gets unmuted).
inline void noteManual(TabMute& s, bool tabMuted)
{
    if (!s.by.empty() && !tabMuted) { s.keep = s.by; s.by.clear(); }
}
// A navigation committed; key = the committed page's host key ("" for new-tab / omni:// / about: pages).
inline Act committed(TabMute& s, const std::string& key, bool siteMuted, bool tabMuted)
{
    noteManual(s, tabMuted);
    if (!key.empty() && siteMuted) {
        if (s.keep == key) {                                      // unmuted by hand here: this tab keeps its sound
            if (s.by.empty()) return kNothing;
            s.by.clear();                                         // (muted for another muted site on the way: undone)
            return tabMuted ? kUnmute : kNothing;
        }
        if (tabMuted) { if (!s.by.empty()) s.by = key; return kNothing; }   // already muted (ours moves along; a user's stays the user's)
        s.by = key;
        return kMute;
    }
    if (!s.by.empty()) { s.by.clear(); return tabMuted ? kUnmute : kNothing; }   // left the muted site: sound back
    return kNothing;
}
// The choice for `key` changed in Site settings (or the site list) while the tab shows `key`.
inline Act changed(TabMute& s, const std::string& key, bool siteMuted, bool tabMuted)
{
    noteManual(s, tabMuted);
    if (key.empty()) return kNothing;
    if (siteMuted) {
        if (s.keep == key) s.keep.clear();                        // asked again: the override ends
        if (tabMuted) return kNothing;
        s.by = key;
        return kMute;
    }
    if (s.keep == key) s.keep.clear();
    if (s.by == key) { s.by.clear(); return tabMuted ? kUnmute : kNothing; }
    return kNothing;
}

// --- texts -------------------------------------------------------------------------------------------------------
inline std::string siteValue(bool on, bool privateTab)
{
    if (!on) return "Allow";
    return privateTab ? "Always mute (this private session)" : "Always mute";
}
// The row's detail when this tab was unmuted by hand on a muted site.
inline std::string overrideDetail() { return "This tab: sound on (unmuted by hand)"; }
inline std::string siteNotice(const std::string& host, bool on, bool privateTab, bool full)
{
    if (full) return "The always-mute list is full (" + std::to_string(kMaxSites) + " sites)";
    std::string s = std::string(on ? "Sound always muted on " : "Sound allowed on ") + host;
    if (privateTab) s += ", this private session only";
    return s;
}
inline std::string mutedNotice(const std::string& host) { return "Muted: " + host + " is set to Always mute"; }

} // namespace OmniSiteMute
'''

SHELL = r'''// OMNI_SITE_MUTE_V1: Site settings > "Sound: Allow / Always mute" (shell side). Included from OmniFeatures3.h after
// OmniSiteClearShell.h (inside OmniBrowser.cpp's anonymous namespace; OmniTabAudioShell.h is above it). The pure part is
// OmniSiteMute.h; the reasons are in tools/apply_site_mute.py. Main thread only.
// The mute itself is the tab-audio one (OMNI_TAB_AUDIO_V1): Tab::omniTaMuted + WKPageSetMuted, so the badge, the Tabs
// panel's Triangle, Quick toggles and the sleep timer all treat it as the tab's own mute.
#pragma once

namespace OSMU = OmniSiteMute;
static_assert(OSMU::kSiteRowId == omniSmuSiteRowId, "OMNI_SITE_MUTE_V1: Site settings row id");

static OSMU::Store omniSmuStore;
static bool omniSmuLoaded = false;
static OSMU::Session omniSmuSession;

static void omniSmuLoad()
{
    if (omniSmuLoaded) return;
    omniSmuLoaded = true;
    FILE* f = fopen(omniData(OSMU::kFileName).c_str(), "rb");
    if (!f) return;
    std::string text;
    char buf[4096];
    size_t n;
    while ((n = fread(buf, 1, sizeof buf, f)) > 0 && long(text.size()) < OSMU::kMaxFileBytes) text.append(buf, n);
    fclose(f);
    omniSmuStore = OSMU::parse(text);
}
static void omniSmuWrite()
{
    if (omniTestMode()) return;
    omniIoQueue(omniData(OSMU::kFileName), OSMU::serialize(omniSmuStore), false);
}
// The tab's key: a web page's host (not a built-in omni://pages tab), "" otherwise.
static std::string omniSmuKey(const Tab* t)
{
    if (!t || t->omniPagesTab) return std::string();
    return OSMU::hostKey(t->url);
}
static bool omniSmuOn(const Tab& t, const std::string& k)
{
    if (k.empty()) return false;
    omniSmuLoad();
    return OSMU::enabled(omniSmuStore, omniSmuSession, k, t.omniPrivate);
}
// The tab-audio mute / unmute (as omniTaToggle, without its notice).
static void omniSmuDo(Tab& t, OSMU::Act a, const std::string& k, bool atCommit)
{
    if (a == OSMU::kNothing) return;
    const bool mute = a == OSMU::kMute;
    t.omniTaMuted = mute;
    if (t.page) WKPageSetMuted(t.page, mute ? kWKMediaAudioMuted : kWKMediaNoneMuted);
    TA::update(t.omniTaBadge, TA::badge(omniTaPlaying(t), t.omniTaMuted));
    omniShellDirty = true;
    if (mute && atCommit && &t == active()) notice(OSMU::mutedNotice(k));
    fprintf(stderr, "OMNI SITE MUTE: %s tab (%s)\n", mute ? "muted" : "unmuted", k.empty() ? "-" : k.c_str()); fflush(stderr);
}
// didCommitNavigation (OmniBrowser.cpp), after tab.url is updated.
static void omniSmuCommitted(Tab& t)
{
    const std::string k = omniSmuKey(&t);
    omniSmuDo(t, OSMU::committed(t.omniSmu, k, omniSmuOn(t, k), t.omniTaMuted), k, true);
}
// The choice for k changed: every open tab showing k follows (each by its own private / normal rule).
static void omniSmuApplyHost(const std::string& k)
{
    if (k.empty()) return;
    for (auto& tp : tabs) {
        Tab& t = *tp;
        if (omniSmuKey(&t) != k) continue;
        omniSmuDo(t, OSMU::changed(t.omniSmu, k, omniSmuOn(t, k), t.omniTaMuted), k, false);
    }
}

// --- Site settings row ----------------------------------------------------------------------------------------------
static void omniSmuSiteRow(OmniFxPanel& p, const std::string&)
{
    Tab* t = active();
    const std::string k = omniSmuKey(t);
    OmniFxRow r; r.id = OSMU::kSiteRowId; r.label = "Sound"; r.stepper = true; r.enabled = !k.empty();
    if (k.empty()) r.value = "-";
    else {
        const bool on = omniSmuOn(*t, k);
        r.value = OSMU::siteValue(on, t->omniPrivate);
        if (on && t->omniSmu.keep == k && !t->omniTaMuted) r.detail = OSMU::overrideDetail();
    }
    p.rows.push_back(r);
}
static bool omniSmuSiteInput(const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A && b != SDL_CONTROLLER_BUTTON_DPAD_LEFT && b != SDL_CONTROLLER_BUTTON_DPAD_RIGHT) return false;
    Tab* t = active();
    const std::string k = omniSmuKey(t);
    if (!r.enabled || !t || k.empty()) return true;
    const bool on = !omniSmuOn(*t, k);
    bool full = false;
    if (OSMU::setSite(omniSmuStore, omniSmuSession, k, on, t->omniPrivate, &full)) omniSmuWrite();
    if (!full) omniSmuApplyHost(k);
    notice(OSMU::siteNotice(k, on, t->omniPrivate, full));
    omniFxRefresh();
    return true;
}

// --- for "Sites with custom settings" (OMNI_SITE_LIST_V1, optional): the saved list only, never a private choice ------
[[maybe_unused]] static std::vector<std::string> omniSmuSavedSites()
{
    omniSmuLoad();
    return std::vector<std::string>(omniSmuStore.sites.begin(), omniSmuStore.sites.end());
}
[[maybe_unused]] static std::string omniSmuSavedValue(const std::string& key)
{
    if (key.empty()) return "-";
    omniSmuLoad();
    return OSMU::siteValue(omniSmuStore.sites.count(key) != 0, false);
}
// Sets the saved choice for key (OSMU::hostKey of "https://<host>/"), writes, updates the open tabs, shows the notice.
// False: the list is full (nothing changed).
[[maybe_unused]] static bool omniSmuSetSaved(const std::string& key, bool on)
{
    if (key.empty()) return true;
    omniSmuLoad();
    bool full = false;
    if (OSMU::setSite(omniSmuStore, omniSmuSession, key, on, false, &full)) omniSmuWrite();
    if (!full) omniSmuApplyHost(key);
    notice(OSMU::siteNotice(key, on, false, full));
    return !full;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniTabAudio.h" // OMNI_TAB_AUDIO_V1: tab sound badges, per-tab mute (pure)\n',
         '#include "OmniTabAudio.h" // OMNI_TAB_AUDIO_V1: tab sound badges, per-tab mute (pure)\n'
         '#include "OmniSiteMute.h" // OMNI_SITE_MUTE_V1: Site settings > Sound: Always mute, site-mute.txt (pure)\n'),
        ('    uint8_t omniTaBadge = 0;   // OMNI_TAB_AUDIO_V1: OmniTabAudio::Badge last drawn\n',
         '    uint8_t omniTaBadge = 0;   // OMNI_TAB_AUDIO_V1: OmniTabAudio::Badge last drawn\n'
         '    OmniSiteMute::TabMute omniSmu; // OMNI_SITE_MUTE_V1: the host Always mute muted this tab for / the host it was unmuted on by hand\n'),
        ('static void omniHoCommitted(Tab& tab); // OMNI_HTTPS_ONLY_V1\n',
         'static void omniHoCommitted(Tab& tab); // OMNI_HTTPS_ONLY_V1\n'
         'static void omniSmuCommitted(Tab& tab); // OMNI_SITE_MUTE_V1 (OmniSiteMuteShell.h)\n'),
        ('        omniHoCommitted(*tab); // OMNI_HTTPS_ONLY_V1: the https attempt (if any) worked\n',
         '        omniHoCommitted(*tab); // OMNI_HTTPS_ONLY_V1: the https attempt (if any) worked\n'
         '        omniSmuCommitted(*tab); // OMNI_SITE_MUTE_V1: Always mute this site (tab-audio mute + badge)\n'),
    ],
    'OmniQuickMenu.h': [
        ('static bool omniApSiteInput(const OmniFxRow& r, int b);\n',
         'static bool omniApSiteInput(const OmniFxRow& r, int b);\n'
         'constexpr int omniSmuSiteRowId = 776; // OMNI_SITE_MUTE_V1 (OmniSiteMuteShell.h)\n'
         'static void omniSmuSiteRow(OmniFxPanel& p, const std::string& host);\n'
         'static bool omniSmuSiteInput(const OmniFxRow& r, int b);\n'),
        ('    omniApSiteRow(p, host); // OMNI_AUTOPLAY_V1: Autoplay on this site\n',
         '    omniApSiteRow(p, host); // OMNI_AUTOPLAY_V1: Autoplay on this site\n'
         '    omniSmuSiteRow(p, host); // OMNI_SITE_MUTE_V1: Sound: Allow / Always mute\n'),
        ('    if (r.id == omniApSiteRowId) return omniApSiteInput(r, b); // OMNI_AUTOPLAY_V1 (handles its disabled state)\n',
         '    if (r.id == omniSmuSiteRowId) return omniSmuSiteInput(r, b); // OMNI_SITE_MUTE_V1 (handles its disabled state)\n'
         '    if (r.id == omniApSiteRowId) return omniApSiteInput(r, b); // OMNI_AUTOPLAY_V1 (handles its disabled state)\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniSiteClearShell.h" // OMNI_SITE_CLEAR_V1\n',
         '#include "OmniSiteClearShell.h" // OMNI_SITE_CLEAR_V1\n'
         '#include "OmniSiteMuteShell.h" // OMNI_SITE_MUTE_V1 (after tab audio; before the site list)\n'),
    ],
}
NEEDS = {'OmniBrowser.cpp': ('OMNI_TAB_AUDIO_V1', 'OMNI_HTTPS_ONLY_V1'),
         'OmniQuickMenu.h': ('OMNI_AUTOPLAY_V1',),
         'OmniFeatures3.h': ('OMNI_SITE_CLEAR_V1',)}


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
GUIDE_TOOL = 'apply_controls_help.py'
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
    mine = {'OmniSiteMute.h', 'OmniSiteMuteShell.h'}
    # A sibling not applied to this tree yet still owns its ids: its code (generated headers / edits included,
    # comments and docstring stripped) assigning one of ours to a row id ("kSiteRowId = 776", "omniXxSiteRowId = 776",
    # "constexpr int x = 776") is a clash.
    assign = re.compile(r'(?:\b\w*[Rr]ow\w*|\bconstexpr\s+int\s+\w+)\s*=\s*(%s)(?![\w.])' % '|'.join(IDS))
    for f in sorted(HERE.glob('apply_*.py')):
        if f.name == Path(__file__).name:
            continue
        if f.name == 'apply_controls_help.py' or MARK in f.read_text(encoding='utf-8', errors='replace'):   # OMNI_SIBLING_SKIP: the guide quotes names; a patch built on this one uses them
            continue
        t = code_only(f.read_text(encoding='utf-8', errors='replace'))
        # Siblings whose code names this patch's functions by design: the Controls guide and "Sites with custom
        # settings" (apply_site_list.py, OMNI_SITE_LIST_V1 r4 lists this store). Their id assignments are still looked for.
        skip = f.name == GUIDE_TOOL or "MARK = 'OMNI_SITE_LIST_V1'" in t
        m = (None if skip else name.search(t)) or assign.search(t)   # bare numbers: not looked for (siblings' notes list others' ids)
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
    msgs = [write_new('OmniSiteMute.h', PURE, 'OmniTabAudio.h'),
            write_new('OmniSiteMuteShell.h', SHELL, 'OmniSiteClearShell.h')]
    msgs += [patch(fname, edits) for fname, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
