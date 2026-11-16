// OMNI_BOOKMARKLETS_V1: the pure part of bookmarklets (javascript: bookmarks run on the current page). No SDL, no
// WebKit, no I/O. The shell side is OmniBookmarkletsShell.h; the reasons are in tools/apply_bookmarklets.py. Tested on
// the host with g++ (tools/test_bookmarklets.cpp).
//   - javascript: URL -> script source the way browsers do it (URL Standard input clean-up, then HTML's "javascript:
//     URL special case": percent-decode everything after the scheme, UTF-8 decode with U+FFFD for bad bytes).
//   - SHA-256 of the source: the consent key ("Always" remembers it; same code = same key however it was encoded).
//   - the consent store (/data/omni/bookmarklets.txt: one lowercase hex SHA-256 per line, newest last, at most 1000).
//   - when a bookmarklet may run (decide) and every text the shell shows.
#pragma once
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace OmniBookmarklets {

constexpr std::size_t kMaxBytes = 65536;       // the javascript: address as stored, and the decoded source
constexpr std::size_t kConsentMax = 1000;      // remembered "Always" answers
constexpr const char* kConsentFile = "bookmarklets.txt";
constexpr const char* kRunMarker = "omni-bookmarklet-ran";
constexpr int kPanelKind = 7614;               // the "Run this bookmarklet?" panel
constexpr int kAddRowId = -7;                  // bookmarks list: "Add bookmarklet" (-1..-5, -100 down are taken)
constexpr int kEditRowId = 8614;               // Edit bookmark: "Runs without asking"
enum { kAskRun = 1, kAskAlways = 2, kAskNo = 3 };

// --- the address ------------------------------------------------------------------------------------------------
inline bool c0OrSpace(unsigned char c) { return c <= 0x20; }
inline char lowerAscii(char c) { return c >= 'A' && c <= 'Z' ? char(c + ('a' - 'A')) : c; }

// URL Standard, before parsing: leading / trailing C0 controls and spaces go, then every tab, LF and CR anywhere.
inline std::string cleanInput(const std::string& in)
{
    std::size_t a = 0, b = in.size();
    while (a < b && c0OrSpace(static_cast<unsigned char>(in[a]))) ++a;
    while (b > a && c0OrSpace(static_cast<unsigned char>(in[b - 1]))) --b;
    std::string out;
    out.reserve(b - a);
    for (std::size_t i = a; i < b; ++i) if (in[i] != '\t' && in[i] != '\n' && in[i] != '\r') out += in[i];
    return out;
}
// "javascript:" in any case, after the clean-up (so " JavaScript:", "java\nscript:" count; "javascript :" does not).
inline bool isBookmarklet(const std::string& url)
{
    std::size_t i = 0;
    while (i < url.size() && c0OrSpace(static_cast<unsigned char>(url[i]))) ++i;
    static const char* p = "javascript:";
    for (std::size_t k = 0; p[k];) {
        if (i >= url.size()) return false;
        const char c = url[i++];
        if (c == '\t' || c == '\n' || c == '\r') continue;
        if (lowerAscii(c) != p[k]) return false;
        ++k;
    }
    return true;
}

inline int hexValue(char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}
// URL Standard percent-decode: %XX (two hex digits) is that byte; any other '%' stays as it is. '+' stays '+'.
inline std::string percentDecode(const std::string& s)
{
    std::string out;
    out.reserve(s.size());
    for (std::size_t i = 0; i < s.size(); ++i) {
        if (s[i] == '%' && i + 2 < s.size() && hexValue(s[i + 1]) >= 0 && hexValue(s[i + 2]) >= 0) {
            out += char(hexValue(s[i + 1]) * 16 + hexValue(s[i + 2]));
            i += 2;
        } else out += s[i];
    }
    return out;
}

// Encoding Standard "UTF-8 decode": a leading BOM is dropped; each maximal bad subpart becomes U+FFFD.
inline std::string utf8Decode(const std::string& in)
{
    static const char kRepl[] = "\xef\xbf\xbd";
    std::string out;
    out.reserve(in.size());
    std::size_t i = 0;
    if (in.size() >= 3 && in.compare(0, 3, "\xef\xbb\xbf") == 0) i = 3;
    while (i < in.size()) {
        const unsigned char c = static_cast<unsigned char>(in[i]);
        if (c < 0x80) { out += char(c); ++i; continue; }
        int need = 0;
        unsigned char lo = 0x80, hi = 0xbf;
        if (c >= 0xc2 && c <= 0xdf) need = 1;
        else if (c >= 0xe0 && c <= 0xef) { need = 2; if (c == 0xe0) lo = 0xa0; if (c == 0xed) hi = 0x9f; }
        else if (c >= 0xf0 && c <= 0xf4) { need = 3; if (c == 0xf0) lo = 0x90; if (c == 0xf4) hi = 0x8f; }
        else { out += kRepl; ++i; continue; }
        std::size_t j = i + 1;
        int got = 0;
        for (; got < need && j < in.size(); ++got, ++j) {
            const unsigned char d = static_cast<unsigned char>(in[j]);
            if (d < lo || d > hi) break;
            lo = 0x80; hi = 0xbf;
        }
        if (got == need) out.append(in, i, j - i);
        else out += kRepl;   // the bytes read so far are the bad subpart; the one that broke it is read again
        i = j;
    }
    return out;
}

// The script a javascript: address runs ("" when it is not one). Everything after "javascript:" counts, "?" and "#"
// included, as in browsers.
inline std::string sourceOf(const std::string& url)
{
    if (!isBookmarklet(url)) return std::string();
    return utf8Decode(percentDecode(cleanInput(url).substr(11)));
}
inline bool blank(const std::string& s)
{
    for (char c : s) if (!c0OrSpace(static_cast<unsigned char>(c))) return false;
    return true;
}

// Code typed or pasted in "Add bookmarklet" -> the address stored in bookmarks.txt (one line, no tabs).
//   "javascript:..." is taken as an address (cleaned as browsers clean it, so raw line breaks go; scheme lower case);
//   anything else is code: "javascript:" + the code with '%', controls, DEL and spaces percent-encoded, so
//   sourceOf(result) gives the code back byte for byte (line breaks kept, a "//" comment can't swallow the rest).
// "" when there is no code.
inline std::string encodeCode(const std::string& code)
{
    static const char* hex = "0123456789ABCDEF";
    std::string out = "javascript:";
    for (char ch : code) {
        const unsigned char c = static_cast<unsigned char>(ch);
        if (c <= 0x20 || c == 0x7f || c == '%') { out += '%'; out += hex[c >> 4]; out += hex[c & 15]; }
        else out += ch;
    }
    return out;
}
inline std::string fromTyped(const std::string& typed)
{
    if (isBookmarklet(typed)) {
        std::string s = cleanInput(typed);
        std::string out = "javascript:";
        static const char* hex = "0123456789ABCDEF";
        for (std::size_t i = 11; i < s.size(); ++i) {   // C0 controls / DEL left after the clean-up: kept, but encoded
            const unsigned char c = static_cast<unsigned char>(s[i]);
            if (c < 0x20 || c == 0x7f) { out += '%'; out += hex[c >> 4]; out += hex[c & 15]; }
            else out += s[i];
        }
        return blank(sourceOf(out)) ? std::string() : out;
    }
    return blank(typed) ? std::string() : encodeCode(typed);
}

// --- SHA-256 (FIPS 180-4) ---------------------------------------------------------------------------------------
inline std::string sha256Hex(const std::string& data)
{
    static const uint32_t K[64] = {
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
        0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
        0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
        0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
        0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
        0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
        0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
        0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2 };
    uint32_t h[8] = { 0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19 };
    auto rotr = [](uint32_t x, int n) { return (x >> n) | (x << (32 - n)); };
    std::string m = data;
    const uint64_t bits = uint64_t(data.size()) * 8;
    m += char(0x80);
    while (m.size() % 64 != 56) m += char(0);
    for (int i = 7; i >= 0; --i) m += char((bits >> (i * 8)) & 0xff);
    for (std::size_t off = 0; off < m.size(); off += 64) {
        uint32_t w[64];
        for (int i = 0; i < 16; ++i) {
            const unsigned char* p = reinterpret_cast<const unsigned char*>(m.data() + off + std::size_t(i) * 4);
            w[i] = uint32_t(p[0]) << 24 | uint32_t(p[1]) << 16 | uint32_t(p[2]) << 8 | uint32_t(p[3]);
        }
        for (int i = 16; i < 64; ++i) {
            const uint32_t s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
            const uint32_t s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
            w[i] = w[i - 16] + s0 + w[i - 7] + s1;
        }
        uint32_t a = h[0], b = h[1], c = h[2], d = h[3], e = h[4], f = h[5], g = h[6], k = h[7];
        for (int i = 0; i < 64; ++i) {
            const uint32_t t1 = k + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) + ((e & f) ^ (~e & g)) + K[i] + w[i];
            const uint32_t t2 = (rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) + ((a & b) ^ (a & c) ^ (b & c));
            k = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
        }
        h[0] += a; h[1] += b; h[2] += c; h[3] += d; h[4] += e; h[5] += f; h[6] += g; h[7] += k;
    }
    static const char* hex = "0123456789abcdef";
    std::string out;
    for (uint32_t v : h) for (int i = 28; i >= 0; i -= 4) out += hex[(v >> i) & 15];
    return out;
}
inline std::string keyOf(const std::string& source) { return sha256Hex(source); }

