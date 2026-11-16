#!/usr/bin/env python3
r"""OMNI_SITE_SEARCH_SUGGEST_V1 (2026-11-16): "Search this site" address suggestion (backlog E21).

What existed (patched tree, chain_final order through apply_notice_history.py)
  - Address suggestions (OMNI_KEYBOARD_V2, omniSuggestUpdate in OmniBrowser.cpp): history / shortcut rows, then
    omniTqFilter, omniF3SuggestMerge (engine suggestions, s.search = true), omniTqPrepend ("Switch to tab" /
    "Reopen"), omniQanPrepend ("= 87"), and the search-shortcut row ("yt cats") first; 5 rows at most. Nothing is
    built while the address still equals the page's own address. omniSuggestGo navigates a row's url.
  - omniSearchUrlFor(query) (OMNI_SEARCH_ENGINE_V1, OmniSearchEngineShell.h) is THE search URL for typed words: the
    user's engine (Google / DuckDuckGo / Bing / Brave / Startpage / Ecosia / Qwant / Custom), UTF-8
    percent-encoding, and the safe-search wrap (apply_parental.py) all apply.
  - apply_site_search.py (OMNI_SITE_SEARCH_V1) is something else: OpenSearch "Add <site> search" shortcuts. It does
    not add a site: row. Its name check matches anything containing "OmniSiteSearch" / "OMNI_SITE_SEARCH" in code,
    so this patch's files, namespace and code strings avoid both (the MARK lives in comments only; the Python
    constant is built from two parts).

What the user sees
  - Typing in the address bar while a web page is shown (http / https; not omni:// pages, the new-tab page, file /
    data / about pages, IP addresses or local names such as localhost / *.local / *.lan): when the text is not an
    address (OmniSiteQuery::looksLikeAddress = destination()'s rule + the search shortcuts' looksLikeUrl) and has no
    "site:" of its own, one row "Search <host> for “<text>”" (detail: "Search <engine>", as engine rows) searches
    the chosen engine for "site:<host> <text>". The host drops "www."; long text is cut in the title only.
  - Placement: just before the first engine-suggestion row (or last), always inside the 5 rows. No row when a
    search shortcut matches ("yt cats": the shortcut wins), in self-test modes, or with nothing typed.
  - Private tabs: the row uses only the shown tab's own address (never history, never another tab), stores nothing,
    and the search loads in the same (private) tab like Go does.
  - Nothing new is sent anywhere: the row is built locally; the remote suggestion request (OmniSuggest.h) is
    untouched (it still gets only the typed text, under its own rules). The site: query reaches the engine only
    when the user picks the row.

Pure part: engine/entry/OmniSiteQuery.h (copied from tools/OmniSiteQuery.h). Tests:
    g++ -std=c++20 -Wall -Wextra -Werror -I<tools> test_site_query.cpp -o t && ./t
Shell part: engine/entry/OmniSiteQueryShell.h (written by this script), alias OSQY, names omniSqy*. No ids.

Anchors (exactly once each, whole lines; new lines go after them, the shell include before; line endings kept):
  OmniBrowser.cpp   the OmniSearchTiles.h include (pure include after); "static void omniSuggestUpdate()" (shell
                    include before); the omniQanPrepend(); call line in omniSuggestUpdate (ours after)
Apply AFTER apply_search_engine.py (omniSearchUrlFor), apply_quick_answers.py and apply_search_tiles.py.
usage: apply_site_search_suggest.py <engine tree>   (anchored, idempotent, keeps line endings; re-run: "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_SITE_' + 'SEARCH_SUGGEST_V1'   # two parts: apply_site_search.py's name check matches the whole word
HERE = Path(__file__).resolve().parent
if len(sys.argv) != 2:
    sys.exit('usage: apply_site_search_suggest.py <engine tree>')
root = Path(sys.argv[1]) / 'engine' / 'entry'
IDS = ()   # no panel kinds or settings rows
NAMES = ('OSQY', 'omniSqy', 'OmniSiteQuery')

SHELL = r'''/* MARKER: "Search this site" (shell side). Included from OmniBrowser.cpp right before
   omniSuggestUpdate (inside its anonymous namespace). The pure part is OmniSiteQuery.h; the reasons are in
   tools/apply_site_search_suggest.py. */
namespace OSQY = OmniSiteQuery;
/* One row "Search <host> for “<text>”" -> the chosen engine with "site:<host> <text>". Called from
   omniSuggestUpdate after the tab / answer rows; built locally, nothing is sent until the row is picked. */
static void omniSqyPrepend()
{
    Tab* t = active();
    if (!t || t->omniNewTabPage || omniTestMode()) return;
    OSQY::Offer o;
    if (!OSQY::offer(t->url, address, o)) return;
    OmniSearchTiles::Match m;   /* a search shortcut ("yt cats") is the user's explicit choice: no site row */
    if (OmniSearchTiles::match(address, omniStEngines.get(omniStPath), m)) return;
    OmniSuggestion s;
    s.url = omniSearchUrlFor(o.query);
    s.title = o.title;
    s.search = true;   /* detail "Search <engine>", like the engine rows */
    size_t at = 0;
    while (at < omniSuggestions.size() && !omniSuggestions[at].search) ++at;
    if (at > 4) at = 4;
    omniSuggestions.insert(omniSuggestions.begin() + std::ptrdiff_t(at), std::move(s));
    if (omniSuggestions.size() > 5) omniSuggestions.resize(5);
}
'''.replace('MARKER', MARK)

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniSearchTiles.h" // OMNI_SEARCH_TILES_V1: search shortcuts and most-visited tiles (pure)\n',
         '#include "OmniSearchTiles.h" // OMNI_SEARCH_TILES_V1: search shortcuts and most-visited tiles (pure)\n'
         '#include "OmniSiteQuery.h" /* %s: "Search this site" address row (pure) */\n' % MARK),
        ('\nstatic void omniSuggestUpdate()\n',
         '\n#include "OmniSiteQueryShell.h" /* %s: omniSqyPrepend */\nstatic void omniSuggestUpdate()\n' % MARK),
        ('    omniQanPrepend(); // OMNI_QUICK_ANSWERS_V1: "= 87" above the tab rows, still 5 rows\n',
         '    omniQanPrepend(); // OMNI_QUICK_ANSWERS_V1: "= 87" above the tab rows, still 5 rows\n'
         '    omniSqyPrepend(); /* %s: "Search <host> for ..." row, still 5 rows */\n' % MARK),
    ],
}
NEEDS = {'OmniBrowser.cpp': ('OMNI_SEARCH_TILES_V1', 'OMNI_QUICK_ANSWERS_V1', 'OMNI_TAB_SEARCH_V1', 'OMNI_KEYBOARD_V2'),
         'OmniFeaturesDecl.h': ('OMNI_SEARCH_ENGINE_V1',)}


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


def sibling_names(src):
    """The NAMES tuple of a sibling apply_*.py (its own clash regex), so this patch never trips another one's check."""
    m = re.search(r'^NAMES\s*=\s*\(([^)]*)\)', src, re.M)
    return re.findall(r"'([^']+)'", m.group(1)) if m else []


