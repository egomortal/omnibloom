#!/usr/bin/env python3
"""OMNI_SEARCH_TILES_V1 (2026-11-16): search shortcuts in the address bar and most-visited suggestion tiles.

1. Search shortcuts: "yt lofi beats" + Go searches YouTube. Built-ins: yt YouTube, w Wikipedia, r Reddit, g Google,
   d DuckDuckGo, a Amazon, m Google Maps. Only when the first word is exactly a known prefix (case-insensitive),
   followed by a space and more text, and the input is not an address (scheme, about:/data:/javascript:, "://").
   The query is UTF-8 percent-encoded (RFC 3986 unreserved bytes kept, space = %20) into the template's %s.
   The matched engine is the first address suggestion: Search YouTube for "lofi beats".
   User list: /data/omni/search-shortcuts.txt, one "prefix<TAB>https://...%s[<TAB>Name]" per line, '#' comments,
   at most 30, https:// only (validated: plain host, no credentials, every % is %s or %XX); re-read when its size or
   mtime changes; the built-ins are used only when the file is missing (an empty file = no shortcuts).
2. Most-visited tiles: the empty slots of the shortcut tiles (keyboard tile page, and the new-tab page's shortcut grid
   up to 8 tiles / the end of its last row) show the most visited sites from history.txt: by host, visits in the last
   30 days (all visits when the file has no timestamps), hosts already in shortcuts and local hosts (127.0.0.1
   Downloads, localhost) left out. Private tabs never write history (omniEverydayFinished). Suggested tiles are
   dimmer (keyboard: lighter tile, faint label; new-tab page: dashed, faded, "Suggested"); they are not saved unless
   the user adds one (Square on a suggested keyboard tile, or L3 / Add this site on the page). Computed once when the
   tile page or the new-tab page opens (and when the shortcut count changes), never per frame.
The pure logic (prefix parsing, URL encoding, template validation, file parsing, history ranking) is
engine/entry/OmniSearchTiles.h (no WebKit, no SDL), tested with g++ by test_search_tiles.cpp.

Anchors (OmniBrowser.cpp, each exactly once; none is touched by apply_site_zoom / apply_file_downloads /
apply_grabber_suspects or the rc6 recipe's tools): the OmniBlocker.h include, omniShortcutActivate / omniShortcutRemove
heads, the Sites key, submitKeyboard's address branch, the tile page label, the new-tab page header comment, CSS and
shortcut grid, and the end of omniSuggestUpdate.
usage: apply_search_tiles.py <engine tree>   (writes engine/entry/OmniSearchTiles.h; idempotent; keeps CRLF)
"""
import sys
from pathlib import Path

MARK = 'OMNI_SEARCH_TILES_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

