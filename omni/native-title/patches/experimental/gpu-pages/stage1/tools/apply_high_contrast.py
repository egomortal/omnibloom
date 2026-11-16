#!/usr/bin/env python3
"""OMNI_HIGH_CONTRAST_V1 (2026-11-16): a "High contrast" theme for Omni's own UI and a "Large pointer" option (low vision).

What the user sees
  - Browser settings, just before "Controller, theme and display..." (where the theme is chosen):
        "High contrast"   On / Off      (Left / Right / Cross toggle)  -> switches the UI theme to "High contrast";
                                         Off goes back to the theme used before (ui-theme-prev.txt; Dark if unknown)
        "Large pointer"   On (2x) / Off (Left / Right / Cross toggle)  -> /data/omni/pointer-large.txt ("on" / "off")
  - Controller, theme and display > Theme: a fifth card "High contrast" (the 5 cards share the old 616 px row: disc on
    top, centred caption; the hit test follows OmniHighContrast::cardAt; 4 themes would give the old 156 / 148 layout).
    Saved like the others in /data/omni/ui-theme.txt as "contrast" (no other id is a prefix of it or it of one).
  - With the theme on: black bars / panels / tabs, white text, light-grey secondary text, a yellow accent: selected rows
    and keys are yellow with black text, focus rings (omniRingRect / omniRingDisc: tabs, tool buttons, chips, close
    buttons) are yellow and 6 layout px instead of 2 (3x). Panels get a solid white 2 px edge instead of the soft
    shadow (omniShadow), the bars' soft dark edge over the page (omniFadeRows) is not drawn, panels do not fade in
    (omniPanelT = 1), and translucent surfaces with alpha >= 150 (hint pills, info strips) are drawn solid
    (omniRectPx / omniRoundedPx via OmniHighContrast::opaqueAlpha). Scrims behind modals (alpha 70-120) and selection
    tints (90 / 110) stay translucent: they must show what is under them. There is no blur anywhere in the shell.
    Disabled rows (Browser settings / every OmniFxPanel list and grid, the Browser tools menu) are mid grey (160),
    struck through and followed by "(off)" (not colour alone). Danger rows use a lighter red (255,128,128: 8.6:1 on
    black; the usual 236,98,98 is 6.5:1). The two switches in Controller, theme and display (Hide bars while reading,
    Playback stats) also say "On" / "Off" next to the switch, and the knob is black on the yellow track.
  - Large pointer: the pointer sprite (any style / colour / size / picture from /data/omni/pointers) is scaled 2x with
    bilinear smoothing on premultiplied alpha, once per change (the sprite cache's signature includes the option), and
    the hotspot doubles so clicks still land on the tip. Larger than 2048 px a side: the normal size is kept.
    Self-test modes ignore it (like the keyboard layout).
  - Contrast (WCAG 2 formula, OmniHighContrast::checks, all pairs the shell draws with the palette): text worst 7.59:1
    (inkDim on the 20-grey keys), focus ring worst 10.7:1 (yellow vs the hover fill), disabled grey >= 7:1 on the black
    surfaces and >= 5.5:1 on the raised ones, white vs disabled grey 2.6:1.
Works with:
  - Interface size (apply_ui_scale.py): everything here draws in layout px through physical() / fillRounded /
    omniLabel, so zoomed panels zoom the ring, the strike and "(off)" too; omniShadow's HC branch returns before the
    mask cache ui_scale keys by scale; no ui_scale anchor is used here.
  - Night light: the tint is applied by the GPU present over the finished frame, on top of this theme (fine).
  - Other drawing: the hub / start page cards, the error page, QR, gallery use the theme colours, so they follow.
    omniGood / omniWarn and a few fixed colours (private-tab purple) are unchanged.

Pure part: engine/entry/OmniHighContrast.h (kept next to this script): palette, WCAG contrast, the checks, ring /
alpha / "(off)" rules, theme card layout, pointer-large.txt, the 2x bilinear scaler.
Tested by tools/test_high_contrast.cpp:  g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_high_contrast.cpp -o t && ./t
Shell side: OmniBrowser.cpp (namespace alias OHCT), OmniFeaturesPanel.h, OmniBrowserSettings.h (row ids 838 High
contrast, 839 Large pointer; 834, 836, 837, 845-848, 850, 860, 861, 870, 880, 890, 891, 895, 900+, 940-943 are taken).

Anchors (exactly once each; MARK makes each file idempotent; CRLF / LF kept, matched as \\r?\\n):
  OmniBrowser.cpp
    "struct OmniTheme {"                          -> include, alias, omniHcC before it
    the "purple" theme's last line + "};"         -> the High contrast entry appended to omniThemes
    omniTheme()                                   -> omniHc(), omniHcThemeIndex(), omniHcInk() after it
    omniRectPx's / omniRoundedPx's first lines    -> opaqueAlpha
    omniShadow's first lines                      -> white edge instead of the shadow (before ui_scale's mask lines)
    omniFadeRows's first lines                    -> skipped
    the "OMNI_POLISH_V1: shared look" omniRingRect / omniRingDisc -> thickness from ringPx; omniHcLabel after them
    omniPanelT's "since <= 1" line                -> no fade
    omniPointerSprite's body                      -> Large pointer (state, 2x sprite) before it
    omniSettingsPanel: the theme card loop, the two switch knobs; omniSettingsClick: the theme hit test
    omniMenuDraw: the ink line, the row label
    '#include "OmniFeatures.h" // OMNI_FEATURES_V1' -> the Browser settings rows after it
  OmniFeaturesPanel.h  grid + list: the ink lines (with the fill line before each), the label lines
  OmniBrowserSettings.h  "static std::string omniFxHomeEdit;", the "Controller, theme and display..." row,
                         the omniCwRowId dispatch line
usage: apply_high_contrast.py <engine tree>   (re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_HIGH_CONTRAST_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'
HERE = Path(__file__).resolve().parent
PURE_NAME = 'OmniHighContrast.h'

EDITS = {
    'OmniBrowser.cpp': [
        ('struct OmniTheme {\n',
         '#include "OmniHighContrast.h" // OMNI_HIGH_CONTRAST_V1: High contrast palette, WCAG checks, Large pointer scaler (pure)\n'
         'namespace OHCT = OmniHighContrast;\n'
         'static constexpr SDL_Color omniHcC(OHCT::Rgb c) { return { c.r, c.g, c.b, 255 }; }\n'
         'struct OmniTheme {\n'),
        ('      {43,37,60,255}, {66,58,88,255}, {255,150,210,255} },\n'
         '};\n',
         '      {43,37,60,255}, {66,58,88,255}, {255,150,210,255} },\n'
         '    // OMNI_HIGH_CONTRAST_V1: pure black surfaces, white text, yellow accent / focus (palette checked in OmniHighContrast.h)\n'
         '    { OHCT::kThemeId, OHCT::kThemeName, omniHcC(OHCT::kPalette.bg), omniHcC(OHCT::kPalette.bar), omniHcC(OHCT::kPalette.line),\n'
         '      omniHcC(OHCT::kPalette.tab), omniHcC(OHCT::kPalette.hover), omniHcC(OHCT::kPalette.field), omniHcC(OHCT::kPalette.panel),\n'
         '      omniHcC(OHCT::kPalette.raised), omniHcC(OHCT::kPalette.key), omniHcC(OHCT::kPalette.ink), omniHcC(OHCT::kPalette.inkDim),\n'
         '      omniHcC(OHCT::kPalette.inkFaint), omniHcC(OHCT::kPalette.accent), omniHcC(OHCT::kPalette.accentInk),\n'
         '      omniHcC(OHCT::kPalette.tabOn), omniHcC(OHCT::kPalette.edge), omniHcC(OHCT::kPalette.accent2) },\n'
         '};\n'),
        ('static const OmniTheme& omniTheme() { return omniThemes[omniThemeIndex]; }\n',
         'static const OmniTheme& omniTheme() { return omniThemes[omniThemeIndex]; }\n'
         '// OMNI_HIGH_CONTRAST_V1: the High contrast theme is on (thick yellow rings, solid panels, "(off)" rows ...).\n'
         'static int omniHcThemeIndex()\n'
         '{\n'
         '    static const int index = [] { for (int i = 0; i < omniThemeCount; ++i) if (!strcmp(omniThemes[i].id, OHCT::kThemeId)) return i; return -1; }();\n'
         '    return index;\n'
         '}\n'
         'static bool omniHc() { return omniThemeIndex == omniHcThemeIndex(); }\n'
         '// Row text colours: the shell\'s red is 6.5:1 on black, High contrast uses a lighter one (>= 7:1).\n'
         'static SDL_Color omniHcInk(SDL_Color c)\n'
         '{\n'
         '    if (!omniHc() || c.r != omniBad.r || c.g != omniBad.g || c.b != omniBad.b) return c;\n'
         '    return omniHcC(OHCT::kDanger);\n'
         '}\n'),
        ('    if (r.w <= 0 || r.h <= 0 || !alpha) return;\n'
         '    const OmniPix f = omniPix();\n',
         '    if (r.w <= 0 || r.h <= 0 || !alpha) return;\n'
         '    alpha = OHCT::opaqueAlpha(alpha, omniHc()); // OMNI_HIGH_CONTRAST_V1: translucent surfaces drawn solid (scrims stay)\n'
         '    const OmniPix f = omniPix();\n'),
        ('    r = std::min({ r, R.w / 2, R.h / 2 });\n'
         '    const OmniPix f = omniPix();\n',
         '    r = std::min({ r, R.w / 2, R.h / 2 });\n'
         '    alpha = OHCT::opaqueAlpha(alpha, omniHc()); // OMNI_HIGH_CONTRAST_V1\n'
         '    const OmniPix f = omniPix();\n'),
        ('static void omniShadow(int x, int y, int w, int h, int radius, int blur, uint8_t strength, int dy = 0)\n'
         '{\n'
         '    const OmniPix f = omniPix();\n'
         '    if (!f.ok || !strength) return;\n',
         'static void omniShadow(int x, int y, int w, int h, int radius, int blur, uint8_t strength, int dy = 0)\n'
         '{\n'
         '    const OmniPix f = omniPix();\n'
         '    if (!f.ok || !strength) return;\n'
         '    if (omniHc()) { fillRounded(x - 2, y - 2, w + 4, h + 4, radius + 2, omniTheme().edge); return; } // OMNI_HIGH_CONTRAST_V1: a solid edge, no soft shadow (the panel drawn next covers the inside)\n'),
        ('static void omniFadeRows(int y, int rows, int from, int to)\n'
         '{\n'
         '    const OmniPix f = omniPix();\n'
         '    if (!f.ok) return;\n',
         'static void omniFadeRows(int y, int rows, int from, int to)\n'
         '{\n'
         '    const OmniPix f = omniPix();\n'
         '    if (!f.ok || omniHc()) return; // OMNI_HIGH_CONTRAST_V1: hard bar edges (the hairline stays)\n'),
        ('static void omniRingRect(int x, int y, int w, int h, int r, SDL_Color ring, SDL_Color inside)\n'
         '{\n'
         '    fillRounded(x - 2, y - 2, w + 4, h + 4, r + 2, ring);\n'
         '    fillRounded(x, y, w, h, r, inside);\n'
         '}\n'
         'static void omniRingDisc(float cx, float cy, float r, SDL_Color ring, SDL_Color inside)\n'
         '{\n'
         '    omniDisc(cx, cy, r + 2, ring);\n'
         '    omniDisc(cx, cy, r, inside);\n'
         '}\n',
         '// OMNI_HIGH_CONTRAST_V1: rings 3x thicker (6 layout px) with the High contrast theme (its accent is the yellow).\n'
         'static void omniRingRect(int x, int y, int w, int h, int r, SDL_Color ring, SDL_Color inside)\n'
         '{\n'
         '    const int t = OHCT::ringPx(2, omniHc());\n'
         '    fillRounded(x - t, y - t, w + 2 * t, h + 2 * t, r + t, ring);\n'
         '    fillRounded(x, y, w, h, r, inside);\n'
         '}\n'
         'static void omniRingDisc(float cx, float cy, float r, SDL_Color ring, SDL_Color inside)\n'
         '{\n'
         '    omniDisc(cx, cy, r + OHCT::ringPx(2, omniHc()), ring);\n'
         '    omniDisc(cx, cy, r, inside);\n'
         '}\n'
         '// OMNI_HIGH_CONTRAST_V1: a row label; disabled rows with High contrast are struck through and followed by "(off)".\n'
         '// Returns the width in layout px like omniLabel (align: starts at x).\n'
         'static int omniHcLabel(const std::string& text, float x, float cy, int face, SDL_Color ink, bool enabled, int maxW = 0)\n'
         '{\n'
         '    if (enabled || !omniHc()) return omniLabel(text, x, cy, face, ink, 0, maxW);\n'
         '    const int gap = 8;\n'
         '    const int suffixW = omniLabel(OHCT::kOffSuffix, -10000, cy, face, ink, 0, 0, 1) + gap;   // measure (drawn off screen)\n'
         '    const int w = omniLabel(text, x, cy, face, ink, 0, maxW > 0 ? std::max(24, maxW - suffixW) : 0);\n'
         '    const int t = std::max(1, physical(OHCT::kStrikePx));\n'
         '    omniRectPx({ physical(int(x + 0.5f)), int(cy * displayScale + 0.5) - t / 2, std::max(1, physical(w)), t }, ink);\n'
         '    if (maxW > 0 && w + suffixW > maxW) return w;\n'
         '    return w + gap + omniLabel(OHCT::kOffSuffix, x + w + gap, cy, face, ink);\n'
         '}\n'),
        ('    if (!omniAutoHideAllowed || since <= 1) {',
         '    if (!omniAutoHideAllowed || since <= 1 || omniHc()) { /* OMNI_HIGH_CONTRAST_V1: no fade (no see-through panels) */'),
        ('static SDL_Surface* omniPointerSprite()\n'
         '{\n'
         '    static SDL_Surface* sprite = nullptr;\n'
         '    static uint64_t builtFor = 0;\n'
         '    const uint64_t want = omniPtrSignature(displayScale);\n'
         '    if (builtFor == want) return sprite;\n'
         '    builtFor = want;\n'
         '    if (sprite) { SDL_FreeSurface(sprite); sprite = nullptr; }\n'
         '    sprite = omniPtrBuildSprite(displayScale, &omniPointerHotX, &omniPointerHotY);\n'
         '    return sprite;\n'
         '}\n',
         '// OMNI_HIGH_CONTRAST_V1: Browser settings > "Large pointer": the sprite scaled 2x (bilinear, premultiplied) once per\n'
         '// change. /data/omni/pointer-large.txt "on" / "off", read once; self-tests keep the normal size.\n'
         'static int omniHcLargeState = -1;   // -1: not read yet\n'
         'static bool omniHcLargePointer()\n'
         '{\n'
         '    if (omniTestMode()) return false;\n'
         '    if (omniHcLargeState < 0) {\n'
         '        std::string text;\n'
         '        if (FILE* f = fopen(omniData("pointer-large.txt").c_str(), "rb")) { char b[32]; const size_t n = fread(b, 1, sizeof(b), f); fclose(f); text.assign(b, n); }\n'
         '        omniHcLargeState = OHCT::parseLarge(text) ? 1 : 0;\n'
         '    }\n'
         '    return omniHcLargeState == 1;\n'
         '}\n'
         '// The sprite (straight-alpha ARGB8888 from omniPtrSurface) 2x larger with its hotspot; the original when it cannot.\n'
         'static SDL_Surface* omniHcLargeSprite(SDL_Surface* s, int* hotX, int* hotY)\n'
         '{\n'
         '    if (!s || s->format->format != SDL_PIXELFORMAT_ARGB8888 || !OHCT::canScale(s->w, s->h)) return s;\n'
         '    std::vector<uint32_t> src(size_t(s->w) * s->h), out;\n'
         '    if (SDL_MUSTLOCK(s) && SDL_LockSurface(s)) return s;\n'
         '    for (int y = 0; y < s->h; ++y) memcpy(src.data() + size_t(y) * s->w, static_cast<const uint8_t*>(s->pixels) + size_t(y) * s->pitch, size_t(s->w) * 4);\n'
         '    if (SDL_MUSTLOCK(s)) SDL_UnlockSurface(s);\n'
         '    OHCT::scaleArgb(src.data(), s->w, s->h, OHCT::kPointerScale, out);\n'
         '    const int W = s->w * OHCT::kPointerScale, H = s->h * OHCT::kPointerScale;\n'
         '    SDL_Surface* big = SDL_CreateRGBSurfaceWithFormat(0, W, H, 32, SDL_PIXELFORMAT_ARGB8888);\n'
         '    if (!big) return s;\n'
         '    for (int y = 0; y < H; ++y) memcpy(static_cast<uint8_t*>(big->pixels) + size_t(y) * big->pitch, out.data() + size_t(y) * W, size_t(W) * 4);\n'
         '    SDL_SetSurfaceBlendMode(big, SDL_BLENDMODE_BLEND);\n'
         '    SDL_FreeSurface(s);\n'
         '    *hotX = OHCT::scaledHot(*hotX); *hotY = OHCT::scaledHot(*hotY);\n'
         '    return big;\n'
         '}\n'
         'static SDL_Surface* omniPointerSprite()\n'
         '{\n'
         '    static SDL_Surface* sprite = nullptr;\n'
         '    static uint64_t builtFor = 0;\n'
         '    const bool large = omniHcLargePointer(); // OMNI_HIGH_CONTRAST_V1\n'
         '    const uint64_t want = omniPtrSignature(displayScale) ^ (large ? 0x9e3779b97f4a7c15ull : 0);\n'
         '    if (builtFor == want) return sprite;\n'
         '    builtFor = want;\n'
         '    if (sprite) { SDL_FreeSurface(sprite); sprite = nullptr; }\n'
         '    sprite = omniPtrBuildSprite(displayScale, &omniPointerHotX, &omniPointerHotY);\n'
         '    if (large) sprite = omniHcLargeSprite(sprite, &omniPointerHotX, &omniPointerHotY); // OMNI_HIGH_CONTRAST_V1\n'
         '    return sprite;\n'
         '}\n'),
        ('    for (int i = 0; i < omniThemeCount; ++i) {\n'
         '        const int x = 332 + i * 156;\n'
         '        const bool on = omniThemeIndex == i;\n'
         '        const OmniTheme& t = omniThemes[i];\n'
         '        if (on) fillRounded(x - 2, 358, 152, 56, omniRadius + 1, T.accent);\n'
         '        fillRounded(x, 360, 148, 52, omniRadius, on ? T.raised : T.tab);\n'
         '        omniDisc(x + 24, 386, 13, t.line);\n'
         '        omniDisc(x + 24, 386, 12, t.bar);\n'
         '        omniDisc(x + 24, 386, 5.5f, t.accent);\n'
         '        omniLabel(t.name, x + 44, 386, omniSmall, on ? T.ink : T.inkDim, 0, 100);\n'
         '    }\n',
         '    const int themeStride = OHCT::cardStride(omniThemeCount), themeW = OHCT::cardWidth(omniThemeCount); // OMNI_HIGH_CONTRAST_V1: 5 cards in the row\n'
         '    for (int i = 0; i < omniThemeCount; ++i) {\n'
         '        const int x = 332 + i * themeStride;\n'
         '        const bool on = omniThemeIndex == i;\n'
         '        const OmniTheme& t = omniThemes[i];\n'
         '        if (on) fillRounded(x - 2, 358, themeW + 4, 56, omniRadius + 1, T.accent);\n'
         '        fillRounded(x, 360, themeW, 52, omniRadius, on ? T.raised : T.tab);\n'
         '        if (OHCT::stackedCards(omniThemeCount)) {   // disc above a centred caption\n'
         '            omniDisc(x + themeW / 2.f, 375, 10, t.line);\n'
         '            omniDisc(x + themeW / 2.f, 375, 9, t.bar);\n'
         '            omniDisc(x + themeW / 2.f, 375, 4, t.accent);\n'
         '            omniLabel(t.name, x + themeW / 2.f, 399, omniCaption, on ? T.ink : T.inkDim, 1, themeW - 8);\n'
         '            continue;\n'
         '        }\n'
         '        omniDisc(x + 24, 386, 13, t.line);\n'
         '        omniDisc(x + 24, 386, 12, t.bar);\n'
         '        omniDisc(x + 24, 386, 5.5f, t.accent);\n'
         '        omniLabel(t.name, x + 44, 386, omniSmall, on ? T.ink : T.inkDim, 0, 100);\n'
         '    }\n'),
        ('    omniDisc(omniAutoHide ? 934 : 906, 456, 10, omniAutoHide ? T.ink : T.inkDim);\n',
         '    omniDisc(omniAutoHide ? 934 : 906, 456, 10, omniAutoHide ? (omniHc() ? T.accentInk : T.ink) : T.inkDim);\n'
         '    if (omniHc()) omniLabel(OHCT::toggleWord(omniAutoHide), 880, 456, omniSmallBold, T.ink, 2); // OMNI_HIGH_CONTRAST_V1: the state in words\n'),
        ('    omniDisc(omniStatsPanel.enabled ? 934 : 906, 610, 10, omniStatsPanel.enabled ? T.ink : T.inkDim);\n',
         '    omniDisc(omniStatsPanel.enabled ? 934 : 906, 610, 10, omniStatsPanel.enabled ? (omniHc() ? T.accentInk : T.ink) : T.inkDim);\n'
         '    if (omniHc()) omniLabel(OHCT::toggleWord(omniStatsPanel.enabled), 880, 610, omniSmallBold, T.ink, 2); // OMNI_HIGH_CONTRAST_V1\n'),
        ('    if (y >= 360 && y < 412 && x >= 332 && x < 948 && (x - 332) % 156 < 148) {\n'
         '        omniSettingsRow = 1; omniThemeIndex = (x - 332) / 156; saveUiTheme(); return;\n'
         '    }\n',
         '    if (y >= 360 && y < 412 && OHCT::cardAt(x - 332, omniThemeCount) >= 0) { // OMNI_HIGH_CONTRAST_V1: the card layout of omniSettingsPanel\n'
         '        omniSettingsRow = 1; omniThemeIndex = OHCT::cardAt(x - 332, omniThemeCount); saveUiTheme(); return;\n'
         '    }\n'),
        ('        const SDL_Color ink = sel && on ? T.accentInk : on ? (i == omniMenuClear ? omniBad : T.ink) : T.inkFaint;\n',
         '        const SDL_Color ink = omniHcInk(sel && on ? T.accentInk : on ? (i == omniMenuClear ? omniBad : T.ink) : T.inkFaint); // OMNI_HIGH_CONTRAST_V1\n'),
        ('        omniLabel(labels[i], x + 32, cy, omniBody, ink);\n',
         '        omniHcLabel(labels[i], x + 32, cy, omniBody, ink, on); // OMNI_HIGH_CONTRAST_V1: disabled: struck, "(off)"\n'),
        ('#include "OmniFeatures.h" // OMNI_FEATURES_V1\n',
         '#include "OmniFeatures.h" // OMNI_FEATURES_V1\n'
         '// OMNI_HIGH_CONTRAST_V1: Browser settings > "High contrast" and "Large pointer" (row ids in OmniBrowserSettings.h).\n'
         'static int omniHcPrevTheme = -1;   // the theme to go back to when High contrast is turned off\n'
         'static void omniHcSetTheme(bool on)\n'
         '{\n'
         '    const int hc = omniHcThemeIndex();\n'
         '    if (hc < 0 || on == omniHc()) return;\n'
         '    if (on) {\n'
         '        omniHcPrevTheme = omniThemeIndex;\n'
         '        omniIoQueue(omniData("ui-theme-prev.txt"), std::string(omniThemes[omniThemeIndex].id) + "\\n", false);\n'
         '        omniThemeIndex = hc;\n'
         '    } else {\n'
         '        int prev = omniHcPrevTheme;\n'
         '        if (prev < 0) {\n'
         '            char b[32] {};\n'
         '            if (FILE* f = fopen(omniData("ui-theme-prev.txt").c_str(), "rb")) { const size_t n = fread(b, 1, sizeof(b) - 1, f); fclose(f); b[n] = 0; }\n'
         '            std::string id(b);\n'
         '            while (!id.empty() && (id.back() == \'\\n\' || id.back() == \'\\r\' || id.back() == \' \')) id.pop_back();\n'
         '            for (int i = 0; i < omniThemeCount; ++i) if (id == omniThemes[i].id) prev = i;\n'
         '        }\n'
         '        omniThemeIndex = prev >= 0 && prev != hc ? prev : 0;\n'
         '    }\n'
         '    saveUiTheme();\n'
         '    omniChromeWanted = true; omniShellDirty = omniPageDirty = true;\n'
         '    notice(on ? "High contrast on" : "High contrast off");\n'
         '}\n'
         'static void omniHcSettingsRows(OmniFxPanel& p)\n'
         '{\n'
         '    OmniFxRow r; r.id = omniHcRowTheme; r.label = "High contrast"; r.value = OHCT::toggleWord(omniHc()); r.stepper = true;\n'
         '    p.rows.push_back(r);\n'
         '    OmniFxRow q; q.id = omniHcRowPointer; q.label = "Large pointer"; q.value = omniHcLargePointer() ? "On (2x)" : "Off"; q.stepper = true;\n'
         '    p.rows.push_back(q);\n'
         '}\n'
         'static bool omniHcSettingsInput(int id, int b)\n'
         '{\n'
         '    if (b != SDL_CONTROLLER_BUTTON_DPAD_LEFT && b != SDL_CONTROLLER_BUTTON_DPAD_RIGHT && b != SDL_CONTROLLER_BUTTON_A) return false;\n'
         '    if (id == omniHcRowTheme) omniHcSetTheme(!omniHc());\n'
         '    else {\n'
         '        if (omniTestMode()) { notice("Large pointer is off in test modes"); return true; }\n'
         '        omniHcLargeState = omniHcLargePointer() ? 0 : 1;\n'
         '        omniIoQueue(omniData("pointer-large.txt"), OHCT::serializeLarge(omniHcLargeState == 1), false);\n'
         '        omniShellDirty = true;\n'
         '    }\n'
         '    omniFxRefresh();\n'
         '    return true;\n'
         '}\n'),
    ],
    'OmniFeaturesPanel.h': [
        ('            fillRounded(tx, ty, tw, th, omniRadius, sel ? (on ? T.accent : T.key) : T.tab);\n'
         '            const SDL_Color ink = sel && on ? T.accentInk : on ? (r.danger ? omniBad : T.ink) : T.inkFaint;\n',
         '            fillRounded(tx, ty, tw, th, omniRadius, sel ? (on ? T.accent : T.key) : T.tab);\n'
         '            const SDL_Color ink = omniHcInk(sel && on ? T.accentInk : on ? (r.danger ? omniBad : T.ink) : T.inkFaint); // OMNI_HIGH_CONTRAST_V1\n'),
        ('            omniLabel(r.label, tx + 46, cy, omniBody, ink, 0, tw - 60 - vw);\n',
         '            omniHcLabel(r.label, tx + 46, cy, omniBody, ink, on, tw - 60 - vw); // OMNI_HIGH_CONTRAST_V1: disabled: struck, "(off)"\n'),
        ('            if (sel) fillRounded(g.x + 12, ry + 2, g.w - 24, p.rowH - 4, omniRadius, on ? T.accent : T.key);\n'
         '            const SDL_Color ink = sel && on ? T.accentInk : on ? (r.danger ? omniBad : T.ink) : T.inkFaint;\n',
         '            if (sel) fillRounded(g.x + 12, ry + 2, g.w - 24, p.rowH - 4, omniRadius, on ? T.accent : T.key);\n'
         '            const SDL_Color ink = omniHcInk(sel && on ? T.accentInk : on ? (r.danger ? omniBad : T.ink) : T.inkFaint); // OMNI_HIGH_CONTRAST_V1\n'),
        ('            const int lw = omniLabel(r.label, lx, cy, omniBody, ink, 0, r.detail.empty() ? room : std::min(room, room * 3 / 5));\n',
         '            const int lw = omniHcLabel(r.label, lx, cy, omniBody, ink, on, r.detail.empty() ? room : std::min(room, room * 3 / 5)); // OMNI_HIGH_CONTRAST_V1\n'),
    ],
    'OmniBrowserSettings.h': [
        ('static std::string omniFxHomeEdit;\n',
         'constexpr int omniHcRowTheme = 838, omniHcRowPointer = 839; // OMNI_HIGH_CONTRAST_V1: "High contrast", "Large pointer" (OmniBrowser.cpp)\n'
         'static void omniHcSettingsRows(OmniFxPanel& p);\n'
         'static bool omniHcSettingsInput(int id, int b);\n'
         'static std::string omniFxHomeEdit;\n'),
        ('    add(omniFxSetDisplay, "Controller, theme and display...", "", false);\n',
         '    omniHcSettingsRows(p); // OMNI_HIGH_CONTRAST_V1: High contrast, Large pointer (next to the theme row)\n'
         '    add(omniFxSetDisplay, "Controller, theme and display...", "", false);\n'),
        ('    if (r.id == omniCwRowId) return omniCwSettingsInput(b); // OMNI_CONTINUE_WATCHING_V1 (before the >= 300 rows)\n',
         '    if (r.id == omniHcRowTheme || r.id == omniHcRowPointer) return omniHcSettingsInput(r.id, b); // OMNI_HIGH_CONTRAST_V1 (before the >= 300 rows)\n'
         '    if (r.id == omniCwRowId) return omniCwSettingsInput(b); // OMNI_CONTINUE_WATCHING_V1 (before the >= 300 rows)\n'),
    ],
}


def pattern(text):
    return re.compile(''.join(r'\r?\n' if c == '\n' else re.escape(c) for c in text))


def check(name, edits):
    s = (root / name).read_bytes().decode('utf-8')
    if MARK in s:
        return
    for old, _ in edits:
        n = len(pattern(old).findall(s))
        if n != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, n, old[:90]))


def patch(name, edits):
    p = root / name
    s = p.read_bytes().decode('utf-8')
    if MARK in s:
        return name + ': already'
    for old, new in edits:
        rx = pattern(old)
        m = list(rx.finditer(s))
        if len(m) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, len(m), old[:90]))
        eol = '\r\n' if '\r\n' in m[0].group(0) else ('\r\n' if '\n' not in old and s.count('\r\n') * 2 > s.count('\n') else '\n')
        s = s[:m[0].start()] + new.replace('\n', eol) + s[m[0].end():]
    p.write_bytes(s.encode('utf-8'))
    return name + ': applied'


def write_new(name, like):
    text = (HERE / name).read_text(encoding='utf-8')
    raw = (root / like).read_bytes()
    nl = '\r\n' if raw.count(b'\r\n') * 2 > raw.count(b'\n') else '\n'
    data = text.replace('\r\n', '\n').replace('\n', nl).encode('utf-8')
    h = root / name
    if h.exists() and h.read_bytes() == data:
        return name + ': already'
    h.write_bytes(data)
    return name + ': written'


def main():
    if 'OMNI_POINTER_STYLE_V1' not in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8'):
        sys.exit('OmniBrowser.cpp: OMNI_POINTER_STYLE_V1 missing (the pointer sprite cache this patches)')
    if 'OHCT' in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8') and MARK not in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8'):
        sys.exit('OmniBrowser.cpp: the namespace alias OHCT is already used by something else')
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new(PURE_NAME, 'OmniKbWords.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
