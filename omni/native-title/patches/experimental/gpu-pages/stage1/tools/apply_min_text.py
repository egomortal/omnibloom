#!/usr/bin/env python3
"""OMNI_MIN_TEXT_V1 (2026-11-16): Browser settings > "Minimum text size" (backlog E01). Default Off.

What the user sees
  Browser settings, right after "Captions":
      "Minimum text size"   Off / 12 px / 14 px / 16 px / 18 px / 20 px
      D-pad left / right: one size down / up (stops at Off and 20 px); Cross: next size (20 px wraps to Off);
      Triangle: back to Off. Saved in min-text.txt ("off" / "16" ...). A notice names the new size.
  Every page (all tabs, private tabs, every frame, Omni's own repo pages too) shows text smaller than the chosen size
  at that size. Open pages change at once, no reload.
  Test modes: always Off (self-tests measure normal layouts; the row says so, the saved choice is kept).

Mechanism: WebKit's own preference, not CSS. This port's C API has WKPreferencesSetMinimumFontSize(WKPreferencesRef,
uint32_t) (WKPreferencesRef.h, defined in WKPreferences.cpp next to WKPreferencesSetFullScreenEnabled, which Omni
already calls). It sets UnifiedWebPreferences.yaml's MinimumFontSize (double, status embedder, default 0,
webcoreOnChange: setNeedsRecalcStyleInAllFrames); WebPreferences::updateDoubleValueForKey -> update() -> every page's
preferencesDidChange, so open pages restyle without a reload. Every tab uses the one `preferences` object (newTab()
and the private-tab path both call WKPageConfigurationSetPreferences(config, preferences)), so one call covers all.
WebCore applies it as a hard minimum (Style::usedFontSizeFromComputedSize, "minSize"): used size =
max(computed size x zoom, minimum), where zoom is page zoom (Default page zoom / site zoom) times Text size; 0 px text
stays hidden; SVG text is exempt. So at 50 % page zoom, 10 px text becomes the minimum, not 5 px. The "smart"
MinimumLogicalFontSize (WebKit default 9) is left alone. Off sends 0 (MinimumFontSize's default); with nothing saved
(or in test modes) WebKit is never called at startup.
Not done here: the backlog's per-site override (site_list) - global only, as asked.

Pure part: OmniMinText.h (kept next to this script, copied to engine/entry): sizes, min-text.txt, row value, stepping,
webkitValue(), and WebCore's hard-minimum rule copied for the tests. Tested by tools/test_min_text.cpp:
    g++ -std=c++20 -Wall -Wextra -I. test_min_text.cpp -o t && ./t [<tree>/engine/entry [<webkit>/Source]]
(with the tree it checks each patched site; with WebKit's Source it checks the C API, the preference's yaml entry and
the hard-minimum lines the copy follows).
Shell side: engine/entry/OmniMinTextShell.h (included from OmniFeatures3.h after OmniCaptionStyleShell.h), the
OmniMinText.h include + namespace alias OMTX in OmniBrowser.cpp, the startup call, the settings row.

Anchors (each exactly once; MARK makes each file idempotent; CRLF / LF kept; whole lines only, nothing appended after a
line-prefix anchor):
  OmniBrowser.cpp       the OmniCaptionStyle.h include line           -> + #include "OmniMinText.h", OMTX alias
                        "    WKPreferencesSetFullScreenEnabled(preferences.get(), true);" -> + omniMtxApplyStartup();
  OmniBrowserSettings.h "static bool omniCcsSettingsInput(int b);"    -> + declarations
                        the omniCcsSettingsRow(p) line                -> + our row after it
                        the OmniCaptionStyle::kSettingsRowId dispatch line -> + our dispatch before it (before >= 300)
  OmniFeatures3.h       the OmniCaptionStyleShell.h include line      -> + our shell
  OmniSettingsSearch.h  the { "font", ... } synonym line              -> + "readable" / "small text" synonyms before it
Row id 817 (OMTX::kRowId). Refused before the first apply if "= 817" is in the tree's code (comments stripped).
Alias OMTX; names omniMtx*, OmniMinText, min-text.txt: refused if a sibling apply_*.py's code (comments and docstring
stripped) or the tree's code already uses them.

Order: after apply_caption_style.py and apply_settings_search.py (their lines are anchors); last of the feature units
is fine (no other patch anchors on what this adds).
usage: apply_min_text.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_MIN_TEXT_V1'
ROW_ID = 817
PURE_NAME = 'OmniMinText.h'
SHELL_NAME = 'OmniMinTextShell.h'
NAMES = (r'\bOMTX\b', r'\bomniMtx', r'\bOmniMinText\b', r'min-text\.txt')
HERE = Path(__file__).resolve().parent
root = Path(sys.argv[1]) / 'engine' / 'entry' if len(sys.argv) > 1 else None

SHELL = r'''// OMNI_MIN_TEXT_V1: Browser settings > "Minimum text size" (shell side). Included from OmniFeatures3.h (inside
// OmniBrowser.cpp's anonymous namespace, after OmniCaptionStyleShell.h). The pure part is OmniMinText.h (alias OMTX,
// next to its include in OmniBrowser.cpp); the reasons are in tools/apply_min_text.py.
// WebKit's own hard minimum (WKPreferencesSetMinimumFontSize) on the one shared `preferences` object: every tab and
// private tab; open pages restyle at once (no reload). Main thread only; the file is written by omniIoQueue.
#pragma once

static bool omniMtxLoaded = false;
static int omniMtxPx = 0;   // 0 = Off
static int omniMtxSaved()
{
    if (!omniMtxLoaded) {
        omniMtxLoaded = true;
        if (FILE* f = fopen(omniData(OMTX::kFileName).c_str(), "rb")) {
            char buf[32];
            const size_t n = fread(buf, 1, sizeof buf, f);
            fclose(f);
            omniMtxPx = OMTX::parse(std::string(buf, n));
        }
    }
    return omniMtxPx;
}
static void omniMtxApply()
{
    if (!preferences.get()) return;
    WKPreferencesSetMinimumFontSize(preferences.get(), OMTX::webkitValue(omniMtxSaved(), omniTestMode()));   // updates open pages too
}
// main(), right after the preferences are made (before any page): only a saved size; Off / test modes: no call.
static void omniMtxApplyStartup()
{
    if (omniTestMode() || !omniMtxSaved()) return;
    omniMtxApply();
    fprintf(stderr, "OMNI MIN TEXT: %d px\n", omniMtxPx);
}

// --- Browser settings row (OMTX::kRowId, declared in OmniBrowserSettings.h) -------------------------------------------
static void omniMtxSettingsRow(OmniFxPanel& p)
{
    OmniFxRow r; r.id = OMTX::kRowId; r.label = OMTX::kRowLabel; r.value = OMTX::rowValue(omniTestMode() ? 0 : omniMtxSaved());
    r.stepper = true;
    r.detail = omniTestMode() ? std::string(OMTX::kTestDetail) : std::string(OMTX::kRowDetail);
    p.rows.push_back(r);
}
static bool omniMtxSettingsInput(int b)
{
    const int now = omniMtxSaved();
    int px = now;
    if (b == SDL_CONTROLLER_BUTTON_DPAD_LEFT) px = OMTX::stepped(now, -1);
    else if (b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT) px = OMTX::stepped(now, 1);
    else if (b == SDL_CONTROLLER_BUTTON_A) px = OMTX::cycled(now);
    else if (b == SDL_CONTROLLER_BUTTON_Y) px = 0;   // Triangle: back to the default (Off)
    else return false;
    if (omniTestMode()) { notice("Minimum text size is off in test modes"); return true; }
    if (px == now) return true;   // already at Off / the largest size
    omniMtxPx = px;
    omniIoQueue(omniData(OMTX::kFileName), OMTX::serialize(px), false);
    omniMtxApply();
    omniShellDirty = true;
    omniFxRefresh();
    notice(OMTX::noticeText(px));
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniCaptionStyle.h" // OMNI_CAPTION_STYLE_V1: caption look (::cue user sheet), captions.txt (pure)\n',
         '#include "OmniCaptionStyle.h" // OMNI_CAPTION_STYLE_V1: caption look (::cue user sheet), captions.txt (pure)\n'
         '#include "OmniMinText.h" // OMNI_MIN_TEXT_V1: Minimum text size: sizes, min-text.txt (pure)\n'
         'namespace OMTX = OmniMinText; // OMNI_MIN_TEXT_V1\n'),
        ('    WKPreferencesSetFullScreenEnabled(preferences.get(), true);\n',
         '    WKPreferencesSetFullScreenEnabled(preferences.get(), true);\n'
         '    omniMtxApplyStartup(); // OMNI_MIN_TEXT_V1: the saved "Minimum text size" (none / Off: WebKit default)\n'),
    ],
    'OmniBrowserSettings.h': [
        ('static bool omniCcsSettingsInput(int b);\n',
         'static bool omniCcsSettingsInput(int b);\n'
         'static void omniMtxSettingsRow(OmniFxPanel& p); // OMNI_MIN_TEXT_V1: "Minimum text size" (OmniMinTextShell.h, row id OMTX::kRowId = 817)\n'
         'static bool omniMtxSettingsInput(int b);\n'),
        ('    omniCcsSettingsRow(p); // OMNI_CAPTION_STYLE_V1: Captions (opens its panel)\n',
         '    omniCcsSettingsRow(p); // OMNI_CAPTION_STYLE_V1: Captions (opens its panel)\n'
         '    omniMtxSettingsRow(p); // OMNI_MIN_TEXT_V1: Minimum text size (Off / 12 ... 20 px)\n'),
        ('    if (r.id == OmniCaptionStyle::kSettingsRowId) return omniCcsSettingsInput(b); // OMNI_CAPTION_STYLE_V1 (before the >= 300 rows)\n',
         '    if (r.id == OMTX::kRowId) return omniMtxSettingsInput(b); // OMNI_MIN_TEXT_V1 (before the >= 300 rows)\n'
         '    if (r.id == OmniCaptionStyle::kSettingsRowId) return omniCcsSettingsInput(b); // OMNI_CAPTION_STYLE_V1 (before the >= 300 rows)\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniCaptionStyleShell.h" // OMNI_CAPTION_STYLE_V1\n',
         '#include "OmniCaptionStyleShell.h" // OMNI_CAPTION_STYLE_V1\n'
         '#include "OmniMinTextShell.h" // OMNI_MIN_TEXT_V1\n'),
    ],
    'OmniSettingsSearch.h': [
        ('        { "font", { "text size", "interface size", "zoom", nullptr } },\n',
         '        { "readable", { "minimum text size", "text size", "interface size", nullptr } }, // OMNI_MIN_TEXT_V1\n'
         '        { "small text", { "minimum text size", "text size", nullptr } }, // OMNI_MIN_TEXT_V1\n'
         '        { "font", { "text size", "interface size", "zoom", nullptr } },\n'),
    ],
}


def read(name):
    return (root / name).read_bytes().decode('utf-8')


def variants(old0, s):
    """The anchor with the file's own line endings (mixed files: whichever spelling is present)."""
    for e in ('\r\n', '\n'):
        old = old0.replace('\n', e)
        if s.count(old):
            return old, e
    return old0, '\n'


