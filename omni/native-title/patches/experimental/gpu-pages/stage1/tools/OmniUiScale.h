// OMNI_UI_SCALE_V1: the pure part of Browser settings > "Interface size" (Small / Normal / Large / Extra large):
// the size of Omni's own UI (bars, tabs strip, panels, menus, keyboard, notices), not page zoom. No SDL, no WebKit.
// Installed by tools/apply_ui_scale.py (stage 1: + panels and the settings row, OmniUiScaleShell.h; OMNI_UI_SCALE_V1_R2
// stage 2: + fitBox / toNormal for the fixed-layout regions, OmniUiScalePanels.h; OMNI_UI_SCALE_V1_R3 stage 3: + fitKeyboard /
// fitList / hintLineZoom for the on-screen keyboard and the lists around it; OMNI_UI_SCALE_V1_R4 stage 4: + barTextZoom /
// capZoom / hintsZoom / fitDialog / fitGrid for the bars, the dialogs and the screenshot grid).
// Tested on the host with g++ (tools/test_ui_scale.cpp).
//
// Model: the shell lays everything out in a fixed 1280x720 layout space and draws it with physical(v) = v * displayScale.
// A UI region (a panel, the keyboard, a notice, the bars) is zoomed by drawing it with displayScale * zoom in a layout
// space of 1280/zoom x 720/zoom, so every offset, radius, icon and font inside it grows together; pointer positions
// are mapped into that space with toZoomed(). fitPanel() picks the zoom and the rows per page so a panel always fits
// (1080p and 4K have the same 1280x720 layout space, so one fit serves both).
#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <string>

