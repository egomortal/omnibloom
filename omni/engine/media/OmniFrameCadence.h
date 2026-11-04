// Bounded timestamp hysteresis for frame selection. SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstddef>
#include <cstdint>

namespace OmniMedia::Hw {
// Millisecond WebM timestamps alternate 16/17 ms for a 60 fps stream. A strict
// nearest-frame threshold repeatedly skips then repeats pictures near a phase
// crossing. Prefer the next picture within 1 ms; skip it only when the following
// picture is more than 1 ms due. This bounds the timing error, not the drop count.
// Calls for one display target share a decision: compose, hand-off and presenter
// must not consume another picture inside the hysteresis band for that target.
class FrameCadence {
    bool selected = false;
    double lastTargetMs = 0;
public:
    static constexpr size_t none = size_t(-1);
    bool diagnosticSelected() const { return selected; }
    double diagnosticTargetMs() const { return lastTargetMs; }
    void reset() { selected = false; }
    template<class Timestamp>
    size_t select(double targetMs, double periodMs, int64_t dueUs, size_t count,
                  Timestamp timestamp, bool poster = false)
    {
        if (!count) return none;
        if (!poster && selected && targetMs <= lastTargetMs + periodMs * 0.5) return none;
        constexpr int64_t toleranceUs = 1000;
        size_t pick = none;
        if (timestamp(0) <= dueUs + toleranceUs) {
            pick = 0;
            while (pick + 1 < count && timestamp(pick + 1) <= dueUs - toleranceUs) ++pick;
        } else if (poster) pick = 0;
        if (pick != none) { selected = true; lastTargetMs = targetMs; }
        return pick;
    }
};
}
