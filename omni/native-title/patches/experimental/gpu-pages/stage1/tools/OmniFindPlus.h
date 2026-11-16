// OMNI_FIND_PLUS_V1: the pure part of the TV-friendly Find on page (no SDL, no WebKit).
// The shell side is OmniFindPlusShell.h; the reasons are in tools/apply_find_plus.py. Tested on the host with g++
// (test_find_plus.cpp).
#pragma once
#include <cstddef>
#include <cstdint>
#include <deque>
#include <string>
#include <unordered_map>
#include <vector>

namespace OmniFindPlus {

// WKFindOptions bits (Shared/API/c/WKFindOptions.h); the shell static_asserts that they still match.
constexpr uint32_t kCaseInsensitive = 1u << 0, kBackwards = 1u << 3, kWrapAround = 1u << 4, kShowOverlay = 1u << 5,
    kShowFindIndicator = 1u << 6, kShowHighlight = 1u << 7;
constexpr unsigned kMaxMatches = 1000;                       // WKPageFindString's maxMatchCount
constexpr uint32_t kMoreThanMax = 0xffffffffu;               // kWKMoreThanMaximumMatchCount as the find client sees it
constexpr size_t kQueryMax = 256;                            // bytes kept per tab

// Every search marks all matches (ShowHighlight), moves to the next / previous one with the find indicator, and
// wraps at the ends. ShowOverlay (WebKit's dimming page overlay) is not used: an extra composited layer for nothing.
inline uint32_t options(bool caseSensitive, int step)
{
    uint32_t o = kWrapAround | kShowHighlight | kShowFindIndicator;
    if (!caseSensitive) o |= kCaseInsensitive;
    if (step < 0) o |= kBackwards;
    return o;
}

enum class Wrap { None, ToTop, ToBottom };

// One tab's find state. Lives in memory only (the session); never written anywhere, private tabs included.
struct State {
    std::string query;
    bool open = false;             // the bar is up on this tab (shown while the tab is active)
    bool caseSensitive = false;
    int count = -1;                // -1 searching, 0 no matches, else the number of matches (<= kMaxMatches)
    bool more = false;             // more than kMaxMatches: the count and position are not known
    int index = 0;                 // 1-based position of the current match, 0 none
    std::deque<int> steps;         // the steps of the searches still in flight, oldest first (0 = new search)

