// OMNI_CLEAR_ON_EXIT_V1: the pure part of Browser settings > "Clear on exit..." (no SDL, no WebKit).
// The shell side is OmniClearOnExitShell.h (written by tools/apply_clear_on_exit.py, which has the reasons).
// Tested on the host with g++ (tools/test_clear_on_exit.cpp; tools/test_clear_on_exit_db.py adds real SQLite files).
//
// What is here: the settings file (clear-on-exit.txt), host keys and the kept-site rule (subdomains included), the
// cookie-domain reader for Curl's Cookies.db / Cookies.db-wal (read-only SQLite page walk), the per-site plan, texts.
#pragma once
#include <cstddef>
#include <cstdint>
#include <set>
#include <string>
#include <vector>

namespace OmniClearOnExit {

constexpr const char* kFile = "clear-on-exit.txt";                         // under /data/omni/
constexpr const char* kHeader = "# Omni clear on exit v1";
constexpr const char* kCookieDb = "/data/omni/browser-profile/Cookies.db";  // main(): profile + "/Cookies.db"
constexpr int kPanelKind = 7733;
constexpr int kRowCookies = 7734, kRowHistory = 7735, kRowCache = 7736, kRowAddCurrent = 7737, kRowNone = 7738;
constexpr int kRowSite0 = 7740;              // + index of the kept site (at most kMaxKeep rows)
constexpr size_t kMaxKeep = 100;             // kept sites
constexpr size_t kMaxCalls = 1500;           // per-site cookie deletions of one start (kept sites listed)
constexpr size_t kMaxDbBytes = 32u << 20;    // Cookies.db / -wal bytes read (each)
constexpr size_t kMaxFileBytes = 64u << 10;  // clear-on-exit.txt
constexpr size_t kHostMax = 253;
constexpr uint32_t kNativeMs = 20000;        // the summary is shown after this, whatever has not answered

// SDL_GetTicks() style milliseconds (wrap-safe).
inline bool expired(uint32_t startedAt, uint32_t now) { return uint32_t(now - startedAt) >= kNativeMs; }

inline char lower(char c) { return c >= 'A' && c <= 'Z' ? char(c + ('a' - 'A')) : c; }
inline bool endsWith(const std::string& s, const std::string& tail)
{
    return s.size() >= tail.size() && s.compare(s.size() - tail.size(), tail.size(), tail) == 0;
}

// --- hosts -----------------------------------------------------------------------------------------------------------
// A host, an http(s) address or a cookie domain (".example.com") -> "example.com": lower case, no scheme / user /
// port / path, no leading or trailing dots, "www." dropped while a dot remains. "" for anything else (other schemes,
// IPv6, bad characters, empty labels, labels over 63 characters, labels starting or ending with '-').
inline std::string hostKey(const std::string& in)
{
    size_t b = 0, e = in.size();
    auto space = [](char c) { return c == ' ' || c == '\t' || c == '\r' || c == '\n'; };
    while (b < e && space(in[b])) ++b;
    while (e > b && space(in[e - 1])) --e;
    std::string s;
    s.reserve(e - b);
    for (size_t i = b; i < e; ++i) s += lower(in[i]);
    const size_t scheme = s.find("://");
    if (scheme != std::string::npos) {
        const std::string sc = s.substr(0, scheme);
        if (sc != "http" && sc != "https") return {};
        s.erase(0, scheme + 3);
    }
    const size_t end = s.find_first_of("/?#");
    if (end != std::string::npos) s.resize(end);
    const size_t at = s.rfind('@');
    if (at != std::string::npos) s.erase(0, at + 1);
    if (!s.empty() && s[0] == '[') return {};
    const size_t colon = s.find(':');
    if (colon != std::string::npos) {
        const std::string port = s.substr(colon + 1);
        if (port.empty() || port.size() > 5) return {};
        for (char c : port) if (c < '0' || c > '9') return {};
        s.resize(colon);
    }
    while (!s.empty() && s[0] == '.') s.erase(0, 1);
    while (!s.empty() && s.back() == '.') s.pop_back();
    if (s.empty() || s.size() > kHostMax) return {};
    size_t start = 0;
    while (true) {
        const size_t dot = s.find('.', start);
        const size_t len = (dot == std::string::npos ? s.size() : dot) - start;
        if (len == 0 || len > 63 || s[start] == '-' || s[start + len - 1] == '-') return {};
        for (size_t i = start; i < start + len; ++i) {
            const char c = s[i];
            if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '-' || c == '_')) return {};
        }
        if (dot == std::string::npos) break;
        start = dot + 1;
    }
    if (s.compare(0, 4, "www.") == 0 && s.find('.', 4) != std::string::npos) s.erase(0, 4);
    return s;
}

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