HEADER = r'''// OMNI_SEARCH_TILES_V1: search shortcuts ("yt lofi beats") and most-visited tiles, the pure part (no WebKit, no SDL).
// Written by apply_search_tiles.py; tested on the host with g++ (test_search_tiles.cpp).
#pragma once
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <map>
#include <string>
#include <sys/stat.h>
#include <vector>

namespace OmniSearchTiles {

struct Engine { std::string prefix, name, tmpl; };
constexpr size_t kMaxEngines = 30, kMaxPrefix = 16, kMaxTemplate = 1024, kMaxName = 40, kMaxFile = 64 * 1024;
constexpr long long kWindow = 30LL * 24 * 3600;   // most-visited: the last 30 days

inline std::string lower(std::string s)
{
    for (auto& c : s) if (c >= 'A' && c <= 'Z') c = char(c - 'A' + 'a');
    return s;
}
inline std::string trim(const std::string& v)
{
    const size_t a = v.find_first_not_of(" \t\r\n");
    if (a == std::string::npos) return std::string();
    return v.substr(a, v.find_last_not_of(" \t\r\n") - a + 1);
}

inline const std::vector<Engine>& builtins()
{
    static const std::vector<Engine> list = {
        { "yt", "YouTube", "https://www.youtube.com/results?search_query=%s" },
        { "w", "Wikipedia", "https://en.wikipedia.org/w/index.php?search=%s" },
        { "r", "Reddit", "https://www.reddit.com/search/?q=%s" },
        { "g", "Google", "https://www.google.com/search?q=%s" },
        { "d", "DuckDuckGo", "https://duckduckgo.com/?q=%s" },
        { "a", "Amazon", "https://www.amazon.com/s?k=%s" },
        { "m", "Google Maps", "https://www.google.com/maps/search/?api=1&query=%s" },
    };
    return list;
}

// UTF-8 percent-encoding (RFC 3986): unreserved bytes kept, every other byte %XX (upper case); space is %20.
inline std::string encode(const std::string& q)
{
    static const char hex[] = "0123456789ABCDEF";
    std::string out;
    out.reserve(q.size() * 3);
    for (unsigned char c : q) {
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '-' || c == '_' || c == '.' || c == '~') out += char(c);
        else { out += '%'; out += hex[c >> 4]; out += hex[c & 15]; }
    }
    return out;
}

inline bool validPrefix(const std::string& p)
{
    if (p.empty() || p.size() > kMaxPrefix) return false;
    for (unsigned char c : p)
        if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '!' || c == '-' || c == '_')) return false;
    return true;
}

static inline bool isHex(char c) { return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F'); }

// https:// only; a plain host (letters, digits, '.', '-', optional :port), no credentials; at least one %s after
// the host; every other '%' is %XX; printable ASCII without space, quotes, <>, backslash, backtick, {}|^.
inline bool validTemplate(const std::string& t)
{
    if (t.size() > kMaxTemplate || lower(t.substr(0, 8)) != "https://") return false;
    for (unsigned char c : t)
        if (c <= 0x20 || c >= 0x7f || strchr("\"'<>\\`{}|^", c)) return false;
    const size_t hs = 8, he = t.find_first_of("/?#", hs);
    const std::string auth = t.substr(hs, he == std::string::npos ? std::string::npos : he - hs);
    std::string host = auth, port;
    const size_t colon = auth.find(':');
    if (colon != std::string::npos) { host = auth.substr(0, colon); port = auth.substr(colon + 1); if (port.empty() || port.size() > 5) return false; }
    for (char c : port) if (c < '0' || c > '9') return false;
    if (host.empty() || host.find('.') == std::string::npos || host.front() == '.' || host.back() == '.' || host.front() == '-') return false;
    for (char c : host) {
        const char l = char(c >= 'A' && c <= 'Z' ? c - 'A' + 'a' : c);
        if (!((l >= 'a' && l <= 'z') || (l >= '0' && l <= '9') || l == '.' || l == '-')) return false;
    }
    if (he == std::string::npos) return false;
    bool query = false;
    for (size_t i = he; i < t.size(); ++i) {
        if (t[i] != '%') continue;
        if (i + 1 < t.size() && t[i + 1] == 's') { query = true; ++i; continue; }
        if (i + 2 < t.size() && isHex(t[i + 1]) && isHex(t[i + 2])) { i += 2; continue; }
        return false;
    }
    return query;
}

// Host of an http(s) address, lower case, without credentials, port, trailing dot and a leading "www."; "" otherwise.
inline std::string hostOf(const std::string& url)
{
    const std::string l = lower(url.substr(0, 8));
    size_t s;
    if (l.rfind("https://", 0) == 0) s = 8; else if (l.rfind("http://", 0) == 0) s = 7; else return std::string();
    const size_t e = url.find_first_of("/?#", s);
    std::string a = lower(url.substr(s, e == std::string::npos ? std::string::npos : e - s));
    const size_t at = a.rfind('@');
    if (at != std::string::npos) a = a.substr(at + 1);
    if (!a.empty() && a[0] == '[') { const size_t b = a.find(']'); a = b == std::string::npos ? std::string() : a.substr(0, b + 1); }
    else { const size_t c = a.find(':'); if (c != std::string::npos) a = a.substr(0, c); }
    while (!a.empty() && a.back() == '.') a.pop_back();
    if (a.rfind("www.", 0) == 0 && a.find('.', 4) != std::string::npos) a = a.substr(4);
    return a;
}
inline bool localHost(const std::string& h)
{
    return h == "localhost" || h.rfind("127.", 0) == 0 || h == "[::1]" || h == "0.0.0.0" || (h.size() > 10 && h.compare(h.size() - 10, 10, ".localhost") == 0);
}

// One engine per line: "prefix<TAB>template[<TAB>Name]" (spaces instead of the first TAB are accepted); '#' comments
// and blank lines skipped; the first entry of a prefix wins; at most kMaxEngines. *rejected counts invalid lines.
inline std::vector<Engine> parseFile(const std::string& text, int* rejected = nullptr)
{
    std::vector<Engine> out;
    int bad = 0;
    size_t pos = text.compare(0, 3, "\xEF\xBB\xBF") == 0 ? 3 : 0;
    while (pos < text.size()) {
        size_t e = text.find('\n', pos);
        if (e == std::string::npos) e = text.size();
        const std::string line = trim(text.substr(pos, e - pos));
        pos = e + 1;
        if (line.empty() || line[0] == '#') continue;
        std::string prefix, tmpl, name;
        const size_t t1 = line.find('\t');
        if (t1 != std::string::npos) {
            prefix = line.substr(0, t1);
            const size_t t2 = line.find('\t', t1 + 1);
            tmpl = trim(line.substr(t1 + 1, t2 == std::string::npos ? std::string::npos : t2 - t1 - 1));
            if (t2 != std::string::npos) name = trim(line.substr(t2 + 1));
        } else {
            const size_t sp = line.find(' ');
            if (sp == std::string::npos) { ++bad; continue; }
            prefix = line.substr(0, sp);
            tmpl = trim(line.substr(sp + 1));
        }
        prefix = lower(trim(prefix));
        if (!validPrefix(prefix) || !validTemplate(tmpl) || out.size() >= kMaxEngines) { ++bad; continue; }
        bool dup = false;
        for (const auto& x : out) if (x.prefix == prefix) dup = true;
        if (dup) { ++bad; continue; }
        for (auto& c : name) if ((unsigned char)c < 0x20) c = ' ';
        if (name.size() > kMaxName) name.resize(kMaxName);   // (may cut a UTF-8 sequence; the label drawer copes)
        if (name.empty()) {
            const std::string h = hostOf(tmpl);
            for (const auto& b : builtins()) if (hostOf(b.tmpl) == h) { name = b.name; break; }
            if (name.empty()) name = h;
        }
        out.push_back({ prefix, name, tmpl });
    }
    if (rejected) *rejected = bad;
    return out;
}

// An address, not a search: a scheme or a special prefix, "://" in the first word, or one word with a dot / port.
inline bool looksLikeUrl(const std::string& input)
{
    const std::string l = lower(trim(input));
    for (const char* p : { "http://", "https://", "about:", "data:", "javascript:", "file:", "blob:", "view-source:" })
        if (l.rfind(p, 0) == 0) return true;
    const size_t sp = l.find_first_of(" \t");
    if (l.substr(0, sp).find("://") != std::string::npos) return true;
    if (sp == std::string::npos && (l.find('.') != std::string::npos || l.find(':') != std::string::npos)) return true;
    return false;
}

struct Match { std::string url, name, query; };
// "yt lofi beats" -> YouTube's search for "lofi beats". The first word must be exactly a prefix (case-insensitive),
// then whitespace and a non-empty query; never for an address.
inline bool match(const std::string& input, const std::vector<Engine>& engines, Match& m)
{
    const std::string v = trim(input);
    if (v.empty() || looksLikeUrl(v)) return false;
    const size_t sp = v.find_first_of(" \t");
    if (sp == std::string::npos) return false;
    const std::string word = lower(v.substr(0, sp)), q = trim(v.substr(sp + 1));
    if (q.empty()) return false;
    for (const auto& e : engines) {
        if (e.prefix != word) continue;
        const std::string enc = encode(q);
        std::string url;
        for (size_t i = 0; i < e.tmpl.size(); ++i) {
            if (e.tmpl[i] == '%' && i + 1 < e.tmpl.size() && e.tmpl[i + 1] == 's') { url += enc; ++i; }
            else url += e.tmpl[i];
        }
        m.url = url; m.name = e.name; m.query = q;
        return true;
    }
    return false;
}

// The engine list: the file when it exists (re-read when its size or mtime changes), else the built-ins.
class Store {
public:
    const std::vector<Engine>& get(const char* path)
    {
        struct stat st;
        const bool exists = stat(path, &st) == 0;
        const long long m = exists ? (long long)st.st_mtime : -1, z = exists ? (long long)st.st_size : -1;
        if (loaded_ && m == mtime_ && z == size_) return list_;
        loaded_ = true; mtime_ = m; size_ = z;
        list_ = builtins();
        rejected_ = 0;
        if (!exists) return list_;
        FILE* f = fopen(path, "rb");
        if (!f) return list_;
        std::string text;
        char buf[4096];
        size_t n;
        while ((n = fread(buf, 1, sizeof(buf), f)) > 0 && text.size() < kMaxFile) text.append(buf, n);
        fclose(f);
        list_ = parseFile(text, &rejected_);
        fprintf(stderr, "OMNI SEARCH SHORTCUTS: %zu from %s (%d lines rejected)\n", list_.size(), path, rejected_);
        return list_;
    }
    int rejected() const { return rejected_; }
private:
    std::vector<Engine> list_;
    bool loaded_ = false;
    long long mtime_ = -1, size_ = -1;
    int rejected_ = 0;
};

// --- most-visited tiles -----------------------------------------------------------------------------
struct Site { std::string url, title, host; int visits = 0; long long last = 0; };

// The address's site root ("https://www.example.com/") and whether the address is that root.
inline std::string siteRoot(const std::string& url, bool* isRoot = nullptr)
{
    const size_t s = url.find("://");
    if (s == std::string::npos) return std::string();
    const size_t e = url.find_first_of("/?#", s + 3);
    std::string a = url.substr(s + 3, e == std::string::npos ? std::string::npos : e - s - 3);
    const size_t at = a.rfind('@');
    if (at != std::string::npos) a = a.substr(at + 1);
    if (isRoot) { const std::string rest = e == std::string::npos ? std::string() : url.substr(e); *isRoot = rest.empty() || rest == "/"; }
    return lower(url.substr(0, s)) + "://" + lower(a) + "/";
}

// History entries need .time (seconds, 0 = unknown), .url and .title, oldest first. Ranked by visits per host in the
// last 30 days (every visit when no entry has a time), then the latest visit. Hosts of `exclude` (saved shortcuts),
// local hosts and non-http(s) addresses are left out. Title: the latest title of the site's root page, else the host.
template <class History>
std::vector<Site> mostVisited(const History& history, long long now, const std::vector<std::string>& exclude, size_t max)
{
    bool timed = false;
    for (const auto& v : history) if (v.time > 0) { timed = true; break; }
    std::vector<std::string> skip;
    for (const auto& u : exclude) {
        std::string h = hostOf(u);
        if (h.empty() && u.find("://") == std::string::npos) h = hostOf("https://" + u);
        if (!h.empty()) skip.push_back(h);
    }
    struct Agg { int visits = 0; long long last = 0; size_t order = 0; std::string root, title; };
    std::map<std::string, Agg> by;
    size_t order = 0;
    for (const auto& v : history) {
        ++order;
        if (timed && (v.time <= 0 || now - v.time > kWindow)) continue;
        const std::string h = hostOf(v.url);
        if (h.empty() || localHost(h) || std::find(skip.begin(), skip.end(), h) != skip.end()) continue;
        Agg& a = by[h];
        ++a.visits;
        a.last = std::max(a.last, (long long)v.time);
        a.order = order;
        bool isRoot = false;
        a.root = siteRoot(v.url, &isRoot);
        if (isRoot && !trim(v.title).empty()) a.title = trim(v.title);
    }
    std::vector<std::pair<std::string, Agg>> list(by.begin(), by.end());
    std::sort(list.begin(), list.end(), [](const auto& x, const auto& y) {
        if (x.second.visits != y.second.visits) return x.second.visits > y.second.visits;
        if (x.second.last != y.second.last) return x.second.last > y.second.last;
        return x.second.order > y.second.order;
    });
    std::vector<Site> out;
    for (const auto& [h, a] : list) {
        if (out.size() >= max) break;
        Site s;
        s.url = a.root; s.host = h; s.visits = a.visits; s.last = a.last;
        s.title = a.title.empty() ? h : a.title;
        if (s.title.size() > 120) s.title.resize(120);
        out.push_back(std::move(s));
    }
    return out;
}

} // namespace OmniSearchTiles
'''

