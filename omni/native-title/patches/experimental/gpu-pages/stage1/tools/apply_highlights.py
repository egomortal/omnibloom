#!/usr/bin/env python3
"""OMNI_HIGHLIGHTS_V1 (2026-11-16): highlight passages of a page; they come back (yellow) whenever the page is shown
again, and the "Highlights" panel lists them.

What the user sees
  - Select text (OMNI_TEXT_SELECT_V1: hold Cross on a word > "Select text", D-pad extends), Cross: the "Selected text"
    panel now ends with a fifth row "Highlight" (after Copy / Search for / Paste into address bar / Show as QR code).
    Cross on it: the selection turns into a yellow highlight (<mark class="omni-hl">, background #ffe45c, dark text,
    set through element.style with !important so page CSS can't hide it and a page CSP can't block it) and a notice
    "Highlighted: Options > Browse > Highlights lists it" (+ " (the first 1,600 bytes)" for a longer selection).
  - Every later load of that page (same address without its #fragment and tracking parameters) re-applies its
    highlights after the page finished loading. A passage that can't be found is skipped silently (the page changed);
    the script looks once more 2 s later (pages that build their text late).
  - Options > Browse > "Highlights" (value: how many): pages newest first (the page's title; site . N highlights; date
    of the newest), under each page its highlights newest first ("quoted text"; date).
      Cross on a highlight: the page opens in this tab (or stays, when this tab shows it) and scrolls to the passage
        ("That passage wasn't found on the page any more" when it can't be found).
      Cross on a page row: the page opens.
      Square on a highlight: deleted at once (marks disappear from open tabs showing the page).
      Square on a page row: "Delete N highlights on this page?" (asks), then all of them.
      Circle: back.
  - Reader view: works. It loads with the page's own address (WKPageLoadHTMLString with the page URL as base), so the
    page's highlights are re-applied to the reader text and highlights made there are stored for the page (matching
    ignores whitespace, so the reader's different line breaks don't matter).
  - Reading-list saved copies: work. They are about:blank documents with a CSP "script-src 'none'"; a CSP never
    applies to the shell's WKPageEvaluateJavaScriptInMainFrame (it does not go through the page's script loading) and
    the scripts here use no eval / new Function / inline handlers. For an about:blank tab the shell first asks the page
    for the "Open live page" link of the saved copy's banner (#omni-saved-banner; excluded from matching) and then
    applies / stores the highlights of that live address.

Private tabs (decided)
  - Highlighting in a private tab marks the passage on that page for this visit only; nothing is stored, nothing is
    written ("Highlighted on this page only: private tabs don't save highlights"; the row's value says "This visit
    only").
  - Saved highlights ARE re-applied in private tabs: it only reads the store (no write, no history), so the page looks
    the same as in a normal tab.

Store: /data/omni/highlights.json (omniIoQueue, whole file; nothing written in test mode), read once on first use
(2 MB cap). {"omni-highlights":1,"items":[{"id","at","url","title","p","e","s"}, ...]} one item per line.
  url    normalised: http / https only, scheme and host lower-case, user:password@ and default ports dropped, empty
         path = "/", #fragment dropped, tracking parameters dropped (utm_*, fbclid, gclid, dclid, gbraid, wbraid,
         msclkid, yclid, twclid, ttclid, igshid, mc_cid, mc_eid, _ga, _gl, _hsenc, _hsmi, mkt_tok, oly_anon_id,
         oly_enc_id, vero_id, si, ref_src; names case-insensitive), at most 2048 bytes (longer: not stored).
  e/p/s  the W3C TextQuoteSelector idea: exact text (whitespace collapsed, at most 1,600 bytes: a longer selection is
         cut there and only that part is highlighted), ~32 characters of prefix / suffix context (at most 128 bytes
         each); title at most 160 bytes: an item's text is at most 2 KB.
  Caps: 500 highlights (a new one is refused with a notice when full; a larger file keeps the newest 500).

The page script (ONE function, OmniHighlights::kScript; ops: a apply, c create, r remove, l live address of a saved
copy). Text model: every Text node under <body> (not in script / style / noscript / textarea / template / select /
option / the saved-copy banner) concatenated; matching runs on that text WITHOUT whitespace and zero-width / soft-hyphen
characters, so line breaks, block boundaries and reflow don't matter. Each quote: every occurrence of the exact text is
scored by how many prefix characters (backwards) and suffix characters (forwards) agree; the best wins (ties: the
first). The matched run is mapped back to text-node offsets and wrapped per text node (splitText + <mark>), skipping
whitespace-only pieces and non-HTML parents (SVG text); segments of different highlights that overlap in one node are
skipped. Already present marks (data-omni-hl = id) are not wrapped again, so re-applying is idempotent. Page text
reaches the script only as JSON (OmniHighlights::jsonEscape: quotes, backslashes, controls, U+2028 / U+2029 escaped;
invalid UTF-8 becomes U+FFFD); the shell parses answers with its own JSON reader.

Pure part: engine/entry/OmniHighlights.h (no SDL / WebKit): JSON reader / escaper, URL normalisation, store parse /
serialize / caps, page script + argument builders, answer parsing, panel groups and texts.
Shell part: engine/entry/OmniHighlightsShell.h (namespace alias OHLT; functions omniHlt*), included from
OmniFeatures3.h after OmniTextSelectShell.h.
Ids: Options tile 425 (reading list 420 / 421); "Selected text" panel row 20 (text select's rows are 1..4).
Anchors (each exactly once, whole lines, CRLF kept; MARK makes each file idempotent):
  OmniBrowser.cpp        the OmniTextSelect.h include line (pure include after it); 'void finished(WKPageRef page, ...'
                         (declaration before it); the omniEverydayFinished(tab) line in finished() (re-apply after it)
  OmniFeatures3.h        the OmniTextSelectShell.h include line (shell include after it)
  OmniQuickMenu.h        the omniRlQuickAction declaration, the omniRlQuickTiles(p) line, the reading list's Browse
                         group case line, the omniRlQuickAction(r.id) dispatch line (all apply_reading_list.py's)
  OmniTextSelectShell.h  'static void omniTslActionsBuild(OmniFxPanel& p)' (declarations before), its row loop (the
                         Highlight row after it), omniTslActionsInput's 'const std::string text = p.text;' line (the
                         Highlight action before it). Apply AFTER apply_text_select.py and apply_reading_list.py.
Tests: tools/test_highlights.cpp (g++, pure part; --emit <dir> writes the page script and built calls for node),
tools/test_highlights_js.cjs <dir> (node: apply / create / remove / live on a small fake DOM).
r2 (OMNI_HIGHLIGHTS_V1_R2, REV; review fixes):
  - Op 'l' (and the 'c' answer's live address) only in a tab where the reading list itself loaded the saved copy:
    Tab::omniHltSaved (OmniBrowser.cpp, before the OMNI_TAB_AUDIO_V1 omniTaMuted field) is set to 1 in
    OmniReadingListShell.h just before WKPageLoadHTMLString; omniHltFinished turns it into 2 for that about:blank load
    and clears it on every other finished load. Never in private tabs. Before: any about:blank page (a site's
    window.open + a planted #omni-saved-banner) got another address's highlights injected (readable by the site).
  - File size: addChecked refuses an item that would push the serialized file past kMaxFileBytes ("Highlights full");
    parseFile reports an unreadable file (too large / not JSON / no items array): the shell keeps a
    highlights.json.bad copy and sets omniHltLoadFailed, which blocks every write this run (no silent overwrite).
  - omniHltFocus and query answers are matched by Tab::omniMediaIdentity (never reused), not a raw Tab*.
  Fresh trees get r1 + r2; an r1 tree is upgraded (headers rewritten, the two r2 lines added); both inserts go before
  their anchors so either path gives the same bytes.
usage: apply_highlights.py <engine tree>   (anchored, idempotent, keeps CRLF)
"""
import sys
from pathlib import Path

MARK = 'OMNI_HIGHLIGHTS_V1'
REV = 'OMNI_HIGHLIGHTS_V1_R2'   # r2: saved-copy banner only in reading-list tabs, file size cap / unreadable file kept
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_HIGHLIGHTS_V1: the pure part of highlights (no SDL, no WebKit): the store (/data/omni/highlights.json) parse /
// serialize and caps, URL normalisation (no #fragment, no tracking parameters), a small JSON reader and escaper, the
// page script (apply / create / remove / live address) and its arguments, answer parsing, the panel's groups and texts.
// Shell side: OmniHighlightsShell.h; reasons in tools/apply_highlights.py. Tested on the host with g++
// (tools/test_highlights.cpp) and node (tools/test_highlights_js.cjs).
// OMNI_HIGHLIGHTS_V1_R2: parseFile (an unreadable file is reported, never silently empty), addChecked (the file stays
// under kMaxFileBytes).
#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <string>
#include <utility>
#include <vector>

