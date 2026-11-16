#!/usr/bin/env python3
"""OMNI_READER_AUTO_V1 (2026-11-16): "Reader view available" hint + "Always open in Reader view" per site.

Which Reader view
  Every "Reader view" entry in the shell (Options > More tile omniQmReader, the hold-Cross page menu omniCxReader, the
  Browser tools menu omniMenuReader, the quick-access item omniQaReader) calls the ENGINE's omniReaderStart()
  (OmniBrowser.cpp): one page script picks the paragraphs' best parent, the shell builds a fixed HTML page and loads it
  with WKPageLoadHTMLString(base = the article's address), Tab::omniReader marks that load. It is a new back-forward
  item, so Back returns to the article. The bundled add-on omni-reader-view (1.1.0, default_on false) is separate: a
  content script that, once switched on (Add-ons / its quick switch), shows its own floating "Reader view" button on
  article pages and opens on Alt+Shift+R or when its quick switch is turned on. Nothing in the shell calls it. This
  feature uses the engine's Reader view (the one the menus use), so it works with the add-on off.

What the user sees
  - Site settings has a new row after "Page tweaks":  "Reader view"   Ask | Always for this site
    (stepper: Cross or D-pad left / right toggles; "-" and disabled on non-web pages). Notice:
        "Reader view on example.com: always. Articles there open in Reader view"   /   "...: ask. ..."
        (+ " (this session only)" in a private tab).
  - After every page load (finished(), main frame) of an http(s) page that is not the start page / an omni:// page /
    a search results page (URL heuristic, OmniReaderAuto::searchResultsUrl), ONE page script measures the page
    (paragraphs >= 80 characters outside nav / aside / footer / form, their total, <article> count and its text,
    a playing <video>, designMode / contentEditable body). No polling, no timer, no observer.
      article + Ask:    a book icon in the address field (left of the bookmark star) and, once per site per run, the
                        notice "Reader view available: Options > Reader view". The Options menu (top level) gets a
                        "Reader view   Article found" row while the shown tab has an article: Cross opens it.
      article + Always: the tab opens Reader view by itself (omniRauTick: when it is the shown tab, the keyboard is
                        not up, nothing plays). The article stays in history: Back returns to it, and that return does
                        not open Reader view again (Tab::omniRauOpened = that address, cleared by any other address).
      never automatic:  a playing video / audio (page script + WKPageGetMediaState + Media downloads ownership),
                        the start page, omni:// pages, search results, editable pages, test modes.

Hint control: no new button. While browsing every face button, L3 / R3 / touchpad, the D-pad, Options / Create, hold
  Cross and the L2 chords (+Square / Triangle / Cross / Circle / R3 / L3 / D-pad up-down / L1-R1) and R2 / L2 taps
  (Media downloads) already do something (OmniControlsHelp.h table, button()); Triangle is the address bar. So the
  hint is visual (book icon, one notice per site) and the action is a conditional Options top-level row (the same
  pattern as "Now playing" 8100 / "Blocked pop-ups" 8470 / Downloads 8480): Options, then Cross on "Reader view".

Private tabs: Always / Ask chosen in a private tab is kept in omniRauSession (this run, private tabs only, never
  written, never read by normal tabs); the saved store is reader-sites.txt (omniIoQueue, /data/omni/reader-sites.txt):
      omni-reader-sites<TAB>1
      always<TAB>example.com          (host key: lower case, "www." dropped, exact host; at most 500)

Ids: Site settings row 760, Options top-level row 8490 (grep of every apply_*.py: unused; site rows 710-750, quick
  rows 8100 / 8200 / 8470 / 8480). Namespace alias ORAU.

Pure part: engine/entry/OmniReaderAuto.h (store parse / serialize / toggle, site key, search-results heuristic,
  eligibility, the page script, its answer, the article thresholds, the decision, texts). Tested by
  tools/test_reader_auto.cpp:  g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_reader_auto.cpp -o t && ./t s.js
  (writes the page script to s.js) and tools/test_reader_auto_js.mjs (node: the script on fake DOMs).
Shell side: engine/entry/OmniReaderAutoShell.h (included from OmniFeatures3.h after OmniWebAppsShell.h, so before
  OmniSiteListShell.h, which could read omniRauStore).

Anchors (exactly once each; MARK makes each file idempotent; whole lines only, every insertion after or before the
whole anchor line):
  OmniBrowser.cpp   the OmniSiteList.h include line (apply_site_list.py's): + OmniReaderAuto.h
                    the Tab line "bool omniPrivate = false, omniMobileUA = ..., omniNewTabPage = false;": + 5 fields
                    the OmniFeatures3Decl.h include line: + declarations (omniRauFinished, omniRauDrawAddress)
                    the omniF3StarDraw() call in omniDrawAddress: + omniRauDrawAddress()
                    the omniFndFinished(tab) call in omniEverydayFinished (apply_find_plus.py's): + omniRauFinished(tab)
                    (before the Tab::omniReader exchange, so the reader page's own load is recognised)
  OmniQuickMenu.h   the omniSliSiteInput declaration (apply_site_list.py's): row id 760 + declarations
                    the omniStSiteRow call (apply_site_css.py's): + omniRauSiteRow(p, host)
                    the omniSliSiteRowId dispatch: our dispatch before it
                    the omniDlpQuickRow declaration / call / input (apply_dl_progress.py's): + ours
  OmniFeatures3.h   the OmniWebAppsShell.h include line (apply_web_apps.py's): + OmniReaderAutoShell.h
                    the omniScTick line of omniF3Tick (apply_site_clear.py's r2): + omniRauTick(now)
r2 (OMNI_READER_AUTO_V1_R2, marker REV): the automatic open is guarded so Back from Reader view cannot trap the user:
  never on a Back / Forward navigation (WKNavigationActionGetNavigationType, recorded per tab at policy time by
  omniRauNavigation), at most once per back/forward-list item (Tab::omniRauItem, retained in memory; only a Reload of
  that item opens again; a page-cache restore with no policy decision counts as not-a-reload), and never within
  ORAU::kLeaveQuietMs (3 s) of leaving Reader view. r2 anchors (OmniBrowser.cpp): r1's omniRauOpened Tab line
  (replaced by omniRauItem + omniRauGuard), r1's omniReaderStart declaration (+ omniRauNavigation), and the omniHoPolicy
  line of omniEverydayNavigation (apply_https_only.py's; omniRauNavigation goes before it). Upgrading an r1 tree:
  the headers are rewritten (they differ) and only the r2 edits are made; a fresh apply makes r1 then r2 in memory,
  so both give byte-identical trees.
Apply AFTER apply_site_list.py, apply_dl_progress.py, apply_find_plus.py, apply_web_apps.py, apply_site_clear.py.
usage: apply_reader_auto.py <engine tree>   (keeps each file's line endings; re-run prints "already")

Sites with custom settings (apply_site_list.py, NOT edited here) would need, to list and reset these sites:
  OmniSiteList.h       a Kind kReader (before kKindCount; its place in the enum is its place in the summary) and
                       itemText: case kReader: return "Reader view always";
  OmniSiteListShell.h  omniSliCollect():  omniRauLoad(); for (const auto& h : omniRauStore.always) add(OSLI::kReader, h, 1);
                       omniSliReset():    case OSLI::kReader: ORAU::setSite(omniRauStore, it.key, false); rau = true; break;
                                          ... if (rau) omniRauWrite();
                       (optional) one-site panel row: value ORAU::rowValue(ORAU::saved(omniRauStore, key)), change
                       with ORAU::setSite(omniRauStore, key, !saved) + omniRauWrite(). Key: ORAU::siteKey("https://<host>/").
  Include order is already right (OmniFeatures3.h, line ~7873, is before OmniSiteListShell.h). Private-tab choices
  (omniRauSession) must not be listed, like the other stores.
"""
import sys
from pathlib import Path

