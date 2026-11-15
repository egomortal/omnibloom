#!/usr/bin/env python3
"""OMNI_GPU_PAGES_ASYNC_V2 (2026-11-14 night run): make stage 1b async scrolling reachable.

Finding: V1 gated DrawingAreaCoordinatedGraphics as `threadedScrollingEnabled && asyncScrollingAllowed()`, and WebPage
also reads threadedScrollingEnabled. But the PlayStation UI process forces that preference OFF
(UIProcess/playstation/WebPreferencesPlayStation.cpp: setThreadedScrollingEnabled(false)), so async scrolling never
turned on with any flag. The console log never printed "OMNI GPUPAGES async scrolling", and the 2026-11-14 Lsc2bhy run
was identical to Lsc2hy: 8.1 fps, ~850 tiles repainted per 2 s.

V2 (child only, the title is unchanged): our runtime gate alone decides.
  DrawingAreaCoordinatedGraphics::updatePreferences  m_supportsAsyncScrolling = OmniGpuPagesS1b::asyncScrollingAllowed()
  WebPage constructor                                m_useAsyncScrolling = pref || drawingArea->supportsAsyncScrolling()
asyncScrollingAllowed() still needs stage 1 on + /data/omni/gpu-pages-async.flag + no gpu-pages-async-off.flag, so the
default (no flag) is unchanged. Apply AFTER apply_gpupages_async.py. Idempotent.
usage: apply_gpupages_async_v2.py TREE"""
import sys
from pathlib import Path

MARK = 'OMNI_GPU_PAGES_ASYNC_V2'
tree = Path(sys.argv[1]) / 'webkit/Source/WebKit/WebProcess/WebPage'

EDITS = {
    'CoordinatedGraphics/DrawingAreaCoordinatedGraphics.cpp': [(
        '    m_supportsAsyncScrolling = store.getBoolValueForKey(WebPreferencesKey::threadedScrollingEnabledKey())\n'
        '        && OmniGpuPagesS1b::asyncScrollingAllowed();   // OMNI_GPU_PAGES_ASYNC_V1\n',
        '    // OMNI_GPU_PAGES_ASYNC_V2: the PlayStation UI process forces threadedScrollingEnabled off, so our gate alone decides\n'
        '    m_supportsAsyncScrolling = OmniGpuPagesS1b::asyncScrollingAllowed();\n')],
    'WebPage.cpp': [(
        '    m_useAsyncScrolling = parameters.store.getBoolValueForKey(WebPreferencesKey::threadedScrollingEnabledKey());\n'
        '    if (!drawingArea->supportsAsyncScrolling())\n',
        '    m_useAsyncScrolling = parameters.store.getBoolValueForKey(WebPreferencesKey::threadedScrollingEnabledKey())\n'
        '        || drawingArea->supportsAsyncScrolling();   // OMNI_GPU_PAGES_ASYNC_V2 (flag-gated in the drawing area)\n'
        '    if (!drawingArea->supportsAsyncScrolling())\n')],
}

for rel, edits in EDITS.items():
    p = tree / rel
    raw = p.read_bytes().decode('utf-8'); crlf = '\r\n' in raw; t = raw.replace('\r\n', '\n')
    if MARK in t:
        print('already', rel); continue
    for old, new in edits:
        if t.count(old) != 1:
            sys.exit('%s: anchor found %d times' % (rel, t.count(old)))
        t = t.replace(old, new, 1)
    p.write_bytes((t.replace('\n', '\r\n') if crlf else t).encode('utf-8'))
    print('patched', rel)
