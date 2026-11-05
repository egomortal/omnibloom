// SPDX-License-Identifier: GPL-3.0-or-later
// omni-native-s3.5-hdr host test (lavapipe = llvmpipe Vulkan on the CPU; host timings are not PS5 figures).
//   V  OmniGpuVideo V4: the PQ layer written by the GPU against a double-precision reference (<= 1 code value):
//      HDR10 (BT.2020 NCL + ST 2084): OmniHdrColour.h's yuv10() (Omni's own reference, PQ kept as it is);
//      HLG: BT.2100 inverse OETF + OOTF (gamma 1.2, 1000 nits) + PQ, in double. Sizes: 3840x2160 1:1, 1920x1080 and
//      2560x1440 -> 3840x2160 (the CPU's integer enlargement rule), full range, and a 10-bit two-plane low-aligned
//      (P010-style) decoder picture split to planar as holeSplitPlanes does. The RGBA8 layer of the same pass is
//      byte-identical to a pass without the PQ layer (SDR output and eligibility untouched).
//   N  no per-frame allocation: 3000 HDR conversions over 6 rotating layers (+ PQ layers) with remaps: live Vulkan
//      buffers/memory constant after warm-up, cache bounded.
//   P  OmniGpuPresent V4, HDR10 output (A2B10G10R10 target): page pixels = the SDR->PQ reference at 203 nits (<= 1 code;
//      SDR white = PQ(203 nits)); opaque video runs = the staged PQ layer exactly (passthrough, no tone mapping);
//      translucent (mix) pixels and a frame without a PQ layer = the SDR mapping (fallback); 1080p canvas too.
//   Q  3000 HDR presents with a PQ layer: live objects constant, retained region vector, every frame counted.
//   L  OmniHdrPolicy: the setting (Off / Auto / On, legacy flags), the HDR10 format choice, full-screen rule, Auto's
//      timing, and the swapchain fallback (HDR refused -> SDR; SDR refused -> fatal; forced refusal keeps SDR).
// Usage: hdr_test [V|N|P|Q|L|all]
#include "OmniGpuVideo.h"
#include "OmniHdrColour.h"
#include "OmniHdrPolicy.h"
#include <algorithm>
#include <cstdarg>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <sys/mman.h>
#include <unistd.h>
#include <vector>

extern "C" void omni_gpu_video_test_live(long* buffers, long* memory, size_t* cached);
extern "C" long omni_gpu_present_test(const uint8_t*, int, int, int, const uint8_t*, size_t, int, int, int, int, int, const uint32_t*, size_t, int, int, uint8_t*, int, int*);
extern "C" void omni_gpu_present_test_counts(long*, long*, long*);
extern "C" void omni_gpu_present_test_hdr(int on, int white);
extern "C" long omni_gpu_present_test_pq_reference(uint8_t r, uint8_t g, uint8_t b, int white);
extern "C" void omni_gpu_present_test_teardown(long*, long*, long*);
extern "C" void omni_gpu_present_forget(const void*);
extern "C" void omni_gpu_present_test_source_pq(const void* pq, size_t bytes, uint32_t info);
extern "C" void omni_gpu_present_test_pq_stats(uint64_t* pqFrames, size_t* pqRegionsCap);
extern "C" int omni_gpu_present_test_up();

static int g_fail = 0;
static void result(bool ok, const char* fmt, ...) __attribute__((format(printf, 2, 3)));
static void result(bool ok, const char* fmt, ...)
{
    va_list ap; va_start(ap, fmt); vprintf(fmt, ap); va_end(ap);
    printf(" -> %s\n", ok ? "PASS" : "FAIL"); if (!ok) ++g_fail; fflush(stdout);
}
static uint8_t* mapBytes(size_t n) { return static_cast<uint8_t*>(mmap(nullptr, n, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0)); }

