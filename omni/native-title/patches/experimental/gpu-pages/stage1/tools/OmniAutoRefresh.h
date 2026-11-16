// OMNI_AUTO_REFRESH_V1: the pure part of the page menu's "Auto-refresh" (no SDL, no WebKit). The shell side is
// OmniAutoRefreshShell.h; the reasons are in tools/apply_auto_refresh.py. Tested on the host with g++
// (test_auto_refresh.cpp).
// Hold Cross on a page > "Auto-refresh": Off / 30 s / 1 / 5 / 15 / 30 min for this tab, plus "Always for this site"
// (stored in /data/omni/refresh-sites.txt; never for a private tab). The tab is reloaded (WKPageReload) at the interval,
// but a due reload is SKIPPED (and tried again one interval later) when the tab is asleep / unloaded, loading, crashed,
// playing media, the user is typing or touched the controller in the last 20 s (shown tab), the page holds unsaved input
// (tab sleep's one-shot page script), the page is the result of a form POST, or the console is offline. omni:// pages,
// other non-web pages, the Downloads app's tab and Reader view are never refreshed.
#pragma once
#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <map>
#include <string>
#include <vector>

namespace OmniAutoRefresh {

constexpr int kContextId = 993;               // hold-Cross page menu row (free among the page menu rows)
constexpr int kPanelKind = 7500;              // the chooser's OmniFxPanel::kind
constexpr int kRowSite = 100;                 // the chooser's "Always for this site" row (interval rows: their seconds)
constexpr uint32_t kQuietMs = 20000;          // shown tab: no reload within 20 s of the last controller input
constexpr uint32_t kProbeTimeoutMs = 10000;   // the unsaved-input script unanswered: this round is skipped
constexpr uint32_t kTickMs = 250;             // the shell looks at the timers at most 4 times a second
constexpr uint32_t kRestoreDelayMs = 1500;    // after our reload finished: the scroll fallback waits this long
constexpr uint32_t kRestoreWindowMs = 30000;  // ... and gives up this long after the reload
constexpr size_t kMaxSites = 200;             // remembered sites (oldest line dropped beyond)
constexpr const char* kFileName = "refresh-sites.txt";   // in /data/omni: "host\tseconds\n" per site

// --- intervals ------------------------------------------------------------------------------------------------------
inline const int* steps() { static const int s[] = { 0, 30, 60, 300, 900, 1800 }; return s; }
constexpr int kStepCount = 6;
inline bool validSeconds(int s)
{
    for (int i = 0; i < kStepCount; ++i) if (steps()[i] == s) return true;
    return false;
}
inline std::string choiceLabel(int s)
{
    if (s <= 0) return "Off";
    if (s < 60) return std::to_string(s) + " s";
    return std::to_string(s / 60) + " min";
}
inline std::string rowValue(int s) { return s > 0 ? "Every " + choiceLabel(s) : std::string("Off"); }
inline std::string setNotice(int s) { return s > 0 ? "Auto-refresh every " + choiceLabel(s) + " (paused while you use the page)" : std::string("Auto-refresh off"); }
inline std::string siteNotice(const std::string& site, int s)
{
    return s > 0 ? "Always for " + site + ": every " + choiceLabel(s) : "Auto-refresh no longer automatic for " + site;
}
inline const char* privateDetail() { return "Private tab: this tab only, nothing is stored"; }

// --- the site key: the page's host, lower case, without "www." and port; http(s) pages only ------------------------
inline std::string siteKey(const std::string& url)
{
    size_t at;
    if (url.rfind("https://", 0) == 0) at = 8;
    else if (url.rfind("http://", 0) == 0) at = 7;
    else return std::string();
    const size_t end = std::min(url.find_first_of("/?#", at), url.size());
    std::string h = url.substr(at, end - at);
    const size_t user = h.rfind('@');
    if (user != std::string::npos) h = h.substr(user + 1);
    if (!h.empty() && h[0] == '[') { const size_t c = h.find(']'); h = c == std::string::npos ? std::string() : h.substr(0, c + 1); }
    else { const size_t c = h.find(':'); if (c != std::string::npos) h = h.substr(0, c); }
    for (char& c : h) if (c >= 'A' && c <= 'Z') c = char(c - 'A' + 'a');
    while (!h.empty() && h.back() == '.') h.pop_back();
    if (h.rfind("www.", 0) == 0 && h.size() > 4) h = h.substr(4);
    for (char c : h) if (c == '\t' || c == '\n' || c == '\r' || c == ' ') return std::string();
    return h;
}

// --- remembered sites -----------------------------------------------------------------------------------------------
struct Sites {
    std::vector<std::pair<std::string, int>> list;   // file order (oldest first)
    int get(const std::string& site) const
    {
        for (const auto& e : list) if (e.first == site) return e.second;
        return 0;
    }
    // seconds 0 removes the site; a new or changed site moves to the end (newest); beyond kMaxSites the oldest goes.
    bool set(const std::string& site, int seconds)
    {
        if (site.empty() || (seconds && !validSeconds(seconds))) return false;
        auto it = std::find_if(list.begin(), list.end(), [&](const std::pair<std::string, int>& e) { return e.first == site; });
        if (!seconds) {
            if (it == list.end()) return false;
            list.erase(it);
            return true;
        }
        if (it != list.end()) {
            if (it->second == seconds) return false;
            list.erase(it);
        }
        list.emplace_back(site, seconds);
        while (list.size() > kMaxSites) list.erase(list.begin());
        return true;
    }
};
inline Sites parseSites(const std::string& text)
{
    Sites s;
    size_t at = 0;
    while (at < text.size()) {
        size_t end = text.find('\n', at);
        if (end == std::string::npos) end = text.size();
        std::string line = text.substr(at, end - at);
        at = end + 1;
        while (!line.empty() && (line.back() == '\r' || line.back() == ' ')) line.pop_back();
        const size_t tab = line.find('\t');
        if (tab == std::string::npos || !tab) continue;
        const std::string k = line.substr(0, tab), v = line.substr(tab + 1);
        if (v.empty() || v.size() > 5 || v.find_first_not_of("0123456789") != std::string::npos) continue;
        if (siteKey("https://" + k + "/") != k) continue;   // only what siteKey makes
        s.set(k, std::atoi(v.c_str()));
    }
    return s;
}
inline std::string serialize(const Sites& s)
{
    std::string out;
    for (const auto& e : s.list) out += e.first + "\t" + std::to_string(e.second) + "\n";
    return out;
}

// --- the schedule (SDL ticks, wrap-safe) --------------------------------------------------------------------------
inline bool reached(uint32_t now, uint32_t at) { return int32_t(now - at) >= 0; }
struct Timer {
    int seconds = 0;     // 0: off
    uint32_t due = 0;
    void set(int s, uint32_t now) { seconds = validSeconds(s) ? s : 0; restart(now); }
    void restart(uint32_t now) { due = now + uint32_t(seconds) * 1000u; }   // a commit, a reload, a skip
    bool on() const { return seconds > 0; }
    bool isDue(uint32_t now) const { return on() && reached(now, due); }
    uint32_t remainingMs(uint32_t now) const { return on() && !reached(now, due) ? uint32_t(due - now) : 0u; }
};
// "4:12" (minutes:seconds, rounded up: a fresh 30 s timer shows "0:30", the last second "0:01", due "0:00").
inline std::string countdown(uint32_t remainingMs)
{
    const uint32_t s = (remainingMs + 999u) / 1000u;
    const uint32_t m = s / 60u, r = s % 60u;
    return std::to_string(m) + ":" + (r < 10 ? "0" : "") + std::to_string(r);
}

// --- the skip rules -------------------------------------------------------------------------------------------------
struct Facts {
    bool web = false;          // http(s) page (omni://, about:, file:, data: never)
    bool reader = false;       // Reader view (its HTML was committed while the tab's omniReader flag was set)
    bool mediaApp = false;     // the Downloads app's tab (omniMediaOwns)
    bool asleep = false;       // unloaded / lazy (tab sleep, tab memory guard, session restore): never woken
    bool loading = false, crashed = false;
    bool media = false;        // WKPageGetMediaState: playing audio or video
    bool shown = false;        // the active tab
    bool typing = false;       // the on-screen keyboard is open (address bar or a page field)
    uint32_t sinceInputMs = 0xffffffffu;   // since the last controller / pointer input
    bool post = false;         // the committed page came from a POST
    bool offline = false;      // OMNI_OFFLINE_RETRY_V1: no route, or this tab shows the offline error
};
enum Reason { kGo = 0, kNever, kAsleep, kLoading, kCrashed, kMedia, kTyping, kRecentInput, kPost, kOffline, kUnsaved, kNoAnswer };
inline Reason decide(const Facts& f)
{
    if (!f.web || f.reader || f.mediaApp) return kNever;
    if (f.asleep) return kAsleep;
    if (f.crashed) return kCrashed;
    if (f.loading) return kLoading;
    if (f.post) return kPost;
    if (f.offline) return kOffline;
    if (f.media) return kMedia;
    if (f.shown && f.typing) return kTyping;
    if (f.shown && f.sinceInputMs < kQuietMs) return kRecentInput;
    return kGo;
}
inline const char* reasonText(Reason r)
{
    switch (r) {
    case kGo: return "reload";
    case kNever: return "not a web page";
    case kAsleep: return "tab asleep";
    case kLoading: return "loading";
    case kCrashed: return "crashed";
    case kMedia: return "media playing";
    case kTyping: return "typing";
    case kRecentInput: return "in use";
    case kPost: return "form result (POST)";
    case kOffline: return "offline";
    case kUnsaved: return "unsaved input";
    case kNoAnswer: return "page did not answer";
    }
    return "?";
}
// The chip shows only where a refresh can happen at all.
inline bool chipShown(const Timer& t, const Facts& f) { return t.on() && decide(f) != kNever; }

// --- the page script: tab sleep's unsaved-input probe ("c" / "d") plus the scroll position ---------------------------
// probe: OmniTabSleep::kProbeScript (an expression). Answer "c,12,3400" (verdict, scrollX, scrollY).
inline std::string probeScript(const char* probe)
{
    return std::string("(function(){var v;try{v=") + probe + ";}catch(e){v='d';}"
        "var x=0,y=0;try{x=Math.round(window.scrollX||0);y=Math.round(window.scrollY||0);}catch(e){}"
        "return String(v)+','+x+','+y;})()";
}
struct Answer { bool ok = false, clean = false; int x = 0, y = 0; };
inline Answer parseAnswer(const std::string& s, bool error)
{
    Answer a;
    if (error || s.size() < 5 || s.size() > 40) return a;
    const size_t c1 = s.find(','), c2 = c1 == std::string::npos ? c1 : s.find(',', c1 + 1);
    if (c1 != 1 || c2 == std::string::npos) return a;
    auto num = [](const std::string& v, int& out) {
        if (v.empty() || v.size() > 9) return false;
        size_t i = v[0] == '-' ? 1 : 0;
        if (i == v.size() || v.find_first_not_of("0123456789", i) != std::string::npos) return false;
        out = std::atoi(v.c_str());
        return true;
    };
    if (!num(s.substr(c1 + 1, c2 - c1 - 1), a.x) || !num(s.substr(c2 + 1), a.y)) return a;
    a.ok = s[0] == 'c' || s[0] == 'd';
    a.clean = s[0] == 'c';
    if (a.x < 0) a.x = 0;
    if (a.y < 0) a.y = 0;
    return a;
}
// WebKit restores the scroll position of a reload from the history item when loading completes
// (FrameLoader::checkLoadCompleteForThisFrame -> HistoryController::restoreScrollPositionAndViewState). Pages that
// build their content after the load event end up clamped near the top; this one script then scrolls once, only when
// the page still sits at the top (never against the user or the page's own scrolling).
inline bool wantsRestore(int savedY) { return savedY > 40; }
inline std::string restoreScript(int x, int y)
{
    return "(function(x,y){try{if((window.scrollY||0)<8)window.scrollTo(x,y);return String(Math.round(window.scrollY||0));}catch(e){return '';}})("
        + std::to_string(std::max(0, x)) + "," + std::to_string(std::max(0, y)) + ")";
}

// --- the top-bar chip: reload icon + "4:12", right of the downloads indicator (layout px, interface size scales) ---
constexpr float kTopBarRight = 1276.f;    // as the sleep timer / offline / downloads badges
constexpr float kIconW = 16.f;            // the reload icon's visible box
constexpr float kTextGap = 3.f;
constexpr float kBadgeGap = 12.f;         // previous badge -> ours
struct Chip { float x = 0, w = 0; int mode = 0; int textMax = 0; };   // mode 0 hidden, 1 icon only, 2 icon + text
inline Chip chipLayout(float x, float textW)
{
    Chip c;
    c.x = x;
    const float room = kTopBarRight - x;
    if (room >= kIconW + kTextGap + textW) { c.mode = 2; c.textMax = int(room - kIconW - kTextGap); c.w = kIconW + kTextGap + textW; }
    else if (room >= kIconW) { c.mode = 1; c.w = kIconW; }
    return c;
}

} // namespace OmniAutoRefresh
