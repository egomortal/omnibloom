#!/usr/bin/env python3
"""OMNI_START_CUSTOM_V1 (2026-11-16): "Customise start page".

How the start page works (studied first)
  - omni://pages/start/ is the pages bundle's start/index.html (omnibloom/omni/pages/bundle-clean4/start, packaged as
    /app0/pages; OmniPages.h, served by OmniBlocker.cpp's scheme handler with a strict CSP: script/style 'self', images
    'self' + data:). Sections: the hero (Universe picker + search box), "Your apps", and a library section with Pinned
    sites + Recent sites. 15 Universes each give it a grid layout (universe-layouts-*.css, visual-layout.js) and the
    page's own "Arrange" swaps panels (universe-arrangement.js, localStorage only). D-pad / Cross reach the page through
    window.omniMediaController (controller.js).
  - Data reaches the page two ways: window.omnibloomHost (request() methods navigation.current / navigation.open, ...,
    params limited to url / mode / revision), and fixed engine scripts after load (OMNI_CONTINUE_WATCHING_V1 inserts
    #omni-cw after the hero). Settings are never fetched by the page: no HTTP server, no file:// .

What this adds
  - Browser settings: "Customise start page..." (value Default / Customised) right after "Continue watching on start
    page"; the start page has a "Customise" gear in its header (only once Omni has given it its data, so never a dead
    button). Both open the panel "Customise start page":
      one row per section, in the current order: Search, Your apps, Pinned and recent sites, Continue watching,
      Reading list (latest 3), Recently closed tabs. Cross / D-pad left-right: Shown / Hidden; Square: move up;
      Triangle: move down (the moved row keeps the focus). "Search" hidden hides the search box only (the Universe
      picker stays). Continue watching is OMNI_CONTINUE_WATCHING_V1's own flag (continue-watching-off.flag): one switch.
      Background: D-pad left / right steps Theme default / 8 colours / picture; Cross opens a picker: Theme default,
      Midnight Graphite Forest Ocean Plum Crimson Sand Snow, "Your picture" (/data/omni/start-bg.png, when it exists)
      and the 40 newest PNGs in Downloads > Saved > Screenshots. No downloads.
      Clock: On / Off (HH:MM in the page header, updated every 10 s while shown).
      Reset to default.
  - /data/omni/start-page.json (OmniStartCustom.h has the format), read once on first use, written through omniIoQueue.
  - The page: start-custom.js / start-custom.css in the pages bundle (index.html loads them). Omni hands it the
    settings + the latest 3 reading-list entries + up to 5 recently closed tabs as ONE fixed script after a start page
    loads (and, only when the data changed, when that tab is shown again / once a second while it is the active tab:
    the reading list loads on a thread). Default order: the Universe's grid stays, the new sections span its full
    width after it; any other order: one column in that order (CSS order; Arrange is hidden then).
    Reading list tiles: Cross opens the saved copy (new tab, as the Reading list does); "All saved pages" opens the
    Reading list panel. Recently closed tiles: Cross reopens the address in this tab and drops it from the list.
  - Bridge: request() methods start.customise, start.reading.all, start.reading.open (params.url = the saved file's
    id), start.closed.open (params.url = the address); only from a start page, done on the next tick, only for the
    active tab.
  - Picture: never read on the main thread. When the settings need one, the main thread stat()s the chosen file
    (/data/omni/start-bg.png or a screenshot) and a worker thread reads it (<= 8 MB; PNG or JPEG by its magic bytes,
    anything else refused) into ONE in-memory copy keyed by path + mtime + size, so repeat loads re-read nothing.
    Only once the copy is ready does the page get omni://pages/_user/start-bg.png?v=<mtime-size-name> (the tick
    redraws open start pages). OmniBlocker.cpp's pages handler serves exactly "_user/start-bg.png" from that copy
    (omniPagesSetUserFile callback); any other _user/ path, or no matching copy, is 404.
  - Private tabs: the same start page, never Continue watching or Recently closed (engine and page both drop them);
    the reading list peek shows (saving stays refused there, as before).

Files
  new  OmniStartCustom.h        pure: sections, order moves, background choices, JSON parse / serialize, page JSON
                                (tests: tools/test_start_custom.cpp)
  new  OmniStartCustomShell.h   load / save, page script, panel + picker, bridge requests, user-file callback, tick
  OmniBrowser.cpp       after the OmniControlsHelp.h include: the pure include; after "static bool omniCwButton(int b);":
                        declarations; after the omniCwFinished / omniCwActivated lines: ours
  OmniBrowserSettings.h after the omniCwRowId line: declarations; after the Continue watching row: ours; before its
                        input line: ours (row id OmniStartCustom::kRowId = 875, free)
  OmniFeatures3.h       after the OmniControlsHelpShell.h include: the shell; after omniRlTick(now): omniScuTick(now)
  OmniPages.h           before the navigation.open branch of request(): the "start." methods
  OmniBlocker.h         after omniPagesSetBridge's declaration: OmniPagesUserFileFn + omniPagesSetUserFile
  OmniBlocker.cpp       after "OmniPagesMessageFn pagesMessage = nullptr;": the callback; before the handler's file line: the
                        _user/start-bg.png branch (served from memory); before omniPagesSetBridge's definition: omniPagesSetUserFile
  Pages bundle (repo, not this script): omnibloom/omni/pages/bundle-clean4/start/{index.html,start-custom.js,
                        start-custom.css} (tests: tools/test_start_custom_js.cjs)
Panel kinds 7480 / 7481 (unused). Each anchor exactly once, CRLF / LF kept per file, idempotent (MARK per file).
Apply after apply_continue_watching.py, apply_reading_list.py and apply_controls_help.py.
r2 (REV = OMNI_START_CUSTOM_V1_R2):
  - The once-a-second look at the active start page no longer rebuilds the page data (reading-list copy + sort under
    omniRlLock, the picture's stat, the closed-tab walk, the JSON) just to compare it. omniScuGen counts changes and a
    page is rebuilt only when its drawn generation differs. Bumped by: a settings change (omniScuSave), the picture's
    cached copy being ready / refused, a closed tab reopened from the start page, and omniScuWatch, which (only while a
    drawn start page is the active tab, once a second) looks at O(1) / O(10) things with no copy, sort or stat: the
    reading list's size, loaded flag and last entry id (every change there is a load, a save = push_back after
    makeRoom, or a delete; this tree has no reading progress on the entries), a hash of the <= 10 closed tabs (pushed
    on close, popped / erased on reopen, cleared by Clear data), the button style, Continue watching's cached flag and
    the hour (for "Today" / "Yesterday", and a picture file replaced from outside). No other patch's file is touched.
    A start page shown again (omniScuActivated) still compares in full.
  - A start-page.json that does not parse is renamed to start-page.json.bad-<unix time> (at most 3 kept), one log
    line, defaults used; nothing is written until the user changes a setting (omniScuSave's only callers).
  Only the two headers change; a tree patched by r1 gets them rewritten (write_new), the anchored edits are untouched:
  the result is byte-identical to a fresh apply.
usage: apply_start_custom.py <engine tree>
"""
import sys
from pathlib import Path

