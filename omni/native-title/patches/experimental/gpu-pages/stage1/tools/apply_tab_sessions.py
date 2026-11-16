#!/usr/bin/env python3
"""OMNI_TAB_SESSIONS_V1 (2026-11-16): save the open tabs as a named session ("Movie night", "Research") and open it later.

What it does
  - Tabs panel (OmniTabsPage.h): two rows after "Reopen closed tab":
      "Save these tabs as a session..."  Cross: name it on Omni's on-screen keyboard (omniKbEdit; default
                                         "Session 16 Nov 2026", made unique), Go saves, Cancel drops it. Saving under
                                         a name that already exists updates that session (it moves to the top).
      "Sessions..."                      Cross: the Sessions panel.
  - Sessions panel: one row per session, newest first: name, the first sites, "5 tabs . 16 Nov". Cross: open,
    Triangle: rename (keyboard), Square: delete (press Square twice on the same row: the row turns red and says so;
    moving off the row disarms it), Circle: back.
  - Open asks how: "Replace the open tabs" (closes every open tab: they go to "Reopen closed tab" as usual) or "Add to
    the open tabs" (URLs already open are skipped). Both respect Browser settings > Tab limit (what does not fit is
    counted in the notice) and open the tabs the way start-up restore does (omniF3Restoring + Tab::omniLazyURL): only
    the tab shown loads, the others load when first shown, so opening 10 tabs loads one page. Before opening, the
    shell memory guard of newTab() is checked once (omniTmQueryMiB < refuse_mib refuses, as for a new tab).
    Replace closes the other tabs first (their lazy URLs cleared and omniTmSkipRestore set, so none loads on the way
    out), creates what fits beside the last old tab, closes that one (the first session tab is shown and loads), then
    creates the rest.
  - Storage: /data/omni/sessions.txt, written through omniIoQueue (the background writer, full rewrite):
        omni-sessions\t1
        session\t<unix time>\t<name>
        tab\t<url>\t<title>
    max 30 sessions (a 31st name is refused: delete one first), max 16 tabs each (the highest Tab limit; a save keeps
    at most the current limit), http(s) URLs only, URL <= 2048 bytes, title <= 200, name <= 60. Private tabs and tabs
    owned by the Media section are never saved. Read once, on first use, on the main thread (<= 2 MB, ~100 KB typical).
    Nothing is written in the self-test modes.

Pure part: engine/entry/OmniTabSessions.h (no SDL/WebKit): parse/serialize, caps, naming, open plan, row texts.
Tested by tools/test_tab_sessions.cpp:   g++ -std=c++20 -I<tree>/engine/entry test_tab_sessions.cpp -o t && ./t
Shell side: engine/entry/OmniTabSessionsShell.h (included from OmniFeatures3.h after OmniReadingListShell.h, so
omniF3Set / omniTmQueryMiB from OmniTabMemory.h are visible); OmniTabsPage.h gets forward declarations.

Anchors (exactly once each; MARK makes each file idempotent):
  OmniBrowser.cpp    the OmniReadingList.h include line
  OmniTabsPage.h     the omniFxTabNew enum line; the p.corner line (rows go before it); the "b != A || !r.enabled"
                     fall-through line of omniFxTabsInput (handler goes before it). Does not touch the Triangle /
                     omniTaTabFaces lines of apply_tab_audio.py.
  OmniFeatures3.h    the OmniReadingListShell.h include line
Apply AFTER apply_reading_list.py (its include lines are anchors); independent of apply_tab_audio.py.
usage: apply_tab_sessions.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_TAB_SESSIONS_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_TAB_SESSIONS_V1: the pure part of named tab sessions (no SDL, no WebKit). The shell side is
// OmniTabSessionsShell.h; the reasons are in tools/apply_tab_sessions.py. Tested on the host with g++ (test_tab_sessions.cpp).
#pragma once
#include <algorithm>
#include <cstdio>
#include <ctime>
#include <string>
#include <vector>

namespace OmniTabSessions {

constexpr int kMaxSessions = 30;
constexpr int kMaxTabs = 16;                  // the highest Browser settings > Tab limit
constexpr size_t kNameMax = 60, kUrlMax = 2048, kTitleMax = 200;
constexpr long kMaxFileBytes = 2L << 20;
constexpr const char* kFileName = "sessions.txt";
constexpr const char* kHeader = "omni-sessions\t1";

struct Tab { std::string url, title; };
struct Session { std::string name; long long savedAt = 0; std::vector<Tab> tabs; };
// One open tab as the shell sees it (skip: owned by the Media section).
struct Candidate { std::string url, title; bool priv = false, skip = false; };

inline std::string cut(std::string s, size_t max)   // never splits a UTF-8 sequence
{
    if (s.size() > max) { size_t c = max; while (c && (static_cast<unsigned char>(s[c]) & 0xc0) == 0x80) --c; s.resize(c); }
    return s;
}
inline std::string oneLine(std::string s, size_t max)
{
    for (auto& c : s) if (c == '\t' || c == '\n' || c == '\r') c = ' ';
    return cut(std::move(s), max);
}
inline std::string trim(const std::string& s)
{
    const size_t a = s.find_first_not_of(' ');
    if (a == std::string::npos) return std::string();
    return s.substr(a, s.find_last_not_of(' ') - a + 1);
}
inline std::string lower(std::string s) { for (auto& c : s) if (c >= 'A' && c <= 'Z') c += 'a' - 'A'; return s; }
inline bool sameName(const std::string& a, const std::string& b) { return lower(trim(a)) == lower(trim(b)); }
inline bool webUrl(const std::string& u) { return u.rfind("https://", 0) == 0 || u.rfind("http://", 0) == 0; }
inline int find(const std::vector<Session>& list, const std::string& name)
{
    for (size_t i = 0; i < list.size(); ++i) if (sameName(list[i].name, name)) return int(i);
    return -1;
}

// --- names -------------------------------------------------------------------------------------------------------
inline std::string shortDate(time_t t)   // "16 Nov 2026"
{
    static const char* const months[] = { "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec" };
    struct tm a {};
    localtime_r(&t, &a);
    char b[32];
    snprintf(b, sizeof(b), "%d %s %d", a.tm_mday, months[a.tm_mon % 12], a.tm_year + 1900);
    return b;
}
inline std::string defaultName(time_t now) { return "Session " + shortDate(now); }
// `base`, or "base (2)", "base (3)" ... so no other session (except index `except`) has it.
inline std::string uniqueName(const std::vector<Session>& list, const std::string& base, int except = -1)
{
    auto taken = [&](const std::string& n) { const int i = find(list, n); return i >= 0 && i != except; };
    if (!taken(base)) return base;
    for (int k = 2; k < 1000; ++k) {
        const std::string suffix = " (" + std::to_string(k) + ")";
        const std::string n = cut(base, kNameMax - suffix.size()) + suffix;
        if (!taken(n)) return n;
    }
    return base;
}
// What the keyboard returned, made storable; empty -> `fallback`.
inline std::string cleanName(const std::string& raw, const std::string& fallback)
{
    std::string n = trim(oneLine(raw, 4096));
    n = trim(cut(n, kNameMax));
    return n.empty() ? fallback : n;
}

// --- file --------------------------------------------------------------------------------------------------------
inline std::string serialize(const std::vector<Session>& list)
{
    std::string s = std::string(kHeader) + "\n";
    int n = 0;
    for (auto& e : list) {
        if (e.tabs.empty() || n >= kMaxSessions) continue;
        ++n;
        s += "session\t" + std::to_string(e.savedAt) + "\t" + oneLine(e.name, kNameMax) + "\n";
        int k = 0;
        for (auto& t : e.tabs) {
            if (k >= kMaxTabs || !webUrl(t.url) || t.url.size() > kUrlMax) continue;
            ++k;
            s += "tab\t" + oneLine(t.url, kUrlMax) + "\t" + oneLine(t.title, kTitleMax) + "\n";
        }
    }
    return s;
}
// Tolerant: unknown or bad lines are skipped, a session without tabs is dropped, names are made unique.
inline std::vector<Session> parse(const std::string& text)
{
    std::vector<Session> out;
    bool open = false;   // the last "session" line started out.back()
    auto close = [&] { if (open && out.back().tabs.empty()) out.pop_back(); open = false; };
    size_t pos = 0;
    while (pos < text.size()) {
        size_t end = text.find('\n', pos);
        if (end == std::string::npos) end = text.size();
        std::string line = text.substr(pos, end - pos);
        pos = end + 1;
        while (!line.empty() && (line.back() == '\r' || line.back() == '\n')) line.pop_back();
        if (line.rfind("session\t", 0) == 0) {
            close();
            if (int(out.size()) >= kMaxSessions) break;
            const size_t a = line.find('\t', 8);
            Session e;
            e.savedAt = atoll(line.substr(8, a == std::string::npos ? std::string::npos : a - 8).c_str());
            std::string name = a == std::string::npos ? std::string() : trim(cut(line.substr(a + 1), kNameMax));
            if (name.empty()) name = "Session";
            e.name = uniqueName(out, name);
            out.push_back(std::move(e));
            open = true;
        } else if (open && line.rfind("tab\t", 0) == 0) {
            if (int(out.back().tabs.size()) >= kMaxTabs) continue;
            const size_t a = line.find('\t', 4);
            Tab t;
            t.url = line.substr(4, a == std::string::npos ? std::string::npos : a - 4);
            if (!webUrl(t.url) || t.url.size() > kUrlMax) continue;
            if (a != std::string::npos) t.title = cut(line.substr(a + 1), kTitleMax);
            out.back().tabs.push_back(std::move(t));
        }
    }
    close();
    return out;
}

// --- saving ------------------------------------------------------------------------------------------------------
// The tabs a save keeps: web pages only, no private or Media tabs, no duplicate URLs, at most `limit` (and kMaxTabs).
inline std::vector<Tab> collect(const std::vector<Candidate>& open, int limit)
{
    std::vector<Tab> out;
    const size_t cap = size_t(std::clamp(limit, 1, kMaxTabs));
    for (auto& c : open) {
        if (out.size() >= cap) break;
        if (c.priv || c.skip || !webUrl(c.url) || c.url.size() > kUrlMax) continue;
        bool dup = false;
        for (auto& t : out) if (t.url == c.url) { dup = true; break; }
        if (!dup) out.push_back({ c.url, oneLine(c.title, kTitleMax) });
    }
    return out;
}
enum SaveResult { kAdded, kUpdated, kFull, kEmpty };
// Newest first. A name that exists is updated (and moves to the top); a new name when 30 exist is refused.
inline SaveResult save(std::vector<Session>& list, const std::string& name, std::vector<Tab> tabs, long long now)
{
    if (tabs.empty()) return kEmpty;
    Session e; e.name = name; e.savedAt = now; e.tabs = std::move(tabs);
    const int at = find(list, name);
    if (at >= 0) {
        list.erase(list.begin() + at);
        list.insert(list.begin(), std::move(e));
        return kUpdated;
    }
    if (int(list.size()) >= kMaxSessions) return kFull;
    list.insert(list.begin(), std::move(e));
    return kAdded;
}
// False when the new name is empty (the old one stays). A name another session has gets " (2)".
inline bool rename(std::vector<Session>& list, int index, const std::string& raw)
{
    if (index < 0 || index >= int(list.size())) return false;
    const std::string n = cleanName(raw, std::string());
    if (n.empty()) return false;
    list[size_t(index)].name = uniqueName(list, n, index);
    return true;
}
inline bool remove(std::vector<Session>& list, int index)
{
    if (index < 0 || index >= int(list.size())) return false;
    list.erase(list.begin() + index);
    return true;
}

// --- opening -----------------------------------------------------------------------------------------------------
struct Plan {
    std::vector<int> open;   // indexes into the session's tabs, in order
    int alreadyOpen = 0;     // add: the URL is open already (or twice in the session)
    int overLimit = 0;       // did not fit under the tab limit
    int closes = 0;          // replace: tabs closed first
};
// openUrls: the URLs of the open tabs (for "already open"); openCount: every open tab (private ones too).
inline Plan plan(const Session& s, const std::vector<std::string>& openUrls, int openCount, int limit, bool replace)
{
    Plan p;
    p.closes = replace ? openCount : 0;
    int room = std::max(0, replace ? limit : limit - openCount);
    std::vector<std::string> seen = replace ? std::vector<std::string>() : openUrls;
    for (size_t i = 0; i < s.tabs.size(); ++i) {
        const std::string& u = s.tabs[i].url;
        if (std::find(seen.begin(), seen.end(), u) != seen.end()) { ++p.alreadyOpen; continue; }
        seen.push_back(u);
        if (room <= 0) { ++p.overLimit; continue; }
        --room;
        p.open.push_back(int(i));
    }
    return p;
}

// --- texts -------------------------------------------------------------------------------------------------------
inline std::string tabsText(size_t n) { return std::to_string(n) + (n == 1 ? " tab" : " tabs"); }
inline std::string host(const std::string& url)
{
    size_t a = url.find("://");
    a = a == std::string::npos ? 0 : a + 3;
    size_t b = url.find_first_of("/?#", a);
    std::string h = url.substr(a, b == std::string::npos ? std::string::npos : b - a);
    const size_t at = h.rfind('@');
    if (at != std::string::npos) h = h.substr(at + 1);
    if (h.rfind("www.", 0) == 0) h = h.substr(4);
    return h;
}
// "youtube.com, imdb.com +3": the distinct sites in order, at most `maxChars` bytes before the "+N".
inline std::string sitesText(const Session& s, size_t maxChars)
{
    std::vector<std::string> sites;
    for (auto& t : s.tabs) { const std::string h = host(t.url); if (!h.empty() && std::find(sites.begin(), sites.end(), h) == sites.end()) sites.push_back(h); }
    std::string out;
    size_t shown = 0;
    for (auto& h : sites) {
        const size_t add = (out.empty() ? 0 : 2) + h.size();
        if (shown && out.size() + add > maxChars) break;
        out += (out.empty() ? "" : ", ") + h;
        ++shown;
    }
    if (shown < sites.size()) out += " +" + std::to_string(sites.size() - shown);
    return out;
}
// "Today 21:05", "Yesterday", "16 Nov", "16 Nov 2025" (another year).
inline std::string whenText(time_t t, time_t now)
{
    static const char* const months[] = { "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec" };
    struct tm a {}, n {}, y {};
    localtime_r(&t, &a);
    localtime_r(&now, &n);
    const time_t yesterday = now - 86400;
    localtime_r(&yesterday, &y);
    char b[48];
    if (a.tm_year == n.tm_year && a.tm_yday == n.tm_yday) snprintf(b, sizeof(b), "Today %02d:%02d", a.tm_hour, a.tm_min);
    else if (a.tm_year == y.tm_year && a.tm_yday == y.tm_yday) snprintf(b, sizeof(b), "Yesterday");
    else if (a.tm_year == n.tm_year) snprintf(b, sizeof(b), "%d %s", a.tm_mday, months[a.tm_mon % 12]);
    else snprintf(b, sizeof(b), "%d %s %d", a.tm_mday, months[a.tm_mon % 12], a.tm_year + 1900);
    return b;
}
inline std::string listValue(const Session& s, time_t now) { return tabsText(s.tabs.size()) + " \xc2\xb7 " + whenText(time_t(s.savedAt), now); }
// The choice rows' right-hand text.
inline std::string planValue(const Plan& p, bool replace)
{
    if (p.open.empty()) return p.overLimit ? "Tab limit reached" : "All open already";
    std::string v = "Opens " + std::to_string(p.open.size());
    if (replace && p.closes) v += ", closes " + std::to_string(p.closes);
    if (p.overLimit) v += " (" + std::to_string(p.overLimit) + " over the limit)";
    return v;
}
inline std::string savedNotice(SaveResult r, const std::string& name, size_t tabs)
{
    switch (r) {
    case kAdded: return "Saved " + tabsText(tabs) + " as \"" + name + "\"";
    case kUpdated: return "Updated \"" + name + "\" (" + tabsText(tabs) + ")";
    case kFull: return std::to_string(kMaxSessions) + " sessions saved: delete one first (Tabs > Sessions)";
    default: return "No tabs to save (private tabs are never saved)";
    }
}
inline std::string openedNotice(const std::string& name, size_t opened, int alreadyOpen, int overLimit)
{
    std::string s = opened ? "Opened \"" + name + "\": " + tabsText(opened) : "Nothing opened from \"" + name + "\"";
    if (alreadyOpen) s += ", " + std::to_string(alreadyOpen) + " already open";
    if (overLimit) s += ", " + std::to_string(overLimit) + " over the tab limit";
    return s;
}

} // namespace OmniTabSessions
'''

SHELL = r'''// OMNI_TAB_SESSIONS_V1: named tab sessions (shell side). Included from OmniFeatures3.h (inside OmniBrowser.cpp's
// anonymous namespace, after OmniTabMemory.h). The pure part is OmniTabSessions.h; the reasons are in
// tools/apply_tab_sessions.py. Everything runs on the main thread; the file is written by omniIoQueue.
#pragma once

namespace TS = OmniTabSessions;
static std::vector<TS::Session> omniTsList;      // newest first
static bool omniTsLoaded = false;
static std::string omniTsNameBuf, omniTsRenameOf;
static std::vector<TS::Tab> omniTsPending;       // the tabs taken when Save was pressed
static int omniTsOpenIdx = -1, omniTsDeleteArm = -1;
enum { omniTsRowSave = 110, omniTsRowList = 111 };            // Tabs panel (its own rows: tabs 0..15, 100..102)
enum { omniTsRowEmpty = 1, omniTsRowFirst = 1000 };           // Sessions panel
enum { omniTsRowReplace = 1, omniTsRowAdd = 2 };              // Open panel

static void omniTsLoad()
{
    if (omniTsLoaded) return;
    omniTsLoaded = true;
    FILE* f = fopen(omniData(TS::kFileName).c_str(), "rb");
    if (!f) return;
    std::string text;
    char buf[8192];
    size_t got;
    while ((got = fread(buf, 1, sizeof(buf), f)) > 0 && long(text.size()) < TS::kMaxFileBytes) text.append(buf, got);
    fclose(f);
    omniTsList = TS::parse(text);
    fprintf(stderr, "OMNI TAB SESSIONS: %zu session(s)\n", omniTsList.size());
}
static void omniTsWrite()
{
    if (omniTestMode()) return;
    omniIoQueue(omniData(TS::kFileName), TS::serialize(omniTsList), false);
}
static std::string omniTsTabURL(const Tab& t) { return !t.omniLazyURL.empty() && t.omniLazyURL != "newtab" ? t.omniLazyURL : t.url; }
static std::vector<TS::Candidate> omniTsCandidates()
{
    std::vector<TS::Candidate> out;
    for (auto& tp : tabs) {
        const Tab& t = *tp;
        TS::Candidate c; c.url = omniTsTabURL(t); c.title = t.title; c.priv = t.omniPrivate; c.skip = omniMediaOwns(t);
        out.push_back(std::move(c));
    }
    return out;
}
static std::vector<TS::Tab> omniTsSavable() { return TS::collect(omniTsCandidates(), omniF3TabLimit()); }

// --- save ------------------------------------------------------------------------------------------------------------
static void omniTsStartSave()
{
    omniTsLoad();
    omniTsPending = omniTsSavable();
    if (omniTsPending.empty()) { notice(TS::savedNotice(TS::kEmpty, "", 0)); return; }
    omniTsNameBuf = TS::uniqueName(omniTsList, TS::defaultName(time(nullptr)));
    omniKbEdit(&omniTsNameBuf, "Session name", [](bool ok) {
        std::vector<TS::Tab> list = std::move(omniTsPending);
        omniTsPending.clear();
        if (!ok) return;
        const std::string name = TS::cleanName(omniTsNameBuf, TS::uniqueName(omniTsList, TS::defaultName(time(nullptr))));
        const size_t n = list.size();
        const TS::SaveResult r = TS::save(omniTsList, name, std::move(list), (long long)time(nullptr));
        if (r == TS::kAdded || r == TS::kUpdated) omniTsWrite();
        notice(TS::savedNotice(r, name, n));
        omniFxRefresh();
    });
}

// --- open ------------------------------------------------------------------------------------------------------------
static void omniTsOpen(const TS::Session s, bool replace)
{
    omniFxCloseAll();
    const long long freeMiB = omniTestMode() ? -1 : omniTmQueryMiB();   // newTab()'s guard, once (the tabs open lazily)
    if (freeMiB >= 0 && freeMiB < omniF3Set.refuseMiB) { notice("Memory is low (" + std::to_string(freeMiB) + " MiB free): close a tab first"); return; }
    std::vector<std::string> urls;
    for (auto& t : tabs) if (!t->omniPrivate) urls.push_back(omniTsTabURL(*t));
    const TS::Plan plan = TS::plan(s, urls, int(tabs.size()), omniF3TabLimit(), replace);
    if (plan.open.empty()) { notice(TS::openedNotice(s.name, 0, plan.alreadyOpen, plan.overLimit)); return; }
    Tab* keep = nullptr;
    if (replace && !tabs.empty()) {
        keep = active();
        for (auto& t : tabs) if (t.get() != keep) t->omniLazyURL.clear();   // closing must not load them first
        omniTmSkipRestore = true;                                           // nor reload an unloaded one
        while (tabs.size() > 1) {
            size_t i = 0;
            while (i < tabs.size() && tabs[i].get() == keep) ++i;
            if (i >= tabs.size()) break;
            activate(i);
            closeTab();   // to "Reopen closed tab" (omniFxTabClosing) as usual
        }
        omniTmSkipRestore = false;
    }
    std::vector<Tab*> made;
    size_t next = 0;
    auto make = [&](size_t upTo) {   // as start-up restore: no memory check per tab, nothing loads until shown
        omniF3Restoring = true;
        for (; next < upTo && next < plan.open.size(); ++next) {
            Tab* t = newTab();
            if (!t) break;
            const TS::Tab& st = s.tabs[size_t(plan.open[next])];
            t->omniLazyURL = st.url; t->url = st.url;
            t->title = st.title.empty() ? omniBlockerHostOf(st.url) : st.title;
            made.push_back(t);
        }
        omniF3Restoring = false;
    };
    const int room = std::max(0, omniF3TabLimit() - int(tabs.size()));
    make(size_t(room));
    if (keep && !made.empty()) {   // the last old tab goes; its neighbour (the first session tab) is shown and loads
        for (size_t i = 0; i < tabs.size(); ++i) if (tabs[i].get() == keep) {
            omniTmSkipRestore = true; activate(i); omniTmSkipRestore = false;
            closeTab();
            break;
        }
        make(plan.open.size());
    }
    if (!made.empty()) for (size_t i = 0; i < tabs.size(); ++i) if (tabs[i].get() == made.front()) { activate(i); break; }
    const int notOpened = int(plan.open.size() - made.size());
    notice(TS::openedNotice(s.name, made.size(), plan.alreadyOpen, plan.overLimit + notOpened));
    omniShellDirty = true;
}
static void omniTsChoiceBuild(OmniFxPanel& p)
{
    if (omniTsOpenIdx < 0 || omniTsOpenIdx >= int(omniTsList.size())) { OmniFxRow r; r.id = 0; r.label = "This session was deleted"; r.enabled = false; p.rows.push_back(r); return; }
    const TS::Session& s = omniTsList[size_t(omniTsOpenIdx)];
    std::vector<std::string> urls;
    for (auto& t : tabs) if (!t->omniPrivate) urls.push_back(omniTsTabURL(*t));
    const int limit = omniF3TabLimit();
    const TS::Plan pr = TS::plan(s, urls, int(tabs.size()), limit, true), pa = TS::plan(s, urls, int(tabs.size()), limit, false);
    p.title = "Open \"" + s.name + "\"";
    p.subtitle = TS::tabsText(s.tabs.size()) + " saved \xc2\xb7 " + TS::tabsText(tabs.size()) + " open now \xc2\xb7 tab limit " + std::to_string(limit);
    OmniFxRow a; a.id = omniTsRowReplace; a.label = "Replace the open tabs"; a.value = TS::planValue(pr, true); a.enabled = !pr.open.empty();
    OmniFxRow b; b.id = omniTsRowAdd; b.label = "Add to the open tabs"; b.value = TS::planValue(pa, false); b.enabled = !pa.open.empty();
    p.rows.push_back(a);
    p.rows.push_back(b);
}
static bool omniTsChoiceInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    if (!r.enabled || omniTsOpenIdx < 0 || omniTsOpenIdx >= int(omniTsList.size())) return true;
    omniTsOpen(omniTsList[size_t(omniTsOpenIdx)], r.id == omniTsRowReplace);   // a copy: the panels close first
    return true;
}
static void omniTsChoiceShow(int index)
{
    omniTsOpenIdx = index;
    OmniFxPanel p;
    p.title = "Open session"; p.w = 820; p.maxVisible = 2;
    p.build = omniTsChoiceBuild; p.input = omniTsChoiceInput;
    p.faces = { { 0, "Open" }, { 1, "Back" } };
    omniFxPush(std::move(p));
}

// --- the Sessions panel ----------------------------------------------------------------------------------------------
static void omniTsListBuild(OmniFxPanel& p)
{
    omniTsLoad();
    if (omniTsDeleteArm >= 0 && p.sel != omniTsDeleteArm) omniTsDeleteArm = -1;   // moved off the row: disarmed
    if (omniTsList.empty()) {
        OmniFxRow r; r.id = omniTsRowEmpty; r.enabled = false;
        r.label = "No saved sessions"; r.detail = "Tabs > Save these tabs as a session";
        p.rows.push_back(r);
    }
    const time_t now = time(nullptr);
    for (size_t i = 0; i < omniTsList.size(); ++i) {
        const TS::Session& s = omniTsList[i];
        OmniFxRow r; r.id = omniTsRowFirst + int(i);
        r.label = s.name; r.detail = TS::sitesText(s, 48);
        const bool armed = omniTsDeleteArm == int(i);
        r.value = armed ? std::string("Square again: delete") : TS::listValue(s, now);
        r.danger = armed;
        p.rows.push_back(r);
    }
    p.corner = std::to_string(omniTsList.size()) + " / " + std::to_string(TS::kMaxSessions);
}
static bool omniTsListInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (r.id < omniTsRowFirst) return b == SDL_CONTROLLER_BUTTON_A;
    const int i = r.id - omniTsRowFirst;
    if (i >= int(omniTsList.size())) return false;
    if (b != SDL_CONTROLLER_BUTTON_X) omniTsDeleteArm = -1;
    switch (b) {
    case SDL_CONTROLLER_BUTTON_A: omniTsChoiceShow(i); return true;
    case SDL_CONTROLLER_BUTTON_Y:
        omniTsNameBuf = omniTsRenameOf = omniTsList[size_t(i)].name;
        omniKbEdit(&omniTsNameBuf, "Rename session", [](bool ok) {
            if (!ok) return;
            const int at = TS::find(omniTsList, omniTsRenameOf);
            if (at >= 0 && TS::rename(omniTsList, at, omniTsNameBuf)) { omniTsWrite(); notice("Renamed to \"" + omniTsList[size_t(at)].name + "\""); }
            omniFxRefresh();
        });
        return true;
    case SDL_CONTROLLER_BUTTON_X:
        if (omniTsDeleteArm != i) { omniTsDeleteArm = i; return true; }
        omniTsDeleteArm = -1;
        notice("Deleted session \"" + omniTsList[size_t(i)].name + "\"");
        TS::remove(omniTsList, i);
        omniTsWrite();
        return true;
    default: return false;
    }
}
static void omniTsListShow()
{
    omniTsLoad();
    omniTsDeleteArm = -1;
    OmniFxPanel p;
    p.title = "Sessions"; p.subtitle = "Saved sets of tabs (private tabs are never saved)";
    p.w = 980; p.maxVisible = 8;
    p.build = omniTsListBuild; p.input = omniTsListInput;
    p.faces = { { 0, "Open" }, { 3, "Rename" }, { 2, "Delete" }, { 1, "Back" } };
    omniFxPush(std::move(p));
}

// --- Tabs panel rows (declared in OmniTabsPage.h) --------------------------------------------------------------------
static void omniTsTabsRows(OmniFxPanel& p)
{
    omniTsLoad();
    const size_t n = omniTsSavable().size();
    OmniFxRow s; s.id = omniTsRowSave; s.label = "Save these tabs as a session\xe2\x80\xa6"; s.icon = omniIconCheck;
    s.enabled = n > 0; s.value = n ? TS::tabsText(n) : std::string("Nothing to save");
    p.rows.push_back(s);
    OmniFxRow l; l.id = omniTsRowList; l.label = "Sessions\xe2\x80\xa6"; l.icon = omniIconForward;
    l.enabled = !omniTsList.empty(); l.value = omniTsList.empty() ? std::string("None saved") : std::to_string(omniTsList.size()) + " saved";
    p.rows.push_back(l);
}
static bool omniTsTabsInput(const OmniFxRow& r, int b)
{
    if (r.id != omniTsRowSave && r.id != omniTsRowList) return false;
    if (b != SDL_CONTROLLER_BUTTON_A || !r.enabled) return true;   // the panel takes the button
    if (r.id == omniTsRowSave) omniTsStartSave(); else omniTsListShow();
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniReadingList.h" // OMNI_READING_LIST_V1: reading list index, caps, saved-page wrapper (pure)\n',
         '#include "OmniReadingList.h" // OMNI_READING_LIST_V1: reading list index, caps, saved-page wrapper (pure)\n'
         '#include "OmniTabSessions.h" // OMNI_TAB_SESSIONS_V1: named tab sessions, sessions.txt (pure)\n'),
    ],
    'OmniTabsPage.h': [
        ('enum { omniFxTabNew = 100, omniFxTabPrivate, omniFxTabReopen };\n',
         'enum { omniFxTabNew = 100, omniFxTabPrivate, omniFxTabReopen };\n'
         'static void omniTsTabsRows(OmniFxPanel& p);              // OMNI_TAB_SESSIONS_V1 (OmniTabSessionsShell.h): rows 110, 111\n'
         'static bool omniTsTabsInput(const OmniFxRow& r, int b);\n'),
        ('    p.corner = std::to_string(tabs.size()) + " of " + std::to_string(omniF3TabLimit()); // OMNI_FEATURES_V3\n',
         '    omniTsTabsRows(p); // OMNI_TAB_SESSIONS_V1: Save these tabs as a session..., Sessions...\n'
         '    p.corner = std::to_string(tabs.size()) + " of " + std::to_string(omniF3TabLimit()); // OMNI_FEATURES_V3\n'),
        ('    if (b != SDL_CONTROLLER_BUTTON_A || !r.enabled) return r.id >= omniFxTabNew;\n',
         '    if (omniTsTabsInput(r, b)) return true; // OMNI_TAB_SESSIONS_V1\n'
         '    if (b != SDL_CONTROLLER_BUTTON_A || !r.enabled) return r.id >= omniFxTabNew;\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniReadingListShell.h" // OMNI_READING_LIST_V1\n',
         '#include "OmniReadingListShell.h" // OMNI_READING_LIST_V1\n'
         '#include "OmniTabSessionsShell.h" // OMNI_TAB_SESSIONS_V1\n'),
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
    if 'OMNI_READING_LIST_V1' not in (root / 'OmniFeatures3.h').read_bytes().decode('utf-8'):
        sys.exit('OmniFeatures3.h: OMNI_READING_LIST_V1 missing: apply_reading_list.py first')
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniTabSessions.h', PURE, 'OmniReadingList.h'),
            write_new('OmniTabSessionsShell.h', SHELL, 'OmniFeatures.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
