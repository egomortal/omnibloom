// OMNI_NOTICE_HISTORY_V1: the pure part of "Recent notices" (no SDL, no WebKit): the last 30 notices of this run, in
// memory only. The shell side is OmniNoticeHistoryShell.h; the reasons are in tools/apply_notice_history.py. Tested on
// the host with g++ (tools/test_notice_history.cpp).
#pragma once
#include <cstddef>
#include <cstdint>
#include <deque>
#include <string>

namespace OmniNoticeHistory {

constexpr size_t kMax = 30;                 // entries kept (oldest dropped)
constexpr uint32_t kDedupeMs = 5000;        // the same text again within 5 s: the entry counts it (x2) instead
constexpr size_t kTextMax = 300;            // bytes kept of one notice (cut on a UTF-8 boundary)
constexpr int kQuickRowId = 8476, kPanelKind = 7476;
constexpr uint32_t kRefreshMs = 15000;      // the open list redraws its "2 min ago" texts this often

// --- which notices are not kept -------------------------------------------------------------------------------------
// Steps that fire on every key press (each press replaces the last; the setting itself shows the value) and progress
// texts that are always followed by a result notice. Prefixes of the English text.
constexpr const char* kNoisyPrefixes[] = {
    "Zoom ",                        // L2 + D-pad / Options zoom steps: "Zoom 110% on host", "Zoom is at its largest ..."
    "Volume: ",                     // tab volume steps (OmniTabVolume.h notice)
    "Speed: ",                      // playback speed steps (OmniPlaybackSpeed.h notice)
    "Magnifier ",                   // magnifier zoom steps (OmniMagnifier.h notice)
    "Downloading ",                 // file download progress, every second (the "Downloaded ..." result is kept)
    "Copying from the USB drive: ", // USB copy percent
    "Copying to the USB drive: ",
    "Press ",                       // the first-launch controls hint (OmniControlsHelp.h hintText)
};
inline bool startsWith(const std::string& s, const char* p)
{
    size_t i = 0;
    for (; p[i]; ++i) if (i >= s.size() || s[i] != p[i]) return false;
    return true;
}
inline bool endsWith(const std::string& s, const char* p)
{
    const std::string t(p);
    return s.size() >= t.size() && s.compare(s.size() - t.size(), t.size(), t) == 0;
}
// "Ready" is the idle status; "..." / an ellipsis marks progress ("Saving screenshot...", "Reloading...").
inline bool noisy(const std::string& text)
{
    if (text.empty() || text == "Ready") return true;
    if (endsWith(text, "...") || endsWith(text, "\xe2\x80\xa6")) return true;
    for (const char* p : kNoisyPrefixes) if (startsWith(text, p)) return true;
    return false;
}

// --- what Cross does on an entry (only where the shell has a cheap hook) ----------------------------------------------
enum Action { kNone = 0, kMediaDownloads, kFileDownloads, kBlockedPopups, kScreenshots };
inline Action actionFor(const std::string& t)
{
    if (startsWith(t, "Sent to Downloads")) return kMediaDownloads;          // context menu / send-link hand-overs
    if (startsWith(t, "Downloaded: ")) return kMediaDownloads;               // a Downloads app job finished (small comforts)
    if (startsWith(t, "Downloaded ") || startsWith(t, "Download failed: ")) return kFileDownloads;   // WebKit file downloads
    if (startsWith(t, "Pop-up blocked")) return kBlockedPopups;              // OmniPopupNotice / OmniPermissions texts
    if (startsWith(t, "Screenshot saved")) return kScreenshots;
    return kNone;
}
inline const char* actionHint(Action a)
{
    switch (a) {
    case kMediaDownloads: return "Open Downloads";
    case kFileDownloads: return "Open file downloads";
    case kBlockedPopups: return "Open Blocked pop-ups";
    case kScreenshots: return "Open Screenshots";
    default: return "";
    }
}

// At most kTextMax bytes, never in the middle of a UTF-8 sequence; line breaks become spaces.
inline std::string clip(const std::string& s)
{
    std::string out = s.substr(0, kTextMax);
    if (s.size() > kTextMax) {
        size_t lead = out.size();   // the start of the last character
        while (lead > 0 && (static_cast<unsigned char>(out[lead - 1]) & 0xc0) == 0x80) --lead;
        if (lead > 0) {
            const unsigned char c = static_cast<unsigned char>(out[lead - 1]);
            const size_t need = c >= 0xf0 ? 4 : c >= 0xe0 ? 3 : c >= 0xc0 ? 2 : 1;
            if (out.size() - (lead - 1) < need) out.resize(lead - 1);   // cut inside it: drop it
        }
    }
    for (auto& c : out) if (c == '\n' || c == '\r' || c == '\t') c = ' ';
    return out;
}

// --- the history ------------------------------------------------------------------------------------------------------
struct Entry {
    std::string text;        // English, as raised (translated only where it is drawn)
    uint32_t at = 0;         // SDL ticks of the last time it was raised
    int count = 1;           // times raised within kDedupeMs of each other
    uint64_t seq = 0;        // bumped on every raise (unread: seq > the read mark)
    Action action = kNone;
};
inline bool within(uint32_t now, uint32_t at, uint32_t ms) { return uint32_t(now - at) <= ms; }

class History {
public:
    // false: not kept (noisy). A repeat within kDedupeMs of an entry's last raise counts there and moves it to the top.
    bool add(const std::string& raw, uint32_t now)
    {
        if (noisy(raw)) return false;
        const std::string text = clip(raw);
        for (size_t i = 0; i < m_list.size(); ++i) {
            if (!within(now, m_list[i].at, kDedupeMs)) continue;
            if (m_list[i].text != text) continue;
            Entry e = m_list[i];
            m_list.erase(m_list.begin() + long(i));
            ++e.count; e.at = now; e.seq = ++m_seq;
            m_list.push_front(e);
            return true;
        }
        Entry e; e.text = text; e.at = now; e.seq = ++m_seq; e.action = actionFor(text);
        m_list.push_front(e);
        while (m_list.size() > kMax) m_list.pop_back();
        return true;
    }
    const std::deque<Entry>& entries() const { return m_list; }   // newest first
    size_t size() const { return m_list.size(); }
    bool empty() const { return m_list.empty(); }
    size_t unread() const { size_t n = 0; for (const auto& e : m_list) n += e.seq > m_read; return n; }
    void markRead() { m_read = m_seq; }
    void clear() { m_list.clear(); m_read = m_seq; }
    const Entry* find(uint64_t seq) const { for (const auto& e : m_list) if (e.seq == seq) return &e; return nullptr; }

private:
    std::deque<Entry> m_list;
    uint64_t m_seq = 0, m_read = 0;
};

// --- the toast path: statuses set without notice() --------------------------------------------------------------------
// The shell looks at (status, statusUntil) once per pass. A new text is a new notice; the same text with a later
// deadline is the same notice raised again (notice() / a direct "status = x; statusUntil = now + n"). A deadline set
// where there was none (the toast giving an untimed status its 6 s) or moved earlier (a notice ended early) is not.
// notice() itself records directly and calls sync() so the pass after it sees nothing new.
class StatusWatch {
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
inline std::string ago(uint32_t now, uint32_t at)
{
    const uint32_t s = uint32_t(now - at) / 1000;
    if (s < 10) return "just now";
    if (s < 60) return std::to_string(s) + " s ago";
    if (s < 3600) return std::to_string(s / 60) + " min ago";
    const uint32_t h = s / 3600, m = (s % 3600) / 60;
    return std::to_string(h) + " h" + (m ? " " + std::to_string(m) + " min" : std::string()) + " ago";
}
inline std::string rowValue(const Entry& e, uint32_t now)
{
    return (e.count > 1 ? "x" + std::to_string(e.count) + "  " : std::string()) + ago(now, e.at);
}
inline std::string quickLabel(size_t n) { return "Notices (" + std::to_string(n) + ")"; }
inline std::string quickValue(size_t unread) { return unread ? "\xe2\x97\x8f " + std::to_string(unread) + " new" : std::string(); }
inline const char* panelTitle() { return "Recent notices"; }
inline const char* panelSubtitle() { return "The last 30 messages, until Omni closes. None are kept while a private tab is open"; }
inline const char* emptyLabel() { return "No notices yet"; }

} // namespace OmniNoticeHistory
