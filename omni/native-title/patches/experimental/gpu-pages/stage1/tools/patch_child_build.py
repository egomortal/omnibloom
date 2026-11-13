#!/usr/bin/env python3
"""omni-gpu-pages stage 1: teach a COPY of the ack child's child_build.py one switch. With OGP_S1_LINK=1 it drops
Omni's lazy GL shim (OmniLazyGraphics.cpp.o) and the two GL .so stubs from the link and adds the inputs listed in
$OGP_S1_LINK_INPUTS. Without the switch the copy links exactly as the original. Idempotent.
usage: patch_child_build.py <path to the copied child_build.py>"""
import sys
p = sys.argv[1]; t = open(p).read()
anchor = "lcmd += [str(secobj), '-Wl,--wrap=connect']\n"
if 'OGP_S1_LINK' in t:
    print('already patched'); sys.exit(0)
if t.count(anchor) != 1: sys.exit('child_build.py: link anchor not found exactly once')
t = t.replace(anchor, anchor + """if os.environ.get('OGP_S1_LINK') == '1':   # OMNI_GPU_PAGES_STAGE1_V1: our static Mesa replaces Omni's lazy GL shim
    gone = [x for x in lcmd if x.endswith('OmniLazyGraphics.cpp.o') or x.endswith(('/libEGL.so', '/libGLESv2.so'))]
    assert len(gone) == 3, f'expected the lazy GL shim and the two GL stubs, found {gone}'
    lcmd = [x for x in lcmd if x not in gone] + json.load(open(os.environ['OGP_S1_LINK_INPUTS']))
    print('OGP_S1_LINK: dropped', [x.rsplit('/', 1)[-1] for x in gone])
""")
open(p, 'w').write(t); print('patched: OGP_S1_LINK switch added')
