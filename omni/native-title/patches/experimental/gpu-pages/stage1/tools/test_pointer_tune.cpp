// OMNI_POINTER_TUNE_V1 host tests: g++ -std=c++20 -Wall -Wextra -Werror -I. test_pointer_tune.cpp -o t && ./t
#include "OmniPointerTune.h"
#include <cstdio>
#include <cstring>

namespace OPTN = OmniPointerTune;
static int fails = 0;
#define CHECK(c) do { if (!(c)) { ++fails; std::printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); } } while (0)

int main()
{
    // Normal snap is today's 36 px; table order and names.
    CHECK(OPTN::snapRadius(OPTN::kSnapNormal) == 36.f);
    CHECK(OPTN::snapRadius(OPTN::kSnapLight) == 24.f && OPTN::snapRadius(OPTN::kSnapStrong) == 56.f && OPTN::snapRadius(OPTN::kSnapOff) == 0.f);
    CHECK(OPTN::snapRadius(-5) == 0.f && OPTN::snapRadius(99) == 56.f);
    CHECK(!std::strcmp(OPTN::snapName(2), "Normal (36 px)") && !std::strcmp(OPTN::snapName(0), "Off"));

    // Migration: old files (no snapsize) keep their on / off; Off always wins; garbage strength is Normal.
    CHECK(OPTN::snapLevel(-1, true) == OPTN::kSnapNormal);
    CHECK(OPTN::snapLevel(-1, false) == OPTN::kSnapOff);
    for (int s = -1; s <= 5; ++s) CHECK(OPTN::snapLevel(s, false) == OPTN::kSnapOff);
    CHECK(OPTN::snapLevel(1, true) == 1 && OPTN::snapLevel(3, true) == 3 && OPTN::snapLevel(2, true) == 2);
    CHECK(OPTN::snapLevel(0, true) == OPTN::kSnapNormal && OPTN::snapLevel(7, true) == OPTN::kSnapNormal);
    // Round trip through the file: the snap key (level != 0) plus snapsize gives the level back.
    for (int lv = 0; lv < OPTN::kSnapCount; ++lv) {
        const std::string t = OPTN::saveText(lv, 1);
        const size_t a = t.find("snapsize\t") + 9;
        const int stored = OPTN::parseIndex(t.substr(a, t.find('\n', a) - a), OPTN::kSnapCount, -1);
        CHECK(OPTN::snapLevel(stored, lv != 0) == lv);
    }
    CHECK(OPTN::saveText(2, 1) == "snapsize\t2\nptrcurve\t1\n");
    CHECK(OPTN::saveText(9, -3) == "snapsize\t3\nptrcurve\t0\n");

    // parseIndex
    CHECK(OPTN::parseIndex("2", 3, 1) == 2 && OPTN::parseIndex("3", 3, 1) == 1 && OPTN::parseIndex("", 3, 1) == 1);
    CHECK(OPTN::parseIndex("-1", 4, -1) == -1 && OPTN::parseIndex("1x", 4, -1) == -1 && OPTN::parseIndex("0001", 4, -1) == -1);
    CHECK(OPTN::parseIndex("0", 4, -1) == 0 && OPTN::parseIndex(" 1", 4, -1) == -1);

    // Smooth is bit-identical to the old expression for every m the stick can give.
    for (int i = 0; i <= 32768; ++i) {
        const float m = std::min(1.f, i / 32768.f);
        const float old = 0.05f + 0.95f * std::pow(m, 2.3f);
        const float now = OPTN::curveGain(OPTN::kCurveSmooth, m);
        if (std::memcmp(&old, &now, sizeof(float))) { CHECK(false); break; }
    }
    // Every curve: 0.05 at the dead-zone edge, 1 at full tilt, never decreasing, clamped outside 0..1.
    for (int c = 0; c < OPTN::kCurveCount; ++c) {
        CHECK(std::fabs(OPTN::curveGain(c, 0) - 0.05f) < 1e-6f);
        CHECK(std::fabs(OPTN::curveGain(c, 1) - 1.f) < 1e-6f);
        CHECK(OPTN::curveGain(c, -1) == OPTN::curveGain(c, 0) && OPTN::curveGain(c, 3) == OPTN::curveGain(c, 1));
        float prev = 0;
        for (int i = 0; i <= 1000; ++i) { const float g = OPTN::curveGain(c, i / 1000.f); CHECK(g >= prev); prev = g; }
    }
    // Ordering at half tilt: Smooth (precise) < Linear < Fast.
    CHECK(OPTN::curveGain(OPTN::kCurveSmooth, .5f) < OPTN::curveGain(OPTN::kCurveLinear, .5f));
    CHECK(OPTN::curveGain(OPTN::kCurveLinear, .5f) < OPTN::curveGain(OPTN::kCurveFast, .5f));
    CHECK(std::fabs(OPTN::curveGain(OPTN::kCurveLinear, .5f) - 0.525f) < 1e-6f && std::fabs(OPTN::curveGain(OPTN::kCurveFast, .5f) - 0.7625f) < 1e-6f);
    CHECK(!std::strcmp(OPTN::curveName(1), "Smooth") && !std::strcmp(OPTN::curveName(5), "Fast"));

    // step
    CHECK(OPTN::step(2, 4, 1, false) == 3 && OPTN::step(3, 4, 1, false) == 3 && OPTN::step(0, 4, -1, false) == 0);
    CHECK(OPTN::step(3, 4, 1, true) == 0 && OPTN::step(2, 3, 1, true) == 0 && OPTN::step(-4, 3, 0, true) == 1);

    std::printf(fails ? "%d FAILED\n" : "all pointer tune tests passed\n", fails);
    return fails != 0;
}
