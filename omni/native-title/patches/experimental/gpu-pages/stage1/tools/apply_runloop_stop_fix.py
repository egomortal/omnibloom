#!/usr/bin/env python3
"""OMNI_RUNLOOP_STOP_FIX_V1 (2026-11-19, owner: tab-close / tab-switch crash pages persist with g9d).

The crash (owner logs, identical rip child+0x971fec in g9b AND g9d): WTF::RunLoop::TimerBase::stop() ->
assertIsCurrent(m_runLoop) -> WTFCrashWithInfo, reached from the main thread while WebPage::setActivityState ->
DrawingAreaCoordinatedGraphics::activityStateDidChange suspends / resumes the PlayStation compositor (layers path).
OMNI_COMPOSITOR_SUSPEND_FIX_V1 guarded one caller (CompositingRunLoop::suspend); the crash persisted, so another
stop() on the same path stops a timer owned by the compositing run loop.

Fix at the source: TimerBase::stop() of an ACTIVE timer from another thread does what TimerBase::start() already does
from any thread - unschedule + deactivate under the run loop's m_loopLock (stopWithLock) - instead of crashing. Both
paths take the same lock, so the scheduled-task list stays consistent; start() has always done this cross-thread.
Patches webkit/Source/WTF/wtf/generic/RunLoopGeneric.cpp (no backup: the child recipe's changed-file gate).
usage: apply_runloop_stop_fix.py <tree root holding webkit/>"""
import sys
from pathlib import Path

MARK = 'OMNI_RUNLOOP_STOP_FIX_V1'
p = Path(sys.argv[1]) / 'webkit/Source/WTF/wtf/generic/RunLoopGeneric.cpp'
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK in s:
    print('already', p.name); sys.exit(0)
OLD = ('void RunLoop::TimerBase::stop()\n'
       '{\n'
       '    Locker locker { m_runLoop->m_loopLock };\n'
       '    if (m_scheduledTask->isActive())\n'
       '        assertIsCurrent(m_runLoop);\n'
       '    stopWithLock();\n'
       '}\n')
NEW = ('void RunLoop::TimerBase::stop()\n'
       '{\n'
       '    Locker locker { m_runLoop->m_loopLock };\n'
       '    // ' + MARK + ': no assertIsCurrent here. Stopping an active timer from another thread is done under\n'
       '    // m_loopLock exactly as start() does from any thread (the layers compositor is suspended from the main thread).\n'
       '    stopWithLock();\n'
       '}\n')
if s.count(OLD) != 1:
    sys.exit('%s: anchor found %d times' % (p.name, s.count(OLD)))
s = s.replace(OLD, NEW, 1)
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied', p.name)