// ---- V: the GPU's PQ layer ------------------------------------------------------------------------------------------
struct Pic { int w, h; std::vector<uint16_t> planes; };   // planar 4:2:0, 10-bit low-aligned (yuv420p10le)
static Pic makePic(int w, int h, unsigned seed, bool full)
{
    Pic p { w, h, {} }; const int cw = (w + 1) / 2, ch = (h + 1) / 2;
    p.planes.assign(size_t(w) * h + 2 * size_t(cw) * ch + 64, 0);
    srand(seed);
    const int lo = full ? 0 : 64, hi = full ? 1023 : 940;
    for (int y = 0; y < h; ++y) for (int x = 0; x < w; ++x) {   // a luminance ramp over the whole PQ range + noise + hard bars
        double v = double(x) / (w - 1) * 0.8 + 0.15 * sin(y * 0.01) + (rand() % 9 - 4) / 1023.0 + ((x / 101 + y / 67) % 2 ? 0.05 : 0);
        p.planes[size_t(y) * w + x] = uint16_t(std::clamp(int(std::lround(lo + v * (hi - lo))), 0, 1023));
    }
    const size_t yn = size_t(w) * h, cn = size_t(cw) * ch;
    const int clo = full ? 0 : 64, chi = full ? 1023 : 960;
    for (int y = 0; y < ch; ++y) for (int x = 0; x < cw; ++x) {   // saturated BT.2020 colours, and the limits
        double u = 0.5 + 0.45 * sin(x * 0.021 + y * 0.013), v = 0.5 + 0.45 * cos(x * 0.017 - y * 0.023);
        if ((x / 37) % 7 == 0) { u = 0; v = 1; }
        p.planes[yn + size_t(y) * cw + x] = uint16_t(std::clamp(int(std::lround(clo + u * (chi - clo))), 0, 1023));
        p.planes[yn + cn + size_t(y) * cw + x] = uint16_t(std::clamp(int(std::lround(clo + v * (chi - clo))), 0, 1023));
    }
    return p;
}
// The decoder's 10-bit picture as two planes, low-aligned (Y; then interleaved Cb,Cr), and the split to planar that the
// title's holeSplitPlanes does before the GPU (the split itself is unchanged by this build).
static Pic viaTwoPlane(const Pic& in)
{
    const int w = in.w, h = in.h, cw = (w + 1) / 2, ch = (h + 1) / 2; const size_t yn = size_t(w) * h, cn = size_t(cw) * ch;
    std::vector<uint16_t> p010(yn + 2 * cn);
    memcpy(p010.data(), in.planes.data(), yn * 2);
    for (size_t i = 0; i < cn; ++i) { p010[yn + 2 * i] = in.planes[yn + i]; p010[yn + 2 * i + 1] = in.planes[yn + cn + i]; }
    Pic out { w, h, {} }; out.planes.assign(in.planes.size(), 0);
    memcpy(out.planes.data(), p010.data(), yn * 2);
    for (size_t i = 0; i < cn; ++i) { out.planes[yn + i] = p010[yn + 2 * i] & 1023; out.planes[yn + cn + i] = p010[yn + 2 * i + 1] & 1023; }
    return out;
}
static double pqEnc(double nits) { return OmniMedia::Hdr::pqEncode(nits); }
static uint32_t hlgRef(unsigned y, unsigned u, unsigned v, bool full)   // BT.2100 HLG -> PQ, double
{
    const double yy = (double(y) - (full ? 0 : 64)) / (full ? 1023 : 876), cb = (double(u) - 512) / (full ? 1023 : 896), cr = (double(v) - 512) / (full ? 1023 : 896);
    double e[3] = { yy + 1.4746 * cr, yy - 0.16455312684366 * cb - 0.57135312684366 * cr, yy + 1.8814 * cb };
    const double a = 0.17883277, b = 1 - 4 * a, c = 0.5 - a * std::log(4 * a);
    double s[3];
    for (int i = 0; i < 3; ++i) { const double x = OmniMedia::Hdr::unit(e[i]); s[i] = x <= 0.5 ? x * x / 3 : (std::exp((x - c) / a) + b) / 12; }
    const double ys = 0.2627 * s[0] + 0.6780 * s[1] + 0.0593 * s[2];
    const double k = 1000.0 * std::pow(std::max(ys, 1e-9), 0.2);
    return OmniMedia::Hdr::pack(pqEnc(k * s[0]), pqEnc(k * s[1]), pqEnc(k * s[2]));
}
struct Layer { uint8_t* px = nullptr; size_t bytes = 0; int w = 0, h = 0, stride = 0; };
static Layer makeLayer(int w, int h) { Layer L; L.w = w; L.h = h; L.stride = (w + 15) / 16 * 16 * 4; L.bytes = size_t(L.stride) * h; L.px = mapBytes(L.bytes); return L; }
static void freeLayer(Layer& L) { OmniGpuVideo::forget(L.px); munmap(L.px, L.bytes); L = Layer {}; }
static OmniGpuVideo::Job job(const Pic& p, const Layer& L, bool full)
{
    OmniGpuVideo::Job j; j.planes = reinterpret_cast<const uint8_t*>(p.planes.data()); j.planesBytes = p.planes.size() * 2; j.srcW = p.w; j.srcH = p.h; j.bps = 2;
    j.dst = L.px; j.dstBytes = L.bytes; j.dstW = L.w; j.dstH = L.h; j.dstStride = L.stride; j.swapRB = true; j.matrix = 9; j.fullRange = full;
    return j;
}
static bool caseV(const char* name, const Pic& p, int outW, int outH, int mode, bool full)
{
    Layer L = makeLayer(outW, outH), H = makeLayer(outW, outH), S = makeLayer(outW, outH);
    OmniGpuVideo::Job j0 = job(p, S, full);   // the same picture without the PQ layer (V3's pass)
    const bool ok0 = OmniGpuVideo::plan(j0) == OmniGpuVideo::kGpu && OmniGpuVideo::convert(j0);
    OmniGpuVideo::Job j = job(p, L, full); bool done = false;
    j.hdrDst = H.px; j.hdrDstBytes = H.bytes; j.hdrMode = mode; j.hdrDone = &done;
    const bool ok = OmniGpuVideo::plan(j) == OmniGpuVideo::kGpu && OmniGpuVideo::convert(j);
    const int cw = (p.w + 1) / 2, ch = (p.h + 1) / 2; const size_t yn = size_t(p.w) * p.h, cn = size_t(cw) * ch;
    const bool enlarge = outW > p.w || outH > p.h;
    long off = 0; int worst = 0; bool alpha = true; size_t sdrDiff = 0;
    for (int y = 0; y < outH; ++y) {
        const int sy = enlarge ? std::min(p.h - 1, int((int64_t(2 * y + 1) * p.h) / (2 * outH))) : y;
        const uint32_t* got = reinterpret_cast<const uint32_t*>(H.px + size_t(y) * H.stride);
        for (int x = 0; x < outW; ++x) {
            const int sx = enlarge ? std::min(p.w - 1, int((int64_t(2 * x + 1) * p.w) / (2 * outW))) : x;
            const unsigned Y = p.planes[size_t(sy) * p.w + sx], U = p.planes[yn + size_t(sy >> 1) * cw + (sx >> 1)], V = p.planes[yn + cn + size_t(sy >> 1) * cw + (sx >> 1)];
            const uint32_t want = mode == 1 ? OmniMedia::Hdr::yuv10(Y, U, V, full) : hlgRef(Y, U, V, full);
            if (got[x] == want) continue;
            ++off; if ((got[x] >> 30) != 3) alpha = false;
            for (int s = 0; s < 30; s += 10) worst = std::max(worst, std::abs(int((got[x] >> s) & 1023) - int((want >> s) & 1023)));
        }
        if (memcmp(L.px + size_t(y) * L.stride, S.px + size_t(y) * S.stride, size_t(outW) * 4)) sdrDiff++;
    }
    result(ok && ok0 && done && alpha && worst <= 1 && sdrDiff == 0,
           "V %-40s %dx%d -> %dx%d: PQ layer %s, %ld of %d pixels off the double reference, worst %d code(s); RGBA8 layer vs the pass without PQ: %zu rows differ",
           name, p.w, p.h, outW, outH, done ? "written" : "MISSING", off, outW * outH, worst, sdrDiff);
    freeLayer(L); freeLayer(H); freeLayer(S);
    (void)ch;
    return true;
}
static void partV()
{
    printf("== V: the PQ layer (OmniGpuVideo V4) against double-precision references\n");
    const Pic p2160 = makePic(3840, 2160, 7, false), p1080 = makePic(1920, 1080, 8, false), p1440 = makePic(2560, 1440, 9, false);
    caseV("HDR10 2160 1:1 (limited)", p2160, 3840, 2160, 1, false);
    caseV("HDR10 1080p -> 2160", p1080, 3840, 2160, 1, false);
    caseV("HDR10 1440p -> 2160", p1440, 3840, 2160, 1, false);
    caseV("HDR10 2160 from a two-plane 10-bit picture", viaTwoPlane(p2160), 3840, 2160, 1, false);
    caseV("HDR10 1080p from a two-plane picture -> 2160", viaTwoPlane(p1080), 3840, 2160, 1, false);
    caseV("HDR10 1080p 1:1 full range", makePic(1920, 1080, 10, true), 1920, 1080, 1, true);
    caseV("HLG 2160 1:1 -> PQ", p2160, 3840, 2160, 2, false);
    caseV("HLG 1080p -> 2160 -> PQ", p1080, 3840, 2160, 2, false);
}
static void partN(int n)
{
    printf("== N: %d HDR conversions, 6 rotating layers + PQ layers, remapped every 500\n", n);
    const Pic p = makePic(1920, 1080, 11, false);
    Layer L[6], H[6]; for (int i = 0; i < 6; ++i) { L[i] = makeLayer(1920, 1080); H[i] = makeLayer(1920, 1080); }
    long b0 = 0, m0 = 0, bMax = 0, mMax = 0; size_t c = 0, cMax = 0; int done = 0;
    for (int k = 0; k < n; ++k) {
        const int i = k % 6;
        if (k && k % 500 == 0) { freeLayer(L[i]); freeLayer(H[i]); L[i] = makeLayer(1920, 1080); H[i] = makeLayer(1920, 1080); }
        OmniGpuVideo::Job j = job(p, L[i], false); bool d = false; j.hdrDst = H[i].px; j.hdrDstBytes = H[i].bytes; j.hdrMode = 1; j.hdrDone = &d;
        if (OmniGpuVideo::convert(j) && d) ++done;
        long b, m; omni_gpu_video_test_live(&b, &m, &c);
        if (k == 20) { b0 = b; m0 = m; }
        if (k > 20) { bMax = std::max(bMax, b); mMax = std::max(mMax, m); } cMax = std::max(cMax, c);
    }
    result(done == n && bMax <= b0 && mMax <= m0 && cMax <= 16, "N %d of %d PQ layers written; live buffers %ld -> max %ld, memory %ld -> max %ld (after warm-up), cached imports max %zu (limit 16)",
           done, n, b0, bMax, m0, mMax, cMax);
    for (int i = 0; i < 6; ++i) { freeLayer(L[i]); freeLayer(H[i]); }
    uint64_t hp = 0; OmniGpuVideo::stats3(hp); printf("   OmniGpuVideo stats3: %llu PQ layers in total\n", (unsigned long long)hp);
}

