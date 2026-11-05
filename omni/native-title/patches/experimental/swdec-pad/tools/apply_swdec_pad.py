#!/usr/bin/env python3
"""OMNI_SWDEC_PAD_V1: OmniVideoDecoder::next() converts each software-decoded frame into an RGBA vector of
exactly w*h*4 bytes with stride w*4. FFmpeg 7.1.5's x86 4:2:0/4:2:2 -> RGB converters write whole 16-pixel
groups and run up to 32 bytes past the end of that buffer (host test: omni-crash-memloop/swstest.txt), which
overwrites the next libc heap chunk's header with pixels -> #GP in malloc/free -> SIGBUS code 3 (memloop, reddit).
Convert into rows padded to 16 pixels (plus 64 bytes of slack), as OmniPacketDecoder / OmniHwClient already do,
then pack the rows. Usage: apply_swdec_pad.py <tree>  (edits <tree>/engine/media/OmniVideoDecoder.cpp)"""
import sys
from pathlib import Path
p = Path(sys.argv[1]) / 'engine/media/OmniVideoDecoder.cpp'
s = open(p, newline='').read()
nl = '\r\n' if '\r\n' in s else '\n'
if 'OMNI_SWDEC_PAD_V1' in s: print('already'); sys.exit(0)
old = '''            output.rgba.resize(size_t(w) * h * 4);
            uint8_t* planes[] = {output.rgba.data(), nullptr, nullptr, nullptr};
            int strides[] = {w * 4, 0, 0, 0};
            if (sws_scale(s.scale, s.frame->data, s.frame->linesize, 0, h, planes, strides) != h) {
                s.fail("Incomplete converted frame"); return Result::Error;
            }
'''
new = '''            // OMNI_SWDEC_PAD_V1: swscale's x86 4:2:0 -> RGB converters write whole 16-pixel groups, up to
            // 32 bytes past an exactly sized w * 4 * h buffer (heap overflow). Rows padded to 16 pixels
            // (+64 bytes slack), as OmniPacketDecoder / OmniHwClient, then packed back to w * 4.
            const size_t row = size_t(w) * 4, stride = (size_t(w) + 15) / 16 * 16 * 4;
            output.rgba.resize(stride * size_t(h) + 64);
            uint8_t* planes[] = {output.rgba.data(), nullptr, nullptr, nullptr};
            int strides[] = {int(stride), 0, 0, 0};
            if (sws_scale(s.scale, s.frame->data, s.frame->linesize, 0, h, planes, strides) != h) {
                s.fail("Incomplete converted frame"); return Result::Error;
            }
            if (stride != row)
                for (int r = 1; r < h; r++) memmove(output.rgba.data() + size_t(r) * row, output.rgba.data() + size_t(r) * stride, row);
            output.rgba.resize(row * size_t(h));
'''
old, new = old.replace('\n', nl), new.replace('\n', nl)
assert s.count(old) == 1, 'anchor not found exactly once'
s = s.replace(old, new)
assert '#include <cstring>' in s
open(p, 'w', newline='').write(s); print('OMNI_SWDEC_PAD_V1: 1 edit')
