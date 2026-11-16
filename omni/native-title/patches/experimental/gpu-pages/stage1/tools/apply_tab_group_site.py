#!/usr/bin/env python3
"""OMNI_TAB_GROUP_SITE_V1 (2026-11-16): "Group tabs by site", one quick action (backlog E35; tab groups were manual).

What the user sees
  - Tabs panel, hold Cross on a tab row: the tab menu (OMNI_TAB_GROUPS_V1 + OMNI_TAB_ACTIONS_V1) has a new row
    "Group tabs by site" first among the tab actions (after the group rows; for a private or pinned tab after the
    "can't join groups" line: the action is about all tabs, not this one). Value: "3 sites, 9 tabs", or why it is off:
    "No site has 2 ungrouped tabs", "Group limit reached (8 of 8)".
  - Cross: for every site (registrable domain: www.youtube.com, m.youtube.com -> "youtube.com"; news.bbc.co.uk ->
    "bbc.co.uk"; IP addresses / localhost whole) with 2 or more ungrouped tabs, a new group named after the site
    (made unique by tab groups: "youtube.com (2)" when a manual group has that name) gets those tabs; colours are
    tab groups' next free colour each time, then round the six (round-robin). Sites go in order of their first tab;
    each group's tabs keep their relative order (tab groups' order is a stable sort: pinned, groups, ungrouped).
    Never moved: tabs already in a group (manual or earlier site groups), pinned tabs, private tabs (tab groups never
    lets a private tab join a group, so they are skipped, not grouped among themselves), non-web pages (omni://,
    about:, new tab). Groups past tab groups' limit (8) are not made: "Grouped 2 sites; group limit reached".
    Otherwise one notice: "Grouped 4 sites" (1: "Grouped 1 site"). The menu closes; the Tabs panel shows the groups.
  - Undo: for 30 s the row reads "Undo grouping" (value "Grouped 4 sites, 23 s left"). Cross ungroups the groups it
    made that still exist (their tabs stay open) and puts the tabs back in the order they had before (tabs opened since
    stay after them; then tab groups' order again): notice "Grouping undone". A row built as "Undo grouping" whose
    30 s ran out while the menu was open says "Too late to undo: the groups stay" (it never groups again by surprise).
    A new "Group tabs by site" replaces the undo. Memory only: nothing is written (tab groups' session lines save the
    groups as any group).

Registrable domain: OmniLinkPreview::registrableDomain (OMNI_LINK_PREVIEW_V1's built-in approximation of the Public
Suffix List: last two labels, three under co.uk-style registry second levels, shared hosting suffixes such as
github.io kept per owner). Omni has no libpsl call in the title (WebKit's libpsl is inside the network process), so
this is the helper used. Names shown use its unicodeHost (xn-- labels decoded).

Pure part: engine/entry/OmniTabGroupSite.h (no SDL / WebKit; uses OmniTabGroups.h and OmniLinkPreview.h): site of a URL,
the plan (which tabs, which sites, the limit), applying it to an OmniTabGroups::Model, undo, order restore, texts.
Tested by tools/test_tab_group_site.cpp:
  g++ -std=c++20 -Wall -Wextra -Werror -I<tree>/engine/entry test_tab_group_site.cpp -o t && ./t
Shell side: engine/entry/OmniTabGroupSiteShell.h (included from OmniFeatures3.h after OmniTabActionsShell.h; its two
hooks declared in OmniFeatures3Decl.h). Alias OTGSITE, names omniTgs*, menu row id 7546 (checked unused).

Anchors (exactly once each; MARK makes each file idempotent; whole lines, ours after / before them):
  OmniBrowser.cpp        the OmniTabActions.h include line (pure include after).
  OmniFeatures3Decl.h    tab actions' omniTacMenuInput declaration (ours after).
  OmniFeatures3.h        the OmniTabActionsShell.h include line (ours after).
  OmniTabActionsShell.h  omniTacMenuRows' `const bool full = omniF3TabsFull();` (our row before it); omniTacMenuInput's
                         isRow line (our input before it). apply_tab_actions.py rewrites that file when its bytes
                         differ, so a re-run of it drops these two edits; this script then sees no MARK there and
                         applies them again (run it after).
Apply AFTER apply_tab_groups.py (r2), apply_tab_actions.py (r2) and apply_link_preview.py.
usage: apply_tab_group_site.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_TAB_GROUP_SITE_V1'
HERE = Path(__file__).resolve().parent
if len(sys.argv) != 2:
    sys.exit('usage: apply_tab_group_site.py <engine tree>')
root = Path(sys.argv[1]) / 'engine' / 'entry'
IDS = ('7546',)
NAMES = ('OTGSITE', 'omniTgs', 'OmniTabGroupSite', 'OMNI_TAB_GROUP_SITE')

PURE = r'''// OMNI_TAB_GROUP_SITE_V1: the pure part of "Group tabs by site" (no SDL, no WebKit). The shell side is
// OmniTabGroupSiteShell.h; the reasons are in tools/apply_tab_group_site.py. Tested on the host with g++
// (test_tab_group_site.cpp). Sites are OmniLinkPreview::registrableDomain (a built-in Public Suffix List approximation).
#pragma once
#include "OmniTabGroups.h"
#include "OmniLinkPreview.h"
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace OmniTabGroupSite {

constexpr int kRowId = 7546;            // the tab menu's row (tab actions use 7530..7538, tab groups 1..3 and 10..17)
constexpr uint32_t kUndoMs = 30000;     // "Undo grouping" stays this long
constexpr size_t kMinTabs = 2;          // a site needs this many ungrouped tabs
constexpr size_t kUrlMax = 8192;

// The site of a web page's URL ("youtube.com"); empty for anything that is not http(s) with a host.
inline std::string siteOf(const std::string& url)
{
    const OmniLinkPreview::Url u = OmniLinkPreview::parseUrl(url.substr(0, kUrlMax));
    if (!u.ok || !u.hierarchical || (u.scheme != "http" && u.scheme != "https")) return std::string();
    std::string h = u.host;
    while (!h.empty() && h.back() == '.') h.pop_back();
    if (h.empty()) return std::string();
    return OmniLinkPreview::registrableDomain(h);
}
inline std::string siteName(const std::string& site) { return OmniLinkPreview::unicodeHost(site); }   // the group's name

// --- the plan --------------------------------------------------------------------------------------------------------
struct In { std::string url; bool priv = false, pinned = false, grouped = false; };   // one tab, in tab order
struct Site { std::string site; std::vector<size_t> tabs; };                             // tab indexes, in order
struct Plan {
    std::vector<Site> sites;   // the groups to make, in order of each site's first tab
    int left = 0;              // sites with enough tabs that the group limit leaves out
    int room = 0;              // groups that could still be made
    size_t tabCount() const { size_t n = 0; for (auto& s : sites) n += s.tabs.size(); return n; }
};
inline bool movable(const In& t) { return !t.priv && !t.pinned && !t.grouped; }
inline Plan plan(const std::vector<In>& tabs, int groupsNow, int maxGroups = OmniTabGroups::kMaxGroups)
{
    std::vector<Site> all;
    for (size_t i = 0; i < tabs.size(); ++i) {
        if (!movable(tabs[i])) continue;
        const std::string s = siteOf(tabs[i].url);
        if (s.empty()) continue;
        Site* at = nullptr;
        for (auto& x : all) if (x.site == s) { at = &x; break; }
        if (!at) { all.push_back(Site { s, {} }); at = &all.back(); }
        at->tabs.push_back(i);
    }
    Plan p;
    p.room = std::max(0, maxGroups - groupsNow);
    for (auto& s : all) {
        if (s.tabs.size() < kMinTabs) continue;
        if (int(p.sites.size()) >= p.room) { ++p.left; continue; }
        p.sites.push_back(std::move(s));
    }
    return p;
}

// Makes the plan's groups in `m` (tabs[i] is the tab of index i). Colours: the next free one each time, then round
// the six (OmniTabGroups::nextColour). A tab already in a group is skipped; a group that got no tab is not kept.
// Returns the new groups' ids, in order.
inline std::vector<int> apply(OmniTabGroups::Model& m, const Plan& p, const std::vector<const void*>& tabs)
{
    std::vector<int> ids;
    for (const Site& s : p.sites) {
        const int id = OmniTabGroups::create(m, siteName(s.site), OmniTabGroups::nextColour(m));
        if (!id) break;   // the limit (the plan already stops before it)
        int added = 0;
        for (size_t i : s.tabs) {
            if (i >= tabs.size() || !tabs[i] || OmniTabGroups::groupOf(m, tabs[i])) continue;
            if (OmniTabGroups::add(m, tabs[i], id)) ++added;
        }
        if (!added) { OmniTabGroups::ungroup(m, id); continue; }
        ids.push_back(id);
    }
    return ids;
}

// --- undo ------------------------------------------------------------------------------------------------------------
struct Undo {
    std::vector<int> ids;                 // the groups it made
    std::vector<const void*> order;       // the tab order before
    uint32_t at = 0;                      // when (ms)
    int sites = 0;
    bool armed = false;
};
inline bool anyLeft(const Undo& u, const OmniTabGroups::Model& m)
{
    for (int id : u.ids) if (OmniTabGroups::indexOf(m, id) >= 0) return true;
    return false;
}
inline bool undoable(const Undo& u, const OmniTabGroups::Model& m, uint32_t now) { return u.armed && now - u.at < kUndoMs && anyLeft(u, m); }
inline int secondsLeft(const Undo& u, uint32_t now)
{
    const uint32_t gone = now - u.at;
    return gone >= kUndoMs ? 0 : int((kUndoMs - gone + 999) / 1000);
}
// Ungroups the groups it made that still exist (their tabs stay open); returns how many. The undo is used up.
inline int undo(OmniTabGroups::Model& m, Undo& u)
{
    int n = 0;
    for (int id : u.ids) if (OmniTabGroups::indexOf(m, id) >= 0) { OmniTabGroups::ungroup(m, id); ++n; }
    u.armed = false;
    return n;
}
// The order to put `now` in (indexes into `now`): the tabs of `before` in that order, then the others as they are.
inline std::vector<size_t> restoreOrder(const std::vector<const void*>& now, const std::vector<const void*>& before)
{
    std::vector<size_t> out;
    std::vector<bool> used(now.size(), false);
    for (const void* b : before)
        for (size_t i = 0; i < now.size(); ++i)
            if (!used[i] && now[i] == b) { used[i] = true; out.push_back(i); break; }
    for (size_t i = 0; i < now.size(); ++i) if (!used[i]) out.push_back(i);
    return out;
}

// --- texts -----------------------------------------------------------------------------------------------------------
inline const char* label() { return "Group tabs by site"; }
inline const char* undoLabel() { return "Undo grouping"; }
inline std::string sitesText(int n) { return std::to_string(n) + (n == 1 ? " site" : " sites"); }
inline std::string rowValue(const Plan& p)
{
    if (!p.sites.empty()) return sitesText(int(p.sites.size())) + ", " + OmniTabGroups::tabsText(int(p.tabCount()));
    if (p.left) return "Group limit reached (" + std::to_string(OmniTabGroups::kMaxGroups) + " of " + std::to_string(OmniTabGroups::kMaxGroups) + ")";
    return "No site has 2 ungrouped tabs";
}
inline std::string undoValue(int sites, int seconds) { return "Grouped " + sitesText(sites) + ", " + std::to_string(seconds) + " s left"; }
inline std::string doneNotice(int sites, bool limited) { return "Grouped " + sitesText(sites) + (limited ? "; group limit reached" : ""); }
inline std::string emptyNotice(const Plan& p) { return p.left ? doneNotice(0, true) : std::string("No site has 2 ungrouped tabs"); }
inline const char* undoneNotice() { return "Grouping undone"; }
inline const char* tooLateNotice() { return "Too late to undo: the groups stay"; }

} // namespace OmniTabGroupSite
'''

SHELL = r'''// OMNI_TAB_GROUP_SITE_V1: "Group tabs by site" in the Tabs panel's hold-Cross tab menu (shell side). Included from
// OmniFeatures3.h after OmniTabActionsShell.h (inside OmniBrowser.cpp's anonymous namespace); its two hooks are declared
// in OmniFeatures3Decl.h for tab actions. The pure part is OmniTabGroupSite.h; the reasons are in
// tools/apply_tab_group_site.py. Main thread only; memory only.
#pragma once

namespace OTGSITE = OmniTabGroupSite;
static OTGSITE::Undo omniTgsUndo;

static OTGSITE::Plan omniTgsPlan(std::vector<const void*>* ptrs)
{
    omniTgNormalize();   // pinned, groups, ungrouped: the plan's indexes are this order
    std::vector<OTGSITE::In> in;
    in.reserve(tabs.size());
    for (auto& t : tabs) {
        OTGSITE::In i;
        i.url = omniTsTabURL(*t); i.priv = t->omniPrivate; i.pinned = omniPtPinned(*t);
        i.grouped = OTG::groupOf(omniTgModel, t.get()) != 0;
        in.push_back(i);
        if (ptrs) ptrs->push_back(t.get());
    }
    return OTGSITE::plan(in, int(omniTgModel.groups.size()));
}
// omniTacMenuRows: the row, first among the tab actions.
static void omniTgsMenuRow(OmniFxPanel& p)
{
    OmniFxRow r;
    r.id = OTGSITE::kRowId;
    const uint32_t now = SDL_GetTicks();
    if (OTGSITE::undoable(omniTgsUndo, omniTgModel, now)) {
        r.label = OTGSITE::undoLabel();
        r.value = OTGSITE::undoValue(omniTgsUndo.sites, OTGSITE::secondsLeft(omniTgsUndo, now));
    } else {
        const OTGSITE::Plan plan = omniTgsPlan(nullptr);
        r.label = OTGSITE::label();
        r.enabled = !plan.sites.empty();
        r.value = OTGSITE::rowValue(plan);
    }
    p.rows.push_back(r);
}
static void omniTgsGroup()
{
    std::vector<const void*> ptrs;
    const OTGSITE::Plan plan = omniTgsPlan(&ptrs);
    if (plan.sites.empty()) { notice(OTGSITE::emptyNotice(plan)); return; }
    OTGSITE::Undo u;
    u.order = ptrs;
    u.ids = OTGSITE::apply(omniTgModel, plan, ptrs);
    omniTgNormalize();   // each group's tabs together, in their relative order
    u.sites = int(u.ids.size());
    u.at = SDL_GetTicks();
    u.armed = !u.ids.empty();
    omniTgsUndo = std::move(u);
    notice(OTGSITE::doneNotice(omniTgsUndo.sites, plan.left > 0 || omniTgsUndo.sites < int(plan.sites.size())));
    omniTgFocus = active();
    omniShellDirty = true;
    fprintf(stderr, "OMNI TAB GROUP SITE: %d site group(s), %zu tab(s), %d left by the limit, %zu group(s)\n",
            omniTgsUndo.sites, plan.tabCount(), plan.left, omniTgModel.groups.size());
}
static void omniTgsUndoNow()
{
    const std::vector<const void*> before = omniTgsUndo.order;
    const int n = OTGSITE::undo(omniTgModel, omniTgsUndo);
    omniTgsUndo = OTGSITE::Undo();
    std::vector<const void*> now;
    for (auto& t : tabs) now.push_back(t.get());
    const std::vector<size_t> ord = OTGSITE::restoreOrder(now, before);
    const void* shown = active();
    std::vector<std::unique_ptr<Tab>> next;
    next.reserve(tabs.size());
    for (size_t i : ord) next.push_back(std::move(tabs[i]));
    tabs = std::move(next);
    for (size_t i = 0; i < tabs.size(); ++i) if (tabs[i].get() == shown) selected = i;
    omniTgNormalize();   // pinned, groups, ungrouped again (tabs pinned / grouped meanwhile keep their block)
    omniTgFocus = active();
    omniShellDirty = true;
    notice(OTGSITE::undoneNotice());
    fprintf(stderr, "OMNI TAB GROUP SITE: undo, %d group(s) removed, %zu group(s)\n", n, omniTgModel.groups.size());
}
// omniTacMenuInput: first. True: the row was ours.
static bool omniTgsMenuInput(const OmniFxRow& r, int b)
{
    if (r.id != OTGSITE::kRowId || b != SDL_CONTROLLER_BUTTON_A) return false;
    if (!r.enabled) return true;
    if (r.label == OTGSITE::undoLabel()) {   // decided by what the row said, never by the clock alone
        if (OTGSITE::undoable(omniTgsUndo, omniTgModel, SDL_GetTicks())) omniTgsUndoNow();
        else { omniTgsUndo = OTGSITE::Undo(); notice(OTGSITE::tooLateNotice()); }
    } else {
        omniTgsGroup();
    }
    omniFxPop();
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniTabActions.h" // OMNI_TAB_ACTIONS_V1: tab menu actions: duplicate, move, close others / right, reload / bookmark all (pure)\n',
         '#include "OmniTabActions.h" // OMNI_TAB_ACTIONS_V1: tab menu actions: duplicate, move, close others / right, reload / bookmark all (pure)\n'
         '#include "OmniTabGroupSite.h" /* OMNI_TAB_GROUP_SITE_V1: Group tabs by site: plan, undo (pure) */\n'),
    ],
    'OmniFeatures3Decl.h': [
        ('static bool omniTacMenuInput(const OmniFxRow& r, int b);     // omniTgMenuInput: first\n',
         'static bool omniTacMenuInput(const OmniFxRow& r, int b);     // omniTgMenuInput: first\n'
         '/* OMNI_TAB_GROUP_SITE_V1 (OmniTabGroupSiteShell.h): Group tabs by site / Undo grouping, in the tab menu */\n'
         'static void omniTgsMenuRow(OmniFxPanel& p);                   /* omniTacMenuRows: first among the actions */\n'
         'static bool omniTgsMenuInput(const OmniFxRow& r, int b);      /* omniTacMenuInput: first */\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniTabActionsShell.h" // OMNI_TAB_ACTIONS_V1 (after tab groups: it extends their tab menu)\n',
         '#include "OmniTabActionsShell.h" // OMNI_TAB_ACTIONS_V1 (after tab groups: it extends their tab menu)\n'
         '#include "OmniTabGroupSiteShell.h" /* OMNI_TAB_GROUP_SITE_V1 */\n'),
    ],
    'OmniTabActionsShell.h': [
        ('    const bool full = omniF3TabsFull();\n',
         '    omniTgsMenuRow(p); /* OMNI_TAB_GROUP_SITE_V1: Group tabs by site / Undo grouping (row 7546) */\n'
         '    const bool full = omniF3TabsFull();\n'),
        ('    if (!OTAC::isRow(r.id) || b != SDL_CONTROLLER_BUTTON_A) return false;\n',
         '    if (omniTgsMenuInput(r, b)) return true; /* OMNI_TAB_GROUP_SITE_V1 */\n'
         '    if (!OTAC::isRow(r.id) || b != SDL_CONTROLLER_BUTTON_A) return false;\n'),
    ],
}
NEEDS = (('OMNI_TAB_GROUPS_V1_R2', 'OmniBrowser.cpp', 'apply_tab_groups.py'),
         ('OMNI_TAB_ACTIONS_V1', 'OmniBrowser.cpp', 'apply_tab_actions.py'),
         ('OMNI_TAB_ACTIONS_V1_R2', 'OmniTabActionsShell.h', 'apply_tab_actions.py'),
         ('OMNI_LINK_PREVIEW_V1', 'OmniLinkPreview.h', 'apply_link_preview.py'),
         ('OMNI_TAB_GROUPS_V1', 'OmniTabGroups.h', 'apply_tab_groups.py'))


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
    """Before a first apply: no other patch or tree file uses this patch's ids or names. Skipped in the name scan:
    apply_controls_help.py and its siblings (the guide names other patches' handlers) and any sibling that carries this
    patch's MARK (it refers to us on purpose)."""
    word = re.compile(r'\b(%s)\b' % '|'.join(IDS))
    name = re.compile('|'.join(NAMES))
    mine = {'OmniTabGroupSite.h', 'OmniTabGroupSiteShell.h'}
    for f in sorted(HERE.glob('apply_*.py')):
        if f.name == Path(__file__).name or f.name.startswith('apply_controls_help'):
            continue
        raw = f.read_text(encoding='utf-8', errors='replace')
        if MARK in raw:
            continue
        m = name.search(code_only(raw))   # numeric ids: engine tree only (a sibling's notes list other patches' ids)
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
    for need, f, tool in NEEDS:
        p = root / f
        if not p.exists() or need not in p.read_bytes().decode('utf-8'):
            sys.exit('%s: %s missing: %s first' % (f, need, tool))
    if MARK not in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8'):
        ids_free()
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniTabGroupSite.h', PURE, 'OmniTabGroups.h'),
            write_new('OmniTabGroupSiteShell.h', SHELL, 'OmniTabActionsShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
