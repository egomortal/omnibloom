// OMNI_UI_SCALE_V1_R2 (stage 2): Browser settings > "Interface size" for the regions that draw their own geometry.
// Installed by tools/apply_ui_scale.py: included from OmniBrowser.cpp after OmniFeatures3.h (inside its anonymous
// namespace), so it sees the whole shell; OmniUiScaleShell.h declares what is defined here. Nothing here runs at
// Normal: every caller checks the level (or gets a box with zoom 1) first.
// OMNI_UI_SCALE_V1_R3 (stage 3): + the keyboard's geometry (omniUisKb), its preview text, its hint line, the address
// suggestions and the find bar (end of this file).
// OMNI_UI_SCALE_V1_R4 (stage 4): + the hints bar (omniUisHints), the dialogs (omniUisModalLayout) and the screenshot
// grid (omniUisSsGeometry); the top bar's text-only zoom is in OmniUiScaleShell.h (OmniUisTextScope).
#pragma once

// --- toast (OMNI_STYLE_V1 / OMNI_POLISH_V1 pill): omniDrawToast hands over after its fade maths ---------------------
// The same pill zoomed, still centred and still just above the page bottom / the keyboard (screen layout positions);
// the text gets an ellipsis at what fits the screen (940 layout px at Normal).
static void omniUisToast(const std::string& message, bool error, float a)
{
    const OmniTheme& T = omniTheme();
    const double z = omniUisZoom();
    const int base = editing ? omniUisKbTop() - 2 : std::min(omniPageBottom(), height - bottom) - 18;   // screen layout (R3: the zoomed keyboard's top)
    OmniUisZoomScope uisZoom(z);
    const int W = OUIS::zoomedW(z), icon = error ? 28 : 0;
    const std::string shown = omniFit(omniSmall, message, physical(std::min(940, W - 32 - 48 - icon)));
    const int w = int(omniTextWidthPx(omniSmall, shown) / displayScale + 0.5) + 48 + icon, h = 44;
    const int x = (W - w) / 2;
    const int y = OUIS::toZoomed(base, z) - h + int((1 - a) * 12);
    const uint8_t A = uint8_t(255 * a);
    omniShadow(x, y, w, h, h / 2, 12, uint8_t(110 * a), 3);
    fillRounded(x, y, w, h, h / 2, omniMix(T.raised, T.line, 0.6f), A);
    fillRounded(x + 1, y + 1, w - 2, h - 2, h / 2 - 1, T.raised, A);
    if (error) { omniDisc(x + 32, y + h / 2.f, 9, omniBad, A); omniIcon(omniIconAlert, x + 32, y + h / 2.f, T.bg, A); }
    omniLabel(shown, x + 24 + icon, y + h / 2.f, omniSmall, T.ink, 0, 0, A);
}

// --- History (constexpr geometry: OMNI_UIS_HISTORY_LOCALS shadows it in draw / buttons; clicks via omniUisToNormal) --
// The list: 980 wide, 70 + rows * 50 + 20, rows clamped (L1 / R1 page by them). Typing (the search keyboard is open):
// 4 rows ending above the keyboard's preview row (R3: the zoomed keyboard's top, omniUisKbTop()), as at Normal.
static OmniUisBox omniUisHistoryBox()
{
    OmniUisBox b;
    const int level = omniUisLevel();
    if (level == OUIS::Normal) return b;
    const bool typing = omniHpTyping();
    const OUIS::BoxFit f = typing ? OUIS::fitBox(level, omniHistoryW, 80, omniHistoryRowH, 4, 0, omniUisKbTop(), 8)
                                  : OUIS::fitBox(level, omniHistoryW, 90, omniHistoryRowH, omniHistoryRows, 0, height - bottom);
    b.zoom = f.zoom; b.x = f.x; b.y = f.y; b.nx = ::omniHistoryX; b.ny = ::omniHistoryTop; b.w = f.w; b.h = f.h; b.rows = f.rows;
    return b;
}

// --- Browser tools (omniMenuX / omniMenuY at Normal; the zoom is lowered so all its rows fit, it does not scroll) ------
static OmniUisBox omniUisMenuBox()
{
    OmniUisBox b;
    const int level = omniUisLevel();
    if (level == OUIS::Normal) return b;
    const int h = 96 + omniMenuCount * omniMenuRowH + 18;
    const OUIS::BoxFit f = OUIS::fitBox(level, omniMenuW, h, 0, 0, 0, height - bottom);
    b.zoom = f.zoom; b.x = f.x; b.y = f.y; b.nx = omniMenuX(); b.ny = omniMenuY(); b.w = omniMenuW; b.h = h;
    return b;
}

