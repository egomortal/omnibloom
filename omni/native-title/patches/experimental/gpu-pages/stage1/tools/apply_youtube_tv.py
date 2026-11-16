#!/usr/bin/env python3
"""OMNI_YOUTUBE_TV_V1 (2026-11-16): YouTube TV mode + an honest " Omni/<version>" user agent.

1. YouTube TV mode (optional, off by default). Browser settings row "YouTube: Normal / TV mode", stored in
   /data/omni/youtube-mode.txt ("tv" or "normal"). When on, a main-frame navigation to a YouTube home page, watch page,
   short, live page or youtu.be link opens YouTube's TV app instead: https://www.youtube.com/tv, the video as
   /tv#/watch?v=ID (start time t= and playlist list= carried over). Pushed-state moves inside the desktop site
   (didSameDocumentNavigation) are caught too. Other YouTube pages (search, channels, settings) open as usual; the TV app
   is never redirected (no loop); Back/Forward and Reload are never redirected.
   The TV app gets a living-room user agent (Cobalt form; see OmniYoutubeTv.h) on www.youtube.com/tv only (tab user-agent
   kind 2); every other page keeps its desktop / mobile-site UA. /data/omni/ua-youtube-tv.txt (first line) replaces it.
   Controller on the TV app: D-pad = arrow keys, Cross = Enter, Circle = Escape (the TV app's Back), sent as key presses
   like the full-screen video keys (omniFullscreenKey). Cross while the pointer leads still clicks at the pointer
   (OMNI_POINTER_CROSS_V1 runs first). The pointer is hidden there until the stick moves it (the D-pad hides it again).
   The web Gamepad API is not fed to the TV app (it would see every press twice with the keys).
   The YouTube guard (OMNI_YT_ATTEST_GUARD_V1) stands down on /tv: it watches /watch pages only, and its fetch/XHR
   wrappers and overlay are not installed on the TV app.
2. Honest user agent: " Omni/<version>" after the built-in Safari-compatible desktop UA and the mobile-site UA (as Edge
   adds "Edg/<version>" after Chrome's), version OMNI_UA_VERSION (OmniYoutubeTv.h, default "0.5.3", -D overrides).
   On by default; Browser settings "Tell sites this is Omni" turns it off (/data/omni/ua-omni-off.flag) for a site that
   breaks. /data/omni/ua-desktop.txt (OMNI_UA_OVERRIDE_V1) still wins and is used exactly as written.

Pure logic (URL mapping, UA strings, key table) in engine/entry/OmniYoutubeTv.h (no SDL, no WebKit), tested by
test_youtube_tv.cpp (g++ -std=c++17 -Wall -Wextra -Werror -I <tree>/engine/entry test_youtube_tv.cpp).
Needs OMNI_UA_OVERRIDE_V1 (apply_ua_override.py) and OMNI_POINTER_CROSS_V1 in the tree.
usage: apply_youtube_tv.py <engine tree>   (writes engine/entry/OmniYoutubeTv.h; edits OmniBrowser.cpp,
       OmniBrowserSettings.h, OmniGamepad.h, OmniYtGuard.h)
"""
import sys
from pathlib import Path

MARK = 'OMNI_YOUTUBE_TV_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

