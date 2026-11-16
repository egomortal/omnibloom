#!/usr/bin/env python3
"""OMNI_WEB_APPS_V1 (2026-11-16): "Open as app" and Apps on the start page.

What existed (studied first)
  - The start page's "Your apps" section (omni://pages/start/, pages bundle start/app.js) lists Bloom Core's local apps
    (window.omnibloomHost.getApps / openApp, OmniHub::liveApps): not web sites. Pinned + Recent sites are links that
    open in the same tab with the full browser chrome. OMNI_START_CUSTOM_V1 orders / hides the sections ("apps" =
    the whole "Your apps" section) and shows how Omni hands a start page its data: ONE fixed script after load.
  - Bars: pageFullscreen (a WebKit fullscreen element: the view gets the whole display, every browser button is a
    video key) and OMNI_VIDEO_IMMERSIVE_V1 (a video filling the view keeps the auto-hidden bars away). Auto-hide
    (omniAutoHideActive) gives the page the full height and draws the bars over it, so hiding / showing never resizes
    the view; omniStyleTick decides omniChromeWanted once per pass.
  - Tab flags live outside struct Tab where they can (pinned tabs: a set of Tab pointers forgotten in
    omniFxTabClosing). tab->omniMediaSection is the Downloads ("Media") tab: never pinned, never an app here.
  - Web app manifests: Omni never read <link rel=manifest> (no code anywhere). Reading one is cheap with a page script
    (fetch of the manifest by the page itself, 2.5 s), so it is used when present; title + icon links otherwise.

What this adds
  - Hold-Cross page menu (web pages, not private tabs, not the Downloads tab):
      "Open as app"     this tab becomes an app tab (on an app tab: "Leave app mode")
      "Add to Apps"     saves the site to Apps (value "In Apps" when its site is already there, "Full (12)")
    Both read the page first (one async page script, OmniWebApps::pageScript; native timeout 4 s, then the page's
    address + tab title are used): manifest name / short_name, start_url (only when it is the page's own origin,
    else the page's address), the largest icon, theme_color; without a manifest: <title>, the largest
    <link rel=icon / apple-touch-icon>, <meta name=theme-color>. Everything is checked in the pure part.
  - An app tab is a normal tab with an app flag (OmniWebAppsShell.h, omniWapTabs; private tabs never are):
      * no address bar / tab strip / bottom bar: while an app tab is shown, the layout is Auto-hide's (full-height page)
        with the bars kept hidden (omniWapOn); they only come back while typing (keyboard) or in settings. Nothing
        else brings them back: not the stick, not buttons.
      * Options opens the app menu instead of the quick menu: Back, Home (the app's start address), Reload,
        Browser menu (the usual quick menu: tabs, settings, ...), Leave app mode, Close app.
      * Tabs panel: "App" after the row's value. Circle is still Back, L1 / R1 still switch tabs (leaving the app's
        layout while another tab is shown).
  - Start page: inside "Your apps", a "Web apps" row of up to 12 tiles (colour from theme_color, first letter, name,
    host) drawn by the pages bundle's start-webapps.js; Cross on a tile opens the app (the start page's own tab turns
    into the app; a private start page opens it in a new normal tab; an app already open is switched to). "Manage"
    opens the panel below. Icons are stored but not drawn: the start page's CSP allows only 'self' and data: images.
  - Browser settings: "Apps on start page..." (value "3 of 12") after "Customise start page...": the list;
    Cross opens, Square removes (asks), Triangle moves up.
  - /data/omni/apps.json: {"v":1,"apps":[{"id","name","url","icon","theme"}]} through omniIoQueue, read once on first
    use; only names, addresses, an icon address and a colour (never cookies, history or page data). At most 12.
  - Bridge (OmniPages.h request()): "webapps.open" (params.url = the app id), "webapps.manage"; only from a start
    page, done on the next tick, only for the active tab.

Files
  new  OmniWebApps.h        pure: URLs / origins, apps.json parse / serialize, caps, manifest-answer validation,
                            the page script, start-page JSON, texts  (tests: tools/test_web_apps.cpp,
                            tools/test_web_apps_js.cjs)
  new  OmniWebAppsShell.h   app tabs, page query, menu rows, app menu, Apps panel, start-page data + bridge, tick
  OmniBrowser.cpp       after the OmniStartCustom.h include: the pure include; the omniAutoHideActive() line is replaced
                        (omniWapOn + "(omniAutoHide || omniWapOn)"); after the OMNI_VIDEO_IMMERSIVE_V1 line of
                        omniStyleTick: bars kept hidden; after omniScuFinished / omniScuActivated: ours; before
                        Options' quick-menu line in button(): the app menu
  OmniFeatures3Decl.h   after "static bool omniPtStripClick(int x);": declarations
  OmniFeatures3.h       after the OmniStartCustomShell.h include: the shell; after omniScuTick(now): omniWapTick(now)
  OmniTabsPage.h        after omniPtForget(&tab): omniWapForget; after omniPtTabRow(...): omniWapTabRow
  OmniContextMenu.h     after omniPtContextRows(p): rows; after the omniPtContextAction line: actions
  OmniBrowserSettings.h after the "Customise start page..." row: ours; before its input line: ours
  OmniPages.h           before the "start." methods line: the "webapps." methods
  Pages bundle (repo, not this script): omnibloom/omni/pages/bundle-clean4/start/{index.html,start-webapps.js,
                        start-webapps.css}
Ids (unused): page-menu rows 980 / 981 (pinned 960, QR 975), Browser settings row 876, panel kinds 7490 / 7491.
Namespace alias OWAP. Each anchor exactly once, CRLF / LF kept per file, idempotent (MARK per file).
Apply after apply_start_custom.py (and so after pinned tabs, QR share, tab groups, popup notice, site clear).
r2 (REV = OMNI_WEB_APPS_V1_R2): an apps.json that does not parse is renamed to apps.json.bad-<unix time> (at most 3
  kept, the oldest deleted) and the list starts empty, with one log line; nothing is written until the user adds,
  removes or moves an app (omniWapSave's only callers), so a broken file is never silently replaced. Only the two
  headers change; a tree patched by r1 gets them rewritten (write_new), the anchored edits are untouched: the result
  is byte-identical to a fresh apply.
usage: apply_web_apps.py <engine tree>
"""
import sys
from pathlib import Path

MARK = 'OMNI_WEB_APPS_V1'
REV = 'OMNI_WEB_APPS_V1_R2'   # r2: a broken apps.json is kept as apps.json.bad-<time> (at most 3); in the headers only
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_WEB_APPS_V1: "Open as app" and Apps on the start page, the pure part (no SDL, no WebKit).
// /data/omni/apps.json (written through omniIoQueue, read once on first use, <= 64 KB, at most 12 apps):
//   {"v":1,"apps":[{"id":"a0123456789ab","name":"YouTube","url":"https://www.youtube.com/tv","icon":"https://...","theme":"#ff0000"}]}
// Only a name, the start address, an icon address and a colour: never cookies, history or page data.
// The shell side is OmniWebAppsShell.h; the reasons are in tools/apply_web_apps.py. Tests: tools/test_web_apps.cpp.
// OMNI_WEB_APPS_V1_R2: a file that does not parse is kept as apps.json.bad-<unix time> (badName / badToDrop).
#pragma once
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <string>
#include <utility>
#include <vector>

