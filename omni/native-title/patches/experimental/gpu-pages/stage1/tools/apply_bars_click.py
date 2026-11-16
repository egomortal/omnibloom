#!/usr/bin/env python3
"""OMNI_BARS_CLICK_V1 (2026-11-16, owner: "pressing the below when clicking above", the tab "x" opened the page
link): clicks in the top bar landed 52 px too low while the quick-access row is hidden (OMNI_BARS_HIDE_V1).

click() maps a pointer inside the top bar to bar coordinates with `by = y + (top - omniPageTop())`, so that a bar
slid up by Auto-hide is hit where it is drawn. With the quick-access row hidden the bar is not slid: it simply ends at
omniTopH() (112) instead of `top` (164), so the formula added the hidden row's 52 px to every click: the tab strip's
"x" became the toolbar, the toolbar became the page (opening the link under the pointer), the settings button moved.
The slide is the drawn bar height minus the page top: omniTopH() - omniPageTop(). With the row shown omniTopH() is
`top`, so nothing changes there. Apply AFTER apply_bars_hide.py (omniTopH() comes from it).
usage: apply_bars_click.py <engine tree>"""
import sys
from pathlib import Path

MARK = 'OMNI_BARS_CLICK_V1'
p = Path(sys.argv[1]) / 'engine' / 'entry' / 'OmniBrowser.cpp'
raw = p.read_bytes()
nl = '\r\n' if b'\r\n' in raw else '\n'
s = raw.decode('utf-8')
if MARK in s:
    print('already ' + MARK)
    sys.exit(0)
if 'static int omniTopH()' not in s:
    sys.exit('OmniBrowser.cpp: omniTopH() missing: apply_bars_hide.py first')
old = '    const int omniTop = omniPageTop(), by = y < omniTop ? y + (top - omniTop) : top;'
new = ('    const int omniTop = omniPageTop(), by = y < omniTop ? y + (omniTopH() - omniTop) : top; // ' + MARK +
       ': the drawn bar height, not `top` (52 px off with the quick-access row hidden)')
if s.count(old) != 1:
    sys.exit('OmniBrowser.cpp: anchor found %d times' % s.count(old))
p.write_bytes(s.replace(old, new, 1).encode('utf-8'))
print('applied ' + MARK)