MARK = 'OMNI_READER_AUTO_V1'
REV = 'OMNI_READER_AUTO_V1_R2'   # r2: the automatic open's guard (no Back / Forward trap)
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_READER_AUTO_V1: the pure part of "Reader view available" + "Always open in Reader view" per site (no SDL, no
// WebKit). The shell side is OmniReaderAutoShell.h; the reasons are in tools/apply_reader_auto.py. Tested on the host
// with g++ (tools/test_reader_auto.cpp) and node (tools/test_reader_auto_js.mjs, the page script on fake DOMs).
// OMNI_READER_AUTO_V1_R2: the automatic open's guard (Guard, autoAllowed): no Back / Forward trap.
#pragma once
#include <cstddef>
#include <cstdint>
#include <map>
#include <set>
#include <string>
#include <vector>

namespace OmniReaderAuto {

constexpr const char* kFileName = "reader-sites.txt";
constexpr const char* kHeader = "omni-reader-sites\t1";
constexpr size_t kMaxSites = 500, kHostMax = 253, kHintedMax = 200;
constexpr long kMaxFileBytes = 64L << 10;
constexpr int kSiteRowId = 760, kQuickRowId = 8490;
constexpr const char* kAnswerTag = "omni-rauto";

// --- article thresholds (the page script counts, isArticle() decides) ---------------------------------------------
constexpr int kMinParagraphChars = 80;     // a <p> counts from this many characters (whitespace squashed)
constexpr int kScanParagraphs = 600;       // the script looks at the first 600 <p> only
constexpr int kParagraphCap = 4000;        // one paragraph adds at most this much
constexpr int kMinParagraphs = 5, kMinChars = 2000;               // enough long paragraphs ...
constexpr int kArticleMinParagraphs = 3, kArticleMinChars = 1500; // ... or a real <article> with some of them
constexpr int kMaxArticles = 3;            // more <article> elements: a listing (blog index, feed), not one article

// --- hosts ------------------------------------------------------------------------------------------------------
inline char lower(char c) { return c >= 'A' && c <= 'Z' ? char(c + ('a' - 'A')) : c; }
inline std::string lowerAll(std::string s) { for (auto& c : s) c = lower(c); return s; }

struct UrlParts { std::string host, path, query; };   // host lower case (brackets kept), path lower case, raw query
inline bool split(const std::string& url, UrlParts& u)
{
    size_t start;
    if (url.compare(0, 8, "https://") == 0) start = 8;
    else if (url.compare(0, 7, "http://") == 0) start = 7;
    else return false;
    size_t end = url.find_first_of("/?#", start);
    if (end == std::string::npos) end = url.size();
    std::string auth = url.substr(start, end - start);
    const size_t at = auth.rfind('@');
    if (at != std::string::npos) auth = auth.substr(at + 1);
    if (!auth.empty() && auth[0] == '[') {
        const size_t close = auth.find(']');
        if (close == std::string::npos) return false;
        u.host = auth.substr(0, close + 1);
    } else u.host = auth.substr(0, auth.find(':'));
    u.host = lowerAll(u.host);
    while (!u.host.empty() && u.host.back() == '.') u.host.pop_back();
    if (u.host.empty()) return false;
    const size_t hash = url.find('#', end);
    const std::string rest = url.substr(end, hash == std::string::npos ? std::string::npos : hash - end);
    const size_t q = rest.find('?');
    u.path = lowerAll(q == std::string::npos ? rest : rest.substr(0, q));
    if (u.path.empty()) u.path = "/";
    u.query = q == std::string::npos ? std::string() : rest.substr(q + 1);
    return true;
}
// "https://User@WWW.Example.COM:8443/a?b" -> "example.com". "" for anything that is not http(s) or has no usable host.
inline std::string siteKey(const std::string& url)
{
    UrlParts u;
    if (!split(url, u)) return std::string();
    std::string host = u.host;
    if (host.compare(0, 4, "www.") == 0 && host.size() > 4) host = host.substr(4);
    if (host.empty() || host.size() > kHostMax) return std::string();
    for (char c : host)
        if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '.' || c == '-' || c == '_' || c == ':' || c == '[' || c == ']'))
            return std::string();
    return host;
}

