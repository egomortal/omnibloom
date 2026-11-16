// SPDX-License-Identifier: GPL-3.0-or-later
// OMNI_COLOUR_FILTER_V1 host test of the title side (tools/apply_colour_filter_present.py on top of
// apply_night_light_present.py): OmniGpuPresent.cpp built with OMNI_GPU_PRESENT_HOST_TEST runs the console's
// recordCompose offscreen on lavapipe; the composed output is compared with the CPU reference (OmniColourFilter.h).
//   C1 both off: output == frame, NO pass recorded             C2 filter only (Deuteranopia): every pixel = reference (+-1)
//   C3 Night light only: = its 3x3 (offset 0, as before)        C4 both on: ONE pass per frame, = N (F c + f)
//   C5 Invert (the offset path), alone and under Night light    C6 SDR hole-punch video runs are filtered too
//   C7 read-back (verify) frames: unfiltered, no pass           C8 both off again: exact, no pass
//   C9 300 presents cycling every filter x night: no new objects   C10 teardown: nothing left
// Build (WSL): clang++ -std=c++17 -O2 -Wall -Wextra -DOMNI_GPU_PRESENT_HOST_TEST -isystem <PS5_Mesa/include> -I<src>
//   -I<tree>/engine/entry test_colour_filter_present.cpp <src>/OmniGpuPresent.cpp -l:libvulkan.so.1 -pthread
// Run: VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.json ./a.out
#include "OmniColourFilter.h"
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <vector>
extern "C" long omni_gpu_present_test(const uint8_t*, int, int, int, const uint8_t*, size_t, int, int, int, int, int, const uint32_t*, size_t, int, int, uint8_t*, int, int*);
extern "C" void omni_gpu_present_test_counts(long*, long*, long*);
extern "C" void omni_gpu_present_test_readback(int on);
extern "C" void omni_gpu_present_test_teardown(long*, long*, long*);
extern "C" int omni_gpu_present_night(const float* m);
extern "C" int omni_gpu_present_colour_filter(const float* m);
extern "C" long omni_gpu_present_colour_test_passes(void);

namespace CF = OmniColourFilter;
static int fails = 0;
static void check(bool ok, const char* name, const char* fmt = "", ...) __attribute__((format(printf, 3, 4)));
static void check(bool ok, const char* name, const char* fmt, ...)
{
    char b[512] = ""; va_list a; va_start(a, fmt); vsnprintf(b, sizeof b, fmt, a); va_end(a);
    printf("%s %s -> %s\n", name, b, ok ? "PASS" : "FAIL"); if (!ok) ++fails;
}
// out vs expected: per channel |d| <= tol, alpha exact. Returns the worst difference (-1: alpha differs).
static int worst(const std::vector<uint8_t>& out, const std::vector<uint8_t>& want)
{
    int w = 0;
    for (size_t i = 0; i < out.size(); ++i) {
        const int d = std::abs(int(out[i]) - int(want[i]));
        if (i % 4 == 3) { if (d) return -1; continue; }
        w = std::max(w, d);
    }
    return w;
}
static std::vector<uint8_t> filtered(const std::vector<uint8_t>& in, const CF::Affine& a)
{
    std::vector<uint8_t> o(in);
    for (size_t i = 0; i < in.size(); i += 4) CF::applyPixel(a, o[i], o[i + 1], o[i + 2]);
    return o;
}

