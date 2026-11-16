// OMNI_SITE_SEARCH_V1: the pure part of site search shortcuts (no SDL, no WebKit): a small, strict OpenSearch
// description parser (ShortName + the text/html Url template), template conversion ({searchTerms} -> %s, the other
// parameters filled or dropped) checked by OmniSearchEngine::check (https only, exactly one %s) and by
// OmniSearchTiles::validTemplate (the shortcut file's own rule), keyword rules, edits of search-shortcuts.txt that keep
// its format (and every line they do not touch), and the page script that fetches the description from the page's own
// context. The shell side is OmniSiteSearchShell.h; the reasons are in tools/apply_site_search.py.
// Tested on the host with g++ (tools/test_site_search.cpp) and node (tools/test_site_search_js.mjs).
#pragma once
#include "OmniSearchEngine.h"
#include "OmniSearchTiles.h"
#include <cstddef>
#include <cstdint>
#include <map>
#include <set>
#include <string>
#include <vector>

namespace OmniSiteSearch {

constexpr size_t kMaxXml = 16384;          // bytes of description accepted (the page script refuses more)
constexpr size_t kMaxDepth = 16, kMaxElements = 512, kMaxAttrs = 32, kMaxName = 40;
constexpr int kPanelKind = 7620, kManagerKind = 7621;   // the confirm panel, the Search shortcuts list
constexpr int kRowKeyword = 1, kRowWhere = 2, kRowAdd = 3, kRowCancel = 4, kRowEmpty = 5, kRowEntry = 100;   // panel-local
constexpr const char* kTag = "omni-sse\n";          // page script answers: kTag + the XML
constexpr const char* kTagNone = "omni-sse-none";   // no <link rel=search> on the page
constexpr const char* kTagFail = "omni-sse-fail";   // a link, but the fetch failed / was refused / too big

inline char lower(char c) { return c >= 'A' && c <= 'Z' ? char(c - 'A' + 'a') : c; }
inline std::string lowerStr(std::string s) { for (auto& c : s) c = lower(c); return s; }
inline bool isWs(char c) { return c == ' ' || c == '\t' || c == '\r' || c == '\n'; }
inline bool startsWith(const std::string& s, size_t at, const char* p)
{
    for (size_t k = 0; p[k]; ++k) if (at + k >= s.size() || s[at + k] != p[k]) return false;
    return true;
}

// --- XML (just enough of it) -----------------------------------------------------------------------------------------
// Entities: the five predefined ones and numeric references (valid XML characters only). Anything else ("&foo;", a
// bare '&') fails: no DTD is ever read, so no entity can expand (a DOCTYPE fails the whole document).
inline void putUtf8(std::string& out, uint32_t cp)
{
    if (cp < 0x80) out += char(cp);
    else if (cp < 0x800) { out += char(0xC0 | (cp >> 6)); out += char(0x80 | (cp & 0x3F)); }
    else if (cp < 0x10000) { out += char(0xE0 | (cp >> 12)); out += char(0x80 | ((cp >> 6) & 0x3F)); out += char(0x80 | (cp & 0x3F)); }
    else { out += char(0xF0 | (cp >> 18)); out += char(0x80 | ((cp >> 12) & 0x3F)); out += char(0x80 | ((cp >> 6) & 0x3F)); out += char(0x80 | (cp & 0x3F)); }
}
inline bool xmlChar(uint32_t cp)
{
    return cp == 0x9 || cp == 0xA || cp == 0xD || (cp >= 0x20 && cp <= 0xD7FF) || (cp >= 0xE000 && cp <= 0xFFFD) || (cp >= 0x10000 && cp <= 0x10FFFF);
}
inline bool decodeEntities(const std::string& in, std::string& out)
{
    out.clear();
    for (size_t i = 0; i < in.size(); ++i) {
        if (in[i] != '&') { out += in[i]; continue; }
        const size_t semi = in.find(';', i);
        if (semi == std::string::npos || semi - i > 12) return false;
        const std::string e = in.substr(i + 1, semi - i - 1);
        i = semi;
        if (e == "amp") out += '&';
        else if (e == "lt") out += '<';
        else if (e == "gt") out += '>';
        else if (e == "quot") out += '"';
        else if (e == "apos") out += '\'';
        else if (e.size() >= 2 && e[0] == '#') {
            const bool hex = e[1] == 'x';
            const size_t from = hex ? 2 : 1;
            if (from >= e.size() || e.size() - from > 8) return false;
            uint32_t cp = 0;
            for (size_t k = from; k < e.size(); ++k) {
                const char c = e[k];
                int d;
                if (c >= '0' && c <= '9') d = c - '0';
                else if (hex && c >= 'a' && c <= 'f') d = c - 'a' + 10;
                else if (hex && c >= 'A' && c <= 'F') d = c - 'A' + 10;
                else return false;
                cp = cp * (hex ? 16 : 10) + uint32_t(d);
                if (cp > 0x10FFFF) return false;
            }
            if (!xmlChar(cp)) return false;
            putUtf8(out, cp);
        } else return false;
    }
    return true;
}
inline std::string localName(const std::string& qname)
{
    const size_t c = qname.rfind(':');
    return c == std::string::npos ? qname : qname.substr(c + 1);
}
inline bool nameStart(char c) { return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || c == '_' || c == ':' || (unsigned char)c >= 0x80; }
inline bool nameChar(char c) { return nameStart(c) || (c >= '0' && c <= '9') || c == '-' || c == '.'; }

struct UrlEl { std::string type, method, rel, tmpl; };
struct Doc {
    bool ok = false;
    std::string why;                       // when !ok
    std::string shortName;                 // decoded text, raw (see cleanName)
    std::vector<UrlEl> urls;               // the root's Url children, in order
};
// A strict, bounded pass over the document: one root element named (local name) OpenSearchDescription; its direct
// ShortName / Url children are read; comments, processing instructions and CDATA are allowed; DOCTYPE and every other
// "<!" construct fail; at most kMaxDepth levels, kMaxElements elements, kMaxAttrs attributes each, kMaxXml bytes;
// tags must nest and close; nothing but whitespace / comments / PIs after the root.
inline Doc parseDocument(const std::string& s)
{
    Doc d;
    auto fail = [&](const char* why) { d = Doc(); d.why = why; return d; };
    if (s.empty()) return fail("empty");
    if (s.size() > kMaxXml) return fail("too big");
    std::vector<std::string> stack;
    size_t i = (s.size() >= 3 && startsWith(s, 0, "\xEF\xBB\xBF")) ? 3 : 0, elements = 0;
    bool rootSeen = false, rootDone = false, inShortName = false, gotShortName = false;
    std::string nameText;
    while (i < s.size()) {
        if (s[i] != '<') {
            const size_t lt = s.find('<', i);
            const std::string text = s.substr(i, (lt == std::string::npos ? s.size() : lt) - i);
            i = lt == std::string::npos ? s.size() : lt;
            if (stack.empty()) { for (char c : text) if (!isWs(c)) return fail("text outside the root"); continue; }
            std::string dec;
            if (!decodeEntities(text, dec)) return fail("bad entity");
            if (inShortName) nameText += dec;
            continue;
        }
        if (startsWith(s, i, "<?")) {
            const size_t e = s.find("?>", i + 2);
            if (e == std::string::npos) return fail("unterminated <?");
            i = e + 2;
            continue;
        }
        if (startsWith(s, i, "<!--")) {
            const size_t e = s.find("-->", i + 4);
            if (e == std::string::npos) return fail("unterminated comment");
            i = e + 3;
            continue;
        }
        if (startsWith(s, i, "<![CDATA[")) {
            const size_t e = s.find("]]>", i + 9);
            if (e == std::string::npos || stack.empty()) return fail("bad CDATA");
            if (inShortName) nameText += s.substr(i + 9, e - i - 9);
            i = e + 3;
            continue;
        }
        if (startsWith(s, i, "<!")) return fail("DOCTYPE / declarations not allowed");
        if (startsWith(s, i, "</")) {
            size_t k = i + 2;
            while (k < s.size() && nameChar(s[k])) ++k;
            const std::string name = s.substr(i + 2, k - i - 2);
            while (k < s.size() && isWs(s[k])) ++k;
            if (k >= s.size() || s[k] != '>' || stack.empty() || stack.back() != name) return fail("mismatched end tag");
            if (inShortName && stack.size() == 2) { inShortName = false; if (!gotShortName) { d.shortName = nameText; gotShortName = true; } }
            stack.pop_back();
            if (stack.empty()) rootDone = true;
            i = k + 1;
            continue;
        }
        // a start tag
        if (rootDone) return fail("content after the root");
        size_t k = i + 1;
        if (k >= s.size() || !nameStart(s[k])) return fail("bad tag");
        while (k < s.size() && nameChar(s[k])) ++k;
        const std::string name = s.substr(i + 1, k - i - 1), local = localName(name);
        if (++elements > kMaxElements) return fail("too many elements");
        std::vector<std::pair<std::string, std::string>> attrs;
        bool selfClose = false;
        while (true) {
            const size_t before = k;
            while (k < s.size() && isWs(s[k])) ++k;
            if (k >= s.size()) return fail("unterminated tag");
            if (s[k] == '>') { ++k; break; }
            if (s[k] == '/') { if (k + 1 < s.size() && s[k + 1] == '>') { selfClose = true; k += 2; break; } return fail("bad tag"); }
            if (k == before || !nameStart(s[k])) return fail("bad attribute");
            const size_t a0 = k;
            while (k < s.size() && nameChar(s[k])) ++k;
            const std::string an = s.substr(a0, k - a0);
            while (k < s.size() && isWs(s[k])) ++k;
            if (k >= s.size() || s[k] != '=') return fail("attribute without a value");
            ++k;
            while (k < s.size() && isWs(s[k])) ++k;
            if (k >= s.size() || (s[k] != '"' && s[k] != '\'')) return fail("unquoted attribute");
            const char q = s[k++];
            const size_t e = s.find(q, k);
            if (e == std::string::npos) return fail("unterminated attribute");
            const std::string raw = s.substr(k, e - k);
            if (raw.find('<') != std::string::npos) return fail("'<' in an attribute");
            std::string val;
            if (!decodeEntities(raw, val)) return fail("bad entity");
            if (attrs.size() >= kMaxAttrs) return fail("too many attributes");
            attrs.emplace_back(localName(an), val);
            k = e + 1;
        }
        i = k;
        if (stack.empty()) {
            if (rootSeen) return fail("two roots");
            if (local != "OpenSearchDescription") return fail("not an OpenSearch description");
            rootSeen = true;
        }
        auto attr = [&](const char* n) { for (auto& a : attrs) if (a.first == n) return a.second; return std::string(); };
        if (stack.size() == 1 && local == "Url") d.urls.push_back({ attr("type"), attr("method"), attr("rel"), attr("template") });
        if (selfClose) {
            if (stack.empty()) rootDone = true;
            continue;
        }
        if (stack.size() >= kMaxDepth) return fail("nested too deep");
        stack.push_back(name);
        if (stack.size() == 2 && local == "ShortName" && !gotShortName) { inShortName = true; nameText.clear(); }
    }
    if (!rootSeen || !rootDone || !stack.empty()) return fail("truncated document");
    d.ok = true;
    return d;
}

// --- templates -------------------------------------------------------------------------------------------------------
// The OpenSearch template as a shortcut template: {searchTerms} -> %s (exactly once, required); the other parameters
// filled the way Firefox does: optional ones ("{x?}") empty, required ones with their defaults (startIndex,
// startPage: 1, count: 20, language: *, input/outputEncoding: UTF-8); any other required parameter, a literal "%s",
// a stray brace, or a template that is not https fails. The result must pass OmniSearchEngine::check (https only, one
// %s, plain host, %XX) and OmniSearchTiles::validTemplate (the shortcut file's rule) or "" is returned.
inline std::string convertTemplate(const std::string& raw, std::string* why = nullptr)
{
    auto no = [&](const char* w) { if (why) *why = w; return std::string(); };
    const std::string t = OmniSearchEngine::trim(raw);
    if (t.empty()) return no("no template");
    if (t.find("%s") != std::string::npos) return no("the template already has %s");
    std::string out;
    int terms = 0;
    for (size_t i = 0; i < t.size(); ++i) {
        if (t[i] == '}') return no("stray }");
        if (t[i] != '{') { out += t[i]; continue; }
        const size_t e = t.find('}', i);
        if (e == std::string::npos) return no("unclosed {");
        std::string p = t.substr(i + 1, e - i - 1);
        i = e;
        if (p.find('{') != std::string::npos || p.empty()) return no("bad parameter");
        const bool optional = p.back() == '?';
        if (optional) p.pop_back();
        const bool prefixed = p.find(':') != std::string::npos;
        if (p == "searchTerms") { ++terms; out += "%s"; continue; }
        if (optional) continue;
        if (prefixed) return no("unknown required parameter");
        if (p == "startIndex" || p == "startPage") out += "1";
        else if (p == "count") out += "20";
        else if (p == "language") out += "*";
        else if (p == "inputEncoding" || p == "outputEncoding") out += "UTF-8";
        else return no("unknown required parameter");
    }
    if (terms == 0) return no("no {searchTerms}");
    if (terms > 1) return no("{searchTerms} more than once");
    const OmniSearchEngine::Bad bad = OmniSearchEngine::check(out);
    if (bad != OmniSearchEngine::Bad::None) return no(OmniSearchEngine::why(bad));
    if (!OmniSearchTiles::validTemplate(out)) return no("not a valid shortcut address");
    return out;
}

// --- names ---------------------------------------------------------------------------------------------------------
// The site's name as shown and saved: valid UTF-8 only (bad bytes dropped), control characters and runs of whitespace
// as one space (no TAB / newline can reach the file), trimmed, at most kMaxName bytes on a character boundary.
inline std::string cleanName(const std::string& in)
{
    std::string out;
    bool space = false;
    for (size_t i = 0; i < in.size();) {
        const unsigned char c = (unsigned char)in[i];
        size_t n = c < 0x80 ? 1 : (c >> 5) == 6 ? 2 : (c >> 4) == 14 ? 3 : (c >> 3) == 30 ? 4 : 0;
        if (n == 0 || i + n > in.size()) { ++i; continue; }
        bool good = true;
        for (size_t k = 1; k < n; ++k) if (((unsigned char)in[i + k] & 0xC0) != 0x80) good = false;
        if (n > 1 && good) {   // no overlong forms, surrogates or > U+10FFFF
            uint32_t cp = c & (0xFF >> (n + 1));
            for (size_t k = 1; k < n; ++k) cp = (cp << 6) | ((unsigned char)in[i + k] & 0x3F);
            const uint32_t minimum[] = { 0, 0, 0x80, 0x800, 0x10000 };
            if (cp < minimum[n] || (cp >= 0xD800 && cp <= 0xDFFF) || cp > 0x10FFFF || cp == 0x2028 || cp == 0x2029 || (cp >= 0x80 && cp < 0xA0)) good = false;
        }
        if (!good) { ++i; continue; }
        if (n == 1 && (c < 0x20 || c == 0x7F || c == ' ')) { space = !out.empty(); i += 1; continue; }
        if (out.size() + (space ? 1 : 0) + n > kMaxName) break;
        if (space) { out += ' '; space = false; }
        out.append(in, i, n);
        i += n;
    }
    return out;
}

struct Offer {
    bool ok = false;
    std::string why;       // when !ok
    std::string name;      // cleanName(ShortName), or the template's host when it has none
    std::string tmpl;      // https://...%s...
    std::string host;      // the template's host (lower case, no www.)
};
inline bool htmlType(const std::string& type)
{
    std::string t = lowerStr(OmniSearchEngine::trim(type.substr(0, type.find(';'))));
    return t == "text/html";
}
inline bool resultsRel(const std::string& rel)
{
    const std::string r = lowerStr(rel);
    if (OmniSearchEngine::trim(r).empty()) return true;
    size_t p = 0;
    while (p < r.size()) {
        while (p < r.size() && isWs(r[p])) ++p;
        size_t e = p;
        while (e < r.size() && !isWs(r[e])) ++e;
        if (r.compare(p, e - p, "results") == 0) return true;
        p = e;
    }
    return false;
}
// The description -> what Omni offers: the first Url (type text/html, GET, rel results or none) whose template
// converts; otherwise why the first such Url did not.
inline Offer offerFrom(const std::string& xml)
{
    Offer o;
    const Doc d = parseDocument(xml);
    if (!d.ok) { o.why = d.why; return o; }
    std::string firstWhy;
    for (const UrlEl& u : d.urls) {
        if (!htmlType(u.type)) continue;
        const std::string m = lowerStr(OmniSearchEngine::trim(u.method));
        if (!m.empty() && m != "get") { if (firstWhy.empty()) firstWhy = "POST searches are not supported"; continue; }
        if (!resultsRel(u.rel)) continue;
        std::string why;
        const std::string t = convertTemplate(u.tmpl, &why);
        if (t.empty()) { if (firstWhy.empty()) firstWhy = why; continue; }
        o.ok = true;
        o.tmpl = t;
        o.host = OmniSearchTiles::hostOf(t);
        o.name = cleanName(d.shortName);
        if (o.name.empty()) o.name = o.host;
        return o;
    }
    o.why = firstWhy.empty() ? "no text/html search address" : firstWhy;
    return o;
}

// --- the page ------------------------------------------------------------------------------------------------------
// "https://www.example.com/..." -> "example.com" (OmniSearchTiles::hostOf); "" for anything not https.
inline std::string pageSite(const std::string& url)
{
    if (lowerStr(url.substr(0, 8)) != "https://") return std::string();
    return OmniSearchTiles::hostOf(url);
}
// The template's host is the page's site or under it (or the other way round): otherwise the panel says so.
inline bool sameSite(const std::string& a, const std::string& b)
{
    if (a.empty() || b.empty()) return false;
    auto under = [](const std::string& x, const std::string& y) { return x == y || (x.size() > y.size() && x.compare(x.size() - y.size() - 1, y.size() + 1, "." + y) == 0); };
    return under(a, b) || under(b, a);
}
// Two templates search the same place (host without www. and path, query ignored): an offer already saved.
inline bool sameSearch(const std::string& a, const std::string& b)
{
    auto key = [](const std::string& t) {
        const size_t s = t.find("://");
        if (s == std::string::npos) return std::string();
        const size_t e = t.find_first_of("?#", s + 3);
        const std::string rest = t.substr(s + 3, e == std::string::npos ? std::string::npos : e - s - 3);
        const size_t slash = rest.find('/');
        std::string path = slash == std::string::npos ? std::string("/") : rest.substr(slash);
        while (path.size() > 1 && path.back() == '/') path.pop_back();
        return OmniSearchTiles::hostOf(t) + path;
    };
    const std::string ka = key(a), kb = key(b);
    return !ka.empty() && ka == kb;
}
inline bool alreadySaved(const Offer& o, const std::vector<OmniSearchTiles::Engine>& list)
{
    for (const auto& e : list) if (sameSearch(e.tmpl, o.tmpl)) return true;
    return false;
}

// --- keywords ------------------------------------------------------------------------------------------------------
inline bool taken(const std::string& kw, const std::vector<OmniSearchTiles::Engine>& list, const std::string& except = std::string())
{
    for (const auto& e : list) if (e.prefix == kw && e.prefix != except) return true;
    return false;
}
// The first word of the name (letters / digits, lower case), else the first label of the host; at most 16
// characters; "2", "3", ... appended while it is taken.
inline std::string defaultKeyword(const std::string& name, const std::string& host, const std::vector<OmniSearchTiles::Engine>& list)
{
    std::string kw;
    for (char c0 : name) {
        const char c = lower(c0);
        if ((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9')) { kw += c; continue; }
        if (!kw.empty()) break;
    }
    if (kw.empty()) for (char c0 : host) { const char c = lower(c0); if ((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9')) kw += c; else break; }
    if (kw.empty()) kw = "site";
    if (kw.size() > 14) kw.resize(14);
    std::string base = kw;
    for (int n = 2; taken(kw, list) && n < 100; ++n) kw = base + std::to_string(n);
    return kw;
}
enum class KwBad { None, Invalid, Taken };
// What the user typed as a keyword: trimmed, lower case; letters, digits, '-', '_', '!', 1..16 (OmniSearchTiles's rule).
inline KwBad checkKeyword(const std::string& typed, const std::vector<OmniSearchTiles::Engine>& list, std::string& kw, const std::string& except = std::string())
{
    kw = lowerStr(OmniSearchEngine::trim(typed));
    if (!OmniSearchTiles::validPrefix(kw)) return KwBad::Invalid;
    if (taken(kw, list, except)) return KwBad::Taken;
    return KwBad::None;
}

// --- search-shortcuts.txt ------------------------------------------------------------------------------------------
// Format (OmniSearchTiles::parseFile): "prefix<TAB>template[<TAB>Name]" per line, '#' comments; the built-ins are
// used only while the file is missing. Edits keep every line they do not touch (comments, invalid lines, spacing)
// and the file's line ending (CRLF when its first line ends so).
inline std::string lineEnding(const std::string& text)
{
    const size_t n = text.find('\n');
    return n != std::string::npos && n > 0 && text[n - 1] == '\r' ? "\r\n" : "\n";
}
inline std::string entryLine(const std::string& prefix, const std::string& tmpl, const std::string& name)
{
    return prefix + "\t" + tmpl + (name.empty() ? std::string() : "\t" + cleanName(name));
}
// The text a missing file stands for: the built-ins, so adding a first site search keeps "yt", "w", ...
inline std::string builtinsText()
{
    std::string s = "# Omni search shortcuts: keyword<TAB>https://...%s<TAB>Name (type \"keyword words\" in the address bar)\n";
    for (const auto& e : OmniSearchTiles::builtins()) s += entryLine(e.prefix, e.tmpl, e.name) + "\n";
    return s;
}
// The keyword a line defines (lower case), "" for comments / blank lines (as parseFile splits it).
inline std::string linePrefix(const std::string& line0)
{
    const std::string line = OmniSearchTiles::trim(line0);
    if (line.empty() || line[0] == '#') return std::string();
    const size_t t = line.find('\t');
    const size_t cut = t != std::string::npos ? t : line.find(' ');
    if (cut == std::string::npos) return std::string();
    return lowerStr(OmniSearchTiles::trim(line.substr(0, cut)));
}
inline std::vector<std::string> splitLines(const std::string& text)
{
    std::vector<std::string> lines;
    size_t p = text.compare(0, 3, "\xEF\xBB\xBF") == 0 ? 3 : 0;
    while (p < text.size()) {
        size_t e = text.find('\n', p);
        if (e == std::string::npos) e = text.size();
        std::string l = text.substr(p, e - p);
        if (!l.empty() && l.back() == '\r') l.pop_back();
        lines.push_back(l);
        p = e + 1;
    }
    return lines;
}
inline std::string joinLines(const std::vector<std::string>& lines, const std::string& nl)
{
    std::string s;
    for (const auto& l : lines) s += l + nl;
    return s;
}
// The index of the line that defines `prefix` for parseFile (the first VALID one), -1 when none.
inline int activeLine(const std::vector<std::string>& lines, const std::string& prefix)
{
    for (size_t i = 0; i < lines.size(); ++i) {
        if (linePrefix(lines[i]) != prefix) continue;
        const auto one = OmniSearchTiles::parseFile(lines[i]);
        if (!one.empty() && one[0].prefix == prefix) return int(i);
    }
    return -1;
}
// Adds an entry at the end. exists=false: the file is missing (the built-ins are written first).
inline std::string addEntry(const std::string& text, bool exists, const std::string& prefix, const std::string& tmpl, const std::string& name)
{
    std::string base = exists ? text : builtinsText();
    const std::string nl = lineEnding(base);
    if (!base.empty() && base.back() != '\n') base += nl;
    return base + entryLine(prefix, tmpl, name) + nl;
}
// Removes the entry for `prefix`, and the dead duplicates of it (later lines parseFile ignored, which would otherwise
// come alive). Every other line is kept. *found: an active entry existed.
inline std::string removeEntry(const std::string& text, bool exists, const std::string& prefix, bool* found = nullptr)
{
    const std::string base = exists ? text : builtinsText();
    std::vector<std::string> lines = splitLines(base);
    const int at = activeLine(lines, prefix);
    if (found) *found = at >= 0;
    if (at < 0) return base;
    std::vector<std::string> keep;
    for (size_t i = 0; i < lines.size(); ++i) if (linePrefix(lines[i]) != prefix) keep.push_back(lines[i]);
    return joinLines(keep, lineEnding(base));
}
// Gives the entry for `from` the keyword `to` (its template and name kept; the line is rewritten in the TAB form);
// dead duplicates of `from` are dropped. Nothing changes when `from` has no active entry.
inline std::string renameEntry(const std::string& text, bool exists, const std::string& from, const std::string& to, bool* found = nullptr)
{
    const std::string base = exists ? text : builtinsText();
    std::vector<std::string> lines = splitLines(base);
    const int at = activeLine(lines, from);
    if (found) *found = at >= 0;
    if (at < 0) return base;
    const auto one = OmniSearchTiles::parseFile(lines[size_t(at)]);
    std::string name;   // only the name the line itself had (parseFile fills one in otherwise)
    {
        const std::string l = OmniSearchTiles::trim(lines[size_t(at)]);
        const size_t t1 = l.find('\t'), t2 = t1 == std::string::npos ? std::string::npos : l.find('\t', t1 + 1);
        if (t2 != std::string::npos) name = OmniSearchTiles::trim(l.substr(t2 + 1));
    }
    std::vector<std::string> out;
    for (size_t i = 0; i < lines.size(); ++i) {
        if (int(i) == at) out.push_back(entryLine(to, one[0].tmpl, name));
        else if (linePrefix(lines[i]) != from) out.push_back(lines[i]);
    }
    return joinLines(out, lineEnding(base));
}

// --- Browser settings: site-search.txt ("offer<TAB>1|0"); On by default -----------------------------------------------
inline bool parseOffer(const std::string& text)
{
    for (const auto& l : splitLines(text)) {
        const std::string t = OmniSearchTiles::trim(l);
        if (t.compare(0, 5, "offer") != 0) continue;
        const std::string v = OmniSearchTiles::trim(t.substr(5));
        if (v == "0") return false;
        if (v == "1") return true;
    }
    return true;
}
inline std::string offerText(bool on) { return std::string("offer\t") + (on ? "1" : "0") + "\n"; }

// --- texts ---------------------------------------------------------------------------------------------------------
inline std::string quickLabel(const Offer& o) { return "Add " + o.name + " search"; }
inline std::string hintText(const Offer& o) { return o.name + " has a search: Options > Add " + o.name + " search"; }
inline std::string whereValue(const Offer& o, const std::string& site)
{
    return o.host + (sameSite(o.host, site) ? std::string() : std::string(" (not this site)"));
}
inline std::string usage(const std::string& kw, const std::string& name) { return "Type \"" + kw + " words\" in the address bar to search " + name; }
inline const char* keywordWhy(KwBad b)
{
    return b == KwBad::Taken ? "that keyword is already used" : b == KwBad::Invalid ? "use 1-16 letters, digits, - _ or !" : "OK";
}

// --- the page script -----------------------------------------------------------------------------------------------
// The body of an async function (WKPageCallAsyncJavaScriptWithoutUserGesture), run once after a load of an https page:
// finds <link rel="search" type="application/opensearchdescription+xml" href>, fetches it FROM THE PAGE (its own
// network context: same-origin is typical; a cross-origin description without CORS fails and is skipped), https only
// (the link and the final address after redirects), no cookies, at most kMaxXml bytes (more: refused), 4 s.
// Answers kTag + XML, kTagNone or kTagFail. Everything it returns is untrusted: the shell parses it (offerFrom).
inline std::string pageScript()
{
    std::string s = "const MAX = " + std::to_string(kMaxXml) + ", TAG = \"omni-sse\\n\", NONE = \"" + kTagNone + "\", FAIL = \"" + kTagFail + "\";\n";
    s += R"JS(const later = setTimeout, stop = clearTimeout;
let link = null;
try {
  link = document.querySelector('link[rel~="search" i][type="application/opensearchdescription+xml" i][href]');
} catch (e) { return NONE; }
if (!link) return NONE;
let u;
try { u = new URL(link.getAttribute("href"), document.baseURI); } catch (e) { return FAIL; }
if (u.protocol !== "https:" || location.protocol !== "https:") return FAIL;
const ac = typeof AbortController === "function" ? new AbortController() : null;
const timer = later(() => { try { if (ac) ac.abort(); } catch (e) {} }, 4000);
try {
  const r = await fetch(u.href, { credentials: "omit", redirect: "follow", signal: ac ? ac.signal : undefined });
  if (!r || !r.ok || typeof r.url !== "string" || !r.url.startsWith("https:")) return FAIL;
  const len = Number(r.headers && r.headers.get ? r.headers.get("content-length") : NaN);
  if (len > MAX) return FAIL;
  let text = "";
  if (r.body && typeof r.body.getReader === "function" && typeof TextDecoder === "function") {
    const rd = r.body.getReader(), dec = new TextDecoder("utf-8");
    let n = 0;
    for (;;) {
      const c = await rd.read();
      if (c.done) break;
      n += c.value.length;
      if (n > MAX) { try { rd.cancel(); } catch (e) {} return FAIL; }
      text += dec.decode(c.value, { stream: true });
    }
    text += dec.decode();
  } else {
    text = await r.text();
    if (typeof text !== "string" || text.length > MAX) return FAIL;
  }
  return TAG + text;
} catch (e) {
  return FAIL;
} finally {
  stop(timer);
}
)JS";
    return s;
}
enum class Answer { Nothing, NoLink, Failed, Xml };
// The script's answer: Xml (and the text in *xml, at most kMaxXml bytes) or what happened.
inline Answer parseAnswer(const std::string& a, std::string* xml)
{
    if (a == kTagNone) return Answer::NoLink;
    if (a == kTagFail) return Answer::Failed;
    const std::string tag = kTag;
    if (a.compare(0, tag.size(), tag) != 0) return Answer::Nothing;
    if (a.size() - tag.size() > kMaxXml) return Answer::Failed;
    if (xml) *xml = a.substr(tag.size());
    return Answer::Xml;
}

} // namespace OmniSiteSearch