// --- search results pages (heuristic) -----------------------------------------------------------------------------
// A parameter with a non-empty value ("q=x"; "q=" and "q" alone do not count).
inline bool hasParam(const std::string& query, const std::vector<const char*>& names)
{
    size_t pos = 0;
    while (pos <= query.size()) {
        size_t amp = query.find('&', pos);
        if (amp == std::string::npos) amp = query.size();
        const std::string part = query.substr(pos, amp - pos);
        const size_t eq = part.find('=');
        if (eq != std::string::npos && eq + 1 < part.size()) {
            const std::string name = lowerAll(part.substr(0, eq));
            for (const char* n : names) if (name == n) return true;
        }
        pos = amp + 1;
    }
    return false;
}
// google.com, google.co.uk, www.bing.com, duckduckgo.com, html.duckduckgo.com, search.yahoo.com, search.brave.com ...
inline bool searchEngineHost(const std::string& host0)
{
    std::string host = host0;
    if (host.compare(0, 4, "www.") == 0) host = host.substr(4);
    if (host.compare(0, 7, "search.") == 0) return true;
    static const char* const engines[] = { "google", "bing", "duckduckgo", "yandex", "baidu", "ecosia", "startpage", "qwant",
                                           "kagi", "sogou", "naver", "seznam", "mojeek", "searx", "presearch" };
    for (const char* e : engines) {
        const std::string name(e);
        // "<engine>." at the start, or ".<engine>." (html.duckduckgo.com)
        if (host.compare(0, name.size() + 1, name + ".") == 0) return true;
        if (host.find("." + name + ".") != std::string::npos) return true;
    }
    return false;
}
inline bool searchResultsUrl(const std::string& url)
{
    UrlParts u;
    if (!split(url, u)) return false;
    static const std::vector<const char*> terms = { "q", "query", "p", "text", "wd", "search_query", "search", "s", "k",
                                                    "keyword", "keywords", "term", "searchterm" };
    const bool term = hasParam(u.query, terms);
    if (searchEngineHost(u.host)) return term || u.path.compare(0, 7, "/search") == 0;
    if (!term) return false;
    if (u.path == "/" && hasParam(u.query, { "s" })) return true;          // WordPress: /?s=words
    size_t pos = 0;                                                         // /search, /en/search/, /results, /find
    while (pos < u.path.size()) {
        size_t slash = u.path.find('/', pos);
        if (slash == std::string::npos) slash = u.path.size();
        const std::string seg = u.path.substr(pos, slash - pos);
        if (seg == "search" || seg == "results" || seg == "searchresults" || seg == "find" || seg == "search.php"
            || seg == "search.html" || seg == "search.aspx") return true;
        pos = slash + 1;
    }
    return false;
}
// Pages the check runs on at all: http(s) with a host, not search results. (The shell also skips the start page,
// omni:// pages, the Reader view page itself and test modes.)
inline bool eligible(const std::string& url) { return !siteKey(url).empty() && !searchResultsUrl(url); }

// --- the page script --------------------------------------------------------------------------------------------
// One evaluation per finished main-frame load. textContent only (no layout). Answer:
//   "omni-rauto 1 p<long paragraphs> c<their characters> a<article elements> t<longest article text> v<video playing>
//    e<editable>"   or "omni-rauto 0" (no body / an exception).
// The numbers 80 / 600 / 4000 are kMinParagraphChars / kScanParagraphs / kParagraphCap (the test checks).
constexpr const char* kCheckScript = R"JS((function(){try{var d=document,b=d.body;if(!b)return 'omni-rauto 0';
var v=0,vs=d.getElementsByTagName('video');for(var i=0;i<vs.length&&i<20;i++){var x=vs[i];if(!x.paused&&!x.ended&&x.readyState>2){v=1;break;}}
var e=(d.designMode==='on'||b.isContentEditable)?1:0;
var ps=d.getElementsByTagName('p'),n=0,c=0,m=Math.min(ps.length,600);
for(var j=0;j<m;j++){var p=ps[j],t=p.textContent||'';if(t.length<80)continue;t=t.replace(/\s+/g,' ').trim();if(t.length<80)continue;
if(p.closest&&p.closest('nav,aside,footer,form,[role=navigation],[role=complementary]'))continue;n++;c+=Math.min(t.length,4000);}
var as=d.getElementsByTagName('article'),ac=0;for(var k=0;k<as.length&&k<4;k++){var l=(as[k].textContent||'').length;if(l>ac)ac=l;}
return 'omni-rauto 1 p'+n+' c'+c+' a'+as.length+' t'+Math.min(ac,1000000)+' v'+v+' e'+e;}catch(_){return 'omni-rauto 0';}})())JS";

