# Experimental: `OMNI_SWDEC_PAD_V1`, software video decoder overflow (child engine)

> **Fix pending console test.** Proven on the host; a candidate child is built but has not been run on the console.
> Not part of any release build.

**The bug** ([`REPORT.md`](REPORT.md)): pages with many small autoplay videos (reddit.com's feed) use up the hardware
decoder, so the rest fall back to the software player. That player converts each frame with FFmpeg 7.1.5's `sws_scale`
into a buffer of exactly `w*h*4` bytes, and the x86 4:2:0 converters write whole 16-pixel groups: **up to 32 bytes past
the end** whenever the width is not a multiple of 16. The overrun lands on the next heap chunk's header, and the next
`malloc`/`free` faults (SIGBUS code 3). The page process crashes; Omni recovers and reloads. It happens on the stock child
too (reddit crashed in both passes of all three memloop runs) and is not a memory-size problem.

**The fix** (`tools/apply_swdec_pad.py <tree>`, one edit in `engine/media/OmniVideoDecoder.cpp`): convert into rows padded
to 16 pixels (+64 bytes), then pack the rows, as `OmniPacketDecoder` and `OmniHwClient` already do. The player's size
checks are unchanged. Host proof: 996 of 3535 sizes overflow today, 0 of 3535 with the padded stride.

**Still to do:** the console repro in `REPORT.md` §6 (a local page of small non-multiple-of-16 H.264 videos on the
software path, then reddit only, then the full memloop) on the candidate child, before it goes into a release child.
