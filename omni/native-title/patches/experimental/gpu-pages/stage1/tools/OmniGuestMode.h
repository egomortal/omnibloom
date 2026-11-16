// OMNI_GUEST_MODE_V1: the pure part of guest mode (no SDL, no WebKit). The shell side is OmniGuestModeShell.h; the
// reasons are in tools/apply_guest_mode.py. Tested on the host with g++ (test_guest_mode.cpp).
//   - the mode state machine: Owner -> Entering -> Guest -> Leaving -> Owner (guest rules hold in all three non-Owner
//     phases, so nothing the transitions do can write the owner's files or show the owner's lists)
//   - omniGuest(): the one flag every chokepoint checks (atomic: the reading-list worker may ask from its thread)
//   - the write allowlist for the background writer (omniIoQueue): nothing under the data folder is written in guest
//     mode except crash / startup markers
//   - Stash: the owner's in-memory stores, taken (guest starts empty) or kept (guest works on a copy) on entering and
//     put back on leaving
//   - the texts
// OMNI_GUEST_MODE_V1_R2: parental.txt and running.txt allowed (parental fail count / lockout and the startup crash
// marker must survive a guest session); parseSession (the owner's tabs come back from the session text captured on
// entering, not through omniEverydayStart: its startup choice / crash marker must not run again); parental and private
// tab texts.
#pragma once
#include <atomic>
#include <cstddef>
#include <functional>
#include <memory>
#include <string>
#include <utility>
#include <vector>

