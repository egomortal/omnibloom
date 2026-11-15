"""OMNI_BARS_HIDE_V1 (2026-11-13, owner request): separate hide toggles for the quick-access row and the bottom
button bar (Browser settings > "Quick access row" / "Bottom button bar": Shown or Hidden, /data/omni/ui-bars.txt).

How: Omni already has a full-height page layout (used while Auto-hide is on): the page view has the whole display
height and the bars are drawn over it, so they never resize the view. Hiding a row switches to that layout and shrinks
the bar it belongs to, so the page gets the space:
  quick-access row  the top bar ends at y 112 instead of 164 (the row is neither drawn nor clickable)
  bottom button bar the hint bar has no height while browsing; it still shows while you type or are in Settings
Sliding (Auto-hide) still works on what's left. Self-tests keep the fixed layout (omniAutoHideAllowed is false there).

Apply AFTER apply_dark_qa.py (anchors on its Settings rows).
usage: apply_bars_hide.py <engine tree>   (edits OmniBrowser.cpp, OmniMqQuickAccess.h, OmniBrowserSettings.h)
"""
import sys
from pathlib import Path

MARK = 'OMNI_BARS_HIDE_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'


def patch(name, edits):
    p = root / name
    raw = p.read_bytes()
    nl = '\r\n' if b'\r\n' in raw else '\n'
    s = raw.decode('utf-8')
    if MARK in s:
        return 'already'
    for old, new in edits:
        old, new = old.replace('\n', nl), new.replace('\n', nl)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old[:90]))
        s = s.replace(old, new, 1)
    p.write_bytes(s.encode('utf-8'))
    return 'applied'


BROWSER = [
    ('static bool omniAutoHideActive() { return omniAutoHide && omniAutoHideAllowed; }',
     '''static bool omniAutoHideActive() { return omniAutoHide && omniAutoHideAllowed; }
// OMNI_BARS_HIDE_V1: the quick-access row and the bottom button bar can be hidden; a hidden row gives its space to the
// page (full-height layout, as while Auto-hide is on). /data/omni/ui-bars.txt: "qa=hidden", "hints=hidden".
static bool omniQaHidden = false, omniHintsHidden = false, omniBarsLoaded = false;
static void omniBarsLoad()
{
    if (omniBarsLoaded) return;
    omniBarsLoaded = true;
    if (FILE* f = fopen("/data/omni/ui-bars.txt", "r")) {
        char line[64];
        while (fgets(line, sizeof(line), f)) {
            if (!strncmp(line, "qa=hidden", 9)) omniQaHidden = true;
            if (!strncmp(line, "hints=hidden", 12)) omniHintsHidden = true;
        }
        fclose(f);
    }
}
static void omniBarsSave()
{
    if (FILE* f = fopen("/data/omni/ui-bars.txt", "w")) {
        fprintf(f, "qa=%s\\nhints=%s\\n", omniQaHidden ? "hidden" : "shown", omniHintsHidden ? "hidden" : "shown");
        fclose(f);
    }
}
static bool omniQaRowHidden() { omniBarsLoad(); return omniQaHidden && omniAutoHideAllowed; }
static bool omniHintBarHidden() { omniBarsLoad(); return omniHintsHidden && omniAutoHideAllowed && !editing && !settingsOpen; }
static bool omniFullLayout() { omniBarsLoad(); return omniAutoHideActive() || ((omniQaHidden || omniHintsHidden) && omniAutoHideAllowed); }
static int omniTopH() { return omniQaRowHidden() ? 112 : top; }
static int omniBottomH() { return omniHintBarHidden() ? 0 : bottom; }'''),
    ('static int omniNormalPageHeight() { return omniAutoHideActive() ? renderHeight : physical(pageHeight); }',
     'static int omniNormalPageHeight() { return omniFullLayout() ? renderHeight : physical(pageHeight); } // OMNI_BARS_HIDE_V1'),
    ('static float omniPageTopF() { return pageFullscreen ? 0.f : omniAutoHideActive() ? top * omniChromeShown : float(top); }',
     'static float omniPageTopF() { return pageFullscreen ? 0.f : omniFullLayout() ? omniTopH() * (omniAutoHideActive() ? omniChromeShown : 1.f) : float(top); }'),
    ('static int omniPageBottom() { return pageFullscreen ? height : omniAutoHideActive() ? height - int(bottom * omniChromeShown + 0.5f) : height - bottom; }',
     'static int omniPageBottom() { return pageFullscreen ? height : omniFullLayout() ? height - int(omniBottomH() * (omniAutoHideActive() ? omniChromeShown : 1.f) + 0.5f) : height - bottom; }'),
    ('''    if (!omniAutoHideActive() || pageFullscreen || omniChromeShown < 1) return renderPageHeight;
    return std::clamp(renderHeight - physical(top), 1, renderPageHeight);''',
     '''    if (!omniFullLayout() || pageFullscreen || (omniAutoHideActive() && omniChromeShown < 1)) return renderPageHeight; // OMNI_BARS_HIDE_V1
    return std::clamp(renderHeight - physical(omniTopH()), 1, renderPageHeight);'''),
    ('''    fill(0, 52, width, top - 52, T.bar);
    omniRectPx({ 0, physical(top) - omniHairPx(), renderWidth, omniHairPx() }, omniMix(T.line, T.edge, 0.5f));''',
     '''    fill(0, 52, width, omniTopH() - 52, T.bar); // OMNI_BARS_HIDE_V1
    omniRectPx({ 0, physical(omniTopH()) - omniHairPx(), renderWidth, omniHairPx() }, omniMix(T.line, T.edge, 0.5f));'''),
    ('''    const int topRows = std::min(physical(top), canvas->h), pageY = int(top * shown * displayScale + 0.5);''',
     '''    const int topRows = std::min(physical(omniTopH()), canvas->h), pageY = int(omniTopH() * shown * displayScale + 0.5); // OMNI_BARS_HIDE_V1'''),
    ('''    omniFadeRows(pageY, physical(5), 70, 0);
    const int y0 = std::min(physical(height - bottom), canvas->h), rows = canvas->h - y0;
    const int visible = std::min(rows, int(bottom * shown * displayScale + 0.5)), down = rows - visible;''',
     '''    omniFadeRows(pageY, physical(5), 70, 0);
    if (!omniBottomH()) return; // OMNI_BARS_HIDE_V1: bottom button bar hidden
    const int y0 = std::min(physical(height - omniBottomH()), canvas->h), rows = canvas->h - y0;
    const int visible = std::min(rows, int(omniBottomH() * shown * displayScale + 0.5)), down = rows - visible;'''),
    ('''    z.topEnd = std::min(physical(top), canvas->h);
    z.fadeTop0 = int(top * shown * displayScale + 0.5); z.fadeTopRows = physical(5);
    const int y0 = std::min(physical(height - bottom), canvas->h), rows = canvas->h - y0;
    const int visible = std::min(rows, int(bottom * shown * displayScale + 0.5));''',
     '''    z.topEnd = std::min(physical(omniTopH()), canvas->h); // OMNI_BARS_HIDE_V1
    z.fadeTop0 = int(omniTopH() * shown * displayScale + 0.5); z.fadeTopRows = physical(5);
    const int y0 = std::min(physical(height - omniBottomH()), canvas->h), rows = canvas->h - y0;
    const int visible = std::min(rows, int(omniBottomH() * shown * displayScale + 0.5));'''),
    ('    renderPageHeight = omniAutoHideActive() ? renderHeight : renderHeight - physical(top) - physical(bottom);',
     '    renderPageHeight = omniFullLayout() ? renderHeight : renderHeight - physical(top) - physical(bottom); // OMNI_BARS_HIDE_V1'),
]

