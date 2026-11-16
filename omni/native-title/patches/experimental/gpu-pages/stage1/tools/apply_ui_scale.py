#!/usr/bin/env python3
"""OMNI_UI_SCALE_V1 (2026-11-16): "Interface size" for Omni's own UI (Small / Normal / Large / Extra large).
STAGE 0: the pure part, engine/entry/OmniUiScale.h.
STAGE 1: the controller panels (OmniFxPanel, OmniFeaturesPanel.h) and the Browser settings row.

Audit (r-T tree with every patch up to apply_playback_speed.py; still true with tab groups / bookmarks manager):
  - The whole shell is laid out in a fixed 1280x720 layout space (constexpr width/height/top/bottom) and drawn through
    physical(v) = v * displayScale, displayScale = renderWidth / 1280 (1.5 at 1080p, 3 at 4K).
  - Fonts: 7 faces opened once in omniOpenFonts() at physical(22/17/22/17/28/14/14); text surfaces cached by face id
    (omniTextSurface, 256 strings). Icons: omniIconMask() rasterises each icon once at displayScale.
  - Panels: OmniFeaturesPanel.h (Options, context menu, site settings, downloads, bookmarks (+ manager), tabs (+ tab
    groups menu), browser settings, reading list, quick access, sleep timer chooser, now playing, sessions, file
    picker, passwords, autofill, permissions, add-ons, page tweaks ...) all go through omniFxGeometry / omniFxRowAt.
  Bespoke (own geometry, NOT zoomed by stage 1): History and the Browser tools menu (omniHistoryDraw, omniMenuDraw),
  Controller/theme/display settings (omniSettingsToolsDraw), autofill fill bar (omniF2FillDraw), error page
  (omniFxErrorDraw), the QR code overlay (OmniQrShareShell.h omniQrDraw), the screenshot gallery (OmniShotGalleryShell.h
  omniSsDraw), the address suggestions, find bar, keyboard, notices, top bar.

Stage 1 design (a uniform zoom per panel; Normal takes none of the new paths, so it is unchanged):
  - omniFxGeometry: at a level other than Normal, OmniUiScale::fitPanel gives the zoom and the geometry in a
    1280/zoom x 720/zoom layout space with rows per page clamped so the panel fits above the hints bar
    (OmniFxGeom gets `zoom`, 1.0 by default). L1/R1 page by the clamped rows.
  - omniFxDrawPanel draws with displayScale * zoom (OmniUisZoomScope) and restores it before omniPanelHints (the hints
    bar is stage 4's). omniFxHover / omniFxClick map the pointer with toZoomed() before omniFxRowAt, so the stepper
    arrows and every row hit exactly where they are drawn.
  - Text: no new faces / atlases. omniLabel, inside a zoomed region, renders through today's face and today's text
    cache and blends the cached surface scaled by the zoom (bilinear, per draw, no second cache); ellipsis fitting is
    done in face pixels. Icon masks likewise (kept at the base scale). omniShadow's mask cache key gets displayScale.
    (Nearest larger face was rejected: body 22 has no regular 27.5 / 33 px face, only the bold 28 title.)
  - Browser settings row "Interface size" (id 834, stepper; Left/Right step, Cross cycles, Y Normal), applied on the
    next frame, saved with omniIoQueue to /data/omni/ui-scale.txt.
Later stages (each its own anchors under the same MARK): 3 keyboard, 4 top bar + hints bar.

STAGE 2 (OMNI_UI_SCALE_V1_R2, 2026-11-16): notices and the regions that draw their own geometry, same zoom:
  - toast (OMNI_STYLE_V1 status / page-message pill): omniDrawToast hands over to omniUisToast after its fade maths
    (zoomed pill, same place above the page bottom / keyboard, ellipsis at what fits the screen).
  - QR code panel (OmniQrShareShell.h, apply_qr_share.py): title / address / margins zoomed (fitBox), the code's
    modules stay physical pixels; click mapped (omniUisMap).
  - screenshot gallery (OmniShotGalleryShell.h, apply_screenshot_gallery.py): the full-screen viewer's caption strip
    zoomed. The 4 x 3 grid is NOT zoomed: it already fills the screen (1078 x 669 of 1280 x 688) and its thumbnails
    are decoded at the Normal box size; a bigger grid needs a cols/rows-per-level pager in OmniShotGallery.h.
  - History (constexpr geometry): OMNI_UIS_HISTORY_LOCALS shadows omniHistoryX / Top / Rows / omniHpSearchX /
    omniHpVisible in omniHistoryDraw and omniHistoryButton (rows clamped; L1 / R1 page by them; typing: 4 rows above
    the keyboard); clicks and pointer hover via omniUisToNormal (today's hit-test code, pointer in Normal coordinates).
  - Browser tools menu: drawn zoomed (local omniMenuX / omniMenuY lambdas); zoom lowered so all 9 rows fit (no
    scrolling there); click / hover via omniUisToNormal.
  - controller / theme / display settings (omniSettingsPanel, literal positions): drawn by omniUisSettingsPanel, a
    copy moved by (dx, dy) into the zoomed space; this script checks omniSettingsPanel's sha256 (SETTINGS_SHA) so the
    copy cannot drift. omniSettingsClick / omniPtrSettingsRowAt / the Browser tools pill click: omniUisToNormal.
    The pill (omniSettingsToolsDraw) is drawn zoomed on the moved header row.
  - autofill fill bar (OmniFeatures2.h): zoomed, still just above the keyboard (width / keyboardY shadowed).
  - error page (OmniErrorPage.h) with the HTTPS-only interstitial (OmniHttpsOnlyShell.h, same layout via
    omniHoErrorGeom) and the offline body (OmniOfflineRetryShell.h, text only) inside it: omniFxErrorGeom returns the
    zoomed layout (OmniFxErrorLayout.zoom), draw zoomed with the pointer mapped for chip hover, clicks have a zoomed
    branch. Their handover lines (omniHoErrorDraw / omniHoErrorClick / omniOrOfflineShown / omniOrPanelBody) are
    untouched.
  - shared: inside a zoomed region omniTextWidthPx / omniFit measure in drawn px (so "w / displayScale" and
    omniWrap stay right), omniPanelHints draws the hints bar at today's size (OmniUisUnzoom; stage 4's).
  NOT covered: keyboard (stage 3), top bar / hints bar / offline badge (stage 4), address suggestions, find bar, the
  modal dialogs (omniModal*), the full-screen "Return to browser" hint, the gallery grid (above).
  Upgrade: every edit is idempotent on its own, so a tree with the stage-1 edits gets only the stage-2 ones (and the
  rewritten headers); a fresh tree gets both, byte-identical.
  ORDER: anchors on the generated text of apply_qr_share.py, apply_screenshot_gallery.py, apply_https_only.py and
  apply_offline_retry.py: run apply_ui_scale.py AFTER them (last in the recipe).

STAGE 3 (OMNI_UI_SCALE_V1_R3, 2026-11-16): the on-screen keyboard and what sits around it, same zoom model:
  - keyboard (OMNI_KEYBOARD_V2): OmniUiScale::fitKeyboard. Extra large wants 1.5, the panel (912 wide) caps it at 1.368
    (width); its bottom edge stays 22 px above the hints bar and it grows upwards, but its top may not pass the top bar
    + 140 px (kKbMinPage: the page stays visible above it; Normal leaves 198). The key ROWS give way first (pitch 40 ->
    at least 32; key width, labels and text keep the full zoom); only if even pitch 32 does not fit is the keyboard's
    own zoom lowered (never below 1 for Large / Extra large). Today (bars 164): Large 1.25 / pitch 37, Extra large
    1.368 / pitch 33, top ~306 (Normal 362). While a compact modal dialog is being typed into (its fields end at 374)
    the top stays at 362: zoom 1.187 / pitch 32 at Large and Extra large.
    OMNI_UIS_KB_LOCALS (defined next to keyboardX) shadows keyboardX / keyboardY / keyHeight / actionY in
    omniDrawKeyboard, omniKwDraw (word chips, OMNI_KB_WORDS_V1), omniKblGeometry (accent popup, OMNI_KB_LAYOUTS_V1) and
    omniKbClick; the draw runs in OmniUisZoomScope, omniKbClick maps the pointer with toZoomed first and hands that to
    omniKblClick / omniKwClick / the key rows, so every hit test runs on the numbers the drawing used (the
    OMNI_BARS_CLICK_V1 lesson). Shortcut tiles page included. Preview text (omniKbDrawText, its own surface): laid out in
    face px for the zoomed room and blended scaled (omniUisKbTextDraw).
  - around it: everything that sat above keyboardY - 58 asks omniUisKbTop(): the toast, History while typing, the
    autofill fill bar (its R2 locals line is upgraded in place), the page-field probe (where the field is scrolled to).
  - address suggestions (tab search / quick answers / search engine rows, omniSuggestDraw): the keyboard's zoom, under
    the address row and above the zoomed keyboard, at least 3 rows (zoom lowered for them), a window that follows the
    selection when fewer rows fit ("2-4 of 5" pill); drawn by omniUisSuggestDraw, a copy checked by SUGGEST_SHA.
  - the keyboard hint line (omniKbHints, in the hints bar): zoomed up to 1.25 while the bar keeps its 32 px (stage 4),
    lowered to fit the width (measured on the previous draw, redrawn once when it grew).
  - find bar: zoomed by the level's scale, right edge (1260) and top kept; click via omniUisToNormal. Either bar:
    OMNI_EVERYDAY_V1's in OmniBrowser.cpp, or (tree with apply_find_plus.py) OmniFindPlusShell.h's (OFND::hit kept).
  - omniUisSettingsPanel (stage 2's copy) now copies the OMNI_HIGH_CONTRAST_V1 omniSettingsPanel (SETTINGS_SHA): the
    recipe applies apply_high_contrast.py before this script.
  ORDER (r3): also after apply_kb_words.py, apply_kb_layouts.py, apply_tab_search.py, apply_quick_answers.py,
  apply_find_plus.py, apply_high_contrast.py: still LAST.
  Normal: every new branch starts with the level (or a zoom-1 box) and leaves today's numbers and drawing.
  Upgrade: an R2 tree gets the stage-3 edits, the rewritten headers and the fill bar line replaced in place; a fresh
  tree gets everything, byte-identical.
  NOT covered: top bar (incl. the address field's own text) / hints bar / offline badge (stage 4), the modal dialogs,
  the gallery grid, History's dimmed band while typing (still ends at 362).

STAGE 4 (OMNI_UI_SCALE_V1_R4, 2026-11-16): the top bar, the hints bar, the dialogs, the screenshot grid.
  - CHOICE: the bars keep their height at every level (top 164, or 112 with the quick-access row hidden; hints 32). The
    page area (`top` / pageHeight, omniPageTop / omniPageBottom, WebKit's view size, page-click mapping) is the same at
    every Interface size: nothing WebKit sees changes. Growing the bars was rejected (view resize + page hit-testing
    at every level, the OMNI_BARS_CLICK_V1 class of bug).
  - top bar (omniDrawTopBar after the identity: tabs strip incl. the compact / pinned strips, "+", the badges right of it
    (small comforts battery, sleep timer "zZ", offline, Downloads ring, data saver "Saver"), back / forward / reload,
    the address field (shown URL and the typed text with caret), the bookmark star, the Protection pill, gear, the
    quick-access row): a TEXT-ONLY zoom (OmniUisTextScope, OUIS::barTextZoom: Large 1.25, Extra large 1.5, Small 0.85):
    labels and icons drawn larger at today's positions, boxes / fills / hit areas today's, so the click code is today's
    (no mapping at all). Tab titles and the address ellipsise in their boxes; the badges' own layouts run on the
    zoomed text widths, so they drop their words / hide first; the Protection word is capped to its pill
    (OmniUisTextCap); the star is drawn at the same zoom. The battery glyph (fills) and the "OMNI" identity stay
    today's size.
  - hints bar: every omniHints line (browsing, settings, panels, dialogs, controls help, gallery) drawn by omniUisHints
    with displayScale * OUIS::hintsZoom (at most 1.25 = kHintLineMax, the cap the keyboard's line already has: the bar
    keeps 32 px; lowered so the line fits the width; never below 1 at Large / Extra large).
  - dialogs (omniModal*: alert / confirm / prompt / login / select, every omniAsk): omniModalLayout at a level is
    omniUisModalLayout (today's layout with fewer message lines / select rows when needed, fitted by OUIS::fitDialog,
    moved into the zoomed space; compact dialogs keep 116..374); omniDrawModal draws in its zoom (hover: the zoomed
    pointer), omniModalHit maps the pointer with the same L.zoom.
  - screenshot grid: OUIS::fitGrid (Large 3 x 2 at 1.25, Extra large 3 x 2 at 1.444, Small 4 x 3 at 0.85); OSG::Pager
    gets cols / rows (OmniShotGallery.h, Normal 4 x 3 = today's arithmetic), omniUisSsGeometry sets them, the grid is
    drawn zoomed with the Normal-size thumbnails scaled (omniSsBlitFit), clicks mapped. omniUisSet puts the pager back
    to 4 x 3 when the level returns to Normal.
  ORDER (r4): also after apply_small_comforts.py, apply_sleep_timer.py, apply_offline_retry.py, apply_dl_progress.py,
  apply_data_saver.py: still LAST. (apply_screenshot_gallery.py rewrites OmniShotGallery.h / OmniShotGalleryShell.h if it
  runs again after this script: run this one again then.)
  Normal: no new drawing path; each new branch starts with the level (or a zoom-1 scope that does nothing).
  Upgrade: an r3 tree gets the stage-4 edits and the rewritten headers (no r3 text changes); a fresh tree gets
  everything, byte-identical.
  NOT covered: the battery glyph and the "OMNI" identity (today's size), the full-screen "Return to browser" hint,
  History's dimmed band while typing.

Files: writes engine/entry/OmniUiScale.h, OmniUiScaleShell.h and OmniUiScalePanels.h (kept next to this script),
anchors OmniBrowser.cpp, OmniFeaturesPanel.h, OmniBrowserSettings.h, OmniFeatures2.h, OmniErrorPage.h,
OmniHttpsOnlyShell.h, OmniQrShareShell.h, OmniShotGalleryShell.h, (r3) OmniFindPlusShell.h, (r4) OmniAddressStar.h,
OmniShotGallery.h. Anchors match \\n or \\r\\n (OmniFeaturesPanel.h has
mixed endings); the new lines use the ending of the text they replace. All anchors are checked before anything is
written.
Tested by tools/test_ui_scale.cpp: g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_ui_scale.cpp -o t && ./t
usage: apply_ui_scale.py <engine tree>   (re-run prints "already")
"""
import hashlib
import re
import sys
from pathlib import Path