MARK = 'OMNI_START_CUSTOM_V1'
REV = 'OMNI_START_CUSTOM_V1_R2'   # r2: generation-gated start-page refresh; a broken start-page.json is kept; in the headers only
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_START_CUSTOM_V1: "Customise start page", the pure part (no SDL, no WebKit).
// /data/omni/start-page.json (written through omniIoQueue, read once on first use, <= 16 KB):
//   {"v":1,"order":["search","apps","shortcuts","cw","reading","closed"],"hidden":["closed"],
//    "bg":"theme"|"colour"|"picture","colour":0..7,"picture":""|"<screenshot file name>","clock":true}
// picture "" = /data/omni/start-bg.png, else a PNG in the Screenshots folder. Continue watching on / off stays
// OMNI_CONTINUE_WATCHING_V1's own flag (continue-watching-off.flag): "cw" is never stored in "hidden".
// The start page (omni://pages/start/, start-custom.js) gets pageJson() through one fixed script after it loads.
// Shell side: OmniStartCustomShell.h. Tests: tools/test_start_custom.cpp (g++ on the host).
// OMNI_START_CUSTOM_V1_R2: closedFingerprint (the shell's change watch); a broken file is kept (badName / badToDrop).
#pragma once
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <string>
#include <utility>
#include <vector>