def check(name, edits):
    s = read(name)
    if MARK in s:
        return
    for old0, _ in edits:
        old, _e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))


def patch(name, edits):
    p = root / name
    s = read(name)
    if MARK in s:
        return name + ': already'
    for old0, new0 in edits:
        old, e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))
        s = s.replace(old, new0.replace('\n', e), 1)
    p.write_bytes(s.encode('utf-8'))
    return name + ': applied'


def write_new(name, text, like):
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


def code_only(src):
    """A sibling apply_*.py without its comments and module docstring (line numbers kept): names mentioned only in its
    notes are not a use. Numeric ids are never looked for in siblings (their notes list other patches' id ranges)."""
    import io
    import tokenize
    cut, first = [], True
    try:
        for t in tokenize.generate_tokens(io.StringIO(src).readline):
            if t.type == tokenize.COMMENT or (first and t.type == tokenize.STRING):
                cut.append((t.start, t.end))
            if t.type not in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT,
                              tokenize.ENCODING):
                first = False
    except (tokenize.TokenError, SyntaxError):
        return ''.join(r for r in src.splitlines(True) if not r.lstrip().startswith('#'))
    starts = [0] + [i + 1 for i, c in enumerate(src) if c == '\n']   # tokenize's rows end at '\n' only
    out = list(src)
    for (r0, c0), (r1, c1) in cut:
        for i in range(starts[r0 - 1] + c0, starts[r1 - 1] + c1):
            if out[i] not in '\r\n':
                out[i] = ' '
    return ''.join(out)