MARK = 'OMNI_UI_SCALE_V1'
REV2 = 'OMNI_UI_SCALE_V1_R2'  # r2: stage 2 (notices + the bespoke regions); its edit text stays as written
REV3 = 'OMNI_UI_SCALE_V1_R3'  # r3: stage 3 (the on-screen keyboard, suggestions, hint line, find bar); its edit text stays as written
REV = 'OMNI_UI_SCALE_V1_R4'   # r4: stage 4 (top bar text, hints bar, dialogs, screenshot grid); the headers carry it
ROW_ID = 834
# omniSettingsPanel as OmniUiScalePanels.h's omniUisSettingsPanel copies it (LF, without our guard line)
SETTINGS_SHA = '95e85846262c6381fcf0539e0407a91df2a533de9cdcdf17150e3658a1773c44'  # with OMNI_HIGH_CONTRAST_V1 (theme cards, toggle words)
# omniSuggestDraw as OmniUiScalePanels.h's omniUisSuggestDraw copies it (LF, without our guard line)
SUGGEST_SHA = 'd9e7ca0956159e939bf412dc483a11550072ab6163f0ba70ffdca5095d759aa1'
root = Path(sys.argv[1]) / 'engine' / 'entry'
HERE = Path(__file__).parent

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniBlocker.h"\n',
         '#include "OmniBlocker.h"\n#include "OmniUiScale.h" // OMNI_UI_SCALE_V1: Interface size (pure)\n'),
        ('// A label whose capitals are centred on layout y `cy`; align 0 = starts at x, 1 = centred, 2 = ends.\n',
         '#include "OmniUiScaleShell.h" // OMNI_UI_SCALE_V1: zoomed panels (scaled text / icon bitmaps, settings row)\n'
         '// A label whose capitals are centred on layout y `cy`; align 0 = starts at x, 1 = centred, 2 = ends.\n'),
        ('static int omniLabel(const std::string& value, float x, float cy, int id, SDL_Color color, int align = 0, int maxW = 0, uint8_t alpha = 255)\n'
         '{\n'
         '    if (value.empty() || !omniFaces[id].f || !alpha) return 0;\n',
         'static int omniLabel(const std::string& value, float x, float cy, int id, SDL_Color color, int align = 0, int maxW = 0, uint8_t alpha = 255)\n'
         '{\n'
         '    if (value.empty() || !omniFaces[id].f || !alpha) return 0;\n'
         '    if (omniUisTextZoom != 1.0) return omniUisLabel(value, x, cy, id, color, align, maxW, alpha); // OMNI_UI_SCALE_V1\n'),
        ('    const OmniIconMask& mask = omniIconMask(id);\n'
         '    const int x0 = int(cx * displayScale + 0.5) - mask.w / 2, y0 = int(cy * displayScale + 0.5) - mask.h / 2;\n',
         '    if (omniUisTextZoom != 1.0) { // OMNI_UI_SCALE_V1: zoomed panel: the base-scale mask, scaled\n'
         '        const double ds = displayScale; displayScale = omniUisBaseScale;\n'
         '        const OmniIconMask& m = omniIconMask(id);\n'
         '        displayScale = ds;\n'
         '        const int sw = int(m.w * omniUisTextZoom + 0.5), sh = int(m.h * omniUisTextZoom + 0.5);\n'
         '        omniUisBlitCoverage(m.a.data(), m.w, m.h, m.w, 1, 0, int(cx * displayScale + 0.5) - sw / 2, int(cy * displayScale + 0.5) - sh / 2, 0, color, alpha);\n'
         '        return;\n'
         '    }\n'
         '    const OmniIconMask& mask = omniIconMask(id);\n'
         '    const int x0 = int(cx * displayScale + 0.5) - mask.w / 2, y0 = int(cy * displayScale + 0.5) - mask.h / 2;\n'),
        ('    struct Mask { int key[5] = {}; int ox = 0, oy = 0, w = 0; std::vector<uint8_t> a; std::vector<Run> runs; };',
         '    struct Mask { int key[6] = {}; int ox = 0, oy = 0, w = 0; std::vector<uint8_t> a; std::vector<Run> runs; }; // OMNI_UI_SCALE_V1: + scale'),
        ('    const int key[5] = { w, h, radius, blur, dy };\n',
         '    const int key[6] = { w, h, radius, blur, dy, int(displayScale * 1000 + 0.5) }; // OMNI_UI_SCALE_V1: zoomed panels\n'),
    ],
    'OmniFeaturesPanel.h': [
        ('struct OmniFxGeom { int x, y, w, h, listY, vis, header; };\n',
         'struct OmniFxGeom { int x, y, w, h, listY, vis, header; double zoom = 1.0; /* OMNI_UI_SCALE_V1 */ };\n'),
        ('    OmniFxGeom g {};\n'
         '    const int n = int(p.rows.size());\n'
         '    g.header = p.subtitle.empty() ? 64 : 88;\n',
         '    OmniFxGeom g {};\n'
         '    const int n = int(p.rows.size());\n'
         '    if (const int uisLevel = omniUisLevel(); uisLevel != OUIS::Normal) { // OMNI_UI_SCALE_V1: zoomed, rows per page clamped\n'
         '        const OUIS::PanelFit f = OUIS::fitPanel(uisLevel, p.w, p.rowH, n, p.cols, p.maxVisible, !p.subtitle.empty(), 1.0, p.anchorX, p.anchorY);\n'
         '        g.x = f.x; g.y = f.y; g.w = f.w; g.h = f.h; g.listY = f.listY; g.vis = f.vis; g.header = f.header; g.zoom = f.zoom;\n'
         '        return g;\n'
         '    }\n'
         '    g.header = p.subtitle.empty() ? 64 : 88;\n'),
        ('    omniFxKeepVisible(p, g.vis);\n'
         '    omniRectPx({ 0, 0, canvas->w, canvas->h }, { 0, 0, 0, 255 }, p.anchorX >= 0 ? 70 : 110);\n',
         '    omniFxKeepVisible(p, g.vis);\n'
         '    omniRectPx({ 0, 0, canvas->w, canvas->h }, { 0, 0, 0, 255 }, p.anchorX >= 0 ? 70 : 110);\n'
         '    OmniUisZoomScope uisZoom(g.zoom); // OMNI_UI_SCALE_V1: the panel at displayScale * zoom (restored for the hints)\n'),
        ('    omniPanelHints(p.faces, p.extra.empty() ? nullptr : p.extra.c_str());\n'
         '}\n'
         'static void omniFxDraw()',
         '    uisZoom.restore(); // OMNI_UI_SCALE_V1\n'
         '    omniPanelHints(p.faces, p.extra.empty() ? nullptr : p.extra.c_str());\n'
         '}\n'
         'static void omniFxDraw()'),
        ('        const int page = std::max(1, q.maxVisible - 1), m = int(q.rows.size());\n',
         '        const int page = std::max(1, (omniUisLevel() == OUIS::Normal ? q.maxVisible : std::min(q.maxVisible, omniFxGeometry(q).vis)) - 1), m = int(q.rows.size()); // OMNI_UI_SCALE_V1\n'),
        ('    const int row = omniFxRowAt(p, omniFxGeometry(p), x, y, true);\n',
         '    const OmniFxGeom g = omniFxGeometry(p);\n'
         '    omniUisMap(g.zoom, x, y); // OMNI_UI_SCALE_V1: pointer in the zoomed layout space\n'
         '    const int row = omniFxRowAt(p, g, x, y, true);\n'),
        ('    const OmniFxGeom g = omniFxGeometry(p);\n'
         '    const int row = omniFxRowAt(p, g, x, y, omniPtrCross.inCross);\n',
         '    const OmniFxGeom g = omniFxGeometry(p);\n'
         '    omniUisMap(g.zoom, x, y); // OMNI_UI_SCALE_V1: pointer in the zoomed layout space (rows and stepper arrows)\n'
         '    const int row = omniFxRowAt(p, g, x, y, omniPtrCross.inCross);\n'),
    ],
    'OmniBrowserSettings.h': [
        ('    add(omniFxSetHintBar, "Bottom button bar", omniBarsHidden(false) ? "Hidden" : "Shown", true);\n',
         '    add(omniFxSetHintBar, "Bottom button bar", omniBarsHidden(false) ? "Hidden" : "Shown", true);\n'
         '    add(omniUisRowId, "Interface size", OUIS::nameOf(omniUisLevel()), true); // OMNI_UI_SCALE_V1: Small / Normal / Large / Extra large\n'),
        ('    if (r.id >= 900) return omniF2SettingsInput(r, b); // OMNI_FEATURES_V2\n',
         '    if (r.id == omniUisRowId) return omniUisSettingsInput(b); // OMNI_UI_SCALE_V1 (before the >= 300 / >= 900 rows)\n'
         '    if (r.id >= 900) return omniF2SettingsInput(r, b); // OMNI_FEATURES_V2\n'),
    ],
}

