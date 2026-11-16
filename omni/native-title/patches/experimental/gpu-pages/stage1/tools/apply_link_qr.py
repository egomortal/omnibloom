#!/usr/bin/env python3
"""OMNI_LINK_QR_V1 (2026-11-16): "Show link as QR code" in the hold-Cross page menu over a link, so a phone opens the
link under the pointer, not just the page (backlog E09).

What the user sees
  - Hold Cross with the pointer over a link: a new row "Show link as QR code" right after "Copy link address".
    Only for http(s) links with a host; never for javascript: (the page script already drops those), data:, blob:,
    omni:, about:, file:, mailto: or addresses carrying a user / password (they would be shown on the TV).
  - Cross on it: the existing QR panel (OMNI_QR_SHARE_V1, OmniQrShareShell.h) opens with the LINK's address as the
    code, the heading "Scan to open this link on your phone" (the panel's title field, OMNI_TEXT_SELECT_V1), the
    shortened address under it and "Tracking parameters removed" when any were (the same cleaner, OmniQr::cleanURL).
    Circle closes, as before. Nothing is stored; private tabs too, as the page QR.
  - A link over 666 bytes after cleaning (version 20, level M) gets a notice instead, like the page QR.
  The page script (omniFxContextScript) is not touched: it already reports the link (a.href, absolute) under the
  pointer, as apply_save_image.py documents.

Pure part: tools/OmniLinkQr.h, copied to engine/entry (scheme filter, length cap, row id 977). Tests:
  g++ -std=c++20 -Wall -Wextra -I tools -I <tree>/engine/entry tools/test_link_qr.cpp -o t && ./t
  (with the tree on the include path it also checks kMaxBytes == OmniQr::maxBytes()).
Shell part: engine/entry/OmniLinkQrShell.h (omniLqrShow), included from OmniFeatures3.h right after
OmniQrShareShell.h (it fills that file's omniQr panel state). Namespace alias OLQR (function scope).
Anchors (each exactly once; whole lines kept, our lines inserted after them; MARK makes each file idempotent):
  OmniBrowser.cpp     the OmniQrShare.h include line (pure include after it)
  OmniContextMenu.h   'static bool omniQrContextAction(int id);' (declaration after); the "Copy link address" add()
                      line (row after); the 'if (omniQrContextAction(r.id)) return true;' line (action after)
  OmniFeatures3.h     the OmniQrShareShell.h include line (shell include after it)
Apply AFTER apply_qr_share.py, apply_text_select.py (the panel's title field) and apply_save_image.py.
Ids / names: refuses to apply when another patch or tree file already uses row id 977 or the omniLqr / OmniLinkQr
names (comments and notes are not uses; siblings are checked for row-id assignments of 977).
usage: apply_link_qr.py <engine tree>   (anchored, idempotent, keeps each file's line endings; re-run: "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_LINK_QR_V1'
HERE = Path(__file__).resolve().parent
root = Path(sys.argv[1]) / 'engine' / 'entry'
IDS = ('977',)
NAMES = (r'\bomniLqr\w*', r'\bOmniLinkQr\w*', r'\bOLQR\b')

SHELL = r'''// OMNI_LINK_QR_V1: "Show link as QR code" (shell side). Included from OmniFeatures3.h (inside OmniBrowser.cpp's
// anonymous namespace, right after OmniQrShareShell.h, whose panel it opens). Pure part: OmniLinkQr.h; reasons in
// tools/apply_link_qr.py. Main thread only; nothing is stored anywhere.
#pragma once

// Hold Cross over a link > "Show link as QR code": the QR panel with the link (tracking parameters dropped).
static void omniLqrShow(const std::string& link)
{
    namespace OLQR = OmniLinkQr;
    const OLQR::Check first = OLQR::check(link);
    if (first == OLQR::Check::Empty || first == OLQR::Check::NotWeb) { notice("Only web links can be shown as a QR code"); return; }
    const std::string url = OQR::cleanURL(link);
    OQR::Code code;
    if (OLQR::check(url) != OLQR::Check::Ok || !OQR::encode(url, code)) {
        notice("This link is too long for a QR code (" + std::to_string(url.size()) + " characters, at most " + std::to_string(OLQR::kMaxBytes) + ")");
        return;
    }
    omniFxCloseAll();
    omniQr = OmniQrState();
    omniQr.code = std::move(code);
    omniQr.shown = OQR::shownURL(url);
    omniQr.trimmed = url != link;
    omniQr.title = "Scan to open this link on your phone";
    omniQr.open = true;
    omniShellDirty = true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniQrShare.h" // OMNI_QR_SHARE_V1: Show QR code (pure encoder)\n',
         '#include "OmniQrShare.h" // OMNI_QR_SHARE_V1: Show QR code (pure encoder)\n'
         '#include "OmniLinkQr.h" /* ' + MARK + ': Show link as QR code (pure: scheme filter, length cap) */\n'),
    ],
    'OmniContextMenu.h': [
        ('static bool omniQrContextAction(int id);\n',
         'static bool omniQrContextAction(int id);\n'
         'static void omniLqrShow(const std::string& link); /* ' + MARK + ' (OmniLinkQrShell.h) */\n'),
        ('        add(omniCxCopyLink, "Copy link address");\n',
         '        add(omniCxCopyLink, "Copy link address");\n'
         '        if (OmniLinkQr::offered(p.link)) add(OmniLinkQr::kContextId, "Show link as QR code"); /* ' + MARK + ': http(s) only */\n'),
        ('    if (omniQrContextAction(r.id)) return true; // OMNI_QR_SHARE_V1\n',
         '    if (omniQrContextAction(r.id)) return true; // OMNI_QR_SHARE_V1\n'
         '    if (r.id == OmniLinkQr::kContextId) { omniLqrShow(p.link); return true; } /* ' + MARK + ' */\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniQrShareShell.h" // OMNI_QR_SHARE_V1\n',
         '#include "OmniQrShareShell.h" // OMNI_QR_SHARE_V1\n'
         '#include "OmniLinkQrShell.h" /* ' + MARK + ': Show link as QR code */\n'),
    ],
}
NEEDS = {'OmniBrowser.cpp': ('OMNI_QR_SHARE_V1', 'OMNI_SAVE_IMAGE_V1'),
         'OmniContextMenu.h': ('OMNI_QR_SHARE_V1', 'OMNI_SAVE_IMAGE_V1'),
         'OmniQrShareShell.h': ('OMNI_TEXT_SELECT_V1',),
         'OmniFeatures3.h': ('OMNI_QR_SHARE_V1',)}


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
    """Before a first apply: no other patch, sibling pure header or tree file uses this patch's ids or names."""
    word = re.compile(r'\b(%s)\b' % '|'.join(IDS))
    name = re.compile('|'.join(NAMES))
    # A sibling's row-id assignment ("kContextId = 977", "r.id = 977", "Id = 977;") even inside its C++ text; bare
    # numbers in its notes ("pinned 960, QR 975") are not.
    assign = re.compile(r'\b\w*(?:id|Id|ID)\w*\s*(?:=|\{|\()\s*(%s)\b' % '|'.join(IDS))
    mine = {'OmniLinkQr.h', 'OmniLinkQrShell.h'}
    for f in sorted(HERE.glob('apply_*.py')):
        if f.name == Path(__file__).name:
            continue
        if f.name == 'apply_controls_help.py' or MARK in f.read_text(encoding='utf-8', errors='replace'):   # OMNI_SIBLING_SKIP: the guide quotes names; a patch built on this one uses them
            continue
        t = code_only(f.read_text(encoding='utf-8', errors='replace'))
        m = name.search(t) or assign.search(cpp_code(t))
        if m:
            sys.exit('%s already uses %r: pick other ids / names' % (f.name, m.group(0)))
    for f in sorted(HERE.glob('*.h')):   # pure headers kept next to the patches (copied into the tree at apply time)
        if f.name in mine:
            continue
        c = cpp_code(f.read_text(encoding='utf-8', errors='replace'))
        m = word.search(c) or name.search(c)
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
    pure = (HERE / 'OmniLinkQr.h').read_text(encoding='utf-8')
    if MARK not in pure:
        sys.exit('OmniLinkQr.h: %s missing' % MARK)
    msgs = [write_new('OmniLinkQr.h', pure, 'OmniQrShare.h'),
            write_new('OmniLinkQrShell.h', SHELL, 'OmniQrShareShell.h')]
    msgs += [patch(fname, edits) for fname, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