// --- controller / theme / display settings (omniSettingsPanel: literal positions, panel 300..980 x 124..648) ----------
static OmniUisBox omniUisSettingsBox()
{
    OmniUisBox b;
    const int level = omniUisLevel();
    if (level == OUIS::Normal) return b;
    const OUIS::BoxFit f = OUIS::fitBox(level, 680, 524, 0, 0, 0, height - bottom);
    b.zoom = f.zoom; b.x = f.x; b.y = f.y; b.nx = 300; b.ny = 124; b.w = 680; b.h = 524;
    return b;
}
// omniSettingsPanel (OMNI_STYLE_V1 / OMNI_POLISH_V1) drawn zoomed: the same drawing with every position moved by
// (dx, dy) into the zoomed layout space. apply_ui_scale.py refuses to patch a tree whose omniSettingsPanel is not the
// version this copies (sha256 check), so the two cannot drift apart silently. Clicks and hover use today's
// omniSettingsClick / omniPtrSettingsRowAt with the pointer in Normal coordinates (omniUisToNormal).
static void omniUisSettingsPanel()
{
    const OmniUisBox box = omniUisSettingsBox();
    OmniUisZoomScope uisZoom(box.zoom, true);   // the close button's hover test below uses the zoomed pointer
    const int dx = box.x - box.nx, dy = box.y - box.ny;
    const OmniTheme& T = omniTheme();
    struct FadeScope { ~FadeScope() { omniFadeEnd(); } } fadeScope;
    omniFadeBegin(270 + dx, 100 + dy, 740, 580, omniPanelT(omniPanelSettings));
    omniShadow(300 + dx, 124 + dy, 680, 524, omniRadius + 2, 20, 150, 6);
    fillRounded(300 + dx, 124 + dy, 680, 524, omniRadius + 2, T.panel);
    omniLabel("Settings", 332 + dx, 162 + dy, omniTitle, T.ink);
    const bool closeHover = pointerX >= 918 + dx && pointerX < 970 + dx && pointerY >= 136 + dy && pointerY < 188 + dy;
    if (closeHover) omniRingDisc(944 + dx, 162 + dy, 18, T.accent, T.hover);
    omniIcon(omniIconClose, 944 + dx, 162 + dy, closeHover ? T.ink : T.inkDim);
    omniRectPx({ physical(320 + dx), physical(194 + dy), physical(640), std::max(1, physical(1) / 2) }, T.line);
    const int rowTop[] = { 202, 330, 426, 502, 588 }, rowBottom[] = { 324, 420, 496, 582, 632 };
    fillRounded(316 + dx, rowTop[omniSettingsRow] + dy, 648, rowBottom[omniSettingsRow] - rowTop[omniSettingsRow], omniRadius, omniMix(T.panel, T.accent, 0.08f));
    fillRounded(310 + dx, rowTop[omniSettingsRow] + 6 + dy, 4, rowBottom[omniSettingsRow] - rowTop[omniSettingsRow] - 12, 2, T.accent);
    auto heading = [&](int row, const char* label, int cy) { omniLabel(label, 332 + dx, cy + dy, omniSettingsRow == row ? omniSmallBold : omniSmall, omniSettingsRow == row ? T.ink : T.inkDim); };
    heading(0, "Controller buttons", 216);
    for (int i = 0; i < 2; ++i) {
        const int x = (i ? 644 : 332) + dx;
        const bool on = playStationIcons == bool(i);
        if (on) fillRounded(x - 2, 230 + dy, 308, 88, omniRadius + 1, T.accent);
        fillRounded(x, 232 + dy, 304, 84, omniRadius, on ? T.raised : T.tab);
        omniLabel(i ? "PlayStation" : "Xbox", x + 20, 256 + dy, omniBody, on ? T.ink : T.inkDim);
        for (int b = 0; b < 4; ++b) faceIcon(x + 36 + b * 52, 292 + dy, b, i);
        if (on) { omniDisc(x + 280, 256 + dy, 11, T.accent); omniIcon(omniIconCheck, x + 280, 256 + dy, T.accentInk); }
    }
    heading(1, "Theme", 346);
    const int themeStride = OHCT::cardStride(omniThemeCount), themeW = OHCT::cardWidth(omniThemeCount); // OMNI_HIGH_CONTRAST_V1: 5 cards in the row
    for (int i = 0; i < omniThemeCount; ++i) {
        const int x = 332 + i * themeStride + dx;
        const bool on = omniThemeIndex == i;
        const OmniTheme& t = omniThemes[i];
        if (on) fillRounded(x - 2, 358 + dy, themeW + 4, 56, omniRadius + 1, T.accent);
        fillRounded(x, 360 + dy, themeW, 52, omniRadius, on ? T.raised : T.tab);
        if (OHCT::stackedCards(omniThemeCount)) {   // disc above a centred caption
            omniDisc(x + themeW / 2.f, 375 + dy, 10, t.line);
            omniDisc(x + themeW / 2.f, 375 + dy, 9, t.bar);
            omniDisc(x + themeW / 2.f, 375 + dy, 4, t.accent);
            omniLabel(t.name, x + themeW / 2.f, 399 + dy, omniCaption, on ? T.ink : T.inkDim, 1, themeW - 8);
            continue;
        }
        omniDisc(x + 24, 386 + dy, 13, t.line);
        omniDisc(x + 24, 386 + dy, 12, t.bar);
        omniDisc(x + 24, 386 + dy, 5.5f, t.accent);
        omniLabel(t.name, x + 44, 386 + dy, omniSmall, on ? T.ink : T.inkDim, 0, 100);
    }
    heading(2, "Hide bars while reading", 444);
    omniLabel("After 3 s without input. Any button brings them back.", 332 + dx, 470 + dy, omniCaption, T.inkDim, 0, 548);
    fillRounded(892 + dx, 442 + dy, 56, 28, 14, omniAutoHide ? T.accent : T.key);
    omniDisc((omniAutoHide ? 934 : 906) + dx, 456 + dy, 10, omniAutoHide ? (omniHc() ? T.accentInk : T.ink) : T.inkDim);
    if (omniHc()) omniLabel(OHCT::toggleWord(omniAutoHide), 880 + dx, 456 + dy, omniSmallBold, T.ink, 2); // OMNI_HIGH_CONTRAST_V1: the state in words
    heading(3, "Resolution (restart to apply)", 518);
    for (int i = 0; i < 3; ++i) {
        const int x = 332 + i * 208 + dx;
        const bool on = omniDisplayChoice == i;
        fillRounded(x, 534 + dy, 200, 40, omniRadius, on ? T.accent : T.key);
        omniLabel(omniDisplayLabels[i], x + 100, 554 + dy, omniSmallBold, on ? T.accentInk : T.ink, 1);
    }
    heading(4, "Playback stats (this session)", 610);
    fillRounded(892 + dx, 596 + dy, 56, 28, 14, omniStatsPanel.enabled ? T.accent : T.key);
    omniDisc((omniStatsPanel.enabled ? 934 : 906) + dx, 610 + dy, 10, omniStatsPanel.enabled ? (omniHc() ? T.accentInk : T.ink) : T.inkDim);
    if (omniHc()) omniLabel(OHCT::toggleWord(omniStatsPanel.enabled), 880 + dx, 610 + dy, omniSmallBold, T.ink, 2); // OMNI_HIGH_CONTRAST_V1
}