# --- stage 2 (REV2): same per-edit idempotency, applied after the stage-1 edits of the same file -----------------------
R2 = ' // ' + REV2
R3 = ' // ' + REV3
R4 = ' // ' + REV
# the fill bar's locals: r2 put the strip above today's keyboard; r3 above the zoomed one (an r2 tree is upgraded in place)
LOCALS_W_KB_R2 = ('    [[maybe_unused]] const int width = OUIS::zoomedW(uisZ), keyboardY = OUIS::toZoomed(::keyboardY - 58, uisZ) + 58;'
                  ' // ' + REV2 + ' (Normal: 1280, 420)\n')
LOCALS_W_KB = ('    [[maybe_unused]] const int width = OUIS::zoomedW(uisZ), keyboardY = OUIS::toZoomed(omniUisKbTop(), uisZ) + 58;'
               ' // ' + REV3 + ' (Normal: 1280, 420; above the zoomed keyboard)\n')


def fill_draw(locals_line):
    return ('    const OmniTheme& T = omniTheme();\n'
            '    const double uisZ = omniUisZoom();' + R2 + ': the strip zoomed, still just above the keyboard (stage 3)\n'
            '    OmniUisZoomScope uisZoom(uisZ);\n'
            + locals_line +
            '    const int stripY = keyboardY - 58 - 48;\n')


def fill_click(locals_line):
    return ('    if (items.empty()) return false;\n'
            '    const double uisZ = omniUisZoom(); omniUisMap(uisZ, cx, cy);' + R2 + ': the pointer in the zoomed strip\n'
            + locals_line +
            '    const int stripY = keyboardY - 58 - 48;\n')


def hover(flag_line, first_line, box):
    # omniPtrHover: the pointer in the region's Normal coordinates for today's hover test (x, y shadowed in the block)
    return (flag_line + first_line,
            flag_line + '            int x = int(pointerX), y = int(pointerY); omniUisToNormal(' + box + ', x, y);' + R2 + '\n' + first_line)