namespace OmniStartCustom {

constexpr const char* kFileName = "start-page.json";
constexpr const char* kUserPicture = "/data/omni/start-bg.png";
constexpr const char* kPictureUrl = "omni://pages/_user/start-bg.png";   // served by OmniBlocker.cpp's handler
constexpr const char* kUserFileName = "start-bg.png";                    // the only name the handler asks the shell for
constexpr size_t kMaxFile = 16 * 1024;
constexpr long long kMaxPicture = 8LL << 20;    // bytes; read by a worker thread into one cached copy, never on the main thread
constexpr size_t kReadingShown = 3, kClosedShown = 5, kShotsListed = 40;
constexpr int kRowId = 875;                      // Browser settings row (845-891 / 900+ partly taken; 875 free)
constexpr int kPanelKind = 7480, kPickKind = 7481;

enum Section : int { sSearch, sApps, sShortcuts, sCw, sReading, sClosed, sCount };
enum Bg : int { bgTheme, bgColour, bgPicture };

inline const char* sectionKey(int s)
{
    static const char* const k[sCount] = { "search", "apps", "shortcuts", "cw", "reading", "closed" };
    return s >= 0 && s < sCount ? k[s] : "";
}
inline const char* sectionLabel(int s)
{
    static const char* const k[sCount] = { "Search", "Your apps", "Pinned and recent sites", "Continue watching", "Reading list (latest 3)", "Recently closed tabs" };
    return s >= 0 && s < sCount ? k[s] : "";
}
inline int sectionOf(const std::string& key)
{
    for (int s = 0; s < sCount; ++s) if (key == sectionKey(s)) return s;
    return -1;
}

struct Colour { const char* name; const char* hex; };
constexpr int kColours = 8;
inline const Colour& colour(int i)
{
    static const Colour c[kColours] = {
        { "Midnight", "#0e1621" }, { "Graphite", "#2a2e35" }, { "Forest", "#173a2b" }, { "Ocean", "#12355b" },
        { "Plum", "#3b2346" }, { "Crimson", "#561a1d" }, { "Sand", "#b9a57c" }, { "Snow", "#e9edf1" } };
    return c[(i % kColours + kColours) % kColours];
}

struct Config {
    std::vector<int> order;       // every section once
    bool hidden[sCount] = {};     // hidden[sCw] unused (the Continue watching flag decides)
    int bg = bgTheme, colour = 0;
    std::string picture;          // bgPicture: "" = kUserPicture, else a screenshot file name
    bool clock = false;
};
inline Config defaults()
{
    Config c;
    for (int s = 0; s < sCount; ++s) c.order.push_back(s);
    return c;
}
inline bool sameAsDefault(const Config& c)
{
    const Config d = defaults();
    if (c.order != d.order || c.bg != d.bg || c.clock != d.clock) return false;
    for (int s = 0; s < sCount; ++s) if (s != sCw && c.hidden[s]) return false;
    return true;
}
inline bool defaultOrder(const Config& c) { return c.order == defaults().order; }

// A screenshot file name the picture may be: "*.png" / "*.jpg" / "*.jpeg" (any case), no path, not hidden, printable,
// <= 200 bytes. The content decides in the end (pictureMime).
inline bool validPictureName(const std::string& n)
{
    if (n.size() < 5 || n.size() > 200 || n[0] == '.') return false;
    for (unsigned char c : n) if (c < 0x20 || c == 0x7f || c == '/' || c == '\\' || c == '"') return false;
    const size_t dot = n.rfind('.');
    if (dot == std::string::npos || dot == 0) return false;
    std::string e = n.substr(dot);
    for (auto& c : e) if (c >= 'A' && c <= 'Z') c = char(c - 'A' + 'a');
    return e == ".png" || e == ".jpg" || e == ".jpeg";
}
// The picture's type from its first bytes: PNG (89 50 4E 47 0D 0A 1A 0A) or JPEG (FF D8 FF); "" for anything else.
inline const char* pictureMime(const unsigned char* d, size_t n)
{
    static const unsigned char png[8] = { 0x89, 'P', 'N', 'G', 0x0d, 0x0a, 0x1a, 0x0a };
    if (d && n >= 8 && memcmp(d, png, 8) == 0) return "image/png";
    if (d && n >= 3 && d[0] == 0xff && d[1] == 0xd8 && d[2] == 0xff) return "image/jpeg";
    return "";
}
// The cached copy's key: another file, or the same file changed (time or size), is read again.
inline std::string pictureKey(const std::string& path, long long mtime, long long size)
{
    return path + "|" + std::to_string(mtime) + "|" + std::to_string(size);
}
// The file the start page's picture comes from ("" when the background is not a usable picture).
inline std::string picturePath(const Config& c, const std::string& shotDir)
{
    if (c.bg != bgPicture) return std::string();
    if (c.picture.empty()) return kUserPicture;
    if (!validPictureName(c.picture) || shotDir.empty()) return std::string();
    return shotDir + "/" + c.picture;
}

// --- moving and toggling ---------------------------------------------------------------------------------------------
inline int position(const Config& c, int section)
{
    for (size_t i = 0; i < c.order.size(); ++i) if (c.order[i] == section) return int(i);
    return -1;
}
// dir -1 up, +1 down; false at an end (nothing changes).
inline bool move(Config& c, int section, int dir)
{
    const int i = position(c, section), j = i + dir;
    if (i < 0 || (dir != -1 && dir != 1) || j < 0 || j >= int(c.order.size())) return false;
    std::swap(c.order[size_t(i)], c.order[size_t(j)]);
    return true;
}
// Background choices for D-pad left / right: theme, the 8 colours, the picture (when one is set or allowed).
inline int choiceOf(const Config& c) { return c.bg == bgTheme ? 0 : c.bg == bgColour ? 1 + ((c.colour % kColours + kColours) % kColours) : 1 + kColours; }
inline void setChoice(Config& c, int choice)
{
    if (choice <= 0) { c.bg = bgTheme; return; }
    if (choice <= kColours) { c.bg = bgColour; c.colour = choice - 1; return; }
    c.bg = bgPicture;
}
inline void stepBackground(Config& c, int dir, bool pictureAvailable)
{
    const int n = 1 + kColours + (pictureAvailable ? 1 : 0);
    int k = choiceOf(c);
    if (k >= n) k = 0;
    setChoice(c, ((k + dir) % n + n) % n);
}
inline std::string backgroundText(const Config& c)
{
    if (c.bg == bgColour) return colour(c.colour).name;
    if (c.bg == bgPicture) return c.picture.empty() ? std::string("Your picture (start-bg.png)") : "Screenshot " + c.picture;
    return "Theme default";
}

// --- JSON ---------------------------------------------------------------------------------------------------------------
struct Json {
    enum T { tNull, tBool, tNum, tStr, tArr, tObj } t = tNull;
    bool b = false;
    double n = 0;
    std::string s;
    std::vector<Json> a;
    std::map<std::string, Json> o;
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
        for (size_t k = 0; k < 4; ++k) {
            const char c = s[i + k];
            v <<= 4;
            if (c >= '0' && c <= '9') v |= unsigned(c - '0');
            else if (c >= 'a' && c <= 'f') v |= unsigned(c - 'a' + 10);
            else if (c >= 'A' && c <= 'F') v |= unsigned(c - 'A' + 10);
            else return false;
        }
        i += 4;
        return true;
    }
    bool str(std::string& out)
    {
        out.clear();
        if (i >= s.size() || s[i] != '"') return false;
        for (++i; i < s.size();) {
            const char c = s[i++];
            if (c == '"') return true;
            if ((unsigned char)c < 0x20) return false;
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
                v.o[k] = std::move(x);
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
inline bool parseJson(const std::string& text, Json& out)
{
    if (text.size() > kMaxFile) return false;
    Parser p { text };
    if (!p.value(out)) return false;
    p.ws();
    return p.i == text.size();
}

// The file -> Config. Anything unknown is ignored; a missing / broken file is the defaults (false).
inline bool parse(const std::string& text, Config& c)
{
    c = defaults();
    Json j;
    if (!parseJson(text, j) || j.t != Json::tObj) return false;
    auto get = [&](const char* k) -> const Json* { auto it = j.o.find(k); return it == j.o.end() ? nullptr : &it->second; };
    if (const Json* o = get("order"); o && o->t == Json::tArr) {
        std::vector<int> order;
        for (const Json& x : o->a) {
            const int s = x.t == Json::tStr ? sectionOf(x.s) : -1;
            bool dup = false;
            for (int y : order) dup = dup || y == s;
            if (s >= 0 && !dup) order.push_back(s);
        }
        for (int s = 0; s < sCount; ++s) {   // a section the file does not name (a newer list): after its default predecessor
            bool seen = false;
            for (int y : order) seen = seen || y == s;
            if (seen) continue;
            size_t at = 0;
            for (int p = s - 1; p >= 0 && !at; --p)
                for (size_t k = 0; k < order.size(); ++k) if (order[k] == p) { at = k + 1; break; }
            order.insert(order.begin() + long(at), s);
        }
        c.order = order;
    }
    if (const Json* h = get("hidden"); h && h->t == Json::tArr)
        for (const Json& x : h->a) { const int s = x.t == Json::tStr ? sectionOf(x.s) : -1; if (s >= 0 && s != sCw) c.hidden[s] = true; }
    if (const Json* b = get("bg"); b && b->t == Json::tStr) c.bg = b->s == "colour" ? bgColour : b->s == "picture" ? bgPicture : bgTheme;
    if (const Json* k = get("colour"); k && k->t == Json::tNum && k->n >= 0 && k->n < kColours) c.colour = int(k->n);
    if (const Json* p = get("picture"); p && p->t == Json::tStr && (p->s.empty() || validPictureName(p->s))) c.picture = p->s;
    else if (c.bg == bgPicture && p) c.bg = bgTheme;   // a picture name that is not allowed: the theme
    if (const Json* k = get("clock"); k && k->t == Json::tBool) c.clock = k->b;
    return true;
}

// A JSON string literal that is also safe inside a <script>-less JavaScript source (U+2028 / U+2029, '<' escaped).
inline std::string quote(const std::string& s)
{
    std::string o = "\"";
    for (size_t i = 0; i < s.size(); ++i) {
        const unsigned char c = (unsigned char)s[i];
        if (c == '"' || c == '\\') { o += '\\'; o += char(c); }
        else if (c < 0x20 || c == 0x7f) { char b[8]; snprintf(b, sizeof b, "\\u%04x", c); o += b; }
        else if (c == 0xe2 && i + 2 < s.size() && (unsigned char)s[i + 1] == 0x80 && ((unsigned char)s[i + 2] == 0xa8 || (unsigned char)s[i + 2] == 0xa9)) {
            o += (unsigned char)s[i + 2] == 0xa8 ? "\\u2028" : "\\u2029";
            i += 2;
        } else if (c == '<') o += "\\u003c";
        else o += char(c);
    }
    return o + "\"";
}
inline std::string serialize(const Config& c)
{
    std::string o = "{\"v\":1,\"order\":[";
    for (size_t i = 0; i < c.order.size(); ++i) o += (i ? "," : "") + quote(sectionKey(c.order[i]));
    o += "],\"hidden\":[";
    bool first = true;
    for (int s : c.order) if (s != sCw && c.hidden[s]) { o += (first ? "" : ",") + quote(sectionKey(s)); first = false; }
    o += "],\"bg\":";
    o += quote(c.bg == bgColour ? "colour" : c.bg == bgPicture ? "picture" : "theme");
    o += ",\"colour\":" + std::to_string((c.colour % kColours + kColours) % kColours);
    o += ",\"picture\":" + quote(c.picture);
    o += std::string(",\"clock\":") + (c.clock ? "true" : "false") + "}\n";
    return o;
}

// --- what the start page gets ------------------------------------------------------------------------------------------
struct Reading { std::string id, title, site, when; };   // a saved page (Reading list)
struct Closed { std::string url, title, site; };         // a recently closed tab
inline std::string cleanText(const std::string& s, size_t max)
{
    std::string o;
    for (unsigned char c : s) o += (c < 0x20 || c == 0x7f) ? ' ' : char(c);
    if (o.size() <= max) return o;
    size_t n = max;
    while (n && (static_cast<unsigned char>(o[n]) & 0xc0) == 0x80) --n;
    return o.substr(0, n) + "\xE2\x80\xA6";
}
// "example.com" from "https://user@www.Example.com:8443/x" (lowercase, no "www.", no port).
inline std::string site(const std::string& url)
{
    size_t b = url.find("://");
    if (b == std::string::npos) return std::string();
    b += 3;
    const size_t e = url.find_first_of("/?#", b);
    std::string h = url.substr(b, e == std::string::npos ? std::string::npos : e - b);
    const size_t at = h.rfind('@');
    if (at != std::string::npos) h = h.substr(at + 1);
    if (!h.empty() && h[0] == '[') { const size_t r = h.find(']'); h = h.substr(0, r == std::string::npos ? h.size() : r + 1); }
    else { const size_t c = h.find(':'); if (c != std::string::npos) h = h.substr(0, c); }
    for (auto& c : h) if (c >= 'A' && c <= 'Z') c += 'a' - 'A';
    if (h.rfind("www.", 0) == 0) h = h.substr(4);
    return h;
}
// The newest `max` closed tabs (the shell's list is newest last), one per address.
inline std::vector<Closed> newestClosed(const std::vector<std::pair<std::string, std::string>>& list, size_t max = kClosedShown)
{
    std::vector<Closed> out;
    for (size_t i = list.size(); i-- > 0 && out.size() < max;) {
        bool dup = false;
        for (auto& o : out) dup = dup || o.url == list[i].first;
        if (dup) continue;
        out.push_back({ list[i].first, list[i].second, site(list[i].first) });
    }
    return out;
}
// OMNI_START_CUSTOM_V1_R2: a cheap fingerprint of the shell's closed-tab list (<= 10 entries): any push, pop, erase or
// clear changes it (the shell compares it once a second instead of rebuilding the page data).
inline uint64_t closedFingerprint(const std::vector<std::pair<std::string, std::string>>& list)
{
    uint64_t h = 1469598103934665603ull ^ list.size();
    auto mix = [&h](const std::string& s) {
        for (unsigned char ch : s) { h ^= ch; h *= 1099511628211ull; }
        h ^= 0xff; h *= 1099511628211ull;   // a separator: ("ab","c") != ("a","bc")
    };
    for (const auto& e : list) { mix(e.first); mix(e.second); }
    return h;
}
// pictureVersion: changes whenever the picture does (the page asks for it again); cwOn: Continue watching's own flag.
inline std::string pageJson(const Config& c, bool privateTab, bool cwOn, const std::vector<Reading>& reading,
    const std::vector<Closed>& closed, const std::string& pictureVersion, const std::string& hint)
{
    std::string o = "{\"v\":1,\"order\":[";
    for (size_t i = 0; i < c.order.size(); ++i) o += (i ? "," : "") + quote(sectionKey(c.order[i]));
    o += "],\"hidden\":[";
    bool first = true;
    for (int s = 0; s < sCount; ++s) {
        const bool off = s == sCw ? (!cwOn || privateTab) : s == sClosed ? (c.hidden[s] || privateTab) : c.hidden[s];
        if (off) { o += (first ? "" : ",") + quote(sectionKey(s)); first = false; }
    }
    o += "],\"bg\":{\"kind\":";
    if (c.bg == bgColour) o += quote("colour") + ",\"value\":" + quote(colour(c.colour).hex);
    else if (c.bg == bgPicture && !pictureVersion.empty()) o += quote("picture") + ",\"url\":" + quote(std::string(kPictureUrl) + "?v=" + pictureVersion);
    else o += quote("theme");
    o += std::string("},\"clock\":") + (c.clock ? "true" : "false") + ",\"private\":" + (privateTab ? "true" : "false");
    o += ",\"linear\":" + std::string(defaultOrder(c) ? "false" : "true");
    o += ",\"reading\":[";
    for (size_t i = 0; i < reading.size() && i < kReadingShown; ++i)
        o += (i ? "," : "") + std::string("{\"id\":") + quote(reading[i].id) + ",\"t\":" + quote(cleanText(reading[i].title.empty() ? reading[i].site : reading[i].title, 200))
            + ",\"s\":" + quote(reading[i].site) + ",\"d\":" + quote(reading[i].when) + "}";
    o += "],\"closed\":[";
    if (!privateTab)
        for (size_t i = 0; i < closed.size() && i < kClosedShown; ++i)
            o += (i ? "," : "") + std::string("{\"u\":") + quote(closed[i].url) + ",\"t\":" + quote(cleanText(closed[i].title.empty() ? closed[i].site : closed[i].title, 200))
                + ",\"s\":" + quote(closed[i].site) + "}";
    return o + "],\"hint\":" + quote(hint) + "}";
}

// Bridge arguments: a reading-list id (the file name in the reading-list folder) or a closed tab's address.
inline bool validReadingId(const std::string& id)
{
    if (id.empty() || id.size() > 255 || id[0] == '.') return false;
    for (unsigned char c : id) if (c <= 0x20 || c == 0x7f || c == '/' || c == '\\') return false;
    return true;
}

// --- a settings file that does not parse (OMNI_START_CUSTOM_V1_R2) ----------------------------------------------------
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

} // namespace OmniStartCustom
'''

SHELL = r'''// OMNI_START_CUSTOM_V1: "Customise start page" (shell side). Included from OmniFeatures3.h after the other shells
// (inside OmniBrowser.cpp's anonymous namespace). The pure part is OmniStartCustom.h; the reasons are in
// tools/apply_start_custom.py.
//   - Settings: /data/omni/start-page.json, read once on first use, written through omniIoQueue after each change
//     (only then: a file that does not parse is kept as start-page.json.bad-<time>, OMNI_START_CUSTOM_V1_R2).
//   - The start page (omni://pages/start/, pages bundle start-custom.js) gets OSCU::pageJson through ONE fixed script
//     after it loads (and when a start-page tab is shown again and its data changed): no page text is evaluated.
//   - The page asks back through window.omnibloomHost.request() methods "start.*" (OmniPages.h's bridge): open this
//     panel (the page's gear button), open a Reading list entry / the Reading list, reopen a recently closed tab.
//   - The picture background is served as omni://pages/_user/start-bg.png by OmniBlocker.cpp's pages handler from ONE
//     cached in-memory copy (omniScuUserFile): a worker thread reads the chosen file (/data/omni/start-bg.png or a
//     screenshot; <= 8 MB, PNG / JPEG by its first bytes) once per path + mtime + size. The main thread only stat()s;
//     the page gets the picture's address only once the copy is ready (the tick then redraws the start pages).
// Main thread only; nothing per frame (the tick looks at the active start page at most once a second, and since
// OMNI_START_CUSTOM_V1_R2 rebuilds its data only when the change generation omniScuGen moved).
#pragma once

namespace OSCU = OmniStartCustom;

static OSCU::Config omniScuCfg;
static bool omniScuLoaded = false, omniScuRegistered = false;
static std::map<WKPageRef, std::string> omniScuDrawn;   // what each start page was given last
struct OmniScuAct { int kind = 0; WKPageRef page = nullptr; std::string text; };
static std::vector<OmniScuAct> omniScuQueue;            // bridge requests, done on the next tick
enum { omniScuActPanel = 1, omniScuActReading, omniScuActReadingAll, omniScuActLoad };
static std::vector<std::string> omniScuShots;           // the picture picker's screenshots (listed when it opens)
static uint32_t omniScuCheckedAt = 0;
// OMNI_START_CUSTOM_V1_R2: the data generation. Anything a start page shows bumps it; a page whose drawn generation is
// current is not rebuilt (omniScuRender). Main thread only.
static uint64_t omniScuGen = 1;
static std::map<WKPageRef, uint64_t> omniScuDrawnGen;
struct OmniScuSeen { size_t rlSize = 0; bool rlLoaded = false; std::string rlLast; uint64_t closed = 0; bool icons = false, cw = false; long long hour = -1; };
static OmniScuSeen omniScuSeen;

// OMNI_START_CUSTOM_V1_R2: the file did not parse. It is kept as <name>.bad-<unix time> (at most 3; OSCU::badToDrop) and
// the defaults are used; nothing is written until the user changes something (the only writer is that change's save).
static void omniScuKeepBad(const std::string& path)
{
    const size_t slash = path.rfind('/');
    const std::string dir = slash == std::string::npos ? std::string(".") : path.substr(0, slash);
    const std::string name = slash == std::string::npos ? path : path.substr(slash + 1);
    const std::string bad = OSCU::badName(name, (long long)time(nullptr));
    const bool kept = rename(path.c_str(), (dir + "/" + bad).c_str()) == 0;
    std::vector<std::string> files;
    if (DIR* d = opendir(dir.c_str())) {
        while (dirent* e = readdir(d)) if (files.size() < 1000 && OSCU::badTime(e->d_name, name) >= 0) files.emplace_back(e->d_name);
        closedir(d);
    }
    for (const auto& f : OSCU::badToDrop(files, name)) unlink((dir + "/" + f).c_str());
    fprintf(stderr, "OMNI_START_CUSTOM_V1: %s unreadable, %s%s; defaults used (nothing is written until a change)\n", name.c_str(),
            kept ? "kept as " : "could not be renamed", kept ? bad.c_str() : "");
}
static OSCU::Config& omniScuConfig()
{
    if (omniScuLoaded) return omniScuCfg;
    omniScuLoaded = true;
    omniScuCfg = OSCU::defaults();
    std::string text;
    if (FILE* f = fopen(omniData(OSCU::kFileName).c_str(), "rb")) {
        char buf[4096];
        size_t n;
        while ((n = fread(buf, 1, sizeof buf, f)) > 0 && text.size() <= OSCU::kMaxFile) text.append(buf, n);
        fclose(f);
        if (!OSCU::parse(text, omniScuCfg)) omniScuKeepBad(omniData(OSCU::kFileName));   // OMNI_START_CUSTOM_V1_R2
    }
    return omniScuCfg;
}
static bool omniScuStartTab(const Tab* t) { return t && t->omniPagesTab && t->omniNewTabPage && !t->crashed; }
static bool omniScuFileOk(const std::string& path, struct stat* out = nullptr)
{
    struct stat st {};
    if (path.empty() || stat(path.c_str(), &st) || !S_ISREG(st.st_mode) || st.st_size <= 0 || st.st_size > OSCU::kMaxPicture) return false;
    if (out) *out = st;
    return true;
}
// The picture's cached copy (the worker thread fills it under the lock; the main thread reads it).
struct OmniScuPicture {
    std::mutex m;
    std::string key, failedKey;                          // what `bytes` holds / the last read that was refused
    std::shared_ptr<const std::vector<uint8_t>> bytes;
    std::string mime;
    bool loading = false, done = false;                 // done: a read finished (the tick redraws)
};
static OmniScuPicture omniScuPic;
static std::string omniScuPicWant;                      // main thread: the key the current settings need ("" none)
static void omniScuPicLoad(const std::string& key, const std::string& path)
{
    std::thread([key, path] {
        auto buf = std::make_shared<std::vector<uint8_t>>();
        std::string mime;
        if (FILE* f = fopen(path.c_str(), "rb")) {
            unsigned char chunk[65536];
            size_t n;
            while (buf->size() <= size_t(OSCU::kMaxPicture) && (n = fread(chunk, 1, sizeof chunk, f)) > 0) buf->insert(buf->end(), chunk, chunk + n);
            fclose(f);
            if (!buf->empty() && buf->size() <= size_t(OSCU::kMaxPicture)) mime = OSCU::pictureMime(buf->data(), buf->size());
        }
        std::lock_guard<std::mutex> g(omniScuPic.m);
        omniScuPic.loading = false;
        omniScuPic.done = true;
        if (mime.empty()) { omniScuPic.failedKey = key; fprintf(stderr, "OMNI_START_CUSTOM_V1: picture not used (not PNG / JPEG, empty or over 8 MB)\n"); return; }
        omniScuPic.key = key;
        omniScuPic.bytes = std::move(buf);
        omniScuPic.mime = mime;
    }).detach();
}
// OmniBlocker.cpp's pages handler (main thread): omni://pages/_user/start-bg.png from the cached copy only, never a read.
static bool omniScuUserFile(const std::string& name, std::vector<uint8_t>& data, std::string& mime)
{
    if (name != OSCU::kUserFileName || omniScuPicWant.empty()) return false;
    std::lock_guard<std::mutex> g(omniScuPic.m);
    if (!omniScuPic.bytes || omniScuPic.key != omniScuPicWant) return false;
    data = *omniScuPic.bytes;
    mime = omniScuPic.mime;
    return true;
}
// Changes whenever the picture does (the page then asks for it again); "" while no ready copy matches. Starts the
// worker read when the settings need a copy that is not cached; drops the copy when no picture is in use.
static std::string omniScuPictureVersion(const OSCU::Config& c)
{
    struct stat st {};
    const std::string path = OSCU::picturePath(c, OmniQuickActions::kShotDir);
    if (!omniScuFileOk(path, &st)) {
        omniScuPicWant.clear();
        std::lock_guard<std::mutex> g(omniScuPic.m);
        if (!omniScuPic.loading) { omniScuPic.bytes.reset(); omniScuPic.key.clear(); }
        return std::string();
    }
    omniScuPicWant = OSCU::pictureKey(path, (long long)st.st_mtime, (long long)st.st_size);
    {
        std::lock_guard<std::mutex> g(omniScuPic.m);
        if (omniScuPic.key != omniScuPicWant || !omniScuPic.bytes) {
            if (!omniScuPic.loading && omniScuPic.failedKey != omniScuPicWant) { omniScuPic.loading = true; omniScuPicLoad(omniScuPicWant, path); }
            return std::string();
        }
    }
    return std::to_string((long long)st.st_mtime) + "-" + std::to_string((long long)st.st_size) + "-" + std::to_string(std::hash<std::string>{}(c.picture) & 0xffff);
}
static std::vector<OSCU::Reading> omniScuReading()
{
    omniRlEnsureLoading();   // once per run, on a thread; the tick redraws when it is in
    std::vector<RL::Entry> list;
    { std::lock_guard<std::mutex> g(omniRlLock); list = omniRlList; }
    list = RL::newestFirst(std::move(list));
    std::vector<OSCU::Reading> out;
    const time_t now = time(nullptr);
    for (size_t i = 0; i < list.size() && out.size() < OSCU::kReadingShown; ++i)
        out.push_back({ list[i].id, list[i].title, RL::site(list[i].url), RL::dateText(time_t(list[i].savedAt), now) });
    return out;
}

// One fixed script; %DATA% is OSCU::pageJson (a JSON literal). start-custom.js may still be loading: it then picks the
// data up from window.__omniStartCustom itself.
static const char* const omniScuScript = "(function(D){window.__omniStartCustom=D;var f=window.omniStartCustomApply;"
    "return typeof f==='function'?String(f(D)):'later'})(%DATA%)";
// OMNI_START_CUSTOM_V1_R2: once a second while a drawn start page is the active tab: O(1) / O(10) looks, no copy, sort
// or stat (the reading list's size / loaded flag / last id under its lock, the closed tabs' fingerprint, the button
// style, Continue watching's cached flag, the hour). Anything different bumps omniScuGen.
static void omniScuWatch()
{
    bool changed = false;
    {
        static const std::string none;
        std::lock_guard<std::mutex> g(omniRlLock);
        const std::string& last = omniRlList.empty() ? none : omniRlList.back().id;   // a save is a push_back
        if (omniRlList.size() != omniScuSeen.rlSize || omniRlLoaded != omniScuSeen.rlLoaded || last != omniScuSeen.rlLast) {
            omniScuSeen.rlSize = omniRlList.size(); omniScuSeen.rlLoaded = omniRlLoaded; omniScuSeen.rlLast = last;
            changed = true;
        }
    }
    const uint64_t closed = OSCU::closedFingerprint(omniFxClosed);
    const bool cw = omniCwOn();
    const long long hour = (long long)(time(nullptr) / 3600);
    if (closed != omniScuSeen.closed || playStationIcons != omniScuSeen.icons || cw != omniScuSeen.cw || hour != omniScuSeen.hour) {
        omniScuSeen.closed = closed; omniScuSeen.icons = playStationIcons; omniScuSeen.cw = cw; omniScuSeen.hour = hour;
        changed = true;
    }
    if (changed) ++omniScuGen;
}
static void omniScuRender(Tab* tab, bool force)
{
    if (!tab || tab->loading || tab->crashed || omniTestMode()) return;
    const auto seen = omniScuDrawnGen.find(tab->page);
    if (!force && seen != omniScuDrawnGen.end() && seen->second == omniScuGen) return;   // R2: nothing it shows changed
    if (omniScuDrawnGen.size() > 64) omniScuDrawnGen.clear();
    omniScuDrawnGen[tab->page] = omniScuGen;
    const OSCU::Config& c = omniScuConfig();
    const std::string hint = playStationIcons ? "\xC3\x97 Open" : "A Open";
    const std::string data = OSCU::pageJson(c, tab->omniPrivate, omniCwOn(), omniScuReading(), OSCU::newestClosed(omniFxClosed),
        omniScuPictureVersion(c), hint);
    const auto it = omniScuDrawn.find(tab->page);
    if (!force && it != omniScuDrawn.end() && it->second == data) return;
    if (omniScuDrawn.size() > 64) omniScuDrawn.clear();
    omniScuDrawn[tab->page] = data;
    std::string js = omniScuScript;
    js.replace(js.find("%DATA%"), 6, data);
    auto source = adoptWK(WKStringCreateWithUTF8CString(js.c_str()));
    WKPageEvaluateJavaScriptInMainFrame(tab->page, source.get(), nullptr, [](WKTypeRef, WKErrorRef, void*) { });
}
static void omniScuRenderAll()
{
    for (auto& t : tabs) if (omniScuStartTab(t.get()) && omniScuDrawn.count(t->page)) omniScuRender(t.get(), true);
}
static void omniScuSave(const char* what)
{
    ++omniScuGen;   // OMNI_START_CUSTOM_V1_R2
    omniIoQueue(omniData(OSCU::kFileName), OSCU::serialize(omniScuConfig()), false);
    omniScuRenderAll();
    if (what) notice(what);
}
// omniEverydayFinished(): a page finished loading (tab.url not cleared yet). Only Omni's built-in start page.
static void omniScuFinished(Tab& tab)
{
    omniScuDrawn.erase(tab.page);   // a fresh document has nothing yet
    omniScuDrawnGen.erase(tab.page);
    if (tab.url.rfind("omni://pages/start/", 0) != 0) return;
    if (!omniScuRegistered) { omniScuRegistered = true; omniPagesSetUserFile(omniScuUserFile); }
    omniScuRender(&tab, true);
}
// omniEverydayActivated(): a start page shown again (closed tabs or the reading list may have changed): compared in full
// (R2: its generation is forgotten, so the data is built and compared once).
static void omniScuActivated(Tab* tab)
{
    if (!omniScuStartTab(tab) || !omniScuDrawn.count(tab->page)) return;
    omniScuDrawnGen.erase(tab->page);
    omniScuRender(tab, false);
}

// --- the panel (Browser settings > Customise start page..., or the start page's gear) ----------------------------------
enum { omniScuRowSection = 100, omniScuRowBg = 200, omniScuRowClock, omniScuRowReset,
    omniScuPickTheme = 300, omniScuPickColour = 310, omniScuPickUser = 330, omniScuPickShot = 400 };
static bool omniScuShown(const OSCU::Config& c, int s) { return s == OSCU::sCw ? omniCwOn() : !c.hidden[s]; }
static bool omniScuPictureAvailable(const OSCU::Config& c)
{
    OSCU::Config t = c;
    t.bg = OSCU::bgPicture;
    return omniScuFileOk(OSCU::picturePath(t, OmniQuickActions::kShotDir));
}
static void omniScuBuild(OmniFxPanel& p)
{
    const OSCU::Config& c = omniScuConfig();
    const int n = int(c.order.size());
    for (int i = 0; i < n; ++i) {
        const int s = c.order[size_t(i)];
        OmniFxRow r; r.id = omniScuRowSection + s; r.label = OSCU::sectionLabel(s); r.stepper = true;
        r.value = omniScuShown(c, s) ? "Shown" : "Hidden";
        r.detail = std::to_string(i + 1) + " of " + std::to_string(n);
        if (s == OSCU::sSearch) r.detail += " \xc2\xb7 hidden: the search box only";
        if (s == OSCU::sCw || s == OSCU::sClosed) r.detail += " \xc2\xb7 never in private tabs";
        p.rows.push_back(r);
    }
    OmniFxRow bg; bg.id = omniScuRowBg; bg.label = "Background"; bg.value = OSCU::backgroundText(c); bg.stepper = true;
    bg.detail = c.bg == OSCU::bgPicture && !omniScuPictureAvailable(c) ? "Picture missing: the theme shows" : "Cross: colours and pictures";
    p.rows.push_back(bg);
    OmniFxRow clock; clock.id = omniScuRowClock; clock.label = "Clock"; clock.value = c.clock ? "On" : "Off"; clock.stepper = true;
    p.rows.push_back(clock);
    OmniFxRow reset; reset.id = omniScuRowReset; reset.label = "Reset to default"; reset.enabled = !OSCU::sameAsDefault(c);
    p.rows.push_back(reset);
    p.subtitle = OSCU::sameAsDefault(c) ? "Default layout" : OSCU::defaultOrder(c) ? "Customised" : "Customised \xc2\xb7 one column, in your order";
}
static void omniScuPickBuild(OmniFxPanel& p)
{
    const OSCU::Config& c = omniScuConfig();
    auto add = [&](int id, std::string label, std::string detail, bool on, bool enabled) {
        OmniFxRow r; r.id = id; r.label = std::move(label); r.detail = std::move(detail); r.value = on ? "In use" : ""; r.enabled = enabled;
        p.rows.push_back(r);
    };
    add(omniScuPickTheme, "Theme default", "The Universe's own background", c.bg == OSCU::bgTheme, true);
    for (int i = 0; i < OSCU::kColours; ++i)
        add(omniScuPickColour + i, OSCU::colour(i).name, OSCU::colour(i).hex, c.bg == OSCU::bgColour && c.colour == i, true);
    const bool user = omniScuFileOk(OSCU::kUserPicture);
    add(omniScuPickUser, "Your picture", user ? std::string(OSCU::kUserPicture) : std::string("Put a PNG or JPEG (8 MB at most) at ") + OSCU::kUserPicture,
        c.bg == OSCU::bgPicture && c.picture.empty(), user);
    for (size_t i = 0; i < omniScuShots.size(); ++i)
        add(omniScuPickShot + int(i), omniScuShots[i], "Screenshots", c.bg == OSCU::bgPicture && c.picture == omniScuShots[i], true);
    p.subtitle = omniScuShots.empty() ? "No screenshots yet (L2 + R3 on a page)" : std::to_string(omniScuShots.size()) + " newest screenshots";
}
static bool omniScuPickInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A || !r.enabled) return false;
    OSCU::Config& c = omniScuConfig();
    if (r.id == omniScuPickTheme) c.bg = OSCU::bgTheme;
    else if (r.id >= omniScuPickColour && r.id < omniScuPickColour + OSCU::kColours) { c.bg = OSCU::bgColour; c.colour = r.id - omniScuPickColour; }
    else if (r.id == omniScuPickUser) { c.bg = OSCU::bgPicture; c.picture.clear(); }
    else if (r.id >= omniScuPickShot && size_t(r.id - omniScuPickShot) < omniScuShots.size()) { c.bg = OSCU::bgPicture; c.picture = omniScuShots[size_t(r.id - omniScuPickShot)]; }
    else return false;
    omniScuSave(("Start page background: " + OSCU::backgroundText(c)).c_str());
    omniFxPop();
    return true;
}
static void omniScuPickShow()
{
    omniScuShots.clear();
    std::vector<std::pair<long long, std::string>> found;   // newest first, PNG screenshots only
    if (DIR* d = opendir(OmniQuickActions::kShotDir)) {
        size_t looked = 0;
        while (dirent* e = readdir(d)) {
            if (++looked > 20000) break;
            const std::string name = e->d_name;
            struct stat st {};
            if (!OSCU::validPictureName(name) || !omniScuFileOk(std::string(OmniQuickActions::kShotDir) + "/" + name, &st)) continue;
            found.emplace_back((long long)st.st_mtime, name);
        }
        closedir(d);
    }
    std::sort(found.begin(), found.end(), [](const auto& a, const auto& b) { return a.first != b.first ? a.first > b.first : a.second > b.second; });
    for (size_t i = 0; i < found.size() && i < OSCU::kShotsListed; ++i) omniScuShots.push_back(found[i].second);
    OmniFxPanel p;
    p.kind = OSCU::kPickKind; p.title = "Start page background"; p.w = 820; p.maxVisible = 9;
    p.build = omniScuPickBuild; p.input = omniScuPickInput;
    p.faces = { { 0, "Use" }, { 1, "Back" } };
    omniFxPush(std::move(p));
}
static bool omniScuInput(OmniFxPanel& p, const OmniFxRow& r, int b)
{
    OSCU::Config& c = omniScuConfig();
    const bool a = b == SDL_CONTROLLER_BUTTON_A, left = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT, right = b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT;
    if (r.id >= omniScuRowSection && r.id < omniScuRowSection + int(OSCU::sCount)) {
        const int s = r.id - omniScuRowSection;
        if (a || left || right) {
            if (s == OSCU::sCw) { omniCwSettingsInput(SDL_CONTROLLER_BUTTON_A); ++omniScuGen; omniScuRenderAll(); return true; }   // its own flag and notice
            c.hidden[s] = !c.hidden[s];
            omniScuSave((std::string(OSCU::sectionLabel(s)) + (c.hidden[s] ? " hidden on the start page" : " shown on the start page")).c_str());
            return true;
        }
        if (b == SDL_CONTROLLER_BUTTON_X || b == SDL_CONTROLLER_BUTTON_Y) {   // Square up, Triangle down
            const int dir = b == SDL_CONTROLLER_BUTTON_X ? -1 : 1;
            if (!OSCU::move(c, s, dir)) { notice(dir < 0 ? "Already at the top" : "Already at the bottom"); return true; }
            p.sel = OSCU::position(c, s);   // the rows follow the order: the moved row keeps the focus
            omniScuSave(nullptr);
            return true;
        }
        return false;
    }
    switch (r.id) {
    case omniScuRowBg:
        if (a) { omniScuPickShow(); return true; }
        if (!left && !right) return false;
        OSCU::stepBackground(c, left ? -1 : 1, omniScuPictureAvailable(c));
        omniScuSave(nullptr);
        return true;
    case omniScuRowClock:
        if (!a && !left && !right) return false;
        c.clock = !c.clock;
        omniScuSave(c.clock ? "Clock shown on the start page" : "Clock hidden");
        return true;
    case omniScuRowReset:
        if (!a || !r.enabled) return false;
        c = OSCU::defaults();
        omniScuSave("Start page back to the default layout");
        return true;
    }
    return false;
}
static void omniScuShow()
{
    OmniFxPanel p;
    p.kind = OSCU::kPanelKind; p.title = "Customise start page"; p.w = 820; p.maxVisible = 9;
    p.build = omniScuBuild; p.input = omniScuInput;
    p.faces = { { 0, "Show / hide" }, { 2, "Move up" }, { 3, "Move down" }, { 1, "Back" } };
    p.extra = "Background: D-pad \xe2\x97\x80 \xe2\x96\xb6 steps, Cross picks";
    omniFxPush(std::move(p));
}
// Browser settings row value.
static std::string omniScuSummary() { return OSCU::sameAsDefault(omniScuConfig()) ? "Default" : "Customised"; }

