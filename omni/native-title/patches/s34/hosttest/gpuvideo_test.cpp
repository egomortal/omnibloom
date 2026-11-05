// SPDX-License-Identifier: GPL-3.0-or-later
// omni-native-s3.2-video host test for OMNI_GPU_VIDEO_V2 (OmniGpuVideo.cpp built with OMNI_GPU_VIDEO_HOST_TEST) on a
// software Vulkan ICD (lavapipe/llvmpipe). Host timings are NOT PS5 figures.
//   part A  pixel tests at a 2160 canvas and odd sizes, against two references:
//           (1) the title's CPU path, as holeConvert runs it: swscale at the picture's own size (+ the OMNI_FAST_UPSCALE
//               nearest-pixel enlargement, same integer maths) or swscale's bilinear scaler when shrinking;
//           (2) a CPU model of the shader's own arithmetic (float, same order): the pixel-for-pixel reference.
//   part B  the gap fix: at a 2160 canvas with 1080p video, plan() verifies and then hands the pictures to the GPU.
//   part C  10 000 pictures: no per-picture Vulkan objects (live buffers/memory constant), layer cache bounded,
//           forget() of a layer that is unmapped and mapped again, RSS stable.
//   part D  (omni-video-4k60, OMNI_GPU_VIDEO_V3) pace-queue pictures read IN PLACE (planesPersistent, mmap'd like direct
//           memory): pixel-for-pixel equal to the ring-copy path and to the CPU references at 2160->2160, 1080->2160,
//           1440->2160 (8-bit and 10-bit); in-place count up, ring copies 0.
//   part E  10 000 pictures through a 16-buffer rotating "pace queue" (buffers freed and mapped again, forget() first, as
//           PaceAlloc does): no per-picture Vulkan objects after warm-up, picture cache bounded, RSS stable, 0 ring copies.
//   part S  (binary built with OmniGpuPresent.cpp, -DOMNI_SHARED_TEST) the present's device is SHARED: no second device,
//           conversions and presents interleaved on one queue, the present's teardown shuts the video down first.
// Usage: gpuvideo_test [A|B|C|D|E|S|all]   (fallback test: run with VK_ICD_FILENAMES=/nonexistent and argument F)
#include "OmniGpuVideo.h"
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <sys/mman.h>
#include <unistd.h>
#include <vector>
#include <algorithm>
#include <atomic>
#include <thread>
extern "C" {
#include <libswscale/swscale.h>
#include <libavutil/pixfmt.h>
}
extern "C" void omni_gpu_video_test_live(long* buffers, long* memory, size_t* cached);
static bool quiet = false;
static void note(const char* s) { if (!quiet) printf("  [note] %s\n", s); }