def error_click(geom, actions):
    old = '    const OmniFxErrorLayout L = %s;\n    if (y >= L.chipY && y < L.chipY + 44) {\n' % geom
    body = ''.join('            if (%szx >= L.chipX[%d] && zx < L.chipX[%d] + L.chipW[%d]) { %s; return true; }\n'
                   % (cond, i, i, i, act) for i, (cond, act) in enumerate(actions))
    new = ('    const OmniFxErrorLayout L = %s;\n' % geom
           + '    if (L.zoom != 1.0) {' + R2 + ': the chips in the zoomed layout space; the dimmed page as before\n'
           '        int zx = x, zy = y;\n'
           '        omniUisMap(L.zoom, zx, zy);\n'
           '        if (zy >= L.chipY && zy < L.chipY + 44) {\n'
           + body +
           '        }\n'
           '        return y >= omniPageTop() && y < omniPageBottom();\n'
           '    }\n'
           '    if (y >= L.chipY && y < L.chipY + 44) {\n')
    return (old, new)


EDITS_R2 = {
    'OmniBrowser.cpp': [
        ('#include "OmniFeatures3.h" // OMNI_FEATURES_V3\n',
         '#include "OmniFeatures3.h" // OMNI_FEATURES_V3\n'
         '#include "OmniUiScalePanels.h"' + R2 + ': toast, History, Browser tools, settings drawn zoomed\n'),
        ('static int omniTextWidthPx(int id, const std::string& value)\n{\n',
         'static double omniUisZoomNow(); static int omniUisDrawnWidth(int id, const std::string& value);' + R2 + ' (OmniUiScaleShell.h)\n'
         'static std::string omniUisFitZoomed(int id, const std::string& value, int maxPx);' + R2 + '\n'
         'static int omniTextWidthPx(int id, const std::string& value)\n{\n'
         '    if (omniUisZoomNow() != 1.0) return omniUisDrawnWidth(id, value);' + R2 + ': drawn px inside a zoomed region\n'),
        ('static std::string omniFit(int id, const std::string& value, int maxPx)\n{\n',
         'static std::string omniFit(int id, const std::string& value, int maxPx)\n{\n'
         '    if (maxPx > 0 && omniUisZoomNow() != 1.0) return omniUisFitZoomed(id, value, maxPx);' + R2 + ': maxPx in drawn px\n'),
        ('    if (a <= 0) return;\n    const std::string shown = omniFit(omniSmall, message, physical(940));\n',
         '    if (a <= 0) return;\n'
         '    if (omniUisLevel() != OUIS::Normal) { omniUisToast(message, error, a); return; }' + R2 + ': the pill zoomed\n'
         '    const std::string shown = omniFit(omniSmall, message, physical(940));\n'),
        ('static void omniSettingsPanel()\n{\n',
         'static void omniSettingsPanel()\n{\n'
         '    if (omniUisLevel() != OUIS::Normal) { omniUisSettingsPanel(); return; }' + R2 + ': drawn zoomed (OmniUiScalePanels.h)\n'),
        ('static void omniSettingsClick(int x, int y)\n{\n',
         'static void omniSettingsClick(int x, int y)\n{\n'
         '    omniUisToNormal(omniUisSettingsBox(), x, y);' + R2 + ': today\'s hit areas, the pointer in Normal coordinates\n'),
        ('static bool omniHistoryButton(int b)\n{\n',
         'static bool omniHistoryButton(int b)\n{\n'
         '    OMNI_UIS_HISTORY_LOCALS;' + R2 + ': L1 / R1 page by the rows shown\n'),
        ('static bool omniHistoryClick(int x, int y)\n{\n    if (editing) return false;   // keyboard keys are clicked as usual\n',
         'static bool omniHistoryClick(int x, int y)\n{\n    if (editing) return false;   // keyboard keys are clicked as usual\n'
         '    omniUisToNormal(omniUisHistoryBox(), x, y);' + R2 + ': today\'s hit areas, the pointer in Normal coordinates\n'),
        ('    const bool typing = omniHpTyping();\n    const int rows = omniHpMode == 1 ? 4 : omniHpVisible();\n',
         '    const bool typing = omniHpTyping();\n'
         '    OMNI_UIS_HISTORY_LOCALS;' + R2 + ': zoomed geometry, rows clamped (Normal: today\'s constants)\n'
         '    const int rows = omniHpMode == 1 ? 4 : omniHpVisible();\n'),
        ('    omniRectPx({ 0, 0, canvas->w, typing ? physical(keyboardY - 58) : canvas->h }, { 0, 0, 0, 255 }, uint8_t(110 * fadeT));\n',
         '    omniRectPx({ 0, 0, canvas->w, typing ? physical(keyboardY - 58) : canvas->h }, { 0, 0, 0, 255 }, uint8_t(110 * fadeT));\n'
         '    OmniUisZoomScope uisZoom(uisHistoryBox.zoom);' + R2 + ' (the hints bar stays today\'s: omniPanelHints)\n'),
        ('static void omniPanelHints(const std::vector<std::pair<int, const char*>>& faces, const char* extra)\n{\n',
         'static void omniPanelHints(const std::vector<std::pair<int, const char*>>& faces, const char* extra)\n{\n'
         '    OmniUisUnzoom uisUnzoom;' + R2 + ': the hints bar at today\'s size inside a zoomed region (stage 4)\n'),
        ('static bool omniMenuClick(int x, int y)\n{\n',
         'static bool omniMenuClick(int x, int y)\n{\n'
         '    omniUisToNormal(omniUisMenuBox(), x, y);' + R2 + ': today\'s hit areas, the pointer in Normal coordinates\n'),
        ('    omniRectPx({ 0, 0, canvas->w, canvas->h }, { 0, 0, 0, 255 }, uint8_t(110 * fadeT));\n'
         '    const int x = omniMenuX(), y = omniMenuY(), h = 96 + omniMenuCount * omniMenuRowH + 18;\n',
         '    omniRectPx({ 0, 0, canvas->w, canvas->h }, { 0, 0, 0, 255 }, uint8_t(110 * fadeT));\n'
         '    const OmniUisBox uisMenu = omniUisMenuBox();' + R2 + ': zoomed, every row (Normal: today\'s position)\n'
         '    OmniUisZoomScope uisZoom(uisMenu.zoom);\n'
         '    const auto omniMenuX = [&] { return uisMenu.zoom != 1.0 ? uisMenu.x : ::omniMenuX(); };\n'
         '    const auto omniMenuY = [&] { return uisMenu.zoom != 1.0 ? uisMenu.y : ::omniMenuY(); };\n'
         '    const int x = omniMenuX(), y = omniMenuY(), h = 96 + omniMenuCount * omniMenuRowH + 18;\n'),
        ('static bool omniSettingsToolsClick(int x, int y)\n{\n',
         'static bool omniSettingsToolsClick(int x, int y)\n{\n'
         '    omniUisToNormal(omniUisSettingsBox(), x, y);' + R2 + '\n'),
        ('static void omniSettingsToolsDraw()\n{\n    const OmniTheme& T = omniTheme();\n',
         'static void omniSettingsToolsDraw()\n{\n    const OmniTheme& T = omniTheme();\n'
         '    const OmniUisBox uisBox = omniUisSettingsBox();' + R2 + ': on the zoomed settings panel\'s header row\n'
         '    OmniUisZoomScope uisZoom(uisBox.zoom, true);\n'
         '    const int omniToolsX = ::omniToolsX + uisBox.x - uisBox.nx, omniToolsY = ::omniToolsY + uisBox.y - uisBox.ny;\n'),
        hover('        if (omniHistoryOpenFlag) {\n', '            const int row = omniHistoryRowAt(x, y);\n', 'omniUisHistoryBox()'),
        hover('        if (omniMenuOpenFlag) {\n', '            const int listY = omniMenuY() + 96;\n', 'omniUisMenuBox()'),
        hover('        if (settingsOpen) {\n', '            const int row = omniPtrSettingsRowAt(x, y);\n', 'omniUisSettingsBox()'),
    ],
    'OmniFeatures2.h': [
        # r3 upgrade of an r2 tree (optional: a fresh tree has no r2 line; the edits below then write the r3 one)
        (fill_draw(LOCALS_W_KB_R2), fill_draw(LOCALS_W_KB), 'upgrade'),
        (fill_click(LOCALS_W_KB_R2), fill_click(LOCALS_W_KB), 'upgrade'),
        ('    const OmniTheme& T = omniTheme();\n    const int stripY = keyboardY - 58 - 48;\n', fill_draw(LOCALS_W_KB)),
        ('    if (items.empty()) return false;\n    const int stripY = keyboardY - 58 - 48;\n', fill_click(LOCALS_W_KB)),
    ],
    'OmniErrorPage.h': [
        ('struct OmniFxErrorLayout { int x, y, w, h, chipY; int chipX[3], chipW[3]; int chips; };',
         'struct OmniFxErrorLayout { int x, y, w, h, chipY; int chipX[3], chipW[3]; int chips; double zoom = 1.0; /* ' + REV2 + ' */ };'),
        ('    OmniFxErrorLayout L {};\n    const int py0 = omniPageTop(), py1 = omniPageBottom();\n',
         '    OmniFxErrorLayout L {};\n'
         '    if (omniUisLevel() != OUIS::Normal) {' + R2 + ': the same panel in the zoomed layout space, centred on the page\n'
         '        const OUIS::BoxFit f = OUIS::fitBox(omniUisLevel(), 700, 264, 0, 0, omniPageTop(), omniPageBottom());\n'
         '        L.zoom = f.zoom; L.w = 700; L.h = 264; L.x = f.x; L.y = f.y; L.chipY = L.y + L.h - 68; L.chips = 3;\n'
         '        int zx = L.x + 40;\n'
         '        const int zw[3] = { 170, 170, 220 };\n'
         '        for (int i = 0; i < 3; ++i) { L.chipX[i] = zx; L.chipW[i] = zw[i]; zx += zw[i] + 14; }\n'
         '        return L;\n'
         '    }\n'
         '    const int py0 = omniPageTop(), py1 = omniPageBottom();\n'),
        ('    const OmniFxErrorLayout L = omniFxErrorGeom();\n    omniShadow(',
         '    const OmniFxErrorLayout L = omniFxErrorGeom();\n'
         '    OmniUisZoomScope uisZoom(L.zoom, true);' + R2 + ': the panel zoomed (chip hover: the zoomed pointer)\n'
         '    omniShadow('),
        error_click('omniFxErrorGeom()', [('', 'omniFxErrorRetry()'), ('', 'omniFxErrorBack()'), ('omniFxErrorBlocked() && ', 'omniFxErrorAllow()')]),
    ],
    'OmniHttpsOnlyShell.h': [
        ('    const OmniFxErrorLayout L = omniHoErrorGeom();\n    omniShadow(',
         '    const OmniFxErrorLayout L = omniHoErrorGeom();\n'
         '    OmniUisZoomScope uisZoom(L.zoom, true);' + R2 + ': the interstitial zoomed like the error panel\n'
         '    omniShadow('),
        error_click('omniHoErrorGeom()', [('', 'omniHoGoBack()'), ('', 'omniHoContinue()')]),
    ],
    'OmniQrShareShell.h': [
        ('struct OmniQrGeom { int x, y, w, h, qr; };',
         'struct OmniQrGeom { int x, y, w, h, qr; double zoom = 1.0; /* ' + REV2 + ' */ };'),
        ('    OmniQrGeom g {};\n    g.qr = int(sq.side / displayScale + 0.999);\n',
         '    OmniQrGeom g {};\n'
         '    if (const int uisLevel = omniUisLevel(); uisLevel != OUIS::Normal) {' + R2 + ': text and margins zoomed, the code keeps its pixels\n'
         '        const int qrLayout = int(sq.side / displayScale + 0.999), below = omniQr.trimmed ? 88 : 64;\n'
         '        const OUIS::BoxFit f = OUIS::fitBox(uisLevel, 620, 64 + below, 0, 0, 0, height - bottom, 8, qrLayout);\n'
         '        g.zoom = f.zoom;\n'
         '        g.qr = int(sq.side / (displayScale * f.zoom) + 0.999);\n'
         '        g.w = std::max(g.qr + 64, 620);\n'
         '        g.h = 64 + g.qr + below;\n'
         '        g.x = (OUIS::zoomedW(f.zoom) - g.w) / 2;\n'
         '        g.y = f.y;\n'
         '        return g;\n'
         '    }\n'
         '    g.qr = int(sq.side / displayScale + 0.999);\n'),
        ('    omniRectPx({ 0, 0, canvas->w, canvas->h }, { 0, 0, 0, 255 }, 150);\n    omniShadow(g.x, g.y, g.w, g.h,',
         '    omniRectPx({ 0, 0, canvas->w, canvas->h }, { 0, 0, 0, 255 }, 150);\n'
         '    OmniUisZoomScope uisZoom(g.zoom);' + R2 + ' (the modules stay physical pixels; the hints bar: today\'s)\n'
         '    omniShadow(g.x, g.y, g.w, g.h,'),
        ('    const OmniQrGeom g = omniQrGeometry(OQR::square(omniQr.code.size, canvas->h));\n',
         '    const OmniQrGeom g = omniQrGeometry(OQR::square(omniQr.code.size, canvas->h));\n'
         '    omniUisMap(g.zoom, x, y);' + R2 + '\n'),
    ],
    'OmniShotGalleryShell.h': [
        ('    omniRectPx({ 0, 0, canvas->w, physical(40) }, { 0, 0, 0, 255 }, 150);\n',
         '    const double uisZ = omniUisZoom();' + R2 + ': the caption strip zoomed (the shot itself fills the screen)\n'
         '    OmniUisZoomScope uisZoom(uisZ);\n'
         '    [[maybe_unused]] const int width = OUIS::zoomedW(uisZ);\n'
         '    omniRectPx({ 0, 0, canvas->w, physical(40) }, { 0, 0, 0, 255 }, 150);\n'),
    ],
}
for _name, _edits in EDITS_R2.items():
    EDITS.setdefault(_name, []).extend(_edits)

