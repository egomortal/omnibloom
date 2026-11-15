#!/usr/bin/env python3
"""OMNI_SPARE_LAZY_V1 (2026-11-15, "cut the spike"): no reserve spare engine by default.

Evidence (klog-2026-11-15-starter.log, SceShellCore FMEM dumps at every LOW FMEM event): Omni's engines hold
1.0-1.2 GB of the ~1.6 GB in use: the page engine 680-930 MB, the network engine 55-195 MB, and an idle process of
exactly 244.1 MB every time = the reserve spare that OMNI_SPARE_DEFER_V1 starts 30 s after the first launch, which
lands right on the page load's peak (LOW FMEM ~45 s after the title starts). With Omni's engine starter
(OMNI_STARTER_V1) a new engine starts in 0.6-1.8 s, so the reserve buys little.

Now the refill only runs when /data/omni/spare-reserve.flag exists (then 30 s after the launch, as V1). Without it, a
launch that needs a process starts one then, as it already does when no spare is ready. The two early spares that
serve the first page and network launches are unchanged.
Apply AFTER apply_spare_defer.py. usage: apply_spare_lazy.py <tree root (the title's T tree)>"""
import sys
from pathlib import Path

MARK = 'OMNI_SPARE_LAZY_V1'
p = Path(sys.argv[1]) / 'engine/ports/webkit-requirements/src/omni-process-launcher-v2.inc'
raw = p.read_bytes().decode('utf-8')
crlf = '\r\n' in raw
t = raw.replace('\r\n', '\n')
if MARK in t:
    print('already ' + MARK)
    sys.exit(0)
old = ('            else {\n'
       '                std::thread([t = std::string(target ? target : "")]() {\n'
       '                    usleep(30 * 1000 * 1000);\n')
new = ('            else if (!access("/data/omni/spare-reserve.flag", F_OK)) {   // ' + MARK + ': no reserve spare unless asked\n'
       '                std::thread([t = std::string(target ? target : "")]() {\n'
       '                    usleep(30 * 1000 * 1000);\n')
if t.count(old) != 1:
    sys.exit('omni-process-launcher-v2.inc: OMNI_SPARE_DEFER_V1 block found %d times (apply apply_spare_defer.py first)' % t.count(old))
t = t.replace(old, new, 1)
if crlf:
    t = t.replace('\n', '\r\n')
p.write_bytes(t.encode('utf-8'))
print('applied ' + MARK)
