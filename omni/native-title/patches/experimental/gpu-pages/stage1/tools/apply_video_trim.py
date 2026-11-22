#!/usr/bin/env python3
"""OMNI_GPUPAGES_VIDEO_TRIM_V1 (2026-11-19, owner: "Yes, build it" - the video-time trim for the 4K + layers hang).

Measured 2026-11-19 (g9f, 4K HDR YouTube): page tables peak 6880 with layers ON vs 6529 OFF; the web process holds
2157 MiB ON vs 1628 MiB OFF (+529 MiB). Part of that is the async readback ring (OMNI_GPUPAGES_ASYNCREAD_V1): 3 pixel-pack
buffers of 3840x2160x4 = 33 MB each. While a large video plays the page is redrawn about every 500 ms (the video fix
paints the page on a timer while a video uses the plane), so the pipelined ring buys nothing then.

What it does (web process only):
  * engine/media/OmniHwClient.cpp: omniHwBigVideoActive() = a hardware video stream of 1440p or more is configured in
    this process (set in Client::configure, cleared in Client::disconnect; the destructor disconnects).
  * ogp-s1-surface.inc didRenderImpl: while that is true, pending ring frames are handed on, the ring is freed
    (asyncFreeGL, context current) and the frame takes the synchronous readback path that runs when asyncread is off.
    When the video ends the ring is allocated again by the next async frame, as at page start.
Off switch: /data/omni/gpu-pages-video-trim-off.flag. Logs "OMNI GPUPAGES video-trim pid=..: ring released / ring back".
usage: apply_video_trim.py <CoordinatedGraphics dir holding ogp-s1-surface.inc> <engine dir holding media/>"""
import sys
from pathlib import Path

MARK = 'OMNI_GPUPAGES_VIDEO_TRIM_V1'


def patch(p, edits, prepend=None):
    raw = p.read_bytes().decode('utf-8')
    nl = '\r\n' if '\r\n' in raw else '\n'
    s = raw.replace('\r\n', '\n')
    if MARK in s:
        return 'already ' + p.name
    for old, _ in edits:
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (p.name, s.count(old), old.strip()[:90]))
    for old, new in edits:
        s = s.replace(old, new, 1)
    if prepend:
        first = s.index('#include ')
        s = s[:first] + prepend + s[first:]
    p.write_bytes(s.replace('\n', nl).encode('utf-8'))
    return 'applied ' + p.name


surface = Path(sys.argv[1]) / 'ogp-s1-surface.inc'
client = Path(sys.argv[2]) / 'media' / 'OmniHwClient.cpp'

CLIENT = [
    ('Client::~Client()\n{\n',
     '// ' + MARK + ': which clients in this process hold a stream of 1440p or more (read by the layers compositor)\n'
     'static std::mutex s_omniBigLock;\n'
     'static std::set<const void*> s_omniBig;\n'
     'extern "C" int omniHwBigVideoActive(void) { std::lock_guard<std::mutex> l(s_omniBigLock); return !s_omniBig.empty(); }\n'
     'static void omniBigNote(const void* c, bool big) { std::lock_guard<std::mutex> l(s_omniBigLock); if (big) s_omniBig.insert(c); else s_omniBig.erase(c); }\n'
     'Client::~Client()\n{\n'),
    ('void Client::disconnect()\n{\n',
     'void Client::disconnect()\n{\n'
     '    omniBigNote(this, false);   // ' + MARK + '\n'),
    ('    codec_ = codec; track_ = track; bgra_ = bgra;\n',
     '    codec_ = codec; track_ = track; bgra_ = bgra;\n'
     '    omniBigNote(this, int64_t(track.width) * track.height >= int64_t(2560) * 1440);   // ' + MARK + '\n'),
]

SURFACE = [
    ('static bool asyncReadOn()\n{\n',
     '// ' + MARK + ': a large hardware video plays in this process (OmniHwClient.cpp); the ring is released meanwhile\n'
     'extern "C" int omniHwBigVideoActive(void);\n'
     'static bool videoTrimOn() { static const bool on = access("/data/omni/gpu-pages-video-trim-off.flag", F_OK) != 0; return on; }\n'
     'static bool asyncReadOn()\n{\n'),
    ('    // OMNI_GPUPAGES_ASYNCREAD_V1: pipelined whole-frame readback when on; its failure falls through to the code below\n'
     '    if (asyncReadOn() && didRenderAsync(surface, *state, source, w, h)) {\n',
     '    // ' + MARK + ': while a large video plays, hand on what is pending, free the ring, read synchronously\n'
     '    const bool omniTrim = videoTrimOn() && asyncReadOn() && omniHwBigVideoActive();\n'
     '    if (omniTrim) {\n'
     '        bool held = state->ringPending > 0;\n'
     '        for (auto& slot : state->ring) held = held || slot.pbo;\n'
     '        if (held) {\n'
     '            while (state->ringPending && asyncDeliverOldest(*state, 100)) { }\n'
     '            asyncFreeGL(*state);\n'
     '            fprintf(stderr, "OMNI GPUPAGES video-trim pid=%d: ring released (large video playing)\\n", getpid());\n'
     '            state->omniTrimmed = true;\n'
     '        }\n'
     '    } else if (state->omniTrimmed) {\n'
     '        state->omniTrimmed = false;\n'
     '        fprintf(stderr, "OMNI GPUPAGES video-trim pid=%d: ring back (video ended)\\n", getpid());\n'
     '    }\n'
     '    // OMNI_GPUPAGES_ASYNCREAD_V1: pipelined whole-frame readback when on; its failure falls through to the code below\n'
     '    if (!omniTrim && asyncReadOn() && didRenderAsync(surface, *state, source, w, h)) {\n'),
    ('    int ringHead { 0 }, ringPending { 0 };\n',
     '    int ringHead { 0 }, ringPending { 0 };\n'
     '    bool omniTrimmed { false };   // ' + MARK + '\n'),
]

print(patch(client, CLIENT, prepend='#include <set>  // ' + MARK + '\n'))
print(patch(surface, SURFACE))
