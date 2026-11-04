// OMNI_POINTER_STYLE_V1: Omni's own arrow (candidate 56c's pointer sprite) with its size, body colour and rim
// as parameters. Needs SDL_FPoint and omniSdPoly() declared before it (OmniBrowser.cpp). With size 1, a white
// body and the dark rim it gives exactly 56c's pixels and hotspot (tests/pointer_style_test.cc).
#pragma once
#include <vector>
static std::vector<uint32_t> omniPtrOmniArrow(float displayScale, float size, const uint8_t body[3], const uint8_t rimColour[3], bool rimOn,
    int& w, int& h, int& hotX, int& hotY)
{
    static const SDL_FPoint omniPtrArrowPoly[] = { {0,0}, {0,22.5f}, {5.4f,17.4f}, {9.1f,25.6f}, {12.9f,24}, {9.3f,15.9f}, {16.6f,15.9f} };
    const float s = displayScale * size, m = 4;   // m: omniPointerMargin
    w = int(std::ceil((17 + 2 * m + 3) * s)), h = int(std::ceil((26 + 2 * m + 4) * s));
    hotX = hotY = int(m * s + 0.5f);
    const float br = body[0] / 255.f, bg = body[1] / 255.f, bb = body[2] / 255.f;
    const float rr = rimColour[0] / 255.f, rg = rimColour[1] / 255.f, rb = rimColour[2] / 255.f;
    std::vector<uint32_t> out(size_t(w) * h);
    for (int y = 0; y < h; ++y) {
        for (int x = 0; x < w; ++x) {
            const float lx = (x + 0.5f) / s - m, ly = (y + 0.5f) / s - m;
            const float d = omniSdPoly(omniPtrArrowPoly, 7, lx, ly), ds = omniSdPoly(omniPtrArrowPoly, 7, lx - 1.3f, ly - 2.3f);
            const float shadow = 0.45f * std::pow(std::clamp(1 - (ds + 0.6f) / 4.2f, 0.f, 1.f), 1.7f);
            const float rim = rimOn ? std::clamp(0.5f - (d - 1.6f) * s, 0.f, 1.f) : 0.f, bodyA = std::clamp(0.5f - d * s, 0.f, 1.f);
            float a = shadow, r = 0, g = 0, b = 0;   // premultiplied: shadow, then rim, then body
            r = rr * rim + r * (1 - rim); g = rg * rim + g * (1 - rim); b = rb * rim + b * (1 - rim); a = rim + a * (1 - rim);
            r = br * bodyA + r * (1 - bodyA); g = bg * bodyA + g * (1 - bodyA); b = bb * bodyA + b * (1 - bodyA); a = bodyA + a * (1 - bodyA);
            auto ch = [a](float v) { return uint32_t(a > 0 ? std::clamp(v / a, 0.f, 1.f) * 255 + 0.5f : 0); };
            out[size_t(y) * w + x] = (uint32_t(a * 255 + 0.5f) << 24) | (ch(r) << 16) | (ch(g) << 8) | ch(b);
        }
    }
    return out;
}
