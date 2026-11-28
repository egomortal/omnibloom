#!/usr/bin/env python3
"""OMNI_HLS_H264_LARGE_V1 (2026-11-25, after Bloom Preview 6: native HLS still capped H.264 at 1080p).

Native HLS (<video src="...m3u8">, OmniHlsPlayer) picks its variant through Hls::variantPlayable(), which allowed
H.264 only up to 1920*1080 pixels: a 1440p/4K or ultrawide (2560x1080, 2600x1080) H.264 variant was skipped, so the
player stayed at 1080p or, when every variant was larger, refused the stream. Since OMNI_MSE_H264_LARGE_V1 the rest of
the path already takes them: TS segments have no size cap (SPS parse only), fMP4 segments go through demuxMP4Fragment
(to 3840x2160), and PacketDecoder sends H.264 above 1080p to the hardware decoder only.

Now an H.264 variant may be up to 3840x2160 (each side) when the hardware decoder is on, as HEVC already was. Without
the hardware (or with either kill switch) the old 1080p limit stays.
Kill switches: /data/omni/hls-h264-large-off.flag (this alone), /data/omni/mse-h264-large-off.flag (also turns off the
hardware-only route in PacketDecoder, so HLS must not pick large H.264 then either).
Needs OMNI_MSE_H264_LARGE_V1 in the same tree (the decoder half).
usage: apply_hls_h264_large.py <tree root holding engine/media>"""
import sys
from pathlib import Path

MARK = 'OMNI_HLS_H264_LARGE_V1'
p = Path(sys.argv[1]) / 'engine/media/OmniHlsSession.cpp'
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK in s:
    print('already', p.name); sys.exit(0)
dec = Path(sys.argv[1]) / 'engine/media/OmniPacketDecoder.cpp'
if 'OMNI_MSE_H264_LARGE_V1' not in dec.read_bytes().decode('utf-8'):
    sys.exit('OmniPacketDecoder.cpp lacks OMNI_MSE_H264_LARGE_V1: apply it first')


def rep(old, new):
    global s
    if s.count(old) != 1:
        sys.exit('%s: anchor found %d times: %r' % (p.name, s.count(old), old[:90]))
    s = s.replace(old, new, 1)


rep('bool variantPlayable(const Variant& v, bool hardware)\n{\n',
    'static bool omniHlsFlag(const char* path) // ' + MARK + '\n'
    '{\n'
    '    FILE* f = fopen(path, "r");\n'
    '    if (f) { fclose(f); return true; }\n'
    '    return false;\n'
    '}\n'
    'bool variantPlayable(const Variant& v, bool hardware)\n{\n')
rep('    const int64_t maxPixels = hevc ? int64_t(3840) * 2160 : int64_t(1920) * 1080;\n'
    '    return int64_t(v.width) * v.height <= maxPixels && v.width <= (hevc ? 3840 : 4096) && v.height <= (hevc ? 2160 : 4096);\n',
    '    // ' + MARK + ': H.264 to 3840x2160 on the hardware decoder (PacketDecoder: hardware-only above 1080p), like HEVC.\n'
    '    static const bool largeOff = omniHlsFlag("/data/omni/hls-h264-large-off.flag") || omniHlsFlag("/data/omni/mse-h264-large-off.flag");\n'
    '    const int64_t maxPixels = hevc ? int64_t(3840) * 2160 : int64_t(1920) * 1080;\n'
    '    if (int64_t(v.width) * v.height <= maxPixels && v.width <= (hevc ? 3840 : 4096) && v.height <= (hevc ? 2160 : 4096)) return true;\n'
    '    return !hevc && hardware && !largeOff && v.width <= 3840 && v.height <= 2160;\n')
if '#include <cstdio>' not in s:
    i = s.index('#include ')
    s = s[:i] + '#include <cstdio> // ' + MARK + ': fopen (kill switches)\n' + s[i:]
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('hls h264 large: patched', p.name, MARK)