// ---- P / Q: the present's HDR10 output ---------------------------------------------------------------------------
struct Scene { int w, h, lx, ly, lw, lh, stride; std::vector<uint8_t> frame; uint8_t* layer; uint8_t* pq; size_t lbytes; std::vector<uint32_t> runs; std::vector<char> mix; };
static Scene makeScene(int w, int h)
{
    Scene s; s.w = w; s.h = h; s.lx = w / 8; s.ly = h / 8; s.lw = w * 3 / 4; s.lh = h * 3 / 4; s.stride = (s.lw + 15) / 16 * 16 * 4;
    s.lbytes = size_t(s.stride) * s.lh; s.layer = mapBytes(s.lbytes); s.pq = mapBytes(s.lbytes);
    s.frame.assign(size_t(w) * h * 4, 0); s.mix.assign(size_t(w) * h, 0);
    srand(5);
    for (int y = 0; y < h; ++y) for (int x = 0; x < w; ++x) {   // page: white text band, greys, colours
        uint8_t* p = &s.frame[(size_t(y) * w + x) * 4];
        if (y < h / 16) { p[0] = p[1] = p[2] = 255; } else { p[0] = uint8_t(x * 255 / w); p[1] = uint8_t(y * 255 / h); p[2] = uint8_t((x + y) & 255); }
        p[3] = 255;
    }
    for (int y = 0; y < s.lh; ++y) for (int x = 0; x < s.lw; ++x) {
        uint8_t* q = s.layer + size_t(y) * s.stride + size_t(x) * 4; q[0] = uint8_t(x); q[1] = uint8_t(y); q[2] = 128; q[3] = 255;
        reinterpret_cast<uint32_t*>(s.pq + size_t(y) * s.stride)[x] = uint32_t(rand() % 1024) | (uint32_t(rand() % 1024) << 10) | (uint32_t(rand() % 1024) << 20) | 0xc0000000u;
    }
    // runs: every video row, except a translucent control band (the bottom tenth) where the CPU writes mix pixels
    for (int y = s.ly; y < s.ly + s.lh; ++y) {
        if (y >= s.ly + s.lh * 9 / 10) {   // mix: the CPU blended a grey over the SDR video into the frame
            for (int x = s.lx; x < s.lx + s.lw; ++x) { uint8_t* p = &s.frame[(size_t(y) * w + x) * 4]; p[0] = p[1] = p[2] = 90; s.mix[size_t(y) * w + x] = 1; }
            continue;
        }
        s.runs.push_back(uint32_t(y)); s.runs.push_back(uint32_t(s.lx)); s.runs.push_back(uint32_t(s.lw));
    }
    return s;
}
static void freeScene(Scene& s) { omni_gpu_present_forget(s.layer); omni_gpu_present_forget(s.pq); munmap(s.layer, s.lbytes); munmap(s.pq, s.lbytes); }
static bool inRun(const Scene& s, int x, int y) { return x >= s.lx && x < s.lx + s.lw && y >= s.ly && y < s.ly + s.lh && !s.mix[size_t(y) * s.w + x]; }
static void caseP(const char* name, Scene& s, bool withPq)
{
    std::vector<uint8_t> out(size_t(s.w) * s.h * 4); int released = 0;
    omni_gpu_present_test_source_pq(withPq ? s.pq : nullptr, withPq ? s.lbytes : 0, withPq ? (0x80000000u | (16u << 8) | 10u) : 0u);
    const long bad = omni_gpu_present_test(s.frame.data(), s.w * 4, s.w, s.h, s.layer, s.lbytes, s.stride, s.lx, s.ly, s.lw, s.lh, s.runs.data(), s.runs.size(), s.w, s.h, out.data(), 0, &released);
    omni_gpu_present_test_source_pq(nullptr, 0, 0);
    long runOff = 0, pageOff = 0, mixOff = 0; int worstPage = 0, worstMix = 0; uint32_t white = 0;
    auto diff = [](uint32_t a, uint32_t b) { int w = 0; for (int k = 0; k < 30; k += 10) w = std::max(w, std::abs(int((a >> k) & 1023) - int((b >> k) & 1023))); return (a >> 30) != (b >> 30) ? 1024 : w; };
    for (int y = 0; y < s.h; ++y) for (int x = 0; x < s.w; ++x) {
        const uint32_t got = reinterpret_cast<const uint32_t*>(out.data())[size_t(y) * s.w + x];
        const uint8_t* f = &s.frame[(size_t(y) * s.w + x) * 4];
        if (inRun(s, x, y)) {
            const uint32_t want = withPq ? reinterpret_cast<const uint32_t*>(s.pq + size_t(y - s.ly) * s.stride)[x - s.lx]
                : uint32_t(omni_gpu_present_test_pq_reference(s.layer[size_t(y - s.ly) * s.stride + size_t(x - s.lx) * 4], s.layer[size_t(y - s.ly) * s.stride + size_t(x - s.lx) * 4 + 1], s.layer[size_t(y - s.ly) * s.stride + size_t(x - s.lx) * 4 + 2], 203));
            const int d = diff(got, want); if (withPq ? d != 0 : d > 1) ++runOff;
        } else {
            const uint32_t want = uint32_t(omni_gpu_present_test_pq_reference(f[0], f[1], f[2], 203));
            const int d = diff(got, want);
            if (s.mix[size_t(y) * s.w + x]) { worstMix = std::max(worstMix, d); if (d > 1) ++mixOff; }
            else { worstPage = std::max(worstPage, d); if (d > 1) ++pageOff; }
            if (x == 1 && y == 1) white = got;
        }
    }
    const unsigned whiteWant = unsigned(std::lround(pqEnc(203) * 1023));
    result(bad == 0 && released == 1 && runOff == 0 && pageOff == 0 && mixOff == 0 && (white & 1023) == whiteWant && ((white >> 10) & 1023) == whiteWant,
        "P %-34s %dx%d: video runs %s (%ld off), page worst %d code(s) vs the 203-nit SDR->PQ reference, mix pixels worst %d, SDR white = PQ code %u (want %u = %.1f nits)",
        name, s.w, s.h, withPq ? "= the PQ layer exactly" : "= SDR mapping (no PQ layer)", runOff, worstPage, worstMix, white & 1023, whiteWant,
        OmniMedia::Hdr::pqDecode((white & 1023) / 1023.0));
}
static void partP()
{
    printf("== P: HDR10 output, page at 203 nits, HDR10 video passed through\n");
    omni_gpu_present_test_hdr(1, 203);
    Scene s = makeScene(3840, 2160); caseP("2160 canvas, PQ layer staged", s, true); caseP("2160 canvas, no PQ layer (fallback)", s, false); freeScene(s);
    Scene t = makeScene(1920, 1080); caseP("1080 canvas, PQ layer staged", t, true); freeScene(t);
}
static void partQ(int n)
{
    printf("== Q: %d HDR presents with a PQ layer\n", n);
    omni_gpu_present_test_hdr(1, 203);
    Scene s = makeScene(1280, 720); std::vector<uint8_t> out(size_t(s.w) * s.h * 4);
    long b0 = 0, i0 = 0, m0 = 0, bMax = 0, iMax = 0, mMax = 0; size_t cap0 = 0, capMax = 0; uint64_t f0 = 0, f1 = 0; int rel = 0;
    for (int k = 0; k < n; ++k) {
        omni_gpu_present_test_source_pq(s.pq, s.lbytes, 0x80000000u | (16u << 8) | 10u);
        omni_gpu_present_test(s.frame.data(), s.w * 4, s.w, s.h, s.layer, s.lbytes, s.stride, s.lx, s.ly, s.lw, s.lh, s.runs.data(), s.runs.size(), s.w, s.h, out.data(), 0, &rel);
        long b, im, m; omni_gpu_present_test_counts(&b, &im, &m); uint64_t fr; size_t cap; omni_gpu_present_test_pq_stats(&fr, &cap);
        if (k == 10) { b0 = b; i0 = im; m0 = m; cap0 = cap; f0 = fr; }
        if (k > 10) { bMax = std::max(bMax, b); iMax = std::max(iMax, im); mMax = std::max(mMax, m); capMax = std::max(capMax, cap); } f1 = fr;
    }
    omni_gpu_present_test_source_pq(nullptr, 0, 0);
    // the per-call target image and read-back buffer of the host harness are made and freed inside each call
    result(bMax <= b0 && iMax <= i0 && mMax <= m0 && capMax == cap0 && f1 - f0 == uint64_t(n - 11) && rel == n,
           "Q live buffers %ld -> max %ld, images %ld -> max %ld, memory %ld -> max %ld; region vector capacity %zu -> %zu; PQ frames %llu of %d; released %d",
           b0, bMax, i0, iMax, m0, mMax, cap0, capMax, (unsigned long long)(f1 - f0), n - 11, rel);
    freeScene(s);
    long b, im, m; omni_gpu_present_test_teardown(&b, &im, &m);
    result(b == 0 && im == 0 && m == 0, "Q teardown: live buffers %ld images %ld memory %ld (want 0 0 0)", b, im, m);
}