struct Measure { bool ok = false; int paragraphs = 0, chars = 0, articles = 0, articleChars = 0; bool video = false, editable = false; };
inline Measure parseAnswer(const std::string& s)
{
    Measure m;
    const std::string tag = std::string(kAnswerTag) + " 1";
    if (s.compare(0, tag.size(), tag) != 0 || (s.size() > tag.size() && s[tag.size()] != ' ')) return m;
    size_t pos = tag.size();
    bool any = false;
    while (pos < s.size()) {
        while (pos < s.size() && s[pos] == ' ') ++pos;
        if (pos >= s.size()) break;
        const char k = s[pos++];
        long n = 0;
        size_t digits = 0;
        while (pos < s.size() && s[pos] >= '0' && s[pos] <= '9') { if (n < 100000000L) n = n * 10 + (s[pos] - '0'); ++pos; ++digits; }
        if (!digits) return Measure();
        while (pos < s.size() && s[pos] != ' ') ++pos;
        const int v = int(n);
        switch (k) {
        case 'p': m.paragraphs = v; break;
        case 'c': m.chars = v; break;
        case 'a': m.articles = v; break;
        case 't': m.articleChars = v; break;
        case 'v': m.video = v != 0; break;
        case 'e': m.editable = v != 0; break;
        default: break;                     // newer fields: ignored
        }
        any = true;
    }
    m.ok = any;
    return m;
}
inline bool isArticle(const Measure& m)
{
    if (!m.ok || m.editable || m.articles > kMaxArticles) return false;
    if (m.paragraphs >= kMinParagraphs && m.chars >= kMinChars) return true;
    return m.articles >= 1 && m.articleChars >= kArticleMinChars && m.paragraphs >= kArticleMinParagraphs;
}
enum Action { kNone = 0, kHint, kOpen };
// always: the site's choice for this tab; blocked: autoAllowed() said no for this load (Back / Forward, the history
// item already converted, just left Reader view); playing: the shell sees media playing in the tab.
inline Action decide(const Measure& m, bool always, bool blocked, bool playing)
{
    if (!isArticle(m)) return kNone;
    return always && !blocked && !playing && !m.video ? kOpen : kHint;
}

// --- the automatic open's guard (OMNI_READER_AUTO_V1_R2) ------------------------------------------------------------
// Never on a Back / Forward navigation; at most once per back/forward-list item (the shell keeps the converted item;
// only a Reload of it opens Reader view again); never within kLeaveQuietMs of leaving Reader view. In memory only.
constexpr uint32_t kLeaveQuietMs = 3000;
enum Nav { kNavUnknown = 0, kNavNormal, kNavBackForward, kNavReload };
struct Guard {
    Nav nav = kNavUnknown;        // the main-frame navigation the next finished() belongs to (set at policy time)
    bool inReader = false;        // the last finished load was the Reader view page
    bool left = false;            // Reader view was left at leftAt (SDL_GetTicks() ms)
    uint32_t leftAt = 0;
    void navigation(Nav n) { nav = n; }
    // finished(): the load's navigation type (unknown when no policy decision was seen, e.g. a page-cache restore).
    Nav finished(bool reader, uint32_t now)
    {
        const Nav n = nav;
        nav = kNavUnknown;
        if (!reader && inReader) { left = true; leftAt = now; }
        inReader = reader;
        return n;
    }
};
// sameItem: the shown history item is the one Reader view was opened for automatically.
inline bool autoAllowed(const Guard& g, Nav n, bool sameItem, uint32_t now)
{
    if (n == kNavBackForward) return false;
    if (g.left && uint32_t(now - g.leftAt) < kLeaveQuietMs) return false;
    if (sameItem && n != kNavReload) return false;
    return true;
}

