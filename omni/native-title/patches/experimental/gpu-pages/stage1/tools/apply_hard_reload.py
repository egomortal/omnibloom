#!/usr/bin/env python3
"""OMNI_HARD_RELOAD_V1 (2026-11-16): "Reload without cache" (backlog E06) in the hold-Cross page menu and Options > Browse.

What existed (grep of the patched tree, recipe chain_final)
  Every reload in the shell is WKPageReload (context menu omniCxReload, Options omniQmReload, button map, error page...):
  a normal reload that may revalidate from the HTTP cache. A site stuck on a bad cached script / stylesheet stayed stuck
  until "Clear browsing data". WebKit's C API has WKPageReloadFromOrigin (WKPage.h, WK_EXPORT, real body in
  WKPage.cpp: page->reload(ReloadOption::FromOrigin)); this port already calls it (OmniYtGuard.h,
  OMNI_YT_ATTEST_GUARD_V1), so it is exported and linked in the title. No new import, no child change.

What the user sees now
  - Hold Cross on a page (no link / image under the pointer): after "Reload" a row "Reload without cache".
  - Options > Browse: after "Reload" / "Stop" a row "Reload without cache".
  Cross: the menus close, the tab reloads bypassing the cache (WKPageReloadFromOrigin) and the notice
  "Reloaded without cache" shows. Cookies and site data are untouched.
  The rows are only there for ordinary web pages (http / https with a host): never on omni:// built-in pages
  (omniPagesTab), the new-tab page, about: / data: / file: / blob: pages, or a crashed tab (its normal Reload restarts
  the web process). Private tabs work the same (their own non-persistent store).

Pure part: engine/entry/OmniHardReload.h (from tools/OmniHardReload.h: ids, texts, which pages get the row).
  Tests: tools/test_hard_reload.cpp (g++ -std=c++20 -Wall -Wextra -Werror -I. test_hard_reload.cpp -o t && ./t).
Shell part: engine/entry/OmniHardReloadShell.h (written by this script), namespace alias OHRL, names omniHrl*.
Ids: context row 7741, Options row 8741 (checked unused in every apply_*.py's code, tools/*.h and the tree; 8741 >= 900,
  so its quick-menu hook sits before the `r.id >= 900` line).

Anchors (each once; whole lines; new lines inserted after them; CRLF / LF kept):
  OmniBrowser.cpp     the OmniBfList.h include line (pure include after); the OmniBfListShell.h include line (shell after)
  OmniContextMenu.h   the omniImvContextAction declaration (declarations after); the omniCxReload add() line (row after);
                      the omniImvContextAction call in omniFxContextInput (action after)
  OmniQuickMenu.h     the omniBflQuickAction declaration (declarations after); the Reload / Stop add() line (row after);
                      the OmniBfList::kQuickRowId omniMqGroup case (Browse case after); the omniBflQuickAction input
                      line (input after)
Controls guide (OmniControlsHelp.h) is not edited.
Apply AFTER apply_bf_list.py and apply_image_viewer.py (their lines are anchors).
usage: apply_hard_reload.py <engine tree>   (anchored, idempotent, keeps each file's line endings; re-run: "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_HARD_RELOAD_V1'
HERE = Path(__file__).resolve().parent
if len(sys.argv) != 2:
    sys.exit('usage: apply_hard_reload.py <engine tree>')
root = Path(sys.argv[1]) / 'engine' / 'entry'
IDS = ('7741', '8741')
NAMES = ('OHRL', 'omniHrl', 'OmniHardReload', 'OMNI_HARD_RELOAD')

SHELL = r'''// OMNI_HARD_RELOAD_V1: "Reload without cache" (shell side): hold-Cross page menu and Options > Browse. Included from
// OmniBrowser.cpp after OmniBfListShell.h. The pure part is OmniHardReload.h; the reasons are in
// tools/apply_hard_reload.py. WKPageReloadFromOrigin is exported and already linked (OmniYtGuard.h uses it).
#pragma once

namespace OHRL = OmniHardReload;

static bool omniHrlOffered(const Tab* t)
{
    return t && OHRL::offered(t->url, t->omniPagesTab, t->omniNewTabPage, t->crashed);
}
static void omniHrlRun()
{
    Tab* t = active();
    if (!omniHrlOffered(t)) return;   // checked again: the tab may have changed under the open menu
    fprintf(stderr, "OMNI HARD RELOAD: %s\n", t->omniPrivate ? "(private tab)" : t->url.c_str()); fflush(stderr);
    WKPageReloadFromOrigin(t->page);
    notice(OHRL::kNotice);
    omniShellDirty = true;
}
static void omniHrlAddRow(OmniFxPanel& p, int id)
{
    if (!omniHrlOffered(active())) return;   // web pages only: never omni:// / new-tab / about: / crashed
    OmniFxRow r;
    r.id = id;
    r.label = OHRL::kLabel;
    r.icon = omniIconReload;
    p.rows.push_back(r);
}
static void omniHrlContextRow(OmniFxPanel& p) { omniHrlAddRow(p, OHRL::kContextRowId); }
static void omniHrlQuickRow(OmniFxPanel& p) { omniHrlAddRow(p, OHRL::kQuickRowId); }
static bool omniHrlAction(int id)
{
    if (id != OHRL::kContextRowId && id != OHRL::kQuickRowId) return false;
    omniFxCloseAll();
    omniHrlRun();
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniBfList.h" // OMNI_BF_LIST_V1: Back history list model and hold timing (pure)\n',
         '#include "OmniBfList.h" // OMNI_BF_LIST_V1: Back history list model and hold timing (pure)\n'
         '#include "OmniHardReload.h" // OMNI_HARD_RELOAD_V1: Reload without cache (pure)\n'),
        ('#include "OmniBfListShell.h" /* OMNI_BF_LIST_V1: Back history (hold Circle, Options > Browse) */\n',
         '#include "OmniBfListShell.h" /* OMNI_BF_LIST_V1: Back history (hold Circle, Options > Browse) */\n'
         '#include "OmniHardReloadShell.h" /* OMNI_HARD_RELOAD_V1: Reload without cache (page menu, Options > Browse) */\n'),
    ],
    'OmniContextMenu.h': [
        ('static bool omniImvContextAction(OmniFxPanel& p, int id); /* OMNI_IMAGE_VIEWER_V1 */\n',
         'static bool omniImvContextAction(OmniFxPanel& p, int id); /* OMNI_IMAGE_VIEWER_V1 */\n'
         'static void omniHrlContextRow(OmniFxPanel& p); /* OMNI_HARD_RELOAD_V1 (OmniHardReloadShell.h) */\n'
         'static bool omniHrlAction(int id); /* OMNI_HARD_RELOAD_V1 */\n'),
        ('        add(omniCxReload, "Reload", t != nullptr, omniIconReload);\n',
         '        add(omniCxReload, "Reload", t != nullptr, omniIconReload);\n'
         '        omniHrlContextRow(p); /* OMNI_HARD_RELOAD_V1: Reload without cache (web pages only) */\n'),
        ('    if (omniImvContextAction(p, r.id)) return true; /* OMNI_IMAGE_VIEWER_V1 */\n',
         '    if (omniImvContextAction(p, r.id)) return true; /* OMNI_IMAGE_VIEWER_V1 */\n'
         '    if (omniHrlAction(r.id)) return true; /* OMNI_HARD_RELOAD_V1 */\n'),
    ],
    'OmniQuickMenu.h': [
        ('static bool omniBflQuickAction(int id); // OMNI_BF_LIST_V1\n',
         'static bool omniBflQuickAction(int id); // OMNI_BF_LIST_V1\n'
         'static void omniHrlQuickRow(OmniFxPanel& p); // OMNI_HARD_RELOAD_V1 (OmniHardReloadShell.h): Reload without cache\n'
         'static bool omniHrlAction(int id); // OMNI_HARD_RELOAD_V1\n'),
        ('    if (t && t->loading) add(omniQmReload, "Stop", true, omniIconClose); else add(omniQmReload, "Reload", t != nullptr, omniIconReload);\n',
         '    if (t && t->loading) add(omniQmReload, "Stop", true, omniIconClose); else add(omniQmReload, "Reload", t != nullptr, omniIconReload);\n'
         '    omniHrlQuickRow(p); // OMNI_HARD_RELOAD_V1: Reload without cache (web pages only)\n'),
        ('    case OmniBfList::kQuickRowId: return 1; // OMNI_BF_LIST_V1: Back history (Browse)\n',
         '    case OmniBfList::kQuickRowId: return 1; // OMNI_BF_LIST_V1: Back history (Browse)\n'
         '    case OmniHardReload::kQuickRowId: return 1; // OMNI_HARD_RELOAD_V1: Reload without cache (Browse)\n'),
        ('    if (omniBflQuickAction(r.id)) return true; // OMNI_BF_LIST_V1: Back history (before the >= 900 rows)\n',
         '    if (omniBflQuickAction(r.id)) return true; // OMNI_BF_LIST_V1: Back history (before the >= 900 rows)\n'
         '    if (omniHrlAction(r.id)) return true; // OMNI_HARD_RELOAD_V1: Reload without cache (before the >= 900 rows)\n'),
    ],
}
NEEDS = {'OmniBrowser.cpp': ('OMNI_BF_LIST_V1',),
         'OmniContextMenu.h': ('OMNI_IMAGE_VIEWER_V1',),
         'OmniQuickMenu.h': ('OMNI_BF_LIST_V1',)}


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
    mine_tree = {'OmniHardReload.h', 'OmniHardReloadShell.h'}
    # A sibling not applied to this tree yet still owns its ids: its code (generated headers / edits included,
    # comments and docstring stripped) assigning one of ours to a row id / kind ("kRowId = 894", "kPanelKind = 7614",
    # "constexpr int x = 894") is a clash. The same goes for the pure headers siblings keep in tools/.
    assign = re.compile(r'(?:\b\w*(?:[Rr]ow|[Kk]ind|[Ii]d|[Tt]ile)\w*|\bconstexpr\s+int\s+\w+)\s*=\s*(%s)(?![\w.])'
                        % '|'.join(IDS))
    for f in sorted(HERE.glob('apply_*.py')):
        if f.name == Path(__file__).name:
            continue
        if f.name == 'apply_controls_help.py' or MARK in f.read_text(encoding='utf-8', errors='replace'):   # OMNI_SIBLING_SKIP: the guide quotes names; a patch built on this one uses them
            continue
        t = code_only(f.read_text(encoding='utf-8', errors='replace'))
        m = name.search(t) or assign.search(t)   # bare numbers: not looked for (siblings' notes list others' ids)
        if m:
            sys.exit('%s already uses %r: pick other ids / names' % (f.name, m.group(0)))
    for f in sorted(HERE.glob('*.h')):
        if f.name == 'OmniHardReload.h':
            continue
        c = cpp_code(f.read_text(encoding='utf-8', errors='replace'))
        m = assign.search(c) or (None if f.name in GUIDE else name.search(c))
        if m:
            sys.exit('tools/%s already uses %r: pick other ids / names' % (f.name, m.group(0)))
    for f in sorted(root.iterdir()):
        if f.name in mine_tree or f.suffix not in ('.h', '.cpp', '.inc'):
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
    pure = (HERE / 'OmniHardReload.h').read_text(encoding='utf-8')
    if MARK not in pure:
        sys.exit('OmniHardReload.h: %s missing' % MARK)
    msgs = [write_new('OmniHardReload.h', pure, 'OmniQuickMenu.h'),
            write_new('OmniHardReloadShell.h', SHELL, 'OmniFeatures.h')]
    msgs += [patch(fname, edits) for fname, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