// --- consent ("Always") -----------------------------------------------------------------------------------------
inline bool isKey(const std::string& s)
{
    if (s.size() != 64) return false;
    for (char c : s) if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return false;
    return true;
}
struct Consent {
    std::vector<std::string> keys;   // oldest first
    bool has(const std::string& key) const { for (auto& k : keys) if (k == key) return true; return false; }
    void forget(const std::string& key)
    {
        for (std::size_t i = 0; i < keys.size(); ++i) if (keys[i] == key) { keys.erase(keys.begin() + std::ptrdiff_t(i)); return; }
    }
    void allow(const std::string& key)   // newest last; the oldest go past kConsentMax
    {
        if (!isKey(key)) return;
        forget(key);
        keys.push_back(key);
        if (keys.size() > kConsentMax) keys.erase(keys.begin(), keys.begin() + std::ptrdiff_t(keys.size() - kConsentMax));
    }
};
inline Consent parseConsent(const std::string& text)
{
    Consent c;
    std::size_t i = 0;
    while (i < text.size()) {
        std::size_t e = text.find('\n', i);
        if (e == std::string::npos) e = text.size();
        std::string line = text.substr(i, e - i);
        i = e + 1;
        while (!line.empty() && (line.back() == '\r' || line.back() == ' ')) line.pop_back();
        for (auto& ch : line) ch = lowerAscii(ch);
        if (isKey(line)) c.allow(line);
    }
    return c;
}
inline std::string serializeConsent(const Consent& c)
{
    std::string s;
    for (auto& k : c.keys) s += k + "\n";
    return s;
}

