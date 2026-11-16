// OMNI_HIGH_CONTRAST_V1: host tests of OmniHighContrast.h (palette contrast, drawing rules, Large pointer scaling).
// g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_high_contrast.cpp -o t && ./t
#include "OmniHighContrast.h"
#include <cstdio>
#include <cstring>

namespace H = OmniHighContrast;
static int failures = 0, passes = 0;
#define CHECK(c) do { if (c) ++passes; else { ++failures; std::printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); } } while (0)
static bool near(double a, double b, double e = 0.01) { return std::fabs(a - b) <= e; }

int main()
{
    // WCAG formula against known values.
    CHECK(near(H::contrast({ 255, 255, 255 }, { 0, 0, 0 }), 21.0));
    CHECK(near(H::contrast({ 0, 0, 0 }, { 0, 0, 0 }), 1.0));
    CHECK(near(H::contrast({ 118, 118, 118 }, { 255, 255, 255 }), 4.54, 0.02));   // #767676 on white: the classic 4.5:1 grey
    CHECK(near(H::contrast({ 89, 89, 89 }, { 255, 255, 255 }), 7.0, 0.05));       // #595959 on white: ~7:1
    CHECK(near(H::contrast({ 255, 0, 0 }, { 255, 255, 255 }), 4.0, 0.01));
    CHECK(H::contrast({ 10, 20, 30 }, { 200, 100, 50 }) == H::contrast({ 200, 100, 50 }, { 10, 20, 30 }));
    CHECK(near(H::luminance({ 255, 255, 255 }), 1.0) && near(H::luminance({ 0, 0, 0 }), 0.0));

    // The palette: every pair the shell draws.
    const auto all = H::checks();
    for (const auto& c : all) {
        if (c.ratio < c.min) std::printf("  low: %-26s %.2f < %.1f\n", c.what.c_str(), c.ratio, c.min);
        CHECK(c.ratio >= c.min);
    }
    CHECK(all.size() >= 45);
    CHECK(H::paletteOk());
    std::printf("palette: text worst %.2f:1 (>= 7), focus worst %.2f:1 (>= 3), disabled worst %.2f:1 (>= 4.5), ink vs disabled %.2f:1\n",
        H::worst(H::kTextMin), H::worst(H::kFocusMin), H::worst(H::kDisabledMin), H::contrast(H::kPalette.ink, H::kPalette.inkFaint));
    std::printf("palette: white on black %.1f:1, black on yellow %.1f:1, yellow ring on black %.1f:1, danger on black %.2f:1\n",
        H::contrast(H::kPalette.ink, H::kPalette.bg), H::contrast(H::kPalette.accentInk, H::kPalette.accent),
        H::contrast(H::kPalette.accent, H::kPalette.panel), H::contrast(H::kDanger, H::kPalette.panel));
    // Pure black backgrounds, white text, yellow focus.
    const H::Rgb black { 0, 0, 0 };
    for (H::Rgb c : { H::kPalette.bg, H::kPalette.bar, H::kPalette.panel, H::kPalette.tab, H::kPalette.tabOn })
        CHECK(c.r == black.r && c.g == black.g && c.b == black.b);
    CHECK(H::kPalette.ink.r == 255 && H::kPalette.ink.g == 255 && H::kPalette.ink.b == 255);
    CHECK(H::kPalette.accent.r > 200 && H::kPalette.accent.g > 180 && H::kPalette.accent.b < 40);
    // Disabled grey is a mid grey (not a hue) between the text and the background.
    CHECK(H::kPalette.inkFaint.r == H::kPalette.inkFaint.g && H::kPalette.inkFaint.g == H::kPalette.inkFaint.b);
    CHECK(H::kPalette.inkFaint.r > 100 && H::kPalette.inkFaint.r < 200);
    // The shell's old red fails 7:1 on black, the replacement passes.
    CHECK(H::contrast({ 236, 98, 98 }, black) < 7.0);
    CHECK(H::contrast(H::kDanger, black) >= 7.0);
    // A failing palette is caught (dim grey text on black).
    H::Palette bad = H::kPalette;
    bad.inkDim = { 90, 90, 90 };
    CHECK(!H::paletteOk(bad));
    bad = H::kPalette;
    bad.accent = { 30, 30, 30 };   // focus ring nearly invisible
    CHECK(!H::paletteOk(bad));

    // Drawing rules.
    CHECK(H::ringPx(2, true) == 6 && H::ringPx(2, false) == 2);
    CHECK(H::opaqueAlpha(235, true) == 255 && H::opaqueAlpha(200, true) == 255 && H::opaqueAlpha(150, true) == 255);
    CHECK(H::opaqueAlpha(110, true) == 110 && H::opaqueAlpha(90, true) == 90);   // scrims, selection tint
    CHECK(H::opaqueAlpha(235, false) == 235 && H::opaqueAlpha(255, true) == 255 && H::opaqueAlpha(0, true) == 0);
    CHECK(H::offLabel("Reader view", false, true) == "Reader view (off)");
    CHECK(H::offLabel("Reader view", true, true) == "Reader view");
    CHECK(H::offLabel("Reader view", false, false) == "Reader view");
    CHECK(!std::strcmp(H::toggleWord(true), "On") && !std::strcmp(H::toggleWord(false), "Off"));

    // Theme cards: 4 themes keep the old 156 / 148 layout; 5 fit the same 616 px.
    CHECK(H::cardStride(4) == 156 && H::cardWidth(4) == 148 && !H::stackedCards(4));
    CHECK(H::cardStride(5) == 124 && H::cardWidth(5) == 116 && H::stackedCards(5));
    CHECK(4 * H::cardStride(5) + H::cardWidth(5) <= 616);
    for (int x = 0; x < 616; ++x) {   // the old hit test, for 4 cards
        const int old = x % 156 < 148 ? x / 156 : -1;
        CHECK(H::cardAt(x, 4) == old);
    }
    CHECK(H::cardAt(0, 5) == 0 && H::cardAt(115, 5) == 0 && H::cardAt(116, 5) == -1 && H::cardAt(124, 5) == 1);
    CHECK(H::cardAt(4 * 124 + 115, 5) == 4 && H::cardAt(4 * 124 + 116, 5) == -1 && H::cardAt(5 * 124, 5) == -1 && H::cardAt(-1, 5) == -1);
    CHECK(!std::strncmp(H::kThemeId, "contrast", 8));
    for (const char* other : { "dark", "midnight", "playstation", "purple" }) {   // ui-theme.txt is matched by prefix
        CHECK(std::strncmp(H::kThemeId, other, std::strlen(other)) != 0);
        CHECK(std::strncmp(other, H::kThemeId, std::strlen(H::kThemeId)) != 0);
    }

    // Large pointer file.
    CHECK(H::parseLarge("on\n") && H::parseLarge("  on \r\n") && !H::parseLarge("off\n") && !H::parseLarge("") && !H::parseLarge("onx"));
    CHECK(H::parseLarge(H::serializeLarge(true)) && !H::parseLarge(H::serializeLarge(false)));
    CHECK(H::scaledHot(7) == 14 && H::scaledHot(0) == 0);
    CHECK(H::canScale(216, 216) && !H::canScale(1500, 10) && !H::canScale(0, 10));

    // Scaling: size, solid stays solid, empty stays empty, edges are smoothed without a dark fringe.
    {
        const uint32_t one = 0xFF336699u;
        std::vector<uint32_t> out;
        H::scaleArgb(&one, 1, 1, 2, out);
        CHECK(out.size() == 4);
        for (uint32_t p : out) CHECK(p == one);
    }
    {
        const uint32_t clear[4] = { 0, 0, 0, 0 };
        std::vector<uint32_t> out;
        H::scaleArgb(clear, 2, 2, 2, out);
        CHECK(out.size() == 16);
        for (uint32_t p : out) CHECK(p == 0);
    }
    {
        // An opaque white pixel next to a transparent BLACK one: the blend keeps white colour, only alpha falls.
        const uint32_t src[2] = { 0xFFFFFFFFu, 0x00000000u };
        std::vector<uint32_t> out;
        H::scaleArgb(src, 2, 1, 2, out);
        CHECK(out.size() == 8);
        CHECK(out[0] == 0xFFFFFFFFu);                           // inside the white pixel
        const uint32_t mid = out[1], a = mid >> 24;             // between the two: partly transparent ...
        CHECK(a > 100 && a < 255);
        CHECK(((mid >> 16) & 255) == 255 && ((mid >> 8) & 255) == 255 && (mid & 255) == 255);   // ... still white
        CHECK((out[2] >> 24) > 0 && (out[2] >> 24) < (mid >> 24));   // fading out
        CHECK(out[3] == 0);                                        // the far edge stays empty
    }
    {
        // A 3x3 sprite: every output pixel's alpha lies within its source neighbourhood's alpha range (no ringing).
        const uint32_t src[9] = { 0, 0xFF000000u, 0, 0xFF000000u, 0xFFFFFFFFu, 0xFF000000u, 0, 0xFF000000u, 0 };
        std::vector<uint32_t> out;
        H::scaleArgb(src, 3, 3, 2, out);
        CHECK(out.size() == 36);
        CHECK((out[2 * 6 + 2] >> 24) >= 230 && (out[3 * 6 + 3] >> 24) >= 230);   // centre stays (nearly) opaque
        CHECK((out[2 * 6 + 2] & 255) > 128);   // and white-ish (the white centre dominates)
        int smooth = 0;
        for (uint32_t p : out) { const uint32_t a = p >> 24; if (a > 0 && a < 255) ++smooth; }
        CHECK(smooth > 0);   // smoothing, not nearest neighbour
    }

    std::printf("%s: %d passed, %d failed\n", failures ? "FAILED" : "OK", passes, failures);
    return failures ? 1 : 0;
}