# --- stage 3 (REV3): the on-screen keyboard, the suggestions above it, its hint line, the find bar ---------------------
KB_LOCALS = '    OMNI_UIS_KB_LOCALS;' + R3
EDITS_R3 = {
    'OmniBrowser.cpp': [
        ('constexpr int keyboardWidth = 10 * keyWidth, actionY = keyboardY + 5 * keyHeight;\n',
         'constexpr int keyboardWidth = 10 * keyWidth, actionY = keyboardY + 5 * keyHeight;\n'
         'static OmniUiScale::KbFit omniUisKb(); static int omniUisKbTop();' + R3 + ': the keyboard at the Interface size (OmniUiScalePanels.h); Normal: the constants above\n'
         '#define OMNI_UIS_KB_LOCALS const OmniUiScale::KbFit uisKb = omniUisKb(); [[maybe_unused]] const int keyboardX = uisKb.x, '
         'keyboardY = uisKb.y, keyHeight = uisKb.pitch, actionY = keyboardY + 5 * keyHeight' + R3 + ' (Normal: 200, 420, 40, 620)\n'),
        ('        const float view = renderPageHeight / float(displayScale);\n',
         '        const float view = renderPageHeight / float(displayScale);\n'
         '        const int keyboardY = omniUisKbTop() + 58;' + R3 + ': the field goes above the zoomed keyboard (Normal: 420)\n'),
        ('static void omniKblGeometry(int& x, int& y, int& cw, int& ch)\n{\n',
         'static void omniKblGeometry(int& x, int& y, int& cw, int& ch)\n{\n'
         + KB_LOCALS + ': over the zoomed keys (omniKblClick gets the zoomed pointer)\n'),
        ('static void omniKbClick(int x, int y)\n{\n    omniKbEnsure();\n',
         'static void omniKbClick(int x, int y)\n{\n    omniKbEnsure();\n'
         + KB_LOCALS + ': the pointer in the zoomed keyboard: popup, chips and keys hit where they are drawn\n'
         '    if (uisKb.zoom != 1.0) { x = OmniUiScale::toZoomed(x, uisKb.zoom); y = OmniUiScale::toZoomed(y, uisKb.zoom); }\n'),
        ('    if (!omniFaces[font].f || w <= 0) return;\n    const int room = physical(w), margin = physical(20);\n',
         '    if (!omniFaces[font].f || w <= 0) return;\n'
         '    if (omniUisTextZoom != 1.0) w = std::max(1, int(w / omniUisTextZoom + 0.5));' + R3 + ': zoomed keyboard: laid out in face px (room = w at the base scale)\n'
         '    const int room = physical(w), margin = physical(20);\n'),
        ('    const int px = physical(x), half = font == omniBody ? 13 : 11;\n',
         '    if (omniUisTextZoom != 1.0) { omniUisKbTextDraw(v, x, cy, room, font, ink, accent, s1 > s0); return; }' + R3 + ': drawn scaled\n'
         '    const int px = physical(x), half = font == omniBody ? 13 : 11;\n'),
        ('static void omniKbHints()\n{\n    omniKbEnsure();\n    const OmniTheme& T = omniTheme();\n    const int y = height - 16;\n',
         'static void omniKbHints()\n{\n'
         '    if (omniUisKbHints()) return;' + R3 + ': drawn zoomed (omniUisKbHints draws this line again inside its zoom)\n'
         '    omniKbEnsure();\n    const OmniTheme& T = omniTheme();\n'
         '    const int y = omniUisTextZoom != 1.0 ? OUIS::toZoomed(height - 16, omniUisTextZoom) : height - 16;' + R3 + ': the bar\'s centre line\n'),
        ('static int omniKwDraw(int fy, int fh)\n{\n',
         'static int omniKwDraw(int fy, int fh)\n{\n'
         + KB_LOCALS + ': the chips in the zoomed preview row (omniKwClick gets the zoomed pointer)\n'),
        ('static void omniDrawKeyboard()\n{\n    omniKbEnsure();\n    const OmniTheme& T = omniTheme();\n',
         'static void omniDrawKeyboard()\n{\n    omniKbEnsure();\n    const OmniTheme& T = omniTheme();\n'
         + KB_LOCALS + ': zoomed, rows clamped (OmniUiScale::fitKeyboard); Normal: today\'s constants\n'
         '    OmniUisZoomScope uisZoom(uisKb.zoom);\n'),
        ('static bool omniSuggestClick(int x, int y)\n{\n',
         'static bool omniSuggestClick(int x, int y)\n{\n'
         '    if (omniUisLevel() != OUIS::Normal) return omniUisSuggestClick(x, y);' + R3 + '\n'),
        ('static void omniSuggestDraw()\n{\n',
         'static void omniSuggestDraw()\n{\n'
         '    if (omniUisLevel() != OUIS::Normal) { omniUisSuggestDraw(); return; }' + R3 + ': zoomed, above the zoomed keyboard (OmniUiScalePanels.h)\n'),
        ('static bool omniFindClick(int x, int y)\n{\n',
         '// The find bar at a level (OMNI_EVERYDAY_V1: 584 x 50, right edge 1260, 10 px under the page top):' + R3 + '\n'
         '// zoomed by the level\'s scale with its right edge and top kept; omniFindDraw draws it with local omniFindX /\n'
         '// omniFindY, omniFindClick maps the pointer to today\'s coordinates.\n'
         'static OmniUisBox omniUisFindBox()\n{\n'
         '    OmniUisBox b;\n'
         '    if (omniUisLevel() == OUIS::Normal) return b;\n'
         '    b.zoom = OUIS::scaleOf(omniUisLevel());\n'
         '    b.nx = omniFindX; b.ny = omniFindY(); b.w = omniFindW; b.h = omniFindH;\n'
         '    b.x = OUIS::zoomedLeft(omniFindX + omniFindW, omniFindW, b.zoom);\n'
         '    b.y = OUIS::zoomedTop(b.ny, b.zoom);\n'
         '    return b;\n'
         '}\n'
         'static bool omniFindClick(int x, int y)\n{\n'
         '    omniUisToNormal(omniUisFindBox(), x, y);' + R3 + ': today\'s hit areas, the pointer in Normal coordinates\n', 'findbar'),
        ('static void omniFindDraw()\n{\n    const OmniTheme& T = omniTheme();\n',
         'static void omniFindDraw()\n{\n    const OmniTheme& T = omniTheme();\n'
         '    const OmniUisBox uisFind = omniUisFindBox();' + R3 + ': zoomed, right edge and top kept (Normal: today\'s position)\n'
         '    OmniUisZoomScope uisZoom(uisFind.zoom);\n'
         '    const int omniFindX = uisFind.zoom != 1.0 ? uisFind.x : ::omniFindX;\n'
         '    const auto omniFindY = [&] { return uisFind.zoom != 1.0 ? uisFind.y : ::omniFindY(); };\n', 'findbar'),
    ],
    # the OMNI_FIND_PLUS_V1 find bar (apply_find_plus.py: 644 x 50 at OFND::kBarX 616, the same right edge and top)
    'OmniFindPlusShell.h': [
        ('static int omniFindY() { return std::max(8, omniPageTop() + 10); }\nstatic bool omniFindClick(int x, int y)\n{\n',
         'static int omniFindY() { return std::max(8, omniPageTop() + 10); }\n'
         '// The find bar at a level:' + R3 + ': zoomed by the level\'s scale with its right edge (1260) and top kept;\n'
         '// omniFindDraw draws it there, omniFindClick maps the pointer to today\'s coordinates (OFND::hit unchanged).\n'
         'static OmniUisBox omniUisFindBox()\n{\n'
         '    OmniUisBox b;\n'
         '    if (omniUisLevel() == OUIS::Normal) return b;\n'
         '    b.zoom = OUIS::scaleOf(omniUisLevel());\n'
         '    b.nx = OFND::kBarX; b.ny = omniFindY(); b.w = OFND::kBarW; b.h = OFND::kBarH;\n'
         '    b.x = OUIS::zoomedLeft(OFND::kBarX + OFND::kBarW, OFND::kBarW, b.zoom);\n'
         '    b.y = OUIS::zoomedTop(b.ny, b.zoom);\n'
         '    return b;\n'
         '}\n'
         'static bool omniFindClick(int x, int y)\n{\n'
         '    omniUisToNormal(omniUisFindBox(), x, y);' + R3 + ': today\'s hit areas, the pointer in Normal coordinates\n', 'findplus'),
        ('    const OmniTheme& T = omniTheme();\n    const int x = OFND::kBarX, y = omniFindY(), w = OFND::kBarW, h = OFND::kBarH;\n',
         '    const OmniTheme& T = omniTheme();\n'
         '    const OmniUisBox uisFind = omniUisFindBox();' + R3 + ': zoomed, right edge and top kept (Normal: today\'s position)\n'
         '    OmniUisZoomScope uisZoom(uisFind.zoom);\n'
         '    const int x = uisFind.zoom != 1.0 ? uisFind.x : OFND::kBarX, y = uisFind.zoom != 1.0 ? uisFind.y : omniFindY(), w = OFND::kBarW, h = OFND::kBarH;\n',
         'findplus'),
    ],
}
for _name, _edits in EDITS_R3.items():
    EDITS.setdefault(_name, []).extend(_edits)

