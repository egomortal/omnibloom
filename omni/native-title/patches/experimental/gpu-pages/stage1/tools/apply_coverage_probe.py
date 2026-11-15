#!/usr/bin/env python3
"""OMNI_COVERAGE_PROBE_V1 (2026-11-14 night run, diagnostics only): does async scrolling checkerboard?

Async scrolling took layers-on YouTube home scroll from 8 to 40 fps, but present fps counts frames, not finished
content: the compositor can scroll past the painted tiles, showing blank edges (reviewer 13:3xZ). This measures that in
the compositor itself (CoordinatedBackingStore::paintToTextureMapper, the WebProcess's threaded compositor in stage 1):
for each BIG layer (on-screen area >= 50% of the clip), the fraction of its on-screen area NOT covered by a tile that has
content (canBePainted). Every 2 s:
  OMNI COVERAGE: layers=N gap1=G gap10=H meanMissPct=M maxMissPct=X pid=P
(gap1 / gap10 = layer draws missing more than 1% / 10% of their visible area). No behaviour change. Anchored, idempotent.
Limits: ignores ancestor clips other than the scissor/clip box, and overlap by other layers; a big layer with zero tiles
is skipped (the early return).
usage: apply_coverage_probe.py <engine tree>
"""
import sys
from pathlib import Path

MARK = 'OMNI_COVERAGE_PROBE_V1'
p = Path(sys.argv[1]) / 'webkit/Source/WebCore/platform/graphics/texmap/coordinated/CoordinatedBackingStore.cpp'

EDITS = [
    ('#include <wtf/SystemTracing.h>\n',
     r'''#include <wtf/SystemTracing.h>
// OMNI_COVERAGE_PROBE_V1: unpainted share of big layers on screen, reported every 2 s (compositor thread)
#include <algorithm>
#include <cstdio>
#include <time.h>
#include <unistd.h>
static long long s_omniCovLayers = 0, s_omniCovGap1 = 0, s_omniCovGap10 = 0;
static double s_omniCovSum = 0, s_omniCovMax = 0, s_omniCovLastMs = 0;
static void omniCoverageAdd(double missing)
{
    s_omniCovLayers++; s_omniCovSum += missing; s_omniCovMax = std::max(s_omniCovMax, missing);
    if (missing > 0.01) s_omniCovGap1++;
    if (missing > 0.10) s_omniCovGap10++;
    struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts);
    double now = ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6;
    if (now - s_omniCovLastMs >= 2000) {
        fprintf(stderr, "OMNI COVERAGE: layers=%lld gap1=%lld gap10=%lld meanMissPct=%.2f maxMissPct=%.1f pid=%d\n", s_omniCovLayers,
            s_omniCovGap1, s_omniCovGap10, s_omniCovLayers ? 100.0 * s_omniCovSum / s_omniCovLayers : 0.0, 100.0 * s_omniCovMax, getpid());
        s_omniCovLayers = s_omniCovGap1 = s_omniCovGap10 = 0; s_omniCovSum = s_omniCovMax = 0; s_omniCovLastMs = now;
    }
}
'''),
    ('    if (m_tiles.isEmpty())\n        return;\n\n    ASSERT(!m_size.isZero());\n    FloatRect layerRect = { { }, m_size };\n'
     '    TransformationMatrix adjustedTransform = transform * TransformationMatrix::rectToRect(layerRect, targetRect);\n',
     r'''    if (m_tiles.isEmpty())
        return;

    ASSERT(!m_size.isZero());
    FloatRect layerRect = { { }, m_size };
    TransformationMatrix adjustedTransform = transform * TransformationMatrix::rectToRect(layerRect, targetRect);

    {   // OMNI_COVERAGE_PROBE_V1
        const FloatRect clip = textureMapper.clipBounds();
        const FloatRect onScreen = intersection(adjustedTransform.mapRect(layerRect), clip);
        const double area = double(onScreen.width()) * onScreen.height(), clipArea = double(clip.width()) * clip.height();
        if (clipArea > 0 && area >= 0.5 * clipArea) {
            double covered = 0;
            for (const auto& tile : m_tiles.values()) {
                if (!tile.canBePainted())
                    continue;
                const FloatRect t = intersection(adjustedTransform.mapRect(FloatRect(tile.rect())), onScreen);
                covered += double(t.width()) * t.height();
            }
            omniCoverageAdd(std::max(0.0, 1.0 - covered / area));
        }
    }
'''),
]

s = p.read_text(encoding='utf-8')
if MARK in s:
    print('already CoordinatedBackingStore.cpp'); sys.exit(0)
for old, new in EDITS:
    if s.count(old) != 1:
        sys.exit('CoordinatedBackingStore.cpp: anchor found %d times: %r' % (s.count(old), old[:60]))
    s = s.replace(old, new, 1)
p.write_text(s, encoding='utf-8')
print('patched CoordinatedBackingStore.cpp')
