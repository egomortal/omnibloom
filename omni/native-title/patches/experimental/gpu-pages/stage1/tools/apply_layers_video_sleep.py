#!/usr/bin/env python3
"""OMNI_LAYERS_VIDEO_SLEEP_V1 (2026-11-20, owner: "no i need it gone forever" - cut the page-table cost at its source).

Measured: page layers (GPU page compositing, stage 1) cost the web process ~529 MiB at 4K = ~265 kernel page tables in
the console's shared pool (4K YouTube peak 6,880 ON vs 6,529 OFF; hangs from ~6,771). While a large hardware video
plays, the video is on its own plane and the page behind it barely changes, so the layers buy nothing then.

What it does (web process, DrawingAreaCoordinatedGraphics.cpp, checked on every frame acknowledgement in both modes):
  * omniHwBigVideoActive() (OMNI_GPUPAGES_VIDEO_TRIM_V1: a 1440p+ hardware stream is configured in this process) turns
    true -> forceCompositingMode + acceleratedCompositing off for that page and m_alwaysUseCompositing false: WebCore
    drops its compositing layers on the next update and the drawing area leaves composited mode (layer tree host and
    its tiles freed), the page paints in backing-store mode like layers-off.
  * it turns false -> the settings go back on, m_alwaysUseCompositing true, a rendering update is scheduled: the page
    re-enters composited mode exactly as at page start.
Off switch: /data/omni/layers-video-sleep-off.flag. Logs "OMNI LAYERS SLEEP pid=..: ...".
Needs OMNI_GPU_PAGES_STAGE1_V1 hooks (omniGpuPagesProcessReady) and OMNI_GPUPAGES_VIDEO_TRIM_V1 (omniHwBigVideoActive).
usage: apply_layers_video_sleep.py <CoordinatedGraphics dir holding DrawingAreaCoordinatedGraphics.cpp>"""
import sys
from pathlib import Path

MARK = 'OMNI_LAYERS_VIDEO_SLEEP_V1'
p = Path(sys.argv[1]) / 'DrawingAreaCoordinatedGraphics.cpp'
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK in s:
    print('already', p.name); sys.exit(0)
for need in ('omniGpuPagesProcessReady()',):
    if need not in s:
        sys.exit('needs ' + need)

A = ('void DrawingAreaCoordinatedGraphics::displayDidRefresh(MonotonicTime omniShellAckedAt) // OMNI_ACK_V1\n{\n')
if s.count(A) != 1:
    sys.exit('anchor found %d times' % s.count(A))
BLOCK = ('    {   // ' + MARK + ': page layers sleep while a large hardware video plays (tools/apply_layers_video_sleep.py)\n'
         '        static const bool lvsOn = access("/data/omni/layers-video-sleep-off.flag", F_OK) != 0;\n'
         '        static std::set<const void*>* lvsAsleep = new std::set<const void*>();\n'
         '        if (lvsOn && omniGpuPagesProcessReady()) {\n'
         '            const bool big = omniHwBigVideoActive() != 0;\n'
         '            const bool sleeping = lvsAsleep->count(this) != 0;\n'
         '            if (big != sleeping) {\n'
         '                Settings& lvsSettings = m_webPage->corePage()->settings();\n'
         '                if (big) {\n'
         '                    lvsAsleep->insert(this);\n'
         '                    m_alwaysUseCompositing = false;\n'
         '                    lvsSettings.setForceCompositingMode(false);\n'
         '                    lvsSettings.setAcceleratedCompositingEnabled(false);\n'
         '                } else {\n'
         '                    lvsAsleep->erase(this);\n'
         '                    lvsSettings.setAcceleratedCompositingEnabled(true);\n'
         '                    lvsSettings.setForceCompositingMode(true);\n'
         '                    lvsSettings.setAcceleratedCompositingForFixedPositionEnabled(true);\n'
         '                    m_alwaysUseCompositing = true;\n'
         '                    triggerRenderingUpdate();\n'
         '                }\n'
         '                fprintf(stderr, "OMNI LAYERS SLEEP pid=%d: %s (large hardware video %s)\\n", getpid(),\n'
         '                        big ? "layers off" : "layers back on", big ? "playing" : "gone");\n'
         '                fflush(stderr);\n'
         '            }\n'
         '        }\n'
         '    }\n')
s = s.replace(A, A + BLOCK, 1)
# declarations/includes before the first "namespace WebKit {"
NS = 'namespace WebKit {\n'
if NS not in s:
    sys.exit('no namespace WebKit')
decl = ('#include <set>  // ' + MARK + '\n#include <unistd.h>  // ' + MARK + '\n#include <cstdio>  // ' + MARK + '\n'
        'extern "C" int omniHwBigVideoActive(void);  // ' + MARK + ' (OmniHwClient.cpp, OMNI_GPUPAGES_VIDEO_TRIM_V1)\n')
i = s.index(NS)
s = s[:i] + decl + s[i:]
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied', p.name)
