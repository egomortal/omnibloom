#!/usr/bin/env python3
"""OMNI_GAME_MODE_V1 (2026-11-16): "Game mode" per site, for web games and cloud-gaming pages.

What the user sees
  - Site settings (Options > Site settings) has a new row after "HTTPS-only on this site":
        "Game mode"     Off / On for this site / On (this private session) / "-" on omni:// / about: / new-tab pages
    Cross or D-pad left / right switches it. The hold-Cross page menu has a row "Game mode" (after "Open as app" /
    "Add to Apps"), value Off / Paused / On: Cross turns it on for the site (or resumes it after the exit chord).
  - In game mode (the shown tab's site is on, nothing of Omni's is open over the page):
      * every controller event (buttons, sticks, triggers, touchpad) goes ONLY to the page, through the web Gamepad
        API (navigator.getGamepads(), standard mapping, OmniGamepad.h). button(), hold Cross, the L1+R1 / L2 chords,
        the trigger taps, the button map (OMNI_BUTTON_MAP_V1), YouTube TV's arrow keys, the full-screen video keys:
        none of them sees the event, so no Omni shortcut fires and nothing reaches the page twice (as keys AND pad).
      * the pointer is hidden and the sticks neither move it nor scroll; the bars are hidden with the page at full
        height (the same layout as an app tab, OMNI_WEB_APPS_V1: omniAutoHideActive).
      * a USB keyboard still types into the page; its Esc / F6 / Ctrl+L shell shortcuts are dropped.
      * "Web pages can use the controller" (Browser settings) does not apply: game mode is the site's own opt-in.
    The one exception: hold Options + Create (Xbox: Menu + View) on the same pad for 1 second. Game mode is left for
    this tab ("Paused": the page menu row resumes it), a notice says how to come back, and the two buttons' releases are
    swallowed so they do nothing in Omni. The page does see Start + Select during that second (it gets every event).
  - Entering game mode shows the exit chord: the first time ever a hint for 8 s, later a short notice.
  - An Omni panel / dialog / keyboard over the page (a page's alert(), the error panel, the keyboard for a text box)
    takes the controller as usual while it is open; game mode resumes when it closes.
  - Private tabs: their choices are kept for this run only (Session), never written; they also follow the saved list.

Gamepad API facts (checked in this tree): ENABLE_GAMEPAD 1 (s1/build/cmakeconfig.h); OmniGamepad.h (OMNI_GAMEPAD_V1)
installs a libwpe gamepad provider fed from the shell's SDL events (omniGamepadEvent, every event, every pad) and
names the receiving page through WKOmniSetGamepadInputPage (omniGamepadTick: active tab, focused, no Omni UI, setting
on, not the Master Control page). Before this patch a page with gamepad support got the pad AND Omni acted on the same
press. The exit chord is free: no handler combines START and BACK (Options = quick menu, Create = Browser settings,
both on press, both swallowed in game mode); the button map binds neither; the PS button is not delivered to titles.

Store: /data/omni/game-sites.txt ("omni-game-sites\\t1", "hint\\tseen", "site\\t<host>"), written through omniIoQueue.
Host key: lower case, "www." dropped while a dot remains, no port, IPv6 without brackets (http / https only).

Pure part: engine/entry/OmniGameMode.h (host key, store parse / serialize, per-site choice, exit chord, texts),
tested by tools/test_game_mode.cpp:  g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_game_mode.cpp -o t && ./t
Shell side: engine/entry/OmniGameModeShell.h (included from OmniFeatures3.h after OmniWebAppsShell.h). Alias OGMM.
Ids: Site settings row 770, page-menu row 990 (both unused by every apply_*.py and the tree).

Anchors (whole lines, exactly once each; MARK makes each file idempotent; line endings kept):
  OmniBrowser.cpp      omniWapOn declaration + omniAutoHideActive (apply_web_apps.py's): omniGmOn, || omniGmOn
                       omniStyleTick's omniWapOn line: + the game-mode line after it
                       omniDrawPointer's omniMagHidesPointer line: + hidden in game mode
                       the OmniSiteClear.h include: + OmniGameMode.h
                       the omniGamepadTick call: game mode names the page itself (if-wrapped, the line is unchanged)
                       the event loop's omniChromeEvent line: the game-mode filter goes before it
                       the stick tick's `if (controller && !editing) {`: + && !omniGmTakesPad()
  OmniFeatures3.h      the OmniWebAppsShell.h include; the omniWapTick line of omniF3Tick
  OmniContextMenu.h    the omniPtContextRows declaration; the omniWapContextRows call; the omniWapContextAction line
  OmniQuickMenu.h      the omniSliSiteInput declaration; the omniHoSiteRow call; the omniSliSiteRowId dispatch (ours first)
  OmniControlsHelp.h   the quick tab switcher row (Quick actions): + "Hold Options + Create: Leave game mode"
Apply LAST (after apply_button_map.py): game mode must take the controller before everything else.
usage: apply_game_mode.py <engine tree>   (re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_GAME_MODE_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_GAME_MODE_V1: the pure part of Game mode (no SDL, no WebKit). The shell side is OmniGameModeShell.h; the
// reasons are in tools/apply_game_mode.py. Tested on the host with g++ (test_game_mode.cpp).
#pragma once
#include <cstddef>
#include <cstdint>
#include <set>
#include <string>

namespace OmniGameMode {

constexpr size_t kMaxSites = 500, kHostMax = 253;
constexpr long kMaxFileBytes = 64L << 10;
constexpr const char* kFileName = "game-sites.txt";
constexpr const char* kHeader = "omni-game-sites\t1";
constexpr int kSiteRowId = 770;            // Site settings row (710-750 taken there)
constexpr int kContextId = 990;            // hold-Cross page menu row (pinned 960, QR 975, apps 980/981, text 985)
constexpr uint32_t kExitHoldMs = 1000;     // Options + Create held this long leaves game mode
constexpr uint32_t kHintMs = 8000;         // the first-time hint stays up this long (later: the normal 3.5 s notice)

struct Store { std::set<std::string> sites; bool hintSeen = false; };
struct Session {                           // private tabs only, this run only (never written)
    std::set<std::string> on, off;         // turned on here / a saved site turned off here
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
        if (line == "hint\tseen") { s.hintSeen = true; continue; }
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
    if (s.hintSeen) out += "hint\tseen\n";
    for (const auto& k : s.sites) out += "site\t" + k + "\n";
    return out;
}

// --- the exit chord: Options + Create on one pad, held kExitHoldMs ---------------------------------------------
enum Button : int { kOther = 0, kOptions = 1, kCreate = 2 };
class ExitChord {
public:
    // Every controller button edge while game mode is on (whatever is open over the page).
    void edge(int pad, int button, bool down, uint32_t now)
    {
        if (button != kOptions && button != kCreate) return;
        const unsigned bit = button == kOptions ? 1u : 2u;
        if (pad != m_pad) {
            if (m_bits || !down) return;   // another pad holds part of the chord: pads are never combined
            m_pad = pad;
        }
        const unsigned before = m_bits;
        if (down) m_bits |= bit; else m_bits &= ~bit;
        if (m_bits == 3u && before != 3u) m_since = now;
        if (!m_bits && !m_drain) m_pad = -1;
    }
    bool due(uint32_t now) const { return !m_drain && m_bits == 3u && uint32_t(now - m_since) >= kExitHoldMs; }
    // Game mode was left by the chord: the chord buttons' events are swallowed until both are up.
    void fired() { m_drain = true; }
    bool draining() const { return m_drain; }
    // After the exit (game mode off): true = swallow this event.
    bool swallowAfterExit(int pad, int button, bool down, uint32_t now)
    {
        if (!m_drain || pad != m_pad || (button != kOptions && button != kCreate)) return false;
        edge(pad, button, down, now);
        if (!m_bits) { m_drain = false; m_pad = -1; }
        return true;
    }
    void reset() { m_pad = -1; m_bits = 0; m_since = 0; m_drain = false; }
    unsigned held() const { return m_bits; }
private:
    int m_pad = -1;
    unsigned m_bits = 0;
    uint32_t m_since = 0;
    bool m_drain = false;
};

// --- texts -------------------------------------------------------------------------------------------------------
inline const char* chordName(bool ps) { return ps ? "Options + Create" : "Menu + View"; }
inline const char* crossName(bool ps) { return ps ? "Cross" : "A"; }
inline std::string hintText(bool ps, bool first)
{
    if (first)
        return std::string("Game mode: the controller now goes to the page. To leave, hold ") + chordName(ps) + " for 1 second";
    return std::string("Game mode. Hold ") + chordName(ps) + " to leave";
}
inline std::string leftNotice(const std::string& host, bool ps)
{
    return "Left game mode on " + host + ". Back to it: hold " + crossName(ps) + " > Game mode";
}
inline std::string siteValue(bool on, bool privateTab)
{
    if (!on) return "Off";
    return privateTab ? "On (this private session)" : "On for this site";
}
inline std::string siteNotice(const std::string& host, bool on, bool privateTab, bool full)
{
    if (full) return "Game mode list is full (" + std::to_string(kMaxSites) + " sites)";
    std::string s = std::string("Game mode ") + (on ? "on" : "off") + " for " + host;
    if (on) s += " (when the menus close)";
    if (privateTab) s += ", this private session only";
    return s;
}
inline const char* contextValue(bool on, bool paused) { return !on ? "Off" : paused ? "Paused" : "On"; }

} // namespace OmniGameMode
'''

SHELL = r'''// OMNI_GAME_MODE_V1: Game mode per site (shell side). Included from OmniFeatures3.h after OmniWebAppsShell.h (inside
// OmniBrowser.cpp's anonymous namespace). The pure part is OmniGameMode.h; the reasons are in tools/apply_game_mode.py.
// Main thread only. omniGmOn (OmniBrowser.cpp, next to omniWapOn) is true while the shown tab is in game mode; the
// event loop asks omniGmEvent first, omniGmTick (from omniF3Tick) switches the mode and watches the exit chord.
#pragma once

namespace OGMM = OmniGameMode;
static_assert(OGMM::kSiteRowId == omniGmSiteRowId, "OMNI_GAME_MODE_V1: Site settings row id");

static OGMM::Store omniGmStore;
static bool omniGmLoaded = false;
static OGMM::Session omniGmSession;
static OGMM::ExitChord omniGmChord;
static std::map<const void*, std::string> omniGmPaused;   // tab -> the host left with the exit chord (this run)
static std::string omniGmHost;                            // the host in game mode now ("" off)

static void omniGmLoad()
{
    if (omniGmLoaded) return;
    omniGmLoaded = true;
    FILE* f = fopen(omniData(OGMM::kFileName).c_str(), "rb");
    if (!f) return;
    std::string text;
    char buf[4096];
    size_t n;
    while ((n = fread(buf, 1, sizeof buf, f)) > 0 && long(text.size()) < OGMM::kMaxFileBytes) text.append(buf, n);
    fclose(f);
    omniGmStore = OGMM::parse(text);
}
static void omniGmWrite()
{
    if (omniTestMode()) return;
    omniIoQueue(omniData(OGMM::kFileName), OGMM::serialize(omniGmStore), false);
}
// The tab's game-mode key: a web page (not the Master Control page, not the Downloads tab), "" otherwise.
static std::string omniGmKey(Tab* t)
{
    if (!t || !omniWebURL(t->url) || omniMcOrigin(t->url) || omniMediaOwns(*t)) return std::string();
    return OGMM::hostKey(t->url);
}
static bool omniGmPausedHere(Tab* t, const std::string& key)
{
    const auto it = omniGmPaused.find(t);
    return it != omniGmPaused.end() && it->second == key;
}
static bool omniGmWanted(Tab* t)
{
    if (!t || t->crashed || omniTestMode()) return false;
    const std::string k = omniGmKey(t);
    if (k.empty()) return false;
    omniGmLoad();
    return OGMM::enabled(omniGmStore, omniGmSession, k, t->omniPrivate) && !omniGmPausedHere(t, k);
}
// Something of Omni's is over the page: it takes the controller while open.
static bool omniGmUiOpen() { return settingsOpen || editing || pageEditing || omniKbTarget || omniOverlayOpen(); }
static bool omniGmTakesPad() { return omniGmOn && !omniGmUiOpen(); }

static void omniGmSwitch(bool on, Tab* t)
{
    const bool hideBefore = omniAutoHideActive();
    omniGmOn = on;
    omniGmHost = on ? omniGmKey(t) : std::string();
    if (!omniGmChord.draining()) omniGmChord.reset();
    omniShoulderReset();              // L1 / R1 / trigger states start from neutral again
    omniFxHoldState = OmniFxHold();   // no half-done hold Cross
    if (omniAutoHideActive() != hideBefore) {
        omniApplyPageHeight();        // Auto-hide's full-height layout (or back), as an app tab
        if (active() && !pageFullscreen) WKViewSetSize(active()->view.get(), omniViewSize());
    }
    omniChromeWanted = !on;
    omniShellDirty = true;
    omniPageDirty = true;
    fprintf(stderr, "OMNI_GAME_MODE_V1: %s%s\n", on ? "on for " : "off", on ? omniGmHost.c_str() : ""); fflush(stderr);
    if (!on || !t) return;
    omniGmLoad();
    const bool first = !omniGmStore.hintSeen;
    status = OGMM::hintText(playStationIcons, first);
    statusUntil = SDL_GetTicks() + (first ? OGMM::kHintMs : 3500);
    if (first) { omniGmStore.hintSeen = true; if (!t->omniPrivate) omniGmWrite(); }   // a private tab writes nothing
}
static void omniGmExit(Tab* t)
{
    const std::string host = omniGmHost;
    omniGmPaused[t] = host;
    omniGmChord.fired();
    omniGmSwitch(false, t);
    notice(OGMM::leftNotice(host, playStationIcons));
}

// omniF3Tick(): the shown tab's mode, the exit chord's 1 s.
static void omniGmTick(uint32_t now)
{
    if (!omniGmPaused.empty())
        for (auto it = omniGmPaused.begin(); it != omniGmPaused.end();) {
            bool open = false;
            for (auto& tab : tabs) if (static_cast<const void*>(&*tab) == it->first) { open = true; break; }
            it = open ? std::next(it) : omniGmPaused.erase(it);
        }
    Tab* t = active();
    const bool want = omniGmWanted(t);
    if (want != omniGmOn || (want && omniGmKey(t) != omniGmHost)) omniGmSwitch(want, t);
    if (!omniGmOn) { if (!omniGmChord.draining()) omniGmChord.reset(); return; }
    if (omniGmTakesPad() && omniGmChord.due(now)) omniGmExit(t);
}

// The event loop, first: true = the event is the page's alone (the caller still feeds the Gamepad API with it).
static bool omniGmEvent(const SDL_Event& e)
{
    if (e.type == SDL_CONTROLLERDEVICEREMOVED) { omniGmChord.reset(); return false; }
    const bool button = e.type == SDL_CONTROLLERBUTTONDOWN || e.type == SDL_CONTROLLERBUTTONUP;
    if (button) {
        const int b = e.cbutton.button == SDL_CONTROLLER_BUTTON_START ? OGMM::kOptions
            : e.cbutton.button == SDL_CONTROLLER_BUTTON_BACK ? OGMM::kCreate : OGMM::kOther;
        const bool down = e.type == SDL_CONTROLLERBUTTONDOWN;
        if (!omniGmOn) return omniGmChord.swallowAfterExit(int(e.cbutton.which), b, down, SDL_GetTicks());
        omniGmChord.edge(int(e.cbutton.which), b, down, SDL_GetTicks());
    }
    if (!omniGmTakesPad()) return false;
    if (button || e.type == SDL_CONTROLLERAXISMOTION || e.type == SDL_CONTROLLERTOUCHPADDOWN
        || e.type == SDL_CONTROLLERTOUCHPADUP || e.type == SDL_CONTROLLERTOUCHPADMOTION) return true;
    if (e.type == SDL_KEYDOWN) {   // a keyboard still types into the page; only the shell's own keys are dropped
        const auto k = e.key.keysym.sym;
        return k == SDLK_ESCAPE || k == SDLK_F6 || (k == SDLK_l && (e.key.keysym.mod & KMOD_CTRL));
    }
    return false;
}
// The omniGamepadTick call: in game mode the page is named here (the "Web pages can use the controller" setting does
// not apply: game mode is the site's own choice). True: done, omniGamepadTick is skipped.
static bool omniGmPadTick(bool omniUiOpen)
{
    if (!omniGmOn) return false;
    Tab* t = active();
    WKPageRef want = t && omniShoulderFocused && !omniUiOpen && !t->crashed ? t->page : nullptr;
    if (want != omniGpTarget) { omniGpTarget = want; WKOmniSetGamepadInputPage(want); }
    return true;
}

// --- hold-Cross page menu -------------------------------------------------------------------------------------------
static void omniGmContextRows(OmniFxPanel& p)
{
    Tab* t = active();
    const std::string k = omniGmKey(t);
    OmniFxRow r; r.id = OGMM::kContextId; r.label = "Game mode";
    r.enabled = !k.empty() && !t->crashed;
    if (!k.empty()) {
        omniGmLoad();
        r.value = OGMM::contextValue(OGMM::enabled(omniGmStore, omniGmSession, k, t->omniPrivate), omniGmPausedHere(t, k));
    }
    p.rows.push_back(r);
}
static bool omniGmContextAction(int id)
{
    if (id != OGMM::kContextId) return false;
    omniFxCloseAll();
    Tab* t = active();
    const std::string k = omniGmKey(t);
    if (!t || k.empty()) return true;
    omniGmLoad();
    if (!OGMM::enabled(omniGmStore, omniGmSession, k, t->omniPrivate)) {
        bool full = false;
        if (OGMM::setSite(omniGmStore, omniGmSession, k, true, t->omniPrivate, &full)) omniGmWrite();
        if (full) { notice(OGMM::siteNotice(k, true, t->omniPrivate, true)); return true; }
    }
    omniGmPaused.erase(t);   // omniGmTick switches it on and shows the exit chord
    return true;
}

// --- Site settings row ----------------------------------------------------------------------------------------------
static void omniGmSiteRow(OmniFxPanel& p, const std::string&)
{
    Tab* t = active();
    const std::string k = omniGmKey(t);
    OmniFxRow r; r.id = OGMM::kSiteRowId; r.label = "Game mode"; r.stepper = true; r.enabled = !k.empty();
    if (k.empty()) r.value = "-";
    else { omniGmLoad(); r.value = OGMM::siteValue(OGMM::enabled(omniGmStore, omniGmSession, k, t->omniPrivate), t->omniPrivate); }
    p.rows.push_back(r);
}
static bool omniGmSiteInput(const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A && b != SDL_CONTROLLER_BUTTON_DPAD_LEFT && b != SDL_CONTROLLER_BUTTON_DPAD_RIGHT) return false;
    Tab* t = active();
    const std::string k = omniGmKey(t);
    if (!r.enabled || !t || k.empty()) return true;
    omniGmLoad();
    const bool on = !OGMM::enabled(omniGmStore, omniGmSession, k, t->omniPrivate);
    bool full = false;
    if (OGMM::setSite(omniGmStore, omniGmSession, k, on, t->omniPrivate, &full)) omniGmWrite();
    if (on && !full) omniGmPaused.erase(t);
    notice(OGMM::siteNotice(k, on, t->omniPrivate, full));
    omniFxRefresh();
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('static bool omniWapOn = false;               // OMNI_WEB_APPS_V1: the shown tab is an app tab (OmniWebAppsShell.h, omniWapTick)\n'
         'static bool omniAutoHideActive() { return (omniAutoHide || omniWapOn) && omniAutoHideAllowed; } // OMNI_WEB_APPS_V1: an app tab gets Auto-hide\'s layout\n',
         'static bool omniWapOn = false;               // OMNI_WEB_APPS_V1: the shown tab is an app tab (OmniWebAppsShell.h, omniWapTick)\n'
         'static bool omniGmOn = false;                // OMNI_GAME_MODE_V1: the shown tab is in game mode (OmniGameModeShell.h, omniGmTick)\n'
         'static bool omniAutoHideActive() { return (omniAutoHide || omniWapOn || omniGmOn) && omniAutoHideAllowed; } // OMNI_WEB_APPS_V1: an app tab gets Auto-hide\'s layout; OMNI_GAME_MODE_V1 too\n'),
        ('    if (omniWapOn && !pageFullscreen && !editing && !settingsOpen) omniChromeWanted = false;   // OMNI_WEB_APPS_V1: an app tab\'s bars stay hidden (Options: the app menu)\n',
         '    if (omniWapOn && !pageFullscreen && !editing && !settingsOpen) omniChromeWanted = false;   // OMNI_WEB_APPS_V1: an app tab\'s bars stay hidden (Options: the app menu)\n'
         '    if (omniGmOn && !pageFullscreen && !editing && !settingsOpen) omniChromeWanted = false;   // OMNI_GAME_MODE_V1: bars hidden in game mode\n'),
        ('    if (omniMagHidesPointer()) return; // OMNI_MAGNIFIER_V1: the lens is up; its crosshair marks the pointer\n',
         '    if (omniMagHidesPointer()) return; // OMNI_MAGNIFIER_V1: the lens is up; its crosshair marks the pointer\n'
         '    if (omniGmOn) return; // OMNI_GAME_MODE_V1: no pointer in game mode\n'),
        ('#include "OmniSiteClear.h" // OMNI_SITE_CLEAR_V1: Clear data for this site (pure)\n',
         '#include "OmniSiteClear.h" // OMNI_SITE_CLEAR_V1: Clear data for this site (pure)\n'
         '#include "OmniGameMode.h" // OMNI_GAME_MODE_V1: Game mode per site (pure)\n'),
        ('    omniGamepadTick(active(), settingsOpen || editing || omniOverlayOpen() || (active() && active()->omniPaintHold.active), omniShoulderFocused); // OMNI_GAMEPAD_V1 OMNI_PAINT_HOLD_V1\n',
         '    if (!omniGmPadTick(settingsOpen || editing || omniOverlayOpen() || (active() && active()->omniPaintHold.active))) /* OMNI_GAME_MODE_V1: game mode names the page itself */\n'
         '    omniGamepadTick(active(), settingsOpen || editing || omniOverlayOpen() || (active() && active()->omniPaintHold.active), omniShoulderFocused); // OMNI_GAMEPAD_V1 OMNI_PAINT_HOLD_V1\n'),
        ('        omniChromeEvent(event); // OMNI_STYLE_V1\n',
         '        if (omniGmEvent(event)) { omniSleepWake(event.type); omniGamepadEvent(event); continue; } // OMNI_GAME_MODE_V1: the page\'s alone (exit chord: omniGmTick)\n'
         '        omniChromeEvent(event); // OMNI_STYLE_V1\n'),
        ('    if (controller && !editing) {\n',
         '    if (controller && !editing && !omniGmTakesPad()) { // OMNI_GAME_MODE_V1: the sticks are the page\'s in game mode\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniWebAppsShell.h" // OMNI_WEB_APPS_V1 (uses the pinned tabs\' close rule)\n',
         '#include "OmniWebAppsShell.h" // OMNI_WEB_APPS_V1 (uses the pinned tabs\' close rule)\n'
         '#include "OmniGameModeShell.h" // OMNI_GAME_MODE_V1 (after web apps: shares the full-height layout)\n'),
        ('    omniWapTick(now);   // OMNI_WEB_APPS_V1: page-query timeout, start-page requests, the app layout of the shown tab\n',
         '    omniWapTick(now);   // OMNI_WEB_APPS_V1: page-query timeout, start-page requests, the app layout of the shown tab\n'
         '    omniGmTick(now);    // OMNI_GAME_MODE_V1: game mode of the shown tab, the exit chord\n'),
    ],
    'OmniContextMenu.h': [
        ('static void omniPtContextRows(OmniFxPanel& p); // OMNI_PINNED_TABS_V1 (OmniPinnedTabsShell.h)\n',
         'static void omniPtContextRows(OmniFxPanel& p); // OMNI_PINNED_TABS_V1 (OmniPinnedTabsShell.h)\n'
         'static void omniGmContextRows(OmniFxPanel& p); // OMNI_GAME_MODE_V1 (OmniGameModeShell.h)\n'
         'static bool omniGmContextAction(int id); // OMNI_GAME_MODE_V1\n'),
        ('        omniWapContextRows(p); // OMNI_WEB_APPS_V1: Open as app (Leave app mode) / Add to Apps\n',
         '        omniWapContextRows(p); // OMNI_WEB_APPS_V1: Open as app (Leave app mode) / Add to Apps\n'
         '        omniGmContextRows(p); // OMNI_GAME_MODE_V1: Game mode\n'),
        ('    if (omniWapContextAction(r.id)) return true; // OMNI_WEB_APPS_V1\n',
         '    if (omniWapContextAction(r.id)) return true; // OMNI_WEB_APPS_V1\n'
         '    if (omniGmContextAction(r.id)) return true; // OMNI_GAME_MODE_V1\n'),
    ],
    'OmniQuickMenu.h': [
        ('static bool omniSliSiteInput(const OmniFxRow& r, int b);\n',
         'static bool omniSliSiteInput(const OmniFxRow& r, int b);\n'
         'constexpr int omniGmSiteRowId = 770; // OMNI_GAME_MODE_V1 (OmniGameModeShell.h)\n'
         'static void omniGmSiteRow(OmniFxPanel& p, const std::string& host);\n'
         'static bool omniGmSiteInput(const OmniFxRow& r, int b);\n'),
        ('    omniHoSiteRow(p, host); // OMNI_HTTPS_ONLY_V1: HTTPS-only on this site\n',
         '    omniHoSiteRow(p, host); // OMNI_HTTPS_ONLY_V1: HTTPS-only on this site\n'
         '    omniGmSiteRow(p, host); // OMNI_GAME_MODE_V1: Game mode\n'),
        ('    if (r.id == omniSliSiteRowId) return omniSliSiteInput(r, b); // OMNI_SITE_LIST_V1\n',
         '    if (r.id == omniGmSiteRowId) return omniGmSiteInput(r, b); // OMNI_GAME_MODE_V1 (handles its disabled state)\n'
         '    if (r.id == omniSliSiteRowId) return omniSliSiteInput(r, b); // OMNI_SITE_LIST_V1\n'),
    ],
    'OmniControlsHelp.h': [
        ('    { kQuick, { gL2, gShoulders }, \'+\', false, "Quick tab switcher (most recent first)", "Keep {L2} held: {L1} / {R1} or D-pad choose, let go; {Circle} cancels", "omniTswChord (OMNI_TAB_SWITCHER_V1)" },\n',
         '    { kQuick, { gL2, gShoulders }, \'+\', false, "Quick tab switcher (most recent first)", "Keep {L2} held: {L1} / {R1} or D-pad choose, let go; {Circle} cancels", "omniTswChord (OMNI_TAB_SWITCHER_V1)" },\n'
         '    { kQuick, { gOptions, gCreate }, \'+\', true, "Leave game mode", "1 second; game mode: hold {Cross} > Game mode", "omniGmEvent / omniGmTick (OMNI_GAME_MODE_V1)" },\n'),
    ],
}


def variants(old0, s):
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
    for need, mark, tool in (('OmniFeatures3.h', 'OMNI_WEB_APPS_V1', 'apply_web_apps.py'),
                             ('OmniQuickMenu.h', 'OMNI_SITE_LIST_V1', 'apply_site_list.py'),
                             ('OmniBrowser.cpp', 'OMNI_GAMEPAD_V1', 'the OMNI_GAMEPAD_V1 base'),
                             ('OmniControlsHelp.h', 'OMNI_TAB_SWITCHER_V1', 'apply_tab_switcher.py')):
        if mark not in (root / need).read_bytes().decode('utf-8'):
            sys.exit('%s: %s missing: %s first' % (need, mark, tool))
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniGameMode.h', PURE, 'OmniSiteClear.h'),
            write_new('OmniGameModeShell.h', SHELL, 'OmniSiteClearShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
