#!/usr/bin/env python3
"""omni-launch packaging guard for an ELF: PT_LOAD segments must not overlap (vaddr or file ranges), the set of
executable sections must equal the reference's, and the PT_LOAD flags must equal the reference's (the payload layout's
first LOAD is RWE in the release child 7b810ea5 itself, so the guard is 'no new W+X mapping', not 'none').
  elfguard.py TARGET.elf REFERENCE.elf      -> prints one line per check, exit 1 on any failure (reads only)."""
import re, subprocess, sys
RE = '/usr/lib/llvm-21/bin/llvm-readelf'
def info(p):
    segs, secs = [], []
    out = subprocess.run([RE, '-lSW', p], capture_output=True, text=True).stdout
    for l in out.splitlines():
        m = re.match(r'\s*LOAD\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+([RWE ]+?)\s+0x', l)
        if m: segs.append((int(m[1], 16), int(m[2], 16), int(m[4], 16), int(m[5], 16), m[6].replace(' ', '')))
        m = re.match(r'\s*\[\s*\d+\]\s+(\S+)\s+\S+\s+[0-9a-f]+\s+[0-9a-f]+\s+[0-9a-f]+\s+[0-9a-f]+\s+(\S*)', l)
        if m and 'X' in m[2]: secs.append(m[1])
    return segs, sorted(secs)
t, r = sys.argv[1], sys.argv[2]
ts, tx = info(t); rs, rx = info(r); bad = 0
def ck(ok, what):
    global bad; bad += not ok; print(('PASS ' if ok else 'FAIL ') + what)
ck(len(ts) > 0, f'{len(ts)} PT_LOAD segments read')
v = sorted((s[1], s[1] + s[3]) for s in ts); f = sorted((s[0], s[0] + s[2]) for s in ts if s[2])
ck(all(a[1] <= b[0] for a, b in zip(v, v[1:])), 'PT_LOAD virtual ranges do not overlap')
ck(all(a[1] <= b[0] for a, b in zip(f, f[1:])), 'PT_LOAD file ranges do not overlap')
ck([s[4] for s in ts] == [s[4] for s in rs], f'PT_LOAD flags {[s[4] for s in ts]} == reference {[s[4] for s in rs]} (no new writable+executable mapping)')
ck(tx == rx, f'executable sections {tx} == reference {rx}')
ck(len(ts) == len(rs), f'PT_LOAD count {len(ts)} == reference {len(rs)}')
print('ELFGUARD', 'PASS' if not bad else f'FAIL ({bad})')
sys.exit(1 if bad else 0)
