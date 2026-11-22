#!/usr/bin/env python3
"""OMNI_PT_GATE_RECAL_V1 (2026-11-21): recalibrate OMNI_PT_OPEN_GATE_V1's decoder cost estimate.

The gate's estimate (410 * pixels/4K + 40 = ~450 page tables for 4K) came from 2026-11-20, when a 4K stream's whole shared
block (input ring + 6 picture slots, ~250 MiB) was mapped as flexible memory in the title AND the engine child. Title
memory maps on 2026-11-21 show the decoder's other buffers are DIRECT memory (0 page tables), and OMNI_SHM_LAZY_SLOTS_V1
maps the slots only on first use. g9t (75c1e253 + 4f9f2233) then refused every 4K open at a pool of 6,102-6,166
("+ ~450 would reach 6400") although 4K now plays at a pool peak of ~6,170.
New estimate: 220 * pixels/4K + 40 (= 260 at 4K, slots mapped since lazy slots default off; still covers the ring on both sides and slot fallback on one side; the
6,600 watchdog and the pace-queue backstop stay behind it). Override without a rebuild: /data/omni/pt-gate-4k-cost.txt
(the 4K figure, 40..600; scaled by pixels like before).
usage: apply_pt_gate_recal.py <engine dir holding media/OmniHwService.cpp>   (title $NE/engine, pre-prep, after the gate)"""
import sys
from pathlib import Path

MARK = 'OMNI_PT_GATE_RECAL_V1'
p = Path(sys.argv[1]) / 'media/OmniHwService.cpp'
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK in s:
    print('already', p.name); sys.exit(0)
old = '    const int cost = int(410.0 * double(w) * h / (3840.0 * 2160.0)) + 40;\n'
if s.count(old) != 1:
    sys.exit('gate cost line found %d times' % s.count(old))
new = ('    static const double omniGate4k = [] {   // ' + MARK + ': 4K figure, was 410+40 before lazy slots\n'
       '        double v = 220.0;\n'
       '        if (FILE* f = fopen("/data/omni/pt-gate-4k-cost.txt", "r")) { int x = 0; if (fscanf(f, "%d", &x) == 1 && x >= 40 && x <= 600) v = x - 40; fclose(f); }\n'
       '        return v;\n'
       '    }();\n'
       '    const int cost = int(omniGate4k * double(w) * h / (3840.0 * 2160.0)) + 40;\n')
s = s.replace(old, new, 1)
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied', p.name)
