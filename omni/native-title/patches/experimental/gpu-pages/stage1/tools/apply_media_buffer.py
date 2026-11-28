#!/usr/bin/env python3
"""OMNI_MEDIA_BUFFER_V1 (2026-11-26, owner: "do 20 mins with the cap"): one video buffer budget for the title's players,
plus page-table peak logging.

Before: the title's (in-app) MSE player held 32 MiB per SourceBuffer (= ~10 s of 4K HDR; the separate engine's
OMNI_MSE_QUOTA_V1 64 MiB fix never reached the title), the progressive player a 16 MiB cache reading 6 MiB ahead, native
HLS 30 s / 48 MiB ahead. Small buffers = stalls on every network dip (and the November "freeze at ~11 s").

Now (title only; the separate engine child is unchanged):
  budget  /data/omni/media-buffer-mb.txt (64-4096, default 1024 MiB), logged once "OMNI MEDIABUF: budget ...".
  MSE     (YouTube, movy, hls.js sites): a video SourceBuffer may hold budget / live video SourceBuffers (at least 32 MiB),
          audio-only ones 64 MiB. The site's player decides how far ahead it asks; this cap no longer cuts it short.
          Every 10 s while appending: "OMNI MEDIABUF: video N s ahead, M MiB held, cap C MiB" (to measure YouTube).
  files   progressive cache = budget / 2, read-ahead = 7/8 of it (the whole file when it fits).
  HLS     native session: 20 minutes ahead, at most budget / 2.
  pages   OMNI_PT_GENTLE_V1 gets a first step: over the line, the video budget halves (up to 3 times, one step / 6 s)
          before any tab is touched; it grows back one step a minute once the count is 300 under the line.
  peak    the watchdog's 1 s sampler logs "OMNI PT PEAK: N page tables" at each new high (10+ above the last).
Kill switch: /data/omni/media-buffer-off.flag (MSE 64 MiB, files/HLS as before; the peak log stays).
usage: apply_media_buffer.py <title tree root holding engine/>"""
import sys
from pathlib import Path

MARK = 'OMNI_MEDIA_BUFFER_V1'
root = Path(sys.argv[1]) / 'engine'

HEADER = r'''// OMNI_MEDIA_BUFFER_V1: one video buffer budget for Omni's players (see tools/apply_media_buffer.py).
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <algorithm>
#include <atomic>
#include <cstddef>
#include <cstdio>
#include <unistd.h>

namespace OmniMediaBuffer {
inline constexpr double aheadSeconds = 1200;   // 20 minutes ahead when the budget allows
inline bool off()
{
    static const bool v = access("/data/omni/media-buffer-off.flag", F_OK) == 0;
    return v;
}
inline size_t budgetBytes()
{
    static const size_t v = [] {
        unsigned mb = 1024;
        if (FILE* f = fopen("/data/omni/media-buffer-mb.txt", "r")) { unsigned x = 0; if (fscanf(f, "%u", &x) == 1 && x >= 64 && x <= 4096) mb = x; fclose(f); }
        fprintf(stderr, "OMNI MEDIABUF: budget %u MiB, up to 20 min ahead (OMNI_MEDIA_BUFFER_V1; media-buffer-mb.txt, off: media-buffer-off.flag%s)\n", mb, off() ? " = ON, old limits" : "");
        fflush(stderr);
        return size_t(mb) << 20;
    }();
    return v;
}
inline std::atomic<int>& shrink() { static std::atomic<int> v { 0 }; return v; }      // page-table pressure: each step halves
inline std::atomic<int>& liveVideo() { static std::atomic<int> v { 0 }; return v; }   // video SourceBuffers holding a share
inline size_t budgetNow() { return budgetBytes() >> std::min(shrink().load(std::memory_order_relaxed), 3); }
inline size_t videoShare() { return std::max<size_t>(size_t(32) << 20, budgetNow() / size_t(std::max(1, liveVideo().load(std::memory_order_relaxed)))); }
inline constexpr size_t audioBytes = size_t(64) << 20;
} // namespace OmniMediaBuffer
'''


def load(rel):
    p = root / rel
    raw = p.read_bytes().decode('utf-8')
    return p, ('\r\n' if '\r\n' in raw else '\n'), raw.replace('\r\n', '\n')


def save(p, nl, s):
    p.write_bytes(s.replace('\n', nl).encode('utf-8'))


def sub(s, old, new, what):
    if s.count(old) != 1:
        sys.exit('%s: anchor found %d times: %r' % (what, s.count(old), old[:90]))
    return s.replace(old, new, 1)


hp = root / 'media' / 'OmniMediaBuffer.h'
hp.write_bytes(HEADER.encode('utf-8'))

