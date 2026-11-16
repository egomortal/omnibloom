#!/usr/bin/env python3
"""OMNI_SITE_CLEAR_V1 (2026-11-16): Site settings > "Clear data for this site".

What the user sees
  - Site settings (Options > Site settings) has a new row after "HTTPS-only on this site":
        "Clear data for this site"    value: the page's host (www.example.com), "Clearing..." while busy, "-" on
                                      omni:// / about: / new-tab pages (row disabled there)
    Cross asks once (the shell's own modal, Cancel focused):
        "Clear cookies and site data for www.example.com?"
        "You may be signed out. Cookies for www.example.com (and its parent site) are deleted, and this page's
         storage (https://www.example.com) too; other addresses keep their storage. The page reloads afterwards."
        (+ "Private tab: only this private session is affected." in a private tab)
      The host is named because that is what is certain: WebKit widens the cookie deletion to the host's registrable
      domain by libpsl (www.example.com -> example.com and all its subdomains; alice.github.io -> alice.github.io
      only, github.io being a public suffix), which the pure part can't compute exactly.
    "Clear": the menus close, "Clearing site data..." shows, then a summary such as
        "Cleared www.example.com: cookies, 3 stored items, 1 database. Reloading"
        "... Not cleared: 1 database in use. Reloading"
        "... Not cleared: page storage (the page didn't answer in time). Reloading"   (native timeout, below)
    and the tab reloads. Private tabs work the same way: everything goes through the page's own data store
    (WKPageGetWebsiteDataStore), which for a private tab is omniPrivateStore (non-persistent).

What WebKit's C API offers here (checked in /home/builder/s1/webkit + the UIProcess unified object of the build):
  per site / origin, real implementations, exported:
    WKWebsiteDataStoreStatisticsDeleteCookiesForTesting(store, url, includeHttpOnly, ...)
        -> NetworkProcess::deleteCookiesForTesting -> deleteAndRestrictWebsiteDataForRegistrableDomains(Cookies):
           every cookie host whose registrable domain (libpsl, leading dots skipped) equals the URL's is deleted
           with IncludeHttpOnlyCookies::Yes (Curl: CookieJarDB "DELETE FROM Cookie WHERE domain = ?"). Not gated
           by any ENABLE() in NetworkProcess.messages.in; works for any session (private too). "ForTesting" is
           only its name. So HttpOnly (sign-in) cookies ARE cleared, for www. and bare and every subdomain.
    WKWebsiteDataStoreGetFetchCacheOrigins + WKWebsiteDataStoreRemoveFetchCacheForOrigin   (CacheStorage)
    WKWebsiteDataStoreRemoveITPDataForDomain                                              (tracking-prevention
        statistics for the domain; harmless when ITP is off)
  only ALL origins: WKWebsiteDataStoreRemoveLocalStorage / RemoveAllIndexedDatabases /
    RemoveAllServiceWorkerRegistrations / RemoveNetworkCache / RemoveMemoryCaches, WKHTTPCookieStoreDeleteAllCookies.
  stubs (empty bodies in this WebKit): WKCookieManagerDeleteCookiesForHostname,
    WKKeyValueStorageManagerDeleteEntriesForOrigin, WKResourceCacheManagerClearCacheForOrigin (deprecated).
  WKHTTPCookieStoreDeleteCookie / WKWebsiteDataStoreRemoveDataOfTypes do not exist in this tree.
  So localStorage, sessionStorage, IndexedDB, service workers (and CacheStorage again, and the page's non-HttpOnly
  cookies as a second pass) are cleared by a script in the page itself (WKPageCallAsyncJavaScriptWithoutUserGesture,
  an async function body; 2.5 s per step, 6 s overall, then it answers anyway). That reaches only the page's own
  origin: on https://www.example.com the storage of https://example.com stays (the ask says so). The HTTP cache
  is not touched (only an all-sites API exists; it holds no sign-in state).

  CacheStorage through WebKit is removed only for origins whose host is the page's host or its www. / bare twin
  (any scheme / port): never by the heuristic site (that wiped every *.github.io / *.netlify.app / *.blogspot.com /
  *.herokuapp.com origin, and k12.ca.us pages took all of ca.us).

Order: on "Clear" the cookie / CacheStorage / ITP calls and the page script start together; when every callback
has come back (main thread, a pending counter in OmniScJob) the summary notice is shown and the tab reloads (if it
still exists). The script only runs when the tab still shows the same origin as when the question was asked.
One clear at a time.
Native timeout (r2): the page script's own timers can't be trusted (a page may replace setTimeout / Promise.race
before it runs, hang, or the tab may close). omniScTick (called from omniF3Tick every pass) finishes the job
OmniSiteClear::kNativeMs (10 s) after it started: the summary says what had come back (cookies / caches /
page storage "no answer in time"), the tab reloads, a new clear can start. The OmniScJob stays allocated (its page
and store retains released) until each WebKit callback it handed out has returned; a callback for a finished job
(an older generation, omniScGen) only counts down and touches nothing else. The page script also takes its own
copies of Promise / setTimeout first (helps against replacements made while it runs; the native timeout is the fix).

Pure part: engine/entry/OmniSiteClear.h (no SDL / WebKit): URL -> target (host, site, origin), the heuristic site
(only the page script's cookie-domain walk uses it), www. twin, CacheStorage origin match, cookie URLs, JS string
escaping, the page script, its answer, the native-timeout check, the summary / question texts.
Tested by tools/test_site_clear.cpp:  g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_site_clear.cpp -o t && ./t
(it also writes the script to argv[1] when given, so node can check it: tools/test_site_clear_js.mjs).
Shell side: engine/entry/OmniSiteClearShell.h (included from OmniFeatures3.h after OmniHttpsOnlyShell.h).

Anchors (exactly once each; MARK makes each file idempotent, REV the r2 edits):
  OmniBrowser.cpp     the OmniHttpsOnly.h include line (apply_https_only.py's): pure include + WKArray / WKDictionary.
  OmniQuickMenu.h     the omniHoSiteInput declaration, the omniHoSiteRow call, the omniHoSiteRowId input line
                      (all apply_https_only.py's).
  OmniFeatures3.h     the OmniHttpsOnlyShell.h include line; r2: the omniTaTick line of omniF3Tick (apply_tab_audio.py's)
                      (omniScTick goes after it).
Upgrading: a tree patched by r1 gets the new headers (always rewritten when they differ) and only the r2 edits;
the result is byte-identical to a fresh apply.
Apply AFTER apply_https_only.py and apply_tab_audio.py (their lines are anchors).
usage: apply_site_clear.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_SITE_CLEAR_V1'
REV = 'OMNI_SITE_CLEAR_V1_R2'   # r2: native timeout (omniScTick), exact-host CacheStorage filter, host-named texts
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_SITE_CLEAR_V1: the pure part of Site settings > "Clear data for this site" (no SDL, no WebKit).
// The shell side is OmniSiteClearShell.h; the reasons are in tools/apply_site_clear.py. Tested on the host with g++
// (test_site_clear.cpp).
// OMNI_SITE_CLEAR_V1_R2: native 10 s timeout (expired / Native), exact-host CacheStorage filter, texts name the host.
#pragma once
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace OmniSiteClear {

constexpr size_t kHostMax = 253;
constexpr int kStepMs = 2500, kScriptMs = 6000;   // page script: per step, overall
constexpr uint32_t kNativeMs = 10000;             // the shell finishes the job after this, whatever is still out
constexpr const char* kAnswerTag = "omni-site-clear";

// SDL_GetTicks() style milliseconds (wrap-safe).
inline bool expired(uint32_t startedAt, uint32_t now) { return uint32_t(now - startedAt) >= kNativeMs; }

inline char lower(char c) { return c >= 'A' && c <= 'Z' ? char(c + ('a' - 'A')) : c; }
inline bool startsWithNoCase(const std::string& s, const char* p)
{
    size_t i = 0;
    for (; p[i]; ++i) if (i >= s.size() || lower(s[i]) != p[i]) return false;
    return true;
}
inline bool endsWith(const std::string& s, const std::string& tail)
{
    return s.size() >= tail.size() && s.compare(s.size() - tail.size(), tail.size(), tail) == 0;
}

// --- hosts -------------------------------------------------------------------------------------------------------
inline bool isIPv4(const std::string& h)
{
    int parts = 0, digits = 0, value = 0;
    for (size_t i = 0; i <= h.size(); ++i) {
        if (i == h.size() || h[i] == '.') {
            if (!digits || value > 255) return false;
            ++parts; digits = 0; value = 0;
            continue;
        }
        if (h[i] < '0' || h[i] > '9' || ++digits > 3) return false;
        value = value * 10 + (h[i] - '0');
    }
    return parts == 4;
}
inline bool isIPLiteral(const std::string& h) { return isIPv4(h) || h.find(':') != std::string::npos; }

// The highest parent domain the page script tries when it expires the page's own (visible) cookies by name.
// A heuristic only ("www." dropped, the last two labels, three for co.uk-style ccTLD second levels; IP literals and
// one-label hosts stay): it can name a public suffix (alice.github.io -> github.io, school.k12.ca.us -> ca.us), so it
// is used for nothing else. A cookie write for a public suffix is rejected by WebKit, and a name the page cannot see
// is never touched. WebKit's own cookie deletion (libpsl, private section included) and the CacheStorage filter
// (cacheOriginMatches: exact host + its www. twin) do not use it.
inline std::string siteOf(const std::string& host0)
{
    std::string host;
    for (char c : host0) host += lower(c);
    while (!host.empty() && host.back() == '.') host.pop_back();
    if (host.empty() || isIPLiteral(host)) return host;
    std::vector<std::string> labels;
    size_t start = 0;
    while (true) {
        const size_t dot = host.find('.', start);
        labels.push_back(host.substr(start, dot == std::string::npos ? std::string::npos : dot - start));
        if (dot == std::string::npos) break;
        start = dot + 1;
    }
    for (const auto& l : labels) if (l.empty()) return host;   // "a..b": leave it alone
    if (labels.size() <= 2) return host;
    static const char* const kSecond[] = { "co", "com", "net", "org", "gov", "edu", "ac", "or", "ne", "go", "gob",
                                           "mil", "nom", "ltd", "plc", "sch", "gv", "lg" };
    size_t keep = 2;
    const std::string& tld = labels[labels.size() - 1];
    const std::string& sld = labels[labels.size() - 2];
    if (tld.size() == 2)
        for (const char* s : kSecond) if (sld == s) { keep = 3; break; }
    if (labels.size() <= keep) return host;
    std::string site;
    for (size_t i = labels.size() - keep; i < labels.size(); ++i) site += (site.empty() ? "" : ".") + labels[i];
    return site;
}
// host is the site or one of its subdomains (both lower case).
inline bool sameSite(const std::string& host, const std::string& site)
{
    if (host.empty() || site.empty()) return false;
    return host == site || (host.size() > site.size() && endsWith(host, "." + site));
}
// "www.example.com" <-> "example.com"; "" for IP literals and one-label hosts.
inline std::string wwwTwin(const std::string& host)
{
    if (host.empty() || isIPLiteral(host)) return std::string();
    if (host.compare(0, 4, "www.") == 0) return host.size() > 4 && host.find('.', 4) != std::string::npos ? host.substr(4) : std::string();
    return host.find('.') != std::string::npos ? "www." + host : std::string();
}

// --- the page --------------------------------------------------------------------------------------------------
struct Target {
    bool ok = false, https = false;
    std::string host;     // lower case, IPv6 without brackets, no trailing dot
    std::string site;     // siteOf(host)
    std::string origin;   // "https://www.example.com" (port only when not the default)
};
inline Target target(const std::string& url)
{
    Target t;
    size_t p;
    if (startsWithNoCase(url, "https://")) { t.https = true; p = 8; }
    else if (startsWithNoCase(url, "http://")) p = 7;
    else return t;
    size_t end = url.find_first_of("/?#", p);
    if (end == std::string::npos) end = url.size();
    const size_t at = url.rfind('@', end ? end - 1 : 0);
    if (at != std::string::npos && at >= p && at < end) p = at + 1;
    std::string host, port;
    bool v6 = false;
    if (p < end && url[p] == '[') {
        const size_t close = url.find(']', p);
        if (close == std::string::npos || close >= end) return t;
        host = url.substr(p + 1, close - p - 1);
        v6 = true;
        if (close + 1 < end) { if (url[close + 1] != ':') return t; port = url.substr(close + 2, end - close - 2); }
    } else {
        const size_t colon = url.find(':', p);
        if (colon != std::string::npos && colon < end) { host = url.substr(p, colon - p); port = url.substr(colon + 1, end - colon - 1); }
        else host = url.substr(p, end - p);
    }
    for (auto& c : host) c = lower(c);
    while (!host.empty() && host.back() == '.') host.pop_back();
    if (host.empty() || host.size() > kHostMax) return t;
    for (char c : host) {
        const bool ok = (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '.' || c == '-' || c == '_' || (v6 && c == ':');
        if (!ok) return t;
    }
    if (!v6 && host.find(':') != std::string::npos) return t;
    if (port.size() > 5) return t;
    int portValue = -1;
    if (!port.empty()) {
        portValue = 0;
        for (char c : port) { if (c < '0' || c > '9') return t; portValue = portValue * 10 + (c - '0'); }
        if (portValue > 65535) return t;
    }
    t.host = host;
    t.site = siteOf(host);
    t.origin = std::string(t.https ? "https://" : "http://") + (v6 ? "[" + host + "]" : host);
    if (portValue >= 0 && portValue != (t.https ? 443 : 80)) t.origin += ":" + std::to_string(portValue);
    t.ok = true;
    return t;
}
// URLs for WKWebsiteDataStoreStatisticsDeleteCookiesForTesting: it takes a URL (a bare host is an invalid URL,
// which would name no domain) and deletes the cookies of every host whose registrable domain (libpsl, private
// section included: alice.github.io is its own site) equals the URL's. Only the page's own host: WebKit draws the
// site line itself (www.example.com -> example.com and its subdomains; alice.github.io -> alice.github.io only).
inline std::vector<std::string> cookieUrls(const Target& t)
{
    std::vector<std::string> out;
    if (!t.ok) return out;
    const bool v6 = t.host.find(':') != std::string::npos;
    out.push_back("https://" + (v6 ? "[" + t.host + "]" : t.host) + "/");
    return out;
}
// A CacheStorage origin (WKWebsiteDataStoreGetFetchCacheOrigins) to remove: the page's exact host or its www. / bare
// twin, any scheme / port. Never other subdomains or the heuristic site (that would wipe every *.github.io,
// *.netlify.app, *.blogspot.com, *.herokuapp.com origin).
inline bool cacheOriginMatches(const std::string& originHost, const Target& t)
{
    if (!t.ok) return false;
    std::string h;
    for (char c : originHost) h += lower(c);
    if (h.size() > 2 && h.front() == '[' && h.back() == ']') h = h.substr(1, h.size() - 2);
    while (!h.empty() && h.back() == '.') h.pop_back();
    if (h.empty()) return false;
    if (h == t.host) return true;
    const std::string twin = wwwTwin(t.host);
    return !twin.empty() && h == twin;
}

// --- the page script ---------------------------------------------------------------------------------------------
// A JavaScript string literal (double quotes) that is also safe inside an HTML <script>.
inline std::string jsString(const std::string& s)
{
    static const char* const hex = "0123456789abcdef";
    std::string out = "\"";
    for (size_t i = 0; i < s.size(); ++i) {
        const unsigned char c = static_cast<unsigned char>(s[i]);
        if (c == '"') out += "\\\"";
        else if (c == '\\') out += "\\\\";
        else if (c == '\n') out += "\\n";
        else if (c == '\r') out += "\\r";
        else if (c == '\t') out += "\\t";
        else if (c == '<' || c == '>' || c == '&' || c < 0x20 || c == 0x7f) { out += "\\u00"; out += hex[c >> 4]; out += hex[c & 15]; }
        else if (c == 0xe2 && i + 2 < s.size() && static_cast<unsigned char>(s[i + 1]) == 0x80
                 && (static_cast<unsigned char>(s[i + 2]) == 0xa8 || static_cast<unsigned char>(s[i + 2]) == 0xa9)) {
            out += static_cast<unsigned char>(s[i + 2]) == 0xa8 ? "\\u2028" : "\\u2029";   // line / paragraph separator
            i += 2;
        } else out += char(c);
    }
    return out + "\"";
}
// The body of an async function (WKPageCallAsyncJavaScript*): clears what the page's own origin holds and answers
// "omni-site-clear;ls=..;ss=..;ck=..;idb=..;idbb=..;idbf=..;cs=..;sw=..;to=..". -1: not available / not reached.
inline std::string clearScript(const std::string& site)
{
    std::string s = "const site = " + jsString(site) + ";\n";
    s += "const stepMs = " + std::to_string(kStepMs) + ", allMs = " + std::to_string(kScriptMs) + ";\n";
    // The page's Promise.race / setTimeout as they are now (a page replacing them later doesn't stop the timers).
    // A page that replaced them before this runs, or a hung page, is the shell's native timeout's job (kNativeMs).
    s += R"JS(const P = Promise, race = Promise.race.bind(Promise), all = Promise.all.bind(Promise), resolve = Promise.resolve.bind(Promise), later = setTimeout;
const out = { ls: -1, ss: -1, ck: -1, idb: -1, idbb: 0, idbf: 0, cs: -1, sw: -1, to: 0 };
const answer = () => "omni-site-clear;" + Object.keys(out).map(k => k + "=" + out[k]).join(";");
const wait = (p, fallback) => race([resolve(p).catch(() => fallback), new P(r => later(() => r(fallback), stepMs))]);
const work = async () => {
  try { out.ls = localStorage.length; localStorage.clear(); } catch (e) { out.ls = -1; }
  try { out.ss = sessionStorage.length; sessionStorage.clear(); } catch (e) { out.ss = -1; }
  try {
    const names = document.cookie.split(";").map(c => c.split("=")[0].trim()).filter(n => n.length > 0);
    const domains = [""];
    let d = location.hostname;
    while (d && (d === site || d.endsWith("." + site))) {
      domains.push(d);
      if (d === site) break;
      const i = d.indexOf(".");
      if (i < 0) break;
      d = d.slice(i + 1);
    }
    const paths = ["/"];
    let p = location.pathname;
    while (p.length > 1 && paths.length < 8) { paths.push(p); p = p.slice(0, p.lastIndexOf("/")); }
    for (const n of names) for (const dm of domains) for (const q of paths)
      document.cookie = n + "=; expires=Thu, 01 Jan 1970 00:00:00 GMT; max-age=0; path=" + q + (dm ? "; domain=" + dm : "");
    out.ck = names.length;
  } catch (e) {}
  try {
    if (window.indexedDB && typeof indexedDB.databases === "function") {
      const list = await wait(indexedDB.databases(), null);
      if (Array.isArray(list)) {
        out.idb = 0;
        await all(list.map(db => new P(res => {
          let blocked = false, done = false;
          const fin = ok => { if (done) return; done = true; if (ok) out.idb++; else if (blocked) out.idbb++; else out.idbf++; res(); };
          try {
            const rq = indexedDB.deleteDatabase(db.name);
            rq.onsuccess = () => fin(true);
            rq.onerror = () => fin(false);
            rq.onblocked = () => { blocked = true; };
          } catch (e) { fin(false); }
          later(() => fin(false), stepMs);
        })));
      }
    }
  } catch (e) {}
  try {
    if (window.caches && typeof caches.keys === "function") {
      const keys = await wait(caches.keys(), null);
      if (Array.isArray(keys)) {
        out.cs = 0;
        for (const ok of await all(keys.map(k => wait(caches.delete(k), false)))) if (ok) out.cs++;
      }
    }
  } catch (e) {}
  try {
    const sw = navigator.serviceWorker;
    if (sw && typeof sw.getRegistrations === "function") {
      const regs = await wait(sw.getRegistrations(), null);
      if (regs && typeof regs.length === "number") {
        out.sw = 0;
        for (const ok of await all(Array.from(regs).map(r => wait(r.unregister(), false)))) if (ok) out.sw++;
      }
    }
  } catch (e) {}
  return answer();
};
return await race([work(), new P(r => later(() => { out.to = 1; r(answer()); }, allMs))]);
)JS";
    return s;
}

struct Report {
    bool ok = false;                       // the page answered
    int ls = -1, ss = -1, ck = -1, idb = -1, idbBlocked = 0, idbFailed = 0, cs = -1, sw = -1;
    bool timedOut = false;
};
inline Report parseReport(const std::string& text)
{
    Report r;
    const std::string tag = std::string(kAnswerTag) + ";";
    if (text.compare(0, tag.size(), tag) != 0) return r;
    r.ok = true;
    size_t p = tag.size();
    while (p < text.size()) {
        size_t semi = text.find(';', p);
        if (semi == std::string::npos) semi = text.size();
        const std::string item = text.substr(p, semi - p);
        p = semi + 1;
        const size_t eq = item.find('=');
        if (eq == std::string::npos || eq + 1 >= item.size()) continue;
        const std::string key = item.substr(0, eq), val = item.substr(eq + 1);
        bool neg = false;
        size_t i = 0;
        if (val[0] == '-') { neg = true; i = 1; }
        if (i >= val.size() || val.size() - i > 7) continue;
        int v = 0;
        bool good = true;
        for (; i < val.size(); ++i) { if (val[i] < '0' || val[i] > '9') { good = false; break; } v = v * 10 + (val[i] - '0'); }
        if (!good) continue;
        if (neg) v = v ? -1 : 0;
        if (key == "ls") r.ls = v; else if (key == "ss") r.ss = v; else if (key == "ck") r.ck = v;
        else if (key == "idb") r.idb = v; else if (key == "idbb") r.idbBlocked = v < 0 ? 0 : v;
        else if (key == "idbf") r.idbFailed = v < 0 ? 0 : v; else if (key == "cs") r.cs = v;
        else if (key == "sw") r.sw = v; else if (key == "to") r.timedOut = v > 0;
    }
    return r;
}

// --- texts -------------------------------------------------------------------------------------------------------
// Everything names the page's host: that is what WebKit's cookie deletion starts from (it widens to the host's
// registrable domain, which the pure part cannot know exactly), and the page storage is the page's own origin.
inline std::string count(int n, const char* one, const char* many) { return std::to_string(n) + " " + (n == 1 ? one : many); }
inline std::string askTitle(const Target& t) { return "Clear cookies and site data for " + t.host + "?"; }
inline std::string askBody(const Target& t, bool privateTab)
{
    std::string s = "You may be signed out. Cookies for " + t.host + " (and its parent site) are deleted, and this page's storage ("
        + t.origin + ") too; other addresses keep their storage. The page reloads afterwards.";
    if (privateTab) s += " Private tab: only this private session is affected.";
    return s;
}
inline std::string rowValue(const Target& t, bool busy) { return busy ? std::string("Clearing...") : t.ok ? t.host : std::string("-"); }
inline std::string busyNotice() { return "Still clearing site data..."; }
inline std::string startNotice() { return "Clearing site data..."; }
// What the shell's own WebKit calls got back before the summary (all true when every callback returned in time).
struct Native {
    bool timedOut = false;   // kNativeMs passed: the summary was shown with whatever had come back
    bool cookies = true;     // every cookie deletion answered
    bool caches = true;      // the CacheStorage list came back and every removal answered
};
// scriptAsked: the page script was started (false: the tab had moved to another site meanwhile).
// cacheOrigins: CacheStorage origins of the host removed through WebKit.
inline std::string summary(const Target& t, const Report& r, bool scriptAsked, int cacheOrigins, bool privateTab, const Native& n = Native())
{
    std::vector<std::string> done, left;
    if (n.cookies) done.push_back("cookies");
    else left.push_back("cookies (no answer in time)");
    const int items = (r.ls > 0 ? r.ls : 0) + (r.ss > 0 ? r.ss : 0);
    if (items > 0) done.push_back(count(items, "stored item", "stored items"));
    if (r.idb > 0) done.push_back(count(r.idb, "database", "databases"));
    const int caches = r.cs > 0 ? r.cs : 0;
    if (caches > 0) done.push_back(count(caches, "cache", "caches"));
    else if (cacheOrigins > 0 && n.caches) done.push_back("caches");
    if (r.sw > 0) done.push_back(count(r.sw, "service worker", "service workers"));
    if (!n.caches) left.push_back("caches (no answer in time)");
    if (!scriptAsked) left.push_back("page storage (the tab shows another site)");
    else if (!r.ok) left.push_back(n.timedOut ? "page storage (the page didn't answer in time)" : "page storage (the page didn't answer)");
    else {
        if (r.idbBlocked > 0) left.push_back(count(r.idbBlocked, "database in use", "databases in use"));
        if (r.idbFailed > 0) left.push_back(count(r.idbFailed, "database", "databases"));
        if (r.timedOut) left.push_back("some storage (timed out)");
    }
    std::string s = privateTab ? "Private tab: " : "";
    if (done.empty()) s += std::string(privateTab ? "nothing" : "Nothing") + " confirmed cleared for " + t.host + ".";
    else {
        s += std::string(privateTab ? "cleared " : "Cleared ") + t.host + ": ";
        for (size_t i = 0; i < done.size(); ++i) s += (i ? ", " : "") + done[i];
        s += ".";
    }
    if (!left.empty()) {
        s += " Not cleared: ";
        for (size_t i = 0; i < left.size(); ++i) s += (i ? ", " : "") + left[i];
        s += ".";
    }
    return s + " Reloading";
}

} // namespace OmniSiteClear
'''

SHELL = r'''// OMNI_SITE_CLEAR_V1: Site settings > "Clear data for this site" (shell side). Included from OmniFeatures3.h
// (inside OmniBrowser.cpp's anonymous namespace, after OmniHttpsOnlyShell.h). The pure part is OmniSiteClear.h; the
// reasons (which WebKit calls exist and what they reach) are in tools/apply_site_clear.py. Main thread only.
// OMNI_SITE_CLEAR_V1_R2: a native timeout (omniScTick, from omniF3Tick) finishes a job after OSC::kNativeMs even
// when the page never answers (a page that replaced setTimeout / Promise.race, a hung page, a closed tab) or a
// WebKit callback is late. A job is freed only once every WebKit callback it handed out has come back; a callback
// for a finished job (an older generation) only counts itself down.
#pragma once

namespace OSC = OmniSiteClear;

struct OmniScJob {
    WKRetainPtr<WKPageRef> page;                   // the tab's page (released when the job finishes)
    WKRetainPtr<WKWebsiteDataStoreRef> store;      // its data store: omniPrivateStore for a private tab
    OSC::Target target;
    uint32_t gen = 0, startedAt = 0;               // generation (omniScGen when started), SDL_GetTicks() then
    bool priv = false, scriptAsked = false;
    bool finished = false;                         // the summary was shown; late callbacks are ignored
    std::string answer;                            // the page script's answer
    int pending = 0;                               // WebKit callbacks not back yet (+1 while starting)
    int cookieCalls = 0, cookieDone = 0;
    bool cacheListed = false;
    int cacheCalls = 0, cacheDone = 0;
};
static OmniScJob* omniScJob = nullptr;             // the running clear (one at a time); finished jobs are not here
static uint32_t omniScGen = 0;

static bool omniScLive(const OmniScJob* j) { return !j->finished && omniScJob == j && j->gen == omniScGen; }
static void omniScFinish(OmniScJob* j, bool timedOut)
{
    if (j->finished) return;
    j->finished = true;
    if (omniScJob == j) omniScJob = nullptr;
    OSC::Native n;
    n.timedOut = timedOut;
    n.cookies = j->cookieDone == j->cookieCalls;
    n.caches = j->cacheListed && j->cacheDone == j->cacheCalls;
    const OSC::Report r = OSC::parseReport(j->answer);
    notice(OSC::summary(j->target, r, j->scriptAsked, j->cacheDone, j->priv, n));
    fprintf(stderr, "OMNI SITE CLEAR: %s gen %u %s (script %s, cookies %d/%d, caches %d/%d%s, %d callbacks out)\n",
            j->target.host.c_str(), j->gen, timedOut ? "timed out" : "done", j->answer.empty() ? "-" : j->answer.c_str(),
            j->cookieDone, j->cookieCalls, j->cacheDone, j->cacheCalls, j->cacheListed ? "" : " unlisted", j->pending); fflush(stderr);
    if (Tab* t = omniTabForPage(j->page.get())) WKPageReload(t->page);
    j->page.clear();    // a closed tab's page is not kept alive by a late callback
    j->store.clear();
    omniShellDirty = true;
}
// Every WebKit callback ends here (once each). The last one frees the job.
static void omniScBack(OmniScJob* j)
{
    if (--j->pending > 0) return;
    if (!j->finished) omniScFinish(j, false);
    delete j;
}
static void omniScTick(uint32_t now)   // from omniF3Tick
{
    OmniScJob* j = omniScJob;
    if (!j || !OSC::expired(j->startedAt, now)) return;
    omniScFinish(j, true);   // stays allocated until its outstanding callbacks are back
}
static void omniScStart(WKPageRef page, const std::string& askedURL)
{
    if (omniScJob) { notice(OSC::busyNotice()); return; }
    Tab* t = omniTabForPage(page);
    const OSC::Target tg = OSC::target(askedURL);
    if (!t || !tg.ok) return;
    WKWebsiteDataStoreRef store = WKPageGetWebsiteDataStore(page);
    if (!store) { notice("Couldn't clear site data (no data store)"); return; }
    auto* j = new OmniScJob;
    j->page = page;
    j->store = store;
    j->target = tg;
    j->priv = t->omniPrivate;
    j->gen = ++omniScGen;
    j->startedAt = SDL_GetTicks();
    j->pending = 1;   // held until everything below has been started
    omniScJob = j;
    notice(OSC::startNotice());
    // 1. the page's own storage: only when the tab still shows the origin that was asked about
    const OSC::Target now = OSC::target(t->url);
    if (now.ok && now.origin == tg.origin && !t->crashed) {
        j->scriptAsked = true;
        ++j->pending;
        auto body = adoptWK(WKStringCreateWithUTF8CString(OSC::clearScript(tg.site).c_str()));
        auto args = adoptWK(WKDictionaryCreate(nullptr, nullptr, 0));   // an async function needs an argument list
        WKPageCallAsyncJavaScriptWithoutUserGesture(page, body.get(), args.get(), nullptr, j, [](WKTypeRef result, WKErrorRef error, void* ctx) {
            OmniScJob* job = static_cast<OmniScJob*>(ctx);
            if (omniScLive(job)) job->answer = omniFxResultString(result, error);
            omniScBack(job);
        });
    }
    // 2. cookies of the host's registrable domain (libpsl), HttpOnly included
    for (const std::string& u : OSC::cookieUrls(tg)) {
        ++j->pending;
        ++j->cookieCalls;
        auto s = adoptWK(WKStringCreateWithUTF8CString(u.c_str()));
        WKWebsiteDataStoreStatisticsDeleteCookiesForTesting(store, s.get(), true, j, [](void* ctx) {
            OmniScJob* job = static_cast<OmniScJob*>(ctx);
            if (omniScLive(job)) ++job->cookieDone;
            omniScBack(job);
        });
    }
    // 3. tracking-prevention statistics for the domain
    ++j->pending;
    auto host = adoptWK(WKStringCreateWithUTF8CString(tg.host.c_str()));
    WKWebsiteDataStoreRemoveITPDataForDomain(store, host.get(), j, [](void* ctx) { omniScBack(static_cast<OmniScJob*>(ctx)); });
    // 4. CacheStorage of the page's host and its www. / bare twin (any scheme / port), nothing wider
    ++j->pending;
    WKWebsiteDataStoreGetFetchCacheOrigins(store, j, [](WKArrayRef origins, void* ctx) {
        OmniScJob* job = static_cast<OmniScJob*>(ctx);
        if (omniScLive(job)) {
            job->cacheListed = true;
            const size_t n = origins ? WKArrayGetSize(origins) : 0;
            for (size_t i = 0; i < n; ++i) {
                WKSecurityOriginRef o = static_cast<WKSecurityOriginRef>(WKArrayGetItemAtIndex(origins, i));
                if (!OSC::cacheOriginMatches(omniOriginHost(o), job->target)) continue;
                ++job->pending;
                ++job->cacheCalls;
                WKWebsiteDataStoreRemoveFetchCacheForOrigin(job->store.get(), o, job, [](void* c) {
                    OmniScJob* jj = static_cast<OmniScJob*>(c);
                    if (omniScLive(jj)) ++jj->cacheDone;
                    omniScBack(jj);
                });
            }
        }
        omniScBack(job);
    });
    omniScBack(j);
}

// --- Site settings row ---------------------------------------------------------------------------------------------
static void omniScSiteRow(OmniFxPanel& p, const std::string&)
{
    Tab* t = active();
    const OSC::Target tg = t ? OSC::target(t->url) : OSC::Target();
    OmniFxRow r; r.id = omniScSiteRowId; r.label = "Clear data for this site";
    r.value = OSC::rowValue(tg, omniScJob != nullptr);
    r.enabled = tg.ok && !omniScJob;
    r.danger = r.enabled;
    p.rows.push_back(r);
}
static bool omniScSiteInput(const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    Tab* t = active();
    if (!r.enabled || !t) return true;
    if (omniScJob) { notice(OSC::busyNotice()); return true; }
    const OSC::Target tg = OSC::target(t->url);
    if (!tg.ok) return true;
    WKRetainPtr<WKPageRef> page = t->page;
    const std::string url = t->url;
    omniAsk(OSC::askTitle(tg), OSC::askBody(tg, t->omniPrivate), "Clear", [page, url](bool ok) {
        if (!ok) return;
        omniFxCloseAll();
        omniScStart(page.get(), url);
    });
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniHttpsOnly.h" // OMNI_HTTPS_ONLY_V1: HTTPS-only mode + GPC, https-only.txt (pure)\n',
         '#include "OmniHttpsOnly.h" // OMNI_HTTPS_ONLY_V1: HTTPS-only mode + GPC, https-only.txt (pure)\n'
         '#include "OmniSiteClear.h" // OMNI_SITE_CLEAR_V1: Clear data for this site (pure)\n'
         '#include <WebKit/WKArray.h> // OMNI_SITE_CLEAR_V1: CacheStorage origins\n'
         '#include <WebKit/WKDictionary.h> // OMNI_SITE_CLEAR_V1: the page script\'s (empty) argument list\n'),
    ],
    'OmniQuickMenu.h': [
        ('static bool omniHoSiteInput(const OmniFxRow& r, int b);\n',
         'static bool omniHoSiteInput(const OmniFxRow& r, int b);\n'
         'constexpr int omniScSiteRowId = 730; // OMNI_SITE_CLEAR_V1 (OmniSiteClearShell.h)\n'
         'static void omniScSiteRow(OmniFxPanel& p, const std::string& host);\n'
         'static bool omniScSiteInput(const OmniFxRow& r, int b);\n'),
        ('    omniHoSiteRow(p, host); // OMNI_HTTPS_ONLY_V1: HTTPS-only on this site\n',
         '    omniHoSiteRow(p, host); // OMNI_HTTPS_ONLY_V1: HTTPS-only on this site\n'
         '    omniScSiteRow(p, host); // OMNI_SITE_CLEAR_V1: Clear data for this site\n'),
        ('    if (r.id == omniHoSiteRowId) return omniHoSiteInput(r, b); // OMNI_HTTPS_ONLY_V1 (handles its disabled state)\n',
         '    if (r.id == omniScSiteRowId) return omniScSiteInput(r, b); // OMNI_SITE_CLEAR_V1 (handles its disabled state)\n'
         '    if (r.id == omniHoSiteRowId) return omniHoSiteInput(r, b); // OMNI_HTTPS_ONLY_V1 (handles its disabled state)\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniHttpsOnlyShell.h" // OMNI_HTTPS_ONLY_V1\n',
         '#include "OmniHttpsOnlyShell.h" // OMNI_HTTPS_ONLY_V1\n'
         '#include "OmniSiteClearShell.h" // OMNI_SITE_CLEAR_V1\n'),
    ],
}


def variants(old0, s):
    """The anchor with the file's own line endings (mixed files: whichever spelling is present)."""
    for e in ('\r\n', '\n'):
        old = old0.replace('\n', e)
        if s.count(old):
            return old, e
    return old0, '\n'


# r2 edits (files that already have MARK from r1 get only these; REV makes them idempotent)
EDITS_R2 = {
    'OmniFeatures3.h': [
        ('    omniTaTick(now);    // OMNI_TAB_AUDIO_V1: media state every 500 ms\n',
         '    omniTaTick(now);    // OMNI_TAB_AUDIO_V1: media state every 500 ms\n'
         '    omniScTick(now);    // OMNI_SITE_CLEAR_V1_R2: native timeout of "Clear data for this site"\n'),
    ],
}


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
    if 'OMNI_HTTPS_ONLY_V1' not in (root / 'OmniFeatures3.h').read_bytes().decode('utf-8'):
        sys.exit('OmniFeatures3.h: OMNI_HTTPS_ONLY_V1 missing: apply_https_only.py first')
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    for name, edits in EDITS_R2.items():
        check(name, edits, REV)
    msgs = [write_new('OmniSiteClear.h', PURE, 'OmniHttpsOnly.h'),
            write_new('OmniSiteClearShell.h', SHELL, 'OmniHttpsOnlyShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    msgs += [patch(name, edits, REV).replace(': ', ' (r2): ', 1) for name, edits in EDITS_R2.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK + ' (r2)')


main()