// --- may it run here? -------------------------------------------------------------------------------------------
struct Context {
    bool parental = false;      // parental controls on (any mode)
    bool hasTab = false, crashed = false, unloaded = false;
    bool omniPage = false;      // omni:// built-in page / new-tab page
    bool reader = false;        // Reader view
    bool savedCopy = false;     // a reading-list saved copy
    bool privateTab = false;
    std::string pageUrl;        // the tab's address
};
enum class Verdict { Run, Ask, AskPrivate, Parental, TooBig, Empty, NoPage, OmniPage, Reader, SavedCopy, NotWeb };

inline bool webUrl(const std::string& u) { return u.rfind("https://", 0) == 0 || u.rfind("http://", 0) == 0; }
// The page rules alone (Run: this page may run one). Checked again when "Run" / "Always" is chosen.
inline Verdict pageVerdict(const Context& c)
{
    if (c.parental) return Verdict::Parental;
    if (!c.hasTab || c.crashed || c.unloaded) return Verdict::NoPage;
    if (c.omniPage || c.pageUrl.rfind("omni:", 0) == 0) return Verdict::OmniPage;
    if (c.reader) return Verdict::Reader;
    if (c.savedCopy) return Verdict::SavedCopy;
    if (!webUrl(c.pageUrl)) return Verdict::NotWeb;
    return Verdict::Run;
}
inline Verdict decide(const Context& c, const std::string& url, const Consent& consent, std::string* sourceOut = nullptr,
                      std::string* keyOut = nullptr)
{
    if (c.parental) return Verdict::Parental;
    if (url.size() > kMaxBytes) return Verdict::TooBig;
    const std::string src = sourceOf(url);
    if (src.size() > kMaxBytes) return Verdict::TooBig;
    if (blank(src)) return Verdict::Empty;
    const Verdict page = pageVerdict(c);
    if (page != Verdict::Run) return page;
    const std::string key = keyOf(src);
    if (sourceOut) *sourceOut = src;
    if (keyOut) *keyOut = key;
    if (c.privateTab) return Verdict::AskPrivate;   // asked every time; nothing is remembered from a private tab
    return consent.has(key) ? Verdict::Run : Verdict::Ask;
}
inline const char* refusal(Verdict v)
{
    switch (v) {
    case Verdict::Parental: return "Bookmarklets are off while parental controls are on";
    case Verdict::TooBig: return "This bookmarklet is too big (over 64 KB)";
    case Verdict::Empty: return "This bookmarklet has no code";
    case Verdict::NoPage: return "Open a web page first: bookmarklets run on the page in this tab";
    case Verdict::OmniPage: return "Bookmarklets don't run on Omni's own pages";
    case Verdict::Reader: return "Bookmarklets don't run in Reader view";
    case Verdict::SavedCopy: return "Bookmarklets don't run on saved pages";
    case Verdict::NotWeb: return "Bookmarklets run on web pages only";
    default: return "";
    }
}