// The site a host belongs to, by the same heuristic as OmniSiteClear::siteOf (last two labels, three for co.uk-style
// ccTLD second levels; IPs and one- / two-label hosts stay). It may be WIDER than WebKit's registrable domain
// (alice.github.io -> github.io), which only makes the kept-site rule keep more: see related().
inline std::string siteKey(const std::string& host)
{
    if (host.empty() || isIPv4(host)) return host;
    std::vector<std::string> labels;
    size_t start = 0;
    while (true) {
        const size_t dot = host.find('.', start);
        labels.push_back(host.substr(start, dot == std::string::npos ? std::string::npos : dot - start));
        if (dot == std::string::npos) break;
        start = dot + 1;
    }
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
inline bool under(const std::string& host, const std::string& parent)
{
    return host.size() > parent.size() && endsWith(host, "." + parent);
}
// Two host keys whose cookies WebKit may treat as one site. WebKit deletes cookies by registrable domain (libpsl), so a
// deletion for accounts.example.com also takes example.com's: a candidate related to a kept site is never deleted.
// Same host, one under the other, or the same siteKey (which is never narrower than the registrable domain for the
// usual suffixes; for a private suffix like github.io it is wider, so more is kept, never less).
inline bool related(const std::string& a, const std::string& b)
{
    if (a.empty() || b.empty()) return false;
    if (a == b || under(a, b) || under(b, a)) return true;
    return siteKey(a) == siteKey(b);
}
// The index of the kept site covering `host` (a host key), -1: none.
inline int keptBy(const std::string& host, const std::vector<std::string>& keep)
{
    for (size_t i = 0; i < keep.size(); ++i) if (related(host, keep[i])) return int(i);
    return -1;
}

// --- settings ----------------------------------------------------------------------------------------------------------
struct Settings {
    bool cookies = false, history = false, cache = false;   // all off by default
    std::vector<std::string> keep;                         // host keys, A-Z, unique, at most kMaxKeep
};
inline bool any(const Settings& s) { return s.cookies || s.history || s.cache; }

// false: not a host, already listed exactly, or the list is full.
inline bool addKeep(Settings& s, const std::string& hostOrUrl)
{
    const std::string h = hostKey(hostOrUrl);
    if (h.empty() || s.keep.size() >= kMaxKeep) return false;
    auto it = s.keep.begin();
    while (it != s.keep.end() && *it < h) ++it;
    if (it != s.keep.end() && *it == h) return false;
    s.keep.insert(it, h);
    return true;
}
inline bool removeExact(Settings& s, const std::string& host)
{
    for (auto it = s.keep.begin(); it != s.keep.end(); ++it)
        if (*it == host) { s.keep.erase(it); return true; }
    return false;
}
// Every kept site covering hostOrUrl (Site settings' "Keep cookies on exit" Off); returns what went.
inline std::vector<std::string> removeRelated(Settings& s, const std::string& hostOrUrl)
{
    std::vector<std::string> gone;
    const std::string h = hostKey(hostOrUrl);
    if (h.empty()) return gone;
    std::vector<std::string> left;
    for (auto& k : s.keep) (related(h, k) ? gone : left).push_back(k);
    s.keep.swap(left);
    return gone;
}

// clear-on-exit.txt:
//   # Omni clear on exit v1
//   cookies=1
//   history=0
//   cache=1
//   keep=example.com
// Unknown lines are skipped; CRLF is fine; bad / duplicate hosts are dropped; at most kMaxKeep hosts.
inline Settings parse(const std::string& text)
{
    Settings s;
    size_t p = 0;
    while (p < text.size()) {
        size_t nl = text.find('\n', p);
        if (nl == std::string::npos) nl = text.size();
        std::string line = text.substr(p, nl - p);
        p = nl + 1;
        while (!line.empty() && (line.back() == '\r' || line.back() == ' ' || line.back() == '\t')) line.pop_back();
        if (line.empty() || line[0] == '#') continue;
        const size_t eq = line.find('=');
        if (eq == std::string::npos) continue;
        const std::string key = line.substr(0, eq), val = line.substr(eq + 1);
        if (key == "cookies") s.cookies = val == "1";
        else if (key == "history") s.history = val == "1";
        else if (key == "cache") s.cache = val == "1";
        else if (key == "keep") addKeep(s, val);
    }
    return s;
}
inline std::string serialize(const Settings& s)
{
    std::string out = std::string(kHeader) + "\n";
    out += std::string("cookies=") + (s.cookies ? "1" : "0") + "\n";
    out += std::string("history=") + (s.history ? "1" : "0") + "\n";
    out += std::string("cache=") + (s.cache ? "1" : "0") + "\n";
    for (const auto& k : s.keep) out += "keep=" + k + "\n";
    return out;
}

// --- cookie domains from Curl's cookie database ----------------------------------------------------------------------------
// WebKit's C API here cannot list cookie hosts (WKCookieManagerGetHostnamesWithCookies has an empty body; there is no
// fetch-records call for cookies), so the start-up sweep reads Cookies.db and Cookies.db-wal itself, READ-ONLY, before
// the network process opens them. Table "Cookie"(name, value, domain, path, ...), indexes domain_index(domain),
// path_index(path) and the UNIQUE(name, domain, path) autoindex. Every b-tree page (main file, and each page image in
// the WAL) is walked: table-leaf cells with a text path starting with '/' give column 2; index cells with 2 columns
// give column 0 (not a path), with 4 columns column 1. Only bytes local to the page are read (an overflowing record
// whose domain lies past the local part is skipped; the index cells, which are short, still have it). Anything odd
// (a freelist page that looks like a b-tree page, a damaged file) yields junk or nothing: every candidate is checked
// against the kept sites before it is deleted, and deleting a junk name does nothing, so junk is harmless.
inline uint32_t be16(const unsigned char* p) { return (uint32_t(p[0]) << 8) | p[1]; }
inline uint32_t be32(const unsigned char* p) { return (uint32_t(p[0]) << 24) | (uint32_t(p[1]) << 16) | (uint32_t(p[2]) << 8) | p[3]; }
inline bool varint(const unsigned char* p, size_t end, size_t& i, uint64_t& v)
{
    v = 0;
    for (int k = 0; k < 9; ++k) {
        if (i >= end) return false;
        const unsigned char c = p[i++];
        if (k == 8) { v = (v << 8) | c; return true; }
        v = (v << 7) | (c & 0x7f);
        if (!(c & 0x80)) return true;
    }
    return true;
}
inline bool serialSize(uint64_t t, size_t& size)
{
    static const size_t fixed[10] = { 0, 1, 2, 3, 4, 6, 8, 8, 0, 0 };
    if (t < 10) { size = fixed[t]; return true; }
    if (t < 12) return false;   // reserved
    size = size_t((t - (t & 1 ? 13 : 12)) / 2);
    return true;
}
struct Col { uint64_t type = 0; size_t off = 0, size = 0; };
// A record (header + body) of `len` local bytes; columns whose bytes lie past `len` keep their place (size checked later).
inline bool record(const unsigned char* p, size_t len, std::vector<Col>& cols)
{
    cols.clear();
    size_t i = 0;
    uint64_t h;
    if (!varint(p, len, i, h) || h < 1 || h > len) return false;
    size_t off = size_t(h);
    while (i < h) {
        uint64_t t;
        if (!varint(p, size_t(h), i, t)) return false;
        size_t sz;
        if (!serialSize(t, sz)) return false;
        cols.push_back({ t, off, sz });
        off += sz;
        if (cols.size() > 64) return false;
    }
    return true;
}
inline bool isText(const Col& c) { return c.type >= 13 && (c.type & 1); }
inline bool textOf(const unsigned char* p, size_t len, const Col& c, std::string& out)
{
    if (!isText(c) || c.off > len || c.size > len - c.off) return false;
    out.assign(reinterpret_cast<const char*>(p) + c.off, c.size);
    return true;
}
// Bytes of a payload of size P kept on the b-tree page itself (SQLite file format, "cell payload overflow").
inline size_t localBytes(uint64_t P, size_t U, bool tableLeaf)
{
    const size_t X = tableLeaf ? U - 35 : ((U - 12) * 64 / 255) - 23;
    if (P <= X) return size_t(P);
    const size_t M = ((U - 12) * 32 / 255) - 23;
    const size_t K = M + size_t((P - M) % (U - 4));
    return K <= X ? K : M;
}
// One page (`hdrOff`: 100 on page 1, else 0; `U`: usable bytes = page size - reserved).
inline void pageDomains(const unsigned char* page, size_t U, size_t hdrOff, std::vector<std::string>& out)
{
    if (U < 480 || hdrOff + 12 > U) return;
    const unsigned char type = page[hdrOff];
    if (type != 0x0d && type != 0x0a && type != 0x02) return;
    const size_t cells = be16(page + hdrOff + 3);
    const size_t ptrs = hdrOff + (type == 0x02 ? 12 : 8);
    if (ptrs + cells * 2 > U) return;
    std::vector<Col> cols;
    for (size_t c = 0; c < cells; ++c) {
        size_t i = be16(page + ptrs + 2 * c);
        if (i < ptrs + cells * 2 || i >= U) continue;
        if (type == 0x02) i += 4;   // left child page number
        uint64_t P, rowid;
        if (!varint(page, U, i, P)) continue;
        if (type == 0x0d && !varint(page, U, i, rowid)) continue;
        if (P == 0 || P > (uint64_t(1) << 31)) continue;
        const size_t local = localBytes(P, U, type == 0x0d);
        if (i + local > U) continue;
        const unsigned char* rec = page + i;
        if (!record(rec, local, cols)) continue;
        std::string text, path;
        if (type == 0x0d) {   // Cookie row: name, value, domain, path, ...
            if (cols.size() < 4 || !textOf(rec, local, cols[3], path) || path.empty() || path[0] != '/') continue;
            if (textOf(rec, local, cols[2], text)) out.push_back(text);
        } else if (cols.size() == 2) {   // domain_index / path_index: key, rowid
            if (textOf(rec, local, cols[0], text) && !text.empty() && text[0] != '/') out.push_back(text);
        } else if (cols.size() == 4) {   // UNIQUE(name, domain, path) + rowid
            if (textOf(rec, local, cols[1], text)) out.push_back(text);
        }
    }
}
inline size_t pageSizeOf(uint32_t v) { return v == 1 ? 65536 : v; }
inline bool goodPageSize(size_t ps) { return ps >= 512 && ps <= 65536 && (ps & (ps - 1)) == 0; }
// The main database file. false: not an SQLite 3 file. *reserved: the file's reserved bytes per page (for the WAL).
inline bool dbDomains(const std::string& file, std::vector<std::string>& out, size_t* reserved = nullptr)
{
    static const char magic[] = "SQLite format 3";
    if (file.size() < 100 || file.compare(0, 16, std::string(magic, 16)) != 0) return false;
    const unsigned char* p = reinterpret_cast<const unsigned char*>(file.data());
    const size_t ps = pageSizeOf(be16(p + 16));
    if (!goodPageSize(ps)) return false;
    const size_t res = p[20];
    if (res >= ps - 480) return false;
    if (reserved) *reserved = res;
    for (size_t off = 0; off + ps <= file.size(); off += ps)
        pageDomains(p + off, ps - res, off == 0 ? 100 : 0, out);
    return true;
}
// The write-ahead log: a 32-byte header, then frames of a 24-byte header + one page image (page 1 has the file header).
inline bool walDomains(const std::string& file, size_t reserved, std::vector<std::string>& out)
{
    if (file.size() < 32) return false;
    const unsigned char* p = reinterpret_cast<const unsigned char*>(file.data());
    const uint32_t magic = be32(p);
    if (magic != 0x377f0682u && magic != 0x377f0683u) return false;
    const size_t ps = be32(p + 8);
    if (!goodPageSize(ps) || reserved >= ps - 480) return false;
    for (size_t off = 32; off + 24 + ps <= file.size(); off += 24 + ps) {
        const uint32_t pgno = be32(p + off);
        if (!pgno) continue;
        pageDomains(p + off + 24, ps - reserved, pgno == 1 ? 100 : 0, out);
    }
    return true;
}

// --- the plan of one start ---------------------------------------------------------------------------------------------
struct Plan {
    std::vector<std::string> hosts;   // host keys to delete cookies for (one WebKit call each), in candidate order
    size_t keptSkipped = 0;           // distinct candidates covered by a kept site
    size_t more = 0;                  // distinct candidates left out (kMaxCalls)
};
// candidates: cookie domains first, then history addresses (any of hostKey's inputs); junk and duplicates go.
inline Plan plan(const std::vector<std::string>& candidates, const std::vector<std::string>& keep, size_t max = kMaxCalls)
{
    Plan p;
    std::set<std::string> seen;
    for (const auto& c : candidates) {
        const std::string h = hostKey(c);
        if (h.empty() || !seen.insert(h).second) continue;
        if (keptBy(h, keep) >= 0) { ++p.keptSkipped; continue; }
        if (p.hosts.size() < max) p.hosts.push_back(h);
        else ++p.more;
    }
    return p;
}
// A CacheStorage origin (WKWebsiteDataStoreGetFetchCacheOrigins) is removed unless a kept site covers its host.
inline bool removeCacheOrigin(const std::string& originHost, const std::vector<std::string>& keep)
{
    const std::string h = hostKey(originHost);
    return h.empty() ? !originHost.empty() && keep.empty() : keptBy(h, keep) < 0;
}

// --- texts ---------------------------------------------------------------------------------------------------------------
inline std::string count(size_t n, const char* one, const char* many) { return std::to_string(n) + " " + (n == 1 ? one : many); }
inline const char* onOff(bool on) { return on ? "On" : "Off"; }
// Browser settings row "Clear on exit...".
inline std::string settingsValue(const Settings& s)
{
    std::vector<std::string> parts;
    if (s.cookies) parts.push_back("Cookies");
    if (s.history) parts.push_back(parts.empty() ? "History" : "history");
    if (s.cache) parts.push_back(parts.empty() ? "Cache" : "cache");
    if (parts.empty()) return "Off";
    std::string v;
    for (size_t i = 0; i < parts.size(); ++i) v += (i ? ", " : "") + parts[i];
    return v;
}
inline std::string settingsDetail(const Settings& s)
{
    if (!any(s)) return "Nothing is cleared when Omni closes";
    std::string d = "Cleared when Omni next starts";
    if (s.cookies && !s.keep.empty()) d += "; " + count(s.keep.size(), "kept site", "kept sites");
    return d;
}
inline std::string subtitle() { return "Done when Omni next starts, before any page opens. Passwords, bookmarks and the reading list are never cleared."; }
inline std::string cookiesDetail(const Settings& s)
{
    if (s.keep.empty()) return "Every site, with its storage: you will be signed out";
    return "Every site except " + count(s.keep.size(), "kept site", "kept sites") + "; site storage stays while sites are kept";
}
inline std::string historyDetail() { return "Every visit. Open tabs still come back (On start)"; }
inline std::string cacheDetail() { return "The whole cache: pages load slower once"; }
inline std::string noneLabel() { return "No kept sites"; }
inline std::string noneDetail() { return "Add one here or in Site settings > Keep cookies on exit"; }
inline std::string keptDetail() { return "Its cookies and its subdomains' stay. Cross: remove"; }
inline std::string askCookiesTitle() { return "Clear cookies every time Omni starts?"; }
inline std::string askCookiesBody(size_t keepCount)
{
    if (!keepCount)
        return "From the next start on, Omni deletes the cookies and site storage of every site before any page opens: you "
               "will be signed out everywhere. Add sites to keep their sign-ins. Private tabs are not affected.";
    return "From the next start on, Omni deletes the cookies and offline caches of every site except your "
           + count(keepCount, "kept site", "kept sites") + " before any page opens: you will be signed out of the others. "
           "Site storage stays while sites are kept. Private tabs are not affected.";
}
inline std::string askHistoryTitle() { return "Clear history every time Omni starts?"; }
inline std::string askHistoryBody()
{
    return "From the next start on, Omni deletes every history visit before any page opens. Bookmarks, the reading list, "
           "passwords and open tabs stay.";
}
inline std::string turnOnLabel() { return "Turn on"; }
// Site settings row "Keep cookies on exit".
inline std::string siteValue(const std::string& host, bool privateTab, const std::vector<std::string>& keep)
{
    if (privateTab) return "Private tab";
    if (host.empty()) return "-";
    const int k = keptBy(host, keep);
    if (k < 0) return "Off";
    return keep[size_t(k)] == host ? "On" : "On (" + keep[size_t(k)] + ")";
}
inline std::string keptNotice(const std::string& host, bool kept, bool cookiesOn)
{
    std::string s = kept ? host + ": cookies kept when Omni clears on exit" : host + ": no longer kept";
    if (kept && !cookiesOn) s += " (Clear on exit is off for cookies)";
    return s;
}
inline std::string fullNotice() { return "Up to " + std::to_string(kMaxKeep) + " kept sites: remove one first"; }

// What one start-up clear did (the shell fills it in as the parts finish).
struct Result {
    bool cookies = false, cookiesAll = false, history = false, cache = false;   // asked for (cookiesAll: no kept sites)
    size_t sites = 0, more = 0, keepCount = 0, visits = 0;
    bool cookiesOk = true, cacheOk = true, timedOut = false;
};
inline std::string summary(const Result& r)
{
    std::vector<std::string> done, left;
    if (r.cookies) {
        if (!r.cookiesOk) left.push_back(r.cookiesAll ? "cookies and site data (no answer in time)" : "some cookies (no answer in time)");
        else if (r.cookiesAll) done.push_back("cookies and site data");
        else done.push_back("cookies of " + count(r.sites, "site", "sites") + " (" + count(r.keepCount, "kept site", "kept sites") + " left alone)");
        if (r.more) left.push_back("cookies of " + count(r.more, "more site", "more sites") + " (limit " + std::to_string(kMaxCalls) + ")");
    }
    if (r.history) done.push_back("history (" + count(r.visits, "visit", "visits") + ")");
    if (r.cache) { if (r.cacheOk) done.push_back("cached files"); else left.push_back("cached files (no answer in time)"); }
    std::string s = "Clear on exit: ";
    if (done.empty()) s += "nothing cleared.";
    else {
        s += "cleared ";
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

} // namespace OmniClearOnExit