// --- the store --------------------------------------------------------------------------------------------------
struct Store { std::set<std::string> always; };
inline bool saved(const Store& s, const std::string& host) { return !host.empty() && s.always.count(host) != 0; }
// session: choices made in private tabs (this run); consulted only when privateTab (it wins there). A normal tab sees
// the saved store only, so it never shows or follows a private-tab choice.
inline bool always(const Store& s, const std::map<std::string, bool>& session, const std::string& host, bool privateTab)
{
    if (host.empty()) return false;
    if (privateTab) { auto it = session.find(host); if (it != session.end()) return it->second; }
    return saved(s, host);
}
// Removing always works; a new host when 500 are saved does not.
inline bool setSite(Store& s, const std::string& host, bool on)
{
    if (host.empty()) return false;
    if (!on) { s.always.erase(host); return true; }
    if (!s.always.count(host) && s.always.size() >= kMaxSites) return false;
    s.always.insert(host);
    return true;
}
// The row's change. Private tab: a session row exists only while it differs from the saved choice. Returns false when
// the saved store is full (nothing changed).
inline bool toggle(Store& s, std::map<std::string, bool>& session, const std::string& host, bool privateTab, bool& now)
{
    now = !always(s, session, host, privateTab);
    if (privateTab) {
        if (now == saved(s, host)) session.erase(host); else session[host] = now;
        return true;
    }
    return setSite(s, host, now);
}
inline std::string serialize(const Store& s)
{
    std::string out = std::string(kHeader) + "\n";
    size_t n = 0;
    for (const auto& h : s.always) {
        if (h.empty() || n >= kMaxSites) continue;
        out += "always\t" + h + "\n";
        ++n;
    }
    return out;
}
inline Store parse(const std::string& text)
{
    Store s;
    size_t pos = 0;
    while (pos < text.size()) {
        size_t nl = text.find('\n', pos);
        if (nl == std::string::npos) nl = text.size();
        std::string line = text.substr(pos, nl - pos);
        pos = nl + 1;
        while (!line.empty() && (line.back() == '\r' || line.back() == ' ')) line.pop_back();
        const size_t t1 = line.find('\t');
        if (t1 == std::string::npos || line.compare(0, t1, "always") != 0) continue;
        const std::string host = siteKey("https://" + line.substr(t1 + 1) + "/");
        if (host.empty() || line.find('/', t1 + 1) != std::string::npos) continue;
        if (!s.always.count(host) && s.always.size() >= kMaxSites) continue;
        s.always.insert(host);
    }
    return s;
}
// Once per site per run (the set is capped; past the cap no more hints are remembered, so none repeat either).
inline bool firstHint(std::set<std::string>& seen, const std::string& host)
{
    if (host.empty() || seen.count(host) || seen.size() >= kHintedMax) return false;
    seen.insert(host);
    return true;
}

// --- texts ------------------------------------------------------------------------------------------------------
inline const char* rowLabel() { return "Reader view"; }
inline std::string rowValue(bool on) { return on ? "Always for this site" : "Ask"; }
inline std::string siteNotice(const std::string& host, bool on, bool privateTab, bool full)
{
    if (full) return "Too many sites open in Reader view (500). Set one back to Ask first";
    std::string s = "Reader view on " + host + (on ? ": always. Articles there open in Reader view" : ": ask. Articles there show a hint");
    if (privateTab) s += " (this session only)";
    return s;
}
inline const char* hintNotice() { return "Reader view available: Options > Reader view"; }
inline const char* quickLabel() { return "Reader view"; }
inline const char* quickValue() { return "Article found"; }

} // namespace OmniReaderAuto
'''

SHELL = r'''// OMNI_READER_AUTO_V1: "Reader view available" + "Always open in Reader view" per site (shell side). Included from
// OmniFeatures3.h (inside OmniBrowser.cpp's anonymous namespace, after OmniWebAppsShell.h, so before
// OmniSiteListShell.h). The pure part is OmniReaderAuto.h; the reasons are in tools/apply_reader_auto.py.
// Main thread only; reader-sites.txt is written by omniIoQueue. It opens the ENGINE's Reader view (omniReaderStart),
// the one every menu uses.
// OMNI_READER_AUTO_V1_R2: the automatic open is guarded (ORAU::Guard / autoAllowed): never on Back / Forward, once per
// history item (Tab::omniRauItem; a Reload opens again), never within 3 s of leaving Reader view.
#pragma once

namespace ORAU = OmniReaderAuto;
static ORAU::Store omniRauStore;
static bool omniRauLoaded = false;
static std::map<std::string, bool> omniRauSession;   // choices made in private tabs: this run, private tabs only
static std::set<std::string> omniRauHinted;           // sites whose "Reader view available" notice was shown this run

static void omniRauLoad()
{
    if (omniRauLoaded) return;
    omniRauLoaded = true;
    FILE* f = fopen(omniData(ORAU::kFileName).c_str(), "rb");
    if (!f) return;
    std::string text;
    char buf[4096];
    size_t n;
    while ((n = fread(buf, 1, sizeof buf, f)) > 0 && long(text.size()) < ORAU::kMaxFileBytes) text.append(buf, n);
    fclose(f);
    omniRauStore = ORAU::parse(text);
}
static void omniRauWrite()
{
    if (omniTestMode()) return;
    omniIoQueue(omniData(ORAU::kFileName), ORAU::serialize(omniRauStore), false);
}
static bool omniRauAlwaysFor(const Tab& t)
{
    omniRauLoad();
    return ORAU::always(omniRauStore, omniRauSession, ORAU::siteKey(t.url), t.omniPrivate);
}
// UI-process cached media state (no IPC) + a Media downloads section tab.
static bool omniRauPlaying(const Tab& t)
{
    if (omniMediaOwns(t)) return true;
    return t.page && !t.crashed && (WKPageGetMediaState(t.page) & (kWKMediaIsPlayingAudio | kWKMediaIsPlayingVideo));
}

// --- the guard (OMNI_READER_AUTO_V1_R2): navigation type at policy time, the converted history item ---------------------
// From omniEverydayNavigation's decidePolicyForNavigationAction (main frame, before any early answer).
static void omniRauNavigation(Tab& t, WKFrameNavigationType type)
{
    t.omniRauGuard.navigation(type == kWKFrameNavigationTypeBackForward ? ORAU::kNavBackForward
        : type == kWKFrameNavigationTypeReload ? ORAU::kNavReload : ORAU::kNavNormal);
}
static WKBackForwardListItemRef omniRauItemNow(const Tab& t)
{
    WKBackForwardListRef list = t.page ? WKPageGetBackForwardList(t.page) : nullptr;
    return list ? WKBackForwardListGetCurrentItem(list) : nullptr;
}

