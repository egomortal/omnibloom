// SPDX-License-Identifier: GPL-3.0-or-later
// OMNI_VIDEO_ENHANCE_V1 host test: OmniGpuVideo.cpp (patched by apply_video_enhance_media.py, built with
// -DOMNI_GPU_VIDEO_HOST_TEST) on lavapipe. Grey test pictures (Cb = Cr = 128), so every output channel is one monotonic
// function of luma and "no ringing" can be checked exactly.
//   1  level 0 is the old nearest-pixel rule: a 2x enlargement repeats each source pixel in 2x2 blocks
//   2  level 1 (Smooth) differs from level 0, keeps the nearest rule's value range around each pixel (no halo / ringing:
//      every output within the min..max of the 4 source pixels around it, +-1 for rounding), and turns the ramp's
//      2-pixel steps into a smoother ramp (more distinct adjacent values)
//   3  level 2 (Sharp) keeps the same clamp and has at least Smooth's edge contrast
//   4  verify() still compares with the old rule while a level is set: the CPU-equivalent reference (level 0 output)
//      verifies 3/3 and the module reports the depth as verified
//   5  1:1 and shrinking are untouched by any level (byte-identical to level 0)
//   6  the setter clamps (-5 -> 0, 9 -> 2)
// Build (WSL): clang++ -std=c++17 -O2 -DOMNI_GPU_VIDEO_HOST_TEST -isystem <Vulkan headers> -I<ews>/engine/media
//   -I<ews>/fetch test_video_enhance.cpp <ews>/engine/media/OmniGpuVideo.cpp -l:libvulkan.so.1 -pthread
// Run: VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.json ./ve   (exit 0 only if every check passes)
#include "OmniGpuVideo.h"
#include <algorithm>
#include <cmath>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <set>
#include <string>
#include <sys/mman.h>
#include <vector>

extern "C" void omni_gpu_video_set_enhance(int level);
extern "C" int omni_gpu_video_get_enhance(void);
extern "C" int omni_gpu_video_test_verified(int bps);
extern "C" void omni_gpu_video_test_reset_verify();

static int fails = 0, passes = 0;
static void check(bool ok, const char* fmt, ...)
{
    va_list ap; va_start(ap, fmt); char b[512]; vsnprintf(b, sizeof b, fmt, ap); va_end(ap);
    printf("%s -> %s\n", b, ok ? "PASS" : "FAIL"); (ok ? passes : fails)++;
}
static std::vector<std::string> notes;
static void note(const char* s) { notes.push_back(s); }

struct Pic { int w = 0, h = 0; std::vector<uint8_t> planes; uint8_t& y(int x, int yy) { return planes[size_t(yy) * w + x]; } };
// Grey picture: a hard vertical edge, a 1-pixel diagonal line, a horizontal ramp and flat areas.
static Pic picture(int w, int h)
{
    Pic p; p.w = w; p.h = h; const int cw = (w + 1) / 2, ch = (h + 1) / 2;
    p.planes.assign(size_t(w) * h + 2 * size_t(cw) * ch + 64, 128);
    for (int yy = 0; yy < h; ++yy) for (int x = 0; x < w; ++x) {
        uint8_t v;
        if (yy < h / 3) v = x < w / 2 ? 40 : 220;                              // hard edge
        else if (yy < 2 * h / 3) v = uint8_t(16 + (x * 219) / (w - 1));        // ramp 16..235
        else v = (x == yy - 2 * h / 3 || x == yy - 2 * h / 3 + 1) ? 235 : 60;  // thin diagonal on flat
        p.y(x, yy) = v;
    }
    return p;
}
struct Layer { uint8_t* px = nullptr; size_t bytes = 0; int w = 0, h = 0, stride = 0; };
static Layer layer(int w, int h)
{
    Layer L; L.w = w; L.h = h; L.stride = (w + 15) / 16 * 16 * 4; L.bytes = size_t(L.stride) * h;
    L.px = static_cast<uint8_t*>(mmap(nullptr, L.bytes, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0)); return L;
}
static void drop(Layer& L) { OmniGpuVideo::forget(L.px); munmap(L.px, L.bytes); L = Layer {}; }
static OmniGpuVideo::Job job(Pic& p, Layer& L)
{
    OmniGpuVideo::Job j; j.planes = p.planes.data(); j.planesBytes = p.planes.size(); j.srcW = p.w; j.srcH = p.h; j.bps = 1;
    j.dst = L.px; j.dstBytes = L.bytes; j.dstW = L.w; j.dstH = L.h; j.dstStride = L.stride; j.matrix = 1; return j;
}
static int g(const Layer& L, int x, int y) { return L.px[size_t(y) * L.stride + size_t(x) * 4 + 1]; }   // green byte
static bool convertAt(Pic& p, Layer& L, int level)
{
    omni_gpu_video_set_enhance(level);
    OmniGpuVideo::Job j = job(p, L); return OmniGpuVideo::convert(j);
}

