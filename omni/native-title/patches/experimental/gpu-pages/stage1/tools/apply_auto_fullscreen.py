#!/usr/bin/env python3
"""OMNI_AUTO_FULLSCREEN_V1 (2026-11-16): Site settings > "Video: Normal / Fullscreen when playing" (backlog E20,
"Auto-fullscreen video per site").

What the user sees
  - Site settings (Options > Site settings) has a new row right after "Autoplay on this site":
        "Video"     Normal / Fullscreen when playing / "-" on omni:// / about: / new-tab pages (row disabled there)
    Cross or D-pad left / right switches it; a notice confirms ("Video on example.com: fullscreen when playing" /
    "Video on example.com: normal", + " (this session only)" in a private tab).
  - On such a site, when audible video starts playing in the shown tab (the tab's media state gains "playing audio"
    together with "playing video", or "playing audio" while Omni's video plane is in use), the playing <video> goes
    full screen through ONE page script (Element.requestFullscreen, webkitRequestFullscreen as a fallback). Exactly
    once per start of playback: a pause and resume within the leave delay changes nothing.
  - When playback has stopped (paused / ended) for 10 s (OmniAutoFullscreen::kLeaveMs), Omni leaves the full screen it
    entered (the shell's own exit: WKViewRequestExitFullScreen + setPageFullscreen(false), as on a tab switch).
  - Leaving that full screen by hand (Circle / the page's own button) is respected: no automatic full screen again on
    that page (address) in that tab until it shows another address (YouTube's next video is another address).
  - Never: YouTube TV mode (youtube.com/tv, any subdomain), a tab in Game mode (OMNI_GAME_MODE_V1, compiled in only when
    OmniGameModeShell.h is in the tree), test modes, omni:// / start / new-tab pages, the Master Control page, a Media
    downloads view, a crashed tab, background tabs (only the shown tab is watched; switching tabs starts over without a
    trigger), and not while an Omni panel / keyboard / settings / page editing is open when playback starts (that start
    is skipped, the next one counts).

The user-gesture question (checked in the engine's WebKit tree (s1/webkit))
  DocumentFullscreen::requestFullscreen refuses without transient activation (window->consumeTransientActivation()).
  WKPageCallAsyncJavaScript (unlike ...WithoutUserGesture) runs with WebCore::ForceUserGesture::Yes:
  ScriptController::executeScriptInWorld wraps the call in a UserGestureIndicator(IsProcessingUserGesture::Yes,
  ActivationTriggering), which grants the window transient activation for the synchronous part of the script. The
  page script calls requestFullscreen first thing (before any await), so the request passes the activation check by
  itself: the controller press that started playback is NOT needed (nor any ~1 s window), autoplaying / next-video
  starts work too. WKPreferencesSetFullScreenEnabled(true) is already set by Omni (OmniBrowser.cpp).
  Fallback: when the script answers "no video" (the player lives in a cross-origin iframe the main frame cannot see),
  "fail" (refused), nothing within 4 s, or WebKit's full screen has not arrived 2 s after an "ok", Omni's immersive
  mode takes over for that playback: the bars slide away and inputs leave them hidden (OMNI_VIDEO_IMMERSIVE_V1's
  behaviour, forced on: omniVideoImmersive = omniAutoHideActive() while omniAfsImmersiveNow()), Triangle / Options /
  R3 / L1 / R1 / touchpad still show them; it ends after 10 s of stopped playback or when the page goes full screen
  itself. Only with Auto-hide on (bars over the page); with Auto-hide off the bars are part of the layout and stay.
  The OMNI AUTO FULLSCREEN log line says which path was taken (fullscreen ok / sent / fallback: <answer>).

Cost: no page polling, no observer. omniAfsTick (from omniF3Tick) returns at once while no site is set (store and
private session empty) and nothing is being managed; otherwise one UI-process cached WKPageGetMediaState of the shown
tab every 250 ms (no IPC). One page script per playback start.

Store: /data/omni/site-autofs.txt ("omni-site-autofs\\t1", "fullscreen\\t<host>" lines, at most 500), written through
omniIoQueue (never in test modes). Host key: lower case, "www." dropped while a dot remains, no port, IPv6 without
brackets, http / https only. Private tabs: a choice made there is kept for this run only (omniAfsSession, never
written, never shown or applied in normal tabs); private tabs otherwise follow the saved list.

Pure part: engine/entry/OmniAutoFullscreen.h (no SDL / WebKit): host key, YouTube TV check, store parse / serialize /
toggle with the private session, the page script and its answer, the per-tab Tracker (edges, phases, timers), texts.
Tested by tools/test_auto_fullscreen.cpp:
    g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_auto_fullscreen.cpp -o t && ./t s.js
(writes the page script, wrapped in an async function, to s.js: node --check s.js; tools/test_auto_fullscreen_js.mjs
runs it on fake DOMs).
Shell side: engine/entry/OmniAutoFullscreenShell.h (included from OmniFeatures3.h after OmniReaderAutoShell.h, so
after OmniGameModeShell.h when that exists and before OmniSiteListShell.h). Alias OAFS, names omniAfs*, Site settings
row 793 (free in the tree and in every sibling's code on 2026-11-16; checked again before the first apply).

Anchors (whole lines, exactly once each; MARK makes each file idempotent; line endings kept):
  OmniBrowser.cpp   the OmniReaderAuto.h include line (pure include after it); `static bool omniVideoImmersive = false;`
                    (declaration after it); the omniVideoImmersive line of omniStyleTick (the fallback after it).
  OmniQuickMenu.h   the omniApSiteInput declaration (row id + declarations after it); the omniApSiteRow(p, host) call
                    (our row after it); the omniApSiteRowId dispatch (ours before it).
  OmniFeatures3.h   the OmniReaderAutoShell.h include line (ours after it); the omniTaTick line of omniF3Tick (ours after).
Apply AFTER apply_video_immersive.py, apply_autoplay.py, apply_tab_audio.py, apply_site_clear.py (WKDictionary.h) and
apply_reader_auto.py (their lines are anchors).
usage: apply_auto_fullscreen.py <engine tree>   (keeps each file's line endings; re-run prints "already")

"Sites with custom settings" (apply_site_list.py, NOT edited here) would need, to list and reset these sites (the same
optional way as reader view / game mode):
  OmniSiteList.h       a Kind kAutoFs (before kKindCount) and itemText: case kAutoFs: return "Video fullscreen";
  OmniSiteListShell.h  #if __has_include("OmniAutoFullscreenShell.h") (it is included from OmniFeatures3.h, before)
                       omniSliCollect():  omniAfsLoad(); for (const auto& h : omniAfsStore.sites) add(OSLI::kAutoFs, h, 1);
                       omniSliReset():    case OSLI::kAutoFs: OAFS::setSite(omniAfsStore, it.key, false); afs = true; break;
                                          ... if (afs) omniAfsWrite();
                       one-site panel row (optional): value OAFS::rowValue(OAFS::saved(omniAfsStore, k)), change with
                       OAFS::setSite(omniAfsStore, k, !saved) + omniAfsWrite(); key k = OAFS::hostKey("https://<host>/").
                       Private-tab choices (omniAfsSession) must not be listed, like the other stores.
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_AUTO_FULLSCREEN_V1'
HERE = Path(__file__).resolve().parent
if len(sys.argv) != 2:
    sys.exit('usage: apply_auto_fullscreen.py <engine tree>')
root = Path(sys.argv[1]) / 'engine' / 'entry'
IDS = ('793',)
NAMES = ('OAFS', 'omniAfs', 'OmniAutoFullscreen', 'OMNI_AUTO_FULLSCREEN', r'site-autofs\.txt')

PURE = r'''// OMNI_AUTO_FULLSCREEN_V1: the pure part of Site settings > "Video: Normal / Fullscreen when playing" (no SDL, no
// WebKit). The shell side is OmniAutoFullscreenShell.h; the reasons are in tools/apply_auto_fullscreen.py. Tested on
// the host with g++ (test_auto_fullscreen.cpp) and node (test_auto_fullscreen_js.mjs, the page script on fake DOMs).
#pragma once
#include <cstddef>
#include <cstdint>
#include <map>
#include <set>
#include <string>

namespace OmniAutoFullscreen {

constexpr const char* kFileName = "site-autofs.txt";
constexpr const char* kHeader = "omni-site-autofs\t1";
constexpr size_t kMaxSites = 500, kHostMax = 253;
constexpr long kMaxFileBytes = 64L << 10;
constexpr int kSiteRowId = 793;
constexpr uint32_t kPollMs = 250;      // the shown tab's media state (UI-process cached) at most this often
constexpr uint32_t kLeaveMs = 10000;   // playback stopped this long: leave the full screen (or the bars fallback)
constexpr uint32_t kAskMs = 4000;      // no answer from the page script by then: the bars fallback
constexpr uint32_t kEnterMs = 2000;    // after "ok" / "sent": WebKit's full screen must have arrived by then
constexpr int kScriptWaitMs = 2500;    // the page script waits this long for requestFullscreen's promise
constexpr const char* kAnswerTag = "omni-autofs;";

// --- hosts ------------------------------------------------------------------------------------------------------
inline char lower(char c) { return c >= 'A' && c <= 'Z' ? char(c + ('a' - 'A')) : c; }
struct UrlParts { std::string host, path; bool v6 = false; };   // host lower case without brackets / port / trailing dot
inline bool split(const std::string& url, UrlParts& u)
{
    size_t start;
    std::string head;
    for (size_t i = 0; i < url.size() && i < 8; ++i) head += lower(url[i]);
    if (head.compare(0, 8, "https://") == 0) start = 8;
    else if (head.compare(0, 7, "http://") == 0) start = 7;
    else return false;
    size_t end = url.find_first_of("/?#", start);
    if (end == std::string::npos) end = url.size();
    std::string auth = url.substr(start, end - start);
    const size_t at = auth.rfind('@');
    if (at != std::string::npos) auth = auth.substr(at + 1);
    std::string host;
    if (!auth.empty() && auth[0] == '[') {
        const size_t close = auth.find(']');
        if (close == std::string::npos || close < 2) return false;
        if (close + 1 < auth.size() && auth[close + 1] != ':') return false;
        host = auth.substr(1, close - 1);
        u.v6 = true;
    } else {
        host = auth.substr(0, auth.find(':'));
        u.v6 = false;
    }
    for (auto& c : host) c = lower(c);
    while (!host.empty() && host.back() == '.') host.pop_back();
    if (host.empty() || host.size() > kHostMax) return false;
    for (char c : host) {
        const bool ok = (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '.' || c == '-' || c == '_' || (u.v6 && c == ':');
        if (!ok) return false;
    }
    u.host = host;
    size_t pathEnd = url.find_first_of("?#", end);
    if (pathEnd == std::string::npos) pathEnd = url.size();
    u.path = end < pathEnd ? url.substr(end, pathEnd - end) : std::string();
    if (u.path.empty()) u.path = "/";
    return true;
}
// "https://User@WWW.Example.COM:8443/a" -> "example.com", "http://[::1]:80/" -> "::1". "" for anything else.
inline std::string hostKey(const std::string& url)
{
    UrlParts u;
    if (!split(url, u)) return std::string();
    std::string h = u.host;
    if (!u.v6 && h.compare(0, 4, "www.") == 0 && h.find('.', 4) != std::string::npos) h = h.substr(4);
    return h;
}
// YouTube's TV app (youtube.com/tv, /tv/..., /tv#/watch...; any youtube.com subdomain). Never automatic there.
inline bool tvUrl(const std::string& url)
{
    UrlParts u;
    if (!split(url, u) || u.v6) return false;
    const std::string yt = "youtube.com";
    const bool host = u.host == yt || (u.host.size() > yt.size() && u.host.compare(u.host.size() - yt.size() - 1, yt.size() + 1, "." + yt) == 0);
    if (!host) return false;
    std::string p;
    for (char c : u.path) p += lower(c);
    return p == "/tv" || p.compare(0, 4, "/tv/") == 0;
}

// --- the store ----------------------------------------------------------------------------------------------------
struct Store { std::set<std::string> sites; };
using Session = std::map<std::string, bool>;   // choices made in private tabs (this run, private tabs only)
inline bool saved(const Store& s, const std::string& host) { return !host.empty() && s.sites.count(host) != 0; }
// A normal tab sees the saved store only; a private tab sees its session choice first.
inline bool enabled(const Store& s, const Session& session, const std::string& host, bool privateTab)
{
    if (host.empty()) return false;
    if (privateTab) { const auto it = session.find(host); if (it != session.end()) return it->second; }
    return saved(s, host);
}
// Removing always works; a new host when 500 are saved does not.
inline bool setSite(Store& s, const std::string& host, bool on)
{
    if (host.empty()) return false;
    if (!on) { s.sites.erase(host); return true; }
    if (!s.sites.count(host) && s.sites.size() >= kMaxSites) return false;
    s.sites.insert(host);
    return true;
}
// The row's change. Private tab: a session row exists only while it differs from the saved choice (never written).
// Returns false when the saved store is full (nothing changed).
inline bool toggle(Store& s, Session& session, const std::string& host, bool privateTab, bool& now)
{
    now = !enabled(s, session, host, privateTab);
    if (host.empty()) return false;
    if (privateTab) {
        if (now == saved(s, host)) session.erase(host); else session[host] = now;
        return true;
    }
    return setSite(s, host, now);
}
inline std::string serialize(const Store& s)
{
    std::string out = std::string(kHeader) + "\n";
    size_t n = 0;
    for (const auto& h : s.sites) {
        if (h.empty() || n >= kMaxSites) continue;
        out += "fullscreen\t" + h + "\n";
        ++n;
    }
    return out;
}
inline Store parse(const std::string& text)
{
    Store s;
    size_t pos = 0;
    while (pos < text.size()) {
        size_t nl = text.find('\n', pos);
        if (nl == std::string::npos) nl = text.size();
        std::string line = text.substr(pos, nl - pos);
        pos = nl + 1;
        while (!line.empty() && (line.back() == '\r' || line.back() == ' ')) line.pop_back();
        const size_t tab = line.find('\t');
        if (tab == std::string::npos || line.compare(0, tab, "fullscreen") != 0) continue;
        const std::string raw = line.substr(tab + 1);
        if (raw.empty() || raw.find_first_of("/?#@ \t") != std::string::npos) continue;
        const bool v6 = raw.find(':') != std::string::npos;
        const std::string host = hostKey("https://" + (v6 ? "[" + raw + "]" : raw) + "/");
        if (host.empty() || host != raw) continue;   // only keys as serialize() writes them
        if (!s.sites.count(host) && s.sites.size() >= kMaxSites) continue;
        s.sites.insert(host);
    }
    return s;
}

// --- the page script ------------------------------------------------------------------------------------------------
// The body of an async function (WKPageCallAsyncJavaScript: ForceUserGesture::Yes, so the window has transient
// activation while the synchronous part runs). requestFullscreen is called before any await. Picks the largest
// playing, audible, decoded <video> of the main frame. Answers "omni-autofs;" + ok | sent | already | novideo | fail:<name>.
inline std::string pageScript()
{
    std::string s = "const waitMs = " + std::to_string(kScriptWaitMs) + ";\n";
    s += "const tag = \"" + std::string(kAnswerTag) + "\";\n";
    s += R"JS(const P = Promise, later = setTimeout;
const d = document;
if (d.fullscreenElement || d.webkitFullscreenElement) return tag + "already";
let best = null, area = -1;
const vs = d.getElementsByTagName("video");
for (let i = 0; i < vs.length && i < 50; i++) {
  const v = vs[i];
  if (v.paused || v.ended || v.muted || v.volume === 0 || v.readyState < 2) continue;
  let a = 0;
  try { const r = v.getBoundingClientRect(); a = Math.max(0, r.width) * Math.max(0, r.height); } catch (e) {}
  if (a > area) { area = a; best = v; }
}
if (!best) return tag + "novideo";
const req = best.requestFullscreen || best.webkitRequestFullscreen;
if (typeof req !== "function") return tag + "fail:noapi";
let p;
try { p = req.call(best); } catch (e) { return tag + "fail:" + (e && e.name ? String(e.name) : "error"); }
if (!p || typeof p.then !== "function") return tag + "sent";
return await new P(res => {
  let done = false;
  const fin = s => { if (!done) { done = true; res(s); } };
  p.then(() => fin(tag + "ok"), e => fin(tag + "fail:" + (e && e.name ? String(e.name) : "error")));
  later(() => fin(tag + "sent"), waitMs);
});
)JS";
    return s;
}
enum class Answer { None, Ok, Sent, Already, NoVideo, Failed };
inline Answer parseAnswer(const std::string& text)
{
    const std::string tag(kAnswerTag);
    if (text.compare(0, tag.size(), tag) != 0) return Answer::None;
    const std::string v = text.substr(tag.size());
    if (v == "ok") return Answer::Ok;
    if (v == "sent") return Answer::Sent;
    if (v == "already") return Answer::Already;
    if (v == "novideo") return Answer::NoVideo;
    if (v.compare(0, 5, "fail:") == 0) return Answer::Failed;
    return Answer::None;
}

// --- the tracker: the shown tab's playback edges, what Omni did, the timers ------------------------------------------
enum class Phase { Idle, Asking, Full, Bars };
enum class Act { None, Request, Exit, StartBars, EndBars };
struct Input {
    uintptr_t tab = 0;        // the shown tab (0: none)
    std::string url;
    bool on = false;          // the site's choice for this tab (private session or saved)
    bool excluded = false;    // never here: YouTube TV, game mode, test mode, not a web page, Downloads view, crashed
    bool busy = false;        // an Omni panel / keyboard / settings / page editing is open (a start now is skipped)
    bool playing = false;     // audible video playing
    bool fullscreen = false;  // the page is full screen (pageFullscreen)
};
struct Tracker {
    uintptr_t tab = 0;
    std::string url, declined;   // declined: the user left Omni's full screen on this address (no repeat there)
    bool playing = false, stopped = false, seenFull = false;
    uint32_t stoppedAt = 0, askedAt = 0, fullAt = 0;
    unsigned gen = 0;            // the page script's generation (late / stale answers are dropped)
    Phase phase = Phase::Idle;

    bool idle() const { return phase == Phase::Idle; }
    Act step(const Input& in, uint32_t now)
    {
        if (in.tab != tab) {     // another tab shown (or none): start over, no trigger for what already plays
            const bool bars = phase == Phase::Bars;
            tab = in.tab; url = in.url; declined.clear();
            playing = in.playing; stopped = false; seenFull = false;
            phase = Phase::Idle;
            ++gen;
            return bars ? Act::EndBars : Act::None;
        }
        if (in.url != url) { url = in.url; declined.clear(); }
        const bool rise = in.playing && !playing, fall = !in.playing && playing;
        playing = in.playing;
        if (rise) stopped = false;
        if (fall) { stopped = true; stoppedAt = now; }
        const bool longStop = !playing && stopped && uint32_t(now - stoppedAt) >= kLeaveMs;
        if (in.excluded || !in.on) {   // a full screen Omni entered stays until the user leaves it
            const bool bars = phase == Phase::Bars;
            if (phase == Phase::Asking) ++gen;
            phase = Phase::Idle;
            return bars ? Act::EndBars : Act::None;
        }
        switch (phase) {
        case Phase::Idle:
            if (rise && !in.busy && !in.fullscreen && declined != url) {
                phase = Phase::Asking;
                askedAt = now;
                ++gen;
                return Act::Request;
            }
            return Act::None;
        case Phase::Asking:
            if (uint32_t(now - askedAt) >= kAskMs) { ++gen; phase = Phase::Bars; return Act::StartBars; }
            return Act::None;
        case Phase::Full:
            if (in.fullscreen) seenFull = true;
            if (!seenFull) {
                if (uint32_t(now - fullAt) >= kEnterMs) { phase = Phase::Bars; return Act::StartBars; }
                return Act::None;
            }
            if (!in.fullscreen) { declined = url; phase = Phase::Idle; return Act::None; }   // left by hand (or by the page)
            if (longStop) { phase = Phase::Idle; return Act::Exit; }
            return Act::None;
        case Phase::Bars:
            if (in.fullscreen) { phase = Phase::Idle; return Act::EndBars; }   // the page went full screen itself
            if (longStop) { phase = Phase::Idle; return Act::EndBars; }
            return Act::None;
        }
        return Act::None;
    }
    // The page script's answer for (forTab, forGen).
    Act answered(Answer a, uintptr_t forTab, unsigned forGen, uint32_t now)
    {
        if (phase != Phase::Asking || forTab != tab || forGen != gen) return Act::None;
        if (a == Answer::Ok || a == Answer::Sent) { phase = Phase::Full; fullAt = now; seenFull = false; return Act::None; }
        if (a == Answer::Already) { phase = Phase::Idle; return Act::None; }   // not Omni's full screen: not managed
        phase = Phase::Bars;
        return Act::StartBars;
    }
    bool barsFor(uintptr_t shown) const { return phase == Phase::Bars && shown != 0 && shown == tab; }
};

// --- texts --------------------------------------------------------------------------------------------------------
inline const char* rowLabel() { return "Video"; }
inline std::string rowValue(bool on) { return on ? "Fullscreen when playing" : "Normal"; }
inline std::string siteNotice(const std::string& host, bool on, bool privateTab, bool full)
{
    if (full) return "Too many sites with fullscreen video (500). Set one back to Normal first";
    std::string s = "Video on " + host + (on ? ": fullscreen when playing" : ": normal");
    if (privateTab) s += " (this session only)";
    return s;
}
inline const char* barsNotice() { return "Full screen not available here: bars hidden while the video plays"; }
inline const char* actName(Act a)
{
    switch (a) {
    case Act::Request: return "request";
    case Act::Exit: return "exit";
    case Act::StartBars: return "fallback bars";
    case Act::EndBars: return "bars back";
    default: return "none";
    }
}

} // namespace OmniAutoFullscreen
'''

SHELL = r'''// OMNI_AUTO_FULLSCREEN_V1: Site settings > "Video: Normal / Fullscreen when playing" (shell side). Included from
// OmniFeatures3.h (inside OmniBrowser.cpp's anonymous namespace, after OmniReaderAutoShell.h, so after
// OmniGameModeShell.h when that exists and before OmniSiteListShell.h). The pure part is OmniAutoFullscreen.h; the
// reasons (the user-gesture question, the fallback) are in tools/apply_auto_fullscreen.py. Main thread only;
// site-autofs.txt is written by omniIoQueue.
#pragma once

namespace OAFS = OmniAutoFullscreen;
static_assert(OAFS::kSiteRowId == omniAfsSiteRowId, "OMNI_AUTO_FULLSCREEN_V1: Site settings row id");

static OAFS::Store omniAfsStore;
static bool omniAfsLoaded = false;
static OAFS::Session omniAfsSession;         // choices made in private tabs: this run, private tabs only
static OAFS::Tracker omniAfsTrack;
static uint32_t omniAfsLastPoll = 0;
static std::set<std::string> omniAfsHinted;  // sites whose fallback notice was shown this run

static void omniAfsLoad()
{
    if (omniAfsLoaded) return;
    omniAfsLoaded = true;
    FILE* f = fopen(omniData(OAFS::kFileName).c_str(), "rb");
    if (!f) return;
    std::string text;
    char buf[4096];
    size_t n;
    while ((n = fread(buf, 1, sizeof buf, f)) > 0 && long(text.size()) < OAFS::kMaxFileBytes) text.append(buf, n);
    fclose(f);
    omniAfsStore = OAFS::parse(text);
}
static void omniAfsWrite()
{
    if (omniTestMode()) return;
    omniIoQueue(omniData(OAFS::kFileName), OAFS::serialize(omniAfsStore), false);
}
static bool omniAfsOnFor(const Tab& t)
{
    omniAfsLoad();
    return OAFS::enabled(omniAfsStore, omniAfsSession, OAFS::hostKey(t.url), t.omniPrivate);
}
static bool omniAfsGameMode(Tab* t)
{
#if __has_include("OmniGameModeShell.h")
    return omniGmOn || omniGmWanted(t);   // OMNI_GAME_MODE_V1 (included before this file)
#else
    (void)t;
    return false;
#endif
}
static bool omniAfsExcluded(Tab* t)
{
    return !t || t->crashed || !t->page || omniTestMode() || !omniWebURL(t->url) || t->omniNewTabPage || t->omniPagesTab
        || omniMcOrigin(t->url) || omniMediaOwns(*t) || OAFS::tvUrl(t->url) || omniAfsGameMode(t);
}
// Audible video: UI-process cached media state (no IPC); Omni's video plane counts as video.
static bool omniAfsPlaying(const Tab& t)
{
    const auto m = WKPageGetMediaState(t.page);
    return (m & kWKMediaIsPlayingAudio) && ((m & kWKMediaIsPlayingVideo) || OmniMedia::Hw::holePunchActive());
}
// OmniBrowser.cpp's omniStyleTick: the fallback keeps the bars away (OMNI_VIDEO_IMMERSIVE_V1's behaviour) for this tab.
static bool omniAfsImmersiveNow() { return omniAfsTrack.barsFor(reinterpret_cast<uintptr_t>(active())); }

struct OmniAfsAsk { uintptr_t tab; unsigned gen; };
static void omniAfsDo(OAFS::Act a);
static void omniAfsRequest(Tab* t)
{
    auto body = adoptWK(WKStringCreateWithUTF8CString(OAFS::pageScript().c_str()));
    auto args = adoptWK(WKDictionaryCreate(nullptr, nullptr, 0));   // an async function needs an argument list
    // WKPageCallAsyncJavaScript (not ...WithoutUserGesture): ForceUserGesture::Yes gives requestFullscreen its activation.
    WKPageCallAsyncJavaScript(t->page, body.get(), args.get(), nullptr, new OmniAfsAsk{ reinterpret_cast<uintptr_t>(t), omniAfsTrack.gen },
        [](WKTypeRef result, WKErrorRef error, void* context) {
            std::unique_ptr<OmniAfsAsk> ask(static_cast<OmniAfsAsk*>(context));
            const std::string answer = omniFxResultString(result, error);
            const OAFS::Act act = omniAfsTrack.answered(OAFS::parseAnswer(answer), ask->tab, ask->gen, SDL_GetTicks());
            fprintf(stderr, "OMNI AUTO FULLSCREEN: answer %s -> %s\n", answer.empty() ? "-" : answer.c_str(),
                    act == OAFS::Act::StartBars ? "fallback (bars hidden)" : omniAfsTrack.phase == OAFS::Phase::Full ? "fullscreen" : "ignored");
            fflush(stderr);
            omniAfsDo(act);
        });
}
static void omniAfsDo(OAFS::Act a)
{
    if (a == OAFS::Act::None) return;
    Tab* t = active();
    fprintf(stderr, "OMNI AUTO FULLSCREEN: %s (%s)\n", OAFS::actName(a), t ? OAFS::hostKey(t->url).c_str() : "-"); fflush(stderr);
    switch (a) {
    case OAFS::Act::Request:
        if (t && t->page && !t->crashed) omniAfsRequest(t);
        break;
    case OAFS::Act::Exit:
        if (pageFullscreen && t) { WKViewRequestExitFullScreen(t->view.get()); setPageFullscreen(false); }
        break;
    case OAFS::Act::StartBars:
        omniChromeWanted = false;   // slide away now; omniStyleTick keeps them away while omniAfsImmersiveNow()
        omniShellDirty = true;
        if (t && !omniAutoHideActive()) break;   // bars are part of the layout: nothing to hide
        if (t && omniAfsHinted.size() < 200 && omniAfsHinted.insert(OAFS::hostKey(t->url)).second) notice(OAFS::barsNotice());
        break;
    case OAFS::Act::EndBars:
        omniLastInput = SDL_GetTicks();
        omniChromeWanted = true;
        omniShellDirty = true;
        break;
    default:
        break;
    }
}
// omniF3Tick, every pass: returns at once while no site is set and nothing is managed; else 4 cached reads a second.
static void omniAfsTick(uint32_t now)
{
    omniAfsLoad();
    if (omniAfsStore.sites.empty() && omniAfsSession.empty() && omniAfsTrack.idle()) return;
    if (uint32_t(now - omniAfsLastPoll) < OAFS::kPollMs) return;
    omniAfsLastPoll = now;
    Tab* t = active();
    OAFS::Input in;
    if (t) {
        in.tab = reinterpret_cast<uintptr_t>(t);
        in.url = t->url;
        in.excluded = omniAfsExcluded(t);
        in.on = !in.excluded && omniAfsOnFor(*t);
        in.busy = settingsOpen || editing || pageEditing || omniKbTarget || omniOverlayOpen();
        in.playing = !in.excluded && omniAfsPlaying(*t);
        in.fullscreen = pageFullscreen;
    }
    omniAfsDo(omniAfsTrack.step(in, now));
}

// --- Site settings > Video: Normal / Fullscreen when playing ------------------------------------------------------------
static std::string omniAfsSiteHost()
{
    Tab* t = active();
    return t && omniWebURL(t->url) && !t->omniNewTabPage && !t->omniPagesTab ? OAFS::hostKey(t->url) : std::string();
}
static void omniAfsSiteRow(OmniFxPanel& p, const std::string&)
{
    omniAfsLoad();
    const std::string host = omniAfsSiteHost();
    OmniFxRow r; r.id = omniAfsSiteRowId; r.label = OAFS::rowLabel(); r.stepper = true; r.enabled = !host.empty();
    r.value = host.empty() ? std::string("-") : OAFS::rowValue(OAFS::enabled(omniAfsStore, omniAfsSession, host, active()->omniPrivate));
    p.rows.push_back(r);
}
static bool omniAfsSiteInput(const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A && b != SDL_CONTROLLER_BUTTON_DPAD_LEFT && b != SDL_CONTROLLER_BUTTON_DPAD_RIGHT) return false;
    const std::string host = omniAfsSiteHost();
    Tab* t = active();
    if (!r.enabled || host.empty() || !t) return true;
    omniAfsLoad();
    const bool priv = t->omniPrivate;
    bool now = false;
    const bool ok = OAFS::toggle(omniAfsStore, omniAfsSession, host, priv, now);
    if (ok && !priv) omniAfsWrite();
    notice(OAFS::siteNotice(host, now, priv, !ok));
    omniShellDirty = true;
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniReaderAuto.h" // OMNI_READER_AUTO_V1: Reader view hint + Always open in Reader view per site (pure)\n',
         '#include "OmniReaderAuto.h" // OMNI_READER_AUTO_V1: Reader view hint + Always open in Reader view per site (pure)\n'
         '#include "OmniAutoFullscreen.h" // OMNI_AUTO_FULLSCREEN_V1: Video fullscreen when playing, per site (pure)\n'),
        ('static bool omniVideoImmersive = false;\n',
         'static bool omniVideoImmersive = false;\n'
         'static bool omniAfsImmersiveNow(); // OMNI_AUTO_FULLSCREEN_V1 (OmniAutoFullscreenShell.h): the no-fullscreen fallback\n'),
        ('    omniVideoImmersive = omniAutoHideActive() && omniVideoFillsView();   // OMNI_VIDEO_IMMERSIVE_V1\n',
         '    omniVideoImmersive = omniAutoHideActive() && omniVideoFillsView();   // OMNI_VIDEO_IMMERSIVE_V1\n'
         '    if (omniAfsImmersiveNow()) omniVideoImmersive = omniAutoHideActive();   // OMNI_AUTO_FULLSCREEN_V1: fallback while the video plays\n'),
    ],
    'OmniQuickMenu.h': [
        ('static bool omniApSiteInput(const OmniFxRow& r, int b);\n',
         'static bool omniApSiteInput(const OmniFxRow& r, int b);\n'
         'constexpr int omniAfsSiteRowId = 793; // OMNI_AUTO_FULLSCREEN_V1 (OmniAutoFullscreenShell.h)\n'
         'static void omniAfsSiteRow(OmniFxPanel& p, const std::string& host);\n'
         'static bool omniAfsSiteInput(const OmniFxRow& r, int b);\n'),
        ('    omniApSiteRow(p, host); // OMNI_AUTOPLAY_V1: Autoplay on this site\n',
         '    omniApSiteRow(p, host); // OMNI_AUTOPLAY_V1: Autoplay on this site\n'
         '    omniAfsSiteRow(p, host); // OMNI_AUTO_FULLSCREEN_V1: Video: Normal / Fullscreen when playing\n'),
        ('    if (r.id == omniApSiteRowId) return omniApSiteInput(r, b); // OMNI_AUTOPLAY_V1 (handles its disabled state)\n',
         '    if (r.id == omniAfsSiteRowId) return omniAfsSiteInput(r, b); // OMNI_AUTO_FULLSCREEN_V1 (handles its disabled state)\n'
         '    if (r.id == omniApSiteRowId) return omniApSiteInput(r, b); // OMNI_AUTOPLAY_V1 (handles its disabled state)\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniReaderAutoShell.h" // OMNI_READER_AUTO_V1 (before OmniSiteListShell.h)\n',
         '#include "OmniReaderAutoShell.h" // OMNI_READER_AUTO_V1 (before OmniSiteListShell.h)\n'
         '#include "OmniAutoFullscreenShell.h" // OMNI_AUTO_FULLSCREEN_V1 (after game mode, before the site list)\n'),
        ('    omniTaTick(now);    // OMNI_TAB_AUDIO_V1: media state every 500 ms\n',
         '    omniTaTick(now);    // OMNI_TAB_AUDIO_V1: media state every 500 ms\n'
         '    omniAfsTick(now);   // OMNI_AUTO_FULLSCREEN_V1: the shown tab\'s playback (only while a site is set)\n'),
    ],
}
NEEDS = {'OmniBrowser.cpp': ('OMNI_VIDEO_IMMERSIVE_V1', 'OMNI_READER_AUTO_V1', 'OMNI_SITE_CLEAR_V1'),
         'OmniQuickMenu.h': ('OMNI_AUTOPLAY_V1',),
         'OmniFeatures3.h': ('OMNI_READER_AUTO_V1', 'OMNI_TAB_AUDIO_V1')}


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
    mine = {'OmniAutoFullscreen.h', 'OmniAutoFullscreenShell.h'}
    # A sibling not applied to this tree yet still owns its ids: its code (generated headers / edits included,
    # comments and docstring stripped) assigning one of ours to a row id ("kSiteRowId = 793", "omniXxSiteRowId = 793",
    # "constexpr int x = 793", "r.id = 793") is a clash.
    assign = re.compile(r'(?:\b\w*[Rr]ow\w*|\bconstexpr\s+int\s+\w+|\.id)\s*=\s*(%s)(?![\w.])' % '|'.join(IDS))
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
    msgs = [write_new('OmniAutoFullscreen.h', PURE, 'OmniReaderAuto.h'),
            write_new('OmniAutoFullscreenShell.h', SHELL, 'OmniReaderAutoShell.h')]
    msgs += [patch(fname, edits) for fname, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
