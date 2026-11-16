// OMNI_BF_LIST_V1: the pure part of "Back history" (hold Circle while browsing, or Options > Browse > Back history):
// the list of the tab's earlier and later pages, its order, labels, and the hold timing of Circle. No SDL, no WebKit.
// The shell side is OmniBfListShell.h; the reasons are in tools/apply_bf_list.py. Tested on the host with g++
// (test_bf_list.cpp). Memory only: the list is read from the tab's own back/forward list when it opens and is never
// written anywhere (private tabs included).
#pragma once
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace OmniBfList {

constexpr int kPanelKind = 7593;       // OmniFxPanel::kind of the list
constexpr int kQuickRowId = 8593;      // Options > Browse row "Back history"
constexpr unsigned kMaxEach = 15;      // at most this many earlier and this many later pages
constexpr uint32_t kHoldMs = 500;      // Circle held this long opens the list (hold Cross uses 500 ms too)
constexpr size_t kTitleMaxBytes = 72;  // label: at most this many bytes of the title, then "..."
constexpr size_t kHostMaxBytes = 48;   // detail: the host, shortened the same way
constexpr const char* kEllipsis = "...";

// --- UTF-8 -----------------------------------------------------------------------------------------------------------
// Length of the valid UTF-8 sequence at s[i] (1-4), or 0 when it is not valid (overlong, surrogate, > U+10FFFF, cut).
inline size_t utf8Len(const std::string& s, size_t i)
{
    const unsigned char c = static_cast<unsigned char>(s[i]);
    if (c < 0x80) return 1;
    size_t n;
    uint32_t cp;
    if (c >= 0xC2 && c <= 0xDF) { n = 2; cp = c & 0x1F; }
    else if (c >= 0xE0 && c <= 0xEF) { n = 3; cp = c & 0x0F; }
    else if (c >= 0xF0 && c <= 0xF4) { n = 4; cp = c & 0x07; }
    else return 0;
    if (i + n > s.size()) return 0;
    for (size_t k = 1; k < n; ++k) {
        const unsigned char d = static_cast<unsigned char>(s[i + k]);
        if ((d & 0xC0) != 0x80) return 0;
        cp = (cp << 6) | (d & 0x3F);
    }
    if ((n == 3 && cp < 0x800) || (n == 4 && (cp < 0x10000 || cp > 0x10FFFF)) || (cp >= 0xD800 && cp <= 0xDFFF)) return 0;
    return n;
}

// One line of text: control characters (tabs, line breaks, DEL) become spaces, runs of spaces collapse, both ends are
// trimmed, invalid UTF-8 bytes are dropped. Whatever comes back is valid UTF-8.
inline std::string clean(const std::string& in)
{
    std::string out;
    out.reserve(in.size());
    bool space = false;
    for (size_t i = 0; i < in.size();) {
        const size_t n = utf8Len(in, i);
        if (!n) { ++i; continue; }
        const unsigned char c = static_cast<unsigned char>(in[i]);
        if (n == 1 && (c <= 0x20 || c == 0x7F)) { space = !out.empty(); ++i; continue; }
        if (space) { out += ' '; space = false; }
        out.append(in, i, n);
        i += n;
    }
    return out;
}

// At most maxBytes bytes of (already clean) text, cut before a whole UTF-8 character, a trailing space dropped,
// "..." added when anything was cut (the "..." counts towards maxBytes; maxBytes < 4 gives "...").
inline std::string shorten(const std::string& text, size_t maxBytes)
{
    if (text.size() <= maxBytes) return text;
    const size_t room = maxBytes > 3 ? maxBytes - 3 : 0;
    size_t end = 0;
    for (size_t i = 0; i < text.size();) {
        const size_t n = utf8Len(text, i);
        const size_t step = n ? n : 1;
        if (i + step > room) break;
        i += step;
        end = i;
    }
    std::string out = text.substr(0, end);
    while (!out.empty() && out.back() == ' ') out.pop_back();
    return out + kEllipsis;
}

// --- hosts -------------------------------------------------------------------------------------------------------------
inline char lower(char c) { return c >= 'A' && c <= 'Z' ? char(c + ('a' - 'A')) : c; }

// What the detail column shows for a URL: the host ("https://www.Example.com:8443/a?b" -> "example.com"), without
// user info, port or a leading "www."; "[::1]" stays bracketed. No host: the scheme ("file", "about:blank" -> "about",
// "data:..." -> "data"); omni:// pages -> "omni". Nothing usable: "".
inline std::string hostOf(const std::string& url)
{
    const size_t colon = url.find(':');
    if (colon == std::string::npos || colon == 0) return std::string();
    std::string scheme;
    for (size_t i = 0; i < colon; ++i) {
        const char c = lower(url[i]);
        if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '+' || c == '-' || c == '.')) return std::string();
        scheme += c;
    }
    if (scheme == "blob") return hostOf(url.substr(colon + 1));
    if (url.compare(colon, 3, "://") != 0) return scheme;
    const size_t start = colon + 3;
    size_t end = url.find_first_of("/?#\\", start);
    if (end == std::string::npos) end = url.size();
    std::string auth = url.substr(start, end - start);
    const size_t at = auth.rfind('@');
    if (at != std::string::npos) auth.erase(0, at + 1);
    std::string host;
    if (!auth.empty() && auth[0] == '[') {
        const size_t close = auth.find(']');
        host = close == std::string::npos ? auth : auth.substr(0, close + 1);
    } else {
        host = auth.substr(0, auth.find(':'));
    }
    for (auto& c : host) c = lower(c);
    if (host.size() > 4 && host.compare(0, 4, "www.") == 0) host.erase(0, 4);
    if (host.empty()) return scheme;
    return host;
}