// --- OMNI_UI_SCALE_V1_R3 (stage 3): the on-screen keyboard -------------------------------------------------------------
// Its geometry at the level (declared next to keyboardX in OmniBrowser.cpp; OMNI_UIS_KB_LOCALS reads it). The page
// stays visible under the top bar (OUIS::kKbMinPage); while a compact dialog (omniModalLayout: fields above the keyboard,
// ending at 374) is being typed into, the keyboard keeps today's top edge and gets the zoom that fits under it.
static_assert(keyboardX == OUIS::kKbNormalX && keyboardY == OUIS::kKbNormalY && keyHeight == OUIS::kKbPitch && keyboardWidth == OUIS::kKbKeysW
              && actionY == keyboardY + 5 * keyHeight && keyboardY - 58 == OUIS::kKbNormalTop,
              "OMNI_KEYBOARD_V2 geometry changed: update OmniUiScale.h's keyboard constants (stage 3)");
static OUIS::KbFit omniUisKb()
{
    const int level = omniUisLevel();
    if (level == OUIS::Normal) return OUIS::kbNormal();
    return OUIS::fitKeyboard(level, omniEditingModal && editing ? OUIS::kKbNormalTop : top + OUIS::kKbMinPage);
}
// The keyboard panel's top edge in screen layout px (Normal: keyboardY - 58 = 362): toast, History, fill bar, probe.
static int omniUisKbTop() { return omniUisLevel() == OUIS::Normal ? keyboardY - 58 : omniUisKb().top; }

