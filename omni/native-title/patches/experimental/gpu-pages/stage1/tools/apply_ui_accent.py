#!/usr/bin/env python3
"""OMNI_UI_ACCENT_V1 (2026-11-16): Browser settings > "Accent colour" for Omni's own UI, on top of every theme.

What the user sees
  - Browser settings, right after "High contrast" / "Large pointer" and just before "Controller, theme and display...":
        "Accent colour   Theme default"   detail "High contrast keeps its yellow"
    Left / Right step through Theme default / Blue / Teal / Green / Amber / Orange / Red / Pink / Violet, Cross steps
    forward. Saved through omniIoQueue in /data/omni/ui-accent.txt (one id: default, blue, teal, green, amber, orange,
    red, pink, violet; anything else = Theme default). Read once at start in omniLoadStyleSettings; self-test modes
    keep the theme default (the file is not read).
  - The colour shows wherever the theme accent is used: focus rings (omniRingRect / omniRingDisc), selected rows and
    keys (accent fill with accentInk text), progress bars, switches, the active tab's line (accent -> accent2, accent2
    = the accent 30% lighter), the theme card border, the new-tab page (omniNewTabVars, open new-tab pages re-themed
    at once) and the controller light bar (OMNI_PAD_FEEDBACK_V1: OmniPadFeedbackShell.h reads omniTheme().accent for
    its "theme accent" fallback, so it follows with no change there).
  - With the High contrast theme the accent is ignored (its yellow focus ring and black-on-yellow rows stay); the row
    stays usable and says so in its detail and in a notice when changed.

How: the one lookup, omniTheme(), returns a copy of omniThemes[omniThemeIndex] with accent / accentInk / accent2
replaced (rebuilt only when the theme or accent index changes, two int compares per call otherwise). The theme cards
in omniSettingsPanel keep each theme's own disc colours (they read omniThemes[i]); omniSettingsPanel is NOT touched,
so apply_ui_scale.py's SETTINGS_SHA copy check is unaffected. The accent index is also mixed into
omniShellSignature and omniFrameKey (theme bits 24-27, accent bits 28-31) so a change redraws everything.

Contrast (WCAG 2 formula, OmniHighContrast::contrast reused): every accent vs every surface of dark / midnight /
playstation / purple (bg, bar, tab, hover, field, panel, raised, key, tabOn) >= 3:1 (worst 4.12:1); text on the
accent (black or white, picked by OmniUiAccent::inkOn: black for all eight) >= 4.5:1 (worst 7.59:1, Red), and on
accent2 >= 4.5:1. tools/test_ui_accent.cpp asserts all of it and, given OmniBrowser.cpp, that its omniThemes[]
match the copy tested.

Pure part: engine/entry/OmniUiAccent.h (kept next to this script; includes OmniHighContrast.h).
Tested by tools/test_ui_accent.cpp:
    g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_ui_accent.cpp -o t && ./t <tree>/engine/entry/OmniBrowser.cpp
Shell side: OmniBrowser.cpp (namespace alias OUAC), OmniBrowserSettings.h. Row id 832 (OUAC::kRowId); taken on
2026-11-16 by any apply_*.py / the tree: 825-829, 834-842, 845-848, 850, 855, 860, 861, 865, 870, 875, 876, 880, 890,
891, 895, 897, 900+, 940-943 (830-833, 843, 844, 849 were free).
Needs OMNI_HIGH_CONTRAST_V1 (anchors on its omniTheme() neighbourhood, its settings rows and its dispatch line).

Anchors (exactly once each; MARK makes each file idempotent; CRLF / LF kept, matched as \\r?\\n; whole lines, except
the two mid-line ones, which only insert /* */ comments):
  OmniBrowser.cpp
    "static const OmniTheme& omniTheme() { return omniThemes[omniThemeIndex]; }"  -> include, alias, accent state,
                                                                                    the overriding omniTheme()
    'if (FILE* file = fopen("/data/omni/ui-autohide.txt", "r")) {' (omniLoadStyleSettings) -> read ui-accent.txt before it
    "static int theme = -1;" + "if (theme != omniThemeIndex) {"  -> also re-theme new-tab pages on an accent change
    "mix(&omniThemeIndex, sizeof omniThemeIndex); " (line prefix, omniShellSignature) -> + the accent index
    "(uint64_t(uint32_t(omniThemeIndex) & 255) << 24)" (mid-line, omniFrameKey)       -> theme 4 bits + accent 4 bits
    '#include "OmniFeatures.h" // OMNI_FEATURES_V1'  -> omniUacSettingsRow / omniUacSettingsInput after it
  OmniBrowserSettings.h
    "static bool omniHcSettingsInput(int id, int b);"   -> the two declarations after it
    the omniHcSettingsRows(p) line in omniFxSettingsBuild -> the row after it
    the omniHcRowTheme dispatch line in omniFxSettingsInput -> the accent dispatch before it (before the >= 300 rows)
usage: apply_ui_accent.py <engine tree>   (re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_UI_ACCENT_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'
HERE = Path(__file__).resolve().parent
PURE_NAME = 'OmniUiAccent.h'

EDITS = {
    'OmniBrowser.cpp': [
        ('static const OmniTheme& omniTheme() { return omniThemes[omniThemeIndex]; }\n',
         '#include "OmniUiAccent.h" // OMNI_UI_ACCENT_V1: accent palette, contrast checks, automatic text colour (pure)\n'
         'namespace OUAC = OmniUiAccent;\n'
         'static int omniAccentIndex = 0;   // OUAC::kAccents, 0 = Theme default (/data/omni/ui-accent.txt, read in omniLoadStyleSettings)\n'
         '// OMNI_UI_ACCENT_V1: the one theme lookup. Browser settings > "Accent colour" replaces accent / accentInk / accent2\n'
         '// here, so every consumer (rings, selected rows, bars, switches, new-tab page, light bar) follows. Rebuilt only when\n'
         '// the theme or the accent changes. High contrast and "Theme default" keep the theme\'s own colours.\n'
         'static const OmniTheme& omniTheme()\n'
         '{\n'
         '    static OmniTheme theme = omniThemes[0];\n'
         '    static int builtTheme = -1, builtAccent = -1;\n'
         '    if (builtTheme != omniThemeIndex || builtAccent != omniAccentIndex) {\n'
         '        builtTheme = omniThemeIndex; builtAccent = omniAccentIndex;\n'
         '        theme = omniThemes[omniThemeIndex];\n'
         '        const OUAC::Pick pick = OUAC::accentFor(omniAccentIndex, theme.id);\n'
         '        if (pick.ok) { theme.accent = omniHcC(pick.o.accent); theme.accentInk = omniHcC(pick.o.accentInk); theme.accent2 = omniHcC(pick.o.accent2); }\n'
         '    }\n'
         '    return theme;\n'
         '}\n'),
        ('    if (FILE* file = fopen("/data/omni/ui-autohide.txt", "r")) {\n',
         '    if (!omniTestMode()) {   // OMNI_UI_ACCENT_V1: Browser settings > Accent colour (self-tests keep the theme default)\n'
         '        char value[32] {};\n'
         '        if (FILE* file = fopen(omniData(OUAC::kFile).c_str(), "rb")) { const size_t n = fread(value, 1, sizeof(value) - 1, file); fclose(file); value[n] = 0; }\n'
         '        omniAccentIndex = OUAC::parse(value);\n'
         '    }\n'
         '    if (FILE* file = fopen("/data/omni/ui-autohide.txt", "r")) {\n'),
        ('    static int theme = -1;\n'
         '    if (theme != omniThemeIndex) {\n',
         '    static int theme = -1, accentSeen = 0;   // OMNI_UI_ACCENT_V1: an accent change re-themes open new-tab pages too\n'
         '    if (theme != omniThemeIndex || accentSeen != omniAccentIndex) {\n'
         '        accentSeen = omniAccentIndex;\n'),
        ('    mix(&omniThemeIndex, sizeof omniThemeIndex); ',
         '    mix(&omniThemeIndex, sizeof omniThemeIndex); mix(&omniAccentIndex, sizeof omniAccentIndex); /* OMNI_UI_ACCENT_V1 */ '),
        ('(uint64_t(uint32_t(omniThemeIndex) & 255) << 24)',
         '(uint64_t(uint32_t(omniThemeIndex) & 15) << 24) | (uint64_t(uint32_t(omniAccentIndex) & 15) << 28) /* OMNI_UI_ACCENT_V1 */'),
        ('#include "OmniFeatures.h" // OMNI_FEATURES_V1\n',
         '#include "OmniFeatures.h" // OMNI_FEATURES_V1\n'
         '// OMNI_UI_ACCENT_V1: Browser settings > "Accent colour" (row id OUAC::kRowId; declared in OmniBrowserSettings.h).\n'
         'static void omniUacSettingsRow(OmniFxPanel& p)\n'
         '{\n'
         '    OmniFxRow r; r.id = OUAC::kRowId; r.label = OUAC::kRowLabel; r.value = OUAC::name(omniAccentIndex); r.detail = OUAC::kRowDetail; r.stepper = true;\n'
         '    p.rows.push_back(r);\n'
         '}\n'
         'static bool omniUacSettingsInput(int b)\n'
         '{\n'
         '    const int dir = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT ? -1 : (b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT || b == SDL_CONTROLLER_BUTTON_A) ? 1 : 0;\n'
         '    if (!dir) return false;\n'
         '    omniAccentIndex = OUAC::step(omniAccentIndex, dir);\n'
         '    omniIoQueue(omniData(OUAC::kFile), OUAC::serialize(omniAccentIndex), false);\n'
         '    omniChromeWanted = true; omniShellDirty = omniPageDirty = true;\n'
         '    if (omniHc()) notice("High contrast keeps its yellow accent");\n'
         '    omniFxRefresh();\n'
         '    return true;\n'
         '}\n'),
    ],
    'OmniBrowserSettings.h': [
        ('static bool omniHcSettingsInput(int id, int b);\n',
         'static bool omniHcSettingsInput(int id, int b);\n'
         'static void omniUacSettingsRow(OmniFxPanel& p); // OMNI_UI_ACCENT_V1: "Accent colour" (OmniBrowser.cpp, row id OUAC::kRowId = 832)\n'
         'static bool omniUacSettingsInput(int b);\n'),
        ('    omniHcSettingsRows(p); // OMNI_HIGH_CONTRAST_V1: High contrast, Large pointer (next to the theme row)\n',
         '    omniHcSettingsRows(p); // OMNI_HIGH_CONTRAST_V1: High contrast, Large pointer (next to the theme row)\n'
         '    omniUacSettingsRow(p); // OMNI_UI_ACCENT_V1: Accent colour (Theme default / Blue ... Violet)\n'),
        ('    if (r.id == omniHcRowTheme || r.id == omniHcRowPointer) return omniHcSettingsInput(r.id, b); // OMNI_HIGH_CONTRAST_V1 (before the >= 300 rows)\n',
         '    if (r.id == OUAC::kRowId) return omniUacSettingsInput(b); // OMNI_UI_ACCENT_V1 (before the >= 300 rows)\n'
         '    if (r.id == omniHcRowTheme || r.id == omniHcRowPointer) return omniHcSettingsInput(r.id, b); // OMNI_HIGH_CONTRAST_V1 (before the >= 300 rows)\n'),
    ],
}


def pattern(text):
    return re.compile(''.join(r'\r?\n' if c == '\n' else re.escape(c) for c in text))


def read(name):
    return (root / name).read_bytes().decode('utf-8')


def check(name, edits):
    s = read(name)
    if MARK in s:
        return
    for old, _ in edits:
        n = len(pattern(old).findall(s))
        if n != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, n, old[:90]))


def patch(name, edits):
    p = root / name
    s = read(name)
    if MARK in s:
        return name + ': already'
    for old, new in edits:
        m = list(pattern(old).finditer(s))
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


# The Controls guide's table names other patches' handlers by design: never a name clash (numbers still count there).
GUIDE = ('OmniControlsHelp.h', 'OmniControlsHelpShell.h')
_CPP_TOK = re.compile(r'//[^\n]*|/\*.*?\*/|R"([^()\\\s"]{0,16})\(.*?\)\1"|"(?:\\.|[^"\\\n])*"' + r"|'(?:\\.|[^'\\\n])*'", re.S)


def cpp_code(s):
    """C/C++ text without its // and /* */ comments (string, char and raw string literals kept; newlines kept, so line
    numbers stay): an id or name in another patch's notes (e.g. "834-839" in a generated header) is not a use."""
    return _CPP_TOK.sub(lambda m: m.group(0) if m.group(0)[0] in 'R"\'' else '\n' * m.group(0).count('\n'), s)


def main():
    browser = read('OmniBrowser.cpp')
    if 'OMNI_HIGH_CONTRAST_V1' not in browser or not (root / 'OmniHighContrast.h').exists():
        sys.exit('OmniBrowser.cpp: OMNI_HIGH_CONTRAST_V1 missing (run apply_high_contrast.py first: omniHcC, omniHc, its rows)')
    if MARK not in browser:
        for alias in ('OUAC', 'omniAccentIndex', 'omniUacSettings'):
            if alias in cpp_code(browser) or alias in cpp_code(read('OmniBrowserSettings.h')):
                sys.exit('%s is already used by something else' % alias)
        for f in sorted(root.glob('*.[ch]*')):
            if f.name == PURE_NAME:
                continue
            for rid in re.findall(r'(?:RowId\w*|kRowId|kSettingsRowId|Row[A-Z]\w*)\s*=\s*(\d+)', cpp_code(f.read_bytes().decode('utf-8', 'replace'))):
                if int(rid) == 832:
                    sys.exit('row id 832 is already taken in the tree (%s)' % f.name)
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new(PURE_NAME, 'OmniHighContrast.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


if __name__ == '__main__':
    main()
