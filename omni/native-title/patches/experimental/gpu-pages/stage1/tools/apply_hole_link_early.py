#!/usr/bin/env python3
"""OMNI_HOLE_LINK_EARLY_V1 (2026-11-24): fix a start-up deadlock of MSE video with the shell's video plane (V5).

Seen as Bloom Preview 5's in-app YouTube stall (played 0.015 s; HOLEDIAG on the console, run Lytiw-143459: eligible=1
onScreen=1 paused=0 link=0 for the whole run, hold=start). The order that deadlocks:
  1. while the video's size is unknown the hole controller does not want the plane (eligible=0), so the decoder's first
     frames are ordinary converted images; the first one is painted (m_image) and the V5 startup hold keeps the
     playhead at the first frame;
  2. once the video is eligible the decoder makes hole frames, but each is ahead of the held playhead, and consume()
     returned false BEFORE it took the frame's HoleLink (m_holeLink was only set from a frame it accepted);
  3. without a link the controller never claims the plane, pacing never starts, and the startup gate (no timeout by
     design, V133) waits for pacing forever.
The in-app page engine's timing hits this order often; the separate engine rarely. Fix: a hole frame that is held back
still hands over its link (it is the same link the frame would set when accepted; the frame itself stays queued). With
the link the controller claims, the shell paces, and V5 frees the held frames ahead of the playhead as designed.
usage: apply_hole_link_early.py <OmniMSEPlayer.cpp>"""
import sys
from pathlib import Path

MARK = 'OMNI_HOLE_LINK_EARLY_V1'
p = Path(sys.argv[1])
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK in s:
    print('already', p.name); sys.exit(0)
old = '            if ((m_image || m_holeHasFrame) && time > m_position + 0.005) return false;\n'
new = ('            // ' + MARK + ' part 2 (console run Lytiw-162135 on the part-1 build: decodedAccepted=2 painted=1, then\n'
       '            // nothing): the frames decoded before the video was eligible are converted images. One of them ahead of\n'
       '            // the held playhead blocks the queue, so the hole frames behind it never arrive and there is no link to\n'
       '            // take. While the start hold waits for the plane, the player wants hole frames and has no link yet, such\n'
       '            // a converted frame is dropped (the first frame is already on screen; the plane takes over from the\n'
       '            // hole frames behind it).\n'
       '            if (m_v5 && m_v5Hold && !output.hole && m_holeDecoderWanted && !m_holeLink && m_holeAllowed\n'
       '                && (m_image || m_holeHasFrame) && time > m_position + 0.005) {\n'
       '                ++m_decodedVideoFrames; ++m_droppedVideoFrames; ++m_discardedPrerollFrames;\n'
       '                if (!m_holeEarlyDropLogged) {\n'
       '                    m_holeEarlyDropLogged = true;\n'
       '                    fprintf(stderr, "OMNI HOLEPUNCH: start hold without a plane link: dropping converted frames ahead of %.3f so the hole frames behind them arrive\\n", m_position);\n'
       '                    fflush(stderr);\n'
       '                }\n'
       '                return true;\n'
       '            }\n'
       '            if ((m_image || m_holeHasFrame) && time > m_position + 0.005) {\n'
       '                // ' + MARK + ': a held-back hole frame still hands over its link, or the plane is never claimed\n'
       '                // and the V5 startup hold (no timeout) waits for pacing forever.\n'
       '                if (output.hole && !m_holeLink) m_holeLink = output.hole->link();\n'
       '                return false;\n'
       '            }\n')
if s.count(old) != 1:
    sys.exit('%s: anchor found %d times' % (p.name, s.count(old)))
s = s.replace(old, new, 1)
for a, b in (('        source.setVideoHolePunch(act.decoderHoles);\n',
              '        source.setVideoHolePunch(act.decoderHoles);\n'
              '        m_holeDecoderWanted = act.decoderHoles; // ' + MARK + '\n'),
             ('    bool m_v5 = false;\n',
              '    bool m_v5 = false;\n'
              '    bool m_holeDecoderWanted = false, m_holeEarlyDropLogged = false; // ' + MARK + '\n')):
    if s.count(a) != 1:
        sys.exit('%s: anchor found %d times: %r' % (p.name, s.count(a), a[:60]))
    s = s.replace(a, b, 1)
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('hole link early: patched', p.name)