namespace OmniWebApps {

constexpr const char* kFileName = "apps.json";
constexpr size_t kMaxApps = 12, kMaxFile = 64 * 1024, kNameMax = 40, kUrlMax = 2048, kAnswerMax = 16 * 1024;
constexpr int kSettingsRowId = 876;               // Browser settings row (start custom 875, autoplay 880)
constexpr int kPanelKind = 7490, kMenuKind = 7491;
constexpr int kContextOpen = 980, kContextAdd = 981;   // hold-Cross page menu rows (pinned 960, QR 975)
constexpr uint32_t kQueryMs = 4000;               // the page query's native timeout (the page script gives up at 3 s)
constexpr const char* kStartPrefix = "omni://pages/start/";

inline bool expired(uint32_t startedAt, uint32_t now) { return uint32_t(now - startedAt) >= kQueryMs; }
inline char lower(char c) { return c >= 'A' && c <= 'Z' ? char(c + ('a' - 'A')) : c; }

struct App { std::string id, name, url, icon, theme; };

// --- addresses ---------------------------------------------------------------------------------------------------
struct Origin {
    bool ok = false, https = false;
    std::string host;   // lower case, IPv6 without brackets
    int port = 0;       // the effective port (443 / 80 when none is written)
    std::string text;   // "https://www.example.com" (port only when not the default)
};
// http(s) only; an address with user info ("user@host") is refused (navigation.open refuses it too).
inline Origin originOf(const std::string& url)
{
    Origin o;
    size_t p;
    auto starts = [&](const char* s) { size_t i = 0; for (; s[i]; ++i) if (i >= url.size() || lower(url[i]) != s[i]) return false; return true; };
    if (starts("https://")) { o.https = true; p = 8; }
    else if (starts("http://")) p = 7;
    else return o;
    size_t end = url.find_first_of("/?#", p);
    if (end == std::string::npos) end = url.size();
    const std::string auth = url.substr(p, end - p);
    if (auth.empty() || auth.find('@') != std::string::npos) return o;
    std::string host, port;
    bool v6 = false;
    if (auth[0] == '[') {
        const size_t close = auth.find(']');
        if (close == std::string::npos) return o;
        host = auth.substr(1, close - 1);
        v6 = true;
        if (close + 1 < auth.size()) { if (auth[close + 1] != ':') return o; port = auth.substr(close + 2); }
    } else {
        const size_t colon = auth.find(':');
        host = auth.substr(0, colon);
        if (colon != std::string::npos) port = auth.substr(colon + 1);
    }
    for (auto& c : host) c = lower(c);
    while (!host.empty() && host.back() == '.') host.pop_back();
    if (host.empty() || host.size() > 253) return o;
    for (char c : host) {
        const bool good = (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '.' || c == '-' || c == '_' || (v6 && c == ':');
        if (!good) return o;
    }
    o.port = o.https ? 443 : 80;
    if (!port.empty()) {
        if (port.size() > 5) return o;
        int v = 0;
        for (char c : port) { if (c < '0' || c > '9') return o; v = v * 10 + (c - '0'); }
        if (v < 1 || v > 65535) return o;
        o.port = v;
    }
    o.host = host;
    o.text = std::string(o.https ? "https://" : "http://") + (v6 ? "[" + host + "]" : host);
    if (o.port != (o.https ? 443 : 80)) o.text += ":" + std::to_string(o.port);
    o.ok = true;
    return o;
}
inline std::string noFragment(const std::string& url) { return url.substr(0, url.find('#')); }
// An address an app may start at / an icon may come from: http(s), a valid origin, <= 2 KB, printable ASCII without
// spaces, quotes, angle brackets, backslashes or backticks (what URL.href gives for any real address).
inline bool validWebUrl(const std::string& u)
{
    if (u.empty() || u.size() > kUrlMax) return false;
    for (unsigned char c : u) if (c <= 0x20 || c >= 0x7f || c == '"' || c == '<' || c == '>' || c == '\\' || c == '`') return false;
    return originOf(u).ok;
}
inline bool sameOrigin(const std::string& a, const std::string& b)
{
    const Origin x = originOf(a), y = originOf(b);
    return x.ok && y.ok && x.text == y.text;
}
// "youtube.com" from "https://www.YouTube.com:443/tv" (lower case, no "www.").
inline std::string shownHost(const std::string& url)
{
    const Origin o = originOf(url);
    if (!o.ok) return std::string();
    return o.host.compare(0, 4, "www.") == 0 && o.host.size() > 4 ? o.host.substr(4) : o.host;
}

// --- texts and colours --------------------------------------------------------------------------------------------
// Control characters become spaces, runs of white space one space, trimmed, cut at `max` bytes on a UTF-8 boundary.
inline std::string cleanText(const std::string& s, size_t max)
{
    std::string o;
    bool space = false;
    for (unsigned char c : s) {
        if (c < 0x20 || c == 0x7f || c == ' ') { space = !o.empty(); continue; }
        if (space) { o += ' '; space = false; }
        o += char(c);
    }
    if (o.size() <= max) return o;
    size_t n = max;
    while (n && (static_cast<unsigned char>(o[n]) & 0xc0) == 0x80) --n;
    o.resize(n);
    while (!o.empty() && o.back() == ' ') o.pop_back();
    return o;
}
inline int hexValue(char c) { return c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1; }
// "#abc" / "#aabbcc" (any case, spaces around) -> "#aabbcc"; anything else "".
inline std::string validTheme(const std::string& s0)
{
    const std::string s = cleanText(s0, 16);
    if (s.size() != 4 && s.size() != 7) return std::string();
    if (s[0] != '#') return std::string();
    for (size_t i = 1; i < s.size(); ++i) if (hexValue(s[i]) < 0) return std::string();
    std::string o = "#";
    for (size_t i = 1; i < s.size(); ++i) { o += lower(s[i]); if (s.size() == 4) o += lower(s[i]); }
    return o;
}
// Text colour on a tile of colour `hex` (#rrggbb): dark on light colours.
inline std::string inkFor(const std::string& hex)
{
    if (hex.size() != 7) return "#ffffff";
    const int r = hexValue(hex[1]) * 16 + hexValue(hex[2]), g = hexValue(hex[3]) * 16 + hexValue(hex[4]), b = hexValue(hex[5]) * 16 + hexValue(hex[6]);
    return (r * 299 + g * 587 + b * 114) / 1000 >= 150 ? "#111111" : "#ffffff";
}
inline uint64_t fnv(const std::string& s, uint64_t h = 1469598103934665603ULL)
{
    for (unsigned char c : s) { h ^= c; h *= 1099511628211ULL; }
    return h;
}
// A tile colour for an app without theme_color (stable per id).
inline std::string fallbackColour(const std::string& id)
{
    static const char* const k[8] = { "#107c10", "#0e5a8a", "#5c2d91", "#a4262c", "#2d6a4f", "#8a4b08", "#1f4e79", "#3a3a3a" };
    return k[fnv(id) % 8];
}
// The first character of the name (ASCII letters upper case), "?" for none.
inline std::string letter(const std::string& name)
{
    const std::string s = cleanText(name, 200);
    if (s.empty()) return "?";
    const unsigned char c = static_cast<unsigned char>(s[0]);
    if (c < 0x80) return std::string(1, c >= 'a' && c <= 'z' ? char(c - 'a' + 'A') : char(c));
    size_t n = (c & 0xe0) == 0xc0 ? 2 : (c & 0xf0) == 0xe0 ? 3 : (c & 0xf8) == 0xf0 ? 4 : 1;
    if (n > s.size()) return "?";
    for (size_t i = 1; i < n; ++i) if ((static_cast<unsigned char>(s[i]) & 0xc0) != 0x80) return "?";
    return n == 1 ? std::string("?") : s.substr(0, n);
}

// --- ids ------------------------------------------------------------------------------------------------------------
inline bool validId(const std::string& id)
{
    if (id.size() != 13 || id[0] != 'a') return false;
    for (size_t i = 1; i < id.size(); ++i) if (!((id[i] >= '0' && id[i] <= '9') || (id[i] >= 'a' && id[i] <= 'f'))) return false;
    return true;
}
inline int find(const std::vector<App>& apps, const std::string& id)
{
    for (size_t i = 0; i < apps.size(); ++i) if (apps[i].id == id) return int(i);
    return -1;
}
inline int findUrl(const std::vector<App>& apps, const std::string& url)
{
    const std::string u = noFragment(url);
    for (size_t i = 0; i < apps.size(); ++i) if (apps[i].url == u) return int(i);
    return -1;
}
// An app of the same site (origin) as `url`, -1 none.
inline int findOrigin(const std::vector<App>& apps, const std::string& url)
{
    for (size_t i = 0; i < apps.size(); ++i) if (sameOrigin(apps[i].url, url)) return int(i);
    return -1;
}
// "a" + 12 hex digits from the start address; another hash when the list already has it for another app.
inline std::string makeId(const std::string& url, const std::vector<App>& apps)
{
    for (uint64_t salt = 0; salt < 64; ++salt) {
        char b[16];
        snprintf(b, sizeof b, "a%012llx", (unsigned long long)(fnv(url, 1469598103934665603ULL ^ (salt * 0x9e3779b97f4a7c15ULL)) & 0xffffffffffffULL));
        if (find(apps, b) < 0) return b;
    }
    return std::string();
}

// --- JSON (apps.json and the page's answer) ------------------------------------------------------------------------
struct Json {
    enum T { tNull, tBool, tNum, tStr, tArr, tObj } t = tNull;
    bool b = false;
    double n = 0;
    std::string s;
    std::vector<Json> a;
    std::map<std::string, Json> o;
    const Json* get(const char* k) const { auto it = o.find(k); return t == tObj && it != o.end() ? &it->second : nullptr; }
    std::string str(const char* k) const { const Json* v = get(k); return v && v->t == tStr ? v->s : std::string(); }
};
inline void putUtf8(std::string& o, unsigned cp)
{
    if (cp < 0x80) o += char(cp);
    else if (cp < 0x800) { o += char(0xc0 | (cp >> 6)); o += char(0x80 | (cp & 0x3f)); }
    else if (cp < 0x10000) { o += char(0xe0 | (cp >> 12)); o += char(0x80 | ((cp >> 6) & 0x3f)); o += char(0x80 | (cp & 0x3f)); }
    else { o += char(0xf0 | (cp >> 18)); o += char(0x80 | ((cp >> 12) & 0x3f)); o += char(0x80 | ((cp >> 6) & 0x3f)); o += char(0x80 | (cp & 0x3f)); }
}
struct Parser {
    const std::string& s;
    size_t i = 0;
    int depth = 0;
    void ws() { while (i < s.size() && (s[i] == ' ' || s[i] == '\t' || s[i] == '\n' || s[i] == '\r')) ++i; }
    bool hex4(unsigned& v)
    {
        if (i + 4 > s.size()) return false;
        v = 0;
        for (int k = 0; k < 4; ++k) { const int h = hexValue(s[i++]); if (h < 0) return false; v = v * 16 + unsigned(h); }
        return true;
    }
    bool str(std::string& out)
    {
        out.clear();
        if (i >= s.size() || s[i] != '"') return false;
        for (++i; i < s.size();) {
            const char c = s[i++];
            if (c == '"') return true;
            if (static_cast<unsigned char>(c) < 0x20) return false;
            if (c != '\\') { out += c; continue; }
            if (i >= s.size()) return false;
            const char e = s[i++];
            switch (e) {
            case '"': out += '"'; break; case '\\': out += '\\'; break; case '/': out += '/'; break;
            case 'b': out += '\b'; break; case 'f': out += '\f'; break; case 'n': out += '\n'; break;
            case 'r': out += '\r'; break; case 't': out += '\t'; break;
            case 'u': {
                unsigned cp;
                if (!hex4(cp)) return false;
                if (cp >= 0xd800 && cp < 0xdc00) {
                    unsigned lo;
                    if (i + 1 < s.size() && s[i] == '\\' && s[i + 1] == 'u') {
                        i += 2;
                        if (!hex4(lo)) return false;
                        cp = lo >= 0xdc00 && lo < 0xe000 ? 0x10000 + ((cp - 0xd800) << 10) + (lo - 0xdc00) : 0xfffd;
                    } else cp = 0xfffd;
                } else if (cp >= 0xdc00 && cp < 0xe000) cp = 0xfffd;
                putUtf8(out, cp);
                break;
            }
            default: return false;
            }
        }
        return false;
    }
    bool value(Json& v)
    {
        ws();
        if (i >= s.size() || ++depth > 8) return false;
        bool ok = false;
        const char c = s[i];
        if (c == '{') {
            v.t = Json::tObj; ++i; ws();
            if (i < s.size() && s[i] == '}') { ++i; ok = true; }
            else for (;;) {
                std::string k; Json x;
                ws();
                if (!str(k)) break;
                ws();
                if (i >= s.size() || s[i] != ':') break;
                ++i;
                if (!value(x)) break;
                if (v.o.size() < 64) v.o[k] = std::move(x);
                ws();
                if (i < s.size() && s[i] == ',') { ++i; continue; }
                if (i < s.size() && s[i] == '}') { ++i; ok = true; }
                break;
            }
        } else if (c == '[') {
            v.t = Json::tArr; ++i; ws();
            if (i < s.size() && s[i] == ']') { ++i; ok = true; }
            else for (;;) {
                Json x;
                if (!value(x)) break;
                if (v.a.size() < 64) v.a.push_back(std::move(x));
                ws();
                if (i < s.size() && s[i] == ',') { ++i; continue; }
                if (i < s.size() && s[i] == ']') { ++i; ok = true; }
                break;
            }
        } else if (c == '"') { v.t = Json::tStr; ok = str(v.s); }
        else if (s.compare(i, 4, "true") == 0) { v.t = Json::tBool; v.b = true; i += 4; ok = true; }
        else if (s.compare(i, 5, "false") == 0) { v.t = Json::tBool; i += 5; ok = true; }
        else if (s.compare(i, 4, "null") == 0) { i += 4; ok = true; }
        else if (c == '-' || (c >= '0' && c <= '9')) {
            const char* b = s.c_str() + i;
            char* e = nullptr;
            v.n = strtod(b, &e);
            if (e != b) { v.t = Json::tNum; i += size_t(e - b); ok = v.n == v.n && v.n < 1e300 && v.n > -1e300; }
        }
        --depth;
        return ok;
    }
};
inline bool parseJson(const std::string& text, Json& out, size_t max)
{
    if (text.size() > max) return false;
    Parser p { text };
    if (!p.value(out)) return false;
    p.ws();
    return p.i == text.size();
}
// A JSON string literal that is also safe inside JavaScript source and HTML (U+2028 / U+2029, '<' escaped).
inline std::string quote(const std::string& s)
{
    std::string o = "\"";
    for (size_t i = 0; i < s.size(); ++i) {
        const unsigned char c = static_cast<unsigned char>(s[i]);
        if (c == '"' || c == '\\') { o += '\\'; o += char(c); }
        else if (c < 0x20 || c == 0x7f) { char b[8]; snprintf(b, sizeof b, "\\u%04x", c); o += b; }
        else if (c == 0xe2 && i + 2 < s.size() && static_cast<unsigned char>(s[i + 1]) == 0x80
                 && (static_cast<unsigned char>(s[i + 2]) == 0xa8 || static_cast<unsigned char>(s[i + 2]) == 0xa9)) {
            o += static_cast<unsigned char>(s[i + 2]) == 0xa8 ? "\\u2028" : "\\u2029";
            i += 2;
        } else if (c == '<') o += "\\u003c";
        else o += char(c);
    }
    return o + "\"";
}

// --- apps.json ------------------------------------------------------------------------------------------------------
// One entry -> an App ("" url: unusable). The name falls back to the host; a bad id gets a new one later.
inline App checked(const App& in)
{
    App a;
    a.url = validWebUrl(in.url) ? noFragment(in.url) : std::string();
    if (a.url.empty()) return a;
    a.id = validId(in.id) ? in.id : std::string();
    a.name = cleanText(in.name, kNameMax);
    if (a.name.empty()) a.name = shownHost(a.url);
    a.icon = validWebUrl(in.icon) ? in.icon : std::string();
    a.theme = validTheme(in.theme);
    return a;
}
// The file -> the list (false: missing / broken file, the list is empty). Unknown fields are ignored; entries with a
// bad address are dropped; a repeated address or id keeps the first; at most kMaxApps.
inline bool parse(const std::string& text, std::vector<App>& apps)
{
    apps.clear();
    Json j;
    if (!parseJson(text, j, kMaxFile) || j.t != Json::tObj) return false;
    const Json* list = j.get("apps");
    if (!list || list->t != Json::tArr) return true;
    for (const Json& e : list->a) {
        if (apps.size() >= kMaxApps) break;
        if (e.t != Json::tObj) continue;
        App a = checked({ e.str("id"), e.str("name"), e.str("url"), e.str("icon"), e.str("theme") });
        if (a.url.empty() || findUrl(apps, a.url) >= 0) continue;
        if (a.id.empty() || find(apps, a.id) >= 0) a.id = makeId(a.url, apps);
        if (a.id.empty()) continue;
        apps.push_back(a);
    }
    return true;
}
inline std::string serialize(const std::vector<App>& apps)
{
    std::string o = "{\"v\":1,\"apps\":[";
    for (size_t i = 0; i < apps.size() && i < kMaxApps; ++i) {
        const App& a = apps[i];
        o += (i ? "," : "") + std::string("{\"id\":") + quote(a.id) + ",\"name\":" + quote(a.name) + ",\"url\":" + quote(a.url)
            + ",\"icon\":" + quote(a.icon) + ",\"theme\":" + quote(a.theme) + "}";
    }
    return o + "]}\n";
}

enum AddResult { kAdded, kUpdated, kFull, kInvalid };
// Adds `in` (its id is made here), or refreshes the app with the same start address (name, icon, colour; it keeps its
// id and place). Nothing changes on kFull / kInvalid.
inline AddResult add(std::vector<App>& apps, const App& in)
{
    App a = checked(in);
    if (a.url.empty()) return kInvalid;
    const int same = findUrl(apps, a.url);
    if (same >= 0) {
        App& e = apps[size_t(same)];
        e.name = a.name;
        if (!a.icon.empty()) e.icon = a.icon;
        if (!a.theme.empty()) e.theme = a.theme;
        return kUpdated;
    }
    if (apps.size() >= kMaxApps) return kFull;
    a.id = makeId(a.url, apps);
    if (a.id.empty()) return kInvalid;
    apps.push_back(a);
    return kAdded;
}
inline bool remove(std::vector<App>& apps, const std::string& id)
{
    const int i = find(apps, id);
    if (i < 0) return false;
    apps.erase(apps.begin() + i);
    return true;
}
// dir -1 up / +1 down; false at an end.
inline bool move(std::vector<App>& apps, const std::string& id, int dir)
{
    const int i = find(apps, id), j = i + dir;
    if (i < 0 || (dir != -1 && dir != 1) || j < 0 || j >= int(apps.size())) return false;
    std::swap(apps[size_t(i)], apps[size_t(j)]);
    return true;
}

// --- the page query --------------------------------------------------------------------------------------------------
// The body of an async function (WKPageCallAsyncJavaScriptWithoutUserGesture). Read-only: it reads the document's
// title, icon links and theme-color, and fetches the page's web app manifest (if any) as the page itself would.
// Answers JSON.stringify({title,fav,tc,name,short,start,icon,theme,m}) within 3 s whatever the page does.
inline std::string pageScript()
{
    return R"JS(const P = Promise, race = Promise.race.bind(Promise), resolve = Promise.resolve.bind(Promise), later = setTimeout;
const out = { title: "", fav: "", tc: "", name: "", short: "", start: "", icon: "", theme: "", m: 0 };
const str = (v, n) => typeof v === "string" ? v.slice(0, n) : "";
const web = u => typeof u === "string" && /^https?:\/\//i.test(u);
const wait = (p, ms, fb) => race([resolve(p).catch(() => fb), new P(r => later(() => r(fb), ms))]);
const size = s => {
  let best = 0;
  for (const t of String(s || "").split(/\s+/)) {
    if (t.toLowerCase() === "any") best = Math.max(best, 512);
    const m = /^(\d{1,4})x(\d{1,4})$/i.exec(t);
    if (m) best = Math.max(best, Math.min(+m[1], +m[2]));
  }
  return best;
};
const work = async () => {
  try {
    out.title = str(document.title, 200);
    let best = -1;
    for (const l of Array.from(document.querySelectorAll("link[rel][href]")).slice(0, 64)) {
      const rel = String(l.getAttribute("rel") || "").toLowerCase().split(/\s+/);
      const touch = rel.includes("apple-touch-icon") || rel.includes("apple-touch-icon-precomposed");
      if (!touch && !rel.includes("icon")) continue;
      const s = (touch ? 180 : 0) + size(l.getAttribute("sizes"));
      if (s > best && web(l.href)) { best = s; out.fav = str(l.href, 2048); }
    }
    if (!out.fav && web(location.href)) out.fav = new URL("/favicon.ico", location.href).href;
    const tm = document.querySelector('meta[name="theme-color"][content]');
    if (tm) out.tc = str(tm.getAttribute("content"), 32);
    const ml = document.querySelector('link[rel~="manifest"][href]');
    if (ml && web(ml.href) && typeof fetch === "function") {
      const href = ml.href;
      const r = await wait(fetch(href, { credentials: ml.crossOrigin === "use-credentials" ? "include" : "same-origin" }), 2500, null);
      const text = r && r.ok ? await wait(r.text(), 1000, "") : "";
      if (typeof text === "string" && text.length > 0 && text.length <= 65536) {
        const j = JSON.parse(text);
        if (j && typeof j === "object") {
          out.m = 1;
          out.name = str(j.name, 200);
          out.short = str(j.short_name, 200);
          out.theme = str(j.theme_color, 32);
          if (typeof j.start_url === "string") { try { out.start = str(new URL(j.start_url, href).href, 2048); } catch (e) {} }
          let ib = -1;
          for (const i of Array.isArray(j.icons) ? j.icons.slice(0, 32) : []) {
            if (!i || typeof i.src !== "string") continue;
            const purpose = typeof i.purpose === "string" ? i.purpose.toLowerCase() : "any";
            if (!/\bany\b/.test(purpose) && !/\bmaskable\b/.test(purpose)) continue;
            const s = size(i.sizes);
            if (s <= ib) continue;
            try { const u = new URL(i.src, href).href; if (web(u)) { ib = s; out.icon = str(u, 2048); } } catch (e) {}
          }
        }
      }
    }
  } catch (e) {}
  return JSON.stringify(out);
};
return await race([work(), new P(r => later(() => r(JSON.stringify(out)), 3000))]);
)JS";
}

struct Found {
    bool ok = false;        // the page's address can be an app
    bool manifest = false;  // a manifest was read
    App app;                // id empty
};
// The page's answer (may be "" or anything: a page can replace what the script uses) -> what is saved / used.
// start_url only when it is the page's own origin (as browsers do), else the page's address; name: manifest name
// (short_name when the name is over 24 bytes or missing), else the page title, the tab title, the host.
inline Found fromPage(const std::string& answer, const std::string& pageUrl, const std::string& tabTitle)
{
    Found f;
    const std::string page = noFragment(pageUrl);
    if (!validWebUrl(page)) return f;
    Json j;
    if (answer.size() > kAnswerMax || !parseJson(answer, j, kAnswerMax) || j.t != Json::tObj) j = Json();
    const Json* m = j.get("m");
    f.manifest = m && m->t == Json::tNum && m->n == 1;
    const std::string name = cleanText(j.str("name"), 200), shortName = cleanText(j.str("short"), 200);
    std::string pick = !shortName.empty() && (name.empty() || name.size() > 24) ? shortName : name;
    if (pick.empty()) pick = cleanText(j.str("title"), 200);
    if (pick.empty()) pick = cleanText(tabTitle, 200);
    if (pick.empty()) pick = shownHost(page);
    f.app.name = cleanText(pick, kNameMax);
    const std::string start = j.str("start");
    f.app.url = validWebUrl(start) && sameOrigin(start, page) ? noFragment(start) : page;
    const std::string icon = j.str("icon"), fav = j.str("fav");
    f.app.icon = validWebUrl(icon) ? icon : validWebUrl(fav) ? fav : std::string();
    f.app.theme = validTheme(j.str("theme"));
    if (f.app.theme.empty()) f.app.theme = validTheme(j.str("tc"));
    f.ok = true;
    return f;
}

// --- the start page --------------------------------------------------------------------------------------------------
// What start-webapps.js gets: {"v":1,"apps":[{"id","n","h","c","k","l"}],"max":12,"hint":".."} (no addresses but the
// host shown under the name; the page asks Omni to open an app by id).
inline std::string pageJson(const std::vector<App>& apps, const std::string& hint)
{
    std::string o = "{\"v\":1,\"apps\":[";
    for (size_t i = 0; i < apps.size() && i < kMaxApps; ++i) {
        const App& a = apps[i];
        const std::string c = a.theme.empty() ? fallbackColour(a.id) : a.theme;
        o += (i ? "," : "") + std::string("{\"id\":") + quote(a.id) + ",\"n\":" + quote(a.name) + ",\"h\":" + quote(shownHost(a.url))
            + ",\"c\":" + quote(c) + ",\"k\":" + quote(inkFor(c)) + ",\"l\":" + quote(letter(a.name)) + "}";
    }
    return o + "],\"max\":" + std::to_string(kMaxApps) + ",\"hint\":" + quote(hint) + "}";
}

// --- texts -------------------------------------------------------------------------------------------------------------
inline std::string addNotice(AddResult r, const std::string& name)
{
    switch (r) {
    case kAdded: return "Added " + name + " to Apps on the start page";
    case kUpdated: return name + " is already in Apps (details updated)";
    case kFull: return "Apps is full (" + std::to_string(kMaxApps) + "): remove one in Browser settings > Apps on start page";
    default: return "This page can't be added to Apps";
    }
}
inline std::string enterNotice(const std::string& name) { return name + " opened as an app: Options for Back, Home and Leave app mode"; }
inline std::string summary(size_t n) { return n ? std::to_string(n) + " of " + std::to_string(kMaxApps) : std::string("None yet"); }
constexpr const char* kPrivateRefusal = "Private tabs can't be apps";

// --- a settings file that does not parse (OMNI_WEB_APPS_V1_R2) ----------------------------------------------------
// It is renamed to "<name>.bad-<unix time>" before the defaults are used, so the next save (only ever after the user
// changes something) never replaces it; at most kBadKept such copies stay, the oldest go.
constexpr size_t kBadKept = 3;
inline std::string badName(const std::string& name, long long now) { return name + ".bad-" + std::to_string(now < 0 ? 0 : now); }
// The time of a kept copy "<name>.bad-<1..18 digits>"; -1 for any other file name.
inline long long badTime(const std::string& file, const std::string& name)
{
    const std::string pre = name + ".bad-";
    if (file.size() <= pre.size() || file.size() > pre.size() + 18 || file.compare(0, pre.size(), pre) != 0) return -1;
    long long t = 0;
    for (size_t i = pre.size(); i < file.size(); ++i) {
        if (file[i] < '0' || file[i] > '9') return -1;
        t = t * 10 + (file[i] - '0');
    }
    return t;
}
// Of a folder's file names: the kept copies to delete (all but the `keep` newest, by time, then name).
inline std::vector<std::string> badToDrop(const std::vector<std::string>& files, const std::string& name, size_t keep = kBadKept)
{
    std::vector<std::pair<long long, std::string>> bad;
    for (const auto& f : files) {
        const long long t = badTime(f, name);
        if (t >= 0) bad.emplace_back(t, f);
    }
    std::sort(bad.begin(), bad.end(), [](const std::pair<long long, std::string>& a, const std::pair<long long, std::string>& b) {
        return a.first != b.first ? a.first > b.first : a.second > b.second; });
    std::vector<std::string> out;
    for (size_t i = keep; i < bad.size(); ++i) out.push_back(bad[i].second);
    return out;
}

} // namespace OmniWebApps
'''

SHELL = r'''// OMNI_WEB_APPS_V1: "Open as app" and Apps on the start page (shell side). Included from OmniFeatures3.h after
// OmniStartCustomShell.h (inside OmniBrowser.cpp's anonymous namespace). The pure part is OmniWebApps.h; the reasons
// are in tools/apply_web_apps.py. Main thread only; nothing per frame (omniWapTick compares one flag).
//   - An app tab: a normal tab listed in omniWapTabs (never a private tab, never the Downloads tab). While it is the
//     shown tab, omniWapOn is set: omniAutoHideActive() is true (full-height page, bars drawn over it) and
//     omniStyleTick keeps the bars hidden unless the keyboard or settings are open. Options opens the app menu.
//   - /data/omni/apps.json: read once on first use, written through omniIoQueue after each change (only then: a file
//     that does not parse is kept as apps.json.bad-<time>, OMNI_WEB_APPS_V1_R2).
//   - The start page gets OWAP::pageJson through ONE fixed script after it loads (start-webapps.js draws the tiles);
//     it asks back through request() "webapps.open" / "webapps.manage" (OmniPages.h).
#pragma once