// --- the page's requests (OmniPages.h: request() methods "start.*") -----------------------------------------------------
static std::string omniScuBridge(WKPageRef page, Tab& tab, const std::string& method, const std::string& arg)
{
    auto err = [](const char* code) { return std::string("{\"ok\":false,\"code\":\"") + code + "\"}"; };
    const std::string ok = "{\"ok\":true,\"result\":null}";
    if (!omniScuStartTab(&tab)) return err("UNSUPPORTED");
    if (method == "start.customise") { omniScuQueue.push_back({ omniScuActPanel, page, std::string() }); return ok; }
    if (method == "start.reading.all") { omniScuQueue.push_back({ omniScuActReadingAll, page, std::string() }); return ok; }
    if (method == "start.reading.open") {
        if (!OSCU::validReadingId(arg)) return err("INVALID_VALUE");
        bool found = false;
        { std::lock_guard<std::mutex> g(omniRlLock); for (const auto& e : omniRlList) found = found || e.id == arg; }
        if (!found) return err("NOT_FOUND");
        omniScuQueue.push_back({ omniScuActReading, page, arg });
        return ok;
    }
    if (method == "start.closed.open") {
        if (tab.omniPrivate) return err("UNSUPPORTED");   // private tabs never list them
        if (!omniWebURL(arg) || arg.size() > 4096) return err("INVALID_VALUE");
        for (size_t i = omniFxClosed.size(); i-- > 0;)
            if (omniFxClosed[i].first == arg) {
                omniFxClosed.erase(omniFxClosed.begin() + long(i));
                ++omniScuGen;   // OMNI_START_CUSTOM_V1_R2
                omniScuQueue.push_back({ omniScuActLoad, page, arg });
                return ok;
            }
        return err("NOT_FOUND");
    }
    return err("UNSUPPORTED");
}
// omniF3Tick(): the queued requests; once a second the change watch for the active start page, which is rebuilt only
// when something it shows changed (R2; the reading list loads on a thread).
static void omniScuTick(uint32_t now)
{
    if (!omniScuQueue.empty()) {
        auto queue = std::move(omniScuQueue);
        omniScuQueue.clear();
        for (auto& act : queue) {
            Tab* tab = omniTabForPage(act.page);
            if (!tab || tab != active()) continue;   // only the tab the user is looking at
            if (act.kind == omniScuActPanel) { if (!editing && !settingsOpen && omniFxStack.empty()) omniScuShow(); }
            else if (act.kind == omniScuActReadingAll) { if (!editing && !settingsOpen && omniFxStack.empty()) omniRlShow(); }
            else if (act.kind == omniScuActReading) {
                RL::Entry e;
                bool found = false;
                { std::lock_guard<std::mutex> g(omniRlLock); for (const auto& x : omniRlList) if (x.id == act.text) { e = x; found = true; } }
                if (found) omniRlOpenSaved(e); else notice("That saved page is gone");
            } else if (act.kind == omniScuActLoad && omniWebURL(act.text)) {
                auto u = adoptWK(WKURLCreateWithUTF8CString(act.text.c_str()));
                WKPageLoadURL(tab->page, u.get());
            }
        }
        omniShellDirty = true;
    }
    bool picDone = false;
    { std::lock_guard<std::mutex> g(omniScuPic.m); picDone = std::exchange(omniScuPic.done, false); }
    if (picDone) {   // the picture's copy is ready (or was refused): open start pages get the new data
        ++omniScuGen;   // OMNI_START_CUSTOM_V1_R2
        for (auto& t : tabs) if (omniScuStartTab(t.get()) && omniScuDrawn.count(t->page)) omniScuRender(t.get(), false);
    }
    if (now - omniScuCheckedAt < 1000) return;
    omniScuCheckedAt = now;
    Tab* t = active();
    if (omniScuStartTab(t) && omniScuDrawn.count(t->page)) {   // R2: rebuilt only when the generation moved
        omniScuWatch();
        omniScuRender(t, false);
    }
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniControlsHelp.h" // OMNI_CONTROLS_HELP_V1: the Controls guide: shortcut table, order, layout (pure)\n',
         '#include "OmniControlsHelp.h" // OMNI_CONTROLS_HELP_V1: the Controls guide: shortcut table, order, layout (pure)\n'
         '#include "OmniStartCustom.h" // OMNI_START_CUSTOM_V1: Customise start page: order, sections, background (pure)\n'),
        ('static bool omniCwButton(int b);\n',
         'static bool omniCwButton(int b);\n'
         'static void omniScuFinished(Tab& tab);    // OMNI_START_CUSTOM_V1 (OmniStartCustomShell.h)\n'
         'static void omniScuActivated(Tab* tab);\n'),
        ('    omniCwFinished(tab); // OMNI_CONTINUE_WATCHING_V1: the start page gets its row (reads tab.url before it is cleared)\n',
         '    omniCwFinished(tab); // OMNI_CONTINUE_WATCHING_V1: the start page gets its row (reads tab.url before it is cleared)\n'
         '    omniScuFinished(tab); // OMNI_START_CUSTOM_V1: the start page gets its settings (after the row: it places it)\n'),
        ('    omniCwActivated(tab); // OMNI_CONTINUE_WATCHING_V1: a start page shown again redraws its row if the list changed\n',
         '    omniCwActivated(tab); // OMNI_CONTINUE_WATCHING_V1: a start page shown again redraws its row if the list changed\n'
         '    omniScuActivated(tab); // OMNI_START_CUSTOM_V1: and its settings / lists, if they changed\n'),
    ],
    'OmniBrowserSettings.h': [
        ('constexpr int omniCwRowId = 870; // OMNI_CONTINUE_WATCHING_V1 (OmniContinueWatchingShell.h)\n',
         'constexpr int omniCwRowId = 870; // OMNI_CONTINUE_WATCHING_V1 (OmniContinueWatchingShell.h)\n'
         'static void omniScuShow(); // OMNI_START_CUSTOM_V1 (OmniStartCustomShell.h); row id OmniStartCustom::kRowId\n'
         'static std::string omniScuSummary();\n'),
        ('    add(omniCwRowId, "Continue watching on start page", omniCwOn() ? "On" : "Off", true); // OMNI_CONTINUE_WATCHING_V1\n',
         '    add(omniCwRowId, "Continue watching on start page", omniCwOn() ? "On" : "Off", true); // OMNI_CONTINUE_WATCHING_V1\n'
         '    add(OmniStartCustom::kRowId, "Customise start page...", omniScuSummary(), false); // OMNI_START_CUSTOM_V1\n'),
        ('    if (r.id == omniCwRowId) return omniCwSettingsInput(b); // OMNI_CONTINUE_WATCHING_V1 (before the >= 300 rows)\n',
         '    if (r.id == OmniStartCustom::kRowId) { if (b != SDL_CONTROLLER_BUTTON_A) return false; omniScuShow(); return true; } // OMNI_START_CUSTOM_V1\n'
         '    if (r.id == omniCwRowId) return omniCwSettingsInput(b); // OMNI_CONTINUE_WATCHING_V1 (before the >= 300 rows)\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniControlsHelpShell.h" // OMNI_CONTROLS_HELP_V1 (after the other shells: it recognises their panels)\n',
         '#include "OmniControlsHelpShell.h" // OMNI_CONTROLS_HELP_V1 (after the other shells: it recognises their panels)\n'
         '#include "OmniStartCustomShell.h" // OMNI_START_CUSTOM_V1 (uses the reading list and the closed-tab list)\n'),
        ('    omniRlTick(now);    // OMNI_READING_LIST_V1\n',
         '    omniRlTick(now);    // OMNI_READING_LIST_V1\n'
         '    omniScuTick(now);   // OMNI_START_CUSTOM_V1: start-page requests; the active start page\'s data (at most 1/s)\n'),
    ],
    'OmniPages.h': [
        ('        if (method == "navigation.open") {\n',
         '        if (method.rfind("start.", 0) == 0) return omniScuBridge(page, *tab, method, omniPagesField(a, "url")); // OMNI_START_CUSTOM_V1 (OmniStartCustomShell.h)\n'
         '        if (method == "navigation.open") {\n'),
    ],
    'OmniBlocker.h': [
        ('bool omniPagesSetBridge(const std::string& source);      // page-world document-start script, omni://pages/* top frames only\n',
         'bool omniPagesSetBridge(const std::string& source);      // page-world document-start script, omni://pages/* top frames only\n'
         '// OMNI_START_CUSTOM_V1: omni://pages/_user/start-bg.png (the only _user/ path) is served from the bytes this gives\n'
         '// (the shell\'s cached copy; no file is read here); false = not found. Unset: nothing under _user/ is served.\n'
         'using OmniPagesUserFileFn = bool (*)(const std::string& name, std::vector<uint8_t>& data, std::string& mime);\n'
         'void omniPagesSetUserFile(OmniPagesUserFileFn fn);\n'),
    ],
    'OmniBlocker.cpp': [
        ('OmniPagesMessageFn pagesMessage = nullptr;\n',
         'OmniPagesMessageFn pagesMessage = nullptr;\n'
         'OmniPagesUserFileFn pagesUserFile = nullptr;   // OMNI_START_CUSTOM_V1\n'),
        ('        const std::string file = pagesRoot + "/" + rel;\n',
         '        if (rel.rfind("_user/", 0) == 0) { // OMNI_START_CUSTOM_V1: only the start page\'s picture, from the shell\'s cached copy\n'
         '            std::vector<uint8_t> bytes;\n'
         '            std::string mime;\n'
         '            if (rel != "_user/start-bg.png" || !pagesUserFile || !pagesUserFile(rel.substr(6), bytes, mime) || bytes.empty()\n'
         '                || (mime != "image/png" && mime != "image/jpeg")) { fail(404, "not found"); return; }\n'
         '            WebCore::ResourceResponse response { WTF::URL { wurl }, WTF::String::fromLatin1(mime.c_str()), static_cast<long long>(bytes.size()), WTF::String() };\n'
         '            response.setHTTPStatusCode(200);\n'
         '            response.setHTTPHeaderField(WebCore::HTTPHeaderName::ContentSecurityPolicy, WTF::String::fromLatin1(pagesCSP));\n'
         '            response.setHTTPHeaderField(WTF::String::fromLatin1("X-Content-Type-Options"), WTF::String::fromLatin1("nosniff"));\n'
         '            response.setHTTPHeaderField(WTF::String::fromLatin1("Cache-Control"), WTF::String::fromLatin1("no-cache"));\n'
         '            task.didReceiveResponse(WTF::move(response));\n'
         '            task.didReceiveData(WebCore::SharedBuffer::create(std::span<const uint8_t>(bytes.data(), bytes.size())));\n'
         '            task.didComplete(WebCore::ResourceError());\n'
         '            return;\n'
         '        }\n'
         '        const std::string file = pagesRoot + "/" + rel;\n'),
        ('bool omniPagesSetBridge(const std::string& source)\n',
         'void omniPagesSetUserFile(OmniPagesUserFileFn fn) { pagesUserFile = fn; } // OMNI_START_CUSTOM_V1\n'
         'bool omniPagesSetBridge(const std::string& source)\n'),
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
    needs = (('OmniBrowser.cpp', 'OMNI_CONTINUE_WATCHING_V1'), ('OmniBrowser.cpp', 'OMNI_CONTROLS_HELP_V1'),
             ('OmniFeatures3.h', 'OMNI_READING_LIST_V1'), ('OmniFeatures3.h', 'OMNI_CONTROLS_HELP_V1'), ('OmniPages.h', 'OMNI_PAGES_V1'))
    for need, mark in needs:
        if mark not in (root / need).read_bytes().decode('utf-8'):
            sys.exit('%s: %s missing: apply that patch first' % (need, mark))
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniStartCustom.h', PURE, 'OmniContinueWatching.h'),
            write_new('OmniStartCustomShell.h', SHELL, 'OmniContinueWatchingShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK + ' (r2)')


main()
