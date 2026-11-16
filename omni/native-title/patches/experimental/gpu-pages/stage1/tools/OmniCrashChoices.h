// OMNI_CRASH_CHOICES_V1: the crash panel with choices, the pure part (no SDL, no WebKit).
// Which host a crash counts for, the per-session crash ledger (memory only, never written), the loop guard for the
// one automatic reload, the choice list, focus moves, the panel layout and the texts.
// Shell side: OmniCrashChoicesShell.h. The reasons are in tools/apply_crash_choices.py.
#pragma once
#include <cstdint>
#include <string>
#include <vector>

namespace OmniCrashChoices {

constexpr uint32_t kLoopWindowMs = 5u * 60u * 1000u;   // a 2nd crash on the same host within 5 min: no automatic reload
constexpr uint32_t kReaderWaitMs = 60000;              // "Open in Reader view": give the reload this long to finish
constexpr size_t kMaxHosts = 64;                       // ledger size (the oldest host is dropped beyond this)
constexpr int kAdviceAt = 2;                           // crashes on one host before the advice line shows

constexpr const char* kTitle = "This page stopped working";
constexpr const char* kBody = "The page's process ended (often memory on a heavy page). Your other tabs are fine.";
constexpr const char* kAdvice = "This site crashed twice. Try Lite mode or Data saver.";

inline bool after(uint32_t now, uint32_t at) { return int32_t(now - at) >= 0; }   // SDL tick wrap-safe

// The host a crash counts for: http(s) only; lower case, no user info / port / trailing dot, "www." dropped.
// "" for anything else (start page, omni:// pages, about:blank, data:): such crashes are counted under "" and never
// get the advice line.
inline std::string hostKey(const std::string& url)
{
    size_t start;
    if (url.compare(0, 8, "https://") == 0) start = 8;
    else if (url.compare(0, 7, "http://") == 0) start = 7;
    else return std::string();
    size_t end = url.find_first_of("/?#", start);
    if (end == std::string::npos) end = url.size();
    std::string auth = url.substr(start, end - start);
    if (size_t at = auth.rfind('@'); at != std::string::npos) auth = auth.substr(at + 1);
    std::string host;
    if (!auth.empty() && auth[0] == '[') {
        const size_t close = auth.find(']');
        if (close == std::string::npos) return std::string();
        host = auth.substr(0, close + 1);
    } else host = auth.substr(0, auth.find(':'));
    for (char& c : host) if (c >= 'A' && c <= 'Z') c = char(c + 32);
    while (!host.empty() && host.back() == '.') host.pop_back();
    if (host.compare(0, 4, "www.") == 0 && host.size() > 4) host = host.substr(4);
    return host;
}

// Crashes per host in this session. Kept in memory only (never written); private tabs use a ledger of their own.
class Ledger {
public:
    struct Entry { std::string host; int count = 0; uint32_t last = 0, prev = 0; uint64_t seq = 0; };
    // Records a crash; returns this host's count in the session.
    int note(const std::string& host, uint32_t now)
    {
        Entry* e = find(host);
        if (!e) {
            if (entries_.size() >= kMaxHosts) {
                size_t old = 0;
                for (size_t i = 1; i < entries_.size(); ++i) if (entries_[i].seq < entries_[old].seq) old = i;
                entries_.erase(entries_.begin() + long(old));
            }
            entries_.push_back(Entry());
            e = &entries_.back();
            e->host = host;
        }
        e->prev = e->last;
        e->last = now;
        ++e->count;
        e->seq = ++seq_;
        return e->count;
    }
    int count(const std::string& host) const { const Entry* e = find(host); return e ? e->count : 0; }
    // The loop guard: an automatic reload is allowed unless the last two crashes on this host were within 5 min.
    bool autoReloadOk(const std::string& host) const
    {
        const Entry* e = find(host);
        if (!e || e->count < 2) return true;
        return e->last - e->prev >= kLoopWindowMs;   // unsigned: wrap-safe
    }
    size_t size() const { return entries_.size(); }
    void clear() { entries_.clear(); }

private:
    Entry* find(const std::string& host) { for (Entry& e : entries_) if (e.host == host) return &e; return nullptr; }
    const Entry* find(const std::string& host) const { for (const Entry& e : entries_) if (e.host == host) return &e; return nullptr; }
    std::vector<Entry> entries_;
    uint64_t seq_ = 0;
};

// The advice line ("crashed twice") for this host's session count.
inline bool showAdvice(const std::string& host, int count) { return !host.empty() && count >= kAdviceAt; }

// --- choices ---------------------------------------------------------------------------------------------------------
enum Choice { Reload = 0, Reader, DataSaver, UnloadOthers, CloseTab };
inline std::vector<Choice> choices(bool webPage, bool otherTabs)
{
    std::vector<Choice> v { Reload };
    if (webPage) { v.push_back(Reader); v.push_back(DataSaver); }
    if (otherTabs) v.push_back(UnloadOthers);
    v.push_back(CloseTab);
    return v;
}
inline const char* label(Choice c, bool saverOn)
{
    switch (c) {
    case Reload: return "Reload";
    case Reader: return "Open in Reader view";
    case DataSaver: return saverOn ? "Reload (Data saver is on)" : "Reload with Data saver";
    case UnloadOthers: return "Unload other tabs and reload";
    case CloseTab: return "Close tab";
    }
    return "";
}
// D-pad up / down: no wrap; an out-of-range focus (the list got shorter) is clamped first.
inline int moveFocus(int focus, int delta, int n)
{
    if (n <= 0) return 0;
    if (focus < 0) focus = 0;
    if (focus >= n) focus = n - 1;
    focus += delta;
    return focus < 0 ? 0 : focus >= n ? n - 1 : focus;
}

// --- layout (layout px, as the error panel: 700 wide, centred on the page area) -----------------------------------------
constexpr int kW = 700, kRowH = 40, kRowGap = 6, kRowX = 88, kRowW = 572, kLineH = 26;
struct Layout { int h = 0, adviceY = 0, listY = 0, hintY = 0; };
// y offsets from the panel top: title 42, address 70, body from 108 (bodyLines x 26), the advice line, the choices, the
// Circle hint at the bottom.
inline Layout layout(int bodyLines, bool advice, int rows)
{
    Layout L;
    int y = 108 + bodyLines * kLineH;
    if (advice) { L.adviceY = y + 8; y += 34; }
    L.listY = y + 12;
    y = L.listY + rows * (kRowH + kRowGap) - kRowGap;
    L.hintY = y + 28;
    L.h = y + 56;
    return L;
}
inline int rowY(const Layout& L, int i) { return L.listY + i * (kRowH + kRowGap); }
// The row under a point (panel-relative coordinates), -1: none.
inline int rowAt(const Layout& L, int rows, int px, int py)
{
    if (px < kRowX || px >= kRowX + kRowW) return -1;
    for (int i = 0; i < rows; ++i) if (py >= rowY(L, i) && py < rowY(L, i) + kRowH) return i;
    return -1;
}

// --- texts -------------------------------------------------------------------------------------------------------------
inline std::string unloadNotice(int n)
{
    if (n <= 0) return "No other tab could be unloaded. Reloading...";
    return "Unloaded " + std::to_string(n) + (n == 1 ? " tab" : " tabs") + ". Reloading...";
}
inline std::string saverNotice(bool wasOn) { return wasOn ? "Data saver is on. Reloading..." : "Data saver on. Reloading..."; }
constexpr const char* kReaderNotice = "Reloading, then Reader view...";
constexpr const char* kAutoNotice = "This tab stopped in the background. Reloading...";
// The log line: never a host (private or not), only the count.
inline std::string logLine(int count, bool priv, bool autoReload)
{
    return std::string("OMNI CRASH: page process ended (crash ") + std::to_string(count) + " on this site this session"
        + (priv ? ", private tab" : "") + (autoReload ? "; reloads when shown" : "") + ")";
}

} // namespace OmniCrashChoices