namespace OWAP = OmniWebApps;

static std::vector<OWAP::App> omniWapList;
static bool omniWapLoaded = false;
struct OmniWapTab { const void* tab = nullptr; std::string id, url, name; };   // id "": opened as an app, not saved
static std::vector<OmniWapTab> omniWapTabs;
static std::map<WKPageRef, std::string> omniWapDrawn;   // what each start page was given last
struct OmniWapAct { int kind = 0; WKPageRef page = nullptr; std::string text; };
static std::vector<OmniWapAct> omniWapQueue;            // bridge requests, done on the next tick
enum { omniWapActOpen = 1, omniWapActManage };

// OMNI_WEB_APPS_V1_R2: the file did not parse. It is kept as <name>.bad-<unix time> (at most 3; OWAP::badToDrop) and
// the defaults are used; nothing is written until the user changes something (the only writer is that change's save).
static void omniWapKeepBad(const std::string& path)
{
    const size_t slash = path.rfind('/');
    const std::string dir = slash == std::string::npos ? std::string(".") : path.substr(0, slash);
    const std::string name = slash == std::string::npos ? path : path.substr(slash + 1);
    const std::string bad = OWAP::badName(name, (long long)time(nullptr));
    const bool kept = rename(path.c_str(), (dir + "/" + bad).c_str()) == 0;
    std::vector<std::string> files;
    if (DIR* d = opendir(dir.c_str())) {
        while (dirent* e = readdir(d)) if (files.size() < 1000 && OWAP::badTime(e->d_name, name) >= 0) files.emplace_back(e->d_name);
        closedir(d);
    }
    for (const auto& f : OWAP::badToDrop(files, name)) unlink((dir + "/" + f).c_str());
    fprintf(stderr, "OMNI_WEB_APPS_V1: %s unreadable, %s%s; no apps until one is added (nothing is written until a change)\n", name.c_str(),
            kept ? "kept as " : "could not be renamed", kept ? bad.c_str() : "");
}
static std::vector<OWAP::App>& omniWapApps()
{
    if (omniWapLoaded) return omniWapList;
    omniWapLoaded = true;
    std::string text;
    if (FILE* f = fopen(omniData(OWAP::kFileName).c_str(), "rb")) {
        char buf[4096];
        size_t n;
        while ((n = fread(buf, 1, sizeof buf, f)) > 0 && text.size() <= OWAP::kMaxFile) text.append(buf, n);
        fclose(f);
        if (!OWAP::parse(text, omniWapList)) omniWapKeepBad(omniData(OWAP::kFileName));   // OMNI_WEB_APPS_V1_R2
    }
    return omniWapList;
}
static OmniWapTab* omniWapOf(const void* tab)
{
    for (auto& a : omniWapTabs) if (a.tab == tab) return &a;
    return nullptr;
}
static bool omniWapIsApp(const Tab& t) { return omniWapOf(&t) != nullptr; }
static void omniWapForget(const void* tab)
{
    omniWapTabs.erase(std::remove_if(omniWapTabs.begin(), omniWapTabs.end(), [tab](const OmniWapTab& a) { return a.tab == tab; }), omniWapTabs.end());
}
static bool omniWapStartTab(const Tab* t) { return t && t->omniPagesTab && t->omniNewTabPage && !t->crashed; }

