// OMNI_TAB_THUMBS_V1 host test for OmniTabThumbs.h (pure part of tab thumbnails).
//   g++ -std=c++20 -O2 -Wall -Wextra -I<tools> test_tab_thumbs.cpp -o t && ./t
#include "OmniTabThumbs.h"
#include <chrono>
#include <cstdio>
#include <cstring>

namespace OTTH = OmniTabThumbs;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

// A w x h page in memory order B, G, R, A (bgra) or R, G, B, A.
struct Page {
    int w, h; bool bgra; std::vector<uint8_t> px;
    Page(int w_, int h_, bool b) : w(w_), h(h_), bgra(b), px(size_t(w_) * h_ * 4, 0) {}
    void set(int x, int y, unsigned r, unsigned g, unsigned b, unsigned a = 255)
    {
        uint8_t* p = px.data() + (size_t(y) * w + x) * 4;
        p[bgra ? 2 : 0] = uint8_t(r); p[1] = uint8_t(g); p[bgra ? 0 : 2] = uint8_t(b); p[3] = uint8_t(a);
    }
    void fill(unsigned r, unsigned g, unsigned b, unsigned a = 255) { for (int y = 0; y < h; ++y) for (int x = 0; x < w; ++x) set(x, y, r, g, b, a); }
    OTTH::Source src() const { OTTH::Source s; s.px = px.data(); s.stride = size_t(w) * 4; s.w = w; s.h = h; s.bgra = bgra; return s; }
};

static void testCrop()
{
    // the console's half-size page under the bars: 1920 x 975 is wider than 16:9 -> centred 1733 x 975
    OTTH::Crop c = OTTH::crop16x9(1920, 975);
    CHECK(c.h == 975 && c.w == 1733 && c.x == (1920 - 1733) / 2 && c.y == 0);
    c = OTTH::crop16x9(1920, 1080);   // exactly 16:9
    CHECK(c.x == 0 && c.y == 0 && c.w == 1920 && c.h == 1080);
    c = OTTH::crop16x9(800, 2000);    // tall: the top
    CHECK(c.x == 0 && c.y == 0 && c.w == 800 && c.h == 450);
    c = OTTH::crop16x9(0, 100);
    CHECK(c.w == 0 && c.h == 0);
    c = OTTH::crop16x9(1, 1);
    CHECK(c.w >= 1 && c.h >= 1 && c.x >= 0 && c.x + c.w <= 1 && c.y + c.h <= 1);
}

static void testSpread()
{
    std::vector<int> v = OTTH::spread(4, 8);
    CHECK(v.size() == 4 && v[0] == 1 && v[1] == 3 && v[2] == 5 && v[3] == 7);
    v = OTTH::spread(8, 4);   // enlarging: each source twice
    CHECK(v[0] == 0 && v[1] == 0 && v[2] == 1 && v[7] == 3);
    v = OTTH::spread(960, 1733);
    bool inside = true; for (int i : v) inside = inside && i >= 0 && i < 1733;
    CHECK(inside);
    CHECK(OTTH::spread(0, 10).empty());
}