// --- finished(): one readability check per main-frame load ----------------------------------------------------------
struct OmniRauAsk { Tab* tab; unsigned gen; std::string url; bool blocked; };
static void omniRauFinished(Tab& t)
{
    if (t.omniRauArticle) omniShellDirty = true;   // the icon goes
    t.omniRauArticle = t.omniRauPending = false;
    ++t.omniRauGen;
    const uint32_t now = SDL_GetTicks();
    const ORAU::Nav nav = t.omniRauGuard.finished(t.omniReader, now);
    if (t.omniReader) { t.omniRauInReader = true; return; }   // the Reader view page itself (it keeps the article's address)
    t.omniRauInReader = false;
    if (omniTestMode() || t.omniNewTabPage || t.omniPagesTab || !t.page || !ORAU::eligible(t.url)) return;
    WKBackForwardListItemRef item = omniRauItemNow(t);
    const bool blocked = !ORAU::autoAllowed(t.omniRauGuard, nav, item && item == t.omniRauItem.get(), now);
    auto script = adoptWK(WKStringCreateWithUTF8CString(ORAU::kCheckScript));
    WKPageEvaluateJavaScriptInMainFrame(t.page, script.get(), new OmniRauAsk{ &t, t.omniRauGen, t.url, blocked }, [](WKTypeRef result, WKErrorRef error, void* context) {
        std::unique_ptr<OmniRauAsk> ask(static_cast<OmniRauAsk*>(context));
        if (!omniTabAlive(ask->tab)) return;
        Tab& tab = *ask->tab;
        if (tab.omniRauGen != ask->gen || tab.url != ask->url) return;   // a newer load: its own check answers
        std::string answer;
        if (!error && result && WKGetTypeID(result) == WKStringGetTypeID()) answer = OmniTest::toStd(static_cast<WKStringRef>(result));
        const ORAU::Action a = ORAU::decide(ORAU::parseAnswer(answer), omniRauAlwaysFor(tab), ask->blocked, omniRauPlaying(tab));
        if (a == ORAU::kNone) return;
        tab.omniRauArticle = true;
        omniShellDirty = true;
        if (a == ORAU::kOpen) { tab.omniRauPending = true; return; }   // omniRauTick opens it once the tab is shown
        if (&tab == active() && ORAU::firstHint(omniRauHinted, ORAU::siteKey(tab.url))) notice(ORAU::hintNotice());
    });
}
// omniF3Tick: an automatic open waits until its tab is the shown one and the keyboard is down. One flag test otherwise.
static void omniRauTick(uint32_t)
{
    Tab* t = active();
    if (!t || !t->omniRauPending || editing || t->loading) return;
    t->omniRauPending = false;
    if (omniRauPlaying(*t) || !ORAU::eligible(t->url)) return;
    t->omniRauItem = omniRauItemNow(*t);   // R2: this history item is converted once (Back to it stays on the page)
    omniReaderStart();
}

// --- address field: the book icon left of the bookmark star --------------------------------------------------------
static void omniRauDrawAddress()
{
    const Tab* t = active();
    if (!t || !t->omniRauArticle || !omniF3StarShown()) return;
    const OmniTheme& T = omniTheme();
    const int cx = 1036, cy = 82;                       // the star is at 1078 (omniStarCX); the address text ends at 1052
    fillRounded(cx - 20, cy - 18, 40, 36, 8, T.field);  // covers the end of a long address
    fillRounded(cx - 13, cy - 9, 12, 18, 2, T.accent);  // an open book: two pages ...
    fillRounded(cx + 1, cy - 9, 12, 18, 2, T.accent);
    for (int i = 0; i < 3; ++i) {                       // ... with three lines each
        fill(cx - 11, cy - 5 + i * 4, 8, 2, T.field);
        fill(cx + 3, cy - 5 + i * 4, 8, 2, T.field);
    }
}

// --- Options (top level): "Reader view  Article found" while the shown tab has an article ---------------------------
static void omniRauQuickRow(OmniFxPanel& p)
{
    const Tab* t = active();
    if (!t || !t->omniRauArticle) return;
    OmniFxRow r; r.id = ORAU::kQuickRowId; r.label = ORAU::quickLabel(); r.value = ORAU::quickValue();
    p.rows.push_back(r);
}
static bool omniRauQuickInput(const OmniFxRow& r, int b)
{
    if (r.id != ORAU::kQuickRowId || b != SDL_CONTROLLER_BUTTON_A) return false;
    omniFxCloseAll();
    omniReaderStart();
    return true;
}