// --- the start page ------------------------------------------------------------------------------------------------
static const char* const omniWapScript = "(function(D){window.__omniWebApps=D;var f=window.omniWebAppsApply;"
    "return typeof f==='function'?String(f(D)):'later'})(%DATA%)";
static void omniWapRender(Tab* tab, bool force)
{
    if (!tab || tab->loading || tab->crashed || omniTestMode()) return;
    const std::string data = OWAP::pageJson(omniWapApps(), playStationIcons ? "\xC3\x97 Open" : "A Open");
    const auto it = omniWapDrawn.find(tab->page);
    if (!force && it != omniWapDrawn.end() && it->second == data) return;
    if (omniWapDrawn.size() > 64) omniWapDrawn.clear();
    omniWapDrawn[tab->page] = data;
    std::string js = omniWapScript;
    js.replace(js.find("%DATA%"), 6, data);
    auto source = adoptWK(WKStringCreateWithUTF8CString(js.c_str()));
    WKPageEvaluateJavaScriptInMainFrame(tab->page, source.get(), nullptr, [](WKTypeRef, WKErrorRef, void*) { });
}
static void omniWapRenderAll()
{
    for (auto& t : tabs) if (omniWapStartTab(t.get()) && omniWapDrawn.count(t->page)) omniWapRender(t.get(), true);
}
static void omniWapSave()
{
    omniIoQueue(omniData(OWAP::kFileName), OWAP::serialize(omniWapApps()), false);
    omniWapRenderAll();
}
// omniEverydayFinished(): a page finished loading (tab.url not cleared yet). Only Omni's built-in start page.
static void omniWapFinished(Tab& tab)
{
    omniWapDrawn.erase(tab.page);
    if (tab.url.rfind(OWAP::kStartPrefix, 0) != 0) return;
    omniWapRender(&tab, true);
}
// omniEverydayActivated(): a start page shown again (apps may have changed meanwhile).
static void omniWapActivated(Tab* tab)
{
    if (omniWapStartTab(tab) && omniWapDrawn.count(tab->page)) omniWapRender(tab, false);
}

