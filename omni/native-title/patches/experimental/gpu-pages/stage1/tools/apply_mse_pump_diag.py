#!/usr/bin/env python3
"""OMNI_MSE_PUMP_DIAG_V1 (2026-11-25, diagnostic): why MSE video stops after the first segment.

movy The Hunger Games (H.264 2600x1080 + AAC, HLS fMP4) on the separate engine after
OMNI_MSE_H264_LARGE_V1: the first ~5.7 s of video decode on the hardware (137 frames, the shell shows
132), then no video sample is decoded again while audio plays on (36 s+); no error, no quality switch.
Once a second (at most 150 lines) the video track's pump prints what reached it and what the decoder
answered, so the next run tells "samples never arrive" (append / WebKit) from "decoder refuses them"
(NeedOutput forever) from "decoder gives nothing back":
  OMNI MSE PUMP: v appended=N (last pts) enqueued=N (last pts) queue=N ... submit acc/need/err receive out/need/end/err
usage: apply_mse_pump_diag.py <tree root holding engine/entry>"""
import sys
from pathlib import Path

MARK = 'OMNI_MSE_PUMP_DIAG_V1'
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


V = 'OmniMedia::isVideoCodec'
rep('class Buffer final : public SourceBufferPrivate {\n',
    'namespace { struct OmniPumpDiag { unsigned long long appV = 0, appA = 0, enqV = 0, enqA = 0, subAcc = 0, subNeed = 0, subErr = 0,\n'
    '    rcvOut = 0, rcvNeed = 0, rcvEnd = 0, rcvErr = 0; double lastAppV = -1, lastEnqV = -1, lastPrint = 0; unsigned lines = 0; } omniPd; } // ' + MARK + '\n'
    'class Buffer final : public SourceBufferPrivate {\n')
# fragments demuxed (before WebKit's sample processing)
rep('                    packet.configuration = found->second->latest; // OMNI_WEBM_V1\n',
    '                    packet.configuration = found->second->latest; // OMNI_WEBM_V1\n'
    '                    if (' + V + '(info.codec)) { ++omniPd.appV; if (packet.timeBase.denominator > 0) omniPd.lastAppV = double(packet.pts) * packet.timeBase.numerator / packet.timeBase.denominator; } else ++omniPd.appA; // ' + MARK + '\n')
# samples WebKit hands to the decoder queue
rep('        found->second->queue.push_back(std::move(*packet));\n',
    '        if (' + V + '(found->second->info.codec)) { ++omniPd.enqV; if (packet->timeBase.denominator > 0) omniPd.lastEnqV = double(packet->pts) * packet->timeBase.numerator / packet->timeBase.denominator; } else ++omniPd.enqA; // ' + MARK + '\n'
    '        found->second->queue.push_back(std::move(*packet));\n')
rep('                    auto sent = track.decoder.submit(track.queue.front());\n',
    '                    auto sent = track.decoder.submit(track.queue.front());\n'
    '                    if (' + V + '(track.info.codec)) { if (sent == OmniMedia::PacketDecoder::Submit::Accepted) ++omniPd.subAcc; else if (sent == OmniMedia::PacketDecoder::Submit::NeedOutput) ++omniPd.subNeed; else ++omniPd.subErr; } // ' + MARK + '\n')
rep('                auto received = track.decoder.receive(output);\n',
    '                auto received = track.decoder.receive(output);\n'
    '                if (' + V + '(track.info.codec)) { if (received == OmniMedia::PacketDecoder::Receive::Output) ++omniPd.rcvOut; else if (received == OmniMedia::PacketDecoder::Receive::NeedInput) ++omniPd.rcvNeed; else if (received == OmniMedia::PacketDecoder::Receive::End) ++omniPd.rcvEnd; else ++omniPd.rcvErr; } // ' + MARK + '\n')
rep('            auto& track = *owned;\n',
    '            auto& track = *owned;\n'
    '            if (' + V + '(track.info.codec) && omniPd.lines < 150) { // ' + MARK + '\n'
    '                const double nowS = MonotonicTime::now().secondsSinceEpoch().seconds();\n'
    '                if (nowS - omniPd.lastPrint >= 1.0) {\n'
    '                    omniPd.lastPrint = nowS; ++omniPd.lines;\n'
    '                    fprintf(stderr, "OMNI MSE PUMP: v appended=%llu (last %.3f) enqueued=%llu (last %.3f) queue=%zu queuedAll=%llu output=%d ended=%d reconf=%d drainSent=%d allEnq=%d active=%u latest=%u configs=%zu hw=%d held=%d released=%d submit acc=%llu need=%llu err=%llu receive out=%llu need=%llu end=%llu err=%llu | a appended=%llu enqueued=%llu (' + MARK + ')\\n",\n'
    '                        omniPd.appV, omniPd.lastAppV, omniPd.enqV, omniPd.lastEnqV, track.queue.size(), (unsigned long long)m_queuedCount, !!track.output, track.ended, track.reconfiguring,\n'
    '                        track.drainSent, track.allEnqueued, track.active, track.latest, track.configs.size(), track.decoder.usingHardware(), m_videoHeld, track.decoder.hardwareReleased(),\n'
    '                        omniPd.subAcc, omniPd.subNeed, omniPd.subErr, omniPd.rcvOut, omniPd.rcvNeed, omniPd.rcvEnd, omniPd.rcvErr, omniPd.appA, omniPd.enqA);\n'
    '                    fflush(stderr);\n'
    '                }\n'
    '            }\n')
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('mse pump diag: patched', p.name)
