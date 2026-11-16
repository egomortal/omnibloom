#!/usr/bin/env python3
"""OMNI_TAB_SEARCH_V1 (2026-11-16): find an open tab from the address bar.

What the user sees
  - Typing in the address bar (the suggestion list under it, OMNI_KEYBOARD_V2), open tabs that match come first:
        [tab icon]  GitHub - omni/issues          Switch to tab · github.com
        [tab icon]  Lo-fi radio                   Switch to tab · Pinned · youtube.com
    then recently closed tabs (the "Reopen closed tab" list, omniFxClosed, newest first):
        [reload]    Example article               Reopen · example.com
    then the usual history / shortcut / search-engine rows. At most 3 tab rows and 2 reopen rows; the list stays at
    5 rows in all (it never grows toward the keyboard panel or OMNI_KB_WORDS_V1's word chips in its preview row).
    A history row with the same address as a tab row is dropped (no duplicate). A search shortcut ("yt lofi",
    OMNI_SEARCH_TILES_V1) stays the very first row.
  - Up from the top row of keys selects the rows as before; Cross (or Triangle, or a click) on a "Switch to tab" row
    shows that tab (activate(): an unloaded tab reloads as usual; the keyboard closes) instead of loading the
    address in the current tab. On a "Reopen" row it opens a new tab with that page and removes it from the closed
    list (same as Tabs > Reopen closed tab; the tab limit / memory guard can refuse and says why).
  - The current tab is never offered. Only web pages (http / https) are offered (no new-tab / omni:// pages).
  - Private: in a normal tab only normal tabs are offered; in a private tab private and normal tabs are offered
    ("Switch to private tab" on the private ones). Closed private tabs are never kept (omniFxTabClosing), so
    "Reopen" never shows one.

Matching (pure, engine/entry/OmniTabSearch.h, no SDL / WebKit): the typed text lowercased, trimmed, without
http(s):// and www., split at spaces; every word must match the tab's title or address:
    quality 0: a word of the title starts with it, or a label of the host (split at . and -) starts with it, or the
               bare address (no scheme / www.) starts with the whole query;
    quality 1: it occurs anywhere in the title or the bare address (only words of 2+ characters, so one letter
               doesn't match every tab).
  A tab's quality is its worst word's. Ranking: quality, then most recently shown first (omniTmTabs[t].shownAt,
  OmniTabMemory.h; never-shown background tabs last), then tab order. Two tabs with the same bare address: only
  the more recent one. Closed tabs rank by quality then newest; ones whose address is open in a tab are skipped.
Cost: everything runs inside omniSuggestUpdate(), which returns at once unless the typed text changed (or the
search engine's answer arrived): a pass over <= 16 tabs and <= 10 closed tabs per change, nothing per frame.

Files
  engine/entry/OmniTabSearch.h       (new, pure) normalize / match quality / rank / detail texts.
  engine/entry/OmniTabSearchShell.h  (new, shell) builds the rows, switches / reopens, draws the tab icon.
  Tested by tools/test_tab_search.cpp:  g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_tab_search.cpp -o t && ./t

Anchors (exactly once each; MARK makes each file idempotent):
  OmniBrowser.cpp   the OmniHistoryPlus.h include line (pure include after it);
                    the OmniSuggestion struct line (row kind + tab fields, forward declarations after it);
                    the omniF3SuggestMerge(local) line in omniSuggestUpdate (filter before, prepend after);
                    the first two lines of omniSuggestGo (switch / reopen instead of navigate);
                    the three lines in omniSuggestDraw that compute the detail and draw the two labels (icon + offset).
  OmniFeatures3.h   the OmniSiteClearShell.h include line (OmniTabSearchShell.h after it).
Apply AFTER apply_history_plus.py and apply_site_clear.py (their lines are anchors).
usage: apply_tab_search.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_TAB_SEARCH_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_TAB_SEARCH_V1: the pure part of "Switch to tab" / "Reopen" address suggestions (no SDL, no WebKit).
// The shell side is OmniTabSearchShell.h; the reasons are in tools/apply_tab_search.py. Tested on the host with g++
// (test_tab_search.cpp).
#pragma once
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace OmniTabSearch {

constexpr size_t kMaxTabs = 3, kMaxReopen = 2, kMaxRows = 5;
enum Kind { kNone = 0, kSwitch = 1, kReopen = 2 };

inline std::string lower(std::string s)
{
    for (char& c : s) if (c >= 'A' && c <= 'Z') c = char(c + ('a' - 'A'));
    return s;
}
inline std::string trim(const std::string& s)
{
    const size_t a = s.find_first_not_of(" \t\r\n");
    if (a == std::string::npos) return std::string();
    return s.substr(a, s.find_last_not_of(" \t\r\n") - a + 1);
}
inline std::string stripScheme(std::string s)   // s lowercased
{
    for (const char* p : { "https://", "http://" }) {
        const std::string q(p);
        if (s.compare(0, q.size(), q) == 0) { s.erase(0, q.size()); break; }
    }
    if (s.compare(0, 4, "www.") == 0) s.erase(0, 4);
    return s;
}
// The typed text as matched: lowercased, trimmed, without http(s):// and www.
inline std::string normalizeQuery(const std::string& typed) { return trim(stripScheme(lower(trim(typed)))); }
// Lowercased address without scheme, www. and trailing slashes.
inline std::string bareURL(const std::string& url)
{
    std::string s = stripScheme(lower(trim(url)));
    while (!s.empty() && s.back() == '/') s.pop_back();
    return s;
}
// Lowercased host without www. and port ("" when there is none).
inline std::string hostOf(const std::string& url)
{
    std::string s = bareURL(url);
    const size_t at = s.find('@'), end0 = s.find_first_of("/?#");
    if (at != std::string::npos && (end0 == std::string::npos || at < end0)) s.erase(0, at + 1);
    s = s.substr(0, s.find_first_of("/?#"));
    if (!s.empty() && s[0] == '[') return s.substr(0, s.find(']') + 1);   // IPv6 literal
    s = s.substr(0, s.find(':'));
    return s;
}
inline std::vector<std::string> words(const std::string& q)
{
    std::vector<std::string> w;
    size_t i = 0;
    while (i < q.size()) {
        while (i < q.size() && q[i] == ' ') ++i;
        const size_t j = q.find(' ', i);
        const size_t e = j == std::string::npos ? q.size() : j;
        if (e > i) w.push_back(q.substr(i, e - i));
        i = e;
    }
    return w;
}
inline bool wordChar(unsigned char c) { return (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c >= 0x80; }
// `hay` (lowercased) has a word starting with `w`: at 0 or right after a non-word character.
inline bool wordPrefix(const std::string& hay, const std::string& w)
{
    if (w.empty()) return false;
    for (size_t p = hay.find(w); p != std::string::npos; p = hay.find(w, p + 1))
        if (p == 0 || !wordChar(static_cast<unsigned char>(hay[p - 1]))) return true;
    return false;
}
// A label of `host` (split at . and -) starts with `w`.
inline bool hostLabelPrefix(const std::string& host, const std::string& w)
{
    if (w.empty()) return false;
    for (size_t p = host.find(w); p != std::string::npos; p = host.find(w, p + 1))
        if (p == 0 || host[p - 1] == '.' || host[p - 1] == '-') return true;
    return false;
}
// 0: word-prefix match, 1: substring match, -1: no match. `query` is normalizeQuery()'s result.
inline int quality(const std::string& title, const std::string& url, const std::string& query)
{
    if (query.empty()) return -1;
    const std::string t = lower(title), bare = bareURL(url), host = hostOf(url);
    if (bare.compare(0, query.size(), query) == 0) return 0;
    int worst = 0;
    const std::vector<std::string> ws = words(query);
    if (ws.empty()) return -1;
    for (const std::string& w : ws) {
        if (wordPrefix(t, w) || hostLabelPrefix(host, w)) continue;
        if (w.size() >= 2 && (t.find(w) != std::string::npos || bare.find(w) != std::string::npos)) { worst = 1; continue; }
        return -1;
    }
    return worst;
}
// Private tabs are offered only while typing in a private tab; normal tabs always.
inline bool visible(bool itemPrivate, bool typingInPrivate) { return !itemPrivate || typingInPrivate; }

struct Item {
    std::string url, title;
    uint64_t recency = 0;    // larger: used more recently
    bool priv = false, current = false, web = true;
    int id = -1;             // the caller's handle
};
struct Hit { int id; int quality; };

// Matching items, best first, at most `max`; one per bare address (the best-ranked one).
inline std::vector<Hit> rank(const std::vector<Item>& items, const std::string& typed, bool typingInPrivate, size_t max,
                             const std::vector<std::string>& skipBare = {})
{
    const std::string q = normalizeQuery(typed);
    struct S { Hit h; uint64_t rec; size_t order; std::string bare; };
    std::vector<S> found;
    if (q.empty() || max == 0) return {};
    for (size_t i = 0; i < items.size(); ++i) {
        const Item& it = items[i];
        if (it.current || !it.web || !visible(it.priv, typingInPrivate)) continue;
        const int qy = quality(it.title, it.url, q);
        if (qy < 0) continue;
        std::string b = bareURL(it.url);
        if (std::find(skipBare.begin(), skipBare.end(), b) != skipBare.end()) continue;
        found.push_back({ { it.id, qy }, it.recency, i, std::move(b) });
    }
    std::sort(found.begin(), found.end(), [](const S& a, const S& b) {
        if (a.h.quality != b.h.quality) return a.h.quality < b.h.quality;
        if (a.rec != b.rec) return a.rec > b.rec;
        return a.order < b.order;
    });
    std::vector<Hit> out;
    std::vector<std::string> seen;
    for (const S& s : found) {
        if (std::find(seen.begin(), seen.end(), s.bare) != seen.end()) continue;
        seen.push_back(s.bare);
        out.push_back(s.h);
        if (out.size() >= max) break;
    }
    return out;
}
// Shown address of a row: "github.com" (host without www.), or the bare address when there is no host.
inline std::string shownHost(const std::string& url)
{
    const std::string h = hostOf(url);
    return h.empty() ? bareURL(url) : h;
}
// The dim text after the title.
inline std::string detail(Kind k, const std::string& url, bool pinned, bool priv)
{
    std::string s = k == kReopen ? "Reopen" : priv ? "Switch to private tab" : "Switch to tab";
    if (k == kSwitch && pinned) s += " \xC2\xB7 Pinned";
    return s + " \xC2\xB7 " + shownHost(url);
}
// Keeps `rows` within kMaxRows after `extra` rows are put in front of it: how many of `rows` stay.
inline size_t keepAfter(size_t extra, size_t rows) { return extra >= kMaxRows ? 0 : std::min(rows, kMaxRows - extra); }

} // namespace OmniTabSearch
'''

SHELL = r'''// OMNI_TAB_SEARCH_V1: "Switch to tab" / "Reopen" rows in the address suggestions (shell side). Included from
// OmniFeatures3.h (inside OmniBrowser.cpp's anonymous namespace, after OmniSiteClearShell.h). The pure part is
// OmniTabSearch.h; the reasons are in tools/apply_tab_search.py. Main thread only; runs only from
// omniSuggestUpdate() (once per change of the typed text) and when a row is chosen / drawn.
#pragma once

namespace OTQ = OmniTabSearch;

static std::vector<OmniSuggestion> omniTqRows;   // the tab / reopen rows of the current text

static uint64_t omniTqShownAt(const Tab* t)
{
    auto f = omniTmTabs.find(t);   // no entry: never shown (a background tab), least recent
    return f == omniTmTabs.end() ? 0 : f->second.shownAt;
}
static std::string omniTqTabURL(const Tab& t) { return !t.omniLazyURL.empty() ? t.omniLazyURL : t.url; }

// Before omniF3SuggestMerge: builds omniTqRows and drops history rows that a tab row already offers.
static void omniTqFilter(std::vector<OmniSuggestion>& local)
{
    omniTqRows.clear();
    const Tab* cur = active();
    const bool priv = cur && cur->omniPrivate;
    std::vector<OTQ::Item> items;
    std::vector<std::string> openBare;
    for (size_t i = 0; i < tabs.size(); ++i) {
        const Tab& t = *tabs[i];
        OTQ::Item it;
        it.url = omniTqTabURL(t);
        it.title = t.title;
        it.recency = omniTqShownAt(&t);
        it.priv = t.omniPrivate;
        it.current = &t == cur;
        it.web = omniWebURL(it.url) && !t.omniNewTabPage && !t.omniPagesTab;
        it.id = int(i);
        if (it.web) openBare.push_back(OTQ::bareURL(it.url));
        items.push_back(std::move(it));
    }
    for (const OTQ::Hit& h : OTQ::rank(items, address, priv, OTQ::kMaxTabs)) {
        const Tab& t = *tabs[size_t(h.id)];
        OmniSuggestion s;
        s.url = items[size_t(h.id)].url;
        s.title = t.title.empty() ? omniShownURL(s.url) : t.title;
        s.omniTqKind = OTQ::kSwitch;
        s.omniTqTab = &t;
        s.omniTqPinned = omniPtPinned(t);
        s.omniTqPrivate = t.omniPrivate;
        omniTqRows.push_back(std::move(s));
    }
    std::vector<OTQ::Item> closed;   // omniFxClosed: newest last; never private
    for (size_t i = 0; i < omniFxClosed.size(); ++i) {
        OTQ::Item it;
        it.url = omniFxClosed[i].first;
        it.title = omniFxClosed[i].second;
        it.recency = i + 1;
        it.web = omniWebURL(it.url);
        it.id = int(i);
        closed.push_back(std::move(it));
    }
    for (const OTQ::Hit& h : OTQ::rank(closed, address, priv, OTQ::kMaxReopen, openBare)) {
        OmniSuggestion s;
        s.url = closed[size_t(h.id)].url;
        s.title = closed[size_t(h.id)].title.empty() ? omniShownURL(s.url) : closed[size_t(h.id)].title;
        s.omniTqKind = OTQ::kReopen;
        omniTqRows.push_back(std::move(s));
    }
    if (omniTqRows.empty()) return;
    local.erase(std::remove_if(local.begin(), local.end(), [](const OmniSuggestion& l) {
        const std::string b = OTQ::bareURL(l.url);
        for (const auto& r : omniTqRows) if (OTQ::bareURL(r.url) == b) return true;
        return false;
    }), local.end());
}
// After omniF3SuggestMerge: the tab rows go first; the list stays at OTQ::kMaxRows.
static void omniTqPrepend()
{
    if (omniTqRows.empty()) return;
    const size_t keep = OTQ::keepAfter(omniTqRows.size(), omniSuggestions.size());
    omniSuggestions.resize(keep);
    omniSuggestions.insert(omniSuggestions.begin(), omniTqRows.begin(), omniTqRows.end());
    if (omniSuggestions.size() > OTQ::kMaxRows) omniSuggestions.resize(OTQ::kMaxRows);
}
// Cross / Triangle / click on a row: true when it was a tab row (handled here).
static bool omniTqGo(const OmniSuggestion& s)
{
    if (s.omniTqKind == OTQ::kSwitch) {
        for (size_t i = 0; i < tabs.size(); ++i) {
            if (tabs[i].get() != s.omniTqTab) continue;
            fprintf(stderr, "OMNI TAB SEARCH: switch to tab %zu of %zu\n", i, tabs.size()); fflush(stderr);
            editing = false;
            activate(i);
            omniSuggestFor = "\x01";
            omniShellDirty = true;
            return true;
        }
        notice("That tab was closed");   // can't happen while typing; the address loads here instead
        return false;
    }
    if (s.omniTqKind == OTQ::kReopen) {
        const std::string url = s.url, title = s.title;
        if (!newTab()) return true;   // newTab() says why (limit or memory)
        for (size_t i = omniFxClosed.size(); i-- > 0;)
            if (omniFxClosed[i].first == url) { omniFxClosed.erase(omniFxClosed.begin() + long(i)); break; }
        navigate(url);
        notice("Reopened " + title);
        fprintf(stderr, "OMNI TAB SEARCH: reopened a closed tab (%zu left)\n", omniFxClosed.size()); fflush(stderr);
        omniSuggestFor = "\x01";
        omniShellDirty = true;
        return true;
    }
    return false;
}
static std::string omniTqDetail(const OmniSuggestion& s)
{
    return OTQ::detail(OTQ::Kind(s.omniTqKind), s.url, s.omniTqPinned, s.omniTqPrivate);
}
// The row icon at x (layout px), centred on cy; returns the width it takes (0: none).
static int omniTqIcon(const OmniSuggestion& s, int x, float cy, bool sel)
{
    if (!s.omniTqKind) return 0;
    const OmniTheme& T = omniTheme();
    const SDL_Color ink = sel ? T.accentInk : T.inkDim, bg = sel ? T.accent : T.raised;
    if (s.omniTqKind == OTQ::kReopen) { omniIcon(omniIconReload, x + 11, cy, ink); return 30; }
    // a tab: a nub on the top-left of an outlined page (2 px line)
    const int bx = x, by = int(cy) - 6, bw = 22, bh = 14;
    fillRounded(bx, by - 4, 10, 6, 2, ink);
    fillRounded(bx, by, bw, bh, 3, ink);
    fillRounded(bx + 2, by + 2, bw - 4, bh - 4, 2, bg);
    if (s.omniTqPrivate) omniDisc(bx + bw / 2.f, by + bh / 2.f, 2.5f, ink);
    return 30;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniHistoryPlus.h" // OMNI_HISTORY_PLUS_V1: history search, day groups, range deletes (pure)\n',
         '#include "OmniHistoryPlus.h" // OMNI_HISTORY_PLUS_V1: history search, day groups, range deletes (pure)\n'
         '#include "OmniTabSearch.h" // OMNI_TAB_SEARCH_V1: "Switch to tab" / "Reopen" address suggestions (pure)\n'),
        ('struct OmniSuggestion { std::string url, title; bool search = false; }; // OMNI_FEATURES_V3: search: a search-engine suggestion\n',
         'struct OmniSuggestion { std::string url, title; bool search = false; // OMNI_FEATURES_V3: search: a search-engine suggestion\n'
         '    int omniTqKind = 0; const void* omniTqTab = nullptr; bool omniTqPinned = false, omniTqPrivate = false; }; // OMNI_TAB_SEARCH_V1: OmniTabSearch::Kind, the tab\n'
         'static void omniTqFilter(std::vector<OmniSuggestion>& local); // OMNI_TAB_SEARCH_V1 (OmniTabSearchShell.h)\n'
         'static void omniTqPrepend();\n'
         'static bool omniTqGo(const OmniSuggestion& s);\n'
         'static std::string omniTqDetail(const OmniSuggestion& s);\n'
         'static int omniTqIcon(const OmniSuggestion& s, int x, float cy, bool sel);\n'),
        ('    omniF3SuggestMerge(local);\n',
         '    omniTqFilter(local); // OMNI_TAB_SEARCH_V1: open / recently closed tabs that match (drops their history rows)\n'
         '    omniF3SuggestMerge(local);\n'
         '    omniTqPrepend(); // OMNI_TAB_SEARCH_V1: "Switch to tab" / "Reopen" rows first, 5 rows in all\n'),
        ('    if (i < 0 || i >= int(omniSuggestions.size())) return;\n'
         '    const std::string url = omniSuggestions[i].url;\n',
         '    if (i < 0 || i >= int(omniSuggestions.size())) return;\n'
         '    if (omniSuggestions[i].omniTqKind) { // OMNI_TAB_SEARCH_V1: switch to / reopen the tab instead of loading here\n'
         '        const OmniSuggestion s = omniSuggestions[i];\n'
         '        omniSuggestSel = -1;\n'
         '        omniKbPageReset();\n'
         '        if (omniTqGo(s)) return;\n'
         '        navigate(s.url);\n'
         '        return;\n'
         '    }\n'
         '    const std::string url = omniSuggestions[i].url;\n'),
        ('        const std::string bare = s.search ? omniF3SuggestDetail() : omniShownURL(s.url); // OMNI_FEATURES_V3\n'
         '        const int w = omniLabel(s.title.empty() ? bare : s.title, omniSuggestX + 18, y + omniSuggestRow / 2.f, omniSmall, sel ? T.accentInk : T.ink, 0, 520);\n'
         '        omniLabel(bare, omniSuggestX + 30 + w, y + omniSuggestRow / 2.f, omniSmall, sel ? T.accentInk : T.inkDim, 0, omniSuggestW - 60 - w);\n',
         '        const std::string bare = s.search ? omniF3SuggestDetail() : s.omniTqKind ? omniTqDetail(s) : omniShownURL(s.url); // OMNI_FEATURES_V3 OMNI_TAB_SEARCH_V1\n'
         '        const int ix = omniTqIcon(s, omniSuggestX + 18, y + omniSuggestRow / 2.f, sel); // OMNI_TAB_SEARCH_V1: tab / reopen icon (0: none)\n'
         '        const int w = omniLabel(s.title.empty() ? bare : s.title, omniSuggestX + 18 + ix, y + omniSuggestRow / 2.f, omniSmall, sel ? T.accentInk : T.ink, 0, 520 - ix);\n'
         '        omniLabel(bare, omniSuggestX + 30 + ix + w, y + omniSuggestRow / 2.f, omniSmall, sel ? T.accentInk : T.inkDim, 0, omniSuggestW - 60 - ix - w);\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniSiteClearShell.h" // OMNI_SITE_CLEAR_V1\n',
         '#include "OmniSiteClearShell.h" // OMNI_SITE_CLEAR_V1\n'
         '#include "OmniTabSearchShell.h" // OMNI_TAB_SEARCH_V1\n'),
    ],
}


def variants(old0, s):
    """The anchor with the file's own line endings (mixed files: whichever spelling is present)."""
    for e in ('\r\n', '\n'):
        old = old0.replace('\n', e)
        if s.count(old):
            return old, e
    return old0, '\n'


def check(name, edits, mark=MARK):
    s = (root / name).read_bytes().decode('utf-8')
    if mark in s:
        return
    for old0, _ in edits:
        old, _e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))


def patch(name, edits, mark=MARK):
    p = root / name
    s = p.read_bytes().decode('utf-8')
    if mark in s:
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
    if 'OMNI_SITE_CLEAR_V1' not in (root / 'OmniFeatures3.h').read_bytes().decode('utf-8'):
        sys.exit('OmniFeatures3.h: OMNI_SITE_CLEAR_V1 missing: apply_site_clear.py first')
    if 'OMNI_HISTORY_PLUS_V1' not in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8'):
        sys.exit('OmniBrowser.cpp: OMNI_HISTORY_PLUS_V1 missing: apply_history_plus.py first')
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniTabSearch.h', PURE, 'OmniSiteClear.h'),
            write_new('OmniTabSearchShell.h', SHELL, 'OmniSiteClearShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