namespace OmniUiScale {

enum Level { Small = 0, Normal = 1, Large = 2, ExtraLarge = 3, kLevelCount = 4 };
struct LevelInfo { const char* id; const char* name; int permille; };
constexpr LevelInfo kLevels[kLevelCount] = {
    { "small", "Small", 850 },
    { "normal", "Normal", 1000 },
    { "large", "Large", 1250 },
    { "xlarge", "Extra large", 1500 },
};
constexpr int kDefault = Normal;
constexpr const char* kFile = "/data/omni/ui-scale.txt";
constexpr int kLayoutW = 1280, kLayoutH = 720, kHintsH = 32;   // the shell's width / height / bottom
constexpr int kMargin = 10;                                    // omniFxGeometry keeps panels 10 px from the edges

inline int clampLevel(int level) { return std::clamp(level, 0, kLevelCount - 1); }
inline double scaleOf(int level) { return kLevels[clampLevel(level)].permille / 1000.0; }
inline int permilleOf(int level) { return kLevels[clampLevel(level)].permille; }
inline const char* nameOf(int level) { return kLevels[clampLevel(level)].name; }
// The stepper row (Left / Right): no wrap-around, so holding Right never jumps back to Small.
inline int stepped(int level, int dir) { return clampLevel(clampLevel(level) + (dir < 0 ? -1 : dir > 0 ? 1 : 0)); }

// ui-scale.txt: one id per line ("large\n"); unknown or empty text is Normal. Names and a few aliases are accepted.
inline int parse(const std::string& text)
{
    std::string s;
    for (char c : text) {
        if (c == '\r' || c == '\n') { if (!s.empty()) break; continue; }
        if (c == ' ' || c == '\t' || c == '-' || c == '_') continue;
        s += (c >= 'A' && c <= 'Z') ? char(c + 32) : c;
    }
    if (s == "small" || s == "s") return Small;
    if (s == "normal" || s == "default" || s == "m") return Normal;
    if (s == "large" || s == "l") return Large;
    if (s == "xlarge" || s == "extralarge" || s == "xl") return ExtraLarge;
    return kDefault;
}
inline std::string serialize(int level) { return std::string(kLevels[clampLevel(level)].id) + "\n"; }

// A layout length at `zoom` (rounded, never 0 for a non-zero length).
inline int scaled(int layoutPx, double zoom)
{
    const int v = int(std::lround(layoutPx * zoom));
    return layoutPx > 0 ? std::max(1, v) : v;
}
// A screen layout position (pointerX / pointerY) in the zoomed layout space of a region drawn with displayScale * zoom.
inline int toZoomed(double layoutPos, double zoom) { return zoom > 0 ? int(std::floor(layoutPos / zoom)) : int(layoutPos); }
inline int zoomedW(double zoom) { return int(kLayoutW / zoom); }
inline int zoomedH(double zoom) { return int(kLayoutH / zoom); }

// Rows that fit in `availablePx` (layout px at zoom 1) of rows `rowH` tall at `zoom`, between minRows and maxRows.
inline int rowsPerPage(int availablePx, int rowH, double zoom, int minRows, int maxRows)
{
    if (rowH <= 0 || zoom <= 0) return std::max(1, minRows);
    const int fit = int(std::floor(availablePx / (rowH * zoom)));
    return std::clamp(fit, std::max(1, minRows), std::max(std::max(1, minRows), maxRows));
}

// An OmniFxPanel at a level: the zoom it is drawn with and its geometry in that zoomed layout space (what
// omniFxGeometry returns, with width/height/bottom replaced by zoomedW/zoomedH/hintsH). Rules:
//   - zoom = the level's scale, lowered until the panel's width fits the screen (1280 - 2 * 16);
//   - rows per page = the panel's own maxVisible, fewer when header + rows would not fit above the hints bar;
//   - at least min(rows, 3) rows stay visible: the zoom is lowered further (never below the level's floor of 1.0
//     for Large / Extra large, i.e. a panel never gets smaller than Normal) until they do.
// hintsZoom: the zoom the hints bar is drawn with (its height is kHintsH * hintsZoom).
struct PanelFit { double zoom; int vis, x, y, w, h, header, listY; };
inline PanelFit fitPanel(int level, int w, int rowH, int rows, int cols, int maxVisible, bool subtitle, double hintsZoom = 1.0,
                         int anchorX = -1, int anchorY = -1)
{
    PanelFit f {};
    const double want = scaleOf(level), floorZoom = std::min(1.0, want);
    f.header = subtitle ? 88 : 64;
    const int lines = cols > 1 ? (rows + cols - 1) / std::max(1, cols) : rows;
    const int wantRows = std::max(1, std::min(lines, maxVisible));
    const int minRows = std::min(wantRows, 3);
    const double hintsPx = kHintsH * std::max(1.0, hintsZoom);
    double zoom = std::min(want, double(kLayoutW - 32) / std::max(1, w));
    auto fits = [&](double z, int n) { return (f.header + n * rowH + 14) * z + 2 * kMargin <= kLayoutH - hintsPx; };
    if (!fits(zoom, minRows)) zoom = (kLayoutH - hintsPx - 2 * kMargin) / double(f.header + minRows * rowH + 14);
    zoom = std::max(zoom, floorZoom);
    zoom = std::floor(zoom * 1000) / 1000;   // stable keys for the face / icon caches
    f.zoom = zoom;
    const int roomPx = int(std::floor((kLayoutH - hintsPx - 2 * kMargin) / zoom)) - f.header - 14;
    f.vis = rowsPerPage(roomPx, rowH, 1.0, 1, wantRows);
    while (f.vis > 1 && !fits(zoom, f.vis)) --f.vis;
    const int W = zoomedW(zoom), H = zoomedH(zoom), bottom = int(std::ceil(hintsPx / zoom));
    f.w = std::min(w, W - 2 * kMargin);
    f.h = f.header + f.vis * rowH + 14;
    if (anchorX >= 0) {   // context menu: next to the pointer, positions given in screen layout px
        f.x = std::clamp(toZoomed(anchorX, zoom) + 18, 16, std::max(16, W - f.w - 16));
        f.y = std::clamp(toZoomed(anchorY, zoom) - 24, 12, std::max(12, H - bottom - f.h - 10));
    } else {
        f.x = (W - f.w) / 2;
        f.y = std::max(kMargin, (H - bottom - f.h) / 2);
    }
    f.listY = f.y + f.header;
    return f;
}

// --- stage 2 (OMNI_UI_SCALE_V1_R2): fixed-layout regions ---------------------------------------------------------
// A region with its own geometry (QR code panel, History, Browser tools, controller settings, error page, toast, fill
// bar) at a level: the zoom it is drawn with and its top-left in that zoomed layout space (1280/zoom x 720/zoom).
// At Normal it is `w` x (fixedH + maxRows * rowH) layout px, plus `unscaledH` screen layout px that do not grow (the QR
// code's modules are physical pixels). Rules, as fitPanel:
//   - zoom = the level's scale, lowered until the width fits the screen (1280 - 2 * 16) and min(maxRows, 3) rows plus
//     the fixed part fit in [areaTop + margin, areaBottom - margin) (screen layout px), never below min(1, scale);
//   - rows = maxRows, fewer when they do not fit at that zoom (a list pages by them: L1 / R1);
//   - centred horizontally on the screen and vertically in the area.
struct BoxFit { double zoom; int rows, x, y, w, h; };   // x, y, w, h: zoomed layout px (h: header + rows, + unscaledH / zoom)
inline BoxFit fitBox(int level, int w, int fixedH, int rowH = 0, int maxRows = 0, int areaTop = 0, int areaBottom = kLayoutH - kHintsH,
                     int margin = kMargin, int unscaledH = 0)
{
    BoxFit f {};
    const double want = scaleOf(level), floorZoom = std::min(1.0, want);
    maxRows = std::max(0, maxRows);
    const int minRows = std::min(maxRows, 3);
    const double room = areaBottom - areaTop - 2.0 * margin;
    double zoom = std::min(want, double(kLayoutW - 32) / std::max(1, w));
    auto fits = [&](double z, int n) { return (fixedH + n * rowH) * z + unscaledH <= room; };
    if (!fits(zoom, minRows)) zoom = (room - unscaledH) / std::max(1, fixedH + minRows * rowH);
    zoom = std::max(zoom, floorZoom);
    zoom = std::floor(zoom * 1000) / 1000;
    f.zoom = zoom;
    f.rows = maxRows;
    while (f.rows > 1 && !fits(zoom, f.rows)) --f.rows;
    f.w = w;
    f.h = fixedH + f.rows * rowH + int(std::ceil(unscaledH / zoom));
    f.x = std::max(0, (zoomedW(zoom) - w) / 2);
    const int a0 = int(std::ceil(areaTop / zoom)), a1 = int(std::floor(areaBottom / zoom)), m = int(std::ceil(margin / zoom));
    f.y = a0 + std::max(m, (a1 - a0 - f.h) / 2);
    return f;
}
// Hit-testing a zoomed fixed-layout region with its Normal code: the screen layout point (sx, sy) in the region's
// Normal layout coordinates. The region is drawn at zoomed (zx, zy) and is at (nx, ny) at Normal, w x h (the part
// drawn). A point off the drawn region maps far off it (false), so "outside" stays outside (rows not drawn at this
// zoom included).
constexpr int kOff = -100000;
inline bool toNormal(double zoom, int zx, int zy, int nx, int ny, int w, int h, int& sx, int& sy)
{
    const int ix = toZoomed(sx, zoom) - zx, iy = toZoomed(sy, zoom) - zy;
    if (ix < 0 || iy < 0 || ix >= w || iy >= h) { sx = sy = kOff; return false; }
    sx = nx + ix;
    sy = ny + iy;
    return true;
}

// --- stage 3 (OMNI_UI_SCALE_V1_R3): the on-screen keyboard and what sits around it ------------------------------
// The keyboard (OMNI_KEYBOARD_V2, OmniBrowser.cpp): keys 10 x 88 = 880 wide from keyboardX, rows `pitch` apart from
// keyboardY (5 rows, then the action row), the preview row (field + word chips) in the 58 px above keyboardY, the
// panel 16 px wider on each side and 6 px below the action row. At Normal: keyboardX 200, keyboardY 420, pitch 40, the
// panel 362..666 (screen), the hints bar from 688.
// At another level the whole keyboard is drawn with displayScale * zoom (text, keys, chips, accent popup together),
// its bottom edge stays where it is (22 px above the hints bar) and it grows upwards and sideways:
//   - zoom = the level's scale, lowered until the panel's width fits the screen (1280 - 2 * 16): Extra large 1.368;
//   - the page must stay visible above it: the panel's top may not go above `minTop` (screen layout px; the shell
//     passes the top bar + kKbMinPage, or kKbNormalTop while a compact dialog is above the keyboard). The key ROWS
//     give way first: the pitch shrinks from 40 down to kKbMinPitch (keys keep their full zoomed width and text);
//   - only when even that pitch does not fit is the zoom lowered (never below the level's floor: 1.0 for Large /
//     Extra large, so the keyboard never gets smaller than Normal).
// Hit-testing: the shell maps the pointer with toZoomed(.., zoom) and runs today's click code on the same numbers.
constexpr int kKbKeysW = 880, kKbPanelW = 912, kKbPreviewH = 58, kKbRows = 6, kKbPitch = 40, kKbMinPitch = 32, kKbPad = 6;
constexpr int kKbGap = 22;                 // panel bottom (666) to the hints bar (688)
constexpr int kKbNormalX = 200, kKbNormalY = 420, kKbNormalTop = 362;
constexpr int kKbMinPage = 140;            // page left visible under the top bar (Normal: 198)
struct KbFit { double zoom; int x, y, pitch, top; };   // x, y: keyboardX / keyboardY (zoomed layout px); top: screen layout px
inline int kbPanelH(int pitch) { return kKbPreviewH + kKbRows * pitch + kKbPad; }
inline KbFit kbNormal() { return { 1.0, kKbNormalX, kKbNormalY, kKbPitch, kKbNormalTop }; }
inline KbFit fitKeyboard(int level, int minTop = 164 + kKbMinPage, double hintsZoom = 1.0, bool normalAsIs = true)
{
    if (normalAsIs && clampLevel(level) == Normal) return kbNormal();
    KbFit f {};
    const double want = scaleOf(level), floorZoom = std::min(1.0, want);
    const double bottomPx = kLayoutH - kHintsH * std::max(1.0, hintsZoom) - kKbGap;   // 666 with today's hints bar
    // the rows that fit between minTop and the bottom edge, in whole zoomed layout px (as the panel is placed below)
    auto pitchAt = [&](double z) {
        const int roomZ = int(std::floor(bottomPx / z)) - int(std::ceil(minTop / z));
        return std::min(kKbPitch, int(std::floor((roomZ - kKbPreviewH - kKbPad) / double(kKbRows))));
    };
    double zoom = std::min(want, double(kLayoutW - 32) / kKbPanelW);
    if (pitchAt(zoom) < kKbMinPitch) zoom = (bottomPx - minTop) / kbPanelH(kKbMinPitch);
    zoom = std::max(zoom, floorZoom);
    zoom = std::floor(zoom * 1000) / 1000;
    while (zoom > floorZoom && pitchAt(zoom) < kKbMinPitch) zoom = std::max(floorZoom, zoom - 0.001);   // rounding
    f.zoom = zoom;
    f.pitch = std::clamp(pitchAt(zoom), kKbMinPitch, kKbPitch);
    f.x = (zoomedW(zoom) - kKbKeysW) / 2;
    f.y = int(std::floor(bottomPx / zoom)) - kKbPad - kKbRows * f.pitch;
    f.top = int(std::floor((f.y - kKbPreviewH) * zoom));
    return f;
}
// A list that drops down from `areaTop` and must end above `areaBottom` (screen layout px): the address suggestions
// (914 wide, rows 46, 8 px padding + the 28 px tip pill below) above the keyboard. zoom = the level's scale capped by
// `zoomCap` (the keyboard's zoom, so the two line up) and the width; at least min(n, 3) rows (the zoom is lowered for
// them, never below the level's floor); fewer rows than items: a window that keeps `sel` in view (first..first+rows).
struct ListFit { double zoom; int x, y, rows, first; };
inline ListFit fitList(int level, double zoomCap, int w, int padH, int rowH, int n, int sel, int areaTop, int areaBottom)
{
    ListFit f {};
    const double want = std::min(scaleOf(level), zoomCap), floorZoom = std::min(1.0, scaleOf(level));
    const double room = areaBottom - areaTop;
    n = std::max(0, n);
    const int minRows = std::min(n, 3);
    auto fits = [&](double z, int k) { return (padH + k * rowH) * z <= room; };
    double zoom = std::min(want, double(kLayoutW - 32) / std::max(1, w));
    if (!fits(zoom, minRows)) zoom = room / std::max(1, padH + minRows * rowH);
    zoom = std::max(zoom, floorZoom);
    zoom = std::floor(zoom * 1000) / 1000;
    f.zoom = zoom;
    f.rows = n;
    while (f.rows > 1 && !fits(zoom, f.rows)) --f.rows;
    f.x = (zoomedW(zoom) - w) / 2;
    f.y = int(std::ceil(areaTop / zoom));
    f.first = sel < 0 ? 0 : std::clamp(sel - f.rows + 1, 0, std::max(0, n - f.rows));
    return f;
}
// A bar anchored to the right edge and a top line (the find bar: right edge 1260, top = page top + 10): its zoomed
// top-left, the right edge and the top staying where they are at Normal.
inline int zoomedLeft(int screenRight, int w, double zoom) { return int(std::floor(screenRight / zoom)) - w; }
inline int zoomedTop(int screenTop, double zoom) { return int(std::ceil(screenTop / zoom)); }
// The keyboard's hint line (inside the hints bar): the level's scale, at most kHintLineMax while the bar keeps
// today's 32 px (stage 4 grows the bar: hintsZoom), lowered so a line `naturalW` layout px long (from x 0, its left
// margin included) ends 18 px from the right edge; Large / Extra large never below 1.
constexpr double kHintLineMax = 1.25;
inline double hintLineZoom(int level, int naturalW, double hintsZoom = 1.0)
{
    const double want = scaleOf(level);
    double z = std::min(want, kHintLineMax * std::max(1.0, hintsZoom));
    if (naturalW > 0) z = std::min(z, double(kLayoutW - 18) / naturalW);
    z = std::max(z, std::min(1.0, want));
    return std::floor(z * 1000) / 1000;
}

// The top bar (tabs strip 52 + address row 60 [+ quick-access row 52]) if it GREW with the level: its height in screen
// layout px. Stage 4 does not grow it (see below: the bars keep 164 / 112 and 32 at every level); kept as the
// worst case the stage-3 keyboard fit was checked against.
inline int barHeight(int baseLayoutPx, int level) { return scaled(baseLayoutPx, std::max(0.85, scaleOf(level))); }
// Bars may not take more than 40 % of the screen (Extra large with the quick-access row: 164 * 1.5 = 246 = 34 %).
inline bool barsFit(int baseLayoutPx, int level) { return barHeight(baseLayoutPx, level) * 10 <= kLayoutH * 4; }

// --- stage 4 (OMNI_UI_SCALE_V1_R4): the bars, the dialogs, the screenshot grid ------------------------------------
// The bars keep their height at every level (top 164, or 112 with the quick-access row hidden; hints bar 32), so the
// page area (WebKit's view size, page clicks, omniPageTop / omniPageBottom) is the same at every Interface size.
// Top bar: every box (tabs, "+", address field, star, Protection pill, gear, quick-access tiles) and every hit area
// stays where it is; the TEXT and the ICONS inside are drawn at barTextZoom (a text-only zoom: today's text cache
// blended scaled, positions in today's layout px). Labels with a width limit get an ellipsis (tab titles, the
// address); the badges right of "+" (sleep timer, offline, Downloads ring, data saver) are laid out by their own
// code with the zoomed text widths, so they drop their words / hide first when the room runs out; a word that must
// fit a small pill gets capZoom. Clicks: today's code on today's numbers (nothing is mapped, OMNI_BARS_CLICK_V1).
// The tallest zoomed line is the 17 px face at 1.5 (about 30 px) in 44 px tabs / tiles and the 40 px field;
// captions (14 px) in the 36 px pill.
constexpr double kBarTextMax = 1.5;
inline double barTextZoom(int level) { return clampLevel(level) == Normal ? 1.0 : std::min(scaleOf(level), kBarTextMax); }
// A label `naturalW` layout px wide at zoom 1 that must fit `maxW` layout px: the zoom it gets (`zoom`, lowered to fit,
// never below min(1, zoom): Large / Extra large never draw it smaller than Normal).
inline double capZoom(double zoom, double naturalW, int maxW)
{
    if (naturalW <= 0 || naturalW * zoom <= maxW) return zoom;
    const double fit = std::floor(maxW / naturalW * 1000) / 1000;
    return std::max(std::min(zoom, fit), std::min(1.0, zoom));
}
// The hints bar (every line: browsing, settings, panels, dialogs, controls help; the keyboard's own line is
// hintLineZoom): drawn with displayScale * z inside the bar's 32 px, at most kHintLineMax (the 32 px controller glyphs
// reach 40 px), lowered so a line `naturalW` layout px long (both 20 px margins included) fits the width; Large /
// Extra large never below 1 (today's line, with today's ellipsis on the note).
inline double hintsZoom(int level, int naturalW)
{
    const double want = scaleOf(level);
    double z = std::min(want, kHintLineMax);
    if (naturalW > 0) z = std::min(z, double(kLayoutW) / naturalW);
    z = std::max(z, std::min(1.0, want));
    return std::floor(z * 1000) / 1000;
}
// Dialogs (omniModalLayout: 760 / 640 wide, message lines 30 px, select rows 40 px, buttons): fitBox on the screen
// above the hints bar; fewer lines / rows when they do not fit (the message scrolls, the list pages). Compact (a field
// being typed into, the keyboard below): top edge kept at 116 and the bottom at 374, as at Normal.
constexpr int kModalCompactTop = 116, kModalCompactBottom = 374;
inline BoxFit fitDialog(int level, int w, int fixedH, int rowH, int rows, bool compact)
{
    if (!compact) return fitBox(level, w, fixedH, rowH, rows, 0, kLayoutH - kHintsH, kMargin);
    BoxFit f = fitBox(level, w, fixedH, rowH, rows, kModalCompactTop, kModalCompactBottom - 2, 0);   // 2: the top rounded up below
    f.y = int(std::ceil(kModalCompactTop / f.zoom));
    return f;
}
// The screenshot grid (4 x 3 tiles of tileW x tileH, `gap` apart, a header and padding): fewer columns / rows at a
// larger level instead of a grid larger than the screen. zoom = the level's scale, lowered (never below the level's
// floor) until at least min(minRows, maxRows) rows fit above the hints bar; then as many columns / rows as fit.
// x, y, w, h: the panel in the zoomed layout space (centred). Normal: 4 x 3 at (101, 9), today's.
struct GridFit { double zoom; int cols, rows, x, y, w, h; };
inline GridFit fitGrid(int level, int tileW, int tileH, int gap, int maxCols, int maxRows, int headH, int padW, int padH,
                       int minRows = 2, int margin = 6)
{
    GridFit f {};
    const double want = scaleOf(level), floorZoom = std::min(1.0, want);
    const double roomW = kLayoutW - 2.0 * margin, roomH = kLayoutH - kHintsH - 2.0 * margin;
    maxCols = std::max(1, maxCols); maxRows = std::max(1, maxRows);
    auto W = [&](int c) { return padW + c * tileW + (c - 1) * gap; };
    auto H = [&](int r) { return headH + r * tileH + (r - 1) * gap + padH; };
    const int need = std::min(std::max(1, minRows), maxRows);
    double zoom = want;
    if (H(need) * zoom > roomH) zoom = roomH / H(need);
    if (W(1) * zoom > roomW) zoom = std::min(zoom, roomW / W(1));
    zoom = std::max(zoom, floorZoom);
    zoom = std::floor(zoom * 1000) / 1000;
    f.zoom = zoom;
    f.cols = maxCols;
    while (f.cols > 1 && W(f.cols) * zoom > roomW) --f.cols;
    f.rows = maxRows;
    while (f.rows > 1 && H(f.rows) * zoom > roomH) --f.rows;
    f.w = W(f.cols);
    f.h = H(f.rows);
    f.x = (zoomedW(zoom) - f.w) / 2;
    const int bottomZ = int(std::floor((kLayoutH - kHintsH) / zoom));
    f.y = std::max(int(std::ceil(margin / zoom)), (bottomZ - f.h) / 2);
    return f;
}

// --- memory ----------------------------------------------------------------------------------------------------
// SDL_ttf has no atlas: each open face keeps a 256-entry glyph cache (8-bit pixmap, about px wide x 1.2 px tall for
// CJK), and the shell keeps the last 256 rendered strings as ARGB surfaces (omniTextSurface). A zoomed region needs
// its own 7 faces (22/17/22/17/28/14/14 layout px; + up to 2 CJK fallback sets opened only when a string needs them).
constexpr int kFaceLayoutPx[7] = { 22, 17, 22, 17, 28, 14, 14 };
constexpr int kGlyphCache = 256, kTextCache = 256;
inline int facePx(int layoutPx, double displayScale, double zoom) { return int(layoutPx * displayScale * zoom + 0.5); }
// Worst-case glyph caches of one face set (+ fallback sets) at displayScale * zoom.
inline uint64_t faceSetBytes(double displayScale, double zoom, int fallbackSets = 0)
{
    uint64_t sum = 0;
    for (int px : kFaceLayoutPx) {
        const uint64_t p = uint64_t(facePx(px, displayScale, zoom));
        sum += uint64_t(kGlyphCache) * p * (p * 6 / 5);
    }
    return sum * uint64_t(1 + std::clamp(fallbackSets, 0, 2));
}
// Worst-case text surface cache: `entries` strings, `avgLayoutW` wide on average, line height 1.4 x the body face.
inline uint64_t textCacheBytes(double displayScale, double zoom, int entries = kTextCache, int avgLayoutW = 300)
{
    const uint64_t w = uint64_t(avgLayoutW * displayScale * zoom + 0.5), h = uint64_t(22 * 1.4 * displayScale * zoom + 0.5);
    return uint64_t(entries) * w * h * 4;
}
// Text cache entries that keep the surfaces within `budgetBytes` (16 .. 256): the cap the shell should use instead
// of the fixed 256 once zoomed faces exist (4K Extra large would otherwise reach ~190 MB worst case).
inline int textCacheEntries(double displayScale, double zoom, uint64_t budgetBytes, int avgLayoutW = 300)
{
    const uint64_t one = std::max<uint64_t>(1, textCacheBytes(displayScale, zoom, 1, avgLayoutW));
    return int(std::clamp<uint64_t>(budgetBytes / one, 16, kTextCache));
}
// Extra memory a level costs over Normal: one more face set (only when the level is not Normal; Normal keeps today's
// faces) with its fallbacks, plus the zoomed text surfaces (they share the capped cache, so only the growth counts).
inline uint64_t extraBytes(int level, double displayScale, int fallbackSets = 2)
{
    if (clampLevel(level) == Normal) return 0;
    const double z = scaleOf(level);
    return faceSetBytes(displayScale, z, fallbackSets);
}
// The largest level whose extra face memory fits `budgetBytes` (Normal always allowed; Small always fits when Large does).
inline int maxLevelFor(double displayScale, uint64_t budgetBytes, int fallbackSets = 2)
{
    for (int l = kLevelCount - 1; l > Normal; --l)
        if (extraBytes(l, displayScale, fallbackSets) <= budgetBytes) return l;
    return Normal;
}
// The level actually used: the saved one, capped by memory.
inline int effectiveLevel(int saved, double displayScale, uint64_t budgetBytes)
{
    const int l = clampLevel(saved);
    return l <= Normal ? l : std::min(l, maxLevelFor(displayScale, budgetBytes));
}

} // namespace OmniUiScale