// --- Site settings > Reader view: Ask / Always for this site ---------------------------------------------------------
static std::string omniRauSiteHost() { return active() ? ORAU::siteKey(active()->url) : std::string(); }
static void omniRauSiteRow(OmniFxPanel& p, const std::string&)
{
    omniRauLoad();
    const std::string host = omniRauSiteHost();
    OmniFxRow r; r.id = omniRauSiteRowId; r.label = ORAU::rowLabel(); r.stepper = true; r.enabled = !host.empty();
    r.value = host.empty() ? std::string("-") : ORAU::rowValue(ORAU::always(omniRauStore, omniRauSession, host, active()->omniPrivate));
    p.rows.push_back(r);
}
static bool omniRauSiteInput(const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A && b != SDL_CONTROLLER_BUTTON_DPAD_LEFT && b != SDL_CONTROLLER_BUTTON_DPAD_RIGHT) return false;
    const std::string host = omniRauSiteHost();
    Tab* t = active();
    if (!r.enabled || host.empty() || !t) return true;
    omniRauLoad();
    const bool priv = t->omniPrivate;
    bool now = false;
    const bool ok = ORAU::toggle(omniRauStore, omniRauSession, host, priv, now);
    if (ok && !priv) omniRauWrite();
    notice(ORAU::siteNotice(host, now, priv, !ok));
    if (ok && now && t->omniRauArticle && !t->omniRauInReader) t->omniRauPending = true;   // this article too (the user asked)
    if (ok && !now) t->omniRauPending = false;
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniSiteList.h" // OMNI_SITE_LIST_V1: Sites with custom settings (pure)\n',
         '#include "OmniSiteList.h" // OMNI_SITE_LIST_V1: Sites with custom settings (pure)\n'
         '#include "OmniReaderAuto.h" // OMNI_READER_AUTO_V1: Reader view hint + Always open in Reader view per site (pure)\n'),
        ('    bool omniPrivate = false, omniMobileUA = false, omniReader = false, omniNewTabPage = false;\n',
         '    bool omniPrivate = false, omniMobileUA = false, omniReader = false, omniNewTabPage = false;\n'
         '    bool omniRauArticle = false, omniRauPending = false, omniRauInReader = false; // OMNI_READER_AUTO_V1: article found, open pending, the reader page is shown\n'
         '    unsigned omniRauGen = 0; // OMNI_READER_AUTO_V1: finished() count (late check answers are dropped)\n'
         '    std::string omniRauOpened; // OMNI_READER_AUTO_V1: Reader view was opened automatically for this address\n'),
        ('#include "OmniFeatures3Decl.h" // OMNI_FEATURES_V3: star, suggestions, page tools, dark pages, tab memory\n',
         '#include "OmniFeatures3Decl.h" // OMNI_FEATURES_V3: star, suggestions, page tools, dark pages, tab memory\n'
         'static void omniRauFinished(Tab& tab); // OMNI_READER_AUTO_V1 (OmniReaderAutoShell.h): the readability check\n'
         'static void omniRauDrawAddress(); // OMNI_READER_AUTO_V1: the book icon in the address field\n'
         'static void omniReaderStart(); // OMNI_READER_AUTO_V1: the engine Reader view (defined below)\n'),
        ('    omniF3StarDraw(); // OMNI_FEATURES_V3: bookmark star\n',
         '    omniF3StarDraw(); // OMNI_FEATURES_V3: bookmark star\n'
         '    omniRauDrawAddress(); // OMNI_READER_AUTO_V1: book icon while the page is an article\n'),
        ("    omniFndFinished(tab); // OMNI_FIND_PLUS_V1: a navigation closes this tab's find bar (query kept)\n",
         "    omniFndFinished(tab); // OMNI_FIND_PLUS_V1: a navigation closes this tab's find bar (query kept)\n"
         "    omniRauFinished(tab); // OMNI_READER_AUTO_V1: readability check (before the omniReader exchange below)\n"),
    ],
    'OmniQuickMenu.h': [
        ('static bool omniSliSiteInput(const OmniFxRow& r, int b);\n',
         'static bool omniSliSiteInput(const OmniFxRow& r, int b);\n'
         'constexpr int omniRauSiteRowId = 760; // OMNI_READER_AUTO_V1 (OmniReaderAutoShell.h)\n'
         'static void omniRauSiteRow(OmniFxPanel& p, const std::string& host);\n'
         'static bool omniRauSiteInput(const OmniFxRow& r, int b);\n'),
        ('    omniStSiteRow(p, host); // OMNI_SITE_TWEAKS_V1: Page tweaks\n',
         '    omniStSiteRow(p, host); // OMNI_SITE_TWEAKS_V1: Page tweaks\n'
         '    omniRauSiteRow(p, host); // OMNI_READER_AUTO_V1: Reader view: Ask / Always for this site\n'),
        ('    if (r.id == omniSliSiteRowId) return omniSliSiteInput(r, b); // OMNI_SITE_LIST_V1\n',
         '    if (r.id == omniRauSiteRowId) return omniRauSiteInput(r, b); // OMNI_READER_AUTO_V1 (handles its disabled state)\n'
         '    if (r.id == omniSliSiteRowId) return omniSliSiteInput(r, b); // OMNI_SITE_LIST_V1\n'),
        ('static void omniDlpQuickRow(OmniFxPanel& p); // OMNI_DL_PROGRESS_V1 (OmniDlProgressShell.h)\n',
         'static void omniDlpQuickRow(OmniFxPanel& p); // OMNI_DL_PROGRESS_V1 (OmniDlProgressShell.h)\n'
         'static void omniRauQuickRow(OmniFxPanel& p); // OMNI_READER_AUTO_V1 (OmniReaderAutoShell.h)\n'
         'static bool omniRauQuickInput(const OmniFxRow& r, int b);\n'),
        ('        omniDlpQuickRow(p); // OMNI_DL_PROGRESS_V1: Downloads (n active), while the Downloads app has jobs\n',
         '        omniDlpQuickRow(p); // OMNI_DL_PROGRESS_V1: Downloads (n active), while the Downloads app has jobs\n'
         '        omniRauQuickRow(p); // OMNI_READER_AUTO_V1: Reader view, while the shown tab has an article\n'),
        ('    if (omniDlpQuickInput(r, b)) return true; // OMNI_DL_PROGRESS_V1 (before the >= 900 rows)\n',
         '    if (omniDlpQuickInput(r, b)) return true; // OMNI_DL_PROGRESS_V1 (before the >= 900 rows)\n'
         '    if (omniRauQuickInput(r, b)) return true; // OMNI_READER_AUTO_V1 (before the >= 900 rows)\n'),
    ],
    'OmniFeatures3.h': [
        ("#include \"OmniWebAppsShell.h\" // OMNI_WEB_APPS_V1 (uses the pinned tabs' close rule)\n",
         "#include \"OmniWebAppsShell.h\" // OMNI_WEB_APPS_V1 (uses the pinned tabs' close rule)\n"
         "#include \"OmniReaderAutoShell.h\" // OMNI_READER_AUTO_V1 (before OmniSiteListShell.h)\n"),
        ('    omniScTick(now);    // OMNI_SITE_CLEAR_V1_R2: native timeout of "Clear data for this site"\n',
         '    omniScTick(now);    // OMNI_SITE_CLEAR_V1_R2: native timeout of "Clear data for this site"\n'
         '    omniRauTick(now);   // OMNI_READER_AUTO_V1: an automatic Reader view open, once its tab is shown\n'),
    ],
}


