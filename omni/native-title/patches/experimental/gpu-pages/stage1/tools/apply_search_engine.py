#!/usr/bin/env python3
r"""OMNI_SEARCH_ENGINE_V1 (2026-11-16): a proper default search engine choice.

What existed (audit of state T, OMNI_FEATURES_V1 / V3 + OMNI_GOOGLE_SEARCH_V1)
  - Address bar: destination() (OmniBrowser.cpp) loads http(s):// as typed, "x.y" without spaces as https://x.y,
    anything else as a search: omniFxSearchPrefix() + its own encoding (only A-Z a-z 0-9 - _ kept). Search
    shortcuts ("yt cats", OMNI_SEARCH_TILES_V1, /data/omni/search-shortcuts.txt or built-ins) are resolved BEFORE
    that (omniStResolve on Go, and the first suggestion row) into a full https URL, so they always win.
  - Browser settings already had "Search engine" (omniFxEngines: Google = 0 = default, DuckDuckGo, Bing, Startpage;
    saved as "search\t<index>" in /data/omni/browser-settings.txt) and OMNI_FEATURES_V3's "Search suggestions"
    On/Off (default On, /data/omni/... f3 settings "suggest").
  - REMOTE SUGGESTIONS EXIST (OmniSuggest.h): 220 ms after typing stops, the typed text is sent to the engine's
    OpenSearch endpoint (Google suggestqueries / DuckDuckGo ac / Bing osjson / Startpage osuggestions) by a hidden
    WKView in the normal (persistent) data store, so the engine sees each typed query plus its cookies. Never for
    private tabs, addresses, self-test modes, or when switched off; off until restart after 3 failures. The
    default stays On (as today). The endpoint was picked by clamping the engine index into that 4-entry list.
  - Other search entry points: omni://pages search (OmniPages.h), Select text > Search (OmniTextSelectShell.h,
    a private tab searches in a private tab), the new-tab page's box (a GET form to omniFxSearchAction(), field q).
  - Quick answers (OMNI_QUICK_ANSWERS_V1) and tab search (OMNI_TAB_SEARCH_V1) are rows in the same suggestion list
    (order: shortcut row, "= answer", Switch-to-tab / Reopen rows, history, engine suggestions; 5 rows). They never
    load a search URL, and Go on the keyboard never goes through the rows; nothing there changes.

What this adds
  - Browser settings > "Search engine" steps DuckDuckGo / Google / Bing / Brave / Startpage / Ecosia / Qwant /
    Custom... (D-pad left / right; Cross steps forward). Saved indexes keep their meaning (0..3 as before, Brave 4,
    Ecosia 5, Qwant 6, Custom 7 appended), so the default is still Google and existing choices stay.
    Custom: Cross on it (or Cross landing on it with no address yet) opens the on-screen keyboard for a URL template
    with %s for the words; refused (notice says why, nothing saved) unless: https:// only, exactly one %s (after
    the host), no spaces, printable ASCII without quotes / <> / backslash / backtick / {}|^, no user:password@, a
    plain host with a dot (optional :port), every other % is %XX. Saved in /data/omni/search-custom.txt (re-checked
    on load). While Custom has no valid address, searches use Google and the row says "Custom... (not set)".
  - "Search suggestions" keeps its label (translations and settings search use it) and gains a detail:
    "as you type, from <engine>; never in private tabs", "none for a custom engine". Built-in endpoints for
    Brave / Ecosia / Qwant are added (OpenSearch format, as Firefox uses them; not tried on the console). Custom
    never sends suggestions, not even to the fallback engine. Private tabs: same engine, never any suggestions
    (unchanged rule, omniSgEligible).
  - Queries: control characters -> spaces, trimmed, at most 2000 bytes (UTF-8 boundary), UTF-8 bytes
    percent-encoded per RFC 3986 (unreserved kept, space %20): an accented e (UTF-8 C3 A9) becomes %C3%A9.

One function: omniSearchUrlFor(query) (OmniSearchEngineShell.h, declared in OmniFeaturesDecl.h) is the only place a
search URL for typed words is built: address bar, engine-suggestion rows, omni://pages search, Select text > Search
and the new-tab box (its script gets omniSearchUrlFor("omnisenq7z9x") and swaps the sentinel for the words).
Safe search (parental controls, apply_parental.py) hooks in WITHOUT editing callers: at start-up set
    omniSearchUrlHook = omniParentalSearchUrl;   // std::string(const std::string& url, const char* engineKey)
and append the engine's switch by key (google &safe=active, bing &adlt=strict, duckduckgo &kp=1, brave
&safesearch=strict, ...; "custom": its own call). Search SHORTCUTS ("g cats", "yt cats") are full URLs from
OmniSearchTiles and do not pass through it (wrap omniStResolve / the shortcut row there). The remote suggest
request is built by omniSearchSuggestUrlFor; parental should switch suggestions off (omniF3Set.suggest) rather
than rewrite that URL. Apply parental AFTER this script.

Pure part: engine/entry/OmniSearchEngine.h (table, settings order, template check + reasons, encoding, URLs, names,
the new-tab script). Tested by tools/test_search_engine.cpp:
    g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_search_engine.cpp -o t && ./t
Shell: engine/entry/OmniSearchEngineShell.h (included from OmniBrowserSettings.h in place of the three hooks).

Anchors (exactly once each, whole lines; MARK makes each file idempotent; line endings kept):
  OmniBrowserSettings.h  the Startpage line + "};" of omniFxEngines; the omniFxSearchPrefix / Action / Name lines
                         (replaced by the shell include); the "Search engine" add line (kept; apply_ui_lang.py
                         anchors on it); the omniFxSet.search stepping line + its "return true;"
  OmniFeaturesDecl.h     the omniFxSearchName declaration
  OmniBrowser.cpp        destination()'s encoding loop + return; the new-tab form's address-check line
  OmniSuggest.h          the omniSgEncode line ([[maybe_unused]]); omniSgEligible's private-tab line; omniSgStart's engine + url lines; the merge's s.url line
  OmniPages.h            the "search" action's push_back line
  OmniTextSelectShell.h  the Search action's omniFxOpenInNewTab line (apply_text_select.py's)
  OmniFeatures3.h        the "Search suggestions" add line
No new settings row ids; namespace alias OSEN, prefix omniSen (refused if the tree already has them elsewhere).
Apply AFTER apply_text_select.py (its file is an anchor) and before apply_parental.py.
usage: apply_search_engine.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_SEARCH_ENGINE_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_SEARCH_ENGINE_V1: the pure part of the default search engine (no SDL, no WebKit): the engine table, the
// settings order, custom-template validation, UTF-8 percent-encoding of queries, search / suggest URLs, the names
// shown, the new-tab page's search script. The shell side is OmniSearchEngineShell.h; the reasons are in
// tools/apply_search_engine.py. Tested on the host with g++ (test_search_engine.cpp).
#pragma once
#include <cstddef>
#include <string>

namespace OmniSearchEngine {

// Index = the number saved as "search\t<n>" in browser-settings.txt (omniFxSet.search). 0..3 are the engines Omni
// had before (same order as omniFxEngines), so saved settings keep their meaning; new engines are appended.
enum : int { kGoogle = 0, kDuckDuckGo, kBing, kStartpage, kBrave, kEcosia, kQwant, kCustom, kCount };
struct Engine {
    const char* key;       // stable id (handed to omniSearchUrlHook, e.g. for safe search)
    const char* name;
    const char* tmpl;      // search URL, %s = the query (percent-encoded)
    const char* suggest;   // OpenSearch suggest URL (answers ["q",["s1",...]]); "" = none
    const char* action;    // the new-tab page form's action (only used when scripts are off)
};
inline constexpr Engine kEngines[kCount] = {
    { "google", "Google", "https://www.google.com/search?q=%s",
      "https://suggestqueries.google.com/complete/search?client=firefox&ie=utf-8&oe=utf-8&q=%s", "https://www.google.com/search" },
    { "duckduckgo", "DuckDuckGo", "https://duckduckgo.com/?q=%s", "https://duckduckgo.com/ac/?type=list&q=%s", "https://duckduckgo.com/" },
    { "bing", "Bing", "https://www.bing.com/search?q=%s", "https://api.bing.com/osjson.aspx?query=%s", "https://www.bing.com/search" },
    { "startpage", "Startpage", "https://www.startpage.com/do/search?q=%s", "https://www.startpage.com/osuggestions?q=%s",
      "https://www.startpage.com/do/search" },
    { "brave", "Brave", "https://search.brave.com/search?q=%s", "https://search.brave.com/api/suggest?q=%s", "https://search.brave.com/search" },
    { "ecosia", "Ecosia", "https://www.ecosia.org/search?q=%s", "https://ac.ecosia.org/autocomplete?q=%s&type=list", "https://www.ecosia.org/search" },
    { "qwant", "Qwant", "https://www.qwant.com/?q=%s", "https://api.qwant.com/v3/suggest?q=%s&client=opensearch", "https://www.qwant.com/" },
    { "custom", "Custom\xE2\x80\xA6", "", "", "" },   // the user's own template (search-custom.txt); never any suggestions
};
// The order Browser settings steps through (D-pad left / right, Cross).
inline constexpr int kOrder[kCount] = { kDuckDuckGo, kGoogle, kBing, kBrave, kStartpage, kEcosia, kQwant, kCustom };
constexpr int kDefault = kGoogle;            // OMNI_GOOGLE_SEARCH_V1's default, unchanged
constexpr size_t kMaxTemplate = 512;
constexpr size_t kMaxQuery = 2000;           // bytes, cut on a UTF-8 boundary
constexpr const char* kSentinel = "omnisenq7z9x";   // encodes to itself; the new-tab script swaps it for the query

inline int clampIndex(int i) { return i < 0 || i >= kCount ? kDefault : i; }
inline int step(int cur, int dir)
{
    cur = clampIndex(cur);
    int pos = 0;
    for (int k = 0; k < kCount; ++k) if (kOrder[k] == cur) pos = k;
    pos = ((pos + (dir < 0 ? -1 : 1)) % kCount + kCount) % kCount;
    return kOrder[pos];
}

inline bool isSpace(unsigned char c) { return c == ' ' || c == '\t' || c == '\r' || c == '\n' || c == '\f' || c == '\v'; }
inline std::string trim(const std::string& v)
{
    size_t a = 0, b = v.size();
    while (a < b && isSpace((unsigned char)v[a])) ++a;
    while (b > a && isSpace((unsigned char)v[b - 1])) --b;
    return v.substr(a, b - a);
}
inline char lower(char c) { return c >= 'A' && c <= 'Z' ? char(c - 'A' + 'a') : c; }
inline bool isHex(char c) { return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F'); }

// The query as searched: control characters become spaces, the ends are trimmed, at most kMaxQuery bytes (never
// cutting a UTF-8 sequence in half). Inner spaces are kept (the engine sees "a  b" as typed).
inline std::string cleanQuery(const std::string& q)
{
    std::string s;
    s.reserve(q.size());
    for (unsigned char c : q) s += (c < 0x20 || c == 0x7f) ? ' ' : char(c);
    s = trim(s);
    if (s.size() > kMaxQuery) {
        size_t n = kMaxQuery;
        while (n > 0 && ((unsigned char)s[n] & 0xC0) == 0x80) --n;   // s[n] is the first byte dropped: back to a lead byte
        s.resize(n);
        s = trim(s);
    }
    return s;
}

// UTF-8 percent-encoding (RFC 3986): unreserved bytes kept, every other byte %XX (upper case); space is %20.
// Bytes are encoded as they are (UTF-8 text gives its UTF-8 bytes: "é" -> %C3%A9).
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

// --- custom templates ------------------------------------------------------------------------------
enum class Bad { None, Empty, TooLong, Space, NotHttps, BadChar, Credentials, BadHost, NoPlaceholder, ManyPlaceholders, BadPercent };
// What the notice says when a template is refused.
inline const char* why(Bad b)
{
    switch (b) {
    case Bad::None: return "OK";
    case Bad::Empty: return "the address is empty";
    case Bad::TooLong: return "the address is too long";
    case Bad::Space: return "the address can't contain spaces";
    case Bad::NotHttps: return "the address must start with https://";
    case Bad::BadChar: return "the address has characters that aren't allowed";
    case Bad::Credentials: return "the address can't contain a user name or password";
    case Bad::BadHost: return "the site name isn't valid (e.g. search.example.com)";
    case Bad::NoPlaceholder: return "put %s where the search words go";
    case Bad::ManyPlaceholders: return "use %s only once";
    case Bad::BadPercent: return "a % that isn't %s must be followed by two hex digits";
    }
    return "invalid";
}
// https:// only; no whitespace; printable ASCII without quotes, <>, backslash, backtick, {}|^; no credentials; a
// plain host (letters, digits, '.', '-', at least one dot, optional :port); exactly one %s, after the host; every
// other '%' is %XX.
inline Bad check(const std::string& t)
{
    if (t.empty()) return Bad::Empty;
    if (t.size() > kMaxTemplate) return Bad::TooLong;
    for (unsigned char c : t) if (isSpace(c)) return Bad::Space;
    std::string scheme;
    for (size_t i = 0; i < t.size() && i < 8; ++i) scheme += lower(t[i]);
    if (scheme != "https://") return Bad::NotHttps;
    for (unsigned char c : t)
        if (c < 0x21 || c > 0x7e || c == '"' || c == '\'' || c == '<' || c == '>' || c == '\\' || c == '`' || c == '{' || c == '}' || c == '|' || c == '^')
            return Bad::BadChar;
    const size_t hs = 8, he = t.find_first_of("/?#", hs);
    const std::string auth = t.substr(hs, he == std::string::npos ? std::string::npos : he - hs);
    if (auth.find('@') != std::string::npos) return Bad::Credentials;
    std::string host = auth, port;
    const size_t colon = auth.find(':');
    if (colon != std::string::npos) {
        host = auth.substr(0, colon); port = auth.substr(colon + 1);
        if (port.empty() || port.size() > 5) return Bad::BadHost;
        for (char c : port) if (c < '0' || c > '9') return Bad::BadHost;
    }
    if (host.empty() || host.find('.') == std::string::npos || host.front() == '.' || host.back() == '.' || host.front() == '-'
        || host.find("..") != std::string::npos)
        return Bad::BadHost;
    for (char c : host) {
        const char l = lower(c);
        if (!((l >= 'a' && l <= 'z') || (l >= '0' && l <= '9') || l == '.' || l == '-')) return Bad::BadHost;
    }
    int found = 0;
    for (size_t i = he == std::string::npos ? t.size() : he; i < t.size(); ++i) {
        if (t[i] != '%') continue;
        if (i + 1 < t.size() && t[i + 1] == 's') { ++found; ++i; continue; }
        if (i + 2 < t.size() && isHex(t[i + 1]) && isHex(t[i + 2])) { i += 2; continue; }
        return Bad::BadPercent;
    }
    if (found == 0) return Bad::NoPlaceholder;
    if (found > 1) return Bad::ManyPlaceholders;
    return Bad::None;
}
inline bool validTemplate(const std::string& t) { return check(t) == Bad::None; }

// The template with its (single) %s replaced by `encoded`.
inline std::string fill(const std::string& tmpl, const std::string& encoded)
{
    const size_t p = tmpl.find("%s");
    if (p == std::string::npos) return tmpl;
    return tmpl.substr(0, p) + encoded + tmpl.substr(p + 2);
}
// The part before %s (the old "prefix" hook: only right for templates that end in %s).
inline std::string prefixOf(const std::string& tmpl)
{
    const size_t p = tmpl.find("%s");
    return p == std::string::npos ? tmpl : tmpl.substr(0, p);
}
// Host of a template (lower case, without port and a leading "www."): "" when there is none.
inline std::string hostOf(const std::string& tmpl)
{
    if (tmpl.size() < 9) return std::string();
    const size_t e = tmpl.find_first_of("/?#:", 8);
    std::string h;
    for (char c : tmpl.substr(8, e == std::string::npos ? std::string::npos : e - 8)) h += lower(c);
    if (h.compare(0, 4, "www.") == 0 && h.find('.', 4) != std::string::npos) h = h.substr(4);
    return h;
}

// --- choosing ----------------------------------------------------------------------------------------
// The engine searches actually use: Google in self-test modes (as before) and while Custom has no valid template.
inline int effective(int stored, bool customValid, bool testMode)
{
    if (testMode) return kGoogle;
    stored = clampIndex(stored);
    return stored == kCustom && !customValid ? kDefault : stored;
}
inline std::string templateFor(int e, const std::string& custom)
{
    e = clampIndex(e);
    if (e == kCustom) return validTemplate(custom) ? custom : std::string(kEngines[kDefault].tmpl);
    return kEngines[e].tmpl;
}
// The search URL for what the user typed (the engine as returned by effective()).
inline std::string urlFor(int e, const std::string& custom, const std::string& query)
{
    return fill(templateFor(e, custom), encode(cleanQuery(query)));
}
// The suggest template of the STORED engine ("" when it has none: Custom never sends suggestions, not even to the
// fallback engine, since the user chose not to use the built-in ones).
inline std::string suggestTemplate(int stored)
{
    stored = clampIndex(stored);
    return stored == kCustom ? std::string() : std::string(kEngines[stored].suggest);
}
inline std::string suggestUrlFor(int stored, const std::string& query)
{
    const std::string t = suggestTemplate(stored);
    return t.empty() ? std::string() : fill(t, encode(cleanQuery(query)));
}
inline std::string actionFor(int e, const std::string& custom)
{
    e = clampIndex(e);
    if (e != kCustom) return kEngines[e].action;
    const std::string t = templateFor(e, custom);
    return t.substr(0, t.find_first_of("?#"));
}
// "Google", ... or the custom template's site ("search.example.org"); used in "Search X or type an address".
inline std::string shortName(int e, const std::string& custom)
{
    e = clampIndex(e);
    if (e != kCustom) return kEngines[e].name;
    const std::string h = validTemplate(custom) ? hostOf(custom) : std::string();
    return h.empty() ? std::string(kEngines[kDefault].name) : h;
}
// Browser settings > "Search engine" value (the STORED choice).
inline std::string displayName(int stored, const std::string& custom)
{
    stored = clampIndex(stored);
    if (stored != kCustom) return kEngines[stored].name;
    return validTemplate(custom) ? "Custom: " + hostOf(custom) : std::string("Custom\xE2\x80\xA6 (not set)");
}
// Browser settings > "Search suggestions" detail text.
inline std::string suggestNote(int stored, bool on)
{
    stored = clampIndex(stored);
    if (stored == kCustom) return "none for a custom engine";
    if (suggestTemplate(stored).empty()) return std::string("none for ") + kEngines[stored].name;
    if (!on) return std::string();
    return std::string("as you type, from ") + kEngines[stored].name + "; never in private tabs";
}

// --- new-tab page -------------------------------------------------------------------------------------------
// The search part of the new-tab form's onsubmit (inside a double-quoted HTML attribute, after the address checks):
// `url` is omniSearchUrlFor(kSentinel), so wrappers (safe search) apply; the script puts the typed words in place of
// the sentinel. Characters that could end the JS string or the attribute are percent-encoded; & is &amp;.
inline std::string formScript(const std::string& url)
{
    std::string u;
    for (char c : url) {
        switch (c) {
        case '&': u += "&amp;"; break;
        case '\'': u += "%27"; break;
        case '"': u += "%22"; break;
        case '<': u += "%3C"; break;
        case '>': u += "%3E"; break;
        case '\\': u += "%5C"; break;
        case '\n': case '\r': break;
        default: u += c;
        }
    }
    return std::string("if(v){location.href='") + u + "'.split('" + kSentinel + "').join(encodeURIComponent(v));return false}";
}

} // namespace OmniSearchEngine
'''

SHELL = r'''// OMNI_SEARCH_ENGINE_V1: the shell side of the default search engine (included from OmniBrowserSettings.h where the
// omniFxSearchPrefix / Action / Name hooks were). The pure part is OmniSearchEngine.h; the reasons are in
// tools/apply_search_engine.py.
//   omniSearchUrlFor(query)     THE search URL for typed words (address bar, suggestion rows, omni://pages search,
//                               Select text > Search, the new-tab page box). Wrappers hook in through
//                               omniSearchUrlHook (e.g. parental controls' safe search), never by editing callers.
//   omniSearchSuggestUrlFor(q)  the stored engine's suggest URL ("" when it has none: Custom).
// The custom template is /data/omni/search-custom.txt (one line, validated on load and on entry).
#pragma once
#include "OmniSearchEngine.h"
namespace OSEN = OmniSearchEngine;
static_assert(omniFxEngineCount == OSEN::kCount, "omniFxEngines and OmniSearchEngine.h list the same engines");

static std::string omniSenCustomTmpl;
static bool omniSenCustomLoaded = false;
static const std::string& omniSenCustom()
{
    if (!omniSenCustomLoaded) {
        omniSenCustomLoaded = true;
        if (FILE* f = fopen(omniData("search-custom.txt").c_str(), "r")) {
            char line[OSEN::kMaxTemplate + 8] = {};
            if (fgets(line, sizeof line, f)) {
                const std::string t = OSEN::trim(line);
                if (OSEN::validTemplate(t)) omniSenCustomTmpl = t;
                else fprintf(stderr, "OMNI SEARCH ENGINE: search-custom.txt ignored (%s)\n", OSEN::why(OSEN::check(t)));
            }
            fclose(f);
        }
    }
    return omniSenCustomTmpl;
}
static void omniSenCustomSet(const std::string& t)
{
    omniSenCustomTmpl = t; omniSenCustomLoaded = true;
    omniIoQueue(omniData("search-custom.txt"), t + "\n", false);
}
static int omniSenStored() { omniFxLoad(); return OSEN::clampIndex(omniFxSet.search); }
static int omniSenEffective() { return OSEN::effective(omniSenStored(), !omniSenCustom().empty(), omniTestMode()); }

// The wrap point: when set, every search URL omniSearchUrlFor builds goes through it (url, engine key "google",
// "duckduckgo", "bing", "startpage", "brave", "ecosia", "qwant" or "custom") and its result is loaded instead.
static std::string (*omniSearchUrlHook)(const std::string& url, const char* engineKey) = nullptr;
static std::string omniSearchUrlFor(const std::string& query)
{
    const int e = omniSenEffective();
    std::string url = OSEN::urlFor(e, omniSenCustom(), query);
    if (omniSearchUrlHook) url = omniSearchUrlHook(url, OSEN::kEngines[e].key);
    return url;
}
static bool omniSearchSuggestAvailable() { return !omniTestMode() && !OSEN::suggestTemplate(omniSenStored()).empty(); }
static std::string omniSearchSuggestUrlFor(const std::string& q)
{
    return omniSearchSuggestAvailable() ? OSEN::suggestUrlFor(omniSenStored(), q) : std::string();
}
// The OMNI_FEATURES_V1 hooks (OmniFeaturesDecl.h), now from the table. omniFxSearchPrefix is only right for templates
// ending in %s; nothing in Omni calls it any more (omniSearchUrlFor instead).
[[maybe_unused]] static std::string omniFxSearchPrefix() { return OSEN::prefixOf(OSEN::templateFor(omniSenEffective(), omniSenCustom())); }
static std::string omniFxSearchAction() { return OSEN::actionFor(omniSenEffective(), omniSenCustom()); }
static std::string omniFxSearchName() { return OSEN::shortName(omniSenEffective(), omniSenCustom()); }
static std::string omniSenFormScript() { return OSEN::formScript(omniSearchUrlFor(OSEN::kSentinel)); }   // new-tab page box

// --- Browser settings -------------------------------------------------------------------------------
static std::string omniSenRowValue() { return OSEN::displayName(omniSenStored(), omniSenCustom()); }
static std::string omniSenSuggestDetail(bool on) { return OSEN::suggestNote(omniSenStored(), on); }
static std::string omniSenEdit;
static void omniSenEditCustom()
{
    omniSenEdit = omniSenCustom().empty() ? std::string("https://") : omniSenCustom();
    omniKbEdit(&omniSenEdit, "Custom search address, %s = the words (https://...?q=%s)", [](bool ok) {
        if (!ok) { omniFxRefresh(); return; }
        const std::string t = OSEN::trim(omniSenEdit);
        const OSEN::Bad bad = OSEN::check(t);
        if (bad != OSEN::Bad::None) { notice(std::string("Custom search not saved: ") + OSEN::why(bad)); omniFxRefresh(); return; }
        omniSenCustomSet(t);
        omniFxSet.search = OSEN::kCustom; omniFxSave();
        omniSuggestFor = "\x01";
        omniFxRefresh();
        notice("Searching with " + OSEN::hostOf(t));
    });
}
// "Search engine" row: D-pad left / right step through the engines; Cross steps forward, except on Custom (and when
// it lands on a Custom that has no address yet), where it opens the keyboard for the template.
static bool omniSenSettingsInput(int dir, bool cross)
{
    if (!dir) return false;
    const int cur = omniSenStored();
    if (cross && cur == OSEN::kCustom) { omniSenEditCustom(); return true; }
    const int next = OSEN::step(cur, dir);
    omniFxSet.search = next; omniFxSave();
    omniSuggestFor = "\x01";   // suggestion rows are rebuilt with the new engine
    if (next == OSEN::kCustom && omniSenCustom().empty()) {
        if (cross) omniSenEditCustom();
        else notice("Custom search: press Cross to enter its address (Google is used until then)");
    }
    return true;
}
'''

EDITS = {
    'OmniBrowserSettings.h': [
        ('    { "Startpage", "https://www.startpage.com/do/search", "https://www.startpage.com/do/search?q=" },\n'
         '};\n',
         '    { "Startpage", "https://www.startpage.com/do/search", "https://www.startpage.com/do/search?q=" },\n'
         '    { "Brave", "https://search.brave.com/search", "https://search.brave.com/search?q=" }, // OMNI_SEARCH_ENGINE_V1: 4..7 appended (saved indexes keep their meaning); OmniSearchEngine.h is the table\n'
         '    { "Ecosia", "https://www.ecosia.org/search", "https://www.ecosia.org/search?q=" },\n'
         '    { "Qwant", "https://www.qwant.com/", "https://www.qwant.com/?q=" },\n'
         r'    { "Custom\xE2\x80\xA6", "", "" }, // OMNI_SEARCH_ENGINE_V1: the template in search-custom.txt' '\n'
         '};\n'),
        ('static std::string omniFxSearchPrefix() { if (omniTestMode()) return omniFxEngines[0].prefix; omniFxLoad(); return omniFxEngines[omniFxSet.search].prefix; }\n'
         'static std::string omniFxSearchAction() { omniFxLoad(); return omniFxEngines[omniFxSet.search].action; }\n'
         'static std::string omniFxSearchName() { omniFxLoad(); return omniFxEngines[omniFxSet.search].name; }\n',
         '#include "OmniSearchEngineShell.h" // OMNI_SEARCH_ENGINE_V1: omniSearchUrlFor + the omniFxSearchPrefix / Action / Name hooks\n'),
        ('    add(omniFxSetSearch, "Search engine", omniFxEngines[omniFxSet.search].name, true);\n',
         '    add(omniFxSetSearch, "Search engine", omniFxEngines[omniFxSet.search].name, true);\n'
         '    p.rows.back().value = omniSenRowValue(); // OMNI_SEARCH_ENGINE_V1: "Custom: <site>" / "Custom... (not set)"\n'),
        ('        omniFxSet.search = (omniFxSet.search + dir + omniFxEngineCount) % omniFxEngineCount; omniFxSave();\n'
         '        return true;\n',
         '        return omniSenSettingsInput(dir, a); // OMNI_SEARCH_ENGINE_V1: settings order; Cross on Custom edits its address\n'),
    ],
    'OmniFeaturesDecl.h': [
        ('static std::string omniFxSearchName();                         // "Google", "DuckDuckGo", ...\n',
         'static std::string omniFxSearchName();                         // "Google", "DuckDuckGo", ...\n'
         'static std::string omniSearchUrlFor(const std::string& query); // OMNI_SEARCH_ENGINE_V1: THE search URL for typed words (OmniSearchEngineShell.h)\n'
         'static std::string omniSenFormScript();                        // OMNI_SEARCH_ENGINE_V1: the new-tab box\'s search script\n'),
    ],
    'OmniBrowser.cpp': [
        ('    std::string encoded;\n'
         '    for (unsigned char c : value) {\n'
         "        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '-' || c == '_') encoded += c;\n"
         '        else { char hex[4]; snprintf(hex, sizeof(hex), "%%%02X", c); encoded += hex; }\n'
         '    }\n'
         '    return omniFxSearchPrefix() + encoded; // OMNI_GOOGLE_SEARCH_V1 (was DuckDuckGo) OMNI_FEATURES_V1: engine setting (Google default)\n',
         '    return omniSearchUrlFor(value); // OMNI_SEARCH_ENGINE_V1: the chosen engine, UTF-8 percent-encoded (was omniFxSearchPrefix() + encoded; OMNI_GOOGLE_SEARCH_V1 / OMNI_FEATURES_V1)\n'),
        (r'''        "if(/^https?:\\/\\//i.test(v)){location.href=v;return false}if(v&&v.indexOf(' ')<0&&/^[^\\s\\/]+\\.[a-z]{2,}(\\/.*)?$/i.test(v)){location.href='https://'+v;return false}\">"''' '\n',
         r'''        "if(/^https?:\\/\\//i.test(v)){location.href=v;return false}if(v&&v.indexOf(' ')<0&&/^[^\\s\\/]+\\.[a-z]{2,}(\\/.*)?$/i.test(v)){location.href='https://'+v;return false}"''' '\n'
         '        + omniSenFormScript() + "\\">" // OMNI_SEARCH_ENGINE_V1: words go through omniSearchUrlFor (custom templates, wrappers)\n'),
    ],
    'OmniSuggest.h': [
        ('static std::string omniSgEncode(const std::string& v)\n',
         '[[maybe_unused]] static std::string omniSgEncode(const std::string& v) // OMNI_SEARCH_ENGINE_V1: no caller left (OmniSearchEngine.h encodes)\n'),
        ('    if (!active() || active()->omniPrivate) return false;\n',
         '    if (!omniSearchSuggestAvailable()) return false;   // OMNI_SEARCH_ENGINE_V1: this engine has no suggestions (Custom)\n'
         '    if (!active() || active()->omniPrivate) return false;\n'),
        ('    const int engine = std::clamp(omniFxSet.search, 0, int(sizeof(omniSgEndpoints) / sizeof(omniSgEndpoints[0])) - 1);\n'
         '    const std::string url = std::string(omniSgEndpoints[engine]) + omniSgEncode(q);\n',
         '    const std::string url = omniSearchSuggestUrlFor(q);   // OMNI_SEARCH_ENGINE_V1: the stored engine\'s endpoint (OmniSearchEngine.h; omniSgEndpoints unused)\n'),
        ('            OmniSuggestion s; s.url = omniFxSearchPrefix() + omniSgEncode(r); s.title = r; s.search = true;\n',
         '            OmniSuggestion s; s.url = omniSearchUrlFor(r); s.title = r; s.search = true;   // OMNI_SEARCH_ENGINE_V1\n'),
    ],
    'OmniPages.h': [
        ('        omniPagesQueue.push_back({ omniPagesActLoad, page, omniFxSearchPrefix() + omniPercentEncode(q) });\n',
         '        omniPagesQueue.push_back({ omniPagesActLoad, page, omniSearchUrlFor(q) }); // OMNI_SEARCH_ENGINE_V1\n'),
    ],
    'OmniTextSelectShell.h': [
        ('        omniFxOpenInNewTab(omniFxSearchPrefix() + OTSL::encode(q), false, false);   // private tabs search in a private tab\n',
         '        omniFxOpenInNewTab(omniSearchUrlFor(q), false, false);   // private tabs search in a private tab; OMNI_SEARCH_ENGINE_V1: the chosen engine\n'),
    ],
    'OmniFeatures3.h': [
        ('    add(omniF3SetSuggest, "Search suggestions", omniF3Set.suggest ? "On" : "Off", true);\n',
         '    add(omniF3SetSuggest, "Search suggestions", omniF3Set.suggest ? "On" : "Off", true);\n'
         '    p.rows.back().detail = omniSenSuggestDetail(omniF3Set.suggest); // OMNI_SEARCH_ENGINE_V1: where they go, or none for this engine\n'),
    ],
}

# Names this script introduces: refused when the tree already has them in a file this script has not patched.
TAKEN = re.compile(r'OmniSearchEngine|namespace OSEN\b|\bOSEN::|omniSearchUrlFor|omniSearchUrlHook|omniSearchSuggest|\bomniSen[A-Z]')
OWN = ('OmniSearchEngine.h', 'OmniSearchEngineShell.h')


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


# The Controls guide's table names other patches' handlers by design: never a name clash (numbers still count there).
GUIDE = ('OmniControlsHelp.h', 'OmniControlsHelpShell.h')
_CPP_TOK = re.compile(r'//[^\n]*|/\*.*?\*/|R"([^()\\\s"]{0,16})\(.*?\)\1"|"(?:\\.|[^"\\\n])*"' + r"|'(?:\\.|[^'\\\n])*'", re.S)


def cpp_code(s):
    """C/C++ text without its // and /* */ comments (string, char and raw string literals kept; newlines kept, so line
    numbers stay): an id or name in another patch's notes (e.g. "834-839" in a generated header) is not a use."""
    return _CPP_TOK.sub(lambda m: m.group(0) if m.group(0)[0] in 'R"\'' else '\n' * m.group(0).count('\n'), s)


def collisions():
    if MARK in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8'):   # OMNI_RERUN_SAFE: already applied; later patches call omniSearchUrlFor on purpose
        return
    bad = []
    for f in sorted(root.iterdir()):
        if not f.is_file() or f.name in OWN or f.name in GUIDE or f.suffix not in ('.h', '.cpp'):
            continue
        s = f.read_bytes().decode('utf-8', 'replace')
        if MARK in s:
            continue
        bad += ['%s: %s' % (f.name, m) for m in sorted(set(TAKEN.findall(cpp_code(s))))]
    if bad:
        sys.exit('names already taken (refusing): ' + '; '.join(bad[:6]))


def main():
    if 'OMNI_TEXT_SELECT_V1' not in (root / 'OmniTextSelectShell.h').read_bytes().decode('utf-8'):
        sys.exit('OmniTextSelectShell.h: OMNI_TEXT_SELECT_V1 missing: apply_text_select.py first')
    collisions()
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniSearchEngine.h', PURE, 'OmniBrowserSettings.h'),
            write_new('OmniSearchEngineShell.h', SHELL, 'OmniBrowserSettings.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
