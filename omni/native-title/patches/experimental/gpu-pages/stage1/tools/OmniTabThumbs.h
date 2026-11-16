// OMNI_TAB_THUMBS_V1: the pure part of tab thumbnails (a 240 x 135 snapshot of each tab, taken when the user switches
// away from it). No SDL, no WebKit. The shell side is OmniTabThumbsShell.h; the reasons are in tools/apply_tab_thumbs.py.
// Tested on the host with g++ (tools/test_tab_thumbs.cpp).
#pragma once
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <utility>
#include <vector>

namespace OmniTabThumbs {

constexpr int kW = 240, kH = 135;                       // stored thumbnail (pixels, 16:9)
constexpr size_t kPixels = size_t(kW) * kH;
constexpr int kMax = 16;                                // thumbnails kept at most: 16 x 240 x 135 x 4 = 2 073 600 bytes
constexpr size_t kMaxBytes = size_t(kMax) * kPixels * 4;
constexpr int kRowW = 64, kRowH = 36;                   // layout px in a panel row (Tabs, Tab memory)
constexpr int kTileW = 134, kTileH = 75;                // layout px in a quick tab switcher tile

// --- source rectangle ------------------------------------------------------------------------------------------------
struct Crop { int x = 0, y = 0, w = 0, h = 0; };
// The largest 16:9 part of a w x h page: the top of a tall page, the middle of a wide one (a page under the bars is
// wider than 16:9: about 5 % comes off each side).
inline Crop crop16x9(int w, int h)
{
    Crop c;
    if (w <= 0 || h <= 0) return c;
    if (int64_t(w) * 9 > int64_t(h) * 16) {   // wider than 16:9
        c.h = h;
        c.w = std::max(1, int(int64_t(h) * 16 / 9));
        c.x = (w - c.w) / 2;
    } else {
        c.w = w;
        c.h = std::max(1, int(int64_t(w) * 9 / 16));
    }
    return c;
}
// The source index of each of `dst` evenly spread samples over `src` (sample centres).
inline std::vector<int> spread(int dst, int src)
{
    std::vector<int> v(size_t(std::max(dst, 0)));
    for (int i = 0; i < dst; ++i) v[size_t(i)] = src <= 0 ? 0 : int((int64_t(2 * i + 1) * src) / (int64_t(2) * dst));
    return v;
}

// --- downscale -------------------------------------------------------------------------------------------------------
// Canvas order (SDL ABGR8888 in memory: R, G, B, A) packed into a uint32_t on a little-endian CPU.
inline uint32_t pack(unsigned r, unsigned g, unsigned b) { return 0xff000000u | (b << 16) | (g << 8) | r; }
inline unsigned red(uint32_t p) { return p & 0xff; }
inline unsigned green(uint32_t p) { return (p >> 8) & 0xff; }
inline unsigned blue(uint32_t p) { return (p >> 16) & 0xff; }
struct Source {
    const uint8_t* px = nullptr;   // first byte of the page's first row
    size_t stride = 0;             // bytes per row
    int w = 0, h = 0;              // pixels
    bool bgra = true;              // memory order B, G, R, A (WKPagePaint's ARGB8888, the engine's zero-copy frame); else R, G, B, A
};
// Box-filters the 16:9 crop of `s` into kW x kH opaque pixels: per thumbnail pixel, `rows` source rows (1 or 2) x 4
// columns spread over its cell, each blended over `bg` by its alpha (the video hole-punch leaves alpha 0: black). Reads
// kW x kH x 4 x rows pixels whatever the page size. false (out untouched) when the source is unusable.
inline bool downscale(const Source& s, int rows, uint32_t bg, uint32_t* out)
{
    if (!s.px || !out || s.w <= 0 || s.h <= 0 || s.stride < size_t(s.w) * 4) return false;
    rows = std::clamp(rows, 1, 2);
    const Crop c = crop16x9(s.w, s.h);
    const std::vector<int> xs = spread(kW * 4, c.w), ys = spread(kH * rows, c.h);
    const int ri = s.bgra ? 2 : 0, bi = s.bgra ? 0 : 2;
    const unsigned br = red(bg), bgc = green(bg), bb = blue(bg);
    const unsigned n = 4u * unsigned(rows);
    for (int oy = 0; oy < kH; ++oy) {
        const uint8_t* line[2];
        for (int k = 0; k < rows; ++k) line[k] = s.px + size_t(c.y + ys[size_t(oy * rows + k)]) * s.stride + size_t(c.x) * 4;
        uint32_t* o = out + size_t(oy) * kW;
        for (int ox = 0; ox < kW; ++ox) {
            unsigned r = 0, g = 0, b = 0;
            for (int k = 0; k < rows; ++k) {
                for (int j = 0; j < 4; ++j) {
                    const uint8_t* p = line[k] + size_t(xs[size_t(ox * 4 + j)]) * 4;
                    const unsigned a = p[3];
                    if (a == 255) { r += p[ri]; g += p[1]; b += p[bi]; continue; }
                    const unsigned na = 255 - a;
                    r += (p[ri] * a + br * na + 127) / 255;
                    g += (p[1] * a + bgc * na + 127) / 255;
                    b += (p[bi] * a + bb * na + 127) / 255;
                }
            }
            o[ox] = pack((r + n / 2) / n, (g + n / 2) / n, (b + n / 2) / n);
        }
    }
    return true;
}
// An unloaded (asleep) tab's thumbnail: grey and dimmed.
inline uint32_t grey(uint32_t p)
{
    const unsigned l = (red(p) * 77 + green(p) * 150 + blue(p) * 29) >> 8;
    const unsigned v = 40 + l * 5 / 8;
    return pack(v, v, v);
}

// --- the engine's zero-copy frame (OMNI_GPUPAGES_ZEROCOPY_V1) -------------------------------------------------------------
// The broker's host windows (gpu-broker/protocol.h, as ogp-s1-surface.inc's zcInBrokerWindow): the only engine memory
// mapped at the same address in the title. Anything else is never read.
inline bool inBrokerWindow(uint64_t a, uint64_t bytes)
{
    auto in = [&](uint64_t base, uint64_t len) { return a >= base && bytes <= len && a - base <= len - bytes; };
    return in(UINT64_C(0x240000000), UINT64_C(512) << 20) || in(UINT64_C(0x3000000000), UINT64_C(16) << 30);
}
// The engine keeps a ring of 3 frame buffers; the one read was published as `before`. If the published frame moved on
// by 2 or more while it was read, its buffer may have been written again: the thumbnail is dropped.
inline bool frameKept(uint64_t before, uint64_t after) { return after >= before && after - before < 2; }
inline bool zcUsable(uint64_t frame, uint64_t address, uint32_t w, uint32_t h, uint32_t stride)
{
    return frame && address && w && h && stride >= w * 4 && !(stride % 4) && inBrokerWindow(address, uint64_t(stride) * h);
}

// --- the store (memory only, never saved; private tabs too) --------------------------------------------------------------
class Store {
public:
    struct Entry { const void* tab = nullptr; std::vector<uint32_t> px; uint64_t stamp = 0; };
    // Replaces the tab's thumbnail; past kMax the oldest capture goes. false: wrong size (nothing kept).
    bool put(const void* tab, std::vector<uint32_t> px)
    {
        if (!tab || px.size() != kPixels) return false;
        ++clock_;
        for (Entry& e : e_) if (e.tab == tab) { e.px = std::move(px); e.stamp = clock_; return true; }
        e_.push_back({ tab, std::move(px), clock_ });
        while (e_.size() > size_t(kMax)) {
            auto oldest = std::min_element(e_.begin(), e_.end(), [](const Entry& a, const Entry& b) { return a.stamp < b.stamp; });
            e_.erase(oldest);
        }
        return true;
    }
    const Entry* find(const void* tab) const
    {
        for (const Entry& e : e_) if (e.tab == tab) return &e;
        return nullptr;
    }
    void forget(const void* tab) { e_.erase(std::remove_if(e_.begin(), e_.end(), [tab](const Entry& e) { return e.tab == tab; }), e_.end()); }
    template <class Alive> void prune(Alive alive)
    {
        e_.erase(std::remove_if(e_.begin(), e_.end(), [&alive](const Entry& e) { return !alive(e.tab); }), e_.end());
    }
    size_t size() const { return e_.size(); }
    size_t bytes() const { size_t b = 0; for (const Entry& e : e_) b += e.px.size() * 4; return b; }
private:
    std::vector<Entry> e_;
    uint64_t clock_ = 0;
};

} // namespace OmniTabThumbs
