// OMNI_TAB_MEMORY_VIEW_V1: the pure part of the Tabs > Memory panel (no SDL, no WebKit). The shell side is
// OmniTabMemoryViewShell.h; the reasons are in tools/apply_tab_memory_view.py. Tested on the host with g++
// (tools/test_tab_memory_view.cpp).
// What can be measured on this port: the shell's own flexible memory (sceKernelConfiguredFlexibleMemorySize minus
// sceKernelAvailableFlexibleMemorySize), the hardware decoders' shared memory and the rendered-text cache. Every tab
// shares ONE web process (WKContextSetUsesSingleWebProcess) and its memory cannot be read from the shell
// (WKContextGetStatistics is an empty stub), so there is no per-tab number: rows say loaded / unloaded only.
// "Keep loaded" is a memory-only soft pin (at most 2, this session only): such a tab is never unloaded to keep the
// loaded-tab count, nor by "Unload all background tabs"; only when the shell is low on memory and no other tab can
// go. Unload order otherwise as before: unpinned before pinned (OMNI_PINNED_TABS_V1), a collapsed group's tabs first
// (OMNI_TAB_GROUPS_V1), then the least recently shown.
#pragma once
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace OmniTabMemoryView {

constexpr int kMaxKeep = 2;
constexpr uint32_t kRefreshMs = 2000;   // panel numbers while it is open; nothing while closed

// Why a tab cannot be unloaded now (the shell mirrors omniTmCanUnload).
enum Block { kFree = 0, kCurrent, kAlready, kLoading, kStopped, kPlaying, kMediaOwned, kNotWeb };

struct TabState {
    bool loaded = true;
    Block block = kFree;          // kFree: the guard may unload it
    bool pinned = false, collapsed = false, kept = false;
    uint32_t shownAt = 0;
};

// Is a unloaded before b? "Keep loaded" last, then pinned last, a collapsed group's tabs first, least recently shown.
inline bool unloadsBefore(const TabState& a, const TabState& b)
{
    if (a.kept != b.kept) return !a.kept;
    if (a.pinned != b.pinned) return !a.pinned;
    if (a.collapsed != b.collapsed) return a.collapsed;
    return a.shownAt < b.shownAt;
}
// The tab the guard unloads next, -1 none. allowKept: the shell is low on memory (a kept tab is the last resort).
inline int pickUnload(const std::vector<TabState>& tabs, bool allowKept)
{
    int best = -1;
    for (size_t i = 0; i < tabs.size(); ++i) {
        const TabState& t = tabs[i];
        if (!t.loaded || t.block != kFree || (t.kept && !allowKept)) continue;
        if (best < 0 || unloadsBefore(t, tabs[size_t(best)])) best = int(i);
    }
    return best;
}
// "Unload all background tabs": every loaded tab the guard may unload, except "Keep loaded" ones (pinned included).
inline std::vector<int> unloadAllPlan(const std::vector<TabState>& tabs)
{
    std::vector<int> out;
    for (size_t i = 0; i < tabs.size(); ++i)
        if (tabs[i].loaded && tabs[i].block == kFree && !tabs[i].kept) out.push_back(int(i));
    return out;
}
// The reasons omniTmUnloadOne is called with: which may take a kept tab.
inline bool allowKeptFor(const std::string& why)
{
    return why == "shell memory low" || why == "new tab refused";
}

// --- "Keep loaded" set (pointers to tabs; session only) ------------------------------------------------------------
enum KeepResult { kKeepAdded, kKeepRemoved, kKeepFull, kKeepRefused };
// canKeep: false for a tab the guard never unloads anyway (not a web page, owned by the media section): refused.
inline KeepResult toggleKeep(std::vector<const void*>& set, const void* tab, bool canKeep)
{
    for (size_t i = 0; i < set.size(); ++i)
        if (set[i] == tab) { set.erase(set.begin() + long(i)); return kKeepRemoved; }
    if (!canKeep) return kKeepRefused;
    if (int(set.size()) >= kMaxKeep) return kKeepFull;
    set.push_back(tab);
    return kKeepAdded;
}
inline bool kept(const std::vector<const void*>& set, const void* tab)
{
    for (const void* p : set) if (p == tab) return true;
    return false;
}
inline void forget(std::vector<const void*>& set, const void* tab)
{
    for (size_t i = set.size(); i-- > 0;) if (set[i] == tab) set.erase(set.begin() + long(i));
}
inline const char* keepNotice(KeepResult r)
{
    switch (r) {
    case kKeepAdded: return "This tab stays loaded (until Omni closes)";
    case kKeepRemoved: return "This tab may be unloaded again to save memory";
    case kKeepFull: return "Two tabs are kept loaded already: release one first (Triangle)";
    default: return "This tab can't be kept loaded";
    }
}

constexpr const char* kPerTabLabel = "Memory per tab";
constexpr const char* kPerTabValue = "Not readable";
constexpr const char* kPerTabDetail = "All tabs share one web process; its memory can't be read on this console";

// --- text ----------------------------------------------------------------------------------------------------------
inline std::string mbText(long long mib) { return std::to_string(mib < 0 ? 0 : mib) + " MB"; }
// "Shell 312 MB · 3 of 9 tabs loaded" (· is U+00B7). shellUsedMiB < 0: unknown (host, or the query failed).
inline std::string summary(long long shellUsedMiB, int loaded, int total)
{
    std::string s = shellUsedMiB >= 0 ? "Shell " + mbText(shellUsedMiB) : std::string("Shell memory unknown");
    s += " \xc2\xb7 " + std::to_string(loaded) + " of " + std::to_string(total) + (total == 1 ? " tab loaded" : " tabs loaded");
    return s;
}
// The panel's hint-bar line: free shell memory, video decoders' shared memory (while any is open), text cache.
inline std::string detailLine(long long shellFreeMiB, size_t hwSharedMiB, int hwDecoders, size_t textCacheKiB)
{
    std::string s;
    if (shellFreeMiB >= 0) s += mbText(shellFreeMiB) + " free";
    if (hwDecoders > 0) s += (s.empty() ? "" : " \xc2\xb7 ") + std::string("video ") + mbText((long long)hwSharedMiB);
    s += (s.empty() ? "" : " \xc2\xb7 ") + std::string("text ") + mbText((long long)((textCacheKiB + 512) >> 10));
    return s;
}
// Row label: "● title" loaded, "○ title" unloaded (U+25CF / U+25CB).
inline std::string rowLabel(bool loaded, const std::string& title)
{
    return std::string(loaded ? "\xe2\x97\x8f " : "\xe2\x97\x8b ") + title;
}
inline std::string rowValue(const TabState& t)
{
    if (t.block == kCurrent) return t.kept ? "Current, kept loaded" : "Current";
    if (!t.loaded) return "Unloaded";
    if (t.kept) return "Kept loaded";
    switch (t.block) {
    case kLoading: return "Loading";
    case kStopped: return "Stopped";
    case kPlaying: return "Playing";
    case kMediaOwned: return "Media";
    default: return t.pinned ? "Loaded, pinned" : "Loaded";
    }
}
// Square on a row that cannot be unloaded: why (empty: it can).
inline const char* unloadRefusal(const TabState& t)
{
    if (!t.loaded) return "This tab is already unloaded";
    switch (t.block) {
    case kCurrent: return "The tab you are viewing can't be unloaded";
    case kLoading: return "This tab is still loading: try again when it is done";
    case kStopped: return "This tab stopped (crashed): it holds no page";
    case kPlaying: return "This tab is playing audio or video";
    case kMediaOwned: return "This tab belongs to the media player";
    case kNotWeb: return "Only web pages are unloaded";
    default: return "";
    }
}
inline std::string unloadAllValue(size_t n)
{
    return n ? std::to_string(n) + (n == 1 ? " tab" : " tabs") : std::string("Nothing to unload");
}
inline std::string unloadAllNotice(size_t n)
{
    return n ? "Unloaded " + std::to_string(n) + (n == 1 ? " background tab" : " background tabs") : std::string("No background tab can be unloaded");
}
// "Keep loaded" face label for the selected row.
inline const char* keepFace(bool isKept) { return isKept ? "Don't keep loaded" : "Keep loaded"; }
// SDL_GetTicks()-style clock, wrap-safe.
inline bool refreshDue(uint32_t now, uint32_t last) { return uint32_t(now - last) >= kRefreshMs; }

} // namespace OmniTabMemoryView