# ---- MSE (engine/entry/OmniMSESource.cpp) ----
p, nl, s = load('entry/OmniMSESource.cpp')
if MARK not in s:
    s = sub(s, '#include "OmniMediaSample.h"\n', '#include "OmniMediaSample.h"\n#include "../media/OmniMediaBuffer.h" // ' + MARK + '\n', 'MSE include')
    s = sub(s, '    size_t platformMaximumBufferSize() const final { return 32 * 1024 * 1024; }\n',
            '    // ' + MARK + ': was a fixed 32 MiB (~10 s of 4K HDR). Video: a share of the media budget; audio: 64 MiB.\n'
            '    mutable bool m_omniVideoCounted = false; mutable size_t m_omniCapSet = 0; double m_omniLogAt = 0;\n'
            '    bool omniHasVideo() const { for (auto& [id, track] : m_tracks) if (OmniMedia::isVideoCodec(track->info.codec)) return true; return false; }\n'
            '    void omniUncount() { if (m_omniVideoCounted) { m_omniVideoCounted = false; OmniMediaBuffer::liveVideo().fetch_sub(1); } }\n'
            '    size_t platformMaximumBufferSize() const final {\n'
            '        if (OmniMediaBuffer::off()) return size_t(64) << 20;\n'
            '        if (!omniHasVideo()) return OmniMediaBuffer::audioBytes;\n'
            '        if (!m_omniVideoCounted) { m_omniVideoCounted = true; OmniMediaBuffer::liveVideo().fetch_add(1); }\n'
            '        m_omniCapSet = OmniMediaBuffer::videoShare();\n'
            '        fprintf(stderr, "OMNI MEDIABUF: video SourceBuffer cap %zu MiB (budget %zu MiB, %d video buffers)\\n", m_omniCapSet >> 20, OmniMediaBuffer::budgetNow() >> 20, OmniMediaBuffer::liveVideo().load());\n'
            '        fflush(stderr);\n'
            '        return m_omniCapSet;\n'
            '    }\n'
            '    void omniBufferCheck() {   // each append: a new share (page-table step, buffers came or went) + a 10 s log of how far ahead\n'
            '        if (OmniMediaBuffer::off() || !m_omniVideoCounted) return;\n'
            '        const size_t want = OmniMediaBuffer::videoShare();\n'
            '        if (want != m_omniCapSet) {\n'
            '            fprintf(stderr, "OMNI MEDIABUF: video SourceBuffer cap %zu -> %zu MiB\\n", m_omniCapSet >> 20, want >> 20); fflush(stderr);\n'
            '            m_omniCapSet = want; (void)setMaximumBufferSize(want);\n'
            '        }\n'
            '        const double now = MonotonicTime::now().secondsSinceEpoch().seconds();\n'
            '        if (now - m_omniLogAt < 10) return;\n'
            '        m_omniLogAt = now;\n'
            '        const double cur = currentTime().toDouble();\n'
            '        double ahead = 0;\n'
            '        for (auto& r : trackBuffersRanges())\n'
            '            for (unsigned i = 0; i < r.length(); ++i)\n'
            '                if (r.start(i).toDouble() <= cur + 0.5 && r.end(i).toDouble() > cur) ahead = std::max(ahead, r.end(i).toDouble() - cur);\n'
            '        fprintf(stderr, "OMNI MEDIABUF: video %.0f s ahead, %llu MiB held, cap %zu MiB\\n", ahead, (unsigned long long)(contentSize() >> 20), m_omniCapSet >> 20);\n'
            '        fflush(stderr);\n'
            '    }\n', 'MSE cap')
    s = sub(s, '    Buffer(OmniMSESource& source, uint32_t id, bool webm) : SourceBufferPrivate(source), m_namespace(id), m_webm(webm) { } // OMNI_WEBM_V1\n',
            '    Buffer(OmniMSESource& source, uint32_t id, bool webm) : SourceBufferPrivate(source), m_namespace(id), m_webm(webm) { } // OMNI_WEBM_V1\n'
            '    ~Buffer() { omniUncount(); } // ' + MARK + '\n', 'MSE dtor')
    s = sub(s, '        if (m_webm) return appendWebM(bytes.get()); // OMNI_WEBM_V1\n',
            '        omniBufferCheck(); // ' + MARK + '\n        if (m_webm) return appendWebM(bytes.get()); // OMNI_WEBM_V1\n', 'MSE append')
    s = sub(s, '        m_detached = true;\n', '        m_detached = true;\n        omniUncount(); // ' + MARK + '\n', 'MSE removed')
    save(p, nl, s)
    print('OmniMSESource.cpp: applied')