// omniKbDrawText's drawing inside the zoomed keyboard: the view (start, caret / selection x, the surface) was laid out
// in face pixels for `room` face px; drawn here scaled by the zoom at the zoomed layout position (x, cy).
static void omniUisKbTextDraw(const OmniKbView& v, int x, float cy, int room, int font, SDL_Color ink, SDL_Color accent, bool selection)
{
    const double z = omniUisTextZoom;
    auto Z = [&](int facePx) { return int(facePx * z + 0.5); };
    const int px = physical(x), half = font == omniBody ? 13 : 11, roomPx = Z(room);
    const int top = int(cy * displayScale + 0.5) - Z(omniFaces[font].capMid), y0 = physical(int(cy) - half), h = physical(2 * half);
    if (selection && v.selX1 > v.selX0) omniRectPx({ px + Z(v.selX0), y0, Z(v.selX1) - Z(v.selX0), h }, accent, 90);
    if (SDL_Surface* s = v.surface) {
        const SDL_PixelFormat* sf = s->format;
        if (sf->BytesPerPixel == 4 && sf->Amask && !SDL_MUSTLOCK(s)) {
            SDL_Color c = ink; c.a = 255;
            omniUisBlitCoverage(static_cast<const uint8_t*>(s->pixels), s->w, s->h, s->pitch, 4, sf->Ashift / 8, px, top, room, c, 255);
        } else {
            omniBlitText(s, px, int(cy * displayScale + 0.5) - omniFaces[font].capMid, room, 255);   // unknown format: unscaled
        }
    }
    const int bar = std::max(2, physical(2));
    omniRectPx({ px + std::min(Z(v.caretX), roomPx - bar) - bar / 2, y0, bar, h }, accent);
    if (v.left) omniRectPx({ px - physical(6), y0, std::max(1, physical(1)), h }, accent, 110);
    if (v.right) omniRectPx({ px + roomPx + physical(5), y0, std::max(1, physical(1)), h }, accent, 110);
}

// The keyboard's hint line (omniKbHints, inside the hints bar) zoomed: the level's scale, at most OUIS::kHintLineMax
// while the bar keeps today's height, lowered so the line fits the width. The line's width is remembered from the last
// draw (labels report their right edge, omniUisLineRight); when the line got wider than that zoom allows it is drawn
// once more, on a fresh bar, at the zoom that fits. true: drawn here (omniKbHints returns at once).
static bool omniUisKbHints()
{
    if (omniUisKbHintsBusy) return false;
    const int level = omniUisLevel();
    if (level == OUIS::Normal) return false;
    static int natural = 0;
    double z = OUIS::hintLineZoom(level, natural);
    for (int pass = 0; pass < 2; ++pass) {
        if (z == 1.0) return false;   // today's line, drawn by the caller
        omniUisLineRight = 0;
        {
            OmniUisZoomScope uisZoom(z);
            omniUisKbHintsBusy = true;
            omniKbHints();
            omniUisKbHintsBusy = false;
        }
        natural = omniUisLineRight;
        const double fit = OUIS::hintLineZoom(level, natural);
        if (fit >= z) return true;
        omniHintBarBg();
        z = fit;
    }
    return true;
}

