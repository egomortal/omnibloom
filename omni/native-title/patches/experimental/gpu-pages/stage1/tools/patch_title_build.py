#!/usr/bin/env python3
"""omni-gpu-pages stage 1: add the title-side sources to a build.py that prep_s34.py has just written.
Adds, after Omni's own native sources and compiled with the same compiler: OmniGpuPagesService.cpp (ours) and the
gpu-broker owner (PS5_Vulkan tooling/gpu-broker: server.cpp, display.cpp, packet_io.c, LGPL-2.1-or-later), against
the PS5_Mesa tree the title's RADV is built from. Nothing else in build.py changes. Idempotent.
usage: patch_title_build.py <build.py> <stage1/src-title dir>"""
import sys
p, srcdir = sys.argv[1], sys.argv[2]
t = open(p).read()
if 'OMNI_GPU_PAGES_STAGE1_V1' in t:
    print('already patched'); sys.exit(0)
anchor = "    mine.append(str(o))\n"
if t.count(anchor) != 1: sys.exit(f'build.py: "mine.append" anchor found {t.count(anchor)} times, expected 1')
import os
brk = os.environ.get('OGP_BRK', '')   # OMNI_GPUPAGES_MEMSPLIT_V1 experiment: a patched broker copy
block = anchor + f'''# OMNI_GPU_PAGES_STAGE1_V1: the gpu-broker owner for Omni's WebProcesses (OmniGpuPagesService.cpp; off unless its flag)
OGP_S1 = Path({srcdir!r}); BRK = Path({brk!r}) if {brk!r} else UP / 'tooling/gpu-broker'; MESA = AV2 / 'upstream/PS5_Mesa'
s1inc = [f'-I{{BRK}}', f'-I{{MESA}}/src/amd/vulkan/winsys/ps5', f'-I{{MESA}}/src', f'-I{{MESA}}/src/amd/vulkan', f'-I{{MESA}}/src/vulkan/util',
         f'-I{{MESA}}/src/util', f'-I{{MESA}}/include']
for s1src in [OGP_S1 / 'OmniGpuPagesService.cpp', BRK / 'server.cpp', BRK / 'display.cpp']:
    o = B / ('s1-' + s1src.stem + '.o')
    run([CXX, '-std=c++20', '-O2', '-ffunction-sections', '-fdata-sections', '-D__PROSPERO__', *s1inc, '-c', s1src, '-o', o], out=B / ('s1-' + s1src.stem + '.compile.log'))
    mine.append(str(o))
o = B / 's1-packet_io.o'
run([CC, '-std=c11', '-O2', '-ffunction-sections', '-fdata-sections', '-D__PROSPERO__', *s1inc, '-c', BRK / 'packet_io.c', '-o', o], out=B / 's1-packet_io.compile.log')
mine.append(str(o))
say('stage 1: OmniGpuPagesService + gpu-broker owner compiled into the title (off unless /data/omni/gpu-pages-stage1.flag)')
'''
t = t.replace(anchor, block, 1)
open(p, 'w').write(t); print('build.py: stage-1 title sources added')
