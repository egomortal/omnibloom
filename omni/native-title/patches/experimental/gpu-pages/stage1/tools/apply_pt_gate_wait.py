#!/usr/bin/env python3
"""OMNI_PT_GATE_WAIT_V1 (2026-11-21): let the page-table gate wait briefly for a closing stream before refusing.

YouTube switches quality by opening the new decoder while the old stream is still being released. On g9q/g9p the 4K
open was refused at pools of 6,146-6,267 (+260 >= 6400) during such a switch, fell back to software and stalled (2 of
9 4K runs on 2026-11-21), although 4K plays at pool peaks of ~6,200 once the old stream is gone.
Now: an open from the V5 configure WORKER (never the service thread, which must keep running to release the old
stream) re-reads the pool every 250 ms for up to 3 s and passes as soon as it fits. Service-thread opens are unchanged.
Off without a rebuild: /data/omni/pt-gate-wait-off.flag (read once).
usage: apply_pt_gate_wait.py <engine dir holding media/OmniHwService.cpp>   (title $NE/engine, after the gate recal)"""
import sys
from pathlib import Path

MARK = 'OMNI_PT_GATE_WAIT_V1'
p = Path(sys.argv[1]) / 'media/OmniHwService.cpp'
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK in s:
    print('already', p.name); sys.exit(0)


def rep(old, new):
    global s
    if s.count(old) != 1:
        sys.exit('%s: anchor found %d times: %r' % (p.name, s.count(old), old[:90]))
    s = s.replace(old, new, 1)


rep('static int omniPtOpenGate(int w, int h, std::string& stage)\n{\n',
    'static int omniPtOpenGate(int w, int h, std::string& stage, bool mayWait = false)   // ' + MARK + ': mayWait only from the V5 worker\n{\n')
rep('    if (used + cost < limit) return 0;\n',
    '    if (used + cost < limit) return 0;\n'
    '    static const bool omniWaitOn = access("/data/omni/pt-gate-wait-off.flag", F_OK) != 0;   // ' + MARK + '\n'
    '    if (mayWait && omniWaitOn) {\n'
    '        for (int i = 0; i < 12; ++i) {\n'
    '            usleep(250000);\n'
    '            const int u2 = omniPtUsed(&total);\n'
    '            if (u2 >= 0 && u2 + cost < limit) {\n'
    '                fprintf(stderr, "OMNI PT GATE: %dx%d decoder admitted after %d ms: %d -> %d page tables (' + MARK + ')\\n", w, h, (i + 1) * 250, used, u2);\n'
    '                fflush(stderr);\n'
    '                return 0;\n'
    '            }\n'
    '        }\n'
    '    }\n')
rep('        int rc = omniPtOpenGate(int(in.d), int(in.e), stage);   // OMNI_PT_OPEN_GATE_V1\n',
    '        int rc = omniPtOpenGate(int(in.d), int(in.e), stage, true);   // OMNI_PT_OPEN_GATE_V1 + ' + MARK + '\n')
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied', p.name)
