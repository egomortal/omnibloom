"""Group OMNI MEMTRACE lines (title direct-memory calls) by caller offset; print the biggest. usage: memtrace_group.py <log>..."""
import re, sys, collections
pat = re.compile(r'OMNI MEMTRACE: (\S+) len (\d+) KB align (\S+) type/prot (\S+) -> (\S+) phys (\S+) va (\S+) caller (\S+) \(\+(\S+)\)')
tot = collections.defaultdict(lambda: [0, 0, set(), set()])
for fn in sys.argv[1:]:
    for line in open(fn, encoding='utf-8', errors='replace'):
        m = pat.search(line)
        if not m: continue
        call, kb, al, tp, res, ph, va, ra, off = m.groups()
        if res not in ('0', '0x0'): continue
        k = (call, ra); t = tot[k]; t[0] += int(kb); t[1] += 1; t[2].add(tp); t[3].add(al)
for (call, off), (kb, n, tps, als) in sorted(tot.items(), key=lambda x: -x[1][0])[:40]:
    print('%-36s +%-10s %8.1f MB  n=%-4d type/prot=%s align=%s' % (call, off, kb / 1024, n, ','.join(sorted(tps)), ','.join(sorted(als))))
