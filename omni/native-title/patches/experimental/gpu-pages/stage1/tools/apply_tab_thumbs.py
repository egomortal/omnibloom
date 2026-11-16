#!/usr/bin/env python3
"""OMNI_TAB_THUMBS_V1 (2026-11-16): tab thumbnails: a small snapshot of each tab in the Tabs panel rows, the quick tab
switcher's tiles (OMNI_TAB_SWITCHER_V1) and the Tab memory panel rows (OMNI_TAB_MEMORY_VIEW_V1).

What the user sees
  - Tabs panel and Tab memory panel: a 64 x 36 picture of the page before each tab's title. A tab not left yet this run
    (just opened, restored, never shown) has its site letter on the site's colour instead (the switcher's letter/colour).
  - Quick tab switcher: the tile's letter square becomes a 134 x 75 picture with the site letter small in its corner.
    The new tab page keeps its "+" square.
  - Unloaded (asleep) tabs keep their last picture, grey and dimmed.
  - Visibility follows each list's existing rule: the Tabs panel and the Tab memory panel list every tab (private ones
    too, as their titles today); the switcher lists private tabs only from a private tab (OmniTabSearch::visible).

How the snapshot is taken (checked in the r-T tree, 2026-11-16) and why no title / engine change is needed
  - WebKit C API: WKViewCreateSnapshot / WKPageGetSnapshot do not exist on this port's WKView (PlayStation WKView.h has
    no snapshot call); a WKPagePaint into a small buffer would repaint the whole page in the UI process (~4 ms per full
    page today, OMNI zero-copy design table) and is skipped in zero-copy mode. Not used.
  - GPU present (OmniGpuPresent.cpp): the composed canvas holds bars, panels, the Night light tint and the magnifier lens
    over the page, and a capture there needs a cross-thread request plus a read-back one frame later (after the switch).
    Not needed: the shell already holds the page's own pixels at the moment of the switch:
      * CPU page path (default): omniPageSmall (half-size page, while omniPixelsStale, OMNI_PERF_A_S5) or the page buffer
        `pixels` (ARGB8888 from WKPagePaint) still hold the tab being left when activate() starts (activate() whitens
        `pixels` a few lines later).
      * zero-copy path (OMNI_GPUPAGES_ZEROCOPY_V1, flag): the engine's published frame (control page {frame, address,
        width, height, stride}) lies in broker host memory mapped at the SAME address in the title
        (ZERO-COPY-DESIGN.md: gpu-broker allocate MAP_SHARED|MAP_FIXED), so the shell reads it on the CPU. The address
        is checked against the broker windows (as ogp-s1-surface.inc's zcInBrokerWindow); the seqlock is read as
        omniZcTick does; the picture is dropped if the published frame moved on by 2+ while it was read (ring of 3).
  - Downscale: box filter of the 16:9 crop (the page under the bars is wider: ~5 % off each side), per thumbnail pixel
    4 columns x 2 rows (CPU) or x 1 row (zero-copy: GPU-written memory, ~1.8 GB/s per the design table): 259 200 /
    129 600 pixel reads whatever the page size. Host (test_tab_thumbs.cpp): ~0.3-0.5 ms; console estimate < 1 ms CPU,
    < 1.5 ms zero-copy. Every capture's time is logged ("OMNI TAB THUMBS:", first 6, then any >= 2 ms).
  - Only on switch-away (activate() with another tab), never per frame. omniTthSrc says which tab the page buffers / the
    last zero-copy frame were painted for (set in omniPaintPage and omniZcTick, cleared by activate()), so a close that
    activates the neighbour, or a tab left before its first paint, never stores another tab's picture. Not captured: a
    crashed tab, a tab inside its paint hold (OMNI_PAINT_HOLD_V1), test mode.
  - Memory: at most 16 thumbnails x 240 x 135 x 4 = 2 073 600 bytes, memory only (never saved; private tabs the same),
    oldest capture dropped first, a closed tab's dropped in omniFxTabClosing, dead tabs pruned at each capture.
  - Coexistence: nothing in OmniGpuPresent.cpp (Night light, magnifier and the colour-filter work are untouched).

Pure part: engine/entry/OmniTabThumbs.h (copied from tools/): crop, downscale, grey, zero-copy checks, the store.
  Tested by tools/test_tab_thumbs.cpp:  g++ -std=c++20 -O2 -Wall -Wextra -I<tools> test_tab_thumbs.cpp -o t && ./t
Shell side: engine/entry/OmniTabThumbsShell.h (copied from tools/): capture, blit, panel row mark, switcher tile.
  Names omniTth*, namespace OmniTabThumbs (alias OTTH). No new ids, files, settings or imports.

Anchors (exactly once each, whole lines; MARK makes each file idempotent):
  OmniBrowser.cpp         the OmniTabSwitcher.h include line (pure include after it); activate()'s first four lines
                          (state + declaration before, the capture call after); omniZcTick's "omniZc.lastFrame = frame;"
                          line and omniPaintPage's zero-copy return line (the paint marks after each).
  OmniFeatures3Decl.h     the omniTgRowMark declaration line (ours after it).
  OmniFeaturesPanel.h     omniFxDrawPanel's omniTgRowMark call line (the row mark after it).
  OmniTabsPage.h          the omniTmvForget line of omniFxTabClosing (ours after it).
  OmniFeatures3.h         the OmniTabSwitcherShell.h include line (ours before it: the switcher calls omniTthTile).
  OmniTabSwitcherShell.h  the two lines drawing the tile's letter square (wrapped: thumbnail first).
  Note: OmniTabSwitcherShell.h is written whole by apply_tab_switcher.py; if that script rewrites it on a re-run of a
  persistent tree, this script finds the file without MARK and wraps the two lines again.
Apply AFTER apply_tab_switcher.py, apply_tab_memory_view.py and apply_zerocopy_shell.py (recipe: after
apply_ublock_refine.py):
    python3 "$S1/tools/apply_tab_thumbs.py" "$TT" > "$LT_/apply_tab_thumbs.log" 2>&1 || { st "OMNI_TAB_THUMBS_V1 FAILED: $(tail -1 "$LT_/apply_tab_thumbs.log")"; exit 1; }
usage: apply_tab_thumbs.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_TAB_THUMBS_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'
HERE = Path(__file__).parent
PURE = HERE / 'OmniTabThumbs.h'
SHELL = HERE / 'OmniTabThumbsShell.h'

TILE_OLD = ('        fillRounded(sx, sy, sq, sq, omniRadius + 2, { c.r, c.g, c.b, 255 });\n'
            '        omniLabel(t->omniNewTabPage ? std::string("+") : OTSW::letter(site, t->title), sx + sq / 2.f, sy + sq / 2.f, omniTitle, { 255, 255, 255, 255 }, 1);\n')

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniTabSwitcher.h" // OMNI_TAB_SWITCHER_V1: hold L2 + L1 / R1 tab strip (pure)\n',
         '#include "OmniTabSwitcher.h" // OMNI_TAB_SWITCHER_V1: hold L2 + L1 / R1 tab strip (pure)\n'
         '#include "OmniTabThumbs.h" // OMNI_TAB_THUMBS_V1: tab snapshots: crop, downscale, store (pure)\n'),
        ('void activate(size_t index)\n'
         '{\n'
         '    ++omniMqInputGeneration; // OMNI_MQ_NATIVE_V1\n'
         '    if (index >= tabs.size()) return;\n',
         'static const void* omniTthSrc = nullptr; // OMNI_TAB_THUMBS_V1: the tab the page buffers / the last zero-copy frame were painted for\n'
         'static void omniTthCapture(size_t index); // OMNI_TAB_THUMBS_V1 (OmniTabThumbsShell.h): snapshot of the tab being left\n'
         'void activate(size_t index)\n'
         '{\n'
         '    ++omniMqInputGeneration; // OMNI_MQ_NATIVE_V1\n'
         '    if (index >= tabs.size()) return;\n'
         '    omniTthCapture(index); // OMNI_TAB_THUMBS_V1: before the page buffer is whitened and full screen is left\n'),
        ('    omniZc.lastFrame = frame; ++omniZc.frames;\n',
         '    omniZc.lastFrame = frame; ++omniZc.frames;\n'
         '    omniTthSrc = active(); // OMNI_TAB_THUMBS_V1: the published frame shows this tab\n'),
        ('    if (omniZcActive()) { omniPageDamage.add(0, renderPageHeight); return; }   // OMNI_GPUPAGES_ZEROCOPY_V1: no WKPagePaint\n',
         '    if (omniZcActive()) { omniPageDamage.add(0, renderPageHeight); return; }   // OMNI_GPUPAGES_ZEROCOPY_V1: no WKPagePaint\n'
         '    omniTthSrc = active(); // OMNI_TAB_THUMBS_V1: the page buffers show this tab\n'),
    ],
    'OmniFeatures3Decl.h': [
        ('static bool omniTgRowMark(const OmniFxPanel& p, const OmniFxRow& r, int x, int y, int h);   // omniFxDrawPanel: colours\n',
         'static bool omniTgRowMark(const OmniFxPanel& p, const OmniFxRow& r, int x, int y, int h);   // omniFxDrawPanel: colours\n'
         '// OMNI_TAB_THUMBS_V1 (OmniTabThumbsShell.h): tab snapshots\n'
         'static int omniTthRowMark(const OmniFxPanel& p, const OmniFxRow& r, int lx, int y, int h);   // omniFxDrawPanel: Tabs / Tab memory rows\n'
         'static void omniTthForget(const void* tab);                // omniFxTabClosing: drops its thumbnail\n'),
    ],
    'OmniFeaturesPanel.h': [
        ('            if (omniTgRowMark(p, r, g.x, ry, p.rowH)) lx = g.x + 66; // OMNI_TAB_GROUPS_V1: group colour\n',
         '            if (omniTgRowMark(p, r, g.x, ry, p.rowH)) lx = g.x + 66; // OMNI_TAB_GROUPS_V1: group colour\n'
         '            lx = omniTthRowMark(p, r, lx, ry, p.rowH); // OMNI_TAB_THUMBS_V1: the tab\'s snapshot before its title\n'),
    ],
    'OmniTabsPage.h': [
        ('    omniTmvForget(&tab); // OMNI_TAB_MEMORY_VIEW_V1: its "Keep loaded" mark\n',
         '    omniTmvForget(&tab); // OMNI_TAB_MEMORY_VIEW_V1: its "Keep loaded" mark\n'
         '    omniTthForget(&tab); // OMNI_TAB_THUMBS_V1: its snapshot\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniTabSwitcherShell.h" // OMNI_TAB_SWITCHER_V1 (after tab groups and pinned tabs: it reads both)\n',
         '#include "OmniTabThumbsShell.h" // OMNI_TAB_THUMBS_V1 (before the tab switcher: its tiles draw them)\n'
         '#include "OmniTabSwitcherShell.h" // OMNI_TAB_SWITCHER_V1 (after tab groups and pinned tabs: it reads both)\n'),
    ],
    'OmniTabSwitcherShell.h': [
        (TILE_OLD,
         '        if (!omniTthTile(*t, x + 8, y + 14, OTTH::kTileW, OTTH::kTileH, { c.r, c.g, c.b, 255 }, OTSW::letter(site, t->title))) { // OMNI_TAB_THUMBS_V1: the snapshot, else the letter\n'
         + TILE_OLD +
         '        }\n'),
    ],
}


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


def main():
    for f in (PURE, SHELL):
        if not f.exists():
            sys.exit('%s missing (it ships next to this script)' % f)
    for name in ('OmniTabThumbs.h', 'OmniTabThumbsShell.h'):   # never overwrite someone else's file
        h = root / name
        if h.exists() and MARK not in h.read_bytes().decode('utf-8', 'replace'):
            sys.exit('%s exists without %s' % (name, MARK))
    f3 = (root / 'OmniFeatures3.h').read_bytes().decode('utf-8')
    for need, tool in (('OMNI_TAB_SWITCHER_V1', 'apply_tab_switcher.py'), ('OMNI_TAB_GROUPS_V1', 'apply_tab_groups.py')):
        if need not in f3:
            sys.exit('OmniFeatures3.h: %s missing: %s first' % (need, tool))
    if 'OMNI_TAB_MEMORY_VIEW_V1' not in (root / 'OmniTabsPage.h').read_bytes().decode('utf-8'):
        sys.exit('OmniTabsPage.h: OMNI_TAB_MEMORY_VIEW_V1 missing: apply_tab_memory_view.py first')
    if 'OMNI_GPUPAGES_ZEROCOPY_V1' not in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8'):
        sys.exit('OmniBrowser.cpp: OMNI_GPUPAGES_ZEROCOPY_V1 missing: apply_zerocopy_shell.py first')
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniTabThumbs.h', PURE.read_bytes().decode('utf-8'), 'OmniTabSwitcher.h'),
            write_new('OmniTabThumbsShell.h', SHELL.read_bytes().decode('utf-8'), 'OmniTabSwitcherShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
