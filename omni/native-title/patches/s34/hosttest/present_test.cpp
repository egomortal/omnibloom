// SPDX-License-Identifier: GPL-3.0-or-later
// omni-native-s3.2-video host test for OMNI_GPU_PRESENT_V2 (OmniGpuPresent.cpp built with OMNI_GPU_PRESENT_HOST_TEST): the
// same recordCompose the console runs, offscreen on lavapipe, against a CPU reference. Host timings are NOT PS5 figures.
//   P1  s2-gpu's 8 compose cases (frame import / staging, GPU hole-punch runs, letterboxed scale), with V2's caches
//   P2  staging mirror + damage rects: only damaged rows (and the video rectangle) are copied, the canvas stays exact;
//       a change outside every damaged area is caught by the differential check (negative control)
//   P3  HDR phase 2: the PQ pass's set-up check, and a composed frame with video through PQ vs the CPU reference
//   P4  10 000 presents: live Vulkan objects constant, layer cache bounded, imports once per layer / frame
// Usage: present_test [P1|P2|P3|P4|all]   (fallback: VK_ICD_FILENAMES=/nonexistent present_test F)
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cmath>
#include <vector>
#include <sys/mman.h>
#include <algorithm>
extern "C" long omni_gpu_present_test(const uint8_t*, int, int, int, const uint8_t*, size_t, int, int, int, int, int, const uint32_t*, size_t, int, int, uint8_t*, int, int*);
extern "C" void omni_gpu_present_test_counts(long*, long*, long*);
extern "C" void omni_gpu_present_test_damage(const int* rects, int n);
extern "C" long omni_gpu_present_test_hdr_selftest(int white, int* worst, long* off);
extern "C" void omni_gpu_present_test_hdr(int on, int white);
extern "C" long omni_gpu_present_test_pq_reference(uint8_t r, uint8_t g, uint8_t b, int white);
extern "C" void omni_gpu_present_test_cache(size_t*, uint64_t*, uint64_t*, uint64_t*, uint64_t*);
extern "C" void omni_gpu_present_test_teardown(long*, long*, long*);
extern "C" void omni_gpu_present_forget(const void*);
static uint8_t* amap(size_t n) { return (uint8_t*)mmap(nullptr, n, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0); }
static void unmap(uint8_t* p, size_t n) { omni_gpu_present_forget(p); munmap(p, n); }   // the title's rule: forget, then free
static long rssKiB() { long kb = 0; if (FILE* f = fopen("/proc/self/status", "r")) { char l[256]; while (fgets(l, sizeof l, f)) if (!strncmp(l, "VmRSS:", 6)) kb = atol(l + 6); fclose(f); } return kb; }

struct Scene {
    int w, h, pitch, lx, ly, lw, lh, stride; uint8_t* frame; uint8_t* layer; std::vector<uint32_t> runs;
    Scene(int w_, int h_, bool video, unsigned seed) : w(w_), h(h_), pitch(w_ * 4)
    {
        srand(seed);
        frame = amap(size_t(pitch) * h);
        for (int y = 0; y < h; ++y) for (int x = 0; x < w; ++x) { uint8_t* p = frame + size_t(y) * pitch + x * 4;
            p[0] = uint8_t(x * 255 / w); p[1] = uint8_t(y * 255 / h); p[2] = uint8_t((x ^ y) & 255); p[3] = (x / 64 + y / 64) % 3 ? 255 : 0; }
        lx = w / 8; ly = h / 6; lw = w * 3 / 4 - 1; lh = h * 2 / 3; stride = (lw + 15) / 16 * 16 * 4;
        layer = amap(size_t(stride) * lh);
        for (int y = 0; y < lh; ++y) for (int x = 0; x < lw; ++x) { uint8_t* p = layer + size_t(y) * stride + x * 4; p[0] = uint8_t(200 - x % 200); p[1] = uint8_t(rand()); p[2] = uint8_t(y % 251); p[3] = 255; }
        if (video) for (int y = ly; y < ly + lh; ++y) {   // a control-bar band left as page (no runs), and a 5-pixel gap
            if (y > ly + lh - 40) continue;
            runs.insert(runs.end(), { uint32_t(y), uint32_t(lx), uint32_t(lw / 2), uint32_t(y), uint32_t(lx + lw / 2 + 5), uint32_t(lw - lw / 2 - 5) });
        }
    }
    ~Scene() { unmap(frame, size_t(pitch) * h); unmap(layer, size_t(stride) * lh); }
    std::vector<uint8_t> canvas() const   // what the CPU present path shows
    {
        std::vector<uint8_t> c(size_t(w) * h * 4);
        for (int y = 0; y < h; ++y) memcpy(&c[size_t(y) * w * 4], frame + size_t(y) * pitch, size_t(w) * 4);
        for (size_t k = 0; k + 2 < runs.size(); k += 3) memcpy(&c[(size_t(runs[k]) * w + runs[k + 1]) * 4], layer + size_t(runs[k] - ly) * stride + size_t(runs[k + 1] - lx) * 4, size_t(runs[k + 2]) * 4);
        return c;
    }
    long present(int outW, int outH, std::vector<uint8_t>& out, int staging, int* released)
    {
        out.assign(size_t(outW) * outH * 4, 0);
        return omni_gpu_present_test(frame, pitch, w, h, runs.empty() ? nullptr : layer, size_t(stride) * lh, stride, lx, ly, lw, lh, runs.data(), runs.size(), outW, outH, out.data(), staging, released);
    }
};

