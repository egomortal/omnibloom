#!/usr/bin/env python3
"""OMNI_MSE_H264_PROBE_V1 (2026-11-25, movy The Hunger Games: H.264 2600x1080 MSE).

After OMNI_MSE_H264_LARGE_V1 every fragment of a large H.264 stream still runs the bounded AAC probe
(avformat_find_stream_info) with max_pixels 2073600 on the video stream: the h264 decoder refuses to
open ("Picture size 2600x1080 exceeds specified max pixel count", "Could not find codec parameters for
stream 0"). skip_frame=all alone does not help: the open itself fails. Now such a stream's probe
options allow 3840x2160 pixels (8294400); with skip_frame=all its frames are still never decoded in
software. Needs OMNI_MSE_H264_LARGE_V1 applied first (its kill switch covers this too: the probe
only differs for H.264 above 1920x1080, which that switch refuses before the probe).
usage: apply_mse_h264_probe.py <tree root holding engine/media>"""
import sys
from pathlib import Path

MARK = 'OMNI_MSE_H264_PROBE_V1'
p = Path(sys.argv[1]) / 'engine/media/OmniMP4Demuxer.cpp'
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK in s:
    print('already', p.name); sys.exit(0)
old = ('                av_dict_set(&probeOptions[i],"skip_frame","all",0); // OMNI_MSE_H264_LARGE_V1: large H.264 is hardware-only; never software-probed\n')
new = ('                { av_dict_set(&probeOptions[i],"skip_frame","all",0); // OMNI_MSE_H264_LARGE_V1: large H.264 is hardware-only; never software-probed\n'
       '                  av_dict_set(&probeOptions[i],"max_pixels","8294400",0); } // ' + MARK + ': or the probe cannot even open the decoder\n')
if s.count(old) != 1:
    sys.exit('%s: anchor found %d times (apply OMNI_MSE_H264_LARGE_V1 first)' % (p.name, s.count(old)))
s = s.replace(old, new, 1)
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('mse h264 probe: patched', p.name, MARK)
