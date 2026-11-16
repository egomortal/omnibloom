#!/usr/bin/env python3
"""OMNI_KB_FIELDS_V1 (2026-11-16): field-aware on-screen keyboard: a big phone-style number pad for number, phone and
one-time-code fields.

What the user sees
  - A webpage number field opens on a large pad instead of the old 5-column number layer (three keys a row):
        1 2 3 / 4 5 6 / 7 8 9 / last row:
          one-time codes (autocomplete="one-time-code") and inputmode="numeric":   Delete  0  Done
          phone fields (type="tel" or inputmode="tel"):                            *  0  #
          type="number" / inputmode="decimal":                                     -  0  .
    Quick row (the Edit tools still replace it):  tel  + ( ) - Paste Clips;  decimal  , + e / Paste Clips;
        numeric  - / . , Paste Clips;  codes  Paste Clips (two wide keys: paste the code you copied).
    Action row on the pad:  ABC  Edit  Space  Delete  Done  Close   (no Shift; Delete and Done widest). ABC goes to the
    letters as before and the layer key / R3 comes back to the pad. The Enter key says "Done" on the pad where it said
    "Go" (an enterkeyhint of Search / Send / Next is kept). Focus starts on "1" (as before: row 0, column 0).
  - A one-time-code box that is a plain text input (most sign-in code boxes) now counts as a number field, so it opens
    on the pad; inputmode="text" (alphanumeric codes), password-type code boxes (they keep Show / Hide) and e-mail
    fields are left alone. inputmode wins over type, as in browsers (type=number + inputmode=text: no pad).
  - Word chips stay off on the pad (omniKwContext already returns nothing on the number layer).
  - URL and e-mail fields: nothing new is needed and nothing is duplicated. OMNI_KEYBOARD_V2's quick row already has
    ":" https:// www. .com .org .net = & (URL; the address bar has Sites in place of ":") and @ .com .net @gmail.com
    @outlook.com (e-mail), and OMNI_KB_LAYOUTS_V1's letter tails have . / ? (URL) and . _ @ (e-mail) in every layout.
  - Self-test modes keep the old number layer (omniTestMode()).

Where the field kind comes from: OMNI_KEYBOARD_V2's mirror probe (omniKbProbeScript / omniKbProbeDone), which already
reads element kind, type and inputmode once per keyboard session (fieldKnown). This patch adds autocomplete as a 9th
U+001F-separated part (lower-cased like the others; the probe's other parts and their order are unchanged) and computes
the pad there with the field kind. The pad is remembered with the keyboard session (omniKbfSession), so a new field
never inherits the last one's pad, and it is part of omniKbRows' cache key.

Coexists with: kb layouts (letter rows only; the pad is the number layer), accent popup (letters layer only), emoji
page (omniKbPage 2, symbols layer key; unchanged), show password (password fields never get a pad), clipboard
history (the pad's Clips key is the same OmniClipHistory::kKbKey action as Edit > Clips; Paste is omniKbPasteKey).

Pure part: OmniKbFields.h (kept in tools/, copied into engine/entry): padKind (type / inputmode / autocomplete ->
pad), settle (with the shell's field kind), the grid / quick / action key tables.
Tested by tools/test_kb_fields.cpp:  g++ -std=c++20 -Wall -Wextra -I. test_kb_fields.cpp -o t && ./t   (in tools/)
Shell side: OmniBrowser.cpp only (namespace alias OKBF, names omniKbf*). No settings row, no file, no new import.

Anchors in OmniBrowser.cpp (exactly once each, whole lines; MARK makes it idempotent; CRLF / LF kept):
  the OmniKbLayouts.h include (apply_kb_layouts.py's)                 -> + OmniKbFields.h include
  "// Webpage fields ---" comment                                     -> pad state + omniKbfPadNow() before it
  the probe script's return line                                      -> + c(g('autocomplete'))
  omniKbProbeDone: "while (part.size() < 7)", "part.size() != 8"      -> 8 / 9
  omniKbProbeDone: "omniKb.field = f;"                                -> the pad decided before it
  omniKbGoLabel: the "done" / "Go" lines                              -> "Done" on the pad
  omniKbRows: the cache-key line (apply_kb_layouts.py's), the numpad branch line, the end of the Edit tools block
    (apply_clip_history.py's "Clear" line + "} else if (url) {"), "auto& action = rows[5];"
  "// Rows 0-3 characters, row 4 ..." comment (re-emitted by apply_kb_layouts.py) -> omniKbfRow before it
Apply AFTER apply_kb_layouts.py, apply_kb_emoji.py, apply_kb_showpw.py and apply_clip_history.py.
usage: apply_kb_fields.py <engine tree>   (re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_KB_FIELDS_V1'
HERE = Path(__file__).resolve().parent
if len(sys.argv) != 2:
    sys.exit('usage: apply_kb_fields.py <engine tree>')
root = Path(sys.argv[1]) / 'engine' / 'entry'
NAMES = ('OKBF', 'omniKbf', 'OmniKbFields', 'OMNI_KB_FIELDS')
NEEDS = {'OmniBrowser.cpp': ('OMNI_KEYBOARD_V2', 'OMNI_KB_WORDS_V1', 'OMNI_KB_LAYOUTS_V1', 'OMNI_KB_EMOJI_V1',
                             'OMNI_KB_SHOWPW_V1', 'OMNI_CLIP_HISTORY_V1')}

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniKbLayouts.h" // OMNI_KB_LAYOUTS_V1: keyboard layouts, accent variants, UTF-8 (pure)\n',
         '#include "OmniKbLayouts.h" // OMNI_KB_LAYOUTS_V1: keyboard layouts, accent variants, UTF-8 (pure)\n'
         '#include "OmniKbFields.h" // OMNI_KB_FIELDS_V1: number / phone / one-time-code pads (pure)\n'),
        ('// Webpage fields ---------------------------------------------------------------------------------\n',
         '// OMNI_KB_FIELDS_V1: the number pad a webpage field gets (OmniKbFields.h: phone-style digits, tel * #, codes),\n'
         '// decided by omniKbProbeDone with the field kind (the probe\'s 9th part is autocomplete) and valid for that\n'
         '// keyboard session only. 0 (kNone) also in self-tests, dialogs, the address bar and off the number layer.\n'
         '// Reasons: tools/apply_kb_fields.py.\n'
         'namespace OKBF = OmniKbFields;\n'
         'static int omniKbfPad = 0, omniKbfSession = -1;\n'
         'static int omniKbfPadNow()\n'
         '{\n'
         '    if (omniTestMode() || omniKb.kind != 1 || omniKb.layer != omniKbNumpad || omniKb.field != omniKbFieldNumber) return OKBF::kNone;\n'
         '    return omniKbfSession == omniKb.session ? omniKbfPad : int(OKBF::kNone);\n'
         '}\n'
         '// Webpage fields ---------------------------------------------------------------------------------\n'),
        ("return [k,t,c(g('inputmode')),c(g('enterkeyhint')),dir,c(b),c(m),c(a)].join(S);\n",
         "return [k,t,c(g('inputmode')),c(g('enterkeyhint')),dir,c(b),c(m),c(a),c(g('autocomplete'))].join(S);\n"),
        ('        while (part.size() < 7) {\n',
         '        while (part.size() < 8) { // OMNI_KB_FIELDS_V1: 9 parts (autocomplete last)\n'),
        ('        if (part.size() != 8 || part[0] == "none") omniKb.mirrorValid = false;\n',
         '        if (part.size() != 9 || part[0] == "none") omniKb.mirrorValid = false; // OMNI_KB_FIELDS_V1: was 8\n'),
        ('                omniKb.field = f;\n',
         '                { // OMNI_KB_FIELDS_V1: the pad; a one-time-code text box becomes a number field\n'
         '                    const int pad = OKBF::settle(OKBF::padKind(k, type, mode, part[8]), f == omniKbFieldNumber,\n'
         '                        f == omniKbFieldText || f == omniKbFieldSearch);\n'
         '                    if (pad != OKBF::kNone) f = omniKbFieldNumber;\n'
         '                    omniKbfPad = pad;\n'
         '                    omniKbfSession = omniKb.session;\n'
         '                }\n'
         '                omniKb.field = f;\n'),
        ('    if (h == "done") return "Done";\n'
         '    return "Go";\n',
         '    if (h == "done") return "Done";\n'
         '    if (omniKbfPadNow()) return "Done"; // OMNI_KB_FIELDS_V1: the number pad\'s Enter key\n'
         '    return "Go";\n'),
        ('        + "|" + std::to_string(omniKblLayout()); // OMNI_KB_LAYOUTS_V1\n',
         '        + "|" + std::to_string(omniKblLayout()) // OMNI_KB_LAYOUTS_V1\n'
         '        + "|" + std::to_string(omniKbfPadNow()); // OMNI_KB_FIELDS_V1: which number pad\n'),
        ('// Rows 0-3 characters, row 4 quick keys (or the edit tools), row 5 actions; each row is 10 units wide.\n',
         '// OMNI_KB_FIELDS_V1: one row of the number pad from an OmniKbFields.h table (its kinds -> this keyboard\'s actions).\n'
         'static void omniKbfRow(std::vector<OmniKbKey>& row, const std::vector<OKBF::Key>& keys, const std::string& go)\n'
         '{\n'
         '    for (const OKBF::Key& k : keys) {\n'
         '        int a = omniKbInsert;\n'
         '        std::string label = k.label;\n'
         '        switch (k.kind) {\n'
         '        case OKBF::kDelete: a = omniKbBackKey; break;\n'
         '        case OKBF::kDone: a = omniKbGoKey; label = go; break;\n'
         '        case OKBF::kPaste: a = omniKbPasteKey; break;\n'
         '        case OKBF::kClips: a = OmniClipHistory::kKbKey; break;\n'
         '        case OKBF::kLayer: a = omniKbLayerKey; label = omniKbLayerLabel(); break;\n'
         '        case OKBF::kTools: a = omniKbToolsKey; break;\n'
         '        case OKBF::kSpace: a = omniKbSpaceKey; break;\n'
         '        case OKBF::kClose: a = omniKbCloseKey; break;\n'
         '        default: break;\n'
         '        }\n'
         '        row.push_back({ label, a == omniKbInsert ? std::string(k.label) : std::string(), a, k.units });\n'
         '    }\n'
         '}\n'
         '// Rows 0-3 characters, row 4 quick keys (or the edit tools), row 5 actions; each row is 10 units wide.\n'),
        ('    } else if (omniKb.layer == omniKbNumpad) {\n',
         '    } else if (omniKbfPadNow()) { // OMNI_KB_FIELDS_V1: the big pad (1 2 3 / 4 5 6 / 7 8 9 / Delete 0 Done, * 0 #, - 0 .)\n'
         '        for (int i = 0; i < 4; ++i) omniKbfRow(rows[size_t(i)], OKBF::gridRow(omniKbfPadNow(), i), go);\n'
         '    } else if (omniKb.layer == omniKbNumpad) {\n'),
        ('        act(quick, "Clear", omniKbClearKey, 1);\n'
         '    } else if (url) {\n',
         '        act(quick, "Clear", omniKbClearKey, 1);\n'
         '    } else if (omniKbfPadNow()) { // OMNI_KB_FIELDS_V1: tel + ( ) -, decimal , + e /, codes Paste Clips\n'
         '        omniKbfRow(quick, OKBF::quickRow(omniKbfPadNow()), go);\n'
         '    } else if (url) {\n'),
        ('    auto& action = rows[5];\n',
         '    auto& action = rows[5];\n'
         '    if (omniKbfPadNow()) { omniKbfRow(action, OKBF::actionRow(), go); return rows; } // OMNI_KB_FIELDS_V1: ABC Edit Space Delete Done Close\n'),
    ],
}


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


# The Controls guide's table names other patches' handlers by design: never a name clash.
GUIDE = ('OmniControlsHelp.h', 'OmniControlsHelpShell.h')
_CPP_TOK = re.compile(r'//[^\n]*|/\*.*?\*/|R"([^()\\\s"]{0,16})\(.*?\)\1"|"(?:\\.|[^"\\\n])*"' + r"|'(?:\\.|[^'\\\n])*'", re.S)


def cpp_code(s):
    """C/C++ text without its // and /* */ comments (string, char and raw string literals kept; newlines kept, so line
    numbers stay): a name in another patch's notes is not a use."""
    return _CPP_TOK.sub(lambda m: m.group(0) if m.group(0)[0] in 'R"\'' else '\n' * m.group(0).count('\n'), s)


