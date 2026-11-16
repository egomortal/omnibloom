// OMNI_UI_SCALE_V1 (stage 1): Browser settings > "Interface size" for the controller panels (OmniFxPanel).
// Shell side; the pure part is OmniUiScale.h. Installed by tools/apply_ui_scale.py: included from OmniBrowser.cpp just
// before omniLabel (inside its anonymous namespace), so omniLabel / omniIcon can hand zoomed drawing to it.
//
// How a panel is zoomed: omniFxGeometry returns OmniUiScale::fitPanel's geometry (a 1280/zoom x 720/zoom layout space,
// rows per page clamped) with the zoom; omniFxDrawPanel draws the panel with displayScale * zoom (OmniUisZoomScope), so
// fillRounded / omniShadow / positions grow together, and puts displayScale back before the hints bar; omniFxHover /
// omniFxClick map the pointer with OmniUiScale::toZoomed before omniFxRowAt. Normal (the default) takes none of these
// paths: the geometry code, the drawing and the hit-test are today's.
// Text and icons: no extra font faces or atlases. Labels are rendered by today's faces into today's text cache
// (omniTextSurface, untouched) and the cached surface is blended into the canvas scaled by the zoom (bilinear, per
// draw, no second cache); icon masks likewise. The shell only redraws panels when something changes, so the cost is a
// few hundred thousand samples per redraw at 4K Extra large.
//
// OMNI_UI_SCALE_V1_R2 (stage 2): the regions with their own geometry: the toast, the QR code panel, the screenshot
// viewer's caption, History, Browser tools, the controller / theme / display settings panel and its Browser tools
// pill, the autofill fill bar, the error page (with the HTTPS-only and offline panels inside it). Same zoom: drawn
// with displayScale * zoom (OmniUisZoomScope, which can also put the pointer in the zoomed space for hover tests);
// inside a zoomed region omniTextWidthPx / omniFit measure in drawn pixels, so the existing "width / displayScale"
// arithmetic stays right, and omniPanelHints draws the hints bar at today's size (OmniUisUnzoom; stage 4's).
// Hit-testing: either the pointer in the zoomed space (omniUisMap) or, for code with fixed Normal coordinates,
// the pointer in the region's Normal coordinates (omniUisToNormal), so today's hit-test code is reused as is.
// The definitions that need the later shell (toast, History / menu / settings boxes, the settings panel drawn
// zoomed) are in OmniUiScalePanels.h, included after OmniFeatures3.h. Normal takes none of these paths.
//
// OMNI_UI_SCALE_V1_R3 (stage 3): the on-screen keyboard (keys, preview row with its text / caret / word chips, the
// shortcut tiles, the accent popup), the address suggestions above it, the keyboard's hint line and the find bar.
// The keyboard's geometry is OmniUiScale::fitKeyboard (omniUisKb(), declared next to keyboardX in OmniBrowser.cpp):
// OMNI_UIS_KB_LOCALS shadows keyboardX / keyboardY / keyHeight / actionY in omniDrawKeyboard, omniKwDraw,
// omniKblGeometry and omniKbClick (Normal: today's constants), the drawing runs in an OmniUisZoomScope and the click
// maps the pointer into the same zoomed space first, so keys, chips (positions stored by the draw) and the accent
// popup hit exactly where they are drawn. The preview text (omniKbDrawText, its own surface) is laid out in face
// pixels and blended scaled (omniUisKbTextDraw). Everything that sits above the keyboard asks omniUisKbTop().
//
// OMNI_UI_SCALE_V1_R4 (stage 4): the bars keep their height, so the page area never changes (OmniUiScale.h).
//   - top bar: OmniUisTextScope, a TEXT-ONLY zoom: displayScale stays, omniUisTextZoom = OUIS::barTextZoom, so
//     omniLabel / omniIcon / omniTextWidthPx / omniFit draw and measure the text and icons larger while every box,
//     position and hit area is today's (the click code is not touched: nothing to map). OmniUisTextCap lowers it for
//     one word that must fit a small pill (Protection); the bookmark star is drawn at the same zoom.
//   - hints bar: every omniHints line is drawn by omniUisHints at OUIS::hintsZoom (full zoom, inside the 32 px bar);
//     omniHints / omniHintDraw shadow width / the centre line while zoomed.
//   - dialogs (omniModal*, omniAsk): omniModalLayout at a level is omniUisModalLayout (today's layout, fewer lines /
//     rows when needed, moved into the zoomed space, L.zoom); drawn in an OmniUisZoomScope (pointer mapped for
//     hover), omniModalHit maps the pointer with the same zoom first: draw, hover, Cross and clicks share it.
//   - screenshot grid: omniUisSsGeometry (OUIS::fitGrid: 3 x 2 at Large / Extra large), the pager's cols / rows
//     follow it (OSG::Pager), drawn zoomed with the Normal-size thumbnails scaled, clicks mapped.
#pragma once

