// OMNI_OLED_CARE_V1 host test: idle timing, the shift cycle, the canvas row helpers, the clock spot and the wake rules.
//   g++ -std=c++20 -Wall -Wextra -I<tools or engine/entry> test_oled_care.cpp -o t && ./t
#include "OmniOledCare.h"
#include <cstdio>
#include <vector>

namespace O = OmniOledCare;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

static void settings()
{
    O::Settings s;
    CHECK(!s.on && s.dimMinutes == 10);
    s.on = true; s.dimMinutes = 20;
    const O::Settings r = O::parse(O::serialize(s));
    CHECK(r.on && r.dimMinutes == 20);
    const O::Settings bad = O::parse("on\tyes\r\ndim\t7\r\n# x\r\nzzz\r\n");
    CHECK(!bad.on && bad.dimMinutes == 10);
    CHECK(O::parse("on\t1\r\ndim\t5\r\n").on && O::parse("dim\t5\n").dimMinutes == 5);
    CHECK(O::stepDim(5, 1) == 10 && O::stepDim(10, 1) == 20 && O::stepDim(20, 1) == 5);
    CHECK(O::stepDim(5, -1) == 20 && O::stepDim(10, -1) == 5 && O::stepDim(99, 1) == 20);
    O::Settings odd; odd.dimMinutes = 3;
    CHECK(O::serialize(odd).find("dim\t10") != std::string::npos);
    CHECK(O::dimValue(5) == "5 min" && O::dimValue(4) == "10 min");
}

static void idle()
{
    O::Idle i;
    const uint32_t t0 = 1000;
    i.input(t0); i.block(0);
    CHECK(i.fadeK(t0, false) == 256);
    CHECK(i.fadeK(t0 + 19999, false) == 256);
    CHECK(i.fadeK(t0 + 20000, false) == 256);               // the fade starts at 20 s (first step still 256)
    CHECK(i.fadeK(t0 + 20000, true) == O::kFadedK);         // reduce motion: at once
    const uint32_t mid = i.fadeK(t0 + 20000 + O::kFadeMs / 2, false);
    CHECK(mid < 256 && mid > O::kFadedK && mid % O::kKStep == 0);
    CHECK(i.fadeK(t0 + 20000 + O::kFadeMs, false) == O::kFadedK);
    CHECK(i.fadeK(t0 + 3600000, false) == O::kFadedK);
    uint32_t last = 256;                                    // monotonic, never below the floor
    for (uint32_t t = 20000; t <= 20000 + O::kFadeMs + 50; t += 7) { const uint32_t k = i.fadeK(t0 + t, false); CHECK(k <= last && k >= O::kFadedK); last = k; }
    CHECK(O::kFadedK * 100 / 256 >= 14 && O::kFadedK * 100 / 256 <= 16);   // ~15 %
    i.input(t0 + 50000);                                    // input: back at once
    CHECK(i.fadeK(t0 + 50000, false) == 256);
    // wrap of SDL_GetTicks
    O::Idle w; w.input(0xfffff000u); CHECK(w.fadeK(0xfffff000u + 25000u, true) == O::kFadedK);
    // dim: N min without input AND without playback
    O::Idle d; d.input(0); d.block(0);
    CHECK(!d.dimDue(5 * 60000 - 1, 5));
    CHECK(d.dimDue(5 * 60000, 5));
    CHECK(!d.dimDue(5 * 60000, 10) && d.dimDue(20 * 60000, 20));
    d.block(4 * 60000);                                     // a video played until minute 4: the wait restarts there
    CHECK(!d.dimDue(5 * 60000, 5) && !d.dimDue(9 * 60000 - 1, 5) && d.dimDue(9 * 60000, 5));
    d.input(10 * 60000);
    CHECK(!d.dimDue(14 * 60000, 5) && d.dimDue(15 * 60000, 5));
}

static void shift()
{
    int seen[5][5] = {};
    for (int s = 0; s < O::kShiftCycle; ++s) {
        const O::Offset a = O::shiftAt(s), b = O::shiftAt(s + 1);
        CHECK(a.dx >= -O::kShiftMax && a.dx <= O::kShiftMax && a.dy >= -O::kShiftMax && a.dy <= O::kShiftMax);
        CHECK(std::abs(a.dx - b.dx) <= 1 && std::abs(a.dy - b.dy) <= 1);   // slow: 1 px per axis per step (also across the wrap)
        CHECK(a.dx != b.dx || a.dy != b.dy);                                 // it does move every step
        seen[a.dx + 2][a.dy + 2] = 1;
    }
    int n = 0; for (auto& r : seen) for (int v : r) n += v;
    CHECK(n >= 12);                                          // spreads over the +-2 square, not one line
    CHECK(O::shiftAt(0).dx == 0 && O::shiftAt(0).dy == 0);
    CHECK(O::shiftAt(-1).dx == O::shiftAt(O::kShiftCycle - 1).dx && O::shiftAt(O::kShiftCycle).dy == O::shiftAt(0).dy);
    CHECK(O::shiftStep(0) == 0 && O::shiftStep(O::kShiftEveryMs - 1) == 0 && O::shiftStep(O::kShiftEveryMs) == 1);
    CHECK(O::shiftStep(O::kShiftEveryMs * O::kShiftCycle) == 0);
    CHECK(O::toCanvas(2, 3.0) == 6 && O::toCanvas(-2, 3.0) == -6 && O::toCanvas(-1, 1.5) == -2 && O::toCanvas(1, 1.5) == 2 && O::toCanvas(0, 3.0) == 0);
}

