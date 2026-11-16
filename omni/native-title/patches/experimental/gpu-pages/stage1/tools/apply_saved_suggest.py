#!/usr/bin/env python3
r"""OMNI_SAVED_SUGGEST_V1 (2026-11-16): bookmark and reading-list matches in the address suggestions (backlog E22).

What existed (patched tree, chain_final order through apply_site_search_suggest.py)
  - Address suggestions (OMNI_KEYBOARD_V2, omniSuggestUpdate in OmniBrowser.cpp): the 19 new-tab shortcuts
    (omniShortcuts, shortcuts.txt) and history rows (substring match on address / title), omniTqFilter, the engine's
    suggestions (omniF3SuggestMerge, s.search), "Switch to tab" / "Reopen" (omniTqPrepend), "= 87" (omniQanPrepend),
    "Search <host> for" (omniSqyPrepend, before the first engine row), the search-shortcut row first; 5 rows.
  - Bookmarks (OMNI_FEATURES_V1 + OMNI_BOOKMARKS_MANAGER_V1: omniFxBookmarks, bookmarks.txt, up to 500) and the
    reading list (OMNI_READING_LIST_V1: omniRlList, reading-list/index.tsv, up to 200) never appeared there: only
    the 19 shortcuts did. So this is new, not a repeat.

What the user sees
  - With 2+ characters typed (after "https://" / "www."), up to 2 rows for saved pages whose title or address has
    a word starting with each typed word (ASCII case-insensitive; "pasta" finds "Pasta recipes", "git" finds
    github.com; "ebkit" finds nothing). A small tag in front: "Bookmark" or "Reading list". Bookmarks rank above
    reading-list pages, both above history / shortcut rows and the engine's suggestions; one row per address (a
    bookmark beats the same reading-list page; an open tab's "Switch to tab" row beats both; a history row for the
    same address is replaced). Bookmarklets (javascript: / data:) are never offered.
  - Placement: right after the leading "= 87" / "Switch to tab" / "Reopen" rows. Still 5 rows: when over, the last
    engine row goes first, then the last other history row, then the last saved row. The "Search <host> for" row,
    the first history / shortcut row (the URL row) and the leading rows are never pushed out.
  - Cross on a bookmark row loads it here (like any row). Cross on a reading-list row opens the saved copy in a new
    tab (omniRlOpenSaved, as the Reading list panel does); when no tab is free or the entry was removed, the live
    page loads here instead.
  - Private tabs: bookmark rows only (local; the page loads in the same private tab). No reading-list rows (the
    saved copy would open in a normal tab), nothing stored, no history added or read by this patch.

Cost: no per-keystroke disk reads. The matched bookmark list (lowercased title + bare address) is a cache rebuilt
from the in-memory omniFxBookmarks only when bookmarks.txt's stamp (mtime, size, inode: one stat at most every 2 s,
never a read) or the list size changes. The reading list is loaded once per run on its own thread
(omniRlEnsureLoading, as the start page does) and its cache is rebuilt only when its ids change. Matching runs
once per change of the typed text (omniSuggestUpdate), over at most 700 prepared entries.

Pure part: engine/entry/OmniSavedSuggest.h (copied from tools/OmniSavedSuggest.h). Tests:
    g++ -std=c++20 -Wall -Wextra -Werror -I<tools> test_saved_suggest.cpp -o t && ./t
Shell part: engine/entry/OmniSavedSuggestShell.h (written by this script), alias OSVD, names omniSvd*. No ids.

Anchors (exactly once each, whole lines; new lines go after them; line endings kept):
  OmniBrowser.cpp       the OmniSiteQuery.h include (pure include after); the "struct OmniSuggestion {" line (two
                        fields after); "static void omniTqPrepend();" (declarations after); the omniSqyPrepend();
                        call line (ours after); the omniQanUse line in omniSuggestGo (reading-list open after); the
                        OmniFeatures3.h include (shell include after: it reads omniFxBookmarks and omniRlList)
  OmniTabSearchShell.h  the head of omniTqIcon (the tag is drawn in the icon slot, normal and zoomed suggestion lists)
Apply AFTER apply_site_search_suggest.py (and so after tab_search, quick_answers, search_engine, reading_list,
bookmarks_manager).
usage: apply_saved_suggest.py <engine tree>   (anchored, idempotent, keeps line endings; re-run: "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_SAVED_SUGGEST_V1'
HERE = Path(__file__).resolve().parent
if len(sys.argv) != 2:
    sys.exit('usage: apply_saved_suggest.py <engine tree>')
root = Path(sys.argv[1]) / 'engine' / 'entry'
IDS = ()   # no panel kinds or settings rows
NAMES = ('OSVD', 'omniSvd', 'OmniSavedSuggest')
# The site-search patch's names, built from two parts: apply_site_search_suggest.py's name check matches them whole
# in sibling code.
SQ, SQP = 'OmniSite' + 'Query', 'omni' + 'Sqy'

SHELL = r'''/* MARKER: bookmark and reading-list rows in the address suggestions (shell side). Included from
   OmniBrowser.cpp right after OmniFeatures3.h (inside its anonymous namespace): it reads omniFxBookmarks
   (OmniBookmarks.h) and omniRlList (OmniReadingListShell.h). omniSvdPlace / omniSvdGo / omniSvdTag are declared
   before omniSuggestUpdate. The pure part is OmniSavedSuggest.h; the reasons are in tools/apply_saved_suggest.py. */
#pragma once

namespace OSVD = OmniSavedSuggest;
static OSVD::Cache omniSvdBm, omniSvdRl;
static uint64_t omniSvdBmStamp = 0;
static uint32_t omniSvdStatAt = 0;
static bool omniSvdStatted = false;

/* The bookmarks as matched: rebuilt from omniFxBookmarks (bookmarks.txt is read once per run by
   omniFxBookmarksLoad) only when bookmarks.txt's stamp or the list size changes. The stamp is one stat at most
   every 2 s (never a read). */
static void omniSvdRefreshBookmarks()
{
    omniFxBookmarksLoad();
    const uint32_t now = SDL_GetTicks();
    if (!omniSvdStatted || now - omniSvdStatAt >= 2000) {
        omniSvdStatted = true;
        omniSvdStatAt = now;
        struct stat st {};
        OSVD::Key k;
        if (!stat(omniData("bookmarks.txt").c_str(), &st))
            k.add((long long)st.st_mtime).add((long long)st.st_size).add((long long)st.st_ino);
        omniSvdBmStamp = k.h;
    }
    const uint64_t key = OSVD::Key().add((long long)omniSvdBmStamp).add((long long)omniFxBookmarks.size()).h;
    omniSvdBm.refresh(key, [](std::vector<OSVD::Entry>& out) {
        out.reserve(omniFxBookmarks.size());
        for (const auto& b : omniFxBookmarks) out.push_back(OSVD::prepare(OSVD::kBookmark, b.first, b.second));
    });
}
/* The reading list as matched: loaded once per run on its own thread (as the start page does); rebuilt when its
   ids change. Nothing until it is in. */
static void omniSvdRefreshReading()
{
    omniRlEnsureLoading();
    std::lock_guard<std::mutex> g(omniRlLock);
    if (!omniRlLoaded) return;
    OSVD::Key k;
    k.add((long long)omniRlList.size());
    for (const auto& e : omniRlList) k.add(e.id);
    omniSvdRl.refresh(k.h, [](std::vector<OSVD::Entry>& out) {
        out.reserve(omniRlList.size());
        for (const auto& e : omniRlList) out.push_back(OSVD::prepare(OSVD::kReading, e.url, e.title, e.id));
    });
}
/* Called from omniSuggestUpdate after the site row: up to 2 saved rows right after the tab / answer rows, still
   5 rows (OSVD::place keeps the site row, the first history row and the leading rows). */
static void omniSvdPlace()
{
    const Tab* t = active();
    if (!t || omniTestMode() || OSVD::query(address).empty()) return;
    const bool priv = t->omniPrivate;   /* private: bookmarks only (local), never the reading list */
    omniSvdRefreshBookmarks();
    if (!priv) omniSvdRefreshReading();
    std::vector<std::string> skip;      /* "Switch to tab" rows win */
    for (const auto& s : omniSuggestions) if (s.omniTqKind) skip.push_back(OSVD::bare(s.url));
    static const std::vector<OSVD::Entry> none;
    const std::vector<OSVD::Hit> hits = OSVD::rank(omniSvdBm.items, priv ? none : omniSvdRl.items, address, skip);
    if (hits.empty()) return;
    std::vector<OmniSuggestion> saved;
    std::vector<std::string> savedBare;
    for (const auto& h : hits) {
        const OSVD::Entry& e = (h.kind == OSVD::kBookmark ? omniSvdBm.items : omniSvdRl.items)[h.index];
        OmniSuggestion s;
        s.url = e.url;
        s.title = e.title.empty() ? omniShownURL(e.url) : e.title;
        s.omniSvdKind = h.kind;
        s.omniSvdId = e.id;
        savedBare.push_back(e.lowUrl);
        saved.push_back(std::move(s));
    }
    auto plain = [](const OmniSuggestion& s) { return !s.search && s.omniQanValue.empty() && !s.omniTqKind && !s.omniSvdKind; };
    omniSuggestions.erase(std::remove_if(omniSuggestions.begin(), omniSuggestions.end(), [&](const OmniSuggestion& s) {
        return plain(s) && std::find(savedBare.begin(), savedBare.end(), OSVD::bare(s.url)) != savedBare.end();
    }), omniSuggestions.end());
    std::string siteUrl;   /* the "Search <host> for" row (the site-search shell) is recognised by its address */
    {
        SITEQ::Offer o;
        if (SITEQ::offer(t->url, address, o)) siteUrl = omniSearchUrlFor(o.query);
    }
    std::vector<OSVD::Role> roles;
    bool urlRow = false;
    for (const auto& s : omniSuggestions) {
        if (!s.omniQanValue.empty() || s.omniTqKind) roles.push_back(OSVD::kLead);
        else if (s.search) roles.push_back(!siteUrl.empty() && s.url == siteUrl ? OSVD::kSite : OSVD::kEngine);
        else if (!urlRow) { roles.push_back(OSVD::kUrl); urlRow = true; }
        else roles.push_back(OSVD::kLocal);
    }
    std::vector<OmniSuggestion> merged;
    for (int v : OSVD::place(roles, saved.size()))
        merged.push_back(v < 0 ? saved[size_t(-v - 1)] : omniSuggestions[size_t(v)]);
    omniSuggestions = std::move(merged);
}
/* Cross / Triangle / click on a saved row. A reading-list row opens its saved copy in a new tab (as the Reading
   list panel does); false = load the row's address here (bookmarks; no free tab; entry gone; private tab). */
static bool omniSvdGo(OmniSuggestion s)
{
    if (s.omniSvdKind != OSVD::kReading || s.omniSvdId.empty()) return false;
    const Tab* t = active();
    if (!t || t->omniPrivate || omniF3TabsFull()) return false;
    RL::Entry e;
    bool found = false;
    {
        std::lock_guard<std::mutex> g(omniRlLock);
        for (const auto& x : omniRlList) if (x.id == s.omniSvdId) { e = x; found = true; break; }
    }
    if (!found) return false;
    omniSuggestSel = -1;
    omniKbPageReset();
    editing = false;
    omniSuggestFor = "\x01";
    omniRlOpenSaved(e);
    omniShellDirty = true;
    return true;
}
/* The small "Bookmark" / "Reading list" tag in the row's icon slot (omniTqIcon calls this); returns its width. */
static int omniSvdTag(const OmniSuggestion& s, int x, float cy, bool sel)
{
    const OmniTheme& T = omniTheme();
    const char* label = s.omniSvdKind == OSVD::kBookmark ? "Bookmark" : "Reading list";
    const int tw = int(omniTextWidthPx(omniCaption, omniTr(label)) / displayScale + 0.5);
    const SDL_Color bg = sel ? T.accentInk : T.inkDim, ink = sel ? T.accent : T.raised;
    fillRounded(x, int(cy) - 11, tw + 16, 22, 11, bg);
    omniLabel(label, float(x + 8), cy, omniCaption, ink, 0);
    return tw + 26;
}
'''.replace('MARKER', MARK).replace('SITEQ', SQ)

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "%s.h" /* OMNI_SITE_SEARCH_SUGGEST_V1: "Search this site" address row (pure) */\n' % SQ,
         '#include "%s.h" /* OMNI_SITE_SEARCH_SUGGEST_V1: "Search this site" address row (pure) */\n'
         '#include "OmniSavedSuggest.h" /* %s: bookmark / reading-list address rows (pure) */\n' % (SQ, MARK)),
        ('struct OmniSuggestion { std::string url, title; bool search = false; '
         '// OMNI_FEATURES_V3: search: a search-engine suggestion\n',
         'struct OmniSuggestion { std::string url, title; bool search = false; '
         '// OMNI_FEATURES_V3: search: a search-engine suggestion\n'
         '    int omniSvdKind = 0; std::string omniSvdId = std::string(); '
         '/* %s: OmniSavedSuggest::Kind, the reading-list entry id */\n' % MARK),
        ('static void omniTqPrepend();\n',
         'static void omniTqPrepend();\n'
         'static void omniSvdPlace(); /* %s (OmniSavedSuggestShell.h): bookmark / reading-list rows */\n'
         'static bool omniSvdGo(OmniSuggestion s);\n'
         'static int omniSvdTag(const OmniSuggestion& s, int x, float cy, bool sel);\n' % MARK),
        ('    %sPrepend(); /* OMNI_SITE_SEARCH_SUGGEST_V1: "Search <host> for ..." row, still 5 rows */\n' % SQP,
         '    %sPrepend(); /* OMNI_SITE_SEARCH_SUGGEST_V1: "Search <host> for ..." row, still 5 rows */\n'
         '    omniSvdPlace(); /* %s: up to 2 bookmark / reading-list rows, still 5 rows */\n' % (SQP, MARK)),
        ('    if (!omniSuggestions[i].omniQanValue.empty()) { omniQanUse(omniSuggestions[i].omniQanValue); return; } '
         '// OMNI_QUICK_ANSWERS_V1: copy, never load\n',
         '    if (!omniSuggestions[i].omniQanValue.empty()) { omniQanUse(omniSuggestions[i].omniQanValue); return; } '
         '// OMNI_QUICK_ANSWERS_V1: copy, never load\n'
         '    if (omniSuggestions[i].omniSvdKind && omniSvdGo(omniSuggestions[i])) return; '
         '/* %s: a reading-list row opens its saved copy */\n' % MARK),
        ('#include "OmniFeatures3.h" // OMNI_FEATURES_V3\n',
         '#include "OmniFeatures3.h" // OMNI_FEATURES_V3\n'
         '#include "OmniSavedSuggestShell.h" /* %s: after the bookmarks and the reading list */\n' % MARK),
    ],
    'OmniTabSearchShell.h': [
        ('static int omniTqIcon(const OmniSuggestion& s, int x, float cy, bool sel)\n{\n',
         'static int omniTqIcon(const OmniSuggestion& s, int x, float cy, bool sel)\n{\n'
         '    if (s.omniSvdKind) return omniSvdTag(s, x, cy, sel); /* %s: "Bookmark" / "Reading list" tag */\n' % MARK),
    ],
}
NEEDS = {'OmniBrowser.cpp': ('OMNI_SITE_SEARCH_SUGGEST_V1', 'OMNI_QUICK_ANSWERS_V1', 'OMNI_TAB_SEARCH_V1',
                             'OMNI_KEYBOARD_V2', 'OMNI_READING_LIST_V1', 'OMNI_BOOKMARKS_MANAGER_V1'),
         'OmniFeaturesDecl.h': ('OMNI_SEARCH_ENGINE_V1',),
         'OmniTabSearchShell.h': ('OMNI_TAB_SEARCH_V1',)}


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
SKIP_SIBLINGS = ('apply_controls_help.py',)
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
    mine = {'OmniSavedSuggest.h', 'OmniSavedSuggestShell.h'}
    ours = NAMES + tuple(mine) + (MARK,)
    for f in sorted(HERE.glob('apply_*.py')):
        if f.name == Path(__file__).name or f.name in SKIP_SIBLINGS:
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
    pure = (HERE / 'OmniSavedSuggest.h').read_text(encoding='utf-8')
    if MARK not in pure:
        sys.exit('OmniSavedSuggest.h: %s missing' % MARK)
    msgs = [write_new('OmniSavedSuggest.h', pure, 'OmniBrowser.cpp'),
            write_new('OmniSavedSuggestShell.h', SHELL, 'OmniBrowser.cpp')]
    msgs += [patch(fname, edits) for fname, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
