// OMNI_POINTER_STYLE_V1: pointer art scaling and colouring (no SDL, host-testable).
// The art is two 8-bit coverage planes (fill = the body, edge = the dark outline) or, for a user's
// own picture, straight-alpha RGBA. omniPtrRender() scales it to the size the pointer is drawn at
// (2x2 box halving while the source is at least twice the target, then bilinear), colours it and adds
// the same soft drop shadow as Omni's own arrow. It runs once per setting change, never per frame.
// The hotspot (arrow tip, finger tip or crosshair centre) is carried through every step so a click
// lands on it at any size.
#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <vector>

struct OmniPtrImage { int w = 0, h = 0, hotX = 0, hotY = 0; std::vector<uint32_t> argb; }; // straight alpha, A<<24|R<<16|G<<8|B

// One 8-bit plane, sw x sh -> dw x dh.
static std::vector<uint8_t> omniPtrResample(const uint8_t* src, int sw, int sh, int dw, int dh)
{
    std::vector<float> cur(size_t(sw) * sh);
    for (size_t i = 0; i < cur.size(); ++i) cur[i] = src[i];
    int cw = sw, ch = sh;
    while (cw >= 2 * dw && ch >= 2 * dh && cw >= 2 && ch >= 2) {
        const int nw = cw / 2, nh = ch / 2;
        std::vector<float> next(size_t(nw) * nh);
        for (int y = 0; y < nh; ++y)
            for (int x = 0; x < nw; ++x) {
                const float* r0 = &cur[size_t(2 * y) * cw + 2 * x];
                const float* r1 = r0 + cw;
                next[size_t(y) * nw + x] = (r0[0] + r0[1] + r1[0] + r1[1]) * 0.25f;
            }
        cur.swap(next); cw = nw; ch = nh;
    }
    std::vector<uint8_t> out(size_t(dw) * dh);
    const float sx = float(cw) / dw, sy = float(ch) / dh;
    for (int y = 0; y < dh; ++y) {
        const float fy = std::clamp((y + 0.5f) * sy - 0.5f, 0.f, float(ch - 1));
        const int y0 = int(fy), y1 = std::min(y0 + 1, ch - 1);
        const float ty = fy - y0;
        for (int x = 0; x < dw; ++x) {
            const float fx = std::clamp((x + 0.5f) * sx - 0.5f, 0.f, float(cw - 1));
            const int x0 = int(fx), x1 = std::min(x0 + 1, cw - 1);
            const float tx = fx - x0;
            const float a = cur[size_t(y0) * cw + x0] * (1 - tx) + cur[size_t(y0) * cw + x1] * tx;
            const float b = cur[size_t(y1) * cw + x0] * (1 - tx) + cur[size_t(y1) * cw + x1] * tx;
            out[size_t(y) * dw + x] = uint8_t(std::clamp(a * (1 - ty) + b * ty + 0.5f, 0.f, 255.f));
        }
    }
    return out;
}

// Separable box blur of a float plane (radius r, two passes = a soft tent).
static void omniPtrBlur(std::vector<float>& p, int w, int h, int r)
{
    if (r <= 0) return;
    std::vector<float> t(p.size());
    for (int pass = 0; pass < 2; ++pass) {
        for (int y = 0; y < h; ++y)
            for (int x = 0; x < w; ++x) {
                float s = 0; int n = 0;
                for (int k = std::max(0, x - r); k <= std::min(w - 1, x + r); ++k) { s += p[size_t(y) * w + k]; ++n; }
                t[size_t(y) * w + x] = s / n;
            }
        for (int y = 0; y < h; ++y)
            for (int x = 0; x < w; ++x) {
                float s = 0; int n = 0;
                for (int k = std::max(0, y - r); k <= std::min(h - 1, y + r); ++k) { s += t[size_t(k) * w + x]; ++n; }
                p[size_t(y) * w + x] = s / n;
            }
    }
}

struct OmniPtrPaint {
    uint8_t fill[3] = { 255, 255, 255 };   // body colour
    uint8_t edge[3] = { 16, 20, 28 };      // outline colour (chosen for contrast with the body)
    bool outline = true;                   // draw the edge plane
    float unit = 1;                        // physical pixels per layout pixel at this size (shadow offset and softness)
};