// --- app tabs ----------------------------------------------------------------------------------------------------------
static bool omniWapEnter(Tab& t, const std::string& id, const std::string& url, const std::string& name)
{
    if (t.omniPrivate) { notice(OWAP::kPrivateRefusal); return false; }
    if (omniMediaOwns(t)) { notice("The Downloads tab can't be an app"); return false; }
    OmniWapTab* a = omniWapOf(&t);
    if (!a) { omniWapTabs.push_back(OmniWapTab()); a = &omniWapTabs.back(); a->tab = &t; }
    a->id = id; a->url = url; a->name = name.empty() ? OWAP::shownHost(url) : name;
    if (&t == active()) notice(OWAP::enterNotice(a->name));
    fprintf(stderr, "OMNI WEB APPS: app mode on (%s, %s)\n", a->id.empty() ? "not saved" : a->id.c_str(), OWAP::shownHost(url).c_str());
    omniShellDirty = true;
    return true;
}
static void omniWapLeave(Tab& t)
{
    omniWapForget(&t);
    notice("Left app mode");
    omniShellDirty = true;
}
// Opens a saved app: an open app tab of it comes forward; else `from` (a non-private start page) becomes the app,
// else a new normal tab does.
static void omniWapLaunch(const std::string& id, Tab* from)
{
    auto& list = omniWapApps();
    const int i = OWAP::find(list, id);
    if (i < 0) { notice("That app was removed"); return; }
    const OWAP::App app = list[size_t(i)];
    for (size_t k = 0; k < tabs.size(); ++k) {
        const OmniWapTab* a = omniWapOf(tabs[k].get());
        if (a && a->id == app.id) { if (k != selected) activate(k); notice(app.name + " is already open"); return; }
    }
    Tab* t = from;
    if (!t || t->omniPrivate || omniMediaOwns(*t) || !omniWapStartTab(t)) {
        if (!newTab()) return;   // newTab() says why (tab limit, memory)
        t = active();
    }
    if (!t || !OWAP::validWebUrl(app.url)) return;
    auto u = adoptWK(WKURLCreateWithUTF8CString(app.url.c_str()));
    WKPageLoadURL(t->page, u.get());
    omniWapEnter(*t, app.id, app.url, app.name);
}

