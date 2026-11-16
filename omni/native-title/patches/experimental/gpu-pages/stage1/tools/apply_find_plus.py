#!/usr/bin/env python3
"""OMNI_FIND_PLUS_V1 (2026-11-16): a TV-friendly Find on page.

What existed (OMNI_EVERYDAY_V1's find block in OmniBrowser.cpp, audited in the real state T):
  - opened from Options > More > Find on page (omniMenuFind), the Options menu tile (omniQmFind) and Quick access
    (omniQaFind), all calling omniFindStart(): the on-screen keyboard (omniKbEdit, so word chips work; learning skips
    private tabs) typed one GLOBAL omniFindQuery, prefilled with the last search of ANY tab (private tabs leaked theirs);
  - WKPageFindString(CaseInsensitive | WrapAround | ShowHighlight | ShowFindIndicator, max 1000): all matches were
    already highlighted, next / previous by D-pad right / left, Triangle edit, Circle close (WKPageHideFindUI);
  - "N of M" from didFindString's matchCount, the position guessed by arithmetic with one global "last step";
    "No matches" in omniBad (small text only);
  - bugs: more than 1000 matches comes back as kWKMoreThanMaximumMatchCount (0xffffffff) -> int -1 -> the bar said
    "..." forever; fast mixed presses (R then L) skewed the position (one global step for answers still in flight);
    one bar for one tab (opening it on tab B forgot tab A's); Escape opened the Options menu instead of closing it.

What the C API offers (checked in the engine's WebKit tree (s1/webkit)):
  WKPageFindString + WKPageFindClientV0 { didFindString(matchCount), didFailToFindString, didCountStringMatches }.
  The C adapter (WKPage.cpp WKPageSetPageFindClient) DROPS the match index and didWrap that WebKit computes; so the
  position and the wrap are tracked here (pure, below), the same arithmetic as FindController::updateMatchIndex.
  WKPageCountStringMatches would walk the DOM a second time for the same number (marking already counts:
  FindController::updateFindUIAfterIncrementalFind), so it is not used. WKPageFindStringMatches (+ match images) is
  heavier still. kWKFindOptionsShowHighlight marks every match; ShowOverlay (dimming page overlay) is left off.
  WKPageHideFindUI unmarks all matches and hides the indicator (FindController::hideFindUI).

What the user gets now
  - The bar is per tab: each tab remembers its last search and its Match case setting for the session (memory only,
    nothing written; a private tab's search is never offered in another tab and dies with the tab). Switching back
    to a tab whose bar was open shows it again (its highlights were never removed).
  - Next / previous: R1 / L1 (new) and D-pad right / left. D-pad up / down still scroll the page, Cross clicks.
    (L1 / R1 reach the bar: omniShoulderContext is not "allowed" while omniFindBarOpen(), so they pass to button().)
  - "3 of 17", "1000+ matches", "Searching..." (new search), "No matches" as white on a red pill with the query in
    red and a red underline under the bar.
  - Wrap-around notice: "Reached the end of the page - back to the first match" / "Reached the top ...".
  - Square toggles Match case (the "Aa" chip, clickable too; notice "Match case: on/off"), searching again.
  - Circle, the X, and now Escape close the bar and clear every highlight. Navigating the tab closes it (query kept).
  - The tip pill uses the controller's names ({L1} ... via OmniControlsHelp::expand), was "Y edit B close" on PS too.

Files: engine/entry/OmniFindPlus.h (pure, copied from tools/OmniFindPlus.h; tested by tools/test_find_plus.cpp:
  g++ -std=c++20 -Wall -Wextra -I<tools> test_find_plus.cpp -o t && ./t), engine/entry/OmniFindPlusShell.h (copied
  from tools/OmniFindPlusShell.h; included where the old block was, so every name before it is visible).

Anchors in OmniBrowser.cpp (exactly once each; MARK makes the file idempotent; LF / CRLF kept):
  - '#include <WebKit/WKFindOptions.h>' line (OMNI_EVERYDAY_V1): + the pure include.
  - the find block, from its '// --- find on page ---' line to the end of omniEverydayTabCreated (the
    'WKPageSetPageFindClient(tab->page, &find.base);' line + '}'): replaced by the shell include. The block must hash
    to BLOCK_SHA256 (LF), else nothing is written.
  - omniEverydayFinished's 'if (omniFindTab == &tab) omniFindOpenFlag = false;' line -> omniFndFinished(tab).
  - the SDL Escape line ('} else if (key == SDLK_ESCAPE) { if (pageFullscreen) ...'): an Escape-closes-find branch
    goes before it.
usage: apply_find_plus.py <engine tree>   (re-run prints "already")
"""
import hashlib
import sys
from pathlib import Path

MARK = 'OMNI_FIND_PLUS_V1'
HERE = Path(__file__).resolve().parent
root = Path(sys.argv[1]) / 'engine' / 'entry'
NAME = 'OmniBrowser.cpp'