HEADER = r'''// OMNI_YOUTUBE_TV_V1: the pure part (no SDL, no WebKit) of two features:
//  1. YouTube TV mode (Browser settings "YouTube: Normal / TV mode", /data/omni/youtube-mode.txt): YouTube watch and home
//     pages open YouTube's TV app (https://www.youtube.com/tv, the "Leanback" app smart TVs and consoles run) with a TV
//     user agent on that app only; the D-pad, Cross and Circle become the arrow keys, Enter and Escape (Back) there.
//  2. Honest user agent: " Omni/<version>" after the Safari-compatible user agent (as Edge adds "Edg/<version>" after
//     Chrome's), on unless /data/omni/ua-omni-off.flag (Browser settings "Tell sites this is Omni").
// Unit-tested on the host by test_youtube_tv.cpp (written next to apply_youtube_tv.py).
#pragma once
#include <cstddef>
#include <string>

#ifndef OMNI_UA_VERSION
#define OMNI_UA_VERSION "0.5.3" // the Omni release the " Omni/<version>" user-agent token names (-DOMNI_UA_VERSION=... overrides)
#endif

namespace OmniYoutubeTv {

// --- user agents ----------------------------------------------------------------------------------
// The TV app is served only to living-room clients. YouTube's TV clients today are Cobalt (Google's living-room engine:
// Android TV, Fire TV, most smart TVs and set-top boxes; its UA format is fixed by cobalt/browser/user_agent_string.cc:
// "Mozilla/5.0 (<os>) Cobalt/<version>-<config> (unlike Gecko) <js engine> <rasterizer> Starboard/<api>,
// <ODM>_<chipset>_<year>/<firmware> (<brand>, <model>, <connection>)") and the older "Leanback Shell" apps (PS4).
// The default below is that Cobalt form (LTS 23, Starboard 14: a release YouTube still serves) with Omni named as the
// device maker ("Omni_PS5_2020/<version>") so the string stays honest about the browser. A console A/B can replace it
// without a rebuild: /data/omni/ua-youtube-tv.txt (first line, 20..400 printable characters). Known alternative:
//   Mozilla/5.0 (PS4; Leanback Shell) Gecko/20100101 Firefox/65.0 LeanbackShell/01.00.01.75 Sony PS4/ (PS4, , no, CH)
inline std::string tvUserAgent(const std::string& version)
{
    return "Mozilla/5.0 (Linux x86_64; PlayStation 5) Cobalt/23.lts.4.308003-gold (unlike Gecko) v8/8.8.278.17-jit gles "
           "Starboard/14, Omni_PS5_2020/" + version + " (Sony, PS5, Wired)";
}
// A version token is 1..32 of [0-9A-Za-z._-].
inline bool validVersion(const std::string& v)
{
    if (v.empty() || v.size() > 32) return false;
    for (char c : v)
        if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '.' || c == '_' || c == '-')) return false;
    return true;
}
// base + " Omni/<version>" (when on, the version is valid and base doesn't name Omni already).
inline std::string withOmniToken(const std::string& base, const std::string& version, bool on)
{
    if (!on || !validVersion(version) || base.find(" Omni/") != std::string::npos) return base;
    return base + " Omni/" + version;
}
// A user-agent line from a file: trailing newline / spaces dropped; 20..400 printable ASCII characters, else false.
inline bool cleanUaLine(std::string& v)
{
    while (!v.empty() && (v.back() == '\n' || v.back() == '\r' || v.back() == ' ' || v.back() == '\t')) v.pop_back();
    if (v.size() < 20 || v.size() > 400) return false;
    for (char c : v) if (c < 32 || c > 126) return false;
    return true;
}

// --- the setting file -----------------------------------------------------------------------------
// /data/omni/youtube-mode.txt: "tv" (any case, surrounding space ignored) = TV mode; anything else or no file = Normal.
inline bool modeIsTv(const std::string& text)
{
    size_t a = 0, b = text.size();
    while (a < b && (text[a] == ' ' || text[a] == '\t' || text[a] == '\r' || text[a] == '\n')) ++a;
    while (b > a && (text[b - 1] == ' ' || text[b - 1] == '\t' || text[b - 1] == '\r' || text[b - 1] == '\n')) --b;
    if (b - a != 2) return false;
    return (text[a] == 't' || text[a] == 'T') && (text[a + 1] == 'v' || text[a + 1] == 'V');
}

// --- URLs -----------------------------------------------------------------------------------------
struct UrlParts { std::string scheme, host, path, query, fragment; };
inline char lowerChar(char c) { return (c >= 'A' && c <= 'Z') ? char(c - 'A' + 'a') : c; }
// scheme://[user@]host[:port][/path][?query][#fragment]; scheme and host lower-cased. False when there is no "://".
inline bool splitUrl(const std::string& url, UrlParts& p)
{
    p = UrlParts();
    const size_t se = url.find("://");
    if (se == std::string::npos || se == 0) return false;
    for (size_t i = 0; i < se; ++i) p.scheme += lowerChar(url[i]);
    size_t i = se + 3, hostEnd = url.find_first_of("/?#", i);
    if (hostEnd == std::string::npos) hostEnd = url.size();
    std::string auth = url.substr(i, hostEnd - i);
    const size_t at = auth.rfind('@');
    if (at != std::string::npos) auth = auth.substr(at + 1);
    const size_t colon = auth.find(':');
    if (colon != std::string::npos) auth = auth.substr(0, colon);
    for (char c : auth) p.host += lowerChar(c);
    if (!p.host.empty() && p.host.back() == '.') p.host.pop_back();   // "youtube.com." is youtube.com
    i = hostEnd;
    size_t q = url.find_first_of("?#", i);
    if (q == std::string::npos) q = url.size();
    p.path = url.substr(i, q - i);
    if (q < url.size() && url[q] == '?') {
        size_t h = url.find('#', q);
        if (h == std::string::npos) h = url.size();
        p.query = url.substr(q + 1, h - q - 1);
        q = h;
    }
    if (q < url.size() && url[q] == '#') p.fragment = url.substr(q + 1);
    return true;
}
inline bool webScheme(const std::string& s) { return s == "http" || s == "https"; }
// The hosts whose pages TV mode sends to the TV app (and that get the TV user agent on /tv).
inline bool youtubeHost(const std::string& host) { return host == "youtube.com" || host == "www.youtube.com" || host == "m.youtube.com"; }
// The value of name=... in a query string ("" when absent). Values used here need no percent-decoding (checked after).
inline std::string queryValue(const std::string& query, const std::string& name)
{
    size_t i = 0;
    while (i <= query.size()) {
        size_t e = query.find('&', i);
        if (e == std::string::npos) e = query.size();
        const std::string kv = query.substr(i, e - i);
        const size_t eq = kv.find('=');
        if ((eq == std::string::npos ? kv : kv.substr(0, eq)) == name) return eq == std::string::npos ? std::string() : kv.substr(eq + 1);
        i = e + 1;
    }
    return std::string();
}
inline bool idChars(const std::string& v, size_t minLen, size_t maxLen)
{
    if (v.size() < minLen || v.size() > maxLen) return false;
    for (char c : v)
        if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '_' || c == '-')) return false;
    return true;
}
inline bool validVideoId(const std::string& v) { return idChars(v, 11, 11); }   // YouTube video ids: 11 of [A-Za-z0-9_-]
inline bool validListId(const std::string& v) { return idChars(v, 2, 64); }
// A start time: "90", "90s", "1m30s", "1h2m3s" -> seconds; -1 when not one of those (or over 24 h).
inline long startSeconds(const std::string& t)
{
    if (t.empty() || t.size() > 16) return -1;
    long total = 0, n = 0;
    bool digits = false, unitSeen = false;
    for (char c : t) {
        if (c >= '0' && c <= '9') { n = n * 10 + (c - '0'); digits = true; if (n > 86400) return -1; continue; }
        if (!digits) return -1;
        if (c == 'h') total += n * 3600; else if (c == 'm') total += n * 60; else if (c == 's') total += n; else return -1;
        n = 0; digits = false; unitSeen = true;
    }
    if (digits) { if (unitSeen) return -1; total += n; }   // "1m30" is not a form YouTube writes
    return total > 86400 ? -1 : total;
}
// True for YouTube's TV app itself (www.youtube.com/tv, /tv/..., any fragment): the TV user agent and keys apply there.
inline bool isTvUrl(const std::string& url)
{
    UrlParts p;
    if (!splitUrl(url, p) || !webScheme(p.scheme) || !youtubeHost(p.host)) return false;
    return p.path == "/tv" || p.path == "/tv/" || p.path.compare(0, 4, "/tv/") == 0;
}
inline std::string tvWatchUrl(const std::string& id, const std::string& query)
{
    std::string u = "https://www.youtube.com/tv#/watch?v=" + id;
    const long t = startSeconds(queryValue(query, "t"));
    if (t > 0) u += "&t=" + std::to_string(t);
    const std::string list = queryValue(query, "list");
    if (validListId(list)) u += "&list=" + list;
    return u;
}
// Where TV mode sends a main-frame navigation: the TV-app URL for a YouTube home page (/), watch page (/watch?v=ID),
// short (/shorts/ID), live page (/live/ID) or youtu.be/ID link; "" for everything else (other YouTube pages such as
// channels, search and settings open as usual; the TV app itself is never redirected, so there is no loop).
inline std::string tvUrlFor(const std::string& url)
{
    UrlParts p;
    if (!splitUrl(url, p) || !webScheme(p.scheme)) return std::string();
    if (p.host == "youtu.be" || p.host == "www.youtu.be") {
        std::string id = p.path.size() > 1 ? p.path.substr(1) : std::string();
        if (!id.empty() && id.back() == '/') id.pop_back();
        return validVideoId(id) ? tvWatchUrl(id, p.query) : std::string();
    }
    if (!youtubeHost(p.host)) return std::string();
    if (p.path.empty() || p.path == "/") return "https://www.youtube.com/tv";
    if (p.path == "/watch" || p.path == "/watch/") {
        const std::string v = queryValue(p.query, "v");
        return validVideoId(v) ? tvWatchUrl(v, p.query) : std::string();
    }
    for (const char* prefix : { "/shorts/", "/live/" }) {
        const std::string pre(prefix);
        if (p.path.compare(0, pre.size(), pre) != 0) continue;
        std::string id = p.path.substr(pre.size());
        if (!id.empty() && id.back() == '/') id.pop_back();
        return validVideoId(id) ? tvWatchUrl(id, p.query) : std::string();
    }
    return std::string();
}

// --- controller -> keys on the TV app --------------------------------------------------------------
// The TV app is driven by a remote: arrow keys move the focus, Enter selects, Escape (or Backspace) is Back.
// Same keysyms and identifiers the shell already sends to pages (omniFullscreenKey, the on-screen keyboard's Enter).
enum class Pad { Up, Down, Left, Right, Cross, Circle };
struct Key { const char* text; const char* identifier; int keysym; };
inline Key keyFor(Pad p)
{
    switch (p) {
    case Pad::Up: return { nullptr, "Up", 0xff52 };
    case Pad::Down: return { nullptr, "Down", 0xff54 };
    case Pad::Left: return { nullptr, "Left", 0xff51 };
    case Pad::Right: return { nullptr, "Right", 0xff53 };
    case Pad::Cross: return { "\r", "Enter", 0xff0d };
    case Pad::Circle: return { nullptr, "U+001B", 0xff1b };   // Escape: the TV app's Back
    }
    return { nullptr, "", 0 };
}

} // namespace OmniYoutubeTv
'''

