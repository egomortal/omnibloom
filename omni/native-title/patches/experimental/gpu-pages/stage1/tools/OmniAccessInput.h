// OMNI_ACCESS_INPUT_V1: the pure part of the motor-accessibility input options (no SDL, no WebKit):
//   Browser settings > "Sticky L2"     tap L2 once: it counts as held for the next button (3 s, or a second tap ends it)
//                    > "Hold time"     Short 0.3 s / Normal / Long 0.9 s for every hold (hold Cross, accents, hold Circle ...)
//                    > "Repeat delay"  Normal / Long / Very long / No repeat for the keyboard's hold-to-repeat
// Defaults are exactly today's timings. The shell side is OmniAccessInputShell.h; the reasons are in
// tools/apply_access_input.py. Tested on the host with g++ (tools/test_access_input.cpp).
#pragma once
#include <cstddef>
#include <cstdint>
#include <string>

namespace OmniAccessInput {

constexpr const char* kFileName = "access-input.txt";
constexpr int kRowSticky = 821, kRowHold = 822, kRowRepeat = 823;   // Browser settings rows

// --- hold time --------------------------------------------------------------------------------------------------------
enum class HoldTime : int { Short = 0, Normal = 1, Long = 2 };
constexpr int kHoldTimeCount = 3;
// Every hold detection in the tree, by what it is. normalMs() is today's threshold of each (the constant it replaces).
enum class Hold : int {
    Cross,         // hold Cross over the page / a Tabs panel row: page menu, tab menu (OmniFeatures.h omniFxTick, 500)
    Accent,        // hold Cross on a keyboard letter: the accent popup (OmniKbLayouts.h kHoldMs, 450)
    Circle,        // hold Circle while browsing: Back history (OmniBfList.h kHoldMs, 500)
    AddonToggle,   // hold on the add-ons quick row: on / off everywhere instead of this site (OmniAddons.h, 600)
    StickEnd,      // L2 + right stick still pushed after the page step: to the top / bottom (OmniScrollPlus.h kHoldMs, 600)
    GameExit,      // game mode: Options + Create held to leave (OmniGameMode.h kExitHoldMs, 1000; when built)
    Count
};
constexpr uint32_t kShortMs = 300, kLongMs = 900;
constexpr uint32_t normalMs(Hold k)
{
    switch (k) {
    case Hold::Cross: return 500;
    case Hold::Accent: return 450;
    case Hold::Circle: return 500;
    case Hold::AddonToggle: return 600;
    case Hold::StickEnd: return 600;
    case Hold::GameExit: return 1000;
    default: return 500;
    }
}
// The press-and-hold gestures people aim for get the named times (0.3 s / 0.9 s); the others scale with them
// (x 0.6 / x 1.8). Leaving game mode never gets shorter than today's 1 s (a game is left by accident otherwise).
constexpr uint32_t holdMs(Hold k, HoldTime t)
{
    const uint32_t n = normalMs(k);
    if (t == HoldTime::Normal) return n;
    switch (k) {
    case Hold::Cross: case Hold::Accent: case Hold::Circle: return t == HoldTime::Short ? kShortMs : kLongMs;
    case Hold::GameExit: return t == HoldTime::Short ? n : n * 9 / 5;
    default: return t == HoldTime::Short ? n * 3 / 5 : n * 9 / 5;
    }
}

// A clock for holds whose threshold sits inside another patch's pure struct (Hold::tick, Gesture::update,
// ExitChord::due compare `now - start >= normalMs`): fed this clock instead of SDL_GetTicks(), their own threshold
// is reached after holdMs real milliseconds. 64-bit underneath, so differences stay right across the 49.7-day wrap of
// the 32-bit ticks. At Normal the shell passes SDL_GetTicks() itself (not this): nothing changes by default.
struct Clock {
    bool started = false;
    uint32_t last = 0;
    uint64_t real = 0;
    uint64_t unwrap(uint32_t now)
    {
        if (!started) { started = true; real = now; }
        else real += uint32_t(now - last);
        last = now;
        return real;
    }
};
inline uint32_t scaledClock(uint64_t real, uint32_t normal, uint32_t hold)
{
    if (!hold || hold == normal) return uint32_t(real);
    return uint32_t(real * normal / hold);
}

// --- repeat delay (the keyboard's hold-to-repeat: buttons, L2 / R2 word moves, right-stick caret) ----------------------
enum class Repeat : int { Normal = 0, Long = 1, VeryLong = 2, Off = 3 };
constexpr int kRepeatCount = 4;
enum class Rep : int { First, Rate };   // the wait before the first repeat, the wait between repeats
constexpr uint32_t kNever = 0x3FFFFFFF;  // "No repeat": ~12 days (the shells compare int32_t(now - next) >= 0)
constexpr uint32_t repeatMs(Repeat r, Rep k, uint32_t base)
{
    switch (r) {
    case Repeat::Long: return k == Rep::First ? base * 7 / 4 : base * 3 / 2;     // 380 -> 665 ms, 60 -> 90 ms
    case Repeat::VeryLong: return k == Rep::First ? base * 5 / 2 : base * 2;     // 380 -> 950 ms, 60 -> 120 ms
    case Repeat::Off: return kNever;
    default: return base;
    }
}

// --- Sticky L2 --------------------------------------------------------------------------------------------------------
// L2 is an axis; omniL2Track counts it held at >= 20000 and let go at <= 8000 (OMNI_L2_CHORDS_V1). With Sticky L2 on, a
// plain tap while browsing (no chord used during it) latches: omniL2Held stays true, so every L2 chord sees L2 held,
// until the next button press (that press is the chord), 3 s without one, a second L2 tap, or leaving the browsing
// context. While the quick tab switcher (L2 + R1 / L1) is up, or an L2 + right-stick push is still held, the latch
// waits (and its 3 s start again afterwards).
constexpr int kPress = 20000, kRelease = 8000;   // omniL2Track's thresholds
constexpr uint32_t kLatchMs = 3000;
enum class AxisAct { Pass, Ignore, Latch, Cancel };
enum class End { None, Timeout, Used, Context };
struct Sticky {
    bool latched = false;
    bool pressed = false;   // a button went down while latched
    uint32_t since = 0;
    // Each L2 axis event, before omniL2Track's own handling. held = omniL2Held, chordUsed = omniL2ChordUsed,
    // on = the setting, eligible = browsing context. Pass: omniL2Track goes on as before.
    AxisAct axis(int value, bool held, bool chordUsed, bool on, bool eligible, uint32_t now)
    {
        if (latched) {
            if (value < kPress) return AxisAct::Ignore;   // a resting trigger's small events: still latched
            latched = false; pressed = false;            // the second tap (or a real hold) takes over
            return AxisAct::Cancel;
        }
        if (value <= kRelease && held && on && eligible && !chordUsed) {
            latched = true; pressed = false; since = now;
            return AxisAct::Latch;
        }
        return AxisAct::Pass;
    }
    void button() { if (latched) pressed = true; }
    // Every pass. busy: the tab switcher strip is up or an L2 + stick push is held (the latch waits).
    End tick(uint32_t now, bool on, bool eligible, bool chordUsed, bool busy)
    {
        if (!latched) return End::None;
        if (busy) { since = now; return End::None; }
        const End e = !on || !eligible ? End::Context : chordUsed || pressed ? End::Used
            : uint32_t(now - since) >= kLatchMs ? End::Timeout : End::None;
        if (e != End::None) { latched = false; pressed = false; }
        return e;
    }
    void cancel() { latched = false; pressed = false; }
};
inline const char* endName(End e)
{
    return e == End::Timeout ? "timed out" : e == End::Used ? "used" : e == End::Context ? "left browsing" : "none";
}
inline const char* chipLabel(bool playStation) { return playStation ? "L2" : "LT"; }

// --- settings, access-input.txt ---------------------------------------------------------------------------------------
struct Settings {
    bool stickyL2 = false;
    HoldTime hold = HoldTime::Normal;
    Repeat repeat = Repeat::Normal;
    bool operator==(const Settings& o) const { return stickyL2 == o.stickyL2 && hold == o.hold && repeat == o.repeat; }
};
inline bool isDefault(const Settings& s) { return s == Settings(); }
inline const char* holdWord(HoldTime t) { return t == HoldTime::Short ? "short" : t == HoldTime::Long ? "long" : "normal"; }
inline const char* repeatWord(Repeat r)
{
    return r == Repeat::Long ? "long" : r == Repeat::VeryLong ? "very-long" : r == Repeat::Off ? "off" : "normal";
}
inline std::string serialize(const Settings& s)
{
    return std::string("sticky-l2 ") + (s.stickyL2 ? "on" : "off") + "\nhold-time " + holdWord(s.hold)
        + "\nrepeat-delay " + repeatWord(s.repeat) + "\n";
}
// Unknown lines / values keep the default (a damaged file never changes a timing).
inline Settings parse(const std::string& text)
{
    Settings s;
    size_t pos = 0;
    while (pos < text.size()) {
        size_t end = text.find('\n', pos);
        if (end == std::string::npos) end = text.size();
        std::string line = text.substr(pos, end - pos);
        pos = end + 1;
        while (!line.empty() && (line.back() == '\r' || line.back() == ' ' || line.back() == '\t')) line.pop_back();
        const size_t sp = line.find(' ');
        if (sp == std::string::npos) continue;
        const std::string key = line.substr(0, sp), value = line.substr(sp + 1);
        if (key == "sticky-l2") { if (value == "on") s.stickyL2 = true; else if (value == "off") s.stickyL2 = false; }
        else if (key == "hold-time") {
            for (int i = 0; i < kHoldTimeCount; ++i) if (value == holdWord(HoldTime(i))) s.hold = HoldTime(i);
        } else if (key == "repeat-delay") {
            for (int i = 0; i < kRepeatCount; ++i) if (value == repeatWord(Repeat(i))) s.repeat = Repeat(i);
        }
    }
    return s;
}

// --- rows -------------------------------------------------------------------------------------------------------------
inline int wrap(int v, int n) { return ((v % n) + n) % n; }
// D-pad left / right step (wrapping), Cross steps forward, Triangle (reset) puts the row back to its default.
inline Settings step(Settings s, int rowId, int dir, bool reset)
{
    const Settings d;
    if (rowId == kRowSticky) s.stickyL2 = reset ? d.stickyL2 : !s.stickyL2;
    else if (rowId == kRowHold) s.hold = reset ? d.hold : HoldTime(wrap(int(s.hold) + dir, kHoldTimeCount));
    else if (rowId == kRowRepeat) s.repeat = reset ? d.repeat : Repeat(wrap(int(s.repeat) + dir, kRepeatCount));
    return s;
}
inline const char* rowLabel(int rowId)
{
    return rowId == kRowSticky ? "Sticky L2" : rowId == kRowHold ? "Hold time" : rowId == kRowRepeat ? "Repeat delay" : "";
}
inline const char* holdValue(HoldTime t) { return t == HoldTime::Short ? "Short (0.3 s)" : t == HoldTime::Long ? "Long (0.9 s)" : "Normal"; }
inline const char* repeatValue(Repeat r)
{
    return r == Repeat::Long ? "Long" : r == Repeat::VeryLong ? "Very long" : r == Repeat::Off ? "No repeat" : "Normal";
}
inline std::string rowValue(int rowId, const Settings& s)
{
    if (rowId == kRowSticky) return s.stickyL2 ? "On" : "Off";
    if (rowId == kRowHold) return holdValue(s.hold);
    if (rowId == kRowRepeat) return repeatValue(s.repeat);
    return "";
}
inline const char* rowDetail(int rowId)
{
    if (rowId == kRowSticky) return "Tap L2, then the button: L2 chords without holding (3 s, tap L2 again to cancel)";
    if (rowId == kRowHold) return "How long Cross, Circle and other holds take";
    if (rowId == kRowRepeat) return "Keyboard: wait before a held button repeats";
    return "";
}
inline std::string noticeText(int rowId, const Settings& s)
{
    if (rowId == kRowSticky) return s.stickyL2 ? "Sticky L2 on: tap L2, then the button" : "Sticky L2 off";
    if (rowId == kRowHold) return std::string("Hold time: ") + holdValue(s.hold);
    if (rowId == kRowRepeat) return std::string("Repeat delay: ") + repeatValue(s.repeat);
    return "";
}

} // namespace OmniAccessInput