# --- stage 4 (REV = R4): top bar text (text-only zoom), hints bar, dialogs, screenshot grid ---------------------------
HINT_CY = 'height - bottom / 2'
HINT_CY_R4 = 'omniUisTextZoom != 1.0 ? omniUisZoomedY(height - bottom / 2) : height - bottom / 2'
PAGER_R3 = (
    'struct Pager {\n'
    '    int count = 0, sel = 0;\n'
    '    int page() const { return count > 0 ? sel / kPerPage : 0; }\n'
    '    int pages() const { return count > 0 ? (count + kPerPage - 1) / kPerPage : 1; }\n'
    '    int first() const { return page() * kPerPage; }\n'
    '    int onPage() const { return count > 0 ? std::min(kPerPage, count - first()) : 0; }\n'
    '    void clamp() { sel = count > 0 ? std::clamp(sel, 0, count - 1) : 0; }\n'
    '    // D-pad: left / right one shot (across pages), up / down one grid row; down onto a shorter last row lands on the\n'
    '    // last shot. True when the selection moved.\n'
    '    bool move(int dx, int dy)\n'
    '    {\n'
    '        const int was = sel;\n'
    '        if (count <= 0) return false;\n'
    '        if (dx > 0 && sel + 1 < count) ++sel;\n'
    '        else if (dx < 0 && sel > 0) --sel;\n'
    '        else if (dy > 0) {\n'
    '            if (sel + kCols < count) sel += kCols;\n'
    '            else if ((count - 1) / kCols > sel / kCols) sel = count - 1;\n'
    '        } else if (dy < 0 && sel >= kCols) sel -= kCols;\n'
    '        return sel != was;\n'
    '    }\n'
    '    // L1 / R1: the same place on the previous / next page (the last shot when the next page is shorter).\n'
    '    bool pageBy(int d)\n'
    '    {\n'
    '        const int p = std::clamp(page() + d, 0, pages() - 1);\n'
    '        if (p == page() || count <= 0) return false;\n'
    '        sel = std::min(count - 1, sel + (p - page()) * kPerPage);\n'
    '        return true;\n'
    '    }\n'
    '    bool onCurrentPage(int index) const { return index >= first() && index < first() + onPage(); }\n'
    '};\n')