struct Pic { int w, h, bps; std::vector<uint8_t> planes; };
static Pic makePic(int w, int h, int bps, unsigned seed)
{
    Pic p { w, h, bps, {} };
    const int cw = (w + 1) / 2, ch = (h + 1) / 2;
    p.planes.assign((size_t(w) * h + 2 * size_t(cw) * ch) * bps + 64, 0);
    auto put = [&](size_t i, int v) { if (bps == 2) reinterpret_cast<uint16_t*>(p.planes.data())[i] = uint16_t(v); else p.planes[i] = uint8_t(v); };
    const int maxv = bps == 2 ? 1023 : 255;
    srand(seed);
    for (int y = 0; y < h; ++y) for (int x = 0; x < w; ++x) {   // gradients + hard-edged bars + noise (video-like and worst-case edges)
        double v = 0.5 + 0.35 * sin(x * 0.013) * cos(y * 0.011) + ((x / 97 + y / 61) % 2 ? 0.08 : -0.08) + (rand() % 7 - 3) / 255.0;
        put(size_t(y) * w + x, int(std::lround(std::fmin(std::fmax(v, 0.0), 1.0) * maxv * 0.86 + maxv * 0.0627)));
    }
    const size_t yn = size_t(w) * h, cn = size_t(cw) * ch;
    for (int y = 0; y < ch; ++y) for (int x = 0; x < cw; ++x) {
        double u = 0.5 + 0.3 * sin(x * 0.02 + y * 0.01), v = 0.5 + 0.3 * cos(x * 0.015 - y * 0.02);
        if ((x / 40) % 5 == 0) { u = 0.2; v = 0.85; }
        put(yn + size_t(y) * cw + x, int(std::lround(u * maxv))); put(yn + cn + size_t(y) * cw + x, int(std::lround(v * maxv)));
    }
    return p;
}
struct Layer { uint8_t* px = nullptr; size_t bytes = 0; int w = 0, h = 0, stride = 0; };
static Layer makeLayer(int w, int h)   // as HoleLayer: rows of whole 16-pixel groups, mmap'd (CpuPixelBuffer)
{
    Layer L; L.w = w; L.h = h; L.stride = (w + 15) / 16 * 16 * 4; L.bytes = size_t(L.stride) * h;
    L.px = static_cast<uint8_t*>(mmap(nullptr, L.bytes, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0));
    return L;
}
static void freeLayer(Layer& L) { OmniGpuVideo::forget(L.px); munmap(L.px, L.bytes); L = Layer {}; }
// V3: a picture buffer as the pace queue holds it (its own page-aligned mapping, freed only after forget()).
struct Mapped { uint8_t* p = nullptr; size_t bytes = 0; };
static Mapped mapCopy(const Pic& pic)
{
    Mapped m; m.bytes = (pic.planes.size() + 0x3fff) & ~size_t(0x3fff);
    m.p = static_cast<uint8_t*>(mmap(nullptr, m.bytes, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0));
    memcpy(m.p, pic.planes.data(), pic.planes.size());
    return m;
}
static void unmapCopy(Mapped& m) { OmniGpuVideo::forget(m.p); munmap(m.p, m.bytes); m = Mapped {}; }
static OmniGpuVideo::Job job(const Pic& p, const Layer& L, int matrix, bool full, bool swap)
{
    OmniGpuVideo::Job j; j.planes = p.planes.data(); j.planesBytes = p.planes.size(); j.srcW = p.w; j.srcH = p.h; j.bps = p.bps;
    j.dst = L.px; j.dstBytes = L.bytes; j.dstW = L.w; j.dstH = L.h; j.dstStride = L.stride; j.swapRB = swap; j.matrix = matrix; j.fullRange = full;
    return j;
}
// Reference (1): the title's CPU conversion rules (OmniHwService.cpp holeConvert / omniConvertIntegerUpscale).
static void cpuTitle(const Pic& p, const Layer& L, int matrix, bool full, bool swap)
{
    const int cw = (p.w + 1) / 2, ch = (p.h + 1) / 2, bps = p.bps;
    const int srcFormat = bps == 2 ? AV_PIX_FMT_YUV420P10LE : AV_PIX_FMT_YUV420P, dstFormat = swap ? AV_PIX_FMT_RGBA : AV_PIX_FMT_BGRA;
    const uint8_t* yp = p.planes.data(); const uint8_t* up = yp + size_t(p.w) * p.h * bps;
    const uint8_t* src[4] = { yp, up, up + size_t(cw) * ch * bps, nullptr };
    int srcStride[4] = { p.w * bps, cw * bps, cw * bps, 0 };
    const bool enlarge = L.w >= p.w && L.h >= p.h && (L.w > p.w || L.h > p.h);
    const int ow = enlarge ? p.w : L.w, oh = enlarge ? p.h : L.h;
    const int sstride = enlarge ? (p.w + 15) / 16 * 16 * 4 : L.stride;
    std::vector<uint8_t> mid(enlarge ? size_t(sstride) * p.h : 0);
    SwsContext* s = sws_getContext(p.w, p.h, AVPixelFormat(srcFormat), ow, oh, AVPixelFormat(dstFormat), SWS_BILINEAR, nullptr, nullptr, nullptr);
    sws_setColorspaceDetails(s, sws_getCoefficients(matrix), full, sws_getCoefficients(SWS_CS_DEFAULT), 1, 0, 1 << 16, 1 << 16);
    uint8_t* dst[4] = { enlarge ? mid.data() : L.px, nullptr, nullptr, nullptr }; int dstStride[4] = { sstride, 0, 0, 0 };
    sws_scale(s, src, srcStride, 0, p.h, dst, dstStride); sws_freeContext(s);
    if (!enlarge) return;
    for (int y = 0; y < L.h; ++y) {   // OMNI_FAST_UPSCALE: centre-aligned source pixel, integer maths
        const int sy = std::min(p.h - 1, int((int64_t(2 * y + 1) * p.h) / (2 * L.h)));
        const uint32_t* srow = reinterpret_cast<const uint32_t*>(mid.data() + size_t(sy) * sstride);
        uint32_t* d = reinterpret_cast<uint32_t*>(L.px + size_t(y) * L.stride);
        for (int x = 0; x < L.w; ++x) d[x] = srow[std::min(p.w - 1, int((int64_t(2 * x + 1) * p.w) / (2 * L.w)))];
    }
}
// Reference (2): the shader's arithmetic on the CPU (omni_yuv_to_rgb.comp), float in the same order.
static void cpuShader(const Pic& p, const Layer& L, int matrix, bool full, bool swap)
{
    double kr = 0.299, kb = 0.114;
    if (matrix == 1) { kr = 0.2126; kb = 0.0722; } else if (matrix == 9 || matrix == 10) { kr = 0.2627; kb = 0.0593; }
    const double kg = 1 - kr - kb, maxv = p.bps == 2 ? 1023.0 : 255.0, k = p.bps == 2 ? 4.0 : 1.0;
    const float yOff = full ? 0.f : float(16 * k), yMul = float(full ? 1.0 / maxv : 1.0 / (219 * k)), cMul = float(full ? 1.0 / maxv : 1.0 / (224 * k)), cMid = float(128 * k);
    const float crR = float(2 * (1 - kr)), cbB = float(2 * (1 - kb)), cbG = float(2 * kb * (1 - kb) / kg), crG = float(2 * kr * (1 - kr) / kg);
    const int cw = (p.w + 1) / 2, ch = (p.h + 1) / 2;
    auto at = [&](size_t base, int w, int h, int x, int y) -> float {
        x = std::clamp(x, 0, w - 1); y = std::clamp(y, 0, h - 1);
        return p.bps == 2 ? float(reinterpret_cast<const uint16_t*>(p.planes.data())[base + size_t(y) * w + x]) : float(p.planes[base + size_t(y) * w + x]);
    };
    const size_t yb = 0, ub = size_t(p.w) * p.h, vb = ub + size_t(cw) * ch;
    const bool enlarge = L.w >= p.w && L.h >= p.h && (L.w > p.w || L.h > p.h);
    for (int oy = 0; oy < L.h; ++oy) for (int ox = 0; ox < L.w; ++ox) {
        float Y = 0, U = 0, V = 0; int nx = 1, ny = 1;
        if ((p.w == L.w && p.h == L.h) || enlarge) {
            int sx = ox, sy = oy;
            if (enlarge) { sx = std::min(p.w - 1, ((2 * ox + 1) * p.w) / (2 * L.w)); sy = std::min(p.h - 1, ((2 * oy + 1) * p.h) / (2 * L.h)); }
            Y = at(yb, p.w, p.h, sx, sy); U = at(ub, cw, ch, sx >> 1, sy >> 1); V = at(vb, cw, ch, sx >> 1, sy >> 1);
        } else {
            const float rx = float(p.w) / float(L.w), ry = float(p.h) / float(L.h);
            nx = std::clamp(int(std::ceil(rx - 0.01f)), 1, 4); ny = std::clamp(int(std::ceil(ry - 0.01f)), 1, 4);
            auto bil = [&](size_t base, int w, int h, float px, float py) {
                const float fx = std::floor(px), fy = std::floor(py), tx = px - fx, ty = py - fy; const int x0 = int(fx), y0 = int(fy);
                const float a = at(base, w, h, x0, y0), b = at(base, w, h, x0 + 1, y0), c = at(base, w, h, x0, y0 + 1), d = at(base, w, h, x0 + 1, y0 + 1);
                const float top = a + (b - a) * tx, bot = c + (d - c) * tx; return top + (bot - top) * ty;
            };
            for (int j = 0; j < ny; ++j) for (int i = 0; i < nx; ++i) {
                const float subx = (float(i) + 0.5f) / float(nx), suby = (float(j) + 0.5f) / float(ny);
                const float lx = (float(ox) + subx) * rx - 0.5f, ly = (float(oy) + suby) * ry - 0.5f;
                const float cx = (lx + 0.5f) * 0.5f - 0.5f, cy = (ly + 0.5f) * 0.5f - 0.5f;
                Y += bil(yb, p.w, p.h, lx, ly); U += bil(ub, cw, ch, cx, cy); V += bil(vb, cw, ch, cx, cy);
            }
        }
        const float inv = 1.0f / float(nx * ny);
        const float yy = (Y * inv - yOff) * yMul, cb = (U * inv - cMid) * cMul, cr = (V * inv - cMid) * cMul;
        float rgb[3] = { yy + crR * cr, yy - cbG * cb - crG * cr, yy + cbB * cb };
        unsigned q[3]; for (int c = 0; c < 3; ++c) q[c] = unsigned(std::clamp(rgb[c], 0.f, 1.f) * 255.0f + 0.5f);
        uint8_t* d = L.px + size_t(oy) * L.stride + size_t(ox) * 4;
        if (swap) { d[0] = uint8_t(q[0]); d[1] = uint8_t(q[1]); d[2] = uint8_t(q[2]); } else { d[0] = uint8_t(q[2]); d[1] = uint8_t(q[1]); d[2] = uint8_t(q[0]); }
        d[3] = 255;
    }
}
struct Diff { double mean = 0, p12 = 0, exact = 0; int worst = 0; };
static Diff diff(const Layer& a, const Layer& b)
{
    Diff d; uint64_t sum = 0, over12 = 0, same = 0, n = 0;
    for (int y = 0; y < a.h; ++y) for (int x = 0; x < a.w; ++x) {
        const uint8_t* p = a.px + size_t(y) * a.stride + size_t(x) * 4; const uint8_t* q = b.px + size_t(y) * b.stride + size_t(x) * 4;
        bool eq = true;
        for (int c = 0; c < 4; ++c) { const int e = std::abs(int(p[c]) - int(q[c])); sum += unsigned(e); over12 += e > 12; d.worst = std::max(d.worst, e); eq &= e == 0; n++; }
        same += eq;
    }
    d.mean = double(sum) / double(n); d.p12 = 100.0 * double(over12) / double(n); d.exact = 100.0 * double(same) / (double(n) / 4);
    if (getenv("OMNI_TEST_EDGES") && over12) {   // where the >12 differences are: right/bottom edge columns or rows?
        uint64_t edge = 0, inner = 0;
        for (int y = 0; y < a.h; ++y) for (int x = 0; x < a.w; ++x) {
            const uint8_t* p = a.px + size_t(y) * a.stride + size_t(x) * 4; const uint8_t* q = b.px + size_t(y) * b.stride + size_t(x) * 4;
            bool big = false; for (int c = 0; c < 3; ++c) big |= std::abs(int(p[c]) - int(q[c])) > 12;
            if (big) (x >= a.w - 4 || y >= a.h - 4 ? edge : inner)++;
        }
        printf("    >12 pixels: %llu in the last 4 columns/rows, %llu elsewhere\n", (unsigned long long)edge, (unsigned long long)inner);
    }
    return d;
}
static long rssKiB() { long kb = 0; if (FILE* f = fopen("/proc/self/status", "r")) { char l[256]; while (fgets(l, sizeof l, f)) if (!strncmp(l, "VmRSS:", 6)) kb = atol(l + 6); fclose(f); } return kb; }

