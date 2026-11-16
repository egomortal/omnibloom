// OMNI_SLEEP_END_V1: tests of the pure part (OmniSleepEnd.h).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_sleep_end.cpp -o t && ./t
#include "OmniSleepEnd.h"
#include <cmath>
#include <cstdio>

namespace SE = OmniSleepEnd;
static int failures = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; std::printf("FAIL line %d: %s\n", __LINE__, #c); } } while (0)

int main()
{
    // actions, cycling
    CHECK(SE::clampAction(7) == SE::kPause && SE::clampAction(-1) == SE::kPause && SE::clampAction(2) == SE::kClose);
    CHECK(SE::cycle(SE::kPause, 1) == SE::kDim && SE::cycle(SE::kDim, 1) == SE::kClose && SE::cycle(SE::kClose, 1) == SE::kPause);
    CHECK(SE::cycle(SE::kPause, -1) == SE::kClose && SE::cycle(SE::kClose, -1) == SE::kDim);
    CHECK(SE::cycle(99, 1) == SE::kDim);

    // settings file
    for (int a = 0; a < SE::kActions; ++a) CHECK(SE::parse(SE::serialize(a)) == a);
    CHECK(SE::serialize(SE::kDim) == "end=dim\n");
    CHECK(SE::parse("") == SE::kPause);
    CHECK(SE::parse("garbage") == SE::kPause);
    CHECK(SE::parse("end=close\r\n") == SE::kClose);
    CHECK(SE::parse("other=1\nend=dim  \n") == SE::kDim);
    CHECK(SE::parse("end=explode\n") == SE::kPause);
    CHECK(SE::parse("end=dim") == SE::kDim);   // no final newline

    // texts
    CHECK(SE::value(SE::kPause) == "Pause playback");
    CHECK(SE::value(SE::kDim) == "Pause and dim the screen");
    CHECK(SE::value(SE::kClose) == "Pause and close Omni");
    CHECK(!SE::detail(SE::kClose).empty() && SE::detail(SE::kClose) != SE::detail(SE::kDim));
    CHECK(SE::closeNotice() == "Sleep timer: closing Omni in 10 s. Press any button to stay");

    // dim matrix: 0.2 x base; identity without a base
    float id[9], out[9];
    SE::dimMatrix(nullptr, id);
    for (int i = 0; i < 9; ++i) CHECK(std::fabs(id[i] - (i % 4 == 0 ? 0.2f : 0.f)) < 1e-6f);
    const float warm[9] = { 1, 0, 0, 0, 0.9f, 0, 0, 0, 0.6f };
    SE::dimMatrix(warm, out);
    CHECK(std::fabs(out[4] - 0.18f) < 1e-6f && std::fabs(out[8] - 0.12f) < 1e-6f && out[1] == 0.f);
    CHECK(std::fabs((256 - SE::kDimDarken) / 256.0 - SE::kDimKeep) < 0.01);   // software dim matches the pass

    // state: pause does nothing more
    SE::State s;
    CHECK(!s.active());
    s.fired(SE::kPause, 1000);
    CHECK(!s.active() && s.wake() == SE::Woke::None);

    // dim: until a button
    s.fired(SE::kDim, 1000);
    CHECK(s.dimmed() && s.active() && !s.closeDue(999999));
    CHECK(s.wake() == SE::Woke::Undimmed && !s.active());
    CHECK(s.wake() == SE::Woke::None);

    // close: 10 s countdown, a button keeps Omni open
    s.fired(SE::kClose, 5000);
    CHECK(s.closing() && s.closeSecondsLeft(5000) == 10 && s.closeSecondsLeft(14001) == 1);
    CHECK(!s.closeDue(14999));
    CHECK(s.wake() == SE::Woke::Stayed && !s.closeDue(20000) && !s.active());
    s.fired(SE::kClose, 5000);
    CHECK(s.closeDue(15000) && !s.active() && !s.closeDue(15001));   // once
    CHECK(s.closeSecondsLeft(15000) == 0);

    // wrap-safe ticks
    s.fired(SE::kClose, 0xFFFFF000u);
    CHECK(!s.closeDue(0xFFFFFFF0u) && !s.closeDue(100) && s.closeDue(0xFFFFF000u + SE::kCloseDelayMs));

    std::printf("%d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
