#!/usr/bin/env python3
"""OMNI_STACK_MIN_2M_V1 (2026-11-21, page-table pool): stage 1's pthread_create wrapper (ogp-s1-child.c, CP-2 try 5)
raises EVERY engine-child thread to an 8 MiB stack because radv_shader_object_create has a ~99 KB frame (Mesa has no
stack probes). Child memory maps: ~25-30 such stacks per process at 4 kernel page tables each (the shared pool is
charged per mapped 2 MiB) = 76-130 tables per process. A 2 MiB minimum keeps ~20x the radv frame and costs 1 table.

Default minimum 2 MiB (was 8). Override without a rebuild: /data/omni/gpu-pages-stack-kb.txt (256..65536 KiB, e.g. 8192
for the old behaviour); the OMNI_GPU_PAGES_STACK_KB environment variable still wins when set.
usage: apply_stack_min.py <ogp-s1-child.c path (the recipe's private copy)>"""
import sys
from pathlib import Path

MARK = 'OMNI_STACK_MIN_2M_V1'
p = Path(sys.argv[1])
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK in s:
    print('already', p.name); sys.exit(0)
old = ('    if (!v) { const char* e = getenv("OMNI_GPU_PAGES_STACK_KB"); long kb = e ? atol(e) : 0; '
       'v = (kb >= 256 && kb <= 65536) ? (size_t)kb << 10 : (size_t)8 << 20; }\n')
new = ('    if (!v) {   /* ' + MARK + ': 2 MiB default (was 8); /data/omni/gpu-pages-stack-kb.txt overrides */\n'
       '        const char* e = getenv("OMNI_GPU_PAGES_STACK_KB"); long kb = e ? atol(e) : 0;\n'
       '        if (!(kb >= 256 && kb <= 65536)) { FILE* f = fopen("/data/omni/gpu-pages-stack-kb.txt", "r"); if (f) { if (fscanf(f, "%ld", &kb) != 1) kb = 0; fclose(f); } }\n'
       '        v = (kb >= 256 && kb <= 65536) ? (size_t)kb << 10 : (size_t)2 << 20;\n'
       '    }\n')
if s.count(old) != 1:
    sys.exit('anchor found %d times' % s.count(old))
s = s.replace(old, new, 1)
if '#include <stdio.h>' not in s:
    s = '#include <stdio.h>  /* ' + MARK + ' */\n' + s
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied', p.name)