int main()
{
    OmniGpuVideo::setNote(note);
    if (FILE* f = fopen("gpu-video.flag", "w")) fclose(f);
    if (!OmniGpuVideo::preinit()) { printf("preinit failed: no Vulkan\n"); return 2; }
    const int sw = 480, sh = 270, dw = 960, dh = 540;
    Pic p = picture(sw, sh);
    Layer a = layer(dw, dh), b = layer(dw, dh), c = layer(dw, dh);
    const bool oa = convertAt(p, a, 0), ob = convertAt(p, b, 1), oc = convertAt(p, c, 2);
    check(oa && ob && oc, "1/2/3 the GPU converted the 2x enlargement at levels 0, 1 and 2 (%d %d %d)", oa, ob, oc);

    // 1: level 0 = 2x2 blocks
    long blocks = 0, cells = 0;
    for (int y = 0; y + 1 < dh; y += 2) for (int x = 0; x + 1 < dw; x += 2) {
        ++cells; const int v = g(a, x, y); blocks += v == g(a, x + 1, y) && v == g(a, x, y + 1) && v == g(a, x + 1, y + 1);
    }
    check(blocks == cells, "1 level 0 is the nearest-pixel rule (2x2 blocks: %ld of %ld)", blocks, cells);

    // 2/3: clamp to the min..max of the source pixels around each output pixel (from level 0's blocks), +-1
    auto clampOk = [&](const Layer& L, long& bad) {
        bad = 0;
        for (int y = 0; y < dh; ++y) for (int x = 0; x < dw; ++x) {
            // output pixel centre in source space: (x + 0.5) / 2 - 0.5 -> neighbours floor / floor + 1 (clamped)
            const double sx = (x + 0.5) / 2 - 0.5, sy = (y + 0.5) / 2 - 0.5;
            const int x0 = std::max(0, std::min(sw - 1, int(std::floor(sx)))), x1 = std::min(sw - 1, x0 + 1);
            const int y0 = std::max(0, std::min(sh - 1, int(std::floor(sy)))), y1 = std::min(sh - 1, y0 + 1);
            int lo = 255, hi = 0;
            for (int yy : { y0, y1 }) for (int xx : { x0, x1 }) { const int v = g(a, 2 * xx, 2 * yy); lo = std::min(lo, v); hi = std::max(hi, v); }
            const int v = g(L, x, y); bad += v < lo - 1 || v > hi + 1;
        }
        return bad == 0;
    };
    long badB = 0, badC = 0; const bool cb = clampOk(b, badB), cc = clampOk(c, badC);
    long diffB = 0; for (int y = 0; y < dh; ++y) for (int x = 0; x < dw; ++x) diffB += g(b, x, y) != g(a, x, y);
    check(diffB > 0, "2 Smooth differs from nearest (%ld pixels)", diffB);
    check(cb, "2 Smooth: no ringing / halo (outside the 4 source neighbours: %ld)", badB);
    auto distinctRamp = [&](const Layer& L) { std::set<int> s; const int y = dh / 2; long steps = 0;
        for (int x = 1; x < dw; ++x) steps += g(L, x, y) != g(L, x - 1, y); (void)s; return steps; };
    const long rampA = distinctRamp(a), rampB = distinctRamp(b);
    check(rampB > rampA, "2 Smooth: the ramp is smoother (value changes along a row: nearest %ld, smooth %ld)", rampA, rampB);
    check(cc, "3 Sharp: no ringing / halo (outside the 4 source neighbours: %ld)", badC);
    auto edgeContrast = [&](const Layer& L) { int best = 0; const int y = dh / 6;
        for (int x = 1; x < dw; ++x) best = std::max(best, std::abs(g(L, x, y) - g(L, x - 1, y))); return best; };
    check(edgeContrast(c) >= edgeContrast(b), "3 Sharp: edge step %d >= Smooth's %d", edgeContrast(c), edgeContrast(b));

    // 4: verify keeps the old rule while a level is set (reference = level 0's output, which is the CPU rule)
    omni_gpu_video_test_reset_verify(); omni_gpu_video_set_enhance(2);
    { OmniGpuVideo::Job j = job(p, a); for (int i = 0; i < 3 && omni_gpu_video_test_verified(1) == 0; ++i) OmniGpuVideo::verify(j); }
    std::string last = notes.empty() ? "" : notes.back();
    check(omni_gpu_video_test_verified(1) == 1, "4 verify with Sharp set still matches the nearest rule (verified = %d; %s)", omni_gpu_video_test_verified(1), last.c_str());

    // 5: 1:1 and shrinking are untouched
    for (int k = 0; k < 2; ++k) {
        const int ow = k == 0 ? sw : sw / 2, oh = k == 0 ? sh : sh / 2;
        Layer x0 = layer(ow, oh), x2 = layer(ow, oh);
        convertAt(p, x0, 0); convertAt(p, x2, 2);
        bool same = true; for (int y = 0; y < oh && same; ++y) same = !memcmp(x0.px + size_t(y) * x0.stride, x2.px + size_t(y) * x2.stride, size_t(ow) * 4);
        check(same, "5 %s: Sharp is byte-identical to Off", k == 0 ? "1:1" : "shrink");
        drop(x0); drop(x2);
    }
    // 6: clamping
    omni_gpu_video_set_enhance(-5); const int lo = omni_gpu_video_get_enhance();
    omni_gpu_video_set_enhance(9); const int hi = omni_gpu_video_get_enhance();
    check(lo == 0 && hi == 2, "6 the level is clamped (-5 -> %d, 9 -> %d)", lo, hi);
    omni_gpu_video_set_enhance(0);
    drop(a); drop(b); drop(c);
    omni_gpu_video_shutdown();
    printf("VIDEO ENHANCE TESTS: %d passed, %d failed\n", passes, fails);
    return fails ? 1 : 0;
}