PAGER_R4 = (
    'struct Pager {\n'
    '    int count = 0, sel = 0;\n'
    '    int cols = kCols, rows = kRows;' + R4 + ': the grid shown (fewer at a larger Interface size; the shell sets it)\n'
    '    int per() const { return std::max(1, cols) * std::max(1, rows); }\n'
    '    int page() const { return count > 0 ? sel / per() : 0; }\n'
    '    int pages() const { return count > 0 ? (count + per() - 1) / per() : 1; }\n'
    '    int first() const { return page() * per(); }\n'
    '    int onPage() const { return count > 0 ? std::min(per(), count - first()) : 0; }\n'
    '    void clamp() { sel = count > 0 ? std::clamp(sel, 0, count - 1) : 0; }\n'
    '    // D-pad: left / right one shot (across pages), up / down one grid row; down onto a shorter last row lands on the\n'
    '    // last shot. True when the selection moved.\n'
    '    bool move(int dx, int dy)\n'
    '    {\n'
    '        const int was = sel, c = std::max(1, cols);\n'
    '        if (count <= 0) return false;\n'
    '        if (dx > 0 && sel + 1 < count) ++sel;\n'
    '        else if (dx < 0 && sel > 0) --sel;\n'
    '        else if (dy > 0) {\n'
    '            if (sel + c < count) sel += c;\n'
    '            else if ((count - 1) / c > sel / c) sel = count - 1;\n'
    '        } else if (dy < 0 && sel >= c) sel -= c;\n'
    '        return sel != was;\n'
    '    }\n'
    '    // L1 / R1: the same place on the previous / next page (the last shot when the next page is shorter).\n'
    '    bool pageBy(int d)\n'
    '    {\n'
    '        const int p = std::clamp(page() + d, 0, pages() - 1);\n'
    '        if (p == page() || count <= 0) return false;\n'
    '        sel = std::min(count - 1, sel + (p - page()) * per());\n'
    '        return true;\n'
    '    }\n'
    '    bool onCurrentPage(int index) const { return index >= first() && index < first() + onPage(); }\n'
    '};\n')
EDITS_R4 = {
    'OmniBrowser.cpp': [
        # hints bar: every omniHints line zoomed by omniUisHints (the bar keeps its 32 px)
        ('    const int cy = ' + HINT_CY + ';\n    const bool ps = playStationIcons;\n',
         '    const int cy = ' + HINT_CY_R4 + ';' + R4 + ': the bar\'s centre line in a zoomed hint line\n'
         '    const bool ps = playStationIcons;\n'),
        ('static void omniHints(const std::vector<OmniHint>& left, const std::vector<OmniHint>& right = {}, const std::string& note = "")\n'
         '{\n    const OmniTheme& T = omniTheme();\n    int x = 20;\n',
         'static void omniHints(const std::vector<OmniHint>& left, const std::vector<OmniHint>& right = {}, const std::string& note = "")\n'
         '{\n'
         '    if (omniUisHints(left, right, note)) return;' + R4 + ': drawn zoomed (omniUisHints draws this line again inside its zoom)\n'
         '    const OmniTheme& T = omniTheme();\n'
         '    [[maybe_unused]] const int width = omniUisTextZoom != 1.0 && !omniUisTextOnly ? OUIS::zoomedW(omniUisTextZoom) : ::width;' + R4 + ' (Normal: 1280)\n'
         '    int x = 20;\n'),
        ('    if (!note.empty() && room > 60) omniLabel(note, float(x), float(' + HINT_CY + '), omniSmall, T.inkDim, 0, room);\n',
         '    if (!note.empty() && room > 60) omniLabel(note, float(x), float(' + HINT_CY_R4 + '), omniSmall, T.inkDim, 0, room);' + R4 + '\n'),
        # top bar: text and icons at the level, everything else (height, boxes, hit areas, the page area) today's
        ('    omniHudIdentity(); // OMNI_HUD_ASTRA_V1: the user\'s icon + "OMNI" (was "O" in the accent colour + "MNI")\n',
         '    omniHudIdentity(); // OMNI_HUD_ASTRA_V1: the user\'s icon + "OMNI" (was "O" in the accent colour + "MNI")\n'
         '    OmniUisTextScope uisBar(omniUisBarZoom());' + R4 + ': text / icons at the Interface size; height, boxes, hit areas today\'s\n'),
        ('        if (!usable) omniLabel("Protection", 1153, 82, omniCaption, T.inkFaint, 1, 88);\n',
         '        OmniUisTextCap uisCap(usable ? omniCaptionBold : omniCaption, !usable ? "Protection" : trusted ? "Allowed" : "Protected", usable ? 78 : 88);'
         + R4 + ': the word fits the 98 px pill\n'
         '        if (!usable) omniLabel("Protection", 1153, 82, omniCaption, T.inkFaint, 1, 88);\n'),
        # dialogs
        ('    int lineHeight = 30, visibleLines = 0, rowHeight = 40, visibleRows = 0;\n    bool compact = false;\n};\n',
         '    int lineHeight = 30, visibleLines = 0, rowHeight = 40, visibleRows = 0;\n    bool compact = false;\n'
         '    double zoom = 1.0;' + R4 + ': drawn and hit at this zoom (omniUisModalLayout)\n};\n'),
        ('static OmniModalLayout omniModalLayout(OmniModal& m)\n{\n    OmniModalLayout L;\n',
         'static OmniModalLayout omniModalLayout(OmniModal& m)\n{\n'
         '    if (!omniUisModalBusy && omniUisLevel() != OUIS::Normal) return omniUisModalLayout(m);' + R4 + ': zoomed (OmniUiScalePanels.h)\n'
         '    OmniModalLayout L;\n'),
        ('        L.visibleRows = std::min<int>(int(m.rows.size()), 11);\n',
         '        L.visibleRows = std::min<int>(int(m.rows.size()), std::min(11, omniUisModalCap));' + R4 + ': fewer when zoomed\n'),
        ('        L.visibleLines = std::min<int>(int(m.lines.size()), maxLines);\n',
         '        L.visibleLines = std::min<int>(int(m.lines.size()), std::min(maxLines, omniUisModalCap));' + R4 + ': fewer when zoomed\n'),
        ('    if (!L.compact) omniRectPx({ 0, 0, canvas->w, canvas->h }, { 0, 0, 0, 255 }, uint8_t(120 * fadeT));   // dim what is behind (not the keyboard)\n',
         '    if (!L.compact) omniRectPx({ 0, 0, canvas->w, canvas->h }, { 0, 0, 0, 255 }, uint8_t(120 * fadeT));   // dim what is behind (not the keyboard)\n'
         '    OmniUisZoomScope uisZoom(L.zoom, true);' + R4 + ': the dialog zoomed (hover tests: the zoomed pointer)\n'),
        ('static int omniModalHit(OmniModal& m, int x, int y)\n{\n    OmniModalLayout L = omniModalLayout(m);\n',
         'static int omniModalHit(OmniModal& m, int x, int y)\n{\n    OmniModalLayout L = omniModalLayout(m);\n'
         '    omniUisMap(L.zoom, x, y);' + R4 + ': the pointer in the dialog\'s zoomed space (Cross, clicks)\n'),
    ],
    'OmniAddressStar.h': [
        ('    omniStarPaint(omniStarCX, omniStarCY, on, on ? T.accent : T.inkDim);\n',
         '    if (omniUisTextOnly) {' + R4 + ': the star at the top bar\'s text zoom, same centre\n'
         '        const double ds = displayScale, z = omniUisTextZoom;\n'
         '        displayScale = ds * z;\n'
         '        omniStarPaint(float(omniStarCX / z), float(omniStarCY / z), on, on ? T.accent : T.inkDim);\n'
         '        displayScale = ds;\n'
         '        return;\n'
         '    }\n'
         '    omniStarPaint(omniStarCX, omniStarCY, on, on ? T.accent : T.inkDim);\n'),
    ],
    'OmniShotGallery.h': [
        (PAGER_R3, PAGER_R4),
    ],
    'OmniShotGalleryShell.h': [
        ('struct OmniSsGeom { int x, y, w, h, listY, tw, th, gap; };',
         'struct OmniSsGeom { int x, y, w, h, listY, tw, th, gap; double zoom = 1.0; int cols = OSG::kCols; /* ' + REV + ' */ };'),
        ('static OmniSsGeom omniSsGeometry()\n{\n    OmniSsGeom g {};\n',
         'static OmniSsGeom omniSsGeometry()\n{\n'
         '    if (omniUisLevel() != OUIS::Normal) return omniUisSsGeometry();' + R4 + ': fewer, larger tiles (OmniUiScalePanels.h)\n'
         '    OmniSsGeom g {};\n'),
        ('    tx = g.x + 12 + (k % OSG::kCols) * (g.tw + g.gap);\n    ty = g.listY + (k / OSG::kCols) * (g.th + g.gap);\n',
         '    tx = g.x + 12 + (k % g.cols) * (g.tw + g.gap);' + R4 + ' (Normal: g.cols = OSG::kCols)\n'
         '    ty = g.listY + (k / g.cols) * (g.th + g.gap);\n'),
        ('    const OmniSsGeom g = omniSsGeometry();\n    omniShadow(g.x, g.y, g.w, g.h, omniRadius + 2, 22, 160, 6);\n',
         '    const OmniSsGeom g = omniSsGeometry();\n'
         '    OmniUisZoomScope uisZoom(g.zoom);' + R4 + ': the grid zoomed (its hints bar: omniPanelHints)\n'
         '    omniShadow(g.x, g.y, g.w, g.h, omniRadius + 2, 22, 160, 6);\n'),
        ('        if (it != omniSsThumbs.end()) { omniSsBudget.touch(s.name); omniSsBlit(it->second, box.x, box.y, box.w, box.h); }\n',
         '        if (it != omniSsThumbs.end()) { omniSsBudget.touch(s.name); (g.zoom != 1.0 ? omniSsBlitFit : omniSsBlit)(it->second, box.x, box.y, box.w, box.h); }'
         + R4 + ': Normal-size thumbnails scaled\n'),
        ('static bool omniSsClick(int x, int y)\n{\n    if (omniSsView >= 0) return true;\n    const OmniSsGeom g = omniSsGeometry();\n',
         'static bool omniSsClick(int x, int y)\n{\n    if (omniSsView >= 0) return true;\n    const OmniSsGeom g = omniSsGeometry();\n'
         '    omniUisMap(g.zoom, x, y);' + R4 + ': the pointer in the grid\'s zoomed space\n'),
        ('static bool omniSsButton(int b)\n{\n',
         'static bool omniSsButton(int b)\n{\n'
         '    if (omniUisLevel() != OUIS::Normal) omniUisSsGrid();' + R4 + ': the pager\'s grid before the D-pad moves in it\n'),
        ('static bool omniSsScroll(double amount)\n{\n',
         'static bool omniSsScroll(double amount)\n{\n'
         '    if (omniUisLevel() != OUIS::Normal) omniUisSsGrid();' + R4 + '\n'),
    ],
}
for _name, _edits in EDITS_R4.items():
    EDITS.setdefault(_name, []).extend(_edits)


