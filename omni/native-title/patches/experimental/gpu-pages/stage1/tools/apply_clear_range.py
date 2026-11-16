#!/usr/bin/env python3
"""OMNI_CLEAR_RANGE_V1 (2026-11-16): "Clear browsing data" with a time range and categories.

What the user sees
  Options (Tools menu) > "Clear browsing data" no longer asks "Clear browsing data?" and wipes everything; it opens
  a panel:
      Time range                  < Last hour | Last 24 hours | Last 7 days | All time >   (default Last hour)
      History                     On / Off   "12 visits"
      Cookies and site data       On / Off   "cookies of 4 sites visited"  /  "every site (signs you out)"
      Cached files                On / Off   "whole cache, any range"
      Learned keyboard words      On / Off   "37 words"            ("All time only", row disabled, other ranges)
      Continue watching list      On / Off   "2 entries"
      Closed-tab list             On / Off   "3 tabs"              ("All time only", row disabled, other ranges)
      Clear data                  (red) asks once, Cancel focused, naming what goes
  Defaults: History, Cookies and site data, Cached files on; the other three off. The choice is kept until Omni
  exits (not saved). After "Clear" the panel stays open; a summary is shown as a notice and as the panel's
  subtitle, e.g. "Cleared 12 visits, cookies of 4 sites, cached files. Not cleared: cached files (no answer in time)."
  The panel has no checkbox widget: the categories are On / Off stepper rows like the rest of Browser settings.

What each category really clears (persistent data store only; private tabs are never touched, as before)
  History              time-filtered: every history.txt visit with time >= range start (history keeps a unix time
                       per visit; a reload moves the visit's time to the reload). Rewrites history.txt
                       (omniHpChanged: suggestions / most-visited refresh too).
  Cookies and site     All time: WKHTTPCookieStoreDeleteAllCookies, RemoveLocalStorage, RemoveAllIndexedDatabases,
  data                 RemoveAllServiceWorkerRegistrations, RemoveAllFetchCaches (what the old menu item did).
                       A shorter range: WebKit's C API here has no "modified since" removal (WKWebsiteDataStoreRemove-
                       DataOfTypes does not exist in this tree, see apply_site_clear.py), so the range picks SITES:
                       every host visited in the range (from history, read BEFORE history is cleared, newest first,
                       at most 400, www./bare merged) gets the per-site calls site_clear proved:
                       WKWebsiteDataStoreStatisticsDeleteCookiesForTesting (whole registrable domain, HttpOnly
                       included), WKWebsiteDataStoreRemoveITPDataForDomain, and CacheStorage origins of that host and
                       its www./bare twin (GetFetchCacheOrigins + RemoveFetchCacheForOrigin). Their localStorage,
                       IndexedDB and service workers STAY (only all-sites calls exist; site_clear reaches them only by
                       a script in an open page). Cookies set by sites never visited as a page (third-party frames)
                       and cookies older than the range of a site visited in it are deleted / kept by site, not by age.
  Cached files         WKWebsiteDataStoreRemoveNetworkCache + RemoveMemoryCaches: the WHOLE cache for every range
                       (only an all-sites call exists; it holds no sign-in state). The row says so.
  Learned keyboard     All time only: kb-words.txt keeps a use counter per word, no date. Same steps as Browser
  words                settings > Clear learned words (queue an empty write, flush, unlink the file and .tmp).
  Continue watching    time-filtered: the omni-resume-videos add-on's "w:" storage entries whose "a" (unix seconds,
  list                 written by the add-on) is >= range start; All time: every "w:" entry (entries without "a" go only
                       then). Saved with omniAdSaveStorage; open start pages redraw. The add-on's other keys (a page's
                       own resume offer) stay. Missing add-on: nothing to clear.
  Closed-tab list      All time only: omniFxClosed (in memory, this run, at most 10) keeps no close time.
  Not touched          open tabs / session.txt (restore), the tabs' back/forward lists, bookmarks, reading list,
                       passwords, autofill, site settings, downloads (the Downloads app), private-tab data.
  One clear at a time. The WebKit calls finish asynchronously; omniClrTick (omniF3Tick) shows the summary after
  OmniClearRange::kNativeMs (15 s) with whatever has not answered marked "no answer in time"; the job is freed only
  when every callback it handed out has come back (site_clear's pattern). The active tab reloads when cookies went.

Pure part: engine/entry/OmniClearRange.h (no SDL / WebKit): ranges, categories and how each applies to a range,
host list from history, history count / erase by time, the add-on's "a" field, row texts, the question, the summary.
Tested by tools/test_clear_range.cpp:  g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_clear_range.cpp -o t && ./t
Shell side: engine/entry/OmniClearRangeShell.h, included from OmniBrowser.cpp after OmniContinueWatchingShell.h
(it uses omniCw*, omniAd*, omniKw*, omniHistory / omniHpChanged, omniFxClosed, OmniSiteClear's target helpers).
Panel kind 7420, row ids 7421-7428 (unused elsewhere).

Anchors (exactly once each; MARK makes each file idempotent):
  OmniBrowser.cpp   the OmniBookmarksModel.h include line (pure include after it);
                    "static void omniClearBrowsingData()" (made [[maybe_unused]]: the menu no longer calls it);
                    "static void omniMenuActivate(int item)" (forward declarations before it);
                    the two omniAsk lines of case omniMenuClear (replaced by omniClrShow());
                    the OmniContinueWatchingShell.h include line (shell include after it).
  OmniFeatures3.h   the "    omniDkTick(now);" line of omniF3Tick (omniClrTick after it).
Apply AFTER apply_site_clear.py and apply_continue_watching.py (their headers are used).
usage: apply_clear_range.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_CLEAR_RANGE_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_CLEAR_RANGE_V1: the pure part of "Clear browsing data" with a time range and categories (no SDL, no WebKit).
// The shell side is OmniClearRangeShell.h; what each category can really do is in tools/apply_clear_range.py.
// Tested on the host with g++ (test_clear_range.cpp).
#pragma once
#include <climits>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <map>
#include <set>
#include <string>
#include <vector>

namespace OmniClearRange {

constexpr int kPanelKind = 7420;
constexpr int kRowRange = 7421, kRowCat = 7422, kRowClear = 7428;   // kRowCat + category (7422..7427)
constexpr size_t kMaxSites = 400;          // per-site cookie deletions of one clear (newest sites first)
constexpr uint32_t kNativeMs = 15000;      // the summary is shown after this, whatever has not answered

// SDL_GetTicks() style milliseconds (wrap-safe).
inline bool expired(uint32_t startedAt, uint32_t now) { return uint32_t(now - startedAt) >= kNativeMs; }

// --- ranges --------------------------------------------------------------------------------------------------------
enum Range { LastHour, Last24Hours, Last7Days, AllTime, RangeCount };
inline const char* rangeName(int r)
{
    return r == LastHour ? "Last hour" : r == Last24Hours ? "Last 24 hours" : r == Last7Days ? "Last 7 days" : "All time";
}
// Unix seconds; every visit / entry with a time >= this is in the range (All time: everything).
inline long long rangeStart(int r, long long now)
{
    if (r == LastHour) return now - 3600;
    if (r == Last24Hours) return now - 24 * 3600;
    if (r == Last7Days) return now - 7 * 24 * 3600;
    return LLONG_MIN;
}
inline int stepRange(int r, int dir) { return ((r + dir) % RangeCount + RangeCount) % RangeCount; }

// --- categories ----------------------------------------------------------------------------------------------------
enum Cat { History, Cookies, Cache, KbWords, ContinueWatching, ClosedTabs, CatCount };
inline const char* catName(int c)
{
    static const char* const names[CatCount] = { "History", "Cookies and site data", "Cached files",
                                                  "Learned keyboard words", "Continue watching list", "Closed-tab list" };
    return c >= 0 && c < CatCount ? names[c] : "";
}
// What a category can do for a range.
enum How {
    Everything,      // All time: all of it
    ByTime,          // entries with a time >= the range start
    SitesInRange,    // cookies (+ CacheStorage, ITP data) of the sites visited in the range; their storage stays
    WholeAnyRange,   // the whole thing whatever the range (no time-based API; harmless to empty)
    AllTimeOnly      // keeps no times: only with All time
};
inline How how(int cat, int range)
{
    if (range == AllTime) return Everything;
    switch (cat) {
    case History: case ContinueWatching: return ByTime;
    case Cookies: return SitesInRange;
    case Cache: return WholeAnyRange;
    default: return AllTimeOnly;
    }
}
struct Choice {
    int range = LastHour;
    bool on[CatCount] = { true, true, true, false, false, false };
};
inline bool applies(const Choice& c, int cat) { return cat >= 0 && cat < CatCount && c.on[cat] && how(cat, c.range) != AllTimeOnly; }
inline bool anything(const Choice& c)
{
    for (int i = 0; i < CatCount; ++i) if (applies(c, i)) return true;
    return false;
}

// --- history -------------------------------------------------------------------------------------------------------
template <class V> size_t countSince(const std::vector<V>& h, long long start)
{
    size_t n = 0;
    for (const auto& v : h) if (v.time >= start) ++n;
    return n;
}
template <class V> size_t eraseSince(std::vector<V>& h, long long start)
{
    const size_t before = h.size();
    std::vector<V> kept;
    kept.reserve(h.size());
    for (auto& v : h) if (v.time < start) kept.push_back(std::move(v));
    h.swap(kept);
    return before - h.size();
}
inline char lower(char c) { return c >= 'A' && c <= 'Z' ? char(c + ('a' - 'A')) : c; }
// The host of an http(s) address: lower case, no user@, no :port, no trailing dot, IPv6 kept in brackets
// ("[2001:db8::1]"); "" for anything else or a host with characters a host can't have.
inline std::string hostOf(const std::string& url)
{
    std::string u;
    for (size_t i = 0; i < url.size() && i < 8; ++i) u += lower(url[i]);
    size_t p;
    if (u.rfind("https://", 0) == 0) p = 8;
    else if (u.rfind("http://", 0) == 0) p = 7;
    else return {};
    size_t end = url.find_first_of("/?#", p);
    if (end == std::string::npos) end = url.size();
    const size_t at = url.rfind('@', end ? end - 1 : 0);
    if (at != std::string::npos && at >= p && at < end) p = at + 1;
    std::string h;
    if (p < end && url[p] == '[') {
        const size_t close = url.find(']', p);
        if (close == std::string::npos || close >= end) return {};
        h = url.substr(p, close - p + 1);
    } else {
        const size_t colon = url.find(':', p);
        h = url.substr(p, (colon != std::string::npos && colon < end ? colon : end) - p);
    }
    for (auto& c : h) c = lower(c);
    while (!h.empty() && h.back() == '.') h.pop_back();
    if (h.empty() || h.size() > 255) return {};
    const bool v6 = h[0] == '[';
    for (char c : h) {
        const bool ok = (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '.' || c == '-' || c == '_'
            || (v6 && (c == ':' || c == '[' || c == ']'));
        if (!ok) return {};
    }
    return h;
}
// www.example.com and example.com are one site here (site_clear's cookie call widens to the registrable domain
// anyway, and its CacheStorage filter takes the www. / bare twin).
inline std::string siteKey(const std::string& host) { return host.rfind("www.", 0) == 0 && host.size() > 4 ? host.substr(4) : host; }
// The hosts visited since `start`, newest first, one per siteKey, at most `max`; *more: further sites left out.
template <class V> std::vector<std::string> hostsSince(const std::vector<V>& h, long long start, size_t max, size_t* more = nullptr)
{
    std::vector<std::string> out;
    std::set<std::string> seen;
    size_t extra = 0;
    for (size_t i = h.size(); i-- > 0;) {
        if (h[i].time < start) continue;
        const std::string host = hostOf(h[i].url);
        if (host.empty() || !seen.insert(siteKey(host)).second) continue;
        if (out.size() < max) out.push_back(host);
        else ++extra;
    }
    if (more) *more = extra;
    return out;
}

// --- Continue watching (the omni-resume-videos add-on's "w:" entries) ----------------------------------------------
// A top-level number field of a flat JSON object as JSON.stringify writes it ({"u":"..","a":1700000000}); strings
// are skipped with their escapes, so a title containing "a": is never read as the field.
inline bool jsonNumber(const std::string& s, const std::string& key, double& out)
{
    size_t i = 0;
    auto ws = [&] { while (i < s.size() && (s[i] == ' ' || s[i] == '\t' || s[i] == '\n' || s[i] == '\r')) ++i; };
    auto str = [&](std::string* into) {   // at '"': past the closing quote
        if (i >= s.size() || s[i] != '"') return false;
        for (++i; i < s.size(); ++i) {
            if (s[i] == '\\') { if (into) into->push_back(s[i + 1 < s.size() ? i + 1 : i]); ++i; continue; }
            if (s[i] == '"') { ++i; return true; }
            if (into) into->push_back(s[i]);
        }
        return false;
    };
    ws();
    if (i >= s.size() || s[i] != '{') return false;
    ++i;
    while (true) {
        ws();
        if (i < s.size() && s[i] == '}') return false;
        std::string k;
        if (!str(&k)) return false;
        ws();
        if (i >= s.size() || s[i] != ':') return false;
        ++i;
        ws();
        if (i >= s.size()) return false;
        if (s[i] == '"') { if (!str(nullptr)) return false; }
        else if (s[i] == '{' || s[i] == '[') {   // nested: skip to its end (strings inside skipped)
            int depth = 0;
            while (i < s.size()) {
                if (s[i] == '"') { if (!str(nullptr)) return false; continue; }
                if (s[i] == '{' || s[i] == '[') ++depth;
                else if (s[i] == '}' || s[i] == ']') { if (--depth == 0) { ++i; break; } }
                ++i;
            }
        } else {
            const size_t b = i;
            while (i < s.size() && s[i] != ',' && s[i] != '}' && s[i] != ' ' && s[i] != '\n' && s[i] != '\r' && s[i] != '\t') ++i;
            if (k == key) {
                const std::string num = s.substr(b, i - b);
                char* endp = nullptr;
                const double v = strtod(num.c_str(), &endp);
                if (num.empty() || !endp || *endp) return false;
                out = v;
                return true;
            }
        }
        ws();
        if (i < s.size() && s[i] == ',') { ++i; continue; }
        return false;
    }
}
inline bool cwKey(const std::string& k) { return k.size() > 2 && k.compare(0, 2, "w:") == 0; }
// The "w:" keys to remove: All time (start == LLONG_MIN) every one; otherwise those whose "a" >= start (an entry
// without a usable "a" has no time and stays).
inline std::vector<std::string> cwKeysSince(const std::map<std::string, std::string>& kv, long long start)
{
    std::vector<std::string> out;
    for (auto it = kv.lower_bound("w:"); it != kv.end() && it->first.compare(0, 2, "w:") == 0; ++it) {
        if (!cwKey(it->first)) continue;
        if (start == LLONG_MIN) { out.push_back(it->first); continue; }
        double a = 0;
        if (jsonNumber(it->second, "a", a) && a > 0 && a >= double(start)) out.push_back(it->first);
    }
    return out;
}

// --- texts ---------------------------------------------------------------------------------------------------------
inline std::string count(size_t n, const char* one, const char* many) { return std::to_string(n) + " " + (n == 1 ? one : many); }
struct Counts {
    size_t visits = 0, sites = 0, sitesMore = 0, words = 0, cw = 0, closed = 0;
    bool cwAvailable = true;   // the add-on is installed
};
// The small text beside a category row.
inline std::string rowDetail(int cat, int range, const Counts& c)
{
    switch (how(cat, range)) {
    case AllTimeOnly: return "All time only (no dates kept)";
    case WholeAnyRange: return "Whole cache: it can't be cleared by time";
    case SitesInRange:
        if (!c.sites) return "No sites visited in this time";
        return "Cookies of " + count(c.sites + c.sitesMore, "site", "sites") + " visited; their storage stays";
    default: break;
    }
    switch (cat) {
    case History: return count(c.visits, "visit", "visits");
    case Cookies: return "Every site: you will be signed out";
    case Cache: return "Whole cache";
    case KbWords: return count(c.words, "word", "words");
    case ContinueWatching: return c.cwAvailable ? count(c.cw, "entry", "entries") : "Add-on not installed";
    case ClosedTabs: return count(c.closed, "tab", "tabs");
    }
    return {};
}
inline std::string askTitle(int range)
{
    if (range == AllTime) return "Clear all browsing data?";
    std::string r = rangeName(range);
    r[0] = lower(r[0]);
    return "Clear browsing data from the " + r + "?";
}
inline std::string askBody(const Choice& ch, const Counts& c)
{
    std::vector<std::string> parts;
    const int r = ch.range;
    if (applies(ch, History)) parts.push_back("History: " + count(c.visits, "visit", "visits"));
    if (applies(ch, Cookies)) {
        if (how(Cookies, r) == Everything) parts.push_back("Cookies, site storage and offline data of every site (you will be signed out)");
        else if (c.sites) parts.push_back("Cookies and offline caches of the " + count(c.sites, "site", "sites") + " you visited in that time"
            + (c.sitesMore ? " (the newest " + std::to_string(c.sites) + " of " + std::to_string(c.sites + c.sitesMore) + ")" : std::string())
            + ": signed out there; their local storage and databases stay (only All time clears those)");
        else parts.push_back("Cookies: no sites visited in that time");
    }
    if (applies(ch, Cache)) parts.push_back(how(Cache, r) == Everything ? "Cached files" : "Cached files: the whole cache (it can't be cleared by time)");
    if (applies(ch, KbWords)) parts.push_back(count(c.words, "learned keyboard word", "learned keyboard words"));
    if (applies(ch, ContinueWatching)) parts.push_back("Continue watching: " + count(c.cw, "entry", "entries"));
    if (applies(ch, ClosedTabs)) parts.push_back(count(c.closed, "closed tab", "closed tabs"));
    std::string s;
    for (size_t i = 0; i < parts.size(); ++i) s += parts[i] + (i + 1 < parts.size() ? ". " : ".");
    return s + " Private tabs are not affected.";
}
// What one clear did (the shell fills it in as the parts finish).
struct Result {
    int range = LastHour;
    bool history = false, cookies = false, cache = false, words = false, cw = false, closed = false;   // asked for
    size_t visits = 0, sites = 0, sitesMore = 0, wordCount = 0, cwCount = 0, closedCount = 0;
    bool cookiesOk = true, cacheOk = true, timedOut = false;   // every WebKit call answered (in time)
};
inline std::string summary(const Result& r)
{
    std::vector<std::string> done, left;
    if (r.history && r.visits) done.push_back(count(r.visits, "visit", "visits"));
    if (r.cookies) {
        const bool all = how(Cookies, r.range) == Everything;
        if (!r.cookiesOk) left.push_back(all ? "cookies and site data (no answer in time)" : "some cookies (no answer in time)");
        else if (all) done.push_back("cookies and site data");
        else if (r.sites) done.push_back("cookies of " + count(r.sites, "site", "sites"));
        if (r.sitesMore) left.push_back("cookies of " + count(r.sitesMore, "older site", "older sites") + " (limit " + std::to_string(kMaxSites) + ")");
    }
    if (r.cache) { if (r.cacheOk) done.push_back("cached files"); else left.push_back("cached files (no answer in time)"); }
    if (r.words && r.wordCount) done.push_back(count(r.wordCount, "learned word", "learned words"));
    if (r.cw && r.cwCount) done.push_back(count(r.cwCount, "Continue watching entry", "Continue watching entries"));
    if (r.closed && r.closedCount) done.push_back(count(r.closedCount, "closed tab", "closed tabs"));
    std::string s;
    if (done.empty()) {
        std::string range = rangeName(r.range);
        range[0] = lower(range[0]);
        s = r.range == AllTime ? "Nothing to clear." : "Nothing to clear from the " + range + ".";
    } else {
        s = "Cleared ";
        for (size_t i = 0; i < done.size(); ++i) s += (i ? ", " : "") + done[i];
        s += ".";
    }
    if (!left.empty()) {
        s += " Not cleared: ";
        for (size_t i = 0; i < left.size(); ++i) s += (i ? ", " : "") + left[i];
        s += ".";
    }
    return s;
}
inline std::string busyNotice() { return "Still clearing browsing data..."; }
inline std::string startNotice() { return "Clearing browsing data..."; }

} // namespace OmniClearRange
'''

SHELL = r'''// OMNI_CLEAR_RANGE_V1: "Clear browsing data" panel with a time range and categories (shell side). Included from
// OmniBrowser.cpp after OmniContinueWatchingShell.h (inside its anonymous namespace). The pure part is
// OmniClearRange.h; what each category can really do is in tools/apply_clear_range.py. Main thread only.
// Only the persistent data store (websiteDataStore) is touched: private tabs keep their own, as before.
#pragma once
namespace OCLR = OmniClearRange;
static OCLR::Choice omniClrChoice;     // kept until Omni exits
static std::string omniClrLast;        // the last summary (the panel's subtitle)
struct OmniClrJob {
    WKRetainPtr<WKWebsiteDataStoreRef> store;
    OCLR::Result res;
    std::vector<OSC::Target> targets;  // SitesInRange: hosts whose CacheStorage origins go
    uint32_t gen = 0, startedAt = 0;
    bool finished = false;             // the summary was shown; late callbacks only count down
    int pending = 0;                   // WebKit callbacks not back yet (+1 while starting)
    int cookieCalls = 0, cookieDone = 0;   // cookie / site-data calls
    int cacheCalls = 0, cacheDone = 0;     // HTTP + memory cache
    bool originsListed = true;             // SitesInRange: the CacheStorage list came back
};
static OmniClrJob* omniClrJob = nullptr;
static uint32_t omniClrGen = 0;
static bool omniClrLive(const OmniClrJob* j) { return !j->finished && omniClrJob == j && j->gen == omniClrGen; }
static void omniClrFinish(OmniClrJob* j, bool timedOut)
{
    if (j->finished) return;
    j->finished = true;
    if (omniClrJob == j) omniClrJob = nullptr;
    j->res.timedOut = timedOut;
    j->res.cookiesOk = j->cookieDone == j->cookieCalls && j->originsListed;
    j->res.cacheOk = j->cacheDone == j->cacheCalls;
    omniClrLast = OCLR::summary(j->res);
    notice(omniClrLast);
    fprintf(stderr, "OMNI CLEAR RANGE: %s gen %u %s (cookies %d/%d%s, caches %d/%d, %d callbacks out): %s\n",
            OCLR::rangeName(j->res.range), j->gen, timedOut ? "timed out" : "done", j->cookieDone, j->cookieCalls,
            j->originsListed ? "" : " origins unlisted", j->cacheDone, j->cacheCalls, j->pending, omniClrLast.c_str()); fflush(stderr);
    if (j->res.cookies && active() && !active()->omniPrivate && omniWebURL(active()->url)) WKPageReload(active()->page);
    j->store.clear();
    omniFxRefresh();
}
// Every WebKit callback ends here (once each). The last one frees the job.
static void omniClrBack(OmniClrJob* j)
{
    if (--j->pending > 0) return;
    if (!j->finished) omniClrFinish(j, false);
    delete j;
}
static void omniClrCookieBack(void* ctx) { auto* j = static_cast<OmniClrJob*>(ctx); if (omniClrLive(j)) ++j->cookieDone; omniClrBack(j); }
static void omniClrCacheBack(void* ctx) { auto* j = static_cast<OmniClrJob*>(ctx); if (omniClrLive(j)) ++j->cacheDone; omniClrBack(j); }
static void omniClrOtherBack(void* ctx) { omniClrBack(static_cast<OmniClrJob*>(ctx)); }
static void omniClrTick(uint32_t now)   // from omniF3Tick
{
    OmniClrJob* j = omniClrJob;
    if (!j || !OCLR::expired(j->startedAt, now)) return;
    omniClrFinish(j, true);   // stays allocated until its outstanding callbacks are back
}

// What the panel and the question show for a range.
static OCLR::Counts omniClrCounts(int range)
{
    omniHistoryLoad();
    omniKwLoadLearned();
    const long long start = OCLR::rangeStart(range, time(nullptr));
    OCLR::Counts c;
    c.visits = OCLR::countSince(omniHistory, start);
    c.sites = OCLR::hostsSince(omniHistory, start, OCLR::kMaxSites, &c.sitesMore).size();
    c.words = omniKw.learned.words.size();
    OmniAd* a = omniAdFind(omniCwAddon);
    c.cwAvailable = a != nullptr;
    c.cw = a ? OCLR::cwKeysSince(a->storage.kv, start).size() : 0;
    c.closed = omniFxClosed.size();
    return c;
}

static void omniClrClearWords()   // Browser settings > Clear learned words, without its question
{
    omniKw.learned = OmniKbWords::Learned();
    omniKw.learnedLoaded = true;   // empty; the file is gone
    omniKw.dirty = false;
    ++omniKw.gen;
    omniKw.hashValid = false;
    const std::string path = omniData("kb-words.txt");
    omniIoQueue(path, "", false);   // drops any queued write of the file ...
    omniIoFlush();                  // ... and waits (at most 0.8 s) for the writer
    unlink(path.c_str());
    unlink((path + ".tmp").c_str());
}

static void omniClrStart()
{
    if (omniClrJob) { notice(OCLR::busyNotice()); return; }
    const OCLR::Choice ch = omniClrChoice;
    if (!OCLR::anything(ch)) return;
    omniHistoryLoad();
    omniKwLoadLearned();
    const long long now = time(nullptr), start = OCLR::rangeStart(ch.range, now);
    auto* j = new OmniClrJob;
    j->res.range = ch.range;
    j->gen = ++omniClrGen;
    j->startedAt = SDL_GetTicks();
    j->pending = 1;   // held until everything below has been started
    j->store = websiteDataStore.get();
    omniClrJob = j;
    // The sites first: they come from the history about to be cleared.
    std::vector<std::string> hosts;
    if (OCLR::applies(ch, OCLR::Cookies) && OCLR::how(OCLR::Cookies, ch.range) == OCLR::SitesInRange)
        hosts = OCLR::hostsSince(omniHistory, start, OCLR::kMaxSites, &j->res.sitesMore);
    // 1. the parts kept by Omni itself: done now
    if (OCLR::applies(ch, OCLR::History)) {
        j->res.history = true;
        j->res.visits = OCLR::eraseSince(omniHistory, start);
        if (j->res.visits) omniHpChanged();   // history.txt rewrite, suggestions, most visited
    }
    if (OCLR::applies(ch, OCLR::KbWords)) {
        j->res.words = true;
        j->res.wordCount = omniKw.learned.words.size();
        omniClrClearWords();
    }
    if (OCLR::applies(ch, OCLR::ContinueWatching)) {
        j->res.cw = true;
        if (OmniAd* a = omniAdFind(omniCwAddon)) {
            for (const std::string& k : OCLR::cwKeysSince(a->storage.kv, start))
                if (OmniAddonsCore::storageRemove(a->storage, k)) ++j->res.cwCount;
            if (j->res.cwCount) {
                omniAdSaveStorage(*a);
                a->dirty = true; a->dirtyAt = SDL_GetTicks();   // new documents get the new storage
                for (auto& t : tabs) if (t->omniNewTabPage && omniCwDrawn.count(t->page)) omniCwRender(t.get(), -1, true);
            }
        }
    }
    if (OCLR::applies(ch, OCLR::ClosedTabs)) {
        j->res.closed = true;
        j->res.closedCount = omniFxClosed.size();
        omniFxClosed.clear();
    }
    notice(OCLR::startNotice());
    WKWebsiteDataStoreRef store = j->store.get();
    // 2. cookies and site data
    if (OCLR::applies(ch, OCLR::Cookies) && store) {
        j->res.cookies = true;
        if (OCLR::how(OCLR::Cookies, ch.range) == OCLR::Everything) {
            j->pending += 5; j->cookieCalls += 5;
            WKHTTPCookieStoreDeleteAllCookies(WKWebsiteDataStoreGetHTTPCookieStore(store), j, omniClrCookieBack);
            WKWebsiteDataStoreRemoveLocalStorage(store, j, omniClrCookieBack);
            WKWebsiteDataStoreRemoveAllIndexedDatabases(store, j, omniClrCookieBack);
            WKWebsiteDataStoreRemoveAllServiceWorkerRegistrations(store, j, omniClrCookieBack);
            WKWebsiteDataStoreRemoveAllFetchCaches(store, j, omniClrCookieBack);
        } else {
            for (const std::string& h : hosts) {
                const OSC::Target tg = OSC::target("https://" + h + "/");
                if (!tg.ok) continue;
                ++j->res.sites;
                j->targets.push_back(tg);
                for (const std::string& u : OSC::cookieUrls(tg)) {   // the whole registrable domain, HttpOnly included
                    ++j->pending; ++j->cookieCalls;
                    auto s = adoptWK(WKStringCreateWithUTF8CString(u.c_str()));
                    WKWebsiteDataStoreStatisticsDeleteCookiesForTesting(store, s.get(), true, j, omniClrCookieBack);
                }
                ++j->pending;
                auto d = adoptWK(WKStringCreateWithUTF8CString(tg.host.c_str()));
                WKWebsiteDataStoreRemoveITPDataForDomain(store, d.get(), j, omniClrOtherBack);
            }
            if (!j->targets.empty()) {   // CacheStorage of those hosts and their www. / bare twins
                ++j->pending;
                j->originsListed = false;
                WKWebsiteDataStoreGetFetchCacheOrigins(store, j, [](WKArrayRef origins, void* ctx) {
                    OmniClrJob* job = static_cast<OmniClrJob*>(ctx);
                    if (omniClrLive(job)) {
                        job->originsListed = true;
                        const size_t n = origins ? WKArrayGetSize(origins) : 0;
                        for (size_t i = 0; i < n; ++i) {
                            WKSecurityOriginRef o = static_cast<WKSecurityOriginRef>(WKArrayGetItemAtIndex(origins, i));
                            const std::string host = omniOriginHost(o);
                            bool match = false;
                            for (const auto& tg : job->targets) if (OSC::cacheOriginMatches(host, tg)) { match = true; break; }
                            if (!match) continue;
                            ++job->pending; ++job->cookieCalls;
                            WKWebsiteDataStoreRemoveFetchCacheForOrigin(job->store.get(), o, job, omniClrCookieBack);
                        }
                    }
                    omniClrBack(job);
                });
            }
        }
    }
    // 3. cached files: the whole cache whatever the range
    if (OCLR::applies(ch, OCLR::Cache) && store) {
        j->res.cache = true;
        j->pending += 2; j->cacheCalls += 2;
        WKWebsiteDataStoreRemoveNetworkCache(store, j, omniClrCacheBack);
        WKWebsiteDataStoreRemoveMemoryCaches(store, j, omniClrCacheBack);
    }
    omniFxRefresh();
    omniClrBack(j);
}

// --- the panel -------------------------------------------------------------------------------------------------------
static void omniClrBuild(OmniFxPanel& p)
{
    const OCLR::Choice& ch = omniClrChoice;
    const OCLR::Counts c = omniClrCounts(ch.range);
    p.subtitle = omniClrJob ? OCLR::startNotice() : omniClrLast.empty() ? std::string("From this console. Private tabs are not affected.") : omniClrLast;
    OmniFxRow r;
    r.id = OCLR::kRowRange; r.label = "Time range"; r.value = OCLR::rangeName(ch.range); r.stepper = true;
    p.rows.push_back(r);
    for (int cat = 0; cat < OCLR::CatCount; ++cat) {
        OmniFxRow q;
        q.id = OCLR::kRowCat + cat;
        q.label = OCLR::catName(cat);
        const bool usable = OCLR::how(cat, ch.range) != OCLR::AllTimeOnly;
        q.value = usable ? (ch.on[cat] ? "On" : "Off") : "Off";
        q.stepper = usable;
        q.enabled = usable;
        q.detail = OCLR::rowDetail(cat, ch.range, c);
        p.rows.push_back(q);
    }
    OmniFxRow go;
    go.id = OCLR::kRowClear; go.label = "Clear data";
    go.enabled = OCLR::anything(ch) && !omniClrJob;
    go.danger = go.enabled;
    if (omniClrJob) go.value = "Clearing...";
    p.rows.push_back(go);
}
static bool omniClrInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    const bool left = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT, right = b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT, a = b == SDL_CONTROLLER_BUTTON_A;
    if (r.id == OCLR::kRowRange) {
        if (!left && !right && !a) return false;
        omniClrChoice.range = OCLR::stepRange(omniClrChoice.range, left ? -1 : 1);
        return true;
    }
    if (r.id >= OCLR::kRowCat && r.id < OCLR::kRowCat + OCLR::CatCount) {
        if (!left && !right && !a) return false;
        if (!r.enabled) return true;
        bool& on = omniClrChoice.on[r.id - OCLR::kRowCat];
        on = !on;
        return true;
    }
    if (r.id == OCLR::kRowClear) {
        if (!a) return false;
        if (omniClrJob) { notice(OCLR::busyNotice()); return true; }
        if (!r.enabled) return true;
        const OCLR::Counts c = omniClrCounts(omniClrChoice.range);
        omniAsk(OCLR::askTitle(omniClrChoice.range), OCLR::askBody(omniClrChoice, c), "Clear", [](bool ok) { if (ok) omniClrStart(); });
        return true;
    }
    return false;
}
static void omniClrShow()
{
    OmniFxPanel p;
    p.kind = OCLR::kPanelKind;
    p.title = "Clear browsing data";
    p.w = 900; p.maxVisible = 8;
    p.build = omniClrBuild; p.input = omniClrInput;
    p.faces = { { 0, "Change" }, { 1, "Back" } };
    p.extra = "D-pad \xe2\x97\x80 \xe2\x96\xb6 change";
    omniFxPush(std::move(p));
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniBookmarksModel.h" // OMNI_BOOKMARKS_MANAGER_V1: bookmarks.txt with folders, reorder, search (pure)\n',
         '#include "OmniBookmarksModel.h" // OMNI_BOOKMARKS_MANAGER_V1: bookmarks.txt with folders, reorder, search (pure)\n'
         '#include "OmniClearRange.h" /* OMNI_CLEAR_RANGE_V1: Clear browsing data by time range and category (pure) */\n'),
        ('static void omniClearBrowsingData()\n',
         '[[maybe_unused]] static void omniClearBrowsingData() /* OMNI_CLEAR_RANGE_V1: the menu opens omniClrShow() now */\n'),
        ('static void omniMenuActivate(int item)\n',
         'static void omniClrShow();           /* OMNI_CLEAR_RANGE_V1 (OmniClearRangeShell.h) */\n'
         'static void omniClrTick(uint32_t now); /* OMNI_CLEAR_RANGE_V1: from omniF3Tick */\n'
         'static void omniMenuActivate(int item)\n'),
        ('        omniAsk("Clear browsing data?", "History, cookies, site storage and caches will be deleted (you will be signed out of sites). Shortcuts, settings and private tabs are not affected.",\n'
         '            "Clear data", [](bool ok) { if (ok) omniClearBrowsingData(); });\n',
         '        omniClrShow(); /* OMNI_CLEAR_RANGE_V1: time range + categories, asks once */\n'),
        ('#include "OmniContinueWatchingShell.h" // OMNI_CONTINUE_WATCHING_V1\n',
         '#include "OmniContinueWatchingShell.h" // OMNI_CONTINUE_WATCHING_V1\n'
         '#include "OmniClearRangeShell.h" /* OMNI_CLEAR_RANGE_V1 */\n'),
    ],
    'OmniFeatures3.h': [
        ('    omniDkTick(now);\n',
         '    omniDkTick(now);\n'
         '    omniClrTick(now);   /* OMNI_CLEAR_RANGE_V1: native timeout of Clear browsing data */\n'),
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
    for need, by in (('OmniSiteClearShell.h', 'apply_site_clear.py'), ('OmniContinueWatchingShell.h', 'apply_continue_watching.py')):
        if not (root / need).exists():
            sys.exit('%s missing: %s first' % (need, by))
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniClearRange.h', PURE, 'OmniSiteClear.h'),
            write_new('OmniClearRangeShell.h', SHELL, 'OmniSiteClearShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