static void testDownscale()
{
    std::vector<uint32_t> out(OTTH::kPixels, 0);
    // solid colour, both byte orders, both row counts
    for (int bg = 0; bg < 2; ++bg) for (int rows = 1; rows <= 2; ++rows) {
        Page p(640, 360, bg != 0); p.fill(200, 100, 50);
        CHECK(OTTH::downscale(p.src(), rows, OTTH::pack(0, 0, 0), out.data()));
        bool same = true; for (uint32_t q : out) same = same && q == OTTH::pack(200, 100, 50);
        CHECK(same);
    }
    // alpha 0 (the video hole-punch) -> the background; half alpha -> halfway
    {
        Page p(480, 270, true); p.fill(255, 255, 255, 0);
        CHECK(OTTH::downscale(p.src(), 2, OTTH::pack(0, 0, 0), out.data()));
        CHECK(out[0] == OTTH::pack(0, 0, 0) && out[OTTH::kPixels - 1] == OTTH::pack(0, 0, 0));
        p.fill(255, 255, 255, 128);
        CHECK(OTTH::downscale(p.src(), 2, OTTH::pack(0, 0, 0), out.data()));
        CHECK(OTTH::red(out[100]) == 128 && OTTH::green(out[100]) == 128 && OTTH::blue(out[100]) == 128);
        CHECK((out[100] >> 24) == 255);   // always opaque
    }
    // left half red, right half blue: the thumbnail splits in the middle (16:9 source, no crop)
    {
        Page p(960, 540, true);
        for (int y = 0; y < 540; ++y) for (int x = 0; x < 960; ++x) { if (x < 480) p.set(x, y, 255, 0, 0); else p.set(x, y, 0, 0, 255); }
        CHECK(OTTH::downscale(p.src(), 2, 0, out.data()));
        CHECK(out[size_t(60) * OTTH::kW + 10] == OTTH::pack(255, 0, 0));
        CHECK(out[size_t(60) * OTTH::kW + 230] == OTTH::pack(0, 0, 255));
        CHECK(out[size_t(60) * OTTH::kW + 119] == OTTH::pack(255, 0, 0) && out[size_t(60) * OTTH::kW + 120] == OTTH::pack(0, 0, 255));
    }
    // a wide page is cropped in the middle: columns outside the crop never show
    {
        Page p(1920, 975, true); p.fill(0, 255, 0);
        for (int y = 0; y < 975; ++y) for (int x = 0; x < 90; ++x) { p.set(x, y, 255, 0, 0); p.set(1919 - x, y, 255, 0, 0); }
        CHECK(OTTH::downscale(p.src(), 2, 0, out.data()));
        bool green = true; for (uint32_t q : out) green = green && q == OTTH::pack(0, 255, 0);
        CHECK(green);
    }
    // a tall page: only the top 16:9 shows
    {
        Page p(400, 1000, false); p.fill(10, 20, 30);
        for (int y = 225; y < 1000; ++y) for (int x = 0; x < 400; ++x) p.set(x, y, 250, 250, 250);
        CHECK(OTTH::downscale(p.src(), 2, 0, out.data()));
        bool top = true; for (uint32_t q : out) top = top && q == OTTH::pack(10, 20, 30);   // rows 225+ are below the crop
        CHECK(top);
    }
    // a row stride larger than the width (the engine's frame may pad): padding never read
    {
        const int w = 500, h = 300; const size_t stride = size_t(w) * 4 + 64;
        std::vector<uint8_t> buf(stride * h, 0xEE);
        for (int y = 0; y < h; ++y) for (int x = 0; x < w; ++x) { uint8_t* q = buf.data() + y * stride + x * 4; q[0] = 9; q[1] = 8; q[2] = 7; q[3] = 255; }
        OTTH::Source s; s.px = buf.data(); s.stride = stride; s.w = w; s.h = h; s.bgra = true;
        CHECK(OTTH::downscale(s, 1, 0, out.data()));
        bool ok = true; for (uint32_t q : out) ok = ok && q == OTTH::pack(7, 8, 9);
        CHECK(ok);
    }
    // unusable sources leave `out` alone
    {
        std::fill(out.begin(), out.end(), 0x12345678u);
        OTTH::Source s;
        CHECK(!OTTH::downscale(s, 2, 0, out.data()));
        Page p(10, 10, true); OTTH::Source t = p.src(); t.stride = 8;
        CHECK(!OTTH::downscale(t, 2, 0, out.data()));
        CHECK(out[0] == 0x12345678u);
    }
    // tiny pages still fill the whole thumbnail
    {
        Page p(3, 2, true); p.fill(1, 2, 3);
        CHECK(OTTH::downscale(p.src(), 2, 0, out.data()));
        CHECK(out[OTTH::kPixels - 1] == OTTH::pack(1, 2, 3));
    }
}

static void testGrey()
{
    const uint32_t g = OTTH::grey(OTTH::pack(255, 255, 255));
    CHECK(OTTH::red(g) == OTTH::green(g) && OTTH::green(g) == OTTH::blue(g) && OTTH::red(g) < 255 && OTTH::red(g) > 150);
    CHECK(OTTH::red(OTTH::grey(OTTH::pack(0, 0, 0))) == 40);
    CHECK((OTTH::grey(OTTH::pack(9, 9, 9)) >> 24) == 255);
}

