#!/usr/bin/env python3
"""OMNI_INPROC_AUXMAIN_V1 (2026-11-24): a WebKit role started INSIDE the title returns after initializing instead of
running its own nested RunLoop::run().

Console gin29 (f06c445a, Lytiwn = WebProcess AND NetworkProcess in the title): the WebProcess asked for its network
connection (ensureNetworkProcessConnection, UI NetworkProcessProxy::getNetworkProcessConnection) but the reply never came
and the page was never created (with the NetworkProcess as a child the same steps complete). Each role's
AuxiliaryProcessMain ends in RunLoop::run(), which never returns; started as a main-thread task, the NetworkProcess's
nested loop can begin while the WebProcess is inside a sync wait, so that wait's frame sits below a loop that never
returns. In the title the app's own main loop (WKRunLoopRunMain = RunLoop::main) already serves every main-thread task,
so an in-process role needs no loop of its own: initialize, then return.

Only while omni_inproc_main_spin is set (set by OMNI_INPROC_NET_V1's in-process start; never in a child):
  - AuxiliaryProcessMain<T> keeps its main object in STATIC storage (the original is a NeverDestroyed on the stack,
    which would be freed on return while WebKit may still reach it),
  - run() returns EXIT_SUCCESS right after initializeAuxiliaryProcess() (no RunLoop::run, no platformFinalize).
usage: apply_inproc_auxmain.py <WebKit/Shared/AuxiliaryProcessMain.h>"""
import sys
from pathlib import Path

MARK = 'OMNI_INPROC_AUXMAIN_V1'
p = Path(sys.argv[1])
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK in s:
    print('already', p.name); sys.exit(0)


def rep(old, new):
    global s
    if s.count(old) != 1:
        sys.exit('%s: anchor found %d times: %r' % (p.name, s.count(old), old[:70]))
    s = s.replace(old, new, 1)


rep('#include <wtf/NeverDestroyed.h>\n',
    '#include <wtf/NeverDestroyed.h>\n'
    'extern "C" volatile int omni_inproc_main_spin;   // ' + MARK + ' (IPC/Connection.cpp, OMNI_INPROC_SPIN): role runs in the title\n')
rep('        initializeAuxiliaryProcess(WTF::move(m_parameters));\n'
    '        RunLoop::run();\n',
    '        initializeAuxiliaryProcess(WTF::move(m_parameters));\n'
    '        if (omni_inproc_main_spin)   // ' + MARK + ': in the title, the app\'s main loop serves this role\n'
    '            return EXIT_SUCCESS;\n'
    '        RunLoop::run();\n')
rep('    NeverDestroyed<AuxiliaryProcessMainType> auxiliaryMain;\n\n    return auxiliaryMain->run(argc, argv);\n',
    '    if (omni_inproc_main_spin) {   // ' + MARK + ': returns after initializing, so it must outlive this call\n'
    '        static NeverDestroyed<AuxiliaryProcessMainType> inprocMain;\n'
    '        return inprocMain->run(argc, argv);\n'
    '    }\n'
    '    NeverDestroyed<AuxiliaryProcessMainType> auxiliaryMain;\n\n    return auxiliaryMain->run(argc, argv);\n')
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied', p.name)
