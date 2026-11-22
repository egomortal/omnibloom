#!/usr/bin/env python3
"""OMNI_HWCLIENT_SIZE_GUARD_V1 (2026-11-19, owner session: a video page showed the crash page with no tab closed).

Crash (owner log, web pid 164, SIGABRT): std::vector::__append <- OmniMedia::Hw::Client::convert (OmniHwClient.cpp) <-
Client::handle <- PacketDecoder::receive, with "allocator mmap failed: bytes=18446744064577912832" (a NEGATIVE size cast
to size_t). Client::convert sizes its buffers from track_.width/height (and the shown size from videoOutputSize) without
checking them: a non-positive or absurd size makes resize() ask for ~2^64 bytes -> bad_alloc -> abort -> crash page.

Fix: convert() returns false (that one picture is not converted, exactly like its existing bounds checks) when the
track size or the output size is outside 1..8192. Valid pictures take the unchanged path.
Patches engine/media/OmniHwClient.cpp under the given engine dir (no backup: the child recipe's changed-file gate).
usage: apply_hwclient_size_guard.py <engine dir (holding media/)>"""
import sys
from pathlib import Path

MARK = 'OMNI_HWCLIENT_SIZE_GUARD_V1'
p = Path(sys.argv[1]) / 'media' / 'OmniHwClient.cpp'
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK in s:
    print('already', p.name); sys.exit(0)
EDITS = [
    ('    const int w = track_.width, h = track_.height;\n    const bool tenBit = m.e > 8;\n',
     '    const int w = track_.width, h = track_.height;\n'
     '    if (w <= 0 || h <= 0 || w > 8192 || h > 8192) return false;   // ' + MARK + ': a bogus track size made resize() ask for ~2^64 bytes\n'
     '    const bool tenBit = m.e > 8;\n'),
    ('    videoOutputSize(w, h, targetWidth_, targetHeight_, ow, oh);\n',
     '    videoOutputSize(w, h, targetWidth_, targetHeight_, ow, oh);\n'
     '    if (ow <= 0 || oh <= 0 || ow > 8192 || oh > 8192) return false;   // ' + MARK + '\n'),
]
for old, _ in EDITS:
    if s.count(old) != 1:
        sys.exit('%s: anchor found %d times: %r' % (p.name, s.count(old), old.strip()[:80]))
for old, new in EDITS:
    s = s.replace(old, new, 1)
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied', p.name)
