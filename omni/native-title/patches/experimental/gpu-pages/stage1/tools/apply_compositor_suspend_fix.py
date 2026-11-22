#!/usr/bin/env python3
"""OMNI_COMPOSITOR_SUSPEND_FIX_V1 (2026-11-19, owner report: "heavy memory pages and reloading").

Crash (owner session 2026-11-19, 3x identical, rip child+0x971fec): closing a tab -> the other tab's web process dies:
  WTFCrashWithInfo <- RunLoop assertIsCurrent <- RunLoop::TimerBase::stop (RunLoopGeneric.cpp:340: an ACTIVE timer may
  only be stopped on its own run loop) <- CompositingRunLoop::suspend/resume via ThreadedCompositor <- LayerTreeHost
  resumeRendering/pauseRendering <- DrawingAreaCoordinatedGraphics activityStateDidChange <- WebPage::setActivityState.
CompositingRunLoop::suspend() runs on the MAIN thread and stops m_updateTimer, which belongs to the compositing run loop.
When an update is already scheduled (timer armed) that is a cross-thread stop of an active timer -> release assertion.
Omni then shows its crash page ("often memory on a heavy page") and the page reloads.

Fix: suspend() stops the timer only where that is allowed (on the compositing run loop, or when the timer is not
armed). Otherwise it leaves it armed: updateTimerFired() already returns at once while m_state.isSuspended (state stays
Scheduled), and resume() restarts it with startOneShot as before. No other behaviour changes.
Patches CompositingRunLoop.cpp in the given CoordinatedGraphics dir. No backup file (the child recipe's changed-file
gate counts files in the tree). usage: apply_compositor_suspend_fix.py <CoordinatedGraphics dir>"""
import sys
from pathlib import Path

MARK = 'OMNI_COMPOSITOR_SUSPEND_FIX_V1'
p = Path(sys.argv[1]) / 'CompositingRunLoop.cpp'
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK in s:
    print('already', p.name); sys.exit(0)
OLD = ('void CompositingRunLoop::suspend()\n'
       '{\n'
       '    Locker stateLocker { m_state.lock };\n'
       '    m_state.isSuspended = true;\n'
       '    m_updateTimer.stop();\n'
       '}\n')
NEW = ('void CompositingRunLoop::suspend()\n'
       '{\n'
       '    Locker stateLocker { m_state.lock };\n'
       '    m_state.isSuspended = true;\n'
       '    // ' + MARK + ': called on the main thread; an ARMED timer may only be stopped on its own run loop\n'
       '    // (RunLoop::TimerBase::stop asserts). Left armed, it fires and updateTimerFired() returns while suspended.\n'
       '    if (m_runLoop->isCurrent() || !m_updateTimer.isActive())\n'
       '        m_updateTimer.stop();\n'
       '}\n')
if s.count(OLD) != 1:
    sys.exit('%s: anchor found %d times' % (p.name, s.count(OLD)))
s = s.replace(OLD, NEW, 1)
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied', p.name)