int main()
{
    const int W = 96, H = 48;
    std::vector<uint8_t> frame(size_t(W) * H * 4), out(frame.size());
    for (int y = 0; y < H; ++y) for (int x = 0; x < W; ++x) {
        uint8_t* p = &frame[(size_t(y) * W + x) * 4];
        p[0] = uint8_t(x * 255 / (W - 1)); p[1] = uint8_t(y * 255 / (H - 1)); p[2] = uint8_t((x * 7 + y * 13) & 255); p[3] = (x + y) % 5 ? 255 : 128;
    }
    auto present = [&](const uint8_t* layer = nullptr, size_t lb = 0, const std::vector<uint32_t>* runs = nullptr) {
        int released = 0;
        return omni_gpu_present_test(frame.data(), W * 4, W, H, layer, lb, W * 4, 0, 0, W, H, runs ? runs->data() : nullptr,
                                     runs ? runs->size() : 0, W, H, out.data(), 0, layer ? &released : nullptr);
    };
    omni_gpu_present_test_readback(0);   // a console frame after the verify frames

    // C1: both off
    long r = 0; bool exact = true;
    for (int k = 0; k < 5; ++k) { r |= present(); exact = exact && out == frame; }
    long passes = omni_gpu_present_colour_test_passes();
    check(r == 0 && exact && passes == 0, "C1", "both off: 5 presents == frame, passes recorded %ld (0)", passes);

    // C2: filter only
    const CF::Affine deut = CF::matrix(CF::kDeuteranopia);
    omni_gpu_present_colour_filter(deut.m);
    present();   // the first filtered frame arms the pass; the canvas gets STORAGE usage at the next present
    long p0 = omni_gpu_present_colour_test_passes();
    r = present();
    long p1 = omni_gpu_present_colour_test_passes();
    const int w2 = worst(out, filtered(frame, deut));
    check(r == 0 && w2 >= 0 && w2 <= 1 && p1 == p0 + 1, "C2", "Deuteranopia only: worst %d (<= 1), alpha exact, %ld pass", w2, p1 - p0);

    // C3: Night light only (the filter off): its 3x3, no offset
    const float warm[9] = { 1.0f, 0, 0, 0, 0.74f, 0, 0, 0, 0.36f };
    omni_gpu_present_colour_filter(nullptr);
    omni_gpu_present_night(warm);
    p0 = omni_gpu_present_colour_test_passes();
    r = present();
    p1 = omni_gpu_present_colour_test_passes();
    const int w3 = worst(out, filtered(frame, CF::compose(warm, CF::identity())));
    check(r == 0 && w3 >= 0 && w3 <= 1 && p1 == p0 + 1, "C3", "Night light only (warmth 5): worst %d (<= 1), %ld pass", w3, p1 - p0);

    // C4: both: one pass, N (F c + f) (a full night matrix catches a transposed composition)
    const float full[9] = { 0.9f, 0.1f, 0.0f, 0.05f, 0.8f, 0.1f, 0.0f, 0.2f, 0.5f };
    omni_gpu_present_night(full);
    omni_gpu_present_colour_filter(deut.m);
    p0 = omni_gpu_present_colour_test_passes();
    r = present();
    p1 = omni_gpu_present_colour_test_passes();
    const int w4 = worst(out, filtered(frame, CF::compose(full, deut)));
    const int w4wrong = worst(out, filtered(filtered(frame, deut), CF::compose(full, CF::identity())));
    check(r == 0 && w4 >= 0 && w4 <= 1 && p1 == p0 + 1, "C4", "both on: worst %d (<= 1) vs N (F c + f), %ld pass (one for both); "
          "vs two clamped passes the worst is %d", w4, p1 - p0, w4wrong);

    // C5: Invert (offset row), alone and under Night light
    const CF::Affine inv = CF::matrix(CF::kInvert);
    omni_gpu_present_night(nullptr);
    omni_gpu_present_colour_filter(inv.m);
    r = present();
    const int w5 = worst(out, filtered(frame, inv));
    omni_gpu_present_night(warm);
    long r5b = present();
    const int w5b = worst(out, filtered(frame, CF::compose(warm, inv)));
    check(r == 0 && r5b == 0 && w5 >= 0 && w5 <= 1 && w5b >= 0 && w5b <= 1, "C5", "Invert: worst %d; Invert under warmth 5: worst %d (<= 1); "
          "black -> %d %d %d", w5, w5b, int(out[(size_t(0) * W + 0) * 4]), int(out[1]), int(out[2]));

    // C6: video runs from the hole-punch layer (rows 10..19, x 20..69) are filtered with the rest
    std::vector<uint8_t> layer(size_t(W) * H * 4);
    for (size_t i = 0; i < layer.size(); i += 4) { layer[i] = 200; layer[i + 1] = 60; layer[i + 2] = 30; layer[i + 3] = 255; }
    std::vector<uint32_t> runs; for (uint32_t y = 10; y < 20; ++y) { runs.push_back(y); runs.push_back(20); runs.push_back(50); }
    const CF::Affine prot = CF::matrix(CF::kProtanopia);
    omni_gpu_present_night(nullptr);
    omni_gpu_present_colour_filter(prot.m);
    r = present(layer.data(), layer.size(), &runs);
    std::vector<uint8_t> composed(frame);
    for (int y = 10; y < 20; ++y) memcpy(&composed[(size_t(y) * W + 20) * 4], &layer[(size_t(y) * W + 20) * 4], 50 * 4);
    const int w6 = worst(out, filtered(composed, prot));
    check(r == 0 && w6 >= 0 && w6 <= 1, "C6", "video runs filtered (Protanopia): worst %d (<= 1), video blue %d -> %d", w6, int(layer[2]),
          int(out[(size_t(12) * W + 30) * 4 + 2]));

    // C7: read-back frames are not filtered and record no pass
    omni_gpu_present_test_readback(1);
    p0 = omni_gpu_present_colour_test_passes();
    r = present();
    p1 = omni_gpu_present_colour_test_passes();
    check(r == 0 && out == frame && p1 == p0, "C7", "verify frame: unfiltered, differential check %s, passes +%ld", r == 0 ? "exact" : "differs", p1 - p0);
    omni_gpu_present_test_readback(0);

    // C9 (before C8, so C8 is the final state): no per-frame objects while switching filters and night matrices
    present();
    long b1, i1, m1; omni_gpu_present_test_counts(&b1, &i1, &m1);
    for (int k = 0; k < 300; ++k) {
        const CF::Filter f = CF::Filter(k % CF::kCount);
        omni_gpu_present_colour_filter(f == CF::kOff ? nullptr : CF::matrix(f).m);
        const float t = (k % 50) / 50.0f; const float fm[9] = { 1, 0, 0, 0, 1 - 0.26f * t, 0, 0, 0, 1 - 0.64f * t };
        omni_gpu_present_night(k % 7 ? fm : nullptr);
        present();
    }
    long b2, i2, m2; omni_gpu_present_test_counts(&b2, &i2, &m2);
    check(b2 == b1 && i2 == i1 && m2 == m1, "C9", "300 presents cycling filters x night: buffers %ld->%ld images %ld->%ld memory %ld->%ld", b1, b2, i1, i2, m1, m2);

    // C8: both off again
    omni_gpu_present_colour_filter(nullptr);
    omni_gpu_present_night(nullptr);
    p0 = omni_gpu_present_colour_test_passes();
    exact = true; r = 0;
    for (int k = 0; k < 5; ++k) { r |= present(); exact = exact && out == frame; }
    p1 = omni_gpu_present_colour_test_passes();
    check(r == 0 && exact && p1 == p0, "C8", "both off again: 5 presents == frame, passes +%ld (0)", p1 - p0);

    long tb, ti, tm; omni_gpu_present_test_teardown(&tb, &ti, &tm);
    check(tb == 0 && ti == 0 && tm == 0, "C10", "teardown: live buffers %ld images %ld memory %ld", tb, ti, tm);
    printf("%s (%d failed)\n", fails ? "FAIL" : "ALL PASS", fails);
    return fails ? 1 : 0;
}