BLOCK_START = '// --- find on page --------------------------------------------------------------------------------\n'
BLOCK_END = '    WKPageSetPageFindClient(tab->page, &find.base);\n}\n'
BLOCK_SHA256 = 'a768721bb948040dda79ea5e9e65494e41f64b92199bdfa45d7e0200960d6fad'   # the LF block, start line through end lines (4675 bytes)
BLOCK_NEW = ('// --- find on page (OMNI_FIND_PLUS_V1: OmniFindPlusShell.h; was OMNI_EVERYDAY_V1\'s block) ---------------------\n'
             '#include "OmniFindPlusShell.h" // OMNI_FIND_PLUS_V1: per-tab find bar, L1/R1, count, wrap notice, Match case\n')

EDITS = [
    ('#include <WebKit/WKFindOptions.h>\n',
     '#include <WebKit/WKFindOptions.h>\n'
     '#include "OmniFindPlus.h" // OMNI_FIND_PLUS_V1: find bar state per tab, count label, find options (pure)\n'),
    ('    if (omniFindTab == &tab) omniFindOpenFlag = false;\n',
     '    omniFndFinished(tab); // OMNI_FIND_PLUS_V1: a navigation closes this tab\'s find bar (query kept)\n'),
    ('            } else if (key == SDLK_ESCAPE) { if (pageFullscreen) WKViewRequestExitFullScreen(active()->view.get()); else omniFxQuickMenuShow(); } // OMNI_FEATURES_V1: Esc no longer quits\n',
     '            } else if (key == SDLK_ESCAPE && omniFindBarOpen()) { omniFindClose(); // OMNI_FIND_PLUS_V1: Esc closes the find bar + highlights (next line\'s brace ends it)\n'
     '            } else if (key == SDLK_ESCAPE) { if (pageFullscreen) WKViewRequestExitFullScreen(active()->view.get()); else omniFxQuickMenuShow(); } // OMNI_FEATURES_V1: Esc no longer quits\n'),
]


def eol_of(s):
    return '\r\n' if s.count('\r\n') * 2 > s.count('\n') else '\n'


def block_span(s, e):
    a = s.find(BLOCK_START.replace('\n', e))
    if a < 0 or s.count(BLOCK_START.replace('\n', e)) != 1:
        sys.exit('%s: find block start found %d times' % (NAME, s.count(BLOCK_START.replace('\n', e))))
    end = BLOCK_END.replace('\n', e)
    if s.count(end) != 1:
        sys.exit('%s: find block end found %d times' % (NAME, s.count(end)))
    b = s.find(end)
    if b < a:
        sys.exit('%s: find block end before its start' % NAME)
    b += len(end)
    digest = hashlib.sha256(s[a:b].replace('\r\n', '\n').encode('utf-8')).hexdigest()
    if digest != BLOCK_SHA256:
        sys.exit('%s: the find block is not the audited OMNI_EVERYDAY_V1 one (sha256 %s)' % (NAME, digest))
    return a, b


def write_new(name, src, like):
    raw = (root / like).read_bytes()
    nl = '\r\n' if raw.count(b'\r\n') * 2 > raw.count(b'\n') else '\n'
    data = (HERE / src).read_bytes().decode('utf-8').replace('\r\n', '\n').replace('\n', nl).encode('utf-8')
    h = root / name
    if h.exists() and h.read_bytes() == data:
        return name + ': already'
    h.write_bytes(data)
    return name + ': written'


def patch():
    p = root / NAME
    s = p.read_bytes().decode('utf-8')
    if MARK in s:
        return NAME + ': already'
    e = eol_of(s)
    for old0, _ in EDITS:   # every anchor is checked before anything is written
        old = old0.replace('\n', e)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (NAME, s.count(old), old0[:90]))
    a, b = block_span(s, e)
    s = s[:a] + BLOCK_NEW.replace('\n', e) + s[b:]
    for old0, new0 in EDITS:
        s = s.replace(old0.replace('\n', e), new0.replace('\n', e), 1)
    for gone in ('omniFindOpenFlag', 'omniFindTab'):
        if gone in s:
            sys.exit('%s: %s is still used outside the replaced block' % (NAME, gone))
    p.write_bytes(s.encode('utf-8'))
    return NAME + ': applied'


def main():
    if 'OMNI_CONTROLS_HELP_V1' not in (root / NAME).read_bytes().decode('utf-8'):
        sys.exit(NAME + ': OMNI_CONTROLS_HELP_V1 missing (the tip uses OmniControlsHelp::expand): apply_controls_help.py first')
    s = (root / NAME).read_bytes().decode('utf-8')
    if MARK not in s:   # check before writing the headers
        e = eol_of(s)
        for old0, _ in EDITS:
            if s.count(old0.replace('\n', e)) != 1:
                sys.exit('%s: anchor found %d times: %r' % (NAME, s.count(old0.replace('\n', e)), old0[:90]))
        block_span(s, e)
    msgs = [write_new('OmniFindPlus.h', 'OmniFindPlus.h', 'OmniHttpsOnly.h'),
            write_new('OmniFindPlusShell.h', 'OmniFindPlusShell.h', NAME),
            patch()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
