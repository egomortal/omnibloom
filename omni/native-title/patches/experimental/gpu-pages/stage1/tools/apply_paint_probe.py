#!/usr/bin/env python3
"""OMNI_PAINT_PROBE_V1 (2026-11-14 night run, diagnostics only): where do the 60-130 ms per full composited frame go
when scrolling with layers on (YouTube home scroll: 8 fps with layers, 15 fps without)? stage 1's own counters showed the
readback is only 3-7 ms; the rest is "paint" (willRender -> readback). This adds two stderr probes in the page process:

  SkiaPaintingEngine.cpp  "OMNI PAINT: GPU|CPU painting, N threads" once (which tile-painting path is live), then every
                          2 s "OMNI PAINT: tiles=N paintMs=T maxMs=M mpix=P" (Skia replay time on the worker threads).
  egl/BitmapTexture.cpp   every 2 s "OMNI UPLOAD: n=N ms=T maxMs=M MB=B" for BitmapTexture::updateContents(srcData...)
                          (CPU tile -> GL texture uploads; with Zink each is a staging copy).
No behaviour change. Anchored, once each, idempotent.
usage: apply_paint_probe.py <engine tree>   (edits webkit/Source/WebCore/platform/graphics/...)
"""
import sys
from pathlib import Path

MARK = 'OMNI_PAINT_PROBE_V1'
root = Path(sys.argv[1]) / 'webkit' / 'Source' / 'WebCore' / 'platform' / 'graphics'

HELPER = r'''
// OMNI_PAINT_PROBE_V1: tiny monotonic clock + a 2 s report gate, local to this file.
#include <atomic>
#include <cstdio>
#include <time.h>
#include <unistd.h>
static inline double omniProbeNowMs() { struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts); return ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6; }
'''


def patch(rel, edits):
    p = root / rel
    s = p.read_text(encoding='utf-8')
    if MARK in s:
        print('already', rel); return
    for old, new in edits:
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (rel, s.count(old), old[:70]))
        s = s.replace(old, new, 1)
    p.write_text(s, encoding='utf-8')
    print('patched', rel)


SKIA = [
    ('namespace WebCore {\n\nWTF_MAKE_TZONE_ALLOCATED_IMPL(SkiaPaintingEngine);\n',
     HELPER + r'''static std::atomic<long long> s_omniPaintUs { 0 }, s_omniPaintMaxUs { 0 }, s_omniPaintPix { 0 };
static std::atomic<int> s_omniPaintTiles { 0 };
static std::atomic<long long> s_omniPaintLastMs { 0 };
static void omniPaintAdd(double ms, long long pixels)
{
    long long us = static_cast<long long>(ms * 1000);
    s_omniPaintUs += us; s_omniPaintPix += pixels; s_omniPaintTiles++;
    long long prev = s_omniPaintMaxUs.load();
    while (us > prev && !s_omniPaintMaxUs.compare_exchange_weak(prev, us)) { }
    long long now = static_cast<long long>(omniProbeNowMs()), last = s_omniPaintLastMs.load();
    if (now - last >= 2000 && s_omniPaintLastMs.compare_exchange_strong(last, now)) {
        fprintf(stderr, "OMNI PAINT: tiles=%d paintMs=%.1f maxMs=%.1f mpix=%.2f pid=%d\n", s_omniPaintTiles.exchange(0),
            s_omniPaintUs.exchange(0) / 1000.0, s_omniPaintMaxUs.exchange(0) / 1000.0, s_omniPaintPix.exchange(0) / 1e6, getpid());
    }
}

namespace WebCore {

WTF_MAKE_TZONE_ALLOCATED_IMPL(SkiaPaintingEngine);
'''),
    ('''        if (auto numberOfGPUThreads = numberOfGPUPaintingThreads())
            lazyInitialize(m_paintingWorkerPool, WorkerPool::create("SkiaGPUWorker"_s, numberOfGPUThreads));

        return;''',
     '''        if (auto numberOfGPUThreads = numberOfGPUPaintingThreads())
            lazyInitialize(m_paintingWorkerPool, WorkerPool::create("SkiaGPUWorker"_s, numberOfGPUThreads));
        fprintf(stderr, "OMNI PAINT: GPU painting, %u threads (OMNI_PAINT_PROBE_V1) pid=%d\\n", numberOfGPUPaintingThreads(), getpid());

        return;'''),
    ('''    if (auto numberOfCPUThreads = numberOfCPUPaintingThreads())
        lazyInitialize(m_paintingWorkerPool, WorkerPool::create("SkiaCPUWorker"_s, numberOfCPUThreads));
}''',
     '''    if (auto numberOfCPUThreads = numberOfCPUPaintingThreads())
        lazyInitialize(m_paintingWorkerPool, WorkerPool::create("SkiaCPUWorker"_s, numberOfCPUThreads));
    fprintf(stderr, "OMNI PAINT: CPU painting, %u threads (OMNI_PAINT_PROBE_V1) pid=%d\\n", numberOfCPUPaintingThreads(), getpid());
}'''),
    ('''    m_paintingWorkerPool->postTask([platformLayer = WTF::move(platformLayer), buffer = Ref { buffer }, tileRect, dirtyRect, recording = WTF::move(recording), threadSafeGrContext = m_threadSafeGrContext]() mutable {
        if (auto* canvas = buffer->canvas()) {''',
     '''    m_paintingWorkerPool->postTask([platformLayer = WTF::move(platformLayer), buffer = Ref { buffer }, tileRect, dirtyRect, recording = WTF::move(recording), threadSafeGrContext = m_threadSafeGrContext]() mutable {
        const double omniT0 = omniProbeNowMs();   // OMNI_PAINT_PROBE_V1
        if (auto* canvas = buffer->canvas()) {'''),
    ('''        buffer->completePainting();
        platformLayer->didPaintTile();
    });''',
     '''        buffer->completePainting();
        omniPaintAdd(omniProbeNowMs() - omniT0, static_cast<long long>(dirtyRect.width()) * dirtyRect.height());   // OMNI_PAINT_PROBE_V1
        platformLayer->didPaintTile();
    });'''),
]

