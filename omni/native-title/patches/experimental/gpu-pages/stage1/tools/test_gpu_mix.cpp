// SPDX-License-Identifier: GPL-3.0-or-later
// OMNI_GPU_MIX_V1 host test of the title side (tools/apply_gpu_mix.py): OmniGpuPresent.cpp built with
// OMNI_GPU_PRESENT_HOST_TEST runs the console's recordCompose offscreen on lavapipe, with translucent spans staged as the
// hole-punch stages them (the surface holds the page pixel in canvas byte order there). The composed (1:1) output is
// compared with holeBlendPixel copied verbatim from OmniHwService.cpp (the CPU blend it replaces).
//   G1 spans alone (no runs: a dim layer over the whole video), swapRB (R,G,B,A canvas, the GPU present's): page alphas
//      0/1/127/128/254/255 + random pixels, every span pixel = holeBlendPixel (+-1), everything else = the frame exactly
//   G2 runs + spans, the layer offset and smaller than the canvas (spans clipped to the layer, never into the next row)
//   G3 swapRB off (B,G,R,A canvas): the same arithmetic per byte
//   G4 a verify (read-back) frame: the pass runs and the differential check accepts it (exact outside the spans)
//   G5 spans off again: the frame + runs exactly           G6 > 32768 spans (two dispatch rows)
//   G7 200 presents: no new objects                       G8 teardown: nothing left
//   G9 (V2) the console's partly covering case: layer 3840x2160 at (0,120) under 120 rows of opaque UI, clipped to the canvas
// Build (WSL): clang++ -std=c++20 -O2 -Wall -Wextra -DOMNI_GPU_PRESENT_HOST_TEST -isystem <PS5_Mesa/include> -I<src>
//   test_gpu_mix.cpp <src>/OmniGpuPresent.cpp -l:libvulkan.so.1 -pthread
// Run: VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.json ./a.out
#include <algorithm>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <random>
#include <vector>
extern "C" long omni_gpu_present_test(const uint8_t*, int, int, int, const uint8_t*, size_t, int, int, int, int, int, const uint32_t*, size_t, int, int, uint8_t*, int, int*);
extern "C" void omni_gpu_present_test_counts(long*, long*, long*);
extern "C" void omni_gpu_present_test_readback(int on);
extern "C" void omni_gpu_present_test_teardown(long*, long*, long*);
extern "C" int omni_gpu_present_test_mix(const uint32_t* spans, size_t words);
extern "C" void omni_gpu_present_test_mix_stats(uint64_t* frames, uint64_t* pixels, size_t* spansCap, int* broken);

// ---- verbatim from OmniHwService.cpp (the CPU blend the pass replaces) ----
inline unsigned div255(unsigned x) { x += 128; return (x + (x >> 8)) >> 8; }
uint32_t holeBlendPixel(uint32_t page, const uint8_t* u, bool swapRB)
{
    uint8_t s[4], o[4];
    memcpy(s, &page, 4);
    const int r = swapRB ? 0 : 2, b = swapRB ? 2 : 0;
    const unsigned k = 255 - s[3];
    o[b] = uint8_t(std::min(255u, s[0] + div255(u[b] * k)));
    o[1] = uint8_t(std::min(255u, s[1] + div255(u[1] * k)));
    o[r] = uint8_t(std::min(255u, s[2] + div255(u[r] * k)));
    o[3] = 255;
    uint32_t out; memcpy(&out, o, 4);
    return out;
}
// ----

