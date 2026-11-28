#!/usr/bin/env python3
"""OMNI_AUDIO_MP2_V1 (2026-11-26, after OMNI_AUDIO_AC3_MP3_V1): MPEG-1/2 Layer II audio ("MP2") in HLS MPEG-TS.

Broadcast and IPTV transport streams very often carry MP2 audio (stream type 0x03/0x04), which FFmpeg's mpegts
demuxer reports as AV_CODEC_ID_MP2. After OMNI_AUDIO_AC3_MP3_V1 such a segment still had no playable audio
("no H.264 or AAC in the segment" without video, silent video with it). The FFmpeg in Omni has the mp2 decoder and
the mpegaudio parser. Now:
  media/OmniMP4Demuxer.h      DemuxCodec MP2 (appended), no codec configuration needed
  media/OmniHlsSegment.cpp    TS: AV_CODEC_ID_MP2 like MP3 (layer II frame headers: 1152 samples per frame)
  media/OmniPacketDecoder.cpp AV_CODEC_ID_MP2
  media/OmniHlsSession.cpp    HLS variants listing mp4a.40.33 (MPEG-1 Layer II) are playable
Same kill switch: /data/omni/audio-ac3-mp3-off.flag. Needs OMNI_AUDIO_AC3_MP3_V1 first (edits its lines).
usage: apply_audio_mp2.py <tree root holding engine/media>"""
import sys
from pathlib import Path

MARK = 'OMNI_AUDIO_MP2_V1'
root = Path(sys.argv[1]) / 'engine'


def patch(rel, edits):
    p = root / rel
    raw = p.read_bytes().decode('utf-8')
    nl = '\r\n' if '\r\n' in raw else '\n'
    s = raw.replace('\r\n', '\n')
    if MARK in s:
        return rel + ': already'
    if 'OMNI_AUDIO_AC3_MP3_V1' not in s:
        sys.exit('%s: apply OMNI_AUDIO_AC3_MP3_V1 first' % rel)
    for old, new in edits:
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (rel, s.count(old), old[:100]))
        s = s.replace(old, new, 1)
    p.write_bytes(s.replace('\n', nl).encode('utf-8'))
    return rel + ': applied'


out = []
out.append(patch('media/OmniMP4Demuxer.h', [
    ('HEVC, AC3, EAC3, MP3 };', 'HEVC, AC3, EAC3, MP3, MP2 }; /* ' + MARK + ': + MP2 */'),
    ('return c == DemuxCodec::AC3 || c == DemuxCodec::EAC3 || c == DemuxCodec::MP3; }',
     'return c == DemuxCodec::AC3 || c == DemuxCodec::EAC3 || c == DemuxCodec::MP3 || c == DemuxCodec::MP2; } /* ' + MARK + ' */'),
]))
out.append(patch('media/OmniPacketDecoder.cpp', [
    ('case DemuxCodec::MP3: return AV_CODEC_ID_MP3;', 'case DemuxCodec::MP3: return AV_CODEC_ID_MP3; case DemuxCodec::MP2: return AV_CODEC_ID_MP2; /* ' + MARK + ' */'),
]))
out.append(patch('media/OmniHlsSegment.cpp', [
    # the frame reader: layer II next to layer III (same header; its own bitrate table and 1152 samples in every version)
    ('        if (id == AV_CODEC_ID_MP3) {\n',
     '        if (id == AV_CODEC_ID_MP3 || id == AV_CODEC_ID_MP2) {   // ' + MARK + ': + layer II\n'),
    ('            if (ver == 1 || layer != 1 || bri == 0 || bri == 15 || sri == 3) return false;   // layer III only\n',
     '            const bool l2 = id == AV_CODEC_ID_MP2;   // ' + MARK + '\n'
     '            if (ver == 1 || layer != (l2 ? 2u : 1u) || bri == 0 || bri == 15 || sri == 3) return false;   // layer III (MP3) or II (MP2)\n'),
    ('            fc = mode == 3 ? 1 : 2; fs = ver == 3 ? 1152 : 576;\n'
     '            bytes = size_t((ver == 3 ? 144 : 72) * (ver == 3 ? v1[bri] : v2[bri]) * 1000 / fr + pad);\n',
     '            static const int v1l2[15] = { 0, 32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384 };   // ' + MARK + '\n'
     '            fc = mode == 3 ? 1 : 2; fs = (l2 || ver == 3) ? 1152 : 576;\n'
     '            const int kbps = ver == 3 ? (l2 ? v1l2[bri] : v1[bri]) : v2[bri];\n'
     '            bytes = size_t(((l2 || ver == 3) ? 144 : 72) * kbps * 1000 / fr + pad);\n'),
    ('"h264,aac,ac3,eac3,mp3,mp3float"', '"h264,aac,ac3,eac3,mp3,mp3float,mp2,mp2float"'),
    ('        } else if ((id == AV_CODEC_ID_AC3 || id == AV_CODEC_ID_EAC3 || id == AV_CODEC_ID_MP3) && omniExtraAudioEnabled()\n',
     '        } else if ((id == AV_CODEC_ID_AC3 || id == AV_CODEC_ID_EAC3 || id == AV_CODEC_ID_MP3 || id == AV_CODEC_ID_MP2) && omniExtraAudioEnabled()   // ' + MARK + ': + MP2\n'),
    ('                const DemuxCodec codec = id == AV_CODEC_ID_AC3 ? DemuxCodec::AC3 : id == AV_CODEC_ID_EAC3 ? DemuxCodec::EAC3 : DemuxCodec::MP3;\n',
     '                const DemuxCodec codec = id == AV_CODEC_ID_AC3 ? DemuxCodec::AC3 : id == AV_CODEC_ID_EAC3 ? DemuxCodec::EAC3 : id == AV_CODEC_ID_MP2 ? DemuxCodec::MP2 : DemuxCodec::MP3; // ' + MARK + '\n'),
]))
out.append(patch('media/OmniHlsSession.cpp', [
    ('|| low == "mp4a.40.34")) return true;', '|| low == "mp4a.40.34" || low == "mp4a.40.33")) return true; /* ' + MARK + ': + MPEG-1 Layer II */'),
]))
print('; '.join(out), MARK)