namespace OmniHighlights {

static const char* const kFileName = "highlights.json";   // in /data/omni (omniData)
constexpr size_t kMaxItems = 500;            // highlights kept (a new one is refused when full)
constexpr size_t kExactMaxBytes = 1600;      // the highlighted text (the page script cuts there too: EM)
constexpr size_t kContextMaxBytes = 128;     // prefix / suffix each (the script sends ~32 characters)
constexpr size_t kTitleMaxBytes = 160;
constexpr size_t kItemMaxBytes = 2048;       // exact + prefix + suffix + title
constexpr size_t kUrlMaxBytes = 2048;        // a longer normalised address is not stored
constexpr long kMaxFileBytes = 2L << 20;     // read cap of the file
constexpr int kTileList = 425;               // Options > Browse "Highlights" (reading list 420 / 421)
constexpr int kActionId = 20;                // "Selected text" panel row (OMNI_TEXT_SELECT_V1's rows are 1..4)

struct Item {
    long long id = 0, at = 0;                // at: seconds since 1970
    std::string url, title, exact, prefix, suffix;
};

// --- UTF-8 --------------------------------------------------------------------------------------------------------
// The length of the valid UTF-8 sequence at s[i] (0: invalid: bad lead, truncated, overlong, surrogate, > U+10FFFF).
inline size_t decode(const std::string& s, size_t i, uint32_t& cp)
{
    const unsigned char c = static_cast<unsigned char>(s[i]);
    if (c < 0x80) { cp = c; return 1; }
    size_t n;
    uint32_t min;
    if ((c & 0xE0) == 0xC0) { n = 2; cp = c & 0x1F; min = 0x80; }
    else if ((c & 0xF0) == 0xE0) { n = 3; cp = c & 0x0F; min = 0x800; }
    else if ((c & 0xF8) == 0xF0) { n = 4; cp = c & 0x07; min = 0x10000; }
    else return 0;
    if (i + n > s.size()) return 0;
    for (size_t k = 1; k < n; ++k) {
        const unsigned char d = static_cast<unsigned char>(s[i + k]);
        if ((d & 0xC0) != 0x80) return 0;
        cp = (cp << 6) | (d & 0x3F);
    }
    if (cp < min || cp > 0x10FFFF || (cp >= 0xD800 && cp <= 0xDFFF)) return 0;
    return n;
}
inline void appendUtf8(std::string& o, uint32_t cp)
{
    if (cp < 0x80) o += char(cp);
    else if (cp < 0x800) { o += char(0xC0 | (cp >> 6)); o += char(0x80 | (cp & 0x3F)); }
    else if (cp < 0x10000) { o += char(0xE0 | (cp >> 12)); o += char(0x80 | ((cp >> 6) & 0x3F)); o += char(0x80 | (cp & 0x3F)); }
    else { o += char(0xF0 | (cp >> 18)); o += char(0x80 | ((cp >> 12) & 0x3F)); o += char(0x80 | ((cp >> 6) & 0x3F)); o += char(0x80 | (cp & 0x3F)); }
}
// Valid UTF-8: each invalid byte becomes U+FFFD.
inline std::string sanitize(const std::string& s)
{
    std::string o;
    o.reserve(s.size());
    for (size_t i = 0; i < s.size();) {
        uint32_t cp;
        const size_t n = decode(s, i, cp);
        if (!n) { appendUtf8(o, 0xFFFD); ++i; continue; }
        o.append(s, i, n);
        i += n;
    }
    return o;
}
// The longest prefix of at most max bytes that does not split a sequence.
inline std::string utf8Cut(const std::string& s, size_t max)
{
    if (s.size() <= max) return s;
    size_t n = max;
    while (n > 0 && (static_cast<unsigned char>(s[n]) & 0xC0) == 0x80) --n;
    return s.substr(0, n);
}
// The longest suffix of at most max bytes that starts on a character.
inline std::string utf8Tail(const std::string& s, size_t max)
{
    if (s.size() <= max) return s;
    size_t i = s.size() - max;
    while (i < s.size() && (static_cast<unsigned char>(s[i]) & 0xC0) == 0x80) ++i;
    return s.substr(i);
}
// Whitespace runs (ASCII controls and spaces, U+00A0, U+2028 / U+2029) become one space; trimmed.
inline std::string collapse(const std::string& s)
{
    std::string out;
    bool space = false;
    for (size_t i = 0; i < s.size(); ++i) {
        const unsigned char c = static_cast<unsigned char>(s[i]);
        size_t skip = 0;
        if (c <= 0x20 || c == 0x7F) skip = 1;
        else if (c == 0xC2 && i + 1 < s.size() && static_cast<unsigned char>(s[i + 1]) == 0xA0) skip = 2;
        else if (c == 0xE2 && i + 2 < s.size() && static_cast<unsigned char>(s[i + 1]) == 0x80
                 && (static_cast<unsigned char>(s[i + 2]) == 0xA8 || static_cast<unsigned char>(s[i + 2]) == 0xA9)) skip = 3;
        if (skip) { space = !out.empty(); i += skip - 1; continue; }
        if (space) { out += ' '; space = false; }
        out += char(c);
    }
    return out;
}

// --- JSON ---------------------------------------------------------------------------------------------------------
// A JSON string literal (quotes included): valid UTF-8 out, ", \ and controls escaped, U+2028 / U+2029 escaped (so the
// text is also a safe JavaScript literal), invalid bytes as U+FFFD. Page text spliced into a script goes through here.
inline std::string jsonEscape(const std::string& s)
{
    static const char* const hex = "0123456789abcdef";
    std::string o = "\"";
    for (size_t i = 0; i < s.size();) {
        uint32_t cp;
        const size_t n = decode(s, i, cp);
        if (!n) { o += "\\ufffd"; ++i; continue; }
        i += n;
        switch (cp) {
        case '"': o += "\\\""; break;
        case '\\': o += "\\\\"; break;
        case '\n': o += "\\n"; break;
        case '\r': o += "\\r"; break;
        case '\t': o += "\\t"; break;
        case 0x2028: o += "\\u2028"; break;
        case 0x2029: o += "\\u2029"; break;
        default:
            if (cp < 0x20 || cp == 0x7F) { o += "\\u00"; o += hex[cp >> 4]; o += hex[cp & 15]; }
            else appendUtf8(o, cp);
        }
    }
    return o + "\"";
}

struct Json {
    enum Kind { Null, Bool, Num, Str, Arr, Obj } kind = Null;
    bool b = false;
    double num = 0;
    std::string str;
    std::vector<Json> arr;                   // Arr items; Obj values (keys in `keys`)
    std::vector<std::string> keys;
    const Json* get(const std::string& k) const
    {
        if (kind != Obj) return nullptr;
        for (size_t i = 0; i < keys.size(); ++i) if (keys[i] == k) return &arr[i];
        return nullptr;
    }
    std::string s(const std::string& k) const { const Json* v = get(k); return v && v->kind == Str ? v->str : std::string(); }
    double n(const std::string& k, double def = 0) const { const Json* v = get(k); return v && v->kind == Num ? v->num : def; }
};
struct JsonReader {
    const std::string& t;
    size_t i = 0;
    int depth = 0;
    void ws() { while (i < t.size() && (t[i] == ' ' || t[i] == '\t' || t[i] == '\n' || t[i] == '\r')) ++i; }
    bool word(const char* w) { const size_t n = strlen(w); if (t.compare(i, n, w) != 0) return false; i += n; return true; }
    bool hex4(uint32_t& v)
    {
        if (i + 4 > t.size()) return false;
        v = 0;
        for (int k = 0; k < 4; ++k) {
            const char c = t[i + k];
            v <<= 4;
            if (c >= '0' && c <= '9') v |= uint32_t(c - '0');
            else if (c >= 'a' && c <= 'f') v |= uint32_t(c - 'a' + 10);
            else if (c >= 'A' && c <= 'F') v |= uint32_t(c - 'A' + 10);
            else return false;
        }
        i += 4;
        return true;
    }
    bool string(std::string& out)
    {
        if (i >= t.size() || t[i] != '"') return false;
        ++i;
        while (i < t.size()) {
            const unsigned char c = static_cast<unsigned char>(t[i]);
            if (c == '"') { ++i; return true; }
            if (c < 0x20) return false;
            if (c != '\\') {
                uint32_t cp;
                const size_t n = decode(t, i, cp);
                if (!n) { appendUtf8(out, 0xFFFD); ++i; } else { out.append(t, i, n); i += n; }
                continue;
            }
            if (++i >= t.size()) return false;
            const char e = t[i++];
            switch (e) {
            case '"': out += '"'; break;
            case '\\': out += '\\'; break;
            case '/': out += '/'; break;
            case 'b': out += '\b'; break;
            case 'f': out += '\f'; break;
            case 'n': out += '\n'; break;
            case 'r': out += '\r'; break;
            case 't': out += '\t'; break;
            case 'u': {
                uint32_t u;
                if (!hex4(u)) return false;
                if (u >= 0xD800 && u <= 0xDBFF) {            // a pair, else U+FFFD (the next escape is read again)
                    const size_t save = i;
                    uint32_t lo = 0;
                    if (i + 1 < t.size() && t[i] == '\\' && t[i + 1] == 'u') {
                        i += 2;
                        if (hex4(lo) && lo >= 0xDC00 && lo <= 0xDFFF) u = 0x10000 + ((u - 0xD800) << 10) + (lo - 0xDC00);
                        else { i = save; u = 0xFFFD; }
                    } else u = 0xFFFD;
                } else if (u >= 0xDC00 && u <= 0xDFFF) u = 0xFFFD;
                appendUtf8(out, u);
                break;
            }
            default: return false;
            }
        }
        return false;
    }
    bool value(Json& v)
    {
        ws();
        if (i >= t.size()) return false;
        const char c = t[i];
        if (c == '{' || c == '[') {
            if (++depth > 32) return false;
            ++i;
            const bool obj = c == '{';
            v.kind = obj ? Json::Obj : Json::Arr;
            ws();
            if (i < t.size() && t[i] == (obj ? '}' : ']')) { ++i; --depth; return true; }
            for (;;) {
                ws();
                if (obj) {
                    std::string k;
                    if (!string(k)) return false;
                    ws();
                    if (i >= t.size() || t[i] != ':') return false;
                    ++i;
                    v.keys.push_back(std::move(k));
                }
                Json x;
                if (!value(x)) return false;
                v.arr.push_back(std::move(x));
                ws();
                if (i < t.size() && t[i] == ',') { ++i; continue; }
                if (i < t.size() && t[i] == (obj ? '}' : ']')) { ++i; --depth; return true; }
                return false;
            }
        }
        if (c == '"') { v.kind = Json::Str; return string(v.str); }
        if (word("true")) { v.kind = Json::Bool; v.b = true; return true; }
        if (word("false")) { v.kind = Json::Bool; return true; }
        if (word("null")) { v.kind = Json::Null; return true; }
        const size_t start = i;
        while (i < t.size() && (std::strchr("+-0123456789.eE", t[i]) != nullptr) && t[i] != '\0') ++i;
        if (i == start || i - start > 40) return false;
        const std::string num = t.substr(start, i - start);
        char* end = nullptr;
        v.num = std::strtod(num.c_str(), &end);
        if (!end || *end || !std::isfinite(v.num)) return false;
        v.kind = Json::Num;
        return true;
    }
};
inline bool parseJson(const std::string& text, Json& out)
{
    out = Json();
    JsonReader r { text };
    if (!r.value(out)) return false;
    r.ws();
    return r.i == text.size();
}

// --- addresses ----------------------------------------------------------------------------------------------------
inline std::string lower(std::string s)
{
    for (char& c : s) if (c >= 'A' && c <= 'Z') c = char(c - 'A' + 'a');
    return s;
}
// Query parameters that only track where a click came from (names case-insensitive).
inline bool trackingParam(const std::string& name)
{
    const std::string k = lower(name);
    if (k.compare(0, 4, "utm_") == 0) return true;
    static const char* const names[] = { "fbclid", "gclid", "dclid", "gbraid", "wbraid", "msclkid", "yclid", "twclid",
        "ttclid", "igshid", "mc_cid", "mc_eid", "_ga", "_gl", "_hsenc", "_hsmi", "mkt_tok", "oly_anon_id", "oly_enc_id",
        "vero_id", "si", "ref_src" };
    for (const char* n : names) if (k == n) return true;
    return false;
}
// The key highlights are stored under: http / https only (else ""), scheme and host lower-case, no user:password@,
// no default port, "/" for an empty path, no #fragment, tracking parameters dropped (the others keep their order).
// "" when longer than kUrlMaxBytes.
inline std::string normalizeUrl(const std::string& in)
{
    size_t b = 0, e = in.size();
    while (b < e && static_cast<unsigned char>(in[b]) <= 0x20) ++b;
    while (e > b && static_cast<unsigned char>(in[e - 1]) <= 0x20) --e;
    const std::string u = in.substr(b, e - b);
    for (unsigned char c : u) if (c <= 0x20 || c == 0x7F) return "";
    const size_t se = u.find("://");
    if (se == std::string::npos) return "";
    const std::string scheme = lower(u.substr(0, se));
    if (scheme != "http" && scheme != "https") return "";
    const size_t a = se + 3;
    size_t end = u.find_first_of("/?#", a);
    if (end == std::string::npos) end = u.size();
    std::string auth = u.substr(a, end - a);
    const size_t at = auth.rfind('@');
    if (at != std::string::npos) auth = auth.substr(at + 1);
    auth = lower(auth);
    const std::string port = scheme == "http" ? ":80" : ":443";
    if (auth.size() > port.size() && auth.compare(auth.size() - port.size(), port.size(), port) == 0) auth.resize(auth.size() - port.size());
    if (auth.empty() || auth[0] == ':') return "";
    std::string rest = u.substr(end);
    const size_t h = rest.find('#');
    if (h != std::string::npos) rest.resize(h);
    const size_t q = rest.find('?');
    std::string path = q == std::string::npos ? rest : rest.substr(0, q);
    const std::string query = q == std::string::npos ? std::string() : rest.substr(q + 1);
    if (path.empty()) path = "/";
    std::string kept;
    for (size_t p = 0; p <= query.size();) {
        size_t amp = query.find('&', p);
        if (amp == std::string::npos) amp = query.size();
        const std::string part = query.substr(p, amp - p);
        if (!part.empty() && !trackingParam(part.substr(0, part.find('=')))) { if (!kept.empty()) kept += '&'; kept += part; }
        p = amp + 1;
    }
    std::string out = scheme + "://" + auth + path + (kept.empty() ? std::string() : "?" + kept);
    return out.size() > kUrlMaxBytes ? std::string() : out;
}
// The host without "www." (panel rows).
inline std::string site(const std::string& url)
{
    const size_t se = url.find("://");
    if (se == std::string::npos) return url;
    size_t end = url.find_first_of("/?#", se + 3);
    if (end == std::string::npos) end = url.size();
    std::string h = url.substr(se + 3, end - se - 3);
    if (h.compare(0, 4, "www.") == 0) h = h.substr(4);
    return h;
}

// --- the store ----------------------------------------------------------------------------------------------------
// Caps and clean-up of one item (also for items read from the file). False: unusable (no exact text / address / id).
inline bool clean(Item& it)
{
    if (it.id < 1 || it.url.empty()) return false;
    it.exact = utf8Cut(collapse(sanitize(it.exact)), kExactMaxBytes);
    it.prefix = utf8Tail(collapse(sanitize(it.prefix)), kContextMaxBytes);
    it.suffix = utf8Cut(collapse(sanitize(it.suffix)), kContextMaxBytes);
    it.title = utf8Cut(collapse(sanitize(it.title)), kTitleMaxBytes);
    if (it.at < 0) it.at = 0;
    return !it.exact.empty();
}
inline size_t itemBytes(const Item& it) { return it.exact.size() + it.prefix.size() + it.suffix.size() + it.title.size(); }
inline bool newer(const Item& a, const Item& b) { return a.at != b.at ? a.at > b.at : a.id > b.id; }

// OMNI_HIGHLIGHTS_V1_R2: the whole file, or false when it can't be read as a store (over kMaxFileBytes, not JSON, no
// "items" array): `out` is then empty and the shell writes nothing over the file (it keeps a .bad copy). An empty or
// blank file is an empty store (true).
inline bool parseFile(const std::string& text, std::vector<Item>& out)
{
    out.clear();
    if (text.size() > size_t(kMaxFileBytes)) return false;
    if (text.find_first_not_of(" \t\r\n") == std::string::npos) return true;
    Json root;
    if (!parseJson(text, root) || root.kind != Json::Obj) return false;
    const Json* items = root.get("items");
    if (!items || items->kind != Json::Arr) return false;
    for (const Json& j : items->arr) {
        if (j.kind != Json::Obj) continue;
        const double id = j.n("id"), at = j.n("at");
        if (!(id >= 1 && id <= 9e15) || id != std::floor(id)) continue;
        Item it;
        it.id = static_cast<long long>(id);
        it.at = at >= 0 && at <= 9e15 ? static_cast<long long>(at) : 0;
        it.url = normalizeUrl(j.s("url"));
        it.title = j.s("title"); it.exact = j.s("e"); it.prefix = j.s("p"); it.suffix = j.s("s");
        if (!clean(it)) continue;
        bool dup = false;
        for (const Item& o : out) if (o.id == it.id) { dup = true; break; }
        if (!dup) out.push_back(std::move(it));
    }
    if (out.size() > kMaxItems) {
        std::stable_sort(out.begin(), out.end(), newer);
        out.resize(kMaxItems);
    }
    return true;
}
inline std::vector<Item> parse(const std::string& text)
{
    std::vector<Item> out;
    if (!parseFile(text, out)) out.clear();
    return out;
}
static const char* const kFileHead = "{\"omni-highlights\":1,\"items\":[";
static const char* const kFileTail = "\n]}\n";
inline std::string itemJson(const Item& it)
{
    return "{\"id\":" + std::to_string(it.id) + ",\"at\":" + std::to_string(it.at) + ",\"url\":" + jsonEscape(it.url)
        + ",\"title\":" + jsonEscape(it.title) + ",\"p\":" + jsonEscape(it.prefix) + ",\"e\":" + jsonEscape(it.exact)
        + ",\"s\":" + jsonEscape(it.suffix) + "}";
}
inline std::string serialize(const std::vector<Item>& items)
{
    std::string o = kFileHead;
    for (size_t i = 0; i < items.size(); ++i) {
        o += i ? ",\n" : "\n";
        o += itemJson(items[i]);
    }
    return o + kFileTail;
}
// serialize(items).size() without building it.
inline size_t serializedBytes(const std::vector<Item>& items)
{
    size_t n = strlen(kFileHead) + strlen(kFileTail);
    for (size_t i = 0; i < items.size(); ++i) n += (i ? 2 : 1) + itemJson(items[i]).size();
    return n;
}
inline long long nextId(const std::vector<Item>& items)
{
    long long m = 0;
    for (const Item& it : items) m = std::max(m, it.id);
    return m + 1;
}
// Adds a cleaned item. OMNI_HIGHLIGHTS_V1_R2: also refused (kTooBig) when the file would pass kMaxFileBytes, which
// parse would then refuse (500 items of 2 KB text + 2 KB address + JSON escapes can pass 2 MiB).
enum AddResult { kAdded = 0, kFull, kTooBig, kUnusable };
inline AddResult addChecked(std::vector<Item>& items, Item it)
{
    if (items.size() >= kMaxItems) return kFull;
    if (!clean(it)) return kUnusable;
    for (const Item& o : items) if (o.id == it.id) return kUnusable;
    if (serializedBytes(items) + (items.empty() ? 1 : 2) + itemJson(it).size() > size_t(kMaxFileBytes)) return kTooBig;
    items.push_back(std::move(it));
    return kAdded;
}
// False: full (kMaxItems or the file size), unusable, or its id is taken.
inline bool add(std::vector<Item>& items, Item it) { return addChecked(items, std::move(it)) == kAdded; }
inline size_t removeIds(std::vector<Item>& items, const std::vector<long long>& ids)
{
    const size_t before = items.size();
    items.erase(std::remove_if(items.begin(), items.end(), [&](const Item& it) {
        return std::find(ids.begin(), ids.end(), it.id) != ids.end(); }), items.end());
    return before - items.size();
}
// A page's highlights, oldest first (the order they are applied in).
inline std::vector<Item> forUrl(const std::vector<Item>& items, const std::string& key)
{
    std::vector<Item> v;
    if (key.empty()) return v;
    for (const Item& it : items) if (it.url == key) v.push_back(it);
    std::stable_sort(v.begin(), v.end(), [](const Item& a, const Item& b) { return newer(b, a); });
    return v;
}
inline std::vector<long long> idsForUrl(const std::vector<Item>& items, const std::string& key)
{
    std::vector<long long> v;
    for (const Item& it : items) if (it.url == key) v.push_back(it.id);
    return v;
}

// --- the page script ----------------------------------------------------------------------------------------------
// A function expression (op, a) returning a JSON string. Ops:
//   'a' apply  a = {items:[{i,p,e,s}], f:<id to scroll to or 0>}  -> {ok:1, f:[found ids], m:[missing ids], fx:0|1}
//              (missing ones are looked for once more 2 s later, nothing reported)
//   'c' create a = {i:<new id>}: the main frame's selection -> {ok:1, e, p, s, t:<title>, u:<live address of a saved
//              copy or "">, cut:0|1} and the passage wrapped; or {err:"none"|"frame"|"page"}
//   'r' remove a = {ids:[...]}: those marks unwrapped -> {ok:1, n}
//   'l' live   -> {ok:1, u}: a reading-list saved copy's "Open live page" address ("" elsewhere)
// Only the page's DOM is touched (marks, the selection, a scroll); nothing is stored in the page.
static const char* const kScript = R"JS(function(op,a){try{var D=document,W=window,CX=32,EM=1600,ST=W.setTimeout,XH='http://www.w3.org/1999/xhtml';a=a||{};
function ign(c){return c<=32||c===127||c===160||c===173||c===0x1680||(c>=0x2000&&c<=0x200f)||c===0x2028||c===0x2029||c===0x202f||c===0x205f||c===0x2060||c===0x3000||c===0xfeff;}
function strip(t){t=String(t||'');var o='';for(var i=0;i<t.length;i++){if(!ign(t.charCodeAt(i)))o+=t.charAt(i);}return o;}
function col(t){return String(t).replace(/\s+/g,' ');}
function u8(t){var n=0;for(var i=0;i<t.length;i++){var c=t.charCodeAt(i);if(c<128)n+=1;else if(c<2048)n+=2;else if(c>=0xd800&&c<0xdc00&&i+1<t.length){n+=4;i++;}else n+=3;}return n;}
function cutB(t,max){var n=0,i=0;while(i<t.length){var c=t.charCodeAt(i),w=c<128?1:c<2048?2:(c>=0xd800&&c<0xdc00&&i+1<t.length)?4:3;if(n+w>max)break;n+=w;i+=w===4?2:1;}return t.slice(0,i);}
function live(){try{if(String(location.href)!=='about:blank')return'';var b=D.getElementById('omni-saved-banner'),l=b&&b.querySelector('a[href]');return l?String(l.href):'';}catch(_){return'';}}
function model(){var b=D.body;if(!b)return null;var nodes=[],st=[],R=0,N='',M=[],n;
var tw=D.createTreeWalker(b,5,{acceptNode:function(x){if(x.nodeType===1){var t=String(x.tagName||'').toUpperCase();return t==='SCRIPT'||t==='STYLE'||t==='NOSCRIPT'||t==='TEXTAREA'||t==='TEMPLATE'||t==='SELECT'||t==='OPTION'||x.id==='omni-saved-banner'?2:3;}return 1;}});
while((n=tw.nextNode())){var d=String(n.data),p='';nodes.push(n);st.push(R);for(var i=0;i<d.length;i++){if(!ign(d.charCodeAt(i))){p+=d.charAt(i);M.push(R+i);}}N+=p;R+=d.length;}
return{nodes:nodes,st:st,N:N,M:M};}
function find(m,g){var lo=0,hi=m.st.length-1,r=0;while(lo<=hi){var mid=(lo+hi)>>1;if(m.st[mid]<=g){r=mid;lo=mid+1;}else hi=mid-1;}return r;}
function lb(A,g){var lo=0,hi=A.length;while(lo<hi){var mid=(lo+hi)>>1;if(A[mid]<g)lo=mid+1;else hi=mid;}return lo;}
function rawSl(m,x,y){var o='';for(var k=find(m,x);k<m.nodes.length&&m.st[k]<y;k++){var s0=m.st[k],d=String(m.nodes[k].data);o+=d.slice(Math.max(x,s0)-s0,Math.min(y,s0+d.length)-s0);}return o;}
function best(m,q,pp,ss){var N=m.N,i=N.indexOf(q),bi=-1,bs=-1,k=0;while(i>=0&&k<1000){var s=0,x,y;for(x=pp.length-1,y=i-1;x>=0&&y>=0&&pp.charCodeAt(x)===N.charCodeAt(y);x--,y--)s++;for(x=0,y=i+q.length;x<ss.length&&y<N.length&&ss.charCodeAt(x)===N.charCodeAt(y);x++,y++)s++;if(s>bs){bs=s;bi=i;if(s===pp.length+ss.length)break;}k++;i=N.indexOf(q,i+1);}return bi;}
function has(d,x,y){for(var i=x;i<y;i++)if(!ign(d.charCodeAt(i)))return true;return false;}
function segs(m,ns,ne,id,L){var g0=m.M[ns],g1=m.M[ne-1]+1;for(var k=find(m,g0);k<m.nodes.length&&m.st[k]<g1;k++){var n=m.nodes[k],s0=m.st[k],d=String(n.data),x=Math.max(g0,s0)-s0,y=Math.min(g1,s0+d.length)-s0;if(y>x&&has(d,x,y))L.push({k:k,a:x,b:y,id:id});}}
function sty(e){try{var s=e.style;s.setProperty('background-color','#ffe45c','important');s.setProperty('color','#16181d','important');s.setProperty('border-radius','2px','important');s.setProperty('box-shadow','0 0 0 1px rgba(200,150,0,.6)','important');}catch(_){}}
function wrap(m,L){L.sort(function(u,v){return u.k-v.k||v.a-u.a;});var lk=-1,la=0,c=0;for(var i=0;i<L.length;i++){var g=L[i],n=m.nodes[g.k],pa=n.parentNode;if(g.k===lk&&g.b>la)continue;if(!pa||(pa.namespaceURI&&pa.namespaceURI!==XH))continue;lk=g.k;la=g.a;try{if(g.b<n.data.length)n.splitText(g.b);var mid=g.a>0?n.splitText(g.a):n,mk=D.createElement('mark');mk.className='omni-hl';mk.setAttribute('data-omni-hl',g.id);sty(mk);pa.insertBefore(mk,mid);mk.appendChild(mid);c++;}catch(_){}}return c;}
function have(){var o={},l=D.querySelectorAll('mark.omni-hl');for(var i=0;i<l.length;i++){var x=l[i].getAttribute('data-omni-hl');if(x&&!o[x])o[x]=l[i];}return o;}
function go(e){try{e.scrollIntoView({block:'center'});}catch(_){try{e.scrollIntoView();}catch(__){}}}
function apply(list,f,again){var h=have(),m=null,L=[],fo=[],mi=[];for(var i=0;i<list.length;i++){var it=list[i];if(!it||typeof it.e!=='string')continue;var id=String(it.i);if(h[id]){fo.push(it.i);continue;}var q=strip(it.e);if(!q){mi.push(it);continue;}if(!m){m=model();if(!m){mi.push(it);continue;}}var at=best(m,q,strip(it.p),strip(it.s));if(at<0){mi.push(it);continue;}segs(m,at,at+q.length,id,L);fo.push(it.i);}
if(L.length)wrap(m,L);var fx=0;if(f){var e=have()[String(f)];if(e){fx=1;go(e);}}
if(mi.length&&!again&&typeof ST==='function'){try{ST.call(W,function(){try{apply(mi,fx?0:f,1);}catch(_){}},2000);}catch(_){}}
return{ok:1,f:fo,m:mi.map(function(x){return x.i;}),fx:fx};}
if(op==='a')return JSON.stringify(apply(a.items||[],a.f||0,0));
if(op==='l')return JSON.stringify({ok:1,u:live()});
if(op==='r'){var ids={},z=a.ids||[];for(var q=0;q<z.length;q++)ids[String(z[q])]=1;var l=D.querySelectorAll('mark.omni-hl'),cnt=0;for(var i=0;i<l.length;i++){var mk=l[i];if(!ids[mk.getAttribute('data-omni-hl')])continue;var pa=mk.parentNode;if(!pa)continue;while(mk.firstChild)pa.insertBefore(mk.firstChild,mk);pa.removeChild(mk);try{pa.normalize();}catch(_){}cnt++;}return JSON.stringify({ok:1,n:cnt});}
if(op==='c'){var s=W.getSelection?W.getSelection():null;if(!s||!s.rangeCount||s.isCollapsed){var fr=0;try{for(var j=0;j<W.frames.length&&!fr;j++){try{var fs=W.frames[j].getSelection();if(fs&&fs.rangeCount&&!fs.isCollapsed)fr=1;}catch(_){}}}catch(_){}return JSON.stringify({err:fr?'frame':'none'});}
var r=s.getRangeAt(0),m=model();if(!m)return'{"err":"page"}';var g0=-1,g1=-1;
for(var k=0;k<m.nodes.length;k++){var n=m.nodes[k],hit=false;try{hit=r.intersectsNode(n);}catch(_){}if(!hit)continue;var x=n===r.startContainer?r.startOffset:0,y=n===r.endContainer?r.endOffset:n.data.length;if(y<=x)continue;if(g0<0)g0=m.st[k]+x;g1=m.st[k]+y;}
if(g0<0)return'{"err":"none"}';var ns=lb(m.M,g0),ne=lb(m.M,g1);if(ne<=ns)return'{"err":"none"}';
var e=col(rawSl(m,m.M[ns],m.M[ne-1]+1)).trim(),cut=0;if(u8(e)>EM){ne=ns+strip(cutB(e,EM)).length;cut=1;if(ne<=ns)return'{"err":"none"}';e=col(rawSl(m,m.M[ns],m.M[ne-1]+1)).trim();}
var p=col(rawSl(m,m.M[Math.max(0,ns-CX)],m.M[ns])),sf=ne<m.M.length?col(rawSl(m,m.M[ne-1]+1,m.M[Math.min(m.M.length-1,ne+CX-1)]+1)):'';
if(/^[\uDC00-\uDFFF]/.test(p))p=p.slice(1);if(/[\uD800-\uDBFF]$/.test(sf))sf=sf.slice(0,-1);
var L=[];segs(m,ns,ne,String(a.i),L);wrap(m,L);try{s.removeAllRanges();}catch(_){}
return JSON.stringify({ok:1,e:e,p:p,s:sf,t:String(D.title||''),u:live(),cut:cut});}
return'{}';}catch(err){return'{}';}})JS";

