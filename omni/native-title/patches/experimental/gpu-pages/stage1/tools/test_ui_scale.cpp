// OMNI_UI_SCALE_V1 tests (OMNI_UI_SCALE_V1_R2: + stage 2 fitBox / toNormal; OMNI_UI_SCALE_V1_R3: + stage 3 keyboard,
// suggestions, find bar, hint line; OMNI_UI_SCALE_V1_R4: + stage 4 top bar text zoom, hints bar, dialogs, screenshot grid
// and its pager): g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_ui_scale.cpp -o t && ./t  (a tree with r4 applied)
#include "OmniUiScale.h"
#include "OmniShotGallery.h"
#include <algorithm>
#include <cmath>
#include <cstdio>

namespace U = OmniUiScale;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); } } while (0)

// today's omniFxGeometry (OmniFeaturesPanel.h), for the Normal == unchanged check
struct G { int x, y, w, h, vis, header; };
static G today(int w, int rowH, int n, int cols, int maxVisible, bool subtitle, int ax = -1, int ay = -1)
{
    G g {};
    g.header = subtitle ? 88 : 64;
    g.vis = cols > 1 ? std::max(1, std::min((n + cols - 1) / cols, maxVisible)) : std::max(1, std::min(n, maxVisible));
    g.w = w; g.h = g.header + g.vis * rowH + 14;
    if (ax >= 0) { g.x = std::clamp(ax + 18, 16, 1280 - g.w - 16); g.y = std::clamp(ay - 24, 12, std::max(12, 720 - 32 - g.h - 10)); }
    else { g.x = (1280 - g.w) / 2; g.y = std::max(10, (720 - 32 - g.h) / 2); }
    return g;
}
// the panels in the tree: w, rowH, maxVisible, cols
struct P { const char* name; int w, rowH, maxVisible, cols; };
static const P kPanels[] = {
    { "default", 760, 50, 9, 1 }, { "context", 520, 46, 11, 1 }, { "filepicker", 900, 46, 10, 1 },
    { "quickaccess", 760, 48, 10, 1 }, { "apps", 1040, 96, 4, 2 }, { "submenu", 1000, 56, 8, 1 },
    { "options", 1000, 92, 4, 2 }, { "readinglist", 980, 56, 8, 1 },
};

