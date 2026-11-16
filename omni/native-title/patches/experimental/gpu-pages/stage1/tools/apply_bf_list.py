#!/usr/bin/env python3
"""OMNI_BF_LIST_V1 (2026-11-16): "Back history": hold Circle while browsing for the tab's earlier / later pages.

What existed (grep of the patched tree, recipe order up to apply_ublock_refine.py + apply_button_map.py)
  Back while browsing is Circle: button() -> `else if (button == SDL_CONTROLLER_BUTTON_B) omniFxBack();` (OmniBrowser.cpp,
  OMNI_FEATURES_V1), and D-pad left via omniFxDpadSide (unless Browser settings makes the D-pad switch tabs).
  OMNI_BUTTON_MAP_V1 cannot remap Circle (its slots: Triangle, Square, R3, L3, touchpad, L2 + face buttons); it can map
  one of those to "Back" (which runs omniFxBack). Nothing holds Circle today: SDL button events go
  omniL2Chord -> omniFxButtonEvent (screenshot chord, magnifier chord, hold Cross) -> omniShoulderButton, which calls
  button() on the press; a Circle release reached nothing. No other code reads Circle's held state.
  WebKit C API (s1 build headers): WKPageGetBackForwardList, WKBackForwardListGetBackListCount / GetForwardListCount /
  GetItemAtIndex(list, -1 = previous, +1 = next), WKBackForwardListItemCopyTitle / CopyURL, WKPageGoToBackForwardListItem.
  OmniBrowser.cpp already includes WKBackForwardListRef.h (OMNI_FEATURES_V3); WKBackForwardListItemRef.h is added.

What the user sees now
  - Hold Circle (0.5 s) on a page, nothing open over it: a list "Back history" opens. Rows, newest first: the later
    pages (furthest at the top), the current page (marked "Current page"), then the earlier pages going back in time;
    at most 15 each way (the nearest ones). Each row: the page title (or its address when it has none; one line,
    control characters as spaces, cut at a UTF-8 character boundary with "..."), and the host on the right of it.
    The row of the page before is focused. D-pad up / down picks (L1 / R1 page), Cross goes there
    (WKPageGoToBackForwardListItem; the menus close), Cross on the current page just closes the list, Circle closes it.
    Subtitle: "3 earlier pages, 1 later page" (+ "(the nearest 15 shown)", + ". Private tab: never saved").
    No earlier or later page: notice "No other pages in this tab yet".
  - A Circle press shorter than 0.5 s is the same Back as before, run on release (as hold Cross clicks on release).
    The hold's own release does nothing (no second Back). A release that never reaches us (another handler took the
    UP) is found by omniFxTick from the pad's state and resolved the same way.
  - Options > Browse: a row "Back history" after Forward (disabled with no earlier / later page); Cross opens the same
    list over the menu (Circle comes back to the menu).
  Circle keeps its other meanings: the hold only starts where Circle would run omniFxBack: an active, not crashed tab,
  no keyboard / page editing / settings / full screen / overlay or panel / find bar / quick-access focus / hold Cross
  in progress, not a built-in omni://pages tab, the Master Control page, YouTube TV keys or a Media downloads view
  (those get Circle first, as before), not in test modes. L2 + Circle (omniL2Chord) and the magnifier's Circle run
  before it. A button that OMNI_BUTTON_MAP_V1 maps to Back stays press-only.
Private tabs: the list is read from the tab's own in-memory back/forward list when it opens, shown, and dropped when the
  panel closes (the retained items are released by omniBflTick); nothing is written anywhere, for any tab.
Stale entries: Cross looks the chosen item up again in the tab's current list (pointer identity); gone (the tab
  navigated meanwhile) or the tab closed / no longer active: notice "That page is no longer in this tab's history".

Pure part: engine/entry/OmniBfList.h (from tools/OmniBfList.h: order, initial row, UTF-8 shortening, hosts, row texts,
  hold timing). Tests: tools/test_bf_list.cpp
  (g++ -std=c++20 -Wall -Wextra -Werror -I. test_bf_list.cpp -o t && ./t).
Shell part: engine/entry/OmniBfListShell.h (written by this script), namespace alias OBFL, names omniBfl*.
Ids: panel kind 7593, Options row 8593 (checked unused in every apply_*.py and the tree; >= 900, so its quick-menu hook
  sits before the `r.id >= 900` line).

Anchors (each once; whole lines; new lines inserted after them, or before for the declaration; CRLF / LF kept):
  OmniBrowser.cpp   the WKBackForwardListRef.h include line (OMNI_FEATURES_V3; item header + pure include after);
                    the OmniHistoryKeepShell.h include line (shell include after)
  OmniFeatures.h    the omniMagChord declaration line (declarations before); the omniMagChord call line in
                    omniFxButtonEvent (hold Circle after); `static void omniFxTick()` + `{` + `omniFxLoad();` (tick after)
  OmniQuickMenu.h   the omniSsQuickAction declaration (declarations after); the Forward add() line (row after); the
                    reading-list omniMqGroup case (Browse case after); the omniNlQuickAction input line (input after)
Controls guide (OmniControlsHelp.h) is not edited here; the row to add is in the report.
Apply AFTER apply_history_keep.py, apply_magnifier.py, apply_night_light.py, apply_screenshot_gallery.py,
  apply_reading_list.py (their lines are anchors). Independent of apply_button_map.py.
usage: apply_bf_list.py <engine tree>   (anchored, idempotent, keeps each file's line endings; re-run: "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_BF_LIST_V1'
HERE = Path(__file__).resolve().parent
if len(sys.argv) != 2:
    sys.exit('usage: apply_bf_list.py <engine tree>')
root = Path(sys.argv[1]) / 'engine' / 'entry'
IDS = ('7593', '8593')
NAMES = ('OBFL', 'omniBfl', 'OmniBfList', 'OMNI_BF_LIST')

SHELL = r'''// OMNI_BF_LIST_V1: "Back history" (shell side): hold Circle while browsing, or Options > Browse > Back history, for
// the tab's earlier and later pages. Included from OmniBrowser.cpp after OmniHistoryKeepShell.h. The pure part is
// OmniBfList.h; the reasons are in tools/apply_bf_list.py. Memory only: nothing here is written anywhere.
#pragma once

namespace OBFL = OmniBfList;

// The list as read when it opened (rows and the items they go to, same order). The items are retained only while the
// panel is on the stack (omniBflTick drops them).
struct OmniBflSnap {
    const void* tab = nullptr;   // checked with omniTabAlive before use
    std::vector<OBFL::Row> rows;
    std::vector<WKRetainPtr<WKBackForwardListItemRef>> items;
    bool privateTab = false;
    unsigned back = 0, forward = 0;
};
static OmniBflSnap omniBflSnap;
static OBFL::Hold omniBflHoldState;

static std::string omniBflStr(WKStringRef s) { return s ? OmniTest::toStd(s) : std::string(); }
static Tab* omniBflTab()
{
    for (auto& t : tabs) if (t.get() == omniBflSnap.tab) return t.get();
    return nullptr;
}
// Where a Circle press would run omniFxBack (button()'s browsing tail) and nothing else wants Circle first.
static bool omniBflEligible()
{
    Tab* t = active();
    if (!t || t->crashed || t->omniPagesTab || editing || pageEditing || settingsOpen || pageFullscreen || omniTestMode()) return false;
    if (omniOverlayOpen() || omniFindBarOpen() || omniFxHoldState.active || omniMqFocus >= 0) return false;
    if (omniYtTvKeysActive() || omniMcOrigin(t->url)) return false;
    if (omniMediaDownloadsEnabled && omniSavedOwnedView() != OmniSavedView::None) return false;
    return true;
}

static void omniBflBuild(OmniFxPanel& p)
{
    for (const OBFL::Row& r : omniBflSnap.rows) {
        OmniFxRow row;
        row.id = r.offset;
        row.label = r.label;
        row.detail = r.host;
        row.value = r.value;
        p.rows.push_back(row);
    }
}
static void omniBflGo(int offset)
{
    WKRetainPtr<WKBackForwardListItemRef> item;
    for (size_t i = 0; i < omniBflSnap.rows.size() && i < omniBflSnap.items.size(); ++i)
        if (omniBflSnap.rows[i].offset == offset) item = omniBflSnap.items[i];
    Tab* t = omniBflTab();
    if (offset == 0) { omniFxPop(); return; }   // the current page: just close the list
    omniFxCloseAll();
    omniBflSnap = OmniBflSnap();
    if (!t || t != active() || !item) { notice(OBFL::goneNotice()); return; }
    WKBackForwardListRef list = WKPageGetBackForwardList(t->page);
    bool found = false;
    if (list) {
        const int back = int(WKBackForwardListGetBackListCount(list)), forward = int(WKBackForwardListGetForwardListCount(list));
        for (int i = -back; i <= forward && !found; ++i) found = i && WKBackForwardListGetItemAtIndex(list, i) == item.get();
    }
    if (!found) { notice(OBFL::goneNotice()); return; }
    fprintf(stderr, "OMNI BACK HISTORY: go %+d\n", offset); fflush(stderr);
    WKPageGoToBackForwardListItem(t->page, item.get());
}
static bool omniBflInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    omniBflGo(r.id);
    return true;
}
static void omniBflOpen()
{
    Tab* t = active();
    if (!t) return;
    WKBackForwardListRef list = WKPageGetBackForwardList(t->page);
    const unsigned back = list ? WKBackForwardListGetBackListCount(list) : 0, forward = list ? WKBackForwardListGetForwardListCount(list) : 0;
    OmniBflSnap s;
    s.tab = t; s.privateTab = t->omniPrivate; s.back = back; s.forward = forward;
    std::vector<int> shown;
    if (back || forward) {
        for (int off : OBFL::offsets(back, forward)) {
            WKBackForwardListItemRef item = WKBackForwardListGetItemAtIndex(list, off);
            if (!item) continue;
            auto title = adoptWK(WKBackForwardListItemCopyTitle(item));
            auto url = adoptWK(WKBackForwardListItemCopyURL(item));
            const std::string u = url ? omniBflStr(adoptWK(WKURLCopyString(url.get())).get()) : std::string();
            s.rows.push_back(OBFL::makeRow(off, omniBflStr(title.get()), u));
            s.items.emplace_back(item);   // retained while the list is up
            shown.push_back(off);
        }
    }
    if (s.rows.size() < 2) { notice(OBFL::emptyNotice()); omniShellDirty = true; return; }
    omniBflSnap = std::move(s);
    OmniFxPanel p;
    p.kind = OBFL::kPanelKind;
    p.title = "Back history";
    p.subtitle = OBFL::subtitle(omniBflSnap.privateTab, back, forward);
    p.w = 900; p.rowH = 56; p.maxVisible = 9;
    p.build = omniBflBuild; p.input = omniBflInput;
    p.faces = { { 0, "Go there" }, { 1, "Close" } };
    p.sel = OBFL::initialRow(shown);
    omniFxPush(std::move(p));
    fprintf(stderr, "OMNI BACK HISTORY: open, %u back, %u forward\n", back, forward); fflush(stderr);
}

static void omniBflResolve(OBFL::Act a)
{
    if (a == OBFL::Act::Back) button(SDL_CONTROLLER_BUTTON_B);   // a short press: the ordinary Circle, through button()
    else if (a == OBFL::Act::Open && omniBflEligible()) omniBflOpen();
    if (a != OBFL::Act::None) omniShellDirty = true;
}
// From omniFxButtonEvent, after the magnifier chord: Circle while browsing is held back until release or 0.5 s.
static bool omniBflButtonEvent(const SDL_ControllerButtonEvent& event)
{
    if (event.button != SDL_CONTROLLER_BUTTON_B) return false;
    OBFL::Hold& h = omniBflHoldState;
    if (event.type == SDL_CONTROLLERBUTTONDOWN) {
        if (h.active || !omniBflEligible()) return false;
        auto* previous = controller;
        omniActivatePad(event.which);
        if (previous != controller) omniShoulderReset();
        h.begin(int(event.which), SDL_GetTicks());
        return true;
    }
    if (event.type != SDL_CONTROLLERBUTTONUP || !h.owns(int(event.which))) return false;
    omniBflResolve(h.release());
    return true;
}
// From omniFxTick, every pass: the hold timer (and a release we never saw), and the list's retained items.
static void omniBflTick()
{
    OBFL::Hold& h = omniBflHoldState;
    if (h.active) {
        SDL_GameController* pad = SDL_GameControllerFromInstanceID(SDL_JoystickID(h.pad));
        if (!pad) h.cancel();
        else omniBflResolve(h.tick(SDL_GetTicks(), SDL_GameControllerGetButton(pad, SDL_CONTROLLER_BUTTON_B) != 0));
    }
    if (!omniBflSnap.rows.empty() || !omniBflSnap.items.empty()) {
        bool open = false;
        for (auto& p : omniFxStack) open |= p.kind == OBFL::kPanelKind;
        if (!open) omniBflSnap = OmniBflSnap();
    }
}

// Options > Browse: "Back history" after Forward.
static void omniBflQuickRow(OmniFxPanel& p)
{
    Tab* t = active();
    OmniFxRow r;
    r.id = OBFL::kQuickRowId;
    r.label = "Back history";
    r.enabled = t && (WKPageCanGoBack(t->page) || WKPageCanGoForward(t->page));
    p.rows.push_back(r);
}
static bool omniBflQuickAction(int id)
{
    if (id != OBFL::kQuickRowId) return false;
    omniBflOpen();   // over the menu: Circle comes back to it, Cross on a page closes both
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include <WebKit/WKBackForwardListRef.h> // OMNI_FEATURES_V3: unloaded tabs\n',
         '#include <WebKit/WKBackForwardListRef.h> // OMNI_FEATURES_V3: unloaded tabs\n'
         '#include <WebKit/WKBackForwardListItemRef.h> // OMNI_BF_LIST_V1: Back history titles / addresses\n'
         '#include "OmniBfList.h" // OMNI_BF_LIST_V1: Back history list model and hold timing (pure)\n'),
        ('#include "OmniHistoryKeepShell.h" /* OMNI_HISTORY_KEEP_V1 */\n',
         '#include "OmniHistoryKeepShell.h" /* OMNI_HISTORY_KEEP_V1 */\n'
         '#include "OmniBfListShell.h" /* OMNI_BF_LIST_V1: Back history (hold Circle, Options > Browse) */\n'),
    ],
    'OmniFeatures.h': [
        ('static bool omniMagChord(const SDL_ControllerButtonEvent& event); // OMNI_MAGNIFIER_V1 (OmniMagnifierShell.h)\n',
         'static bool omniBflButtonEvent(const SDL_ControllerButtonEvent& event); // OMNI_BF_LIST_V1 (OmniBfListShell.h): hold Circle\n'
         'static void omniBflTick(); // OMNI_BF_LIST_V1\n'
         'static bool omniMagChord(const SDL_ControllerButtonEvent& event); // OMNI_MAGNIFIER_V1 (OmniMagnifierShell.h)\n'),
        ('    if (omniMagChord(event)) return true; // OMNI_MAGNIFIER_V1: L2 + L3 (2x, 3x, off); Circle closes the lens\n',
         '    if (omniMagChord(event)) return true; // OMNI_MAGNIFIER_V1: L2 + L3 (2x, 3x, off); Circle closes the lens\n'
         '    if (omniBflButtonEvent(event)) return true; // OMNI_BF_LIST_V1: Circle while browsing: Back on release, held 0.5 s: Back history\n'),
        ('static void omniFxTick()\n{\n    omniFxLoad();\n',
         'static void omniFxTick()\n{\n    omniFxLoad();\n'
         '    omniBflTick(); // OMNI_BF_LIST_V1: hold Circle timer; drops the list\'s items once it is closed\n'),
    ],
    'OmniQuickMenu.h': [
        ('static bool omniSsQuickAction(int id); // OMNI_SCREENSHOT_GALLERY_V1 (OmniShotGalleryShell.h)\n',
         'static bool omniSsQuickAction(int id); // OMNI_SCREENSHOT_GALLERY_V1 (OmniShotGalleryShell.h)\n'
         'static void omniBflQuickRow(OmniFxPanel& p); // OMNI_BF_LIST_V1 (OmniBfListShell.h): Back history\n'
         'static bool omniBflQuickAction(int id); // OMNI_BF_LIST_V1\n'),
        ('    add(omniQmForward, "Forward", t && WKPageCanGoForward(t->page), omniIconForward);\n',
         '    add(omniQmForward, "Forward", t && WKPageCanGoForward(t->page), omniIconForward);\n'
         '    omniBflQuickRow(p); // OMNI_BF_LIST_V1: Back history\n'),
        ('    case OmniReadingList::kTileSave: case OmniReadingList::kTileList: return 1; // OMNI_READING_LIST_V1: Browse\n',
         '    case OmniReadingList::kTileSave: case OmniReadingList::kTileList: return 1; // OMNI_READING_LIST_V1: Browse\n'
         '    case OmniBfList::kQuickRowId: return 1; // OMNI_BF_LIST_V1: Back history (Browse)\n'),
        ('    if (omniNlQuickAction(r.id)) return true; // OMNI_NIGHT_LIGHT_V1 (before the >= 900 rows)\n',
         '    if (omniNlQuickAction(r.id)) return true; // OMNI_NIGHT_LIGHT_V1 (before the >= 900 rows)\n'
         '    if (omniBflQuickAction(r.id)) return true; // OMNI_BF_LIST_V1: Back history (before the >= 900 rows)\n'),
    ],
}
NEEDS = {'OmniBrowser.cpp': ('OMNI_FEATURES_V3', 'OMNI_HISTORY_KEEP_V1'),
         'OmniFeatures.h': ('OMNI_MAGNIFIER_V1',),
         'OmniQuickMenu.h': ('OMNI_SCREENSHOT_GALLERY_V1', 'OMNI_NIGHT_LIGHT_V1', 'OMNI_READING_LIST_V1')}


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
    mine = {'OmniBfList.h', 'OmniBfListShell.h'}
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
    pure = (HERE / 'OmniBfList.h').read_text(encoding='utf-8')
    if MARK not in pure:
        sys.exit('OmniBfList.h: %s missing' % MARK)
    msgs = [write_new('OmniBfList.h', pure, 'OmniQuickMenu.h'),
            write_new('OmniBfListShell.h', SHELL, 'OmniFeatures.h')]
    msgs += [patch(fname, edits) for fname, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