// The whole call: op is one of a / c / r / l (anything else becomes 'l', which only reads); arg is JSON built below.
inline std::string script(char op, const std::string& arg)
{
    if (op != 'a' && op != 'c' && op != 'r' && op != 'l') op = 'l';
    return std::string("(") + kScript + ")('" + op + "'," + (arg.empty() ? std::string("{}") : arg) + ")";
}
inline std::string applyArg(const std::vector<Item>& list, long long focus)
{
    std::string o = "{\"items\":[";
    for (size_t i = 0; i < list.size(); ++i) {
        const Item& it = list[i];
        if (i) o += ',';
        o += "{\"i\":" + std::to_string(it.id) + ",\"p\":" + jsonEscape(it.prefix) + ",\"e\":" + jsonEscape(it.exact)
            + ",\"s\":" + jsonEscape(it.suffix) + "}";
    }
    return o + "],\"f\":" + std::to_string(focus > 0 ? focus : 0) + "}";
}
inline std::string createArg(long long id) { return "{\"i\":" + std::to_string(id) + "}"; }
inline std::string removeArg(const std::vector<long long>& ids)
{
    std::string o = "{\"ids\":[";
    for (size_t i = 0; i < ids.size(); ++i) o += (i ? "," : "") + std::to_string(ids[i]);
    return o + "]}";
}