static int partP1()
{
    struct Case { int w, h, outW, outH; bool video; int staging; };
    const Case cases[] = { {1920,1080,1920,1080,false,0}, {1920,1080,1920,1080,true,0}, {1920,1080,3840,2160,true,0}, {2560,1440,3840,2160,false,0},
                           {3840,2160,3840,2160,true,0}, {3840,2160,3840,2160,true,1}, {1920,1080,1920,1200,false,0}, {1280,720,3840,2160,true,1} };
    int fails = 0;
    for (const Case& c : cases) {
        Scene sc(c.w, c.h, c.video, 3);
        std::vector<uint8_t> out; int released = 0;
        const long bad = sc.present(c.outW, c.outH, out, c.staging, &released);
        const std::vector<uint8_t> canvas = sc.canvas();
        const double s = std::min(double(c.outW) / c.w, double(c.outH) / c.h); const int dw = int(std::lround(c.w * s)), dh = int(std::lround(c.h * s));
        const int dx = (c.outW - dw) / 2, dy = (c.outH - dh) / 2;
        double sum = 0; int worst = 0; size_t n = 0, over2 = 0;
        for (int y = 0; y < c.outH; ++y) for (int x = 0; x < c.outW; ++x) {
            uint8_t ref[4] = { 0, 0, 0, 255 };
            if (x >= dx && x < dx + dw && y >= dy && y < dy + dh) {
                const double u = (x - dx + 0.5) * c.w / dw - 0.5, v = (y - dy + 0.5) * c.h / dh - 0.5;
                if (dw == c.w && dh == c.h) memcpy(ref, &canvas[(size_t(y - dy) * c.w + (x - dx)) * 4], 4);
                else { const int x0 = int(std::floor(u)), y0 = int(std::floor(v)); const double fx = u - x0, fy = v - y0;
                    auto at = [&](int xx, int yy, int ch) { xx = std::clamp(xx, 0, c.w - 1); yy = std::clamp(yy, 0, c.h - 1); return double(canvas[(size_t(yy) * c.w + xx) * 4 + ch]); };
                    for (int ch = 0; ch < 4; ++ch) ref[ch] = uint8_t(std::lround((at(x0,y0,ch)*(1-fx)+at(x0+1,y0,ch)*fx)*(1-fy)+(at(x0,y0+1,ch)*(1-fx)+at(x0+1,y0+1,ch)*fx)*fy)); }
            }
            for (int ch = 0; ch < 4; ++ch) { const int e = abs(int(ref[ch]) - int(out[(size_t(y) * c.outW + x) * 4 + ch])); sum += e; worst = std::max(worst, e); over2 += e > 2; ++n; }
        }
        const bool scaled = dw != c.w || dh != c.h;
        const bool pass = bad == 0 && (scaled ? (sum / n < 0.6 && 100.0 * over2 / n < 1.0) : worst == 0) && (!c.video || released == 1);
        printf("P1 %dx%d -> %dx%d %s %s: composed canvas %s, output vs CPU: mean %.4f worst %d >2 %.3f%%, released %d -> %s\n", c.w, c.h, c.outW, c.outH,
               c.video ? "video" : "plain", c.staging ? "staging" : "import", bad == 0 ? "exact" : "DIFF", sum / n, worst, 100.0 * over2 / n, released, pass ? "PASS" : "FAIL");
        fails += !pass;
    }
    printf("P1 RESULT %s (%d failed)\n", fails ? "FAIL" : "PASS", fails);
    return fails;
}