// --- the list ----------------------------------------------------------------------------------------------------------
// Offsets as WKBackForwardListGetItemAtIndex takes them (-1 the page before, 0 the current page, 1 the page after), in
// the order shown, newest first: the furthest later page at the top, then the current page, then the earlier pages
// going back in time. At most kMaxEach each way (the nearest ones).
inline std::vector<int> offsets(unsigned backCount, unsigned forwardCount, unsigned maxEach = kMaxEach)
{
    const int b = int(backCount < maxEach ? backCount : maxEach), f = int(forwardCount < maxEach ? forwardCount : maxEach);
    std::vector<int> v;
    v.reserve(size_t(b + f + 1));
    for (int i = f; i >= 1; --i) v.push_back(i);
    v.push_back(0);
    for (int i = 1; i <= b; ++i) v.push_back(-i);
    return v;
}
// The row focused when the list opens: the page before (what Back would open), else the current page.
inline int initialRow(const std::vector<int>& offs)
{
    for (size_t i = 0; i < offs.size(); ++i) if (offs[i] == -1) return int(i);
    for (size_t i = 0; i < offs.size(); ++i) if (offs[i] == 0) return int(i);
    return 0;
}

struct Row {
    int offset = 0;
    std::string label;   // the page title (or its host / address when it has none), shortened
    std::string host;    // detail column
    std::string value;   // right column: "Current page" on the current one
};
inline Row makeRow(int offset, const std::string& title, const std::string& url)
{
    Row r;
    r.offset = offset;
    r.host = shorten(clean(hostOf(url)), kHostMaxBytes);
    std::string t = clean(title);
    if (t.empty()) t = clean(url.compare(0, 5, "data:") == 0 ? std::string("data:") : url);
    if (t.empty()) t = "Untitled page";
    r.label = shorten(t, kTitleMaxBytes);
    if (r.label == r.host) r.host.clear();   // no title: the address already says it
    if (offset == 0) r.value = "Current page";
    return r;
}
inline std::string subtitle(bool privateTab, unsigned backCount, unsigned forwardCount)
{
    std::string s = std::to_string(backCount) + (backCount == 1 ? " earlier page" : " earlier pages");
    if (forwardCount) s += ", " + std::to_string(forwardCount) + (forwardCount == 1 ? " later page" : " later pages");
    if (backCount > kMaxEach || forwardCount > kMaxEach) s += " (the nearest " + std::to_string(kMaxEach) + " shown)";
    if (privateTab) s += ". Private tab: never saved";
    return s;
}
inline const char* emptyNotice() { return "No other pages in this tab yet"; }
inline const char* goneNotice() { return "That page is no longer in this tab's history"; }

// --- hold Circle -----------------------------------------------------------------------------------------------------------
// The press is held back: a release before kHoldMs is an ordinary Back (run on release, as hold Cross clicks on release);
// kHoldMs held opens the list once, and that press's release then does nothing. Released without an UP event reaching
// us (another handler took it, or the pad's state is already up): tick() resolves it the same way.
enum class Act { None, Back, Open };
struct Hold {
    bool active = false, fired = false;
    int pad = -1;
    uint32_t start = 0;
    bool begin(int padId, uint32_t now)
    {
        if (active) return false;
        active = true; fired = false; pad = padId; start = now;
        return true;
    }
    bool owns(int padId) const { return active && pad == padId; }
    Act release()
    {
        if (!active) return Act::None;
        const bool f = fired;
        *this = Hold();
        return f ? Act::None : Act::Back;
    }
    // Every pass while active: stillDown = the pad still reports the button pressed.
    Act tick(uint32_t now, bool stillDown)
    {
        if (!active) return Act::None;
        if (!stillDown) return release();
        if (!fired && uint32_t(now - start) >= kHoldMs) { fired = true; return Act::Open; }
        return Act::None;
    }
    void cancel() { *this = Hold(); }
};

} // namespace OmniBfList
