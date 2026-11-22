#!/usr/bin/env python3
"""OMNI_PT_GATE_4K_LINE_V1 (2026-11-21): give 4K decoder opens their own, higher page-table gate line.

The gate (OMNI_PT_OPEN_GATE_V1) let 1440p opens through up to max(line, 6700) but held 4K opens to the plain line
(6400) because a 4K stream was estimated at ~450 tables. Since OMNI_PT_GATE_RECAL_V1 the 4K estimate is 260, and
on g9p/g9o (2026-11-21) YouTube quality switches back to 4K were refused at pools of 6,146-6,267 -> software
fallback -> stall at 0 s (3 of 13 4K runs). Waiting 3 s (OMNI_PT_GATE_WAIT_V1) did not help: nothing is released
in that window. 4K plays at pool peaks of ~6,200; the hang zone starts near 6,770; 1440p already uses 6,700.
Now: 4K limit = max(line, 6550) -> admitted while used < ~6,290; the picture-buffer backstop keeps the plain line.
Override without a rebuild: /data/omni/pt-gate-4k-line.txt (5000..7000).
usage: apply_pt_gate_4k_line.py <engine dir holding media/OmniHwService.cpp>   (title $NE/engine, after the gate recal)"""
import sys
from pathlib import Path

MARK = 'OMNI_PT_GATE_4K_LINE_V1'
p = Path(sys.argv[1]) / 'media/OmniHwService.cpp'
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK in s:
    print('already', p.name); sys.exit(0)
old = '    const int limit = big ? line : std::max(line, 6700);\n'
if s.count(old) != 1:
    sys.exit('gate limit line found %d times' % s.count(old))
new = ('    static const int omniGate4kLine = [] {   // ' + MARK + '\n'
       '        int v = 6550;\n'
       '        if (FILE* f = fopen("/data/omni/pt-gate-4k-line.txt", "r")) { int x = 0; if (fscanf(f, "%d", &x) == 1 && x >= 5000 && x <= 7000) v = x; fclose(f); }\n'
       '        return v;\n'
       '    }();\n'
       '    const int limit = big ? std::max(line, omniGate4kLine) : std::max(line, 6700);\n')
s = s.replace(old, new, 1)
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied', p.name)
