#!/usr/bin/env python3
"""OMNI_STARTER_V4_REQ (2026-11-20): the title accepts the engine starter only from OMNI_STARTER_V4 on.

Starter V4 (outputs/omni-starter) answers "pt" with the kernel page-table pool for the title's page-table governor
(OMNI_PT_BACKSTOP_V5). The title's V3 check accepted any starter answering version >= 3, so a resident V3 starter would
keep running and the governor would stay blind. With >= 4, a V3 starter counts as older: the title starts the current
file, which tells the old one to quit and takes its port (the V3 takeover path, unchanged).
Run after apply_starter.py. usage: apply_starter_v4_req.py <title src dir (NativeLauncherState.cpp)>"""
import sys
from pathlib import Path

p = Path(sys.argv[1]) / 'NativeLauncherState.cpp'
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
OLD = '  if(v>=3){state=1;'
NEW = '  if(v>=4){state=1;'   # OMNI_STARTER_V4_REQ
if NEW in s:
    print('already v>=4'); sys.exit(0)
if s.count(OLD) != 1:
    sys.exit('anchor found %d times' % s.count(OLD))
s = s.replace(OLD, NEW, 1)
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied v>=4', p.name)
