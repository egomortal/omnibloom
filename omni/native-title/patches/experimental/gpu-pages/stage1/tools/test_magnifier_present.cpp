// SPDX-License-Identifier: GPL-3.0-or-later
// OMNI_MAGNIFIER_V1 host test of the title side (tools/apply_magnifier_present.py): OmniGpuPresent.cpp built with
// OMNI_GPU_PRESENT_HOST_TEST runs the console's recordCompose offscreen on lavapipe; the composed (1:1) output is compared
// with a CPU reference of omni_magnifier.comp (same geometry, same float math). Host timings mean nothing here.
//   G1 off: output == frame exactly (no pass)
//   G2 2x lens mid-canvas: inside the ring every pixel is the nearest source pixel (exact), outside the lens rect the
//      frame is untouched (exact), the whole canvas matches the reference (+-2 on the anti-aliased edge)
//   G3 3x                          G4 near the bottom-right corner: lens kept on the canvas, still exact inside
//   G5 hole-punch video runs under the lens are magnified (the run colour appears 2x as wide)
//   G6 with Night light (when the title has it): the lens shows the TINTED page
//   G7 read-back (verify) frames: no lens, exact     G8 300 moving-lens presents: no new objects; off again: exact
//   G8c (r2) a bigger lens grows the buffer after the previous frame's fence: still drawn, no leak, the pass stays on
//   G9 teardown: no live objects
// Build (WSL): clang++ -std=c++17 -O2 -Wall -Wextra -DOMNI_GPU_PRESENT_HOST_TEST -isystem <PS5_Mesa/include> -I<src>
//   test_magnifier_present.cpp <src>/OmniGpuPresent.cpp -l:libvulkan.so.1 -pthread
// Run: VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.json ./a.out
#include <algorithm>
#include <cmath>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
extern "C" long omni_gpu_present_test(const uint8_t*, int, int, int, const uint8_t*, size_t, int, int, int, int, int, const uint32_t*, size_t, int, int, uint8_t*, int, int*);
extern "C" void omni_gpu_present_test_counts(long*, long*, long*);
extern "C" void omni_gpu_present_test_readback(int on);
extern "C" void omni_gpu_present_test_teardown(long*, long*, long*);
extern "C" int omni_gpu_present_lens(const float* p);
extern "C" int omni_gpu_present_lens_ready(void);
extern "C" int omni_gpu_present_night(const float* m) __attribute__((weak));

static int fails = 0;
static void check(bool ok, const char* name, const char* fmt = "", ...) __attribute__((format(printf, 3, 4)));
static void check(bool ok, const char* name, const char* fmt, ...)
{
    char b[512] = ""; va_list a; va_start(a, fmt); vsnprintf(b, sizeof b, fmt, a); va_end(a);
    printf("%s %s -> %s\n", name, b, ok ? "PASS" : "FAIL"); if (!ok) ++fails;
}

