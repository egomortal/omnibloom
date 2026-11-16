#!/usr/bin/env python3
"""OMNI_JS_TRIM_FIX_V1 (2026-11-16): page scripts that were cut into invalid JavaScript.

The bug class: a script template is a raw literal R"JS( ... )JS" whose source text ends "})()JS"". The raw string's
closing delimiter is ")JS"", so it eats the last ")" and the template really ends "})(". Code that then cuts two
characters (js.replace(js.size() - 2, 2, ...) / erase / substr) removes ")(" instead of "()", and the script handed
to WKPageEvaluateJavaScriptInMainFrame is a syntax error: it never runs, the callback gets an error, nothing happens.
Already fixed elsewhere (not touched here): omniFxContextQuery (apply_save_image.py, OMNI_SAVE_IMAGE_V1) and the
L2+Square copy script (apply_text_select.py, OMNI_TEXT_SELECT_V1).

Audit (every place in the fully patched tree that builds a page script from C++ strings: 70+ scripts extracted and
run through node --check): the only other broken one is the pointer snap of OmniPointerFeel.h.

  OmniPointerFeel.h  omniFxSnapRequest: "Pointer snaps to links" (Browser settings, default On). When the left
                     stick is released the pointer should ease onto the nearest link / button / field within ~36 px.
                     The hit-test script was "(function(){var X=..;return (function(x,y,R){...}(X,Y,R);})()" (the
                     inner function's "(" never closed): SyntaxError on every release, so the pointer never snapped.
                     Fix: cut "()" or "(" whichever the template ends with (as the two fixes above), then append.

Anchors (exactly once each; MARK makes the file idempotent):
  OmniPointerFeel.h   the 'js.replace(js.size() - 2, 2, "(X,Y,R);})()");' line of omniFxSnapRequest (whole line).
Tested by tools/test_js_trim_fix.cjs (node): assembles the patched script the way the patched code does, node-checks
it and runs it on a mock DOM.
usage: apply_js_trim_fix.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_JS_TRIM_FIX_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

EDITS = {
    'OmniPointerFeel.h': [
        ('    js.replace(js.size() - 2, 2, "(X,Y,R);})()");\n',
         '    if (js.size() >= 2 && js.compare(js.size() - 2, 2, "()") == 0) js.resize(js.size() - 2); /* ' + MARK + ': the template ends "})(" */\n'
         '    else if (!js.empty() && js.back() == \'(\') js.pop_back();\n'
         '    js += "(X,Y,R);})()";   /* call it with X, Y, R */\n'),
    ],
}


def variants(old0, s):
    """The anchor with the file's own line endings (mixed files: whichever spelling is present)."""
    for e in ('\r\n', '\n'):
        old = old0.replace('\n', e)
        if s.count(old):
            return old, e
    return old0, '\n'


def check(name, edits, mark=MARK):
    s = (root / name).read_bytes().decode('utf-8')
    if mark in s:
        return
    for old0, _ in edits:
        old, _e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))


def patch(name, edits, mark=MARK):
    p = root / name
    s = p.read_bytes().decode('utf-8')
    if mark in s:
        return name + ': already'
    for old0, new0 in edits:
        old, e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))
        s = s.replace(old, new0.replace('\n', e), 1)
    p.write_bytes(s.encode('utf-8'))
    return name + ': applied'


def main():
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