static void rows()
{
    const int w = 10, h = 12, stride = 13;
    std::vector<uint32_t> px(size_t(stride) * h, 0xdeadbeefu);
    auto at = [&](int x, int y) -> uint32_t& { return px[size_t(y) * stride + x]; };
    auto fillAll = [&] { for (int y = 0; y < h; ++y) for (int x = 0; x < w; ++x) at(x, y) = uint32_t(y * 100 + x); };
    fillAll();
    O::shiftBand(px.data(), stride, w, h, 0, 2, 3);           // down 2 inside rows [3, 9)
    for (int x = 0; x < w; ++x) {
        CHECK(at(x, 0) == uint32_t(x) && at(x, 2) == uint32_t(200 + x) && at(x, 9) == uint32_t(900 + x) && at(x, 11) == uint32_t(1100 + x)); // outside: kept
        CHECK(at(x, 3) == uint32_t(300 + x) && at(x, 4) == uint32_t(300 + x) && at(x, 5) == uint32_t(300 + x) && at(x, 8) == uint32_t(600 + x));
    }
    CHECK(at(w, 5) == 0xdeadbeefu);                           // the stride padding untouched
    fillAll();
    O::shiftBand(px.data(), stride, w, h, 0, -2, 3);          // up 2
    for (int x = 0; x < w; ++x) CHECK(at(x, 3) == uint32_t(500 + x) && at(x, 6) == uint32_t(800 + x) && at(x, 7) == uint32_t(800 + x) && at(x, 8) == uint32_t(800 + x));
    fillAll();
    O::shiftBand(px.data(), stride, w, h, 2, 0, 3);           // right 2: the left edge repeats
    CHECK(at(0, 4) == 400 && at(1, 4) == 400 && at(2, 4) == 400 && at(3, 4) == 401 && at(9, 4) == 407 && at(0, 2) == 200 && at(2, 2) == 202);
    fillAll();
    O::shiftBand(px.data(), stride, w, h, -2, 1, 3);          // left 2, down 1
    CHECK(at(0, 4) == 302 && at(7, 4) == 309 && at(8, 4) == 309 && at(9, 4) == 309 && at(0, 3) == 302);
    CHECK(at(w, 4) == 0xdeadbeefu);
    fillAll();
    O::shiftBand(px.data(), stride, w, h, 0, 0, 3);           // no shift: nothing
    CHECK(at(4, 4) == 404);
    O::shiftBand(px.data(), stride, w, 4, 0, 2, 3);           // band thinner than the inset: nothing
    CHECK(at(4, 2) == 204);
    // blend: k = 256 keeps, k = 0 is the saved row, all four bytes (premultiplied alpha stays consistent)
    uint32_t d[3] = { 0xffffffffu, 0xff102030u, 0xff0000ffu };
    const uint32_t u[3] = { 0x00000000u, 0x00000000u, 0xff0000ffu };
    O::blendRow(d, u, 3, 256);
    CHECK(d[0] == 0xffffffffu);
    O::blendRow(d, u, 3, O::kFadedK);
    CHECK(((d[0] >> 24) & 255) == ((255 * O::kFadedK) >> 8) && (d[0] & 255) == ((255 * O::kFadedK) >> 8));
    CHECK(d[2] == 0xff0000ffu || d[2] == 0xfe0000feu);       // same colour over itself: (nearly) unchanged
    uint32_t z[1] = { 0x80808080u }; const uint32_t uz[1] = { 0x10203040u };
    O::blendRow(z, uz, 1, 0);
    CHECK(z[0] == 0x10203040u);
    CHECK(O::pointerAlpha(255, 256) == 255 && O::pointerAlpha(255, O::kFadedK) == 38 && O::pointerAlpha(200, 128) == 100 && O::pointerAlpha(0, 128) == 0);
}

static void clock()
{
    for (int m = 0; m < 24 * 60; ++m) {
        const O::Spot s = O::clockSpot(m, 1280, 720, 200, 70);
        CHECK(s.x - 100 >= 40 && s.x + 100 <= 1280 - 40 && s.y - 35 >= 40 && s.y + 35 <= 720 - 40);
    }
    int same = 0;
    for (int m = 0; m < 600; ++m) { const O::Spot a = O::clockSpot(m, 1280, 720, 200, 70), b = O::clockSpot(m + 1, 1280, 720, 200, 70); same += a.x == b.x && a.y == b.y; }
    CHECK(same <= 2);                                        // a new spot (almost) every minute
    const O::Spot tiny = O::clockSpot(5, 100, 100, 200, 70);   // too small a screen: no division by zero
    CHECK(tiny.x >= 0 && tiny.y >= 0);
}