// --- CPU mirror of mgGeometry + omni_magnifier.comp ---------------------------------------------------------------
struct Geom { int sx0, sy0, sw, sh, dx0, dy0, dw, dh; float cx, cy, hw, hh, px, py, zoom, corner, ringW, arm, gap, thick; };
static Geom geometry(const float* q, int w, int h)
{
    Geom o {}; const float H = float(h);
    o.zoom = std::min(std::max(q[2], 1.0f), 8.0f);
    o.hw = std::min(std::max(q[3] * H, 8.0f), w * 0.5f); o.hh = std::min(std::max(q[4] * H, 8.0f), h * 0.5f);
    o.corner = std::min(std::max(q[5] * H, 0.0f), std::min(o.hw, o.hh));
    o.ringW = std::min(std::max(q[6] * H, 0.0f), std::min(o.hw, o.hh) * 0.5f);
    o.arm = std::max(q[7] * H, 0.0f);
    o.gap = std::max(1.0f, std::floor(o.arm * 0.34f)); o.thick = std::max(0.5f, std::floor(o.arm * 0.12f) + 0.5f);
    if (o.arm < 3.0f) o.arm = 0;
    o.px = std::min(std::max(q[0], 0.0f), 1.0f) * float(w); o.py = std::min(std::max(q[1], 0.0f), 1.0f) * float(h);
    o.cx = std::min(std::max(o.px, o.hw), float(w) - o.hw); o.cy = std::min(std::max(o.py, o.hh), float(h) - o.hh);
    o.dx0 = std::max(0, int(std::floor(o.cx - o.hw))); o.dy0 = std::max(0, int(std::floor(o.cy - o.hh)));
    o.dw = std::min(w, int(std::ceil(o.cx + o.hw))) - o.dx0; o.dh = std::min(h, int(std::ceil(o.cy + o.hh))) - o.dy0;
    return o;
}
static float sdist(const Geom& o, float dx, float dy)
{
    const float qx = std::fabs(dx) - (o.hw - o.corner), qy = std::fabs(dy) - (o.hh - o.corner);
    return std::hypot(std::max(qx, 0.0f), std::max(qy, 0.0f)) + std::min(std::max(qx, qy), 0.0f) - o.corner;
}
static uint8_t q8(float v) { return uint8_t(std::lround(std::min(std::max(v, 0.0f), 1.0f) * 255.0f)); }
enum Kind { kOutsideRect, kUntouched, kInterior, kOther };
struct Ref { uint8_t px[4]; Kind kind; int altX, altY; int sx, sy; };
// The reference pixel at (x, y) of the composed canvas `in`. Interior pixels name their source pixel (and, when
// the source coordinate is within 1e-3 of a pixel edge, the neighbour the GPU may round to).
static Ref reference(const Geom& o, const std::vector<uint8_t>& in, int w, int h, int x, int y)
{
    Ref r {}; memcpy(r.px, &in[(size_t(y) * w + x) * 4], 4); r.kind = kUntouched; r.altX = r.altY = -1;
    if (x < o.dx0 || y < o.dy0 || x >= o.dx0 + o.dw || y >= o.dy0 + o.dh) { r.kind = kOutsideRect; return r; }
    const float dx = float(x) + 0.5f - o.cx, dy = float(y) + 0.5f - o.cy, dist = sdist(o, dx, dy);
    const float cov = std::min(std::max(0.5f - dist, 0.0f), 1.0f);
    if (cov <= 0) return r;
    float c[4], u[4];
    for (int k = 0; k < 4; ++k) u[k] = r.px[k] / 255.0f;
    const double fx = double(o.px) + double(dx) / o.zoom, fy = double(o.py) + double(dy) / o.zoom;
    const int sx = int(std::floor(fx)), sy = int(std::floor(fy));
    r.sx = sx; r.sy = sy;
    auto near = [](double f) { const double fr = f - std::floor(f); return fr < 1e-3 || fr > 1 - 1e-3; };
    r.altX = near(fx) ? int(std::floor(fx + (fx - std::floor(fx) < 0.5 ? -0.5 : 0.5))) : sx;
    r.altY = near(fy) ? int(std::floor(fy + (fy - std::floor(fy) < 0.5 ? -0.5 : 0.5))) : sy;
    if (sx < 0 || sy < 0 || sx >= w || sy >= h) { c[0] = c[1] = c[2] = 0.094f; c[3] = 1; }
    else for (int k = 0; k < 4; ++k) c[k] = in[(size_t(sy) * w + sx) * 4 + k] / 255.0f;
    bool cross = false;
    if (o.arm > 0) {
        const float ax = std::fabs(dx), ay = std::fabs(dy), L = o.arm, g = o.gap, t = o.thick;
        const bool core = (ay <= t && ax >= g && ax <= L) || (ax <= t && ay >= g && ay <= L);
        const bool edge = (ay <= t + 1 && ax >= g - 1 && ax <= L + 1) || (ax <= t + 1 && ay >= g - 1 && ay <= L + 1);
        if (core) { c[0] = c[1] = c[2] = 0.96f; c[3] = 1; } else if (edge) { c[0] = c[1] = c[2] = 0.07f; c[3] = 1; }
        cross = std::fabs(dx) <= L + 2 && std::fabs(dy) <= L + 2;
    }
    const float bw = o.ringW;
    const float a1 = std::min(std::max(dist + bw + 0.5f, 0.0f), 1.0f), a2 = std::min(std::max(dist + bw * 0.35f + 0.5f, 0.0f), 1.0f);
    for (int k = 0; k < 4; ++k) {
        float v = c[k] + ((k < 3 ? 0.96f : 1.0f) - c[k]) * a1;
        v = v + ((k < 3 ? 0.07f : 1.0f) - v) * a2;
        r.px[k] = q8(u[k] + (v - u[k]) * cov);
    }
    r.kind = (dist < -bw - 1.0f && !cross) ? kInterior : kOther;
    return r;
}
struct Cmp { int worst = 0, interiorBad = 0, outsideBad = 0, interior = 0; };
static Cmp compare(const float* q, const std::vector<uint8_t>& in, const std::vector<uint8_t>& out, int w, int h)
{
    const Geom o = geometry(q, w, h);
    Cmp m;
    for (int y = 0; y < h; ++y) for (int x = 0; x < w; ++x) {
        const Ref r = reference(o, in, w, h, x, y);
        const uint8_t* g = &out[(size_t(y) * w + x) * 4];
        if (r.kind == kOutsideRect || r.kind == kUntouched) { if (memcmp(g, r.px, 4)) ++m.outsideBad; continue; }
        if (r.kind == kInterior) {
            ++m.interior;
            bool ok = !memcmp(g, r.px, 4);
            for (int ay : { r.sy, r.altY }) for (int ax : { r.sx, r.altX })
                if (!ok && ax >= 0 && ay >= 0 && ax < w && ay < h) ok = !memcmp(g, &in[(size_t(ay) * w + ax) * 4], 4);
            if (!ok) ++m.interiorBad;
            continue;
        }
        for (int k = 0; k < 4; ++k) m.worst = std::max(m.worst, std::abs(int(g[k]) - int(r.px[k])));
    }
    return m;
}

