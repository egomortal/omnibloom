#!/usr/bin/env python3
"""omni-gpu-pages stage 1b (OMNI_GPU_PAGES_ASYNC_V1): gate DrawingAreaCoordinatedGraphics's async-scrolling answer on
our runtime flags (ogp-s1b-async.inc). Apply AFTER apply_gpupages_child.py. Inert in a tree without
ENABLE_ASYNC_SCROLLING (the value it gates is then never used for a scrolling thread). Idempotent.
usage: apply_gpupages_async.py TREE"""
import shutil, sys
from pathlib import Path
tree = Path(sys.argv[1]); here = Path(__file__).resolve().parent.parent / 'src'
CG = tree / 'webkit/Source/WebKit/WebProcess/WebPage/CoordinatedGraphics'
p = CG / 'DrawingAreaCoordinatedGraphics.cpp'
raw = p.read_bytes().decode('utf-8'); crlf = '\r\n' in raw; t = raw.replace('\r\n', '\n')
MARK = 'OMNI_GPU_PAGES_ASYNC_V1'
already = MARK in t
inc = '#include "ogp-s1-drawingarea.inc"\n'
if already: print('gate already applied')
if not already:
    if t.count(inc) != 1: sys.exit('stage-1 include not found: apply apply_gpupages_child.py first')
    t = t.replace(inc, inc + f'#include "ogp-s1b-async.inc"   // {MARK}\n', 1)
    a = '    m_supportsAsyncScrolling = store.getBoolValueForKey(WebPreferencesKey::threadedScrollingEnabledKey());\n'
    if t.count(a) != 1: sys.exit(f'anchor not found exactly once ({t.count(a)})')
    t = t.replace(a, a.rstrip('\n')[:-1] + f'\n        && OmniGpuPagesS1b::asyncScrollingAllowed();   // {MARK}\n', 1)
    p.write_bytes((t.replace('\n', '\r\n') if crlf else t).encode('utf-8'))
    shutil.copy(here / 'ogp-s1b-async.inc', CG / 'ogp-s1b-async.inc')
if not already: print(f'patched {p.name}: async-scrolling gate + include')
# The PlayStation port never built async scrolling, so its WebKit source list lacks the WebProcess scrolling coordinator
# that WebPage creates when ASYNC_SCROLLING is on (GTK/WPE list it in SourcesGTK/SourcesWPE.txt). WebCore's side is
# already listed by platform/CoordinatedGraphics.cmake. Guarded, so a tree without ENABLE_ASYNC_SCROLLING is unchanged.
cm = tree / 'webkit/Source/WebKit/PlatformPlayStation.cmake'
c = cm.read_text()
if MARK not in c:
    c += (f'\n# {MARK}: the WebProcess side of coordinated async scrolling (as SourcesGTK/SourcesWPE.txt list it)\n'
          'if (ENABLE_ASYNC_SCROLLING)\n    list(APPEND WebKit_SOURCES WebProcess/WebPage/CoordinatedGraphics/ScrollingCoordinatorCoordinated.cpp)\nendif ()\n')
    cm.write_text(c); print('patched PlatformPlayStation.cmake: ScrollingCoordinatorCoordinated.cpp when ENABLE_ASYNC_SCROLLING')