def pattern(text):
    return re.compile(''.join(r'\r?\n' if c == '\n' else re.escape(c) for c in text))


def file_nl(raw):
    return '\r\n' if raw.count('\r\n') * 2 > raw.count('\n') else '\n'


def write_new(name, src, like, rev=False):
    raw = (root / like).read_bytes().decode('utf-8')
    nl = file_nl(raw)
    text = (HERE / src).read_text(encoding='utf-8')
    if MARK not in text or (rev and REV not in text):
        sys.exit('%s: %s missing' % (src, REV if rev else MARK))
    data = text.replace('\r\n', '\n').replace('\n', nl).encode('utf-8')
    h = root / name
    if h.exists() and h.read_bytes() == data:
        return name + ': already'
    h.write_bytes(data)
    return name + ': written'


# The Controls guide's table names other patches' handlers by design: never a name clash (numbers still count there).
GUIDE = ('OmniControlsHelp.h', 'OmniControlsHelpShell.h')
_CPP_TOK = re.compile(r'//[^\n]*|/\*.*?\*/|R"([^()\\\s"]{0,16})\(.*?\)\1"|"(?:\\.|[^"\\\n])*"' + r"|'(?:\\.|[^'\\\n])*'", re.S)


def cpp_code(s):
    """C/C++ text without its // and /* */ comments (string, char and raw string literals kept; newlines kept, so line
    numbers stay): an id or name in another patch's notes (e.g. "834-839" in a generated header) is not a use."""
    return _CPP_TOK.sub(lambda m: m.group(0) if m.group(0)[0] in 'R"\'' else '\n' * m.group(0).count('\n'), s)


def check_row_id():
    # the settings row id must be ours alone (every Browser settings row id, incl. other patches' rows)
    rx = re.compile(r'\b%d\b' % ROW_ID)
    for f in sorted(root.iterdir()):
        if f.suffix not in ('.h', '.cpp', '.inc') or f.name in ('OmniUiScaleShell.h',):
            continue
        t = f.read_text(encoding='utf-8', errors='replace')
        for i, (line, code) in enumerate(zip(t.split('\n'), cpp_code(t).split('\n')), 1):
            if rx.search(code) and MARK not in line:
                sys.exit('row id %d already used: %s:%d: %s' % (ROW_ID, f.name, i, line.strip()[:120]))


def body_sha(text, head):
    # sha256 of a function (LF), without our guard lines (any revision)
    t = text.replace('\r\n', '\n')
    i = t.find(head)
    if i < 0:
        return None
    body = t[i:t.index('\n}\n', i) + 3]
    body = ''.join(line for line in body.splitlines(True) if MARK + '_R' not in line)
    return hashlib.sha256(body.encode('utf-8')).hexdigest()


def check_copies(text):
    # omniUisSettingsPanel / omniUisSuggestDraw (OmniUiScalePanels.h) are copies of omniSettingsPanel / omniSuggestDraw:
    # refuse a tree where the original changed
    for head, want, copy, const in (('static void omniSettingsPanel()\n{\n', SETTINGS_SHA, 'omniUisSettingsPanel', 'SETTINGS_SHA'),
                                    ('static void omniSuggestDraw()\n{\n', SUGGEST_SHA, 'omniUisSuggestDraw', 'SUGGEST_SHA')):
        sha = body_sha(text, head)
        if sha is not None and copy + '(); return; }' in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8'):   # OMNI_RERUN_SAFE_COPIES: already hooked (checked at first apply)
            continue
        if sha is None:
            sys.exit('OmniBrowser.cpp: %s not found' % head.split('(')[0])
        if sha != want:
            sys.exit('OmniBrowser.cpp: %s changed (sha256 %s, copy made from %s): update %s in OmniUiScalePanels.h and %s'
                     % (head.split('(')[0], sha, want, copy, const))


def main():
    check_row_id()
    planned, msgs = {}, []
    find_plus = 'OMNI_FIND_PLUS_V1' in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8')
    for name, edits in EDITS.items():
        if name == 'OmniFindPlusShell.h' and not find_plus:
            continue   # no OMNI_FIND_PLUS_V1: the find bar is OMNI_EVERYDAY_V1's (OmniBrowser.cpp)
        raw = (root / name).read_bytes().decode('utf-8')
        text, done = raw, 0
        for old, new, *tag in edits:
            if pattern(new).search(text):
                done += 1
                continue
            if tag == ['findbar'] and find_plus:
                done += 1   # OMNI_FIND_PLUS_V1 replaced that find bar (its own edits: OmniFindPlusShell.h)
                continue
            hits = pattern(old).findall(text)
            rev = re.search(r'OMNI_UI_SCALE_V1(?:_R\d)?', new)   # OMNI_RERUN_SAFE_REV: this revision's edits are in the file (written together); a later patch may rewrite our lines
            if rev and re.search(re.escape(rev.group(0)) + r'(?!_R\d)', raw):
                done += 1
                continue
            if tag == ['upgrade'] and not hits:
                done += 1   # nothing of that revision to upgrade (a fresh tree)
                continue
            if len(hits) != 1:
                sys.exit('%s: anchor found %d times: %r' % (name, len(hits), old[:90]))
            nl = '\r\n' if '\r\n' in hits[0] else ('\n' if '\n' in hits[0] else file_nl(raw))
            repl = new.replace('\n', nl)
            text = pattern(old).sub(lambda _m: repl, text, count=1)
        if text != raw:
            planned[name] = text
        msgs.append('%s: %s' % (name, 'already' if text == raw else 'applied (%d/%d already)' % (done, len(edits))))
    check_copies(planned.get('OmniBrowser.cpp') or (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8'))
    msgs.insert(0, write_new('OmniUiScale.h', 'OmniUiScale.h', 'OmniFeaturesPanel.h', True))
    msgs.insert(1, write_new('OmniUiScaleShell.h', 'OmniUiScaleShell.h', 'OmniFeaturesPanel.h', True))
    msgs.insert(2, write_new('OmniUiScalePanels.h', 'OmniUiScalePanels.h', 'OmniFeaturesPanel.h', True))
    for name, text in planned.items():
        (root / name).write_bytes(text.encode('utf-8'))
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK
          + ' (r4: stage 1 panels + setting, stage 2 notices + bespoke regions, stage 3 keyboard + suggestions + find bar,'
          ' stage 4 top bar text + hints bar + dialogs + screenshot grid)')


main()
