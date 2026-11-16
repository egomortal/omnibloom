#!/usr/bin/env python3
"""OMNI_POINTER_TUNE_V1 (2026-11-16): pointer snap strength and a left-stick speed curve (Browser settings).

What existed (grep of the patched tree, recipe chain_final + apply_access_input.py)
  OmniPointerFeel.h omniFxStickTick: past the radial dead zone ("Stick dead zone", OMNI_STICK_DEADZONE_V1) the deflection
    is rescaled to m = 0..1 and the pointer moves at omniFxPointerSpeed[pointer] * (0.05 + 0.95 * m^2.3) px/s ("Pointer
    speed": Slow / Normal / Fast / Very fast = 650 / 1050 / 1500 / 2000 at full tilt). So today's curve is a smooth power
    curve (exponent 2.3, 5 % floor). On release omniFxSnapRequest runs the hit-test script with R = 36 px (layout px,
    times the CSS scale); it only runs since OMNI_JS_TRIM_FIX_V1 fixed the script.
  OmniBrowserSettings.h: "Pointer snaps to links" On / Off (omniFxSet.snap, saved as "snap\t0|1", default On).

What the user sees now (Browser settings, D-pad left / right step, Cross cycles, Triangle puts the default back)
  "Pointer speed curve"     Linear / Smooth / Fast        (new row after "Pointer speed"; default Smooth = today's curve)
  "Pointer snaps to links"  Off / Light (24 px) / Normal (36 px) / Strong (56 px)   (same row and label; Normal = today)
  Every curve is 0.05 at the dead-zone edge and 1 at full tilt (dead zone and Pointer speed keep their meaning); at
  half tilt Smooth 0.24, Linear 0.525, Fast 0.76. Test modes always use Smooth (the snap is already off in test modes).
  Search settings: "acceleration" finds the curve row, "magnet" the snap row.

Migration (browser-settings.txt): "snap\t0|1" is still written (snap = strength != Off), plus "snapsize\t<0..3>" and
  "ptrcurve\t<0..2>" appended. A file without snapsize (older build): On -> Normal, Off -> Off. snap 0 always wins (an
  older build that turned it off drops snapsize anyway). Older builds ignore the new keys and keep snap on / off.

Pure part: engine/entry/OmniPointerTune.h (from tools/OmniPointerTune.h: radius table, migration, curves, file text).
  Tests: tools/test_pointer_tune.cpp (g++ -std=c++20 -Wall -Wextra -Werror -I. test_pointer_tune.cpp -o t && ./t;
  Smooth is checked bit-identical to the old expression for all 32769 stick values).
No shell header: the two input functions sit in OmniBrowserSettings.h after omniFxSave. Alias OPTN, names omniPtn*.
Ids: Browser settings row 8457 (omniPtnRowCurve; checked unused in the tree's code and in sibling apply_*.py code);
  dispatched first in omniFxSettingsInput (before the >= 300 / >= 900 rows). The snap row keeps omniFxSetSnap.

Anchors (each exactly once; whole lines only, so no `//` lands after a line-prefix anchor; MARK makes each file
idempotent; CRLF / LF kept):
  OmniBrowserSettings.h  `#pragma once` (pure include + alias + row id after); the deadzone member line (members after);
                         the "snap" load line (new keys after); the omniIoQueue save line (replaced); the
                         "// --- hooks used by OmniBrowser.cpp" line (input functions before); the Pointer speed add()
                         line (curve row after); the snap add() line and the omniFxSetSnap case line (replaced); the
                         omniUlRowId dispatch line (curve dispatch after)
  OmniPointerFeel.h      the snap snprintf line (36 -> table); the speed line in omniFxStickTick (curve)
  OmniSettingsSearch.h   the "cursor" synonym line (two synonyms before)
Apply AFTER apply_js_trim_fix.py (the snap script must work) and apply_access_input.py (chain order; it does not touch
  pointer timing). Controls guide not edited.
usage: apply_pointer_tune.py <engine tree>   (anchored, idempotent, keeps each file's line endings; re-run: "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_POINTER_TUNE_V1'
HERE = Path(__file__).resolve().parent
if len(sys.argv) != 2:
    sys.exit('usage: apply_pointer_tune.py <engine tree>')
root = Path(sys.argv[1]) / 'engine' / 'entry'
IDS = ('8457',)
NAMES = ('OPTN', 'omniPtn', 'OmniPointerTune', 'OMNI_POINTER_TUNE')

INPUTS = r'''// OMNI_POINTER_TUNE_V1: Browser settings input for "Pointer snaps to links" and "Pointer speed curve" (pure part:
// OmniPointerTune.h). D-pad left / right step, Cross cycles, Triangle puts the default (today's behaviour) back.
static bool omniPtnSnapInput(int b)
{
    const int dir = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT ? -1 : b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT ? 1 : 0;
    const bool cycle = b == SDL_CONTROLLER_BUTTON_A, reset = b == SDL_CONTROLLER_BUTTON_Y;
    if (!dir && !cycle && !reset) return false;
    const int now = OPTN::snapLevel(omniFxSet.snapsize, omniFxSet.snap);
    const int next = reset ? OPTN::kSnapNormal : OPTN::step(now, OPTN::kSnapCount, dir, cycle);
    omniFxSet.snapsize = next;
    omniFxSet.snap = next != OPTN::kSnapOff;   // the "snap" key older builds read
    omniFxSave();
    return true;
}
static bool omniPtnCurveInput(int b)
{
    const int dir = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT ? -1 : b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT ? 1 : 0;
    const bool cycle = b == SDL_CONTROLLER_BUTTON_A, reset = b == SDL_CONTROLLER_BUTTON_Y;
    if (!dir && !cycle && !reset) return false;
    omniFxSet.ptrcurve = reset ? OPTN::kCurveSmooth : OPTN::step(omniFxSet.ptrcurve, OPTN::kCurveCount, dir, cycle);
    omniFxSave();
    return true;
}

'''

EDITS = {
    'OmniBrowserSettings.h': [
        ('#pragma once\n',
         '#pragma once\n'
         '#include "OmniPointerTune.h" /* OMNI_POINTER_TUNE_V1: snap strength, speed curve (pure) */\n'
         'namespace OPTN = OmniPointerTune; /* OMNI_POINTER_TUNE_V1 */\n'
         'constexpr int omniPtnRowCurve = 8457; /* OMNI_POINTER_TUNE_V1: Browser settings > "Pointer speed curve" */\n'),
        ('    int deadzone = 1;        // OMNI_STICK_DEADZONE_V1: omniFxDeadZoneNames index (1 Medium = the dead zones used before)\n',
         '    int deadzone = 1;        // OMNI_STICK_DEADZONE_V1: omniFxDeadZoneNames index (1 Medium = the dead zones used before)\n'
         '    int snapsize = -1;       /* OMNI_POINTER_TUNE_V1: stored snap strength (-1: none in the file); use OPTN::snapLevel */\n'
         '    int ptrcurve = 1;        /* OMNI_POINTER_TUNE_V1: OPTN curve (1 Smooth = the curve used before) */\n'),
        ('            else if (k == "snap") omniFxSet.snap = v != "0";\n',
         '            else if (k == "snap") omniFxSet.snap = v != "0";\n'
         '            else if (k == "snapsize") omniFxSet.snapsize = OPTN::parseIndex(v, OPTN::kSnapCount, -1); /* OMNI_POINTER_TUNE_V1 */\n'
         '            else if (k == "ptrcurve") omniFxSet.ptrcurve = OPTN::parseIndex(v, OPTN::kCurveCount, OPTN::kCurveSmooth); /* OMNI_POINTER_TUNE_V1 */\n'),
        ('    omniIoQueue(omniData("browser-settings.txt"), std::string(b) + "home\\t" + omniOneLine(omniFxSet.home, 2048) + "\\nptrstyle\\t" + omniOneLine(omniFxSet.pstyle, 160) + "\\n", false);\n',
         '    omniIoQueue(omniData("browser-settings.txt"), std::string(b) + "home\\t" + omniOneLine(omniFxSet.home, 2048) + "\\nptrstyle\\t" + omniOneLine(omniFxSet.pstyle, 160) + "\\n"\n'
         '        + OPTN::saveText(OPTN::snapLevel(omniFxSet.snapsize, omniFxSet.snap), omniFxSet.ptrcurve), false); /* OMNI_POINTER_TUNE_V1: snapsize, ptrcurve */\n'),
        ('// --- hooks used by OmniBrowser.cpp -----------------------------------------------------------------\n',
         INPUTS +
         '// --- hooks used by OmniBrowser.cpp -----------------------------------------------------------------\n'),
        ('    add(omniFxSetPointer, "Pointer speed", omniFxPointerNames[omniFxSet.pointer], true);\n',
         '    add(omniFxSetPointer, "Pointer speed", omniFxPointerNames[omniFxSet.pointer], true);\n'
         '    add(omniPtnRowCurve, "Pointer speed curve", OPTN::curveName(omniFxSet.ptrcurve), true); /* OMNI_POINTER_TUNE_V1: Linear / Smooth / Fast */\n'),
        ('    add(omniFxSetSnap, "Pointer snaps to links", omniFxSet.snap ? "On" : "Off", true);\n',
         '    add(omniFxSetSnap, "Pointer snaps to links", OPTN::snapName(OPTN::snapLevel(omniFxSet.snapsize, omniFxSet.snap)), true); /* OMNI_POINTER_TUNE_V1: Off / Light / Normal / Strong */\n'),
        ('    if (r.id == omniUlRowId) return omniUlSettingsInput(b); // OMNI_UI_LANG_V1 (before the >= 300 rows)\n',
         '    if (r.id == omniUlRowId) return omniUlSettingsInput(b); // OMNI_UI_LANG_V1 (before the >= 300 rows)\n'
         '    if (r.id == omniPtnRowCurve) return omniPtnCurveInput(b); /* OMNI_POINTER_TUNE_V1 (before the >= 300 / >= 900 rows) */\n'),
        ('    case omniFxSetSnap: if (!dir) return false; omniFxSet.snap = !omniFxSet.snap; omniFxSave(); return true;\n',
         '    case omniFxSetSnap: return omniPtnSnapInput(b); /* OMNI_POINTER_TUNE_V1: Off / Light / Normal / Strong (was On / Off) */\n'),
    ],
    'OmniPointerFeel.h': [
        ('    snprintf(head, sizeof(head), "(function(){var X=%.1f,Y=%.1f,R=%.1f;return ", pointerX * k, (pointerY - omniPageTop()) * k, 36 * k);\n',
         '    const float omniPtnR = OPTN::snapRadius(OPTN::snapLevel(omniFxSet.snapsize, omniFxSet.snap)); /* OMNI_POINTER_TUNE_V1: Normal = 36 (as before) */\n'
         '    snprintf(head, sizeof(head), "(function(){var X=%.1f,Y=%.1f,R=%.1f;return ", pointerX * k, (pointerY - omniPageTop()) * k, omniPtnR * k);\n'),
        ('        const float speed = omniFxPointerSpeed[std::clamp(omniFxSet.pointer, 0, 3)] * (0.05f + 0.95f * std::pow(m, 2.3f));\n',
         '        const float speed = omniFxPointerSpeed[std::clamp(omniFxSet.pointer, 0, 3)]\n'
         '            * OPTN::curveGain(omniTestMode() ? OPTN::kCurveSmooth : omniFxSet.ptrcurve, m); /* OMNI_POINTER_TUNE_V1: Smooth = the old 0.05 + 0.95 * m^2.3 */\n'),
    ],
    'OmniSettingsSearch.h': [
        ('        { "cursor", { "pointer", nullptr } },\n',
         '        { "acceleration", { "pointer speed curve", nullptr } }, /* OMNI_POINTER_TUNE_V1 */\n'
         '        { "magnet", { "pointer snaps", nullptr } }, /* OMNI_POINTER_TUNE_V1 */\n'
         '        { "cursor", { "pointer", nullptr } },\n'),
    ],
}
NEEDS = {'OmniBrowserSettings.h': ('OMNI_STICK_DEADZONE_V1',),
         'OmniPointerFeel.h': ('OMNI_JS_TRIM_FIX_V1', 'OMNI_STICK_DEADZONE_V1'),
         'OmniSettingsSearch.h': ('OMNI_SETTINGS_SEARCH_V1',)}


def variants(old0, s):
    """The anchor with the file's own line endings (mixed files: whichever spelling is present)."""
    for e in ('\r\n', '\n'):
        old = old0.replace('\n', e)
        if s.count(old):
            return old, e
    return old0, '\n'


