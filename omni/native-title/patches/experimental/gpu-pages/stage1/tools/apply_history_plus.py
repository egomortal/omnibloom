#!/usr/bin/env python3
"""OMNI_HISTORY_PLUS_V1 (2026-11-16): a better History panel (the shell overlay opened from Options / quick access).

Before: /data/omni/history.txt, one visit per line "<unix time>TAB<url>TAB<title>", oldest first, http(s) only, about
2000 kept (omniHistoryAdd appends through omniIoQueue; trims rewrite the file); private tabs, test modes, Media
downloads tabs and reader views never record (omniEverydayFinished). The panel listed every visit newest first with
"Clear history" (asks) as row 0, Square deleting one visit, L1/R1 paging. There is no omni:// history page.

Now (same file, same format: older builds still read it; every change is ONE full rewrite queued on the background
writer omniIoQueue, never file I/O on the UI thread):
  - Triangle (or clicking the search pill): search. Omni's on-screen keyboard (omniKbEdit, as Find on page) edits the
    query and the list filters as you type (every word must be in the title or the site); OK keeps it, Cancel restores
    the previous query; Circle on the list clears the search first, then closes. While typing the panel shrinks to the
    top 4 rows so it ends above the keyboard (y 362) and the keyboard keeps its own hint bar.
  - Visits grouped under local-day headings: Today, Yesterday, weekday names within the last week, then dates.
    Right-hand time: "just now" / "N min ago" within the hour, else the local clock (HH:MM).
  - Square: delete the selected visit (no ask, as before; a notice). R3: delete every visit to that site ("www." and
    the port ignored), asks first. "Clear history..." (row 0) opens the ranges Last hour / Today / All time with their
    counts; Cross asks, then clears.
  - Paging: D-pad up/down skip the headings; D-pad left/right jump to the previous / next day; L1/R1 a page (9 rows);
    the hint bar shows "page x/y". Pointer hover/click and the wheel still work (headings are not selectable).
  - Address suggestions and most-visited tiles refresh after a delete (omniSuggestFor, omniStSitesStale).

Pure logic: engine/entry/OmniHistoryPlus.h (no SDL/WebKit), tested by test_history_plus.cpp:
  g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_history_plus.cpp -o t && ./t
Anchors in OmniBrowser.cpp (exactly once each; the MARK makes it idempotent):
  1. the '#include "OmniSearchTiles.h" // OMNI_SEARCH_TILES_V1...' line (the new include goes after it)
  2. from 'static int omniHistoryCount() { return int(omniHistory.size()) + 1; }' through the end of
     omniHistoryScrollBy (count / item / show / activate / delete / button / rowAt / click / scroll replaced)
  3. omniHistoryDraw, from its signature through its omniPanelHints(...) line and closing brace
Not touched: OmniTabsPage.h and the tab strip; omniHistoryLoad / Add / Rewrite and the file format.
usage: apply_history_plus.py <engine tree>   (keeps the file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_HISTORY_PLUS_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_HISTORY_PLUS_V1: the pure part of the History panel (no SDL, no WebKit): history.txt lines (parse/format,
// the format every older build reads: "<unix time>\t<url>\t<title>\n", oldest first), search (title/site, every word),
// rows grouped by local day (Today, Yesterday, weekday, date), day/page jumps, and the deletes (one visit, every visit
// to a site, the last hour / today / all time). Works on any visit type with .time, .url and .title.
#pragma once
#include <algorithm>
#include <climits>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

namespace OmniHistoryPlus {

inline std::string lowerAscii(std::string s)
{
    for (auto& c : s) if (c >= 'A' && c <= 'Z') c = char(c + ('a' - 'A'));
    return s;
}

// The site of an address: lower case, no user@, no :port, no leading "www." ("" when there is no "://").
inline std::string hostOf(const std::string& url)
{
    const size_t scheme = url.find("://");
    if (scheme == std::string::npos) return {};
    const size_t start = scheme + 3, end = url.find_first_of("/?#", start);
    std::string h = url.substr(start, end == std::string::npos ? std::string::npos : end - start);
    const size_t at = h.rfind('@');
    if (at != std::string::npos) h.erase(0, at + 1);
    if (!h.empty() && h[0] == '[') { const size_t close = h.find(']'); if (close != std::string::npos) h.resize(close + 1); }
    else { const size_t colon = h.find(':'); if (colon != std::string::npos) h.resize(colon); }
    h = lowerAscii(h);
    if (h.rfind("www.", 0) == 0 && h.size() > 4) h.erase(0, 4);
    return h;
}

// One history.txt line, the rules of omniHistoryLoad: CR/LF trimmed, time TAB url TAB title (the title may be empty
// and is everything after the second TAB). Web addresses only (http/https), as the loader keeps.
template <class V> bool parseLine(std::string s, V& v)
{
    while (!s.empty() && (s.back() == '\n' || s.back() == '\r')) s.pop_back();
    const size_t a = s.find('\t'), b = a == std::string::npos ? a : s.find('\t', a + 1);
    if (b == std::string::npos) return false;
    v.time = atoll(s.substr(0, a).c_str());
    v.url = s.substr(a + 1, b - a - 1);
    v.title = s.substr(b + 1);
    return v.url.rfind("https://", 0) == 0 || v.url.rfind("http://", 0) == 0;
}
template <class V> std::string formatLine(const V& v) { return std::to_string(v.time) + "\t" + v.url + "\t" + v.title + "\n"; }
template <class V> std::string serialize(const std::vector<V>& h)
{
    std::string out;
    for (const auto& v : h) out += formatLine(v);
    return out;
}

// Search: lower-cased words; a visit matches when every word is in its title or its site.
inline std::vector<std::string> words(const std::string& query)
{
    std::vector<std::string> out;
    const std::string q = lowerAscii(query);
    size_t i = 0;
    while (i < q.size()) {
        while (i < q.size() && (q[i] == ' ' || q[i] == '\t')) ++i;
        size_t j = i;
        while (j < q.size() && q[j] != ' ' && q[j] != '\t') ++j;
        if (j > i) out.push_back(q.substr(i, j - i));
        i = j;
    }
    return out;
}
template <class V> bool matches(const V& v, const std::vector<std::string>& w)
{
    if (w.empty()) return true;
    const std::string title = lowerAscii(v.title), host = hostOf(v.url);
    for (const auto& word : w) if (title.find(word) == std::string::npos && host.find(word) == std::string::npos) return false;
    return true;
}

// Local days: utcOffset is seconds east of UTC (tm_gmtoff); floor division so times before 1970 stay right.
inline long long dayKey(long long t, long long utcOffset)
{
    const long long x = t + utcOffset;
    return x >= 0 ? x / 86400 : -((-x + 86399) / 86400);
}
inline long long dayStart(long long day, long long utcOffset) { return day * 86400 - utcOffset; }
struct Civil { int year, month, day, weekday; };   // weekday 0 = Sunday
inline Civil civil(long long days)
{
    const long long z = days + 719468, era = (z >= 0 ? z : z - 146096) / 146097;
    const long long doe = z - era * 146097, yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    const long long doy = doe - (365 * yoe + yoe / 4 - yoe / 100), mp = (5 * doy + 2) / 153;
    const int d = int(doy - (153 * mp + 2) / 5 + 1), m = int(mp < 10 ? mp + 3 : mp - 9);
    const long long y = yoe + era * 400 + (m <= 2);
    const int wd = int(((days % 7) + 7 + 4) % 7);
    return { int(y), m, d, wd };
}
inline std::string dayLabel(long long day, long long today)
{
    static const char* const weekdays[] = { "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday" };
    static const char* const months[] = { "January", "February", "March", "April", "May", "June", "July", "August",
        "September", "October", "November", "December" };
    if (day == today) return "Today";
    if (day == today - 1) return "Yesterday";
    const Civil c = civil(day), t = civil(today);
    char b[64];
    if (day < today && day > today - 7) snprintf(b, sizeof(b), "%s, %d %s", weekdays[c.weekday], c.day, months[c.month - 1]);
    else if (c.year == t.year) snprintf(b, sizeof(b), "%d %s", c.day, months[c.month - 1]);
    else snprintf(b, sizeof(b), "%d %s %d", c.day, months[c.month - 1], c.year);
    return b;
}
// The right-hand time of a row: "just now", "12 min ago" within the hour, else the local clock "14:05".
inline std::string timeLabel(long long t, long long now, long long utcOffset)
{
    const long long d = now - t;
    char b[32];
    if (d >= 0 && d < 60) return "just now";
    if (d >= 0 && d < 3600) { snprintf(b, sizeof(b), "%lld min ago", d / 60); return b; }
    const long long s = t + utcOffset, inDay = ((s % 86400) + 86400) % 86400;
    snprintf(b, sizeof(b), "%02lld:%02lld", inDay / 3600, inDay / 60 % 60);
    return b;
}

// Panel rows, newest first: "Clear history..." first, then a day heading before each day's visits.
enum RowKind { RowClear, RowDay, RowVisit };
struct Row { int kind; int index; long long day; };   // index: into the history vector (RowVisit)
inline bool selectable(const Row& r) { return r.kind != RowDay; }
template <class V> std::vector<Row> buildRows(const std::vector<V>& h, const std::string& query, long long utcOffset, size_t* matched = nullptr)
{
    std::vector<Row> rows { { RowClear, -1, 0 } };
    const auto w = words(query);
    std::vector<int> order;
    order.reserve(h.size());
    for (int i = int(h.size()) - 1; i >= 0; --i) if (matches(h[size_t(i)], w)) order.push_back(i);
    std::stable_sort(order.begin(), order.end(), [&](int a, int b) { return h[size_t(a)].time > h[size_t(b)].time; });   // a clock set back
    if (matched) *matched = order.size();
    long long day = LLONG_MIN;
    for (int i : order) {
        const long long d = dayKey(h[size_t(i)].time, utcOffset);
        if (d != day) { rows.push_back({ RowDay, -1, d }); day = d; }
        rows.push_back({ RowVisit, i, d });
    }
    return rows;
}
inline int firstVisit(const std::vector<Row>& rows)
{
    for (size_t i = 0; i < rows.size(); ++i) if (rows[i].kind == RowVisit) return int(i);
    return 0;
}
// The nearest selectable row at `from`, looking in `dir` first, then the other way.
inline int snap(const std::vector<Row>& rows, int from, int dir)
{
    const int n = int(rows.size());
    if (n == 0) return 0;
    from = std::clamp(from, 0, n - 1);
    for (int i = from; i >= 0 && i < n; i += dir) if (selectable(rows[size_t(i)])) return i;
    for (int i = from; i >= 0 && i < n; i -= dir) if (selectable(rows[size_t(i)])) return i;
    return 0;
}
inline int step(const std::vector<Row>& rows, int sel, int delta)   // D-pad (1) and L1/R1 (a page)
{
    const int n = int(rows.size());
    if (n == 0) return 0;
    const int to = std::clamp(sel + delta, 0, n - 1);
    return snap(rows, to, delta >= 0 ? 1 : -1);
}
// D-pad left/right: the first visit of the previous / next day (left on a day's later visit: that day's first).
inline int dayJump(const std::vector<Row>& rows, int sel, int dir)
{
    const int n = int(rows.size());
    if (n == 0) return 0;
    sel = std::clamp(sel, 0, n - 1);
    if (dir > 0) {
        for (int i = sel + 1; i < n; ++i) if (rows[size_t(i)].kind == RowDay) return snap(rows, i, 1);
        return snap(rows, n - 1, -1);
    }
    int head = -1;
    for (int i = sel; i >= 0; --i) if (rows[size_t(i)].kind == RowDay) { head = i; break; }
    if (head < 0) return 0;                                   // on "Clear history...": stay
    if (sel > head + 1) return snap(rows, head + 1, 1);        // this day's first visit
    for (int i = head - 1; i >= 0; --i) if (rows[size_t(i)].kind == RowDay) return snap(rows, i, 1);
    return 0;                                                 // the first day: up to "Clear history..."
}
inline int pageCount(int rows, int perPage) { return perPage > 0 ? std::max(1, (rows + perPage - 1) / perPage) : 1; }
// The first row shown so `sel` is on screen; a visit right under its day heading brings the heading along.
inline int scrollFor(const std::vector<Row>& rows, int sel, int scroll, int perPage)
{
    const int n = int(rows.size());
    if (sel < scroll) scroll = sel;
    if (sel > 0 && sel - 1 < scroll && rows[size_t(sel - 1)].kind == RowDay) scroll = sel - 1;
    if (sel >= scroll + perPage) scroll = sel - perPage + 1;
    return std::clamp(scroll, 0, std::max(0, n - perPage));
}

// Clear history ranges.
enum Range { LastHour, Today, AllTime, RangeCount };
inline const char* rangeName(int r) { return r == LastHour ? "Last hour" : r == Today ? "Today" : "All time"; }
inline long long rangeStart(int r, long long now, long long utcOffset)
{
    if (r == LastHour) return now - 3600;
    if (r == Today) return dayStart(dayKey(now, utcOffset), utcOffset);
    return LLONG_MIN;
}
template <class V> size_t countSince(const std::vector<V>& h, long long start)
{
    return size_t(std::count_if(h.begin(), h.end(), [&](const V& v) { return v.time >= start; }));
}
template <class V> size_t eraseSince(std::vector<V>& h, long long start)
{
    const size_t before = h.size();
    h.erase(std::remove_if(h.begin(), h.end(), [&](const V& v) { return v.time >= start; }), h.end());
    return before - h.size();
}
template <class V> size_t countHost(const std::vector<V>& h, const std::string& host)
{
    if (host.empty()) return 0;
    return size_t(std::count_if(h.begin(), h.end(), [&](const V& v) { return hostOf(v.url) == host; }));
}
template <class V> size_t eraseHost(std::vector<V>& h, const std::string& host)
{
    if (host.empty()) return 0;
    const size_t before = h.size();
    h.erase(std::remove_if(h.begin(), h.end(), [&](const V& v) { return hostOf(v.url) == host; }), h.end());
    return before - h.size();
}
inline std::string visits(size_t n) { return std::to_string(n) + (n == 1 ? " visit" : " visits"); }

} // namespace OmniHistoryPlus
'''

SHELL_A = r'''// OMNI_HISTORY_PLUS_V1: search (Triangle: the on-screen keyboard; the list filters as you type), visits grouped by
// day under Today / Yesterday / date headings, Square deletes the visit, R3 every visit to its site (asks), "Clear
// history..." picks Last hour / Today / All time (asks), D-pad left/right jumps a day, L1/R1 a page. Every change is
// one full rewrite of history.txt through omniIoQueue (the background writer), in the format older builds read.
// Pure logic: OmniHistoryPlus.h. Private tabs never reach omniHistory (omniEverydayFinished), so never this panel.
namespace OHP = OmniHistoryPlus;
static std::string omniHpQuery, omniHpQueryBefore;
static std::vector<OHP::Row> omniHpRows;
static size_t omniHpMatched = 0;
static unsigned omniHpGen = 0;   // bumped by every delete from the panel
static int omniHpMode = 0;       // 0: the list, 1: "Clear history" ranges
static int omniHpRange = 0;
static long long omniHpOffset = 0, omniHpToday = 0;
static bool omniHpTyping() { return editing && omniKbTarget == &omniHpQuery; }
static int omniHpVisible() { return omniHpTyping() ? 4 : omniHistoryRows; }   // above the keyboard while typing
static long long omniHpUtcOffset(long long now)
{
    time_t t = time_t(now);
    struct tm tmv {};
    localtime_r(&t, &tmv);
    return (long long)tmv.tm_gmtoff;
}
// Rebuilt only when the query, the history (a page finishing in the background adds a visit) or the day changes.
static void omniHpRefresh()
{
    static std::string forQuery = "\x01";
    static size_t forSize = size_t(-1);
    static long long forLast = -1, forDay = LLONG_MIN;
    static unsigned forGen = ~0u;
    const long long now = time(nullptr);
    omniHpOffset = omniHpUtcOffset(now);
    omniHpToday = OHP::dayKey(now, omniHpOffset);
    const long long last = omniHistory.empty() ? 0 : omniHistory.back().time;
    if (forQuery == omniHpQuery && forSize == omniHistory.size() && forLast == last && forDay == omniHpToday && forGen == omniHpGen) return;
    const bool queryChanged = forQuery != omniHpQuery;
    forQuery = omniHpQuery; forSize = omniHistory.size(); forLast = last; forDay = omniHpToday; forGen = omniHpGen;
    omniHpRows = OHP::buildRows(omniHistory, omniHpQuery, omniHpOffset, &omniHpMatched);
    if (queryChanged) { omniHistorySel = OHP::firstVisit(omniHpRows); omniHistoryScroll = 0; }
    omniHistorySel = OHP::snap(omniHpRows, omniHistorySel, 1);
    omniShellDirty = true;
}
static int omniHistoryCount() { omniHpRefresh(); return int(omniHpRows.size()); }
static const OmniVisit* omniHistoryItem(int row)
{
    omniHpRefresh();
    if (row < 0 || row >= int(omniHpRows.size()) || omniHpRows[size_t(row)].kind != OHP::RowVisit) return nullptr;
    const int i = omniHpRows[size_t(row)].index;
    return i >= 0 && i < int(omniHistory.size()) ? &omniHistory[size_t(i)] : nullptr;
}
static void omniHistoryShow()
{
    omniHistoryLoad(); omniHistoryOpenFlag = true;
    omniHpQuery.clear(); omniHpMode = 0; omniHpRange = 0;
    omniHpRefresh();
    omniHistorySel = OHP::firstVisit(omniHpRows); omniHistoryScroll = 0;
}
static void omniHpChanged()
{
    ++omniHpGen;
    omniHistoryRewrite();   // omniIoQueue: a full rewrite on the writer thread (drops older queued writes of the file)
    omniSuggestFor = "\x01"; omniStSitesStale = true;
    omniHpRefresh();
    omniShellDirty = true;
}
static void omniHpSearch()
{
    omniHpQueryBefore = omniHpQuery;
    omniKbEdit(&omniHpQuery, "Search history", [](bool submitted) {
        if (!submitted) omniHpQuery = omniHpQueryBefore;   // Cancel: the search as it was
        omniShellDirty = true;
    });
}
static void omniHpClearRange(int range)
{
    const long long now = time(nullptr), start = OHP::rangeStart(range, now, omniHpUtcOffset(now));
    const size_t n = OHP::countSince(omniHistory, start);
    if (n == 0) { notice(range == OHP::LastHour ? "No visits in the last hour" : range == OHP::Today ? "No visits today" : "History is empty"); return; }
    const std::string what = range == OHP::LastHour ? OHP::visits(n) + " from the last hour" : range == OHP::Today ? OHP::visits(n) + " from today"
        : "All " + OHP::visits(n);
    omniAsk("Clear history?", what + " will be removed from this console.", "Clear", [range](bool ok) {
        if (!ok) return;
        const long long when = time(nullptr);
        const size_t removed = OHP::eraseSince(omniHistory, OHP::rangeStart(range, when, omniHpUtcOffset(when)));
        omniHpMode = 0;
        if (removed) omniHpChanged();
        notice("History cleared: " + OHP::visits(removed) + " removed");
    });
}
static void omniHpDeleteSite(int row)
{
    const OmniVisit* v = omniHistoryItem(row);
    if (!v) return;
    const std::string host = OHP::hostOf(v->url);
    const size_t n = OHP::countHost(omniHistory, host);
    if (n == 0) return;
    omniAsk("Delete " + host + " from history?", "All " + OHP::visits(n) + " to " + host + " will be removed from this console.", "Delete", [host](bool ok) {
        if (!ok) return;
        const size_t removed = OHP::eraseHost(omniHistory, host);
        if (removed) omniHpChanged();
        notice(host + ": " + OHP::visits(removed) + " removed from history");
    });
}
static void omniHistoryActivate(int row)
{
    if (row >= 0 && row < int(omniHpRows.size()) && omniHpRows[size_t(row)].kind == OHP::RowClear) {
        if (omniHistory.empty()) { notice("History is empty"); return; }
        omniHpMode = 1; omniHpRange = 0;
        return;
    }
    if (const OmniVisit* v = omniHistoryItem(row)) { const std::string url = v->url; omniHistoryOpenFlag = false; navigate(url); }
}
static void omniHistoryDelete(int row)
{
    const OmniVisit* v = omniHistoryItem(row);
    if (!v) return;
    omniHistory.erase(omniHistory.begin() + (v - omniHistory.data()));
    omniHpChanged();
    notice("Removed from history");
}
static bool omniHistoryButton(int b)
{
    if (editing) return false;   // the search keyboard (or another field) takes the buttons; the list follows the text
    omniHpRefresh();
    if (omniHpMode == 1) {
        switch (b) {
        case SDL_CONTROLLER_BUTTON_DPAD_UP: omniHpRange = std::max(0, omniHpRange - 1); break;
        case SDL_CONTROLLER_BUTTON_DPAD_DOWN: omniHpRange = std::min(int(OHP::RangeCount) - 1, omniHpRange + 1); break;
        case SDL_CONTROLLER_BUTTON_A: omniHpClearRange(omniHpRange); break;
        case SDL_CONTROLLER_BUTTON_B: case SDL_CONTROLLER_BUTTON_BACK: omniHpMode = 0; break;
        case SDL_CONTROLLER_BUTTON_START: return false;
        default: break;
        }
        return true;
    }
    switch (b) {
    case SDL_CONTROLLER_BUTTON_DPAD_UP: omniHistorySel = OHP::step(omniHpRows, omniHistorySel, -1); break;
    case SDL_CONTROLLER_BUTTON_DPAD_DOWN: omniHistorySel = OHP::step(omniHpRows, omniHistorySel, 1); break;
    case SDL_CONTROLLER_BUTTON_DPAD_LEFT: omniHistorySel = OHP::dayJump(omniHpRows, omniHistorySel, -1); break;
    case SDL_CONTROLLER_BUTTON_DPAD_RIGHT: omniHistorySel = OHP::dayJump(omniHpRows, omniHistorySel, 1); break;
    case SDL_CONTROLLER_BUTTON_LEFTSHOULDER: omniHistorySel = OHP::step(omniHpRows, omniHistorySel, -omniHistoryRows); break;
    case SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: omniHistorySel = OHP::step(omniHpRows, omniHistorySel, omniHistoryRows); break;
    case SDL_CONTROLLER_BUTTON_A: omniHistoryActivate(omniHistorySel); break;
    case SDL_CONTROLLER_BUTTON_X: omniHistoryDelete(omniHistorySel); break;
    case SDL_CONTROLLER_BUTTON_Y: omniHpSearch(); break;
    case SDL_CONTROLLER_BUTTON_RIGHTSTICK: omniHpDeleteSite(omniHistorySel); break;
    case SDL_CONTROLLER_BUTTON_B: case SDL_CONTROLLER_BUTTON_BACK:
        if (!omniHpQuery.empty()) { omniHpQuery.clear(); omniHpRefresh(); } else omniHistoryOpenFlag = false;   // Circle: the search first, then the panel
        break;
    case SDL_CONTROLLER_BUTTON_START: return false;
    default: break;
    }
    return true;
}
constexpr int omniHpSearchX = omniHistoryX + 170, omniHpSearchW = 560;
static int omniHistoryRowAt(int x, int y)
{
    if (omniHpMode != 0) return -1;
    const int listY = omniHistoryTop + 70;
    if (x < omniHistoryX || x >= omniHistoryX + omniHistoryW || y < listY || y >= listY + omniHpVisible() * omniHistoryRowH) return -1;
    const int row = omniHistoryScroll + (y - listY) / omniHistoryRowH;
    return row < omniHistoryCount() && OHP::selectable(omniHpRows[size_t(row)]) ? row : -1;
}
static bool omniHistoryClick(int x, int y)
{
    if (editing) return false;   // keyboard keys are clicked as usual
    const int listY = omniHistoryTop + 70;
    if (omniHpMode == 1) {
        const int r = (y - listY) / omniHistoryRowH;
        if (y >= listY && x >= omniHistoryX && x < omniHistoryX + omniHistoryW && r >= 0 && r < int(OHP::RangeCount)) { omniHpRange = r; omniHpClearRange(r); }
        return true;
    }
    if (y >= omniHistoryTop + 14 && y < omniHistoryTop + 58 && x >= omniHpSearchX && x < omniHpSearchX + omniHpSearchW) { omniHpSearch(); return true; }
    const int row = omniHistoryRowAt(x, y);
    if (row >= 0) { omniHistorySel = row; omniHistoryActivate(row); }
    return true;
}
static bool omniHistoryScrollBy(double amount)
{
    static float acc = 0;
    acc -= float(amount);
    omniHpRefresh();
    while (acc >= 50) { acc -= 50; if (omniHpMode == 1) omniHpRange = std::min(int(OHP::RangeCount) - 1, omniHpRange + 1); else omniHistorySel = OHP::step(omniHpRows, omniHistorySel, 1); }
    while (acc <= -50) { acc += 50; if (omniHpMode == 1) omniHpRange = std::max(0, omniHpRange - 1); else omniHistorySel = OHP::step(omniHpRows, omniHistorySel, -1); }
    return true;
}
'''

SHELL_B = r'''static void omniHistoryDraw()
{
    // OMNI_HISTORY_PLUS_V1: search pill in the title row, day headings, the "Clear history" ranges; while the search
    // keyboard is open the panel keeps to the top (4 rows, ends above the keyboard at y 362) and the keyboard's hints stay.
    const OmniTheme& T = omniTheme();
    omniHpRefresh();
    const bool typing = omniHpTyping();
    const int rows = omniHpMode == 1 ? 4 : omniHpVisible();
    const float fadeT = omniPanelT(omniPanelHistory); // OMNI_POLISH_V1: backdrop and panel fade in
    omniRectPx({ 0, 0, canvas->w, typing ? physical(keyboardY - 58) : canvas->h }, { 0, 0, 0, 255 }, uint8_t(110 * fadeT));
    const int h = 70 + rows * omniHistoryRowH + (typing ? 10 : 20);
    struct FadeScope { ~FadeScope() { omniFadeEnd(); } } fadeScope;
    omniFadeBegin(omniHistoryX - 30, omniHistoryTop - 30, omniHistoryW + 60, h + (typing ? 34 : 60), fadeT);
    omniShadow(omniHistoryX, omniHistoryTop, omniHistoryW, h, omniRadius + 2, typing ? 12 : 22, 160, typing ? 3 : 6);
    fillRounded(omniHistoryX, omniHistoryTop, omniHistoryW, h, omniRadius + 2, T.panel);
    const float headY = omniHistoryTop + 36;
    const int listY = omniHistoryTop + 70;
    if (omniHpMode == 1) {
        omniLabel("Clear history", omniHistoryX + 28, headY, omniTitle, T.ink);
        omniLabel(OHP::visits(omniHistory.size()) + " on this console", omniHistoryX + omniHistoryW - 28, headY, omniSmall, T.inkFaint, 2);
        const long long now = time(nullptr);
        for (int r = 0; r < int(OHP::RangeCount); ++r) {
            const int y = listY + r * omniHistoryRowH;
            const bool sel = r == omniHpRange;
            if (sel) fillRounded(omniHistoryX + 12, y + 2, omniHistoryW - 24, omniHistoryRowH - 4, omniRadius, T.accent);
            const float cy = y + omniHistoryRowH / 2.f;
            omniIcon(omniIconClose, omniHistoryX + 40, cy, sel ? T.accentInk : omniBad);
            omniLabel(OHP::rangeName(r), omniHistoryX + 64, cy, omniBody, sel ? T.accentInk : T.ink);
            omniLabel(OHP::visits(OHP::countSince(omniHistory, OHP::rangeStart(r, now, omniHpOffset))), omniHistoryX + omniHistoryW - 30, cy, omniSmall, sel ? T.accentInk : T.inkDim, 2);
        }
        omniLabel("Removes visits from this console only. Private tabs are never recorded.", omniHistoryX + 32, listY + 3.5f * omniHistoryRowH, omniSmall, T.inkFaint);
        omniFadeEnd(); // OMNI_POLISH_V1: the hint bar is outside the fade
        omniPanelHints({ { 0, "Clear" }, { 1, "Back" } }, "D-pad: choose a range (asks before clearing)");
        return;
    }
    omniLabel("History", omniHistoryX + 28, headY, omniTitle, T.ink); // OMNI_POLISH_V1: title size
    // search pill: Triangle opens the keyboard; the list filters as you type
    const int sx = omniHpSearchX, sy = omniHistoryTop + 16, sw = omniHpSearchW, sh = 40;
    if (typing) fillRounded(sx - 3, sy - 3, sw + 6, sh + 6, omniRadius + 3, T.accent);
    fillRounded(sx, sy, sw, sh, omniRadius + 1, T.field);
    faceIcon(sx + 20, int(headY), 3, playStationIcons);
    if (omniHpQuery.empty()) omniLabel(typing ? "Type a title or a site" : "Search titles and sites", sx + 42, headY, omniSmall, T.inkFaint, 0, sw - 56);
    else omniLabel(omniHpQuery, sx + 42, headY, omniBody, T.ink, 0, sw - 56);
    const std::string count = omniHpQuery.empty() ? OHP::visits(omniHistory.size()) : std::to_string(omniHpMatched) + " of " + OHP::visits(omniHistory.size());
    omniLabel(count, omniHistoryX + omniHistoryW - 28, headY, omniSmall, T.inkFaint, 2);
    const int n = int(omniHpRows.size());
    omniHistoryScroll = OHP::scrollFor(omniHpRows, omniHistorySel, omniHistoryScroll, rows);
    const long long now = time(nullptr);
    for (int r = 0; r < rows && omniHistoryScroll + r < n; ++r) {
        const int row = omniHistoryScroll + r, y = listY + r * omniHistoryRowH;
        const OHP::Row& R = omniHpRows[size_t(row)];
        const float cy = y + omniHistoryRowH / 2.f;
        if (R.kind == OHP::RowDay) {   // day heading: not selectable
            const int lw = omniLabel(OHP::dayLabel(R.day, omniHpToday), omniHistoryX + 32, cy + 6, omniSmallBold, T.accent);
            omniRectPx({ physical(omniHistoryX + 44 + lw), physical(int(cy + 6)), physical(omniHistoryW - 76 - lw), std::max(1, physical(1)) }, T.line);
            continue;
        }
        const bool sel = row == omniHistorySel;
        if (sel) fillRounded(omniHistoryX + 12, y + 2, omniHistoryW - 24, omniHistoryRowH - 4, omniRadius, T.accent);
        const SDL_Color ink = sel ? T.accentInk : T.ink, dim = sel ? T.accentInk : T.inkDim;
        if (R.kind == OHP::RowClear) { omniIcon(omniIconClose, omniHistoryX + 40, cy, sel ? T.accentInk : omniBad); omniLabel("Clear history\xe2\x80\xa6", omniHistoryX + 64, cy, omniBody, sel ? T.accentInk : omniBad); continue; }
        if (R.index < 0 || R.index >= int(omniHistory.size())) continue;
        const OmniVisit& v = omniHistory[size_t(R.index)];
        const std::string bare = omniShownURL(v.url);
        const int w = omniLabel(v.title.empty() ? bare : v.title, omniHistoryX + 32, cy, omniBody, ink, 0, 560);
        omniLabel(bare, omniHistoryX + 48 + w, cy, omniSmall, dim, 0, std::max(0, omniHistoryW - 230 - w));
        omniLabel(OHP::timeLabel(v.time, now, omniHpOffset), omniHistoryX + omniHistoryW - 30, cy, omniSmall, dim, 2);
    }
    if (omniHistory.empty()) omniLabel("Pages you visit appear here (not from private tabs).", omniHistoryX + 32, listY + omniHistoryRowH * 1.5f, omniBody, T.inkFaint);
    else if (omniHpMatched == 0) omniLabel("No visits match \xe2\x80\x9c" + omniHpQuery + "\xe2\x80\x9d", omniHistoryX + 32, listY + omniHistoryRowH * 1.5f, omniBody, T.inkFaint, 0, omniHistoryW - 64);
    omniFadeEnd(); // OMNI_POLISH_V1: the hint bar is outside the fade
    if (typing) return;   // the keyboard's own hint bar stays
    char note[96];
    snprintf(note, sizeof(note), "D-pad left/right: day   L1/R1: page %d/%d",
        omniHistorySel / omniHistoryRows + 1, OHP::pageCount(n, omniHistoryRows));
    const OmniVisit* cur = omniHistoryItem(omniHistorySel);
    if (cur) omniPanelHints({ { 0, "Open" }, { 2, "Delete" }, { omniHintRStick, "Delete site" }, { 3, "Search" }, { 1, omniHpQuery.empty() ? "Close" : "Clear search" } }, note);
    else omniPanelHints({ { 0, "Choose" }, { 3, "Search" }, { 1, omniHpQuery.empty() ? "Close" : "Clear search" } }, note);
}
'''

INCLUDE_AT = '#include "OmniSearchTiles.h" // OMNI_SEARCH_TILES_V1'
INCLUDE = '#include "OmniHistoryPlus.h" // OMNI_HISTORY_PLUS_V1: history search, day groups, range deletes (pure)'
A_START = 'static int omniHistoryCount() { return int(omniHistory.size()) + 1; }   // row 0: Clear history\n'
A_END = ('    while (acc <= -50) { acc += 50; omniHistorySel = std::max(0, omniHistorySel - 1); }\n'
         '    return true;\n'
         '}\n')
A_MUST = ['static void omniHistoryShow()', 'static void omniHistoryActivate(int row)', 'static void omniHistoryDelete(int row)',
          'static bool omniHistoryButton(int b)', 'static int omniHistoryRowAt(int x, int y)', 'static bool omniHistoryClick(int x, int y)',
          'static bool omniHistoryScrollBy(double amount)']
B_START = 'static void omniHistoryDraw()\n{\n'
B_END = '    omniPanelHints({ { 0, "Open" }, { 2, "Delete" }, { 1, "Close" } }, "D-pad: move   L1/R1: page");\n}\n'


def unique(s, what, name):
    n = s.count(what)
    if n != 1:
        sys.exit('OmniBrowser.cpp: %s found %d times: %r' % (name, n, what[:90]))
    return s.index(what)


def span(s, start, end, name, must=()):
    """[begin, finish) of the text from `start` through `end` (both unique, end after start, nothing else between
    them that is not in the expected block)."""
    a = unique(s, start, name + ' start')
    b = unique(s, end, name + ' end')
    if b < a:
        sys.exit('OmniBrowser.cpp: %s end before its start' % name)
    block = s[a:b + len(end)]
    for m in must:
        if block.count(m) != 1:
            sys.exit('OmniBrowser.cpp: %s block does not hold %r once' % (name, m))
    return a, b + len(end)


def main():
    p = root / 'OmniBrowser.cpp'
    raw = p.read_bytes()
    s = raw.decode('utf-8')
    crlf = raw.count(b'\r\n') * 2 > raw.count(b'\n')
    e = '\r\n' if crlf else '\n'
    msgs = []
    if MARK in s:
        msgs.append('OmniBrowser.cpp: already')
    else:
        t = s.replace('\r\n', '\n') if crlf else s
        if 'static void omniKbEdit(std::string* target' not in t or 'static bool omniStSitesStale' not in t:
            sys.exit('OmniBrowser.cpp: omniKbEdit / omniStSitesStale missing (needs the OMNI_DIALOGS_V1 and OMNI_SEARCH_TILES_V1 tree)')
        # every anchor is checked before anything is written
        i = unique(t, INCLUDE_AT, 'include anchor')
        line_end = t.index('\n', i) + 1
        a0, a1 = span(t, A_START, A_END, 'history input block', A_MUST)
        b0, b1 = span(t, B_START, B_END, 'omniHistoryDraw')
        if not (line_end <= a0 < a1 <= b0):
            sys.exit('OmniBrowser.cpp: anchors out of order')
        t = (t[:line_end] + INCLUDE + '\n' + t[line_end:a0] + SHELL_A + t[a1:b0] + SHELL_B + t[b1:])
        p.write_bytes((t.replace('\n', e) if crlf else t).encode('utf-8'))
        msgs.append('OmniBrowser.cpp: applied')
    like = (root / 'OmniSearchTiles.h').read_bytes()
    nl = '\r\n' if like.count(b'\r\n') * 2 > like.count(b'\n') else '\n'
    data = PURE.replace('\n', nl).encode('utf-8')
    h = root / 'OmniHistoryPlus.h'
    if h.exists() and h.read_bytes() == data:
        msgs.append('OmniHistoryPlus.h: already')
    else:
        h.write_bytes(data)
        msgs.append('OmniHistoryPlus.h: written')
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
