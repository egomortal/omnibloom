// OMNI_FEATURES_V3: a bookmark star at the right end of the address field (web pages only, not
// while the address is being edited). Outline: not bookmarked; filled (accent): bookmarked.
// Pointer + Cross toggles it (same storage as the quick menu's Bookmark page: bookmarks.txt).
#pragma once

constexpr float omniStarCX = 1078, omniStarCY = 82;
static const OmniIconMask& omniStarMask(bool filled)
{
    static OmniIconMask masks[2];
    static double scale[2] = { 0, 0 };
    OmniIconMask& mask = masks[filled ? 1 : 0];
    if (mask.a.empty() || scale[filled ? 1 : 0] != displayScale) {
        scale[filled ? 1 : 0] = displayScale;
        SDL_FPoint pts[10];
        for (int k = 0; k < 10; ++k) {
            const float r = (k & 1) ? 3.9f : 9.0f, a = -1.5707963f + k * 0.62831853f;
            pts[k] = { 10.f + r * std::cos(a), 10.6f + r * std::sin(a) };
        }
        const float s = float(displayScale);
        mask.w = int(std::ceil(20 * s)); mask.h = int(std::ceil(20 * s));
        mask.a.assign(size_t(mask.w) * mask.h, 0);
        for (int y = 0; y < mask.h; ++y) for (int x = 0; x < mask.w; ++x) {
            float a = 0;
            for (int k = 0; k < 4; ++k) {
                const float d = omniSdPoly(pts, 10, (x + 0.25f + 0.5f * (k & 1)) / s, (y + 0.25f + 0.5f * (k >> 1)) / s);
                const float sd = filled ? d : std::fabs(d + 0.75f) - 0.75f;   // outline: a 1.5 px band inside the edge
                a += std::clamp(0.5f - s * sd, 0.f, 1.f);
            }
            mask.a[size_t(y) * mask.w + x] = uint8_t(a / 4 * 255 + 0.5f);
        }
    }
    return mask;
}
static void omniStarPaint(float cx, float cy, bool filled, SDL_Color color)
{
    const OmniPix f = omniPix();
    if (!f.ok) return;
    const OmniIconMask& mask = omniStarMask(filled);
    const int x0 = int(cx * displayScale + 0.5) - mask.w / 2, y0 = int(cy * displayScale + 0.5) - mask.h / 2;
    for (int j = std::max(0, -y0); j < mask.h && y0 + j < canvas->h; ++j) {
        uint32_t* row = omniRow(y0 + j);
        const uint8_t* a = mask.a.data() + size_t(j) * mask.w;
        for (int i = std::max(0, -x0); i < mask.w && x0 + i < canvas->w; ++i) if (a[i]) omniBlendPx(row[x0 + i], f, color, a[i]);
    }
}
static bool omniF3StarShown()
{
    const Tab* t = active();
    return t && !(editing && !pageEditing) && omniWebURL(t->url) && !omniTmIsUnloaded(*t);
}
static void omniF3StarDraw()
{
    if (!omniF3StarShown()) return;
    const OmniTheme& T = omniTheme();
    const bool on = omniFxBookmarkIndex(active()->url) >= 0;
    if (omniHover(1058, 52, 44, 60)) omniRingDisc(omniStarCX, omniStarCY, 17, T.accent, T.hover);
    omniStarPaint(omniStarCX, omniStarCY, on, on ? T.accent : T.inkDim);
}
static bool omniF3StarClick(int x, int by)
{
    if (!omniF3StarShown() || x < 1058 || x >= 1102 || by < 52) return false;
    omniFxBookmarkToggleCurrent();
    omniShellDirty = true;
    return true;
}
