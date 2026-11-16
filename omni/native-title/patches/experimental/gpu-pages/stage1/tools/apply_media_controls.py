#!/usr/bin/env python3
"""OMNI_MEDIA_CONTROLS_V1 (2026-11-16): global media controls ("Now playing", roadmap R3-012).

What the user sees
  - Options (the quick menu) gets a "Now playing" tile next to Browse / Quick toggles / Apps / Settings / More while
    some tab plays video or sound (or played sound earlier and is now paused). Its value is the tab's title.
  - Choosing it opens the "Now playing" panel for THAT tab, even when it is in the background:
      subtitle  title (page's media metadata when it has any, else the page title) - artist | site
      Play / Pause      (value: position "1:05 / 4:00", "(live)" for streams)
      Previous track    restarts the track when more than 3 s in; else the site's previous button, else the media key
      Next track        the site's next button (YouTube, YouTube Music, Spotify, SoundCloud, aria "Next..."),
                        else a MediaTrackNext key event (some sites ignore it; the notice says so)
      Back 10 seconds / Forward 10 seconds
      Mute tab / Unmute tab   (the tab-audio mute from OMNI_TAB_AUDIO_V1, so the tab badge follows)
      Go to tab / Back to the page
  - Private tabs work the same; nothing is stored anywhere (all state is in memory), nothing is sent anywhere.

Which tab: the active tab if it plays sound, else the first tab playing sound, else the tab that last played sound
(still open, so a paused song can be resumed), else the active / first tab playing video (muted previews last).
"Playing" is WebKit's cached UI-process media state (WKPageGetMediaState, no IPC); the last-sound tab is recorded in
the existing isPlayingAudioDidChange callback (event driven, no polling, no timer).

How
  No script is added to pages and nothing polls. Opening the panel runs ONE WKPageEvaluateJavaScriptInMainFrame in the
  target tab (read: element state + metadata); each button press runs ONE evaluate that acts and returns the same
  read-out, so the panel updates from the answer. Scripts run with ForceUserGesture::Yes (WKPage.cpp), so play() is
  allowed. The element: the one whose currentSrc was read when the panel opened (passed as a JS string literal,
  escaped by OmniMediaControls::jsString), else the first playing <video>/<audio> (same-origin frames up to depth 3),
  else the most advanced one with a source. Cross-origin frames (an embedded player on another site) are not reachable.
  Media Session: this WebKit is built with ENABLE_MEDIA_SESSION OFF (build/cmakeconfig.h), so navigator.mediaSession is
  absent and a page's action handlers cannot be called; the script still reads navigator.mediaSession.metadata when it
  exists (a later build), and uses site buttons / media-key events for previous / next.
  The play/pause label follows WebKit's media state (refreshed from isPlayingAudioDidChange while the panel is open).

Pure part: engine/entry/OmniMediaControls.h (no SDL/WebKit): target choice, read-out parsing, labels, script text.
Tested by tools/test_media_controls.cpp:  g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_media_controls.cpp -o t && ./t
  and ./t --emit <dir> + node tools/test_media_controls.cjs <dir> (runs the scripts against a small fake DOM).
Shell side: engine/entry/OmniMediaControlsShell.h (included from OmniFeatures3.h after OmniHttpsOnlyShell.h).

Anchors (exactly once each; MARK makes each file idempotent):
  OmniBrowser.cpp   the OmniHttpsOnly.h include line; the omniSavedMediaChanged forward declaration (adds
                    omniNpMediaChanged's); the ui.isPlayingAudioDidChange line (also calls omniNpMediaChanged).
  OmniQuickMenu.h   the "enum { omniMqBrowse = 8000, ..." line (declarations); the top-level group-row loop of
                    omniFxQuickBuild (the tile after it); the omniMqBlock input line of omniFxQuickInput (handler before
                    it, i.e. before the r.id >= 900 rows).
  OmniFeatures3.h   the OmniHttpsOnlyShell.h include line.
Apply AFTER apply_tab_audio.py and apply_https_only.py (their lines / functions are used).
usage: apply_media_controls.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_MEDIA_CONTROLS_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_MEDIA_CONTROLS_V1: the pure part of "Now playing" (no SDL, no WebKit). The shell side is
// OmniMediaControlsShell.h; the reasons are in tools/apply_media_controls.py. Tested with g++ (test_media_controls.cpp).
#pragma once
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

namespace OmniMediaControls {

enum Action { kProbe = 0, kToggle, kPrev, kNext, kBack, kForward };
enum State { kNone = 0, kPlaying, kPaused };
enum Did { kDidNothing = 0, kDidElement, kDidButton, kDidKey };
// Options tile id (top level of the quick menu; the group rows are 8000-8005) and the panel's row ids.
constexpr int kQuickRowId = 8100;
enum { kRowPlay = 1, kRowPrev, kRowNext, kRowBack, kRowForward, kRowMute, kRowGo, kRowGone };
constexpr int kSeekSeconds = 10;
constexpr double kLive = -2;          // Info::duration of a stream without an end
constexpr size_t kSrcMax = 2000, kTextMax = 300;

// --- which tab ---------------------------------------------------------------------------------------------------
struct Candidate { uintptr_t key = 0; bool audio = false, video = false, active = false, usable = true; };
// Active tab playing sound, any tab playing sound, the tab that last played sound, active / any tab playing video.
inline uintptr_t pickTarget(const std::vector<Candidate>& tabs, uintptr_t last)
{
    for (const auto& c : tabs) if (c.usable && c.active && c.audio) return c.key;
    for (const auto& c : tabs) if (c.usable && c.audio) return c.key;
    if (last) for (const auto& c : tabs) if (c.usable && c.key == last) return c.key;
    for (const auto& c : tabs) if (c.usable && c.active && c.video) return c.key;
    for (const auto& c : tabs) if (c.usable && c.video) return c.key;
    return 0;
}

// --- the page's answer -------------------------------------------------------------------------------------------
struct Info {
    bool ok = false;
    State state = kNone;
    double position = -1, duration = -1;   // seconds, -1 unknown, duration kLive for streams
    bool hasPrev = false, hasNext = false; // the site has its own previous / next button
    Did did = kDidNothing;
    std::string src, title, artist, docTitle;
};
inline double parseSeconds(const std::string& s)
{
    if (s == "live") return kLive;
    if (s.empty()) return -1;
    char* end = nullptr;
    const double v = std::strtod(s.c_str(), &end);
    return end && *end == 0 && std::isfinite(v) && v >= 0 ? v : -1;
}
// "omni-np1\n<none|playing|paused>\n<pos>\n<dur|live>\n<0|1 prev>\n<0|1 next>\n<did>\n<src>\n<meta title>\n<meta artist>\n<doc title>"
inline Info parse(const std::string& text)
{
    std::vector<std::string> f;
    size_t pos = 0;
    while (f.size() < 12) {
        const size_t nl = text.find('\n', pos);
        f.push_back(text.substr(pos, nl == std::string::npos ? std::string::npos : nl - pos));
        if (nl == std::string::npos) break;
        pos = nl + 1;
    }
    Info i;
    if (f.size() != 11 || f[0] != "omni-np1") return i;
    i.state = f[1] == "playing" ? kPlaying : f[1] == "paused" ? kPaused : kNone;
    i.position = parseSeconds(f[2]);
    i.duration = parseSeconds(f[3]);
    i.hasPrev = f[4] == "1";
    i.hasNext = f[5] == "1";
    const int did = std::atoi(f[6].c_str());
    i.did = did >= kDidNothing && did <= kDidKey ? Did(did) : kDidNothing;
    i.src = f[7].substr(0, kSrcMax);
    i.title = f[8].substr(0, kTextMax);
    i.artist = f[9].substr(0, kTextMax);
    i.docTitle = f[10].substr(0, kTextMax);
    if (i.state == kNone) { i.position = i.duration = -1; i.src.clear(); }
    i.ok = true;
    return i;
}

// --- texts -------------------------------------------------------------------------------------------------------
// At most maxBytes bytes, never cutting a UTF-8 sequence; "..." marks a cut.
inline std::string clip(const std::string& s, size_t maxBytes)
{
    if (s.size() <= maxBytes) return s;
    if (maxBytes < 4) return std::string();
    size_t n = maxBytes - 3;
    while (n > 0 && (static_cast<unsigned char>(s[n]) & 0xC0) == 0x80) --n;
    return s.substr(0, n) + "...";
}
inline std::string trim(const std::string& s)
{
    size_t a = 0, b = s.size();
    while (a < b && (s[a] == ' ' || s[a] == '\t')) ++a;
    while (b > a && (s[b - 1] == ' ' || s[b - 1] == '\t')) --b;
    return s.substr(a, b - a);
}
// "https://user@www.Example.com:8443/x" -> "example.com"; "" for non-http(s).
inline std::string site(const std::string& url)
{
    size_t start;
    if (url.compare(0, 8, "https://") == 0) start = 8;
    else if (url.compare(0, 7, "http://") == 0) start = 7;
    else return std::string();
    size_t end = url.find_first_of("/?#", start);
    if (end == std::string::npos) end = url.size();
    std::string host = url.substr(start, end - start);
    const size_t at = host.rfind('@');
    if (at != std::string::npos) host = host.substr(at + 1);
    if (!host.empty() && host[0] == '[') host = host.substr(0, host.find(']') + 1);
    else host = host.substr(0, host.find(':'));
    for (auto& c : host) if (c >= 'A' && c <= 'Z') c += 'a' - 'A';
    if (host.compare(0, 4, "www.") == 0 && host.size() > 4) host = host.substr(4);
    return host;
}
// 65 -> "1:05", 3723 -> "1:02:03"; "" when unknown.
inline std::string clock(double seconds)
{
    if (!(seconds >= 0) || !std::isfinite(seconds)) return std::string();
    const long long s = static_cast<long long>(seconds);
    char buf[32];
    if (s >= 3600) std::snprintf(buf, sizeof buf, "%lld:%02lld:%02lld", s / 3600, (s / 60) % 60, s % 60);
    else std::snprintf(buf, sizeof buf, "%lld:%02lld", s / 60, s % 60);
    return buf;
}
inline std::string position(const Info& i)
{
    if (!i.ok || i.state == kNone) return std::string();
    if (i.duration == kLive) return i.position >= 0 ? clock(i.position) + " (live)" : std::string("Live");
    const std::string at = clock(i.position);
    if (i.duration > 0) return (at.empty() ? std::string("0:00") : at) + " / " + clock(i.duration);
    return at;
}
inline std::string displayTitle(const Info& i, const std::string& tabTitle)
{
    for (const std::string* s : { &i.title, &i.docTitle, &tabTitle }) {
        const std::string t = trim(*s);
        if (!t.empty()) return t;
    }
    return "Untitled";
}
// The Options tile's value: the tab's title (or site), short.
inline std::string rowValue(const std::string& tabTitle, const std::string& url)
{
    const std::string t = trim(tabTitle);
    return clip(t.empty() || t == "New tab" ? site(url) : t, 34);
}

struct View {
    std::string subtitle, playLabel, position, prevDetail, nextDetail, muteLabel, goLabel;
    bool hasMedia = false, seekable = false;
};
// info: the last answer (answered: one came back). livePlaying: WebKit's current media state for the tab.
inline View view(const Info& info, bool answered, bool livePlaying, const std::string& tabTitle, const std::string& url,
    bool muted, bool isActive, bool privateTab)
{
    View v;
    std::string head = displayTitle(info, tabTitle);
    const std::string artist = trim(info.artist);
    if (!artist.empty()) head += " - " + artist;
    const std::string host = site(url);
    v.subtitle = clip(head, host.empty() ? 96 : 96 - std::min<size_t>(host.size(), 40) - 3);
    if (!host.empty()) v.subtitle += " | " + clip(host, 40);
    if (privateTab) v.subtitle += " (private)";
    v.hasMedia = info.ok && info.state != kNone;
    const bool playing = v.hasMedia ? livePlaying : false;
    v.playLabel = !answered ? "Play / Pause" : playing ? "Pause" : "Play";
    v.position = !answered ? std::string("Reading...") : !info.ok ? std::string("The page didn't answer")
        : !v.hasMedia ? std::string("No video or audio found") : position(info);
    v.seekable = v.hasMedia && (info.duration > 0 || info.duration == kLive);
    v.prevDetail = info.ok && !info.hasPrev ? "Restarts the track; at the start sends the media key" : "";
    v.nextDetail = info.ok && !info.hasNext ? "Sends the media key; some sites ignore it" : "";
    v.muteLabel = muted ? "Unmute tab" : "Mute tab";
    v.goLabel = isActive ? "Back to the page" : "Go to tab";
    return v;
}
// The notice after an answer ("" none).
inline std::string resultNotice(Action a, const Info& i)
{
    if (!i.ok) return a == kProbe ? std::string() : std::string("The page didn't answer");
    if (a == kProbe) return std::string();
    if ((a == kToggle || a == kBack || a == kForward) && i.state == kNone) return "No video or audio found on this page";
    if ((a == kNext || a == kPrev) && i.did == kDidKey)
        return std::string("Sent \"") + (a == kNext ? "Next track" : "Previous track") + "\" to the page; this site may ignore it";
    return std::string();
}

// --- the script --------------------------------------------------------------------------------------------------
// A JavaScript string literal (double quotes) for any UTF-8 bytes: quotes, backslashes, control characters,
// U+2028 / U+2029 and "</" are escaped, so the result is safe anywhere in a script.
inline std::string jsString(const std::string& s)
{
    std::string out = "\"";
    char buf[8];
    for (size_t i = 0; i < s.size(); ++i) {
        const unsigned char c = static_cast<unsigned char>(s[i]);
        switch (c) {
        case '"': out += "\\\""; break;
        case '\\': out += "\\\\"; break;
        case '\n': out += "\\n"; break;
        case '\r': out += "\\r"; break;
        case '\t': out += "\\t"; break;
        case '<': out += "\\x3c"; break;
        default:
            if (c < 0x20 || c == 0x7f) { std::snprintf(buf, sizeof buf, "\\x%02x", c); out += buf; }
            else if (c == 0xE2 && i + 2 < s.size() && static_cast<unsigned char>(s[i + 1]) == 0x80
                && (static_cast<unsigned char>(s[i + 2]) == 0xA8 || static_cast<unsigned char>(s[i + 2]) == 0xA9)) {
                out += static_cast<unsigned char>(s[i + 2]) == 0xA8 ? "\\u2028" : "\\u2029";
                i += 2;
            } else out += char(c);
        }
    }
    return out + "\"";
}

// One evaluate: find the element, act (A), answer in the parse() format. S: the src read when the panel opened.
constexpr const char* kScriptBody = R"JS((function(A,S,D){
var o=[],i,el=null;
function walk(d,k){if(!d||k>3)return;try{var m=d.querySelectorAll('video,audio');for(var a=0;a<m.length;a++)o.push(m[a]);
var f=d.querySelectorAll('iframe,frame');for(var j=0;j<f.length;j++){var c=null;try{c=f[j].contentDocument;}catch(e){}walk(c,k+1);}}catch(e){}}
walk(document,0);
if(S)for(i=0;i<o.length;i++)if(o[i].currentSrc===S){el=o[i];break;}
if(!el)for(i=0;i<o.length;i++)if(!o[i].paused&&!o[i].ended&&o[i].readyState>0){el=o[i];break;}
if(!el){var best=-1;for(i=0;i<o.length;i++){var v=o[i];if(!v.currentSrc&&!v.srcObject)continue;
var sc=(v.currentTime>0?2:0)+(v.readyState>0?1:0);if(sc>best){best=sc;el=v;}}}
function shown(b){try{return !!b&&!b.disabled&&b.getAttribute('aria-disabled')!=='true'&&b.getClientRects().length>0;}catch(e){return false;}}
function pick(l){for(var a=0;a<l.length;a++){var b=null;try{b=document.querySelector(l[a]);}catch(e){}if(shown(b))return b;}return null;}
var nb=pick(['.ytp-next-button','ytmusic-player-bar .next-button','[data-testid="control-button-skip-forward"]','.skipControl__next','button[aria-label^="Next" i]','button[title^="Next" i]']);
var pb=pick(['.ytp-prev-button','ytmusic-player-bar .previous-button','[data-testid="control-button-skip-back"]','.skipControl__previous','button[aria-label^="Previous" i]','button[title^="Previous" i]']);
function key(k,c){var t=document.activeElement||document.body||document;['keydown','keyup'].forEach(function(n){try{t.dispatchEvent(new KeyboardEvent(n,{key:k,code:k,keyCode:c,which:c,bubbles:true,cancelable:true}));}catch(e){}});}
var did=0;
try{
if(A===1&&el){if(el.paused||el.ended){var p=el.play();if(p&&p.catch)p.catch(function(){});}else el.pause();did=1;}
else if(A===2){if(el&&el.currentTime>3&&isFinite(el.duration)){el.currentTime=0;did=1;}else if(pb){pb.click();did=2;}else{key('MediaTrackPrevious',177);did=3;}}
else if(A===3){if(nb){nb.click();did=2;}else{key('MediaTrackNext',176);did=3;}}
else if((A===4||A===5)&&el){var t=el.currentTime+(A===4?-D:D),du=el.duration,sk=el.seekable;
if(isFinite(du))t=Math.min(t,Math.max(0,du-0.5));else if(sk&&sk.length)t=Math.min(Math.max(t,sk.start(0)),sk.end(sk.length-1));
el.currentTime=Math.max(0,t);did=1;}
}catch(e){}
var md=null;try{md=navigator.mediaSession&&navigator.mediaSession.metadata;}catch(e){}
function c(x,l){return String(x==null?'':x).replace(/[\r\n\t]+/g,' ').slice(0,l);}
function n(x){return typeof x==='number'&&isFinite(x)?x.toFixed(1):(x===Infinity?'live':'');}
return ['omni-np1',el?(el.paused||el.ended?'paused':'playing'):'none',el?n(el.currentTime):'',el?n(el.duration):'',
pb?1:0,nb?1:0,did,el?c(el.currentSrc,2000):'',c(md&&md.title,300),c(md&&md.artist,300),c(document.title,300)].join('\n');
}))JS";
inline std::string script(Action a, const std::string& src, int seekSeconds = kSeekSeconds)
{
    return std::string(kScriptBody) + "(" + std::to_string(int(a)) + "," + jsString(src.substr(0, kSrcMax)) + ","
        + std::to_string(seekSeconds) + ")";
}

} // namespace OmniMediaControls
'''

SHELL = r'''// OMNI_MEDIA_CONTROLS_V1: "Now playing" (shell side). Included from OmniFeatures3.h (inside OmniBrowser.cpp's
// anonymous namespace, after OmniHttpsOnlyShell.h). The pure part is OmniMediaControls.h; the reasons are in
// tools/apply_media_controls.py. Main thread only; nothing is written to disk, nothing is injected into pages.
#pragma once

namespace MC = OmniMediaControls;
constexpr int omniNpKind = 7310;          // the panel's OmniFxPanel::kind
static uintptr_t omniNpLast = 0;          // Tab::omniMediaIdentity of the tab that last started sound (memory only)
static uintptr_t omniNpKey = 0;           // the panel's tab
static MC::Info omniNpInfo;               // the last answer from that tab
static bool omniNpAnswered = false;
static uintptr_t omniNpGen = 0;           // answers to older presses are dropped
static MC::Action omniNpAction = MC::kProbe;

static Tab* omniNpTab(uintptr_t key)
{
    if (key) for (auto& t : tabs) if (t->omniMediaIdentity == key) return t.get();
    return nullptr;
}
static unsigned omniNpMedia(const Tab& t)
{
    // UI-process cached state (WebPageProxy::m_mediaState), no IPC.
    return t.page && !t.crashed ? unsigned(WKPageGetMediaState(t.page)) : 0u;
}
static Tab* omniNpTarget()
{
    std::vector<MC::Candidate> c;
    for (auto& t : tabs) {
        const unsigned m = omniNpMedia(*t);
        MC::Candidate k; k.key = t->omniMediaIdentity; k.audio = m & kWKMediaIsPlayingAudio; k.video = m & kWKMediaIsPlayingVideo;
        k.active = t.get() == active(); k.usable = t->page && !t->crashed && t->omniLazyURL.empty();
        c.push_back(k);
    }
    return omniNpTab(MC::pickTarget(c, omniNpLast));
}
static bool omniNpPanelOnTop() { return !omniFxStack.empty() && omniFxStack.back().kind == omniNpKind; }

// ui.isPlayingAudioDidChange (audio or video state changed): remember the tab, relabel an open panel.
static void omniNpMediaChanged(WKPageRef page)
{
    Tab* t = omniTabForPage(page);
    if (!t) return;
    if (omniNpMedia(*t) & kWKMediaIsPlayingAudio) omniNpLast = t->omniMediaIdentity;
    if (omniNpPanelOnTop() && t->omniMediaIdentity == omniNpKey) omniFxRefresh();
}

// One evaluate in the panel's tab: act (or only read) and take the answer.
static void omniNpRun(MC::Action action)
{
    Tab* t = omniNpTab(omniNpKey);
    if (!t || !t->page || t->crashed) { notice("That tab is closed"); omniFxRefresh(); return; }
    omniNpAction = action;
    const uintptr_t gen = ++omniNpGen;
    auto js = adoptWK(WKStringCreateWithUTF8CString(MC::script(action, omniNpInfo.src).c_str()));
    WKPageEvaluateJavaScriptInMainFrame(t->page, js.get(), reinterpret_cast<void*>(gen), [](WKTypeRef result, WKErrorRef error, void* ctx) {
        if (reinterpret_cast<uintptr_t>(ctx) != omniNpGen) return;   // a newer press is on its way
        const MC::Info i = MC::parse(omniFxResultString(result, error));
        const std::string msg = MC::resultNotice(omniNpAction, i);
        if (i.ok || omniNpAction == MC::kProbe) omniNpInfo = i;
        omniNpAnswered = true;
        if (!msg.empty()) notice(msg);
        if (omniNpPanelOnTop()) omniFxRefresh(); else omniShellDirty = true;
    });
}

static void omniNpBuild(OmniFxPanel& p)
{
    Tab* t = omniNpTab(omniNpKey);
    if (!t) {
        p.subtitle = "Nothing is playing";
        OmniFxRow r; r.id = MC::kRowGone; r.label = "The tab was closed"; r.enabled = false; p.rows.push_back(r);
        return;
    }
    const bool live = omniNpMedia(*t) & (kWKMediaIsPlayingAudio | kWKMediaIsPlayingVideo);
    const MC::View v = MC::view(omniNpInfo, omniNpAnswered, live, t->title, t->url, t->omniTaMuted, t == active(), t->omniPrivate);
    p.subtitle = v.subtitle;
    auto add = [&](int id, const std::string& label, bool on, std::string value = {}, std::string detail = {}) {
        OmniFxRow r; r.id = id; r.label = label; r.enabled = on; r.value = std::move(value); r.detail = std::move(detail);
        p.rows.push_back(r);
    };
    add(MC::kRowPlay, v.playLabel, !omniNpAnswered || v.hasMedia, v.position);
    add(MC::kRowPrev, "Previous track", true, {}, v.prevDetail);
    add(MC::kRowNext, "Next track", true, {}, v.nextDetail);
    add(MC::kRowBack, "Back " + std::to_string(MC::kSeekSeconds) + " seconds", v.seekable);
    add(MC::kRowForward, "Forward " + std::to_string(MC::kSeekSeconds) + " seconds", v.seekable);
    OmniFxRow m; m.id = MC::kRowMute; m.label = v.muteLabel; m.icon = t->omniTaMuted ? omniIconSpeakerMuted : omniIconSpeaker;
    p.rows.push_back(m);
    add(MC::kRowGo, v.goLabel, true);
}
static bool omniNpInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    if (!r.enabled) return true;
    Tab* t = omniNpTab(omniNpKey);
    if (!t) return true;
    switch (r.id) {
    case MC::kRowPlay: omniNpRun(MC::kToggle); break;
    case MC::kRowPrev: omniNpRun(MC::kPrev); break;
    case MC::kRowNext: omniNpRun(MC::kNext); break;
    case MC::kRowBack: omniNpRun(MC::kBack); break;
    case MC::kRowForward: omniNpRun(MC::kForward); break;
    case MC::kRowMute: omniTaToggle(*t); omniFxRefresh(); break;   // OMNI_TAB_AUDIO_V1 mute: badge + notice
    case MC::kRowGo:
        for (size_t i = 0; i < tabs.size(); ++i) if (tabs[i].get() == t) {
            omniFxCloseAll();
            if (t != active()) activate(i);
            break;
        }
        break;
    default: break;
    }
    return true;
}
static void omniNpShow()
{
    Tab* t = omniNpTarget();
    if (!t) { notice("Nothing is playing"); return; }
    omniNpKey = t->omniMediaIdentity;
    omniNpInfo = MC::Info(); omniNpAnswered = false;
    OmniFxPanel p;
    p.kind = omniNpKind; p.title = "Now playing"; p.w = 760;
    p.build = omniNpBuild; p.input = omniNpInput;
    p.faces = { { 0, "Choose" }, { 1, "Back" } };
    p.extra = "Controls the playing tab, also in the background";
    omniFxPush(std::move(p));
    omniNpRun(MC::kProbe);   // one read when the panel opens
}

// --- Options (top level): the "Now playing" tile while something plays ---------------------------------------------
static void omniNpQuickRow(OmniFxPanel& p)
{
    Tab* t = omniNpTarget();
    if (!t) return;
    OmniFxRow r; r.id = MC::kQuickRowId; r.label = "Now playing"; r.value = MC::rowValue(t->title, t->url);
    r.icon = t->omniTaMuted ? omniIconSpeakerMuted : omniIconSpeaker;
    p.rows.push_back(r);
}
static bool omniNpQuickInput(const OmniFxRow& r, int)
{
    if (r.id != MC::kQuickRowId) return false;
    omniNpShow();
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniHttpsOnly.h" // OMNI_HTTPS_ONLY_V1: HTTPS-only mode + GPC, https-only.txt (pure)\n',
         '#include "OmniHttpsOnly.h" // OMNI_HTTPS_ONLY_V1: HTTPS-only mode + GPC, https-only.txt (pure)\n'
         '#include "OmniMediaControls.h" // OMNI_MEDIA_CONTROLS_V1: Now playing (pure)\n'),
        ('static void omniSavedMediaChanged(WKPageRef);\n',
         'static void omniSavedMediaChanged(WKPageRef);\n'
         'static void omniNpMediaChanged(WKPageRef page); // OMNI_MEDIA_CONTROLS_V1 (OmniMediaControlsShell.h)\n'),
        ('    ui.isPlayingAudioDidChange = [](WKPageRef page, const void*) { omniSavedMediaChanged(page); };\n',
         '    ui.isPlayingAudioDidChange = [](WKPageRef page, const void*) { omniSavedMediaChanged(page); omniNpMediaChanged(page); }; // OMNI_MEDIA_CONTROLS_V1\n'),
    ],
    'OmniQuickMenu.h': [
        ('enum { omniMqBrowse = 8000, omniMqToggles, omniMqApps, omniMqSettings, omniMqMore, omniMqBlock };\n',
         'enum { omniMqBrowse = 8000, omniMqToggles, omniMqApps, omniMqSettings, omniMqMore, omniMqBlock };\n'
         'static void omniNpQuickRow(OmniFxPanel& p); // OMNI_MEDIA_CONTROLS_V1 (OmniMediaControlsShell.h)\n'
         'static bool omniNpQuickInput(const OmniFxRow& r, int b);\n'),
        ('        for (int i = 0; i < 5; ++i) { OmniFxRow r; r.id = omniMqBrowse + i; r.label = labels[i]; p.rows.push_back(r); }\n',
         '        for (int i = 0; i < 5; ++i) { OmniFxRow r; r.id = omniMqBrowse + i; r.label = labels[i]; p.rows.push_back(r); }\n'
         '        omniNpQuickRow(p); // OMNI_MEDIA_CONTROLS_V1: Now playing, while a tab plays\n'),
        ('    if (r.id == omniMqBlock) { if (omniBlockerSetEnabled(!omniBlockerEnabled()) && active()) WKPageReload(active()->page); return true; }\n',
         '    if (omniNpQuickInput(r, b)) return true; // OMNI_MEDIA_CONTROLS_V1 (before the >= 900 rows)\n'
         '    if (r.id == omniMqBlock) { if (omniBlockerSetEnabled(!omniBlockerEnabled()) && active()) WKPageReload(active()->page); return true; }\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniHttpsOnlyShell.h" // OMNI_HTTPS_ONLY_V1\n',
         '#include "OmniHttpsOnlyShell.h" // OMNI_HTTPS_ONLY_V1\n'
         '#include "OmniMediaControlsShell.h" // OMNI_MEDIA_CONTROLS_V1\n'),
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
    if 'OMNI_TAB_AUDIO_V1' not in (root / 'OmniFeatures.h').read_bytes().decode('utf-8'):
        sys.exit('OmniFeatures.h: OMNI_TAB_AUDIO_V1 missing: apply_tab_audio.py first')
    if 'OMNI_HTTPS_ONLY_V1' not in (root / 'OmniFeatures3.h').read_bytes().decode('utf-8'):
        sys.exit('OmniFeatures3.h: OMNI_HTTPS_ONLY_V1 missing: apply_https_only.py first')
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniMediaControls.h', PURE, 'OmniTabSessions.h'),
            write_new('OmniMediaControlsShell.h', SHELL, 'OmniFeatures.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