    void setQuery(const std::string& q)
    {
        size_t n = q.size();
        if (n > kQueryMax) {   // never cut a UTF-8 sequence in half: q[n] (the first byte dropped) must start one
            n = kQueryMax;
            while (n > 0 && (static_cast<unsigned char>(q[n]) & 0xc0) == 0x80) --n;
        }
        query = q.substr(0, n);
    }
    // A request is about to be sent. step 0: a new search (forgets the old answers), +1 next, -1 previous.
    void begin(int step)
    {
        if (step == 0) { steps.clear(); count = -1; more = false; index = 0; }
        steps.push_back(step > 0 ? 1 : step < 0 ? -1 : 0);
    }
    // didFindString. `forQuery` is the string the answer is for: an answer for an older query is ignored.
    Wrap found(const std::string& forQuery, uint32_t matchCount)
    {
        if (!open || forQuery != query) return Wrap::None;
        int step = 0;
        if (!steps.empty()) { step = steps.front(); steps.pop_front(); }
        if (matchCount == kMoreThanMax || matchCount > kMaxMatches) {
            more = true; count = int(kMaxMatches); index = 0;
            return Wrap::None;
        }
        const int n = int(matchCount);
        if (n <= 0) { count = 0; more = false; index = 0; return Wrap::None; }   // (its step is already taken)
        Wrap w = Wrap::None;
        if (step == 0 || more || count != n || index < 1 || index > n) index = 1;
        else if (step > 0) { if (index == n) { index = 1; w = Wrap::ToTop; } else ++index; }
        else { if (index == 1) { index = n; w = Wrap::ToBottom; } else --index; }
        more = false; count = n;
        return n > 1 ? w : Wrap::None;   // "1 of 1" says it all
    }
    // didFailToFindString (WebKit has already cleared the highlights).
    void failed(const std::string& forQuery)
    {
        if (!open || forQuery != query) return;
        if (!steps.empty()) steps.pop_front();
        count = 0; more = false; index = 0;
    }
    // Circle / Escape / the page navigated: the bar goes, the query and the case setting stay for next time.
    void close() { open = false; steps.clear(); count = -1; more = false; index = 0; }
    bool noMatches() const { return open && count == 0; }
};

// The count / position text of the bar.
inline std::string countLabel(const State& s)
{
    if (s.count < 0) return "Searching\xe2\x80\xa6";
    if (s.count == 0) return "No matches";
    if (s.more) return std::to_string(kMaxMatches) + "+ matches";
    return std::to_string(s.index < 1 ? 1 : s.index) + " of " + std::to_string(s.count);
}
inline const char* wrapNotice(Wrap w)
{
    return w == Wrap::ToTop ? "Reached the end of the page \xe2\x80\x94 back to the first match"
         : w == Wrap::ToBottom ? "Reached the top of the page \xe2\x80\x94 back to the last match" : "";
}
inline const char* caseNotice(bool caseSensitive) { return caseSensitive ? "Match case: on" : "Match case: off"; }
inline const char* caseChip() { return "Aa"; }

// The tip under the bar. {Tokens} are expanded by OmniControlsHelp::expand (PlayStation or Xbox names).
inline const char* tipText() { return "{L1} {R1} / D-pad \xe2\x97\x80 \xe2\x96\xb6 previous / next   {Triangle} edit   {Square} match case   {Circle} close"; }

// What a controller button does while the bar is up (the shell maps SDL buttons to these).
enum class Action { None, Next, Previous, Edit, ToggleCase, Close };
enum Button { bDpadLeft, bDpadRight, bL1, bR1, bTriangle, bSquare, bCircle, bOther };
inline Action actionFor(Button b)
{
    switch (b) {
    case bDpadRight: case bR1: return Action::Next;
    case bDpadLeft: case bL1: return Action::Previous;
    case bTriangle: return Action::Edit;
    case bSquare: return Action::ToggleCase;
    case bCircle: return Action::Close;
    default: return Action::None;   // Cross clicks, D-pad up / down scroll, Options opens the menu as usual
    }
}

// Per-tab states, keyed by the tab's address. A new tab erases its key first (an address can be reused), and
// retain() drops the states of tabs that are gone.
inline uintptr_t key(const void* tab) { return reinterpret_cast<uintptr_t>(tab); }
class Store {
public:
    State& at(uintptr_t k) { return m_states[k]; }
    State* find(uintptr_t k) { auto it = m_states.find(k); return it == m_states.end() ? nullptr : &it->second; }
    const State* find(uintptr_t k) const { auto it = m_states.find(k); return it == m_states.end() ? nullptr : &it->second; }
    void erase(uintptr_t k) { m_states.erase(k); }
    void retain(const std::vector<uintptr_t>& alive)
    {
        for (auto it = m_states.begin(); it != m_states.end();) {
            bool keep = false;
            for (uintptr_t a : alive) if (a == it->first) { keep = true; break; }
            it = keep ? std::next(it) : m_states.erase(it);
        }
    }
    size_t size() const { return m_states.size(); }
private:
    std::unordered_map<uintptr_t, State> m_states;
};

// Bar layout (layout px, 1280 wide): [Find][query][Aa][count][<][>][x]
constexpr int kBarX = 616, kBarW = 644, kBarH = 50;
constexpr int kQueryMaxW = 220, kChipX = 300, kChipW = 40, kCountRight = 484;   // offsets from kBarX
enum class Hit { None, Edit, ToggleCase, Previous, Next, Close };
inline Hit hit(int dx, int dy)
{
    if (dx < 0 || dx >= kBarW || dy < 0 || dy >= kBarH) return Hit::None;
    if (dx >= kBarW - 50) return Hit::Close;
    if (dx >= kBarW - 100) return Hit::Next;
    if (dx >= kBarW - 150) return Hit::Previous;
    if (dx >= kChipX - 4 && dx < kChipX + kChipW + 4) return Hit::ToggleCase;
    return Hit::Edit;
}

} // namespace OmniFindPlus