STATE = '''#include "OmniSearchTiles.h" // OMNI_SEARCH_TILES_V1: search shortcuts and most-visited tiles (pure)
'''

ACTIVATE_OLD = '''static void omniShortcutActivate(int tile)
{
    omniShortcutsLoad();
    if (tile == 0) { omniShortcutAddCurrent(); return; }
'''
ACTIVATE_NEW = '''// OMNI_SEARCH_TILES_V1 ----------------------------------------------------------------------------
// Search shortcuts: "yt lofi beats" + Go searches YouTube (/data/omni/search-shortcuts.txt, built-ins when missing).
static const char* const omniStPath = "/data/omni/search-shortcuts.txt";
static OmniSearchTiles::Store omniStEngines;
static std::string omniStResolve(const std::string& typed)
{
    OmniSearchTiles::Match m;
    if (!omniTestMode() && OmniSearchTiles::match(typed, omniStEngines.get(omniStPath), m)) return m.url;
    return typed;
}
// Most-visited sites for the empty shortcut tiles: computed when the tile page / new-tab page opens or the shortcut
// count changes, never per frame. Not saved unless the user adds one (Square on the tile).
static std::vector<OmniSearchTiles::Site> omniStSites;
static bool omniStSitesStale = true;
static size_t omniStSitesFor = size_t(-1);
static void omniStSitesCompute();   // after the history (needs omniHistory)
static const OmniSearchTiles::Site* omniStTileAt(int tile)
{
    omniShortcutsLoad();
    if (omniStSitesStale || omniStSitesFor != omniShortcuts.size()) omniStSitesCompute();
    const int k = tile - 1 - int(omniShortcuts.size());
    return tile >= 1 && tile <= omniShortcutMax && k >= 0 && k < int(omniStSites.size()) ? &omniStSites[size_t(k)] : nullptr;
}
static void omniShortcutActivate(int tile)
{
    omniShortcutsLoad();
    if (tile == 0) { omniShortcutAddCurrent(); return; }
    if (tile > int(omniShortcuts.size())) { // OMNI_SEARCH_TILES_V1: a suggested site opens (it is not saved)
        if (const OmniSearchTiles::Site* st = omniStTileAt(tile)) { const std::string url = st->url; editing = pageEditing = false; omniKbPage = 0; navigate(url); }
        return;
    }
'''