def ids_free():
    """Before a first apply: no other patch or tree file uses this patch's names (and none of ours trips a sibling's
    NAMES check). No numeric ids: nothing to look for in the tree's row-id assignments."""
    name = re.compile('|'.join(NAMES))
    mine = {'OmniSiteQuery.h', 'OmniSiteQueryShell.h'}
    ours = NAMES + tuple(mine)   # the new names this patch puts in code (the MARK only in comments)
    for f in sorted(HERE.glob('apply_*.py')):
        if f.name == Path(__file__).name:
            continue
        if f.name == 'apply_controls_help.py' or MARK in f.read_text(encoding='utf-8', errors='replace'):   # OMNI_SIBLING_SKIP: the guide quotes names; a patch built on this one uses them
            continue
        src = f.read_text(encoding='utf-8', errors='replace')
        t = code_only(src)
        m = name.search(t)
        if m:
            sys.exit('%s already uses %r: pick other names' % (f.name, m.group(0)))
        for n in sibling_names(src):
            if any(re.search(n, x) for x in ours):
                sys.exit('%s checks for %r, which this patch uses: pick other names' % (f.name, n))
    for f in sorted(root.iterdir()):
        if f.name in mine or f.suffix not in ('.h', '.cpp', '.inc'):
            continue
        t = f.read_bytes().decode('utf-8', errors='replace')
        if f.name in GUIDE:
            continue
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
        ids_free()
    for fname, edits in EDITS.items():   # every anchor is checked before anything is written
        check(fname, edits)
    pure = (HERE / 'OmniSiteQuery.h').read_text(encoding='utf-8')
    if MARK not in pure:
        sys.exit('OmniSiteQuery.h: %s missing' % MARK)
    msgs = [write_new('OmniSiteQuery.h', pure, 'OmniBrowser.cpp'),
            write_new('OmniSiteQueryShell.h', SHELL, 'OmniBrowser.cpp')]
    msgs += [patch(fname, edits) for fname, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