int main()
{
    // table, names, stepper
    CHECK(U::scaleOf(U::Small) == 0.85 && U::scaleOf(U::Normal) == 1.0 && U::scaleOf(U::Large) == 1.25 && U::scaleOf(U::ExtraLarge) == 1.5);
    CHECK(U::scaleOf(-3) == 0.85 && U::scaleOf(99) == 1.5);
    CHECK(std::string(U::nameOf(U::ExtraLarge)) == "Extra large");
    CHECK(U::stepped(U::Normal, 1) == U::Large && U::stepped(U::ExtraLarge, 1) == U::ExtraLarge && U::stepped(U::Small, -1) == U::Small);
    // parse / save round trip
    for (int l = 0; l < U::kLevelCount; ++l) CHECK(U::parse(U::serialize(l)) == l);
    CHECK(U::parse("") == U::Normal && U::parse("huge") == U::Normal && U::parse("\r\n") == U::Normal);
    CHECK(U::parse("  Extra Large\r\n") == U::ExtraLarge && U::parse("XL") == U::ExtraLarge && U::parse("extra-large") == U::ExtraLarge);
    CHECK(U::parse("LARGE\nsmall\n") == U::Large);
    CHECK(U::serialize(U::Large) == "large\n");
    // scaled / pointer mapping
    CHECK(U::scaled(22, 1.5) == 33 && U::scaled(1, 0.4) == 1 && U::scaled(0, 1.5) == 0);
    CHECK(U::toZoomed(1279, 1.5) == 852 && U::toZoomed(0, 1.5) == 0 && U::toZoomed(600, 1.0) == 600);
    CHECK(U::zoomedW(1.5) == 853 && U::zoomedH(1.5) == 480);
    // a click at the centre of a zoomed row maps back onto that row (draw <-> hit-test use the same geometry)
    {
        const U::PanelFit f = U::fitPanel(U::ExtraLarge, 760, 50, 20, 1, 9, false);
        for (int k = 0; k < f.vis; ++k) {
            const double screenY = (f.listY + k * 50 + 25) * f.zoom, screenX = (f.x + f.w / 2) * f.zoom;
            const int zy = U::toZoomed(screenY, f.zoom), zx = U::toZoomed(screenX, f.zoom);
            CHECK((zy - f.listY) / 50 == k && zx >= f.x && zx < f.x + f.w);
        }
    }
    // rowsPerPage
    CHECK(U::rowsPerPage(600, 50, 1.0, 1, 9) == 9 && U::rowsPerPage(600, 50, 1.5, 1, 99) == 8 && U::rowsPerPage(10, 50, 1.5, 3, 9) == 3);
    CHECK(U::rowsPerPage(600, 0, 1.0, 2, 9) == 2);
    // Normal: exactly today's geometry for every panel in the tree, any row count, both subtitle states, anchored too
    for (const P& p : kPanels)
        for (int n : { 0, 1, 3, 4, 7, 9, 11, 30 })
            for (bool sub : { false, true }) {
                const G g = today(p.w, p.rowH, n, p.cols, p.maxVisible, sub);
                const U::PanelFit f = U::fitPanel(U::Normal, p.w, p.rowH, n, p.cols, p.maxVisible, sub);
                CHECK(f.zoom == 1.0 && f.vis == g.vis && f.x == g.x && f.y == g.y && f.w == g.w && f.h == g.h && f.header == g.header);
                if (!sub && p.cols == 1) {
                    const G a = today(p.w, p.rowH, n, 1, p.maxVisible, false, 900, 500);
                    const U::PanelFit fa = U::fitPanel(U::Normal, p.w, p.rowH, n, 1, p.maxVisible, false, 1.0, 900, 500);
                    CHECK(fa.x == a.x && fa.y == a.y);
                }
            }
    // every level, every panel: fits on screen above the hints bar (1080p and 4K share the 1280x720 layout space),
    // at least min(rows, 3) visible, Large / Extra large never smaller than Normal, Small never larger
    for (int l = 0; l < U::kLevelCount; ++l)
        for (const P& p : kPanels)
            for (int n : { 1, 2, 3, 5, 12, 40 })
                for (bool sub : { false, true })
                    for (double hz : { 1.0, U::scaleOf(l) }) {
                        const U::PanelFit f = U::fitPanel(l, p.w, p.rowH, n, p.cols, p.maxVisible, sub, hz);
                        const int lines = p.cols > 1 ? (n + p.cols - 1) / p.cols : n;
                        const double right = (f.x + f.w) * f.zoom, bottom = (f.y + f.h) * f.zoom;
                        CHECK(f.x >= 0 && f.y >= 0 && right <= 1280 && bottom <= 720 - 32 * std::max(1.0, hz) + 0.5);
                        CHECK(f.vis >= std::min({ lines, 3, p.maxVisible }) && f.vis <= std::max(1, std::min(lines, p.maxVisible)));
                        if (l >= U::Normal) CHECK(f.zoom >= 1.0 && f.zoom <= U::scaleOf(l));
                        else CHECK(f.zoom <= 1.0);
                        if (p.w * U::scaleOf(l) <= 1248 && l == U::Large && p.rowH <= 56) CHECK(f.zoom == 1.25);
                    }
    // stage 1: omniFxRowAt (copied from OmniFeaturesPanel.h) on fitPanel's geometry with the pointer mapped by toZoomed,
    // the way omniFxHover / omniFxClick do it: the centre of every drawn row / tile (screen px = zoomed layout * zoom)
    // hits that row at every level; the stepper arrows' click zones land on the drawn arrows; past the panel is outside.
    {
        auto rowAt = [](const U::PanelFit& g, int cols, int rowH, int n, int scroll, int x, int y) {
            if (x < g.x || x >= g.x + g.w || y < g.y || y >= g.y + g.h) return -2;
            if (y < g.listY) return -1;
            int row = -1;
            if (cols > 1) {
                const int gap = 8, tw = (g.w - 24 - (cols - 1) * gap) / cols;
                const int c = (x - g.x - 12) / (tw + gap), r = (y - g.listY) / rowH;
                if (x < g.x + 12 || c < 0 || c >= cols || r < 0 || r >= g.vis) return -1;
                if ((x - g.x - 12) % (tw + gap) >= tw || (y - g.listY) % rowH >= rowH - gap) return -1;
                row = (r + scroll) * cols + c;
            } else {
                const int k = (y - g.listY) / rowH;
                if (k >= g.vis) return -1;
                row = scroll + k;
            }
            return row < 0 || row >= n ? -1 : row;
        };
        for (int l = 0; l < U::kLevelCount; ++l)
            for (const P& p : kPanels)
                for (int n : { 2, 7, 25 }) {
                    const U::PanelFit g = U::fitPanel(l, p.w, p.rowH, n, p.cols, p.maxVisible, true);
                    const int scroll = 1;
                    auto hit = [&](double lx, double ly) {   // a zoomed layout point -> screen -> back, as the shell does
                        return rowAt(g, p.cols, p.rowH, n, scroll, U::toZoomed(int(lx * g.zoom), g.zoom), U::toZoomed(int(ly * g.zoom), g.zoom));
                    };
                    if (p.cols > 1) {
                        const int gap = 8, tw = (g.w - 24 - (p.cols - 1) * gap) / p.cols, th = p.rowH - gap;
                        for (int i = scroll * p.cols; i < std::min(n, (scroll + g.vis) * p.cols); ++i) {
                            const int c = i % p.cols, row = i / p.cols - scroll;
                            CHECK(hit(g.x + 12 + c * (tw + gap) + tw / 2.0, g.listY + row * p.rowH + th / 2.0) == i);
                        }
                    } else {
                        for (int k = 0; k < g.vis && scroll + k < n; ++k) {
                            const double cy = g.listY + k * p.rowH + p.rowH / 2.0;
                            CHECK(hit(g.x + g.w / 2.0, cy) == scroll + k);
                            CHECK(hit(g.x + g.w - 42, cy) == scroll + k && U::toZoomed((g.x + g.w - 42) * g.zoom, g.zoom) >= g.x + g.w - 70);
                            const int back = U::toZoomed((g.x + g.w - 196) * g.zoom, g.zoom);
                            CHECK(back >= g.x + g.w - 214 && back < g.x + g.w - 170);
                        }
                    }
                    CHECK(hit(g.x - 3, g.y + 5) == -2 && hit(g.x + 5, g.y + g.h + 3) == -2);
                }
        // L1 / R1 page: the clamped rows per page (Normal keeps maxVisible - 1)
        const U::PanelFit c = U::fitPanel(U::ExtraLarge, 520, 46, 40, 1, 11, false);
        CHECK(std::max(1, std::min(11, c.vis) - 1) == c.vis - 1 && c.vis < 11);
    }
    // examples worth knowing: Options (1000 wide) at Extra large is width-limited to 1.248; the context menu keeps 1.5
    CHECK(U::fitPanel(U::ExtraLarge, 1000, 92, 30, 2, 4, false).zoom == 1.248);
    {
        const U::PanelFit c = U::fitPanel(U::ExtraLarge, 520, 46, 20, 1, 11, false, 1.5);
        CHECK(c.zoom == 1.5 && c.vis < 11 && c.vis >= 3);
        std::printf("context menu at XL: zoom %.3f, %d rows per page (11 at Normal)\n", c.zoom, c.vis);
        const U::PanelFit d = U::fitPanel(U::ExtraLarge, 760, 50, 20, 1, 9, true, 1.5);
        std::printf("default panel at XL: zoom %.3f, %d rows per page (9 at Normal)\n", d.zoom, d.vis);
    }
    // anchored (context menu) panel stays on screen when opened at the far bottom-right
    {
        const U::PanelFit f = U::fitPanel(U::ExtraLarge, 520, 46, 6, 1, 11, false, 1.0, 1279, 719);
        CHECK((f.x + f.w) * f.zoom <= 1280 && (f.y + f.h) * f.zoom <= 720);
    }
    // stage 2 (OMNI_UI_SCALE_V1_R2): fitBox for the fixed-layout regions, as apply_ui_scale.py / OmniUiScalePanels.h use it
    {
        struct R { const char* name; int w, fixedH, rowH, maxRows, top, bottom, margin, unscaled; };
        const R regions[] = {
            { "history", 980, 90, 50, 9, 0, 688, 10, 0 }, { "history typing", 980, 80, 50, 4, 0, 362, 8, 0 },
            { "browser tools", 600, 600, 0, 0, 0, 688, 10, 0 }, { "settings", 680, 524, 0, 0, 0, 688, 10, 0 },
            { "error (bars)", 700, 264, 0, 0, 164, 688, 10, 0 }, { "error (no bars)", 700, 264, 0, 0, 0, 720, 10, 0 },
            { "qr", 620, 152, 0, 0, 0, 688, 8, 432 }, { "qr short", 620, 128, 0, 0, 0, 688, 8, 300 },
        };
        for (int l = 0; l < U::kLevelCount; ++l)
            for (const R& r : regions) {
                const U::BoxFit f = U::fitBox(l, r.w, r.fixedH, r.rowH, r.maxRows, r.top, r.bottom, r.margin, r.unscaled);
                const double left = f.x * f.zoom, right = (f.x + f.w) * f.zoom, top = f.y * f.zoom;
                const double bottom = (f.y + r.fixedH + f.rows * r.rowH) * f.zoom + r.unscaled;
                CHECK(left >= 0 && right <= 1280 + 0.5);
                CHECK(top >= r.top + r.margin - 1 && bottom <= r.bottom - r.margin + 1.5);
                CHECK(f.rows <= r.maxRows && (r.maxRows == 0 || f.rows >= std::min(3, r.maxRows)));
                if (l >= U::Normal) CHECK(f.zoom >= 1.0 && f.zoom <= U::scaleOf(l));
                else CHECK(f.zoom <= 1.0);
                if (l == U::Normal) CHECK(f.zoom == 1.0 && f.rows == r.maxRows);
                // a screen point on the drawn region -> toNormal: the Normal point whose zoomed drawing covers it
                // (the first screen pixel of each zoomed unit maps to that unit; at Small a unit is under one pixel)
                const int nx = 150, ny = 74;
                for (int k = 0; k < 4; ++k) {
                    const int ix = 3 + k * (r.w - 7) / 3, iy = 2 + k * (r.fixedH + f.rows * r.rowH - 5) / 3;
                    int sx = int(std::ceil((f.x + ix) * f.zoom)), sy = int(std::ceil((f.y + iy) * f.zoom));
                    const int sx0 = sx, sy0 = sy;
                    CHECK(U::toNormal(f.zoom, f.x, f.y, nx, ny, f.w, r.fixedH + f.rows * r.rowH, sx, sy));
                    CHECK((f.x + sx - nx) * f.zoom <= sx0 + 1e-9 && sx0 < (f.x + sx - nx + 1) * f.zoom);
                    CHECK((f.y + sy - ny) * f.zoom <= sy0 + 1e-9 && sy0 < (f.y + sy - ny + 1) * f.zoom);
                    if (f.zoom >= 1.0) CHECK(sx == nx + ix && sy == ny + iy);
                }
                // just past the drawn bottom (rows that are not drawn at this zoom): far off, not on a Normal row
                int sx = int((f.x + 5) * f.zoom), sy = int((f.y + r.fixedH + f.rows * r.rowH + 1) * f.zoom) + 1;
                CHECK(!U::toNormal(f.zoom, f.x, f.y, nx, ny, f.w, r.fixedH + f.rows * r.rowH, sx, sy) && sx == U::kOff && sy == U::kOff);
            }
        const U::BoxFit h = U::fitBox(U::ExtraLarge, 980, 90, 50, 9);
        const U::BoxFit m = U::fitBox(U::ExtraLarge, 600, 600);
        const U::BoxFit s = U::fitBox(U::ExtraLarge, 680, 524);
        const U::BoxFit q = U::fitBox(U::ExtraLarge, 620, 152, 0, 0, 0, 688, 8, 432);
        std::printf("XL: history zoom %.3f %d rows (9); browser tools %.3f; settings %.3f; qr %.3f\n", h.zoom, h.rows, m.zoom, s.zoom, q.zoom);
        CHECK(h.rows < 9 && h.zoom == 1.273 && m.zoom > 1.1 && s.zoom > 1.27 && q.zoom == 1.5);
        CHECK(U::fitBox(U::Large, 680, 524).zoom == 1.25);   // the settings panel gets the full Large
        CHECK(U::fitBox(U::Small, 980, 90, 50, 9).rows == 9 && U::fitBox(U::Small, 980, 90, 50, 9).zoom == 0.85);
        // toast width cap (OmniUiScalePanels.h omniUisToast): the pill fits the screen at every level
        for (int l = 0; l < U::kLevelCount; ++l) {
            const double z = U::scaleOf(l);
            const int W = U::zoomedW(z), icon = 28, textMax = std::min(940, W - 32 - 48 - icon);
            CHECK((textMax + 48 + icon) * z <= 1280 - 32 * z + 1);
        }
        // fill bar (OmniFeatures2.h, R3 locals): the strip ends above the (zoomed) keyboard's top, as at Normal
        for (int l = 0; l < U::kLevelCount; ++l) {
            const double z = l == U::Normal ? 1.0 : U::scaleOf(l);
            const int kbTop = U::fitKeyboard(l).top;
            const int kbY = U::toZoomed(kbTop, z) + 58, stripY = kbY - 58 - 48;
            CHECK(stripY >= 0 && (stripY + 40) * z <= kbTop - 8 * z + 1);
            if (l == U::Normal) CHECK(kbY == 420 && U::zoomedW(z) == 1280);
        }
    }
    // stage 3 (OMNI_UI_SCALE_V1_R3): the on-screen keyboard
    {
        // Normal: today's constants, and the general formula gives them too
        const U::KbFit n = U::fitKeyboard(U::Normal), g = U::fitKeyboard(U::Normal, 304, 1.0, false);
        CHECK(n.zoom == 1.0 && n.x == 200 && n.y == 420 && n.pitch == 40 && n.top == 362);
        CHECK(g.zoom == 1.0 && g.x == 200 && g.y == 420 && g.pitch == 40 && g.top == 362);
        // a row of keys as OMNI_KEYBOARD_V2 lays them out (units), and omniKbClick's hit test, copied
        const float rowUnits[][11] = { { 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0 }, { 1.5f, 1, 1, 1, 1, 1, 1, 1, 1.5f, 0 }, { 2, 5, 1.5f, 1.5f, 0 } };
        auto keyAt = [](int X, int Y, int pitch, const float* units, int r, int x, int y, int& col) {   // -> row or -1
            if (x < X || x >= X + 880) return -1;
            int hit = -1;
            for (int i = 0; i < 6; ++i) { const int top = i < 5 ? Y + i * pitch : Y + 5 * pitch; if (y >= top && y < top + pitch - 4) hit = i; }
            if (hit != r) return hit;
            const float at = float(x - X) / 88;
            float u = 0;
            col = -1;
            for (int c = 0; units[c] > 0; ++c) { u += units[c]; if (at < u) { col = c; break; } }
            return hit;
        };
        for (int l = 0; l < U::kLevelCount; ++l)
            for (int minTop : { 304, 362, 246 + 140, 0 })
                for (double hz : { 1.0, 1.5 }) {
                    const U::KbFit f = U::fitKeyboard(l, minTop, hz);
                    const double bottomPx = 720 - 32 * hz - 22;
                    const double left = (f.x - 16) * f.zoom, right = (f.x + 880 + 16) * f.zoom;
                    const double top = (f.y - 58) * f.zoom, bottom = (f.y + 6 * f.pitch + 6) * f.zoom;
                    CHECK(left >= 0 && right <= 1280 + 0.5);
                    if (l != U::Normal || hz == 1.0) CHECK(bottom <= bottomPx + 0.01 && bottom >= bottomPx - f.zoom);   // Normal: today's, always
                    CHECK(f.pitch >= U::kKbMinPitch && f.pitch <= U::kKbPitch);
                    CHECK(std::abs(f.top - std::floor(top)) < 1e-9);
                    if (l >= U::Normal) CHECK(f.zoom >= 1.0 && f.zoom <= U::scaleOf(l)); else CHECK(f.zoom <= 1.0);
                    if (l == U::Normal) CHECK(f.zoom == 1.0 && f.x == 200 && f.y == 420 && f.pitch == 40);   // Normal never moves
                    // the page stays visible: the panel's top at or below minTop unless the floor zoom with the
                    // smallest rows still does not fit (then it is the Normal-size keyboard with pitch 32)
                    if (l != U::Normal && (bottomPx - minTop) >= U::kbPanelH(U::kKbMinPitch) * std::min(1.0, U::scaleOf(l)))
                        CHECK(top >= minTop - 0.01);
                    // every key's centre, drawn at (zoomed layout) -> screen px -> toZoomed -> omniKbClick: that key
                    for (int r = 0; r < 6; ++r) {
                        const float* units = rowUnits[r % 3];
                        const int y = r < 5 ? f.y + r * f.pitch : f.y + 5 * f.pitch;
                        float u = 0;
                        for (int c = 0; units[c] > 0; ++c) {
                            const int x0 = f.x + int(u * 88 + 0.5f);
                            u += units[c];
                            const int w = f.x + int(u * 88 + 0.5f) - x0 - 4;
                            const int sx = int((x0 + w / 2.0) * f.zoom), sy = int((y + (f.pitch - 4) / 2.0) * f.zoom);
                            int col = -2;
                            const int row = keyAt(f.x, f.y, f.pitch, units, r, U::toZoomed(sx, f.zoom), U::toZoomed(sy, f.zoom), col);
                            CHECK(row == r && col == c);
                        }
                    }
                    // the accent popup (omniKblGeometry: cells 56 x 48 above the key) and the word chips (stored
                    // by the draw in zoomed layout px): a cell / chip centre maps back into it
                    const int px = f.x + 200, py = f.y - 48 - 8;
                    for (int i = 0; i < 4; ++i) {
                        const int sx = int((px + i * 56 + 28) * f.zoom), sy = int((py + 24) * f.zoom);
                        const int zx = U::toZoomed(sx, f.zoom), zy = U::toZoomed(sy, f.zoom);
                        CHECK(zy >= py && zy < py + 48 && (zx - px) / 56 == i);
                    }
                    const int chipX = f.x + 880 - 300, chipY = f.y - 50 + 5, chipH = 30;
                    const int cx = U::toZoomed(int((chipX + 50) * f.zoom), f.zoom), cy = U::toZoomed(int((chipY + chipH / 2.0) * f.zoom), f.zoom);
                    CHECK(cx >= chipX && cx < chipX + 100 && cy >= chipY && cy < chipY + chipH);
                    // the shortcut tiles: 4 columns of 220, 5 rows + the action row
                    for (int i = 0; i < 20; ++i) {
                        const int tx = f.x + i % 4 * 220, ty = f.y + i / 4 * f.pitch;
                        const int zx = U::toZoomed(int((tx + 108) * f.zoom), f.zoom), zy = U::toZoomed(int((ty + (f.pitch - 4) / 2.0) * f.zoom), f.zoom);
                        CHECK((zx - f.x) / 220 == i % 4 && (zy - f.y) / f.pitch == i / 4);
                    }
                }
        const U::KbFit L = U::fitKeyboard(U::Large), X = U::fitKeyboard(U::ExtraLarge), M = U::fitKeyboard(U::ExtraLarge, U::kKbNormalTop);
        const U::KbFit S = U::fitKeyboard(U::Small);
        std::printf("keyboard: Large zoom %.3f pitch %d top %d; XL %.3f pitch %d top %d; XL under a compact dialog %.3f pitch %d top %d; Small %.3f top %d\n",
                    L.zoom, L.pitch, L.top, X.zoom, X.pitch, X.top, M.zoom, M.pitch, M.top, S.zoom, S.top);
        CHECK(L.zoom == 1.25 && X.zoom == 1.368 && X.pitch >= 32 && X.top >= 304 && M.top >= 362 && M.zoom > 1.1 && S.pitch == 40);
        // with stage 4's bars at Extra large (246) the keyboard still fits, at a lower zoom, never below 1
        const U::KbFit B = U::fitKeyboard(U::ExtraLarge, 246 + U::kKbMinPage);
        CHECK(B.zoom >= 1.0 && B.pitch == U::kKbMinPitch);

        // the address suggestions above the keyboard (fitList): rows >= min(n, 3), the list + tip end above the
        // keyboard's top, the window keeps the selection, a click on each drawn row selects that suggestion
        for (int l = 0; l < U::kLevelCount; ++l)
            for (int minTop : { 304, 362 })
                for (int n = 1; n <= 5; ++n)
                    for (int sel = -1; sel < n; ++sel) {
                        const U::KbFit kb = U::fitKeyboard(l, minTop);
                        const U::ListFit f = U::fitList(l, kb.zoom, 914, 36, 46, n, sel, 108, kb.top);
                        CHECK(f.rows >= std::min(n, 3) && f.rows <= n && f.first >= 0 && f.first + f.rows <= n);
                        if (sel >= 0) CHECK(sel >= f.first && sel < f.first + f.rows);
                        if (l >= U::Normal) CHECK(f.zoom >= 1.0 && f.zoom <= U::scaleOf(l)); else CHECK(f.zoom <= 1.0);
                        CHECK(f.x * f.zoom >= 0 && (f.x + 914) * f.zoom <= 1280 + 0.5 && f.y * f.zoom >= 108 - 0.01);
                        if (f.zoom > 1.0 || l < U::Normal) CHECK((f.y + 36 + f.rows * 46) * f.zoom <= kb.top + 1.0);
                        for (int k = 0; k < f.rows; ++k) {
                            int x = int((f.x + 457) * f.zoom), y = int((f.y + 4 + k * 46 + 23) * f.zoom);
                            x = U::toZoomed(x, f.zoom); y = U::toZoomed(y, f.zoom);
                            const int hit = (x >= f.x && x < f.x + 914 && y >= f.y) ? (y - f.y - 4) / 46 : -1;
                            CHECK(hit == k);
                        }
                        // the keyboard's top row is not a suggestion
                        const int ky = U::toZoomed(int((kb.y + 10) * kb.zoom), f.zoom);
                        CHECK((ky - f.y - 4) / 46 >= f.rows);
                    }
        const U::ListFit sx = U::fitList(U::ExtraLarge, X.zoom, 914, 36, 46, 5, -1, 108, X.top);
        std::printf("suggestions at XL: zoom %.3f, %d of 5 rows\n", sx.zoom, sx.rows);
        CHECK(U::fitList(U::Small, 0.85, 914, 36, 46, 5, -1, 108, S.top).rows == 5);

        // the find bar: right edge 1260 and top kept, clicks map back to today's coordinates
        for (int l = 0; l < U::kLevelCount; ++l)
            for (int pageTop : { 0, 112, 164 }) {
                const double z = U::scaleOf(l);
                const int ny = std::max(8, pageTop + 10), x = U::zoomedLeft(1260, 584, z), y = U::zoomedTop(ny, z);
                CHECK((x + 584) * z <= 1260 + 0.01 && (x + 585) * z > 1260 - 0.01 && y * z >= ny && (y - 1) * z < ny && x * z >= 0);
                for (int part : { 10, 300, 450, 520, 570 }) {   // "Find" text, query, back, forward, close
                    int sx = int(std::ceil((x + part) * z)), sy = int(std::ceil((y + 25) * z));
                    CHECK(U::toNormal(z, x, y, 676, ny, 584, 50, sx, sy) && (z < 1.0 || (sx == 676 + part && sy == ny + 25)));
                }
            }

        // the hint line: fits the width, at most kHintLineMax until stage 4 grows the bar, Large / XL never below 1
        for (int l = 0; l < U::kLevelCount; ++l)
            for (int natural : { 0, 600, 1000, 1150, 1262, 1400 }) {
                const double z = U::hintLineZoom(l, natural);
                CHECK(z <= U::scaleOf(l) && z <= U::kHintLineMax);
                if (l >= U::Normal) CHECK(z >= 1.0);
                if (natural > 0 && natural * std::min(1.0, U::scaleOf(l)) <= 1262) CHECK(natural * z <= 1262 + 0.5);
            }
        CHECK(U::hintLineZoom(U::Normal, 900) == 1.0 && U::hintLineZoom(U::ExtraLarge, 0) == 1.25 && U::hintLineZoom(U::ExtraLarge, 1100) == 1.147);
    }
    // bars
    CHECK(U::barHeight(164, U::Normal) == 164 && U::barHeight(112, U::ExtraLarge) == 168 && U::barHeight(164, U::Small) == 139);
    for (int l = 0; l < U::kLevelCount; ++l) CHECK(U::barsFit(164, l) && U::barsFit(112, l));

    // stage 4 (OMNI_UI_SCALE_V1_R4)
    {
        // top bar: text-only zoom; the bars (and so the page area) keep their height; the zoomed line of each face fits
        // the box it is drawn in (tabs 44 / tiles 44 / field 40: the 17 px face; Protection pill 36 and the badge row:
        // the 14 px captions); a line is about 1.25 x the face size
        CHECK(U::barTextZoom(U::Normal) == 1.0 && U::barTextZoom(U::Large) == 1.25 && U::barTextZoom(U::ExtraLarge) == 1.5
              && U::barTextZoom(U::Small) == 0.85);
        struct Box { int h, face; };
        for (int l = 0; l < U::kLevelCount; ++l)
            for (const Box& b : { Box { 44, 17 }, Box { 40, 17 }, Box { 36, 14 }, Box { 44, 14 } })
                CHECK(b.face * 1.25 * U::barTextZoom(l) <= b.h - 4);
        // a word capped to its pill: fits (or keeps Normal size when even that does not), never above the zoom
        for (int l = 0; l < U::kLevelCount; ++l)
            for (double natural : { 0.0, 40.0, 62.0, 70.0, 78.0, 90.0 }) {
                const double z0 = U::barTextZoom(l), z = U::capZoom(z0, natural, 78);
                CHECK(z <= z0 && z >= std::min(1.0, z0));
                if (natural > 0 && natural * std::min(1.0, z0) <= 78) CHECK(natural * z <= 78 + 1e-9);
                if (l == U::Normal) CHECK(z == 1.0);
            }
        CHECK(std::abs(U::capZoom(1.5, 60, 78) - 1.3) < 0.0015 && U::capZoom(1.25, 60, 78) == 1.25);
        // hints bar: at most kHintLineMax (the bar keeps 32 px), fits the width, Large / XL never below 1, Normal 1
        for (int l = 0; l < U::kLevelCount; ++l)
            for (int natural : { 0, 400, 800, 1024, 1100, 1280, 1500 }) {
                const double z = U::hintsZoom(l, natural);
                CHECK(z <= U::scaleOf(l) && z <= U::kHintLineMax);
                if (l >= U::Normal) CHECK(z >= 1.0);
                if (l == U::Normal) CHECK(z == 1.0);
                if (natural > 0 && natural * std::min(1.0, U::scaleOf(l)) <= 1280) CHECK(natural * z <= 1280 + 0.5);
            }
        CHECK(U::hintsZoom(U::ExtraLarge, 700) == 1.25 && U::hintsZoom(U::ExtraLarge, 1100) == 1.163 && U::hintsZoom(U::Small, 1400) == 0.85);

        // dialogs (omniModalLayout's numbers): w, fixed part, line / row height, lines / rows, compact
        struct D { const char* name; int w, fixedH, rowH, rows; bool compact; int buttons; };
        const D dialogs[] = {
            { "alert 9 lines", 760, 160, 30, 9, false, 1 }, { "confirm 3", 760, 160, 30, 3, false, 2 },
            { "prompt 5", 760, 220, 30, 5, false, 2 }, { "login", 760, 358, 30, 2, false, 2 },
            { "select 11", 640, 94, 40, 11, false, 0 }, { "select 4", 640, 94, 40, 4, false, 0 },
            { "compact prompt", 760, 144, 30, 1, true, 0 }, { "compact login", 760, 244, 30, 0, true, 0 },
        };
        for (int l = 0; l < U::kLevelCount; ++l)
            for (const D& d : dialogs) {
                const U::BoxFit f = U::fitDialog(l, d.w, d.fixedH, d.rowH, d.rows, d.compact);
                const int h = d.fixedH + f.rows * d.rowH;
                CHECK(f.x * f.zoom >= 0 && (f.x + d.w) * f.zoom <= 1280 + 0.5);
                if (d.compact) CHECK(f.y * f.zoom >= 116 - 0.01 && (f.y + h) * f.zoom <= 374 + 1.0);
                else CHECK(f.y * f.zoom >= 10 - 1 && (f.y + h) * f.zoom <= 688 - 10 + 1.5);
                CHECK(f.rows <= d.rows && f.rows >= std::min(3, d.rows));
                if (l >= U::Normal) CHECK(f.zoom >= 1.0 && f.zoom <= U::scaleOf(l)); else CHECK(f.zoom <= 1.0);
                if (l == U::Normal) CHECK(f.zoom == 1.0 && f.rows == d.rows);
                // buttons (bottom-right, 46 tall, 132+ wide) and select rows: their drawn centres map back onto them
                for (int i = 0; i < d.buttons; ++i) {
                    const int bw = 132, bx = f.x + d.w - 28 - (i + 1) * bw - i * 12, by = f.y + h - 28 + 4 - 46;
                    const int sx = int((bx + bw / 2.0) * f.zoom), sy = int((by + 23) * f.zoom);
                    const int zx = U::toZoomed(sx, f.zoom), zy = U::toZoomed(sy, f.zoom);
                    CHECK(zx >= bx && zx < bx + bw && zy >= by && zy < by + 46);
                }
                if (d.rowH == 40)
                    for (int r = 0; r < f.rows; ++r) {
                        const int listY = f.y + 28 + 34 + 10, ry = listY + r * 40;
                        const int zy = U::toZoomed(int((ry + 20) * f.zoom), f.zoom);
                        CHECK((zy - listY) / 40 == r);
                    }
            }
        const U::BoxFit sel = U::fitDialog(U::ExtraLarge, 640, 94, 40, 11, false), al = U::fitDialog(U::ExtraLarge, 760, 160, 30, 9, false);
        std::printf("dialogs at XL: select %.3f %d rows (11), alert %.3f %d lines (9)\n", sel.zoom, sel.rows, al.zoom, al.rows);

        // the screenshot grid (tiles 256 x 191, gap 10, header 64, padding 24 / 12): Normal = today's 4 x 3 at (101, 9)
        const U::GridFit n = U::fitGrid(U::Normal, 256, 191, 10, 4, 3, 64, 24, 12);
        CHECK(n.zoom == 1.0 && n.cols == 4 && n.rows == 3 && n.x == 101 && n.y == 9 && n.w == 1078 && n.h == 669);
        CHECK(n.x == (1280 - 1078) / 2 && n.y == std::max(6, (720 - 32 - 669) / 2));
        for (int l = 0; l < U::kLevelCount; ++l) {
            const U::GridFit g = U::fitGrid(l, 256, 191, 10, 4, 3, 64, 24, 12);
            CHECK(g.x * g.zoom >= 0 && (g.x + g.w) * g.zoom <= 1280 + 0.5 && g.y * g.zoom >= 6 - 1 && (g.y + g.h) * g.zoom <= 688 + 0.5);
            CHECK(g.rows >= 2 && g.cols >= 1 && g.cols <= 4 && g.rows <= 3);
            if (l >= U::Normal) CHECK(g.zoom >= 1.0 && g.zoom <= U::scaleOf(l)); else CHECK(g.zoom <= 1.0);
            // every tile's centre (drawn in the zoomed space) -> screen -> toZoomed -> omniSsClick's test: that tile
            for (int k = 0; k < g.cols * g.rows; ++k) {
                const int tx = g.x + 12 + (k % g.cols) * 266, ty = g.y + 64 + (k / g.cols) * 201;
                const int zx = U::toZoomed(int((tx + 128) * g.zoom), g.zoom), zy = U::toZoomed(int((ty + 95) * g.zoom), g.zoom);
                int hit = -1;
                for (int j = 0; j < g.cols * g.rows; ++j) {
                    const int jx = g.x + 12 + (j % g.cols) * 266, jy = g.y + 64 + (j / g.cols) * 201;
                    if (zx >= jx && zx < jx + 256 && zy >= jy && zy < jy + 191) hit = j;
                }
                CHECK(hit == k);
            }
        }
        const U::GridFit gl = U::fitGrid(U::Large, 256, 191, 10, 4, 3, 64, 24, 12), gx = U::fitGrid(U::ExtraLarge, 256, 191, 10, 4, 3, 64, 24, 12);
        const U::GridFit gs = U::fitGrid(U::Small, 256, 191, 10, 4, 3, 64, 24, 12);
        std::printf("screenshot grid: Large %dx%d @%.3f, XL %dx%d @%.3f, Small %dx%d @%.3f\n", gl.cols, gl.rows, gl.zoom, gx.cols, gx.rows, gx.zoom,
                    gs.cols, gs.rows, gs.zoom);
        CHECK(gl.cols == 3 && gl.rows == 2 && gl.zoom == 1.25 && gx.cols == 3 && gx.rows == 2 && gx.zoom == 1.444);
        CHECK(gs.cols == 4 && gs.rows == 3 && gs.zoom == 0.85);

        // OSG::Pager with the grid (OmniShotGallery.h, r4): 4 x 3 = today's arithmetic (kPerPage / kCols), 3 x 2 pages by 6
        namespace G = OmniShotGallery;
        for (int count : { 0, 1, 5, 12, 13, 25, 40 })
            for (int sel = 0; sel < std::max(1, count); ++sel) {
                G::Pager p; p.count = count; p.sel = sel;
                CHECK(p.page() == (count > 0 ? sel / G::kPerPage : 0) && p.pages() == (count > 0 ? (count + G::kPerPage - 1) / G::kPerPage : 1));
                CHECK(p.first() == p.page() * G::kPerPage && p.onPage() == (count > 0 ? std::min(G::kPerPage, count - p.first()) : 0));
                G::Pager down = p; down.move(0, 1);
                const int want = count <= 0 ? sel : sel + G::kCols < count ? sel + G::kCols : (count - 1) / G::kCols > sel / G::kCols ? count - 1 : sel;
                CHECK(down.sel == want);
                G::Pager q = p; q.cols = 3; q.rows = 2;
                CHECK(q.page() == (count > 0 ? sel / 6 : 0) && q.pages() == (count > 0 ? (count + 5) / 6 : 1) && q.onCurrentPage(sel) == (count > 0));
                G::Pager qd = q; qd.move(0, 1);
                CHECK(qd.sel == (count <= 0 ? sel : sel + 3 < count ? sel + 3 : (count - 1) / 3 > sel / 3 ? count - 1 : sel));
                G::Pager qn = q;
                if (qn.pageBy(1)) CHECK(qn.page() == q.page() + 1 && qn.sel == std::min(count - 1, sel + 6));
            }
    }
    // memory
    CHECK(U::facePx(22, 1.5, 1.0) == 33 && U::facePx(22, 3.0, 1.5) == 99);
    CHECK(U::extraBytes(U::Normal, 3.0) == 0);
    CHECK(U::faceSetBytes(1.5, 1.5) < U::faceSetBytes(3.0, 1.5));
    for (double ds : { 1.5, 3.0 }) {
        std::printf("displayScale %.1f:", ds);
        for (int l = 0; l < U::kLevelCount; ++l)
            std::printf(" %s faces+%.1f MB text %.1f MB (cap %d entries @48MB);", U::kLevels[l].id, U::extraBytes(l, ds) / 1048576.0,
                        U::textCacheBytes(ds, U::scaleOf(l)) / 1048576.0, U::textCacheEntries(ds, U::scaleOf(l), 48ull << 20));
        std::printf("\n");
    }
    CHECK(U::textCacheEntries(1.5, 1.0, 48ull << 20) == 256);              // 1080p Normal: today's 256 kept
    CHECK(U::textCacheEntries(3.0, 1.5, 48ull << 20) < 256 && U::textCacheEntries(3.0, 1.5, 48ull << 20) >= 16);
    CHECK(U::textCacheBytes(3.0, 1.5, U::textCacheEntries(3.0, 1.5, 48ull << 20)) <= (48ull << 20));
    CHECK(U::maxLevelFor(3.0, 64ull << 20) == U::ExtraLarge);             // 4K Extra large fits a 64 MB face budget
    CHECK(U::maxLevelFor(3.0, 1ull << 20) == U::Normal);
    CHECK(U::effectiveLevel(U::ExtraLarge, 3.0, 1ull << 20) == U::Normal && U::effectiveLevel(U::Small, 3.0, 0) == U::Small);
    std::printf("%s: %d checks, %d failed\n", fails ? "FAIL" : "ok", checks, fails);
    return fails ? 1 : 0;
}