// ---- L: the policy ---------------------------------------------------------------------------------------------------
static void partL()
{
    printf("== L: OmniHdrPolicy (setting, format, full screen, Auto timing, swapchain fallback)\n");
    using namespace OmniHdrPolicy;
    struct M { Inputs in; Mode want; const char* name; } ms[] = {
        { { true, false, "off", false, false, false }, kOff, "nothing saved, no flags -> Off (default)" },
        { { true, true, "on", false, false, false }, kOn, "saved On" },
        { { true, true, "auto", false, false, false }, kAuto, "saved Auto" },
        { { true, true, "off", true, false, true }, kOff, "saved Off beats legacy hdr + hdr-auto.flag" },
        { { true, true, "on", false, false, false }, kOn, "saved On without the legacy flag word (s3.4 lost this)" },
        { { false, false, "off", true, true, true }, kOff, "unreadable file -> Off" },
        { { true, false, "off", true, false, true }, kOn, "legacy: word hdr + hdr-auto.flag -> On" },
        { { true, false, "off", true, false, false }, kOff, "legacy: word hdr alone -> Off" },
        { { true, false, "off", false, true, false }, kAuto, "word hdrauto -> Auto" },
    };
    int bad = 0; for (auto& m : ms) { const char* why; if (resolveMode(m.in, &why) != m.want) { ++bad; printf("   setting case failed: %s\n", m.name); } }
    result(!bad, "L setting: %zu cases", sizeof ms / sizeof ms[0]);
    const uint32_t f1[] = { 44, 50, 64 }, s1[] = { 0, 0, kHdr10St2084 };   // what the private WSI member offers
    const uint32_t f2[] = { 44, 50 }, s2[] = { 0, 0 };                     // the stock WSI
    const uint32_t f3[] = { 58, 64, 64 }, s3[] = { kHdr10St2084, 0, kHdr10St2084 };
    result(pickHdrFormat(f1, s1, 3) == 2 && pickHdrFormat(f2, s2, 2) == -1 && pickHdrFormat(f3, s3, 3) == 2, "L HDR10 format: private WSI -> A2B10G10R10, stock WSI -> none (SDR), A2B10G10R10 preferred");
    result(fullscreen(0, 0, 3840, 2160, 3840, 2160) && fullscreen(0, 270, 3840, 1620, 3840, 2160) && !fullscreen(480, 270, 2880, 1620, 3840, 2160) && !fullscreen(0, 0, 0, 0, 3840, 2160),
           "L full screen: whole canvas and a 2.39:1 letterbox yes, a 75%% player no");
    AutoSwitch a; int on = -1, off = -1; bool hdr = false;
    for (int t = 0; t <= 6000; t += 16) {   // 0-3 s full-screen HDR video, then a page
        const int d = a.step(t, t < 3000, hdr);
        if (d > 0 && on < 0) { on = t; hdr = true; } if (d < 0 && off < 0) { off = t; hdr = false; }
    }
    AutoSwitch b; bool flick = false; bool h2 = true; b.step(0, true, true);
    for (int t = 16; t <= 3000; t += 16) if (b.step(t, !(t > 1000 && t < 1400), h2) != 0) flick = true;   // a 0.4 s overlay
    result(on >= 500 && on < 520 && off >= 2992 + 1500 && off < 2992 + 1520 && !flick, "L Auto: HDR on at %d ms (want 0.5 s), off at %d ms (want 1.5 s after), a 0.4 s gap does not switch", on, off);
    auto run = [](bool want, bool have, bool hdrOk, bool sdrOk, bool forced, bool& refused, bool& outHdr, int& calls) {
        calls = 0; refused = false; outHdr = false;
        return switchOutput(want, have, [&](bool h, bool* retired) { ++calls; if (h && forced) return false; *retired = have; return h ? hdrOk : sdrOk; }, refused, outHdr);
    };
    bool r, o; int c;
    const int a1 = run(true, false, true, true, false, r, o, c); const bool t1 = a1 == 1 && o && !r && c == 1;
    const int a2 = run(true, false, false, true, false, r, o, c); const bool t2 = a2 == 0 && !o && r && c == 2;
    const int a3 = run(true, true, false, true, false, r, o, c); const bool t3 = a3 == 0 && !o && r && c == 2;
    const int a4 = run(true, true, false, true, true, r, o, c); const bool t4 = a4 == 0 && !o && r && c == 1;
    const int a5 = run(true, true, false, false, false, r, o, c); const bool t5 = a5 == -1;
    const int a6 = run(false, true, true, true, false, r, o, c); const bool t6 = a6 == 1 && !o && !r;
    result(t1 && t2 && t3 && t4 && t5 && t6, "L swapchain fallback: HDR ok; HDR refused at start -> SDR; refused at a switch -> SDR again (old one retired); hdrfail -> SDR kept; both refused -> fatal; back to SDR ok");
}

