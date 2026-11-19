#!/usr/bin/env python3
"""OMNI_ABR_CEILING_FLAG_V1 (2026-11-19, owner: "make it leaner without any downside" / layers-on page-table headroom).

Why: memtrace (2026-11-19, 4K HDR YouTube, layers off) named the title's biggest direct-memory user: the V5 pace queue of
decoded pictures (OmniAbrSwitch.h Config: steadyCeiling 1 GiB, switchCeiling 2 GiB during a quality switch, poolReserve
320 MiB). Every resolution filled it: 43 x 24 MB at 2160p, 94 x 11 MB at 1440p, 156 x 6 MB at 1080p ("up to N pictures =
~1000 MiB ... decoded until 3.0 s ahead"). The hardware decoder itself is 820 MB at 4K (386 gpu + 205 cpu_gpu + 32 input
+ 196 = 8 output frames). One page-table page per 2 MiB touched (ptprobe), so 1 GiB = ~512 page tables.

This patch only makes the three numbers settable for TESTS, so one build can measure page tables and smoothness at
several caps. With no flag the Config is untouched (today's behaviour, byte for byte the same decisions).
  /data/omni/abr-ceiling-<steadyMiB>-<switchMiB>-<reserveMiB>.flag   e.g. abr-ceiling-512-768-128.flag
read once when the pool is first used; logged as "OMNI HW ABR: ceiling flag ...". Values outside 64..4096 MiB are ignored.
Patches engine/media/OmniHwService.cpp; must run BEFORE prep_launch.py (like apply_memmap.py).
usage: apply_abr_ceiling.py <$NE (holding engine/media)>   prints "applied" / "already"."""
import sys
from pathlib import Path

MARK = 'OMNI_ABR_CEILING_FLAG_V1'
p = Path(sys.argv[1]) / 'engine/media/OmniHwService.cpp'
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK in s:
    print('already', p.name); sys.exit(0)

OLD = ('        Abr::pool().install(h);\n'
       '        Abr::pool().setEnabled(abrOn());\n'
       '        return &Abr::pool();\n')
NEW = ('        Abr::pool().install(h);\n'
       '        Abr::pool().setEnabled(abrOn());\n'
       '        abrCeilingFromFlag();   // ' + MARK + '\n'
       '        return &Abr::pool();\n')
FN = ('// ' + MARK + ' (test): /data/omni/abr-ceiling-<steadyMiB>-<switchMiB>-<reserveMiB>.flag sets the pace queue\'s\n'
      '// direct-memory ceilings; without the flag the Config stays exactly as OmniAbrSwitch.h has it.\n'
      'static void abrCeilingFromFlag()\n'
      '{\n'
      '    DIR* d = opendir("/data/omni");\n'
      '    if (!d) return;\n'
      '    unsigned st = 0, sw = 0, rs = 0; bool found = false;\n'
      '    while (struct dirent* e = readdir(d)) {\n'
      '        unsigned a = 0, b = 0, c = 0; char tail[8] = { 0 };\n'
      '        if (sscanf(e->d_name, "abr-ceiling-%u-%u-%u.fla%1s", &a, &b, &c, tail) == 4 && tail[0] == \'g\') { st = a; sw = b; rs = c; found = true; break; }\n'
      '    }\n'
      '    closedir(d);\n'
      '    if (!found) return;\n'
      '    auto ok = [](unsigned v) { return v >= 64 && v <= 4096; };\n'
      '    if (!ok(st) || !ok(sw) || rs > 4096 || sw < st) { fprintf(stderr, "OMNI HW ABR: ceiling flag %u-%u-%u ignored (out of range)\\n", st, sw, rs); return; }\n'
      '    Abr::Config c = Abr::pool().config();\n'
      '    c.steadyCeiling = size_t(st) << 20; c.switchCeiling = size_t(sw) << 20; c.poolReserve = size_t(rs) << 20;\n'
      '    Abr::pool().setConfig(c);\n'
      '    fprintf(stderr, "OMNI HW ABR: ceiling flag: steady %u MiB, switch %u MiB, pool reserve %u MiB\\n", st, sw, rs);\n'
      '}\n')
ANCHOR = 'Abr::Pool& abrPool()\n{\n'
for old in (OLD, ANCHOR):
    if s.count(old) != 1:
        sys.exit('%s: anchor found %d times: %r' % (p.name, s.count(old), old.strip()[:80]))
s = s.replace(OLD, NEW, 1).replace(ANCHOR, FN + ANCHOR, 1)
if '#include <dirent.h>' not in s:
    first = s.index('#include ')
    s = s[:first] + '#include <dirent.h>  // ' + MARK + '\n' + s[first:]
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied', p.name)