struct Case { int sw, sh, dw, dh, bps, matrix; bool full, swap; const char* what; };
static int partA()
{
    const Case cases[] = {
        { 1920, 1080, 3840, 2160, 1, 1, false, false, "1080p -> 2160 canvas (2x enlarge)" },
        { 1920, 1080, 3840, 2160, 2, 9, false, false, "1080p 10-bit BT.2020 -> 2160" },
        { 3840, 2160, 3840, 2160, 1, 1, false, true,  "2160 -> 2160 (1:1, RGBA)" },
        { 3840, 2160, 3840, 2160, 2, 9, false, false, "2160 10-bit -> 2160 (1:1)" },
        { 2560, 1440, 3840, 2160, 1, 1, false, false, "1440p -> 2160 (1.5x enlarge)" },
        { 1280, 720, 3840, 2160, 1, 1, true, false,   "720p full range -> 2160 (3x)" },
        { 853, 479, 3840, 2160, 1, 6, false, false,   "odd 853x479 -> 2160 (non-integer)" },
        { 1366, 768, 3840, 2160, 1, 1, false, false,  "odd 1366x768 -> 2160" },
        { 721, 405, 721, 405, 1, 6, false, false,     "odd 721x405 1:1" },
        { 3840, 2160, 1919, 1079, 1, 1, false, false, "odd shrink 2160 -> 1919x1079" },
        { 3840, 2160, 2880, 1620, 1, 1, false, false, "shrink 2160 -> 2880x1620 (window)" },
        { 1279, 719, 1920, 1080, 2, 9, false, true,   "odd 10-bit 1279x719 -> 1080p" },
    };
    int bad = 0;
    for (const Case& c : cases) {
        const Pic p = makePic(c.sw, c.sh, c.bps, 7u + unsigned(c.sw));
        Layer gpu = makeLayer(c.dw, c.dh), title = makeLayer(c.dw, c.dh), model = makeLayer(c.dw, c.dh);
        cpuTitle(p, title, c.matrix, c.full, c.swap); cpuShader(p, model, c.matrix, c.full, c.swap);
        OmniGpuVideo::Job j = job(p, gpu, c.matrix, c.full, c.swap);
        const bool ok = OmniGpuVideo::convert(j);
        const Diff a = diff(gpu, model), b = diff(gpu, title);
        const bool shrink = c.dw < c.sw || c.dh < c.sh;
        // pixel-for-pixel against the shader model: float rounding only (worst 1); against the title's CPU path: what verify() accepts
        const bool passModel = ok && a.worst <= 1 && a.exact >= 99.9;
        const bool passTitle = ok && (shrink ? (b.mean <= 2.5 && b.p12 <= 1.0) : (b.mean <= 1.0 && b.p12 <= 0.5));
        printf("A %-38s %4dx%-4d -> %4dx%-4d %2d-bit: GPU vs shader model: %.4f%% exact, worst %d | GPU vs title CPU path: mean %.3f, >12 %.3f%%, worst %d, exact %.2f%% -> %s\n",
            c.what, c.sw, c.sh, c.dw, c.dh, c.bps == 2 ? 10 : 8, a.exact, a.worst, b.mean, b.p12, b.worst, b.exact, passModel && passTitle ? "PASS" : "FAIL");
        bad += !(passModel && passTitle);
        freeLayer(gpu); freeLayer(title); freeLayer(model);
    }
    printf("A RESULT %s (%d of %zu failed)\n", bad ? "FAIL" : "PASS", bad, sizeof cases / sizeof cases[0]);
    return bad;
}
// The gap: at a 2160 canvas, 1080p video. V1 returned kCpu for every enlargement (never verified, never on the GPU).
static int partB()
{
    const Pic p = makePic(1920, 1080, 1, 11);
    Layer L = makeLayer(3840, 2160);
    int plans[5]; int bad = 0;
    for (int i = 0; i < 5; ++i) {
        OmniGpuVideo::Job j = job(p, L, 1, false, false);
        plans[i] = OmniGpuVideo::plan(j);
        if (plans[i] == OmniGpuVideo::kVerify) { cpuTitle(p, L, 1, false, false); OmniGpuVideo::verify(j); }
        else if (plans[i] == OmniGpuVideo::kGpu && !OmniGpuVideo::convert(j)) bad++;
    }
    const bool pass = plans[0] == OmniGpuVideo::kVerify && plans[1] == OmniGpuVideo::kVerify && plans[2] == OmniGpuVideo::kVerify && plans[3] == OmniGpuVideo::kGpu && plans[4] == OmniGpuVideo::kGpu && !bad;
    printf("B 1080p video on a 2160 canvas: plans %d %d %d %d %d (1 = verify, 2 = GPU) -> %s\n", plans[0], plans[1], plans[2], plans[3], plans[4], pass ? "PASS (GPU engages)" : "FAIL");
    freeLayer(L);
    return pass ? 0 : 1;
}
static int partC(int frames)
{
    quiet = true;
    const Pic small = makePic(320, 180, 1, 3), small10 = makePic(320, 180, 2, 4);
    Layer layers[4] = { makeLayer(640, 360), makeLayer(640, 360), makeLayer(320, 180), makeLayer(480, 270) };
    long b0 = 0, m0 = 0, b1 = 0, m1 = 0; size_t c0 = 0, c1 = 0, cmax = 0; long rss0 = 0;
    int fails = 0, remaps = 0;
    for (int i = 0; i < frames; ++i) {
        Layer& L = layers[i % 4];
        if (i % 997 == 500) {   // a layer grows / goes: the hole-punch forgets it before munmap, then maps a new one
            const int w = L.w, h = L.h; freeLayer(L); L = makeLayer(w, h); remaps++;
        }
        OmniGpuVideo::Job j = job(i % 7 == 3 ? small10 : small, L, 1, false, false);
        if (!OmniGpuVideo::convert(j)) fails++;
        if (i == 100) { omni_gpu_video_test_live(&b0, &m0, &c0); rss0 = rssKiB(); }
        if (i > 100) { long b, m; size_t c; omni_gpu_video_test_live(&b, &m, &c); cmax = std::max(cmax, c); if (b > b0 + 1 || m > m0 + 1) { b1 = b; m1 = m; } }
    }
    omni_gpu_video_test_live(&b1, &m1, &c1);
    const long rss1 = rssKiB();
    const bool pass = !fails && b1 == b0 && m1 == m0 && cmax <= 16 && rss1 - rss0 < 4096;
    printf("C %d pictures (%d layer remaps): live buffers %ld -> %ld, memory objects %ld -> %ld, cached layers max %zu, RSS %ld -> %ld KiB, failures %d -> %s\n",
        frames, remaps, b0, b1, m0, m1, cmax, rss0, rss1, fails, pass ? "PASS" : "FAIL");
    for (Layer& L : layers) freeLayer(L);
    long bz, mz; size_t cz; omni_gpu_video_test_live(&bz, &mz, &cz);
    printf("C after the layers are forgotten: %zu cached layers (want 0), live buffers %ld, memory %ld\n", cz, bz, mz);
    quiet = false;
    return pass && cz == 0 ? 0 : 1;
}
static int partD()
{
    struct C { int sw, sh, bps, matrix; const char* what; };
    const C cases[] = { { 3840, 2160, 1, 1, "2160 -> 2160 in place" }, { 3840, 2160, 2, 9, "2160 10-bit -> 2160 in place" },
                        { 1920, 1080, 1, 1, "1080p -> 2160 in place" }, { 2560, 1440, 1, 1, "1440p -> 2160 in place" },
                        { 2560, 1440, 2, 9, "1440p 10-bit -> 2160 in place" } };
    int bad = 0;
    for (const C& c : cases) {
        const Pic p = makePic(c.sw, c.sh, c.bps, 31u + unsigned(c.sw + c.bps));
        Mapped m = mapCopy(p);
        Layer inPlace = makeLayer(3840, 2160), ring = makeLayer(3840, 2160), model = makeLayer(3840, 2160), title = makeLayer(3840, 2160);
        uint64_t ip0, rc0, ip1, rc1; int sh; OmniGpuVideo::stats2(ip0, rc0, sh);
        OmniGpuVideo::Job j = job(p, inPlace, c.matrix, false, false); j.planes = m.p; j.planesBytes = p.planes.size(); j.planesPersistent = true;
        const bool ok1 = OmniGpuVideo::convert(j);
        OmniGpuVideo::stats2(ip1, rc1, sh);
        const bool usedInPlace = ip1 == ip0 + 1 && rc1 == rc0;
        OmniGpuVideo::Job r = job(p, ring, c.matrix, false, false);   // V2's path: the ring copy
        const bool ok2 = OmniGpuVideo::convert(r);
        cpuShader(p, model, c.matrix, false, false); cpuTitle(p, title, c.matrix, false, false);
        const Diff vsRing = diff(inPlace, ring), vsModel = diff(inPlace, model), vsTitle = diff(inPlace, title);
        const bool pass = ok1 && ok2 && usedInPlace && vsRing.worst == 0 && vsModel.worst == 0 && vsTitle.mean <= 1.0 && vsTitle.p12 <= 0.5;
        printf("D %-32s %4dx%-4d %2d-bit: in place %s; vs ring copy worst %d (exact %.4f%%), vs shader model worst %d, vs title CPU mean %.3f >12 %.3f%% -> %s\n",
            c.what, c.sw, c.sh, c.bps == 2 ? 10 : 8, usedInPlace ? "yes" : "NO", vsRing.worst, vsRing.exact, vsModel.worst, vsTitle.mean, vsTitle.p12, pass ? "PASS" : "FAIL");
        bad += !pass;
        unmapCopy(m); freeLayer(inPlace); freeLayer(ring); freeLayer(model); freeLayer(title);
    }
    printf("D RESULT %s (%d of %zu failed)\n", bad ? "FAIL" : "PASS", bad, sizeof cases / sizeof cases[0]);
    return bad;
}
static int partE(int frames)
{
    quiet = true;
    const Pic pic = makePic(640, 360, 1, 5), pic10 = makePic(640, 360, 2, 6);
    constexpr int kQueue = 16;
    Mapped q[kQueue]; bool tenBit[kQueue] = {};
    for (int i = 0; i < kQueue; ++i) { tenBit[i] = i % 5 == 2; q[i] = mapCopy(tenBit[i] ? pic10 : pic); }
    Layer L = makeLayer(1280, 720);
    long b0 = 0, m0 = 0, b1 = 0, m1 = 0; size_t c0 = 0, c1 = 0, cmax = 0; long rss0 = 0; int fails = 0, remaps = 0;
    uint64_t ip0 = 0, rc0 = 0, ip1 = 0, rc1 = 0; int sh = 0;
    for (int i = 0; i < frames; ++i) {
        const int k = i % kQueue;
        if (i % 1013 == 600) { unmapCopy(q[k]); q[k] = mapCopy(tenBit[k] ? pic10 : pic); remaps++; }   // PaceAlloc frees and maps again
        OmniGpuVideo::Job j = job(tenBit[k] ? pic10 : pic, L, 1, false, false);
        j.planes = q[k].p; j.planesPersistent = true;
        if (!OmniGpuVideo::convert(j)) fails++;
        if (i == 200) { omni_gpu_video_test_live(&b0, &m0, &c0); rss0 = rssKiB(); OmniGpuVideo::stats2(ip0, rc0, sh); }
        if (i > 200) { long b, m; size_t c; omni_gpu_video_test_live(&b, &m, &c); cmax = std::max(cmax, c); }
    }
    omni_gpu_video_test_live(&b1, &m1, &c1); OmniGpuVideo::stats2(ip1, rc1, sh);
    const long rss1 = rssKiB();
    // remaps after warm-up replace an entry (forget, then one import): the live count returns to the same value
    const bool pass = !fails && b1 == b0 && m1 == m0 && cmax <= size_t(kQueue + 2) && rss1 - rss0 < 4096 && rc1 == rc0 && ip1 - ip0 == uint64_t(frames - 201);
    printf("E %d pictures through a %d-buffer pace queue (%d buffers freed and mapped again): live buffers %ld -> %ld, memory %ld -> %ld, cache max %zu, RSS %ld -> %ld KiB, in place %llu, ring copies %llu, failures %d -> %s\n",
        frames, kQueue, remaps, b0, b1, m0, m1, cmax, rss0, rss1, (unsigned long long)(ip1 - ip0), (unsigned long long)(rc1 - rc0), fails, pass ? "PASS" : "FAIL");
    for (Mapped& m : q) unmapCopy(m);
    freeLayer(L);
    long bz, mz; size_t cz; omni_gpu_video_test_live(&bz, &mz, &cz);
    printf("E after the queue is freed: %zu cached imports (want 0), live buffers %ld, memory %ld\n", cz, bz, mz);
    quiet = false;
    return pass && cz == 0 ? 0 : 1;
}
#ifdef OMNI_SHARED_TEST
extern "C" int omni_gpu_present_test_up();
extern "C" int omni_gpu_present_test_shared();
extern "C" long omni_gpu_present_test(const uint8_t*, int, int, int, const uint8_t*, size_t, int, int, int, int, int, const uint32_t*, size_t, int, int, uint8_t*, int, int*);
extern "C" void omni_gpu_present_test_teardown(long*, long*, long*);
// The title's order: the present comes up first (SDL_Init), then the video's preinit adopts its device.
static int partS()
{
    if (!omni_gpu_present_test_up()) { printf("S present host device: FAIL\n"); return 1; }
    if (!OmniGpuVideo::preinit()) { printf("S video preinit on the shared device: FAIL\n"); return 1; }
    uint64_t a, b; int shared = 0; OmniGpuVideo::stats2(a, b, shared);
    int bad = !(shared && omni_gpu_present_test_shared());
    printf("S video device shared with the present: %s\n", shared ? "yes (no second VkDevice)" : "NO");
    // conversions (the hole-punch's service thread) and composes (the presenter) interleaved on the one queue
    const Pic p = makePic(1920, 1080, 1, 77);
    Layer L = makeLayer(1920, 1080), model = makeLayer(1920, 1080);
    cpuShader(p, model, 1, false, false);
    std::vector<uint8_t> frame(size_t(1920) * 1080 * 4, 0), out(size_t(1920) * 1080 * 4);
    for (size_t i = 3; i < frame.size(); i += 4) frame[i] = 0;   // alpha 0: the video shows through everywhere
    std::vector<uint32_t> runs; for (int y = 0; y < 1080; ++y) { runs.push_back(uint32_t(y)); runs.push_back(0); runs.push_back(1920); }
    int convFails = 0, composeBad = 0, released = 0;
    for (int i = 0; i < 6; ++i) {
        OmniGpuVideo::Job j = job(p, L, 1, false, false);
        if (OmniGpuVideo::plan(j) == OmniGpuVideo::kVerify) { cpuTitle(p, L, 1, false, false); OmniGpuVideo::verify(j); }
        if (!OmniGpuVideo::convert(j)) convFails++;
        const long r = omni_gpu_present_test(frame.data(), 1920 * 4, 1920, 1080, L.px, L.bytes, L.stride, 0, 0, 1920, 1080, runs.data(), runs.size(), 1920, 1080, out.data(), 0, &released);
        if (r != 0) composeBad++;
    }
    const Diff d = diff(L, model);
    // the presented output must carry the converted layer's pixels (RGBA of the canvas order: the test uses BGRA layers and an RGBA target)
    uint64_t outDiff = 0;
    for (int y = 0; y < 1080; y += 7) for (int x = 0; x < 1920; x += 5) {
        const uint8_t* s = L.px + size_t(y) * L.stride + size_t(x) * 4; const uint8_t* o = out.data() + (size_t(y) * 1920 + x) * 4;
        for (int c = 0; c < 3; ++c) outDiff += std::abs(int(s[c]) - int(o[c])) > 1;
    }
    const bool convOk = !convFails && d.worst == 0;
    printf("S 6 conversions + 6 composes on the shared queue: conversion failures %d, layer vs shader model worst %d, composes with differences %d, presented pixels off %llu -> %s\n",
        convFails, d.worst, composeBad, (unsigned long long)outDiff, convOk && !composeBad && !outDiff ? "PASS" : "FAIL");
    bad += !(convOk && !composeBad && !outDiff);
    {   // the two threads of the title at once: the service thread converts while the presenter composes (queue lock)
        const Pic small = makePic(640, 360, 1, 9);
        Layer A = makeLayer(640, 360), M = makeLayer(640, 360); cpuShader(small, M, 1, false, false);
        std::atomic<int> tFails { 0 }, tWrong { 0 };
        std::thread conv([&] { for (int i = 0; i < 300; ++i) { OmniGpuVideo::Job j = job(small, A, 1, false, false); if (!OmniGpuVideo::convert(j)) tFails++; else if (diff(A, M).worst) tWrong++; } });
        std::vector<uint8_t> f2(size_t(640) * 360 * 4, 255), o2(size_t(640) * 360 * 4); int rel2 = 0, cBad = 0;
        for (int i = 0; i < 300; ++i) if (omni_gpu_present_test(f2.data(), 640 * 4, 640, 360, nullptr, 0, 0, 0, 0, 0, 0, nullptr, 0, 640, 360, o2.data(), 0, &rel2) != 0) cBad++;
        conv.join();
        const bool ok = !tFails && !tWrong && !cBad;
        printf("S concurrent: 300 conversions (thread) + 300 composes (main) on the one queue: conversion failures %d, wrong layers %d, composes with differences %d -> %s\n",
            tFails.load(), tWrong.load(), cBad, ok ? "PASS" : "FAIL");
        bad += !ok;
        freeLayer(A); freeLayer(M);
    }
    freeLayer(L); freeLayer(model);
    long tb = -1, ti = -1, tm = -1; omni_gpu_present_test_teardown(&tb, &ti, &tm);   // shuts the video down first (V3)
    long vb, vm; size_t vc; omni_gpu_video_test_live(&vb, &vm, &vc);
    const bool tdOk = tb == 0 && ti == 0 && tm == 0 && vb == 0 && vm == 0 && vc == 0;
    printf("S teardown: present live buffers %ld images %ld memory %ld, video live buffers %ld memory %ld cached %zu (all want 0) -> %s\n", tb, ti, tm, vb, vm, vc, tdOk ? "PASS" : "FAIL");
    bad += !tdOk;
    OmniGpuVideo::Job j = job(p, L, 1, false, false);
    printf("S after teardown: plan %d (0 = CPU) -> %s\n", OmniGpuVideo::plan(j), OmniGpuVideo::plan(j) == OmniGpuVideo::kCpu ? "PASS (the CPU path takes over)" : "FAIL");
    bad += OmniGpuVideo::plan(j) != OmniGpuVideo::kCpu;
    printf("S RESULT %s\n", bad ? "FAIL" : "PASS");
    return bad;
}
#endif
int main(int argc, char** argv)
{
    const char* what = argc > 1 ? argv[1] : "all";
    OmniGpuVideo::setNote(note);
    FILE* f = fopen("gpu-video.flag", "w");   // the flag (the host build's flag path); W: with the word failsetup
    if (f) { if (!strcmp(what, "W")) fputs("failsetup\n", f); fclose(f); }
    if (!strcmp(what, "F") || !strcmp(what, "W")) {   // fallback: no usable Vulkan ICD (F), or the set-up failed on purpose (W)
        const bool up = OmniGpuVideo::preinit();
        const Pic p = makePic(64, 36, 1, 1); Layer L = makeLayer(128, 72);
        OmniGpuVideo::Job j = job(p, L, 1, false, false);
        const int plan = OmniGpuVideo::plan(j); const bool conv = OmniGpuVideo::convert(j);
        printf("%s fallback (%s): preinit %d, plan %d (0 = CPU), convert %d -> %s\n", what, !strcmp(what, "W") ? "flag word failsetup" : "no Vulkan ICD", up, plan, conv, !up && plan == OmniGpuVideo::kCpu && !conv ? "PASS (CPU path keeps every picture)" : "FAIL");
        freeLayer(L); omni_gpu_video_shutdown();
        return !up && plan == OmniGpuVideo::kCpu && !conv ? 0 : 1;
    }
#ifdef OMNI_SHARED_TEST
    if (!strcmp(what, "S")) { const int bad = partS(); printf("RESULT %s\n", bad ? "FAIL" : "PASS"); return bad ? 1 : 0; }
#endif
    if (!OmniGpuVideo::preinit()) { printf("preinit failed: no Vulkan\n"); return 2; }
    int bad = 0;
    if (!strcmp(what, "B") || !strcmp(what, "all")) bad += partB();   // first: verify state is fresh
    if (!strcmp(what, "A") || !strcmp(what, "all")) bad += partA();
    if (!strcmp(what, "C") || !strcmp(what, "all")) bad += partC(argc > 2 ? atoi(argv[2]) : 10000);
    if (!strcmp(what, "D") || !strcmp(what, "all")) bad += partD();
    if (!strcmp(what, "E") || !strcmp(what, "all")) bad += partE(argc > 2 ? atoi(argv[2]) : 10000);
    omni_gpu_video_shutdown();
    printf("RESULT %s\n", bad ? "FAIL" : "PASS");
    return bad ? 1 : 0;
}
