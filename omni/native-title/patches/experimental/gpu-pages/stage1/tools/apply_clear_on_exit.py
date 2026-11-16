#!/usr/bin/env python3
"""OMNI_CLEAR_ON_EXIT_V1 (2026-11-16): Browser settings > "Clear on exit..." (backlog E33).

What the user sees
  - Browser settings has a new row after "Keep history":
        "Clear on exit..."     value "Off" / "Cookies, history, cache" (what is on)
                               detail "Cleared when Omni next starts; 3 kept sites"
    Cross opens the sub-page "Clear on exit" (subtitle: "Done when Omni next starts, before any page opens. Passwords,
    bookmarks and the reading list are never cleared."):
        Cookies and site data   On / Off  "Every site, with its storage: you will be signed out"   (nothing kept)
                                          "Every site except 3 kept sites; site storage stays while sites are kept"
        History                 On / Off  "Every visit. Open tabs still come back (On start)"
        Cached files            On / Off  "The whole cache: pages load slower once"
        Keep cookies for this site   the active tab's host (Cross adds it; "On" when already kept; "-" with no web page
                                     or in a private tab)
        example.com             "Remove"  one row per kept site, A-Z ("Its cookies and its subdomains' stay. Cross: remove")
        (or a disabled "No kept sites" row: "Add one here or in Site settings > Keep cookies on exit")
    All three are Off by default. Turning Cookies or History On asks once (the shell's modal, Cancel focused):
        "Clear cookies every time Omni starts?" / "Clear history every time Omni starts?"  ("Turn on")
    Cached files and every Off need no question.
  - Site settings has a new row after "Clear data for this site":
        "Keep cookies on exit"  "On" / "On (example.com)" (kept through a parent entry) / "Off" / "-" / "Private tab"
    Cross or D-pad left / right toggles: On adds the page's host (www. dropped); Off removes every kept entry covering
    it (named in the notice). Disabled in private tabs (a kept host is written to a file, a private visit must not be).
  - The start after a session with any of the three on shows a notice such as
        "Clear on exit: cleared cookies of 41 sites (3 kept sites left alone), history (120 visits), cached files."
        "Clear on exit: cleared cookies and site data, cached files."
        "... Not cleared: cached files (no answer in time)."

Why the clear runs at the NEXT START, not at exit
  Omni's exit path: Options > Quit (or SDL_QUIT) sets running = false; the next tick closes every page, stops audio and
  the light bar, runs omniEverydayShutdown (last session save + omniIoFlush, at most 0.8 s), stops the presenter,
  SDL_Quit, then sceSystemServiceLoadExec("exit") and _exit(0). Nothing in that path waits for the network process,
  and every WebKit data-store removal is an asynchronous IPC answered later on the main run loop, which never runs
  again: a clear started there would be cut off at _exit. Worse, the usual way out of a PS5 app is the PS button >
  Close application (or rest mode / power loss / a crash): the system kills the process, no SDL_QUIT arrives and no
  code runs at all. There is no reliable shutdown hook (the title imports no system-event / power functions, see
  START-HERE.md's import gate). A "pending clear" marker would add nothing: the setting itself says what to clear, and
  whatever the last session left is exactly what is on disk at the next start. So: on every start, if any category
  is on, the categories are cleared right after the persistent data store is attached to the context
  (WKContextSetPrimaryWebsiteDataStore in main()), BEFORE the content blocker's callback creates the first tab or
  restores the session. Data from the last session therefore stays on the console only while Omni is closed, and no
  page of the new session ever sees it. Ordering: the removals are the first messages the UI process sends the network
  process (WebsiteDataStore launches it if needed; its launch takes no web-process options), and the web process's
  network connection is only asked for by a later UI-process message when the first page is created; the network
  process handles one connection's messages in order (cookies: Curl's CookieJarDB is changed synchronously in the
  handler; local storage / IndexedDB / service workers: NetworkStorageManager's serial queue, which every later page
  access also goes through). History and the "seen" parts are synchronous. Test modes are never cleared.

What each category clears (persistent store only: private tabs and guest pages use their own non-persistent stores)
  History            every visit (omniHistory cleared, omniHpChanged: history.txt rewritten on the writer thread,
                     suggestions / most visited refreshed). Open tabs (session.txt) and their back / forward lists are
                     not history: On start decides those, as with Clear browsing data.
  Cookies and site   No kept sites: WKHTTPCookieStoreDeleteAllCookies, RemoveLocalStorage, RemoveAllIndexedDatabases,
  data               RemoveAllServiceWorkerRegistrations, RemoveAllFetchCaches (clear_range's All time).
                     Kept sites: WebKit's C API here cannot list cookie hosts (WKCookieManagerGetHostnamesWithCookies has
                     an empty body; there is no fetch-records call for cookies; see apply_site_clear.py for what exists),
                     so the cookie hosts are READ from Curl's own database, /data/omni/browser-profile/Cookies.db and
                     Cookies.db-wal (read-only, before the network process opens them; the pure part walks the SQLite
                     b-tree pages: Cookie rows, domain_index, the UNIQUE autoindex), plus every host in history (read
                     before history is cleared). Each host not covered by a kept site gets
                     WKWebsiteDataStoreStatisticsDeleteCookiesForTesting("https://<host>/", HttpOnly too): WebKit
                     deletes that host's whole registrable domain (libpsl). Because of that widening, a host is skipped
                     when it is related to a kept site at all: the same host, a subdomain or parent of it, or the same
                     site by OmniSiteClear's heuristic (never narrower than the registrable domain for the usual suffixes;
                     wider for private suffixes such as github.io, which only keeps more). CacheStorage: the fetch
                     records (WKWebsiteDataStoreGetFetchCacheOrigins) minus the kept sites' origins are removed one by
                     one. Local storage, IndexedDB and service workers have only all-sites removals in this WebKit, and
                     clearing them would sign kept sites out of storage-based logins, so they STAY for every site while
                     any site is kept (the row and the question say so). At most 1500 deletions per start (the summary
                     names what is left over). Junk read from a damaged file is harmless: every candidate is checked
                     against the kept sites, and a deletion for a name with no cookies does nothing.
  Cached files       WKWebsiteDataStoreRemoveNetworkCache + RemoveMemoryCaches (the whole HTTP cache; no per-site call).
  Never touched      passwords, autofill, bookmarks, the reading list, highlights, notes, screenshots, site settings,
                     downloads, add-on data, learned keyboard words, private tabs.
  One job per start; omniCoeTick (omniF3Tick) shows the summary after OmniClearOnExit::kNativeMs (20 s) with whatever
  has not answered marked "no answer in time"; the job is freed when every callback it handed out is back
  (site_clear's pattern).

Store: /data/omni/clear-on-exit.txt, written only through omniIoQueue (a full rewrite each change), read once:
    # Omni clear on exit v1
    cookies=1
    history=0
    cache=1
    keep=example.com
  Missing file: everything off, nothing kept. At most 100 kept sites.

For other features (no registration needed; the shell is included from OmniFeatures3.h before OmniSiteListShell.h):
  omniCoeKeptSites() -> std::vector<std::string> (host keys, A-Z), omniCoeKeptValue(host) -> "On" / "On (parent)" /
  "Off", omniCoeSetKept(host, bool) -> bool (writes the file; false: invalid host or the list is full).

Pure part: engine/entry/OmniClearOnExit.h (copied from tools/OmniClearOnExit.h): settings file, host keys, the kept-site
rule, the Cookies.db / -wal reader, the plan, texts. Tests: tools/test_clear_on_exit.cpp
  (g++ -std=c++20 -Wall -Wextra -Werror -fsanitize=address,undefined -I. test_clear_on_exit.cpp -o t && ./t)
  and tools/test_clear_on_exit_db.py (real SQLite files, rollback journal and WAL, made with Python's sqlite3).
Shell part: engine/entry/OmniClearOnExitShell.h (written by this script), namespace alias OCOE, names omniCoe*.
Ids: panel kind 7733 (rows 7734-7738, kept sites 7740 + index), Browser settings row 8733 (handled before the >= 300
  rows), Site settings row 735 (handled before the >= 300 rows); checked unused in every apply_*.py and the tree.

Anchors (each once; whole lines; new lines after them, input hooks before them; CRLF / LF kept):
  OmniBrowser.cpp        the OmniClearRange.h include line (pure include after);
                         "    WKContextSetPrimaryWebsiteDataStore(context.get(), websiteDataStore.get());" in main()
                         (omniCoeStartup after)
  OmniFeatures3.h        the OmniSiteClearShell.h include line (shell include after); the omniHkTick line of omniF3Tick
                         (omniCoeTick after)
  OmniBrowserSettings.h  the omniHkRowId line (row id + declarations after); the omniHkSettingsRow line of the build
                         (row after); the omniHkRowId input line (ours before)
  OmniQuickMenu.h        the omniScSiteInput declaration (row id + declarations after); the omniScSiteRow line (row
                         after); the omniScSiteRowId input line (ours before)
Apply AFTER apply_site_clear.py, apply_clear_range.py and apply_history_keep.py (their lines are anchors).
usage: apply_clear_on_exit.py <engine tree>   (anchored, idempotent, keeps each file's line endings; re-run: "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_CLEAR_ON_EXIT_V1'
HERE = Path(__file__).resolve().parent
if len(sys.argv) != 2:
    sys.exit('usage: apply_clear_on_exit.py <engine tree>')
root = Path(sys.argv[1]) / 'engine' / 'entry'
IDS = ('7733', '7734', '7735', '7736', '7737', '7738', '7740', '8733', '735')
NAMES = ('OCOE', 'omniCoe', 'OmniClearOnExit', 'OMNI_CLEAR_ON_EXIT')

SHELL = r'''// OMNI_CLEAR_ON_EXIT_V1: Browser settings > "Clear on exit..." and Site settings > "Keep cookies on exit" (shell side).
// Included from OmniFeatures3.h after OmniSiteClearShell.h (inside OmniBrowser.cpp's anonymous namespace). The pure
// part is OmniClearOnExit.h; the reasons (why the clear runs at the next start, what each category reaches) are in
// tools/apply_clear_on_exit.py. Main thread only. Only the persistent data store (websiteDataStore) is touched.
#pragma once

namespace OCOE = OmniClearOnExit;

static OCOE::Settings omniCoeSet;
static bool omniCoeLoaded = false;
static void omniCoeLoad()
{
    if (omniCoeLoaded) return;
    omniCoeLoaded = true;
    std::string text;
    if (FILE* f = fopen(omniData(OCOE::kFile).c_str(), "rb")) {
        char buf[4096];
        size_t n;
        while ((n = fread(buf, 1, sizeof(buf), f)) > 0 && text.size() < OCOE::kMaxFileBytes) text.append(buf, n);
        fclose(f);
    }
    omniCoeSet = OCOE::parse(text);
}
static void omniCoeSave() { omniIoQueue(omniData(OCOE::kFile), OCOE::serialize(omniCoeSet), false); }

// --- for other features (Sites with custom settings) -------------------------------------------------------------------
[[maybe_unused]] static std::vector<std::string> omniCoeKeptSites() { omniCoeLoad(); return omniCoeSet.keep; }
[[maybe_unused]] static std::string omniCoeKeptValue(const std::string& host)
{
    omniCoeLoad();
    return OCOE::siteValue(OCOE::hostKey(host), false, omniCoeSet.keep);
}
[[maybe_unused]] static bool omniCoeSetKept(const std::string& host, bool keep)
{
    omniCoeLoad();
    const std::string h = OCOE::hostKey(host);
    if (h.empty()) return false;
    if (keep) {
        if (OCOE::keptBy(h, omniCoeSet.keep) >= 0) return true;   // already covered
        if (!OCOE::addKeep(omniCoeSet, h)) return false;          // the list is full
    } else if (OCOE::removeRelated(omniCoeSet, h).empty()) return true;
    omniCoeSave();
    return true;
}

// --- the start-up clear ------------------------------------------------------------------------------------------------
struct OmniCoeJob {
    WKRetainPtr<WKWebsiteDataStoreRef> store;
    OCOE::Result res;
    std::vector<std::string> keep;             // the kept sites (CacheStorage filter)
    uint32_t gen = 0, startedAt = 0;
    bool finished = false;                     // the summary was shown; late callbacks only count down
    int pending = 0;                           // WebKit callbacks not back yet (+1 while starting)
    int cookieCalls = 0, cookieDone = 0;       // cookie / site-data / CacheStorage calls
    int cacheCalls = 0, cacheDone = 0;         // HTTP + memory cache
    bool originsListed = true;                 // kept sites: the CacheStorage list came back
};
static OmniCoeJob* omniCoeJob = nullptr;
static uint32_t omniCoeGen = 0;
static bool omniCoeLive(const OmniCoeJob* j) { return !j->finished && omniCoeJob == j && j->gen == omniCoeGen; }
static void omniCoeFinish(OmniCoeJob* j, bool timedOut)
{
    if (j->finished) return;
    j->finished = true;
    if (omniCoeJob == j) omniCoeJob = nullptr;
    j->res.timedOut = timedOut;
    j->res.cookiesOk = j->cookieDone == j->cookieCalls && j->originsListed;
    j->res.cacheOk = j->cacheDone == j->cacheCalls;
    const std::string s = OCOE::summary(j->res);
    notice(s);
    fprintf(stderr, "OMNI CLEAR ON EXIT: gen %u %s after %u ms (cookies %d/%d%s, caches %d/%d, %d callbacks out): %s\n",
            j->gen, timedOut ? "timed out" : "done", unsigned(SDL_GetTicks() - j->startedAt), j->cookieDone, j->cookieCalls,
            j->originsListed ? "" : " origins unlisted", j->cacheDone, j->cacheCalls, j->pending, s.c_str()); fflush(stderr);
    j->store.clear();
    omniShellDirty = true;
}
// Every WebKit callback ends here (once each). The last one frees the job.
static void omniCoeBack(OmniCoeJob* j)
{
    if (--j->pending > 0) return;
    if (!j->finished) omniCoeFinish(j, false);
    delete j;
}
static void omniCoeCookieBack(void* ctx) { auto* j = static_cast<OmniCoeJob*>(ctx); if (omniCoeLive(j)) ++j->cookieDone; omniCoeBack(j); }
static void omniCoeCacheBack(void* ctx) { auto* j = static_cast<OmniCoeJob*>(ctx); if (omniCoeLive(j)) ++j->cacheDone; omniCoeBack(j); }
static void omniCoeTick(uint32_t now)   // from omniF3Tick
{
    OmniCoeJob* j = omniCoeJob;
    if (!j || !OCOE::expired(j->startedAt, now)) return;
    omniCoeFinish(j, true);   // stays allocated until its outstanding callbacks are back
}
static std::string omniCoeReadFile(const std::string& path)
{
    std::string out;
    if (FILE* f = fopen(path.c_str(), "rb")) {
        char buf[65536];
        size_t n;
        while (out.size() < OCOE::kMaxDbBytes && (n = fread(buf, 1, sizeof(buf), f)) > 0) out.append(buf, n);
        fclose(f);
    }
    return out;
}
// main(): right after the persistent store became the context's, before any page exists (see the patch notes).
static void omniCoeStartup()
{
    if (omniTestMode()) return;
    omniCoeLoad();
    const OCOE::Settings s = omniCoeSet;
    if (!OCOE::any(s)) return;
    WKWebsiteDataStoreRef store = websiteDataStore.get();
    auto* j = new OmniCoeJob;
    j->gen = ++omniCoeGen;
    j->startedAt = SDL_GetTicks();
    j->pending = 1;   // held until everything below has been started
    j->store = store;
    j->keep = s.keep;
    j->res.keepCount = s.keep.size();
    omniCoeJob = j;
    // The cookie hosts first: history is one of their sources and may be cleared below.
    OCOE::Plan plan;
    if (s.cookies && !s.keep.empty()) {
        std::vector<std::string> candidates;
        size_t reserved = 0;
        const std::string db = omniCoeReadFile(OCOE::kCookieDb);
        const bool dbOk = OCOE::dbDomains(db, candidates, &reserved);
        const size_t fromDb = candidates.size();
        OCOE::walDomains(omniCoeReadFile(std::string(OCOE::kCookieDb) + "-wal"), reserved, candidates);
        const size_t fromWal = candidates.size() - fromDb;
        omniHistoryLoad();
        for (size_t i = omniHistory.size(); i-- > 0;) candidates.push_back(omniHistory[i].url);
        plan = OCOE::plan(candidates, s.keep);
        fprintf(stderr, "OMNI CLEAR ON EXIT: Cookies.db %zu bytes%s, %zu domain values (+%zu from the WAL), %zu history visits: "
                "%zu hosts to clear, %zu covered by %zu kept sites, %zu over the limit\n", db.size(), dbOk ? "" : " (not read)",
                fromDb, fromWal, omniHistory.size(), plan.hosts.size(), plan.keptSkipped, s.keep.size(), plan.more); fflush(stderr);
    }
    // 1. history: done now
    if (s.history) {
        omniHistoryLoad();
        j->res.history = true;
        j->res.visits = omniHistory.size();
        if (!omniHistory.empty()) {
            omniHistory.clear();
            omniHpChanged();   // history.txt rewrite on the writer thread, suggestions, most visited
        }
    }
    // 2. cookies and site data
    if (s.cookies && store) {
        j->res.cookies = true;
        if (s.keep.empty()) {
            j->res.cookiesAll = true;
            j->pending += 5; j->cookieCalls += 5;
            WKHTTPCookieStoreDeleteAllCookies(WKWebsiteDataStoreGetHTTPCookieStore(store), j, omniCoeCookieBack);
            WKWebsiteDataStoreRemoveLocalStorage(store, j, omniCoeCookieBack);
            WKWebsiteDataStoreRemoveAllIndexedDatabases(store, j, omniCoeCookieBack);
            WKWebsiteDataStoreRemoveAllServiceWorkerRegistrations(store, j, omniCoeCookieBack);
            WKWebsiteDataStoreRemoveAllFetchCaches(store, j, omniCoeCookieBack);
        } else {
            j->res.sites = plan.hosts.size();
            j->res.more = plan.more;
            for (const std::string& h : plan.hosts) {   // the host's whole registrable domain, HttpOnly included
                ++j->pending; ++j->cookieCalls;
                auto u = adoptWK(WKStringCreateWithUTF8CString(("https://" + h + "/").c_str()));
                WKWebsiteDataStoreStatisticsDeleteCookiesForTesting(store, u.get(), true, j, omniCoeCookieBack);
            }
            ++j->pending;   // CacheStorage: every origin but the kept sites'
            j->originsListed = false;
            WKWebsiteDataStoreGetFetchCacheOrigins(store, j, [](WKArrayRef origins, void* ctx) {
                OmniCoeJob* job = static_cast<OmniCoeJob*>(ctx);
                if (omniCoeLive(job)) {
                    job->originsListed = true;
                    const size_t n = origins ? WKArrayGetSize(origins) : 0;
                    for (size_t i = 0; i < n; ++i) {
                        WKSecurityOriginRef o = static_cast<WKSecurityOriginRef>(WKArrayGetItemAtIndex(origins, i));
                        if (!OCOE::removeCacheOrigin(omniOriginHost(o), job->keep)) continue;
                        ++job->pending; ++job->cookieCalls;
                        WKWebsiteDataStoreRemoveFetchCacheForOrigin(job->store.get(), o, job, omniCoeCookieBack);
                    }
                }
                omniCoeBack(job);
            });
        }
    }
    // 3. cached files: the whole HTTP cache
    if (s.cache && store) {
        j->res.cache = true;
        j->pending += 2; j->cacheCalls += 2;
        WKWebsiteDataStoreRemoveNetworkCache(store, j, omniCoeCacheBack);
        WKWebsiteDataStoreRemoveMemoryCaches(store, j, omniCoeCacheBack);
    }
    fprintf(stderr, "OMNI CLEAR ON EXIT: start-up clear started (cookies %s, history %s, cache %s)\n", OCOE::onOff(s.cookies),
            OCOE::onOff(s.history), OCOE::onOff(s.cache)); fflush(stderr);
    omniCoeBack(j);
}

// --- the "Clear on exit" page --------------------------------------------------------------------------------------------
// The active tab's host when it is a web page in a normal tab ("" otherwise).
static std::string omniCoeCurrentHost()
{
    Tab* t = active();
    if (!t || t->omniPrivate || !omniWebURL(t->url)) return std::string();
    return OCOE::hostKey(t->url);
}
static void omniCoeBuild(OmniFxPanel& p)
{
    omniCoeLoad();
    const OCOE::Settings& s = omniCoeSet;
    p.subtitle = OCOE::subtitle();
    auto row = [&](int id, std::string label, std::string value, std::string detail, bool stepper, bool enabled) {
        OmniFxRow r; r.id = id; r.label = std::move(label); r.value = std::move(value); r.detail = std::move(detail);
        r.stepper = stepper; r.enabled = enabled;
        p.rows.push_back(r);
    };
    row(OCOE::kRowCookies, "Cookies and site data", OCOE::onOff(s.cookies), OCOE::cookiesDetail(s), true, true);
    row(OCOE::kRowHistory, "History", OCOE::onOff(s.history), OCOE::historyDetail(), true, true);
    row(OCOE::kRowCache, "Cached files", OCOE::onOff(s.cache), OCOE::cacheDetail(), true, true);
    const std::string cur = omniCoeCurrentHost();
    const bool curKept = !cur.empty() && OCOE::keptBy(cur, s.keep) >= 0;
    row(OCOE::kRowAddCurrent, "Keep cookies for this site", cur.empty() ? std::string("-") : curKept ? OCOE::siteValue(cur, false, s.keep) : cur,
        cur.empty() ? std::string("Open a site in a normal tab to add it") : std::string(), false,
        !cur.empty() && !curKept && s.keep.size() < OCOE::kMaxKeep);
    if (s.keep.empty()) row(OCOE::kRowNone, OCOE::noneLabel(), std::string(), OCOE::noneDetail(), false, false);
    for (size_t i = 0; i < s.keep.size(); ++i) row(OCOE::kRowSite0 + int(i), s.keep[i], "Remove", OCOE::keptDetail(), false, true);
}
static void omniCoeTurnOn(int rowId)
{
    omniCoeLoad();
    if (rowId == OCOE::kRowCookies) omniCoeSet.cookies = true;
    else if (rowId == OCOE::kRowHistory) omniCoeSet.history = true;
    omniCoeSave();
    omniFxRefresh();
}
static bool omniCoeInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    const bool left = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT, right = b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT, a = b == SDL_CONTROLLER_BUTTON_A;
    omniCoeLoad();
    OCOE::Settings& s = omniCoeSet;
    if (r.id == OCOE::kRowCookies || r.id == OCOE::kRowHistory || r.id == OCOE::kRowCache) {
        if (!left && !right && !a) return false;
        bool& on = r.id == OCOE::kRowCookies ? s.cookies : r.id == OCOE::kRowHistory ? s.history : s.cache;
        if (on || r.id == OCOE::kRowCache) {   // Off, and Cached files either way: no question
            on = !on;
            omniCoeSave();
            omniFxRefresh();
            return true;
        }
        const int id = r.id;
        if (id == OCOE::kRowCookies)
            omniAsk(OCOE::askCookiesTitle(), OCOE::askCookiesBody(s.keep.size()), OCOE::turnOnLabel(), [id](bool ok) { if (ok) omniCoeTurnOn(id); });
        else
            omniAsk(OCOE::askHistoryTitle(), OCOE::askHistoryBody(), OCOE::turnOnLabel(), [id](bool ok) { if (ok) omniCoeTurnOn(id); });
        return true;
    }
    if (r.id == OCOE::kRowAddCurrent) {
        if (!a) return false;
        if (!r.enabled) return true;
        const std::string cur = omniCoeCurrentHost();
        if (cur.empty()) return true;
        if (s.keep.size() >= OCOE::kMaxKeep) { notice(OCOE::fullNotice()); return true; }
        if (OCOE::addKeep(s, cur)) { omniCoeSave(); notice(OCOE::keptNotice(cur, true, s.cookies)); }
        omniFxRefresh();
        return true;
    }
    if (r.id >= OCOE::kRowSite0 && r.id < OCOE::kRowSite0 + int(OCOE::kMaxKeep)) {
        if (!a) return false;
        const size_t i = size_t(r.id - OCOE::kRowSite0);
        if (i >= s.keep.size()) return true;
        const std::string host = s.keep[i];
        OCOE::removeExact(s, host);
        omniCoeSave();
        notice(OCOE::keptNotice(host, false, s.cookies));
        omniFxRefresh();
        return true;
    }
    return r.id == OCOE::kRowNone && a;
}
static void omniCoeShow()
{
    OmniFxPanel p;
    p.kind = OCOE::kPanelKind;
    p.title = "Clear on exit";
    p.w = 900; p.maxVisible = 8;
    p.build = omniCoeBuild; p.input = omniCoeInput;
    p.faces = { { 0, "Change" }, { 1, "Back" } };
    p.extra = "D-pad \xe2\x97\x80 \xe2\x96\xb6 change";
    omniFxPush(std::move(p));
}

// --- Browser settings > Clear on exit... ---------------------------------------------------------------------------------
static void omniCoeSettingsRow(OmniFxPanel& p)
{
    omniCoeLoad();
    OmniFxRow r;
    r.id = omniCoeRowId; r.label = "Clear on exit..."; r.value = OCOE::settingsValue(omniCoeSet); r.detail = OCOE::settingsDetail(omniCoeSet);
    p.rows.push_back(r);
}
static bool omniCoeSettingsInput(int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    omniCoeShow();
    return true;
}

// --- Site settings > Keep cookies on exit --------------------------------------------------------------------------------
static void omniCoeSiteRow(OmniFxPanel& p, const std::string&)
{
    omniCoeLoad();
    Tab* t = active();
    const bool priv = t && t->omniPrivate;
    const std::string host = t && omniWebURL(t->url) ? OCOE::hostKey(t->url) : std::string();
    OmniFxRow r; r.id = omniCoeSiteRowId; r.label = "Keep cookies on exit"; r.stepper = true;
    r.value = OCOE::siteValue(host, priv && !host.empty(), omniCoeSet.keep);
    r.enabled = !host.empty() && !priv;
    p.rows.push_back(r);
}
static bool omniCoeSiteInput(const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A && b != SDL_CONTROLLER_BUTTON_DPAD_LEFT && b != SDL_CONTROLLER_BUTTON_DPAD_RIGHT) return false;
    Tab* t = active();
    if (!r.enabled || !t || t->omniPrivate || !omniWebURL(t->url)) return true;
    omniCoeLoad();
    const std::string host = OCOE::hostKey(t->url);
    if (host.empty()) return true;
    if (OCOE::keptBy(host, omniCoeSet.keep) >= 0) {
        const std::vector<std::string> gone = OCOE::removeRelated(omniCoeSet, host);
        omniCoeSave();
        std::string names;
        for (size_t i = 0; i < gone.size(); ++i) names += (i ? ", " : "") + gone[i];
        notice(OCOE::keptNotice(names.empty() ? host : names, false, omniCoeSet.cookies));
    } else if (omniCoeSet.keep.size() >= OCOE::kMaxKeep) {
        notice(OCOE::fullNotice());
    } else if (OCOE::addKeep(omniCoeSet, host)) {
        omniCoeSave();
        notice(OCOE::keptNotice(host, true, omniCoeSet.cookies));
    }
    omniFxRefresh();
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniClearRange.h" /* OMNI_CLEAR_RANGE_V1: Clear browsing data by time range and category (pure) */\n',
         '#include "OmniClearRange.h" /* OMNI_CLEAR_RANGE_V1: Clear browsing data by time range and category (pure) */\n'
         '#include "OmniClearOnExit.h" /* OMNI_CLEAR_ON_EXIT_V1: Clear on exit, done at the next start (pure) */\n'),
        ('    WKContextSetPrimaryWebsiteDataStore(context.get(), websiteDataStore.get());\n',
         '    WKContextSetPrimaryWebsiteDataStore(context.get(), websiteDataStore.get());\n'
         '    omniCoeStartup(); /* OMNI_CLEAR_ON_EXIT_V1: the last session\'s data goes now, before any page exists (exit may never run) */\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniSiteClearShell.h" // OMNI_SITE_CLEAR_V1\n',
         '#include "OmniSiteClearShell.h" // OMNI_SITE_CLEAR_V1\n'
         '#include "OmniClearOnExitShell.h" /* OMNI_CLEAR_ON_EXIT_V1 (before OmniSiteListShell.h, which may list kept sites) */\n'),
        ('    omniHkTick(now);    /* OMNI_HISTORY_KEEP_V1: startup + hourly history prune */\n',
         '    omniHkTick(now);    /* OMNI_HISTORY_KEEP_V1: startup + hourly history prune */\n'
         '    omniCoeTick(now);   /* OMNI_CLEAR_ON_EXIT_V1: native timeout of the start-up clear */\n'),
    ],
    'OmniBrowserSettings.h': [
        ('constexpr int omniHkRowId = 897; /* OMNI_HISTORY_KEEP_V1 (OmniHistoryKeepShell.h) */\n',
         'constexpr int omniHkRowId = 897; /* OMNI_HISTORY_KEEP_V1 (OmniHistoryKeepShell.h) */\n'
         'constexpr int omniCoeRowId = 8733; /* OMNI_CLEAR_ON_EXIT_V1: "Clear on exit..." (OmniClearOnExitShell.h) */\n'
         'static void omniCoeSettingsRow(OmniFxPanel& p);\n'
         'static bool omniCoeSettingsInput(int b);\n'),
        ('    omniHkSettingsRow(p); /* OMNI_HISTORY_KEEP_V1: Keep history */\n',
         '    omniHkSettingsRow(p); /* OMNI_HISTORY_KEEP_V1: Keep history */\n'
         '    omniCoeSettingsRow(p); /* OMNI_CLEAR_ON_EXIT_V1: Clear on exit... */\n'),
        ('    if (r.id == omniHkRowId) return omniHkSettingsInput(b); /* OMNI_HISTORY_KEEP_V1 (before the >= 300 rows) */\n',
         '    if (r.id == omniCoeRowId) return omniCoeSettingsInput(b); /* OMNI_CLEAR_ON_EXIT_V1 (before the >= 300 rows) */\n'
         '    if (r.id == omniHkRowId) return omniHkSettingsInput(b); /* OMNI_HISTORY_KEEP_V1 (before the >= 300 rows) */\n'),
    ],
    'OmniQuickMenu.h': [
        ('static bool omniScSiteInput(const OmniFxRow& r, int b);\n',
         'static bool omniScSiteInput(const OmniFxRow& r, int b);\n'
         'constexpr int omniCoeSiteRowId = 735; /* OMNI_CLEAR_ON_EXIT_V1: "Keep cookies on exit" (OmniClearOnExitShell.h) */\n'
         'static void omniCoeSiteRow(OmniFxPanel& p, const std::string& host);\n'
         'static bool omniCoeSiteInput(const OmniFxRow& r, int b);\n'),
        ('    omniScSiteRow(p, host); // OMNI_SITE_CLEAR_V1: Clear data for this site\n',
         '    omniScSiteRow(p, host); // OMNI_SITE_CLEAR_V1: Clear data for this site\n'
         '    omniCoeSiteRow(p, host); /* OMNI_CLEAR_ON_EXIT_V1: Keep cookies on exit */\n'),
        ('    if (r.id == omniScSiteRowId) return omniScSiteInput(r, b); // OMNI_SITE_CLEAR_V1 (handles its disabled state)\n',
         '    if (r.id == omniCoeSiteRowId) return omniCoeSiteInput(r, b); /* OMNI_CLEAR_ON_EXIT_V1 (handles its disabled state) */\n'
         '    if (r.id == omniScSiteRowId) return omniScSiteInput(r, b); // OMNI_SITE_CLEAR_V1 (handles its disabled state)\n'),
    ],
}
NEEDS = {'OmniBrowser.cpp': ('OMNI_CLEAR_RANGE_V1', 'OMNI_HISTORY_KEEP_V1'),
         'OmniFeatures3.h': ('OMNI_SITE_CLEAR_V1', 'OMNI_HISTORY_KEEP_V1'),
         'OmniBrowserSettings.h': ('OMNI_HISTORY_KEEP_V1',),
         'OmniQuickMenu.h': ('OMNI_SITE_CLEAR_V1',)}


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
    data = text.replace('\r\n', '\n').replace('\n', nl).encode('utf-8')
    h = root / name
    if h.exists() and h.read_bytes() == data:
        return name + ': already'
    h.write_bytes(data)
    return name + ': written'


# The Controls guide's table names other patches' handlers by design: never a name clash (numbers still count there).
GUIDE = ('OmniControlsHelp.h', 'OmniControlsHelpShell.h')
_CPP_TOK = re.compile(r'//[^\n]*|/\*.*?\*/|R"([^()\\\s"]{0,16})\(.*?\)\1"|"(?:\\.|[^"\\\n])*"' + r"|'(?:\\.|[^'\\\n])*'", re.S)


def cpp_code(s):
    """C/C++ text without its // and /* */ comments (string, char and raw string literals kept; newlines kept, so line
    numbers stay): an id or name in another patch's notes (e.g. "834-839" in a generated header) is not a use."""
    return _CPP_TOK.sub(lambda m: m.group(0) if m.group(0)[0] in 'R"\'' else '\n' * m.group(0).count('\n'), s)


