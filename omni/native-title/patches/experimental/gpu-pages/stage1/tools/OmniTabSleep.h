// OMNI_TAB_SLEEP_V1: the pure part of Browser settings > "Sleep idle tabs" (no SDL, no WebKit). The shell side is
// OmniTabSleepShell.h; the reasons are in tools/apply_tab_sleep.py. Tested on the host with g++ (test_tab_sleep.cpp).
// A background tab not shown for N minutes (Off / 10 / 30 / 60, default 30) is unloaded the same way the tab-count
// guard unloads one (OmniTabMemory.h omniTmUnloadOne: session history kept, reloads when shown). On top of that guard,
// never instead of it. Checked once a minute; at most 2 tabs per check.
// Never slept: the shown tab, a tab the guard may not unload (already unloaded, loading, crashed, owned by the media
// section, not a web page, playing audio or video: background audio OMNI_BG_AUDIO_V1 included), a tab with a sound
// badge, a private tab (its state would be lost for good), a "Keep loaded" tab (OMNI_TAB_MEMORY_VIEW_V1), a pinned tab
// unless "Include pinned tabs" is on, any tab while a download runs or was just handed to Downloads, and a tab whose
// page has unsaved input (a one-shot page script per background stint answers that).
#pragma once
#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <string>
#include <vector>

namespace OmniTabSleep {

constexpr int kRowMinutes = 347;          // Browser settings rows (omniF3SettingsInput: ids 300..899)
constexpr int kRowPinned = 348;
constexpr uint32_t kCheckMs = 60000;      // one check a minute
constexpr int kMaxPerCheck = 2;           // at most 2 tabs probed / put to sleep per check
constexpr uint32_t kProbeTimeoutMs = 30000;   // an unanswered page script is asked again at a later check
constexpr int kDefaultMinutes = 30;
constexpr const char* kFileName = "tab-sleep.txt";   // in /data/omni: "minutes\t30\npinned\t0\n"
constexpr const char* kAsleepValue = "Asleep";       // Tabs panel / Memory panel value instead of "Unloaded"
constexpr const char* kUnloadWhy = "idle tab asleep"; // omniTmUnloadOne's reason (log line; not a "memory low" reason)

inline const int* minuteSteps() { static const int s[] = { 0, 10, 30, 60 }; return s; }
constexpr int kStepCount = 4;

struct Settings {
    int minutes = kDefaultMinutes;   // 0: Off
    bool pinned = false;             // "Include pinned tabs"
};

// The nearest valid step (0 / 10 / 30 / 60).
inline int snapMinutes(int m)
{
    const int* s = minuteSteps();
    int best = s[0];
    for (int i = 0; i < kStepCount; ++i) if (std::abs(s[i] - m) < std::abs(best - m)) best = s[i];
    return best;
}
// D-pad left / right: one step, stops at the ends. Cross (wrap): Off -> 10 -> 30 -> 60 -> Off.
inline int stepMinutes(int m, int dir, bool wrap)
{
    const int* s = minuteSteps();
    int i = 0;
    for (int k = 0; k < kStepCount; ++k) if (s[k] == snapMinutes(m)) i = k;
    if (wrap && dir > 0 && i == kStepCount - 1) return s[0];
    return s[std::clamp(i + dir, 0, kStepCount - 1)];
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
        if (v.empty() || v.find_first_not_of("0123456789") != std::string::npos || v.size() > 6) continue;
        const int n = std::stoi(v);
        if (k == "minutes") s.minutes = snapMinutes(n);
        else if (k == "pinned") s.pinned = n != 0;
    }
    return s;
}
inline std::string serialize(const Settings& s)
{
    return "minutes\t" + std::to_string(snapMinutes(s.minutes)) + "\npinned\t" + (s.pinned ? "1" : "0") + "\n";
}

// --- texts ----------------------------------------------------------------------------------------------------------
inline const char* label() { return "Sleep idle tabs"; }
inline const char* pinnedLabel() { return "Include pinned tabs"; }
inline std::string minutesValue(int m) { return m ? "After " + std::to_string(m) + " min" : std::string("Off"); }
inline std::string minutesDetail(int m)
{
    return m ? "Background tabs not shown for " + std::to_string(m) + " min are unloaded to free memory; they reload when shown"
             : std::string("Background tabs are unloaded only by \"Tabs kept loaded\" and when memory is low");
}
inline std::string pinnedDetail(bool on, int m)
{
    if (!m) return "Used when \"Sleep idle tabs\" is on";
    return on ? std::string("Pinned tabs sleep too") : std::string("Pinned tabs stay loaded");
}
inline std::string minutesNotice(int m)
{
    return m ? "Idle tabs sleep after " + std::to_string(m) + " min (playing, private, kept and unsaved tabs stay)"
             : std::string("Idle tabs stay loaded");
}
inline const char* pinnedNotice(bool on) { return on ? "Pinned tabs may sleep when idle" : "Pinned tabs never sleep"; }

// --- the decision -----------------------------------------------------------------------------------------------------
// The page's answer for this background stint (reset whenever the tab is shown again).
enum Verdict { kUnknown = 0, kProbing, kClean, kDirty };

struct Cand {
    bool free = false;       // omniTmCanUnload: not shown, loaded, not loading / crashed / media-owned, a web page, not playing
    bool sound = false;      // a sound badge (OMNI_TAB_AUDIO_V1): playing, muted or not
    bool priv = false;       // private tab
    bool pinned = false, kept = false, collapsed = false;
    uint32_t idleSince = 0;  // last shown (SDL ticks); first seen by the check when never shown
    Verdict verdict = kUnknown;
};

