// OMNI_PC_LINKS_V1: links sent from Omnibloom Setup on the PC (pure part: no SDL, no WebKit; host-tested by
// tools/test_pc_links.cpp). The shell side is OmniPcLinksShell.h; the reasons are in tools/apply_pc_links.py.
//   - the inbox: Setup uploads /data/omni/inbox/links-<YYYYmmdd>-<HHMMSS>-<6 hex>.txt over FTP (verified upload, then
//     renamed into place, a new name each time): "omni-pc-links\t1" and then one link per line, at most 20
//   - the link check: OmniSendLink::validUrl (http(s) only, no user name / password, no spaces, controls or
//     backslashes, a plain host, port 1..65535) and at most 2048 bytes
//   - the waiting list (at most 20, repeats kept once), the poll timing (every 5 s while Omni is on screen, at once
//     when it comes back; a full look every 60 s in case two changes fell in the same second), the texts
// Links are never logged.
#pragma once
#include <cstdint>
#include <deque>
#include <string>
#include <vector>
#include "OmniSendLink.h"

namespace OmniPcLinks {

constexpr std::size_t maxLinks = 20, maxUrlBytes = 2048, maxFileBytes = 64 * 1024, maxFiles = 32;
constexpr uint32_t pollMs = 5000, fullMs = 60000;
inline const char* header() { return "omni-pc-links\t1"; }

// "links-20261116-123005-a1b2c3.txt": the only names Omni reads in the inbox (nothing else there is touched).
inline bool inboxName(const std::string& n)
{
    static const char shape[] = "links-dddddddd-dddddd-hhhhhh.txt";
    if (n.size() != sizeof shape - 1) return false;
    for (std::size_t i = 0; i < n.size(); ++i) {
        const char c = n[i], s = shape[i];
        if (s == 'd') { if (c < '0' || c > '9') return false; }
        else if (s == 'h') { if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return false; }
        else if (c != s) return false;
    }
    return true;
}

inline bool validUrl(const std::string& in, std::string& out)
{
    std::string clean;
    if (!OmniSendLink::validUrl(in, clean) || clean.size() > maxUrlBytes) return false;
    out = clean;
    return true;
}

struct Parsed {
    std::vector<std::string> links;
    int rejected = 0;          // lines that aren't links Omni opens, and lines past the 20th
    bool badHeader = false;    // not a Setup file: nothing in it is offered
};
inline Parsed parse(const std::string& text)
{
    Parsed p;
    std::size_t pos = 0;
    bool first = true;
    while (pos < text.size()) {
        std::size_t e = text.find('\n', pos);
        if (e == std::string::npos) e = text.size();
        std::string line = text.substr(pos, e - pos);
        pos = e + 1;
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (first) {
            first = false;
            if (line != header()) { p.badHeader = true; return p; }
            continue;
        }
        if (line.empty()) continue;
        std::string u;
        if (p.links.size() >= maxLinks || !validUrl(line, u)) { ++p.rejected; continue; }
        bool seen = false;
        for (const auto& l : p.links) if (l == u) { seen = true; break; }
        if (!seen) p.links.push_back(u);
    }
    if (first) p.badHeader = true;   // empty file
    return p;
}

// The site shown in the question: the host in lower case, without the port ("www.example.com", "[::1]"), cut at 64.
inline std::string host(const std::string& url)
{
    std::size_t b = url.find("://");
    if (b == std::string::npos) return std::string();
    b += 3;
    std::size_t e = url.find_first_of("/?#", b);
    if (e == std::string::npos) e = url.size();
    std::string h = url.substr(b, e - b);
    if (!h.empty() && h[0] == '[') { const std::size_t c = h.find(']'); if (c != std::string::npos) h.resize(c + 1); }
    else if (const std::size_t c = h.find(':'); c != std::string::npos) h.resize(c);
    for (char& c : h) if (c >= 'A' && c <= 'Z') c = char(c - 'A' + 'a');
    if (h.size() > 64) {
        std::size_t cut = 61;
        while (cut > 0 && (static_cast<unsigned char>(h[cut]) & 0xc0) == 0x80) --cut;   // not inside a UTF-8 character
        h = h.substr(0, cut) + "...";
    }
    return h;
}
// The link as shown under the question: at most `max` bytes, cut on a character boundary.
inline std::string shown(const std::string& url, std::size_t max = 200)
{
    if (url.size() <= max) return url;
    std::size_t cut = max - 3;
    while (cut > 0 && (static_cast<unsigned char>(url[cut]) & 0xc0) == 0x80) --cut;
    return url.substr(0, cut) + "...";
}

// Links waiting for their question (oldest first). add() returns how many didn't fit (the list is full at 20).
struct Queue {
    std::deque<std::string> items;
    bool room() const { return items.size() < maxLinks; }
    int add(const std::vector<std::string>& links)
    {
        int dropped = 0;
        for (const auto& u : links) {
            bool seen = false;
            for (const auto& q : items) if (q == u) { seen = true; break; }
            if (seen) continue;
            if (!room()) { ++dropped; continue; }
            items.push_back(u);
        }
        return dropped;
    }
};

// When to look at the inbox: only while Omni is on screen (and not in guest mode: `onScreen` false); every 5 s, at
// once when it comes back on screen. `full`: look even if the folder's time stamp didn't change (first look, back on
// screen, or 60 s since the last full look).
struct Poll {
    uint32_t last = 0, lastFull = 0;
    bool wasOnScreen = false, started = false;
    bool due(uint32_t now, bool onScreen, bool& full)
    {
        full = false;
        const bool back = onScreen && !wasOnScreen;
        wasOnScreen = onScreen;
        if (!onScreen) return false;
        if (!started || back || now - lastFull >= fullMs) { full = true; }
        else if (now - last < pollMs) return false;
        started = true;
        last = now;
        if (full) lastFull = now;
        return true;
    }
};

inline std::string askTitle(const std::string& h) { return "Link from your PC: " + (h.empty() ? std::string("a website") : h); }
inline std::string askBody(const std::string& url) { return "Open it in a new tab?  " + shown(url); }
inline std::string openLabel() { return "Open"; }
inline std::string dismissLabel() { return "Dismiss"; }
inline std::string blockedNotice(const std::string& h) { return "A link from your PC (" + (h.empty() ? std::string("a website") : h) + ") is blocked by parental controls"; }
inline std::string openedNotice() { return "Opened the link from your PC"; }
inline std::string fullNotice(int dropped) { return std::to_string(dropped) + (dropped == 1 ? " link" : " links") + " from your PC didn't fit: 20 are waiting"; }

} // namespace OmniPcLinks