// The 'c' answer. status: 0 ok, 1 nothing selected, 2 the selection is in a frame, 3 no answer / page error.
struct Created { int status = 3; std::string exact, prefix, suffix, title, live; bool cut = false; };
inline Created created(const std::string& json)
{
    Created c;
    Json j;
    if (!parseJson(json, j) || j.kind != Json::Obj) return c;
    const std::string err = j.s("err");
    if (err == "none") { c.status = 1; return c; }
    if (err == "frame") { c.status = 2; return c; }
    if (j.n("ok") <= 0) return c;
    c.exact = collapse(sanitize(j.s("e")));
    if (c.exact.empty()) { c.status = 1; return c; }
    c.cut = j.n("cut") > 0 || c.exact.size() > kExactMaxBytes;
    c.exact = utf8Cut(c.exact, kExactMaxBytes);
    c.prefix = utf8Tail(collapse(sanitize(j.s("p"))), kContextMaxBytes);
    c.suffix = utf8Cut(collapse(sanitize(j.s("s"))), kContextMaxBytes);
    c.title = utf8Cut(collapse(sanitize(j.s("t"))), kTitleMaxBytes);
    c.live = j.s("u");
    c.status = 0;
    return c;
}

// --- the panel ----------------------------------------------------------------------------------------------------
struct Group { std::string url, title; long long newest = 0; std::vector<Item> items; };
// Pages by their newest highlight (newest first), each page's highlights newest first; title: the newest non-empty one.
inline std::vector<Group> groups(const std::vector<Item>& all)
{
    std::vector<Item> v = all;
    std::stable_sort(v.begin(), v.end(), newer);
    std::vector<Group> g;
    for (const Item& it : v) {
        Group* p = nullptr;
        for (Group& x : g) if (x.url == it.url) { p = &x; break; }
        if (!p) { g.push_back(Group()); p = &g.back(); p->url = it.url; p->newest = it.at; }
        if (p->title.empty()) p->title = it.title;
        p->items.push_back(it);
    }
    return g;
}
inline std::string preview(const std::string& s, size_t max)
{
    const std::string c = collapse(s);
    if (c.size() <= max) return c;
    return utf8Cut(c, max > 3 ? max - 3 : 0) + "...";
}
inline std::string rowLabel(const Item& it) { return "\"" + preview(it.exact, 110) + "\""; }
inline std::string pageDetail(const Group& g)
{
    const size_t n = g.items.size();
    return site(g.url) + " \xc2\xb7 " + std::to_string(n) + (n == 1 ? " highlight" : " highlights");
}
// "Today", "Yesterday", else "12 Nov 2026" (local time).
inline std::string dateText(long long at, long long now)
{
    const time_t a = time_t(at), n = time_t(now), y = time_t(now - 86400);
    struct tm ta {}, tn {}, ty {};
    localtime_r(&a, &ta);
    localtime_r(&n, &tn);
    localtime_r(&y, &ty);
    if (ta.tm_year == tn.tm_year && ta.tm_yday == tn.tm_yday) return "Today";
    if (ta.tm_year == ty.tm_year && ta.tm_yday == ty.tm_yday) return "Yesterday";
    static const char* const mon[] = { "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec" };
    char b[40];
    snprintf(b, sizeof b, "%d %s %d", ta.tm_mday, mon[(ta.tm_mon % 12 + 12) % 12], ta.tm_year + 1900);
    return b;
}
inline std::string panelSubtitle(size_t items, size_t pages)
{
    if (!items) return "Select text on a page (hold Cross > Select text), then Cross > Highlight";
    return std::to_string(items) + (items == 1 ? " highlight on " : " highlights on ") + std::to_string(pages)
        + (pages == 1 ? " page" : " pages") + " \xc2\xb7 they come back when the page is opened";
}
inline std::string deletePageTitle(size_t n)
{
    return n == 1 ? std::string("Delete the highlight on this page?") : "Delete " + std::to_string(n) + " highlights on this page?";
}

