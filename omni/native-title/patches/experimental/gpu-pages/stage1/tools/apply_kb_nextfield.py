#!/usr/bin/env python3
"""OMNI_KB_NEXTFIELD_V1 (2026-11-16): previous / next text box from the on-screen keyboard (backlog E19).

What existed (audited in the patched tree after the recipe chain + apply_kb_showpw.py + apply_kb_fields.py)
  - No field-to-field move anywhere: OMNI_KEYBOARD_V2 edits one webpage field per keyboard session (omniKb.session,
    bumped by omniKbBegin); Go sends Enter (submits most forms), Close / Circle / Create keep the field.
    apply_spatial_nav.py moves a ring between links / fields while BROWSING only (never while the keyboard is open,
    and it opens the keyboard on Cross); apply_kb_words.py / apply_kb_fields.py / apply_kb_layouts.py /
    apply_kb_emoji.py / apply_kb_showpw.py / apply_clip_history.py add no traversal.
  - Every pad button already has a keyboard meaning (omniKbButton): Cross type, Square delete, Triangle space,
    Options Go, Circle / Create close, L1 / R1 cursor (held: repeat), L2 / R2 cursor by word (triggers, on press),
    right stick cursor / scroll, L3 Shift, R3 symbols / letters, touchpad Edit tools, D-pad keys. The shoulder chord
    (L1 + R1 together, OMNI_SHOULDER_DOWNLOADS_V1) is off while editing; the L2 chords, the tab strip (L2 + L1 / R1)
    and the magnifier (L2 + L3) are browsing-only. Nothing reads L3 as HELD anywhere.
  - So the chord is HOLD L3 + L1 / R1: L3's own press (Shift) still happens, and the chord puts Shift back as it was
    (a move restarts the keyboard on letters with Shift off anyway). L1 / R1 never move the cursor while L3 is held,
    and hold-to-repeat is cancelled for the chord (one text box per press).

What the user sees
  - Keyboard open on a webpage text box, hold L3: the hint bar becomes  [L3] Held  [L1][R1] Previous / Next text box
    [Circle] Close  ("Previous / Done" on the last text box; the position is read when L3 goes down).
  - Hold L3 + R1: the text box after this one in document order (as Tab) gets the focus, caret at its end. The typed
    text is already in the field (WebKit editing commands), and moving the focus blurs it, so the page sees its usual
    change event. The keyboard restarts on the new field: its kind, layout and number pad come from the existing
    probe (an e-mail box opens with @ keys, a phone box on the OMNI_KB_FIELDS_V1 pad, a password with Show / Hide),
    and the field is scrolled above the keyboard as on a first open.
  - Hold L3 + R1 on the last text box: Done: the keyboard closes (as Close: no Enter, nothing submitted).
  - Hold L3 + L1: the previous text box; on the first one: notice "This is the first text box".
  - No text box to go to / the page refused the focus: notice "No other text box here".
  - Text boxes: <input> that types text (text, search, email, url, tel, password, number, untyped ...), <textarea>,
    contenteditable roots. Skipped: hidden, disabled (also by a disabled fieldset), read-only, tabindex -1, inside
    [inert], not rendered, visibility hidden, empty, or parked above / left of the page (spam traps); checkbox, radio,
    buttons, file, range, colour and date / time pickers.
  - Frames: the script finds the focused field like the keyboard's probe (activeElement through at most 4
    same-origin iframes) and moves within THAT document only: a form inside a frame works the same way, but the move
    never crosses into another frame or out to the parent. (The probe's "scroll above the keyboard" is top-document
    only, as before.) Self-tests (omniTestMode) and the address bar / dialog fields: L3 and L1 / R1 as before.

Pure part: OmniKbNextField.h (kept in tools/, copied into engine/entry): the page script, its answer, the step, the
hint label, the Shift undo, the busy window. Tested by tools/test_kb_nextfield.cpp:
    g++ -std=c++20 -Wall -Wextra -I. test_kb_nextfield.cpp -o t && ./t   (in tools/)
Shell side: OmniBrowser.cpp only (namespace alias OKNF, names omniKnf*). No settings row, no file, no new import.

Anchors in OmniBrowser.cpp (exactly once each, whole lines; MARK makes it idempotent; CRLF / LF kept):
  the OmniKbFields.h include (apply_kb_fields.py's)                      -> + OmniKbNextField.h include
  "// Every controller button while the keyboard is open ..." comment   -> state, script runner, omniKnfButton before it
  omniKbButton's emoji-page line (apply_kb_emoji.py's)                   -> omniKnfButton(b) first
  omniKbHints' clipboard-list line (apply_clip_history.py's)             -> the L3-held hint after it
Apply AFTER apply_kb_fields.py (last in the chain).
usage: apply_kb_nextfield.py <engine tree>   (re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_KB_NEXTFIELD_V1'
HERE = Path(__file__).resolve().parent
if len(sys.argv) != 2:
    sys.exit('usage: apply_kb_nextfield.py <engine tree>')
root = Path(sys.argv[1]) / 'engine' / 'entry'
NAMES = ('OKNF', 'omniKnf', 'OmniKnf', 'OmniKbNextField', 'OMNI_KB_NEXTFIELD')
# Other patches' names, spelled in two parts: their names_free() scans every apply_*.py's code, and a whole name here
# (in an anchor) would make apply_kb_fields.py / apply_clip_history.py refuse to apply on a fresh tree.
KBF_MARK = 'OMNI_KB_' + 'FIELDS_V1'
KBF_INCLUDE = '#include "OmniKb' + 'Fields.h" // ' + KBF_MARK + ': number / phone / one-time-code pads (pure)\n'
CLH_HINTS = ('    if (omni' + 'ClhKbShown()) { face(0, "Paste"); face(2, "Remove"); face(1, "Close"); pill("D-pad"); '
             'label("Choose"); return; } // OMNI_CLIP_HISTORY_V1\n')
NEEDS = {'OmniBrowser.cpp': ('OMNI_KEYBOARD_V2', 'OMNI_KB_WORDS_V1', 'OMNI_KB_EMOJI_V1', 'OMNI_CLIP_HISTORY_V1',
                             KBF_MARK)}

EDITS = {
    'OmniBrowser.cpp': [
        (KBF_INCLUDE,
         KBF_INCLUDE +
         '#include "OmniKbNextField.h" // OMNI_KB_NEXTFIELD_V1: previous / next text box page script (pure)\n'),
        ('// Every controller button while the keyboard is open (Circle and Create close it before this).\n',
         '// OMNI_KB_NEXTFIELD_V1: hold L3 + L1 / R1 while the keyboard edits a webpage text box: the previous / next text box\n'
         '// in document order, in the document (frame) that holds this one (OmniKbNextField.h). The typed text is already in\n'
         '// the field; the move blurs it (the page\'s change event) and the keyboard restarts on the new field (its kind,\n'
         '// layout and pad from the probe). On the last text box R1 is Done (closes, no Enter). Reasons:\n'
         '// tools/apply_kb_nextfield.py.\n'
         'namespace OKNF = OmniKbNextField;\n'
         'struct OmniKnfState {\n'
         '    int capsBefore = 0, l3Session = -1;     // Shift before the L3 press, and its keyboard session\n'
         '    int countSession = -1, index = -1, total = 0;   // where the text box is (the hint\'s Next / Done)\n'
         '    int dir = 0;                            // the move being answered: +1 next, -1 previous\n'
         '    bool waiting = false;\n'
         '    uint32_t since = 0;\n'
         '};\n'
         'static OmniKnfState omniKnf;\n'
         'static void omniKnfRun(char mode)\n'
         '{\n'
         '    if (!active()) return;\n'
         '    auto script = adoptWK(WKStringCreateWithUTF8CString(OKNF::script(mode).c_str()));\n'
         '    WKPageEvaluateJavaScriptInMainFrame(active()->page, script.get(), reinterpret_cast<void*>(intptr_t(omniKb.session) * 2 + (mode != \'c\')), [](WKTypeRef result, WKErrorRef error, void* context) {\n'
         '        const std::string text = !error && result && WKGetTypeID(result) == WKStringGetTypeID() ? OmniTest::toStd(static_cast<WKStringRef>(result)) : std::string();\n'
         '        const OKNF::Result r = OKNF::parse(text);\n'
         '        const bool move = (intptr_t(context) & 1) != 0;   // low bit: a move (else the L3 count)\n'
         '        if (move) omniKnf.waiting = false;\n'
         '        if (!editing || !pageEditing || omniKb.kind != 1 || intptr_t(context) / 2 != omniKb.session) return;   // moved on\n'
         '        if (!move && r.kind != OKNF::kCount) return;   // a count that failed: no hint change, no notice\n'
         '        omniShellDirty = true;\n'
         '        switch (move ? OKNF::step(r, omniKnf.dir) : int(OKNF::sStay)) {\n'
         '        case OKNF::sStay: break;\n'
         '        case OKNF::sReopen: omniKbBegin(1, active()); break;   // a new session: letters / pad, probe, scroll\n'
         '        case OKNF::sDone: dismissKeyboard(); return;\n'
         '        case OKNF::sFirst: notice(OKNF::kFirstNotice); break;\n'
         '        default: notice(OKNF::kNoneNotice); return;\n'
         '        }\n'
         '        omniKnf.countSession = omniKb.session; omniKnf.index = r.index; omniKnf.total = r.total;\n'
         '    });\n'
         '}\n'
         'static bool omniKnfHeld()\n'
         '{\n'
         '    return omniKb.kind == 1 && !omniTestMode() && controller && SDL_GameControllerGetButton(controller, SDL_CONTROLLER_BUTTON_LEFTSTICK);\n'
         '}\n'
         'static const char* omniKnfNextLabel() { return OKNF::nextLabel(omniKnf.countSession == omniKb.session, omniKnf.index, omniKnf.total); }\n'
         '// omniKbButton, first: true when the chord used the button. L3 itself still types Shift (remembered for the undo).\n'
         'static bool omniKnfButton(int b)\n'
         '{\n'
         '    if (omniKb.kind != 1 || omniTestMode() || !controller) return false;\n'
         '    if (b == SDL_CONTROLLER_BUTTON_LEFTSTICK) {\n'
         '        if (omniKbRepeating) return false;\n'
         '        omniKnf.capsBefore = omniKb.caps; omniKnf.l3Session = omniKb.session;\n'
         '        omniKnfRun(\'c\');   // the hint: Next text box, or Done on the last one\n'
         '        return false;\n'
         '    }\n'
         '    if ((b != SDL_CONTROLLER_BUTTON_LEFTSHOULDER && b != SDL_CONTROLLER_BUTTON_RIGHTSHOULDER) || !omniKnfHeld()) return false;\n'
         '    omniKbRepeatButton = -1;   // one text box per press, never the cursor repeat\n'
         '    if (omniKbRepeating) return true;\n'
         '    omniKb.caps = OKNF::capsAfterChord(omniKb.caps, omniKnf.capsBefore, omniKnf.l3Session == omniKb.session);\n'
         '    shift = omniKb.caps != 0;\n'
         '    omniKnf.l3Session = -1;\n'
         '    const uint32_t now = SDL_GetTicks();\n'
         '    if (OKNF::busy(omniKnf.waiting, omniKnf.since, now)) return true;   // the last move is still being answered\n'
         '    omniKnf.waiting = true; omniKnf.since = now;\n'
         '    omniKnf.dir = b == SDL_CONTROLLER_BUTTON_RIGHTSHOULDER ? 1 : -1;\n'
         '    omniKnfRun(omniKnf.dir > 0 ? \'n\' : \'p\');\n'
         '    return true;\n'
         '}\n'
         '// Every controller button while the keyboard is open (Circle and Create close it before this).\n'),
        ('    if (omniKemOn()) { omniKemButton(b); return; } // OMNI_KB_EMOJI_V1: the emoji page (before the word chips)\n',
         '    if (omniKnfButton(b)) return; // OMNI_KB_NEXTFIELD_V1: hold L3 + L1 / R1: previous / next text box\n'
         '    if (omniKemOn()) { omniKemButton(b); return; } // OMNI_KB_EMOJI_V1: the emoji page (before the word chips)\n'),
        (CLH_HINTS,
         CLH_HINTS +
         '    if (omniKnfHeld()) { pill(ps ? "L3" : "LS"); label("Held"); shoulders(std::string("Previous / ") + omniKnfNextLabel()); face(1, "Close"); return; } // OMNI_KB_NEXTFIELD_V1\n'),
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
    mine = {'OmniKbNextField.h'}
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
    pure = (HERE / 'OmniKbNextField.h').read_text(encoding='utf-8')
    if MARK not in pure:
        sys.exit('OmniKbNextField.h: %s missing' % MARK)
    msgs = [write_new('OmniKbNextField.h', pure, 'OmniBrowser.cpp')]
    msgs += [patch(fname, edits) for fname, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