def code_only(src):
    """A sibling apply_*.py without its comments and module docstring (line numbers kept): names mentioned only in its
    notes are not a use. Numeric ids are never looked for in siblings (their notes list other patches' id ranges)."""
    import io
    import tokenize
    cut, first = [], True
    try:
        for t in tokenize.generate_tokens(io.StringIO(src).readline):
            if t.type == tokenize.COMMENT or (first and t.type == tokenize.STRING):
                cut.append((t.start, t.end))
            if t.type not in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT,
                              tokenize.ENCODING):
                first = False
    except (tokenize.TokenError, SyntaxError):
        return ''.join(r for r in src.splitlines(True) if not r.lstrip().startswith('#'))
    starts = [0] + [i + 1 for i, c in enumerate(src) if c == '\n']   # tokenize's rows end at '\n' only
    out = list(src)
    for (r0, c0), (r1, c1) in cut:
        for i in range(starts[r0 - 1] + c0, starts[r1 - 1] + c1):
            if out[i] not in '\r\n':
                out[i] = ' '
    return ''.join(out)


def ids_free():
    """Before a first apply: no other patch or tree file uses this patch's ids or names."""
    word = re.compile(r'\b(%s)\b' % '|'.join(IDS))
    name = re.compile('|'.join(NAMES))
    mine = {'OmniClearOnExit.h', 'OmniClearOnExitShell.h'}
    for f in sorted(HERE.glob('apply_*.py')):
        if f.name == Path(__file__).name:
            continue
        if f.name == 'apply_controls_help.py' or MARK in f.read_text(encoding='utf-8', errors='replace'):   # OMNI_SIBLING_SKIP: the guide quotes names; a patch built on this one uses them
            continue
        t = code_only(f.read_text(encoding='utf-8', errors='replace'))
        m = name.search(t)   # numeric ids: engine tree only (a sibling's notes list other patches' ids)
        if m:
            sys.exit('%s already uses %r: pick other ids / names' % (f.name, m.group(0)))
    for f in sorted(root.iterdir()):
        if f.name in mine or f.suffix not in ('.h', '.cpp', '.inc'):
            continue
        t = f.read_bytes().decode('utf-8', errors='replace')
        c = cpp_code(t)
        m = word.search(c) or (None if f.name in GUIDE else name.search(c))
        if m and MARK not in t:
            sys.exit('%s already uses %r: pick other ids / names' % (f.name, m.group(0)))


def main():
    for fname, needs in NEEDS.items():
        s = (root / fname).read_bytes().decode('utf-8')
        for need in needs:
            if need not in s:
                sys.exit('%s: %s missing: apply its patch first' % (fname, need))
    if MARK not in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8'):
        ids_free()
    for fname, edits in EDITS.items():   # every anchor is checked before anything is written
        check(fname, edits)
    pure = (HERE / 'OmniClearOnExit.h').read_text(encoding='utf-8')
    if MARK not in pure:
        sys.exit('OmniClearOnExit.h: %s missing' % MARK)
    msgs = [write_new('OmniClearOnExit.h', pure, 'OmniHistoryKeep.h'),
            write_new('OmniClearOnExitShell.h', SHELL, 'OmniHistoryKeepShell.h')]
    msgs += [patch(fname, edits) for fname, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