GLUE = r'''// OMNI_YOUTUBE_TV_V1 -------------------------------------------------------------------------------
// YouTube TV mode and the " Omni/<version>" user-agent token (pure parts: OmniYoutubeTv.h; apply_youtube_tv.py).
static int omniYtTvMode = -1;      // -1: /data/omni/youtube-mode.txt not read yet
static int omniUaOmniState = -1;   // -1: /data/omni/ua-omni-off.flag not checked yet
static bool omniYtTvOn()
{
    if (omniYtTvMode < 0) {
        std::string text;
        if (FILE* f = fopen("/data/omni/youtube-mode.txt", "r")) { char b[64] = {0}; if (fgets(b, sizeof b, f)) text = b; fclose(f); }
        omniYtTvMode = OmniYoutubeTv::modeIsTv(text) ? 1 : 0;
        fprintf(stderr, "OMNI YTTV: YouTube %s (/data/omni/youtube-mode.txt; OMNI_YOUTUBE_TV_V1)\n", omniYtTvMode ? "TV mode" : "normal");
    }
    return omniYtTvMode == 1;
}
static bool omniUaOmniOn()
{
    if (omniUaOmniState < 0) omniUaOmniState = access("/data/omni/ua-omni-off.flag", F_OK) ? 1 : 0;
    return omniUaOmniState == 1;
}
// The TV app's user agent: /data/omni/ua-youtube-tv.txt (first line) or the built-in living-room one. Read once.
static const std::string& omniUaTv()
{
    static std::string* ua = nullptr;
    if (ua) return *ua;
    ua = new std::string(OmniYoutubeTv::tvUserAgent(OMNI_UA_VERSION));
    if (FILE* f = fopen("/data/omni/ua-youtube-tv.txt", "r")) {
        char line[512] = {0};
        if (fgets(line, sizeof line, f)) {
            std::string v(line);
            if (OmniYoutubeTv::cleanUaLine(v)) *ua = v;
            else fprintf(stderr, "OMNI YTTV: /data/omni/ua-youtube-tv.txt ignored (needs 20-400 printable characters)\n");
        }
        fclose(f);
    }
    fprintf(stderr, "OMNI YTTV: TV app user agent: %s\n", ua->c_str());
    return *ua;
}
// The user agent of a kind: 0 desktop, 1 mobile site, 2 YouTube's TV app.
static std::string omniUaFor(int kind)
{
    if (kind == 2) return omniUaTv();
    const bool token = omniUaOmniOn() && !omniTestMode();   // self-test modes keep the plain strings
    if (kind == 1) return OmniYoutubeTv::withOmniToken(omniMobileUAString, OMNI_UA_VERSION, token);
    const std::string& desktop = omniUaDesktop();   // reads /data/omni/ua-desktop.txt once (OMNI_UA_OVERRIDE_V1)
    return omniUaFromFile ? desktop : OmniYoutubeTv::withOmniToken(desktop, OMNI_UA_VERSION, token);
}
static bool omniYtTvKeysOn(const std::string& url) { return omniYtTvOn() && OmniYoutubeTv::isTvUrl(url); }
static bool omniYtTvKeysActive() { Tab* t = active(); return t && !t->crashed && omniYtTvKeysOn(t->url); }
// The pointer is hidden on the TV app until the stick (or a mouse) moves it; a D-pad press hides it again.
static bool omniYtTvPointerHidden() { return !omniPtrCross.active && omniYtTvKeysActive(); }
static int omniUaKindFor(const std::string& url)
{
    if (omniYtTvKeysOn(url)) return 2;
    return omniMobileHosts.count(omniBlockerHostOf(url)) ? 1 : 0;
}
static void omniUaSet(Tab* tab, int kind)
{
    tab->omniUaKind = kind;
    tab->omniMobileUA = kind == 1;
    auto ua = adoptWK(WKStringCreateWithUTF8CString(omniUaFor(kind).c_str()));
    WKPageSetCustomUserAgent(tab->page, ua.get());
}
// A pushed-state move inside the desktop YouTube site (a video picked from search or a channel) in TV mode: the TV app.
static void omniYtTvSameDocument(Tab& tab, WKPageRef page)
{
    if (omniTestMode() || !omniYtTvOn() || !tab.omniPendingLoad.empty()) return;
    auto url = adoptWK(WKPageCopyActiveURL(page));
    if (!url) return;
    const std::string tv = OmniYoutubeTv::tvUrlFor(OmniTest::toStd(adoptWK(WKURLCopyString(url.get())).get()));
    if (tv.empty()) return;
    fprintf(stderr, "OMNI YTTV: TV mode: %s (same-document)\n", tv.c_str());
    omniApplyUserAgent(&tab, tv);
    tab.omniPendingLoad = tv;
}
static bool omniYtTvSettingsInput(int id, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_DPAD_LEFT && b != SDL_CONTROLLER_BUTTON_DPAD_RIGHT && b != SDL_CONTROLLER_BUTTON_A) return false;
    if (id == omniYtTvRowId) {
        const bool on = !omniYtTvOn();
        if (FILE* f = fopen("/data/omni/youtube-mode.txt", "w")) { fputs(on ? "tv\n" : "normal\n", f); fclose(f); }
        omniYtTvMode = on ? 1 : 0;
        fprintf(stderr, "OMNI YTTV: setting: YouTube %s\n", on ? "TV mode" : "normal");
        notice(on ? "YouTube TV mode: YouTube videos and the home page open in the TV app" : "YouTube: the normal website");
        if (Tab* t = active()) {   // the YouTube page on screen follows the setting at once
            const std::string tv = on ? OmniYoutubeTv::tvUrlFor(t->url) : std::string();
            if (!tv.empty()) navigate(tv);
            else if (!on && OmniYoutubeTv::isTvUrl(t->url)) navigate("https://www.youtube.com/");
        }
        return true;
    }
    const bool on = !omniUaOmniOn();
    if (on) unlink("/data/omni/ua-omni-off.flag");
    else if (FILE* f = fopen("/data/omni/ua-omni-off.flag", "w")) { fputs("1\n", f); fclose(f); }
    omniUaOmniState = on ? 1 : 0;
    for (auto& t : tabs) if (t->omniUaKind != 2) omniUaSet(t.get(), t->omniUaKind);
    fprintf(stderr, "OMNI UA: Omni token %s; desktop user agent now: %s\n", on ? "on" : "off", omniUaFor(0).c_str());
    notice(on ? "Sites see \"Omni\" in the user agent from the next page you open" : "Sites see a plain Safari user agent from the next page you open");
    return true;
}
'''