UPLOAD = [
    # includes at file scope (BitmapTexture::updateContents is inside namespace WebCore)
    ('#include "config.h"\n', '#include "config.h"\n#include <atomic>\n#include <cstdio>\n#include <time.h>\n#include <unistd.h>\n'),
    ('void BitmapTexture::updateContents(const void* srcData, const IntRect& targetRect, const IntPoint& sourceOffset, int bytesPerLine, PixelFormat pixelFormat)\n{\n',
     r'''// OMNI_PAINT_PROBE_V1
static inline double omniProbeNowMs() { struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts); return ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6; }
static std::atomic<long long> s_omniUpUs { 0 }, s_omniUpMaxUs { 0 }, s_omniUpBytes { 0 };
static std::atomic<int> s_omniUpN { 0 };
static std::atomic<long long> s_omniUpLastMs { 0 };
struct OmniUploadTimer {
    double t0 = omniProbeNowMs(); long long bytes;
    explicit OmniUploadTimer(long long b) : bytes(b) { }
    ~OmniUploadTimer()
    {
        long long us = static_cast<long long>((omniProbeNowMs() - t0) * 1000);
        s_omniUpUs += us; s_omniUpBytes += bytes; s_omniUpN++;
        long long prev = s_omniUpMaxUs.load();
        while (us > prev && !s_omniUpMaxUs.compare_exchange_weak(prev, us)) { }
        long long now = static_cast<long long>(omniProbeNowMs()), last = s_omniUpLastMs.load();
        if (now - last >= 2000 && s_omniUpLastMs.compare_exchange_strong(last, now))
            fprintf(stderr, "OMNI UPLOAD: n=%d ms=%.1f maxMs=%.1f MB=%.1f pid=%d\n", s_omniUpN.exchange(0), s_omniUpUs.exchange(0) / 1000.0,
                s_omniUpMaxUs.exchange(0) / 1000.0, s_omniUpBytes.exchange(0) / 1e6, getpid());
    }
};
void BitmapTexture::updateContents(const void* srcData, const IntRect& targetRect, const IntPoint& sourceOffset, int bytesPerLine, PixelFormat pixelFormat)
{
    OmniUploadTimer omniUploadTimer(static_cast<long long>(targetRect.width()) * targetRect.height() * 4);   // OMNI_PAINT_PROBE_V1
'''),
]

patch('skia/SkiaPaintingEngine.cpp', SKIA)
patch('egl/BitmapTexture.cpp', UPLOAD)