// --- notices ------------------------------------------------------------------------------------------------------
inline std::string savedNotice(bool cut)
{
    return std::string("Highlighted") + (cut ? " (the first 1,600 bytes)" : "") + ": Options > Browse > Highlights lists it";
}
inline std::string privateNotice() { return "Highlighted on this page only: private tabs don't save highlights"; }
inline std::string noAddressNotice() { return "Highlighted on this page only: this page has no address to keep it for"; }
inline std::string fullNotice()
{
    return "Highlights are full (" + std::to_string(kMaxItems) + "): delete some in Options > Browse > Highlights";
}
// OMNI_HIGHLIGHTS_V1_R2: the file size cap (long passages / addresses) rather than the count.
inline std::string bytesFullNotice() { return "Highlights full: delete some in Options > Browse > Highlights"; }
inline std::string unreadableNotice() { return "Highlights can't be saved: the highlights file couldn't be read"; }
inline std::string notFoundNotice() { return "That passage wasn't found on the page any more"; }
inline std::string createErrorNotice(int status)
{
    if (status == 2) return "Text inside a frame can't be highlighted";
    if (status == 1) return "Nothing selected to highlight";
    return "This page can't be highlighted";
}

} // namespace OmniHighlights
'''

SHELL = r'''// OMNI_HIGHLIGHTS_V1: highlights (shell side). Included from OmniFeatures3.h (inside OmniBrowser.cpp's anonymous
// namespace, after OmniTextSelectShell.h). The pure part (store, URL key, JSON, page script, texts) is OmniHighlights.h;
// reasons in tools/apply_highlights.py.
// "Highlight" in the "Selected text" panel wraps the selection in <mark class="omni-hl"> and stores it (never from a
// private tab: those marks last for the visit only); finished() re-applies a page's highlights (private tabs too: read
// only); Options > Browse > Highlights lists them (Cross opens + scrolls, Square deletes). Main thread only; the file
// is written by omniIoQueue (not in test mode).
// OMNI_HIGHLIGHTS_V1_R2:
//   - a saved copy's banner ('l', and the 'c' answer's live address) is only trusted in a tab where the reading list
//     itself loaded the saved copy (Tab::omniHltSaved, set in OmniReadingListShell.h before WKPageLoadHTMLString;
//     2 while that document is the last one finished), never in private tabs: any other about:blank page (window.open + a planted
//     banner) gets nothing.
//   - an unreadable file (too large, not JSON) is kept as highlights.json.bad and nothing is written over it this run
//     (omniHltLoadFailed); an add that would push the file past 2 MiB is refused ("Highlights full").
//   - tabs are matched by Tab::omniMediaIdentity (never reused), not by address.
#pragma once