APPLY_UA_OLD = '''static void omniApplyUserAgent(Tab* tab, const std::string& url)
{
    if (!tab || omniTestMode()) return;
    const bool mobile = omniMobileHosts.count(omniBlockerHostOf(url)) > 0;
    if (mobile == tab->omniMobileUA) return;
    tab->omniMobileUA = mobile;
    auto ua = adoptWK(WKStringCreateWithUTF8CString(mobile ? omniMobileUAString : omniUaDesktop().c_str())); // OMNI_UA_OVERRIDE_V1
    WKPageSetCustomUserAgent(tab->page, ua.get());
}
'''
APPLY_UA_NEW = GLUE + '''static void omniApplyUserAgent(Tab* tab, const std::string& url)
{
    if (!tab || omniTestMode()) return;
    const int kind = omniUaKindFor(url); // OMNI_YOUTUBE_TV_V1: desktop / mobile site / YouTube TV app
    if (kind == tab->omniUaKind) return;
    omniUaSet(tab, kind);
}
'''

BUTTON_FN = '''// OMNI_YOUTUBE_TV_V1: on YouTube's TV app (TV mode) the D-pad, Cross and Circle are the remote's arrows, Enter and Back.
// Cross while the pointer leads still clicks at the pointer (omniPtrCrossRoute runs first); the other buttons keep their
// browser actions (Options quick menu, Create settings, L1 / R1 tabs, Triangle address bar, ...).
static bool omniYtTvButton(int b)
{
    if (!omniYtTvKeysActive()) return false;
    using OmniYoutubeTv::Pad;
    Pad pad;
    switch (b) {
    case SDL_CONTROLLER_BUTTON_DPAD_UP: pad = Pad::Up; break;
    case SDL_CONTROLLER_BUTTON_DPAD_DOWN: pad = Pad::Down; break;
    case SDL_CONTROLLER_BUTTON_DPAD_LEFT: pad = Pad::Left; break;
    case SDL_CONTROLLER_BUTTON_DPAD_RIGHT: pad = Pad::Right; break;
    case SDL_CONTROLLER_BUTTON_A: pad = Pad::Cross; break;
    case SDL_CONTROLLER_BUTTON_B: pad = Pad::Circle; break;
    default: return false;
    }
    const OmniYoutubeTv::Key k = OmniYoutubeTv::keyFor(pad);
    omniFullscreenKey(k.text, k.identifier, k.keysym);
    return true;
}

'''