static void testZc()
{
    CHECK(OTTH::inBrokerWindow(0x240000000ull, 1920ull * 1080 * 4));
    CHECK(OTTH::inBrokerWindow(0x3000000000ull + (1ull << 30), 8ull << 20));
    CHECK(!OTTH::inBrokerWindow(0x240000000ull - 4, 64));
    CHECK(!OTTH::inBrokerWindow(0x240000000ull + (512ull << 20) - 16, 64));   // runs past the window's end
    CHECK(!OTTH::inBrokerWindow(0x7f0000000000ull, 64));
    CHECK(!OTTH::inBrokerWindow(0x240000000ull, ~0ull));
    CHECK(OTTH::zcUsable(5, 0x240000000ull, 1920, 1080, 1920 * 4));
    CHECK(!OTTH::zcUsable(0, 0x240000000ull, 1920, 1080, 1920 * 4));
    CHECK(!OTTH::zcUsable(5, 0, 1920, 1080, 1920 * 4));
    CHECK(!OTTH::zcUsable(5, 0x240000000ull, 1920, 1080, 1920 * 4 - 4));
    CHECK(!OTTH::zcUsable(5, 0x240000000ull, 1920, 1080, 1920 * 4 + 2));
    CHECK(!OTTH::zcUsable(5, 0x100000ull, 1920, 1080, 1920 * 4));
    CHECK(OTTH::frameKept(10, 10) && OTTH::frameKept(10, 11));
    CHECK(!OTTH::frameKept(10, 12) && !OTTH::frameKept(10, 9));
}

static void testStore()
{
    OTTH::Store s;
    int tabs[20];
    CHECK(!s.put(&tabs[0], std::vector<uint32_t>(10)));   // wrong size
    CHECK(!s.put(nullptr, std::vector<uint32_t>(OTTH::kPixels)));
    CHECK(s.size() == 0 && s.bytes() == 0);
    for (int i = 0; i < 20; ++i) CHECK(s.put(&tabs[i], std::vector<uint32_t>(OTTH::kPixels, uint32_t(i))));
    CHECK(s.size() == size_t(OTTH::kMax));
    CHECK(s.bytes() == OTTH::kMaxBytes && OTTH::kMaxBytes == 2073600);
    CHECK(!s.find(&tabs[0]) && !s.find(&tabs[3]) && s.find(&tabs[4]) && s.find(&tabs[19]));   // the 4 oldest went
    // a new capture of an old tab refreshes it: it is no longer the oldest
    CHECK(s.put(&tabs[4], std::vector<uint32_t>(OTTH::kPixels, 44u)));
    CHECK(s.size() == size_t(OTTH::kMax) && s.find(&tabs[4])->px[0] == 44u);
    CHECK(s.put(&tabs[0], std::vector<uint32_t>(OTTH::kPixels, 0u)));
    CHECK(s.find(&tabs[4]) && !s.find(&tabs[5]));   // tab 5 was the oldest now
    s.forget(&tabs[4]);
    CHECK(!s.find(&tabs[4]) && s.size() == size_t(OTTH::kMax) - 1);
    s.forget(&tabs[4]);   // twice: nothing
    CHECK(s.size() == size_t(OTTH::kMax) - 1);
    s.prune([&](const void* t) { return t != &tabs[19] && t != &tabs[0]; });
    CHECK(!s.find(&tabs[19]) && !s.find(&tabs[0]) && s.size() == size_t(OTTH::kMax) - 3);
    s.prune([](const void*) { return false; });
    CHECK(s.size() == 0 && s.bytes() == 0);
}

// Capture cost on this host: the console's half-size page (1920 x 975, under the bars) and the 4K page buffer.
static void bench()
{
    std::vector<uint32_t> out(OTTH::kPixels);
    struct Case { int w, h, rows; const char* what; } cases[] = {
        { 1920, 975, 2, "half-size page, 2 rows" }, { 3840, 1950, 2, "4K page buffer, 2 rows" }, { 1920, 975, 1, "zero-copy frame, 1 row" } };
    for (const Case& c : cases) {
        Page p(c.w, c.h, true);
        for (int y = 0; y < c.h; ++y) for (int x = 0; x < c.w; ++x) p.set(x, y, unsigned(x), unsigned(y), unsigned(x ^ y), (x % 97) ? 255 : 0);
        double best = 1e9;
        for (int k = 0; k < 20; ++k) {
            const auto t0 = std::chrono::steady_clock::now();
            OTTH::downscale(p.src(), c.rows, 0, out.data());
            best = std::min(best, std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count());
        }
        std::printf("bench %-26s %dx%d: %.3f ms\n", c.what, c.w, c.h, best);
        CHECK(best < 2.0);
    }
}

int main()
{
    testCrop(); testSpread(); testDownscale(); testGrey(); testZc(); testStore(); bench();
    std::printf("%d checks, %d failed\n", checks, fails);
    return fails ? 1 : 0;
}