// The staging mirror (import refused) copies only damaged rows: the shell's rect plus the video rectangle.
static int partP2()
{
    Scene sc(1920, 1080, true, 9);
    std::vector<uint8_t> out; int released = 0, fails = 0;
    uint64_t f0, r0, x; size_t l; omni_gpu_present_test_cache(&l, &x, &x, &f0, &r0);
    if (sc.present(1920, 1080, out, 1, &released) != 0) fails++;   // first: full copy
    for (int i = 0; i < 20; ++i) {
        const int y0 = (i * 97) % 1000, rows = 24;
        for (int y = y0; y < y0 + rows; ++y) for (int xx = 0; xx < sc.w; ++xx) sc.frame[size_t(y) * sc.pitch + xx * 4 + 1] ^= uint8_t(0x5a + i);   // the shell redraws a band
        for (int y = sc.ly + sc.lh - 30; y < sc.ly + sc.lh - 2; ++y) for (int xx = sc.lx; xx < sc.lx + 200; ++xx) sc.frame[size_t(y) * sc.pitch + xx * 4] = uint8_t(i * 11);   // mix pixels in the video rect, not in the rect list
        const int rect[4] = { 0, y0, sc.w, rows };
        omni_gpu_present_test_damage(rect, 1);
        if (sc.present(1920, 1080, out, 1, &released) != 0) fails++;
    }
    // negative control: a change outside the damage and the video rect must show up as a difference
    for (int xx = 0; xx < 16; ++xx) sc.frame[size_t(1070) * sc.pitch + xx * 4] ^= 0xff;
    const int rect[4] = { 0, 0, 8, 8 };
    omni_gpu_present_test_damage(rect, 1);
    const long caught = sc.present(1920, 1080, out, 1, &released);
    uint64_t f1, r1; omni_gpu_present_test_cache(&l, &x, &x, &f1, &r1);
    // and a full present repairs it
    const long repaired = sc.present(1920, 1080, out, 1, &released);
    const bool pass = !fails && caught == 1 && repaired == 0 && r1 - r0 == 21 && f1 - f0 >= 1;
    printf("P2 staging mirror, 20 damaged presents: %d differences, rect-only copies %llu, full copies %llu; undamaged change caught %s, full present repairs %s -> %s\n",
        fails, (unsigned long long)(r1 - r0), (unsigned long long)(f1 - f0), caught == 1 ? "yes" : "NO", repaired == 0 ? "yes" : "NO", pass ? "PASS" : "FAIL");
    return pass ? 0 : 1;
}

static int partP3()
{
    int worst = 0; long off = 0; int fails = 0;
    for (int white : { 203, 100, 300 }) {
        const long r = omni_gpu_present_test_hdr_selftest(white, &worst, &off);
        printf("P3 PQ pass set-up check, SDR white %d nits: %ld pixels off, worst %d codes -> %s\n", white, off, worst, r == 0 ? "PASS" : "FAIL");
        fails += r != 0;
    }
    omni_gpu_present_test_hdr(1, 203);
    Scene sc(640, 360, true, 5);
    std::vector<uint8_t> out; int released = 0;
    const long bad = sc.present(640, 360, out, 0, &released);
    const std::vector<uint8_t> canvas = sc.canvas();
    long diff = 0; int w2 = 0;
    for (size_t i = 0; i < size_t(sc.w) * sc.h; ++i) {
        const uint32_t want = uint32_t(omni_gpu_present_test_pq_reference(canvas[i * 4], canvas[i * 4 + 1], canvas[i * 4 + 2], 203));
        uint32_t got; memcpy(&got, &out[i * 4], 4);
        if (got != want) { ++diff; for (int s = 0; s < 30; s += 10) w2 = std::max(w2, std::abs(int((got >> s) & 1023) - int((want >> s) & 1023))); if ((got >> 30) != 3) w2 = 1024; }
    }
    omni_gpu_present_test_hdr(0, 203);
    const bool pass = bad == 0 && w2 <= 1;
    printf("P3 composed 640x360 frame + video runs through PQ (A2B10G10R10, 1:1): canvas %s, %ld of %d pixels differ from the CPU PQ reference, worst %d codes -> %s\n",
        bad == 0 ? "exact" : "DIFF", diff, sc.w * sc.h, w2, pass ? "PASS" : "FAIL");
    return fails + !pass;
}

