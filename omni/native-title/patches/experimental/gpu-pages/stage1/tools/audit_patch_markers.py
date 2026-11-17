#!/usr/bin/env python3
"""OMNI_PATCH_MARKER_AUDIT_V1 (2026-11-17, reviewer's proposal): every OMNI_*_V<n> marker that a step of THIS build
reported as "applied" or "already" (in steps.txt, since the last "TITLE-FIX build start") must still be present in the
final sources just before the title is compiled. A later step that re-copies a file can silently undo an earlier
patch: prep_launch.py's fresh src/OmniGpuPresent.cpp undid OMNI_GPU_DEFAULT_ON_V1 in builds g1 and g3, and only a
console test noticed.

A marker counts as present when it, or a longer marker that starts with it plus "_" (e.g. ..._V1_R2), appears in a
source file (.cpp .h .hpp .c .comp .mm .js .inc; backups *.before* / *.bak* are skipped) under the given roots.

usage: audit_patch_markers.py [--fatal] <steps.txt> <source root>...
Prints one summary line, then one "MISSING <marker>" line each. Exit 1 only with --fatal and something missing."""
import os
import re
import sys

args = sys.argv[1:]
fatal = '--fatal' in args
args = [a for a in args if a != '--fatal']
steps = open(args[0], encoding='utf-8', errors='replace').read().splitlines()
start = max((i for i, l in enumerate(steps) if 'TITLE-FIX build start' in l), default=0)
want = set()
for line in steps[start:]:
    if 'FAILED' in line or not re.search(r'\b(applied|already)\b', line):
        continue
    want.update(re.findall(r'\bOMNI_[A-Z0-9_]+_V[0-9]+\b', line))
have = set()
for root in args[1:]:
    for d, _, files in os.walk(root):
        for n in files:
            if not n.endswith(('.cpp', '.h', '.hpp', '.c', '.comp', '.mm', '.js', '.inc')) or '.before' in n or '.bak' in n:
                continue
            try:
                with open(os.path.join(d, n), 'rb') as f:
                    have.update(m.decode() for m in re.findall(rb'OMNI_[A-Z0-9_]+_V[0-9]+', f.read()))
            except OSError:
                pass
missing = sorted(m for m in want if m not in have and not any(h.startswith(m + '_') for h in have))
print('markers reported applied/already: %d; in the final sources: %d; missing: %d' % (len(want), len(want) - len(missing), len(missing)))
for m in missing:
    print('MISSING', m)
sys.exit(1 if fatal and missing else 0)