static int fails = 0;
static void check(bool ok, const char* name, const char* fmt = "", ...) __attribute__((format(printf, 3, 4)));
static void check(bool ok, const char* name, const char* fmt, ...)
{
    char b[640] = ""; va_list a; va_start(a, fmt); vsnprintf(b, sizeof b, fmt, a); va_end(a);
    printf("%s %s -> %s\n", name, b, ok ? "PASS" : "FAIL"); if (!ok) ++fails;
}
struct Diff { int worst = 0; long alphaBad = 0, exact = 0, near = 0, px = 0; };
static Diff compare(const std::vector<uint8_t>& out, const std::vector<uint8_t>& want, const std::vector<uint8_t>& mask, bool inMask)
{
    Diff d;
    for (size_t p = 0; p < out.size() / 4; ++p) {
        if (bool(mask[p]) != inMask) continue;
        d.px++;
        int w = 0;
        for (int c = 0; c < 3; ++c) w = std::max(w, std::abs(int(out[p * 4 + c]) - int(want[p * 4 + c])));
        if (out[p * 4 + 3] != want[p * 4 + 3]) d.alphaBad++;
        d.worst = std::max(d.worst, w);
        (w ? d.near : d.exact)++;
    }
    return d;
}

struct Scene {
    int W, H, lx, ly, lw, lh; bool swapRB;
    std::vector<uint8_t> frame, layer, want, mask;   // mask: 1 = a span pixel
    std::vector<uint32_t> runs, spans;
};
// page pixels (page order B,G,R,A, premultiplied mostly; some channels above alpha to reach the clamp)
static uint32_t pagePixel(std::mt19937& rng, unsigned alpha)
{
    uint8_t p[4];
    for (int c = 0; c < 3; ++c) p[c] = uint8_t(rng() % 5 == 0 ? rng() % 256 : (alpha ? rng() % (alpha + 1) : 0));
    p[3] = uint8_t(alpha);
    uint32_t v; memcpy(&v, p, 4); return v;
}
static void build(Scene& s, uint32_t seed, int spansPerRow, int spanLen, int gap)
{
    std::mt19937 rng(seed);
    const int W = s.W, H = s.H;
    s.frame.assign(size_t(W) * H * 4, 0); s.mask.assign(size_t(W) * H, 0);
    for (size_t i = 0; i < s.frame.size(); i += 4) { s.frame[i] = uint8_t(rng()); s.frame[i + 1] = uint8_t(rng()); s.frame[i + 2] = uint8_t(rng()); s.frame[i + 3] = 255; }
    const int stride = s.lw * 4;
    s.layer.assign(size_t(stride) * s.lh, 0);
    for (size_t i = 0; i < s.layer.size(); i += 4) { s.layer[i] = uint8_t(rng()); s.layer[i + 1] = uint8_t(rng()); s.layer[i + 2] = uint8_t(rng()); s.layer[i + 3] = 255; }
    s.runs.clear(); s.spans.clear();
    s.want = s.frame;
    static const unsigned alphas[] = { 0, 1, 127, 128, 254, 255 };
    unsigned ai = 0;
    for (int y = 0; y < H; ++y) {
        // a run of video (hole) at the row start, inside the layer
        if (y >= s.ly && y < s.ly + s.lh && s.lw > 6) {
            const int x0 = s.lx, n = 4;
            s.runs.push_back(uint32_t(y)); s.runs.push_back(uint32_t(x0)); s.runs.push_back(uint32_t(n));
            memcpy(&s.want[(size_t(y) * W + x0) * 4], &s.layer[size_t(y - s.ly) * stride + size_t(x0 - s.lx) * 4], size_t(n) * 4);
        }
        for (int k = 0; k < spansPerRow; ++k) {
            const int x0 = s.lx + 4 + k * (spanLen + gap);
            if (x0 >= W) break;
            int n = spanLen;
            if (k == spansPerRow - 1 && y % 3 == 0) n = W;   // reaches past the row end: clipped, never into the next row
            s.spans.push_back(uint32_t(y)); s.spans.push_back(uint32_t(x0)); s.spans.push_back(uint32_t(n));
            // what the hole-punch leaves in the surface: the page pixel in canvas order, over the whole recorded span
            const int inRow = std::min(n, W - x0);
            for (int q = 0; q < inRow; ++q) {
                const unsigned a = (ai < 6 * 40) ? alphas[ai % 6] : unsigned(rng() % 256);
                ai++;
                const uint32_t P = pagePixel(rng, a);
                uint8_t pb[4]; memcpy(pb, &P, 4);
                uint8_t* f = &s.frame[(size_t(y) * W + x0 + q) * 4];
                if (s.swapRB) { f[0] = pb[2]; f[1] = pb[1]; f[2] = pb[0]; f[3] = pb[3]; } else memcpy(f, pb, 4);
                memcpy(&s.want[(size_t(y) * W + x0 + q) * 4], f, 4);
                // blended where the span lies inside the layer (as the runs are clipped)
                if (y < s.ly || y >= s.ly + s.lh || x0 + q - s.lx >= s.lw || x0 + q < s.lx) continue;
                const uint32_t o = holeBlendPixel(P, &s.layer[size_t(y - s.ly) * stride + size_t(x0 + q - s.lx) * 4], s.swapRB);
                memcpy(&s.want[(size_t(y) * W + x0 + q) * 4], &o, 4);
                s.mask[size_t(y) * W + x0 + q] = 1;
            }
        }
    }
}
static long present(Scene& s, std::vector<uint8_t>& out, bool withRuns = true)
{
    int released = 0;
    out.assign(s.frame.size(), 0);
    return omni_gpu_present_test(s.frame.data(), s.W * 4, s.W, s.H, s.layer.data(), s.layer.size(), s.lw * 4, s.lx, s.ly, s.lw, s.lh,
                                 withRuns ? s.runs.data() : nullptr, withRuns ? s.runs.size() : 0, s.W, s.H, out.data(), 0, &released);
}