namespace OmniGuestMode {

enum class Phase : int { Owner = 0, Entering = 1, Guest = 2, Leaving = 3 };

class Machine {
public:
    Phase phase() const { return Phase(phase_.load(std::memory_order_acquire)); }
    bool active() const { return phase() != Phase::Owner; }      // guest rules apply (transitions included)
    bool canEnter() const { return phase() == Phase::Owner; }
    bool canLeave() const { return phase() == Phase::Guest; }
    unsigned sessions() const { return sessions_; }              // guest sessions started this run
    bool beginEnter() { return step(Phase::Owner, Phase::Entering); }
    bool finishEnter() { if (!step(Phase::Entering, Phase::Guest)) return false; ++sessions_; return true; }
    bool beginLeave() { return step(Phase::Guest, Phase::Leaving); }
    bool finishLeave() { return step(Phase::Leaving, Phase::Owner); }
    bool abortEnter() { return step(Phase::Entering, Phase::Owner); }   // nothing was closed yet
private:
    bool step(Phase from, Phase to)
    {
        int f = int(from);
        return phase_.compare_exchange_strong(f, int(to), std::memory_order_acq_rel);
    }
    std::atomic<int> phase_ { int(Phase::Owner) };
    unsigned sessions_ = 0;
};
inline Machine& state() { static Machine m; return m; }

// --- the write allowlist ---------------------------------------------------------------------------------------------
// Files under the data folder a guest session may still write: crash / startup markers (no owner data; a crash during
// guest mode must still be diagnosable: running.txt records only "private" for a guest tab) and parental.txt (only a
// PIN-gated change or the wrong-PIN count / lockout can change it: the lockout must survive a guest session and a
// restart). Exact names; "crash-" / "crash." prefixes; ".pending".
inline bool endsWith(const std::string& s, const char* tail)
{
    const std::string t(tail);
    return s.size() >= t.size() && s.compare(s.size() - t.size(), t.size(), t) == 0;
}
inline bool markerName(const std::string& name)
{
    static const char* const exact[] = { "display-startup.pending", "jank-mark.txt", "nc-reset.marker", "omni-crash.txt",
                                         "running.txt", "parental.txt" };
    for (const char* e : exact) if (name == e) return true;
    if (name.compare(0, 6, "crash-") == 0 || name.compare(0, 6, "crash.") == 0) return name.size() > 6;
    return name.size() > 8 && endsWith(name, ".pending");
}
// dataDir: OMNI_DATA_DIR ("/data/omni/", trailing slash). A path outside it is not an owner store (allowed); one inside
// is allowed only when it names a marker directly in the folder (no sub folder, no "..", no empty part).
inline bool writeAllowed(const std::string& path, const std::string& dataDir = "/data/omni/")
{
    std::string dir = dataDir;
    if (dir.empty()) return true;
    if (dir.back() != '/') dir += '/';
    const std::string bare = dir.substr(0, dir.size() - 1);    // "/data/omni" itself
    if (path == bare || path == dir) return false;
    if (path.compare(0, dir.size(), dir) != 0) {
        // "/data//omni/x", "/data/./omni/x": refuse anything that only looks outside because of its spelling
        if (path.find("//") != std::string::npos || path.find("/./") != std::string::npos || path.find("/../") != std::string::npos) return false;
        return true;
    }
    const std::string rest = path.substr(dir.size());
    if (rest.empty() || rest.find('/') != std::string::npos || rest == "." || rest == "..") return false;
    return markerName(rest);
}

// --- the owner's in-memory stores --------------------------------------------------------------------------------------
// take(): the live store moves into the stash and the guest starts with an empty one (lists the guest must not see).
// keep(): the guest works on a copy; the owner's copy comes back on leaving (site settings: guest changes stay in memory
// and are dropped). restore(): every store back, newest first; the stash is then empty.
class Stash {
public:
    template <class T> void take(T& live)
    {
        auto saved = std::make_shared<T>(std::move(live));
        live = T();
        undo_.push_back([&live, saved] { live = std::move(*saved); });
    }
    template <class T> void keep(T& live)
    {
        auto saved = std::make_shared<T>(live);
        undo_.push_back([&live, saved] { live = std::move(*saved); });
    }
    void restore()
    {
        for (size_t i = undo_.size(); i-- > 0;) undo_[i]();
        undo_.clear();
    }
    size_t size() const { return undo_.size(); }
    bool empty() const { return undo_.empty(); }
private:
    std::vector<std::function<void()>> undo_;
};

// --- the owner's tabs ----------------------------------------------------------------------------------------------------
// omniSessionText() as captured on entering ("tab\t<url>\t<title>", "pinned\t..", "group\t..", "selected\t<n>"): the
// tabs to make (url "newtab" or http(s), at most `limit`), the selected index and the other lines in order (the pinned
// / group lines for omniPtRestoreLine / omniTgRestoreLine, which index the tabs in this order).
struct SavedTabs {
    std::vector<std::pair<std::string, std::string>> tabs;   // url, title
    std::vector<std::string> extra;
    int selected = 0;
};
inline bool webUrl(const std::string& u) { return u.compare(0, 8, "https://") == 0 || u.compare(0, 7, "http://") == 0; }
inline SavedTabs parseSession(const std::string& text, size_t limit)
{
    SavedTabs out;
    size_t from = 0;
    while (from < text.size()) {
        size_t end = text.find('\n', from);
        if (end == std::string::npos) end = text.size();
        std::string s = text.substr(from, end - from);
        from = end + 1;
        while (!s.empty() && (s.back() == '\r' || s.back() == '\n')) s.pop_back();
        if (s.compare(0, 4, "tab\t") == 0) {
            if (out.tabs.size() >= limit) continue;
            const size_t t = s.find('\t', 4);
            const std::string url = s.substr(4, t == std::string::npos ? std::string::npos : t - 4);
            if (url == "newtab" || webUrl(url)) out.tabs.emplace_back(url, t == std::string::npos ? std::string() : s.substr(t + 1));
        } else if (s.compare(0, 9, "selected\t") == 0) {
            int v = 0;
            for (size_t i = 9; i < s.size() && i < 15 && s[i] >= '0' && s[i] <= '9'; ++i) v = v * 10 + (s[i] - '0');
            out.selected = v;
        } else if (!s.empty() && s.compare(0, 13, "omni-session\t") != 0) out.extra.push_back(s);
    }
    return out;
}

// --- texts -------------------------------------------------------------------------------------------------------------
constexpr const char* kBadge = "GUEST";
inline std::string rowLabel(bool guest) { return guest ? "Leave guest mode" : "Guest mode"; }
inline std::string rowValue(bool guest) { return guest ? "Guest session" : "For visitors"; }
inline std::string enterTitle() { return "Start guest mode?"; }
inline std::string enterBody()
{
    return "All tabs close. Your tabs will be restored when you leave guest mode. A guest can't see your bookmarks, "
           "history, reading list, saved sessions, apps or passwords, and nothing the guest does is saved. "
           "Downloads are off for guests. Private tabs close for good.";
}
inline std::string leaveTitle() { return "Leave guest mode?"; }
inline std::string leaveBody()
{
    return "The guest's tabs close and everything from this guest session is deleted: cookies, site data, history and "
           "any changes to site settings. Your tabs come back.";
}
inline std::string enteredNotice() { return "Guest mode: nothing is saved. Options > Leave guest mode brings your tabs back"; }
inline std::string leftNotice() { return "Guest session deleted. Your tabs are back"; }
inline std::string blockedNotice(const std::string& what) { return what + " isn't available in guest mode"; }
inline std::string downloadNotice() { return "Downloads are off in guest mode"; }
inline std::string unavailableNotice() { return "Guest mode isn't available right now"; }
// Parental controls with "Lock private tabs": guest tabs are private tabs, so guest mode is off too (no PIN is asked
// for guest mode; the owner turns the lock off in Parental controls).
inline std::string parentalLockedNotice() { return "Guest mode is off: parental controls lock private tabs"; }
inline std::string parentalLockedValue() { return "Locked"; }

} // namespace OmniGuestMode

// The one flag: guest rules apply (Entering, Guest, Leaving).
inline bool omniGuest() { return OmniGuestMode::state().active(); }