namespace OHLT = OmniHighlights;
static std::vector<OHLT::Item> omniHltItems;
static bool omniHltLoaded = false, omniHltLoadFailed = false;
static long long omniHltNext = 1;
struct OmniHltFocus { uintptr_t tab = 0; long long id = 0; std::string key; };
static OmniHltFocus omniHltFocus;                 // scroll to this highlight when its page finished loading in `tab`
struct OmniHltQuery { const void* tab; uintptr_t ident; char op; long long id; bool priv; std::string key; long long focus; bool saved; };
static OmniHltQuery* omniHltQ(Tab& t, char op, long long id, const std::string& key, long long focus)
{
    return new OmniHltQuery { &t, t.omniMediaIdentity, op, id, t.omniPrivate, key, focus, !t.omniPrivate && t.omniHltSaved == 2 && t.url == "about:blank" };
}

// A copy of the unreadable file next to it (highlights.json.bad); the file itself is left alone.
static void omniHltKeepBad(const std::string& path)
{
    if (omniTestMode()) return;
    FILE* in = fopen(path.c_str(), "rb");
    if (!in) return;
    FILE* out = fopen((path + ".bad").c_str(), "wb");
    if (out) {
        char buf[65536];
        size_t n;
        while ((n = fread(buf, 1, sizeof buf, in)) > 0 && fwrite(buf, 1, n, out) == n) {}
        fclose(out);
    }
    fclose(in);
}
static void omniHltLoad()
{
    if (omniHltLoaded) return;
    omniHltLoaded = true;
    const std::string path = omniData(OHLT::kFileName);
    if (FILE* f = fopen(path.c_str(), "rb")) {
        std::string text;
        char buf[8192];
        size_t n;
        while ((n = fread(buf, 1, sizeof buf, f)) > 0 && long(text.size()) <= OHLT::kMaxFileBytes) text.append(buf, n);
        const bool err = ferror(f) != 0;
        fclose(f);
        if (err || !OHLT::parseFile(text, omniHltItems)) {
            omniHltItems.clear();
            omniHltLoadFailed = true;   // nothing is written over it this run
            omniHltKeepBad(path);
            fprintf(stderr, "OMNI HIGHLIGHTS: %s unreadable (%zu bytes read): kept as .bad, not written\n", path.c_str(), text.size());
            fflush(stderr);
        }
    }
    omniHltNext = std::max(omniHltNext, OHLT::nextId(omniHltItems));
}
static void omniHltWrite()
{
    if (omniTestMode() || omniHltLoadFailed) return;
    std::string text = OHLT::serialize(omniHltItems);
    if (text.size() > size_t(OHLT::kMaxFileBytes)) { fprintf(stderr, "OMNI HIGHLIGHTS: %zu bytes, over the cap: not written\n", text.size()); return; }
    omniIoQueue(omniData(OHLT::kFileName), std::move(text), false);
}