BROWSER = [
    ('    bool omniPrivate = false, omniMobileUA = false, omniReader = false, omniNewTabPage = false;\n',
     '    bool omniPrivate = false, omniMobileUA = false, omniReader = false, omniNewTabPage = false;\n'
     '    int omniUaKind = 0; // ' + MARK + ': the user agent set on the page: 0 desktop, 1 mobile site, 2 YouTube TV app\n'),
    ('// OMNI_UA_OVERRIDE_V1: the desktop user agent; /data/omni/ua-desktop.txt (first line) replaces the built-in one.\n',
     'static bool omniUaFromFile = false; // ' + MARK + ': /data/omni/ua-desktop.txt gave the desktop UA (used as written)\n'
     '// OMNI_UA_OVERRIDE_V1: the desktop user agent; /data/omni/ua-desktop.txt (first line) replaces the built-in one.\n'),
    ('            if (ok) *ua = v;\n',
     '            if (ok) { *ua = v; omniUaFromFile = true; } // ' + MARK + '\n'),
    ('#include "OmniPointerCross.h" // OMNI_POINTER_CROSS_V1: Cross at the pointer while the pointer leads\n',
     '#include "OmniPointerCross.h" // OMNI_POINTER_CROSS_V1: Cross at the pointer while the pointer leads\n'
     '#include "OmniYoutubeTv.h" // ' + MARK + ': YouTube TV mode + the " Omni/<version>" user agent (pure)\n'
     'static std::string omniUaFor(int kind); // ' + MARK + ': 0 desktop, 1 mobile site, 2 YouTube TV app\n'
     'static bool omniYtTvPointerHidden();\n'
     'static void omniYtTvSameDocument(Tab& tab, WKPageRef page);\n'),
    ('    auto userAgent = adoptWK(WKStringCreateWithUTF8CString(omniUaDesktop().c_str())); // OMNI_UA_OVERRIDE_V1\n',
     '    auto userAgent = adoptWK(WKStringCreateWithUTF8CString(omniUaFor(0).c_str())); // OMNI_UA_OVERRIDE_V1 ' + MARK + ': + " Omni/<version>"\n'),
    ('            omniSavedDocumentChanged(*tab);\n            tab->omniNetRing.newEpoch();',
     '            omniSavedDocumentChanged(*tab);\n            omniYtTvSameDocument(*tab, page); // ' + MARK + ': TV mode follows desktop YouTube\'s pushed-state moves\n'
     '            tab->omniNetRing.newEpoch();'),
    ('static void omniDrawPointer()\n{\n',
     'static void omniDrawPointer()\n{\n'
     '    if (omniYtTvPointerHidden()) return; // ' + MARK + ': the TV app is driven by the D-pad\n'),
    (APPLY_UA_OLD, APPLY_UA_NEW),
    ('''            const bool mobile = omniMobileHosts.count(omniBlockerHostOf(targetURL)) > 0;
            if (omniWebURL(targetURL) && mobile != tab->omniMobileUA) {
''',
     '''            // OMNI_YOUTUBE_TV_V1: TV mode opens YouTube's home / watch pages in the TV app (never Back/Forward or Reload)
            if (omniWebURL(targetURL) && omniYtTvOn()) {
                const std::string tv = OmniYoutubeTv::tvUrlFor(targetURL);
                const std::string method = request ? OmniTest::toStd(adoptWK(WKURLRequestCopyHTTPMethod(request.get())).get()) : std::string();
                const WKFrameNavigationType type = WKNavigationActionGetNavigationType(action);
                if (!tv.empty() && (method.empty() || method == "GET") && type != kWKFrameNavigationTypeBackForward && type != kWKFrameNavigationTypeReload) {
                    fprintf(stderr, "OMNI YTTV: TV mode: %s -> %s\\n", targetURL.c_str(), tv.c_str());
                    omniApplyUserAgent(tab, tv);
                    WKFramePolicyListenerIgnore(listener);
                    tab->omniPendingLoad = tv;
                    return;
                }
            }
            if (omniWebURL(targetURL) && omniUaKindFor(targetURL) != tab->omniUaKind) { // OMNI_YOUTUBE_TV_V1: was desktop / mobile only
'''),
    ('    if (!sprite) return { 0, 0, 0, 0 };\n',
     '    if (!sprite) return { 0, 0, 0, 0 };\n'
     '    if (omniYtTvPointerHidden()) return { 0, 0, 0, 0 }; // ' + MARK + ': hidden (its old rows are redrawn)\n'),
    ('void button(int button)\n{\n', BUTTON_FN + 'void button(int button)\n{\n'),
    ('    if (pageFullscreen && active()) {\n        if (button == SDL_CONTROLLER_BUTTON_A) click();\n',
     '    if (!editing && !settingsOpen && omniYtTvButton(button)) return; // ' + MARK + ': arrows / Enter / Back on the TV app\n'
     '    if (pageFullscreen && active()) {\n        if (button == SDL_CONTROLLER_BUTTON_A) click();\n'),
]