int main()
{
    std::vector<uint8_t> out;
    omni_gpu_present_test_readback(0);   // console frames after the verify frames

    // G1: spans alone, full-size layer, swapRB
    Scene a { 96, 48, 0, 0, 96, 48, true, {}, {}, {}, {}, {}, {} };
    build(a, 1, 6, 9, 3);
    check(omni_gpu_present_test_mix(a.spans.data(), a.spans.size()) == 1, "G0", "the pass sets up on lavapipe");
    // spans alone: the want image has no runs; rebuild without them
    { Scene b = a; b.lw = 96; std::vector<uint8_t> want = b.frame;
      for (size_t p = 0; p < b.mask.size(); ++p) if (b.mask[p]) memcpy(&want[p * 4], &a.want[p * 4], 4);
      long r = present(a, out, false);
      const Diff in = compare(out, want, a.mask, true), outside = compare(out, want, a.mask, false);
      check(r == 0 && in.worst <= 1 && !in.alphaBad && outside.worst == 0 && !outside.alphaBad, "G1",
            "spans only, swapRB: %ld span pixels (%ld exact, %ld off by 1, worst %d, alpha wrong %ld); %ld other pixels worst %d", in.px, in.exact, in.near, in.worst, in.alphaBad, outside.px, outside.worst); }

    // G2: runs + spans, layer offset (8, 4) and 80x40
    Scene c { 96, 48, 8, 4, 80, 40, true, {}, {}, {}, {}, {}, {} };
    build(c, 2, 5, 11, 4);
    omni_gpu_present_test_mix(c.spans.data(), c.spans.size());
    { long r = present(c, out);
      const Diff in = compare(out, c.want, c.mask, true), outside = compare(out, c.want, c.mask, false);
      check(r == 0 && in.px > 0 && in.worst <= 1 && !in.alphaBad && outside.worst == 0 && !outside.alphaBad, "G2",
            "runs + spans, layer at 8,4 80x40: %ld span pixels (%ld exact, worst %d); %ld other pixels (runs, clipped span tails, page) worst %d alpha wrong %ld",
            in.px, in.exact, in.worst, outside.px, outside.worst, outside.alphaBad); }

    // G3: swapRB off (B,G,R,A canvas order)
    Scene d { 96, 48, 0, 0, 96, 48, false, {}, {}, {}, {}, {}, {} };
    build(d, 3, 7, 7, 2);
    omni_gpu_present_test_mix(d.spans.data(), d.spans.size());
    { long r = present(d, out);
      const Diff in = compare(out, d.want, d.mask, true), outside = compare(out, d.want, d.mask, false);
      check(r == 0 && in.worst <= 1 && !in.alphaBad && outside.worst == 0, "G3", "swapRB off: %ld span pixels (%ld exact, worst %d); others worst %d",
            in.px, in.exact, in.worst, outside.worst); }

    // G4: a verify (read-back) frame with spans: the pass runs, the check passes
    omni_gpu_present_test_readback(1);
    omni_gpu_present_test_mix(c.spans.data(), c.spans.size());
    { long r = present(c, out);
      const Diff in = compare(out, c.want, c.mask, true), outside = compare(out, c.want, c.mask, false);
      uint64_t f, px; size_t cap; int broken; omni_gpu_present_test_mix_stats(&f, &px, &cap, &broken);
      check(r == 0 && in.worst <= 1 && outside.worst == 0 && !broken, "G4", "verify frame: differential check %s, span worst %d, others worst %d, pass broken %d",
            r == 0 ? "accepted" : "rejected", in.worst, outside.worst, broken); }
    omni_gpu_present_test_readback(0);

    // G5: spans off again: frame + runs exactly (spans untouched: the surface's page pixels)
    omni_gpu_present_test_mix(nullptr, 0);
    { long r = present(c, out);
      std::vector<uint8_t> want = c.want;
      for (size_t p = 0; p < c.mask.size(); ++p) if (c.mask[p]) memcpy(&want[p * 4], &c.frame[p * 4], 4);
      check(r == 0 && out == want, "G5", "no spans staged: output == frame + runs exactly"); }

    // G6: > 32768 spans (two dispatch rows of workgroups)
    Scene e { 640, 300, 0, 0, 640, 300, true, {}, {}, {}, {}, {}, {} };
    build(e, 6, 150, 2, 2);
    omni_gpu_present_test_mix(e.spans.data(), e.spans.size());
    { long r = present(e, out);
      const Diff in = compare(out, e.want, e.mask, true), outside = compare(out, e.want, e.mask, false);
      check(r == 0 && e.spans.size() / 3 > 32768 && in.worst <= 1 && !in.alphaBad && outside.worst == 0, "G6",
            "%zu spans: %ld span pixels (%ld exact, worst %d); others worst %d", e.spans.size() / 3, in.px, in.exact, in.worst, outside.worst); }

    // G9 (OMNI_GPU_MIX_V2): the console's case: a 3840x2160 layer at (0, 120) under Omni's top bar, clipped to a 3840x2160
    // canvas whose top 120 rows are opaque UI. The hole-punch records rows 120..2159 only (layer rows 0..2039); per row a
    // hole run (video), a long translucent dim span and an opaque control. Spans are in canvas coordinates, the layer is
    // read at (x - 0, y - 120); the UI rows and the layer's 120 bottom rows (outside the canvas) are never touched.
    {
        const int W = 3840, H = 2160, LY = 120, LH = 2160;
        std::mt19937 rng(9);
        std::vector<uint8_t> frame(size_t(W) * H * 4), layer(size_t(W) * LH * 4), want, mask(size_t(W) * H, 0);
        for (size_t i = 0; i < frame.size(); i += 4) { frame[i] = uint8_t(rng()); frame[i + 1] = uint8_t(rng()); frame[i + 2] = uint8_t(rng()); frame[i + 3] = 255; }
        for (size_t i = 0; i < layer.size(); i += 4) { layer[i] = uint8_t(rng()); layer[i + 1] = uint8_t(rng()); layer[i + 2] = uint8_t(rng()); layer[i + 3] = 255; }
        std::vector<uint32_t> runs, spans;
        want = frame;
        for (int y = LY; y < H; ++y) {
            const int holeN = 64 + (y % 7), spanX = holeN, spanN = W - spanX - 200;   // [hole][dim span][opaque control 200 px]
            runs.push_back(uint32_t(y)); runs.push_back(0); runs.push_back(uint32_t(holeN));
            memcpy(&want[size_t(y) * W * 4], &layer[size_t(y - LY) * W * 4], size_t(holeN) * 4);
            spans.push_back(uint32_t(y)); spans.push_back(uint32_t(spanX)); spans.push_back(uint32_t(spanN));
            for (int q = 0; q < spanN; ++q) {
                const int x = spanX + q;
                const unsigned a = (q % 97 == 0) ? unsigned(rng() % 256) : 96u + unsigned(y % 3);   // a dim layer, some odd alphas
                const uint32_t P = pagePixel(rng, a);
                uint8_t pb[4]; memcpy(pb, &P, 4);
                uint8_t* f = &frame[(size_t(y) * W + x) * 4];
                f[0] = pb[2]; f[1] = pb[1]; f[2] = pb[0]; f[3] = pb[3];   // canvas order (R,G,B,A), as the hole-punch writes it
                const uint32_t o = holeBlendPixel(P, &layer[(size_t(y - LY) * W + x) * 4], true);
                memcpy(&want[(size_t(y) * W + x) * 4], &o, 4);
                mask[size_t(y) * W + x] = 1;
            }
        }
        omni_gpu_present_test_mix(spans.data(), spans.size());
        int released = 0; out.assign(frame.size(), 0);
        const long r = omni_gpu_present_test(frame.data(), W * 4, W, H, layer.data(), layer.size(), W * 4, 0, LY, W, LH,
                                             runs.data(), runs.size(), W, H, out.data(), 0, &released);
        const Diff in = compare(out, want, mask, true), outside = compare(out, want, mask, false);
        const bool uiSame = !memcmp(out.data(), frame.data(), size_t(LY) * W * 4);
        check(r == 0 && in.px > 7000000 && in.worst <= 1 && !in.alphaBad && outside.worst == 0 && !outside.alphaBad && uiSame, "G9",
              "layer 3840x2160 at (0,120): %ld span pixels (%ld exact, worst %d, alpha wrong %ld); %ld other pixels (UI rows, runs, controls) worst %d; UI rows untouched %s",
              in.px, in.exact, in.worst, in.alphaBad, outside.px, outside.worst, uiSame ? "yes" : "NO");
    }

    // G7: no per-frame objects
    omni_gpu_present_test_mix(c.spans.data(), c.spans.size());
    present(c, out);
    long b1, i1, m1; omni_gpu_present_test_counts(&b1, &i1, &m1);
    bool allGood = true;
    for (int k = 0; k < 200; ++k) {
        present(c, out);
        if (compare(out, c.want, c.mask, true).worst > 1 || compare(out, c.want, c.mask, false).worst) allGood = false;
    }
    long b2, i2, m2; omni_gpu_present_test_counts(&b2, &i2, &m2);
    uint64_t frames, pixels; size_t cap; int broken; omni_gpu_present_test_mix_stats(&frames, &pixels, &cap, &broken);
    check(allGood && b2 == b1 && i2 == i1 && m2 == m1 && !broken, "G7", "200 presents: all exact-or-1; buffers %ld->%ld images %ld->%ld memory %ld->%ld; %llu GPU-blended frames, span list cap %zu",
          b1, b2, i1, i2, m1, m2, (unsigned long long)frames, cap);

    long tb, ti, tm; omni_gpu_present_test_teardown(&tb, &ti, &tm);
    check(tb == 0 && ti == 0 && tm == 0, "G8", "teardown: live buffers %ld images %ld memory %ld", tb, ti, tm);
    printf("%s (%d failed)\n", fails ? "FAIL" : "ALL PASS", fails);
    return fails ? 1 : 0;
}