def variants(old0, s):
    """The anchor with the file's own line endings (mixed files: whichever spelling is present)."""
    for e in ('\r\n', '\n'):
        old = old0.replace('\n', e)
        if s.count(old):
            return old, e
    return old0, '\n'


# r2 edits (OMNI_READER_AUTO_V1_R2). The first anchor is r1's own Tab line (replaced: the address-based guard field
# becomes the history item + the guard); a fresh apply makes the r1 edits and then these, so a fresh tree and an
# upgraded r1 tree end up byte-identical.
EDITS_R2 = {
    'OmniBrowser.cpp': [
        ('    std::string omniRauOpened; // OMNI_READER_AUTO_V1: Reader view was opened automatically for this address\n',
         '    WKRetainPtr<WKBackForwardListItemRef> omniRauItem; // OMNI_READER_AUTO_V1_R2: the history item Reader view was opened for automatically\n'
         '    OmniReaderAuto::Guard omniRauGuard; // OMNI_READER_AUTO_V1_R2: navigation type, leaving Reader view\n'),
        ('static void omniReaderStart(); // OMNI_READER_AUTO_V1: the engine Reader view (defined below)\n',
         'static void omniReaderStart(); // OMNI_READER_AUTO_V1: the engine Reader view (defined below)\n'
         'static void omniRauNavigation(Tab& tab, WKFrameNavigationType type); // OMNI_READER_AUTO_V1_R2: Back / Forward / Reload\n'),
        ('            if (omniHoPolicy(tab, action, request.get(), targetURL, listener)) return; // OMNI_HTTPS_ONLY_V1: http -> https, or the panel\n',
         '            omniRauNavigation(*tab, WKNavigationActionGetNavigationType(action)); // OMNI_READER_AUTO_V1_R2: before any early answer\n'
         '            if (omniHoPolicy(tab, action, request.get(), targetURL, listener)) return; // OMNI_HTTPS_ONLY_V1: http -> https, or the panel\n'),
    ],
}


def apply_edits(name, s, edits, mark):
    """In memory: the edits (each anchor exactly once) unless `mark` is already there."""
    if mark in s:
        return s, False
    for item in edits:
        old0, new0 = item[0], item[1]
        old, e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))
        s = s.replace(old, new0.replace('\n', e), 1)
    return s, True


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
    for need, f in (('OMNI_SITE_LIST_V1', 'OmniQuickMenu.h'), ('OMNI_DL_PROGRESS_V1', 'OmniQuickMenu.h'),
                    ('OMNI_WEB_APPS_V1', 'OmniFeatures3.h'), ('OMNI_SITE_CLEAR_V1_R2', 'OmniFeatures3.h'),
                    ('OMNI_FIND_PLUS_V1', 'OmniBrowser.cpp'), ('OMNI_HTTPS_ONLY_V1', 'OmniBrowser.cpp')):
        if need not in (root / f).read_bytes().decode('utf-8'):
            sys.exit('%s: %s missing: apply its script first' % (f, need))
    out = {}
    for name in EDITS:   # every file is patched in memory (every anchor checked) before anything is written
        s0 = (root / name).read_bytes().decode('utf-8')
        s, r1 = apply_edits(name, s0, EDITS[name], MARK)
        s, r2 = apply_edits(name, s, EDITS_R2.get(name, []), REV) if name in EDITS_R2 else (s, False)
        out[name] = (s0, s, r1, r2)
    msgs = [write_new('OmniReaderAuto.h', PURE, 'OmniAutoplay.h'),
            write_new('OmniReaderAutoShell.h', SHELL, 'OmniAutoplayShell.h')]
    for name, (s0, s, r1, r2) in out.items():
        if s != s0:
            (root / name).write_bytes(s.encode('utf-8'))
        msgs.append(name + (': applied' if r1 else ': upgraded (r2)' if r2 else ': already'))
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK + ' (r2)')


main()