SETTINGS = [
    ('constexpr int omniSlRowId = 850;\n',
     'constexpr int omniSlRowId = 850;\n'
     '// ' + MARK + ': "YouTube: Normal / TV mode" and "Tell sites this is Omni" (OmniBrowser.cpp)\n'
     'constexpr int omniYtTvRowId = 860, omniUaOmniRowId = 861;\n'
     'static bool omniYtTvOn();\n'
     'static bool omniUaOmniOn();\n'
     'static bool omniYtTvSettingsInput(int id, int b);\n'),
    ('    add(omniFxSetGamepad, "Web pages can use the controller", omniGamepadEnabled() ? "On" : "Off", true); // OMNI_GAMEPAD_V1\n',
     '    add(omniFxSetGamepad, "Web pages can use the controller", omniGamepadEnabled() ? "On" : "Off", true); // OMNI_GAMEPAD_V1\n'
     '    add(omniYtTvRowId, "YouTube", omniYtTvOn() ? "TV mode" : "Normal", true); // ' + MARK + '\n'
     '    add(omniUaOmniRowId, "Tell sites this is Omni", omniUaOmniOn() ? "On" : "Off", true); // ' + MARK + ': " Omni/<version>" in the user agent\n'),
    ('    if (r.id == omniSlRowId) return omniSlSettingsInput(b); // OMNI_SEND_LINK_V1\n',
     '    if (r.id == omniSlRowId) return omniSlSettingsInput(b); // OMNI_SEND_LINK_V1\n'
     '    if (r.id == omniYtTvRowId || r.id == omniUaOmniRowId) return omniYtTvSettingsInput(r.id, b); // ' + MARK + '\n'),
]