int main(int argc, char** argv)
{
    const char* what = argc > 1 ? argv[1] : "all";
    const bool all = !strcmp(what, "all");
    char flag[] = "/tmp/omni-hdr-test-flag-XXXXXX"; const int fd = mkstemp(flag); if (fd >= 0) { (void)!write(fd, "noverify\n", 9); close(fd); }
    setenv("OMNI_GPU_FLAG", flag, 1);
    if (all || !strcmp(what, "L")) partL();
    if (all || !strcmp(what, "V") || !strcmp(what, "N")) {
        if (!OmniGpuVideo::preinit()) { printf("video preinit failed (no Vulkan?)\n"); return 2; }
        if (all || !strcmp(what, "V")) partV();
        if (all || !strcmp(what, "N")) partN(argc > 2 ? atoi(argv[2]) : 3000);
    }
    if (all || !strcmp(what, "P") || !strcmp(what, "Q")) {
        if (!omni_gpu_present_test_up()) { printf("present host device failed\n"); return 2; }
        if (all || !strcmp(what, "P")) partP();
        if (all || !strcmp(what, "Q")) partQ(argc > 2 ? atoi(argv[2]) : 3000);
    }
    unlink(flag);
    printf("RESULT %s (%d failed)\n", g_fail ? "FAIL" : "PASS", g_fail);
    return g_fail ? 1 : 0;
}