namespace OUIS = OmniUiScale;
constexpr int omniUisRowId = 834;        // Browser settings row (ids in use: 1..21, 340..345, 845..891, >= 900)
static int omniUisLevelValue = -1;       // -1: not read yet
static double omniUisTextZoom = 1.0;     // != 1 while a zoomed region draws (omniLabel / omniIcon scale their bitmaps)
static double omniUisBaseScale = 1.0;    // displayScale outside the zoomed region
static bool omniUisPtrOn = false;        // OMNI_UI_SCALE_V1_R2: pointerX / pointerY are in the zoomed space
static float omniUisPtrX = 0, omniUisPtrY = 0;   // the screen pointer meanwhile
static bool omniUisTextOnly = false;     // OMNI_UI_SCALE_V1_R4: omniUisTextZoom applies to text / icons only (displayScale kept)
static void omniUisLevelChanged();       // R4 (OmniUiScalePanels.h): the screenshot pager back to its Normal grid

static int omniUisLevel()
{
    if (omniUisLevelValue >= 0) return omniUisLevelValue;
    omniUisLevelValue = OUIS::kDefault;
    if (FILE* f = fopen(omniData("ui-scale.txt").c_str(), "rb")) {
        char buf[64] = {};
        const size_t n = fread(buf, 1, sizeof buf - 1, f);
        fclose(f);
        omniUisLevelValue = OUIS::parse(std::string(buf, n));
    }
    return omniUisLevelValue;
}
static void omniUisSet(int level)
{
    level = OUIS::clampLevel(level);
    if (level == omniUisLevel()) return;
    omniUisLevelValue = level;
    omniUisLevelChanged();
    if (!omniTestMode()) omniIoQueue(omniData("ui-scale.txt"), OUIS::serialize(level), false);
    omniShellDirty = true;   // panels read the level on every draw: the change shows on the next frame
}
// Browser settings row: Left / Right step (no wrap), Cross cycles, Y back to Normal.
static bool omniUisSettingsInput(int b)
{
    const int l = omniUisLevel();
    if (b == SDL_CONTROLLER_BUTTON_DPAD_LEFT) { omniUisSet(OUIS::stepped(l, -1)); return true; }
    if (b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT) { omniUisSet(OUIS::stepped(l, 1)); return true; }
    if (b == SDL_CONTROLLER_BUTTON_A) { omniUisSet((l + 1) % OUIS::kLevelCount); return true; }
    if (b == SDL_CONTROLLER_BUTTON_Y) { omniUisSet(OUIS::Normal); return true; }
    return false;
}

// A pointer position (screen layout px) in the layout space of a region drawn at `zoom`.
static void omniUisMap(double zoom, int& x, int& y)
{
    if (zoom == 1.0) return;
    x = OUIS::toZoomed(x, zoom);
    y = OUIS::toZoomed(y, zoom);
}
// Draws a region at displayScale * zoom until restore() / the end of the scope. zoom 1: does nothing.
// mapPointer (OMNI_UI_SCALE_V1_R2): pointerX / pointerY in the zoomed layout space meanwhile (hover tests in draw code).
struct OmniUisZoomScope {
    double saved = 0;
    bool on = false, ptr = false;
    explicit OmniUisZoomScope(double zoom, bool mapPointer = false)
    {
        if (zoom == 1.0 || zoom <= 0 || omniUisTextZoom != 1.0) return;
        on = true;
        saved = displayScale;
        omniUisBaseScale = displayScale;
        omniUisTextZoom = zoom;
        displayScale = saved * zoom;
        if (mapPointer && !omniUisPtrOn) {
            ptr = omniUisPtrOn = true;
            omniUisPtrX = pointerX; omniUisPtrY = pointerY;
            pointerX = float(pointerX / zoom); pointerY = float(pointerY / zoom);
        }
    }
    void restore()
    {
        if (!on) return;
        on = false;
        displayScale = saved;
        omniUisTextZoom = 1.0;
        if (ptr) { ptr = omniUisPtrOn = false; pointerX = omniUisPtrX; pointerY = omniUisPtrY; }
    }
    ~OmniUisZoomScope() { restore(); }
    OmniUisZoomScope(const OmniUisZoomScope&) = delete;
    OmniUisZoomScope& operator=(const OmniUisZoomScope&) = delete;
};

