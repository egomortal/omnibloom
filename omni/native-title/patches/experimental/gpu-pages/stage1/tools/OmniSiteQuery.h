// OMNI_SITE_SEARCH_SUGGEST_V1: the pure part of "Search this site" (no SDL, no WebKit): the site host of the page
// being shown (http / https only, public-looking names only), the "is the typed text an address?" decision (the
// address bar's own rule plus the search-shortcut one), the query "site:<host> <text>" and the row's title. The
// shell side is OmniSiteQueryShell.h; the reasons are in tools/apply_site_search_suggest.py.
// Tested on the host with g++ (tools/test_site_query.cpp).
#pragma once
#include <cstddef>
#include <string>

namespace OmniSiteQuery {

constexpr size_t kMaxHost = 253, kMaxLabel = 63;
constexpr size_t kMaxShown = 60;   // bytes of the typed text shown in the row's title (then an ellipsis)

inline char low(char c) { return c >= 'A' && c <= 'Z' ? char(c - 'A' + 'a') : c; }
inline std::string lowerStr(std::string s) { for (auto& c : s) c = low(c); return s; }
inline bool isWs(char c) { return c == ' ' || c == '\t' || c == '\r' || c == '\n'; }
inline std::string trim(const std::string& s)
{
    size_t a = 0, b = s.size();
    while (a < b && isWs(s[a])) ++a;
    while (b > a && isWs(s[b - 1])) --b;
    return s.substr(a, b - a);
}
inline bool startsWith(const std::string& s, const char* p) { return s.rfind(p, 0) == 0; }

// The site of a page address: "https://www.Example.co.uk:8443/a?b#c" -> "example.co.uk". Empty (no offer) for
// anything but http / https, user:password@ addresses, IP literals, single-label and local-only names
// (localhost, *.local, *.lan, *.internal, *.home.arpa ...), and names with characters outside a-z 0-9 - . (WebKit
// hands IDN hosts over as xn-- punycode, which passes).
inline std::string hostOf(const std::string& url)
{
    const std::string l = lowerStr(url);
    size_t at;
    if (startsWith(l, "https://")) at = 8;
    else if (startsWith(l, "http://")) at = 7;
    else return std::string();
    const size_t end = l.find_first_of("/?#\\", at);
    std::string auth = l.substr(at, end == std::string::npos ? std::string::npos : end - at);
    if (auth.find('@') != std::string::npos) return std::string();     // credentials in the address: never offered
    if (!auth.empty() && auth[0] == '[') return std::string();          // IPv6 literal
    const size_t colon = auth.find(':');
    if (colon != std::string::npos) {
        for (size_t k = colon + 1; k < auth.size(); ++k) if (auth[k] < '0' || auth[k] > '9') return std::string();
        auth.resize(colon);
    }
    if (!auth.empty() && auth.back() == '.') auth.pop_back();            // "example.com." (fully qualified)
    if (auth.empty() || auth.size() > kMaxHost) return std::string();
    size_t labels = 0, start = 0;
    std::string last;
    for (;;) {
        const size_t dot = auth.find('.', start);
        const std::string lab = auth.substr(start, dot == std::string::npos ? std::string::npos : dot - start);
        if (lab.empty() || lab.size() > kMaxLabel || lab.front() == '-' || lab.back() == '-') return std::string();
        for (char c : lab)
            if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '-')) return std::string();
        ++labels;
        last = lab;
        if (dot == std::string::npos) break;
        start = dot + 1;
    }
    if (labels < 2) return std::string();
    bool digits = true;
    for (char c : last) if (c < '0' || c > '9') digits = false;
    if (digits) return std::string();                                     // 192.168.0.20 and the like
    for (const char* tld : { "localhost", "local", "lan", "internal", "intranet", "arpa", "test", "invalid", "home" })
        if (last == tld) return std::string();
    if (startsWith(auth, "www.") && auth.find('.', 4) != std::string::npos) auth.erase(0, 4);   // www.x.com -> x.com
    return auth;
}

// True when the typed text would be loaded as an address rather than searched, by either rule Omni uses: the
// address bar's destination() (http(s)://, or no space and a dot) and the search shortcuts' looksLikeUrl (other
// schemes, "x://", a colon or dot in a single word). "omni:" pages count as addresses too.
inline bool looksLikeAddress(const std::string& typed)
{
    const std::string l = lowerStr(trim(typed));
    for (const char* p : { "http://", "https://", "omni:", "about:", "data:", "javascript:", "file:", "blob:",
                           "view-source:" })
        if (startsWith(l, p)) return true;
    const size_t sp = l.find_first_of(" \t");
    if (l.substr(0, sp).find("://") != std::string::npos) return true;
    if (sp == std::string::npos && (l.find('.') != std::string::npos || l.find(':') != std::string::npos)) return true;
    return false;
}

// The typed text that gets a "Search <host>" row: not empty, not an address, and not already scoped by the user
// ("site:" anywhere, any case).
inline bool isSearchText(const std::string& typed)
{
    const std::string t = trim(typed);
    if (t.empty() || looksLikeAddress(t)) return false;
    return lowerStr(t).find("site:") == std::string::npos;
}

// "site:<host> <text>" (text trimmed; the engine's own encoding is applied later by omniSearchUrlFor).
inline std::string query(const std::string& host, const std::string& typed) { return "site:" + host + " " + trim(typed); }

// The row's title: Search <host> for "<text>" with typographic quotes; long text is cut at a UTF-8 boundary.
inline std::string title(const std::string& host, const std::string& typed)
{
    std::string t = trim(typed);
    if (t.size() > kMaxShown) {
        size_t n = kMaxShown;
        while (n > 0 && (static_cast<unsigned char>(t[n]) & 0xC0) == 0x80) --n;
        t.resize(n);
        t += "\xE2\x80\xA6";
    }
    return "Search " + host + " for \xE2\x80\x9C" + t + "\xE2\x80\x9D";
}

struct Offer { std::string host, query, title; };
// Everything at once: the page shown (its address) and what is typed; false = no row.
inline bool offer(const std::string& pageUrl, const std::string& typed, Offer& o)
{
    if (!isSearchText(typed)) return false;
    const std::string h = hostOf(pageUrl);
    if (h.empty()) return false;
    o.host = h;
    o.query = query(h, typed);
    o.title = title(h, typed);
    return true;
}

} // namespace OmniSiteQuery