GAMEPAD = [
    ('static bool omniMcOrigin(const std::string& url); // OMNI_PAD_CONTROLLER_V1 (below)\n',
     'static bool omniMcOrigin(const std::string& url); // OMNI_PAD_CONTROLLER_V1 (below)\n'
     'static bool omniYtTvKeysOn(const std::string& url); // ' + MARK + ' (OmniBrowser.cpp)\n'),
    ('    if (omniGamepadEnabled() && tab && focused && !omniUiOpen && !tab->crashed && !omniMcOrigin(tab->url))\n',
     '    if (omniGamepadEnabled() && tab && focused && !omniUiOpen && !tab->crashed && !omniMcOrigin(tab->url)\n'
     '        && !omniYtTvKeysOn(tab->url)) // ' + MARK + ': the TV app gets the pad as keys only (else every press twice)\n'),
]

GUARD = [
    ("if(!/(^|\\.)youtube\\.com$/.test(location.hostname))return;\n",
     "if(!/(^|\\.)youtube\\.com$/.test(location.hostname))return;\n"
     "if(/^\\/tv(\\/|$)/.test(location.pathname))return;   // " + MARK + ": the TV app (YouTube TV mode) is left alone\n"),
]

FILES = (('OmniBrowser.cpp', BROWSER), ('OmniBrowserSettings.h', SETTINGS), ('OmniGamepad.h', GAMEPAD), ('OmniYtGuard.h', GUARD))


