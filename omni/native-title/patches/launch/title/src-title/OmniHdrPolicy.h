// SPDX-License-Identifier: GPL-3.0-or-later
// OMNI_GPU_PRESENT_V4 (omni-native-s3.5-hdr): the HDR output decisions of OmniGpuPresent.cpp as plain functions, so the
// host test runs exactly the logic the console runs (no Vulkan here).
//  - resolveMode(): Omni's HDR setting (Astra's R3-084 Off / Auto / On, /data/omni/video-hdr-preference.txt) decides;
//    without a saved preference, the legacy switches of s3.2 (flag word `hdr` + hdr-auto.flag or hdr-presenter-test.flag
//    = On; flag word `hdrauto` = Auto). An unreadable preference file = Off.
//  - pickHdrFormat(): the 10-bit HDR10 (ST 2084) surface format, A2B10G10R10 first (the format Ex-Box's PPSA99736 showed).
//  - AutoSwitch: Auto = HDR10 output only while an HDR10/HLG video with a PQ layer fills the screen. On after 0.5 s of
//    such frames, off 1.5 s after the last one (no flicker on a short control overlay or a seek).
//  - switchOutput(): a swapchain change with a clean SDR fallback: a refused HDR swapchain is followed at once by an SDR
//    one (Vulkan retires the old swapchain even when the new one fails); only an SDR refusal is fatal.
#pragma once
#include <cstdint>
#include <cstring>
#include <initializer_list>
#include <string>

namespace OmniHdrPolicy {

enum Mode { kOff = 0, kAuto = 1, kOn = 2 };
inline const char* modeName(Mode m) { return m == kOn ? "on" : m == kAuto ? "auto" : "off"; }

struct Inputs {
    bool prefReadable = true, prefExists = false; std::string prefMode = "off";   // OmniHdrPreference::read()
    bool flagHdr = false, flagHdrAuto = false;          // gpu-present.flag words `hdr`, `hdrauto`
    bool legacySetting = false;                         // hdr-auto.flag or hdr-presenter-test.flag
};
inline Mode resolveMode(const Inputs& in, const char** why)
{
    if (!in.prefReadable) { *why = "HDR preference file unreadable: Off"; return kOff; }
    if (in.prefExists) {
        *why = "HDR setting (video-hdr-preference.txt)";
        return in.prefMode == "on" ? kOn : in.prefMode == "auto" ? kAuto : kOff;
    }
    if (in.flagHdrAuto) { *why = "flag word hdrauto (no saved HDR setting)"; return kAuto; }
    if (in.flagHdr && in.legacySetting) { *why = "flag word hdr + hdr-auto.flag / hdr-presenter-test.flag (no saved HDR setting)"; return kOn; }
    *why = in.flagHdr ? "flag word hdr without hdr-auto.flag / hdr-presenter-test.flag: Off" : "no HDR setting saved: Off (default)";
    return kOff;
}

// Vulkan values (checked against the headers in OmniGpuPresent.cpp): A2B10G10R10 64, A2R10G10B10 58, HDR10_ST2084 1000104008.
constexpr uint32_t kA2B10G10R10 = 64, kA2R10G10B10 = 58, kHdr10St2084 = 1000104008u;
inline int pickHdrFormat(const uint32_t* formats, const uint32_t* spaces, size_t n)
{
    for (uint32_t want : { kA2B10G10R10, kA2R10G10B10 })
        for (size_t i = 0; i < n; ++i) if (spaces[i] == kHdr10St2084 && formats[i] == want) return int(i);
    return -1;
}

// The video rectangle fills the screen: at least 90% of the canvas area (fullscreen players letterbox 21:9 films).
inline bool fullscreen(int lx, int ly, int lw, int lh, int cw, int ch)
{
    if (cw <= 0 || ch <= 0 || lw <= 0 || lh <= 0) return false;
    const int64_t x0 = lx < 0 ? 0 : lx, y0 = ly < 0 ? 0 : ly;
    const int64_t x1 = int64_t(lx) + lw > cw ? cw : int64_t(lx) + lw, y1 = int64_t(ly) + lh > ch ? ch : int64_t(ly) + lh;
    if (x1 <= x0 || y1 <= y0) return false;
    return (x1 - x0) * (y1 - y0) * 10 >= int64_t(cw) * ch * 9 || ((x1 - x0) >= cw && (y1 - y0) * 4 >= int64_t(ch) * 3);
}

struct AutoSwitch {
    double onAfterMs = 500, offAfterMs = 1500, gapMs = 300;
    double streakStart = -1, lastEligible = -1;   // -1: none yet
    // Called once per present. +1: switch to HDR now, -1: switch to SDR now, 0: stay.
    int step(double now, bool eligible, bool hdrNow)
    {
        if (eligible) { if (streakStart < 0 || now - lastEligible > gapMs) streakStart = now; lastEligible = now; }
        if (!hdrNow) return eligible && now - streakStart >= onAfterMs ? 1 : 0;
        return (lastEligible < 0 || now - lastEligible >= offAfterMs) ? -1 : 0;
    }
    void reset() { streakStart = lastEligible = -1; }
};

// create(hdr, &retiredOld) makes a swapchain (replacing the current one); it reports through retiredOld whether the old
// swapchain is gone (Vulkan: retired even when the creation fails). Returns: 1 = the wanted output, 0 = SDR instead of a
// refused HDR (refusedHdr set), -1 = no swapchain at all (fatal for the GPU present).
template <class Create> int switchOutput(bool wantHdr, bool haveSwapchain, Create create, bool& refusedHdr, bool& outHdr)
{
    bool retired = false;
    if (create(wantHdr, &retired)) { outHdr = wantHdr; return 1; }
    if (!wantHdr) return -1;
    refusedHdr = true;
    if (haveSwapchain && !retired) { outHdr = false; return 0; }   // the SDR swapchain is still there (forced refusal)
    bool retired2 = false;
    if (create(false, &retired2)) { outHdr = false; return 0; }
    return -1;
}

}  // namespace OmniHdrPolicy