static void omniHltResult(const OmniHltQuery& q, const std::string& json);
static void omniHltRun(Tab* t, char op, const std::string& arg, OmniHltQuery* q)
{
    if (!t || t->crashed) { delete q; return; }
    const std::string js = OHLT::script(op, arg);
    auto src = adoptWK(WKStringCreateWithUTF8CString(js.c_str()));
    WKPageEvaluateJavaScriptInMainFrame(t->page, src.get(), q, [](WKTypeRef result, WKErrorRef error, void* context) {
        std::unique_ptr<OmniHltQuery> q(static_cast<OmniHltQuery*>(context));
        if (!omniTabAlive(q->tab) || static_cast<const Tab*>(q->tab)->omniMediaIdentity != q->ident) return;
        omniHltResult(*q, omniFxResultString(result, error));
    });
}
// The page's highlights (key: OHLT::normalizeUrl), plus a scroll when one was asked for in this tab.
static void omniHltApply(Tab& tab, const std::string& key)
{
    if (key.empty() || tab.crashed) return;
    omniHltLoad();
    long long focus = 0;
    if (omniHltFocus.tab == tab.omniMediaIdentity && omniHltFocus.key == key) { focus = omniHltFocus.id; omniHltFocus = OmniHltFocus(); }
    const std::vector<OHLT::Item> list = OHLT::forUrl(omniHltItems, key);
    if (list.empty()) { if (focus && &tab == active()) notice(OHLT::notFoundNotice()); return; }
    omniHltRun(&tab, 'a', OHLT::applyArg(list, focus), omniHltQ(tab, 'a', 0, key, focus));
}
// finished(): every main-frame load. Reader view keeps the page's address (its highlights apply to the reader text);
// a reading-list saved copy is about:blank: its banner's live address is asked for first, but only when the reading
// list loaded it in this tab (omniHltSaved 1 -> 2 here; any other finished load clears it) and never in private tabs.
static void omniHltFinished(Tab& tab)
{
    const bool saved = tab.omniHltSaved == 1 && tab.url == "about:blank" && !tab.omniPrivate;
    tab.omniHltSaved = saved ? 2 : 0;
    if (tab.crashed) return;
    if (tab.url == "about:blank") {
        if (!saved) return;
        omniHltLoad();
        if (!omniHltItems.empty()) omniHltRun(&tab, 'l', "{}", omniHltQ(tab, 'l', 0, std::string(), 0));
        return;
    }
    omniHltApply(tab, OHLT::normalizeUrl(tab.url));
}
static void omniHltUnmark(const std::vector<long long>& ids, const std::string& key)
{
    if (ids.empty()) return;
    for (auto& t : tabs)
        if (!t->crashed && OHLT::normalizeUrl(t->url) == key)
            omniHltRun(t.get(), 'r', OHLT::removeArg(ids), omniHltQ(*t, 'r', 0, key, 0));
}
static bool omniHltPanelShown();

static void omniHltResult(const OmniHltQuery& q, const std::string& json)
{
    Tab* t = static_cast<Tab*>(const_cast<void*>(q.tab));
    if (q.op == 'l') {
        if (!q.saved || t->omniHltSaved != 2 || t->url != "about:blank" || t->omniPrivate) return;   // navigated since
        OHLT::Json j;
        if (OHLT::parseJson(json, j)) omniHltApply(*t, OHLT::normalizeUrl(j.s("u")));
        return;
    }
    if (q.op == 'a') {
        if (!q.focus || t != active()) return;
        OHLT::Json j;
        if (!OHLT::parseJson(json, j) || j.n("fx") <= 0) notice(OHLT::notFoundNotice());
        return;
    }
    if (q.op != 'c') return;
    const OHLT::Created c = OHLT::created(json);
    if (c.status != 0) { notice(OHLT::createErrorNotice(c.status)); return; }
    if (q.priv) { notice(OHLT::privateNotice()); return; }    // marked on the page; nothing stored
    // a saved copy: for its live page (R2: only a saved copy the reading list opened in this tab, still shown)
    const bool saved = q.saved && t->omniHltSaved == 2 && t->url == "about:blank";
    const std::string key = saved && !c.live.empty() ? OHLT::normalizeUrl(c.live) : q.key;
    if (key.empty()) { notice(OHLT::noAddressNotice()); return; }
    omniHltLoad();
    if (omniHltLoadFailed) { notice(OHLT::unreadableNotice()); return; }
    OHLT::Item it;
    it.id = q.id;
    it.at = static_cast<long long>(time(nullptr));
    it.url = key;
    it.title = c.title.empty() ? t->title : c.title;
    it.exact = c.exact; it.prefix = c.prefix; it.suffix = c.suffix;
    switch (OHLT::addChecked(omniHltItems, it)) {
    case OHLT::kAdded: break;
    case OHLT::kFull: notice(OHLT::fullNotice()); return;
    case OHLT::kTooBig: notice(OHLT::bytesFullNotice()); return;
    default: notice(OHLT::createErrorNotice(3)); return;
    }
    omniHltWrite();
    notice(OHLT::savedNotice(c.cut));
    if (omniHltPanelShown()) omniFxRefresh();
    omniShellDirty = true;
}

// --- "Highlight" in the "Selected text" panel (OmniTextSelectShell.h calls these) --------------------------------------
static void omniHltActionRow(OmniFxPanel& p)
{
    Tab* t = active();
    OmniFxRow r; r.id = OHLT::kActionId; r.label = "Highlight";
    r.enabled = !OTSL::collapse(p.text).empty();
    if (t && t->omniPrivate) r.value = "This visit only";
    p.rows.push_back(r);
}
// Runs before the selection is cleared (the page answers in order: this script, then text select's clear).
static void omniHltCreate()
{
    Tab* t = active();
    if (!t || t->crashed) return;
    omniHltLoad();
    if (!t->omniPrivate && omniHltLoadFailed) { notice(OHLT::unreadableNotice()); return; }
    if (!t->omniPrivate && omniHltItems.size() >= OHLT::kMaxItems) { notice(OHLT::fullNotice()); return; }
    const long long id = omniHltNext++;
    omniHltRun(t, 'c', OHLT::createArg(id), omniHltQ(*t, 'c', id, OHLT::normalizeUrl(t->url), 0));
}