// OMNI_UI_SCALE_V1_R2: today's scale (and the screen pointer) for a moment inside a zoomed region: the hints bar
// (omniPanelHints; R4: omniUisHints then zooms it its own way), text measuring in face pixels. Outside a zoomed region:
// does nothing. R4: also inside the top bar's text-only zoom; displayScale is put back exactly as it was.
struct OmniUisUnzoom {
    double zoom = 1.0, ds = 0;
    bool ptr = false, textOnly = false;
    float px = 0, py = 0;
    OmniUisUnzoom()
    {
        if (omniUisTextZoom == 1.0) return;
        zoom = omniUisTextZoom;
        ds = displayScale;
        textOnly = omniUisTextOnly;
        omniUisTextZoom = 1.0;
        omniUisTextOnly = false;
        displayScale = omniUisBaseScale;
        if (omniUisPtrOn) { ptr = true; omniUisPtrOn = false; px = pointerX; py = pointerY; pointerX = omniUisPtrX; pointerY = omniUisPtrY; }
    }
    ~OmniUisUnzoom()
    {
        if (zoom == 1.0) return;
        omniUisTextZoom = zoom;
        omniUisTextOnly = textOnly;
        displayScale = ds;
        if (ptr) { omniUisPtrOn = true; pointerX = px; pointerY = py; }
    }
    OmniUisUnzoom(const OmniUisUnzoom&) = delete;
    OmniUisUnzoom& operator=(const OmniUisUnzoom&) = delete;
};
// omniTextWidthPx / omniFit inside a zoomed region (declared before them in OmniBrowser.cpp): widths in drawn pixels
// (face pixels * zoom), so "omniTextWidthPx(..) / displayScale" is the width in the zoomed layout space and
// omniFit(.., physical(maxW)) fits maxW zoomed layout px, as at Normal.
static double omniUisZoomNow() { return omniUisTextZoom; }
static int omniUisDrawnWidth(int id, const std::string& value)
{
    OmniUisUnzoom u;
    return int(omniTextWidthPx(id, value) * u.zoom + 0.5);
}
static std::string omniUisFitZoomed(int id, const std::string& value, int maxPx)
{
    OmniUisUnzoom u;
    return omniFit(id, value, std::max(1, int(maxPx / u.zoom)));
}

// --- OMNI_UI_SCALE_V1_R4 (stage 4) ---------------------------------------------------------------------------------------
// The top bar's text-only zoom: until restore() / the end of the scope, labels and icons are drawn `zoom` times larger
// at today's positions (omniUisLabel / omniIcon's zoomed branch with displayScale unchanged), omniTextWidthPx / omniFit
// measure the drawn text. Boxes, fills and hit areas are today's. zoom 1, or inside another zoomed region: nothing.
struct OmniUisTextScope {
    bool on = false;
    explicit OmniUisTextScope(double zoom)
    {
        if (zoom == 1.0 || zoom <= 0 || omniUisTextZoom != 1.0) return;
        on = true;
        omniUisBaseScale = displayScale;
        omniUisTextZoom = zoom;
        omniUisTextOnly = true;
    }
    void restore()
    {
        if (!on) return;
        on = false;
        omniUisTextZoom = 1.0;
        omniUisTextOnly = false;
    }
    ~OmniUisTextScope() { restore(); }
    OmniUisTextScope(const OmniUisTextScope&) = delete;
    OmniUisTextScope& operator=(const OmniUisTextScope&) = delete;
};
// Inside the text-only zoom: a word that must fit `maxW` layout px (a pill) gets OUIS::capZoom for this scope.
struct OmniUisTextCap {
    double saved = 0;
    OmniUisTextCap(int id, const std::string& value, int maxW)
    {
        if (!omniUisTextOnly || omniUisTextZoom == 1.0) return;
        saved = omniUisTextZoom;
        double natural = 0;
        { OmniUisUnzoom u; natural = omniTextWidthPx(id, value) / displayScale; }
        omniUisTextZoom = OUIS::capZoom(saved, natural, maxW);
    }
    ~OmniUisTextCap() { if (saved != 0) omniUisTextZoom = saved; }
    OmniUisTextCap(const OmniUisTextCap&) = delete;
    OmniUisTextCap& operator=(const OmniUisTextCap&) = delete;
};
static double omniUisBarZoom() { return OUIS::barTextZoom(omniUisLevel()); }   // 1 at Normal
// A screen layout y in the space of the full zoom being drawn (the hints bar's centre line); the caller checks the zoom.
static int omniUisZoomedY(int y) { return omniUisTextZoom != 1.0 && !omniUisTextOnly ? OUIS::toZoomed(y, omniUisTextZoom) : y; }
// Defined in OmniUiScalePanels.h:
struct OmniHint;
static bool omniUisHints(const std::vector<OmniHint>& left, const std::vector<OmniHint>& right, const std::string& note);
struct OmniModal;
struct OmniModalLayout;
static OmniModalLayout omniUisModalLayout(OmniModal& m);   // omniModalLayout at a level other than Normal
static bool omniUisModalBusy = false;                      // omniUisModalLayout is asking for today's layout
static int omniUisModalCap = 1 << 20;                      // lines / rows a zoomed dialog shows (omniModalLayout clamps)
struct OmniSsGeom;
static OmniSsGeom omniUisSsGeometry();                     // the screenshot grid at a level (sets the pager's grid)
static void omniUisSsGrid();                               // only the pager's grid (callers before OmniSsGeom is complete)