// --- the page query (hold-Cross menu) ---------------------------------------------------------------------------------
enum { omniWapForOpen = 1, omniWapForAdd };
struct OmniWapJob {
    const void* tab = nullptr;
    std::string url, title;
    int purpose = 0;
    uint32_t startedAt = 0;
    bool finished = false;   // done (answer or native timeout); the job is freed by the WebKit callback
};
static OmniWapJob* omniWapJob = nullptr;   // one query at a time
static void omniWapFinish(OmniWapJob* j, const std::string& answer, bool timedOut)
{
    if (j->finished) return;
    j->finished = true;
    if (omniWapJob == j) omniWapJob = nullptr;
    const OWAP::Found f = OWAP::fromPage(answer, j->url, j->title);
    fprintf(stderr, "OMNI WEB APPS: page read %s (manifest %d, %zu bytes)\n", timedOut ? "timed out" : "done", f.manifest ? 1 : 0, answer.size());
    if (!f.ok) { notice("This page can't be an app"); return; }
    auto& list = omniWapApps();
    if (j->purpose == omniWapForAdd) {
        const OWAP::AddResult r = OWAP::add(list, f.app);
        notice(OWAP::addNotice(r, f.app.name));
        if (r == OWAP::kAdded || r == OWAP::kUpdated) omniWapSave();
        return;
    }
    Tab* t = nullptr;
    for (auto& x : tabs) if (x.get() == j->tab) t = x.get();
    if (!t || !OWAP::sameOrigin(t->url, j->url)) return;   // closed, or on another site by now
    const int saved = OWAP::findUrl(list, f.app.url);
    omniWapEnter(*t, saved >= 0 ? list[size_t(saved)].id : std::string(), f.app.url, f.app.name);
}
static void omniWapQuery(Tab& t, int purpose)
{
    if (omniWapJob) { notice("Still reading this page..."); return; }
    if (t.omniPrivate) { notice(OWAP::kPrivateRefusal); return; }
    auto* j = new OmniWapJob;
    j->tab = &t; j->url = t.url; j->title = t.title; j->purpose = purpose; j->startedAt = SDL_GetTicks();
    omniWapJob = j;
    if (t.crashed) { omniWapFinish(j, std::string(), false); delete j; return; }
    auto body = adoptWK(WKStringCreateWithUTF8CString(OWAP::pageScript().c_str()));
    auto args = adoptWK(WKDictionaryCreate(nullptr, nullptr, 0));   // an async function needs an argument list
    WKPageCallAsyncJavaScriptWithoutUserGesture(t.page, body.get(), args.get(), nullptr, j, [](WKTypeRef result, WKErrorRef error, void* ctx) {
        OmniWapJob* job = static_cast<OmniWapJob*>(ctx);
        if (!job->finished) {
            std::string a = omniFxResultString(result, error);
            if (a.size() > OWAP::kAnswerMax) a.clear();
            omniWapFinish(job, a, false);
        }
        delete job;
    });
}

// --- hold-Cross page menu (declared in OmniFeatures3Decl.h) -----------------------------------------------------------
static void omniWapContextRows(OmniFxPanel& p)
{
    Tab* t = active();
    if (!t || t->omniPrivate) return;   // private tabs are never apps
    const bool app = omniWapIsApp(*t), web = omniWebURL(t->url) && !omniMediaOwns(*t);
    OmniFxRow o; o.id = OWAP::kContextOpen; o.label = app ? "Leave app mode" : "Open as app";
    o.enabled = app || (web && !omniWapJob);
    p.rows.push_back(o);
    const auto& list = omniWapApps();
    OmniFxRow a; a.id = OWAP::kContextAdd; a.label = "Add to Apps";
    a.enabled = web && !omniWapJob;
    a.value = web && OWAP::findOrigin(list, t->url) >= 0 ? "In Apps" : list.size() >= OWAP::kMaxApps ? "Full (12)" : "";
    p.rows.push_back(a);
}
static bool omniWapContextAction(int id)
{
    if (id != OWAP::kContextOpen && id != OWAP::kContextAdd) return false;
    omniFxCloseAll();
    Tab* t = active();
    if (!t) return true;
    if (id == OWAP::kContextOpen && omniWapIsApp(*t)) { omniWapLeave(*t); return true; }
    omniWapQuery(*t, id == OWAP::kContextOpen ? omniWapForOpen : omniWapForAdd);
    return true;
}
// Tabs panel (OmniTabsPage.h): "App" after the row's value.
static void omniWapTabRow(const Tab& t, OmniFxRow& r)
{
    if (!omniWapIsApp(t)) return;
    r.value = r.value.empty() ? std::string("App") : r.value + " \xc2\xb7 App";
}

