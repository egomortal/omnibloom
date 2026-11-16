// SPDX-License-Identifier: GPL-3.0-or-later
// OMNI_NIGHT_LIGHT_V1 host test of the title side (tools/apply_night_light_present.py): OmniGpuPresent.cpp built with
// OMNI_GPU_PRESENT_HOST_TEST runs the console's recordCompose offscreen on lavapipe; the composed (1:1) output is compared
// with a CPU reference of omni_night_light.comp. Host timings mean nothing here; this checks pixels and object counts.
//   N1 off: the output is the frame exactly (no pass)          N2 a warmth matrix: every pixel = reference (+-1)
//   N3 a full 3x3 matrix (row order)                            N4 GPU hole-punch video runs are tinted too
//   N5 read-back (verify) frames stay untinted and exact        N6 off again: exact; 300 tinted presents: no new objects
// Build (WSL): clang++ -std=c++17 -O2 -Wall -Wextra -DOMNI_GPU_PRESENT_HOST_TEST -isystem <PS5_Mesa/include> -I<src>
//   test_night_light_present.cpp <src>/OmniGpuPresent.cpp -l:libvulkan.so.1 -pthread
// Run: VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.json ./a.out
#include <cmath>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <algorithm>
extern "C" long omni_gpu_present_test(const uint8_t*, int, int, int, const uint8_t*, size_t, int, int, int, int, int, const uint32_t*, size_t, int, int, uint8_t*, int, int*);
extern "C" void omni_gpu_present_test_counts(long*, long*, long*);
extern "C" void omni_gpu_present_test_readback(int on);
extern "C" void omni_gpu_present_test_teardown(long*, long*, long*);
extern "C" int omni_gpu_present_night(const float* m);

static int fails = 0;
static void check(bool ok, const char* name, const char* fmt = "", ...) __attribute__((format(printf, 3, 4)));
static void check(bool ok, const char* name, const char* fmt, ...)
{
    char b[512] = ""; va_list a; va_start(a, fmt); vsnprintf(b, sizeof b, fmt, a); va_end(a);
    printf("%s %s -> %s\n", name, b, ok ? "PASS" : "FAIL"); if (!ok) ++fails;
}
static uint8_t ref(const float* row, const uint8_t* px)
{
    const float v = row[0] * (px[0] / 255.0f) + row[1] * (px[1] / 255.0f) + row[2] * (px[2] / 255.0f);
    return uint8_t(std::lround(std::min(std::max(v, 0.0f), 1.0f) * 255.0f));
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
static std::vector<uint8_t> tinted(const std::vector<uint8_t>& in, const float* m)
{
    std::vector<uint8_t> o(in);
    for (size_t i = 0; i < in.size(); i += 4) { o[i] = ref(m, &in[i]); o[i + 1] = ref(m + 3, &in[i]); o[i + 2] = ref(m + 6, &in[i]); }
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

    // N1: off
    long r = present();
    check(r == 0 && out == frame, "N1", "off: output == frame (r=%ld)", r);
    long b0, i0, m0; omni_gpu_present_test_counts(&b0, &i0, &m0);

    // N2: warmth level 5 gains (OmniNightLight.h kGains[4])
    const float warm[9] = { 1.0f, 0, 0, 0, 0.74f, 0, 0, 0, 0.36f };
    omni_gpu_present_night(warm);
    present();   // the first tinted frame arms the pass; the canvas gets STORAGE usage at the next present
    r = present();
    const int w2 = worst(out, tinted(frame, warm));
    check(r == 0 && w2 >= 0 && w2 <= 1, "N2", "warmth 5: worst channel difference %d (<= 1), alpha exact", w2);
    bool blueDown = true; for (size_t i = 0; i < out.size(); i += 4) if (frame[i + 2] > 8 && out[i + 2] >= frame[i + 2]) blueDown = false;
    check(blueDown, "N2b", "blue reduced on every pixel with blue > 8");

    // N3: a full matrix (catches a transposed upload)
    const float full[9] = { 0.9f, 0.1f, 0.0f, 0.05f, 0.8f, 0.1f, 0.0f, 0.2f, 0.5f };
    omni_gpu_present_night(full);
    r = present();
    const int w3 = worst(out, tinted(frame, full));
    check(r == 0 && w3 >= 0 && w3 <= 1, "N3", "full 3x3: worst %d (<= 1)", w3);

    // N4: video runs from the hole-punch layer (rows 10..19, x 20..69) are tinted with the rest
    std::vector<uint8_t> layer(size_t(W) * H * 4);
    for (size_t i = 0; i < layer.size(); i += 4) { layer[i] = 40; layer[i + 1] = 200; layer[i + 2] = 230; layer[i + 3] = 255; }
    std::vector<uint32_t> runs; for (uint32_t y = 10; y < 20; ++y) { runs.push_back(y); runs.push_back(20); runs.push_back(50); }
    omni_gpu_present_night(warm);
    r = present(layer.data(), layer.size(), &runs);
    std::vector<uint8_t> composed(frame);
    for (int y = 10; y < 20; ++y) memcpy(&composed[(size_t(y) * W + 20) * 4], &layer[(size_t(y) * W + 20) * 4], 50 * 4);
    const int w4 = worst(out, tinted(composed, warm));
    check(r == 0 && w4 >= 0 && w4 <= 1, "N4", "video runs tinted: worst %d (<= 1), video blue %d -> %d", w4, int(layer[2]), int(out[(size_t(12) * W + 30) * 4 + 2]));

    // N5: read-back frames are not tinted (the differential check stays exact)
    omni_gpu_present_test_readback(1);
    r = present();
    check(r == 0 && out == frame, "N5", "verify frame: untinted, differential check %s", r == 0 ? "exact" : "differs");
    omni_gpu_present_test_readback(0);

    // N6: off again, and no per-frame objects while tinting
    omni_gpu_present_night(warm);
    present();
    long b1, i1, m1; omni_gpu_present_test_counts(&b1, &i1, &m1);
    for (int k = 0; k < 300; ++k) { float t = (k % 50) / 50.0f; const float fm[9] = { 1, 0, 0, 0, 1 - 0.26f * t, 0, 0, 0, 1 - 0.64f * t }; omni_gpu_present_night(fm); present(); }
    long b2, i2, m2; omni_gpu_present_test_counts(&b2, &i2, &m2);
    check(b2 == b1 && i2 == i1 && m2 == m1, "N6a", "300 tinted presents (a fade every 50): buffers %ld->%ld images %ld->%ld memory %ld->%ld", b1, b2, i1, i2, m1, m2);
    omni_gpu_present_night(nullptr);
    r = present();
    check(r == 0 && out == frame, "N6b", "off again: output == frame");
    printf("(objects at first off frame: buffers %ld images %ld memory %ld)\n", b0, i0, m0);
    long tb, ti, tm; omni_gpu_present_test_teardown(&tb, &ti, &tm);
    check(tb == 0 && ti == 0 && tm == 0, "N7", "teardown: live buffers %ld images %ld memory %ld", tb, ti, tm);
    printf("%s (%d failed)\n", fails ? "FAIL" : "ALL PASS", fails);
    return fails ? 1 : 0;
}