int main()
{
    const int W = 640, H = 360;   // 16:9 like the console canvas (1/3 of 1080p)
    std::vector<uint8_t> frame(size_t(W) * H * 4), out(frame.size());
    for (int y = 0; y < H; ++y) for (int x = 0; x < W; ++x) {   // fine detail: neighbours differ, so a wrong source pixel shows
        uint8_t* p = &frame[(size_t(y) * W + x) * 4];
        p[0] = uint8_t(x * 255 / (W - 1)); p[1] = uint8_t(y * 255 / (H - 1)); p[2] = uint8_t((x * 37 + y * 101) & 255); p[3] = (x + y) % 7 ? 255 : 128;
    }
    auto present = [&](const uint8_t* layer = nullptr, size_t lb = 0, const std::vector<uint32_t>* runs = nullptr) {
        int released = 0;
        return omni_gpu_present_test(frame.data(), W * 4, W, H, layer, lb, W * 4, 0, 0, W, H, runs ? runs->data() : nullptr,
                                     runs ? runs->size() : 0, W, H, out.data(), 0, layer ? &released : nullptr);
    };
    omni_gpu_present_test_readback(0);   // console frames (no verify)

    // G1: off
    long r = present();
    check(r == 0 && out == frame, "G1", "off: output == frame (r=%ld)", r);

    // the shell's wide lens (OmniMagnifier.h kWide): 560 x 220 of 1280 x 720, corner 26, ring 4, crosshair 9
    const float hw = 280.0f / 720, hh = 110.0f / 720, cr = 26.0f / 720, ring = 4.0f / 720, arm = 9.0f / 720;
    // G2: 2x, pointer mid-canvas (a non-integer canvas position)
    float lens2[8] = { 0.4f, 0.47f, 2.0f, hw, hh, cr, ring, arm };
    omni_gpu_present_lens(lens2);
    r = present();
    Cmp c2 = compare(lens2, frame, out, W, H);
    check(r == 0 && c2.interiorBad == 0 && c2.outsideBad == 0 && c2.worst <= 2 && c2.interior > 1000, "G2",
          "2x: %d interior pixels (%d wrong), outside differs %d, edge worst %d (<= 2)", c2.interior, c2.interiorBad, c2.outsideBad, c2.worst);
    const Geom o2 = geometry(lens2, W, H);
    { // the pixel right of the crosshair's arm is the source pixel 1 / zoom away: magnified, not just copied
        const int x = int(o2.cx + o2.arm + 6), y = int(o2.cy);
        const int sx = int(std::floor(o2.px + (x + 0.5f - o2.cx) / 2.0f)), sy = int(std::floor(o2.py + (y + 0.5f - o2.cy) / 2.0f));
        check(!memcmp(&out[(size_t(y) * W + x) * 4], &frame[(size_t(sy) * W + sx) * 4], 4) && sx != x, "G2b",
              "canvas (%d,%d) shows source (%d,%d)", x, y, sx, sy);
    }
    long b1, i1, m1; omni_gpu_present_test_counts(&b1, &i1, &m1);

    // G3: 3x
    float lens3[8] = { 0.55f, 0.52f, 3.0f, hw, hh, cr, ring, arm };
    omni_gpu_present_lens(lens3);
    r = present();
    Cmp c3 = compare(lens3, frame, out, W, H);
    check(r == 0 && c3.interiorBad == 0 && c3.outsideBad == 0 && c3.worst <= 2, "G3",
          "3x: %d interior (%d wrong), outside differs %d, edge worst %d", c3.interior, c3.interiorBad, c3.outsideBad, c3.worst);

    // G4: pointer in the bottom-right corner: the lens stays on the canvas; the source past the edge is dark grey
    float lens4[8] = { 0.995f, 0.99f, 2.0f, hw, hh, cr, ring, arm };
    omni_gpu_present_lens(lens4);
    r = present();
    Cmp c4 = compare(lens4, frame, out, W, H);
    const Geom o4 = geometry(lens4, W, H);
    const uint8_t* dark = &out[(size_t(H - 12) * W + (W - 12)) * 4];
    check(r == 0 && c4.interiorBad == 0 && c4.outsideBad == 0 && c4.worst <= 2 && o4.dx0 + o4.dw == W && o4.dy0 + o4.dh == H
          && dark[0] == 24 && dark[1] == 24 && dark[2] == 24, "G4",
          "corner: lens %d,%d %dx%d inside %dx%d, interior wrong %d, outside differs %d, past-the-edge grey %d", o4.dx0, o4.dy0, o4.dw, o4.dh, W, H,
          c4.interiorBad, c4.outsideBad, int(dark[0]));

    // G5: video runs (rows 140..159, x 240..259 in a solid colour) under a 2x lens centred on them are magnified
    std::vector<uint8_t> layer(size_t(W) * H * 4);
    for (size_t i = 0; i < layer.size(); i += 4) { layer[i] = 40; layer[i + 1] = 200; layer[i + 2] = 230; layer[i + 3] = 255; }
    std::vector<uint32_t> runs; for (uint32_t y = 140; y < 160; ++y) { runs.push_back(y); runs.push_back(240); runs.push_back(20); }
    float lens5[8] = { 250.0f / W, 150.0f / H, 2.0f, hw, hh, cr, ring, 0.0f };   // no crosshair: the whole middle is video
    omni_gpu_present_lens(lens5);
    r = present(layer.data(), layer.size(), &runs);
    std::vector<uint8_t> composed(frame);
    for (int y = 140; y < 160; ++y) memcpy(&composed[(size_t(y) * W + 240) * 4], &layer[(size_t(y) * W + 240) * 4], 20 * 4);
    Cmp c5 = compare(lens5, composed, out, W, H);
    int videoWide = 0; for (int x = 0; x < W; ++x) { const uint8_t* p = &out[(size_t(150) * W + x) * 4]; videoWide += p[0] == 40 && p[1] == 200 && p[2] == 230; }
    check(r == 0 && c5.interiorBad == 0 && c5.outsideBad == 0 && videoWide == 40, "G5",
          "video magnified: %d video pixels on row 150 (40 = 20 x 2), interior wrong %d, outside differs %d", videoWide, c5.interiorBad, c5.outsideBad);

    // G6: Night light first (when this title has it): the lens magnifies the tinted canvas
    if (omni_gpu_present_night) {
        const float warm[9] = { 1.0f, 0, 0, 0, 0.74f, 0, 0, 0, 0.36f };
        omni_gpu_present_night(warm);
        omni_gpu_present_lens(lens2);
        present(); r = present();   // the first tinted frame arms the tint (canvas remade with STORAGE usage)
        std::vector<uint8_t> tinted(frame);
        for (size_t i = 0; i < tinted.size(); i += 4)
            for (int k = 0; k < 3; ++k) tinted[i + k] = q8(warm[k * 4] * (frame[i + k] / 255.0f));
        Cmp c6 = compare(lens2, tinted, out, W, H);
        // the tint's own rounding may differ by 1 from this reference: count interior pixels off by more than 1
        const Geom o = geometry(lens2, W, H); int bad = 0, n = 0;
        for (int y = o.dy0; y < o.dy0 + o.dh; ++y) for (int x = o.dx0; x < o.dx0 + o.dw; ++x) {
            const Ref rr = reference(o, tinted, W, H, x, y);
            if (rr.kind != kInterior) continue;
            ++n; const uint8_t* g = &out[(size_t(y) * W + x) * 4];
            const uint8_t* want = &tinted[(size_t(rr.sy) * W + rr.sx) * 4];
            bool ok = true; for (int k = 0; k < 4; ++k) if (std::abs(int(g[k]) - int(want[k])) > 1) ok = false;
            if (!ok) { const uint8_t* alt = &tinted[(size_t(rr.altY) * W + rr.altX) * 4]; ok = true; for (int k = 0; k < 4; ++k) if (std::abs(int(g[k]) - int(alt[k])) > 1) ok = false; }
            bad += !ok;
        }
        check(r == 0 && bad == 0 && n > 1000 && c6.worst <= 3, "G6", "lens after the tint: %d interior pixels, %d not the tinted source (+-1), edge worst %d", n, bad, c6.worst);
        omni_gpu_present_night(nullptr);
        present();
    } else {
        printf("G6 skipped: this OmniGpuPresent.cpp has no Night light pass\n");
    }

    // G7: read-back frames are not magnified
    omni_gpu_present_lens(lens2);
    omni_gpu_present_test_readback(1);
    r = present();
    check(r == 0 && out == frame, "G7", "verify frame: no lens, differential check %s", r == 0 ? "exact" : "differs");
    omni_gpu_present_test_readback(0);

    // G8: a lens sweeping over the canvas (2x / 3x alternating) makes no per-frame objects; off again is exact
    present();
    long b2, i2, m2; omni_gpu_present_test_counts(&b2, &i2, &m2);
    for (int k = 0; k < 300; ++k) {
        const float u = 0.02f + 0.96f * float((k * 37) % 300) / 299.0f, v = 0.03f + 0.94f * float((k * 53) % 300) / 299.0f;
        const float q[8] = { u, v, k % 2 ? 3.0f : 2.0f, hw, hh, cr, ring, arm };
        omni_gpu_present_lens(q); present();
    }
    long b3, i3, m3; omni_gpu_present_test_counts(&b3, &i3, &m3);
    check(b3 == b2 && i3 == i2 && m3 == m2, "G8a", "300 moving lenses: buffers %ld->%ld images %ld->%ld memory %ld->%ld (first lens frame: %ld/%ld/%ld)",
          b2, b3, i2, i3, m2, m3, b1, i1, m1);
    // G8c (OMNI_MAGNIFIER_V1_R2): a bigger lens grows the buffer; the old one is freed after the previous frame's fence
    // (signalled: the present waited on it) and the new one is bound even when it gets the old handle's value, so the
    // lens is exact again (twice: the frame that grew and the next), nothing leaks and the pass is not switched off
    const float big[8] = { 0.5f, 0.5f, 2.0f, hw * 1.6f, hh * 1.8f, cr, ring, arm };
    omni_gpu_present_lens(big);
    for (int k = 0; k < 2; ++k) {
        r = present();
        const Cmp cb = compare(big, frame, out, W, H);
        long b4, i4, m4; omni_gpu_present_test_counts(&b4, &i4, &m4);
        check(r == 0 && cb.interior > 30000 && cb.interiorBad == 0 && cb.outsideBad == 0 && cb.worst <= 2 && b4 == b3 && m4 == m3, "G8c",
              "grown lens (frame %d): %d interior (%d wrong), outside differs %d, edge worst %d, buffers %ld->%ld memory %ld->%ld",
              k + 1, cb.interior, cb.interiorBad, cb.outsideBad, cb.worst, b3, b4, m3, m4);
    }
    omni_gpu_present_lens(nullptr);
    r = present();
    check(r == 0 && out == frame, "G8b", "off again: output == frame");
    long tb, ti, tm; omni_gpu_present_test_teardown(&tb, &ti, &tm);
    check(tb == 0 && ti == 0 && tm == 0, "G9", "teardown: live buffers %ld images %ld memory %ld", tb, ti, tm);
    printf("%s (%d failed)\n", fails ? "FAIL" : "ALL PASS", fails);
    return fails ? 1 : 0;
}
