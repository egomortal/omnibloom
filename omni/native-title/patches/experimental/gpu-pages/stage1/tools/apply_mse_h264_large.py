#!/usr/bin/env python3
"""OMNI_MSE_H264_LARGE_V1 (2026-11-25, owner: movy "used to play"; now The Hunger Games never starts).

Cause (console run Lmviw2 with OMNI_MSE_FAIL_LOG_V1: "OMNI MSE: source failed: initialization unsupported"): movy serves
HLS fMP4 with H.264 2600x1080 (ultrawide, 2.8 Mpx) + AAC in one init. Page video (MSE) H.264 was capped at 1920x1080
*pixels* in four places, so anything wider than 16:9 1080p was refused, although the hardware decoder plays H.264 up to
3840x2160 (the progressive file player already does: OMNI_PROGRESSIVE_HOLEPUNCH_V1).

Now H.264 above 1920x1080 and up to 3840x2160 (each side) is accepted for MSE too, hardware-only (no software decoder
above 1080p, exactly like VP9 and HEVC):
  media/OmniMP4Demuxer.cpp   init/fragment demux: H.264 to 3840x2160 (was 1920*1080 pixels); the bounded AAC probe
                             skips frames of such an H.264 stream (skip_frame=all, as for HEVC) instead of software
                             decoding them with max_pixels 2073600
  media/OmniPacketDecoder.cpp  large H.264 is hardware-only for MSE as well (was: only inside the progressive player)
  media/OmniMediaCaps.h      isTypeSupported/canPlayType for MSE H.264: above 1080p when the hardware decodes, to 3840x2160
Kill switch: /data/omni/mse-h264-large-off.flag (old 1080p limit everywhere for MSE).
usage: apply_mse_h264_large.py <tree root holding engine/media>"""
import sys
from pathlib import Path

MARK = 'OMNI_MSE_H264_LARGE_V1'
root = Path(sys.argv[1]) / 'engine/media'


def patch(name, edits):
    p = root / name
    raw = p.read_bytes().decode('utf-8')
    nl = '\r\n' if '\r\n' in raw else '\n'
    s = raw.replace('\r\n', '\n')
    if MARK in s:
        return name + ': already'
    for old, new in edits:
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old[:90]))
        s = s.replace(old, new, 1)
    p.write_bytes(s.replace('\n', nl).encode('utf-8'))
    return name + ': applied'


OFF = '[] { FILE* f = fopen("/data/omni/mse-h264-large-off.flag", "r"); if (f) { fclose(f); return true; } return false; }()'

out = []
out.append(patch('OmniMP4Demuxer.cpp', [
    ('#include <cstring>\n', '#include <cstring>\n#include <cstdio> // ' + MARK + ': fopen (kill switch)\n'),
    ('            if(track.width<=0||track.height<=0||int64_t(track.width)*track.height>1920*1080)return fail("Video dimensions unsupported");\n',
     '            // ' + MARK + ': to 3840x2160 (hardware decode; PacketDecoder refuses it without the service). Was 1920*1080 pixels.\n'
     '            static const bool omniLargeOff = ' + OFF + ';\n'
     '            if(track.width<=0||track.height<=0||(omniLargeOff?int64_t(track.width)*track.height>1920*1080:(track.width>3840||track.height>2160)))return fail("Video dimensions unsupported");\n'),
    ('            if(context.format->streams[i]->codecpar->codec_id==AV_CODEC_ID_HEVC)av_dict_set(&probeOptions[i],"skip_frame","all",0);\n',
     '            if(context.format->streams[i]->codecpar->codec_id==AV_CODEC_ID_HEVC)av_dict_set(&probeOptions[i],"skip_frame","all",0);\n'
     '            else if(context.format->streams[i]->codecpar->codec_id==AV_CODEC_ID_H264&&int64_t(context.format->streams[i]->codecpar->width)*context.format->streams[i]->codecpar->height>1920*1080)\n'
     '                av_dict_set(&probeOptions[i],"skip_frame","all",0); // ' + MARK + ': large H.264 is hardware-only; never software-probed\n'),
]))
out.append(patch('OmniPacketDecoder.cpp', [
    ('    return omniLargeH264Hardware && track.codec == DemuxCodec::H264 && int64_t(track.width) * track.height > PacketDecoder::maxPixels;\n',
     '    // ' + MARK + ': MSE too (was the progressive player only), unless /data/omni/mse-h264-large-off.flag.\n'
     '    static const bool omniMseLargeOff = ' + OFF + ';\n'
     '    return (omniLargeH264Hardware || !omniMseLargeOff) && track.codec == DemuxCodec::H264 && int64_t(track.width) * track.height > PacketDecoder::maxPixels;\n'),
]))
out.append(patch('OmniMediaCaps.h', [
    ('#include <cstdint>\n', '#include <cstdint>\n#include <cstdio> // ' + MARK + ': fopen (kill switch)\n'),
    ('    if (pixels > (mse ? kMseMaxPixels : kFileMaxPixels)) return refuse("video: above 1920x1080 pixels");\n',
     '    // ' + MARK + ': MSE H.264 above 1080p when the hardware decodes it, to 3840x2160 (kill switch mse-h264-large-off.flag).\n'
     '    static const bool omniMseLargeOff = ' + OFF + ';\n'
     '    if (mse && hardware && !omniMseLargeOff && pixels > kMseMaxPixels) {\n'
     '        if (v.width > 3840 || v.height > 2160) return refuse("video: above 3840x2160");\n'
     '    } else if (pixels > (mse ? kMseMaxPixels : kFileMaxPixels)) return refuse("video: above 1920x1080 pixels");\n'),
]))
print('; '.join(out), MARK)