// --- the app menu (Options on an app tab) ------------------------------------------------------------------------------
enum { omniWapRowBack = 1, omniWapRowHome, omniWapRowReload, omniWapRowMenu, omniWapRowLeave, omniWapRowClose };
static void omniWapMenuBuild(OmniFxPanel& p)
{
    Tab* t = active();
    const OmniWapTab* a = t ? omniWapOf(t) : nullptr;
    auto add = [&](int id, const char* label, std::string detail, bool on, int icon) {
        OmniFxRow r; r.id = id; r.label = label; r.detail = std::move(detail); r.enabled = on; r.icon = icon; p.rows.push_back(r);
    };
    if (!t || !a) { add(0, "Not an app tab any more", std::string(), false, -1); return; }
    p.title = a->name;
    p.subtitle = omniShownURL(t->url);
    add(omniWapRowBack, "Back", std::string(), WKPageCanGoBack(t->page), omniIconBack);
    add(omniWapRowHome, "Home", omniShownURL(a->url), OWAP::validWebUrl(a->url), -1);
    add(omniWapRowReload, "Reload", std::string(), true, omniIconReload);
    add(omniWapRowMenu, "Browser menu", "Tabs, settings and everything else", true, omniIconGear);
    add(omniWapRowLeave, "Leave app mode", "The address bar and tabs come back", true, -1);
    add(omniWapRowClose, "Close app", "Closes this tab", true, omniIconClose);
    p.rows.back().danger = true;
}
static bool omniWapMenuInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    if (!r.enabled) return true;
    Tab* t = active();
    const OmniWapTab* a = t ? omniWapOf(t) : nullptr;
    omniFxCloseAll();
    if (!t || !a) return true;
    const std::string home = a->url;
    switch (r.id) {
    case omniWapRowBack: omniFxBack(); break;
    case omniWapRowHome: if (OWAP::validWebUrl(home)) { auto u = adoptWK(WKURLCreateWithUTF8CString(home.c_str())); WKPageLoadURL(t->page, u.get()); } break;
    case omniWapRowReload: WKPageReload(t->page); break;
    case omniWapRowMenu: omniFxQuickMenuShow(); break;
    case omniWapRowLeave: omniWapLeave(*t); break;
    case omniWapRowClose: if (omniPtMayClose(*t)) closeTab(); break;   // a pinned tab asks once
    }
    return true;
}
// button(): Options while an app tab is shown (true: the app menu opened instead of the quick menu).
static bool omniWapOptions()
{
    Tab* t = active();
    if (!omniWapOn || !t || !omniWapOf(t)) return false;
    OmniFxPanel p;
    p.kind = OWAP::kMenuKind; p.title = "App"; p.w = 600; p.maxVisible = 7;
    p.build = omniWapMenuBuild; p.input = omniWapMenuInput;
    p.faces = { { 0, "Choose" }, { 1, "Close" } };
    omniFxPush(std::move(p));
    return true;
}

// --- Browser settings > Apps on start page... ---------------------------------------------------------------------------
enum { omniWapRowApp = 100 };
static std::string omniWapSummary() { return OWAP::summary(omniWapApps().size()); }
static void omniWapPanelBuild(OmniFxPanel& p)
{
    const auto& list = omniWapApps();
    for (size_t i = 0; i < list.size(); ++i) {
        OmniFxRow r; r.id = omniWapRowApp + int(i); r.label = list[i].name; r.detail = omniShownURL(list[i].url);
        for (const auto& a : omniWapTabs) if (a.id == list[i].id) r.value = "Open";
        p.rows.push_back(r);
    }
    if (list.empty()) {
        OmniFxRow r; r.id = 0; r.label = "No apps yet"; r.detail = "On a site: hold Cross, then Add to Apps"; r.enabled = false;
        p.rows.push_back(r);
    }
    p.subtitle = OWAP::summary(list.size()) + " \xc2\xb7 shown under Your apps on the start page";
}
static bool omniWapPanelInput(OmniFxPanel& p, const OmniFxRow& r, int b)
{
    auto& list = omniWapApps();
    const int i = r.id - omniWapRowApp;
    if (i < 0 || i >= int(list.size())) return false;
    const std::string id = list[size_t(i)].id, name = list[size_t(i)].name;
    if (b == SDL_CONTROLLER_BUTTON_A) { omniFxCloseAll(); omniWapLaunch(id, active()); return true; }
    if (b == SDL_CONTROLLER_BUTTON_X) {   // Square: remove (asks)
        omniAsk("Remove " + name + " from Apps?", "Its tile leaves the start page. The site's cookies and data are not touched.", "Remove",
            [id, name](bool ok) {
                if (!ok || !OWAP::remove(omniWapApps(), id)) return;
                omniWapSave();
                notice(name + " removed from Apps");
            });
        return true;
    }
    if (b == SDL_CONTROLLER_BUTTON_Y) {   // Triangle: move up
        if (!OWAP::move(list, id, -1)) { notice("Already first"); return true; }
        p.sel = std::max(0, i - 1);
        omniWapSave();
        return true;
    }
    return false;
}
static void omniWapPanelShow()
{
    OmniFxPanel p;
    p.kind = OWAP::kPanelKind; p.title = "Apps on start page"; p.w = 820; p.maxVisible = 9;
    p.build = omniWapPanelBuild; p.input = omniWapPanelInput;
    p.faces = { { 0, "Open" }, { 2, "Remove" }, { 3, "Move up" }, { 1, "Back" } };
    omniFxPush(std::move(p));
}

// --- the start page's requests (OmniPages.h: request() methods "webapps.*") ----------------------------------------------
static std::string omniWapBridge(WKPageRef page, Tab& tab, const std::string& method, const std::string& arg)
{
    auto err = [](const char* code) { return std::string("{\"ok\":false,\"code\":\"") + code + "\"}"; };
    const std::string ok = "{\"ok\":true,\"result\":null}";
    if (!omniWapStartTab(&tab)) return err("UNSUPPORTED");
    if (method == "webapps.manage") { omniWapQueue.push_back({ omniWapActManage, page, std::string() }); return ok; }
    if (method == "webapps.open") {
        if (!OWAP::validId(arg)) return err("INVALID_VALUE");
        if (OWAP::find(omniWapApps(), arg) < 0) return err("NOT_FOUND");
        omniWapQueue.push_back({ omniWapActOpen, page, arg });
        return ok;
    }
    return err("UNSUPPORTED");
}

