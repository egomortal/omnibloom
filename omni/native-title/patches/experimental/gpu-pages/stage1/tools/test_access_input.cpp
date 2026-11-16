// OMNI_ACCESS_INPUT_V1 host tests: g++ -std=c++20 -Wall -Wextra -Werror -I<tools> test_access_input.cpp -o t && ./t [<tree>/engine/entry]
// With a patched tree it also checks that the thresholds named in normalMs() are the tree's and that each site is routed.
#include "OmniAccessInput.h"
#include <cstdio>
#include <fstream>
#include <regex>
#include <sstream>
#include <string>

namespace A = OmniAccessInput;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

static std::string readFile(const std::string& p)
{
    std::ifstream f(p, std::ios::binary);
    std::stringstream ss; ss << f.rdbuf();
    return ss.str();
}

static void holdTable()
{
    // Normal = today's values exactly.
    CHECK(A::holdMs(A::Hold::Cross, A::HoldTime::Normal) == 500);
    CHECK(A::holdMs(A::Hold::Accent, A::HoldTime::Normal) == 450);
    CHECK(A::holdMs(A::Hold::Circle, A::HoldTime::Normal) == 500);
    CHECK(A::holdMs(A::Hold::AddonToggle, A::HoldTime::Normal) == 600);
    CHECK(A::holdMs(A::Hold::StickEnd, A::HoldTime::Normal) == 600);
    CHECK(A::holdMs(A::Hold::GameExit, A::HoldTime::Normal) == 1000);
    for (int k = 0; k < int(A::Hold::Count); ++k) CHECK(A::holdMs(A::Hold(k), A::HoldTime::Normal) == A::normalMs(A::Hold(k)));
    // Short / Long: the named times for the aimed-at holds, scaled for the others, game exit never shorter.
    CHECK(A::holdMs(A::Hold::Cross, A::HoldTime::Short) == 300 && A::holdMs(A::Hold::Cross, A::HoldTime::Long) == 900);
    CHECK(A::holdMs(A::Hold::Accent, A::HoldTime::Short) == 300 && A::holdMs(A::Hold::Accent, A::HoldTime::Long) == 900);
    CHECK(A::holdMs(A::Hold::Circle, A::HoldTime::Short) == 300 && A::holdMs(A::Hold::Circle, A::HoldTime::Long) == 900);
    CHECK(A::holdMs(A::Hold::AddonToggle, A::HoldTime::Short) == 360 && A::holdMs(A::Hold::AddonToggle, A::HoldTime::Long) == 1080);
    CHECK(A::holdMs(A::Hold::StickEnd, A::HoldTime::Short) == 360 && A::holdMs(A::Hold::StickEnd, A::HoldTime::Long) == 1080);
    CHECK(A::holdMs(A::Hold::GameExit, A::HoldTime::Short) == 1000 && A::holdMs(A::Hold::GameExit, A::HoldTime::Long) == 1800);
    for (int k = 0; k < int(A::Hold::Count); ++k) {
        CHECK(A::holdMs(A::Hold(k), A::HoldTime::Short) <= A::holdMs(A::Hold(k), A::HoldTime::Normal));
        CHECK(A::holdMs(A::Hold(k), A::HoldTime::Long) > A::holdMs(A::Hold(k), A::HoldTime::Normal));
    }
}

// A struct like OmniBfList::Hold / OmniScrollPlus::Gesture: fires when (now - start) >= normal on the clock it is fed.
static uint32_t firesAfter(uint32_t start32, uint32_t normal, uint32_t hold)
{
    A::Clock c;
    uint32_t t = start32;
    const uint32_t s = A::scaledClock(c.unwrap(t), normal, hold);
    for (uint32_t ms = 0; ms < 10000; ++ms, ++t) {
        const uint32_t now = A::scaledClock(c.unwrap(t), normal, hold);
        if (uint32_t(now - s) >= normal) return ms;
    }
    return 0xFFFFFFFF;
}
static void holdClock()
{
    // Normal: the clock is the ticks themselves.
    A::Clock c;
    CHECK(A::scaledClock(c.unwrap(12345), 500, 500) == 12345);
    CHECK(A::scaledClock(c.unwrap(12400), 500, 500) == 12400);
    // The threshold is met after holdMs real ms (+-1 ms rounding), also across the 32-bit wrap.
    const uint32_t starts[] = { 0u, 1000u, 0xFFFFFF00u, 0xFFFFFFFFu, 0x7FFFFFFFu };
    for (uint32_t st : starts) {
        CHECK(firesAfter(st, 500, 500) == 500);
        const uint32_t s300 = firesAfter(st, 500, 300), s900 = firesAfter(st, 500, 900);
        CHECK(s300 >= 299 && s300 <= 301);   // floor rounding: +-1 ms
        CHECK(s900 >= 899 && s900 <= 901);
        const uint32_t g = firesAfter(st, 1000, 1800);
        CHECK(g >= 1799 && g <= 1801);
        const uint32_t e = firesAfter(st, 600, 360);
        CHECK(e >= 359 && e <= 361);
    }
    // A long uptime (64-bit real time past 2^32 ms): differences still right.
    A::Clock big;
    uint64_t r = 0;
    for (uint64_t i = 0; i <= 0x180000000ull; i += 0x10000000ull) r = big.unwrap(uint32_t(i));
    CHECK(r == 0x180000000ull);
    const uint32_t a = A::scaledClock(r, 500, 900), b = A::scaledClock(big.unwrap(uint32_t(r + 900)), 500, 900);
    CHECK(uint32_t(b - a) == 500);
}

