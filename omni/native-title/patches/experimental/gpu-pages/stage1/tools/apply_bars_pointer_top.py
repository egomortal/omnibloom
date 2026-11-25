#!/usr/bin/env python3
"""OMNI_BARS_POINTER_TOP_V1 (2026-11-25, owner: on movy the top bar keeps coming out and blocks the Play button).

With Auto-hide on, ANY input woke the bars: moving the pointer (left stick / mouse) and pressing Cross (= click) slid
the top bar in, which pushes the page down by the bar's height. On a page that fills the screen (movy's player before
playback, a site's own "fake" full screen) the user moves down to the Play button, presses Cross, and the bar slides in
and moves the button away / covers it.

Now, while the bars are hidden:
  - pointer movement shows them only when the pointer is in the top band (within 1.5 x the top bar's height of the top
    edge): push the pointer up to get the bars, as with an auto-hiding taskbar;
  - Cross / a mouse click shows them only when the pointer is in that band (a click on the page stays a click on the
    page);
  - every other button (Options, Triangle, L1 / R1, ...), scrolling (per its own setting), typing and panels behave as
    before.
Input still counts as activity, so bars that are already shown do not hide while you use them.
usage: apply_bars_pointer_top.py <title tree root holding engine/entry>"""
import sys
from pathlib import Path

MARK = 'OMNI_BARS_POINTER_TOP_V1'
p = Path(sys.argv[1]) / 'engine/entry/OmniBrowser.cpp'
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK in s:
    print('already', p.name); sys.exit(0)


def rep(old, new):
    global s
    if s.count(old) != 1:
        sys.exit('%s: anchor found %d times: %r' % (p.name, s.count(old), old[:80]))
    s = s.replace(old, new, 1)


# 1. pointer movement / clicks reveal the bars only from the top band
rep('    if (omniChromeWanted || !omniAutoHideActive()) { omniChromeWanted = true; return; }\n'
    '    // Showing the bars pushes the page down by the top bar\'s height. Pointer movement leaves them\n',
    '    if (omniChromeWanted || !omniAutoHideActive()) { omniChromeWanted = true; return; }\n'
    '    // ' + MARK + ': hidden bars come back for the pointer only at the top edge (movement or a click there).\n'
    '    if (pointerOnly && !editing && !settingsOpen && pointerY > omniTopH() * 1.5f) return;\n'
    '    // Showing the bars pushes the page down by the top bar\'s height. Pointer movement leaves them\n')
rep('static void omniChromeWake(bool pointerMotion)\n{\n',
    'static void omniChromeWake(bool pointerMotion, bool pointerOnly)\n{\n')
# every existing call keeps its meaning: pointerOnly = pointerMotion unless a click passes true explicitly
rep('static void omniChromeScroll() { if (omniScrollRevealsChrome) omniChromeWake(); else omniLastInput = SDL_GetTicks(); }\n',
    'static void omniChromeWake(bool pointerMotion) { omniChromeWake(pointerMotion, pointerMotion); }   // ' + MARK + '\n'
    'static void omniChromeScroll() { if (omniScrollRevealsChrome) omniChromeWake(); else omniLastInput = SDL_GetTicks(); }\n')
# 2. Cross (the controller's click) only from the top band
rep('    if (scrollKey) omniChromeScroll(); else omniChromeWake();\n',
    '    if (scrollKey) omniChromeScroll();\n'
    '    else omniChromeWake(false, b == SDL_CONTROLLER_BUTTON_A);   // ' + MARK + ': Cross = a click on the page\n')
# 3. a mouse click the same
rep('    else if (e.type == SDL_MOUSEBUTTONDOWN || e.type == SDL_KEYDOWN || e.type == SDL_TEXTINPUT) omniChromeWake();\n',
    '    else if (e.type == SDL_MOUSEBUTTONDOWN) omniChromeWake(false, true);   // ' + MARK + '\n'
    '    else if (e.type == SDL_KEYDOWN || e.type == SDL_TEXTINPUT) omniChromeWake();\n')

p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('bars pointer top: patched', p.name)
