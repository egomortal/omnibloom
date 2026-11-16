#!/usr/bin/env python3
"""OMNI_READING_LIST_V1 (2026-11-16): "Save page for later", a reading list that works offline.

Save API. This WebKit (PlayStation port) has no usable single-file archive: WKPageGetContentsAsMHTMLData is compiled
with ENABLE_MHTML 0 (cmakeconfig.h of both /opt/omni-build builds; WebKitFeatures.cmake default OFF, only GTK/WPE turn
it on) and then NEVER calls its callback; WKFrameGetWebArchive needs ENABLE_WEB_ARCHIVE (0 outside Cocoa/Win). So the
page is captured with ONE read-only script (WKPageEvaluateJavaScriptInMainFrame, the same call the context menu and
page source use) that serialises the LIVE DOM (what the user sees, also for pages built by script; better than
WKPageGetSourceForFrame's server original) into an inert document (createHTMLDocument: nothing loads or runs there):
  - scripts, <base>, preload/prefetch links and meta http-equiv removed; on* attributes and javascript: links removed;
    <noscript> content shown (scripts never run in the saved copy);
  - every href/src/poster/action made absolute (so no <base> is needed and "#section" links still scroll in the copy);
  - readable stylesheets (same-origin <link>, every <style>, CSS-in-JS rules) inlined as <style> with their url()s made
    absolute; cross-origin sheets stay <link> (they style the copy only while online);
  - images already decoded and readable (same-origin or CORS) inlined as data: URLs (max 1600 px, JPEG 0.8 or PNG,
    8 M characters per page); cross-origin images stay links: shown online, a broken image offline;
  - iframes / embeds / objects become a link to their address;
  - the DOM over 10 M characters -> the page's text only (innerText, 4 M characters) as a plain readable page.
LOST offline: cross-origin images and stylesheets, fonts from other sites, video/audio, frames, anything a script
would draw or fetch later, form state. The page's scripts never run in a saved copy.

Storage: /data/omni/reading-list/<host>-<yyyymmdd-hhmmss>.html + index.tsv (escaped TSV, header
"omni-reading-list\t1"). Caps 500 MB and 200 pages: the oldest are dropped with a notice. One file at most 32 MB.
Private tabs are never saved (refused from every path). The save, the index and the deletes run on detached threads
(mutex-guarded list; the index is written tmp+rename under a second lock); the main loop only converts the script's
string and starts the thread. No network is used.

Open: the saved file is read on a thread and loaded into a NEW tab with WKPageLoadHTMLString(page, html, nullptr)
(an about:blank document, the way "Page source" opens; Omni's omni://pages scheme is not used: that origin has the
privileged window.omnibloomHost bridge and must never serve web content, and file:// is not served). The saved file
carries a CSP meta (script-src/object-src/frame-src/worker-src 'none', form-action 'none'), referrer no-referrer and a
"Saved copy" banner with an "Open live page" link.

UX: hold Cross on a page -> "Save page for later" (page rows, before View page source). Options -> Browse ->
"Save page for later" and "Reading list". Reading list panel (OmniFx, like Tabs): "Save this page", then the pages
newest first (title; site . date; size): Cross open saved copy (new tab), Triangle open live page, Square delete
(asks), Circle back.

Pure logic (index parse/serialize, caps, names, sizes/dates, the saved-document wrapper, the script result format)
is engine/entry/OmniReadingList.h (no SDL/WebKit; reuses OmniQuickActions.h), tested by test_reading_list.cpp:
  g++ -std=c++20 -I<tree>/engine/entry test_reading_list.cpp -o t && ./t <scratch dir>
Shell side: engine/entry/OmniReadingListShell.h (included from OmniFeatures3.h).

Anchors (exactly once each; MARK makes each file idempotent):
  OmniBrowser.cpp    the '#include "OmniQuickActions.h" // OMNI_QUICK_ACTIONS_V1...' line (needs apply_quick_actions.py)
  OmniContextMenu.h  'static void omniFxSiteSettingsShow();' (declarations), the omniF3ContextRows(p) line,
                     the omniF3ContextAction line
  OmniQuickMenu.h    'static void omniFxQuickAllBuild(OmniFxPanel& p)' (declarations), the omniF3QuickTiles(p) line,
                     the omniMqGroup "return 1" case line (tiles go to Options > Browse), the omniF3QuickAction line
  OmniFeatures3.h    '#include "OmniDarkPages.h"', the omniSecTick(now) call in omniF3Tick
usage: apply_reading_list.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_READING_LIST_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_READING_LIST_V1: the pure part of "Save page for later" (no SDL, no WebKit): the index file
// (/data/omni/reading-list/index.tsv) parse / serialize, the 500 MB / 200 page caps (oldest dropped), saved-file names,
// size and date text, the saved document's wrapper (CSP without scripts, "Saved copy" banner) and the capture script's
// result format. Tested on the host with g++ (test_reading_list.cpp).
#pragma once
#include "OmniQuickActions.h"
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <string>
#include <vector>

namespace OmniReadingList {

static const char* const kDir = "/data/omni/reading-list";
static const char* const kIndexName = "index.tsv";
static const char* const kHeader = "omni-reading-list\t1";
constexpr long long kMaxBytes = 500LL * 1024 * 1024;     // all saved pages together
constexpr size_t kMaxCount = 200;                        // saved pages
constexpr long long kMaxPageBytes = 32LL * 1024 * 1024;  // one saved file
constexpr int kTileSave = 420, kTileList = 421;          // Options tiles / context-menu row ids (V3 301+, sleep 700, V2 900+)

struct Entry {
    std::string id, url, title;   // id: the file name in kDir
    long long savedAt = 0, bytes = 0;
    bool textOnly = false;        // the page was too large: its text only
};

// One TSV field: backslash, tab, newline and carriage return escaped.
inline std::string escapeField(const std::string& s)
{
    std::string o;
    o.reserve(s.size());
    for (char c : s) {
        if (c == '\\') o += "\\\\";
        else if (c == '\t') o += "\\t";
        else if (c == '\n') o += "\\n";
        else if (c == '\r') o += "\\r";
        else o += c;
    }
    return o;
}
inline std::string unescapeField(const std::string& s)
{
    std::string o;
    o.reserve(s.size());
    for (size_t i = 0; i < s.size(); ++i) {
        if (s[i] != '\\' || i + 1 >= s.size()) { o += s[i]; continue; }
        const char c = s[++i];
        o += c == 't' ? '\t' : c == 'n' ? '\n' : c == 'r' ? '\r' : c;
    }
    return o;
}

// A file name this feature made: [a-z0-9.-], starts with a letter or digit, ends ".html", no "..", no '/'.
inline bool validId(const std::string& id)
{
    if (id.size() < 6 || id.size() > 140 || id.compare(id.size() - 5, 5, ".html") != 0) return false;
    if (id.find("..") != std::string::npos) return false;
    for (char c : id) if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '.' || c == '-')) return false;
    return (id[0] >= 'a' && id[0] <= 'z') || (id[0] >= '0' && id[0] <= '9');
}

inline std::vector<std::string> splitTabs(const std::string& line)
{
    std::vector<std::string> out;
    size_t at = 0;
    for (;;) {
        const size_t t = line.find('\t', at);
        out.push_back(line.substr(at, t == std::string::npos ? std::string::npos : t - at));
        if (t == std::string::npos) return out;
        at = t + 1;
    }
}
inline bool parseNumber(const std::string& s, long long& out)
{
    if (s.empty() || s.size() > 18) return false;
    for (char c : s) if (c < '0' || c > '9') return false;
    out = atoll(s.c_str());
    return true;
}

// id \t savedAt \t bytes \t h|t \t url \t title
inline std::string serialize(const std::vector<Entry>& list)
{
    std::string o = std::string(kHeader) + "\n";
    for (const Entry& e : list)
        o += e.id + "\t" + std::to_string(e.savedAt) + "\t" + std::to_string(e.bytes) + "\t" + (e.textOnly ? "t" : "h") + "\t"
            + escapeField(e.url) + "\t" + escapeField(e.title) + "\n";
    return o;
}
// Unknown header (another version): nothing. Bad lines and repeated ids are skipped.
inline std::vector<Entry> parse(const std::string& text)
{
    std::vector<Entry> out;
    size_t at = 0;
    bool first = true;
    while (at < text.size()) {
        size_t nl = text.find('\n', at);
        if (nl == std::string::npos) nl = text.size();
        std::string line = text.substr(at, nl - at);
        at = nl + 1;
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (first) { if (line != kHeader) return {}; first = false; continue; }
        if (line.empty()) continue;
        const auto f = splitTabs(line);
        if (f.size() != 6 || !validId(f[0]) || (f[3] != "h" && f[3] != "t")) continue;
        Entry e;
        if (!parseNumber(f[1], e.savedAt) || !parseNumber(f[2], e.bytes) || e.savedAt <= 0) continue;
        e.id = f[0]; e.textOnly = f[3] == "t"; e.url = unescapeField(f[4]); e.title = unescapeField(f[5]);
        bool seen = false;
        for (const Entry& x : out) if (x.id == e.id) { seen = true; break; }
        if (!seen) out.push_back(std::move(e));
    }
    return out;
}

inline long long totalBytes(const std::vector<Entry>& list)
{
    long long n = 0;
    for (const Entry& e : list) n += e.bytes;
    return n;
}
// Drops the oldest pages until one more page of `incoming` bytes fits both caps; returns them (oldest first).
// fits = false (nothing dropped) when the page alone is over the byte cap.
inline std::vector<Entry> makeRoom(std::vector<Entry>& list, long long incoming, bool& fits,
    long long maxBytes = kMaxBytes, size_t maxCount = kMaxCount)
{
    std::vector<Entry> dropped;
    fits = incoming <= maxBytes && maxCount > 0;
    if (!fits) return dropped;
    std::stable_sort(list.begin(), list.end(), [](const Entry& a, const Entry& b) { return a.savedAt < b.savedAt; });
    long long total = totalBytes(list);
    size_t drop = 0;
    while (drop < list.size() && (list.size() - drop + 1 > maxCount || total + incoming > maxBytes)) total -= list[drop++].bytes;
    dropped.assign(list.begin(), list.begin() + long(drop));
    list.erase(list.begin(), list.begin() + long(drop));
    return dropped;
}
inline std::vector<Entry> newestFirst(std::vector<Entry> list)
{
    std::stable_sort(list.begin(), list.end(), [](const Entry& a, const Entry& b) { return a.savedAt > b.savedAt; });
    return list;
}

// "<host>-<yyyymmdd-hhmmss>.html", then "-2" .. "-999"; empty when all are taken.
template <class Exists>
inline std::string makeId(const std::string& url, const struct tm& when, Exists exists)
{
    const std::string base = OmniQuickActions::hostForFile(url) + "-" + OmniQuickActions::stamp(when);
    for (int n = 1; n < 1000; ++n) {
        const std::string id = base + (n >= 2 ? "-" + std::to_string(n) : std::string()) + ".html";
        if (validId(id) && !exists(id)) return id;
    }
    return std::string();
}
// The site shown in the list ("" when the address has no host).
inline std::string site(const std::string& url)
{
    const std::string h = OmniQuickActions::hostForFile(url);
    return h == "page" && url.find("://page") == std::string::npos ? std::string() : h;
}
inline std::string sizeText(long long b)
{
    char s[32];
    if (b >= 1048576) snprintf(s, sizeof(s), "%.1f MB", b / 1048576.0);
    else snprintf(s, sizeof(s), "%lld KB", (b + 1023) / 1024);
    return s;
}
// "Today 14:05", "Yesterday 09:30", "12 Nov", "12 Nov 2025" (local time).
inline std::string dateText(time_t t, time_t now)
{
    static const char* const months[] = { "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec" };
    struct tm a {}, n {}, y {};
    localtime_r(&t, &a);
    localtime_r(&now, &n);
    const time_t yesterday = now - 86400;
    localtime_r(&yesterday, &y);
    char b[48];
    if (a.tm_year == n.tm_year && a.tm_yday == n.tm_yday) snprintf(b, sizeof(b), "Today %02d:%02d", a.tm_hour, a.tm_min);
    else if (a.tm_year == y.tm_year && a.tm_yday == y.tm_yday) snprintf(b, sizeof(b), "Yesterday %02d:%02d", a.tm_hour, a.tm_min);
    else if (a.tm_year == n.tm_year) snprintf(b, sizeof(b), "%d %s", a.tm_mday, months[a.tm_mon % 12]);
    else snprintf(b, sizeof(b), "%d %s %d", a.tm_mday, months[a.tm_mon % 12], a.tm_year + 1900);
    return b;
}
// "16 Nov 2026, 14:05" for the banner.
inline std::string longDate(const struct tm& a)
{
    static const char* const months[] = { "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec" };
    char b[48];
    snprintf(b, sizeof(b), "%d %s %d, %02d:%02d", a.tm_mday, months[a.tm_mon % 12], a.tm_year + 1900, a.tm_hour, a.tm_min);
    return b;
}

inline std::string htmlEscape(const std::string& s)
{
    std::string o;
    o.reserve(s.size() + 16);
    for (char c : s) {
        if (c == '&') o += "&amp;"; else if (c == '<') o += "&lt;"; else if (c == '>') o += "&gt;";
        else if (c == '"') o += "&quot;"; else if (c == '\'') o += "&#39;"; else o += c;
    }
    return o;
}
// Position of the start tag "<name" (any case, followed by '>', '/' or white space), or npos.
inline size_t findTag(const std::string& s, const char* name, size_t from = 0)
{
    const size_t n = std::char_traits<char>::length(name);
    for (size_t i = s.find('<', from); i != std::string::npos && i + n + 1 < s.size(); i = s.find('<', i + 1)) {
        size_t k = 0;
        while (k < n && (s[i + 1 + k] | 0x20) == name[k]) ++k;
        if (k < n) continue;
        const char e = s[i + 1 + n];
        if (e == '>' || e == '/' || e == ' ' || e == '\t' || e == '\n' || e == '\r' || e == '\f') return i;
    }
    return std::string::npos;
}
// Index just past the '>' of the tag starting at `at` (quoted '>' skipped), or npos.
inline size_t tagEnd(const std::string& s, size_t at)
{
    char q = 0;
    for (size_t i = at; i < s.size(); ++i) {
        if (q) { if (s[i] == q) q = 0; continue; }
        if (s[i] == '"' || s[i] == '\'') q = s[i];
        else if (s[i] == '>') return i + 1;
    }
    return std::string::npos;
}

inline std::string headBlock()
{
    return "<meta charset=\"utf-8\"><meta http-equiv=\"Content-Security-Policy\" content=\"script-src 'none'; object-src 'none'; "
           "frame-src 'none'; worker-src 'none'; form-action 'none'\"><meta name=\"referrer\" content=\"no-referrer\">";
}
inline std::string banner(const std::string& url, const std::string& when, bool textOnly)
{
    return "<div id=\"omni-saved-banner\" style=\"all:initial;display:block;box-sizing:border-box;width:100%;position:relative;"
           "z-index:2147483647;background:#17202b;color:#e8edf3;font:16px/1.5 sans-serif;padding:10px 16px;border-bottom:2px solid #3d8bfd\">"
           + std::string(textOnly ? "Saved text (the page was too large to keep whole)" : "Saved copy") + " \xc2\xb7 " + htmlEscape(when)
           + " \xc2\xb7 <a href=\"" + htmlEscape(url) + "\" style=\"all:initial;color:#8ab4ff;font:inherit;text-decoration:underline;cursor:pointer\">"
           "Open live page</a></div>";
}
// The file written to the reading list: the CSP (no scripts, frames, plugins or form posts) first in <head>, the
// banner first in <body>. Missing <head>/<body> are tolerated.
inline std::string wrapSaved(const std::string& html, const std::string& url, const std::string& when, bool textOnly)
{
    std::string s = html;
    const std::string head = headBlock(), ban = banner(url, when, textOnly);
    size_t h = findTag(s, "head"), e = h == std::string::npos ? h : tagEnd(s, h);
    if (e != std::string::npos) s.insert(e, head);
    else {
        const size_t x = findTag(s, "html"), xe = x == std::string::npos ? x : tagEnd(s, x);
        if (xe != std::string::npos) s.insert(xe, "<head>" + head + "</head>");
        else {
            size_t at = 0;
            if (s.size() >= 9 && (s.compare(0, 9, "<!doctype") == 0 || s.compare(0, 9, "<!DOCTYPE") == 0)) { at = s.find('>'); at = at == std::string::npos ? 0 : at + 1; }
            s.insert(at, "<head>" + head + "</head>");
        }
    }
    const size_t b = findTag(s, "body"), be = b == std::string::npos ? b : tagEnd(s, b);
    if (be != std::string::npos) s.insert(be, ban);
    else {
        const size_t hc = s.find("</head>");
        s.insert(hc == std::string::npos ? s.size() : hc + 7, ban);
    }
    return s;
}
// The page's text as a readable page (blank lines separate paragraphs).
inline std::string textDocument(const std::string& text, const std::string& title)
{
    std::string body;
    size_t at = 0;
    while (at < text.size()) {
        size_t nl = text.find('\n', at);
        if (nl == std::string::npos) nl = text.size();
        std::string line = text.substr(at, nl - at);
        at = nl + 1;
        while (!line.empty() && (line.back() == '\r' || line.back() == ' ' || line.back() == '\t')) line.pop_back();
        if (!line.empty()) body += "<p>" + htmlEscape(line) + "</p>\n";
    }
    return "<!doctype html><html><head><title>" + htmlEscape(title) + "</title><style>body{max-width:46em;margin:0 auto;"
           "padding:0 24px 40px;font:20px/1.6 sans-serif;background:#fbfaf7;color:#202124}h1{font-size:1.5em}p{margin:0 0 .8em}"
           "</style></head><body><h1>" + htmlEscape(title) + "</h1>\n" + body + "</body></html>";
}
// The capture script's answer: "OMNIRL1\x01<title>\x01h|t\x01<html or text>". False when it is not one.
inline bool parsePayload(const std::string& p, std::string& title, bool& textOnly, std::string& body)
{
    static const char tag[] = "OMNIRL1\x01";
    if (p.compare(0, sizeof(tag) - 1, tag) != 0) return false;
    const size_t t0 = sizeof(tag) - 1, t1 = p.find('\x01', t0);
    if (t1 == std::string::npos || p.size() < t1 + 3 || p[t1 + 2] != '\x01') return false;
    const char kind = p[t1 + 1];
    if (kind != 'h' && kind != 't') return false;
    title = p.substr(t0, t1 - t0);
    textOnly = kind == 't';
    body = p.substr(t1 + 3);
    return !body.empty();
}

} // namespace OmniReadingList
'''

SHELL = r'''// OMNI_READING_LIST_V1: "Save page for later" and the Reading list panel (shell side). Included from OmniFeatures3.h
// (inside OmniBrowser.cpp's anonymous namespace). The pure part is OmniReadingList.h; the reasons (no MHTML in this
// WebKit, live-DOM capture, about:blank + CSP for opening) are in tools/apply_reading_list.py.
// Threads: the capture script's string is converted on the main thread (WebKit's callback) and everything after it
// (wrap, file write, caps, index) runs on a detached thread; opening reads the file on a thread too. Results come back
// through omniRlDoneQ, drained by omniRlTick() (from omniF3Tick). Private tabs are never saved.
#pragma once

namespace RL = OmniReadingList;
struct OmniRlDone { int kind = 0; std::string a, b; int dropped = 0; };   // 1 saved, 2 save failed, 3 open ready, 4 open failed, 5 index loaded
static std::mutex omniRlLock;              // omniRlList, omniRlLoaded, omniRlDoneQ
static std::mutex omniRlFileLock;          // the folder and index.tsv (worker threads only)
static std::vector<RL::Entry> omniRlList;
static bool omniRlLoaded = false;
static std::vector<OmniRlDone> omniRlDoneQ;
static std::atomic<int> omniRlPhase { 0 };        // 0 idle, 1 waiting for the page's script, 2 writing
static std::atomic<bool> omniRlOpening { false }, omniRlLoadStarted { false };
static uint32_t omniRlAskedAt = 0;
static std::vector<RL::Entry> omniRlShown;        // the panel's page rows (main thread)

static std::string omniRlPath(const std::string& name) { return std::string(RL::kDir) + "/" + name; }
static void omniRlPost(OmniRlDone d) { std::lock_guard<std::mutex> g(omniRlLock); omniRlDoneQ.push_back(std::move(d)); }
static bool omniRlCanSave(const Tab* t) { return t && !t->omniPrivate && omniWebURL(t->url) && !t->crashed && !omniTmIsUnloaded(*t); }

// --- worker threads -----------------------------------------------------------------------------------------------
static bool omniRlReadFile(const std::string& path, std::string& out, long long limit)
{
    FILE* f = fopen(path.c_str(), "rb");
    if (!f) return false;
    fseek(f, 0, SEEK_END);
    const long size = ftell(f);
    fseek(f, 0, SEEK_SET);
    bool ok = size >= 0 && size <= limit;
    if (ok) { out.resize(size_t(size)); ok = fread(out.data(), 1, out.size(), f) == out.size(); }
    fclose(f);
    return ok;
}
static bool omniRlWriteFile(const std::string& path, const std::string& data)
{
    const std::string tmp = path + ".tmp";
    FILE* f = fopen(tmp.c_str(), "wb");
    if (!f) return false;
    const bool ok = fwrite(data.data(), 1, data.size(), f) == data.size();
    if (fclose(f) || !ok || rename(tmp.c_str(), path.c_str())) { unlink(tmp.c_str()); return false; }
    return true;
}
static void omniRlWriteIndexLocked()   // omniRlFileLock held: the last writer always has the newest list
{
    std::string text;
    { std::lock_guard<std::mutex> g(omniRlLock); text = RL::serialize(omniRlList); }
    if (!omniRlWriteFile(omniRlPath(RL::kIndexName), text)) fprintf(stderr, "OMNI READING LIST: index write failed\n");
}
static void omniRlLoadLocked()          // omniRlFileLock held
{
    { std::lock_guard<std::mutex> g(omniRlLock); if (omniRlLoaded) return; }
    std::string text;
    std::vector<RL::Entry> list, keep;
    if (omniRlReadFile(omniRlPath(RL::kIndexName), text, 8 << 20)) list = RL::parse(text);
    for (auto& e : list) {            // the file decides the size; entries without a file are dropped
        struct stat st {};
        if (stat(omniRlPath(e.id).c_str(), &st) == 0 && S_ISREG(st.st_mode)) { e.bytes = (long long)st.st_size; keep.push_back(e); }
    }
    const bool changed = keep.size() != list.size();
    if (DIR* dp = opendir(RL::kDir)) {   // files of a save cut short (not in the index) are removed
        while (dirent* de = readdir(dp)) {
            const std::string n = de->d_name;
            const std::string stem = n.size() > 4 && n.compare(n.size() - 4, 4, ".tmp") == 0 ? n.substr(0, n.size() - 4) : std::string();
            const bool tmp = !stem.empty() && (RL::validId(stem) || stem == RL::kIndexName);
            bool known = false;
            for (auto& e : keep) if (e.id == n) { known = true; break; }
            if (tmp || (RL::validId(n) && !known)) unlink(omniRlPath(n).c_str());
        }
        closedir(dp);
    }
    fprintf(stderr, "OMNI READING LIST: %zu page(s), %lld bytes\n", keep.size(), RL::totalBytes(keep));
    { std::lock_guard<std::mutex> g(omniRlLock); omniRlList = std::move(keep); omniRlLoaded = true; }
    if (changed) omniRlWriteIndexLocked();
}
static void omniRlEnsureLoading()
{
    if (omniRlLoadStarted.exchange(true)) return;
    std::thread([] { { std::lock_guard<std::mutex> fl(omniRlFileLock); omniRlLoadLocked(); } OmniRlDone d; d.kind = 5; omniRlPost(std::move(d)); }).detach();
}
static void omniRlSaveWorker(std::string payload, std::string url, std::string fallbackTitle)
{
    OmniRlDone d; d.kind = 2;
    std::string title, body;
    bool textOnly = false;
    if (!RL::parsePayload(payload, title, textOnly, body)) { d.a = "the page didn't answer"; omniRlPost(std::move(d)); return; }
    std::string().swap(payload);
    if (title.empty()) title = fallbackTitle.empty() ? RL::site(url) : fallbackTitle;
    const time_t now = time(nullptr);
    struct tm tmv {};
    localtime_r(&now, &tmv);
    std::string doc = RL::wrapSaved(textOnly ? RL::textDocument(body, title) : body, url, RL::longDate(tmv), textOnly);
    std::string().swap(body);
    if ((long long)doc.size() > RL::kMaxPageBytes) { d.a = "it is too large (" + RL::sizeText((long long)doc.size()) + ")"; omniRlPost(std::move(d)); return; }
    std::lock_guard<std::mutex> fl(omniRlFileLock);
    omniRlLoadLocked();
    if (!OmniQuickActions::makeDirs(RL::kDir)) { d.a = std::string("couldn't create ") + RL::kDir; omniRlPost(std::move(d)); return; }
    std::string id;
    {
        std::lock_guard<std::mutex> g(omniRlLock);
        id = RL::makeId(url, tmv, [](const std::string& n) {
            for (auto& e : omniRlList) if (e.id == n) return true;
            return OmniQuickActions::fileExists(omniRlPath(n));
        });
    }
    if (id.empty() || !omniRlWriteFile(omniRlPath(id), doc)) { d.a = "the file couldn't be written"; omniRlPost(std::move(d)); return; }
    RL::Entry e;
    e.id = id; e.url = url; e.title = title; e.savedAt = (long long)now; e.bytes = (long long)doc.size(); e.textOnly = textOnly;
    std::vector<RL::Entry> dropped;
    {
        std::lock_guard<std::mutex> g(omniRlLock);
        bool fits = true;
        dropped = RL::makeRoom(omniRlList, e.bytes, fits);
        omniRlList.push_back(e);
    }
    for (auto& x : dropped) unlink(omniRlPath(x.id).c_str());
    omniRlWriteIndexLocked();
    fprintf(stderr, "OMNI READING LIST: saved %s (%lld bytes%s), %zu oldest dropped\n", id.c_str(), e.bytes, textOnly ? ", text only" : "", dropped.size());
    d.kind = 1; d.a = title; d.b = textOnly ? "t" : ""; d.dropped = int(dropped.size());
    omniRlPost(std::move(d));
}

// --- main thread ---------------------------------------------------------------------------------------------------
// The capture script: read-only on the page; works on an inert copy (createHTMLDocument: nothing loads or runs there).
static const char* const omniRlScript = R"JS((function(){var H='OMNIRL1\u0001';try{
var d=document,base=d.baseURI,title=(d.title||'').replace(/[\u0000-\u001f]+/g,' ').trim().slice(0,300);
function txt(){var t=(d.body&&d.body.innerText)||'';return t.length>4194304?t.slice(0,4194304):t;}
if(!d.documentElement)return H+title+'\u0001t\u0001'+txt();
function abs(u,b){if(!u||/^(data:|blob:|#|javascript:|mailto:|tel:|about:)/i.test(u))return u;try{return new URL(u,b||base).href;}catch(e){return u;}}
function cssAbs(css,b){return css.replace(/url\(\s*(['"]?)([^'")]+)\1\s*\)/g,function(m,q,u){var a=abs(u.trim(),b);return a===u?m:'url("'+a+'")';});}
var inert=d.implementation.createHTMLDocument(''),live=d.documentElement,c=inert.importNode(live,true),i,k,n;
var li=live.querySelectorAll('img'),ci=c.querySelectorAll('img'),used=0,IMGB=8388608;
for(i=0;i<ci.length&&i<li.length;i++){var a=li[i],b=ci[i],src=a.currentSrc||a.src||a.getAttribute('data-src')||'';
src=abs(src);b.removeAttribute('srcset');b.removeAttribute('sizes');b.removeAttribute('loading');if(src)b.setAttribute('src',src);
if(a.complete&&a.naturalWidth>0&&used<IMGB&&!/^data:/i.test(src)){try{var w=a.naturalWidth,h=a.naturalHeight,s=Math.min(1,1600/w,1600/h);
if(w*h<=16e6){var cv=d.createElement('canvas');cv.width=Math.max(1,Math.round(w*s));cv.height=Math.max(1,Math.round(h*s));
cv.getContext('2d').drawImage(a,0,0,cv.width,cv.height);var png=/\.(png|gif|svg|webp)(\?|#|$)/i.test(src);
var u=cv.toDataURL(png?'image/png':'image/jpeg',0.8);if(u.length>32&&used+u.length<=IMGB){b.setAttribute('src',u);used+=u.length;}}}catch(e){}}}
var ls=live.querySelectorAll('link[rel~="stylesheet"],style'),cs=c.querySelectorAll('link[rel~="stylesheet"],style');
for(i=0;i<ls.length&&i<cs.length;i++){var sh=ls[i].sheet,css='';if(!sh)continue;
try{var r=sh.cssRules;for(k=0;k<r.length;k++)css+=r[k].cssText+'\n';}catch(e){if(ls[i].tagName==='LINK')cs[i].setAttribute('href',ls[i].href);continue;}
var st=inert.createElement('style');if(sh.media&&sh.media.mediaText)st.setAttribute('media',sh.media.mediaText);
st.textContent=cssAbs(css,sh.href||base);cs[i].parentNode.replaceChild(st,cs[i]);}
n=c.querySelectorAll('script,base,picture source,link[rel~="preload"],link[rel~="modulepreload"],link[rel~="prefetch"],link[rel~="preconnect"],link[rel~="dns-prefetch"],meta[http-equiv]');
for(i=0;i<n.length;i++)n[i].parentNode&&n[i].parentNode.removeChild(n[i]);
n=c.querySelectorAll('noscript');for(i=0;i<n.length;i++){var dv=inert.createElement('div');dv.innerHTML=n[i].textContent;n[i].parentNode.replaceChild(dv,n[i]);}
n=c.querySelectorAll('script');for(i=0;i<n.length;i++)n[i].parentNode.removeChild(n[i]);
n=c.querySelectorAll('iframe,frame,embed,object');for(i=0;i<n.length;i++){var fs=abs(n[i].getAttribute('src')||n[i].getAttribute('data')||''),p=inert.createElement('p');
if(/^https?:/i.test(fs)){var l=inert.createElement('a');l.setAttribute('href',fs);l.textContent='Embedded content: '+fs;p.appendChild(l);}n[i].parentNode.replaceChild(p,n[i]);}
n=c.querySelectorAll('*');for(i=0;i<n.length;i++){var el=n[i],at=el.attributes;
for(k=at.length-1;k>=0;k--){var nm=at[k].name.toLowerCase(),v=at[k].value;
if(nm.slice(0,2)==='on'){el.removeAttribute(at[k].name);continue;}
if(nm==='href'||nm==='src'||nm==='poster'||nm==='action'||nm==='data-src'){if(/^\s*javascript:/i.test(v))el.setAttribute(at[k].name,'#');else if(!/^data:/i.test(v))el.setAttribute(at[k].name,abs(v.trim()));}
else if(nm==='style'&&v.indexOf('url(')>=0)el.setAttribute('style',cssAbs(v,base));else if(nm==='srcset'&&el.tagName!=='IMG')el.removeAttribute('srcset');}}
var html='<!doctype html>'+c.outerHTML;if(html.length>10485760)return H+title+'\u0001t\u0001'+txt();
return H+title+'\u0001h\u0001'+html;}catch(err){try{return H+(document.title||'').replace(/[\u0000-\u001f]+/g,' ')+'\u0001t\u0001'+((document.body&&document.body.innerText)||'');}catch(_){return '';}}})())JS";
struct OmniRlQuery { std::string url, title; };
static void omniRlSaveCurrent()
{
    Tab* t = active();
    if (!t) return;
    if (t->omniPrivate) { notice("Pages in private tabs are never saved"); return; }
    if (!omniRlCanSave(t)) { notice("Open a web page first"); return; }
    if (omniRlPhase.load() != 0) { notice("Still saving the last page..."); return; }
    const long long freeMiB = omniTmQueryMiB();
    if (freeMiB >= 0 && freeMiB < 96) { notice("Not enough memory to save this page right now"); return; }
    omniRlPhase = 1; omniRlAskedAt = SDL_GetTicks();
    omniRlEnsureLoading();
    notice("Saving page for later...");
    auto* q = new OmniRlQuery { t->url, t->title };
    auto js = adoptWK(WKStringCreateWithUTF8CString(omniRlScript));
    WKPageEvaluateJavaScriptInMainFrame(t->page, js.get(), q, [](WKTypeRef result, WKErrorRef error, void* ctx) {
        std::unique_ptr<OmniRlQuery> q(static_cast<OmniRlQuery*>(ctx));
        int waiting = 1;
        if (!omniRlPhase.compare_exchange_strong(waiting, 2)) return;   // timed out already
        std::string payload = omniFxResultString(result, error);
        if (payload.empty()) { omniRlPhase = 0; notice("Couldn't save this page (it didn't answer)"); return; }
        std::thread(omniRlSaveWorker, std::move(payload), q->url, q->title).detach();
    });
}
static void omniRlOpenSaved(const RL::Entry& e)
{
    if (omniF3TabsFull()) { notice("Close a tab first: the saved page opens in a new tab"); return; }
    if (omniRlOpening.exchange(true)) { notice("Still opening a saved page..."); return; }
    omniFxCloseAll();
    notice("Opening saved page...");
    std::thread([e] {
        OmniRlDone d; d.kind = 4; d.b = e.title.empty() ? RL::site(e.url) : e.title;
        if (omniRlReadFile(omniRlPath(e.id), d.a, RL::kMaxPageBytes + (1 << 20)) && !d.a.empty()) d.kind = 3;
        else d.a = "the saved file is missing or unreadable";
        omniRlPost(std::move(d));
    }).detach();
}
static void omniRlDelete(const RL::Entry& e)
{
    { std::lock_guard<std::mutex> g(omniRlLock);
      omniRlList.erase(std::remove_if(omniRlList.begin(), omniRlList.end(), [&](const RL::Entry& x) { return x.id == e.id; }), omniRlList.end()); }
    const std::string id = e.id;
    std::thread([id] { std::lock_guard<std::mutex> fl(omniRlFileLock); unlink(omniRlPath(id).c_str()); omniRlWriteIndexLocked(); }).detach();
    notice("Removed from the reading list");
    omniFxRefresh();
}

// --- the Reading list panel -------------------------------------------------------------------------------------------
enum { omniRlRowSave = 1, omniRlRowInfo, omniRlRowFirst = 1000 };
static void omniRlBuild(OmniFxPanel& p)
{
    std::vector<RL::Entry> list;
    bool loaded;
    { std::lock_guard<std::mutex> g(omniRlLock); list = omniRlList; loaded = omniRlLoaded; }
    omniRlShown = RL::newestFirst(std::move(list));
    Tab* t = active();
    OmniFxRow s; s.id = omniRlRowSave; s.label = "Save this page"; s.icon = omniIconPlus;
    s.enabled = omniRlCanSave(t) && omniRlPhase.load() == 0;
    s.value = omniRlPhase.load() ? std::string("Saving...") : t && t->omniPrivate ? std::string("Not in private tabs") : std::string();
    p.rows.push_back(s);
    if (!loaded || omniRlShown.empty()) {
        OmniFxRow r; r.id = omniRlRowInfo; r.enabled = false;
        r.label = loaded ? "Nothing saved yet" : "Loading...";
        if (loaded) r.detail = "Options > Save page for later, or hold Cross on a page";
        p.rows.push_back(r);
    }
    const time_t now = time(nullptr);
    for (size_t i = 0; i < omniRlShown.size(); ++i) {
        const RL::Entry& e = omniRlShown[i];
        const std::string where = RL::site(e.url);
        OmniFxRow r; r.id = omniRlRowFirst + int(i);
        r.label = omniOneLine(e.title.empty() ? (where.empty() ? e.url : where) : e.title, 120);
        r.detail = where + (where.empty() ? "" : " \xc2\xb7 ") + RL::dateText(time_t(e.savedAt), now) + (e.textOnly ? " \xc2\xb7 text only" : "");
        r.value = RL::sizeText(e.bytes);
        p.rows.push_back(r);
    }
    p.subtitle = std::to_string(omniRlShown.size()) + (omniRlShown.size() == 1 ? " page \xc2\xb7 " : " pages \xc2\xb7 ")
        + RL::sizeText(RL::totalBytes(omniRlShown)) + " of " + std::to_string(RL::kMaxBytes >> 20) + " MB \xc2\xb7 opens offline";
    p.corner = std::to_string(omniRlShown.size()) + " / " + std::to_string(RL::kMaxCount);
}
static bool omniRlInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (r.id == omniRlRowSave) { if (b != SDL_CONTROLLER_BUTTON_A) return false; if (r.enabled) { omniRlSaveCurrent(); omniFxRefresh(); } return true; }
    if (r.id < omniRlRowFirst) return b == SDL_CONTROLLER_BUTTON_A;
    const size_t i = size_t(r.id - omniRlRowFirst);
    if (i >= omniRlShown.size()) return false;
    const RL::Entry e = omniRlShown[i];
    if (b == SDL_CONTROLLER_BUTTON_A) { omniRlOpenSaved(e); return true; }
    if (b == SDL_CONTROLLER_BUTTON_Y) {
        if (!omniWebURL(e.url)) { notice("This saved page has no live address"); return true; }
        omniFxCloseAll();
        omniFxOpenInNewTab(e.url, false, false);
        return true;
    }
    if (b == SDL_CONTROLLER_BUTTON_X) {
        omniAsk("Delete this saved page?", omniOneLine(e.title.empty() ? e.url : e.title, 90) + " (" + RL::sizeText(e.bytes) + ") will be removed from the reading list.",
            "Delete", [e](bool ok) { if (ok) omniRlDelete(e); });
        return true;
    }
    return false;
}
static bool omniRlPanelShown() { return !omniFxStack.empty() && omniFxStack.back().build == omniRlBuild; }
static void omniRlShow()
{
    omniRlEnsureLoading();
    OmniFxPanel p;
    p.title = "Reading list"; p.w = 980; p.rowH = 56; p.maxVisible = 8;
    p.build = omniRlBuild; p.input = omniRlInput;
    p.faces = { { 0, "Open saved copy" }, { 3, "Open live page" }, { 2, "Delete" }, { 1, "Back" } };
    omniFxPush(std::move(p));
}

// --- context menu / Options hooks (OmniContextMenu.h, OmniQuickMenu.h) -------------------------------------------------
static void omniRlContextRows(OmniFxPanel& p)
{
    OmniFxRow r; r.id = RL::kTileSave; r.label = "Save page for later"; r.enabled = omniRlCanSave(active());
    p.rows.push_back(r);
}
static bool omniRlContextAction(int id)
{
    if (id != RL::kTileSave) return false;
    omniFxCloseAll();
    omniRlSaveCurrent();
    return true;
}
static void omniRlQuickTiles(OmniFxPanel& p)
{
    Tab* t = active();
    OmniFxRow s; s.id = RL::kTileSave; s.label = "Save page for later"; s.enabled = omniRlCanSave(t) && omniRlPhase.load() == 0;
    s.value = omniRlPhase.load() ? std::string("Saving...") : t && t->omniPrivate ? std::string("Not in private tabs") : std::string();
    p.rows.push_back(s);
    size_t n = 0; bool loaded;
    { std::lock_guard<std::mutex> g(omniRlLock); n = omniRlList.size(); loaded = omniRlLoaded; }
    OmniFxRow l; l.id = RL::kTileList; l.label = "Reading list"; l.value = loaded ? std::to_string(n) : std::string();
    p.rows.push_back(l);
}
static bool omniRlQuickAction(int id)
{
    if (id == RL::kTileSave) { omniFxCloseAll(); omniRlSaveCurrent(); return true; }
    if (id == RL::kTileList) { omniRlShow(); return true; }   // on top of the menu (Circle comes back)
    return false;
}

// --- per pass (omniF3Tick) ----------------------------------------------------------------------------------------------
static void omniRlTick(uint32_t now)
{
    if (omniRlPhase.load() == 1 && now - omniRlAskedAt > 30000) {
        int waiting = 1;
        if (omniRlPhase.compare_exchange_strong(waiting, 0)) notice("Couldn't save this page (it didn't answer)");
    }
    std::vector<OmniRlDone> done;
    { std::lock_guard<std::mutex> g(omniRlLock); if (omniRlDoneQ.empty()) return; done.swap(omniRlDoneQ); }
    for (auto& d : done) {
        switch (d.kind) {
        case 1:
            omniRlPhase = 0;
            notice("Saved for later: " + omniOneLine(d.a, 60) + (d.b == "t" ? " (text only: the page was too large)" : "")
                + (d.dropped ? " \xc2\xb7 reading list full: removed " + std::to_string(d.dropped) + " oldest" : ""));
            break;
        case 2: omniRlPhase = 0; notice("Couldn't save this page: " + d.a); break;
        case 3: {
            omniRlOpening = false;
            if (!newTab()) { notice(omniF3TabRefusal()); break; }
            Tab* t = active();
            t->title = "Saved: " + d.b;
            auto s = adoptWK(WKStringCreateWithUTF8CString(d.a.c_str()));
            std::string().swap(d.a);
            WKPageLoadHTMLString(t->page, s.get(), nullptr);
            t->loading = true;
            break;
        }
        case 4: omniRlOpening = false; notice("Couldn't open the saved page: " + d.a); break;
        default: break;
        }
    }
    if (omniRlPanelShown()) omniFxRefresh();
    omniShellDirty = true;
}
'''

DECL = '''static bool omniRlContextAction(int id); // OMNI_READING_LIST_V1 (OmniReadingListShell.h)
static void omniRlContextRows(OmniFxPanel& p); // OMNI_READING_LIST_V1
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniQuickActions.h" // OMNI_QUICK_ACTIONS_V1: screenshot folder / file name (pure)\n',
         '#include "OmniQuickActions.h" // OMNI_QUICK_ACTIONS_V1: screenshot folder / file name (pure)\n'
         '#include "OmniReadingList.h" // OMNI_READING_LIST_V1: reading list index, caps, saved-page wrapper (pure)\n'),
    ],
    'OmniContextMenu.h': [
        ('static void omniFxSiteSettingsShow();\n', 'static void omniFxSiteSettingsShow();\n' + DECL),
        ('        omniF3ContextRows(p); // OMNI_FEATURES_V3: page source, screenshot, dark page\n',
         '        omniRlContextRows(p); // OMNI_READING_LIST_V1: Save page for later\n'
         '        omniF3ContextRows(p); // OMNI_FEATURES_V3: page source, screenshot, dark page\n'),
        ('    if (omniF3ContextAction(r.id)) return true; // OMNI_FEATURES_V3\n',
         '    if (omniRlContextAction(r.id)) return true; // OMNI_READING_LIST_V1\n'
         '    if (omniF3ContextAction(r.id)) return true; // OMNI_FEATURES_V3\n'),
    ],
    'OmniQuickMenu.h': [
        ('    omniF3QuickTiles(p); // OMNI_FEATURES_V3: Screenshot, Page source, Dark page\n',
         '    omniF3QuickTiles(p); // OMNI_FEATURES_V3: Screenshot, Page source, Dark page\n'
         '    omniRlQuickTiles(p); // OMNI_READING_LIST_V1: Save page for later, Reading list\n'),
        ('    case omniQmTabs: case omniQmBookmarks: case omniQmHistory: case omniQmBack: case omniQmForward: case omniQmReload: return 1;\n',
         '    case omniQmTabs: case omniQmBookmarks: case omniQmHistory: case omniQmBack: case omniQmForward: case omniQmReload: return 1;\n'
         '    case OmniReadingList::kTileSave: case OmniReadingList::kTileList: return 1; // OMNI_READING_LIST_V1: Browse\n'),
        ('    if (omniF3QuickAction(r.id)) return true; // OMNI_FEATURES_V3\n',
         '    if (omniF3QuickAction(r.id)) return true; // OMNI_FEATURES_V3\n'
         '    if (omniRlQuickAction(r.id)) return true; // OMNI_READING_LIST_V1\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniDarkPages.h"\n', '#include "OmniDarkPages.h"\n#include "OmniReadingListShell.h" // OMNI_READING_LIST_V1\n'),
        ('    omniSecTick(now);   // OMNI_SEC_LOCALHOST_V1\n',
         '    omniSecTick(now);   // OMNI_SEC_LOCALHOST_V1\n    omniRlTick(now);    // OMNI_READING_LIST_V1\n'),
    ],
}
QUICK_DECL = ('static void omniFxQuickAllBuild(OmniFxPanel& p)\n',
              'static void omniRlQuickTiles(OmniFxPanel& p); // OMNI_READING_LIST_V1 (OmniReadingListShell.h)\n'
              'static bool omniRlQuickAction(int id); // OMNI_READING_LIST_V1\n'
              'static void omniFxQuickAllBuild(OmniFxPanel& p)\n')


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
    raw = p.read_bytes()
    s = raw.decode('utf-8')
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
    if not (root / 'OmniQuickActions.h').exists():
        sys.exit('OmniQuickActions.h missing: apply_quick_actions.py first')
    EDITS['OmniQuickMenu.h'].insert(0, QUICK_DECL)
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [patch(name, edits) for name, edits in EDITS.items()]
    msgs.append(write_new('OmniReadingList.h', PURE, 'OmniQuickActions.h'))
    msgs.append(write_new('OmniReadingListShell.h', SHELL, 'OmniFeatures3.h'))
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