static void repeat()
{
    const uint32_t bases[] = { 380, 400, 60, 90, 150, 110, 70 };
    for (uint32_t b : bases) {
        CHECK(A::repeatMs(A::Repeat::Normal, A::Rep::First, b) == b);
        CHECK(A::repeatMs(A::Repeat::Normal, A::Rep::Rate, b) == b);
        CHECK(A::repeatMs(A::Repeat::Long, A::Rep::First, b) > b);
        CHECK(A::repeatMs(A::Repeat::VeryLong, A::Rep::First, b) > A::repeatMs(A::Repeat::Long, A::Rep::First, b));
        CHECK(A::repeatMs(A::Repeat::Off, A::Rep::First, b) == A::kNever);
    }
    CHECK(A::repeatMs(A::Repeat::Long, A::Rep::First, 380) == 665);
    CHECK(A::repeatMs(A::Repeat::VeryLong, A::Rep::First, 380) == 950);
    CHECK(A::repeatMs(A::Repeat::Long, A::Rep::Rate, 60) == 90);
    CHECK(A::repeatMs(A::Repeat::VeryLong, A::Rep::Rate, 150) == 300);
    // "No repeat" stays in the future for the shells' int32_t(now - next) >= 0 test.
    const uint32_t now = 0xFFFFFF00u, next = now + A::kNever;
    CHECK(int32_t(now - next) < 0);
    CHECK(int32_t(uint32_t(now + 86400000u) - next) < 0);
}

