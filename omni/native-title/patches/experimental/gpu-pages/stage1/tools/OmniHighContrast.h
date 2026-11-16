// OMNI_HIGH_CONTRAST_V1: the pure part of the "High contrast" theme and the "Large pointer" option (no SDL, no WebKit).
// High contrast: pure black surfaces, white text, a yellow accent / focus ring drawn 3x thicker, no translucent panels,
// disabled rows in a mid grey with a strike and "(off)", toggles as words. The palette is checked here with the WCAG 2
// contrast formula (text >= 7:1, focus ring >= 3:1 against what it sits on). Large pointer: the pointer sprite scaled 2x
// with bilinear smoothing (premultiplied, no dark fringes), built once per pointer change.
// Shell side and reasons: tools/apply_high_contrast.py. Tested on the host with g++ (tools/test_high_contrast.cpp).
#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

namespace OmniHighContrast {

struct Rgb { uint8_t r, g, b; };
// Same fields and order as OmniTheme in OmniBrowser.cpp (after id / name).
struct Palette {
    Rgb bg, bar, line, tab, hover, field, panel, raised, key, ink, inkDim, inkFaint, accent, accentInk, tabOn, edge, accent2;
};
inline constexpr Palette kPalette {
    /* bg */ { 0, 0, 0 }, /* bar */ { 0, 0, 0 }, /* line */ { 255, 255, 255 }, /* tab */ { 0, 0, 0 },
    /* hover */ { 48, 42, 0 }, /* field */ { 16, 16, 16 }, /* panel */ { 0, 0, 0 }, /* raised */ { 16, 16, 16 },
    /* key */ { 20, 20, 20 }, /* ink */ { 255, 255, 255 }, /* inkDim */ { 224, 224, 224 }, /* inkFaint (disabled) */ { 160, 160, 160 },
    /* accent (focus) */ { 255, 221, 0 }, /* accentInk */ { 0, 0, 0 }, /* tabOn */ { 0, 0, 0 }, /* edge */ { 255, 255, 255 },
    /* accent2 */ { 255, 221, 0 },
};
inline constexpr Rgb kDanger { 255, 128, 128 };   // replaces the shell's red (236,98,98: 6.5:1 on black) for danger rows
inline constexpr const char* kThemeId = "contrast";   // ui-theme.txt (no other theme id is a prefix of it, nor it of one)
inline constexpr const char* kThemeName = "High contrast";

// WCAG 2.x relative luminance and contrast ratio ---------------------------------------------------------------------
inline double channel(uint8_t v)
{
    const double c = v / 255.0;
    return c <= 0.04045 ? c / 12.92 : std::pow((c + 0.055) / 1.055, 2.4);
}
inline double luminance(Rgb c) { return 0.2126 * channel(c.r) + 0.7152 * channel(c.g) + 0.0722 * channel(c.b); }
inline double contrast(Rgb a, Rgb b)
{
    const double la = luminance(a), lb = luminance(b);
    return (std::max(la, lb) + 0.05) / (std::min(la, lb) + 0.05);
}
inline constexpr double kTextMin = 7.0;       // WCAG AAA body text
inline constexpr double kFocusMin = 3.0;      // WCAG 2.2 focus appearance / non-text contrast
inline constexpr double kDisabledMin = 4.5;   // disabled rows on raised surfaces (>= kTextMin on the black ones)
inline constexpr double kDisabledApart = 2.5; // disabled grey vs. white text: visibly different, not colour alone

struct Check { std::string what; double ratio; double min; };
// Every pair the shell draws with the palette (text on each surface, focus ring around / beside each surface).
inline std::vector<Check> checks(const Palette& p = kPalette, Rgb danger = kDanger)
{
    struct Named { const char* n; Rgb c; };
    const Named surfaces[] = { { "bg", p.bg }, { "bar", p.bar }, { "tab", p.tab }, { "tabOn", p.tabOn }, { "panel", p.panel },
        { "field", p.field }, { "raised", p.raised }, { "key", p.key }, { "hover", p.hover } };
    std::vector<Check> out;
    for (const Named& s : surfaces) {
        out.push_back({ std::string("ink on ") + s.n, contrast(p.ink, s.c), kTextMin });
        out.push_back({ std::string("inkDim on ") + s.n, contrast(p.inkDim, s.c), kTextMin });
        const bool black = s.c.r == 0 && s.c.g == 0 && s.c.b == 0;
        out.push_back({ std::string("inkFaint on ") + s.n, contrast(p.inkFaint, s.c), black ? kTextMin : kDisabledMin });
        out.push_back({ std::string("focus vs ") + s.n, contrast(p.accent, s.c), kFocusMin });
        if (s.c.r != p.hover.r || s.c.g != p.hover.g || s.c.b != p.hover.b)
            out.push_back({ std::string("danger on ") + s.n, contrast(danger, s.c), kTextMin });
    }
    out.push_back({ "accentInk on accent", contrast(p.accentInk, p.accent), kTextMin });
    out.push_back({ "accentInk on accent2", contrast(p.accentInk, p.accent2), kTextMin });
    out.push_back({ "edge vs panel", contrast(p.edge, p.panel), kFocusMin });
    out.push_back({ "line vs bar", contrast(p.line, p.bar), kFocusMin });
    out.push_back({ "disabled apart from ink", contrast(p.ink, p.inkFaint), kDisabledApart });
    return out;
}
inline bool paletteOk(const Palette& p = kPalette, Rgb danger = kDanger)
{
    for (const Check& c : checks(p, danger)) if (c.ratio < c.min) return false;
    return true;
}
inline double worst(double min, const Palette& p = kPalette)
{
    double w = 1e9;
    for (const Check& c : checks(p)) if (c.min == min) w = std::min(w, c.ratio);
    return w;
}

// Drawing rules ------------------------------------------------------------------------------------------------------
inline constexpr int kRingScale = 3;
inline int ringPx(int base, bool hc) { return hc ? base * kRingScale : base; }   // focus ring thickness (layout px)
// Translucent surfaces (panels, toasts, info strips: alpha >= kOpaqueFrom) are drawn solid; scrims behind modals and
// selection tints (lower alpha) stay as they are, they must show what is under them.
inline constexpr int kOpaqueFrom = 150;
inline uint8_t opaqueAlpha(uint8_t alpha, bool hc) { return hc && alpha >= kOpaqueFrom ? uint8_t(255) : alpha; }
inline constexpr const char* kOffSuffix = "(off)";
inline std::string offLabel(const std::string& label, bool enabled, bool hc) { return hc && !enabled ? label + " " + kOffSuffix : label; }
inline const char* toggleWord(bool on) { return on ? "On" : "Off"; }
inline constexpr int kStrikePx = 2;   // the strike through a disabled row's label (layout px)

// Settings > Theme cards: `count` cards across `span` layout px with `gap` between (4 themes: 156 / 148, as before).
inline int cardStride(int count, int span = 616, int gap = 8) { return count > 0 ? (span + gap) / count : span + gap; }
inline int cardWidth(int count, int span = 616, int gap = 8) { return cardStride(count, span, gap) - gap; }
// The card under x (layout px from the first card's left edge), -1 between cards or outside.
inline int cardAt(int x, int count, int span = 616, int gap = 8)
{
    const int s = cardStride(count, span, gap);
    if (x < 0 || count <= 0 || x / s >= count || x % s >= s - gap) return -1;
    return x / s;
}
inline bool stackedCards(int count) { return cardStride(count) < 156; }   // disc above a centred caption

// Large pointer ------------------------------------------------------------------------------------------------------
inline constexpr int kPointerScale = 2;
inline constexpr int kPointerMaxSide = 2048;   // never build a larger sprite (falls back to the normal size)
// pointer-large.txt: "on" / "off" (missing, empty or anything else: off).
inline bool parseLarge(std::string_view text)
{
    while (!text.empty() && (text.front() == ' ' || text.front() == '\t' || text.front() == '\r' || text.front() == '\n')) text.remove_prefix(1);
    while (!text.empty() && (text.back() == ' ' || text.back() == '\t' || text.back() == '\r' || text.back() == '\n')) text.remove_suffix(1);
    return text == "on";
}
inline std::string serializeLarge(bool on) { return on ? "on\n" : "off\n"; }
inline int scaledHot(int hot, int factor = kPointerScale) { return hot * factor; }
inline bool canScale(int w, int h, int factor = kPointerScale) { return w > 0 && h > 0 && w * factor <= kPointerMaxSide && h * factor <= kPointerMaxSide; }

// Straight-alpha 0xAARRGGBB, `factor` x larger, bilinear on premultiplied colour (edges clamp). out: (w*f) x (h*f).
inline void scaleArgb(const uint32_t* src, int w, int h, int factor, std::vector<uint32_t>& out)
{
    out.assign(size_t(w) * factor * size_t(h) * factor, 0);
    if (w <= 0 || h <= 0 || factor <= 0) return;
    auto pre = [&](int x, int y, float* c) {
        x = std::clamp(x, 0, w - 1); y = std::clamp(y, 0, h - 1);
        const uint32_t p = src[size_t(y) * w + x];
        const float a = float(p >> 24);
        c[0] = a; c[1] = float((p >> 16) & 255) * a / 255.f; c[2] = float((p >> 8) & 255) * a / 255.f; c[3] = float(p & 255) * a / 255.f;
    };
    const int W = w * factor, H = h * factor;
    for (int y = 0; y < H; ++y) {
        const float sy = (y + 0.5f) / factor - 0.5f;
        const int y0 = int(std::floor(sy));
        const float fy = sy - y0;
        for (int x = 0; x < W; ++x) {
            const float sx = (x + 0.5f) / factor - 0.5f;
            const int x0 = int(std::floor(sx));
            const float fx = sx - x0;
            float c00[4], c10[4], c01[4], c11[4], c[4];
            pre(x0, y0, c00); pre(x0 + 1, y0, c10); pre(x0, y0 + 1, c01); pre(x0 + 1, y0 + 1, c11);
            for (int k = 0; k < 4; ++k)
                c[k] = (c00[k] * (1 - fx) + c10[k] * fx) * (1 - fy) + (c01[k] * (1 - fx) + c11[k] * fx) * fy;
            const uint32_t a = uint32_t(std::clamp(c[0] + 0.5f, 0.f, 255.f));
            if (!a) continue;
            auto un = [&](float v) { return uint32_t(std::clamp(v * 255.f / c[0] + 0.5f, 0.f, 255.f)); };
            out[size_t(y) * W + x] = (a << 24) | (un(c[1]) << 16) | (un(c[2]) << 8) | un(c[3]);
        }
    }
}

} // namespace OmniHighContrast