// --- the address suggestions (OMNI_FEATURES_V3 / OMNI_TAB_SEARCH_V1 / OMNI_QUICK_ANSWERS_V1 rows) ----------------------
// Today: 914 wide under the address row (y 108), 46 px rows, up to 5, the tip pill below. At a level: the keyboard's
// zoom (they line up), ending above the zoomed keyboard; fewer rows than items: a window that follows the selection.
struct OmniUisList { double zoom = 1.0; int x = 0, y = 0, rows = 0, first = 0; };
static OmniUisList omniUisSuggestBox()
{
    OmniUisList b;
    const int level = omniUisLevel();
    if (level == OUIS::Normal) return b;
    const OUIS::KbFit kb = omniUisKb();
    const OUIS::ListFit f = OUIS::fitList(level, kb.zoom, omniSuggestW, 8 + 28, omniSuggestRow, int(omniSuggestions.size()), omniSuggestSel,
                                          omniSuggestY, kb.top);
    b.zoom = f.zoom; b.x = f.x; b.y = f.y; b.rows = f.rows; b.first = f.first;
    return b;
}
// omniSuggestClick at a level: the pointer in the list's zoomed space, rows first..first+rows.
static bool omniUisSuggestClick(int x, int y)
{
    const OmniUisList L = omniUisSuggestBox();
    omniUisMap(L.zoom, x, y);
    if (x < L.x || x >= L.x + omniSuggestW || y < L.y) return false;
    const int k = (y - L.y - 4) / omniSuggestRow;
    if (k < 0 || k >= L.rows || L.first + k >= int(omniSuggestions.size())) return false;
    omniSuggestGo(L.first + k);
    return true;
}
// omniSuggestDraw at a level: the same drawing (apply_ui_scale.py checks omniSuggestDraw's sha256, SUGGEST_SHA) on the
// zoomed box, row k showing suggestion first + k; "2-4 of 5" on a pill when not every row fits.
static void omniUisSuggestDraw()
{
    const OmniUisList L = omniUisSuggestBox();
    OmniUisZoomScope uisZoom(L.zoom);
    const OmniTheme& T = omniTheme();
    const int omniSuggestX = L.x, omniSuggestY = L.y, total = int(omniSuggestions.size());
    const int n = std::min(L.rows, total - L.first), h = n * omniSuggestRow + 8;
    omniShadow(omniSuggestX, omniSuggestY, omniSuggestW, h, omniRadius, 14, 130, 4);
    fillRounded(omniSuggestX, omniSuggestY, omniSuggestW, h, omniRadius, T.raised);
    for (int k = 0; k < n; ++k) {
        const int i = L.first + k;
        const int y = omniSuggestY + 4 + k * omniSuggestRow;
        const bool sel = omniSuggestSel == i;
        if (sel) fillRounded(omniSuggestX + 4, y, omniSuggestW - 8, omniSuggestRow, omniRadius, T.accent);
        const auto& s = omniSuggestions[i];
        const std::string bare = s.search ? omniF3SuggestDetail() : s.omniTqKind ? omniTqDetail(s) : omniShownURL(s.url);
        const int ix = omniTqIcon(s, omniSuggestX + 18, y + omniSuggestRow / 2.f, sel);
        const int w = omniLabel(s.title.empty() ? bare : s.title, omniSuggestX + 18 + ix, y + omniSuggestRow / 2.f, omniSmall, sel ? T.accentInk : T.ink, 0, 520 - ix);
        omniLabel(bare, omniSuggestX + 30 + ix + w, y + omniSuggestRow / 2.f, omniSmall, sel ? T.accentInk : T.inkDim, 0, omniSuggestW - 60 - ix - w);
    }
    if (n < total) {
        char more[48];
        snprintf(more, sizeof more, "%d-%d of %d", L.first + 1, L.first + n, total);
        const int mw = int(omniTextWidthPx(omniCaption, more) / displayScale + 0.5);
        fillRounded(omniSuggestX, omniSuggestY + h + 4, mw + 24, 24, 12, T.raised, 235);
        omniLabel(more, omniSuggestX + 12, omniSuggestY + h + 16, omniCaption, T.inkDim);
    }
    if (omniSuggestSel < 0) {
        const char* tip = "\xe2\x96\xb2 Up from the top row of keys: suggestions";
        const int tw = int(omniTextWidthPx(omniCaption, tip) / displayScale + 0.5);
        fillRounded(omniSuggestX + omniSuggestW - tw - 24, omniSuggestY + h + 4, tw + 24, 24, 12, T.raised, 235);
        omniLabel(tip, omniSuggestX + omniSuggestW - 12, omniSuggestY + h + 16, omniCaption, T.inkDim, 2);
    }
}
// (The find bar's box, omniUisFindBox, is written next to omniFindClick by apply_ui_scale.py: a tree with
// OMNI_FIND_PLUS_V1 has another find bar and gets neither.)