enum Decision { kOff = 0, kNotFree, kSound, kPrivate, kKept, kPinned, kRecent, kDownloads, kUnsaved, kWaiting, kProbe, kSleep };

inline bool idleEnough(uint32_t now, uint32_t idleSince, int minutes)
{
    return minutes > 0 && uint32_t(now - idleSince) >= uint32_t(minutes) * 60000u;   // wrap-safe
}
inline Decision decide(const Cand& c, uint32_t now, const Settings& s, bool downloadsBusy)
{
    if (s.minutes <= 0) return kOff;
    if (!c.free) return kNotFree;
    if (c.sound) return kSound;
    if (c.priv) return kPrivate;
    if (c.kept) return kKept;
    if (c.pinned && !s.pinned) return kPinned;
    if (!idleEnough(now, c.idleSince, s.minutes)) return kRecent;
    if (downloadsBusy) return kDownloads;
    switch (c.verdict) {
    case kDirty: return kUnsaved;
    case kProbing: return kWaiting;
    case kClean: return kSleep;
    default: return kProbe;
    }
}
// Is a taken before b? Unpinned before pinned, a collapsed group's tabs first, then the longest idle (as the
// count guard's order, OTMV::unloadsBefore; "Keep loaded" tabs never get here).
inline bool before(const Cand& a, const Cand& b, uint32_t now)
{
    if (a.pinned != b.pinned) return !a.pinned;
    if (a.collapsed != b.collapsed) return a.collapsed;
    return uint32_t(now - a.idleSince) > uint32_t(now - b.idleSince);
}
// The tabs this check acts on (probe or sleep), in order, at most `max`.
inline std::vector<int> pick(const std::vector<Cand>& tabs, uint32_t now, const Settings& s, bool downloadsBusy, int max = kMaxPerCheck)
{
    std::vector<int> out;
    for (size_t i = 0; i < tabs.size(); ++i) {
        const Decision d = decide(tabs[i], now, s, downloadsBusy);
        if (d == kProbe || d == kSleep) out.push_back(int(i));
    }
    std::stable_sort(out.begin(), out.end(), [&](int a, int b) { return before(tabs[size_t(a)], tabs[size_t(b)], now); });
    if (int(out.size()) > max) out.resize(size_t(std::max(0, max)));
    return out;
}
// Once a minute; the first call only arms the clock (nothing sleeps in the first minute after start).
inline bool checkDue(uint32_t now, uint32_t& last, bool& primed)
{
    if (!primed) { primed = true; last = now; return false; }
    return uint32_t(now - last) >= kCheckMs;
}
inline bool probeTimedOut(uint32_t now, uint32_t probeAt) { return uint32_t(now - probeAt) >= kProbeTimeoutMs; }

// The page script's answer: "c" no unsaved input; anything else (dirty, an error, no string) keeps the tab awake.
inline Verdict verdictOf(const std::string& answer, bool error) { return !error && answer == "c" ? kClean : kDirty; }

// One-shot page script (main frame + same-origin frames, 2 levels). "d": a form control differs from its default
// (text / textarea / checkbox / radio / select / chosen file), the focused contenteditable holds text, or the page set
// window.onbeforeunload ("leave site?"); "c": none. It reads no values out, only compares; capped at 3000 controls.
constexpr const char* kProbeScript =
    "(function(){try{"
    "if(typeof window.onbeforeunload==='function')return 'd';"
    "var seen=0;"
    "function sel(e){var o=e.options,n=o.length,d=-1,k;"
    "if(e.multiple){for(k=0;k<n&&k<500;k++)if(o[k].selected!==o[k].defaultSelected)return true;return false;}"
    "for(k=0;k<n&&k<500;k++)if(o[k].defaultSelected)d=k;"
    "if(d<0&&n&&(e.size||1)<=1)d=0;"
    "return e.selectedIndex!==d;}"
    "function dirty(doc,depth){"
    "var es=doc.querySelectorAll('input,textarea,select'),i,e,t,ty;"
    "for(i=0;i<es.length;i++){if(++seen>3000)return false;e=es[i];t=e.tagName;"
    "if(e.disabled)continue;"
    "if(t==='SELECT'){if(sel(e))return true;continue;}"
    "if(e.readOnly)continue;"
    "if(t==='TEXTAREA'){if(e.value!==e.defaultValue)return true;continue;}"
    "ty=String(e.type||'').toLowerCase();"
    "if(ty==='hidden'||ty==='submit'||ty==='button'||ty==='reset'||ty==='image')continue;"
    "if(ty==='checkbox'||ty==='radio'){if(e.checked!==e.defaultChecked)return true;continue;}"
    "if(ty==='file'){if(e.files&&e.files.length)return true;continue;}"
    "if(e.value!==e.defaultValue)return true;}"
    "var a=doc.activeElement;"
    "if(a&&a.isContentEditable&&String(a.textContent||'').replace(/\\s+/g,'').length)return true;"
    "if(depth<2){var fs=doc.querySelectorAll('iframe,frame');"
    "for(i=0;i<fs.length&&i<20;i++){try{var cd=fs[i].contentDocument;if(cd&&dirty(cd,depth+1))return true;}catch(x){}}}"
    "return false;}"
    "return dirty(document,0)?'d':'c';"
    "}catch(x){return 'd';}})()";

} // namespace OmniTabSleep
