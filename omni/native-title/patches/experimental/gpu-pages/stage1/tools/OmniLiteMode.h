// OMNI_LITE_MODE_V1: the pure part of Browser settings > "Lite mode" (no SDL, no WebKit). The shell side is
// OmniLiteModeShell.h; the reasons are in tools/apply_lite_mode.py. Tested on the host with g++ (test_lite_mode.cpp).
// One switch, default Off. On: at most 3 tabs stay loaded (the others are unloaded through tab sleep's path, least
// recently shown first; never the shown, pinned, audible, private or "Keep loaded" tabs), no tab thumbnails, a smaller
// rendered-text cache, and no reserve spare engine. Off: each of those is back to what it was.
#pragma once
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace OmniLiteMode {

constexpr int kRow = 364;                  // Browser settings row (omniF3SettingsInput: ids 300..899)
constexpr int kMaxLoaded = 3;              // loaded tabs kept while On (the shown one included)
constexpr int kMaxPerCheck = 2;            // at most 2 unloads per check
constexpr uint32_t kCheckMs = 1000;        // one check a second while On
constexpr size_t kMinTextBytes = size_t(8) << 20;   // the lowered text cache never goes under 8 MiB ...
constexpr const char* kFileName = "lite-mode.txt";  // in /data/omni: "on\t1\n"
constexpr const char* kUnloadWhy = "lite mode";      // omniTmUnloadOne's reason (log line)
constexpr const char* kStashSuffix = ".lite";        // a spare-engine flag set aside while On: "<flag>.lite"

// The launcher's reserve spare engine (omni-process-launcher-v2.inc, OMNI_SPARE_DEFER_V1 / OMNI_SPARE_LAZY_V1) is
// started after a launch only while one of these /data/omni flags exists.
inline const char* const* spareFlags() { static const char* const f[] = { "spare-reserve.flag", "spare-defer-off.flag" }; return f; }
constexpr int kSpareFlagCount = 2;

struct Settings {
    bool on = false;
};
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
        if (line == "on\t1") s.on = true;
        else if (line == "on\t0") s.on = false;
    }
    return s;
}
inline std::string serialize(const Settings& s) { return std::string("on\t") + (s.on ? "1" : "0") + "\n"; }

// --- text cache: ... and is never above the normal budget (OTCC::budgetFor) -------------------------------------------
inline size_t textBudget(size_t normal, bool lite)
{
    if (!lite) return normal;
    return std::min(normal, std::max(normal / 2, kMinTextBytes));
}

// --- spare-engine flags: what to do with one flag (live = /data/omni/<flag>, stashed = <flag>.lite) -------------------
// On: a live flag is set aside (renamed to the stash); Off: a stashed flag is put back. A flag the user made again while
// On wins over the stash at Off (the stash is dropped); while On it is set aside again (the stash is replaced).
enum FlagStep { kKeep = 0, kStash, kRestore, kDropStash };
inline FlagStep flagStep(bool liteOn, bool live, bool stashed)
{
    if (liteOn) return live ? kStash : kKeep;
    if (!stashed) return kKeep;
    return live ? kDropStash : kRestore;
}

// --- which tabs to unload ---------------------------------------------------------------------------------------------
struct Cand {
    bool loaded = false;     // !omniTmIsUnloaded (lazy restored tabs count as unloaded)
    bool current = false;    // the shown tab
    bool pinned = false;     // OMNI_PINNED_TABS_V1
    bool audible = false;    // a sound badge or playing audio (OMNI_TAB_AUDIO_V1)
    bool keep = false;       // private, "Keep loaded" (OMNI_TAB_MEMORY_VIEW_V1)
    bool free = false;       // omniTmCanUnload: not loading / crashed / media-owned, a web page, not playing
    uint32_t shownAt = 0;    // last shown (SDL ticks); 0: never shown (oldest)
};
inline bool eligible(const Cand& c) { return c.loaded && !c.current && !c.pinned && !c.audible && !c.keep && c.free; }
// The tabs to unload now, least recently shown first (ties: lower index first), so that at most `maxLoaded` stay
// loaded; at most `maxPerCheck`. Fewer when not enough tabs may be unloaded.
inline std::vector<int> pick(const std::vector<Cand>& tabs, uint32_t now, int maxLoaded = kMaxLoaded, int maxPerCheck = kMaxPerCheck)
{
    int loaded = 0;
    for (const Cand& c : tabs) if (c.loaded) ++loaded;
    const int excess = std::min(loaded - maxLoaded, maxPerCheck);
    std::vector<int> out;
    if (excess <= 0) return out;
    for (size_t i = 0; i < tabs.size(); ++i) if (eligible(tabs[i])) out.push_back(int(i));
    auto idle = [&](int i) { const uint32_t s = tabs[size_t(i)].shownAt; return s ? uint32_t(now - s) : UINT32_MAX; };
    std::stable_sort(out.begin(), out.end(), [&](int a, int b) { return idle(a) > idle(b); });
    if (int(out.size()) > excess) out.resize(size_t(excess));
    return out;
}
inline bool checkDue(uint32_t now, uint32_t last) { return !last || uint32_t(now - last) >= kCheckMs; }

// --- texts ------------------------------------------------------------------------------------------------------------
inline const char* label() { return "Lite mode"; }
inline const char* value(bool on) { return on ? "On" : "Off"; }
inline const char* detail(bool on)
{
    return on ? "3 tabs stay loaded, no tab pictures, smaller text cache, no spare engine"
              : "For heavy sites and long sessions: fewer loaded tabs and caches";
}
inline const char* notice(bool on)
{
    return on ? "Lite mode on: 3 tabs stay loaded (others reload when shown)" : "Lite mode off: tabs and caches back to your settings";
}

} // namespace OmniLiteMode