// --- texts ------------------------------------------------------------------------------------------------------
// The page's host for the question: no scheme, user info or port; lower case; "this page" when there is none.
inline std::string hostOf(const std::string& url)
{
    std::size_t a = url.find("://");
    if (a == std::string::npos) return "this page";
    a += 3;
    const std::size_t b = url.find_first_of("/?#", a);
    std::string h = url.substr(a, b == std::string::npos ? std::string::npos : b - a);
    const std::size_t at = h.rfind('@');
    if (at != std::string::npos) h = h.substr(at + 1);
    if (!h.empty() && h[0] == '[') { const std::size_t e = h.find(']'); if (e != std::string::npos) h.resize(e + 1); }
    else { const std::size_t c = h.find(':'); if (c != std::string::npos) h.resize(c); }
    for (auto& ch : h) ch = lowerAscii(ch);
    return h.empty() ? std::string("this page") : h;
}
inline std::string askTitle(const std::string& pageUrl) { return "Run this bookmarklet on " + hostOf(pageUrl) + "?"; }
inline std::string askSubtitle(bool privateTab)
{
    return privateTab ? "It can read and change this page. Private tab: asked every time"
                      : "It can read and change this page.";
}
inline std::string sizeText(std::size_t bytes)
{
    if (bytes < 1024) return std::to_string(bytes) + (bytes == 1 ? " byte" : " bytes");
    const std::size_t tenths = (bytes * 10 + 512) / 1024;
    return std::to_string(tenths / 10) + (tenths % 10 ? "." + std::to_string(tenths % 10) : std::string()) + " KB";
}
// Bookmarks list: the row's detail instead of the (code-filled) address, and its badge.
inline std::string rowDetail(const std::string& url) { return "Bookmarklet \xc2\xb7 " + sizeText(sourceOf(url).size()); }
inline const char* badge() { return "JS"; }
// The address where one is shown (delete question, Edit subtitle): never the code itself.
inline std::string shown(const std::string& url) { return "bookmarklet, " + sizeText(sourceOf(url).size()); }
// The code as WebKit runs it: the source as a classic script, then a marker as the completion value, so a string
// the bookmarklet evaluates to never replaces the page (Omni ignores the result; see apply_bookmarklets.py).
inline std::string runScript(const std::string& source) { return source + "\n;\"" + kRunMarker + "\""; }

} // namespace OmniBookmarklets