static int partP4(int frames)
{
    std::vector<Scene*> scenes;
    for (int i = 0; i < 4; ++i) scenes.push_back(new Scene(320, 180, true, 20 + unsigned(i)));
    std::vector<uint8_t> out; int released = 0; long fails = 0;
    long b0 = 0, i0 = 0, m0 = 0, b1 = 0, i1 = 0, m1 = 0, bmax = 0; long rss0 = 0; size_t cmax = 0; int remaps = 0;
    uint64_t fh0 = 0, lh0 = 0, x;
    for (int f = 0; f < frames; ++f) {
        if (f % 2500 == 1250) { const int k = (f / 2500) % 4; delete scenes[k]; scenes[k] = new Scene(320, 180, true, 40 + unsigned(f)); remaps++; }   // frame + layer go and come back
        Scene& sc = *scenes[f % 4]; const Scene& surface = *scenes[0];   // one SDL surface (as in the title), 4 layers in turn
        out.assign(size_t(640) * 360 * 4, 0);
        if (omni_gpu_present_test(surface.frame, surface.pitch, surface.w, surface.h, sc.layer, size_t(sc.stride) * sc.lh, sc.stride, sc.lx, sc.ly, sc.lw, sc.lh,
                                  sc.runs.data(), sc.runs.size(), 640, 360, out.data(), 0, &released) != 0) fails++;
        long b, im, m; omni_gpu_present_test_counts(&b, &im, &m);
        size_t l; omni_gpu_present_test_cache(&l, &x, &x, &x, &x); cmax = std::max(cmax, l);
        if (f == 100) { b0 = b; i0 = im; m0 = m; rss0 = rssKiB(); size_t ll; omni_gpu_present_test_cache(&ll, &fh0, &lh0, &x, &x); }
        if (f > 100) bmax = std::max(bmax, b);
        b1 = b; i1 = im; m1 = m;
    }
    uint64_t fh1, lh1; size_t l; omni_gpu_present_test_cache(&l, &fh1, &lh1, &x, &x);
    const long rss1 = rssKiB();
    const bool pass = !fails && b1 <= b0 + 1 && bmax <= b0 + 1 && i1 == i0 && m1 <= m0 + 1 && cmax <= 16 && rss1 - rss0 < 8192;
    printf("P4 %d presents (%d frame+layer remaps): live buffers %ld -> %ld (max %ld), images %ld -> %ld, memory %ld -> %ld, cached layers max %zu, layer cache hits %llu, RSS %ld -> %ld KiB, differences %ld -> %s\n",
        frames, remaps, b0, b1, bmax, i0, i1, m0, m1, cmax, (unsigned long long)(lh1 - lh0), rss0, rss1, fails, pass ? "PASS" : "FAIL");
    for (Scene* s : scenes) delete s;
    omni_gpu_present_test_cache(&l, &x, &x, &x, &x);
    printf("P4 after the scenes are forgotten: %zu cached layers (want 0)\n", l);
    return pass && l == 0 ? 0 : 1;
}

int main(int argc, char** argv)
{
    const char* what = argc > 1 ? argv[1] : "all";
    if (!strcmp(what, "F")) {
        Scene sc(64, 36, true, 1); std::vector<uint8_t> out; int released = 0;
        const long r = sc.present(64, 36, out, 0, &released);
        printf("F no Vulkan ICD: compose returns %ld (want -1: the title keeps SDL's own present) -> %s\n", r, r == -1 ? "PASS" : "FAIL");
        return r == -1 ? 0 : 1;
    }
    int bad = 0;
    if (!strcmp(what, "P1") || !strcmp(what, "all")) bad += partP1();
    if (!strcmp(what, "P2") || !strcmp(what, "all")) bad += partP2();
    if (!strcmp(what, "P3") || !strcmp(what, "all")) bad += partP3();
    if (!strcmp(what, "P4") || !strcmp(what, "all")) bad += partP4(argc > 2 ? atoi(argv[2]) : 10000);
    long b = 0, i = 0, m = 0; omni_gpu_present_test_teardown(&b, &i, &m);
    printf("teardown: live buffers %ld images %ld memory %ld before the device goes (want 0 0 0)\n", b, i, m);
    if (b || i || m) bad++;
    printf("RESULT %s\n", bad ? "FAIL" : "PASS");
    return bad ? 1 : 0;
}