// --- fixed-layout regions (OMNI_UI_SCALE_V1_R2) ------------------------------------------------------------------------
// A region's zoom, its top-left in the zoomed layout space (x, y), its top-left at Normal (nx, ny), its drawn size in
// layout px (w, h) and, for a list, the rows shown. zoom 1 (Normal): today's geometry, nothing mapped.
struct OmniUisBox { double zoom = 1.0; int x = 0, y = 0, nx = 0, ny = 0, w = 0, h = 0, rows = 0; };
// The screen pointer in the region's Normal coordinates (today's hit-test code then works unchanged); off the drawn
// region: far off it.
static void omniUisToNormal(const OmniUisBox& b, int& x, int& y)
{
    if (b.zoom == 1.0) return;
    OUIS::toNormal(b.zoom, b.x, b.y, b.nx, b.ny, b.w, b.h, x, y);
}
// The level's plain zoom for a small region with no fit problem (toast, fill bar, viewer caption); 1 at Normal.
static double omniUisZoom() { const int l = omniUisLevel(); return l == OUIS::Normal ? 1.0 : OUIS::scaleOf(l); }
// Defined in OmniUiScalePanels.h (they need the later shell):
static void omniUisToast(const std::string& message, bool error, float a);   // omniDrawToast at a level other than Normal
static OmniUisBox omniUisHistoryBox();                                      // History (list or "Clear history", typing)
static OmniUisBox omniUisMenuBox();                                         // Browser tools
static OmniUisBox omniUisSettingsBox();                                     // controller / theme / display settings
static void omniUisSettingsPanel();                                         // omniSettingsPanel, zoomed
// OMNI_UI_SCALE_V1_R3 (stage 3), defined in OmniUiScalePanels.h:
struct OmniKbView;
static void omniUisKbTextDraw(const OmniKbView& v, int x, float cy, int room, int font, SDL_Color ink, SDL_Color accent, bool selection);
static bool omniUisKbHints();                                               // omniKbHints zoomed: true when it drew the line
static bool omniUisSuggestClick(int x, int y);                              // the address suggestions at a level
static void omniUisSuggestDraw();
static int omniUisLineRight = 0;          // right edge (zoomed layout px) of the labels drawn zoomed since it was reset
static bool omniUisKbHintsBusy = false;   // omniUisKbHints is drawing the line
// History's geometry is constexpr (OmniBrowser.cpp): inside omniHistoryDraw / omniHistoryButton these locals shadow it
// (zoomed: the box; Normal: today's constants, so the code that follows is today's).
#define OMNI_UIS_HISTORY_LOCALS \
    const OmniUisBox uisHistoryBox = omniUisHistoryBox(); \
    [[maybe_unused]] const int omniHistoryX = uisHistoryBox.zoom != 1.0 ? uisHistoryBox.x : ::omniHistoryX, \
        omniHistoryTop = uisHistoryBox.zoom != 1.0 ? uisHistoryBox.y : ::omniHistoryTop, \
        omniHistoryRows = uisHistoryBox.zoom != 1.0 ? uisHistoryBox.rows : ::omniHistoryRows, omniHpSearchX = omniHistoryX + 170; \
    [[maybe_unused]] const auto omniHpVisible = [&] { return omniHpTyping() ? std::min(4, omniHistoryRows) : omniHistoryRows; }

