#!/usr/bin/env python3
"""OMNI_KB_SHOWPW_V1 (2026-11-16): "Show password while typing" on Omni's on-screen keyboard (backlog E05).

What existed
  The keyboard (OMNI_KEYBOARD_V2) knows the field kind: a webpage field's type comes from the mirror probe
  (omniKbProbeDone: type=password -> omniKbFieldPassword), a dialog field is a password when its label contains
  "assword" (omniKbBegin; the sign-in modal's "Password (hidden)", the Passwords page's "Password", PIN prompts).
  In password fields the preview row (the text row above the keys, omniKbShown) draws one dot per character, Copy / Cut
  refuse ("Passwords can't be copied"; the copy script returns '' for type=password) and OMNI_KB_WORDS_V1 shows no
  chips and learns nothing. Long passwords typed blind with a controller fail often; there was no way to look.

What the user sees now
  - Password fields only: the edit-tools row (Touchpad) has "Show" where "Copy" was (Copy is useless there). Cross on it:
    the preview row shows the typed text instead of dots, the field name reads "Password (shown)" and the key becomes
    "Hide" (Cross again hides it). The hint bar's Touchpad label reads "Edit, Show" in password fields.
  - Off by default, for the current field only, never remembered: hidden again when the keyboard closes, when it moves
    to another field / dialog (a new keyboard session, omniKb.session), or when the field kind changes.
  - Only what the user typed in this keyboard session is ever shown (OmniKbShowPw::Guard, counts only, no text):
      * the field must have been seen empty in this session: a field that already held text when the keyboard opened
        (a saved login filled earlier, Passwords > edit a saved password, a page's pre-filled value) is refused with
        "Only text typed here can be shown: Clear the field, then type" (Clear empties it; what is typed after shows);
      * from then on the field may never hold more code points than the keyboard typed into it (keys, Space, Paste go
        through append(): counted there); more (a page script, anything else) hides it until seen empty again;
      * a saved login filled into the page (omniPwFill, every fill path of OmniPasswords / the vault: keyboard
        "Fill login" strip, Site settings > Fill saved login, page menu, Passwords page) and Undo (it can bring back
        what was there before) hide it at once (taint) until the field is seen empty again.
    So a saved password from the vault is never drawn in clear by this feature.
  - Never logged: no text is written anywhere; notices name no text ("Password shown in this field until the keyboard
    closes", "Password hidden"); the notice history (OMNI_NOTICE_HISTORY_V1) sees only those. Private tabs and guest mode:
    the same rules (nothing is stored in either).
Free buttons (why a key and not a button): omniKbButton gives every face button, L1/R1, L3/R3, Touchpad and Options a
keyboard job (Cross type, Square delete, Triangle space, Circle / Create close before it, L2/R2 word moves in
omniKbTick); the Controls guide (OmniControlsHelp.h, kKeyboard rows) lists them all. The edit-tools row already holds
the rarely used keys, and Copy is dead in password fields, so Show takes its place (the row stays 10 units).
Controls guide row to add (OmniControlsHelp.h is not edited here), after the "Clipboard history" row:
  { kKeyboard, { gTouchpad }, 0, false, "Show password: Edit > Show", "Password fields; typed text only, hidden when the keyboard closes", "omniKsp* (OMNI_KB_SHOWPW_V1)" },

Pure part: engine/entry/OmniKbShowPw.h (from tools/OmniKbShowPw.h: the guard, labels, notices). Tests:
  tools/test_kb_showpw.cpp (g++ -std=c++20 -Wall -Wextra -Werror -I. test_kb_showpw.cpp -o t && ./t).
Shell part: engine/entry/OmniKbShowPwShell.h (written by this script), namespace alias OKSP, names omniKsp*.
Ids: keyboard key action 7571 (OmniKbShowPw::kKbKey; checked unused in every apply_*.py and the tree).
Cost: nothing outside password fields; in one, a code point count of the mirror (<= 1200 bytes) when drawn.

Anchors (each once; whole lines; CRLF kept):
  OmniBrowser.cpp   the OmniClipHistory.h include line (pure include after); the omniKwFocused declaration (shell include
                    before: after omniKbEnsure / omniKbText); append()'s first two lines (typed count after); the
                    omniKbRows cache test (rows rebuilt when Show / Hide flips); the edit-tools Copy / Paste / Clips line
                    (Show / Hide in password fields); 'case omniKbUndoKey:' (Show case before, taint after); the dots
                    test in omniKbShown; omniKbFieldName's dialog and password lines; omniKbHints' Touchpad line
  OmniPasswords.h   'omniPw.list[index].used = time(nullptr);' in omniPwFill (taint before)
Apply AFTER apply_kb_words.py, apply_kb_layouts.py, apply_kb_emoji.py, apply_clip_history.py.
usage: apply_kb_showpw.py <engine tree>   (anchored, idempotent, keeps each file's line endings; re-run: "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_KB_SHOWPW_V1'
HERE = Path(__file__).resolve().parent
root = Path(sys.argv[1]) / 'engine' / 'entry'
IDS = ('7571',)
NAMES = ('OKSP', 'omniKsp', 'OmniKbShowPw')

SHELL = r'''// OMNI_KB_SHOWPW_V1: "Show password while typing" (shell side). Included from OmniBrowser.cpp (inside its anonymous
// namespace) right after the keyboard's session code (omniKbEnsure). Pure part: OmniKbShowPw.h; reasons in
// tools/apply_kb_showpw.py. Only text typed into this field in this keyboard session is ever shown; the guard keeps
// counts, never text; nothing is written or logged. Main thread only.
#pragma once

namespace OKSP = OmniKbShowPw;

static OKSP::Guard omniKsp;
// The keyboard is editing a password field (a webpage field the mirror says is type=password, or a dialog's).
static bool omniKspPassword() { return editing && (omniKb.kind == 1 || omniKb.kind == 2) && omniKb.field == omniKbFieldPassword; }
// The field's length in code points as known now; false while a webpage field hasn't been read.
static bool omniKspLength(size_t& n)
{
    if (omniKb.kind == 1) {
        if (!omniKb.mirrorValid) return false;
        n = OKSP::cpCount(omniKb.before);
        if (!omniKb.mirrorNoSel) n += OKSP::cpCount(omniKb.selected) + OKSP::cpCount(omniKb.after);
        return true;
    }
    const std::string* t = omniKbText();
    if (!t) return false;
    n = OKSP::cpCount(*t);
    return true;
}
// A new session or field starts hidden (closing the keyboard bumps the session); then the field is read.
static void omniKspObserve()
{
    if (!omniKspPassword()) return;
    if (!omniKsp.same(omniKb.session, omniKb.field)) omniKsp.reset(omniKb.session, omniKb.field);
    size_t n = 0;
    if (omniKspLength(n)) omniKsp.observe(n);
}
static bool omniKspReveal()
{
    if (!omniKspPassword()) return false;
    omniKspObserve();
    return omniKsp.reveal();
}
// append(): the keyboard inserts `value` (keys, Space, Paste, emoji) into the field.
static void omniKspTyped(const std::string& value)
{
    if (!omniKspPassword()) return;
    omniKspObserve();
    omniKsp.typed(OKSP::cpCount(value));
}
// A saved login is being filled into the page, or Undo: hidden until the field is seen empty again.
static void omniKspTaint()
{
    omniKsp.taint();
    omniShellDirty = true;
}
// The edit-tools row's Show / Hide key.
static void omniKspToggle()
{
    if (!omniKspPassword()) return;
    omniKspObserve();
    notice(OKSP::toggleNotice(omniKsp.toggle()));   // fixed texts only: never the password
    omniShellDirty = true;
}
// omniKbRows' cache: rebuilt when the key's label (Show / Hide) flips.
static bool omniKspRowsStale()
{
    static int last = -1;
    const int now = omniKspReveal() ? 1 : 0;
    if (now == last) return false;
    last = now;
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniClipHistory.h" // OMNI_CLIP_HISTORY_V1: clipboard history (pure: ring of 10, private rule, labels)\n',
         '#include "OmniClipHistory.h" // OMNI_CLIP_HISTORY_V1: clipboard history (pure: ring of 10, private rule, labels)\n'
         '#include "OmniKbShowPw.h" // ' + MARK + ': show password while typing (pure: typed-text guard, labels)\n'),
        ('static bool omniKwFocused();   // OMNI_KB_WORDS_V1: the word chips have the focus\n',
         '#include "OmniKbShowPwShell.h" // ' + MARK + ': show password while typing (edit row Show / Hide, typed text only)\n'
         'static bool omniKwFocused();   // OMNI_KB_WORDS_V1: the word chips have the focus\n'),
        ('void append(const std::string& value) {\n'
         '    omniKbEnsure(); // OMNI_KEYBOARD_V2: inserts at the caret (replacing a selection)\n',
         'void append(const std::string& value) {\n'
         '    omniKbEnsure(); // OMNI_KEYBOARD_V2: inserts at the caret (replacing a selection)\n'
         '    omniKspTyped(value); // ' + MARK + ': counts what the keyboard typed into a password field\n'),
        ('    if (key == builtFor && !rows.empty()) return rows;\n',
         '    if (omniKspRowsStale()) builtFor.clear(); // ' + MARK + ': the Show / Hide key flipped\n'
         '    if (key == builtFor && !rows.empty()) return rows;\n'),
        ('        act(quick, "Copy", omniKbCopyKey, 1); act(quick, "Paste", omniKbPasteKey, 1); act(quick, "Clips", OmniClipHistory::kKbKey, 1);\n',
         '        // ' + MARK + ': password fields get Show / Hide where Copy is (passwords can\'t be copied)\n'
         '        if (omniKb.field == omniKbFieldPassword) act(quick, OmniKbShowPw::keyLabel(omniKspReveal()), OmniKbShowPw::kKbKey, 1);\n'
         '        else act(quick, "Copy", omniKbCopyKey, 1);\n'
         '        act(quick, "Paste", omniKbPasteKey, 1); act(quick, "Clips", OmniClipHistory::kKbKey, 1);\n'),
        ('    case omniKbUndoKey:\n',
         '    case OmniKbShowPw::kKbKey: omniKb.select = false; omniKspToggle(); return; // ' + MARK + '\n'
         '    case omniKbUndoKey:\n'
         '        omniKspTaint(); // ' + MARK + ': Undo may bring back text from before: hidden until the field is empty\n'),
        ('        if (omniKb.field == omniKbFieldPassword) {\n',
         '        if (omniKb.field == omniKbFieldPassword && !omniKspReveal()) { // ' + MARK + ': dots unless Show (typed text only)\n'),
        ('    if (omniKb.kind == 2) return omniKbLabel;\n',
         '    if (omniKb.kind == 2) return omniKspReveal() ? OmniKbShowPw::shownLabel(omniKbLabel) : std::string(omniKbLabel); // ' + MARK + '\n'),
        ('    case omniKbFieldPassword: return "Password";\n',
         '    case omniKbFieldPassword: return omniKspReveal() ? OmniKbShowPw::shownLabel("Password") : std::string("Password"); // ' + MARK + '\n'),
        ('    if (ps) { pill("Touchpad"); label(omniKb.kind == 0 ? "Sites" : "Edit"); }\n',
         '    if (ps) { pill("Touchpad"); label(omniKb.kind == 0 ? "Sites" : omniKb.field == omniKbFieldPassword ? "Edit, Show" : "Edit"); } // ' + MARK + '\n'),
    ],
    'OmniPasswords.h': [
        ('    omniPw.list[index].used = time(nullptr);\n',
         '    omniKspTaint(); // ' + MARK + ': a saved password goes into the page: the keyboard\'s Show never shows it\n'
         '    omniPw.list[index].used = time(nullptr);\n'),
    ],
}
NEEDS = {'OmniBrowser.cpp': ('OMNI_KEYBOARD_V2', 'OMNI_KB_WORDS_V1', 'OMNI_KB_LAYOUTS_V1', 'OMNI_KB_EMOJI_V1',
                             'OMNI_CLIP_HISTORY_V1')}


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


def ids_free():
    """Before a first apply: no other patch or tree file uses this patch's ids or names."""
    word = re.compile(r'\b(%s)\b' % '|'.join(IDS))
    name = re.compile('|'.join(NAMES))
    mine = {'OmniKbShowPw.h', 'OmniKbShowPwShell.h'}
    for f in sorted(HERE.glob('apply_*.py')):
        if f.name == Path(__file__).name:
            continue
        if f.name == 'apply_controls_help.py' or MARK in f.read_text(encoding='utf-8', errors='replace'):   # OMNI_SIBLING_SKIP: the guide quotes names; a patch built on this one uses them
            continue
        t = code_only(f.read_text(encoding='utf-8', errors='replace'))
        m = name.search(t)   # numeric ids: engine tree only (a sibling's notes list other patches' ids)
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
    if MARK not in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8'):
        ids_free()
    for fname, edits in EDITS.items():   # every anchor is checked before anything is written
        check(fname, edits)
    pure = (HERE / 'OmniKbShowPw.h').read_text(encoding='utf-8')
    if MARK not in pure:
        sys.exit('OmniKbShowPw.h: %s missing' % MARK)
    msgs = [write_new('OmniKbShowPw.h', pure, 'OmniClipHistory.h'),
            write_new('OmniKbShowPwShell.h', SHELL, 'OmniClipHistoryShell.h')]
    msgs += [patch(fname, edits) for fname, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
