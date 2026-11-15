#!/usr/bin/env python3
"""OMNI_SPARE_DEFER_V1 (2026-11-15, the reboot investigation): start the reserve spare engine 30 s after a launch,
not at once.

Evidence (kernel log via omni-klogsrv, 2026-11-14/15): every title launch takes the console's system memory pool to the
edge ("WARNING: LOW FMEM ... timed-out N pages"; free pages down to 15 of 138739 at 00:33:51Z). At that moment: the page
engine loading YouTube (593 MiB, growing ~190 MiB/s), the network engine (240 MiB), the payload loader (236 MiB), and
the RESERVE SPARE engine (240 MiB) that omni-process-launcher-v2.inc's topUp(target, 1) starts right after the first
launch is acknowledged. Each engine is ~240 MiB just by existing (the loader copies the 196 MB program per process).

The two early spares (omni_launcher_prespawn, OMNI_PERF_D_T1) are unchanged: they serve the first page and network
launches. Only the "keep one spare ready for the next launch" refill waits 30 s, so it no longer lands on the page
load's peak. A launch that needs a process in the meantime starts one as it already does when no spare is ready.
/data/omni/spare-defer-off.flag: the old behaviour (refill at once).
usage: apply_spare_defer.py <tree root (the title's T tree)>"""
import sys
from pathlib import Path

MARK = 'OMNI_SPARE_DEFER_V1'
p = Path(sys.argv[1]) / 'engine/ports/webkit-requirements/src/omni-process-launcher-v2.inc'
t = p.read_text(encoding='utf-8')
if MARK in t:
    print('already'); sys.exit(0)
old = '            topUp(target, 1); // keep one spare ready for the next launch\n'
if t.count(old) != 1:
    sys.exit('omni-process-launcher-v2.inc: anchor found %d times' % t.count(old))
new = ('            // OMNI_SPARE_DEFER_V1: the reserve spare 30 s later (not on the page load\'s memory peak); off: spare-defer-off.flag\n'
       '            if (access("/data/omni/spare-defer-off.flag", F_OK) == 0)\n'
       '                topUp(target, 1); // keep one spare ready for the next launch\n'
       '            else {\n'
       '                std::thread([t = std::string(target ? target : "")]() {\n'
       '                    usleep(30 * 1000 * 1000);\n'
       '                    topUp(t.empty() ? nullptr : t.c_str(), 1);   // a later launch may have started one meanwhile: topUp counts\n'
       '                    omni_launcher_trace("launch: reserve spare topped up 30 s after the launch (OMNI_SPARE_DEFER_V1)\\n");\n'
       '                }).detach();\n'
       '            }\n')
t = t.replace(old, new, 1)
if '#include <thread>' not in t:
    if t.count('#include <mutex>\n') != 1:
        sys.exit('omni-process-launcher-v2.inc: #include <mutex> not found once')
    t = t.replace('#include <mutex>\n', '#include <mutex>\n#include <thread>   // OMNI_SPARE_DEFER_V1\n#include <unistd.h>\n', 1)
p.write_text(t, encoding='utf-8')
print('applied ' + MARK)