// Blends an 8-bit coverage bitmap (w x h, row pitch `pitch` bytes, coverage at byte `offset` of each `step`-byte pixel)
// into the canvas scaled by omniUisTextZoom, top-left at physical (x0, y0), tinted `color`. Bilinear.
static void omniUisBlitCoverage(const uint8_t* bits, int w, int h, int pitch, int step, int offset, int x0, int y0, int clipW,
                                SDL_Color color, uint8_t alpha)
{
    const OmniPix f = omniPix();
    const double z = omniUisTextZoom;
    if (!f.ok || w <= 0 || h <= 0 || z <= 0) return;
    const int srcW = clipW > 0 ? std::min(clipW, w) : w;
    const int dw = std::max(1, int(srcW * z + 0.5)), dh = std::max(1, int(h * z + 0.5));
    const int i0 = std::max(0, -x0), i1 = std::min(dw, canvas->w - x0), j0 = std::max(0, -y0), j1 = std::min(dh, canvas->h - y0);
    auto at = [&](int x, int y) -> uint32_t {
        if (x < 0 || y < 0 || x >= srcW || y >= h) return 0;
        return bits[size_t(y) * pitch + size_t(x) * step + offset];
    };
    for (int j = j0; j < j1; ++j) {
        const double sy = (j + 0.5) / z - 0.5;
        const int y = int(std::floor(sy));
        const uint32_t fy = uint32_t((sy - y) * 256);
        uint32_t* row = omniRow(y0 + j) + x0;
        for (int i = i0; i < i1; ++i) {
            const double sx = (i + 0.5) / z - 0.5;
            const int x = int(std::floor(sx));
            const uint32_t fx = uint32_t((sx - x) * 256);
            const uint32_t top = at(x, y) * (256 - fx) + at(x + 1, y) * fx, low = at(x, y + 1) * (256 - fx) + at(x + 1, y + 1) * fx;
            uint32_t a = (top * (256 - fy) + low * fy) >> 16;
            if (!a) continue;
            if (alpha != 255) a = omniDiv255(a * alpha);
            omniBlendPx(row[i], f, color, a);
        }
    }
}
// omniLabel inside a zoomed region: today's face and text cache, the surface scaled by the zoom.
static int omniUisLabel(const std::string& value, float x, float cy, int id, SDL_Color color, int align, int maxW, uint8_t alpha)
{
    const double z = omniUisTextZoom, base = omniUisBaseScale;
    SDL_Surface* s = omniTextSurface(id, maxW > 0 ? omniFit(id, value, physical(maxW)) : value, color);   // fit in drawn px (R2: omniFit)
    if (!s) return 0;
    const int dw = int(s->w * z + 0.5);
    int px = int(x * displayScale + 0.5);
    if (align == 1) px -= dw / 2; else if (align == 2) px -= dw;
    omniUisLineRight = std::max(omniUisLineRight, int((px + dw) / displayScale + 0.5));   // R3: the hint line's width
    const int py = int(cy * displayScale + 0.5) - int(omniFaces[id].capMid * z + 0.5);
    const SDL_PixelFormat* sf = s->format;
    if (sf->BytesPerPixel == 4 && sf->Amask && !SDL_MUSTLOCK(s)) {
        // SDL_ttf Blended text: every pixel has the label colour, coverage in alpha
        SDL_Color c = color; c.a = 255;
        omniUisBlitCoverage(static_cast<const uint8_t*>(s->pixels), s->w, s->h, s->pitch, 4, sf->Ashift / 8, px, py, 0, c, alpha);
    } else {
        omniBlitText(s, px, int(cy * displayScale + 0.5) - omniFaces[id].capMid, 0, alpha);   // unknown format: unscaled
    }
    if (omniUisTextOnly) return int(s->w * z / displayScale + 0.5);   // R4: the drawn width in today's layout px
    return int(s->w / base + 0.5);   // = the drawn width in the zoomed layout space
}