MQ = [
    ('''static bool omniMqAvailable()
{''', '''static bool omniQaRowHidden(); // OMNI_BARS_HIDE_V1
static bool omniMqAvailable()
{
    if (omniQaRowHidden()) return false; // OMNI_BARS_HIDE_V1: the row is hidden'''),
    ('''    fill(0, 112, width, top - 112, t.bar);''', '''    if (omniQaRowHidden()) return; // OMNI_BARS_HIDE_V1
    fill(0, 112, width, top - 112, t.bar);'''),
]

SETTINGS = [
    ('omniFxSetQa /* OMNI_QA_CUSTOM_V1 */ };', 'omniFxSetQa /* OMNI_QA_CUSTOM_V1 */, omniFxSetQaRow, omniFxSetHintBar /* OMNI_BARS_HIDE_V1 */ };\n'
     'static void omniBarsToggle(bool quickAccess); // OMNI_BARS_HIDE_V1 (OmniBrowser.cpp)\nstatic bool omniBarsHidden(bool quickAccess);'),
    ('''    add(omniFxSetQa, "Quick access buttons...", "", false); // OMNI_QA_CUSTOM_V1''',
     '''    add(omniFxSetQa, "Quick access buttons...", "", false); // OMNI_QA_CUSTOM_V1
    add(omniFxSetQaRow, "Quick access row", omniBarsHidden(true) ? "Hidden" : "Shown", true); // OMNI_BARS_HIDE_V1
    add(omniFxSetHintBar, "Bottom button bar", omniBarsHidden(false) ? "Hidden" : "Shown", true);'''),
    ('''    case omniFxSetQa: if (!a) return false; omniQaEditorShow(); return true; // OMNI_QA_CUSTOM_V1''',
     '''    case omniFxSetQa: if (!a) return false; omniQaEditorShow(); return true; // OMNI_QA_CUSTOM_V1
    case omniFxSetQaRow: if (!dir) return false; omniBarsToggle(true); return true; // OMNI_BARS_HIDE_V1
    case omniFxSetHintBar: if (!dir) return false; omniBarsToggle(false); return true;'''),
]

TOGGLE = [
    ('''static void omniSettingsChange(bool right)
{''', '''// OMNI_BARS_HIDE_V1: Browser settings rows
static bool omniBarsHidden(bool quickAccess) { omniBarsLoad(); return quickAccess ? omniQaHidden : omniHintsHidden; }
static void omniBarsToggle(bool quickAccess)
{
    omniBarsLoad();
    bool& v = quickAccess ? omniQaHidden : omniHintsHidden;
    v = !v;
    omniBarsSave();
    omniApplyPageHeight();
    if (active()) WKViewSetSize(active()->view.get(), omniViewSize());
    omniChromeWanted = true; omniShellDirty = omniPageDirty = true;
    notice(std::string(quickAccess ? "Quick access row " : "Bottom button bar ") + (v ? "hidden" : "shown"));
}
static void omniSettingsChange(bool right)
{'''),
]

print('OmniBrowser.cpp', patch('OmniBrowser.cpp', BROWSER + TOGGLE))
print('OmniMqQuickAccess.h', patch('OmniMqQuickAccess.h', MQ))
print('OmniBrowserSettings.h', patch('OmniBrowserSettings.h', SETTINGS))
