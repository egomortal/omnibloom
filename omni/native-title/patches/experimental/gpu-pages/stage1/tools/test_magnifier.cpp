// SPDX-License-Identifier: GPL-3.0-or-later
// OMNI_MAGNIFIER_V1: host test of the pure part (engine/entry/OmniMagnifier.h, written by tools/apply_magnifier.py).
// Build: g++ -std=c++17 -Wall -Wextra -I<tree>/engine/entry test_magnifier.cpp && ./a.out
#include "OmniMagnifier.h"
#include <cstdio>
#include <cstring>

static int checks = 0, fails = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL line %d: %s\n", __LINE__, #c); } } while (0)
namespace M = OmniMagnifier;

int main()
{
    // the chord's cycle: off -> 2x -> 3x -> off
    CHECK(M::nextZoom(M::kOff) == 2 && M::nextZoom(2) == 3 && M::nextZoom(3) == M::kOff);
    CHECK(M::nextZoom(-1) == 2 && M::nextZoom(7) == M::kOff);
    int z = M::kOff, seen[3] = {};
    for (int i = 0; i < 9; ++i) { z = M::nextZoom(z); seen[z == 0 ? 0 : z - 1]++; }
    CHECK(seen[0] == 3 && seen[1] == 3 && seen[2] == 3);

    // parameters: fractions of the view (the present multiplies by its canvas size)
    const M::Params p = M::params(2, 640.0f, 360.0f, 1280.0f, 720.0f);
    CHECK(p.p[0] == 0.5f && p.p[1] == 0.5f && p.p[2] == 2.0f);
    CHECK(std::fabs(p.p[3] * 720 - 280) < 1e-3f && std::fabs(p.p[4] * 720 - 110) < 1e-3f);
    CHECK(std::fabs(p.p[5] * 720 - 26) < 1e-3f && std::fabs(p.p[6] * 720 - 4) < 1e-3f && std::fabs(p.p[7] * 720 - 9) < 1e-3f);
    // at 1080p (displayScale 1.5) the canvas is 1920 x 1080: the pointer's canvas pixel = pointerX * 1.5
    const M::Params q = M::params(3, 1000.0f, 100.0f, 1280.0f, 720.0f);
    CHECK(std::fabs(q.p[0] * 1920 - 1000 * 1.5f) < 1e-2f && std::fabs(q.p[1] * 1080 - 100 * 1.5f) < 1e-2f && q.p[2] == 3.0f);
    CHECK(std::fabs(q.p[3] * 1080 - 280 * 1.5f) < 1e-2f);   // the lens scales with the display like the shell's panels
    // clamped: pointer outside the view, zoom out of range, a bad view
    const M::Params c = M::params(9, -50.0f, 9999.0f, 1280.0f, 720.0f);
    CHECK(c.p[0] == 0.0f && c.p[1] == 1.0f && c.p[2] == 3.0f);
    CHECK(M::params(1, 0, 0, 1280, 720).p[2] == 2.0f);
    const M::Params bad = M::params(2, 10, 10, 0, 720);
    CHECK(bad.p[2] == 0.0f && bad.p[3] == 0.0f);
    // same(): a moved pointer is a change, the same pointer is not
    CHECK(M::same(p, M::params(2, 640.0f, 360.0f, 1280.0f, 720.0f)));
    CHECK(!M::same(p, M::params(2, 641.0f, 360.0f, 1280.0f, 720.0f)) && !M::same(p, M::params(3, 640.0f, 360.0f, 1280.0f, 720.0f)));
    // the lens fits the 720-line view with room to move (the present also keeps it on the canvas)
    CHECK(M::kWide.halfW * 2 < 1280 / 2 && M::kWide.halfH * 2 < 720 / 2 && M::kWide.corner < M::kWide.halfH && M::kWide.ring * 2 < M::kWide.corner);

    // shown only when on, not full screen, not the test mode, and the present can draw it
    CHECK(M::shown(2, false, false, true) && M::shown(3, false, false, true));
    CHECK(!M::shown(0, false, false, true) && !M::shown(2, true, false, true) && !M::shown(2, false, true, true) && !M::shown(2, false, false, false));

    // texts
    CHECK(M::notice(0, true) == "Magnifier off");
    CHECK(M::notice(2, true) == "Magnifier 2×  (L2 + L3: 3×, Circle: close)");
    CHECK(M::notice(3, false) == "Magnifier 3×  (LT + LS: off, B: close)");
    CHECK(M::notice(2, true).size() < 60 && M::unavailableNotice().find("GPU display output") != std::string::npos);
    CHECK(M::chordName(true) == "L2 + L3" && M::chordName(false) == "LT + LS");

    std::printf("%s: %d checks, %d failed\n", fails ? "FAILED" : "ok", checks, fails);
    return fails ? 1 : 0;
}