REMOVE_OLD = '''static void omniShortcutRemove(int tile)
{
    omniShortcutsLoad();
'''
REMOVE_NEW = REMOVE_OLD + '''    if (tile > int(omniShortcuts.size())) { // OMNI_SEARCH_TILES_V1: Square on a suggested site saves it
        const OmniSearchTiles::Site* st = omniStTileAt(tile);
        if (!st || omniShortcuts.size() >= size_t(omniShortcutMax)) return;
        const std::string title = st->title;
        omniShortcuts.emplace_back(st->url, title);
        omniShortcutsSave();
        omniStSitesStale = true;
        notice("Saved to shortcuts: " + title);
        return;
    }
'''

BROWSER = [
    ('#include "OmniBlocker.h"\n', '#include "OmniBlocker.h"\n' + STATE),
    (ACTIVATE_OLD, ACTIVATE_NEW),
    (REMOVE_OLD, REMOVE_NEW),
    ('    if (!pageEditing) { navigate(address); return; }\n',
     '    if (!pageEditing) { navigate(omniStResolve(address)); return; } // ' + MARK + ': "yt lofi beats" searches YouTube\n'),
    ('    case omniKbSitesKey: if (omniKb.kind == 0) { omniKbPage = 1; omniShortcutSel = 0; } return;\n',
     '    case omniKbSitesKey: if (omniKb.kind == 0) { omniKbPage = 1; omniShortcutSel = 0; omniStSitesStale = true; } return; // ' + MARK + ': suggestions once per opening\n'),
    ('            else if (used) omniLabel(omniShortcuts[i - 1].second, x + 12, y + keyH / 2.f, omniSmall, ink, 0, tileW - 28);\n',
     '            else if (used) omniLabel(omniShortcuts[i - 1].second, x + 12, y + keyH / 2.f, omniSmall, ink, 0, tileW - 28);\n'
     '            else if (const OmniSearchTiles::Site* st = omniStTileAt(i)) { // ' + MARK + ': a suggested site, dimmer\n'
     '                if (!sel) fillRounded(x, y, tileW - 4, keyH, omniRadius, omniMix(emptyKey, T.key, 0.3f));\n'
     '                omniLabel(st->title, x + 12, y + keyH / 2.f, omniSmall, sel ? T.accentInk : T.inkDim, 0, tileW - 28);\n'
     '            }\n'),
    ('// --- new-tab page --------------------------------------------------------------------------------\n',
     '''// OMNI_SEARCH_TILES_V1: most-visited sites (history by host, last 30 days; saved shortcuts and local hosts left out).
// Private tabs never write history (omniEverydayFinished).
static void omniStSitesCompute()
{
    omniShortcutsLoad();
    omniHistoryLoad();
    std::vector<std::string> saved;
    for (const auto& s : omniShortcuts) saved.push_back(s.first);
    omniStSites = OmniSearchTiles::mostVisited(omniHistory, (long long)time(nullptr), saved, size_t(omniShortcutMax));
    omniStSitesStale = false;
    omniStSitesFor = omniShortcuts.size();
}

// --- new-tab page --------------------------------------------------------------------------------
'''),
    ('        "p{color:var(--inkFaint);font-size:16px}"\n',
     '        "p{color:var(--inkFaint);font-size:16px}"\n'
     '        "a.s{opacity:.55;background:transparent;outline:2px dashed var(--line);outline-offset:-2px}a.s:hover,a.s:focus{opacity:1;outline:2px solid var(--accent)}a.s i{background:var(--inkFaint)}" // ' + MARK + '\n'),
    ('    else { h += "<div class=\\"g\\">"; for (auto& [url, title] : omniShortcuts) tile(url, title); h += "</div>"; }\n',
     '''    { // OMNI_SEARCH_TILES_V1: the grid's empty slots (to 8 tiles, or the end of its last row) show suggested sites
        omniStSitesCompute();
        const size_t n = std::min(omniShortcuts.size(), size_t(omniShortcutMax));
        const size_t k = std::min(omniStSites.size(), std::min<size_t>(omniShortcutMax, std::max<size_t>(8, (n + 3) / 4 * 4)) - n);
        if (n + k) h += "<div class=\\"g\\">";
        for (auto& [url, title] : omniShortcuts) tile(url, title);
        for (size_t i = 0; i < k; ++i) {
            const auto& st = omniStSites[i];
            const std::string letter(1, char(toupper(static_cast<unsigned char>(st.host.empty() ? '?' : st.host[0]))));
            h += "<a class=\\"s\\" href=\\"" + omniHtmlEscape(st.url) + "\\" title=\\"Suggested: often visited, not saved\\"><i>" + omniHtmlEscape(letter)
                + "</i><span><b>" + omniHtmlEscape(st.title) + "</b><small>Suggested \\xC2\\xB7 " + omniHtmlEscape(st.host) + "</small></span></a>";
        }
        if (n + k) h += "</div>";
    }
'''),
    ('    omniF3SuggestMerge(local);\n',
     '''    omniF3SuggestMerge(local);
    { // OMNI_SEARCH_TILES_V1: a search shortcut ("yt lofi beats") is the first suggestion
        OmniSearchTiles::Match m;
        if (OmniSearchTiles::match(address, omniStEngines.get(omniStPath), m)) {
            OmniSuggestion s;
            s.url = m.url;
            s.title = "Search " + m.name + " for \\xE2\\x80\\x9C" + m.query + "\\xE2\\x80\\x9D";
            omniSuggestions.insert(omniSuggestions.begin(), std::move(s));
            if (omniSuggestions.size() > 5) omniSuggestions.pop_back();
        }
    }
'''),
]


def main():
    p = root / 'OmniBrowser.cpp'
    raw = p.read_bytes()
    nl = '\r\n' if b'\r\n' in raw else '\n'
    s = raw.decode('utf-8')
    if MARK in s:
        print('OmniBrowser.cpp: already ' + MARK)
    else:
        for old0, new0 in BROWSER:
            old, new = old0.replace('\n', nl), new0.replace('\n', nl)
            n = s.count(old)
            if n != 1:
                sys.exit('OmniBrowser.cpp: anchor found %d times: %r' % (n, old0.strip()[:90]))
            s = s.replace(old, new, 1)
        p.write_bytes(s.encode('utf-8'))
        print('OmniBrowser.cpp: applied (%d anchors)' % len(BROWSER))
    h = root / 'OmniSearchTiles.h'
    data = HEADER.replace('\n', nl).encode('utf-8')
    if not h.exists() or h.read_bytes() != data:
        h.write_bytes(data)
        print('OmniSearchTiles.h: written')
    else:
        print('OmniSearchTiles.h: already')
    print('applied ' + MARK)


main()