def check(name, edits):
    s = (root / name).read_bytes().decode('utf-8')
    if MARK in s:
        return
    for old0, _ in edits:
        old, _e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))


def patch(name, edits):
    p = root / name
    s = p.read_bytes().decode('utf-8')
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


# An id ASSIGNED in a sibling's code (its generated C++: "kRowX = 8457", "omniXRowId = 8457", "id == 8457"): a sibling
# whose header is not in this tree yet still owns the number. Bare mentions in its comments / docstring are not looked at.
_ID_ASSIGN = re.compile(r'(?:=|==|case)\s*(%s)\b' % '|'.join(IDS))


def ids_free():
    """Before a first apply: no other patch or tree file uses this patch's ids or names."""
    word = re.compile(r'\b(%s)\b' % '|'.join(IDS))
    name = re.compile('|'.join(NAMES))
    mine = {'OmniPointerTune.h'}
    for f in sorted(HERE.glob('apply_*.py')):
        if f.name == Path(__file__).name:
            continue
        if f.name == 'apply_controls_help.py' or MARK in f.read_text(encoding='utf-8', errors='replace'):   # OMNI_SIBLING_SKIP: the guide quotes names; a patch built on this one uses them
            continue
        t = code_only(f.read_text(encoding='utf-8', errors='replace'))
        m = name.search(t) or _ID_ASSIGN.search(cpp_code(t))
        if m:
            sys.exit('%s already uses %r: pick other ids / names' % (f.name, m.group(0)))
    for f in sorted(root.iterdir()):
        if f.name in mine or f.suffix not in ('.h', '.cpp', '.inc'):
            continue
        t = f.read_bytes().decode('utf-8', errors='replace')
        c = cpp_code(t)
        m = word.search(c) or (None if f.name in GUIDE else name.search(c))
        if m and MARK not in t:
            sys.exit('%s already uses %r: pick other ids / names' % (f.name, m.group(0)))


def main():
    for fname, needs in NEEDS.items():
        s = (root / fname).read_bytes().decode('utf-8')
        for need in needs:
            if need not in s:
                sys.exit('%s: %s missing: apply its patch first' % (fname, need))
    if MARK not in (root / 'OmniBrowserSettings.h').read_bytes().decode('utf-8'):
        ids_free()
    for fname, edits in EDITS.items():   # every anchor is checked before anything is written
        check(fname, edits)
    pure = (HERE / 'OmniPointerTune.h').read_text(encoding='utf-8')
    if MARK not in pure:
        sys.exit('OmniPointerTune.h: %s missing' % MARK)
    msgs = [write_new('OmniPointerTune.h', pure, 'OmniBrowserSettings.h')]
    msgs += [patch(fname, edits) for fname, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
