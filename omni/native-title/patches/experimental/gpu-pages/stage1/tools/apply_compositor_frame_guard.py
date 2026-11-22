#!/usr/bin/env python3
"""OMNI_COMPOSITOR_FRAME_GUARD_V1 (2026-11-21): web-process crash SIGSEGV at address 0x8 in RunLoop::TimerBase::start
<- ThreadedCompositor::frameComplete <- AcceleratedSurface::frameDone (rip child+0x971def; g9y/g9z/g9v, exactly the runs
where OMNI_LAYERS_VIDEO_SLEEP_V1 left composited mode). ThreadedCompositor::invalidate() runs a task on the compositing
run loop that sets m_display.updateTimer = nullptr (and drops the GL context); a frame-done callback already queued on that
run loop then runs frameComplete() -> displayUpdateFired() -> m_display.updateTimer->startOneShot() on a NULL timer.
Fix: frameComplete() and displayUpdateFired() return at once when the timer is gone (the compositor is invalidated; both
run on the compositing thread, the same thread that clears the timer, so the check is not racy).
usage: apply_compositor_frame_guard.py <CoordinatedGraphics dir holding ThreadedCompositorPlayStation.cpp>"""
import sys
from pathlib import Path

MARK = 'OMNI_COMPOSITOR_FRAME_GUARD_V1'
p = Path(sys.argv[1]) / 'ThreadedCompositorPlayStation.cpp'
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK in s:
    print('already', p.name); sys.exit(0)
G = ('#if !HAVE(DISPLAY_LINK)\n    if (!m_display.updateTimer)   // ' + MARK + ': compositor invalidated; a late frame-done does nothing\n'
     '        return;\n#endif\n')
for fn in ('void ThreadedCompositor::frameComplete()\n{\n', 'void ThreadedCompositor::displayUpdateFired()\n{\n'):
    if s.count(fn) != 1:
        sys.exit('%s anchor found %d times' % (fn.split('(')[0], s.count(fn)))
    s = s.replace(fn, fn + G, 1)
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied', p.name)
