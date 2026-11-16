// OMNI_NOTICE_ACTIONS_V1: the pure part of "Toast actions" (no SDL, no WebKit): which notice carries which action, when
// the toast's action button may be pressed, the toast's hold while the pointer is on it, the 10-minute store that
// Recent notices acts from, and the button's place beside the toast pill. The shell side is
// OmniNoticeActionsShell.h; the reasons are in tools/apply_notice_actions.py. Tested on the host with g++
// (tools/test_notice_actions.cpp).
#pragma once
#include <cstddef>
#include <cstdint>
#include <deque>
#include <string>

namespace OmniNoticeActions {

constexpr uint32_t kArmMs = 600;          // a press on the toast in its first 0.6 s is the page's (nobody aimed at it yet)
constexpr uint32_t kShowMs = 8000;        // an actionable toast shows at least this long (notice() gives 3.5 s)
constexpr uint32_t kHoverHoldMs = 1500;   // while the pointer is on it, the toast is kept at least this long
constexpr uint32_t kMaxHoldMs = 30000;    // ... but never longer than this after it appeared
constexpr uint32_t kKeepMs = 600000;      // Recent notices may act on an entry this long (10 min)
constexpr uint32_t kDedupeMs = 5000;      // the same text again within 5 s: the same record (as Recent notices)
constexpr uint32_t kMatchMs = 3000;       // a Recent notices entry and a record are the same notice within this
constexpr size_t kMaxKept = 30;           // records kept (oldest dropped), as Recent notices' 30
constexpr size_t kUrlMax = 2048;          // a blocked pop-up's address longer than this is not kept

enum Action { kNone = 0, kOpenDownloads, kOpenFileDownloads, kAllowPopup };

inline bool startsWith(const std::string& s, const char* p)
{
    size_t i = 0;
    for (; p[i]; ++i) if (i >= s.size() || s[i] != p[i]) return false;
    return true;
}

// The action of a toast text. popupOurs: the text is OMNI_POPUP_NOTICE_V1's notice for the shown tab (the shell
// compares it with omniPnHint); uBlock's ad pop-ups never get "Allow once" (the Blocked pop-ups list still opens them).
inline Action actionFor(const std::string& t, bool popupOurs)
{
    if (popupOurs) return startsWith(t, "Pop-up blocked by uBlock") ? kNone : kAllowPopup;
    if (startsWith(t, "Downloaded: ")) return kOpenDownloads;                                  // a Downloads app job
    if (startsWith(t, "Downloaded ") && t.find(" to ") != std::string::npos) return kOpenFileDownloads;   // WebKit
    return kNone;
}
// Actions that came from one tab (a private tab's go with it). "Downloaded: X" comes from the Downloads app.
inline bool fromTab(Action a) { return a == kAllowPopup || a == kOpenFileDownloads; }
inline const char* label(Action a)
{
    switch (a) {
    case kOpenDownloads: case kOpenFileDownloads: return "Open";
    case kAllowPopup: return "Allow once";
    default: return "";
    }
}

inline bool within(uint32_t now, uint32_t at, uint32_t ms) { return uint32_t(now - at) <= ms; }
inline bool armed(uint32_t now, uint32_t since) { return uint32_t(now - since) >= kArmMs; }
// statusUntil when an actionable toast arrives: at least kShowMs from now (a later deadline is kept).
inline uint32_t showUntil(uint32_t until, uint32_t now)
{
    const uint32_t want = now + kShowMs;
    return until != 0 && int32_t(until - want) >= 0 ? until : want;
}
// statusUntil while the pointer is on the toast: kept kHoverHoldMs ahead, within kMaxHoldMs of its arrival.
inline uint32_t holdUntil(uint32_t until, uint32_t now, uint32_t since)
{
    if (until == 0 || !within(now, since, kMaxHoldMs)) return until;
    const uint32_t want = now + kHoverHoldMs;
    return int32_t(want - until) > 0 ? want : until;
}

// --- geometry (shell layout units) ------------------------------------------------------------------------------------
struct Rect { int x = 0, y = 0, w = 0, h = 0; };
inline bool inside(const Rect& r, float px, float py) { return r.w > 0 && px >= r.x && px < r.x + r.w && py >= r.y && py < r.y + r.h; }
// The action button: right of the pill (8 apart) when it fits the screen with 16 to spare, else above the pill's
// right end (8 apart).
inline Rect chipRect(const Rect& pill, int chipW, int screenW)
{
    Rect r; r.w = chipW; r.h = pill.h;
    if (pill.x + pill.w + 8 + chipW <= screenW - 16) { r.x = pill.x + pill.w + 8; r.y = pill.y; }
    else { r.x = pill.x + pill.w - chipW; r.y = pill.y - pill.h - 8; }
    return r;
}

// --- the toast now showing / the records ------------------------------------------------------------------------------
struct Record {
    std::string text;       // the English toast text
    Action action = kNone;
    uint32_t at = 0;        // SDL ticks it was (last) raised
    uintptr_t tab = 0;      // the tab it came from (fromTab actions; 0 otherwise)
    bool priv = false;      // that tab was private: never offered in Recent notices, gone when the tab closes
    std::string url;        // kAllowPopup: the blocked pop-up's address
};

class Store {
public:
    void add(const Record& r)
    {
        if (r.action == kNone) return;
        for (size_t i = 0; i < m_list.size(); ++i) {
            if (m_list[i].text == r.text && within(r.at, m_list[i].at, kDedupeMs)) { m_list.erase(m_list.begin() + long(i)); break; }
        }
        m_list.push_front(r);
        while (m_list.size() > kMaxKept) m_list.pop_back();
    }
    void prune(uint32_t now)
    {
        while (!m_list.empty() && !within(now, m_list.back().at, kKeepMs)) m_list.pop_back();
        for (size_t i = 0; i < m_list.size();) {   // a wrapped / odd stamp: dropped too
            if (!within(now, m_list[i].at, kKeepMs)) m_list.erase(m_list.begin() + long(i)); else ++i;
        }
    }
    // A private tab closed (alive(tab) false): its records go.
    template <class Alive> size_t dropClosedPrivate(Alive alive)
    {
        size_t n = 0;
        for (size_t i = 0; i < m_list.size();) {
            if (m_list[i].priv && !alive(m_list[i].tab)) { m_list.erase(m_list.begin() + long(i)); ++n; } else ++i;
        }
        return n;
    }
    // The record of a Recent notices entry (its text and last raise): newest first, not private, within kKeepMs.
    const Record* match(const std::string& text, uint32_t at, uint32_t now) const
    {
        for (const auto& r : m_list) {
            if (r.priv || r.text != text || !within(now, r.at, kKeepMs)) continue;
            if (within(r.at, at, kMatchMs) || within(at, r.at, kMatchMs)) return &r;
        }
        return nullptr;
    }
    void remove(const Record* r)
    {
        for (size_t i = 0; i < m_list.size(); ++i) if (&m_list[i] == r) { m_list.erase(m_list.begin() + long(i)); return; }
    }
    size_t size() const { return m_list.size(); }
    const std::deque<Record>& records() const { return m_list; }

private:
    std::deque<Record> m_list;   // newest first
};

// (status, statusUntil) watch of the toast, as OmniNoticeHistory::StatusWatch: a new text, or the same text with a
// later deadline, is a new toast. The shell syncs it after moving the deadline itself.
class Watch {
public:
    bool changed(const std::string& status, uint32_t until)
    {
        bool fresh = status != m_status;
        if (!fresh && until != 0 && m_until != 0 && int32_t(until - m_until) > 0) fresh = true;
        m_status = status; m_until = until;
        return fresh;
    }
    void sync(const std::string& status, uint32_t until) { m_status = status; m_until = until; }

private:
    std::string m_status;
    uint32_t m_until = 0;
};

// --- texts ------------------------------------------------------------------------------------------------------------
// Recent notices' detail line for an entry that can still be acted on: "Allow this pop-up once (9 min left)".
inline std::string historyDetail(Action a, uint32_t at, uint32_t now)
{
    const uint32_t gone = uint32_t(now - at);
    const uint32_t left = gone >= kKeepMs ? 0 : (kKeepMs - gone + 59999) / 60000;
    const char* what = a == kAllowPopup ? "Allow this pop-up once" : a == kOpenDownloads ? "Open Downloads"
        : a == kOpenFileDownloads ? "Open file downloads" : "";
    if (!*what) return {};
    return std::string(what) + " (" + std::to_string(left) + " min left)";
}

} // namespace OmniNoticeActions