// omniF3Tick(): the page query's native timeout, the start page's requests, the app layout of the shown tab.
static void omniWapTick(uint32_t now)
{
    if (omniWapJob && OWAP::expired(omniWapJob->startedAt, now)) omniWapFinish(omniWapJob, std::string(), true);   // freed by its callback
    if (!omniWapQueue.empty()) {
        auto queue = std::move(omniWapQueue);
        omniWapQueue.clear();
        for (auto& act : queue) {
            Tab* tab = omniTabForPage(act.page);
            if (!tab || tab != active()) continue;   // only the tab the user is looking at
            if (act.kind == omniWapActManage) { if (!editing && !settingsOpen && omniFxStack.empty()) omniWapPanelShow(); }
            else if (act.kind == omniWapActOpen) omniWapLaunch(act.text, tab);
        }
        omniShellDirty = true;
    }
    Tab* t = active();
    const bool want = t && !t->crashed && omniWapOf(t) != nullptr;
    if (want == omniWapOn) return;
    omniWapOn = want;
    omniApplyPageHeight();   // Auto-hide's full-height layout (or back), as when Auto-hide is switched in settings
    if (active() && !pageFullscreen) WKViewSetSize(active()->view.get(), omniViewSize());
    omniChromeWanted = !want;
    omniShellDirty = true;
    omniPageDirty = true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniStartCustom.h" // OMNI_START_CUSTOM_V1: Customise start page: order, sections, background (pure)\n',
         '#include "OmniStartCustom.h" // OMNI_START_CUSTOM_V1: Customise start page: order, sections, background (pure)\n'
         '#include "OmniWebApps.h" // OMNI_WEB_APPS_V1: Open as app, Apps on the start page, apps.json (pure)\n'),
        ('static bool omniAutoHideActive() { return omniAutoHide && omniAutoHideAllowed; }\n',
         'static bool omniWapOn = false;               // OMNI_WEB_APPS_V1: the shown tab is an app tab (OmniWebAppsShell.h, omniWapTick)\n'
         'static bool omniAutoHideActive() { return (omniAutoHide || omniWapOn) && omniAutoHideAllowed; } // OMNI_WEB_APPS_V1: an app tab gets Auto-hide\'s layout\n'),
        ('    omniVideoImmersive = omniAutoHideActive() && omniVideoFillsView();   // OMNI_VIDEO_IMMERSIVE_V1\n',
         '    omniVideoImmersive = omniAutoHideActive() && omniVideoFillsView();   // OMNI_VIDEO_IMMERSIVE_V1\n'
         '    if (omniWapOn && !pageFullscreen && !editing && !settingsOpen) omniChromeWanted = false;   // OMNI_WEB_APPS_V1: an app tab\'s bars stay hidden (Options: the app menu)\n'),
        ('    omniScuFinished(tab); // OMNI_START_CUSTOM_V1: the start page gets its settings (after the row: it places it)\n',
         '    omniScuFinished(tab); // OMNI_START_CUSTOM_V1: the start page gets its settings (after the row: it places it)\n'
         '    omniWapFinished(tab); // OMNI_WEB_APPS_V1: the start page gets its Web apps tiles\n'),
        ('    omniScuActivated(tab); // OMNI_START_CUSTOM_V1: and its settings / lists, if they changed\n',
         '    omniScuActivated(tab); // OMNI_START_CUSTOM_V1: and its settings / lists, if they changed\n'
         '    omniWapActivated(tab); // OMNI_WEB_APPS_V1: and its Web apps tiles, if they changed\n'),
        ('    if (button == SDL_CONTROLLER_BUTTON_START) { omniFxQuickMenuShow(); return; } // OMNI_FEATURES_V1: quick menu (Exit Omni is in it, with a confirm)\n',
         '    if (button == SDL_CONTROLLER_BUTTON_START && omniWapOptions()) return; // OMNI_WEB_APPS_V1: an app tab\'s menu (Back, Home, Reload, Leave app mode, Close)\n'
         '    if (button == SDL_CONTROLLER_BUTTON_START) { omniFxQuickMenuShow(); return; } // OMNI_FEATURES_V1: quick menu (Exit Omni is in it, with a confirm)\n'),
    ],
    'OmniFeatures3Decl.h': [
        ('static bool omniPtStripClick(int x);\n',
         'static bool omniPtStripClick(int x);\n'
         '// OMNI_WEB_APPS_V1 (OmniWebAppsShell.h): app tabs, Apps on the start page\n'
         'static void omniWapForget(const void* tab);                // omniFxTabClosing\n'
         'static void omniWapTabRow(const Tab& t, OmniFxRow& r);     // Tabs panel: "App"\n'
         'static void omniWapContextRows(OmniFxPanel& p);            // hold-Cross page menu: Open as app / Add to Apps\n'
         'static bool omniWapContextAction(int id);\n'
         'static bool omniWapOptions();                              // button(): Options on an app tab\n'
         'static void omniWapFinished(Tab& tab);                     // the start page gets its tiles\n'
         'static void omniWapActivated(Tab* tab);\n'
         'static void omniWapPanelShow();                            // Browser settings > Apps on start page...\n'
         'static std::string omniWapSummary();\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniStartCustomShell.h" // OMNI_START_CUSTOM_V1 (uses the reading list and the closed-tab list)\n',
         '#include "OmniStartCustomShell.h" // OMNI_START_CUSTOM_V1 (uses the reading list and the closed-tab list)\n'
         '#include "OmniWebAppsShell.h" // OMNI_WEB_APPS_V1 (uses the pinned tabs\' close rule)\n'),
        ('    omniScuTick(now);   // OMNI_START_CUSTOM_V1: start-page requests; the active start page\'s data (at most 1/s)\n',
         '    omniScuTick(now);   // OMNI_START_CUSTOM_V1: start-page requests; the active start page\'s data (at most 1/s)\n'
         '    omniWapTick(now);   // OMNI_WEB_APPS_V1: page-query timeout, start-page requests, the app layout of the shown tab\n'),
    ],
    'OmniTabsPage.h': [
        ('    omniPtForget(&tab); // OMNI_PINNED_TABS_V1\n',
         '    omniPtForget(&tab); // OMNI_PINNED_TABS_V1\n'
         '    omniWapForget(&tab); // OMNI_WEB_APPS_V1\n'),
        ('        omniPtTabRow(t, i, r); // OMNI_PINNED_TABS_V1: "Pinned", or "Square again: close"\n',
         '        omniPtTabRow(t, i, r); // OMNI_PINNED_TABS_V1: "Pinned", or "Square again: close"\n'
         '        omniWapTabRow(t, r); // OMNI_WEB_APPS_V1: "App"\n'),
    ],
    'OmniContextMenu.h': [
        ('        omniPtContextRows(p); // OMNI_PINNED_TABS_V1: Pin this tab / Unpin this tab\n',
         '        omniPtContextRows(p); // OMNI_PINNED_TABS_V1: Pin this tab / Unpin this tab\n'
         '        omniWapContextRows(p); // OMNI_WEB_APPS_V1: Open as app (Leave app mode) / Add to Apps\n'),
        ('    if (omniPtContextAction(r.id)) return true; // OMNI_PINNED_TABS_V1\n',
         '    if (omniPtContextAction(r.id)) return true; // OMNI_PINNED_TABS_V1\n'
         '    if (omniWapContextAction(r.id)) return true; // OMNI_WEB_APPS_V1\n'),
    ],
    'OmniBrowserSettings.h': [
        ('    add(OmniStartCustom::kRowId, "Customise start page...", omniScuSummary(), false); // OMNI_START_CUSTOM_V1\n',
         '    add(OmniStartCustom::kRowId, "Customise start page...", omniScuSummary(), false); // OMNI_START_CUSTOM_V1\n'
         '    add(OmniWebApps::kSettingsRowId, "Apps on start page...", omniWapSummary(), false); // OMNI_WEB_APPS_V1\n'),
        ('    if (r.id == OmniStartCustom::kRowId) { if (b != SDL_CONTROLLER_BUTTON_A) return false; omniScuShow(); return true; } // OMNI_START_CUSTOM_V1\n',
         '    if (r.id == OmniWebApps::kSettingsRowId) { if (b != SDL_CONTROLLER_BUTTON_A) return false; omniWapPanelShow(); return true; } // OMNI_WEB_APPS_V1\n'
         '    if (r.id == OmniStartCustom::kRowId) { if (b != SDL_CONTROLLER_BUTTON_A) return false; omniScuShow(); return true; } // OMNI_START_CUSTOM_V1\n'),
    ],
    'OmniPages.h': [
        ('        if (method.rfind("start.", 0) == 0) return omniScuBridge(page, *tab, method, omniPagesField(a, "url")); // OMNI_START_CUSTOM_V1 (OmniStartCustomShell.h)\n',
         '        if (method.rfind("webapps.", 0) == 0) return omniWapBridge(page, *tab, method, omniPagesField(a, "url")); // OMNI_WEB_APPS_V1 (OmniWebAppsShell.h)\n'
         '        if (method.rfind("start.", 0) == 0) return omniScuBridge(page, *tab, method, omniPagesField(a, "url")); // OMNI_START_CUSTOM_V1 (OmniStartCustomShell.h)\n'),
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
    needs = (('OmniBrowser.cpp', 'OMNI_START_CUSTOM_V1'), ('OmniFeatures3.h', 'OMNI_START_CUSTOM_V1'),
             ('OmniFeatures3Decl.h', 'OMNI_PINNED_TABS_V1'), ('OmniContextMenu.h', 'OMNI_PINNED_TABS_V1'),
             ('OmniPages.h', 'OMNI_START_CUSTOM_V1'), ('OmniSiteClearShell.h', 'OMNI_SITE_CLEAR_V1'))
    for need, mark in needs:
        if mark not in (root / need).read_bytes().decode('utf-8'):
            sys.exit('%s: %s missing: apply that patch first' % (need, mark))
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniWebApps.h', PURE, 'OmniStartCustom.h'),
            write_new('OmniWebAppsShell.h', SHELL, 'OmniStartCustomShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK + ' (r2)')


main()