def code_only(src):
    """A sibling apply_*.py without its comments and module docstring (line numbers kept): names mentioned only in its
    notes are not a use."""
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


def names_free():
    """Before a first apply: no other patch or tree file uses this patch's names (no ids: no settings row)."""
    name = re.compile('|'.join(NAMES))
    mine = {'OmniKbFields.h'}
    for f in sorted(HERE.glob('apply_*.py')):
        if f.name == Path(__file__).name:
            continue
        if f.name == 'apply_controls_help.py' or MARK in f.read_text(encoding='utf-8', errors='replace'):   # OMNI_SIBLING_SKIP: the guide quotes names; a patch built on this one uses them
            continue
        t = code_only(f.read_text(encoding='utf-8', errors='replace'))
        m = name.search(t)
        if m:
            sys.exit('%s already uses %r: pick other names' % (f.name, m.group(0)))
    for f in sorted(root.iterdir()):
        if f.name in mine or f.name in GUIDE or f.suffix not in ('.h', '.cpp', '.inc'):
            continue
        t = f.read_bytes().decode('utf-8', errors='replace')
        m = name.search(cpp_code(t))
        if m and MARK not in t:
            sys.exit('%s already uses %r: pick other names' % (f.name, m.group(0)))


def main():
    for fname, needs in NEEDS.items():
        s = (root / fname).read_bytes().decode('utf-8')
        for need in needs:
            if need not in s:
                sys.exit('%s: %s missing: apply its patch first' % (fname, need))
    if MARK not in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8'):
        names_free()
    for fname, edits in EDITS.items():   # every anchor is checked before anything is written
        check(fname, edits)
    pure = (HERE / 'OmniKbFields.h').read_text(encoding='utf-8')
    if MARK not in pure:
        sys.exit('OmniKbFields.h: %s missing' % MARK)
    msgs = [write_new('OmniKbFields.h', pure, 'OmniKbLayouts.h')]
    msgs += [patch(fname, edits) for fname, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
