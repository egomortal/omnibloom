#!/usr/bin/env python3
"""OMNI_MSE_TRACK_QUOTA_V1 (2026-11-25, movy: "it starts but the picture dont move").

Cause (console run with OMNI_MSE_PUMP_DIAG_V1, movy The Hunger Games, one SourceBuffer holding H.264 +
AAC): the demuxer appended video to 54 s, but WebKit handed the decoder only the first 144 video samples
(5.96 s). The buffer's sample queue limit (maximumCount 128) was SHARED by its tracks: the audio track,
paced ~3 s ahead, kept its queue at exactly 128 samples, so isReadyForMoreSamples() said no for the video
track for ever (every slot audio freed went back to audio). Picture frozen, sound playing. Sites that
use a separate SourceBuffer per track (YouTube) never hit it.

Now the 128-sample limit is per track (a track's own queue); the byte quota (maxQueued) still bounds the
buffer as a whole, so memory stays bounded the same way. The quality-switch "queue is full" release
looks at the waiting track's own queue.
Kill switch: /data/omni/mse-shared-quota.flag (the old shared limit).
usage: apply_mse_track_quota.py <tree root holding engine/entry>"""
import sys
from pathlib import Path

MARK = 'OMNI_MSE_TRACK_QUOTA_V1'
p = Path(sys.argv[1]) / 'engine/entry/OmniMSESource.cpp'
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK in s:
    print('already', p.name); sys.exit(0)


def rep(old, new):
    global s
    if s.count(old) != 1:
        sys.exit('%s: anchor found %d times: %r' % (p.name, s.count(old), old[:90]))
    s = s.replace(old, new, 1)


rep('class Buffer final : public SourceBufferPrivate {\n',
    '#include <cstdio> // ' + MARK + ': fopen (kill switch)\n'
    'static bool omniMseSharedQuota() // ' + MARK + ': /data/omni/mse-shared-quota.flag = the old shared sample limit\n'
    '{\n'
    '    static const bool on = [] { FILE* f = fopen("/data/omni/mse-shared-quota.flag", "r"); if (f) { fclose(f); return true; } return false; }();\n'
    '    return on;\n'
    '}\n'
    'class Buffer final : public SourceBufferPrivate {\n')
rep('(m_queuedCount + 8 >= maximumCount || m_queuedBytes',
    '((omniMseSharedQuota() ? m_queuedCount : track.queue.size()) + 8 >= maximumCount || m_queuedBytes')   # MARK in the comment below
rep('!found->second->drainSent && m_queuedCount < maximumCount && m_queuedBytes <= maxQueued() - maxPacket(); // OMNI_WEBM_V1\n',
    '!found->second->drainSent && (omniMseSharedQuota() ? m_queuedCount : found->second->queue.size()) < maximumCount && m_queuedBytes <= maxQueued() - maxPacket(); // OMNI_WEBM_V1; ' + MARK + ': per track\n')
rep('m_queuedBytes > maxQueued() - bytes || m_queuedCount >= maximumCount) { fail("encoded queue quota"); return; } // OMNI_WEBM_V1\n',
    'm_queuedBytes > maxQueued() - bytes || (omniMseSharedQuota() ? m_queuedCount : found->second->queue.size()) >= maximumCount) { fail("encoded queue quota"); return; } // OMNI_WEBM_V1; ' + MARK + ': per track\n')
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('mse track quota: patched', p.name, MARK)