static void sticky()
{
    using AA = A::AxisAct;
    // Off: everything passes (omniL2Track as before).
    {
        A::Sticky s;
        CHECK(s.axis(30000, false, false, false, true, 0) == AA::Pass);
        CHECK(s.axis(0, true, false, false, true, 100) == AA::Pass);
        CHECK(!s.latched);
    }
    // On: a plain tap latches; a resting trigger's events are ignored; the next button ends it as Used.
    {
        A::Sticky s;
        CHECK(s.axis(30000, false, false, true, true, 0) == AA::Pass);      // the press: omniL2Track sets held
        CHECK(s.axis(15000, true, false, true, true, 50) == AA::Pass);      // in between: nothing
        CHECK(s.axis(2000, true, false, true, true, 100) == AA::Latch);
        CHECK(s.latched);
        CHECK(s.axis(500, true, false, true, true, 200) == AA::Ignore);
        CHECK(s.axis(19999, true, false, true, true, 210) == AA::Ignore);
        CHECK(s.tick(1000, true, true, false, false) == A::End::None);
        s.button();
        CHECK(s.tick(1001, true, true, false, false) == A::End::Used);
        CHECK(!s.latched);
    }
    // A chord flag set by a consumer (e.g. L2 + right stick) also ends it.
    {
        A::Sticky s;
        CHECK(s.axis(0, true, false, true, true, 0) == AA::Latch);
        CHECK(s.tick(10, true, true, true, false) == A::End::Used);
    }
    // Timeout: 3 s with nothing.
    {
        A::Sticky s;
        CHECK(s.axis(0, true, false, true, true, 0xFFFFF000u) == AA::Latch);
        CHECK(s.tick(0xFFFFF000u + 2999, true, true, false, false) == A::End::None);
        CHECK(s.tick(0xFFFFF000u + 3000, true, true, false, false) == A::End::Timeout);   // across the wrap
    }
    // Second tap: the press cancels (the release then runs omniL2Track's normal let-go).
    {
        A::Sticky s;
        CHECK(s.axis(0, true, false, true, true, 0) == AA::Latch);
        CHECK(s.axis(25000, true, false, true, true, 500) == AA::Cancel);
        CHECK(!s.latched);
        CHECK(s.axis(0, true, true, true, true, 600) == AA::Pass);         // chordUsed (set on Cancel): no new latch
        CHECK(s.tick(700, true, true, false, false) == A::End::None);
    }
    // A tap that used a chord, outside browsing, or with the setting off: no latch.
    {
        A::Sticky s;
        CHECK(s.axis(0, true, true, true, true, 0) == AA::Pass);
        CHECK(s.axis(0, true, false, true, false, 0) == AA::Pass);
        CHECK(s.axis(0, true, false, false, true, 0) == AA::Pass);
        CHECK(s.axis(0, false, false, true, true, 0) == AA::Pass);            // not held: not a tap
        CHECK(!s.latched);
    }
    // Leaving browsing (keyboard, settings, full screen ...) or turning it off ends the latch at once.
    {
        A::Sticky s;
        CHECK(s.axis(0, true, false, true, true, 0) == AA::Latch);
        CHECK(s.tick(5, true, false, false, false) == A::End::Context);
        CHECK(s.axis(0, true, false, true, true, 10) == AA::Latch);
        CHECK(s.tick(15, false, true, false, false) == A::End::Context);
    }
    // Busy (tab switcher strip up / stick push held): waits, even with presses and past 3 s; then ends as Used.
    {
        A::Sticky s;
        CHECK(s.axis(0, true, false, true, true, 0) == AA::Latch);
        s.button();
        CHECK(s.tick(100, true, false, true, true) == A::End::None);         // strip up: not eligible, but busy
        CHECK(s.tick(9000, true, false, true, true) == A::End::None);
        CHECK(s.latched);
        CHECK(s.tick(9001, true, true, true, false) == A::End::Used);
    }
    // Busy then idle with nothing used: the 3 s start again when it stops being busy.
    {
        A::Sticky s;
        CHECK(s.axis(0, true, false, true, true, 0) == AA::Latch);
        CHECK(s.tick(5000, true, true, false, true) == A::End::None);
        CHECK(s.tick(7999, true, true, false, false) == A::End::None);
        CHECK(s.tick(8000, true, true, false, false) == A::End::Timeout);
    }
    // button() outside a latch does nothing.
    {
        A::Sticky s;
        s.button();
        CHECK(!s.pressed);
        CHECK(s.axis(0, true, false, true, true, 0) == AA::Latch);
        CHECK(!s.pressed);
    }
    CHECK(std::string(A::chipLabel(true)) == "L2" && std::string(A::chipLabel(false)) == "LT");
    CHECK(std::string(A::endName(A::End::Timeout)) == "timed out");
}

static void settings()
{
    const A::Settings d;
    CHECK(!d.stickyL2 && d.hold == A::HoldTime::Normal && d.repeat == A::Repeat::Normal && A::isDefault(d));
    CHECK(A::parse("") == d);
    CHECK(A::parse("garbage\nhold-time huge\nrepeat-delay\n") == d);
    A::Settings s; s.stickyL2 = true; s.hold = A::HoldTime::Long; s.repeat = A::Repeat::VeryLong;
    CHECK(A::parse(A::serialize(s)) == s);
    CHECK(A::serialize(d) == "sticky-l2 off\nhold-time normal\nrepeat-delay normal\n");
    CHECK(A::parse("sticky-l2 on\r\nhold-time short\r\nrepeat-delay off\r\n").stickyL2);
    CHECK(A::parse("sticky-l2 on\r\nhold-time short\r\nrepeat-delay off\r\n").hold == A::HoldTime::Short);
    CHECK(A::parse("sticky-l2 on\r\nhold-time short\r\nrepeat-delay off\r\n").repeat == A::Repeat::Off);
    for (int h = 0; h < A::kHoldTimeCount; ++h)
        for (int r = 0; r < A::kRepeatCount; ++r) {
            A::Settings x; x.hold = A::HoldTime(h); x.repeat = A::Repeat(r); x.stickyL2 = (h + r) % 2;
            CHECK(A::parse(A::serialize(x)) == x);
        }
    // Steps wrap, Triangle resets that row only.
    A::Settings t = A::step(d, A::kRowHold, 1, false);
    CHECK(t.hold == A::HoldTime::Long);
    t = A::step(t, A::kRowHold, 1, false);
    CHECK(t.hold == A::HoldTime::Short);
    t = A::step(t, A::kRowHold, -1, false);
    CHECK(t.hold == A::HoldTime::Long);
    t = A::step(t, A::kRowRepeat, -1, false);
    CHECK(t.repeat == A::Repeat::Off);
    t = A::step(t, A::kRowSticky, 1, false);
    CHECK(t.stickyL2);
    t = A::step(t, A::kRowHold, 0, true);
    CHECK(t.hold == A::HoldTime::Normal && t.repeat == A::Repeat::Off && t.stickyL2);
    t = A::step(t, A::kRowSticky, 1, true);
    CHECK(!t.stickyL2);
    CHECK(A::step(d, 999, 1, false) == d);
    CHECK(A::rowValue(A::kRowSticky, d) == "Off" && A::rowValue(A::kRowHold, d) == "Normal" && A::rowValue(A::kRowRepeat, d) == "Normal");
    CHECK(A::rowValue(A::kRowHold, A::step(d, A::kRowHold, 1, false)) == "Long (0.9 s)");
    CHECK(std::string(A::rowLabel(A::kRowSticky)) == "Sticky L2" && std::string(A::rowLabel(A::kRowRepeat)) == "Repeat delay");
    CHECK(A::noticeText(A::kRowRepeat, t) == "Repeat delay: No repeat");
    CHECK(A::kRowSticky != A::kRowHold && A::kRowHold != A::kRowRepeat);
}