static void wake()
{
    using K = O::Kind;
    O::WakeGate g;
    // not dimmed: nothing swallowed, input counted
    O::Result r = g.handle({ K::Button, 0, 1 }, 10);
    CHECK(!r.swallow && !r.wake && r.input);
    CHECK(!g.handle({ K::Raw }, 10).input && !g.handle({ K::Trigger, 0, 4, 100 }, 10).input && g.handle({ K::Trigger, 0, 4, 20000 }, 10).input);
    CHECK(!g.handle({ K::Other }, 10).swallow);
    // dimmed: the first button wakes, is swallowed, and so is its release
    g.setDimmed(true);
    CHECK(g.handle({ K::Raw }, 20).swallow && g.dimmed());          // raw joystick / sensor noise: swallowed, no wake
    CHECK(g.handle({ K::TouchMotion, 0 }, 20).swallow && g.dimmed());   // touchpad motion: swallowed, no wake
    CHECK(!g.handle({ K::Other }, 20).swallow);                     // window / device events pass
    r = g.handle({ K::Button, 0, 0 }, 30);
    CHECK(r.swallow && r.wake && r.input && !g.dimmed() && g.pending() == 1);
    CHECK(!g.handle({ K::ButtonUp, 1, 0 }, 40).swallow);            // another pad's release passes
    CHECK(!g.handle({ K::ButtonUp, 0, 3 }, 40).swallow);            // another button's release passes
    CHECK(g.handle({ K::ButtonUp, 0, 0 }, 50).swallow && g.pending() == 0);
    CHECK(!g.handle({ K::Button, 0, 0 }, 60).swallow);              // the next press is normal
    CHECK(!g.handle({ K::ButtonUp, 0, 0 }, 70).swallow);
    // a lost release: the same button pressed again is a new press (passes), the pending entry goes
    g.setDimmed(true);
    CHECK(g.handle({ K::Button, 0, 5 }, 100).wake);
    CHECK(!g.handle({ K::Button, 0, 5 }, 200).swallow && g.pending() == 0);
    // keys: the key, its text, its release
    g.setDimmed(true);
    CHECK(g.handle({ K::Key, 0, 40 }, 1000).wake);
    CHECK(g.handle({ K::Text }, 1010).swallow);
    CHECK(!g.handle({ K::Text }, 1020).swallow);                    // only one text
    CHECK(g.handle({ K::KeyUp, 0, 40 }, 1100).swallow && g.pending() == 0);
    g.setDimmed(true);
    CHECK(g.handle({ K::Key, 0, 41 }, 2000).wake);
    CHECK(!g.handle({ K::Text }, 2000 + O::kTextAfterKeyMs + 1).swallow);   // too late: not that key's text
    CHECK(g.handle({ K::KeyUp, 0, 41 }, 2400).swallow);
    // trigger: swallowed until let go
    g.setDimmed(true);
    CHECK(!g.handle({ K::Trigger, 0, 4, 2000 }, 3000).wake && g.dimmed());   // a light touch: swallowed, no wake
    r = g.handle({ K::Trigger, 0, 4, 20000 }, 3010);
    CHECK(r.wake && r.swallow);
    CHECK(g.handle({ K::Trigger, 0, 4, 32767 }, 3020).swallow);
    CHECK(!g.handle({ K::Trigger, 0, 5, 32767 }, 3020).swallow);    // the other trigger passes
    CHECK(g.handle({ K::Trigger, 0, 4, 9000 }, 3030).swallow);
    CHECK(g.handle({ K::Trigger, 0, 4, 1000 }, 3040).swallow && g.pending() == 0);
    CHECK(!g.handle({ K::Trigger, 0, 4, 0 }, 3050).swallow);
    // mouse, touchpad, stick, wheel, motion wake too
    g.setDimmed(true);
    CHECK(g.handle({ K::MouseDown, 0, 1 }, 4000).wake && g.handle({ K::MouseUp, 0, 1 }, 4010).swallow);
    g.setDimmed(true);
    CHECK(g.handle({ K::TouchDown, 0, 2 }, 4100).wake && g.handle({ K::TouchUp, 0, 2 }, 4110).swallow);
    g.setDimmed(true);
    CHECK(g.handle({ K::Stick, 0, 0 }, 4200).wake && g.pending() == 0);
    g.setDimmed(true);
    CHECK(g.handle({ K::Wheel }, 4300).wake);
    g.setDimmed(true);
    CHECK(g.handle({ K::Motion }, 4400).wake);
    // while dimmed, a release of a button pressed before the dim is swallowed (no wake)
    g.setDimmed(true);
    r = g.handle({ K::ButtonUp, 0, 9 }, 4500);
    CHECK(r.swallow && !r.wake && g.dimmed());
    // the pending list is bounded
    O::WakeGate b;
    for (int i = 0; i < 20; ++i) { b.setDimmed(true); b.handle({ K::Button, 0, i }, 5000); }
    CHECK(b.pending() == 8);
}

int main()
{
    settings(); idle(); shift(); rows(); clock(); wake();
    std::printf("%s: %d checks, %d failed\n", fails ? "FAIL" : "PASS", checks, fails);
    return fails ? 1 : 0;
}
