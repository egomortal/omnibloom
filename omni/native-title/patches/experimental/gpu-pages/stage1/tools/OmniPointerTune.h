// OMNI_POINTER_TUNE_V1: pointer snap strength and the left stick's speed curve (pure part: no SDL, no WebKit, no I/O).
// Written into engine/entry by tools/apply_pointer_tune.py; tested on the host by tools/test_pointer_tune.cpp.
// Index 2 (snap Normal, 36 px) and curve 1 (Smooth, 0.05 + 0.95 * m^2.3) are exactly what Omni did before.
#pragma once
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <string>

namespace OmniPointerTune {

// --- snap strength ("Pointer snaps to links") ------------------------------------------------------------------------
constexpr int kSnapOff = 0, kSnapLight = 1, kSnapNormal = 2, kSnapStrong = 3, kSnapCount = 4;
inline constexpr float kSnapPx[kSnapCount] = { 0.f, 24.f, 36.f, 56.f };   // search radius in layout px (Normal: the old 36)
inline constexpr const char* kSnapNames[kSnapCount] = { "Off", "Light (24 px)", "Normal (36 px)", "Strong (56 px)" };

// browser-settings.txt keeps "snap\t0|1" (what every older build reads and writes) and adds "snapsize\t<0..3>".
// stored: the snapsize value read (-1 when the file has none: written by an older build); snapOn: the "snap" key.
// Off always wins (an older build that turned snap off drops snapsize anyway); On without a valid strength is Normal.
inline int snapLevel(int stored, bool snapOn)
{
    if (!snapOn) return kSnapOff;
    if (stored >= kSnapLight && stored <= kSnapStrong) return stored;
    return kSnapNormal;
}
inline float snapRadius(int level) { return kSnapPx[std::clamp(level, 0, kSnapCount - 1)]; }
inline const char* snapName(int level) { return kSnapNames[std::clamp(level, 0, kSnapCount - 1)]; }

// --- speed curve ("Pointer speed curve") -----------------------------------------------------------------------------
// m: stick deflection past the dead zone, 0..1. The result multiplies the "Pointer speed" (px/s at full tilt).
// Every curve gives 0.05 at the dead-zone edge and 1 at full tilt, so the dead zone and the top speed stay as set.
//   Linear: straight line.  Smooth: today's (slow and precise near the centre).  Fast: quick from a light push.
constexpr int kCurveLinear = 0, kCurveSmooth = 1, kCurveFast = 2, kCurveCount = 3;
inline constexpr const char* kCurveNames[kCurveCount] = { "Linear", "Smooth", "Fast" };
inline float curveGain(int curve, float m)
{
    m = std::clamp(m, 0.f, 1.f);
    switch (curve) {
    case kCurveLinear: return 0.05f + 0.95f * m;
    case kCurveFast: { const float u = 1 - m; return 0.05f + 0.95f * (1 - u * u); }
    default: return 0.05f + 0.95f * std::pow(m, 2.3f);   // kCurveSmooth: the exact expression used before
    }
}
inline const char* curveName(int curve) { return kCurveNames[std::clamp(curve, 0, kCurveCount - 1)]; }

// --- settings file --------------------------------------------------------------------------------------------------
// A stored index: digits only, in range, else fallback (a damaged value never becomes a surprising choice).
inline int parseIndex(const std::string& v, int count, int fallback)
{
    if (v.empty() || v.size() > 3) return fallback;
    int n = 0;
    for (char c : v) { if (c < '0' || c > '9') return fallback; n = n * 10 + (c - '0'); }
    return n < count ? n : fallback;
}
// The lines appended to browser-settings.txt (after the older keys, so an older build simply ignores them).
inline std::string saveText(int level, int curve)
{
    char b[48];
    snprintf(b, sizeof(b), "snapsize\t%d\nptrcurve\t%d\n", std::clamp(level, 0, kSnapCount - 1), std::clamp(curve, 0, kCurveCount - 1));
    return b;
}
// D-pad left / right step (clamped), Cross cycles, reset gives the default.
inline int step(int value, int count, int dir, bool cycle)
{
    value = std::clamp(value, 0, count - 1);
    if (cycle) return (value + 1) % count;
    return std::clamp(value + dir, 0, count - 1);
}

} // namespace OmniPointerTune
