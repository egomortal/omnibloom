// OMNI_TAB_AUTOCLOSE_V1: the pure part of Browser settings > "Close unused tabs" (no SDL, no WebKit). The shell side
// is OmniTabAutoCloseShell.h; the reasons are in tools/apply_tab_autoclose.py. Tested on the host with g++
// (test_tab_autoclose.cpp).
// Off / 7 / 14 / 30 days (default Off). At start-up (30 s after the session is restored) and once an hour, background
// tabs last shown longer ago than that are closed; they go to "Reopen closed tab" like any closed tab.
// Never closed: the shown tab, a pinned tab, a tab with a sound badge or playing audio, a private tab (it could not be
// reopened), a Media-section tab, and never the last tab. Last-shown times are wall-clock seconds (time()), kept in
// session.txt ("shown\t<n>\t<seconds>\t<url hash>") so they survive restarts.
// Clock safety: nothing is closed while the clock reads before 2024; a time before 2024 or in the future (the clock
// went back) is not used: that tab counts as shown now.
#pragma once
#include <algorithm>
#include <cstdint>
#include <string>
#include <vector>

namespace OmniTabAutoClose {

constexpr int kRowDays = 387;                       // Browser settings row (omniF3SettingsInput: ids >= 300)
constexpr const char* kFileName = "tab-autoclose.txt";   // in /data/omni: "days\t7\nasked\t1\n"
constexpr const char* kLinePrefix = "shown\t";      // session.txt line: "shown\t<n>\t<seconds>\t<url hash>"
constexpr uint32_t kStartDelayMs = 30000;           // the start-up check: 30 s after the first pass with tabs
constexpr uint32_t kCheckMs = 3600000;              // then once an hour
constexpr uint32_t kRetryMs = 60000;                // a check put off (a panel / dialog open, a download): a minute later
constexpr uint32_t kRefreshMs = 900000;             // the shown tab's last-shown time is refreshed every 15 min
constexpr long long kMinValid = 1704067200;         // 2024-01-01 00:00:00 UTC
constexpr long long kFutureSlack = 300;             // a stamp up to 5 min ahead still counts (clock adjustments)
constexpr long long kDay = 86400;
constexpr size_t kMaxMarks = 64;

inline const int* daySteps() { static const int s[] = { 0, 7, 14, 30 }; return s; }
constexpr int kStepCount = 4;

struct Settings {
    int days = 0;          // 0: Off
    bool asked = false;    // the one-time question was answered with "Turn on"
};

inline int snapDays(int d)
{
    const int* s = daySteps();
    int best = s[0];
    for (int i = 0; i < kStepCount; ++i) if ((s[i] > d ? s[i] - d : d - s[i]) < (best > d ? best - d : d - best)) best = s[i];
    return best;
}
// D-pad left / right: one step, stops at the ends. Cross (wrap): Off -> 7 -> 14 -> 30 -> Off.
inline int stepDays(int d, int dir, bool wrap)
{
    const int* s = daySteps();
    int i = 0;
    for (int k = 0; k < kStepCount; ++k) if (s[k] == snapDays(d)) i = k;
    if (wrap && dir > 0 && i == kStepCount - 1) return s[0];
    return s[std::clamp(i + dir, 0, kStepCount - 1)];
}

inline bool digits(const std::string& v, size_t maxLen)
{
    return !v.empty() && v.size() <= maxLen && v.find_first_not_of("0123456789") == std::string::npos;
}
inline Settings parse(const std::string& text)
{
    Settings s;
    size_t at = 0;
    while (at < text.size()) {
        size_t end = text.find('\n', at);
        if (end == std::string::npos) end = text.size();
        std::string line = text.substr(at, end - at);
        at = end + 1;
        while (!line.empty() && (line.back() == '\r' || line.back() == ' ')) line.pop_back();
        const size_t tab = line.find('\t');
        if (tab == std::string::npos) continue;
        const std::string k = line.substr(0, tab), v = line.substr(tab + 1);
        if (!digits(v, 6)) continue;
        const int n = std::stoi(v);
        if (k == "days") s.days = snapDays(n);
        else if (k == "asked") s.asked = n != 0;
    }
    return s;
}
inline std::string serialize(const Settings& s)
{
    return "days\t" + std::to_string(snapDays(s.days)) + "\nasked\t" + (s.asked ? "1" : "0") + "\n";
}

// --- the clock ------------------------------------------------------------------------------------------------------
inline bool clockValid(long long now) { return now >= kMinValid; }
// A stored last-shown time that may be used: from 2024 on and not in the future.
inline bool usable(long long stamp, long long now) { return stamp >= kMinValid && stamp <= now + kFutureSlack; }
// The time a check uses: the stamp when usable (at most now), else now (the tab counts as just shown).
inline long long normalize(long long stamp, long long now)
{
    if (!usable(stamp, now)) return now;
    return std::min(stamp, now);
}

// Start-up / hourly timer (SDL_GetTicks() milliseconds, wrap-safe).
struct Timer {
    bool started = false;
    uint32_t at = 0, wait = kStartDelayMs;
    void restart(uint32_t now) { started = true; at = now; wait = kStartDelayMs; }
    void postpone(uint32_t now) { at = now; wait = kRetryMs; }
    bool due(uint32_t now)
    {
        if (!started) { restart(now); return false; }
        if (uint32_t(now - at) < wait) return false;
        at = now; wait = kCheckMs;
        return true;
    }
};

// --- the decision -----------------------------------------------------------------------------------------------------
struct Cand {
    bool current = false;   // the shown tab
    bool pinned = false;    // OMNI_PINNED_TABS_V1
    bool sound = false;     // sound badge or playing audio (OMNI_TAB_AUDIO_V1)
    bool keep = false;      // private tab / Media section: never closed here
    long long shown = 0;    // last shown (wall seconds, normalized)
};
enum Decision { kOff = 0, kCurrent, kPinned, kSound, kKeep, kRecent, kClose };

inline bool unusedFor(long long shown, long long now, int days)
{
    return days > 0 && clockValid(now) && usable(shown, now) && now - shown >= (long long)days * kDay;
}
inline Decision decide(const Cand& c, long long now, int days)
{
    if (days <= 0 || !clockValid(now)) return kOff;
    if (c.current) return kCurrent;
    if (c.pinned) return kPinned;
    if (c.sound) return kSound;
    if (c.keep) return kKeep;
    if (!unusedFor(c.shown, now, days)) return kRecent;
    return kClose;
}
// The tabs to close (indexes into cs, oldest first). At least one tab always stays open: with no shown tab among them
// (not expected) the most recently shown one is kept.
inline std::vector<int> pick(const std::vector<Cand>& cs, long long now, int days)
{
    std::vector<int> out;
    for (size_t i = 0; i < cs.size(); ++i) if (decide(cs[i], now, days) == kClose) out.push_back(int(i));
    std::stable_sort(out.begin(), out.end(), [&](int a, int b) { return cs[size_t(a)].shown < cs[size_t(b)].shown; });
    if (!cs.empty() && out.size() >= cs.size()) out.resize(cs.size() - 1);   // never the last tab
    return out;
}

// --- session.txt ------------------------------------------------------------------------------------------------------
// FNV-1a of the tab's session URL (as session.txt writes it): a line is applied only to the tab it was written for.
inline uint32_t hashOf(const std::string& s)
{
    uint32_t h = 2166136261u;
    for (unsigned char c : s) { h ^= c; h *= 16777619u; }
    return h;
}
inline std::string hex8(uint32_t v)
{
    static const char* const d = "0123456789abcdef";
    std::string s(8, '0');
    for (int i = 7; i >= 0; --i) { s[size_t(i)] = d[v & 15]; v >>= 4; }
    return s;
}
inline std::string sessionLine(int index, long long seconds, uint32_t urlHash)
{
    if (index < 0 || seconds <= 0) return std::string();
    return std::string(kLinePrefix) + std::to_string(index) + "\t" + std::to_string(seconds) + "\t" + hex8(urlHash) + "\n";
}
struct Mark { int index = -1; long long seconds = 0; uint32_t hash = 0; };
inline bool parseLine(const std::string& line0, Mark& m)
{
    std::string line = line0;
    while (!line.empty() && (line.back() == '\n' || line.back() == '\r')) line.pop_back();
    const std::string p = kLinePrefix;
    if (line.compare(0, p.size(), p) != 0) return false;
    std::vector<std::string> f;
    size_t at = p.size();
    while (true) {
        const size_t t = line.find('\t', at);
        f.push_back(line.substr(at, t == std::string::npos ? std::string::npos : t - at));
        if (t == std::string::npos) break;
        at = t + 1;
    }
    m = Mark();
    if (f.size() != 3 || !digits(f[0], 3) || !digits(f[1], 12) || f[2].size() != 8) return true;   // ours, unusable: skipped
    uint32_t h = 0;
    for (char c : f[2]) {
        int v = c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : -1;
        if (v < 0) return true;
        h = (h << 4) | uint32_t(v);
    }
    m.index = std::stoi(f[0]); m.seconds = std::stoll(f[1]); m.hash = h;
    return true;
}

// --- texts ----------------------------------------------------------------------------------------------------------
inline const char* label() { return "Close unused tabs"; }
inline std::string daysValue(int d) { return d ? std::to_string(d) + " days" : std::string("Off"); }
inline std::string daysDetail(int d)
{
    return d ? "Tabs not opened for " + std::to_string(d) + " days close (checked at start and hourly); pinned, playing and private tabs stay"
             : std::string("Tabs stay open until you close them");
}
inline std::string daysNotice(int d)
{
    return d ? "Tabs unused for " + std::to_string(d) + " days will close (Reopen closed tab brings them back)"
             : std::string("Unused tabs stay open");
}
inline std::string askTitle(int d) { return "Close tabs unused for " + std::to_string(d) + " days?"; }
inline std::string askBody()
{
    return "When Omni starts and once an hour, tabs you haven't opened for that long are closed. Pinned tabs, the tab "
           "you're on, tabs playing sound and private tabs are never closed. Closed tabs can be reopened from \"Reopen "
           "closed tab\" (the last 10).";
}
inline std::string closedNotice(int n) { return "Closed " + std::to_string(n) + (n == 1 ? " unused tab" : " unused tabs"); }

} // namespace OmniTabAutoClose