// --- the Highlights panel (Options > Browse > Highlights) -------------------------------------------------------------
struct OmniHltRow { std::string url; long long id; };   // id 0: the page's row
static std::vector<OmniHltRow> omniHltShown;
enum { omniHltRowInfo = 1, omniHltRowFirst = 1000 };
static void omniHltOpen(const std::string& url, long long id)
{
    omniFxCloseAll();
    Tab* t = active();
    if (!t) return;
    const std::string key = OHLT::normalizeUrl(url);
    if (!t->crashed && !t->loading && OHLT::normalizeUrl(t->url) == key) {   // this tab shows it: scroll there
        if (id) { omniHltFocus = { t->omniMediaIdentity, id, key }; omniHltApply(*t, key); }
        return;
    }
    navigate(url);
    if (id && active()) omniHltFocus = { active()->omniMediaIdentity, id, key };
}
static void omniHltDelete(const std::vector<long long>& ids, const std::string& key)
{
    if (!OHLT::removeIds(omniHltItems, ids)) return;
    omniHltWrite();
    omniHltUnmark(ids, key);
}
static void omniHltBuild(OmniFxPanel& p)
{
    omniHltLoad();
    omniHltShown.clear();
    const std::vector<OHLT::Group> gs = OHLT::groups(omniHltItems);
    if (omniHltLoadFailed) {   // OMNI_HIGHLIGHTS_V1_R2
        OmniFxRow r; r.id = omniHltRowInfo; r.enabled = false; r.label = "The highlights file couldn't be read";
        r.detail = "Kept as highlights.json.bad; nothing is saved over it";
        p.rows.push_back(r);
    } else if (gs.empty()) {
        OmniFxRow r; r.id = omniHltRowInfo; r.enabled = false; r.label = "No highlights yet";
        r.detail = "Hold Cross on a word > Select text, then Cross > Highlight";
        p.rows.push_back(r);
    }
    const long long now = static_cast<long long>(time(nullptr));
    for (const OHLT::Group& g : gs) {
        OmniFxRow h; h.id = omniHltRowFirst + int(omniHltShown.size());
        h.label = omniOneLine(g.title.empty() ? OHLT::site(g.url) : g.title, 120);
        h.detail = OHLT::pageDetail(g);
        h.value = OHLT::dateText(g.newest, now);
        p.rows.push_back(h);
        omniHltShown.push_back({ g.url, 0 });
        for (const OHLT::Item& it : g.items) {
            OmniFxRow r; r.id = omniHltRowFirst + int(omniHltShown.size());
            r.label = OHLT::rowLabel(it);
            r.value = OHLT::dateText(it.at, now);
            p.rows.push_back(r);
            omniHltShown.push_back({ g.url, it.id });
        }
    }
    p.subtitle = OHLT::panelSubtitle(omniHltItems.size(), gs.size());
    p.corner = std::to_string(omniHltItems.size()) + " / " + std::to_string(OHLT::kMaxItems);
}
static bool omniHltInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (r.id < omniHltRowFirst) return b == SDL_CONTROLLER_BUTTON_A;
    const size_t i = size_t(r.id - omniHltRowFirst);
    if (i >= omniHltShown.size()) return false;
    const OmniHltRow row = omniHltShown[i];
    if (b == SDL_CONTROLLER_BUTTON_A) { omniHltOpen(row.url, row.id); return true; }
    if (b != SDL_CONTROLLER_BUTTON_X) return false;
    if (row.id) {
        omniHltDelete({ row.id }, row.url);
        notice("Highlight deleted");
        omniFxRefresh();
        return true;
    }
    const std::vector<long long> ids = OHLT::idsForUrl(omniHltItems, row.url);
    if (ids.empty()) return true;
    const std::string url = row.url;
    omniAsk(OHLT::deletePageTitle(ids.size()), omniOneLine(r.label, 90) + " (" + OHLT::site(url) + ")", "Delete", [ids, url](bool ok) {
        if (!ok) return;
        omniHltDelete(ids, url);
        notice(ids.size() == 1 ? std::string("Highlight deleted") : std::to_string(ids.size()) + " highlights deleted");
        if (omniHltPanelShown()) omniFxRefresh();
    });
    return true;
}
static bool omniHltPanelShown() { return !omniFxStack.empty() && omniFxStack.back().build == omniHltBuild; }
static void omniHltShow()
{
    OmniFxPanel p;
    p.title = "Highlights"; p.w = 1000; p.rowH = 56; p.maxVisible = 8;
    p.build = omniHltBuild; p.input = omniHltInput;
    p.faces = { { 0, "Open" }, { 2, "Delete" }, { 1, "Back" } };
    omniFxPush(std::move(p));
}
// Options > Browse tile (OmniQuickMenu.h)
static void omniHltQuickTiles(OmniFxPanel& p)
{
    omniHltLoad();
    OmniFxRow r; r.id = OHLT::kTileList; r.label = "Highlights"; r.value = std::to_string(omniHltItems.size());
    p.rows.push_back(r);
}
static bool omniHltQuickAction(int id)
{
    if (id != OHLT::kTileList) return false;
    omniHltShow();   // on top of the menu (Circle comes back)
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniTextSelect.h" // OMNI_TEXT_SELECT_V1: Select text (pure: page script, clipboard cap, actions)\n',
         '#include "OmniTextSelect.h" // OMNI_TEXT_SELECT_V1: Select text (pure: page script, clipboard cap, actions)\n'
         '#include "OmniHighlights.h" // ' + MARK + ': highlights (pure: store, URL key, page script)\n'),
        ('void finished(WKPageRef page, WKNavigationRef, WKTypeRef, const void* info)\n',
         'static void omniHltFinished(Tab& tab); // ' + MARK + ' (OmniHighlightsShell.h): re-apply saved highlights\n'
         'void finished(WKPageRef page, WKNavigationRef, WKTypeRef, const void* info)\n'),
        ('    omniEverydayFinished(tab); // OMNI_EVERYDAY_V1: history, new-tab page, find bar\n',
         '    omniEverydayFinished(tab); // OMNI_EVERYDAY_V1: history, new-tab page, find bar\n'
         '    omniHltFinished(tab); // ' + MARK + ': this page\'s saved highlights\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniTextSelectShell.h" // OMNI_TEXT_SELECT_V1: Select text (page menu row, selecting layer, actions)\n',
         '#include "OmniTextSelectShell.h" // OMNI_TEXT_SELECT_V1: Select text (page menu row, selecting layer, actions)\n'
         '#include "OmniHighlightsShell.h" // ' + MARK + ': Highlight, re-apply on load, Highlights panel\n'),
    ],
    'OmniQuickMenu.h': [
        ('static bool omniRlQuickAction(int id); // OMNI_READING_LIST_V1\n',
         'static bool omniRlQuickAction(int id); // OMNI_READING_LIST_V1\n'
         'static void omniHltQuickTiles(OmniFxPanel& p); // ' + MARK + ' (OmniHighlightsShell.h)\n'
         'static bool omniHltQuickAction(int id); // ' + MARK + '\n'),
        ('    omniRlQuickTiles(p); // OMNI_READING_LIST_V1: Save page for later, Reading list\n',
         '    omniRlQuickTiles(p); // OMNI_READING_LIST_V1: Save page for later, Reading list\n'
         '    omniHltQuickTiles(p); // ' + MARK + ': Highlights\n'),
        ('    case OmniReadingList::kTileSave: case OmniReadingList::kTileList: return 1; // OMNI_READING_LIST_V1: Browse\n',
         '    case OmniReadingList::kTileSave: case OmniReadingList::kTileList: return 1; // OMNI_READING_LIST_V1: Browse\n'
         '    case OmniHighlights::kTileList: return 1; // ' + MARK + ': Browse\n'),
        ('    if (omniRlQuickAction(r.id)) return true; // OMNI_READING_LIST_V1\n',
         '    if (omniRlQuickAction(r.id)) return true; // OMNI_READING_LIST_V1\n'
         '    if (omniHltQuickAction(r.id)) return true; // ' + MARK + '\n'),
    ],
    'OmniTextSelectShell.h': [
        ('static void omniTslActionsBuild(OmniFxPanel& p)\n',
         'static void omniHltActionRow(OmniFxPanel& p); // ' + MARK + ' (OmniHighlightsShell.h): the Highlight row\n'
         'static void omniHltCreate();\n'
         'static void omniTslActionsBuild(OmniFxPanel& p)\n'),
        ('        OmniFxRow r; r.id = 1 + int(it.action); r.label = it.label; r.enabled = it.enabled;\n'
         '        p.rows.push_back(r);\n'
         '    }\n',
         '        OmniFxRow r; r.id = 1 + int(it.action); r.label = it.label; r.enabled = it.enabled;\n'
         '        p.rows.push_back(r);\n'
         '    }\n'
         '    omniHltActionRow(p); // ' + MARK + ': Highlight\n'),
        ('    const std::string text = p.text;                  // p is gone after omniFxCloseAll\n',
         '    if (r.id == OmniHighlights::kActionId) { omniFxCloseAll(); omniHltCreate(); omniTslEnd(true); return true; } // ' + MARK + ': the page script reads the selection before the clear\n'
         '    const std::string text = p.text;                  // p is gone after omniFxCloseAll\n'),
    ],
}


def variants(old0, s):
    """The anchor with the file's own line endings (mixed files: whichever spelling is present)."""
    for e in ('\r\n', '\n'):
        old = old0.replace('\n', e)
        if s.count(old):
            return old, e
    return old0, '\n'


# r2 edits (OMNI_HIGHLIGHTS_V1_R2): the per-tab saved-copy flag. Both insert BEFORE their anchor so a fresh chain
# (reading progress applied later) and an upgraded tree end up byte-identical.
EDITS_R2 = {
    'OmniBrowser.cpp': [
        ('    bool omniTaMuted = false;  // OMNI_TAB_AUDIO_V1: the user muted this tab (per tab, never saved)\n',
         '    uint8_t omniHltSaved = 0; // ' + REV + ': 1 the reading list is loading a saved copy here, 2 that copy is shown (banner trusted)\n'
         '    bool omniTaMuted = false;  // OMNI_TAB_AUDIO_V1: the user muted this tab (per tab, never saved)\n'),
    ],
    'OmniReadingListShell.h': [
        ('            WKPageLoadHTMLString(t->page, s.get(), nullptr);\n',
         '            t->omniHltSaved = 1; // ' + REV + ': this tab loads a saved copy (OmniHighlightsShell.h trusts its banner)\n'
         '            WKPageLoadHTMLString(t->page, s.get(), nullptr);\n'),
    ],
}


def apply_edits(name, s, edits, mark):
    """In memory: the edits (each anchor exactly once) unless `mark` is already there."""
    if mark in s:
        return s, False
    for old0, new0 in edits:
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
    for name, need, tool in (('OmniBrowser.cpp', 'OMNI_TEXT_SELECT_V1', 'apply_text_select.py'),
                             ('OmniBrowser.cpp', 'OMNI_TAB_AUDIO_V1', 'apply_tab_audio.py'),
                             ('OmniTextSelectShell.h', 'OMNI_TEXT_SELECT_V1', 'apply_text_select.py'),
                             ('OmniQuickMenu.h', 'OMNI_READING_LIST_V1', 'apply_reading_list.py'),
                             ('OmniReadingListShell.h', 'omniRlOpenSaved', 'apply_reading_list.py')):
        if not (root / name).exists() or need not in (root / name).read_bytes().decode('utf-8'):
            sys.exit('%s: %s missing: %s first' % (name, need, tool))
    out = {}
    for name in sorted(set(EDITS) | set(EDITS_R2)):   # every file is patched in memory (every anchor checked) first
        s0 = (root / name).read_bytes().decode('utf-8')
        s, r1 = apply_edits(name, s0, EDITS.get(name, []), MARK) if name in EDITS else (s0, False)
        s, r2 = apply_edits(name, s, EDITS_R2[name], REV) if name in EDITS_R2 else (s, False)
        out[name] = (s0, s, r1, r2)
    msgs = [write_new('OmniHighlights.h', PURE, 'OmniTextSelect.h'),
            write_new('OmniHighlightsShell.h', SHELL, 'OmniTextSelectShell.h')]
    for name, (s0, s, r1, r2) in out.items():
        if s != s0:
            (root / name).write_bytes(s.encode('utf-8'))
        msgs.append(name + (': applied' if r1 else ': upgraded (r2)' if r2 else ': already'))
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK + ' (r2)')


main()