// Source: planes (fill, edge) or rgba (straight alpha, 4 bytes per pixel), sw x sh, hotspot in source pixels.
// Target: the art square drawn tw x th physical pixels; the sprite adds a margin for the shadow.
static OmniPtrImage omniPtrRender(const uint8_t* fill, const uint8_t* edge, const uint8_t* rgba, int sw, int sh,
    float srcHotX, float srcHotY, int tw, int th, const OmniPtrPaint& p)
{
    OmniPtrImage img;
    tw = std::max(tw, 2); th = std::max(th, 2);
    const int margin = int(std::ceil(4 * p.unit));
    const int ox = int(std::ceil(1.3f * p.unit)), oy = int(std::ceil(2.3f * p.unit));
    img.w = tw + 2 * margin + ox; img.h = th + 2 * margin + oy;
    img.hotX = margin + int(std::floor(srcHotX * tw / sw + 0.5f));
    img.hotY = margin + int(std::floor(srcHotY * th / sh + 0.5f));
    std::vector<uint8_t> f, e, r, g, b;
    if (rgba) {   // premultiply, scale each channel, divide back
        std::vector<uint8_t> pa(size_t(sw) * sh), pr(pa.size()), pg(pa.size()), pb(pa.size());
        for (size_t i = 0; i < pa.size(); ++i) {
            const uint32_t a = rgba[4 * i + 3];
            pa[i] = uint8_t(a); pr[i] = uint8_t((rgba[4 * i] * a + 127) / 255); pg[i] = uint8_t((rgba[4 * i + 1] * a + 127) / 255); pb[i] = uint8_t((rgba[4 * i + 2] * a + 127) / 255);
        }
        f = omniPtrResample(pa.data(), sw, sh, tw, th);
        r = omniPtrResample(pr.data(), sw, sh, tw, th); g = omniPtrResample(pg.data(), sw, sh, tw, th); b = omniPtrResample(pb.data(), sw, sh, tw, th);
    } else {
        f = omniPtrResample(fill, sw, sh, tw, th);
        if (p.outline && edge) e = omniPtrResample(edge, sw, sh, tw, th);
    }
    // Shadow: the drawn shape's coverage, offset by (1.3, 2.3) layout px, softened, at 45% (as Omni's arrow).
    std::vector<float> sh0(size_t(img.w) * img.h, 0.f);
    for (int y = 0; y < th; ++y)
        for (int x = 0; x < tw; ++x) {
            const size_t i = size_t(y) * tw + x;
            const float cov = std::max(f[i], e.empty() ? uint8_t(0) : e[i]) / 255.f;
            sh0[size_t(y + margin + oy) * img.w + (x + margin + ox)] = cov;
        }
    omniPtrBlur(sh0, img.w, img.h, std::max(1, int(1.6f * p.unit + 0.5f)));
    img.argb.assign(size_t(img.w) * img.h, 0);
    for (int y = 0; y < img.h; ++y)
        for (int x = 0; x < img.w; ++x) {
            float a = 0.45f * sh0[size_t(y) * img.w + x], cr = 0, cg = 0, cb = 0;   // premultiplied: shadow, then edge, then body
            const int ax = x - margin, ay = y - margin;
            if (ax >= 0 && ay >= 0 && ax < tw && ay < th) {
                const size_t i = size_t(ay) * tw + ax;
                if (!e.empty()) {
                    const float k = e[i] / 255.f;
                    cr = p.edge[0] / 255.f * k + cr * (1 - k); cg = p.edge[1] / 255.f * k + cg * (1 - k); cb = p.edge[2] / 255.f * k + cb * (1 - k); a = k + a * (1 - k);
                }
                const float k = f[i] / 255.f;
                if (rgba) { cr = r[i] / 255.f + cr * (1 - k); cg = g[i] / 255.f + cg * (1 - k); cb = b[i] / 255.f + cb * (1 - k); }
                else { cr = p.fill[0] / 255.f * k + cr * (1 - k); cg = p.fill[1] / 255.f * k + cg * (1 - k); cb = p.fill[2] / 255.f * k + cb * (1 - k); }
                a = k + a * (1 - k);
            }
            auto ch = [a](float v) { return uint32_t(a > 0 ? std::clamp(v / a, 0.f, 1.f) * 255 + 0.5f : 0); };
            img.argb[size_t(y) * img.w + x] = (uint32_t(std::clamp(a, 0.f, 1.f) * 255 + 0.5f) << 24) | (ch(cr) << 16) | (ch(cg) << 8) | ch(cb);
        }
    return img;
}

// Outline colour for a body colour: dark rim on light bodies (Omni's own rim colour), light rim on dark ones.
static void omniPtrContrast(const uint8_t body[3], uint8_t out[3])
{
    const float lum = (0.2126f * body[0] + 0.7152f * body[1] + 0.0722f * body[2]) / 255.f;
    if (lum > 0.45f) { out[0] = 16; out[1] = 20; out[2] = 28; } else { out[0] = 245; out[1] = 246; out[2] = 248; }
}