def patch(name, edits):
    p = root / name
    raw = p.read_bytes()
    nl = '\r\n' if b'\r\n' in raw else '\n'
    s = raw.decode('utf-8')
    if MARK in s:
        return name + ': already', nl
    for old0, new0 in edits:
        # files with mixed endings (lines added by earlier patches): the anchor's own line ending decides
        for e in (nl, '\n' if nl == '\r\n' else '\r\n'):
            old, new = old0.replace('\n', e), new0.replace('\n', e)
            if s.count(old):
                break
        n = s.count(old)
        if n != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, n, old0[:90]))
        s = s.replace(old, new, 1)
    p.write_bytes(s.encode('utf-8'))
    return name + ': applied', nl


def main():
    b = (root / 'OmniBrowser.cpp').read_text(encoding='utf-8')
    if MARK not in b:
        if 'OMNI_UA_OVERRIDE_V1' not in b:
            sys.exit('OmniBrowser.cpp: OMNI_UA_OVERRIDE_V1 missing: apply_ua_override.py first')
        if 'OmniPointerCross.h' not in b:
            sys.exit('OmniBrowser.cpp: OMNI_POINTER_CROSS_V1 missing')
    for name, edits in FILES:   # check every anchor before writing anything
        s = (root / name).read_text(encoding='utf-8').replace('\r\n', '\n')
        if MARK in s:
            continue
        for old, _ in edits:
            if s.count(old) != 1:
                sys.exit('%s: anchor not found exactly once (%d): %r' % (name, s.count(old), old[:90]))
    nl = '\n'
    for name, edits in FILES:
        msg, e = patch(name, edits)
        if name == 'OmniBrowser.cpp':
            nl = e
        print(msg)
    h = root / 'OmniYoutubeTv.h'
    data = HEADER.replace('\n', nl).encode('utf-8')
    if not h.exists() or h.read_bytes() != data:
        h.write_bytes(data)
        print('OmniYoutubeTv.h: written')
    else:
        print('OmniYoutubeTv.h: already')
    print('applied ' + MARK)


main()