// With the patched tree: the replaced constants are what normalMs() says, and every site goes through OAIN.
static void tree(const std::string& dir)
{
    auto has = [&](const char* file, const char* re) {
        const std::string s = readFile(dir + "/" + file);
        const bool ok = !s.empty() && std::regex_search(s, std::regex(re));
        if (!ok) std::printf("  tree: %s lacks /%s/\n", file, re);
        return ok;
    };
    CHECK(has("OmniKbLayouts.h", "kHoldMs = 450;"));
    CHECK(has("OmniBfList.h", "kHoldMs = 500;"));
    CHECK(has("OmniScrollPlus.h", "kHoldMs = 600;"));
    CHECK(has("OmniFeatures.h", "omniHoldMs\\(OAIN::Hold::Cross\\)"));
    CHECK(has("OmniFeatures.h", "was 500"));
    CHECK(has("OmniBrowser.cpp", "omniHoldMs\\(OAIN::Hold::Accent\\)"));
    CHECK(has("OmniBfListShell.h", "h\\.begin\\(int\\(event\\.which\\), omniHoldClock\\(OAIN::Hold::Circle\\)\\)"));
    CHECK(has("OmniBfListShell.h", "h\\.tick\\(omniHoldClock\\(OAIN::Hold::Circle\\)"));
    CHECK(has("OmniAddons.h", "omniHoldMs\\(OAIN::Hold::AddonToggle\\)"));
    CHECK(has("OmniScrollPlusShell.h", "omniHoldClock\\(OAIN::Hold::StickEnd\\)"));
    CHECK(has("OmniBrowser.cpp", "omniRepeatMs\\(OAIN::Rep::First, 380\\)"));
    CHECK(has("OmniBrowser.cpp", "omniRepeatMs\\(OAIN::Rep::Rate, words \\? 150 : pad \\? 90 : 60\\)"));
    CHECK(has("OmniBrowser.cpp", "omniRepeatMs\\(trigger\\[i\\] \\? OAIN::Rep::Rate : OAIN::Rep::First, trigger\\[i\\] \\? 110 : 400\\)"));
    CHECK(has("OmniBrowser.cpp", "omniRepeatMs\\(dir != stickDir \\? OAIN::Rep::First : OAIN::Rep::Rate, dir != stickDir \\? 380 : 70\\)"));
    CHECK(has("OmniBrowser.cpp", "if \\(omniOainL2Axis\\(event\\)\\) return;"));
    CHECK(has("OmniFeatures.h", "omniOainLatched\\(\\)"));
    CHECK(has("OmniMagnifierShell.h", "omniOainLatched\\(\\)"));
    // No old literal threshold left at the routed sites.
    const std::string f = readFile(dir + "/OmniFeatures.h");
    CHECK(f.find("SDL_GetTicks() - h.start >= 500)") == std::string::npos);
    const std::string b = readFile(dir + "/OmniBrowser.cpp");
    CHECK(b.find("omniKbRepeatNext = SDL_GetTicks() + 380;") == std::string::npos);
    CHECK(b.find("OKBL::holdOpens(omniKbl.pendingSince, SDL_GetTicks())") == std::string::npos);
    const std::string g = readFile(dir + "/OmniGameModeShell.h");
    if (!g.empty()) {
        std::printf("  tree: game mode present\n");
        CHECK(has("OmniGameMode.h", "kExitHoldMs = 1000;"));
        CHECK(g.find("omniGmChord.due(omniHoldClock(OAIN::Hold::GameExit))") != std::string::npos);
    }
}

int main(int argc, char** argv)
{
    holdTable();
    holdClock();
    repeat();
    sticky();
    settings();
    if (argc > 1) tree(argv[1]);
    std::printf("%s: %d checks, %d failed\n", fails ? "FAIL" : "ok", checks, fails);
    return fails ? 1 : 0;
}
