#!/usr/bin/env python3
"""OMNI_JSC_DFGFTL_DEFAULT_ON_V1 (2026-11-17, owner "Yes, build and soak"): the DFG and FTL JIT tiers ON by default.

OMNI_JSC_DFGFTL_V1 (apply_jscftl_tiers.py) turned them on only with /data/omni/jsc-dfg.flag (+ jsc-ftl.flag). Console
2026-11-17 (jscftl child 25a9a20b): js-bench geomean 34.5 -> 14.2 (DFG) -> 12.7 ms (DFG+FTL), all checksums right;
YouTube home FCP 1.80 -> 1.17 s, YouTube watch page frames 42 -> 495, longest page gap 9.5 -> 1.1 s; 0 LOW FMEM with the
tiers on; page tables +8 / +96 of 8192. Now:
  DFG on unless /data/omni/jsc-dfg-off.flag; FTL on (with DFG) unless /data/omni/jsc-ftl-off.flag.
The JIT switch itself (Settings > "JavaScript JIT" / jsc-jit-off.flag) still turns every tier off. The old on-flags are
simply ignored now.

Patches engine/entry/OmniMain.cpp after apply_jscftl_tiers.py (needs its OMNI_JSC_DFGFTL_V1 lines).
Output like the other jscftl scripts: "applied|already MARK relpath" per file, then "applied" or "already".
usage: apply_jscftl_default_on.py <tree root (holding engine/)>"""
import os
import shutil
import sys
from pathlib import Path

MARK = 'OMNI_JSC_DFGFTL_DEFAULT_ON_V1'
root = Path(sys.argv[1])
rel = 'engine/entry/OmniMain.cpp'
p = root / rel
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK in s:
    print('already %s %s' % (MARK, rel))
    print('already')
    sys.exit(0)
if 'OMNI_JSC_DFGFTL_V1' not in s:
    sys.exit('%s: OMNI_JSC_DFGFTL_V1 missing (apply_jscftl_tiers.py first)' % rel)
EDITS = [
    ('        const bool omniDfg = !access("/data/omni/jsc-dfg.flag", F_OK);\n',
     '        const bool omniDfg = access("/data/omni/jsc-dfg-off.flag", F_OK) != 0;   // ' + MARK + ': on unless the off flag\n'),
    ('        const bool omniFtl = omniDfg && !access("/data/omni/jsc-ftl.flag", F_OK);\n',
     '        const bool omniFtl = omniDfg && access("/data/omni/jsc-ftl-off.flag", F_OK) != 0;   // ' + MARK + '\n'),
]
for old, _ in EDITS:
    if s.count(old) != 1:
        sys.exit('%s: anchor found %d times: %r' % (rel, s.count(old), old.strip()[:70]))
for old, new in EDITS:
    s = s.replace(old, new, 1)
bdir = os.environ.get('OMNI_PATCH_BACKUP_DIR')
bak = (Path(bdir) / (rel.replace('/', '__') + '.before-dfgftl-default-on')) if bdir else p.with_name(p.name + '.before-dfgftl-default-on')
if not bak.exists():
    bak.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(p, bak)
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied %s %s' % (MARK, rel))
print('applied')