def ids_free():
    """Before the first apply: row id 817 unused in the tree's code; the alias and names unused anywhere."""
    taken = re.compile(r'=\s*%d\b' % ROW_ID)
    name = re.compile('|'.join(NAMES))
    for f in sorted(HERE.glob('apply_*.py')):
        if f.name == Path(__file__).name:
            continue
        if f.name == 'apply_controls_help.py' or MARK in f.read_text(encoding='utf-8', errors='replace'):   # OMNI_SIBLING_SKIP: the guide quotes names; a patch built on this one uses them
            continue
        m = name.search(code_only(f.read_text(encoding='utf-8', errors='replace')))
        if m:   # numeric ids: engine tree only (a sibling's notes list other patches' ids)
            sys.exit('%s already uses %r: pick other ids / names' % (f.name, m.group(0)))
    for f in sorted(root.iterdir()):
        if f.name in (PURE_NAME, SHELL_NAME) or f.suffix not in ('.h', '.cpp', '.inc'):
            continue
        t = f.read_bytes().decode('utf-8', errors='replace')
        c = cpp_code(t)
        m = taken.search(c) or (None if f.name in GUIDE else name.search(c))
        if m and MARK not in t:
            sys.exit('%s already uses %r: pick other ids / names' % (f.name, m.group(0)))


def main():
    if root is None:
        sys.exit('usage: apply_min_text.py <engine tree>')
    need = {'OmniFeatures3.h': 'OMNI_CAPTION_STYLE_V1', 'OmniBrowserSettings.h': 'OMNI_CAPTION_STYLE_V1',
            'OmniBrowser.cpp': 'OMNI_CAPTION_STYLE_V1', 'OmniSettingsSearch.h': 'OMNI_SETTINGS_SEARCH_V1'}
    for name, mark in need.items():
        if not (root / name).exists() or mark not in read(name):
            sys.exit('%s: %s missing (apply_min_text.py goes after the patch that adds it)' % (name, mark))
    if MARK not in read('OmniBrowser.cpp'):
        ids_free()
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    pure = (HERE / PURE_NAME).read_bytes().decode('utf-8')
    if MARK not in pure:
        sys.exit('%s: %s missing' % (PURE_NAME, MARK))
    msgs = [write_new(PURE_NAME, pure, 'OmniCaptionStyle.h'), write_new(SHELL_NAME, SHELL, 'OmniCaptionStyleShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


if __name__ == '__main__':
    main()
