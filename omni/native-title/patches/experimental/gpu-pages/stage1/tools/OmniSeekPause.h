// OMNI_SEEK_PAUSE_V1: the pure part of two controller comforts (no SDL, no WebKit):
//   E11  hold L1 / R1 in full-screen video: the seek repeats with growing steps (10 s for the first second of the hold,
//        then 30 s, then 1 minute; R2 + L1 / R1 held: 1 minute steps), shown in the video keys OSD (OmniVideoKeys.h).
//   E16  L2 + Options while browsing: pause every playing tab at once ("Paused everything").
// The shell side is OmniSeekPauseShell.h (written by tools/apply_seek_pause.py, which also has the reasons). Tested with
// g++ (tools/test_seek_pause.cpp).
#pragma once
#include <cstdint>
#include <string>
#include "OmniVideoKeys.h"

namespace OmniSeekPause {

namespace V = OmniVideoKeys;

// --- E11: the hold ------------------------------------------------------------------------------------------------
constexpr uint32_t kFirstMs = 500;   // the wait before the first repeat (Repeat delay "Normal"; the shell scales it)
constexpr uint32_t kRateMs = 250;    // the wait between repeats (the shell scales it; one page script in flight at most)
constexpr uint32_t kMidAtMs = 1000;  // from this hold time the step is kMidSeconds
constexpr uint32_t kBigAtMs = 3000;  // from this hold time the step is kBigSeconds
constexpr int kMidSeconds = 30;

// The step of a repeat after the button has been held heldMs. big: the hold began with R2 held (always 1 minute).
inline int stepSeconds(uint32_t heldMs, bool big)
{
    if (big || heldMs >= kBigAtMs) return V::kBigSeconds;
    if (heldMs >= kMidAtMs) return kMidSeconds;
    return V::kShoulderSeconds;
}

// One hold of L1 / R1. Times are SDL ticks (uint32_t, wrap-safe comparisons).
struct Hold {
    bool on = false;
    int dir = 0;          // -1 back (L1), +1 forward (R1)
    bool big = false;     // R2 was held at the press
    uint32_t start = 0;   // the press
    uint32_t next = 0;    // the next repeat is due
    int total = 0;        // seconds moved since the press (the press's own step included)
    uintptr_t tab = 0;    // the tab's media identity at the press

    void begin(uint32_t now, int direction, bool r2, uintptr_t tabId, uint32_t firstMs)
    {
        on = true; dir = direction < 0 ? -1 : 1; big = r2; start = now; next = now + firstMs; tab = tabId;
        total = dir * (r2 ? V::kBigSeconds : V::kShoulderSeconds);
    }
    void stop() { on = false; }
    bool due(uint32_t now) const { return on && int32_t(now - next) >= 0; }
    // The next repeat: its signed step (the total moves with it; the one after is rateMs away).
    int take(uint32_t now, uint32_t rateMs)
    {
        const int s = dir * stepSeconds(now - start, big);
        total += s;
        next = now + rateMs;
        return s;
    }
};

// The press a repeat sends. The 10 s steps without R2 are exactly the video keys' L1 / R1 (YouTube keeps its own j / l
// keys there); 30 s and 1 minute steps are a seek in the page (YouTube: its player's seekTo, as R2 + L1 / R1). A player
// out of reach (another site's frame) still gets j / l for them, so the hold keeps moving it 10 s at a time; with R2
// (the 1 minute chord) it gets nothing, as that chord's press.
inline V::Press repeatPress(int dir, int stepAbs, bool big)
{
    if (!big && stepAbs == V::kShoulderSeconds) return V::plan(dir < 0 ? V::pL1 : V::pR1, false);
    V::Press p;
    p.act = V::kSeek;
    p.amount = dir < 0 ? -stepAbs : stepAbs;
    p.flags = 0;
    p.fallback = big ? V::fbNone : V::fbKey;
    if (!big) p.key = dir < 0 ? V::keyJ() : V::keyL();
    return p;
}

// "+1:40", "-12:05", "+1:02:03": the distance moved so far.
inline std::string totalLabel(int seconds)
{
    const int a = seconds < 0 ? -seconds : seconds;
    return (seconds < 0 ? "-" : "+") + V::clock(double(a));
}
// The OSD title of a repeat: the step, then the total ("+30 s   held: +1:40"). An empty title stays empty.
inline std::string holdTitle(const std::string& step, int total)
{
    if (step.empty()) return step;
    return step + "   held: " + totalLabel(total);
}

// --- E16: pause everything ----------------------------------------------------------------------------------------
constexpr uint32_t kChordGapMs = 800;     // a second chord this soon is ignored (a bouncing press, a double tap)
constexpr uint32_t kCheckAfterMs = 3000;  // then the tabs still playing are counted (as the sleep timer's check)

struct PauseChord {
    bool any = false;
    uint32_t last = 0;
    // true: run it now (and remember when).
    bool fire(uint32_t now)
    {
        if (any && int32_t(now - last) >= 0 && now - last < kChordGapMs) return false;
        any = true; last = now;
        return true;
    }
};

inline const char* pausedNotice() { return "Paused everything"; }
inline const char* nothingNotice() { return "Nothing is playing"; }
inline const char* leftoverNotice() { return "Some media could not be paused (a player from another site)"; }
// The notice right after the chord. playing: tabs WebKit reports as playing audio or video before the scripts ran.
inline const char* chordNotice(int playing) { return playing > 0 ? pausedNotice() : nothingNotice(); }

} // namespace OmniSeekPause