// --- OMNI_UI_SCALE_V1_R4 (stage 4): the hints bar ------------------------------------------------------------------------
// Every omniHints line (browsing, settings, panels via omniPanelHints, dialogs, controls help) at a level: measured at
// today's scale (the line's natural width, both margins, the note included), drawn with displayScale * OUIS::hintsZoom
// inside the bar's 32 px (omniHints / omniHintDraw use the zoomed width and centre line meanwhile). A zoomed panel's
// hints are unzoomed first. true: drawn here (omniHints returns at once). The keyboard's line is omniUisKbHints'.
static bool omniUisHintsBusy = false;
static bool omniUisHints(const std::vector<OmniHint>& left, const std::vector<OmniHint>& right, const std::string& note)
{
    if (omniUisHintsBusy) return false;
    const int level = omniUisLevel();
    if (level == OUIS::Normal) return false;
    OmniUisUnzoom unzoom;
    int natural = 40;
    for (const auto& h : left) natural += omniHintItemW(h) + omniHintGap;
    for (const auto& h : right) natural += omniHintItemW(h) + omniHintGap;
    natural -= omniHintGap;
    if (!note.empty()) natural += int(omniTextWidthPx(omniSmall, note) / displayScale + 0.5) + (right.empty() ? omniHintGap : 0);
    omniUisHintsBusy = true;
    {
        OmniUisZoomScope uisZoom(OUIS::hintsZoom(level, natural));
        omniHints(left, right, note);
    }
    omniUisHintsBusy = false;
    return true;
}

// --- R4: dialogs (omniModal*: alerts, confirms, prompts, logins, selects, omniAsk) ------------------------------------------
// Today's layout (omniModalLayout with omniUisModalBusy), fitted by OUIS::fitDialog: fewer message lines / select rows
// when they do not fit at the zoom (the message scrolls, the list pages as today), then every rectangle moved into the
// zoomed layout space. omniDrawModal draws it in an OmniUisZoomScope (hover: the zoomed pointer) and omniModalHit maps
// the pointer with L.zoom: Cross, clicks and hover all test the rectangles that were drawn.
static OmniModalLayout omniUisModalLayout(OmniModal& m)
{
    const int level = omniUisLevel();
    omniUisModalBusy = true;
    OmniModalLayout L = omniModalLayout(m);
    const bool select = m.kind == omniModalSelect;
    const int rowH = select ? L.rowHeight : L.lineHeight, rows = select ? L.visibleRows : L.visibleLines;
    const OUIS::BoxFit f = OUIS::fitDialog(level, L.panel.w, L.panel.h - rows * rowH, rowH, rows, L.compact);
    if (f.rows < rows) {
        omniUisModalCap = f.rows;
        L = omniModalLayout(m);
        omniUisModalCap = 1 << 20;
    }
    omniUisModalBusy = false;
    const int dx = f.x - L.panel.x, dy = f.y - L.panel.y;
    auto move = [&](OmniRect& r) { r.x += dx; r.y += dy; };
    move(L.panel); move(L.message); move(L.list);
    for (OmniRect& r : L.field) move(r);
    for (OmniRect& r : L.fieldLabel) move(r);
    for (OmniRect& r : L.button) move(r);
    L.zoom = f.zoom;
    return L;
}

// --- R4: the screenshot grid (OMNI_SCREENSHOT_GALLERY_V1, 4 x 3 tiles of 256 x 191 at Normal) ---------------------------------
// OUIS::fitGrid: Large 3 x 2 at 1.25, Extra large 3 x 2 at 1.444 (two rows need it), Small 4 x 3 at 0.85. The pager pages
// by the grid shown (omniSsPager.cols / rows); thumbnails stay decoded at the Normal box size and are drawn scaled.
static OUIS::GridFit omniUisSsFit()
{
    const OUIS::GridFit f = OUIS::fitGrid(omniUisLevel(), OSG::kThumbW + 16, OSG::kThumbH + 56, 10, OSG::kCols, OSG::kRows, 64, 24, 12);
    if (omniSsPager.cols != f.cols || omniSsPager.rows != f.rows) { omniSsPager.cols = f.cols; omniSsPager.rows = f.rows; omniSsPager.clamp(); }
    return f;
}
static void omniUisSsGrid() { omniUisSsFit(); }   // omniSsButton / omniSsScroll: the D-pad and the stick move in the grid shown
static OmniSsGeom omniUisSsGeometry()
{
    OmniSsGeom g {};
    g.tw = OSG::kThumbW + 16; g.th = OSG::kThumbH + 56; g.gap = 10;
    const OUIS::GridFit f = omniUisSsFit();
    g.zoom = f.zoom; g.cols = f.cols;
    g.x = f.x; g.y = f.y; g.w = f.w; g.h = f.h;
    g.listY = g.y + 64;
    return g;
}
// omniUisSet: back at Normal the pager pages by 4 x 3 again (the grid's geometry is today's code there).
static void omniUisLevelChanged()
{
    omniSsPager.cols = OSG::kCols;
    omniSsPager.rows = OSG::kRows;
    omniSsPager.clamp();
}