# ---- progressive files (engine/media/OmniProgressive.h) ----
p, nl, s = load('media/OmniProgressive.h')
if MARK not in s:
    i = s.index('#include')
    s = s[:i] + '#include "OmniMediaBuffer.h" // ' + MARK + '\n' + s[i:]
    s = sub(s, '    size_t cacheBytes = 16 * 1024 * 1024;\n',
            '    size_t cacheBytes = OmniMediaBuffer::off() ? size_t(16) << 20 : OmniMediaBuffer::budgetNow() / 2;   // ' + MARK + ' (was 16 MiB)\n', 'progressive cache')
    s = sub(s, '    size_t readAheadBytes = 6 * 1024 * 1024;\n',
            '    size_t readAheadBytes = OmniMediaBuffer::off() ? size_t(6) << 20 : OmniMediaBuffer::budgetNow() / 16 * 7;   // ' + MARK + ' (was 6 MiB)\n', 'progressive ahead')
    save(p, nl, s)
    print('OmniProgressive.h: applied')

# ---- native HLS (engine/media/OmniHlsSession.h) ----
p, nl, s = load('media/OmniHlsSession.h')
if MARK not in s:
    i = s.index('#include')
    s = s[:i] + '#include "OmniMediaBuffer.h" // ' + MARK + '\n' + s[i:]
    s = sub(s, '    double forwardSeconds = 30;               // media fetched ahead of the playhead\n    size_t forwardBytes = 48 * 1024 * 1024;   // and at most this much queued\n',
            '    double forwardSeconds = OmniMediaBuffer::off() ? 30 : OmniMediaBuffer::aheadSeconds;   // media fetched ahead (' + MARK + ': was 30 s)\n'
            '    size_t forwardBytes = OmniMediaBuffer::off() ? size_t(48) << 20 : OmniMediaBuffer::budgetNow() / 2;   // and at most this much queued (was 48 MiB)\n', 'HLS options')
    save(p, nl, s)
    print('OmniHlsSession.h: applied')

# ---- page-table guard + peak log (engine/entry/OmniBrowser.cpp, after OMNI_PT_GENTLE_V1) ----
p, nl, s = load('entry/OmniBrowser.cpp')
if MARK not in s:
    if 'OMNI_PT_GENTLE_V1' not in s:
        sys.exit('apply OMNI_PT_GENTLE_V1 first')
    s = sub(s, '// OMNI_PT_WATCHDOG_V1: kernel page-table watchdog',
            '#include "../media/OmniMediaBuffer.h" // ' + MARK + '\n// OMNI_PT_WATCHDOG_V1: kernel page-table watchdog', 'browser include')
    s = sub(s, '        std::thread([] { for (;;) { omniPtWdUsed.store(omniPtWdAsk(), std::memory_order_relaxed); sleep(1); } }).detach();\n',
            '        std::thread([] {   // ' + MARK + ': + the peak, logged at each new high (10+ above the last)\n'
            '            int logged = -100;\n'
            '            for (;;) {\n'
            '                const int v = omniPtWdAsk();\n'
            '                omniPtWdUsed.store(v, std::memory_order_relaxed);\n'
            '                if (v >= logged + 10) { logged = v; fprintf(stderr, "OMNI PT PEAK: %d page tables\\n", v); fflush(stderr); }\n'
            '                sleep(1);\n'
            '            }\n'
            '        }).detach();\n', 'peak sampler')
    s = sub(s, '    if (used >= 0 && used < line - 150) gSteps = 0;\n',
            '    if (used >= 0 && used < line - 150) gSteps = 0;\n'
            '    {   // ' + MARK + ': the video budget grows back one step a minute once well under the line\n'
            '        static Uint32 gGrow = 0;\n'
            '        if (used >= 0 && used < line - 300 && OmniMediaBuffer::shrink().load() > 0 && gNow - gGrow >= 60000) {\n'
            '            gGrow = gNow; const int lv = --OmniMediaBuffer::shrink();\n'
            '            fprintf(stderr, "OMNI PT GENTLE: %d page tables: video buffer budget back to step %d (%zu MiB)\\n", used, lv, OmniMediaBuffer::budgetNow() >> 20); fflush(stderr);\n'
            '        }\n'
            '        if (used >= line) gGrow = gNow;\n'
            '    }\n', 'grow back')
    s = sub(s, '        Tab* shown = active();\n        const int apid',
            '        if (!OmniMediaBuffer::off() && OmniMediaBuffer::liveVideo().load() > 0 && OmniMediaBuffer::shrink().load() < 3) {   // ' + MARK + ': video buffers first\n'
            '            gLast = gNow; const int lv = ++OmniMediaBuffer::shrink();\n'
            '            fprintf(stderr, "OMNI PT GENTLE: %d page tables >= line %d: video buffer budget halved (step %d, %zu MiB)\\n", used, line, lv, OmniMediaBuffer::budgetNow() >> 20);\n'
            '            fflush(stderr);\n'
            '            return;\n'
            '        }\n'
            '        Tab* shown = active();\n        const int apid', 'shrink step')
    save(p, nl, s)
    print('OmniBrowser.cpp: applied')
print('applied', MARK)
