// SPDX-License-Identifier: GPL-3.0-or-later
// Tests the production shared gate with exact nanosecond arithmetic. Does not
// exercise WebKit event dispatch, SDL device drainage, or renderer scheduling.
#include "../../entry/OmniMSEClock.h"
#include <cassert>
#include <compare>
#include <cstdint>
#include <cstdio>

struct Time {
    int64_t ns;
    bool finite = true;
    bool isFinite() const { return finite; }
    static Time zeroTime() { return { 0 }; }
    auto operator<=>(const Time&) const = default;
    Time operator-(Time other) const { return { ns - other.ns }; }
};

int main()
{
    constexpr Time duration { 4000000000 }, epsilon { 1000 };
    auto report = [&](Time position, bool drained = false) {
        return Omni::mseReportedTime(position, duration, drained, epsilon);
    };
    assert(report({ 2000000000 }).ns == 2000000000); // Ordinary playback.
    assert(report(duration).ns == duration.ns - epsilon.ns);
    assert(report({ duration.ns + 1000000000 }).ns < duration.ns); // Overshoot.
    assert(report({ duration.ns - 1 }).ns < duration.ns); // Rounded near EOF.
    assert(report(duration, true) == duration); // Terminal notification.

    // The caller only declares drained after both queues finish. Pending
    // decoder output and pending audio independently prohibit public EOF.
    for (bool decoderDrained : { false, true }) {
        for (bool audioDrained : { false, true }) {
            bool drained = decoderDrained && audioDrained;
            assert((report(duration, drained) >= duration) == drained);
        }
    }
    // Paused/stalled calls cannot accidentally advance time. Seek-back/reset
    // supplies its new position and clears the terminal state, without history.
    auto beforePause = report(duration);
    assert(report(duration) == beforePause);
    assert(report({ 1000000000 }).ns == 1000000000);
    assert(report(Time::zeroTime()).ns == 0);
    assert(report(duration).ns < duration.ns); // A second playback after seek.
    assert(report(duration, true) == duration);

    // Tiny positive resources remain strictly before EOF; zero/nonfinite
    // resources retain their caller-supplied position rather than underflowing.
    assert(Omni::mseReportedTime(Time { 500 }, Time { 500 }, false, epsilon).ns == 0);
    assert(Omni::mseReportedTime(Time { 0 }, Time { 0 }, false, epsilon).ns == 0);
    assert(Omni::mseReportedTime(Time { 42 }, Time { 0, false }, false, epsilon).ns == 42);
    std::puts("PASS: shared MSE EOF gate: playback, both drains, overshoot, pause, stall, seek, tiny/zero/nonfinite duration");
}
